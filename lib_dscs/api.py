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
