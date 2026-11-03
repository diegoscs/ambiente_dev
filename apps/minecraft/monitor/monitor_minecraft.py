# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 19/10/2026
# DESCRICAO      : Status do servidor de Minecraft da galera para o hub.
#                  Pergunta ao server (localhost:25565) quem esta online, pelo
#                  mesmo ping da lista de servidores do jogo, e grava a linha
#                  unica de public.minecraft_status no Supabase. Tambem le os
#                  logs do server e manda chat, comandos, entradas/saidas e
#                  conquistas para public.minecraft_eventos, e executa os
#                  pedidos de ligar/desligar do hub (public.minecraft_comandos).
#
# Roda no PC (Agendador do Windows, a cada minuto): o server so existe aqui,
# atras da Radmin VPN, e nem o Actions nem a Vercel conseguem alcanca-lo.
# Nao e carga: nao registra em controle_cargas. A propria linha e o sinal de
# vida - se o PC desliga, ela envelhece e o hub mostra "sem sinal".
# =============================================
from __future__ import annotations

import os
import sys
from pathlib import Path

# --- bootstrap padrao: encoding + caminho da lib (nesta ordem, antes dos imports)
# Pelo Agendador roda com pythonw (sem janela piscando), e ai nao existe console.
if sys.stdout is None:
    sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # raiz: apps/minecraft/monitor/
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import gzip
import json
import re
import socket
import struct
import subprocess
import time
from datetime import datetime, timedelta, timezone

import lib_dscs as dl

# ─── configuracao ────────────────────────────────────────────────────────────
# --dry-run -> consulta o server e mostra o resultado, sem gravar no Supabase.
DRY_RUN = "--dry-run" in sys.argv

NOME = "monitor_minecraft"
BASE = Path(__file__).resolve().parent

HOST = "127.0.0.1"
PORTA = 25565            # server-port do server.properties
TIMEOUT_SEGUNDOS = 5
PROTOCOLO = 767          # 1.21.1; no ping de status o server responde com qualquer um

# Log so em erro, um arquivo por falha. Sem internet o dia inteiro seriam
# 1440 arquivos: fica so o mais recente desta quantidade.
MAX_LOGS_ERRO = 20

# Entradas falsas que alguns servers poem na lista (texto com cor, uuid zerado).
UUID_ZERADO = "00000000-0000-0000-0000-000000000000"

# No PC, a pasta ao lado; na VM do Google, MINECRAFT_DIR=/opt/minecraft/server.
PASTA_SERVER = Path(os.environ.get("MINECRAFT_DIR") or BASE.parent / "local" / "server")

# Logs do server. O latest.log vira AAAA-MM-DD-N.log.gz a cada start e a meia-noite.
PASTA_LOGS = PASTA_SERVER / "logs"
LOG_KUBEJS = PASTA_LOGS / "kubejs" / "server.log"
TEXTO_MAX = 1000

# Ligar/desligar pelo hub (tabela public.minecraft_comandos).
# Ligar = rodar a tarefa sob demanda que abre o start.bat (criada pelo
# instalar_tarefa.ps1): o server nasce na janela de sempre e nao fica
# pendurado neste processo. Desligar = "stop" pelo RCON local.
TAREFA_SERVER = "Minecraft Server (hub)"
PEDIDO_VALIDO_MIN = 10       # pedido mais velho que isso nao executa (PC estava desligado)
EXECUTANDO_MAX_MIN = 5       # "executando" mais velho que isso = monitor caiu no meio
AVISO_DESLIGAR_SEGUNDOS = 30  # aviso no chat antes do stop, se tiver gente jogando
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ─── ping da lista de servidores (Server List Ping) ─────────────────────────
# https://minecraft.wiki/w/Java_Edition_protocol/Server_List_Ping


def _varint(valor: int) -> bytes:
    valor &= 0xFFFFFFFF
    saida = b""
    while True:
        byte = valor & 0x7F
        valor >>= 7
        saida += bytes([byte | (0x80 if valor else 0)])
        if not valor:
            return saida


