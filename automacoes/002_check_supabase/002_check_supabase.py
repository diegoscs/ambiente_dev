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

import sync_supabase as sync
from config_robo import (
    IDCARGA,
    MODO_CLOUD,
    MODO_LOCAL,
    NOME_ROBO,
    modo_execucao,
    url_supabase,
    validar_configuracao,
)
from ping import executar_pings

# ─── configuracao ────────────────────────────────────────────────────────────
# DEBUG=True  -> nada e gravado em lugar nenhum; so o ping e o log.
# --dry-run   -> igual ao DEBUG, sem editar o arquivo.
# --status    -> mostra a configuracao e sai, sem pingar nada.
DEBUG = False
DRY_RUN = "--dry-run" in sys.argv
STATUS = "--status" in sys.argv

BASE = Path(__file__).resolve().parent


def mostrar_status() -> None:
    """Manutencao: o que o robo enxerga, sem tocar em nada."""
    dl.log(f"[STATUS] modo         : {modo_execucao()}")
    dl.log(f"[STATUS] supabase     : {url_supabase()}")
    dl.log(f"[STATUS] telegram     : {'configurado' if dl.telegram_configurado() else 'AUSENTE'}")

    if modo_execucao() == MODO_LOCAL:
        carga = dl.obter_carga(IDCARGA)
        if carga is None:
            dl.log(f"[STATUS] ⚠ id_carga {IDCARGA} nao cadastrado - rode o cadastro_carga.sql")
            return
        dl.log(f"[STATUS] ultima exec : {carga['status']} em {carga['dta_fim']}")
        dl.log(
            f"[STATUS] espelho     : "
            f"{'sincronizado' if carga.get('flg_sincronizado') else 'PENDENTE'} "
            f"(dta_sync={carga.get('dta_sync')})"
        )


def processar_local() -> None:
    """Fluxo do Agendador: controle local + ping + espelho."""
    # Pendencias primeiro: o que ficou para tras vai junto mesmo que o ping de
    # hoje falhe depois.
    sync.sincronizar_pendencias()

    executar_pings()


def processar_cloud(dta_ini: datetime, registrar: bool) -> None:
    """Fluxo do GitHub Actions: sem Postgres local, registro direto no Supabase."""
    if registrar:
        sync.registrar_carga_cloud(dl.STATUS_INICIO, dta_ini, fechar=False)
    executar_pings()


def main() -> None:
    dl.configurar_logger(IDCARGA, NOME_ROBO, BASE)

    modo = modo_execucao()
    dta_ini = datetime.now(timezone.utc)

    dl.logar_contexto(
        "DRY-RUN" if (DEBUG or DRY_RUN) else modo,
        extras={
            "Arquivo .env": str(dl.ENV_FILE),
            "Modo de execucao": modo,
            "Destino Supabase": dl.ler_env().get("SUPABASE_URL") or "(nao definido)",
            "Banco de controle": (
                f"{dl.descrever_conexao()} | {dl.TABELA_CONTROLE} (id_carga {IDCARGA})"
                if modo == MODO_LOCAL
                else "nenhum - carga gravada direto no Supabase"
            ),
            "DEBUG / DRY_RUN": f"{DEBUG} / {DRY_RUN}",
        },
    )

    # --status e manutencao, nao a carga: marcar SUCCESS nele mentiria no
    # monitoramento. Mesma regra do robo 001.
    registrar_controle = not (DEBUG or DRY_RUN or STATUS)
    registrar_local = registrar_controle and modo == MODO_LOCAL

    try:
        validar_configuracao(modo)

        if registrar_local:
            dl.status_inicio(IDCARGA)
            dl.log(f"[CONTROLE] id_carga {IDCARGA} marcado como '{dl.STATUS_INICIO}'")

        if STATUS:
            mostrar_status()
        elif modo == MODO_CLOUD:
            processar_cloud(dta_ini, registrar_controle)
        else:
            processar_local()

        if registrar_local:
            dl.status_sucesso(IDCARGA)
            dl.log(f"[CONTROLE] id_carga {IDCARGA} marcado como '{dl.STATUS_SUCESSO}'")
            # Espelho por ultimo, com a linha ja fechada: falhar aqui nao muda o
            # resultado da carga, so adia a copia para a proxima execucao.
            sync.sincronizar_carga(IDCARGA)
        elif registrar_controle and modo == MODO_CLOUD:
            sync.registrar_carga_cloud(dl.STATUS_SUCESSO, dta_ini, fechar=True)

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
                sync.sincronizar_carga(IDCARGA)
            except Exception as erro_controle:  # noqa: BLE001
                dl.log(f"[CONTROLE] ⚠ falha ao registrar o erro na tabela: {erro_controle}")
        elif registrar_controle and modo == MODO_CLOUD:
            sync.registrar_carga_cloud(dl.STATUS_ERRO, dta_ini, fechar=True)

        if registrar_controle:
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
