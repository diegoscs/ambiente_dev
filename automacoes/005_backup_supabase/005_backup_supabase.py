# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 23/11/2026
# DESCRICAO      : Backup diario dos bancos Supabase: pg_dump pelo Session
#                  pooler, criptografado com age (so a chave PUBLICA fica na
#                  nuvem) e enviado ao Google Drive pelo rclone, com retencao
#                  de 30 dias. Regras em automacoes\PADRAO_ROBOS.md.
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

import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

import lib_dscs as dl

# ─── configuracao ────────────────────────────────────────────────────────────
# --dry-run    -> gera, criptografa e confere os dumps, mas nao envia ao Drive,
#                 nao apaga nada e nao registra status.
# --status     -> mostra configuracao e versoes das ferramentas e sai.
# --alvo NOME  -> so um banco (ex.: --alvo dm antes de uma etapa da migracao).
DEBUG = False
DRY_RUN = "--dry-run" in sys.argv
STATUS = "--status" in sys.argv

IDCARGA = 5  # ★ mesmo numero da pasta e do id_carga em public.controle_cargas
NOME_ROBO = "backup_supabase"

BASE = Path(__file__).resolve().parent

# Bancos copiados: rotulo (vai no nome do arquivo) -> secret com a string do
# Session pooler (porta 5432). Etapa 3 da migracao: entra "clientes". Depois
# da etapa 1 (OpenFinance pausado): sai "openfinance".
ALVOS = {
    "dm": "SUPABASE_DUMP_URL_DM",
    "openfinance": "SUPABASE_DUMP_URL_OPENFINANCE",
}

# Schemas que a Supabase cria e administra. Ficam fora do dump principal: nao
# sao nossos, e restaurar por cima de um projeto novo quebraria. Os dados de
# que precisamos deles (contas, jobs, historico de migrations) vao no dump
# "extras", so dados.
SCHEMAS_GERENCIADOS = (
    "auth", "storage", "realtime", "_realtime", "extensions", "graphql",
    "graphql_public", "pgbouncer", "vault", "pgsodium", "pgsodium_masks",
    "net", "cron", "supabase_functions", "supabase_migrations", "_analytics",
)

# So dados, nunca estrutura: num restore a Supabase ja traz essas tabelas.
# cron.job e schema_migrations nao existem em todo projeto; pg_dump so falha
# se NENHUMA tabela da lista existir.
TABELAS_EXTRAS = (
    "auth.users",
    "auth.identities",
    "cron.job",
    "supabase_migrations.schema_migrations",
)

REMOTO = "gdrive"                  # nome do remote no rclone config
PASTA_DRIVE = "Backups Supabase"   # criada pelo proprio rclone (escopo drive.file)
RETENCAO_DIAS = 30
# So arquivos com este formato entram na limpeza: nada mais da pasta e tocado.
FILTRO_RETENCAO = "{" + ",".join(ALVOS) + ",clientes}_*.tar.age"

TENTATIVAS = 3
SEGUNDOS_ENTRE_TENTATIVAS = 30
TIMEOUT_DUMP_S = 15 * 60

# Backups que chegaram ao Drive nesta execucao (vai para o qtd_itens).
ITENS_FEITOS = 0


# ─── ferramentas externas ────────────────────────────────────────────────────


def binario(nome: str) -> str:
    """Caminho de pg_dump/pg_restore (de BACKUP_PG_BIN, se houver), age ou rclone."""
    pasta_pg = dl.ler_env().get("BACKUP_PG_BIN")
    if pasta_pg and nome.startswith("pg_"):
        caminho = Path(pasta_pg) / (nome + (".exe" if os.name == "nt" else ""))
        if caminho.exists():
            return str(caminho)
        raise FileNotFoundError(f"{nome} nao encontrado em BACKUP_PG_BIN ({pasta_pg})")
    achado = shutil.which(nome)
    if not achado:
        raise FileNotFoundError(f"{nome} nao encontrado no PATH")
    return achado


