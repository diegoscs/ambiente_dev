# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 24/11/2026
# DESCRICAO      : Saude do DMC (banco dos apps de clientes), so LENDO: site
#                  de cada app, API, Auth, Edge Function, RLS, tamanho do banco
#                  e assinaturas. Erro = run vermelho, ERROR no hub e aviso em
#                  #alertas + #cliente-estoque; aviso = hub + #cliente-estoque. Regras em automacoes\PADRAO_ROBOS.md.
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
# --dry-run -> faz todas as checagens, mas nao registra status nem notifica.
# --status  -> mostra a configuracao e sai.
DEBUG = False
DRY_RUN = "--dry-run" in sys.argv
STATUS = "--status" in sys.argv

IDCARGA = 6  # ★ mesmo numero da pasta e do id_carga em public.controle_cargas
NOME_ROBO = "saude_dmc"
ORIGEM_AVISO = "saude_dmc"  # origem das notificacoes no hub
CANAL_DISCORD = "estoque"   # #cliente-estoque (erro vai tambem para #alertas)

BASE = Path(__file__).resolve().parent

# Apps de cliente no DMC: (nome, site, schema, edge functions do app).
# Cliente novo = uma linha aqui (ate o cadastro plataforma.apps existir).
APPS = [
    ("estoque-tattoo", "https://estoque-tattoo-rho.vercel.app", "estoque", ("estoque-admin",)),
]

SITE_LENTO_MS = 5000
BANCO_AVISO_MB = 400   # o plano gratis tem 500 MB
VENCENDO_DIAS = 7

TENTATIVAS = 3
SEGUNDOS_ENTRE_TENTATIVAS = 20

# Checagens que passaram nesta execucao (vai para o qtd_itens).
ITENS_FEITOS = 0

# Regra de escrita igual a estoque.pode_escrever(): pode lancar quem nao esta
# bloqueado e e cortesia, ou esta no teste, ou pagou (com 5 dias de folga).
SQL_ASSINATURAS = """
with e as (
  select bloqueado, cortesia,
         greatest(coalesce(teste_ate, date '1900-01-01'),
                  coalesce(pago_ate + 5, date '1900-01-01')) as libera_ate
    from {schema}.estoques
)
select count(*)                                                        as negocios,
       count(*) filter (where bloqueado)                               as bloqueados,
       count(*) filter (where not bloqueado and cortesia)              as cortesia,
       count(*) filter (where not bloqueado and not cortesia
                          and libera_ate < {schema}.hoje())           as vencidos,
       count(*) filter (where not bloqueado and not cortesia
                          and libera_ate >= {schema}.hoje()
                          and libera_ate < {schema}.hoje() + %s)       as vencendo
  from e
"""

SQL_ULTIMO_LANCAMENTO = """
select max(m) from (
  select max(criado_em) m from {schema}.usos
  union all select max(criado_em) from {schema}.compras
  union all select max(criado_em) from {schema}.ganhos
) s
"""


def validar_configuracao() -> None:
    env = dl.ler_env()
    faltando = [c for c in ("SUPABASE_DMC_URL", "SUPABASE_DMC_KEY", "SUPABASE_DMC_DB_URL") if not env.get(c)]
    if not (DEBUG or DRY_RUN):
        faltando += [c for c in ("SUPABASE_URL", "SUPABASE_KEY") if not env.get(c)]
    if faltando:
        raise ValueError(f"Faltam variaveis no ambiente/.env: {', '.join(faltando)}")


# ─── checagens (cada uma devolve uma lista de (nivel, texto)) ────────────────
# nivel: "ok" | "aviso" | "erro". Texto curto, sem nome de cliente: o log do
# Actions deste repo e publico.


def checar_site(nome: str, url: str) -> list[tuple[str, str]]:
    r = dl.conferir_site(url)
    if r["status"] != 200:
        return [("erro", f"site {nome} fora do ar ({r['erro'] or r['status']})")]
    if r["ms"] > SITE_LENTO_MS:
        return [("aviso", f"site {nome} lento: {r['ms'] / 1000:.1f} s")]
    return [("ok", f"site {nome} {r['ms']:.0f} ms")]


def _cabecalhos(extras: dict[str, str] | None = None) -> dict[str, str]:
    chave = dl.obter_variavel("SUPABASE_DMC_KEY")
    return {"apikey": chave, "Authorization": f"Bearer {chave}", **(extras or {})}


