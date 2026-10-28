# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 28/10/2026
# DESCRICAO      : Ranqueia as praias de Ubatuba por chance de sol, dia a dia,
#                  de amanha ate a proxima terca (previsao Open-Meteo). Mostra
#                  no terminal, gera ranking.html e grava em public.previsao_praias.
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

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import lib_dscs as dl

from src import fetch, report, score

# ─── configuracao ────────────────────────────────────────────────────────────
# DEBUG=True  -> nada vai para o Supabase; terminal e ranking.html sim.
# --dry-run   -> igual ao DEBUG, sem editar o arquivo.
# --status    -> mostra a configuracao e o periodo e sai, sem consultar nada.
# --site      -> gera web/index.html (o app da Vercel) e sai, sem consultar nada.
#
# --dry-run, --status e --site nao registram status: nao sao a carga, e marcar
# SUCCESS neles mentiria no monitoramento.
DEBUG = False
DRY_RUN = "--dry-run" in sys.argv
STATUS = "--status" in sys.argv
SITE = "--site" in sys.argv

IDCARGA = 4  # ★ mesmo numero da pasta e do id_carga em public.controle_cargas
NOME_ROBO = "clima_praias"

BASE = Path(__file__).resolve().parent
ARQUIVO_PRAIAS = BASE / "data" / "praias_ubatuba.json"
ARQUIVO_HTML = BASE / "saida" / "ranking.html"
TABELA_DESTINO = "previsao_praias"
TABELA_APP = "painel_praias"

# App publico na Vercel: a pagina le public.painel_praias com a chave
# publicavel (a mesma do hub; feita para ir no navegador, a RLS e que protege).
PASTA_SITE = BASE / "web"
URL_SUPABASE = "https://mthipdxpedlfnkzddlar.supabase.co"
CHAVE_PUBLICA_SUPABASE = "sb_publishable_Y3utSlAXuOl3vzrMeJWr1Q_Rq6Xbz-D"
FUSO_SP = ZoneInfo(fetch.FUSO)
EMOJI_FAIXA = {"sol": "☀️", "nublado": "⛅", "chuva": "🌧️"}

# Sem trava diaria: a previsao muda ao longo do dia e o destino e upsert por
# (cidade, dia, praia). Rodar de novo so troca a previsao pela mais nova.

TENTATIVAS = 3
SEGUNDOS_ENTRE_TENTATIVAS = 20

# Linhas que chegaram de fato ao Supabase nesta execucao.
ITENS_FEITOS = 0


def validar_configuracao() -> None:
    """Tudo que pode estar faltando, conferido antes de qualquer rede."""
    if not ARQUIVO_PRAIAS.exists():
        raise FileNotFoundError(f"Cadastro das praias nao encontrado: {ARQUIVO_PRAIAS}")
    if DEBUG or DRY_RUN or STATUS or SITE:
        return  # sem gravacao, o Supabase nao e necessario
    faltando = [c for c in ("SUPABASE_URL", "SUPABASE_KEY") if not dl.ler_env().get(c)]
    if faltando:
        raise ValueError(f"Faltam variaveis no ambiente/.env: {', '.join(faltando)}")


def _linha_supabase(cidade: str, s: score.ScoreDia, coleta: datetime) -> dict:
    return {
        "cidade": cidade,
        "dia": s.dia.isoformat(),
        "praia": s.praia.nome,
        "regiao": s.praia.regiao,
        "score": round(s.score, 1),
        "score_manha": None if s.manha is None else round(s.manha, 1),
        "score_tarde": None if s.tarde is None else round(s.tarde, 1),
        "faixa": s.faixa,
        "grupo_previsao": s.grupo,
        "chuva_prob_max": round(s.chuva_prob_max),
        "chuva_mm_total": round(s.chuva_mm_total, 1),
        "nuvens_media": round(s.nuvens_media),
        "vento_medio_kmh": round(s.vento_medio, 1),
        "temp_max": s.temp_max,
        "uv_max": s.uv_max,
        "latitude": s.praia.latitude,
        "longitude": s.praia.longitude,
        "dta_coleta": coleta.isoformat(),
    }


def gravar_supabase(cidade: str, scores: list[score.ScoreDia], coleta: datetime) -> int:
    linhas = [_linha_supabase(cidade, s, coleta) for s in scores]
    dl.executar_com_retry(
        "SUPABASE gravacao",
        lambda: dl.supabase_inserir(TABELA_DESTINO, linhas, conflito="cidade,dia,praia"),
        TENTATIVAS,
        SEGUNDOS_ENTRE_TENTATIVAS,
    )
    return len(linhas)


def gravar_painel(cidade: str, dados: dict) -> None:
    """Pacote que o app na Vercel le ao abrir: sobrescreve a linha da cidade."""
    linha = {"cidade": cidade, "dados": dados, "dta_atualizacao": datetime.now(timezone.utc).isoformat()}
    dl.executar_com_retry(
        "SUPABASE app",
        lambda: dl.supabase_inserir(TABELA_APP, linha, conflito="cidade"),
        TENTATIVAS,
        SEGUNDOS_ENTRE_TENTATIVAS,
    )


def gerar_site() -> tuple[int, str]:
    """--site: a pagina do app (web/index.html), que busca os dados no Supabase.

    Rodar so quando o template mudar, e depois publicar a pasta web/ na Vercel.
    """
    cidade = fetch.carregar_cidade(ARQUIVO_PRAIAS)
    arquivo = report.gerar_site(PASTA_SITE / "index.html", URL_SUPABASE, CHAVE_PUBLICA_SUPABASE, cidade.nome)
    dl.log(f"[SITE] {arquivo} - publique com: cd {PASTA_SITE}; vercel deploy --prod")
    return 0, "site"


