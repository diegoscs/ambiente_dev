# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 19/10/2026
# DESCRICAO      : Monitor do servidor de Minecraft DENTRO da VM do Google.
#                  A cada minuto (monitor-minecraft.timer, root):
#                    - sessao da VM no Supabase (base do custo do hub)
#                    - DuckDNS com o IP novo (o IP muda a cada boot)
#                    - status, chat e eventos (reaproveita o monitor_minecraft)
#                    - trava de economia: 15 min sem ninguem -> para o
#                      servidor (o backup sai no ExecStopPost) e desliga a VM
#                  --backup: chamado pelo ExecStopPost do minecraft.service.
#                  Compacta o mundo, manda para o Cloud Storage e registra.
#
# HTTP na mao aqui so para o que a lib_dscs nao cobre e so existe na VM:
# metadata do Google, upload binario no Cloud Storage e DuckDNS.
# =============================================
from __future__ import annotations

import os
import sys
from pathlib import Path

# /opt/monitor/automacoes/minecraft_gcp/vm/monitor_vm.py -> raiz em /opt/monitor
RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "automacoes" / "monitor_minecraft"))
os.environ.setdefault("MINECRAFT_DIR", "/opt/minecraft/server")

import json
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import lib_dscs as dl
import monitor_minecraft as mm

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extras_vm as extras

# ─── configuracao ────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent
PASTA_SERVER = Path(os.environ["MINECRAFT_DIR"])

# Sem ninguem online por quanto tempo ate desligar:
DESLIGAR_APOS_MIN = int(os.environ.get("MINECRAFT_IDLE_MIN", "5"))         # depois que alguem ja jogou
PRIMEIRA_ENTRADA_MIN = int(os.environ.get("MINECRAFT_PRIMEIRA_MIN", "15"))  # da VM ligar ate o 1o entrar
# (o TLauncher leva minutos para abrir o modpack: com 5 min desde o boot, a VM
# desligaria com a galera ainda na tela de carregamento)
NAO_SUBIU_MIN = 20          # VM ligada ha isso e servidor fora do ar = desliga tambem

DUCKDNS_DOMINIO = "servercasaonlymine"
DUCKDNS_A_CADA_MIN = 30

ESTADO = Path("/var/lib/monitor_minecraft/estado.json")  # boot_id e ultima atividade

BACKUPS_LOCAIS = Path("/opt/minecraft/backups")
MANTER_LOCAIS = 5           # os de verdade ficam no Cloud Storage (30 dias)
BUCKET = "serverminecasaonly-backups"
# O que entra no backup, relativo a pasta do servidor (o que nao existir e pulado).
# config/passwords.txt = senhas do Login System (BCrypt); sem ele, restaurar um
# backup obrigaria todo mundo a fazer /register de novo.
ITENS_BACKUP = ["world", "journeymap", "config/loginsystem", "config/passwords.txt",
                "config/loginsystem.properties", "whitelist.json", "ops.json",
                "usercache.json", "usernamecache.json", "banned-players.json", "banned-ips.json"]

METADATA = "http://metadata.google.internal/computeMetadata/v1/"

RANKING_A_CADA_S = 300          # world/stats so muda no autosave (5 min)
LIMPEZA_A_CADA_S = 3600
DESEMPENHO_DIAS = 7             # historico de minecraft_desempenho


def agora() -> datetime:
    return datetime.now(timezone.utc)


def iso(dta: datetime) -> str:
    # "Z" e nao "+00:00": o "+" num filtro de URL vira espaco no PostgREST.
    return dta.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def atualizar_ranking() -> None:
    linhas = extras.estatisticas_jogadores()
    if linhas:
        dl.supabase_inserir("minecraft_jogadores", linhas, conflito="jogador")


def metadata(caminho: str) -> str:
    req = urllib.request.Request(METADATA + caminho, headers={"Metadata-Flavor": "Google"})
    return urllib.request.urlopen(req, timeout=3).read().decode()


def info_boot() -> tuple[str, datetime, float]:
    """(boot_id, hora do boot, minutos ligada). O boot_id muda a cada boot."""
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    segundos = float(Path("/proc/uptime").read_text().split()[0])
    return boot_id, agora() - timedelta(seconds=segundos), segundos / 60


def ler_estado() -> dict:
    try:
        return json.loads(ESTADO.read_text())
    except (OSError, ValueError):
        return {}


def gravar_estado(estado: dict) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(estado))


# ─── sessao da VM ───────────────────────────────────────────────────────────


