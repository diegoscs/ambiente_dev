# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : DD/MM/AAAA
# DESCRICAO      : <o que o robo faz, em uma ou duas linhas>
#
# MODELO - copie a pasta _modelo para automacoes\NNN_nome_robo\ e troque
# NNN, nome_robo e o conteudo de processar(). Regras em automacoes\PADRAO_ROBOS.md.
# =============================================
from __future__ import annotations

import os
import sys
from pathlib import Path

# --- bootstrap padrao: encoding + caminho da lib (nesta ordem, antes dos imports)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from datetime import datetime, timezone

import lib_dscs as dl

# ─── configuracao ────────────────────────────────────────────────────────────
# DEBUG=True  -> nada e gravado em lugar nenhum; so o log.
# --dry-run   -> igual ao DEBUG, sem editar o arquivo.
# --status    -> mostra a configuracao e sai, sem executar a carga.
#
# --dry-run e --status nao registram status: nao sao a carga, e marcar
# SUCCESS neles mentiria no monitoramento.
DEBUG = False
DRY_RUN = "--dry-run" in sys.argv
STATUS = "--status" in sys.argv

IDCARGA = 999  # ★ mesmo numero da pasta e do id_carga em public.controle_cargas
NOME_ROBO = "nome_robo"

BASE = Path(__file__).resolve().parent

# Uma execucao por dia UTC? Deixe True e a trava le o historico no Supabase
# (funciona na nuvem, onde a maquina nasce vazia). False = roda sempre.
UMA_VEZ_POR_DIA = False

TENTATIVAS = 3
SEGUNDOS_ENTRE_TENTATIVAS = 30

# Trabalho que chegou de fato ao destino nesta execucao. Vai para o qtd_itens
# mesmo quando a execucao quebra no meio.
ITENS_FEITOS = 0


def validar_configuracao() -> None:
    """Tudo que pode estar faltando, conferido antes de qualquer rede.

    Segredo errado nao melhora com retry: a validacao fica fora do
    executar_com_retry, para nao repetir tres vezes o que ja nasceu quebrado.
    """
    faltando = [c for c in ("SUPABASE_URL", "SUPABASE_KEY") if not dl.ler_env().get(c)]
    # faltando += [c for c in ("MINHA_API_TOKEN",) if not dl.ler_env().get(c)]
    if faltando:
        raise ValueError(f"Faltam variaveis no ambiente/.env: {', '.join(faltando)}")


def processar() -> tuple[int, str]:
    """A carga. Devolve (qtd_itens, resumo) para o registro no Supabase."""
    global ITENS_FEITOS

    hoje = datetime.now(timezone.utc)
    if UMA_VEZ_POR_DIA and dl.trabalho_feito_no_dia(IDCARGA, hoje):
        return 0, f"dia {hoje:%Y-%m-%d} (UTC) ja processado - nada a fazer"

    # Etapas de rede sempre com retry; o resto estoura na primeira.
    dados = dl.executar_com_retry(
        "leitura da origem",
        lambda: [],  # troque pela chamada real
        TENTATIVAS,
        SEGUNDOS_ENTRE_TENTATIVAS,
    )

    for item in dados:
        if DEBUG or DRY_RUN:
            dl.log(f"[DRY RUN] processaria {item}")
            continue
        # ... grava o item no destino ...
        ITENS_FEITOS += 1

    return ITENS_FEITOS, f"{ITENS_FEITOS} item(ns) processado(s)"


def main() -> None:
    dl.configurar_logger(IDCARGA, NOME_ROBO, BASE)

    modo = dl.modo_execucao()
    dta_ini = datetime.now(timezone.utc)

    dl.logar_contexto(
        "DRY-RUN" if (DEBUG or DRY_RUN) else modo,
        extras={
            "Modo de execucao": modo,
            "Supabase": "configurado" if dl.supabase_configurado() else "AUSENTE",
            "DEBUG / DRY_RUN": f"{DEBUG} / {DRY_RUN}",
        },
    )

    registrar = not (DEBUG or DRY_RUN or STATUS)

    try:
        validar_configuracao()

        if registrar:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, dta_ini, fechar=False)

        qtd, resumo = (0, "status") if STATUS else processar()

        if registrar:
            dl.registrar_carga_supabase(
                IDCARGA, dl.STATUS_SUCESSO, dta_ini, fechar=True,
                mensagem=resumo, qtd_itens=qtd,
            )

        dl.log(f"[ROBO{IDCARGA:03d}] ✅ RESULTADO FINAL: SUCESSO - {resumo}")
        dl.log("=" * 70)

    except Exception as e:
        dl.log(f"[ROBO{IDCARGA:03d}] ❌ erro final: {e}")
        dl.logar_traceback("erro final")

        if registrar:
            # registrar_carga_supabase e alertar_erro_robo nunca levantam:
            # o erro original do robo continua sendo o que aparece.
            dl.registrar_carga_supabase(
                IDCARGA, dl.STATUS_ERRO, dta_ini, fechar=True,
                mensagem=str(e)[:500], qtd_itens=ITENS_FEITOS,
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
