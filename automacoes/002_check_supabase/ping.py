# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 15/09/2026
# DESCRICAO      : Os dois pings que mantem o projeto Supabase acordado:
#                  conexao Postgres direta e REST (PostgREST).
# =============================================
from __future__ import annotations

import time

import psycopg

import lib_dscs as dl
from config_robo import (
    SQL_PING,
    TABELA_SUPABASE,
    TIMEOUT_SEGUNDOS,
    cabecalhos_rest,
    url_banco_supabase,
    url_supabase,
)

# Os dois caminhos existem de proposito. O Supabase mede atividade por
# componentes separados: o banco e a API REST tem contadores proprios, e ja
# houve relato de projeto pausado mesmo com um dos dois vivo. Pingar os dois
# custa dois segundos e tira a duvida.


def ping_postgres() -> dict[str, object]:
    """SELECT direto no Postgres do Supabase. Devolve metodo, latencia e amostra."""
    inicio = time.perf_counter()

    with psycopg.connect(url_banco_supabase(), connect_timeout=TIMEOUT_SEGUNDOS) as con:
        linha = con.execute(SQL_PING).fetchone()

    latencia_ms = round((time.perf_counter() - inicio) * 1000, 1)
    agora, banco, versao = linha

    resultado = {
        "metodo": "postgres",
        "latencia_ms": latencia_ms,
        "detalhe": f"{banco} | {versao.split(',')[0]} | now()={agora.isoformat()}",
    }
    dl.log(f"[PING] postgres OK em {latencia_ms} ms - {resultado['detalhe']}")
    return resultado


def ping_rest() -> dict[str, object]:
    """SELECT via PostgREST na tabela de controle.

    Usa a tabela de controle porque ela sempre existe no projeto (o proprio robo
    a mantem) e e pequena: limit=1 com uma coluna so. Tabela vazia devolve []
    com HTTP 200 - isso e sucesso, o que importa e a API ter respondido.
    """
    url = f"{url_supabase()}/rest/v1/{TABELA_SUPABASE}?select=id_carga&limit=1"

    inicio = time.perf_counter()
    status, payload = dl.chamar_api_json(
        url, "GET", cabecalhos=cabecalhos_rest(), timeout=TIMEOUT_SEGUNDOS
    )
    latencia_ms = round((time.perf_counter() - inicio) * 1000, 1)

    # 4xx nao levanta no chamar_api_json (e erro de configuracao, nao transitorio),
    # entao o ping precisa transformar em excecao por conta propria - senao a
    # carga fecharia como SUCCESS com a API recusando a chave.
    if status != 200:
        raise RuntimeError(
            f"REST respondeu HTTP {status}: "
            f"{payload.get('message') or payload.get('hint') or payload}"
        )

    resultado = {
        "metodo": "rest",
        "latencia_ms": latencia_ms,
        "detalhe": f"HTTP {status} | {len(payload) if isinstance(payload, list) else 1} linha(s)",
    }
    dl.log(f"[PING] rest OK em {latencia_ms} ms - {resultado['detalhe']}")
    return resultado


def executar_pings() -> list[dict[str, object]]:
    """Os dois pings, cada um com retry proprio.

    Retry separado de proposito: se o Postgres cair e o REST estiver de pe, o
    REST nao paga as tentativas do outro - e vice-versa. Qualquer um dos dois
    falhando apos as tentativas derruba a carga para ERROR, porque metade da
    atividade nao garante o projeto acordado.
    """
    from config_robo import SEGUNDOS_ENTRE_TENTATIVAS, TENTATIVAS

    resultados = []
    for nome, funcao in (("ping postgres", ping_postgres), ("ping rest", ping_rest)):
        resultados.append(
            dl.executar_com_retry(
                nome, funcao, tentativas=TENTATIVAS, espera=SEGUNDOS_ENTRE_TENTATIVAS
            )
        )

    resumo = " | ".join(f"{r['metodo']}={r['latencia_ms']}ms" for r in resultados)
    dl.log(f"[PING] ✅ ambos responderam: {resumo}")
    return resultados
