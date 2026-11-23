# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 23/11/2026
# DESCRICAO      : Backup dos bancos Supabase so com Python (sem pg_dump):
#                  estrutura em SQL + dados em CSV num zip, criptografado com
#                  age (so a chave PUBLICA fica no PC/nuvem). Destino: uma pasta
#                  local (--pasta) ou o Google Drive (rclone, etapa futura).
#                  Regras em automacoes\PADRAO_ROBOS.md.
# =============================================
from __future__ import annotations

import os
import sys
from pathlib import Path

# --- bootstrap padrao: encoding + caminho da lib (nesta ordem, antes dos imports)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone

import psycopg

import lib_dscs as dl
from exportar import conferir_zip, exportar_banco

# ─── configuracao ────────────────────────────────────────────────────────────
# --pasta DIR   -> backup manual: grava <banco>_<data>.zip.age em DIR (fora do
#                  repositorio). Nao registra status nem apaga nada antigo.
# (sem --pasta) -> carga diaria: envia ao Google Drive pelo rclone e registra.
# --dry-run     -> gera e confere em pasta temporaria; nao grava, nao envia e
#                  nao registra. Sem chave age, testa sem criptografar.
# --alvo NOME   -> so um banco.
# --sem-cripto  -> so com --pasta: grava o .zip sem age (quando a chave nao
#                  esta a mao). Rodar de novo com a chave e apagar o .zip depois.
# --status      -> mostra a configuracao e sai.
# --conferir ARQ --chave ARQ_CHAVE -> abre um .zip.age com a chave privada e
#                  confere cada CSV contra o manifesto. Nao usa banco.
DEBUG = False
DRY_RUN = "--dry-run" in sys.argv
STATUS = "--status" in sys.argv
SEM_CRIPTO = "--sem-cripto" in sys.argv


def _valor_do_argumento(nome: str) -> str | None:
    if nome not in sys.argv:
        return None
    i = sys.argv.index(nome)
    if i + 1 >= len(sys.argv) or sys.argv[i + 1].startswith("--"):
        raise ValueError(f"{nome} precisa de um valor")
    return sys.argv[i + 1]


PASTA_LOCAL = _valor_do_argumento("--pasta")
CONFERIR = _valor_do_argumento("--conferir")

IDCARGA = 5  # ★ mesmo numero da pasta e do id_carga em public.controle_cargas
NOME_ROBO = "backup_supabase"

BASE = Path(__file__).resolve().parent

# Bancos: rotulo (vai no nome do arquivo) -> variaveis com a string de conexao,
# na ordem de preferencia. Qualquer pooler serve (a exportacao roda numa
# transacao so). Etapa 3: entra "clientes". OpenFinance pausado: sai.
ALVOS = {
    "dm": ("SUPABASE_DUMP_URL_DM", "SUPABASE_DB_URL"),
    "openfinance": ("SUPABASE_DUMP_URL_OPENFINANCE",),
}

REMOTO = "gdrive"
PASTA_DRIVE = "Backups Supabase"
RETENCAO_DIAS = 30
# So arquivos neste formato entram na limpeza do Drive.
FILTRO_RETENCAO = "{dm,openfinance,clientes}_*.zip.age"

TENTATIVAS = 3
SEGUNDOS_ENTRE_TENTATIVAS = 30

# Backups que chegaram ao destino nesta execucao (vai para o qtd_itens).
ITENS_FEITOS = 0


# ─── auxiliares ──────────────────────────────────────────────────────────────


def binario(nome: str) -> str:
    achado = shutil.which(nome)
    if not achado:
        raise FileNotFoundError(f"{nome} nao encontrado no PATH")
    return achado


def rodar(cmd: list[str], timeout: int = 600) -> str:
    """Roda age/rclone. Segredo nunca vai em `cmd` (que aparece no erro)."""
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    if r.returncode != 0:
        fim = " | ".join((r.stderr or r.stdout or "").strip().splitlines()[-3:])
        raise RuntimeError(f"{Path(cmd[0]).stem} saiu com codigo {r.returncode}: {fim}")
    return r.stdout


def mb(caminho: Path) -> str:
    return f"{caminho.stat().st_size / 1e6:.1f} MB".replace(".", ",")


def url_do_alvo(rotulo: str) -> str | None:
    env = dl.ler_env()
    return next((env[v] for v in ALVOS[rotulo] if env.get(v)), None)


def chave_publica() -> str | None:
    valor = (dl.ler_env().get("BACKUP_AGE_RECIPIENT") or "").strip()
    return valor or None


def alvos_da_execucao() -> list[str]:
    nome = _valor_do_argumento("--alvo")
    if nome is None:
        return list(ALVOS)
    if nome not in ALVOS:
        raise ValueError(f"--alvo invalido: {nome!r}. Opcoes: {', '.join(ALVOS)}")
    return [nome]


