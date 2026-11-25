# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 25/11/2026
# DESCRICAO      : Saude do DMP (banco pessoal: hub, robos, Minecraft, finanças),
#                  so LENDO: sites pessoais, Auth fechado, RLS, escrita do papel
#                  anonimo, tamanho, falhas do pg_cron e o token do Vault. Irmao
#                  do 006 (DMC). Erro = run vermelho + #alertas; aviso = #alertas
#                  so quando muda. Regras em automacoes\PADRAO_ROBOS.md.
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

from datetime import datetime, timezone

import psycopg

import lib_dscs as dl

# ─── configuracao ────────────────────────────────────────────────────────────
# --dry-run -> faz todas as checagens, mas nao registra status nem avisa.
DEBUG = False
DRY_RUN = "--dry-run" in sys.argv

IDCARGA = 7  # ★ mesmo numero da pasta e do id_carga em public.controle_cargas
NOME_ROBO = "saude_dmp"
BASE = Path(__file__).resolve().parent

SITES = [
    ("hub-robos", "https://hub-robos.vercel.app"),
    ("server-galera", "https://server-galera.vercel.app"),
    ("financas-app", "https://financas-app-delta-rose.vercel.app"),
]
SCHEMAS = ("public", "private", "openfinance")
SEGREDOS_VAULT = ("github_dispatch_token",)

SITE_LENTO_MS = 5000
BANCO_AVISO_MB = 400   # o plano gratis tem 500 MB

ITENS_FEITOS = 0


