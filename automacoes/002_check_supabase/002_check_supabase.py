# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 15/09/2026
# DESCRICAO      : Keepalive do projeto Supabase (plano free). Executa uma
#                  consulta real por dois caminhos - conexao Postgres e REST -
#                  para o projeto nao ser pausado por inatividade.
# =============================================
from __future__ import annotations

import os
import sys
from pathlib import Path

# --- bootstrap padrao: encoding + caminho da lib (nesta ordem, antes dos imports)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))  # modulos do proprio robo
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from datetime import datetime, timezone

import lib_dscs as dl

from config_robo import (
    IDCARGA,
    NOME_ROBO,
    url_supabase,
    validar_configuracao,
)
from ping import executar_pings

# ─── configuracao ────────────────────────────────────────────────────────────
# DEBUG=True  -> nada e gravado em lugar nenhum; so o ping e o log.
# --dry-run   -> igual ao DEBUG, sem editar o arquivo.
# --status    -> mostra a configuracao e sai, sem pingar nada.
#
# Roda no GitHub Actions (MODO_EXECUCAO=CLOUD). O registro e o Supabase
# (controle_cargas + historico_cargas).
DEBUG = False
DRY_RUN = "--dry-run" in sys.argv
STATUS = "--status" in sys.argv

BASE = Path(__file__).resolve().parent


def mostrar_status(modo: str) -> None:
    """Manutencao: o que o robo enxerga, sem tocar em nada."""
    dl.log(f"[STATUS] modo         : {modo}")
    dl.log(f"[STATUS] supabase     : {url_supabase()}")
    dl.log(f"[STATUS] telegram     : {'configurado' if dl.telegram_configurado() else 'AUSENTE'}")


def main() -> None:
    dl.configurar_logger(IDCARGA, NOME_ROBO, BASE)

    modo = dl.modo_execucao()
    dta_ini = datetime.now(timezone.utc)

    dl.logar_contexto(
        "DRY-RUN" if (DEBUG or DRY_RUN) else modo,
        extras={
            "Modo de execucao": modo,
            "Destino Supabase": dl.ler_env().get("SUPABASE_URL") or "(nao definido)",
            "Controle de cargas": f"Supabase public.{dl.TABELA_CONTROLE_SUPABASE} (id_carga {IDCARGA})",
            "DEBUG / DRY_RUN": f"{DEBUG} / {DRY_RUN}",
        },
    )

    # --status e manutencao, nao a carga: marcar SUCCESS nele mentiria no
    # monitoramento. Mesma regra do robo 001.
    registrar = not (DEBUG or DRY_RUN or STATUS)

    try:
        validar_configuracao(modo)

        if registrar:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, dta_ini, fechar=False)

        resultados = []
        if STATUS:
            mostrar_status(modo)
        else:
            resultados = executar_pings()

        if registrar:
            # Mensagem do hub: curta e legivel ("banco 1,1 s · API 0,2 s")
            nomes = {"postgres": "banco", "rest": "API"}
            tempos = " · ".join(
                f"{nomes.get(r['metodo'], r['metodo'])} {float(r['latencia_ms']) / 1000:.1f} s".replace(".", ",")
                for r in resultados
            )
            dl.registrar_carga_supabase(
                IDCARGA, dl.STATUS_SUCESSO, dta_ini, fechar=True,
                mensagem=f"Ok, tudo certo: Supabase ativo ✅ · {tempos}", qtd_itens=len(resultados),
            )

        dl.log(f"[ROBO{IDCARGA:03d}] ✅ RESULTADO FINAL: SUCESSO")
        dl.log("=" * 70)

    except Exception as e:
        dl.log(f"[ROBO{IDCARGA:03d}] ❌ erro final: {e}")
        dl.logar_traceback("erro final")

        if registrar:
            # Com o Supabase fora do ar este registro tambem falha - e so vira
            # log. Quem pega esse caso e o ATRASADO da vw_saude_robos.
            dl.registrar_carga_supabase(
                IDCARGA, dl.STATUS_ERRO, dta_ini, fechar=True,
                mensagem=f"⚠️ {e}"[:500], qtd_itens=0,
            )
            dl.alertar_erro_robo(IDCARGA, NOME_ROBO, str(e))

        dl.log(f"[ROBO{IDCARGA:03d}] ❌ RESULTADO FINAL: ERRO")
        dl.log("=" * 70)

        # So aqui o log vira arquivo. Execucao que termina bem nao deixa rastro.
        arquivo = dl.salvar_log_erro()
        if arquivo:
            print(f"Log do erro: {arquivo}", file=sys.stderr)

        raise


if __name__ == "__main__":
    main()
