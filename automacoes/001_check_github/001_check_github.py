# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 04/09/2026
# DESCRICAO      : Registra atividade diaria no GitHub. Faz commits reais em um
#                  repositorio proprio via API REST (Contents API), alimentando
#                  o calendario de contribuicoes do perfil.
# =============================================
from __future__ import annotations

import os
import sys
from pathlib import Path

# --- bootstrap padrao: encoding + caminho da lib (nesta ordem, antes dos imports)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import base64
import random
import time
from datetime import datetime

import lib_dscs as dl

# ─── configuracao ────────────────────────────────────────────────────────────
# DEBUG=True   -> NADA e gravado em dbo.controle_cargas e nenhum commit e feito.
# --dry-run    -> igual ao DEBUG, sem precisar editar o arquivo.
# --force      -> ignora o sorteio de folga e o travamento diario.
# --setup      -> cria o repositorio no GitHub, se ainda nao existir.
# --status     -> mostra a configuracao e o estado atual, sem commitar.
#
# --setup e --status nao registram status na tabela de controle: nao sao a carga
# diaria, sao manutencao. Marcar SUCCESS neles mentiria no monitoramento.
DEBUG = False
DRY_RUN = "--dry-run" in sys.argv
FORCE = "--force" in sys.argv
SETUP = "--setup" in sys.argv
STATUS = "--status" in sys.argv

IDCARGA = 1  # ★ mesmo numero da pasta e do id_carga em dbo.controle_cargas
NOME_ROBO = "check_github"

BASE = Path(__file__).resolve().parent

# ─── GitHub ──────────────────────────────────────────────────────────────────
# Token no .env da raiz (D:\ambiente_dev\.env), classico com scope "repo" ou
# fine-grained com "Contents: Read and write". https://github.com/settings/tokens
API = "https://api.github.com"
CABECALHOS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "robo-001-check_github",
}

GITHUB_REPO = "daily-log"                  # repositorio que recebe os commits
GITHUB_BRANCH = "main"                     # precisa ser o branch padrao para contar
ARQUIVO_REMOTO = "registro/atividades.md"  # arquivo alterado a cada commit
REPO_PRIVADO = False                       # True exige "Private contributions" no perfil

CACHE_REMOTO = BASE / "temp" / "atividades.md"  # copia do que foi enviado

# ─── comportamento ───────────────────────────────────────────────────────────
# Quem decide EM QUE DIA o robo roda e o Agendador do Windows - o Python so
# executa quando e chamado. Por isso aqui nao ha sorteio de folga nem regra de
# fim de semana: chamou, commita. A unica excecao e a trava diaria, que impede
# dois lotes no mesmo dia se a tarefa disparar duas vezes.
MIN_COMMITS = 4               # minimo de commits no dia
MAX_COMMITS = 8               # maximo de commits no dia
PAUSA_ENTRE_COMMITS = (2, 6)  # segundos, sorteado no intervalo

TENTATIVAS_API = 3
SEGUNDOS_ENTRE_TENTATIVAS = 30

MENSAGENS = [
    "chore: registro diario de atividade",
    "docs: atualiza log de acompanhamento",
    "chore: anotacoes do dia",
    "docs: registra progresso diario",
    "chore: atualiza diario de bordo",
    "chore: sincroniza registro de atividades",
]

TOKEN = ""   # preenchido em validar_configuracao()
OWNER = ""   # descoberto pelo token em resolver_owner()


# ============================================================
# API DO GITHUB
# ============================================================
def _chamar_api(metodo: str, rota: str, corpo: dict | None = None) -> tuple[int, dict]:
    """Rota da API do GitHub -> dl.chamar_api_json, com os cabecalhos do GitHub.

    O tratamento de erro (5xx levanta, 4xx devolve o status) fica na lib; o
    retry, no dl.executar_com_retry, uma camada acima.
    """
    return dl.chamar_api_json(
        url=rota if rota.startswith("http") else f"{API}{rota}",
        metodo=metodo,
        corpo=corpo,
        token=TOKEN,
        cabecalhos=CABECALHOS,
    )


def validar_configuracao() -> None:
    """Token e parametros conferidos antes de qualquer chamada de rede."""
    global TOKEN

    TOKEN = dl.obter_variavel("GITHUB_TOKEN")

    if MIN_COMMITS < 1 or MAX_COMMITS < MIN_COMMITS:
        raise ValueError(f"MIN_COMMITS/MAX_COMMITS invalidos: {MIN_COMMITS}/{MAX_COMMITS}")


def resolver_owner() -> str:
    """Descobre o dono do token. E o que define a autoria dos commits."""
    global OWNER

    if OWNER:
        return OWNER

    status, dados = _chamar_api("GET", "/user")
    if status != 200:
        raise ValueError(f"Token invalido ou sem permissao (HTTP {status}): {dados.get('message')}")

    OWNER = dados["login"]
    dl.log(f"[GITHUB] usuario do token: {OWNER}")
    return OWNER


