# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 15/09/2026
# DESCRICAO      : Os dois pings que mantem cada projeto Supabase acordado:
#                  conexao Postgres direta e REST (PostgREST).
#                  24/11/2026: um par de pings por projeto (DMP e DMC).
# =============================================
from __future__ import annotations

import time

import psycopg

import lib_dscs as dl
from config_robo import (
    PROJETOS,
    SEGUNDOS_ENTRE_TENTATIVAS,
    SQL_PING,
    TENTATIVAS,
    TIMEOUT_SEGUNDOS,
    Projeto,
    cabecalhos_rest,
    faltando,
    url_supabase,
    valor,
)

# Os dois caminhos existem de proposito. O Supabase mede atividade por
# componentes separados: o banco e a API REST tem contadores proprios, e ja
# houve relato de projeto pausado mesmo com um dos dois vivo. Pingar os dois
# custa dois segundos e tira a duvida.


def ping_postgres(projeto: Projeto) -> dict[str, object]:
    """SELECT direto no Postgres do projeto. Devolve metodo, latencia e amostra.
    prepare_threshold=None: funciona tambem no Transaction pooler (6543)."""
    inicio = time.perf_counter()

    with psycopg.connect(valor(projeto.var_banco), connect_timeout=TIMEOUT_SEGUNDOS,
                         prepare_threshold=None) as con:
        linha = con.execute(SQL_PING).fetchone()

    latencia_ms = round((time.perf_counter() - inicio) * 1000, 1)
    agora, banco, versao = linha

    resultado = {
        "projeto": projeto.nome,
        "metodo": "postgres",
        "latencia_ms": latencia_ms,
        "detalhe": f"{banco} | {versao.split(',')[0]} | now()={agora.isoformat()}",
    }
    dl.log(f"[PING] {projeto.nome} postgres OK em {latencia_ms} ms - {resultado['detalhe']}")
    return resultado


def ping_rest(projeto: Projeto) -> dict[str, object]:
    """SELECT via PostgREST numa tabela pequena que sempre existe no projeto
    (limit=1, uma coluna). Tabela vazia devolve [] com HTTP 200 - isso e
    sucesso, o que importa e a API ter respondido.
    """
    url = f"{url_supabase(projeto)}/rest/v1/{projeto.tabela}?select={projeto.coluna}&limit=1"

    inicio = time.perf_counter()
    status, payload = dl.chamar_api_json(
        url, "GET", cabecalhos=cabecalhos_rest(projeto), timeout=TIMEOUT_SEGUNDOS
    )
    latencia_ms = round((time.perf_counter() - inicio) * 1000, 1)

    # 4xx nao levanta no chamar_api_json (e erro de configuracao, nao transitorio),
    # entao o ping precisa transformar em excecao por conta propria - senao a
    # carga fecharia como SUCCESS com a API recusando a chave.
    if status != 200:
        raise RuntimeError(
            f"{projeto.nome}: REST respondeu HTTP {status}: "
            f"{payload.get('message') or payload.get('hint') or payload}"
        )

    resultado = {
        "projeto": projeto.nome,
        "metodo": "rest",
        "latencia_ms": latencia_ms,
        "detalhe": f"HTTP {status} | {len(payload) if isinstance(payload, list) else 1} linha(s)",
    }
    dl.log(f"[PING] {projeto.nome} rest OK em {latencia_ms} ms - {resultado['detalhe']}")
    return resultado


def executar_pings() -> list[dict[str, object]]:
    """Os dois pings de cada projeto, cada um com retry proprio.

    Retry separado de proposito: se o Postgres cair e o REST estiver de pe, o
    REST nao paga as tentativas do outro - e vice-versa. Um projeto com falha
    (ou sem variavel) nao impede os outros de serem pingados; no fim, qualquer
    falha derruba a carga para ERROR, porque metade da atividade nao garante o
    projeto acordado.
    """
    resultados: list[dict[str, object]] = []
    erros: list[str] = []
    for projeto in PROJETOS:
        if faltando(projeto):
            erros.append(f"{projeto.nome}: faltam {', '.join(faltando(projeto))}")
            continue
        for nome, funcao in (("postgres", ping_postgres), ("rest", ping_rest)):
            try:
                resultados.append(dl.executar_com_retry(
                    f"ping {projeto.nome} {nome}", lambda f=funcao: f(projeto),
                    tentativas=TENTATIVAS, espera=SEGUNDOS_ENTRE_TENTATIVAS,
                ))
            except Exception as e:  # segue para os outros; vira erro no fim
                erros.append(f"{projeto.nome} {nome}: {e}")

    if erros:
        raise RuntimeError(" · ".join(erros))

    resumo = " | ".join(f"{r['projeto']} {r['metodo']}={r['latencia_ms']}ms" for r in resultados)
    dl.log(f"[PING] ✅ todos responderam: {resumo}")
    return resultados
