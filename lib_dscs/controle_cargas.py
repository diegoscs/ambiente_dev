# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 05/09/2026
# DESCRICAO      : Registro de status das cargas em dbo.controle_cargas.
#                  status_inicio / status_sucesso / status_erro.
# =============================================
from __future__ import annotations

from typing import Any

from .banco import conexao

TABELA_CONTROLE = "dbo.controle_cargas"

# Valores gravados na coluna status. NAO invente outros: a tabela tem a check
# constraint ck_status, que so aceita estes tres e derruba a carga no resto.
#   CHECK (status = ANY (ARRAY['RUNNING', 'SUCCESS', 'ERROR']))
STATUS_INICIO = "RUNNING"
STATUS_SUCESSO = "SUCCESS"
STATUS_ERRO = "ERROR"


def _atualizar(id_carga: int, status: str, zerar_fim: bool) -> None:
    """Base dos tres status_*.

    id_carga inexistente estoura de proposito: silenciar esconderia um numero
    digitado errado, e o sintoma seria um monitoramento vazio que ninguem
    relaciona com o robo.
    """
    coluna_fim = "NULL" if zerar_fim else "now()"

    sql = f"""
        UPDATE {TABELA_CONTROLE}
           SET status    = %s,
               dta_fim   = {coluna_fim},
               dta_modif = now()
             {", dta_ini = now()" if zerar_fim else ""}
         WHERE id_carga  = %s
    """

    with conexao(autocommit=True) as con:
        linhas = con.execute(sql, (status, id_carga)).rowcount

    if linhas == 0:
        raise ValueError(
            f"id_carga {id_carga} nao existe em {TABELA_CONTROLE}. "
            f"Cadastre a carga antes de registrar status."
        )


def status_inicio(id_carga: int) -> None:
    """Abre a execucao: status='Inicio', dta_ini=agora, dta_fim=NULL.

    O dta_fim volta para NULL de proposito. Status 'Inicio' com dta_fim nulo
    significa "rodando agora ou morreu no meio sem fechar" - e assim que se
    descobre robo que caiu sem registrar o erro (ex.: maquina desligada).
    """
    _atualizar(id_carga, STATUS_INICIO, zerar_fim=True)


def status_sucesso(id_carga: int) -> None:
    """Fecha com sucesso: status='Sucesso', dta_fim=agora."""
    _atualizar(id_carga, STATUS_SUCESSO, zerar_fim=False)


def status_erro(id_carga: int) -> None:
    """Fecha com erro: status='Erro', dta_fim=agora.

    A tabela nao tem coluna de mensagem, entao o motivo fica no log do proprio
    robo (logs\\robo_<id>_<nome>_AAAAMMDD.txt). Aqui so marca o estado.
    """
    _atualizar(id_carga, STATUS_ERRO, zerar_fim=False)


def obter_carga(id_carga: int) -> dict[str, Any] | None:
    """Linha de controle da carga, ou None se o id nao existe."""
    with conexao() as con:
        cursor = con.execute(
            f"SELECT * FROM {TABELA_CONTROLE} WHERE id_carga = %s", (id_carga,)
        )
        linha = cursor.fetchone()
        if linha is None:
            return None
        colunas = [d.name for d in cursor.description]

    return dict(zip(colunas, linha))


def listar_cargas(somente_ativas: bool = False) -> list[dict[str, Any]]:
    """Todas as cargas cadastradas, para conferir o monitoramento."""
    filtro = "WHERE flg_ativo IS TRUE" if somente_ativas else ""

    with conexao() as con:
        cursor = con.execute(
            f"SELECT * FROM {TABELA_CONTROLE} {filtro} ORDER BY id_carga"
        )
        colunas = [d.name for d in cursor.description]
        return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]
