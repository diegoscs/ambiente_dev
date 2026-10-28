# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 28/10/2026
# DESCRICAO      : Saida do robo 004: tabelas no terminal (rich) e um
#                  ranking.html que abre no celular, com graficos hora a hora.
# =============================================
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .fetch import Cidade, Grade, PontoChuva, PrevisaoPraia
from .score import (
    FAIXA_NUBLADO,
    FAIXA_SOL,
    ScoreDia,
    amplitude,
    classificar,
    dias,
    grupos_do_dia,
    ranking_do_dia,
    resumo_por_regiao,
)

DIAS_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
COR_RICH = {"sol": "green", "nublado": "yellow", "chuva": "red"}
TOP = 3

# Diferenca entre melhor e pior praia abaixo disso e ruido de previsao.
AMPLITUDE_RELEVANTE = 10


def nome_dia(dia: date) -> str:
    return f"{DIAS_SEMANA[dia.weekday()]} {dia:%d/%m}"


def _fmt(valor: float | None, sufixo: str = "", casas: int = 0) -> str:
    return "-" if valor is None else f"{valor:.{casas}f}{sufixo}"


def nota_grupos(scores: list[ScoreDia]) -> str:
    praias = len({s.praia.nome for s in scores})
    grupos = len({s.grupo for s in scores})
    return (f"As {praias} praias recebem {grupos} previsões distintas do modelo (grade de ~10-25 km). "
            f"Mesma letra em 'Prev.' = mesma previsão: empate entre elas não é diferença real.")


def leitura_amplitude(ranking: list[ScoreDia]) -> str:
    pontos = amplitude(ranking)
    if pontos < AMPLITUDE_RELEVANTE:
        return f"previsão parecida na cidade toda ({pontos:.0f} pts entre a melhor e a pior)"
    return f"diferença relevante: {pontos:.0f} pts entre a melhor e a pior"


# ─── terminal ────────────────────────────────────────────────────────────────
def _console() -> Console:
    # Fora de terminal (log do Actions) o rich assume 80 colunas e quebra a tabela.
    return Console(width=None if sys.stdout.isatty() else 140)


def _score_rich(valor: float | None) -> str:
    if valor is None:
        return "-"
    return f"[{COR_RICH[classificar(valor)]}]{valor:.0f}[/]"


def _linha_praia(tabela: Table, posicao: str, s: ScoreDia) -> None:
    tabela.add_row(
        posicao, s.praia.nome, s.praia.regiao, s.grupo,
        f"[bold]{_score_rich(s.score)}[/]", _score_rich(s.manha), _score_rich(s.tarde),
        _fmt(s.chuva_prob_max, "%"), _fmt(s.chuva_mm_total, "", 1), _fmt(s.nuvens_media, "%"),
        _fmt(s.vento_medio), _fmt(s.temp_max, "°"), _fmt(s.uv_max),
    )


def _tabela_dia(ranking: list[ScoreDia]) -> Table:
    tabela = Table(title=f"[bold]{nome_dia(ranking[0].dia)}[/] · {leitura_amplitude(ranking)}",
                   title_justify="left", header_style="bold")
    for coluna in ("#", "Praia", "Região", "Prev.", "Score", "Manhã", "Tarde"):
        tabela.add_column(coluna, justify="right" if coluna in ("#", "Score", "Manhã", "Tarde") else "left")
    for coluna in ("Chuva máx", "mm", "Nuvens", "Vento km/h", "Máx", "UV"):
        tabela.add_column(coluna, justify="right")

    for i, s in enumerate(ranking[:TOP], 1):
        _linha_praia(tabela, str(i), s)
    if len(ranking) > TOP:
        tabela.add_section()
        _linha_praia(tabela, f"evitar ({len(ranking)}º)", ranking[-1])
    return tabela


def _tabela_regioes(ranking: list[ScoreDia]) -> Table:
    tabela = Table(header_style="bold", show_edge=False)
    tabela.add_column("Região")
    tabela.add_column("Média", justify="right")
    tabela.add_column("Melhor praia")
    for regiao, (media, melhor) in resumo_por_regiao(ranking).items():
        tabela.add_row(regiao, _score_rich(media), f"{melhor.praia.nome} ({melhor.score:.0f})")
    return tabela


def imprimir_terminal(scores: list[ScoreDia]) -> None:
    console = _console()
    console.print()
    console.print(f"[bold]Score de sol[/] (0-100, 9h-17h) · "
                  f"[green]≥{FAIXA_SOL} sol[/] · [yellow]≥{FAIXA_NUBLADO} nublado[/] · [red]abaixo, chuva[/]")
    console.print(f"[dim]{nota_grupos(scores)}[/]")
    for dia in dias(scores):
        ranking = ranking_do_dia(scores, dia)
        console.print()
        console.print(_tabela_dia(ranking))
        console.print(_tabela_regioes(ranking))


# ─── HTML ────────────────────────────────────────────────────────────────────
# A pagina (CSS, graficos e interacao) mora em templates/ranking.html; aqui so
# se monta o JSON que ela consome. O mesmo JSON serve de contrato para o
# painel web.
TEMPLATE_HTML = Path(__file__).resolve().parent / "templates" / "ranking.html"
HORAS_GRAFICO = range(6, 20)  # 6h-19h: o horario de praia com folga dos dois lados


