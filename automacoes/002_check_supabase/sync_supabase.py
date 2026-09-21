# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 15/09/2026
# DESCRICAO      : Espelho de dbo.controle_cargas no Supabase (PostgREST).
#                  A tabela local e a fonte da verdade; aqui e copia.
# =============================================
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import lib_dscs as dl
from config_robo import (
    IDCARGA,
    NOME_CARGA,
    TABELA_SUPABASE,
    TIMEOUT_SEGUNDOS,
    cabecalhos_rest,
    url_supabase,
)

# Colunas espelhadas. flg_sincronizado e dta_sync ficam de fora de proposito:
# sao o controle DA copia, e so fazem sentido do lado de ca.
COLUNAS_ESPELHO = (
    "id_carga",
    "nome_carga",
    "descricao",
    "status",
    "dta_ini",
    "dta_fim",
    "tempo_min",
    "dias_semana",
    "flg_ativo",
    "origem",
    "script",
    "dta_add",
    "dta_modif",
)


def _serializar(valor: Any) -> Any:
    """datetime -> ISO 8601 em UTC. O resto passa direto."""
    if isinstance(valor, datetime):
        return valor.astimezone(timezone.utc).isoformat()
    return valor


def _agora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── escrita no Supabase ─────────────────────────────────────────────────────


def upsert_carga(linha: dict[str, Any]) -> None:
    """Upsert pela chave id_carga. Levanta se o PostgREST recusar.

    resolution=merge-duplicates e o ON CONFLICT DO UPDATE do PostgREST - sem
    ele, id_carga repetido volta 409 toda vez que o robo roda de novo.
    """
    corpo = {c: _serializar(linha.get(c)) for c in COLUNAS_ESPELHO if c in linha}

    status, payload = dl.chamar_api_json(
        f"{url_supabase()}/rest/v1/{TABELA_SUPABASE}?on_conflict=id_carga",
        "POST",
        corpo=corpo,
        cabecalhos=cabecalhos_rest(
            {"Prefer": "resolution=merge-duplicates,return=minimal"}
        ),
        timeout=TIMEOUT_SEGUNDOS,
    )

    if status not in (200, 201, 204):
        raise RuntimeError(
            f"upsert HTTP {status}: "
            f"{payload.get('message') or payload.get('hint') or payload}"
        )


# ─── controle local da copia ─────────────────────────────────────────────────


def _marcar(id_carga: int, sincronizada: bool) -> None:
    """Atualiza so as colunas de sync. Nao mexe em dta_modif: modificar a linha
    aqui faria o espelho parecer desatualizado logo apos ter sido atualizado."""
    dl.executar_comando(
        f"UPDATE {dl.TABELA_CONTROLE} "
        f"   SET flg_sincronizado = %s, dta_sync = {'now()' if sincronizada else 'dta_sync'} "
        f" WHERE id_carga = %s",
        (sincronizada, id_carga),
    )


def sincronizar_carga(id_carga: int = IDCARGA) -> bool:
    """Espelha a linha da carga no Supabase. NUNCA levanta.

    Falha de sync nao pode derrubar o robo: a carga local ja fechou com o status
    certo, e a tabela local e a fonte da verdade. A linha fica marcada como nao
    sincronizada e a proxima execucao reenvia.
    """
    try:
        linha = dl.obter_carga(id_carga)
        if linha is None:
            dl.log(f"[SYNC] id_carga {id_carga} nao existe na tabela local - nada a espelhar")
            return False

        upsert_carga(linha)
        _marcar(id_carga, True)
        dl.log(f"[SYNC] ✅ id_carga {id_carga} espelhado no Supabase")
        return True

    except Exception as e:  # noqa: BLE001 - sync nunca derruba o robo
        dl.log(f"[SYNC] ⚠ falha ao espelhar id_carga {id_carga}: {e}")
        dl.logar_traceback(f"sync do id_carga {id_carga}")
        try:
            _marcar(id_carga, False)
            dl.log(f"[SYNC] id_carga {id_carga} marcado como pendente para a proxima execucao")
        except Exception as erro_marca:  # noqa: BLE001
            dl.log(f"[SYNC] ⚠ nem a marcacao de pendencia funcionou: {erro_marca}")
        return False


def sincronizar_pendencias() -> int:
    """Reenvia o que ficou para tras em execucoes anteriores. NUNCA levanta.

    Roda no inicio, antes do ping: se a rede estiver ruim hoje tambem, a falha
    aparece cedo no log e as pendencias continuam pendentes - sem prejuizo, a
    proxima execucao tenta de novo.
    """
    try:
        pendentes = dl.executar_query_dict(
            f"SELECT id_carga FROM {dl.TABELA_CONTROLE} "
            f" WHERE flg_sincronizado IS FALSE ORDER BY id_carga"
        )
    except Exception as e:  # noqa: BLE001
        dl.log(f"[SYNC] ⚠ nao consegui listar pendencias: {e}")
        return 0

    if not pendentes:
        dl.log("[SYNC] nenhuma pendencia de espelhamento")
        return 0

    dl.log(f"[SYNC] {len(pendentes)} carga(s) pendente(s) de espelhamento")
    enviadas = sum(1 for p in pendentes if sincronizar_carga(p["id_carga"]))
    dl.log(f"[SYNC] pendencias reenviadas: {enviadas}/{len(pendentes)}")
    return enviadas


# ─── modo CLOUD ──────────────────────────────────────────────────────────────


def registrar_carga_cloud(status: str, dta_ini: datetime, fechar: bool) -> None:
    """Grava a carga direto no Supabase. NUNCA levanta.

    No Actions nao existe Postgres local, entao o Supabase deixa de ser copia e
    passa a ser o unico registro. Mesmo assim o registro nao pode derrubar o
    robo: o objetivo do modo CLOUD e o ping, e ele ja aconteceu.
    """
    linha = {
        "id_carga": IDCARGA,
        "nome_carga": NOME_CARGA,
        "descricao": "Keepalive do projeto Supabase (execucao CLOUD / GitHub Actions)",
        "status": status,
        "dta_ini": dta_ini,
        "dta_fim": datetime.now(timezone.utc) if fechar else None,
        "tempo_min": 5,
        "dias_semana": [1, 2, 3, 4, 5, 6, 7],
        "flg_ativo": True,
        "origem": "Python/API",
        "script": "002_check_supabase.py",
        "dta_modif": _agora_utc(),
    }

    try:
        upsert_carga(linha)
        dl.log(f"[CLOUD] carga registrada no Supabase com status '{status}'")
    except Exception as e:  # noqa: BLE001
        dl.log(f"[CLOUD] ⚠ falha ao registrar a carga no Supabase: {e}")
        dl.logar_traceback("registro da carga no modo CLOUD")
