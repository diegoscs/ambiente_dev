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
from datetime import datetime, timezone

import lib_dscs as dl

# ─── configuracao ────────────────────────────────────────────────────────────
# DEBUG=True   -> NADA e gravado em dbo.controle_cargas e nenhum commit e feito.
# --dry-run    -> igual ao DEBUG, sem precisar editar o arquivo.
# --force      -> ignora o sorteio de folga e o travamento diario.
# --setup      -> cria o repositorio no GitHub, se ainda nao existir.
# --status     -> mostra a configuracao e o estado atual, sem commitar.
# MODO_EXECUCAO=CLOUD (env) -> GitHub Actions: trava e registro no Supabase.
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

# LOCAL -> Agendador do Windows: trava em temp\estado.json + dbo.controle_cargas.
# CLOUD -> GitHub Actions: a maquina nasce vazia a cada execucao, entao a trava
#          e o registro ficam no Supabase (public.historico_cargas).
# Nos dois modos, com o Supabase configurado, a carga e registrada la tambem:
# e o que deixa PC e nuvem rodarem em paralelo sem dobrar os commits do dia.
MODO = dl.modo_execucao()


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

    # GH_PAT no GitHub Actions (secret nao pode comecar com GITHUB_),
    # GITHUB_TOKEN no .env do PC.
    TOKEN = dl.ler_env().get("GH_PAT") or dl.obter_variavel("GITHUB_TOKEN")

    if MODO == dl.MODO_CLOUD and not dl.supabase_configurado():
        raise ValueError(
            "Modo CLOUD sem SUPABASE_URL/SUPABASE_KEY: sem o Supabase nao ha trava "
            "diaria nem registro da carga."
        )

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
def dia_github() -> datetime:
    """O "hoje" deste robo e o dia UTC, nao o dia de Sao Paulo.

    O calendario de contribuicoes da GitHub conta o commit pela data do
    carimbo do proprio commit, e a Contents API carimba em UTC (offset Z).
    Entao o quadradinho que fica verde e o do dia UTC - nao o do fuso daqui.

    Usar hora local na trava quebra nos dois sentidos:

      * 24/09/2026 as 22:06 (Sao Paulo) = 25/09 01:06 UTC. Os 8 commits
        cairam inteiros no quadrado do dia 25. O robo gravou SUCCESS, o
        estado.json marcou 24/09 como processado, nao houve log de erro -
        e 24/09 ficou BRANCO no calendario. Silencio identico ao do sucesso,
        que e a mesma armadilha dos 7 dias em branco de setembro.

      * no dia seguinte a trava barra a execucao ("24/09 ja processado")
        justamente quando ela encheria o quadrado que ficou vazio.

    Amarrando a trava ao dia UTC, "uma execucao por dia" passa a significar
    "uma execucao por quadradinho", que e o que o robo existe para fazer.
    """
    return datetime.now(timezone.utc)


def commits_ja_feitos_hoje() -> int:
    """Trava diaria. Soma o que o Supabase e o estado local sabem do dia UTC.

    Com o Supabase configurado ele e a fonte principal: e o unico lugar que o
    PC e o GitHub Actions enxergam juntos. O estado.json continua valendo no PC.
    """
    feitos = 0

    if MODO == dl.MODO_LOCAL and dl.ja_executou_hoje(BASE, dia_github()):
        feitos = max(feitos, int(dl.ler_estado(BASE).get("commits", 0)) or 1)

    if dl.supabase_configurado():
        # Sem resposta do Supabase nao da para saber se o dia ja foi feito. Na
        # nuvem ele e a unica trava, entao o erro sobe e nada e commitado; no
        # PC o estado.json ainda protege, e a execucao segue.
        try:
            feitos = max(feitos, dl.trabalho_feito_no_dia(IDCARGA, dia_github()))
        except Exception as e:  # noqa: BLE001
            if MODO == dl.MODO_CLOUD:
                raise RuntimeError(f"Trava diaria indisponivel no Supabase: {e}") from e
            dl.log(f"[ESTADO] ⚠ Supabase indisponivel para a trava, seguindo com o estado local: {e}")

    return feitos


def processar() -> tuple[int, str]:
    """Faz os commits do dia. Devolve (quantidade, resumo) para o registro da carga."""
    resolver_owner()

    dia = f"{dia_github():%Y-%m-%d}"

    # Travamento diario: o Agendador pode disparar de novo (retry da tarefa,
    # maquina que ligou tarde), o PC e a nuvem podem rodar no mesmo dia, e o
    # robo nao pode dobrar os commits.
    ja_feitos = commits_ja_feitos_hoje()
    if ja_feitos and not FORCE:
        resumo = f"dia {dia} (UTC) ja processado ({ja_feitos} commit(s)) - nada a fazer"
        dl.log(f"[ESTADO] {resumo}")
        return 0, resumo

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
        # UTC de proposito: assim a linha do arquivo bate com a data do
        # commit que a GitHub mostra, em vez de divergir perto da virada.
        linha = f"- {dia_github():%Y-%m-%d %H:%M:%S} UTC | atividade registrada ({i}/{quantidade})\n"
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
        return 0, f"dry-run: {feitos} commit(s) simulado(s)"

    CACHE_REMOTO.parent.mkdir(parents=True, exist_ok=True)
    CACHE_REMOTO.write_text(conteudo, encoding="utf-8")
    dl.marcar_execucao(BASE, dia_github(), commits=feitos, ultimo_sha=sha)

    resumo = f"{feitos} commit(s) em {OWNER}/{GITHUB_REPO} (ultimo {sha[:7]})"
    dl.log(f"[ROBO{IDCARGA:03d}] {resumo} -> {ARQUIVO_REMOTO}")
    return feitos, resumo