def buscar_mapa(cidade: fetch.Cidade, inicio: date, fim: date) -> list[fetch.PontoChuva]:
    """Grade de chuva do mapa. Complemento da pagina, nao a carga: se falhar,
    a pagina sai sem mapa e o resumo do hub diz isso, em vez de derrubar um
    ranking que ja foi gravado."""
    if not cidade.grade:
        return []
    try:
        pontos = fetch.buscar_grade_chuva(cidade.grade, inicio, fim, TENTATIVAS, SEGUNDOS_ENTRE_TENTATIVAS)
        dl.log(f"[MAPA] {len(pontos)} pontos de chuva")
        return pontos
    except Exception as e:  # noqa: BLE001 - vira aviso no resumo
        dl.log(f"[MAPA] indisponivel: {e}")
        dl.logar_traceback("mapa de chuva")
        return []


def resumo_primeiro_dia(scores: list[score.ScoreDia]) -> str:
    """Uma linha para o hub: melhor e pior praia do primeiro dia (amanha)."""
    ranking = score.ranking_do_dia(scores, score.dias(scores)[0])
    melhor, pior = ranking[0], ranking[-1]
    return (f"{report.nome_dia(melhor.dia)}: {EMOJI_FAIXA[melhor.faixa]} {melhor.praia.nome} "
            f"({melhor.score:.0f}), evitar {pior.praia.nome} ({pior.score:.0f})")


def mostrar_status() -> tuple[int, str]:
    cidade = fetch.carregar_cidade(ARQUIVO_PRAIAS)
    inicio, fim = fetch.periodo_ate_proxima_terca(datetime.now(FUSO_SP).date())
    dl.log("-" * 70)
    dl.log(f"Cidade              : {cidade.nome}/{cidade.uf} ({len(cidade.praias)} praias)")
    dl.log(f"Periodo da previsao : {inicio:%d/%m} a {fim:%d/%m} (horario de praia 9h-17h)")
    dl.log(f"Destino             : public.{TABELA_DESTINO} + {ARQUIVO_HTML.relative_to(BASE)}")
    if cidade.grade:
        dl.log(f"Mapa de chuva       : {len(cidade.grade.pontos())} pontos a cada {cidade.grade.passo} grau")
    dl.log("-" * 70)
    return 0, "status"


def processar() -> tuple[int, str]:
    """A carga. Devolve (qtd_itens, resumo) para o registro no Supabase."""
    global ITENS_FEITOS

    agora_sp = datetime.now(FUSO_SP)
    cidade = fetch.carregar_cidade(ARQUIVO_PRAIAS)
    inicio, fim = fetch.periodo_ate_proxima_terca(agora_sp.date())
    dl.log(f"[PREVISAO] {len(cidade.praias)} praias de {cidade.nome}, {inicio:%d/%m} a {fim:%d/%m}")

    previsoes = fetch.buscar_previsao(cidade.praias, inicio, fim, TENTATIVAS, SEGUNDOS_ENTRE_TENTATIVAS)
    scores = score.calcular_scores(previsoes)
    if not scores:
        raise RuntimeError("Open-Meteo respondeu sem nenhuma hora completa no horario de praia")

    report.imprimir_terminal(scores)
    resumo = resumo_primeiro_dia(scores)

    if DEBUG or DRY_RUN:
        dl.log(f"[DRY RUN] {len(scores)} previsao(oes) calculada(s) - nada gravado no Supabase")
        resumo = f"dry-run: {resumo}"
    else:
        ITENS_FEITOS = gravar_supabase(cidade.nome, scores, datetime.now(timezone.utc))
        dl.log(f"[SUPABASE] {ITENS_FEITOS} linha(s) em public.{TABELA_DESTINO}")

    pontos_chuva = buscar_mapa(cidade, inicio, fim)
    if cidade.grade and not pontos_chuva:
        resumo += " (sem mapa)"

    dados = report.dados_pagina(scores, previsoes, pontos_chuva, cidade, agora_sp)
    if not (DEBUG or DRY_RUN):
        gravar_painel(cidade.nome, dados)
        dl.log(f"[SUPABASE] pacote do app em public.{TABELA_APP} ({cidade.nome})")

    html = report.gerar_html(dados, ARQUIVO_HTML)
    dl.log(f"[HTML] {html}")
    return ITENS_FEITOS, resumo


def main() -> None:
    dl.configurar_logger(IDCARGA, NOME_ROBO, BASE)

    modo = dl.modo_execucao()
    dta_ini = datetime.now(timezone.utc)

    dl.logar_contexto(
        "DRY-RUN" if (DEBUG or DRY_RUN) else modo,
        extras={
            "Modo de execucao": modo,
            "Praias": str(ARQUIVO_PRAIAS.relative_to(BASE)),
            "Destino": f"Supabase public.{TABELA_DESTINO} + {ARQUIVO_HTML.relative_to(BASE)}",
            "Supabase": "configurado" if dl.supabase_configurado() else "AUSENTE",
            "DEBUG / DRY_RUN": f"{DEBUG} / {DRY_RUN}",
        },
    )

    registrar = not (DEBUG or DRY_RUN or STATUS or SITE)

    try:
        validar_configuracao()

        if registrar:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, dta_ini, fechar=False)

        if STATUS:
            qtd, resumo = mostrar_status()
        elif SITE:
            qtd, resumo = gerar_site()
        else:
            qtd, resumo = processar()

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
                mensagem=f"⚠️ {e}"[:500], qtd_itens=ITENS_FEITOS,
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
