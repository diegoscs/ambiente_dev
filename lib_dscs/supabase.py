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

# Valores da check constraint de status das duas tabelas - nao invente outros.
STATUS_INICIO = "RUNNING"
STATUS_SUCESSO = "SUCCESS"
STATUS_ERRO = "ERROR"

TIMEOUT_SEGUNDOS = 30

# LOCAL -> rodou no PC (na mao, ou robo que precisa de algo que so existe nele).
# CLOUD -> GitHub Actions, o padrao dos robos. Vai para a coluna "ambiente".
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
    """Soma de qtd_itens das execucoes do dia UTC. 0 = nada feito ainda.

    E a trava diaria que funciona na nuvem: a maquina do Actions nasce vazia a
    cada execucao, entao um arquivo local de estado nao lembra de nada.

    Conta so execucoes que fizeram trabalho (qtd_itens > 0): uma execucao que
    saiu por causa da propria trava tambem fecha SUCCESS, com qtd_itens = 0, e
    nao pode contar como o lote do dia. ERROR entra na conta: um lote que
    quebrou no meio registra o que chegou a fazer, e esse trabalho existe.

    Levanta se o Supabase nao responder. Quem chama decide: sem saber se o dia
    ja foi feito, o seguro e nao commitar de novo.
    """
    inicio = dia_utc.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    filtro = (
        f"{TABELA_HISTORICO_SUPABASE}?select=qtd_itens"
        f"&id_carga=eq.{id_carga}&qtd_itens=gt.0"
        f"&dta_ini=gte.{inicio.isoformat().replace('+00:00', 'Z')}"
    )
    status_http, payload = chamar_api_json(
        _url(filtro), "GET", cabecalhos=_cabecalhos(), timeout=TIMEOUT_SEGUNDOS
    )
    _checar(status_http, payload, "leitura historico_cargas")
    return sum(int(p.get("qtd_itens") or 0) for p in payload)


SAUDE_BOA = ("OK", "RODANDO")


def ler_saude_robos() -> list[dict[str, Any]]:
    """Linhas da public.vw_saude_robos (uma por robo ativo). Levanta se falhar.

    saude: OK / RODANDO / ERRO / ATRASADO / TRAVADO / NUNCA_RODOU. Qualquer
    coisa fora de SAUDE_BOA pede atencao.
    """
    status_http, payload = chamar_api_json(
        _url("vw_saude_robos?select=*&order=id_carga"),
        "GET",
        cabecalhos=_cabecalhos(),
        timeout=TIMEOUT_SEGUNDOS,
    )
    _checar(status_http, payload, "leitura vw_saude_robos")
    return payload


# ─── notificacoes do hub ────────────────────────────────────────────────────

TABELA_NOTIFICACOES = "notificacoes_hub"


def ultima_notificacao(origem: str) -> dict[str, Any] | None:
    """Notificacao mais recente de uma origem, ou None. Levanta se falhar."""
    status_http, payload = chamar_api_json(
        _url(f"{TABELA_NOTIFICACOES}?select=nivel,titulo,dta_add&origem=eq.{origem}"
             f"&order=dta_add.desc&limit=1"),
        "GET",
        cabecalhos=_cabecalhos(),
        timeout=TIMEOUT_SEGUNDOS,
    )
    _checar(status_http, payload, "leitura notificacoes_hub")
    return payload[0] if payload else None


def notificar_hub(nivel: str, titulo: str, detalhe: str | None = None, origem: str = "vigia") -> bool:
    """Deixa uma notificacao no hub (info / atencao / resolvido). NUNCA levanta."""
    try:
        status_http, payload = chamar_api_json(
            _url(TABELA_NOTIFICACOES),
            "POST",
            corpo={"origem": origem, "nivel": nivel, "titulo": titulo, "detalhe": detalhe},
            cabecalhos=_cabecalhos({"Prefer": "return=minimal"}),
            timeout=TIMEOUT_SEGUNDOS,
        )
        _checar(status_http, payload, "insert notificacoes_hub")
        log(f"[HUB] notificacao '{nivel}': {titulo}")
        return True
    except Exception as e:  # noqa: BLE001 - notificacao nunca derruba quem chama
        log(f"[HUB] ⚠ falha ao notificar o hub: {e}")
        return False


# ─── status do servidor de Minecraft ────────────────────────────────────────

TABELA_MINECRAFT = "minecraft_status"


