# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 26/09/2026
# DESCRICAO      : Vigia dos robos. Le a vw_saude_robos no Supabase e FALHA
#                  (exit 1) se algum robo estiver com ERRO, ATRASADO, TRAVADO
#                  ou NUNCA_RODOU. Roda no GitHub Actions: run vermelho = e-mail
#                  do GitHub, mais o alerta no Telegram quando configurado.
#
#                  Existe porque robo que nao roda nao avisa nada - o silencio
#                  dele e identico ao do sucesso. O vigia transforma "nao rodou"
#                  em uma falha que alguem recebe, sem precisar abrir o hub.
# =============================================
from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import lib_dscs as dl


TZ = ZoneInfo("America/Sao_Paulo")
SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def quando(iso: str | None) -> str:
    """Horario legivel em Sao Paulo: "hoje 07:38", "ontem 13:09", "seg 07:12", "02/10 07:38"."""
    if not iso:
        return "nunca"
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)
    dias = (datetime.now(TZ).date() - dt.date()).days
    hora = dt.strftime("%H:%M")
    if dias == 0:
        return f"hoje {hora}"
    if dias == 1:
        return f"ontem {hora}"
    if 1 < dias < 7:
        return f"{SEMANA[dt.weekday()]} {hora}"
    return dt.strftime("%d/%m %H:%M")


def nome(r: dict) -> str:
    return re.sub(r"^\d+\s*-\s*", "", r["nome_carga"])


def robos_txt(n: int) -> str:
    return "1 robô" if n == 1 else f"{n} robôs"


def descrever_problema(r: dict) -> str:
    saude = r["saude"]
    ultima = quando(r.get("dta_fim") or r.get("dta_ini"))
    try:
        horas = f"há {float(r.get('horas_desde')):.0f} h"
    except (TypeError, ValueError):
        horas = ""
    if saude == "ERRO":
        motivo = re.sub(r"^⚠️\s*", "", r.get("mensagem") or "sem detalhe")
        return f"❌ {nome(r)}: deu erro ({ultima}) · {motivo}"
    if saude == "ATRASADO":
        return f"⏰ {nome(r)}: atrasado, última execução {ultima}" + (f" ({horas})" if horas else "")
    if saude == "TRAVADO":
        return f"🧊 {nome(r)}: travado, rodando desde {quando(r.get('dta_ini'))}"
    if saude == "NUNCA_RODOU":
        return f"❔ {nome(r)}: ainda não rodou nenhuma vez"
    return f"{nome(r)}: {saude}"


def main() -> int:
    robos = dl.ler_saude_robos()
    if not robos:
        print("Nenhum robo ativo em vw_saude_robos - nada a vigiar.")
        return 0

    problemas = []
    for r in robos:
        horas = r.get("horas_desde") or "?"
        print(
            f"{r['nome_carga']:<24} {r['saude']:<12} "
            f"ha {horas} h | {r.get('ambiente') or '-'} | {r.get('mensagem') or ''}"
        )
        if r["saude"] not in dl.SAUDE_BOA:
            problemas.append(descrever_problema(r))

    # Uma notificacao por verificacao, para o hub mostrar que o vigia passou.
    # "resolvido" quando a anterior era de atencao e agora esta tudo em dia.
    try:
        anterior = dl.ultima_notificacao("vigia")
    except Exception as e:  # noqa: BLE001 - so muda o texto da notificacao
        print(f"(nao consegui ler a notificacao anterior: {e})", file=sys.stderr)
        anterior = None

    # Detalhe das notificacoes: um robo por linha, com a ultima execucao.
    em_dia = "\n".join(
        f"• {nome(r)} · {quando(r.get('dta_fim') or r.get('dta_ini'))}"
        for r in robos if r["saude"] in dl.SAUDE_BOA
    )

    if problemas:
        n = len(problemas)
        titulo = f"⚠️ {robos_txt(n)} {'precisa' if n == 1 else 'precisam'} de atenção"
        detalhe = "\n".join(problemas) + (f"\n\nEm dia:\n{em_dia}" if em_dia else "")
        dl.notificar_hub("atencao", titulo, detalhe)
        print(f"\nATENCAO: {'; '.join(problemas)}", file=sys.stderr)
        dl.alertar_telegram(f"{titulo}\n\n" + "\n".join(problemas))
        return 1

    if anterior and anterior.get("nivel") == "atencao":
        dl.notificar_hub("resolvido", f"✅ Voltou ao normal: {robos_txt(len(robos))} em dia", em_dia)
        dl.alertar_telegram(f"✅ Voltou ao normal: {robos_txt(len(robos))} em dia", silencioso=True)
    else:
        dl.notificar_hub("info", f"✅ Tudo certo: {robos_txt(len(robos))} em dia", em_dia)
    print(f"\nOK: {len(robos)} robo(s) em dia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
