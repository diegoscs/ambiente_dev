# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 15/09/2026
# DESCRICAO      : Configuracao do robo 002. Le o ambiente uma vez e valida o
#                  que falta ANTES de abrir conexao, para o erro dizer qual
#                  chave esta faltando em vez de "conexao recusada".
#                  24/11/2026: dois projetos (DMP e DMC), cada um com os dois
#                  pings.
# =============================================
from __future__ import annotations

from dataclasses import dataclass

import lib_dscs as dl

IDCARGA = 2
NOME_ROBO = "check_supabase"


# ─── projetos ────────────────────────────────────────────────────────────────
# Cada projeto tem tres variaveis (no Actions, GitHub Secrets):
#   url     https://<ref>.supabase.co
#   chave   service_role / secret key (le a tabela do ping sem esbarrar na RLS)
#   banco   string de conexao do pooler (6543 ou 5432), para o ping via Postgres
# O DMP (pessoal: hub, robos, financas) usa os nomes antigos, que a lib_dscs
# tambem usa para registrar as cargas. O DMC (apps de clientes) tem os seus.
@dataclass(frozen=True)
class Projeto:
    nome: str
    var_url: str
    var_chave: str
    var_banco: str
    schema: str  # schema da tabela do ping REST (vai no Accept-Profile)
    tabela: str  # tabela pequena que sempre existe no projeto
    coluna: str


PROJETOS = (
    Projeto("DMP", "SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_DB_URL",
            "public", "controle_cargas", "id_carga"),
    Projeto("DMC", "SUPABASE_DMC_URL", "SUPABASE_DMC_KEY", "SUPABASE_DMC_DB_URL",
            "estoque", "estoques", "id"),
)

# ─── comportamento ───────────────────────────────────────────────────────────
# O projeto free e pausado por ~7 dias sem atividade. O pg_cron dispara todo dia
# e o schedule do GitHub e a reserva: margem de sobra para varias execucoes
# falharem sem o projeto dormir.
TENTATIVAS = 3
SEGUNDOS_ENTRE_TENTATIVAS = 20
TIMEOUT_SEGUNDOS = 30

# Consulta leve, porem real: o Supabase so conta como atividade o que chega no
# banco. select 1 resolvido pelo pooler nao serve - por isso now() (PG) e um
# select de verdade numa tabela (REST).
SQL_PING = "select now() as agora, current_database() as banco, version() as versao"


def valor(nome_variavel: str) -> str:
    return (dl.ler_env().get(nome_variavel) or "").strip()


def url_supabase(projeto: Projeto = PROJETOS[0]) -> str:
    return valor(projeto.var_url).rstrip("/")


def cabecalhos_rest(projeto: Projeto) -> dict[str, str]:
    """Cabecalhos do PostgREST. A chave vai em apikey E em Authorization -
    o PostgREST exige as duas, e sem a segunda o papel cai para anon.
    Accept-Profile escolhe o schema da tabela."""
    chave = valor(projeto.var_chave)
    return {
        "apikey": chave,
        "Authorization": f"Bearer {chave}",
        "Accept": "application/json",
        "Accept-Profile": projeto.schema,
        "User-Agent": f"robo-{IDCARGA:03d}-{NOME_ROBO}",
    }


def faltando(projeto: Projeto) -> list[str]:
    return [v for v in (projeto.var_url, projeto.var_chave, projeto.var_banco) if not valor(v)]


def validar_configuracao(modo: str) -> None:
    """Estoura antes de qualquer conexao so se o DMP (onde o robo registra)
    estiver incompleto. Projeto sem variavel e avisado aqui e vira erro no fim,
    depois de pingar os outros: um secret faltando nao deixa os demais dormirem.
    """
    if faltando(PROJETOS[0]):
        raise ValueError(
            f"Faltam variaveis no ambiente/.env: {', '.join(faltando(PROJETOS[0]))}. "
            f"Veja o .env.example na raiz."
        )
    for projeto in PROJETOS[1:]:
        if faltando(projeto):
            dl.log(f"[CONFIG] ⚠ {projeto.nome} sem {', '.join(faltando(projeto))}: nao sera pingado")

    if not dl.discord_configurado():
        dl.log("[CONFIG] ⚠ DISCORD_WEBHOOK_ALERTAS ausente: sem alerta de falha")

    dl.log(f"[CONFIG] modo={modo} | projetos={', '.join(p.nome for p in PROJETOS)}")
