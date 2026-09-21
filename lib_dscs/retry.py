# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 05/09/2026
# DESCRICAO      : Retry das etapas instaveis (rede, SFTP, API).
# =============================================
from __future__ import annotations

import time
from typing import Any, Callable

from .log import log, logar_traceback

TENTATIVAS_PADRAO = 3
SEGUNDOS_ENTRE_TENTATIVAS = 30


def executar_com_retry(
    nome_etapa: str,
    funcao: Callable[[], Any],
    tentativas: int = TENTATIVAS_PADRAO,
    espera: int = SEGUNDOS_ENTRE_TENTATIVAS,
) -> Any:
    """Repete a etapa enquanto ela falhar, logando cada tentativa.

    Use so onde a falha e transitoria: rede, SFTP, API fora do ar. Erro de
    permissao, credencial ou layout nao melhora com insistencia - ali o certo e
    estourar na primeira.

    O traceback de cada tentativa vai para o log; a excecao final vira
    RuntimeError com o ultimo erro na mensagem.
    """
    ultimo_erro: Exception | None = None

    for tentativa in range(1, tentativas + 1):
        try:
            log(f"[{nome_etapa}] tentativa {tentativa}/{tentativas}")
            return funcao()

        except Exception as e:  # noqa: BLE001 - reerguido abaixo
            ultimo_erro = e
            log(f"[{nome_etapa}] falhou: {e}")
            logar_traceback(f"{nome_etapa} (tentativa {tentativa}/{tentativas})")

            if tentativa < tentativas:
                log(f"[{nome_etapa}] aguardando {espera}s para tentar de novo...")
                time.sleep(espera)

    raise RuntimeError(
        f"Etapa '{nome_etapa}' falhou apos {tentativas} tentativa(s). "
        f"Ultimo erro: {ultimo_erro}"
    )
