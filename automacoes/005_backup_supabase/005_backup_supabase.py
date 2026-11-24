# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 23/11/2026
# DESCRICAO      : Backup dos bancos Supabase so com Python (sem pg_dump):
#                  estrutura em SQL + dados em CSV num zip por banco, gravado
#                  numa pasta. Opcional: restaura cada zip num Postgres de teste
#                  e confere tudo. A execucao diaria roda no repo PRIVADO
#                  diegoscs/backups-supabase, que guarda os zips por 30 dias.
#                  Regras em automacoes\PADRAO_ROBOS.md.
# =============================================
from __future__ import annotations

import os
import sys
from pathlib import Path

# --- bootstrap padrao: encoding + caminho da lib (nesta ordem, antes dos imports)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import shutil
import tempfile
import time
from datetime import datetime, timezone

import psycopg

import lib_dscs as dl
from exportar import conferir_zip, exportar_banco
from restaurar import restaurar_zip

# ─── configuracao ────────────────────────────────────────────────────────────
# --pasta DIR          -> grava <banco>_<data>.zip em DIR (fora do repositorio).
# --testar-restore     -> restaura cada zip no Postgres de BACKUP_RESTORE_URL
#                         (desfeito no fim) e confere linhas e objetos.
# --dry-run            -> gera e confere numa pasta temporaria; nao grava nada.
# --alvo NOME          -> so um banco.
# --status             -> mostra a configuracao e sai.
# --conferir ARQ.zip   -> confere um zip ja gravado (sem banco).
# --registrar-erro MSG -> so registra ERROR (o workflow usa se o envio falhar).
#
# Registro no hub: so no modo CLOUD (a execucao diaria). Backup feito na mao
# no PC (modo LOCAL) nao e a carga e nao registra.
DEBUG = False
DRY_RUN = "--dry-run" in sys.argv
STATUS = "--status" in sys.argv
TESTAR_RESTORE = "--testar-restore" in sys.argv


def _valor_do_argumento(nome: str) -> str | None:
    if nome not in sys.argv:
        return None
    i = sys.argv.index(nome)
    if i + 1 >= len(sys.argv) or sys.argv[i + 1].startswith("--"):
        raise ValueError(f"{nome} precisa de um valor")
    return sys.argv[i + 1]


PASTA = _valor_do_argumento("--pasta")
CONFERIR = _valor_do_argumento("--conferir")
REGISTRAR_ERRO = _valor_do_argumento("--registrar-erro")

IDCARGA = 5  # ★ mesmo numero da pasta e do id_carga em public.controle_cargas
NOME_ROBO = "backup_supabase"
NOME_APP = f"robo_{IDCARGA:03d}_{NOME_ROBO}"

BASE = Path(__file__).resolve().parent

# Bancos: rotulo (vai no nome do arquivo) -> variaveis com a string de conexao,
# na ordem de preferencia. Qualquer pooler serve (a exportacao e uma transacao
# so). 24/11/2026: OpenFinance pausado (saiu), DMC entrou.
ALVOS = {
    "dmp": ("SUPABASE_DUMP_URL_DMP", "SUPABASE_DB_URL"),
    "dmc": ("SUPABASE_DMC_DB_URL",),
}

TENTATIVAS = 3
SEGUNDOS_ENTRE_TENTATIVAS = 30

# Backups gravados (e testados, com --testar-restore) nesta execucao.
ITENS_FEITOS = 0


# ─── configuracao e validacao ────────────────────────────────────────────────


def url_do_alvo(rotulo: str) -> str | None:
    env = dl.ler_env()
    return next((env[v] for v in ALVOS[rotulo] if env.get(v)), None)


def alvos_da_execucao() -> list[str]:
    nome = _valor_do_argumento("--alvo")
    if nome is None:
        return list(ALVOS)
    if nome not in ALVOS:
        raise ValueError(f"--alvo invalido: {nome!r}. Opcoes: {', '.join(ALVOS)}")
    return [nome]


def deve_registrar() -> bool:
    return not (DEBUG or DRY_RUN) and dl.modo_execucao() == dl.MODO_CLOUD


def validar_configuracao(alvos: list[str]) -> None:
    """Tudo que pode faltar, conferido antes de qualquer rede."""
    env = dl.ler_env()
    faltando = [" ou ".join(ALVOS[r]) for r in alvos if not url_do_alvo(r)]
    if TESTAR_RESTORE and not env.get("BACKUP_RESTORE_URL"):
        faltando.append("BACKUP_RESTORE_URL")
    if deve_registrar():
        faltando += [c for c in ("SUPABASE_URL", "SUPABASE_KEY") if not env.get(c)]
    if faltando:
        raise ValueError(f"Faltam variaveis no ambiente/.env: {', '.join(faltando)}")

    if not (PASTA or DRY_RUN):
        raise ValueError("informe --pasta DIR (ou --dry-run)")
    if PASTA:
        pasta = Path(PASTA).resolve()
        if pasta == dl.RAIZ or dl.RAIZ in pasta.parents:
            raise ValueError(f"--pasta {pasta} fica dentro do repositorio: escolha uma pasta fora dele")


# ─── carga ───────────────────────────────────────────────────────────────────


def exportar_com_retry(rotulo: str, arquivo_zip: Path) -> dict:
    """Retry so em falha de conexao: erro de SQL ou permissao estoura na primeira."""
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return exportar_banco(url_do_alvo(rotulo), rotulo, arquivo_zip, NOME_APP)
        except psycopg.OperationalError as e:
            if tentativa == TENTATIVAS:
                raise
            dl.log(f"[EXPORT] {rotulo}: conexao falhou ({e}); nova tentativa em {SEGUNDOS_ENTRE_TENTATIVAS}s")
            time.sleep(SEGUNDOS_ENTRE_TENTATIVAS)
    raise AssertionError("inalcancavel")