def _ler_varint(sock: socket.socket) -> int:
    valor = 0
    for i in range(5):
        byte = _ler(sock, 1)[0]
        valor |= (byte & 0x7F) << (7 * i)
        if not byte & 0x80:
            return valor
    raise ValueError("VarInt grande demais na resposta do server")


def _ler(sock: socket.socket, n: int) -> bytes:
    dados = b""
    while len(dados) < n:
        pedaco = sock.recv(n - len(dados))
        if not pedaco:
            raise ConnectionError("server fechou a conexao no meio da resposta")
        dados += pedaco
    return dados


def _pacote(conteudo: bytes) -> bytes:
    return _varint(len(conteudo)) + conteudo


def consultar_server() -> dict:
    """JSON de status do server. Levanta OSError se a porta nao responder."""
    host = HOST.encode("utf-8")
    handshake = (
        _varint(0x00) + _varint(PROTOCOLO)
        + _varint(len(host)) + host + struct.pack(">H", PORTA)
        + _varint(1)  # proximo estado: status
    )
    inicio = time.perf_counter()
    with socket.create_connection((HOST, PORTA), timeout=TIMEOUT_SEGUNDOS) as sock:
        sock.sendall(_pacote(handshake) + _pacote(_varint(0x00)))
        _ler_varint(sock)                       # tamanho do pacote
        if _ler_varint(sock) != 0x00:
            raise ValueError("resposta de status inesperada do server")
        texto = _ler(sock, _ler_varint(sock)).decode("utf-8")
    status = json.loads(texto)
    status["_latencia_ms"] = round((time.perf_counter() - inicio) * 1000)
    return status


def _texto_motd(descricao) -> str:
    """O motd vem como texto ou como componente de chat; tira as cores (§x)."""
    if isinstance(descricao, dict):
        partes = [descricao.get("text", "")]
        partes += [_texto_motd(e) for e in descricao.get("extra", [])]
        descricao = "".join(partes)
    return re.sub(r"§.", "", str(descricao or "")).strip()


def montar_linha(status: dict) -> dict:
    jogadores = status.get("players") or {}
    nomes = sorted(
        (p.get("name") or "" for p in jogadores.get("sample") or []
         if p.get("id") != UUID_ZERADO and "§" not in (p.get("name") or "")),
        key=str.lower,
    )
    return {
        "jogadores_online": int(jogadores.get("online") or 0),
        "jogadores_max": jogadores.get("max"),
        "jogadores": [n for n in nomes if n],
        "versao": (status.get("version") or {}).get("name"),
        "motd": _texto_motd(status.get("description")),
        "latencia_ms": status.get("_latencia_ms"),
        "erro": None,
    }


# ─── eventos do log (chat, comandos, entradas, conquistas) ──────────────────
# Linha do server: [19out.2026 09:34:57.332] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: <msg>
# A data sai no idioma e no fuso da maquina: "19out.2026" no Windows em
# portugues, "19Oct2026" no Linux da VM (em UTC).