def repositorio_existe() -> bool:
    status, _ = _chamar_api("GET", f"/repos/{OWNER}/{GITHUB_REPO}")
    return status == 200


def criar_repositorio() -> None:
    if repositorio_existe():
        dl.log(f"[SETUP] repositorio {OWNER}/{GITHUB_REPO} ja existe")
        return

    status, dados = _chamar_api("POST", "/user/repos", {
        "name": GITHUB_REPO,
        "description": "Registro diario de atividades",
        "private": REPO_PRIVADO,
        "auto_init": True,  # ja nasce com um commit, senao nao ha branch para escrever
    })
    if status != 201:
        raise RuntimeError(f"Falha ao criar o repositorio (HTTP {status}): {dados.get('message')}")

    dl.log(f"[SETUP] repositorio criado: {dados.get('html_url')}")
    time.sleep(3)  # o auto_init leva um instante para publicar o primeiro commit


def ler_arquivo_remoto() -> tuple[str, str | None]:
    """Retorna (conteudo, sha). sha=None quando o arquivo ainda nao existe.

    O sha e obrigatorio para atualizar um arquivo existente pela Contents API -
    e a trava de concorrencia dela. Por isso a leitura vem sempre antes do commit.
    """
    rota = f"/repos/{OWNER}/{GITHUB_REPO}/contents/{ARQUIVO_REMOTO}?ref={GITHUB_BRANCH}"
    status, dados = _chamar_api("GET", rota)

    if status == 404:
        dl.log(f"[GITHUB] {ARQUIVO_REMOTO} ainda nao existe — sera criado no primeiro commit")
        return "", None

    if status != 200:
        raise RuntimeError(f"Erro ao ler {ARQUIVO_REMOTO} (HTTP {status}): {dados.get('message')}")

    conteudo = base64.b64decode(dados.get("content", "")).decode("utf-8", "replace")
    dl.log(f"[GITHUB] {ARQUIVO_REMOTO} lido ({len(conteudo):,} bytes)")
    return conteudo, dados["sha"]


