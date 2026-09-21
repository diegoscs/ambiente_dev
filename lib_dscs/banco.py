# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 05/09/2026
# DESCRICAO      : Conexao com o Postgres e helpers de query/comando.
# =============================================
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg

from .config import descrever_conexao, obter_configuracao


def abrir_conexao_banco(autocommit: bool = True) -> psycopg.Connection:
    """Conexao crua. Quem chama e responsavel por fechar.

    autocommit=True  -> registro de status: precisa ficar gravado mesmo que a
                        carga estoure logo depois.
    autocommit=False -> carga transacional: TRUNCATE + INSERT na mesma
                        transacao, com commit/rollback na mao.
    """
    return psycopg.connect(**obter_configuracao(), autocommit=autocommit)


@contextmanager
def conexao(autocommit: bool = True) -> Iterator[psycopg.Connection]:
    """Conexao com fechamento garantido, inclusive em erro:

        with dl.conexao() as con:
            con.execute(...)
    """
    con = abrir_conexao_banco(autocommit=autocommit)
    try:
        yield con
    finally:
        con.close()


def executar_query(sql: str, parametros: tuple | None = None) -> list[tuple]:
    """SELECT avulso. Abre e fecha uma conexao por chamada.

    Para muitas chamadas seguidas ou volume grande, abra a conexao uma vez com
    `conexao()` e itere o cursor - senao o custo e uma conexao por statement.
    """
    with conexao() as con:
        return con.execute(sql, parametros).fetchall()


def executar_query_dict(sql: str, parametros: tuple | None = None) -> list[dict[str, Any]]:
    """Igual ao executar_query, mas devolve dicionarios em vez de tuplas."""
    with conexao() as con:
        cursor = con.execute(sql, parametros)
        colunas = [d.name for d in cursor.description]
        return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def executar_comando(sql: str, parametros: tuple | None = None) -> int:
    """INSERT/UPDATE/DELETE avulso. Devolve quantas linhas foram afetadas."""
    with conexao() as con:
        return con.execute(sql, parametros).rowcount


def testar_conexao() -> str:
    """Uma linha com versao, banco e usuario. Use para validar o .env."""
    with conexao() as con:
        versao, banco, usuario = con.execute(
            "SELECT version(), current_database(), current_user"
        ).fetchone()

    return f"{versao.split(',')[0]} | {descrever_conexao()} | conectado como {usuario}"