def testar_restore(rotulo: str, arquivo_zip: Path) -> str:
    """Restaura no Postgres de teste (desfeito no fim). Levanta se algo nao bater."""
    r = restaurar_zip(arquivo_zip, dl.obter_variavel("BACKUP_RESTORE_URL"), NOME_APP)
    for aviso in r["avisos"]:
        dl.log(f"[RESTORE] {rotulo}: aviso: {aviso}")
    if r["erros"]:
        for erro in r["erros"]:
            dl.log(f"[RESTORE] {rotulo}: ERRO: {erro}")
        raise RuntimeError(f"restore de {rotulo} falhou em {len(r['erros'])} ponto(s); "
                           f"primeiro: {r['erros'][0][:300]}")
    dl.log(f"[RESTORE] {rotulo}: ok, {r['tabelas']} tabelas e {r['linhas']} linhas conferidas")
    return "restore ok"


def processar(alvos: list[str]) -> tuple[int, str]:
    """A carga. Devolve (qtd_itens, resumo) para o registro no Supabase."""
    global ITENS_FEITOS
    carimbo = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MZ")
    feitos: list[str] = []

    with tempfile.TemporaryDirectory(prefix="robo005_") as tmp:
        for rotulo in alvos:
            arquivo_zip = Path(tmp) / f"{rotulo}_{carimbo}.zip"
            manifesto = exportar_com_retry(rotulo, arquivo_zip)
            tabelas, linhas = conferir_zip(arquivo_zip)  # o zip abre e bate com o banco
            dl.log(f"[EXPORT] {rotulo}: {tabelas} tabelas, {linhas} linhas (Postgres {manifesto['servidor']})")

            resumo = f"{rotulo} {tabelas} tabelas/{linhas} linhas"
            if TESTAR_RESTORE:
                resumo += f", {testar_restore(rotulo, arquivo_zip)}"
            resumo += f", {arquivo_zip.stat().st_size / 1e6:.1f} MB".replace(".", ",")

            if not (DEBUG or DRY_RUN):
                pasta = Path(PASTA)
                pasta.mkdir(parents=True, exist_ok=True)
                shutil.move(str(arquivo_zip), pasta / arquivo_zip.name)
                dl.log(f"[PASTA] {(pasta / arquivo_zip.name).resolve()}")
                ITENS_FEITOS += 1
            feitos.append(resumo)

    prefixo = "dry-run: " if (DEBUG or DRY_RUN) else f"{ITENS_FEITOS} backup(s): "
    return ITENS_FEITOS, prefixo + " · ".join(feitos)


def mostrar_status(alvos: list[str]) -> None:
    env = dl.ler_env()
    print(f"Robo {IDCARGA:03d} - {NOME_ROBO} (modo {dl.modo_execucao()}, registra: {deve_registrar()})")
    for rotulo in alvos:
        print(f"  {rotulo:<12} {' ou '.join(ALVOS[rotulo])}: {'configurado' if url_do_alvo(rotulo) else 'AUSENTE'}")
    print(f"  teste de restore: {'BACKUP_RESTORE_URL configurado' if env.get('BACKUP_RESTORE_URL') else 'sem BACKUP_RESTORE_URL'}")


def main() -> None:
    if CONFERIR:
        tabelas, linhas = conferir_zip(CONFERIR)
        print(f"OK: {Path(CONFERIR).name} abre e confere: {tabelas} tabelas, {linhas} linhas")
        return

    dl.configurar_logger(IDCARGA, NOME_ROBO, BASE)
    dta_ini = datetime.now(timezone.utc)

    if REGISTRAR_ERRO:
        dl.registrar_carga_supabase(IDCARGA, dl.STATUS_ERRO, dta_ini, fechar=True,
                                    mensagem=REGISTRAR_ERRO[:500], qtd_itens=0)
        return

    alvos = alvos_da_execucao()
    dl.logar_contexto(
        "DRY-RUN" if (DEBUG or DRY_RUN) else dl.modo_execucao(),
        extras={
            "Bancos": ", ".join(alvos),
            "Destino": str(Path(PASTA).resolve()) if PASTA else "(nenhum)",
            "Teste de restore": str(TESTAR_RESTORE),
            "Registra no hub": str(deve_registrar()),
        },
    )

    if STATUS:
        mostrar_status(alvos)
        return

    registrar = deve_registrar()

    try:
        validar_configuracao(alvos)

        if registrar:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, dta_ini, fechar=False)

        qtd, resumo = processar(alvos)

        if registrar:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_SUCESSO, dta_ini, fechar=True,
                                        mensagem=resumo, qtd_itens=qtd)

        dl.log(f"[ROBO{IDCARGA:03d}] ✅ RESULTADO FINAL: SUCESSO - {resumo}")
        dl.log("=" * 70)

    except Exception as e:
        dl.log(f"[ROBO{IDCARGA:03d}] ❌ erro final: {e}")
        dl.logar_traceback("erro final")

        if registrar:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_ERRO, dta_ini, fechar=True,
                                        mensagem=str(e)[:500], qtd_itens=ITENS_FEITOS)
            dl.alertar_erro_robo(IDCARGA, NOME_ROBO, str(e))

        dl.log(f"[ROBO{IDCARGA:03d}] ❌ RESULTADO FINAL: ERRO")
        dl.log("=" * 70)

        arquivo = dl.salvar_log_erro()
        if arquivo:
            print(f"Log do erro: {arquivo}", file=sys.stderr)

        raise


if __name__ == "__main__":
    main()
