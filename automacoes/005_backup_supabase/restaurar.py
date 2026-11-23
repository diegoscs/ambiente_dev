# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 23/11/2026
# DESCRICAO      : Restore de um backup do robo 005 (zip gerado pelo
#                  exportar.py) num banco Postgres: estrutura comando a comando,
#                  dados por COPY e conferencia de linhas e objetos contra o
#                  manifesto. Por padrao tudo e desfeito no fim (teste); com
#                  confirmar=True fica gravado.
# =============================================
from __future__ import annotations

import json
import zipfile

import psycopg
import psycopg.sql

from exportar import TABELAS_EXTRAS, conectar, contar_objetos

SQL_COLUNAS_DESTINO = """
select a.attname, format_type(a.atttypid, a.atttypmod)
  from pg_attribute a
 where a.attrelid = to_regclass(%s) and a.attnum > 0 and not a.attisdropped and a.attgenerated = ''
 order by a.attnum
"""


def _resumo_erro(e: Exception) -> str:
    return str(e).strip().splitlines()[0][:200]


def _carregar_tabela(conn: psycopg.Connection, zf: zipfile.ZipFile, t: dict, avisos: list[str]) -> bool:
    """COPY de um CSV. Tabelas extras (auth, cron...) aceitam destino com menos
    colunas (versao diferente da Supabase): as que faltam sao avisadas e puladas.
    Devolve False se a tabela foi pulada."""
    schema, tabela = t["tabela"].split(".", 1)
    extra = (schema, tabela) in TABELAS_EXTRAS
    nome_txt = psycopg.sql.Identifier(schema, tabela).as_string(conn)
    destino = dict(conn.execute(SQL_COLUNAS_DESTINO, (nome_txt,)).fetchall())

    if not destino:
        if extra:
            avisos.append(f"{t['tabela']}: nao existe no destino, pulada")
            return False
        raise RuntimeError(f"{t['tabela']}: tabela nao foi criada pela estrutura")

    faltam = [c for c in t["colunas"] if c not in destino]
    if faltam and not extra:
        raise RuntimeError(f"{t['tabela']}: colunas ausentes no destino: {', '.join(faltam)}")

    nome = psycopg.sql.Identifier(schema, tabela)
    dados = zf.read(t["arquivo"])

    if not faltam:
        colunas = psycopg.sql.SQL(", ").join(psycopg.sql.Identifier(c) for c in t["colunas"])
        with conn.cursor() as cur, cur.copy(psycopg.sql.SQL(
                "COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')").format(nome, colunas)) as cp:
            cp.write(dados)
        return True

    # Destino com menos colunas: CSV numa tabela temporaria (tudo texto) e
    # insert so das colunas em comum, convertidas para o tipo do destino.
    comuns = [c for c in t["colunas"] if c in destino]
    temp = psycopg.sql.Identifier("_restore_tmp")
    defs = psycopg.sql.SQL(", ").join(psycopg.sql.SQL("{} text").format(psycopg.sql.Identifier(c))
                                      for c in t["colunas"])
    conn.execute(psycopg.sql.SQL("CREATE TEMP TABLE {} ({})").format(temp, defs))
    todas = psycopg.sql.SQL(", ").join(psycopg.sql.Identifier(c) for c in t["colunas"])
    with conn.cursor() as cur, cur.copy(psycopg.sql.SQL(
            "COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')").format(temp, todas)) as cp:
        cp.write(dados)
    alvo = psycopg.sql.SQL(", ").join(psycopg.sql.Identifier(c) for c in comuns)
    origem = psycopg.sql.SQL(", ").join(
        psycopg.sql.SQL("{}::{}").format(psycopg.sql.Identifier(c), psycopg.sql.SQL(destino[c])) for c in comuns)
    conn.execute(psycopg.sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(nome, alvo, origem, temp))
    conn.execute(psycopg.sql.SQL("DROP TABLE {}").format(temp))
    avisos.append(f"{t['tabela']}: colunas que nao existem no destino ficaram de fora: {', '.join(faltam)}")
    return True


def restaurar_zip(caminho_zip, url: str, nome_app: str, confirmar: bool = False) -> dict:
    """Restaura o zip no banco de `url` e confere. Tudo numa transacao: sem
    `confirmar`, ela e desfeita no fim (teste de restore). Devolve o relatorio
    {tabelas, linhas, erros, avisos}; quem chama decide o que fazer com erros."""
    erros: list[str] = []
    avisos: list[str] = []
    tabelas_ok = 0
    linhas_ok = 0

    with zipfile.ZipFile(caminho_zip) as zf:
        manifesto = json.loads(zf.read("manifesto.json"))
        estrutura = json.loads(zf.read("estrutura.json"))

        with conectar(url, nome_app, leitura=False) as conn:
            with conn.transaction() as tx:

                def executar(comando: str, etapa: str) -> None:
                    # Savepoint por comando: um erro nao derruba os seguintes,
                    # e o relatorio mostra todos de uma vez.
                    try:
                        with conn.transaction():
                            conn.execute(comando)
                    except psycopg.Error as e:
                        erros.append(f"{etapa}: {_resumo_erro(e)} | {' '.join(comando.split())[:150]}")

                for comando in estrutura["antes"]:
                    executar(comando, "estrutura 1")

                carregadas = []
                for t in manifesto["tabelas"]:
                    try:
                        with conn.transaction():
                            if _carregar_tabela(conn, zf, t, avisos):
                                carregadas.append(t)
                    except (psycopg.Error, RuntimeError) as e:
                        erros.append(f"dados {t['tabela']}: {_resumo_erro(e)}")

                for comando in estrutura["depois"]:
                    executar(comando, "estrutura 2")

                # Conferencia: linhas por tabela e objetos por tipo.
                for t in carregadas:
                    nome = psycopg.sql.Identifier(*t["tabela"].split(".", 1))
                    n = conn.execute(psycopg.sql.SQL("select count(*) from {}").format(nome)).fetchone()[0]
                    if n != t["linhas"]:
                        erros.append(f"conferencia {t['tabela']}: {n} linhas restauradas, {t['linhas']} no backup")
                    else:
                        tabelas_ok += 1
                        linhas_ok += n

                if "objetos" in manifesto:
                    agora = contar_objetos(conn, manifesto["schemas"])
                    for tipo, esperado in manifesto["objetos"].items():
                        if agora.get(tipo) != esperado:
                            erros.append(f"conferencia objetos: {tipo} = {agora.get(tipo)}, backup tem {esperado}")

                if not confirmar:
                    raise psycopg.Rollback(tx)

    return {"tabelas": tabelas_ok, "linhas": linhas_ok, "erros": erros, "avisos": avisos,
            "objetos": manifesto.get("objetos", {})}
