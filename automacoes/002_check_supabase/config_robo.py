# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 15/09/2026
# DESCRICAO      : Configuracao do robo 002. Le o ambiente uma vez e valida o
#                  que falta ANTES de abrir conexao, para o erro dizer qual
#                  chave esta faltando em vez de "conexao recusada".
# =============================================
from __future__ import annotations

import lib_dscs as dl

IDCARGA = 2
NOME_ROBO = "check_supabase"
NOME_CARGA = "002 - Check Supabase"

# ─── modo de execucao ────────────────────────────────────────────────────────
# LOCAL -> registra em dbo.controle_cargas (Postgres dm) e espelha no Supabase.
#          E o modo do Agendador do Windows; a tabela local e a fonte da verdade.
# CLOUD -> nao existe Postgres local (GitHub Actions). Faz o ping e grava a
#          carga direto no Supabase, que ali e a unica fonte disponivel.
MODO_LOCAL = "LOCAL"
MODO_CLOUD = "CLOUD"

# ─── Supabase ────────────────────────────────────────────────────────────────
# SUPABASE_URL      https://<ref>.supabase.co
# SUPABASE_KEY      service_role (precisa escrever na tabela de controle; a anon
#                   esbarra na RLS). No Actions vai como GitHub Secret.
# SUPABASE_DB_URL   string de conexao do pooler, para o ping via Postgres:
#                   postgresql://postgres.<ref>:<senha>@aws-0-<regiao>.pooler.supabase.com:6543/postgres
TABELA_SUPABASE = "controle_cargas"

# ─── comportamento ───────────────────────────────────────────────────────────
# O projeto free e pausado por ~7 dias sem atividade. O cron do Actions roda a
# cada 2 dias e o Agendador diariamente: margem de sobra para uma execucao
# falhar inteira sem o projeto dormir.
TENTATIVAS = 3
SEGUNDOS_ENTRE_TENTATIVAS = 20
TIMEOUT_SEGUNDOS = 30

# Consulta leve, porem real: o Supabase so conta como atividade o que chega no
# banco. select 1 resolvido pelo pooler nao serve - por isso now() (PG) e um
# select de verdade na tabela de controle (REST).
SQL_PING = "select now() as agora, current_database() as banco, version() as versao"


def modo_execucao() -> str:
    """LOCAL (padrao) ou CLOUD, de MODO_EXECUCAO."""
    modo = (dl.ler_env().get("MODO_EXECUCAO") or MODO_LOCAL).strip().upper()
    if modo not in (MODO_LOCAL, MODO_CLOUD):
        raise ValueError(
            f"MODO_EXECUCAO invalido: {modo!r}. Use {MODO_LOCAL} ou {MODO_CLOUD}."
        )
    return modo


def url_supabase() -> str:
    return dl.obter_variavel("SUPABASE_URL").rstrip("/")


def chave_supabase() -> str:
    return dl.obter_variavel("SUPABASE_KEY")


def url_banco_supabase() -> str:
    return dl.obter_variavel("SUPABASE_DB_URL")


def cabecalhos_rest(extras: dict[str, str] | None = None) -> dict[str, str]:
    """Cabecalhos do PostgREST. A chave vai em apikey E em Authorization -
    o PostgREST exige as duas, e sem a segunda o papel cai para anon."""
    chave = chave_supabase()
    cabecalhos = {
        "apikey": chave,
        "Authorization": f"Bearer {chave}",
        "Accept": "application/json",
        "User-Agent": f"robo-{IDCARGA:03d}-{NOME_ROBO}",
    }
    cabecalhos.update(extras or {})
    return cabecalhos


def validar_configuracao(modo: str) -> None:
    """Estoura antes de qualquer conexao, dizendo a chave que falta.

    Segredo errado nao melhora com retry: a validacao fica aqui, fora do
    executar_com_retry, para nao repetir tres vezes o que ja nasceu quebrado.
    """
    valores = dl.ler_env()
    faltando = [
        chave
        for chave in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_DB_URL")
        if not valores.get(chave)
    ]
    if faltando:
        raise ValueError(
            f"Faltam variaveis no ambiente/.env: {', '.join(faltando)}. "
            f"Veja o .env.example na raiz."
        )

    if not dl.telegram_configurado():
        dl.log("[CONFIG] ⚠ TELEGRAM_TOKEN/TELEGRAM_CHAT_ID ausentes: sem alerta de falha")

    dl.log(f"[CONFIG] modo={modo} | destino={url_supabase()}")
