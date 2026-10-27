# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 05/09/2026
# DESCRICAO      : Log padrao dos robos. As linhas ficam em memoria durante a
#                  execucao e so viram arquivo se a execucao falhar - dia normal
#                  nao deixa rastro em disco.
# =============================================
from __future__ import annotations

import getpass
import logging
import socket
import sys
import traceback
from datetime import datetime
from pathlib import Path

_logger = logging.getLogger("dscs")

# Estado do log corrente, preenchido pelo configurar_logger.
_buffer: list[str] = []
_id_carga: int = 0
_nome_robo: str = "robo"
_temp: Path | None = None

FORMATO = "%(asctime)s | %(levelname)-7s | %(message)s"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"


class _HandlerMemoria(logging.Handler):
    """Acumula as linhas formatadas em vez de escrever em disco."""

    def emit(self, record: logging.LogRecord) -> None:
        _buffer.append(self.format(record))


def configurar_logger(
    id_carga: int,
    nome_robo: str,
    base_dir: Path,
    console: bool = True,
) -> None:
    """Prepara o log do robo.

    Nada e gravado em disco aqui: as linhas vao para memoria e so descem para
    `temp\\` se o robo chamar salvar_log_erro(). O console continua ligado: e o
    log do run no Actions e a tela de quem roda na mao.
    """
    global _id_carga, _nome_robo, _temp

    _id_carga = id_carga
    _nome_robo = nome_robo
    _temp = Path(base_dir) / "temp"
    _buffer.clear()

    formato = logging.Formatter(fmt=FORMATO, datefmt=FORMATO_DATA)

    _logger.setLevel(logging.DEBUG)
    _logger.handlers.clear()

    handler_memoria = _HandlerMemoria()
    handler_memoria.setFormatter(formato)
    _logger.addHandler(handler_memoria)

    if console:
        handler_console = logging.StreamHandler(sys.stdout)
        handler_console.setFormatter(formato)
        _logger.addHandler(handler_console)


def log(msg: str = "") -> None:
    _logger.info(msg)


def log_erro(msg: str) -> None:
    _logger.error(msg)


def logar_contexto(modo: str, extras: dict[str, str] | None = None) -> None:
    """Cabecalho padrao: quem, onde e com que configuracao o robo esta rodando.

    `extras` recebe o que e especifico do robo (repositorio, tabela destino,
    endpoint SFTP...), na mesma coluna alinhada do resto.
    """
    log("=" * 70)
    log(f"[ROBO{_id_carga:03d}] INICIO — {modo} | {datetime.now():%d/%m/%Y %H:%M:%S}")
    log("-" * 70)

    try:
        usuario = getpass.getuser()
    except Exception as e:  # noqa: BLE001 - so contexto de log
        usuario = f"<nao identificado> ({e})"

    padrao = {
        "Usuario do processo": usuario,
        "Maquina (host)": socket.gethostname(),
        "Python": sys.version.split()[0],
        "Executavel Python": sys.executable,
        "Diretorio do script": str(_temp.parent) if _temp else "<nao configurado>",
    }

    for rotulo, valor in {**padrao, **(extras or {})}.items():
        log(f"{rotulo:<20}: {valor}")

    log("=" * 70)


def logar_traceback(contexto: str) -> None:
    """Traceback completo no log, sem derrubar a execucao."""
    log_erro(f"Traceback de '{contexto}':\n" + traceback.format_exc())


def salvar_log_erro() -> Path | None:
    """Descarrega o buffer em temp\\erro_<id>_<nome>_<AAAAMMDD_HHMMSS>.txt.

    Um arquivo por falha, com carimbo de hora no nome: duas falhas no mesmo dia
    nao se sobrescrevem. Chamado so no except do robo - execucao que termina bem
    nao gera arquivo nenhum.
    """
    if _temp is None or not _buffer:
        return None

    _temp.mkdir(parents=True, exist_ok=True)
    destino = _temp / f"erro_{_id_carga:03d}_{_nome_robo}_{datetime.now():%Y%m%d_%H%M%S}.txt"
    destino.write_text("\n".join(_buffer) + "\n", encoding="utf-8")

    return destino


def linhas_do_log() -> list[str]:
    """Copia do que foi logado ate agora. Util em teste."""
    return list(_buffer)
