# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 26/09/2026
# DESCRICAO      : Controle de cargas no Supabase (PostgREST). E o registro
#                  oficial dos robos desde a migracao para o GitHub Actions:
#                  public.controle_cargas (ultima execucao) e
#                  public.historico_cargas (uma linha por execucao).
# =============================================
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .api import chamar_api_json
from .config import ler_env, obter_variavel
from .log import log, logar_traceback

TABELA_CONTROLE_SUPABASE = "controle_cargas"
TABELA_HISTORICO_SUPABASE = "historico_cargas"

TIMEOUT_SEGUNDOS = 30

# LOCAL -> Agendador do Windows, com Postgres local (dm).
# CLOUD -> GitHub Actions: nao existe Postgres local, o Supabase e o unico registro.
MODO_LOCAL = "LOCAL"
MODO_CLOUD = "CLOUD"


def modo_execucao() -> str:
    """LOCAL (padrao) ou CLOUD, de MODO_EXECUCAO."""
    modo = (ler_env().get("MODO_EXECUCAO") or MODO_LOCAL).strip().upper()
    if modo not in (MODO_LOCAL, MODO_CLOUD):
        raise ValueError(
            f"MODO_EXECUCAO invalido: {modo!r}. Use {MODO_LOCAL} ou {MODO_CLOUD}."
        )
    return modo


def supabase_configurado() -> bool:
    """True quando URL e chave existem. Sem elas o registro no Supabase e pulado."""
    env = ler_env()
    return bool(env.get("SUPABASE_URL") and env.get("SUPABASE_KEY"))


def url_execucao_actions() -> str | None:
    """Link do run atual no GitHub Actions, ou None fora dele.

    As tres variaveis sao do proprio runner. Le do os.environ direto: nao sao
    credencial, e o ler_env so repassa prefixos da lista branca.
    """
    servidor = os.environ.get("GITHUB_SERVER_URL")
    repositorio = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not (servidor and repositorio and run_id):
        return None
    return f"{servidor}/{repositorio}/actions/runs/{run_id}"


def _url(caminho: str) -> str:
    return f"{obter_variavel('SUPABASE_URL').rstrip('/')}/rest/v1/{caminho}"


def _cabecalhos(extras: dict[str, str] | None = None) -> dict[str, str]:
    """A chave vai em apikey E em Authorization: sem a segunda o PostgREST
    rebaixa o papel para anon, que esbarra na RLS sem policy."""
    chave = obter_variavel("SUPABASE_KEY")
    cabecalhos = {
        "apikey": chave,
        "Authorization": f"Bearer {chave}",
        "Accept": "application/json",
        "User-Agent": "lib_dscs",
    }
    cabecalhos.update(extras or {})
    return cabecalhos


def _iso(valor: datetime | None) -> str | None:
    return valor.astimezone(timezone.utc).isoformat() if valor else None


def _checar(status: int, payload: Any, acao: str) -> None:
    if status not in (200, 201, 204):
        motivo = payload.get("message") or payload.get("hint") if isinstance(payload, dict) else None
        raise RuntimeError(f"{acao} HTTP {status}: {motivo or payload}")


# ─── escrita ────────────────────────────────────────────────────────────────


def registrar_carga_supabase(
    id_carga: int,
    status: str,
    dta_ini: datetime,
    fechar: bool,
    mensagem: str | None = None,
    qtd_itens: int | None = None,
) -> bool:
    """Atualiza a linha da carga e, ao fechar, acrescenta uma linha no historico.

    NUNCA levanta: o registro e consequencia da execucao, nao parte dela. Se o
    Supabase recusar, o erro vai para o log e a execucao segue com o resultado
    que teve.

    A linha precisa existir em controle_cargas (cadastro feito na migration):
    o update nao cria robo novo, para um id digitado errado aparecer como erro.
    """
    dta_fim = datetime.now(timezone.utc) if fechar else None
    ambiente = modo_execucao()
    url_run = url_execucao_actions()

    linha = {
        "status": status,
        "dta_ini": _iso(dta_ini),
        "dta_fim": _iso(dta_fim),
        "ambiente": ambiente,
        "mensagem": mensagem,
        "url_execucao": url_run,
        "dta_modif": _iso(datetime.now(timezone.utc)),
    }

    try:
        status_http, payload = chamar_api_json(
            _url(f"{TABELA_CONTROLE_SUPABASE}?id_carga=eq.{id_carga}"),
            "PATCH",
            corpo=linha,
            cabecalhos=_cabecalhos({"Prefer": "return=representation"}),
            timeout=TIMEOUT_SEGUNDOS,
        )
        _checar(status_http, payload, "update controle_cargas")
        if isinstance(payload, list) and not payload:
            raise ValueError(
                f"id_carga {id_carga} nao existe em public.{TABELA_CONTROLE_SUPABASE}. "
                f"Cadastre a carga antes de registrar status."
            )

        if fechar:
            status_http, payload = chamar_api_json(
                _url(TABELA_HISTORICO_SUPABASE),
                "POST",
                corpo={
                    "id_carga": id_carga,
                    "status": status,
                    "dta_ini": _iso(dta_ini),
                    "dta_fim": _iso(dta_fim),
                    "ambiente": ambiente,
                    "qtd_itens": qtd_itens,
                    "mensagem": mensagem,
                    "url_execucao": url_run,
                },
                cabecalhos=_cabecalhos({"Prefer": "return=minimal"}),
                timeout=TIMEOUT_SEGUNDOS,
            )
            _checar(status_http, payload, "insert historico_cargas")

        log(f"[SUPABASE] id_carga {id_carga} registrado como '{status}' ({ambiente})")
        return True

    except Exception as e:  # noqa: BLE001 - registro nunca derruba o robo
        log(f"[SUPABASE] ⚠ falha ao registrar id_carga {id_carga}: {e}")
        logar_traceback(f"registro do id_carga {id_carga} no Supabase")
        return False


# ─── leitura ────────────────────────────────────────────────────────────────


def trabalho_feito_no_dia(id_carga: int, dia_utc: datetime) -> int:
    """Soma de qtd_itens das execucoes SUCCESS do dia UTC. 0 = nada feito ainda.

    E a trava diaria que funciona na nuvem: a maquina do Actions nasce vazia a
    cada execucao, entao um arquivo local de estado nao lembra de nada.

    Conta so execucoes que fizeram trabalho (qtd_itens > 0): uma execucao que
    saiu por causa da propria trava tambem fecha SUCCESS, com qtd_itens = 0, e
    nao pode contar como o lote do dia.

    Levanta se o Supabase nao responder. Quem chama decide: sem saber se o dia
    ja foi feito, o seguro e nao commitar de novo.
    """
    inicio = dia_utc.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    filtro = (
        f"{TABELA_HISTORICO_SUPABASE}?select=qtd_itens"
        f"&id_carga=eq.{id_carga}&status=eq.SUCCESS&qtd_itens=gt.0"
        f"&dta_ini=gte.{inicio.isoformat().replace('+00:00', 'Z')}"
    )
    status_http, payload = chamar_api_json(
        _url(filtro), "GET", cabecalhos=_cabecalhos(), timeout=TIMEOUT_SEGUNDOS
    )
    _checar(status_http, payload, "leitura historico_cargas")
    return sum(int(p.get("qtd_itens") or 0) for p in payload)
