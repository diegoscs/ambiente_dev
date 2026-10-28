# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 28/10/2026
# DESCRICAO      : Coleta do robo 004: praias do JSON e previsao horaria da
#                  Open-Meteo, todas as praias numa requisicao so.
# =============================================
from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import lib_dscs as dl

URL_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
FUSO = "America/Sao_Paulo"
VARIAVEIS_HORARIAS = (
    "precipitation_probability",
    "precipitation",
    "cloud_cover",
    "wind_speed_10m",
    "temperature_2m",
    "uv_index",
)
VARIAVEIS_MAPA = ("precipitation", "precipitation_probability")
TERCA = 1  # date.weekday(): segunda = 0


@dataclass(frozen=True)
class Praia:
    nome: str
    regiao: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class PrevisaoHora:
    """Uma hora da previsao. None = a Open-Meteo nao tem o valor para essa hora."""

    momento: datetime  # hora local de Sao Paulo, sem fuso (como a API devolve)
    chuva_prob: float | None   # %
    chuva_mm: float | None     # mm na hora anterior
    nuvens: float | None       # %
    vento_kmh: float | None
    temperatura: float | None  # graus C
    uv: float | None


@dataclass(frozen=True)
class PrevisaoPraia:
    praia: Praia
    horas: list[PrevisaoHora]

    @property
    def assinatura(self) -> tuple:
        """Os valores que entram no score, hora a hora.

        O modelo tem grade de ~10-25 km: praias vizinhas caem no mesmo ponto e
        recebem a mesma previsao. A lat/lon que a API devolve nao serve para
        agrupar (o best_match mistura modelos de grades diferentes), entao o
        grupo sai da previsao em si: mesma assinatura = empate sem diferenca real.
        """
        return tuple((h.chuva_prob, h.chuva_mm, h.nuvens, h.vento_kmh) for h in self.horas)


@dataclass(frozen=True)
class Grade:
    """Area do mapa de chuva: pontos a cada `passo` graus (0.05 = ~5 km)."""

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    passo: float

    def pontos(self) -> list[tuple[float, float]]:
        n_lat = round((self.lat_max - self.lat_min) / self.passo) + 1
        n_lon = round((self.lon_max - self.lon_min) / self.passo) + 1
        return [(round(self.lat_min + i * self.passo, 4), round(self.lon_min + j * self.passo, 4))
                for i in range(n_lat) for j in range(n_lon)]


@dataclass(frozen=True)
class PontoChuva:
    latitude: float
    longitude: float
    horas: list[datetime]
    chuva_mm: list[float | None]
    chuva_prob: list[float | None]


@dataclass(frozen=True)
class Cidade:
    nome: str
    uf: str
    praias: list[Praia]
    grade: Grade | None  # sem "mapa" no JSON, a pagina sai sem o mapa


def carregar_cidade(arquivo: Path) -> Cidade:
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    praias = [Praia(p["nome"], p["regiao"], float(p["latitude"]), float(p["longitude"]))
              for p in dados["praias"]]
    if not praias:
        raise ValueError(f"Nenhuma praia em {arquivo}")
    grade = Grade(**dados["mapa"]) if dados.get("mapa") else None
    return Cidade(dados["cidade"], dados["uf"], praias, grade)


def periodo_ate_proxima_terca(hoje: date) -> tuple[date, date]:
    """De amanha ate a proxima terca. Numa terca, vai ate a terca seguinte."""
    dias_ate_terca = (TERCA - hoje.weekday()) % 7 or 7
    return hoje + timedelta(days=1), hoje + timedelta(days=dias_ate_terca)


def montar_url(coordenadas: list[tuple[float, float]], variaveis: tuple[str, ...],
               inicio: date, fim: date, **extras: str) -> str:
    parametros = {
        "latitude": ",".join(f"{lat:.5f}" for lat, _ in coordenadas),
        "longitude": ",".join(f"{lon:.5f}" for _, lon in coordenadas),
        "hourly": ",".join(variaveis),
        "timezone": FUSO,
        "start_date": inicio.isoformat(),
        "end_date": fim.isoformat(),
        **extras,
    }
    return f"{URL_OPEN_METEO}?{urllib.parse.urlencode(parametros, safe=',')}"


def _consultar(etapa: str, url: str, esperados: int, tentativas: int, espera: int) -> list[dict[str, Any]]:
    """Uma requisicao com varios locais. Retry so na rede; 4xx estoura na hora."""
    status, dados = dl.executar_com_retry(etapa, lambda: dl.chamar_api_json(url), tentativas, espera)
    if status != 200:
        motivo = dados.get("reason") if isinstance(dados, dict) else dados
        raise ValueError(f"Open-Meteo recusou a consulta (HTTP {status}): {motivo}")

    # Com uma coordenada a API devolve um objeto; com varias, uma lista na mesma ordem.
    blocos: list[dict[str, Any]] = dados if isinstance(dados, list) else [dados]
    if len(blocos) != esperados:
        raise RuntimeError(f"Open-Meteo devolveu {len(blocos)} local(is) para {esperados} pedidos")
    return blocos


def buscar_previsao(praias: list[Praia], inicio: date, fim: date,
                    tentativas: int = 3, espera: int = 20) -> list[PrevisaoPraia]:
    """Todas as praias numa requisicao so."""
    url = montar_url([(p.latitude, p.longitude) for p in praias], VARIAVEIS_HORARIAS, inicio, fim)
    blocos = _consultar("OPEN-METEO praias", url, len(praias), tentativas, espera)
    return [_converter(praia, bloco) for praia, bloco in zip(praias, blocos)]


def buscar_grade_chuva(grade: Grade, inicio: date, fim: date,
                       tentativas: int = 3, espera: int = 20) -> list[PontoChuva]:
    """Chuva hora a hora na grade do mapa, tambem numa requisicao so.

    cell_selection=nearest: o padrao (land) puxaria os pontos do mar para a
    celula de terra mais proxima, e o mapa perderia a chuva sobre o oceano.
    """
    pontos = grade.pontos()
    url = montar_url(pontos, VARIAVEIS_MAPA, inicio, fim, cell_selection="nearest")
    blocos = _consultar("OPEN-METEO mapa", url, len(pontos), tentativas, espera)
    return [
        PontoChuva(
            lat, lon,
            [datetime.fromisoformat(m) for m in bloco["hourly"]["time"]],
            bloco["hourly"]["precipitation"],
            bloco["hourly"]["precipitation_probability"],
        )
        for (lat, lon), bloco in zip(pontos, blocos)
    ]


def _converter(praia: Praia, bloco: dict[str, Any]) -> PrevisaoPraia:
    horario = bloco["hourly"]
    colunas = [horario[v] for v in VARIAVEIS_HORARIAS]
    horas = [
        PrevisaoHora(datetime.fromisoformat(momento), *valores)
        for momento, *valores in zip(horario["time"], *colunas)
    ]
    return PrevisaoPraia(praia, horas)
