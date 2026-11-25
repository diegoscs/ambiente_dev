# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 15/09/2026
# DESCRICAO      : Avisos no Discord por webhook (um por canal). Substituiu o
#                  Telegram em 25/11/2026 (nunca chegou a ser configurado).
#                  Plano em docs/PLANO_DISCORD.md.
#
#                  As URLs dos webhooks sao segredo (quem tem, posta no canal):
#                  ficam no .env / GitHub Secrets e NUNCA vao para log.
# =============================================
from __future__ import annotations

from datetime import datetime, timezone

from .api import chamar_api_json
from .config import ler_env
from .log import log

# Canal logico -> variavel com a URL do webhook.
CANAIS = {
    "alertas": "DISCORD_WEBHOOK_ALERTAS",       # erro ou atraso de qualquer robo
    "resumo": "DISCORD_WEBHOOK_RESUMO",         # resumo diario do vigia
    "estoque": "DISCORD_WEBHOOK_ESTOQUE",       # app do estoque (cliente)
}

CORES = {"erro": 0xB23A32, "atencao": 0xE6A23C, "ok": 0x2F7A4B, "info": 0x2B5F8E}

# O embed aceita 4096 caracteres na descricao; aviso e resumo, nao log.
LIMITE_DETALHE = 3500
NOME_REMETENTE = "ambiente_dev"


def discord_configurado(canal: str = "alertas") -> bool:
    """True se o webhook do canal existe no ambiente ou no .env."""
    return bool(ler_env().get(CANAIS.get(canal, "")))


def notificar_discord(canal: str, titulo: str, detalhe: str | None = None,
                      nivel: str = "info", silencioso: bool = False) -> bool:
    """Posta um aviso no canal e devolve True se chegou.

    NUNCA levanta: aviso e efeito colateral, nao a carga. Sem webhook
    configurado, so loga (rodar no PC sem .env completo continua funcionando).

    nivel: erro | atencao | ok | info (muda a cor). silencioso=True chega sem
    apitar no celular (flag SUPPRESS_NOTIFICATIONS do Discord).
    """
    variavel = CANAIS.get(canal)
    url = ler_env().get(variavel or "")
    if not url:
        log(f"[DISCORD] canal '{canal}' sem webhook ({variavel}) - aviso ignorado")
        return False

    from .supabase import url_execucao_actions  # import tardio: evita ciclo

    texto = (detalhe or "").strip()
    if len(texto) > LIMITE_DETALHE:
        texto = texto[:LIMITE_DETALHE] + "\n[...]"
    execucao = url_execucao_actions()
    if execucao:
        texto += f"\n\n[Ver a execução]({execucao})"

    corpo = {
        "username": NOME_REMETENTE,
        "embeds": [{
            "title": titulo[:250],
            "description": texto or None,
            "color": CORES.get(nivel, CORES["info"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
        "allowed_mentions": {"parse": []},
    }
    if silencioso:
        corpo["flags"] = 4096

    try:
        status, payload = chamar_api_json(f"{url}?wait=true", "POST", corpo=corpo,
                                          cabecalhos={"User-Agent": "lib_dscs (ambiente_dev)"}, timeout=20)
    except Exception as e:  # noqa: BLE001 - a mensagem do erro poderia conter a URL
        log(f"[DISCORD] canal '{canal}': falha ao enviar ({type(e).__name__})")
        return False

    if not 200 <= status < 300:
        log(f"[DISCORD] canal '{canal}': HTTP {status} ({str(payload.get('message', ''))[:80]})")
        return False
    log(f"[DISCORD] aviso enviado em '{canal}'")
    return True


def alertar_erro_robo(id_carga: int, nome_robo: str, erro: str, canal_cliente: str | None = None) -> bool:
    """Formato padrao do alerta de falha, igual em todos os robos: vai para
    #alertas e, se o robo e de um cliente, tambem para o canal dele."""
    titulo = f"❌ Robô {id_carga:03d} · {nome_robo} deu erro"
    ok = notificar_discord("alertas", titulo, erro, nivel="erro")
    if canal_cliente:
        notificar_discord(canal_cliente, titulo, erro, nivel="erro")
    return ok