def validar_configuracao() -> None:
    env = dl.ler_env()
    faltando = [c for c in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_DB_URL") if not env.get(c)]
    if faltando:
        raise ValueError(f"Faltam variaveis no ambiente/.env: {', '.join(faltando)}")


# ─── checagens: lista de (nivel, texto), nivel = ok | aviso | erro ───────────


def checar_sites() -> list[tuple[str, str]]:
    resultado = []
    for nome, url in SITES:
        r = dl.conferir_site(url)
        if r["status"] != 200:
            resultado.append(("erro", f"site {nome} fora do ar ({r['erro'] or r['status']})"))
        elif r["ms"] > SITE_LENTO_MS:
            resultado.append(("aviso", f"site {nome} lento: {r['ms'] / 1000:.1f} s"))
        else:
            resultado.append(("ok", f"{nome} {r['ms']:.0f} ms"))
    return resultado


def checar_auth() -> list[tuple[str, str]]:
    url = dl.obter_variavel("SUPABASE_URL").rstrip("/")
    status, payload = dl.chamar_api_json(f"{url}/auth/v1/settings",
                                         cabecalhos={"apikey": dl.obter_variavel("SUPABASE_KEY")}, timeout=30)
    if status != 200:
        return [("erro", f"Auth do DMP respondeu HTTP {status}")]
    if not payload.get("disable_signup"):
        return [("erro", "Auth do DMP com cadastro aberto: qualquer um cria conta "
                         "(painel: Authentication → Sign In / Providers → desligar 'Allow new users to sign up')")]
    return [("ok", "Auth fechado")]


def checar_banco() -> list[tuple[str, str]]:
    resultado = []
    with psycopg.connect(dl.obter_variavel("SUPABASE_DB_URL"), prepare_threshold=None, connect_timeout=30,
                         sslmode="require", application_name=f"robo_{IDCARGA:03d}") as conn:
        conn.read_only = True
        mb = conn.execute("select pg_database_size(current_database()) / 1e6").fetchone()[0]
        resultado.append(("aviso" if mb > BANCO_AVISO_MB else "ok", f"banco {mb:.0f} MB de 500"))

        sem_rls, total = conn.execute(
            "select count(*) filter (where not c.relrowsecurity), count(*) from pg_class c "
            "join pg_namespace n on n.oid = c.relnamespace where n.nspname = any(%s) and c.relkind = 'r'",
            (list(SCHEMAS),)).fetchone()
        resultado.append(("erro", f"{sem_rls} tabela(s) sem RLS") if sem_rls else ("ok", f"RLS em {total}/{total}"))

        anon = conn.execute(
            "select count(distinct table_schema || '.' || table_name) from information_schema.role_table_grants "
            "where grantee = 'anon' and table_schema = any(%s) "
            "and privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')", (list(SCHEMAS),)).fetchone()[0]
        resultado.append(("erro", f"papel anônimo com escrita em {anon} tabela(s)/view(s)") if anon
                         else ("ok", "anônimo sem escrita"))

        falhas = conn.execute(
            "select coalesce(string_agg(distinct j.jobname, ', '), ''), count(*) from cron.job_run_details d "
            "join cron.job j using (jobid) where d.status = 'failed' and d.start_time > now() - interval '24 hours'"
        ).fetchone()
        resultado.append(("aviso", f"pg_cron: {falhas[1]} falha(s) em 24 h ({falhas[0]})") if falhas[1]
                         else ("ok", "pg_cron sem falhas"))

        presentes = {r[0] for r in conn.execute("select name from vault.secrets").fetchall()}
        faltam = [s for s in SEGREDOS_VAULT if s not in presentes]
        resultado.append(("erro", f"Vault sem {', '.join(faltam)}: o pg_cron não dispara os robôs") if faltam
                         else ("ok", "Vault ok"))
        conn.rollback()
    return resultado


# ─── carga ───────────────────────────────────────────────────────────────────


def avisar_no_discord(avisos: list[str]) -> None:
    """Avisa no #alertas so quando a lista de avisos muda (memoria: a mensagem
    da execucao anterior deste robo, que comeca com "⚠️ ..." quando havia aviso)."""
    texto = " · ".join(avisos)
    try:
        anterior = dl.supabase_ler(f"historico_cargas?select=mensagem&id_carga=eq.{IDCARGA}"
                                   f"&status=eq.SUCCESS&order=dta_ini.desc&limit=1")
    except Exception as e:  # noqa: BLE001
        dl.log(f"[DISCORD] nao consegui ler a execucao anterior: {e}")
        anterior = []
    msg = (anterior[0].get("mensagem") or "") if anterior else ""
    if avisos and not msg.startswith("⚠️ " + texto):
        dl.notificar_discord("alertas", ("⚠️ DMP: " + "; ".join(avisos))[:200],
                             "\n".join(f"• {a}" for a in avisos), nivel="atencao")
    elif not avisos and msg.startswith("⚠️"):
        dl.notificar_discord("alertas", "✅ DMP: avisos resolvidos", None, nivel="ok", silencioso=True)


def processar() -> tuple[int, str]:
    global ITENS_FEITOS
    checagens = checar_sites() + checar_auth() + checar_banco()
    for nivel, texto in checagens:
        dl.log(f"[{nivel.upper():5}] {texto}")
    ITENS_FEITOS = sum(1 for n, _ in checagens if n == "ok")
    erros = [t for n, t in checagens if n == "erro"]
    avisos = [t for n, t in checagens if n == "aviso"]
    if not (DEBUG or DRY_RUN):
        avisar_no_discord(avisos)
    if erros:
        raise RuntimeError("DMP com problema: " + " · ".join(erros + avisos))
    resumo = "DMP ok ✅ · " + " · ".join(t for n, t in checagens if n == "ok")
    if avisos:
        resumo = "⚠️ " + " · ".join(avisos) + " | " + resumo
    return ITENS_FEITOS, resumo[:500]


def main() -> None:
    dl.configurar_logger(IDCARGA, NOME_ROBO, BASE)
    modo = dl.modo_execucao()
    dta_ini = datetime.now(timezone.utc)
    dl.logar_contexto("DRY-RUN" if (DEBUG or DRY_RUN) else modo,
                      extras={"Sites": ", ".join(s[0] for s in SITES), "DEBUG / DRY_RUN": f"{DEBUG} / {DRY_RUN}"})
    registrar = not (DEBUG or DRY_RUN)
    try:
        validar_configuracao()
        if registrar:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, dta_ini, fechar=False)
        qtd, resumo = processar()
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