def mostrar_status() -> None:
    resolver_owner()
    estado = dl.ler_estado(BASE)

    dl.log("-" * 70)
    dl.log(f"Repositorio existe  : {'sim' if repositorio_existe() else 'NAO (rode com --setup)'}")
    dl.log(f"Ultima execucao     : {estado.get('ultima_execucao', 'nunca')} (dia UTC)")
    dl.log(f"Commits no dia      : {estado.get('commits', 0)}")
    dl.log(f"Ultimo sha          : {estado.get('ultimo_sha', '-')}")
    dl.log("-" * 70)


# ============================================================
# MAIN
# ============================================================
def main() -> None:
    dl.configurar_logger(IDCARGA, NOME_ROBO, BASE)

    execucao = "DEBUG" if DEBUG else ("DRY RUN" if DRY_RUN else "PRODUCAO")
    dta_ini = datetime.now(timezone.utc)

    if MODO == dl.MODO_LOCAL:
        try:
            banco = f"{dl.descrever_conexao()} | {dl.TABELA_CONTROLE}"
        except Exception as e:  # noqa: BLE001 - so contexto de log
            banco = f"<nao configurado> ({e})"
    else:
        banco = "nenhum local - carga gravada direto no Supabase"

    dl.logar_contexto(execucao, extras={
        "Modo de execucao": MODO,
        "Arquivo .env": str(dl.ENV_FILE),
        "Repositorio destino": f"{GITHUB_REPO} ({GITHUB_BRANCH})",
        "Arquivo remoto": ARQUIVO_REMOTO,
        "Commits por dia": f"{MIN_COMMITS} a {MAX_COMMITS} (quem define o dia e o agendamento)",
        "Banco de controle": f"{banco} (id_carga {IDCARGA})",
        "Supabase": "configurado" if dl.supabase_configurado() else "AUSENTE",
        "DEBUG / DRY_RUN": f"{DEBUG} / {DRY_RUN}",
    })

    # Manutencao (--status/--setup) nao passa pela tabela de controle: nao e a
    # carga diaria, e marcar SUCCESS nela mentiria no monitoramento.
    registrar_controle = not (DEBUG or DRY_RUN or STATUS or SETUP)
    registrar_local = registrar_controle and MODO == dl.MODO_LOCAL
    registrar_supabase = registrar_controle and dl.supabase_configurado()

    try:
        validar_configuracao()

        if registrar_local:
            dl.status_inicio(IDCARGA)
            dl.log(f"[CONTROLE] id_carga {IDCARGA} marcado como '{dl.STATUS_INICIO}'")
        if registrar_supabase:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, dta_ini, fechar=False)

        commits, resumo = 0, ""
        if STATUS:
            mostrar_status()
        elif SETUP:
            resolver_owner()
            criar_repositorio()
        else:
            commits, resumo = processar()

        if registrar_local:
            dl.status_sucesso(IDCARGA)
            dl.log(f"[CONTROLE] id_carga {IDCARGA} marcado como '{dl.STATUS_SUCESSO}'")
        if registrar_supabase:
            dl.registrar_carga_supabase(
                IDCARGA, dl.STATUS_SUCESSO, dta_ini, fechar=True,
                mensagem=resumo, qtd_itens=commits,
            )

        dl.log(f"[ROBO{IDCARGA:03d}] ✅ RESULTADO FINAL: SUCESSO")
        dl.log("=" * 70)

    except Exception as e:
        dl.log(f"[ROBO{IDCARGA:03d}] ❌ erro final: {e}")
        dl.logar_traceback("erro final")

        if registrar_local:
            # O status_erro nao pode derrubar o traceback original: se o banco
            # tambem estiver fora, o log tem que continuar mostrando o erro real.
            try:
                dl.status_erro(IDCARGA)
                dl.log(f"[CONTROLE] id_carga {IDCARGA} marcado como '{dl.STATUS_ERRO}'")
            except Exception as erro_controle:  # noqa: BLE001
                dl.log(f"[CONTROLE] ⚠ falha ao registrar o erro na tabela: {erro_controle}")
        if registrar_supabase:
            # registrar_carga_supabase nunca levanta: o erro original segue intacto.
            dl.registrar_carga_supabase(
                IDCARGA, dl.STATUS_ERRO, dta_ini, fechar=True,
                mensagem=str(e)[:500], qtd_itens=0,
            )

        if registrar_controle:
            dl.alertar_erro_robo(IDCARGA, NOME_ROBO, str(e))

        dl.log(f"[ROBO{IDCARGA:03d}] ❌ RESULTADO FINAL: ERRO")
        dl.log("=" * 70)

        # So aqui o log vira arquivo. Execucao que termina bem nao deixa rastro.
        arquivo = dl.salvar_log_erro()
        if arquivo:
            print(f"Log do erro: {arquivo}", file=sys.stderr)

        raise


if __name__ == "__main__":
    main()