def abrir_sessao(boot_id: str, dta_boot: datetime) -> None:
    # Sessao anterior sem dta_desligou = a VM caiu sem passar pelo desligar_vm
    # (o Google parou, travou, alguem desligou pelo console). Fecha no ultimo sinal.
    for s in dl.supabase_ler(f"minecraft_sessoes?select=id,dta_ligou,dta_ultimo_sinal"
                             f"&dta_desligou=is.null&boot_id=neq.{boot_id}"):
        dl.supabase_atualizar("minecraft_sessoes", f"id=eq.{s['id']}", {
            "dta_desligou": s["dta_ultimo_sinal"] or s["dta_ligou"],
            "motivo": "desligou sem avisar (console do Google ou queda)",
        })
    maquina = metadata("instance/machine-type").rsplit("/", 1)[-1]
    dl.supabase_inserir("minecraft_sessoes", {
        "boot_id": boot_id, "maquina": maquina,
        "dta_ligou": iso(dta_boot), "dta_ultimo_sinal": iso(agora()),
    }, conflito="boot_id", ignorar_repetidos=True)
    dl.log(f"[VM] sessao aberta: {boot_id} ({maquina})")


# ─── DuckDNS ────────────────────────────────────────────────────────────────


def atualizar_duckdns(estado: dict, forcar: bool) -> None:
    token = dl.ler_env().get("DUCKDNS_TOKEN")
    if not token:
        return
    if not forcar and time.time() - estado.get("duckdns", 0) < DUCKDNS_A_CADA_MIN * 60:
        return
    ip = metadata("instance/network-interfaces/0/access-configs/0/external-ip")
    url = "https://www.duckdns.org/update?" + urllib.parse.urlencode(
        {"domains": DUCKDNS_DOMINIO, "token": token, "ip": ip})
    resposta = urllib.request.urlopen(url, timeout=10).read().decode().strip()
    if resposta != "OK":
        raise RuntimeError(f"DuckDNS respondeu {resposta!r}")
    estado["duckdns"] = time.time()
    dl.log(f"[VM] DuckDNS {DUCKDNS_DOMINIO} -> {ip}")


# ─── pedidos do hub dos robos ───────────────────────────────────────────────


def pedido_de_desligar() -> str | None:
    """Fecha os pedidos abertos. Devolve o motivo se alguem pediu para desligar."""
    motivo = None
    for p in dl.comandos_minecraft_abertos():
        if p["status"] != "pendente":
            continue
        if p["acao"] == "ligar":
            dl.fechar_comando_minecraft(p["id"], "ignorado", "A VM já está ligada.", se_status="pendente")
        elif dl.fechar_comando_minecraft(p["id"], "feito", "Desligando a VM.", se_status="pendente"):
            motivo = "pedido pelo hub"
    return motivo


# ─── desligar ───────────────────────────────────────────────────────────────


def desligar_vm(motivo: str, online: bool, linha: dict, boot_id: str) -> None:
    dl.log(f"[VM] desligando: {motivo}")
    dl.gravar_status_minecraft(online, **{**linha, "estado_vm": "desligando"})
    # Para o servidor com calma: "stop", mundo salvo e o backup do ExecStopPost.
    subprocess.run(["systemctl", "stop", "minecraft"], timeout=300)
    try:
        atualizar_ranking()  # com o servidor parado, world/stats tem a sessao inteira
    except Exception as e:  # noqa: BLE001 - ranking nao impede desligar
        dl.log_erro(f"[VM] ranking no desligamento: {e}")
    dl.supabase_atualizar("minecraft_sessoes", f"boot_id=eq.{boot_id}",
                          {"dta_desligou": iso(agora()), "dta_ultimo_sinal": iso(agora()), "motivo": motivo})
    dl.gravar_status_minecraft(False, **{**linha, "jogadores_online": 0, "jogadores": [],
                                         "estado_vm": "desligada", "erro": motivo})
    subprocess.run(["shutdown", "-h", "now"])


# ─── backup (ExecStopPost) ──────────────────────────────────────────────────


