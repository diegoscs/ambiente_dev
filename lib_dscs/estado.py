# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 05/09/2026
# DESCRICAO      : Estado local do robo, em temp\estado.json. Serve de trava
#                  para o Agendador nao repetir a carga no mesmo dia.
# =============================================
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .log import log

ARQUIVO = "estado.json"


def caminho_estado(base_dir: Path) -> Path:
    return Path(base_dir) / "temp" / ARQUIVO


def ler_estado(base_dir: Path) -> dict[str, Any]:
    """Estado da ultima execucao. Arquivo ausente ou corrompido vira {}.

    Corrompido nao derruba o robo de proposito: o pior caso e perder a trava e
    rodar de novo, o que e melhor do que a carga parar por causa do arquivo de
    controle local.
    """
    arquivo = caminho_estado(base_dir)

    if not arquivo.exists():
        return {}

    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log(f"[ESTADO] ⚠ nao consegui ler {arquivo.name} ({e}) — tratando como vazio")
        return {}


def gravar_estado(base_dir: Path, dados: dict[str, Any]) -> None:
    """Grava o estado, criando temp\\ se precisar."""
    arquivo = caminho_estado(base_dir)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")


def ja_executou_hoje(base_dir: Path, hoje: datetime | None = None) -> bool:
    """True se ja houve execucao registrada na data de hoje.

    O Agendador pode disparar mais de uma vez no mesmo dia (retry da tarefa,
    maquina que ligou tarde, execucao manual). Sem essa trava, a carga dobra.
    """
    dia = f"{hoje or datetime.now():%Y-%m-%d}"
    return ler_estado(base_dir).get("ultima_execucao") == dia


def marcar_execucao(base_dir: Path, hoje: datetime | None = None, **campos: Any) -> None:
    """Registra a execucao do dia, junto dos campos que o robo quiser guardar.

        dl.marcar_execucao(BASE, commits=3, motivo="dia de commit")
    """
    dados = ler_estado(base_dir)
    dados["ultima_execucao"] = f"{hoje or datetime.now():%Y-%m-%d}"
    dados.update(campos)
    gravar_estado(base_dir, dados)