def validar_configuracao(alvos: list[str]) -> None:
    """Tudo que pode faltar, conferido antes de qualquer rede."""
    faltando = [" ou ".join(ALVOS[r]) for r in alvos if not url_do_alvo(r)]
    if not (DRY_RUN or PASTA_LOCAL):
        faltando += [c for c in ("SUPABASE_URL", "SUPABASE_KEY") if not dl.ler_env().get(c)]
    if SEM_CRIPTO and not PASTA_LOCAL:
        raise ValueError("--sem-cripto so vale junto com --pasta (nada sai do PC sem criptografia)")
    if not chave_publica() and not (DRY_RUN or SEM_CRIPTO):
        faltando.append("BACKUP_AGE_RECIPIENT")
    if faltando:
        raise ValueError(f"Faltam variaveis no ambiente/.env: {', '.join(faltando)}")

    if chave_publica() and not chave_publica().startswith("age1"):
        raise ValueError("BACKUP_AGE_RECIPIENT precisa ser a chave PUBLICA do age (age1...)")

    if PASTA_LOCAL:
        pasta = Path(PASTA_LOCAL).resolve()
        if pasta == dl.RAIZ or dl.RAIZ in pasta.parents:
            raise ValueError(f"--pasta {pasta} fica dentro do repositorio: escolha uma pasta fora dele")

    if chave_publica():
        binario("age")
    if not (DRY_RUN or PASTA_LOCAL):
        binario("rclone")


# ─── destino Drive (rclone) ──────────────────────────────────────────────────


def args_rclone(pasta_tmp: Path) -> list[str]:
    """BACKUP_RCLONE_CONF (Actions) num arquivo temporario, ou a config do PC."""
    conteudo = dl.ler_env().get("BACKUP_RCLONE_CONF")
    if not conteudo:
        return []
    arquivo = pasta_tmp / "rclone.conf"
    arquivo.write_text(conteudo.replace("\r\n", "\n").strip() + "\n", encoding="utf-8")
    arquivo.chmod(0o600)
    return ["--config", str(arquivo)]


def destino_drive(nome_arquivo: str = "") -> str:
    return f"{REMOTO}:{PASTA_DRIVE}" + (f"/{nome_arquivo}" if nome_arquivo else "")


def limpar_drive(conf: list[str]) -> int:
    filtro = ["--min-age", f"{RETENCAO_DIAS}d", "--include", FILTRO_RETENCAO]
    velhos = [l for l in rodar([binario("rclone"), *conf, "lsf", destino_drive(), "--files-only", *filtro],
                               timeout=120).splitlines() if l.strip()]
    if velhos:
        rodar([binario("rclone"), *conf, "delete", destino_drive(), *filtro], timeout=300)
    return len(velhos)


# ─── carga ───────────────────────────────────────────────────────────────────


def gerar_backup(rotulo: str, pasta_tmp: Path, carimbo: str) -> tuple[Path, str]:
    """Exporta, confere e (com chave) criptografa. Devolve (arquivo, resumo)."""
    arquivo_zip = pasta_tmp / f"{rotulo}_{carimbo}.zip"
    # Retry so em falha de conexao: erro de SQL ou permissao estoura na primeira.
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            manifesto = exportar_banco(url_do_alvo(rotulo), rotulo, arquivo_zip,
                                       f"robo_{IDCARGA:03d}_{NOME_ROBO}")
            break
        except psycopg.OperationalError as e:
            if tentativa == TENTATIVAS:
                raise
            dl.log(f"[EXPORT] {rotulo}: conexao falhou ({e}); nova tentativa em {SEGUNDOS_ENTRE_TENTATIVAS}s")
            time.sleep(SEGUNDOS_ENTRE_TENTATIVAS)
    tabelas, linhas = conferir_zip(arquivo_zip)  # o zip abre e bate com o banco
    resumo = f"{rotulo}: {tabelas} tabelas, {linhas} linhas"
    dl.log(f"[EXPORT] {resumo} (Postgres {manifesto['servidor']})")

    recipient = chave_publica()
    if SEM_CRIPTO or not recipient:  # --sem-cripto, ou dry-run sem chave
        return arquivo_zip, resumo + " (SEM criptografia)"
    cifrado = arquivo_zip.with_name(arquivo_zip.name + ".age")
    rodar([binario("age"), "--encrypt", "--recipient", recipient, "--output", str(cifrado), str(arquivo_zip)])
    arquivo_zip.unlink()  # o zip em claro nao fica nem no disco temporario
    return cifrado, resumo


