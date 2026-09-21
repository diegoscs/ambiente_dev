# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 15/09/2026
# DESCRICAO      : Alerta de falha por Telegram. Credenciais no .env da raiz
#                  (TELEGRAM_TOKEN / TELEGRAM_CHAT_ID).
# =============================================
from __future__ import annotations

from .api import chamar_api_json
from .config import ler_env, obter_variavel
from .log import log

API_TELEGRAM = "https://api.telegram.org"

# Limite do sendMessage e 4096 caracteres. Cortamos bem antes: alerta e resumo,
# nao e log - o traceback inteiro fica no arquivo de erro do robo.
LIMITE_MENSAGEM = 1200


def telegram_configurado() -> bool:
    """True se as duas variaveis existem no ambiente ou no .env.

    Le pelo ler_env, e nao pelo obter_variavel: este ultimo trata string vazia
    como ausente e levanta ValueError - o que aqui seria o oposto do esperado,
    ja que a pergunta e justamente "esta configurado?".
    """
    valores = ler_env()
    return bool(valores.get("TELEGRAM_TOKEN")) and bool(valores.get("TELEGRAM_CHAT_ID"))


def alertar_telegram(mensagem: str, silencioso: bool = False) -> bool:
    """Envia o alerta e devolve True se chegou.

    NUNCA levanta excecao. Alerta e efeito colateral do erro, nao a carga: se o
    Telegram estiver fora, o robo ja esta tratando um problema e nao pode trocar
    a causa real por uma falha de notificacao. O que acontece aqui vira linha de
    log e nada mais.

    silencioso=True manda sem som (o Telegram chama de disable_notification).
    """
    if not telegram_configurado():
        log("[TELEGRAM] nao configurado (TELEGRAM_TOKEN/TELEGRAM_CHAT_ID) - alerta ignorado")
        return False

    texto = mensagem.strip()
    if len(texto) > LIMITE_MENSAGEM:
        texto = texto[:LIMITE_MENSAGEM] + "\n[...] (mensagem cortada)"

    token = obter_variavel("TELEGRAM_TOKEN")
    url = f"{API_TELEGRAM}/bot{token}/sendMessage"
    corpo = {
        "chat_id": obter_variavel("TELEGRAM_CHAT_ID"),
        "text": texto,
        "disable_notification": silencioso,
    }

    try:
        status, payload = chamar_api_json(url, "POST", corpo=corpo)
    except Exception as e:  # noqa: BLE001 - alerta nunca derruba o robo
        log(f"[TELEGRAM] falha ao enviar: {e}")
        return False

    if status != 200:
        log(f"[TELEGRAM] HTTP {status}: {payload.get('description') or payload.get('message')}")
        return False

    log("[TELEGRAM] alerta enviado")
    return True


def alertar_erro_robo(id_carga: int, nome_robo: str, erro: str) -> bool:
    """Formato padrao do alerta de falha, igual em todos os robos."""
    return alertar_telegram(
        f"\u274c ROBO {id_carga:03d} - {nome_robo}\n"
        f"Status: ERROR\n"
        f"Erro: {erro}"
    )