def rodar(cmd: list[str], env: dict[str, str] | None = None, timeout: int = 600) -> str:
    """Roda um comando e devolve o stdout. No erro, levanta com o fim do stderr.

    Segredos nunca vao em `cmd` (que aparece no erro): senha do banco vai por
    variavel PG*, e a config do rclone por arquivo temporario.
    """
    r = subprocess.run(cmd, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode != 0:
        fim = " | ".join((r.stderr or r.stdout or "").strip().splitlines()[-3:])
        raise RuntimeError(f"{Path(cmd[0]).stem} saiu com codigo {r.returncode}: {fim}")
    return r.stdout


def versao(nome: str) -> str:
    try:
        saida = rodar([binario(nome), "version" if nome == "rclone" else "--version"], timeout=30)
        return saida.strip().splitlines()[0]
    except Exception as e:  # noqa: BLE001 - so informativo no --status
        return f"AUSENTE ({e})"


# ─── configuracao e validacao ────────────────────────────────────────────────


def alvos_da_execucao() -> dict[str, str]:
    if "--alvo" not in sys.argv:
        return dict(ALVOS)
    i = sys.argv.index("--alvo")
    nome = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    if nome not in ALVOS:
        raise ValueError(f"--alvo invalido: {nome!r}. Opcoes: {', '.join(ALVOS)}")
    return {nome: ALVOS[nome]}


def env_postgres(url: str) -> dict[str, str]:
    """Variaveis PG* a partir da string de conexao (a senha nunca vai na linha de comando)."""
    partes = urlsplit(url)
    if partes.scheme not in ("postgres", "postgresql"):
        raise ValueError("string de conexao precisa comecar com postgresql://")
    if (partes.port or 5432) != 5432:
        raise ValueError(
            f"porta {partes.port}: use o Session pooler (porta 5432). O Transaction "
            f"pooler (6543) nao serve para pg_dump."
        )
    if not (partes.username and partes.password and partes.hostname):
        raise ValueError("string de conexao sem usuario, senha ou host")
    env = os.environ.copy()
    env.update({
        "PGHOST": partes.hostname,
        "PGPORT": "5432",
        "PGUSER": unquote(partes.username),
        "PGPASSWORD": unquote(partes.password),
        "PGDATABASE": partes.path.lstrip("/") or "postgres",
        "PGSSLMODE": "require",
        "PGCONNECT_TIMEOUT": "30",
        "PGAPPNAME": f"robo_{IDCARGA:03d}_{NOME_ROBO}",
    })
    return env


def validar_configuracao(alvos: dict[str, str]) -> None:
    """Tudo que pode faltar, conferido antes de qualquer rede."""
    env = dl.ler_env()
    faltando = [c for c in ("SUPABASE_URL", "SUPABASE_KEY", "BACKUP_AGE_RECIPIENT", *alvos.values())
                if not env.get(c)]
    if faltando:
        raise ValueError(f"Faltam variaveis no ambiente/.env: {', '.join(faltando)}")

    if not env["BACKUP_AGE_RECIPIENT"].strip().startswith("age1"):
        raise ValueError("BACKUP_AGE_RECIPIENT precisa ser a chave PUBLICA do age (age1...)")

    for secret in alvos.values():
        try:
            env_postgres(env[secret])
        except ValueError as e:
            raise ValueError(f"{secret}: {e}") from None

    for nome in ("pg_dump", "pg_restore", "age") + (() if DRY_RUN else ("rclone",)):
        binario(nome)  # levanta se faltar


# ─── rclone ──────────────────────────────────────────────────────────────────


def args_rclone(pasta_tmp: Path) -> list[str]:
    """Config do rclone: BACKUP_RCLONE_CONF (Actions) num arquivo temporario,
    ou a config padrao do PC (rclone config)."""
    conteudo = dl.ler_env().get("BACKUP_RCLONE_CONF")
    if not conteudo:
        return []
    arquivo = pasta_tmp / "rclone.conf"
    arquivo.write_text(conteudo.replace("\r\n", "\n").strip() + "\n", encoding="utf-8")
    arquivo.chmod(0o600)
    return ["--config", str(arquivo)]


def destino(nome_arquivo: str = "") -> str:
    return f"{REMOTO}:{PASTA_DRIVE}" + (f"/{nome_arquivo}" if nome_arquivo else "")


def antigos_no_drive(conf: list[str]) -> list[str]:
    saida = rodar([binario("rclone"), *conf, "lsf", destino(), "--files-only",
                   "--min-age", f"{RETENCAO_DIAS}d", "--include", FILTRO_RETENCAO], timeout=120)
    return [linha for linha in saida.splitlines() if linha.strip()]


# ─── backup de um banco ──────────────────────────────────────────────────────


def gerar_dumps(rotulo: str, url: str, pasta: Path) -> None:
    """Dois dumps em formato custom: o principal (estrutura + dados dos nossos
    schemas) e o "extras" (so dados de contas, jobs e historico de migrations)."""
    env = env_postgres(url)
    pg_dump = binario("pg_dump")

    principal = [pg_dump, "--format=custom", "--file", str(pasta / "principal.dump")]
    for schema in SCHEMAS_GERENCIADOS:
        principal += ["--exclude-schema", schema]

    extras = [pg_dump, "--format=custom", "--data-only", "--file", str(pasta / "extras.dump")]
    for tabela in TABELAS_EXTRAS:
        extras += ["--table", tabela]

    for nome, cmd in (("principal", principal), ("extras", extras)):
        dl.executar_com_retry(
            f"pg_dump {rotulo} ({nome})",
            lambda cmd=cmd: rodar(cmd, env=env, timeout=TIMEOUT_DUMP_S),
            TENTATIVAS, SEGUNDOS_ENTRE_TENTATIVAS,
        )

    # Confere que os arquivos abrem: dump truncado nao chega ao Drive.
    for nome in ("principal", "extras"):
        indice = rodar([binario("pg_restore"), "--list", str(pasta / f"{nome}.dump")])
        itens = sum(1 for linha in indice.splitlines() if linha and not linha.startswith(";"))
        if itens == 0:
            raise RuntimeError(f"{rotulo}: {nome}.dump sem nenhum objeto")


def empacotar_e_cifrar(rotulo: str, pasta: Path, carimbo: str) -> Path:
    """tar dos dois dumps -> age com a chave publica. Devolve o .tar.age."""
    tar = pasta.parent / f"{rotulo}_{carimbo}.tar"
    with tarfile.open(tar, "w") as t:
        for nome in ("principal.dump", "extras.dump"):
            t.add(pasta / nome, arcname=f"{rotulo}_{carimbo}/{nome}")
    cifrado = tar.with_name(tar.name + ".age")
    recipient = dl.obter_variavel("BACKUP_AGE_RECIPIENT").strip()
    rodar([binario("age"), "--encrypt", "--recipient", recipient, "--output", str(cifrado), str(tar)])
    tar.unlink()           # o .tar em claro nao fica nem no disco temporario
    shutil.rmtree(pasta)   # nem os dumps
    return cifrado


def mb(caminho: Path) -> str:
    return f"{caminho.stat().st_size / 1e6:.1f} MB".replace(".", ",")


# ─── carga ───────────────────────────────────────────────────────────────────


def processar(alvos: dict[str, str]) -> tuple[int, str]:
    """A carga. Devolve (qtd_itens, resumo) para o registro no Supabase."""
    global ITENS_FEITOS

    carimbo = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MZ")
    env = dl.ler_env()
    feitos: list[str] = []

    with tempfile.TemporaryDirectory(prefix="robo005_") as tmp:
        tmp_path = Path(tmp)
        conf = [] if DRY_RUN else args_rclone(tmp_path)

        for rotulo, secret in alvos.items():
            pasta = tmp_path / rotulo
            pasta.mkdir()
            gerar_dumps(rotulo, env[secret], pasta)
            arquivo = empacotar_e_cifrar(rotulo, pasta, carimbo)

            if DEBUG or DRY_RUN:
                dl.log(f"[DRY RUN] {arquivo.name} ({mb(arquivo)}) pronto; nao enviado")
                feitos.append(f"{rotulo} {mb(arquivo)}")
                continue

            dl.executar_com_retry(
                f"envio {arquivo.name}",
                lambda arquivo=arquivo: rodar(
                    [binario("rclone"), *conf, "copyto", str(arquivo), destino(arquivo.name)],
                    timeout=600,
                ),
                TENTATIVAS, SEGUNDOS_ENTRE_TENTATIVAS,
            )
            ITENS_FEITOS += 1
            feitos.append(f"{rotulo} {mb(arquivo)}")
            dl.log(f"[DRIVE] {arquivo.name} enviado ({mb(arquivo)})")

        if DEBUG or DRY_RUN:
            return 0, f"dry-run: {len(feitos)} backup(s) gerado(s) e conferido(s) ({' · '.join(feitos)})"

        # Limpeza so depois de TODOS os envios do dia: com erro no meio, a
        # excecao ja saiu antes daqui e nada antigo e apagado.
        velhos = antigos_no_drive(conf)
        if velhos:
            rodar([binario("rclone"), *conf, "delete", destino(), "--min-age",
                   f"{RETENCAO_DIAS}d", "--include", FILTRO_RETENCAO], timeout=300)
            dl.log(f"[DRIVE] {len(velhos)} backup(s) com mais de {RETENCAO_DIAS} dias na lixeira")

    resumo = f"{ITENS_FEITOS} backup(s) no Drive: {' · '.join(feitos)}"
    if velhos:
        resumo += f" · {len(velhos)} antigo(s) apagado(s)"
    return ITENS_FEITOS, resumo


def mostrar_status(alvos: dict[str, str]) -> None:
    env = dl.ler_env()
    print(f"Robo {IDCARGA:03d} - {NOME_ROBO}")
    for rotulo, secret in alvos.items():
        print(f"  alvo {rotulo:<12} {secret}: {'configurado' if env.get(secret) else 'AUSENTE'}")
    print(f"  chave age (publica): {'configurada' if env.get('BACKUP_AGE_RECIPIENT') else 'AUSENTE'}")
    print(f"  rclone: {'BACKUP_RCLONE_CONF' if env.get('BACKUP_RCLONE_CONF') else 'config padrao do PC'}"
          f" -> {destino()} (retencao {RETENCAO_DIAS} dias)")
    for nome in ("pg_dump", "pg_restore", "age", "rclone"):
        print(f"  {nome:<11} {versao(nome)}")


def main() -> None:
    dl.configurar_logger(IDCARGA, NOME_ROBO, BASE)

    modo = dl.modo_execucao()
    dta_ini = datetime.now(timezone.utc)
    alvos = alvos_da_execucao()

    dl.logar_contexto(
        "DRY-RUN" if (DEBUG or DRY_RUN) else modo,
        extras={
            "Modo de execucao": modo,
            "Supabase": "configurado" if dl.supabase_configurado() else "AUSENTE",
            "Bancos": ", ".join(alvos),
            "Destino": destino(),
            "DEBUG / DRY_RUN": f"{DEBUG} / {DRY_RUN}",
        },
    )

    if STATUS:
        mostrar_status(alvos)
        return

    registrar = not (DEBUG or DRY_RUN)

    try:
        validar_configuracao(alvos)

        if registrar:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, dta_ini, fechar=False)

        qtd, resumo = processar(alvos)

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
            dl.registrar_carga_supabase(
                IDCARGA, dl.STATUS_ERRO, dta_ini, fechar=True,
                mensagem=str(e)[:500], qtd_itens=ITENS_FEITOS,
            )
            dl.alertar_erro_robo(IDCARGA, NOME_ROBO, str(e))

        dl.log(f"[ROBO{IDCARGA:03d}] ❌ RESULTADO FINAL: ERRO")
        dl.log("=" * 70)

        arquivo = dl.salvar_log_erro()
        if arquivo:
            print(f"Log do erro: {arquivo}", file=sys.stderr)

        raise


if __name__ == "__main__":
    main()