def enviar_cloud_storage(arquivo: Path) -> str:
    """Upload simples com o token da conta de servico da VM (so pode criar objetos)."""
    token = json.loads(metadata("instance/service-accounts/default/token"))["access_token"]
    url = (f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o?uploadType=media&name="
           + urllib.parse.quote(arquivo.name))
    req = urllib.request.Request(url, data=arquivo.read_bytes(), method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/gzip"})
    urllib.request.urlopen(req, timeout=180).read()
    return f"gs://{BUCKET}/{arquivo.name}"


def fazer_backup() -> None:
    dl.configurar_logger(0, "backup_vm", BASE)
    inicio = time.time()
    arquivo = BACKUPS_LOCAIS / f"world_{agora():%Y-%m-%d_%H-%M}_utc.tar.gz"
    linha = {"arquivo": arquivo.name}
    try:
        BACKUPS_LOCAIS.mkdir(parents=True, exist_ok=True)
        itens = [i for i in ITENS_BACKUP if (PASTA_SERVER / i).exists()]
        subprocess.run(["tar", "-czf", str(arquivo), "-C", str(PASTA_SERVER), *itens],
                       check=True, capture_output=True, timeout=240)
        linha["bytes"] = arquivo.stat().st_size
        linha["destino"] = dl.executar_com_retry("upload do backup", lambda: enviar_cloud_storage(arquivo), 3, 5)
        for antigo in sorted(BACKUPS_LOCAIS.glob("world_*.tar.gz"))[:-MANTER_LOCAIS]:
            antigo.unlink(missing_ok=True)
        dl.supabase_inserir("minecraft_backups", {**linha, "ok": True,
                                                  "duracao_s": round(time.time() - inicio, 1)})
        dl.log(f"[BACKUP] {arquivo.name} {linha['bytes'] / 1e6:.1f} MB -> {linha['destino']}")
    except Exception as e:
        dl.log_erro(f"[BACKUP] falhou: {e}")
        dl.logar_traceback("backup")
        dl.salvar_log_erro()
        try:
            dl.supabase_inserir("minecraft_backups", {**linha, "ok": False, "erro": str(e)[:300],
                                                      "duracao_s": round(time.time() - inicio, 1)})
        except Exception:  # noqa: BLE001 - sem internet nao da para registrar; o log fica
            pass
        raise


# ─── execucao ───────────────────────────────────────────────────────────────


def verificar_vm() -> None:
    boot_id, dta_boot, minutos_ligada = info_boot()
    estado = ler_estado()
    novo_boot = estado.get("boot_id") != boot_id
    if novo_boot:
        abrir_sessao(boot_id, dta_boot)
        estado = {"boot_id": boot_id, "ultima_atividade": iso(dta_boot)}

    try:
        atualizar_duckdns(estado, novo_boot)
    except Exception as e:  # noqa: BLE001 - DNS fora nao derruba o resto
        dl.log_erro(f"[VM] DuckDNS: {e}")

    online, linha = mm.verificar()
    if online and linha["jogadores_online"] > 0:
        estado["ultima_atividade"] = iso(agora())
        estado["teve_jogador"] = True
    limite_min = DESLIGAR_APOS_MIN if estado.get("teve_jogador") else PRIMEIRA_ENTRADA_MIN
    if online:
        # Extras do hub: falha aqui so deixa o campo vazio, nao derruba a passada.
        for nome, funcao in (("desempenho", lambda: extras.desempenho(mm.rcon, estado)),
                             ("hora/clima", lambda: extras.hora_clima(mm.rcon))):
            try:
                linha |= funcao()
            except Exception as e:  # noqa: BLE001
                dl.log_erro(f"[VM] {nome}: {e}")
    gravar_estado(estado)
    ultima = datetime.fromisoformat(estado["ultima_atividade"].replace("Z", "+00:00"))

    try:
        ip = metadata("instance/network-interfaces/0/access-configs/0/external-ip")
    except OSError:
        ip = None
    try:
        afk = mm.afk_atual() if online else {}
    except Exception as e:  # noqa: BLE001 - AFK e extra do hub
        dl.log_erro(f"[VM] afk: {e}")
        afk = {}
    linha |= {"estado_vm": "ligada", "dta_ultima_atividade": iso(ultima), "ip": ip,
              "desliga_apos_min": limite_min, "afk": afk}

    dl.executar_com_retry("status no Supabase", lambda: dl.gravar_status_minecraft(online, **linha), 2, 5)
    dl.supabase_atualizar("minecraft_sessoes", f"boot_id=eq.{boot_id}", {"dta_ultimo_sinal": iso(agora())})
    eventos = mm.coletar_eventos(dl.ultimo_evento_minecraft())
    if eventos:
        dl.gravar_eventos_minecraft(eventos)

    if online and linha.get("tps") is not None:
        dl.supabase_inserir("minecraft_desempenho", {
            **{k: linha.get(k) for k in ("tps", "mspt", "cpu_pct", "ram_usada_mb", "java_ram_mb")},
            "jogadores": linha["jogadores_online"],
        })
    if time.time() - estado.get("ranking", 0) >= RANKING_A_CADA_S:
        atualizar_ranking()
        estado["ranking"] = time.time()
    if time.time() - estado.get("limpeza", 0) >= LIMPEZA_A_CADA_S:
        dl.supabase_apagar("minecraft_desempenho", f"dta=lt.{iso(agora() - timedelta(days=DESEMPENHO_DIAS))}")
        estado["limpeza"] = time.time()
    gravar_estado(estado)

    motivo = pedido_de_desligar()
    ociosa = agora() - ultima
    if motivo is None and ociosa >= timedelta(minutes=limite_min):
        if online and linha["jogadores_online"] == 0:
            motivo = (f"{limite_min} min sem ninguém" if estado.get("teve_jogador")
                      else f"ninguém entrou em {limite_min} min")
        elif not online and minutos_ligada >= NAO_SUBIU_MIN:
            motivo = "servidor fora do ar"
    if motivo:
        desligar_vm(motivo, online, linha, boot_id)


def main() -> None:
    if "--backup" in sys.argv:
        fazer_backup()
        return
    dl.configurar_logger(0, "monitor_vm", BASE)
    try:
        verificar_vm()
    except Exception as e:
        dl.log_erro(f"[monitor_vm] {e}")
        dl.logar_traceback("monitor_vm")
        dl.salvar_log_erro()
        # Sem internet seriam 1440 arquivos por dia: ficam os 20 mais recentes.
        for antigo in sorted((BASE / "temp").glob("erro_*_monitor_vm_*.txt"))[:-20]:
            antigo.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