def _arredondar(valor: float | None, casas: int = 0) -> float | None:
    return None if valor is None else round(valor, casas)


def _horas_do_dia(previsao: PrevisaoPraia, dia: date) -> dict[str, list]:
    horas = [h for h in previsao.horas if h.momento.date() == dia and h.momento.hour in HORAS_GRAFICO]
    return {
        "h": [h.momento.hour for h in horas],
        "chuva_prob": [h.chuva_prob for h in horas],
        "chuva_mm": [h.chuva_mm for h in horas],
        "nuvens": [h.nuvens for h in horas],
        "temp": [h.temperatura for h in horas],
        "vento": [h.vento_kmh for h in horas],
        "uv": [h.uv for h in horas],
    }


def _grupo_json(grupo: list[ScoreDia], previsao: PrevisaoPraia) -> dict:
    s = grupo[0]  # mesma previsao no grupo inteiro: so a temperatura varia (altitude)
    temps = [g.temp_max for g in grupo if g.temp_max is not None]
    return {
        "praias": [{"nome": g.praia.nome, "regiao": g.praia.regiao, "temp_max": _arredondar(g.temp_max),
                    "lat": g.praia.latitude, "lon": g.praia.longitude}
                   for g in grupo],
        "score": round(s.score),
        "manha": _arredondar(s.manha),
        "tarde": _arredondar(s.tarde),
        "faixa": s.faixa,
        "chuva_prob_max": round(s.chuva_prob_max),
        "chuva_mm": round(s.chuva_mm_total, 1),
        "nuvens": round(s.nuvens_media),
        "vento": round(s.vento_medio),
        "temp_max": round(max(temps)) if temps else None,
        "uv_max": _arredondar(s.uv_max),
        "horas": _horas_do_dia(previsao, s.dia),
    }


def _mapa_json(grade: Grade, pontos: list[PontoChuva], dias_mapa: list[date]) -> dict:
    """Chuva da grade por dia e hora: mm[hora][ponto] e prob[hora][ponto].

    Todos os pontos vem da mesma consulta, entao dividem o mesmo eixo de horas.
    """
    eixo = pontos[0].horas
    por_dia = {}
    for dia in dias_mapa:
        indices = [i for i, m in enumerate(eixo) if m.date() == dia and m.hour in HORAS_GRAFICO]
        por_dia[dia.isoformat()] = {
            "h": [eixo[i].hour for i in indices],
            "mm": [[_arredondar(p.chuva_mm[i], 1) for p in pontos] for i in indices],
            "prob": [[_arredondar(p.chuva_prob[i]) for p in pontos] for i in indices],
        }
    return {"passo": grade.passo, "pontos": [[p.latitude, p.longitude] for p in pontos], "dias": por_dia}


def dados_pagina(scores: list[ScoreDia], previsoes: list[PrevisaoPraia], pontos_chuva: list[PontoChuva],
                 cidade: Cidade, gerado_em: datetime) -> dict:
    por_praia = {p.praia.nome: p for p in previsoes}
    dias_json = []
    for dia in dias(scores):
        ranking = ranking_do_dia(scores, dia)
        dias_json.append({
            "data": dia.isoformat(),
            "semana": DIAS_SEMANA[dia.weekday()],
            "dm": f"{dia:%d/%m}",
            "amplitude": round(amplitude(ranking)),
            "grupos": [_grupo_json(g, por_praia[g[0].praia.nome]) for g in grupos_do_dia(ranking)],
        })
    mapa = (_mapa_json(cidade.grade, pontos_chuva, dias(scores))
            if cidade.grade and pontos_chuva else None)
    return {
        "cidade": cidade.nome,
        "gerado": f"{gerado_em:%d/%m %H:%M}",
        "faixa_sol": FAIXA_SOL,
        "faixa_nublado": FAIXA_NUBLADO,
        "amplitude_relevante": AMPLITUDE_RELEVANTE,
        "dias": dias_json,
        "mapa": mapa,
    }


def _js(valor: object) -> str:
    # "</" escapado: o JSON vai dentro de <script> e nao pode fecha-lo.
    return json.dumps(valor, ensure_ascii=False).replace("</", "<\\/")


def _escrever_pagina(arquivo: Path, dados: dict | None, fonte: dict | None) -> Path:
    pagina = (TEMPLATE_HTML.read_text(encoding="utf-8")
              .replace("__DADOS__", _js(dados))
              .replace("__FONTE__", _js(fonte)))
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(pagina, encoding="utf-8")
    return arquivo


def gerar_html(dados: dict, arquivo: Path) -> Path:
    """Pagina com os dados embutidos: abre offline (o ranking.html do run)."""
    return _escrever_pagina(arquivo, dados, None)


def gerar_site(arquivo: Path, supabase_url: str, chave_publica: str, cidade: str) -> Path:
    """Pagina sem dados, que le public.painel_praias ao abrir (o app na Vercel).

    So muda quando o template muda: os dados novos chegam pelo Supabase, sem redeploy.
    """
    return _escrever_pagina(arquivo, None, {"url": supabase_url, "chave": chave_publica, "cidade": cidade})