def checar_api(schema: str) -> list[tuple[str, str]]:
    url = dl.obter_variavel("SUPABASE_DMC_URL").rstrip("/")
    status, payload = dl.executar_com_retry(
        "API do DMC",
        lambda: dl.chamar_api_json(f"{url}/rest/v1/estoques?select=id&limit=1",
                                   cabecalhos=_cabecalhos({"Accept-Profile": schema}), timeout=30),
        TENTATIVAS, SEGUNDOS_ENTRE_TENTATIVAS,
    )
    if status != 200:
        return [("erro", f"API do DMC respondeu HTTP {status} ({str(payload.get('message', ''))[:80]})")]
    return [("ok", "API")]


def checar_auth() -> list[tuple[str, str]]:
    url = dl.obter_variavel("SUPABASE_DMC_URL").rstrip("/")
    status, payload = dl.chamar_api_json(f"{url}/auth/v1/settings", cabecalhos=_cabecalhos(), timeout=30)
    if status != 200:
        return [("erro", f"Auth do DMC respondeu HTTP {status}")]
    if not payload.get("disable_signup"):
        return [("erro", "Auth do DMC com cadastro aberto ligado: qualquer um cria conta")]
    return [("ok", "Auth fechado")]


def checar_funcoes(nomes: tuple[str, ...]) -> list[tuple[str, str]]:
    """Chama cada Edge Function SEM login de usuario (so a apikey, que passa o
    portao da Supabase). Esperado: a propria funcao recusar ({"ok": false},
    "Faca login de novo."). 404 = sumiu; 5xx = quebrada; aceitar = furo."""
    url = dl.obter_variavel("SUPABASE_DMC_URL").rstrip("/")
    resultado = []
    for nome in nomes:
        try:
            status, payload = dl.chamar_api_json(f"{url}/functions/v1/{nome}", "POST", corpo={},
                                                 cabecalhos={"apikey": dl.obter_variavel("SUPABASE_DMC_KEY")},
                                                 timeout=30)
        except RuntimeError as e:  # 5xx
            resultado.append(("erro", f"funcao {nome} com erro: {str(e)[:80]}"))
            continue
        if status == 404:
            resultado.append(("erro", f"funcao {nome} nao existe mais"))
        elif status in (401, 403) or (status == 200 and payload.get("ok") is False):
            resultado.append(("ok", f"funcao {nome} recusa sem login"))
        elif status == 200:
            resultado.append(("erro", f"funcao {nome} ACEITOU chamada sem login"))
        else:
            resultado.append(("aviso", f"funcao {nome} respondeu HTTP {status} sem login"))
    return resultado


def checar_banco() -> list[tuple[str, str]]:
    """Leitura so: RLS, tamanho, assinaturas e ultimo lancamento de cada app."""
    resultado = []
    hoje_utc = datetime.now(timezone.utc)
    with psycopg.connect(dl.obter_variavel("SUPABASE_DMC_DB_URL"), prepare_threshold=None,
                         connect_timeout=30, sslmode="require", application_name=f"robo_{IDCARGA:03d}") as conn:
        conn.read_only = True
        mb = conn.execute("select pg_database_size(current_database()) / 1e6").fetchone()[0]
        resultado.append(("aviso" if mb > BANCO_AVISO_MB else "ok", f"banco {mb:.0f} MB de 500"))

        for nome, _, schema, _ in APPS:
            sem_rls, total = conn.execute(
                "select count(*) filter (where not relrowsecurity), count(*) from pg_class "
                "where relnamespace = to_regnamespace(%s) and relkind = 'r'", (schema,)).fetchone()
            if total == 0:
                resultado.append(("erro", f"{nome}: schema {schema} sem tabelas"))
                continue
            if sem_rls:
                resultado.append(("erro", f"{nome}: {sem_rls} tabela(s) sem RLS (dado de um cliente aberto para outro)"))
            else:
                resultado.append(("ok", f"RLS em {total}/{total}"))

            negocios, bloqueados, cortesia, vencidos, vencendo = conn.execute(
                SQL_ASSINATURAS.format(schema=schema), (VENCENDO_DIAS,)).fetchone()
            resultado.append(("ok", f"{negocios} negócio(s), {cortesia} cortesia, {bloqueados} bloqueado(s)"))
            if vencidos:
                resultado.append(("aviso", f"{nome}: {vencidos} negócio(s) com assinatura vencida (só leitura)"))
            if vencendo:
                resultado.append(("aviso", f"{nome}: {vencendo} negócio(s) vencendo em até {VENCENDO_DIAS} dias"))

            ultimo = conn.execute(SQL_ULTIMO_LANCAMENTO.format(schema=schema)).fetchone()[0]
            dias = (hoje_utc - ultimo).days if ultimo else None
            resultado.append(("ok", f"último lançamento há {dias} dia(s)" if dias is not None else "nenhum lançamento"))
        conn.rollback()
    return resultado


