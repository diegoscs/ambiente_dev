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
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import lib_dscs as dl


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
            problemas.append(f"{r['nome_carga']}: {r['saude']} (ultima execucao ha {horas} h)")

    # Uma notificacao por verificacao, para o hub mostrar que o vigia passou.
    # "resolvido" quando a anterior era de atencao e agora esta tudo em dia.
    try:
        anterior = dl.ultima_notificacao("vigia")
    except Exception as e:  # noqa: BLE001 - so muda o texto da notificacao
        print(f"(nao consegui ler a notificacao anterior: {e})", file=sys.stderr)
        anterior = None

    if problemas:
        titulo = f"{len(problemas)} robo(s) precisam de atencao"
        dl.notificar_hub("atencao", titulo, "\n".join(problemas))
        print(f"\nATENCAO: {'; '.join(problemas)}", file=sys.stderr)
        dl.alertar_telegram("⚠️ Vigia dos robos\n" + "\n".join(problemas))
        return 1

    if anterior and anterior.get("nivel") == "atencao":
        dl.notificar_hub("resolvido", f"Voltou ao normal: {len(robos)} robo(s) em dia")
    else:
        dl.notificar_hub("info", f"Verificacao ok: {len(robos)} robo(s) em dia")
    print(f"\nOK: {len(robos)} robo(s) em dia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
