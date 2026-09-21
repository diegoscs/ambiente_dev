# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 05/09/2026
# DESCRICAO      : Leitura das credenciais do ambiente. Tudo vem do .env da
#                  raiz (D:\ambiente_dev\.env) - nenhum robo le credencial
#                  direto do arquivo, sempre passa por aqui.
# =============================================
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# lib_dscs\config.py -> lib_dscs -> D:\ambiente_dev
RAIZ = Path(__file__).resolve().parent.parent
ENV_FILE = RAIZ / ".env"

TIMEOUT_CONEXAO = 10  # segundos para a conexao com o banco

# Prefixos das variaveis que o ambiente pode sobrescrever. A lista e branca de
# proposito: o os.environ inteiro traria PATH, TEMP e companhia para dentro do
# dicionario de credenciais. Robo novo com prefixo novo entra aqui - foi o que
# aconteceu com SUPABASE_/TELEGRAM_/MODO_ no robo 002, que roda no GitHub
# Actions, onde NAO existe .env e tudo chega por variavel de ambiente.
PREFIXOS_AMBIENTE = ("PG_", "GITHUB_", "SUPABASE_", "TELEGRAM_", "MODO_")


def ler_env() -> dict[str, str]:
    """Le o .env da raiz (CHAVE=VALOR, # para comentario).

    A variavel de ambiente do Windows tem prioridade sobre o arquivo: da para
    sobrescrever uma credencial numa execucao pontual sem editar o .env.
    """
    valores: dict[str, str] = {}

    if ENV_FILE.exists():
        for linha in ENV_FILE.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            valores[chave.strip()] = valor.strip().strip('"').strip("'")

    for chave, valor in os.environ.items():
        if chave.startswith(PREFIXOS_AMBIENTE):
            valores[chave] = valor

    return valores


def obter_variavel(chave: str, padrao: str | None = None) -> str:
    """Uma variavel do .env. Sem valor e sem padrao, estoura com a chave no erro."""
    valor = ler_env().get(chave, padrao)

    if valor is None or valor == "":
        raise ValueError(f"Variavel '{chave}' nao configurada em {ENV_FILE}")

    return valor


def obter_configuracao() -> dict[str, Any]:
    """Parametros de conexao com o Postgres, validados antes de conectar.

    Host e porta tem padrao porque o banco e local; banco, usuario e senha nao
    tem - errar em silencio ali daria "conexao recusada" sem dizer o motivo.
    """
    env = ler_env()

    faltando = [c for c in ("PG_DB", "PG_USER", "PG_PASSWORD") if not env.get(c)]
    if faltando:
        raise ValueError(
            f"Credenciais do Postgres ausentes em {ENV_FILE}: {', '.join(faltando)}"
        )

    return {
        "host": env.get("PG_HOST", "localhost"),
        "port": int(env.get("PG_PORT", "5432")),
        "dbname": env["PG_DB"],
        "user": env["PG_USER"],
        "password": env["PG_PASSWORD"],
        "connect_timeout": TIMEOUT_CONEXAO,
    }


def descrever_conexao() -> str:
    """Identificacao da conexao para log, sem a senha."""
    cfg = obter_configuracao()
    return f"{cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