MESES = {m: i for i, m in enumerate(
    ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"), 1)}
MESES |= {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}

RE_LINHA = re.compile(
    r"^\[(\d{1,2})(\w{3})\.?(\d{4}) (\d\d):(\d\d):(\d\d)\.(\d{3})\] "
    r"\[Server thread/INFO\] \[net\.minecraft\.server\.MinecraftServer/\]: (.*)$"
)
NICK = r"([A-Za-z0-9_]{1,16})"
PADROES = [
    # chat normal (online-mode=false sai como [Not Secure]), /me e /say
    ("chat", re.compile(rf"^(?:\[Not Secure\] )?<{NICK}> (.*)$")),
    ("chat", re.compile(rf"^\* {NICK} (.*)$")),
    ("chat", re.compile(rf"^\[{NICK}\] (.*)$")),
    # comando de op com retorno para os admins: [digoscs: Set own game mode to Creative Mode]
    ("comando", re.compile(rf"^\[{NICK}: (.*)\]$")),
    ("entrou", re.compile(rf"^{NICK} joined the game$")),
    ("saiu", re.compile(rf"^{NICK} left the game$")),
    ("conquista", re.compile(rf"^{NICK} has (?:made the advancement|completed the challenge|reached the goal) \[(.*)\]$")),
]

# O hub do servidor e PUBLICO. Comando de senha (mod Login System) nunca sai
# daqui; mensagem privada sai so com o destinatario. Em 19/10/2026 o
# /register com a senha chegou a aparecer no hub: este filtro e a segunda
# barreira (a primeira e o proprio script do KubeJS nao registrar).
COMANDOS_SENHA = {"register", "reg", "login", "l", "changepassword", "changepass", "cp",
                  "loginadmin", "loadmin", "password", "senha"}
COMANDOS_PRIVADOS = {"msg", "tell", "w", "whisper", "m", "r", "reply", "teammsg", "tm"}


def comando_publicavel(texto: str) -> str | None:
    """O comando como pode aparecer no hub, ou None se nao pode aparecer."""
    partes = texto.split()
    if not partes:
        return None
    nome = partes[0].lstrip("/").lower().split(":")[-1]  # "minecraft:msg" -> "msg"
    if nome in COMANDOS_SENHA:
        return None
    if nome in COMANDOS_PRIVADOS:
        para = partes[1] if len(partes) > 1 and nome not in ("r", "reply", "teammsg", "tm") else ""
        return f"/{nome} {para} (mensagem privada)".replace("  ", " ")
    return texto


# Comando de qualquer jogador, escrito pelo kubejs/server_scripts/monitor_comandos.js
# (fica no log do KubeJS, que nao tem data na linha: o script poe o horario em UTC).
# Desde 21/10/2026 a linha traz o efeito entre colchetes ([sem_efeito], [ok],
# [mudou:creative]); linhas antigas, sem ele, continuam valendo.
RE_KUBEJS = re.compile(r"\[monitor_minecraft\] CMD (\S+) " + NICK + r" (?:\[([^\]\s]+)\] )?(/.*)$")


def _evento(dta: datetime, tipo: str, jogador: str, texto: str = "", efeito: str | None = None) -> dict:
    # Todo evento tem as mesmas chaves: o insert em lote do PostgREST exige.
    return {"dta_evento": dta.isoformat(), "tipo": tipo, "jogador": jogador,
            "texto": texto.strip()[:TEXTO_MAX], "efeito": efeito}


def jogadores_conhecidos() -> set[str]:
    """Nicks que ja passaram pelo servidor (usercache + whitelist)."""
    nomes = set()
    for arquivo in ("usercache.json", "whitelist.json"):
        try:
            nomes |= {j["name"] for j in json.loads((PASTA_SERVER / arquivo).read_text(encoding="utf-8"))}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return nomes


# Morte: o servidor escreve "<nick> <causa>" ("was slain by Zombie", "burned
# to death", "was pierced by Necromancer's icicle"...). Com modpack as frases
# variam demais para listar; vale a linha que comeca com um jogador conhecido e
# nao casou com chat/entrada/saida/conquista. Nick conhecido evita pegar a morte
# de um pet com nome.
def _morte(msg: str, conhecidos: set[str]) -> tuple[str, str] | None:
    nick, _, resto = msg.partition(" ")
    if nick in conhecidos and resto and not resto.startswith(("lost connection", "moved ", "issued ")):
        return nick, resto
    return None


def eventos_do_texto(texto: str) -> list[dict]:
    eventos = []
    conhecidos = jogadores_conhecidos()
    for linha in texto.splitlines():
        m = RE_LINHA.match(linha)
        if not m or m.group(2).lower() not in MESES:
            continue
        dia, mes, ano, h, mi, s, ms, msg = m.groups()
        # Sem fuso: o log esta no horario da maquina, e astimezone() assume isso.
        dta = datetime(int(ano), MESES[mes.lower()], int(dia), int(h), int(mi), int(s),
                       int(ms) * 1000).astimezone()
        for tipo, padrao in PADROES:
            p = padrao.match(msg)
            if p:
                eventos.append(_evento(dta, tipo, *p.groups()))
                break
        else:
            morte = _morte(msg, conhecidos)
            if morte:
                eventos.append(_evento(dta, "morte", *morte))
    return eventos


# Kick por inatividade e quem esta parado, do kubejs/server_scripts/afk_kick.js.
RE_AFKKICK = re.compile(r"\[monitor_minecraft\] AFKKICK (\S+) " + NICK + r" (\d+)$")
RE_AFK = re.compile(r"\[monitor_minecraft\] AFK (\S+) (\S+)$")
AFK_VALIDO_S = 90  # a linha AFK sai a cada 30 s; mais velha que isso = ninguem parado


def afk_atual(agora: datetime | None = None) -> dict[str, int]:
    """{nick: minutos parado} da ultima linha AFK do log do KubeJS, se recente."""
    if not LOG_KUBEJS.exists():
        return {}
    ultima = None
    for linha in _ler_log(LOG_KUBEJS).splitlines():
        m = RE_AFK.search(linha)
        if m:
            ultima = m
    if not ultima:
        return {}
    dta = datetime.fromisoformat(ultima.group(1).replace("Z", "+00:00"))
    if ((agora or datetime.now(dta.tzinfo)) - dta).total_seconds() > AFK_VALIDO_S:
        return {}
    parados = {}
    for par in ultima.group(2).split(","):
        nick, _, minutos = par.partition("=")
        if nick and minutos.isdigit():
            parados[nick] = int(minutos)
    return parados


def eventos_do_kubejs(texto: str) -> list[dict]:
    eventos = []
    for linha in texto.splitlines():
        k = RE_AFKKICK.search(linha)
        if k:
            dta = datetime.fromisoformat(k.group(1).replace("Z", "+00:00"))
            eventos.append(_evento(dta, "afk", k.group(2), f"{k.group(3)} min parado"))
            continue
        m = RE_KUBEJS.search(linha)
        if m:
            dta = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
            eventos.append(_evento(dta, "comando", m.group(2), m.group(4), m.group(3)))
    return eventos


def _ler_log(arquivo: Path) -> str:
    if arquivo.suffix == ".gz":
        with gzip.open(arquivo, "rt", encoding="utf-8", errors="replace") as f:
            return f.read()
    return arquivo.read_text(encoding="utf-8", errors="replace")


def coletar_eventos(desde: datetime | None) -> list[dict]:
    """Eventos depois de `desde` (None = tudo que existe nos logs).

    Le o latest.log e os .gz modificados depois de `desde`: cobre a rotacao
    que acontece entre duas execucoes, e na primeira vez importa o historico.
    """
    corte = desde.timestamp() if desde else 0
    arquivos = [a for a in sorted(PASTA_LOGS.glob("*.log.gz")) if a.stat().st_mtime > corte]
    arquivos.append(PASTA_LOGS / "latest.log")

    eventos = []
    for arquivo in arquivos:
        if arquivo.exists():
            eventos += eventos_do_texto(_ler_log(arquivo))
    if LOG_KUBEJS.exists():
        eventos += eventos_do_kubejs(_ler_log(LOG_KUBEJS))

    publicaveis = []
    for e in eventos:
        # Comando do console/RCON (administracao: /give, /reload...) nao e
        # atividade de jogador e nao vai para o painel publico.
        if e["tipo"] == "comando" and e["jogador"] in ("Rcon", "Server"):
            continue
        if e["tipo"] == "comando":
            texto = comando_publicavel(e["texto"])
            if texto is None:
                continue
            e["texto"] = texto
        publicaveis.append(e)
    eventos = publicaveis

    # >= e nao >: dois eventos no mesmo milissegundo. Repetido o banco ignora.
    if desde:
        eventos = [e for e in eventos if datetime.fromisoformat(e["dta_evento"]) >= desde]
    # Sem duplicata no mesmo lote (o Postgres recusa o upsert inteiro se houver).
    unicos = {(e["dta_evento"], e["tipo"], e["jogador"], e["texto"]): e for e in eventos}
    return sorted(unicos.values(), key=lambda e: e["dta_evento"])


# ─── ligar / desligar pelo hub ──────────────────────────────────────────────


def rcon(comando: str) -> str:
    """Um comando pelo RCON local. Senha e porta vem do server.properties do server."""
    cfg = dict(
        linha.split("=", 1)
        for linha in (PASTA_SERVER / "server.properties").read_text(encoding="utf-8").splitlines()
        if "=" in linha and not linha.startswith("#")
    )
    if cfg.get("enable-rcon", "").strip() != "true":
        raise RuntimeError("RCON desligado no server.properties (enable-rcon)")
    porta = int(cfg.get("rcon.port", "25575"))

    with socket.create_connection((HOST, porta), timeout=TIMEOUT_SEGUNDOS) as sock:
        def enviar(id_pacote: int, tipo: int, texto: str) -> None:
            corpo = struct.pack("<ii", id_pacote, tipo) + texto.encode("utf-8") + b"\0\0"
            sock.sendall(struct.pack("<i", len(corpo)) + corpo)

        def receber() -> tuple[int, str]:
            dados = _ler(sock, struct.unpack("<i", _ler(sock, 4))[0])
            return struct.unpack("<i", dados[:4])[0], dados[8:-2].decode("utf-8", "replace")

        enviar(1, 3, cfg["rcon.password"].strip())
        if receber()[0] == -1:
            raise PermissionError("senha do RCON recusada")
        enviar(2, 2, comando)
        return receber()[1]


def server_rodando() -> bool:
    """Ha um java do server rodando (subindo ou no ar)?

    O NeoForge do server sobe com @.../win_args.txt; o jogo aberto pelo
    TLauncher neste mesmo PC tambem e java com neoforge, mas sem esse arquivo.
    No Linux (VM) o arquivo e o unix_args.txt.
    """
    if os.name != "nt":
        return subprocess.run(["pgrep", "-f", "unix_args.txt"], capture_output=True).returncode == 0
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object Name -eq 'java.exe' | ForEach-Object CommandLine"],
        capture_output=True, text=True, errors="replace", timeout=60, creationflags=SEM_JANELA,
    )
    return "win_args.txt" in r.stdout


def executar_pedido(acao: str, online: bool, linha: dict) -> tuple[str, str]:
    """Executa ligar/desligar. Devolve (status, mensagem para o hub)."""
    if acao == "ligar":
        if online:
            return "ignorado", "O server já estava ligado."
        if server_rodando():
            return "ignorado", "O server já está subindo; aparece online em 1 ou 2 minutos."
        r = subprocess.run(
            ["schtasks", "/run", "/tn", TAREFA_SERVER],
            capture_output=True, text=True, errors="replace", timeout=60, creationflags=SEM_JANELA,
        )
        if r.returncode:
            raise RuntimeError(f"schtasks /run '{TAREFA_SERVER}': {(r.stderr or r.stdout).strip()}")
        return "feito", "Server iniciado no PC; aparece online em 1 ou 2 minutos."

    if not online:
        if server_rodando():
            return "ignorado", "O server ainda está subindo; peça para desligar quando ele estiver online."
        return "ignorado", "O server já estava desligado."

    jogando = linha.get("jogadores") or []
    if linha.get("jogadores_online"):
        rcon(f"say O server vai desligar em {AVISO_DESLIGAR_SEGUNDOS} segundos (pedido pelo hub).")
        time.sleep(AVISO_DESLIGAR_SEGUNDOS)
    try:
        rcon("stop")  # salva o mundo e sai com codigo 0: o start.bat nao reinicia
    except (ConnectionError, TimeoutError):
        pass  # o server pode fechar a conexao antes de responder
    if jogando:
        return "feito", f"Server desligado ({', '.join(jogando)} avisado(s) no chat {AVISO_DESLIGAR_SEGUNDOS} s antes)."
    return "feito", "Server desligado (ninguém estava jogando)."


def processar_pedidos(online: bool, linha: dict) -> None:
    agora = datetime.now(timezone.utc)
    for pedido in dl.comandos_minecraft_abertos():
        id_pedido, acao = pedido["id"], pedido["acao"]

        if pedido["status"] == "executando":
            desde = datetime.fromisoformat(pedido["dta_execucao"] or pedido["dta_pedido"])
            if agora - desde > timedelta(minutes=EXECUTANDO_MAX_MIN):
                dl.fechar_comando_minecraft(id_pedido, "erro", "O monitor parou no meio. Peça de novo.",
                                            se_status="executando")
            continue

        idade = agora - datetime.fromisoformat(pedido["dta_pedido"])
        if idade > timedelta(minutes=PEDIDO_VALIDO_MIN):
            dl.fechar_comando_minecraft(
                id_pedido, "ignorado",
                f"Pedido de {int(idade.total_seconds() // 60)} min atrás: o PC não estava ligado para pegar. Peça de novo.",
                se_status="pendente",
            )
            continue

        # Pega o pedido; se outra execucao pegou antes, nao faz de novo.
        if not dl.fechar_comando_minecraft(id_pedido, "executando", se_status="pendente"):
            continue
        dl.log(f"[{NOME}] pedido {id_pedido}: {acao}")
        try:
            status, mensagem = executar_pedido(acao, online, linha)
        except Exception as e:  # noqa: BLE001 - o erro vai para o hub, no pedido
            dl.log_erro(f"[{NOME}] pedido {id_pedido} ({acao}) falhou: {e}")
            status, mensagem = "erro", f"Não consegui {acao}: {e}"[:300]
        dl.fechar_comando_minecraft(id_pedido, status, mensagem)


# ─── execucao ───────────────────────────────────────────────────────────────


def verificar() -> tuple[bool, dict]:
    try:
        return True, montar_linha(consultar_server())
    except OSError as e:
        # Porta fechada ou sem resposta: server desligado ou ainda subindo
        # (o NeoForge leva alguns minutos ate abrir a porta).
        return False, {"jogadores_online": 0, "jogadores": [], "latencia_ms": None,
                       "erro": f"{type(e).__name__}: {e}"[:300]}


def _limpar_logs_antigos() -> None:
    logs = sorted((BASE / "temp").glob(f"erro_*_{NOME}_*.txt"))
    for antigo in logs[:-MAX_LOGS_ERRO]:
        antigo.unlink(missing_ok=True)


def main() -> None:
    dl.configurar_logger(0, NOME, BASE)
    try:
        online, linha = verificar()
        resumo = (
            f"ONLINE {linha['jogadores_online']}/{linha.get('jogadores_max')}"
            f" {', '.join(linha['jogadores']) or '(ninguem)'} · {linha['latencia_ms']} ms"
            if online else f"OFFLINE ({linha['erro']})"
        )
        if DRY_RUN:
            eventos = coletar_eventos(None)
            print(resumo)
            print(json.dumps(linha, ensure_ascii=False, indent=2))
            print(f"{len(eventos)} evento(s) nos logs; os ultimos:")
            for e in eventos[-15:]:
                print(f"  {e['dta_evento'][:19]} {e['tipo']:<9} {e['jogador']}: {e['texto']}")
            print(f"server rodando (java): {server_rodando()}")
            print(f"pedidos abertos (nao executados no dry-run): {dl.comandos_minecraft_abertos()}")
            return
        dl.executar_com_retry(
            "gravar status no Supabase",
            lambda: dl.gravar_status_minecraft(online, **linha),
            2, 5,
        )
        processar_pedidos(online, linha)
        eventos = coletar_eventos(dl.ultimo_evento_minecraft())
        if eventos:
            dl.executar_com_retry(
                "gravar eventos no Supabase",
                lambda: dl.gravar_eventos_minecraft(eventos),
                2, 5,
            )
    except Exception as e:
        dl.log_erro(f"[{NOME}] {e}")
        dl.logar_traceback(NOME)
        dl.salvar_log_erro()
        _limpar_logs_antigos()
        raise


if __name__ == "__main__":
    main()
