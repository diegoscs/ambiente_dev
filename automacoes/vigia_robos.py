# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 26/09/2026
# DESCRICAO      : Vigia dos robos. Le a vw_saude_robos no Supabase e FALHA
#                  (exit 1) se algum robo estiver com ERRO, ATRASADO, TRAVADO
#                  ou NUNCA_RODOU. Roda no GitHub Actions: run vermelho = e-mail
#                  do GitHub, mais o aviso no Discord (#alertas). Todo dia
#                  manda tambem o resumo de todos os robos em #resumo-diario,
#                  de manha (09:00) e a tarde (16:00, depois do sync das 15:00),
#                  e repassa os avisos do sync do financas-app.
#
#                  25/11/2026: avisos do sync separados por peso. So vai ao
#                  #alertas o que pede acao (reconectar, falha, pendencia nova);
#                  o informativo e a pendencia repetida entram no resumo.
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


def enviar_resumo_diario(robos: list[dict], problemas: list[str], externos: list[str] | None = None) -> bool:
    """Uma mensagem por dia em #resumo-diario: cada robo com a ultima execucao e
    a mensagem dela, os avisos informativos dos robos de fora e o que precisa
    de atencao. Chega sem apitar. Devolve True se chegou."""
    linhas = []
    for r in robos:
        msg = re.sub(r"\s+", " ", (r.get("mensagem") or "").strip())
        msg = msg[:110] + "…" if len(msg) > 110 else msg
        linhas.append(f"{ICONE_SAUDE.get(r['saude'], '•')} **{nome(r)}** · {quando(r.get('dta_fim') or r.get('dta_ini'))}"
                      + (f"\n  {msg}" if msg else ""))
    if externos:
        linhas += ["", "**Open Finance:**", *externos]
    if problemas:
        linhas += ["", "**Precisa de atenção:**", *problemas]
    titulo = f"📋 Resumo da {turno()} de {datetime.now(TZ).strftime('%d/%m')}: " + (
        f"{len(problemas)} ponto(s) de atenção" if problemas else f"{robos_txt(len(robos))} em dia")
    return dl.notificar_discord("resumo", titulo, "\n".join(linhas), nivel="atencao" if problemas else "ok",
                                silencioso=True)


REPO = "diegoscs/ambiente_dev"
ORIGENS_PROPRIAS = ("vigia", "saude_dmc")  # avisos que ja vao direto ao Discord


def turno() -> str:
    """manha (vigia das 09:00) ou tarde (vigia das 16:00, depois do sync das 15:00)."""
    return "manhã" if datetime.now(TZ).hour < 13 else "tarde"


def execucoes_do_vigia() -> list[dict] | None:
    """Ultimas execucoes deste workflow no GitHub (o historico do proprio vigia).
    Precisa do GH_TOKEN do Actions; fora dele (no PC) devolve None."""
    token = dl.ler_env().get("GH_TOKEN")
    if not token:
        return None
    try:
        status, dados = dl.chamar_api_json(
            f"https://api.github.com/repos/{REPO}/actions/workflows/vigia_robos.yml/runs?per_page=10",
            token=token, cabecalhos={"Accept": "application/vnd.github+json", "User-Agent": "vigia_robos"})
    except Exception as e:  # noqa: BLE001
        print(f"(nao consegui ler as execucoes do vigia: {e})", file=sys.stderr)
        return None
    if status != 200:
        print(f"(execucoes do vigia: HTTP {status})", file=sys.stderr)
        return None
    atual = os.environ.get("GITHUB_RUN_ID")
    return [r for r in dados.get("workflow_runs", []) if str(r.get("id")) != atual]


# Avisos de fora que pedem acao na hora: vao ao #alertas sempre (o anti-spam de
# 24 h do notificar_hub_externo ja segura a repeticao no mesmo dia).
URGENTES = ("🔌", "❌", "Open Finance: o sync não rodou")


def _linha_aviso(n: dict, prefixo: str = "") -> str:
    detalhe = (n.get("detalhe") or "").strip()
    return f"• {prefixo}**{n['titulo']}**" + (f"\n  {detalhe[:300]}" if detalhe else "")


def separar_avisos_externos(pendentes: list[dict], ja_enviados: list[dict]) -> tuple[list[dict], list[dict]]:
    """Divide os avisos pendentes dos robos de fora em (alertas, resumo).

    - urgente (reconectar, falha, sync parado): #alertas
    - outro 'atencao' (ex.: lancamentos para conferir): #alertas so quando o
      texto muda em relacao ao ultimo ja enviado; igual = resumo, marcado como
      ainda pendente
    - 'info' (movimentacoes novas, data mudada): resumo
    """
    ultimo: dict[tuple, str | None] = {}
    for n in ja_enviados:  # mais novo primeiro: fica o ultimo enviado de cada aviso
        ultimo.setdefault((n["origem"], n["titulo"]), n.get("detalhe"))

    alertas, resumo = [], []
    for n in pendentes:  # mais antigo primeiro
        chave = (n["origem"], n["titulo"])
        if n.get("nivel") != "atencao":
            resumo.append(n)
        elif n["titulo"].startswith(URGENTES):
            alertas.append(n)
        elif chave in ultimo and ultimo[chave] == n.get("detalhe"):
            resumo.append({**n, "repetido": True})
        else:
            alertas.append(n)
        if n.get("nivel") == "atencao":
            ultimo[chave] = n.get("detalhe")  # dois iguais no mesmo lote = um alerta so
    return alertas, resumo


