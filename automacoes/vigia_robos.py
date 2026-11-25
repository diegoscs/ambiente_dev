# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 26/09/2026
# DESCRICAO      : Vigia dos robos. Le a vw_saude_robos no Supabase e FALHA
#                  (exit 1) se algum robo estiver com ERRO, ATRASADO, TRAVADO
#                  ou NUNCA_RODOU. Roda no GitHub Actions: run vermelho = e-mail
#                  do GitHub, mais o aviso no Discord (#alertas). Todo dia
#                  manda tambem o resumo de todos os robos em #resumo-diario.
#
#                  Existe porque robo que nao roda nao avisa nada - o silencio
#                  dele e identico ao do sucesso. O vigia transforma "nao rodou"
#                  em uma falha que alguem recebe, sem precisar abrir o hub.
#
#                  24/11/2026: confere tambem o que faria TODOS pararem juntos:
#                  disparos do pg_cron recusados pelo GitHub (token do Vault) e
#                  tokens dos secrets vencidos ou perto de vencer.
# =============================================
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import lib_dscs as dl


RESERVA = "--reserva" in sys.argv

# Tokens dos secrets que, vencidos, param robos. Nome da variavel -> quem usa.
TOKENS = {
    "GH_PAT": "robô 001 (commits no daily-log)",
    "FINANCAS_DISPATCH_TOKEN": "disparo do sync e do backup",
}
AVISAR_DIAS_ANTES = 15

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


def conferir_disparos() -> list[str]:
    """Disparos do pg_cron nas ultimas 24 h recusados pelo GitHub (401/403/404:
    token do Vault vencido, revogado ou sem permissao). Sem a funcao no banco,
    so avisa no log: o vigia continua valendo para o resto."""
    try:
        disparos = dl.supabase_rpc("disparos_github_recentes") or []
    except Exception as e:  # noqa: BLE001
        print(f"(nao consegui ler os disparos do pg_cron: {e})", file=sys.stderr)
        return []
    ruins = [d for d in disparos if not (d.get("status_http") and 200 <= d["status_http"] < 300)]
    if not ruins:
        return []
    codigos = sorted({str(d.get("status_http") or "sem resposta") for d in ruins})
    return [f"🔑 {len(ruins)} disparo(s) do pg_cron recusado(s) pelo GitHub (HTTP {', '.join(codigos)}): "
            "confira o token github_dispatch_token no Vault do DMP"]


def conferir_tokens() -> list[str]:
    """Tokens dos secrets: invalido ou vencendo em ate AVISAR_DIAS_ANTES dias.
    Token sem data de validade passa direto. Ausente (rodando no PC) e ignorado."""
    problemas = []
    env = dl.ler_env()
    for nome_var, uso in TOKENS.items():
        valor = env.get(nome_var)
        if not valor:
            continue
        try:
            info = dl.validade_token_github(valor)
        except Exception as e:  # noqa: BLE001 - GitHub fora do ar nao e problema do token
            print(f"(nao consegui conferir {nome_var}: {e})", file=sys.stderr)
            continue
        if not info["valido"]:
            problemas.append(f"🔑 Token {nome_var} recusado pelo GitHub (HTTP {info['status']}): {uso} vai parar")
        elif info["expira"]:
            dias = (info["expira"] - datetime.now(timezone.utc)).days
            if dias <= AVISAR_DIAS_ANTES:
                data = info["expira"].astimezone(TZ).strftime("%d/%m/%Y")
                problemas.append(f"🔑 Token {nome_var} vence em {max(dias, 0)} dia(s), {data}: {uso}")
        print(f"{nome_var:<24} HTTP {info['status']} | validade: {info['expira'] or 'sem vencimento'}")
    return problemas


ICONE_SAUDE = {"OK": "✅", "RODANDO": "🔄", "ERRO": "❌", "ATRASADO": "⏰", "TRAVADO": "🧊", "NUNCA_RODOU": "❔"}