# ─── carga ───────────────────────────────────────────────────────────────────


def avisar_no_hub(avisos: list[str]) -> None:
    """Notifica o hub so quando a lista de avisos muda (nada de repetir todo dia)."""
    titulo = ("⚠️ DMC: " + "; ".join(avisos))[:200] if avisos else None
    try:
        anterior = dl.ultima_notificacao(ORIGEM_AVISO)
    except Exception as e:  # noqa: BLE001 - aviso e extra, nao derruba o robo
        dl.log(f"[HUB] nao consegui ler a ultima notificacao: {e}")
        return
    if titulo and (not anterior or anterior.get("titulo") != titulo):
        dl.notificar_hub("atencao", titulo, None, origem=ORIGEM_AVISO)
        dl.notificar_discord(CANAL_DISCORD, titulo, "\n".join(f"• {a}" for a in avisos), nivel="atencao")
    elif not titulo and anterior and anterior.get("nivel") == "atencao":
        dl.notificar_hub("resolvido", "✅ DMC: avisos resolvidos", None, origem=ORIGEM_AVISO)
        dl.notificar_discord(CANAL_DISCORD, "✅ DMC: avisos resolvidos", None, nivel="ok", silencioso=True)


def processar() -> tuple[int, str]:
    """A carga. Devolve (qtd_itens, resumo) para o registro no Supabase."""
    global ITENS_FEITOS
    checagens: list[tuple[str, str]] = []
    for nome, site, schema, funcoes in APPS:
        checagens += checar_site(nome, site)
        checagens += checar_api(schema)
        checagens += checar_funcoes(funcoes)
    checagens += checar_auth()
    checagens += checar_banco()

    for nivel, texto in checagens:
        dl.log(f"[{nivel.upper():5}] {texto}")
    ITENS_FEITOS = sum(1 for n, _ in checagens if n == "ok")
    erros = [t for n, t in checagens if n == "erro"]
    avisos = [t for n, t in checagens if n == "aviso"]

    if not (DEBUG or DRY_RUN):
        avisar_no_hub(avisos)
    if erros:
        raise RuntimeError("DMC com problema: " + " · ".join(erros + avisos))

    ok = [t for n, t in checagens if n == "ok"]
    resumo = "DMC ok ✅ · " + " · ".join(ok)
    if avisos:
        resumo = "⚠️ " + " · ".join(avisos) + " | " + resumo
    return ITENS_FEITOS, resumo[:500]


def main() -> None:
    dl.configurar_logger(IDCARGA, NOME_ROBO, BASE)
    modo = dl.modo_execucao()
    dta_ini = datetime.now(timezone.utc)

    dl.logar_contexto(
        "DRY-RUN" if (DEBUG or DRY_RUN) else modo,
        extras={"Apps": ", ".join(a[0] for a in APPS), "DEBUG / DRY_RUN": f"{DEBUG} / {DRY_RUN}"},
    )
    if STATUS:
        env = dl.ler_env()
        for c in ("SUPABASE_DMC_URL", "SUPABASE_DMC_KEY", "SUPABASE_DMC_DB_URL", "SUPABASE_URL", "SUPABASE_KEY"):
            print(f"  {c:<22} {'configurado' if env.get(c) else 'AUSENTE'}")
        return

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
            dl.alertar_erro_robo(IDCARGA, NOME_ROBO, str(e), canal_cliente=CANAL_DISCORD)
        dl.log(f"[ROBO{IDCARGA:03d}] ❌ RESULTADO FINAL: ERRO")
        dl.log("=" * 70)
        arquivo = dl.salvar_log_erro()
        if arquivo:
            print(f"Log do erro: {arquivo}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
