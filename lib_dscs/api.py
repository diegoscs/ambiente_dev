# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 05/09/2026
# DESCRICAO      : Cliente HTTP/JSON dos robos de API. Sem dependencia externa,
#                  so urllib da biblioteca padrao.
# =============================================
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

TIMEOUT_PADRAO = 30  # segundos


def chamar_api_json(
    url: str,
    metodo: str = "GET",
    corpo: dict | list | None = None,
    cabecalhos: dict[str, str] | None = None,
    token: str | None = None,
    timeout: int = TIMEOUT_PADRAO,
) -> tuple[int, dict[str, Any]]:
    """Requisicao HTTP com corpo e resposta em JSON.

    Devolve (status, payload). O payload de erro tambem volta decodificado -
    quase toda API poe o motivo em {"message": ...}, e engolir isso deixaria o
    log so com o numero do status.

    Regra de erro, de proposito assimetrica:

      5xx  -> levanta RuntimeError. E falha do outro lado, transitoria: quem
              chamou provavelmente quer envolver em executar_com_retry.
      4xx  -> devolve (status, payload) sem levantar. E erro de configuracao
              (token, permissao, recurso inexistente) e insistir nao ajuda -
              cada robo decide o que fazer com um 404, que as vezes e esperado.

    Nao faz retry: isso e responsabilidade do executar_com_retry, uma camada
    acima, que sabe o nome da etapa e loga cada tentativa.
    """
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None

    requisicao = urllib.request.Request(url, data=dados, method=metodo)
    for chave, valor in (cabecalhos or {}).items():
        requisicao.add_header(chave, valor)
    if token:
        requisicao.add_header("Authorization", f"Bearer {token}")
    if dados:
        requisicao.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            texto = resposta.read().decode("utf-8")
            return resposta.status, (json.loads(texto) if texto else {})

    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(texto)
        except json.JSONDecodeError:
            payload = {"message": texto[:300]}

        if e.code >= 500:
            raise RuntimeError(
                f"HTTP {e.code} em {metodo} {url}: {payload.get('message')}"
            ) from e

        return e.code, payload


def conferir_site(url: str, timeout: int = TIMEOUT_PADRAO) -> dict[str, Any]:
    """GET num site (resposta HTML, nao JSON): ele abre e em quanto tempo.

    Devolve {"status": int | None, "ms": float, "erro": str | None}. Nunca
    levanta: site fora do ar e um resultado, nao uma excecao. status None =
    nem respondeu (DNS, timeout, certificado).
    """
    import time

    requisicao = urllib.request.Request(url, method="GET")
    requisicao.add_header("User-Agent", "lib_dscs (conferir_site)")
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            resposta.read(2048)
            status, erro = resposta.status, None
    except urllib.error.HTTPError as e:
        status, erro = e.code, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - qualquer falha de rede vira resultado
        status, erro = None, f"{type(e).__name__}: {str(e)[:150]}"
    return {"status": status, "ms": round((time.perf_counter() - inicio) * 1000, 1), "erro": erro}


def validade_token_github(token: str, timeout: int = TIMEOUT_PADRAO) -> dict[str, Any]:
    """Confere um token do GitHub sem gastar cota (GET /rate_limit).

    Devolve {"status": int, "expira": datetime | None, "valido": bool}. `expira`
    vem do cabecalho github-authentication-token-expiration, que o GitHub so
    manda para token com data de validade; None = token sem vencimento.
    401 = token vencido, revogado ou errado. Nunca loga o token.
    """
    from datetime import datetime, timezone

    requisicao = urllib.request.Request("https://api.github.com/rate_limit", method="GET")
    requisicao.add_header("Authorization", f"Bearer {token}")
    requisicao.add_header("Accept", "application/vnd.github+json")
    requisicao.add_header("User-Agent", "lib_dscs")
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            status, cabecalho = resposta.status, resposta.headers.get("github-authentication-token-expiration")
    except urllib.error.HTTPError as e:
        if e.code >= 500:
            raise RuntimeError(f"HTTP {e.code} em GET /rate_limit") from e
        return {"status": e.code, "expira": None, "valido": False}

    expira = None
    if cabecalho:  # "2026-12-31 23:59:59 UTC" (as vezes com fuso numerico)
        texto = cabecalho.replace(" UTC", " +0000")
        for formato in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"):
            try:
                expira = datetime.strptime(texto, formato)
                break
            except ValueError:
                continue
        if expira and expira.tzinfo is None:
            expira = expira.replace(tzinfo=timezone.utc)
    return {"status": status, "expira": expira, "valido": 200 <= status < 300}

