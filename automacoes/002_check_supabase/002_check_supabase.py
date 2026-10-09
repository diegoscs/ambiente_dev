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
# MODO_EXECUCAO (env):
#   LOCAL -> Agendador do Windows: dbo.controle_cargas (Postgres dm) + Supabase.
#   CLOUD -> GitHub Actions: sem Postgres local, so o Supabase.
# Nos dois o registro oficial e o Supabase (controle_cargas + historico_cargas).
DEBUG = False
DRY_RUN = "--dry-run" in sys.argv
STATUS = "--status" in sys.argv

BASE = Path(__file__).resolve().parent


def mostrar_status(modo: str) -> None:
    """Manutencao: o que o robo enxerga, sem tocar em nada."""
    dl.log(f"[STATUS] modo         : {modo}")
    dl.log(f"[STATUS] supabase     : {url_supabase()}")
    dl.log(f"[STATUS] telegram     : {'configurado' if dl.telegram_configurado() else 'AUSENTE'}")

    if modo == dl.MODO_LOCAL:
        carga = dl.obter_carga(IDCARGA)
        if carga is None:
            dl.log(f"[STATUS] ⚠ id_carga {IDCARGA} nao cadastrado - rode o cadastro_carga.sql")
            return
        dl.log(f"[STATUS] ultima exec : {carga['status']} em {carga['dta_fim']} (tabela local)")


def main() -> None:
    dl.configurar_logger(IDCARGA, NOME_ROBO, BASE)

    modo = dl.modo_execucao()
    dta_ini = datetime.now(timezone.utc)

    dl.logar_contexto(
        "DRY-RUN" if (DEBUG or DRY_RUN) else modo,
        extras={
            "Arquivo .env": str(dl.ENV_FILE),
            "Modo de execucao": modo,
            "Destino Supabase": dl.ler_env().get("SUPABASE_URL") or "(nao definido)",
            "Banco de controle": (
                f"{dl.descrever_conexao()} | {dl.TABELA_CONTROLE} + Supabase (id_carga {IDCARGA})"
                if modo == dl.MODO_LOCAL
                else f"Supabase public.{dl.TABELA_CONTROLE_SUPABASE} (id_carga {IDCARGA})"
            ),
            "DEBUG / DRY_RUN": f"{DEBUG} / {DRY_RUN}",
        },
    )

    # --status e manutencao, nao a carga: marcar SUCCESS nele mentiria no
    # monitoramento. Mesma regra do robo 001.
    registrar_controle = not (DEBUG or DRY_RUN or STATUS)
    registrar_local = registrar_controle and modo == dl.MODO_LOCAL

    try:
        validar_configuracao(modo)

        if registrar_local:
            dl.status_inicio(IDCARGA)
            dl.log(f"[CONTROLE] id_carga {IDCARGA} marcado como '{dl.STATUS_INICIO}'")
        if registrar_controle:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, dta_ini, fechar=False)

        resultados = []
        if STATUS:
            mostrar_status(modo)
        else:
            resultados = executar_pings()

        if registrar_local:
            dl.status_sucesso(IDCARGA)
            dl.log(f"[CONTROLE] id_carga {IDCARGA} marcado como '{dl.STATUS_SUCESSO}'")
        if registrar_controle:
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

        if registrar_local:
            # O status_erro nao pode derrubar o traceback original: se o banco
            # tambem estiver fora, o log tem que continuar mostrando o erro real.
            try:
                dl.status_erro(IDCARGA)
                dl.log(f"[CONTROLE] id_carga {IDCARGA} marcado como '{dl.STATUS_ERRO}'")
            except Exception as erro_controle:  # noqa: BLE001
                dl.log(f"[CONTROLE] ⚠ falha ao registrar o erro na tabela: {erro_controle}")
        if registrar_controle:
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
