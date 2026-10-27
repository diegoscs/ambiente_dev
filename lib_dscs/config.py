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

# lib_dscs\config.py -> lib_dscs -> D:\ambiente_dev
RAIZ = Path(__file__).resolve().parent.parent
ENV_FILE = RAIZ / ".env"

# Prefixos das variaveis que o ambiente pode sobrescrever. A lista e branca de
# proposito: o os.environ inteiro traria PATH, TEMP e companhia para dentro do
# dicionario de credenciais. Robo novo com prefixo novo entra aqui - foi o que
# aconteceu com SUPABASE_/TELEGRAM_/MODO_ no robo 002, que roda no GitHub
# Actions, onde NAO existe .env e tudo chega por variavel de ambiente. GH_ veio
# com o robo 001 na nuvem: o GitHub nao aceita secret com prefixo GITHUB_, entao
# o token dele chega como GH_PAT. (PG_ saiu em 27/10/2026 com o Postgres local.)
PREFIXOS_AMBIENTE = ("GITHUB_", "GH_", "SUPABASE_", "TELEGRAM_", "MODO_")


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