def gravar_status_minecraft(online: bool, **campos: Any) -> None:
    """Grava a linha unica de public.minecraft_status (upsert no id 1). Levanta se falhar.

    Os horarios (dta_verificacao e dta_mudanca) sao carimbados por trigger no
    banco: o relogio do PC nao entra na conta do "sem sinal" do hub.
    """
    status_http, payload = chamar_api_json(
        _url(f"{TABELA_MINECRAFT}?on_conflict=id"),
        "POST",
        corpo={"id": 1, "online": online, **campos},
        cabecalhos=_cabecalhos({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        timeout=TIMEOUT_SEGUNDOS,
    )
    _checar(status_http, payload, "upsert minecraft_status")


TABELA_MINECRAFT_EVENTOS = "minecraft_eventos"
LOTE_EVENTOS = 500


def ultimo_evento_minecraft() -> datetime | None:
    """dta_evento mais recente de public.minecraft_eventos, ou None. Levanta se falhar."""
    status_http, payload = chamar_api_json(
        _url(f"{TABELA_MINECRAFT_EVENTOS}?select=dta_evento&order=dta_evento.desc&limit=1"),
        "GET",
        cabecalhos=_cabecalhos(),
        timeout=TIMEOUT_SEGUNDOS,
    )
    _checar(status_http, payload, "leitura minecraft_eventos")
    return datetime.fromisoformat(payload[0]["dta_evento"]) if payload else None


def gravar_eventos_minecraft(eventos: list[dict[str, Any]]) -> None:
    """Insere eventos (dta_evento, tipo, jogador, texto), ignorando repetidos. Levanta se falhar.

    A unique (dta_evento, tipo, jogador, texto) torna o reenvio inofensivo.
    """
    for i in range(0, len(eventos), LOTE_EVENTOS):
        status_http, payload = chamar_api_json(
            _url(f"{TABELA_MINECRAFT_EVENTOS}?on_conflict=dta_evento,tipo,jogador,texto"),
            "POST",
            corpo=eventos[i:i + LOTE_EVENTOS],
            cabecalhos=_cabecalhos({"Prefer": "resolution=ignore-duplicates,return=minimal"}),
            timeout=TIMEOUT_SEGUNDOS,
        )
        _checar(status_http, payload, "insert minecraft_eventos")


TABELA_MINECRAFT_COMANDOS = "minecraft_comandos"


def comandos_minecraft_abertos() -> list[dict[str, Any]]:
    """Pedidos de ligar/desligar pendentes ou executando, mais antigo primeiro. Levanta se falhar.

    "executando" velho e pedido que o monitor pegou e nao fechou (caiu no meio):
    quem chama fecha como erro, senao o indice de um-aberto-por-vez trava a fila.
    """
    status_http, payload = chamar_api_json(
        _url(f"{TABELA_MINECRAFT_COMANDOS}?select=id,acao,status,dta_pedido,dta_execucao"
             f"&status=in.(pendente,executando)&order=dta_pedido"),
        "GET",
        cabecalhos=_cabecalhos(),
        timeout=TIMEOUT_SEGUNDOS,
    )
    _checar(status_http, payload, "leitura minecraft_comandos")
    return payload


def fechar_comando_minecraft(id_comando: int, status: str, mensagem: str | None = None,
                             se_status: str | None = None) -> bool:
    """Atualiza o status de um pedido. Com `se_status`, so muda se ainda estiver nele.

    Devolve False quando nenhuma linha mudou: e assim que o monitor "pega" um
    pedido (pendente -> executando) sem executar duas vezes. Levanta se falhar.
    """
    filtro = f"id=eq.{id_comando}" + (f"&status=eq.{se_status}" if se_status else "")
    status_http, payload = chamar_api_json(
        _url(f"{TABELA_MINECRAFT_COMANDOS}?{filtro}"),
        "PATCH",
        corpo={"status": status, "mensagem": mensagem, "dta_execucao": _iso(datetime.now(timezone.utc))},
        cabecalhos=_cabecalhos({"Prefer": "return=representation"}),
        timeout=TIMEOUT_SEGUNDOS,
    )
    _checar(status_http, payload, "update minecraft_comandos")
    return bool(payload)


# ─── acesso generico (tabelas sem funcao propria) ───────────────────────────


def supabase_ler(consulta: str) -> list[dict[str, Any]]:
    """GET no PostgREST: consulta = "tabela?select=...&filtro". Levanta se falhar."""
    status_http, payload = chamar_api_json(
        _url(consulta), "GET", cabecalhos=_cabecalhos(), timeout=TIMEOUT_SEGUNDOS
    )
    _checar(status_http, payload, f"leitura {consulta.split('?')[0]}")
    return payload


def supabase_inserir(tabela: str, linhas: dict | list[dict], conflito: str | None = None,
                     ignorar_repetidos: bool = False) -> None:
    """Insere uma ou varias linhas. Com `conflito` (colunas da unique) vira upsert:
    atualiza a linha existente, ou a deixa como esta se ignorar_repetidos. Levanta se falhar."""
    prefer = ["return=minimal"]
    if conflito:
        prefer.append("resolution=" + ("ignore-duplicates" if ignorar_repetidos else "merge-duplicates"))
    status_http, payload = chamar_api_json(
        _url(tabela + (f"?on_conflict={conflito}" if conflito else "")),
        "POST",
        corpo=linhas,
        cabecalhos=_cabecalhos({"Prefer": ",".join(prefer)}),
        timeout=TIMEOUT_SEGUNDOS,
    )
    _checar(status_http, payload, f"insert {tabela}")


def supabase_atualizar(tabela: str, filtro: str, campos: dict[str, Any]) -> list[dict[str, Any]]:
    """PATCH nas linhas do filtro ("id=eq.3"). Devolve as linhas alteradas. Levanta se falhar."""
    status_http, payload = chamar_api_json(
        _url(f"{tabela}?{filtro}"),
        "PATCH",
        corpo=campos,
        cabecalhos=_cabecalhos({"Prefer": "return=representation"}),
        timeout=TIMEOUT_SEGUNDOS,
    )
    _checar(status_http, payload, f"update {tabela}")
    return payload


def supabase_apagar(tabela: str, filtro: str) -> None:
    """DELETE nas linhas do filtro ("dta=lt.2026-01-01"). Filtro vazio e recusado. Levanta se falhar."""
    if not filtro:
        raise ValueError("supabase_apagar sem filtro apagaria a tabela inteira")
    status_http, payload = chamar_api_json(
        _url(f"{tabela}?{filtro}"), "DELETE",
        cabecalhos=_cabecalhos({"Prefer": "return=minimal"}), timeout=TIMEOUT_SEGUNDOS,
    )
    _checar(status_http, payload, f"delete {tabela}")