def repassar_avisos_externos() -> tuple[list[str], list[int]]:
    """Avisos que robos de fora (o sync do financas-app, via notificar_hub_externo)
    deixam em notificacoes_hub. O que pede acao vai agora ao #alertas (e e
    marcado como lido); o resto volta como linhas para o resumo, com os ids a
    marcar depois que o resumo chegar."""
    try:
        pendentes = dl.supabase_ler(
            "notificacoes_hub?select=id,origem,nivel,titulo,detalhe&lida=is.false&order=dta_add")
        ja_enviados = dl.supabase_ler(
            "notificacoes_hub?select=origem,titulo,detalhe&lida=is.true&nivel=eq.atencao"
            "&order=dta_add.desc&limit=200")
    except Exception as e:  # noqa: BLE001
        print(f"(nao consegui ler os avisos pendentes: {e})", file=sys.stderr)
        return [], []
    pendentes = [n for n in pendentes if n.get("origem") not in ORIGENS_PROPRIAS]
    ja_enviados = [n for n in ja_enviados if n.get("origem") not in ORIGENS_PROPRIAS]
    if not pendentes:
        return [], []

    alertas, resumo = separar_avisos_externos(pendentes, ja_enviados)

    if alertas:
        titulo = alertas[0]["titulo"] if len(alertas) == 1 else f"📨 {len(alertas)} avisos do Open Finance"
        texto = (alertas[0].get("detalhe") or "") if len(alertas) == 1 else "\n".join(_linha_aviso(n) for n in alertas)
        if dl.notificar_discord("alertas", titulo, texto, nivel="atencao"):
            dl.supabase_atualizar("notificacoes_hub", f"id=in.({','.join(str(n['id']) for n in alertas)})",
                                  {"lida": True})
            print(f"{len(alertas)} aviso(s) de robos de fora enviado(s) ao #alertas.")

    linhas = [_linha_aviso(n, "ainda pendente: " if n.get("repetido") else "") for n in resumo]
    return linhas, [n["id"] for n in resumo]


def main() -> int:
    execucoes = execucoes_do_vigia()

    # --reserva: o schedule do GitHub (meio-dia). O vigia de verdade sai as
    # 09:00 pelo pg_cron; se alguma execucao dele ja deu certo hoje, a reserva
    # nao tem o que fazer. Se nao, o disparo falhou - e isso vira um problema.
    problemas = []
    if RESERVA:
        hoje = datetime.now(TZ).date()
        rodou_hoje = execucoes is not None and any(
            r.get("event") == "workflow_dispatch" and r.get("conclusion") in ("success", "failure")
            and datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).astimezone(TZ).date() == hoje
            for r in execucoes)
        if rodou_hoje:
            print("Reserva: o vigia ja passou hoje - nada a fazer.")
            return 0
        problemas.append(
            "🛰️ O vigia das 09:00 não rodou: o disparo pelo Supabase (pg_cron) "
            "pode ter falhado. Confira o token github_dispatch_token no Vault."
        )

    problemas += conferir_disparos()
    problemas += conferir_tokens()
    externos, ids_externos = repassar_avisos_externos()

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

    if enviar_resumo_diario(robos, problemas, externos) and ids_externos:
        dl.supabase_atualizar("notificacoes_hub", f"id=in.({','.join(map(str, ids_externos))})", {"lida": True})

    if problemas:
        n = len(problemas)
        titulo = f"⚠️ {n} {'ponto precisa' if n == 1 else 'pontos precisam'} de atenção"
        print(f"\nATENCAO: {'; '.join(problemas)}", file=sys.stderr)
        dl.notificar_discord("alertas", titulo, "\n".join(problemas), nivel="atencao")
        return 1

    # "Voltou ao normal": a execucao anterior do vigia tinha falhado (achou problema).
    anterior = next((r for r in (execucoes or []) if r.get("status") == "completed"), None)
    if anterior and anterior.get("conclusion") == "failure":
        em_dia = "\n".join(f"• {nome(r)} · {quando(r.get('dta_fim') or r.get('dta_ini'))}" for r in robos)
        dl.notificar_discord("alertas", f"✅ Voltou ao normal: {robos_txt(len(robos))} em dia", em_dia,
                             nivel="ok", silencioso=True)
    print(f"\nOK: {len(robos)} robo(s) em dia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
