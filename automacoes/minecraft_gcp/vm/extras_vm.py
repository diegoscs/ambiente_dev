# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 19/10/2026
# DESCRICAO      : Extras do hub do servidor, lidos dentro da VM pelo monitor_vm:
#                  desempenho (TPS, CPU, RAM), hora/clima do jogo e o ranking
#                  da galera (estatisticas que o proprio Minecraft grava).
#                  Separado do monitor_vm para ele nao passar de ~400 linhas.
# =============================================
from __future__ import annotations

import gzip
import json
import os
import re
import struct
import subprocess
import time
from pathlib import Path

PASTA_SERVER = Path(os.environ.get("MINECRAFT_DIR", "/opt/minecraft/server"))
MUNDO = PASTA_SERVER / "world"


# ─── desempenho ─────────────────────────────────────────────────────────────


def _tps(rcon) -> tuple[float | None, float | None]:
    """(TPS, ms por tick) da linha Overall do /neoforge tps."""
    m = re.search(r"Overall:\s*([\d.]+)\s*TPS\s*\(([\d.]+)\s*ms", rcon("neoforge tps"))
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def _cpu_pct(estado: dict) -> float | None:
    """CPU da VM entre esta leitura e a anterior (/proc/stat), em %."""
    campos = [int(x) for x in Path("/proc/stat").read_text().split("\n", 1)[0].split()[1:]]
    ocioso, total = campos[3] + campos[4], sum(campos)
    anterior = estado.get("cpu")
    estado["cpu"] = [ocioso, total]
    if not anterior or total <= anterior[1]:
        return None
    return round(100 * (1 - (ocioso - anterior[0]) / (total - anterior[1])), 1)


def _memoria() -> tuple[int, int, int | None]:
    """(RAM usada da VM, RAM total, RAM do java do servidor), em MB."""
    info = dict(l.split(":", 1) for l in Path("/proc/meminfo").read_text().splitlines() if ":" in l)
    kb = lambda chave: int(info[chave].split()[0])
    total, livre = kb("MemTotal") // 1024, kb("MemAvailable") // 1024
    java = None
    r = subprocess.run(["pgrep", "-f", "unix_args.txt"], capture_output=True, text=True)
    for pid in r.stdout.split():
        try:
            rss = re.search(r"VmRSS:\s*(\d+)", Path(f"/proc/{pid}/status").read_text())
            if rss:
                java = int(rss.group(1)) // 1024
        except OSError:
            pass
    return total - livre, total, java


def desempenho(rcon, estado: dict) -> dict:
    tps, mspt = _tps(rcon)
    usada, total, java = _memoria()
    return {"tps": tps, "mspt": mspt, "cpu_pct": _cpu_pct(estado),
            "ram_usada_mb": usada, "ram_total_mb": total, "java_ram_mb": java}


# ─── hora e clima ───────────────────────────────────────────────────────────


def _nbt_compound(dados: bytes, pos: int) -> tuple[dict, int]:
    """Leitor minimo de NBT (formato do level.dat): devolve o compound e a posicao."""
    resultado = {}
    while True:
        tipo = dados[pos]; pos += 1
        if tipo == 0:
            return resultado, pos
        tam = struct.unpack(">H", dados[pos:pos + 2])[0]; pos += 2
        nome = dados[pos:pos + tam].decode("utf-8", "replace"); pos += tam
        resultado[nome], pos = _nbt_valor(tipo, dados, pos)


def _nbt_valor(tipo: int, dados: bytes, pos: int):
    fixos = {1: ">b", 2: ">h", 3: ">i", 4: ">q", 5: ">f", 6: ">d"}
    if tipo in fixos:
        fmt = fixos[tipo]; n = struct.calcsize(fmt)
        return struct.unpack(fmt, dados[pos:pos + n])[0], pos + n
    if tipo in (7, 11, 12):  # arrays de byte/int/long: so pula
        qtd = struct.unpack(">i", dados[pos:pos + 4])[0]
        return None, pos + 4 + qtd * {7: 1, 11: 4, 12: 8}[tipo]
    if tipo == 8:
        tam = struct.unpack(">H", dados[pos:pos + 2])[0]
        return dados[pos + 2:pos + 2 + tam].decode("utf-8", "replace"), pos + 2 + tam
    if tipo == 9:
        filho, qtd = dados[pos], struct.unpack(">i", dados[pos + 1:pos + 5])[0]; pos += 5
        itens = []
        for _ in range(max(0, qtd)):
            v, pos = _nbt_valor(filho, dados, pos)
            itens.append(v)
        return itens, pos
    if tipo == 10:
        return _nbt_compound(dados, pos)
    raise ValueError(f"tipo NBT desconhecido: {tipo}")


def hora_clima(rcon) -> dict:
    """Hora/dia pelo RCON (exatos) e chuva pelo level.dat (atualizado no autosave)."""
    numero = lambda texto: int(re.search(r"(-?\d+)", texto).group(1))
    linha = {"mundo_tick": numero(rcon("time query daytime")) % 24000,
             "mundo_dia": numero(rcon("time query day"))}
    try:
        raw = gzip.decompress((MUNDO / "level.dat").read_bytes())
        raiz, _ = _nbt_compound(raw, 3 + struct.unpack(">H", raw[1:3])[0])  # pula o cabecalho do compound raiz
        dados = raiz.get("Data", {})
        linha |= {"chuva": bool(dados.get("raining")), "trovoada": bool(dados.get("thundering"))}
    except (OSError, ValueError, struct.error, IndexError):
        pass
    return linha


# ─── ranking ────────────────────────────────────────────────────────────────


def estatisticas_jogadores() -> list[dict]:
    """Uma linha por jogador, de world/stats (custom/mined) e world/advancements."""
    nomes = {}
    try:
        nomes = {u["uuid"]: u["name"] for u in json.loads((PASTA_SERVER / "usercache.json").read_text())}
    except (OSError, ValueError, KeyError):
        pass
    linhas = []
    for arquivo in (MUNDO / "stats").glob("*.json"):
        uuid = arquivo.stem
        try:
            stats = json.loads(arquivo.read_text())["stats"]
        except (OSError, ValueError, KeyError):
            continue
        c = stats.get("minecraft:custom", {})
        cm = sum(v for k, v in c.items() if k.endswith("_one_cm") and k != "minecraft:fall_one_cm")
        conquistas = 0
        try:
            avancos = json.loads((MUNDO / "advancements" / f"{uuid}.json").read_text())
            conquistas = sum(1 for k, v in avancos.items()
                             if isinstance(v, dict) and v.get("done") and "recipes/" not in k)
        except (OSError, ValueError):
            pass
        linhas.append({
            "jogador": nomes.get(uuid, uuid[:8]), "uuid": uuid,
            "tempo_jogado_min": c.get("minecraft:play_time", 0) // 1200,   # 20 ticks/s
            "mortes": c.get("minecraft:deaths", 0),
            "mobs_mortos": c.get("minecraft:mob_kills", 0),
            "jogadores_mortos": c.get("minecraft:player_kills", 0),
            "distancia_km": round(cm / 100000, 2),
            "blocos_minerados": sum(stats.get("minecraft:mined", {}).values()),
            "conquistas": conquistas,
            "dta_atualizacao": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    return linhas