def enviar_resumo_diario(robos: list[dict], problemas: list[str]) -> None:
    """Uma mensagem por dia em #resumo-diario: cada robo com a ultima execucao e
    a mensagem dela, mais o que precisa de atencao. Chega sem apitar."""
    linhas = []
    for r in robos:
        msg = re.sub(r"\s+", " ", (r.get("mensagem") or "").strip())
        msg = msg[:110] + "…" if len(msg) > 110 else msg
        linhas.append(f"{ICONE_SAUDE.get(r['saude'], '•')} **{nome(r)}** · {quando(r.get('dta_fim') or r.get('dta_ini'))}"
                      + (f"\n  {msg}" if msg else ""))
    if problemas:
        linhas += ["", "**Precisa de atenção:**", *problemas]
    titulo = f"📋 Resumo de {datetime.now(TZ).strftime('%d/%m')}: " + (
        f"{len(problemas)} ponto(s) de atenção" if problemas else f"{robos_txt(len(robos))} em dia")
    dl.notificar_discord("resumo", titulo, "\n".join(linhas), nivel="atencao" if problemas else "ok",
                         silencioso=True)


def main() -> int:
    # Uma notificacao por verificacao, para o hub mostrar que o vigia passou.
    # "resolvido" quando a anterior era de atencao e agora esta tudo em dia.
    try:
        anterior = dl.ultima_notificacao("vigia")
    except Exception as e:  # noqa: BLE001 - so muda o texto da notificacao
        print(f"(nao consegui ler a notificacao anterior: {e})", file=sys.stderr)
        anterior = None

    # --reserva: o schedule do GitHub. O vigia de verdade sai as 09:00 pelo
    # pg_cron do Supabase; se ele ja passou hoje, a reserva nao tem o que fazer.
    # Se nao passou, o disparo falhou - e isso vira um problema a mais.
    problemas = []
    if RESERVA:
        if anterior and datetime.fromisoformat(
            anterior["dta_add"].replace("Z", "+00:00")
        ).astimezone(TZ).date() == datetime.now(TZ).date():
            print("Reserva: o vigia ja passou hoje - nada a fazer.")
            return 0
        problemas.append(
            "🛰️ O vigia das 09:00 não rodou: o disparo pelo Supabase (pg_cron) "
            "pode ter falhado. Confira o token github_dispatch_token no Vault."
        )

    problemas += conferir_disparos()
    problemas += conferir_tokens()

    robos = dl.ler_saude_robos()
    if not robos and not problemas:
        print("Nenhum robo ativo em vw_saude_robos - nada a vigiar.")
        return 0

    for r in robos:
        horas = r.get("horas_desde") or "?"
        print(
            f"{r['nome_carga']:<24} {r['saude']:<12} "
            f"ha {horas} h | {r.get('ambiente') or '-'} | {r.get('mensagem') or ''}"
        )
        if r["saude"] not in dl.SAUDE_BOA:
            problemas.append(descrever_problema(r))

    enviar_resumo_diario(robos, problemas)

    # Detalhe das notificacoes: um robo por linha, com a ultima execucao.
    em_dia = "\n".join(
        f"• {nome(r)} · {quando(r.get('dta_fim') or r.get('dta_ini'))}"
        for r in robos if r["saude"] in dl.SAUDE_BOA
    )

    if problemas:
        n = len(problemas)
        titulo = f"⚠️ {n} {'ponto precisa' if n == 1 else 'pontos precisam'} de atenção"
        detalhe = "\n".join(problemas) + (f"\n\nEm dia:\n{em_dia}" if em_dia else "")
        dl.notificar_hub("atencao", titulo, detalhe)
        print(f"\nATENCAO: {'; '.join(problemas)}", file=sys.stderr)
        dl.notificar_discord("alertas", titulo, "\n".join(problemas), nivel="atencao")
        return 1

    if anterior and anterior.get("nivel") == "atencao":
        dl.notificar_hub("resolvido", f"✅ Voltou ao normal: {robos_txt(len(robos))} em dia", em_dia)
        dl.notificar_discord("alertas", f"✅ Voltou ao normal: {robos_txt(len(robos))} em dia", em_dia,
                             nivel="ok", silencioso=True)
    else:
        dl.notificar_hub("info", f"✅ Tudo certo: {robos_txt(len(robos))} em dia", em_dia)
    print(f"\nOK: {len(robos)} robo(s) em dia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
