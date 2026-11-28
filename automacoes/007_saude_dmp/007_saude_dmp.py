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
import re
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


def checar_sites() -> list[tuple[str, ...]]:
    resultado = []
    for nome, url in SITES:
        r = dl.conferir_site(url)
        if r["status"] != 200:
            resultado.append(("erro", f"site {nome} fora do ar ({r['erro'] or r['status']})"))
        elif r["ms"] > SITE_LENTO_MS:
            resultado.append(("aviso", f"site {nome} lento", f"{url} abriu em {r['ms'] / 1000:.1f} s "
                              f"(limite {SITE_LENTO_MS // 1000} s); uma vez só costuma ser a Vercel acordando."))
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


# Trechos do erro do Postgres -> o que costuma ser, em portugues.
CAUSAS_PG_CRON = (
    ("does not exist", "o job chama algo que não existe (função/tabela apagada, renomeada ou ainda não criada)"),
    ("statement timeout", "a rodada passou do tempo limite"),
    ("permission denied", "o job ficou sem permissão no que ele chama"),
    ("job startup timeout", "o pg_cron não conseguiu iniciar o job (banco sobrecarregado ou sem conexão livre)"),
    ("connection", "falha de conexão do pg_cron com o banco"),
)


def checar_pg_cron(conn: psycopg.Connection) -> list[tuple[str, str, str]]:
    """Falhas das ultimas 24 h por job: quantas, quando, o erro e se ja voltou
    a rodar com sucesso. Falha que ja normalizou vira ok (fica so no historico)."""
    linhas = conn.execute(
        "select j.jobname, j.active, count(*), "
        "to_char(min(d.start_time) at time zone 'America/Sao_Paulo', 'DD/MM HH24:MI'), "
        "to_char(max(d.start_time) at time zone 'America/Sao_Paulo', 'DD/MM HH24:MI'), "
        "(array_agg(d.return_message order by d.start_time desc))[1], "
        "(select count(*) from cron.job_run_details s where s.jobid = j.jobid "
        "   and s.status = 'succeeded' and s.start_time > max(d.start_time)) "
        "from cron.job_run_details d join cron.job j on j.jobid = d.jobid "
        "where d.status = 'failed' and d.start_time > now() - interval '24 hours' "
        "group by j.jobid, j.jobname, j.active order by max(d.start_time) desc").fetchall()
    if not linhas:
        return [("ok", "pg_cron sem falhas", "")]
    resultado = []
    for job, ativo, qtd, primeira, ultima, mensagem, sucessos_depois in linhas:
        erro = next((l.strip() for l in (mensagem or "").splitlines() if l.strip()), "sem mensagem")
        erro = erro.removeprefix("ERROR:").strip()[:160]
        causa = next((c for trecho, c in CAUSAS_PG_CRON if trecho in erro.lower()), "")
        quando = ultima if qtd == 1 else (f"de {primeira} a {ultima}" if primeira[:5] != ultima[:5]
                                          else f"{primeira} a {ultima[6:]}")
        if sucessos_depois:
            resultado.append(("ok", f"pg_cron {job}: {qtd} falha(s) em {quando}, já normalizou", ""))
            continue
        detalhe = (f"{qtd} falha(s) em 24 h ({quando}, horário de Brasília), sem sucesso depois"
                   f"{'; o job está pausado' if not ativo else ''}.\n"
                   f"Erro: `{erro}`" + (f"\nProvável causa: {causa}." if causa else ""))
        resultado.append(("aviso", f"pg_cron: {job} falhando", detalhe))
    return resultado