def commitar(conteudo: str, sha: str | None, mensagem: str) -> str:
    """Grava o arquivo e devolve o sha novo, que alimenta o proximo commit."""
    corpo = {
        "message": mensagem,
        "content": base64.b64encode(conteudo.encode("utf-8")).decode("ascii"),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        corpo["sha"] = sha

    status, dados = _chamar_api(
        "PUT", f"/repos/{OWNER}/{GITHUB_REPO}/contents/{ARQUIVO_REMOTO}", corpo
    )
    if status not in (200, 201):
        raise RuntimeError(f"Falha no commit (HTTP {status}): {dados.get('message')}")

    return dados["content"]["sha"]


# ============================================================
# PROCESSAMENTO
# ============================================================
def processar() -> None:
    resolver_owner()

    dia = f"{datetime.now():%Y-%m-%d}"

    # Travamento diario: o Agendador pode disparar de novo (retry da tarefa,
    # maquina que ligou tarde) e o robo nao pode dobrar os commits do dia.
    if dl.ja_executou_hoje(BASE) and not FORCE:
        anterior = dl.ler_estado(BASE)
        dl.log(f"[ESTADO] dia {dia} ja processado ({anterior.get('commits', 0)} commit(s)) — nada a fazer")
        return

    if not repositorio_existe():
        raise RuntimeError(
            f"Repositorio {OWNER}/{GITHUB_REPO} nao encontrado. "
            f"Rode uma vez com --setup para cria-lo."
        )

    quantidade = random.randint(MIN_COMMITS, MAX_COMMITS)
    dl.log(f"[PLANO] {quantidade} commit(s) previsto(s) para hoje")

    conteudo, sha = dl.executar_com_retry(
        "GITHUB leitura", ler_arquivo_remoto, TENTATIVAS_API, SEGUNDOS_ENTRE_TENTATIVAS
    )
    if not conteudo:
        conteudo = "# Registro de atividades\n\n"

    feitos = 0
    for i in range(1, quantidade + 1):
        linha = f"- {datetime.now():%Y-%m-%d %H:%M:%S} | atividade registrada ({i}/{quantidade})\n"
        mensagem = random.choice(MENSAGENS)

        if DEBUG or DRY_RUN:
            dl.log(f"[DRY RUN] commit {i}/{quantidade}: '{mensagem}' | linha: {linha.strip()}")
            feitos += 1
            continue

        conteudo += linha
        sha_atual = sha  # capturado para o closure do retry
        sha = dl.executar_com_retry(
            f"COMMIT {i}/{quantidade}",
            lambda c=conteudo, s=sha_atual, m=mensagem: commitar(c, s, m),
            TENTATIVAS_API,
            SEGUNDOS_ENTRE_TENTATIVAS,
        )
        feitos += 1
        dl.log(f"[COMMIT] {i}/{quantidade} enviado ({sha[:7]}): {mensagem}")

        if i < quantidade:
            pausa = random.uniform(*PAUSA_ENTRE_COMMITS)
            dl.log(f"[COMMIT] aguardando {pausa:.1f}s antes do proximo")
            time.sleep(pausa)

    if DEBUG or DRY_RUN:
        dl.log(f"[DRY RUN] {feitos} commit(s) simulado(s) — nada enviado ao GitHub")
        return

    CACHE_REMOTO.parent.mkdir(parents=True, exist_ok=True)
    CACHE_REMOTO.write_text(conteudo, encoding="utf-8")
    dl.marcar_execucao(BASE, commits=feitos, ultimo_sha=sha)

    dl.log(f"[ROBO{IDCARGA:03d}] {feitos} commit(s) em {OWNER}/{GITHUB_REPO} -> {ARQUIVO_REMOTO}")


def mostrar_status() -> None:
    resolver_owner()
    estado = dl.ler_estado(BASE)

    dl.log("-" * 70)
    dl.log(f"Repositorio existe  : {'sim' if repositorio_existe() else 'NAO (rode com --setup)'}")
    dl.log(f"Ultima execucao     : {estado.get('ultima_execucao', 'nunca')}")
    dl.log(f"Commits no dia      : {estado.get('commits', 0)}")
    dl.log(f"Ultimo sha          : {estado.get('ultimo_sha', '-')}")
    dl.log("-" * 70)


# ============================================================
# MAIN
# ============================================================
def main() -> None:
    dl.configurar_logger(IDCARGA, NOME_ROBO, BASE)

    modo = "DEBUG" if DEBUG else ("DRY RUN" if DRY_RUN else "PRODUCAO")
    try:
        banco = dl.descrever_conexao()
    except Exception as e:  # noqa: BLE001 - so contexto de log
        banco = f"<nao configurado> ({e})"

    dl.logar_contexto(modo, extras={
        "Arquivo .env": str(dl.ENV_FILE),
        "Repositorio destino": f"{GITHUB_REPO} ({GITHUB_BRANCH})",
        "Arquivo remoto": ARQUIVO_REMOTO,
        "Commits por dia": f"{MIN_COMMITS} a {MAX_COMMITS} (quem define o dia e o Agendador)",
        "Banco de controle": f"{banco} | {dl.TABELA_CONTROLE} (id_carga {IDCARGA})",
        "DEBUG / DRY_RUN": f"{DEBUG} / {DRY_RUN}",
    })

    # Manutencao (--status/--setup) nao passa pela tabela de controle: nao e a
    # carga diaria, e marcar SUCCESS nela mentiria no monitoramento.
    registrar_controle = not (DEBUG or DRY_RUN or STATUS or SETUP)

    try:
        validar_configuracao()

        if registrar_controle:
            dl.status_inicio(IDCARGA)
            dl.log(f"[CONTROLE] id_carga {IDCARGA} marcado como '{dl.STATUS_INICIO}'")

        if STATUS:
            mostrar_status()
        elif SETUP:
            resolver_owner()
            criar_repositorio()
        else:
            processar()

        if registrar_controle:
            dl.status_sucesso(IDCARGA)
            dl.log(f"[CONTROLE] id_carga {IDCARGA} marcado como '{dl.STATUS_SUCESSO}'")

        dl.log(f"[ROBO{IDCARGA:03d}] ✅ RESULTADO FINAL: SUCESSO")
        dl.log("=" * 70)

    except Exception as e:
        dl.log(f"[ROBO{IDCARGA:03d}] ❌ erro final: {e}")
        dl.logar_traceback("erro final")

        if registrar_controle:
            # O status_erro nao pode derrubar o traceback original: se o banco
            # tambem estiver fora, o log tem que continuar mostrando o erro real.
            try:
                dl.status_erro(IDCARGA)
                dl.log(f"[CONTROLE] id_carga {IDCARGA} marcado como '{dl.STATUS_ERRO}'")
            except Exception as erro_controle:  # noqa: BLE001
                dl.log(f"[CONTROLE] ⚠ falha ao registrar o erro na tabela: {erro_controle}")

        dl.log(f"[ROBO{IDCARGA:03d}] ❌ RESULTADO FINAL: ERRO")
        dl.log("=" * 70)

        # So aqui o log vira arquivo. Execucao que termina bem nao deixa rastro.
        arquivo = dl.salvar_log_erro()
        if arquivo:
            print(f"Log do erro: {arquivo}", file=sys.stderr)

        raise


if __name__ == "__main__":
    main()