def processar(alvos: list[str]) -> tuple[int, str]:
    """A carga. Devolve (qtd_itens, resumo) para o registro no Supabase."""
    global ITENS_FEITOS
    carimbo = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MZ")
    feitos: list[str] = []

    with tempfile.TemporaryDirectory(prefix="robo005_") as tmp:
        tmp_path = Path(tmp)
        usa_drive = not (DEBUG or DRY_RUN or PASTA_LOCAL)
        conf = args_rclone(tmp_path) if usa_drive else []

        for rotulo in alvos:
            arquivo, resumo = gerar_backup(rotulo, tmp_path, carimbo)
            tamanho = mb(arquivo)

            if DEBUG or DRY_RUN:
                feitos.append(f"{resumo}, {tamanho}")
                continue

            if PASTA_LOCAL:
                pasta = Path(PASTA_LOCAL)
                pasta.mkdir(parents=True, exist_ok=True)
                shutil.move(str(arquivo), pasta / arquivo.name)
                dl.log(f"[PASTA] {pasta.resolve() / arquivo.name} ({tamanho})")
            else:
                dl.executar_com_retry(
                    f"envio {arquivo.name}",
                    lambda arquivo=arquivo: rodar([binario("rclone"), *conf, "copyto", str(arquivo),
                                                   destino_drive(arquivo.name)]),
                    TENTATIVAS, SEGUNDOS_ENTRE_TENTATIVAS,
                )
                dl.log(f"[DRIVE] {arquivo.name} enviado ({tamanho})")
            ITENS_FEITOS += 1
            feitos.append(f"{resumo}, {tamanho}")

        if DEBUG or DRY_RUN:
            return 0, "dry-run: " + " · ".join(feitos)
        if PASTA_LOCAL:
            return ITENS_FEITOS, f"{ITENS_FEITOS} backup(s) em {Path(PASTA_LOCAL).resolve()}: " + " · ".join(feitos)

        # Limpeza so depois de TODOS os envios: com erro no meio, nada antigo sai.
        apagados = limpar_drive(conf)

    resumo = f"{ITENS_FEITOS} backup(s) no Drive: " + " · ".join(feitos)
    return ITENS_FEITOS, resumo + (f" · {apagados} antigo(s) apagado(s)" if apagados else "")


def conferir_arquivo(arquivo: str) -> None:
    """--conferir: decifra com a chave privada numa pasta temporaria e confere."""
    chave = _valor_do_argumento("--chave")
    if not chave:
        raise ValueError("--conferir precisa de --chave <arquivo com a chave privada do age>")
    with tempfile.TemporaryDirectory(prefix="robo005_conf_") as tmp:
        aberto = Path(tmp) / "backup.zip"
        rodar([binario("age"), "--decrypt", "--identity", chave, "--output", str(aberto), arquivo])
        tabelas, linhas = conferir_zip(aberto)
    print(f"OK: {Path(arquivo).name} abre e confere: {tabelas} tabelas, {linhas} linhas")


def mostrar_status(alvos: list[str]) -> None:
    print(f"Robo {IDCARGA:03d} - {NOME_ROBO}")
    for rotulo in alvos:
        print(f"  {rotulo:<12} {' ou '.join(ALVOS[rotulo])}: {'configurado' if url_do_alvo(rotulo) else 'AUSENTE'}")
    print(f"  chave age (publica): {'configurada' if chave_publica() else 'AUSENTE'}")
    for nome in ("age", "rclone"):
        print(f"  {nome:<7} {'ok' if shutil.which(nome) else 'AUSENTE'}")


def main() -> None:
    if CONFERIR:
        conferir_arquivo(CONFERIR)
        return

    dl.configurar_logger(IDCARGA, NOME_ROBO, BASE)
    modo = dl.modo_execucao()
    dta_ini = datetime.now(timezone.utc)
    alvos = alvos_da_execucao()

    dl.logar_contexto(
        "DRY-RUN" if (DEBUG or DRY_RUN) else modo,
        extras={
            "Modo de execucao": modo,
            "Bancos": ", ".join(alvos),
            "Destino": str(Path(PASTA_LOCAL).resolve()) if PASTA_LOCAL else destino_drive(),
            "DEBUG / DRY_RUN": f"{DEBUG} / {DRY_RUN}",
        },
    )

    if STATUS:
        mostrar_status(alvos)
        return

    # Backup manual em pasta local nao e a carga diaria: nao registra no hub.
    registrar = not (DEBUG or DRY_RUN or PASTA_LOCAL)

    try:
        validar_configuracao(alvos)

        if registrar:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, dta_ini, fechar=False)

        qtd, resumo = processar(alvos)

        if registrar:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_SUCESSO, dta_ini, fechar=True,
                                        mensagem=resumo, qtd_itens=qtd)

        dl.log(f"[ROBO{IDCARGA:03d}] ✅ RESULTADO FINAL: SUCESSO - {resumo}")
        dl.log("=" * 70)

    except Exception as e:
        dl.log(f"[ROBO{IDCARGA:03d}] ❌ erro final: {e}")
        dl.logar_traceback("erro final")

        if registrar:
            dl.registrar_carga_supabase(IDCARGA, dl.STATUS_ERRO, dta_ini, fechar=True,
                                        mensagem=str(e)[:500], qtd_itens=ITENS_FEITOS)
            dl.alertar_erro_robo(IDCARGA, NOME_ROBO, str(e))

        dl.log(f"[ROBO{IDCARGA:03d}] ❌ RESULTADO FINAL: ERRO")
        dl.log("=" * 70)

        arquivo = dl.salvar_log_erro()
        if arquivo:
            print(f"Log do erro: {arquivo}", file=sys.stderr)

        raise


if __name__ == "__main__":
    main()
