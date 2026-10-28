# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 28/10/2026
# DESCRICAO      : Score de sol (0-100) por praia e por dia, so no horario de
#                  praia. Puro calculo: nada de rede nem de tela aqui.
# =============================================
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import mean

from .fetch import Praia, PrevisaoHora, PrevisaoPraia

# Pesos do score. Somam 1.
PESO_CHUVA_PROB = 0.40
PESO_NUVENS = 0.35
PESO_CHUVA_MM = 0.15
PESO_VENTO = 0.10

# Horas cheias da janela. A Open-Meteo carimba cada hora no inicio dela para
# nuvens/temperatura (instantaneo) e no fim para chuva (soma da hora anterior);
# a diferenca de uma hora na borda nao muda o ranking.
HORARIO_PRAIA = range(9, 17)  # 9h-17h
MANHA = range(9, 13)          # 9h-13h
TARDE = range(13, 17)         # 13h-17h

CHUVA_MM_SATURA = 2.0   # mm/h: dali para cima e "chuva de verdade", nota zero
VENTO_FRACO_KMH = 10.0  # ate aqui, nota cheia
VENTO_FORTE_KMH = 30.0  # dali para cima, nota zero

# Faixas de cor. Ceu 100% fechado sem chuva e sem vento da 65: amarelo.
FAIXA_SOL = 70
FAIXA_NUBLADO = 45

ORDEM_REGIOES = ("norte", "centro", "sul")


@dataclass(frozen=True)
class ScoreDia:
    praia: Praia
    dia: date
    score: float
    manha: float | None
    tarde: float | None
    chuva_prob_max: float
    chuva_mm_total: float
    nuvens_media: float
    vento_medio: float
    temp_max: float | None
    uv_max: float | None
    grupo: str  # praias com a mesma letra receberam a mesma previsao

    @property
    def faixa(self) -> str:
        return classificar(self.score)


def classificar(score: float) -> str:
    if score >= FAIXA_SOL:
        return "sol"
    if score >= FAIXA_NUBLADO:
        return "nublado"
    return "chuva"


def _inverso(valor: float, limite: float) -> float:
    """1 no zero, 0 a partir do limite, linear no meio."""
    return 1 - min(max(valor, 0.0), limite) / limite


def _nota_vento(kmh: float) -> float:
    if kmh <= VENTO_FRACO_KMH:
        return 1.0
    return _inverso(kmh - VENTO_FRACO_KMH, VENTO_FORTE_KMH - VENTO_FRACO_KMH)


def _hora_completa(h: PrevisaoHora) -> bool:
    return None not in (h.chuva_prob, h.chuva_mm, h.nuvens, h.vento_kmh)


def score_hora(h: PrevisaoHora) -> float:
    return 100 * (
        PESO_CHUVA_PROB * _inverso(h.chuva_prob, 100)
        + PESO_NUVENS * _inverso(h.nuvens, 100)
        + PESO_CHUVA_MM * _inverso(h.chuva_mm, CHUVA_MM_SATURA)
        + PESO_VENTO * _nota_vento(h.vento_kmh)
    )


def _media_score(horas: list[PrevisaoHora], janela: range) -> float | None:
    notas = [score_hora(h) for h in horas if h.momento.hour in janela]
    return mean(notas) if notas else None


def _maximo(valores: list[float | None]) -> float | None:
    presentes = [v for v in valores if v is not None]
    return max(presentes) if presentes else None


def _score_do_dia(praia: Praia, dia: date, horas: list[PrevisaoHora], grupo: str) -> ScoreDia:
    return ScoreDia(
        praia=praia,
        dia=dia,
        score=_media_score(horas, HORARIO_PRAIA),
        manha=_media_score(horas, MANHA),
        tarde=_media_score(horas, TARDE),
        chuva_prob_max=max(h.chuva_prob for h in horas),
        chuva_mm_total=sum(h.chuva_mm for h in horas),
        nuvens_media=mean(h.nuvens for h in horas),
        vento_medio=mean(h.vento_kmh for h in horas),
        temp_max=_maximo([h.temperatura for h in horas]),
        uv_max=_maximo([h.uv for h in horas]),
        grupo=grupo,
    )


def grupos_de_previsao(previsoes: list[PrevisaoPraia]) -> dict[str, str]:
    """praia -> letra do grupo (A, B, ...), na ordem do cadastro (norte para sul)."""
    letras: dict[tuple, str] = {}
    for p in previsoes:
        letras.setdefault(p.assinatura, chr(ord("A") + len(letras)))
    return {p.praia.nome: letras[p.assinatura] for p in previsoes}


def calcular_scores(previsoes: list[PrevisaoPraia]) -> list[ScoreDia]:
    """Um ScoreDia por praia e por dia. Dia sem nenhuma hora completa fica de fora."""
    grupos = grupos_de_previsao(previsoes)
    scores: list[ScoreDia] = []
    for previsao in previsoes:
        por_dia: dict[date, list[PrevisaoHora]] = defaultdict(list)
        for h in previsao.horas:
            if h.momento.hour in HORARIO_PRAIA and _hora_completa(h):
                por_dia[h.momento.date()].append(h)
        scores += [_score_do_dia(previsao.praia, dia, horas, grupos[previsao.praia.nome])
                   for dia, horas in sorted(por_dia.items())]
    return scores


def dias(scores: list[ScoreDia]) -> list[date]:
    return sorted({s.dia for s in scores})


def ranking_do_dia(scores: list[ScoreDia], dia: date) -> list[ScoreDia]:
    """Praias do dia, da melhor para a pior."""
    return sorted((s for s in scores if s.dia == dia), key=lambda s: s.score, reverse=True)


def grupos_do_dia(ranking: list[ScoreDia]) -> list[list[ScoreDia]]:
    """Praias do dia juntas por grupo de previsao, do melhor grupo para o pior.

    Dentro do grupo o score e identico (mesma previsao), entao a ordem e a do cadastro.
    """
    grupos: dict[str, list[ScoreDia]] = defaultdict(list)
    for s in ranking:
        grupos[s.grupo].append(s)
    return sorted(grupos.values(), key=lambda g: g[0].score, reverse=True)


def resumo_por_regiao(ranking: list[ScoreDia]) -> dict[str, tuple[float, ScoreDia]]:
    """regiao -> (media do score, melhor praia), de norte para sul."""
    grupos: dict[str, list[ScoreDia]] = defaultdict(list)
    for s in ranking:
        grupos[s.praia.regiao].append(s)
    ordem = sorted(grupos, key=lambda r: ORDEM_REGIOES.index(r) if r in ORDEM_REGIOES else 99)
    return {regiao: (mean(s.score for s in grupos[regiao]), max(grupos[regiao], key=lambda s: s.score))
            for regiao in ordem}


def amplitude(ranking: list[ScoreDia]) -> float:
    """Distancia entre a melhor e a pior praia do dia, em pontos de score."""
    return ranking[0].score - ranking[-1].score if ranking else 0.0