def checar_banco() -> list[tuple[str, ...]]:
    resultado = []
    with psycopg.connect(dl.obter_variavel("SUPABASE_DB_URL"), prepare_threshold=None, connect_timeout=30,
                         sslmode="require", application_name=f"robo_{IDCARGA:03d}") as conn:
        conn.read_only = True
        mb = conn.execute("select pg_database_size(current_database()) / 1e6").fetchone()[0]
        if mb > BANCO_AVISO_MB:
            maiores = conn.execute(
                "select n.nspname || '.' || c.relname, pg_total_relation_size(c.oid) / 1e6 from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace where c.relkind in ('r', 'm') "
                "order by 2 desc limit 3").fetchall()
            resultado.append(("aviso", f"banco {mb:.0f} MB de 500", "Maiores: " + ", ".join(
                f"{t} {m:.0f} MB" for t, m in maiores) + ". Acima de 500 MB o plano grátis fica só leitura."))
        else:
            resultado.append(("ok", f"banco {mb:.0f} MB de 500"))

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

        resultado += checar_pg_cron(conn)

        presentes = {r[0] for r in conn.execute("select name from vault.secrets").fetchall()}
        faltam = [s for s in SEGREDOS_VAULT if s not in presentes]
        resultado.append(("erro", f"Vault sem {', '.join(faltam)}: o pg_cron não dispara os robôs") if faltam
                         else ("ok", "Vault ok"))
        conn.rollback()
    return resultado


# ─── carga ───────────────────────────────────────────────────────────────────


def avisar_no_discord(avisos: list[str], detalhes: dict[str, str]) -> None:
    """Avisa no #alertas so quando a lista de avisos muda (memoria: a mensagem
    da execucao anterior deste robo, que comeca com "⚠️ ..." quando havia aviso).
    O titulo e curto; o corpo explica cada aviso (quando, erro, provavel causa)."""
    texto = " · ".join(avisos)
    try:
        anterior = dl.supabase_ler(f"historico_cargas?select=mensagem&id_carga=eq.{IDCARGA}"
                                   f"&status=eq.SUCCESS&order=dta_ini.desc&limit=1")
    except Exception as e:  # noqa: BLE001
        dl.log(f"[DISCORD] nao consegui ler a execucao anterior: {e}")
        anterior = []
    msg = (anterior[0].get("mensagem") or "") if anterior else ""
    # so a parte dos avisos: "⚠️ a · b — detalhes | DMP ok ..." -> "a · b"
    eram = re.split(r" — | \| ", msg, maxsplit=1)[0].removeprefix("⚠️ ") if msg.startswith("⚠️") else ""
    if avisos and eram != texto:
        dl.notificar_discord("alertas", ("⚠️ DMP: " + "; ".join(avisos))[:200],
                             "\n\n".join(f"**• {a}**" + (f"\n{detalhes[a]}" if detalhes.get(a) else "")
                                         for a in avisos), nivel="atencao")
    elif not avisos and eram:
        dl.notificar_discord("alertas", "✅ DMP: avisos resolvidos", f"Eram: {eram}", nivel="ok", silencioso=True)


def processar() -> tuple[int, str]:
    global ITENS_FEITOS
    # cada checagem: (nivel, texto curto) ou (nivel, texto curto, detalhe)
    checagens = [(c + ("",))[:3] for c in checar_sites() + checar_auth() + checar_banco()]
    for nivel, texto, detalhe in checagens:
        dl.log(f"[{nivel.upper():5}] {texto}" + (f" | {detalhe}" if detalhe else ""))
    ITENS_FEITOS = sum(1 for n, _, _ in checagens if n == "ok")
    erros = [t for n, t, _ in checagens if n == "erro"]
    avisos = [t for n, t, _ in checagens if n == "aviso"]
    detalhes = {t: d for _, t, d in checagens if d}
    if not (DEBUG or DRY_RUN):
        avisar_no_discord(avisos, detalhes)
    if erros:
        raise RuntimeError("DMP com problema: " + " · ".join(
            f"{t} ({detalhes[t]})" if t in detalhes else t for t in erros + avisos).replace("\n", " "))
    resumo = "DMP ok ✅ · " + " · ".join(t for n, t, _ in checagens if n == "ok")
    if avisos:
        # o comeco ("⚠️ " + avisos) e a memoria do avisar_no_discord: detalhe vem depois
        explicacao = " ".join(detalhes.get(a, "") for a in avisos).replace("\n", " ").strip()
        resumo = "⚠️ " + " · ".join(avisos) + (f" — {explicacao}" if explicacao else "") + " | " + resumo
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
