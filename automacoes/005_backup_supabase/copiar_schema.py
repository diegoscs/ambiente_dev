# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 24/11/2026
# DESCRICAO      : Copia UM schema de um projeto Supabase para outro (migracao
#                  DM + Clientes): estrutura gerada do catalogo (o mesmo gerador
#                  do backup), dados por COPY direto entre os bancos e, se
#                  pedido, as contas do Auth que o schema usa (mesmos IDs) ou a
#                  troca de uma conta por outra. Tudo numa transacao no destino:
#                  sem --confirmar, e desfeita no fim (ensaio).
#
# Uso (as conexoes vem de variaveis do .env, nunca da linha de comando):
#   python copiar_schema.py --origem VAR --destino VAR --schema NOME
#          [--trocar-usuario ID_ORIGEM=ID_DESTINO] [--copiar-contas]
#          [--substituir] [--confirmar]
#
#   --trocar-usuario  todo uuid do schema igual a ID_ORIGEM vira ID_DESTINO
#                     (conta com o mesmo e-mail e outro ID no destino)
#   --copiar-contas   copia auth.users e auth.identities das contas que o schema
#                     referencia, com os mesmos IDs (destino sem essas contas)
#   --substituir      apaga o schema do destino, se existir, na mesma transacao
#   --confirmar       grava; sem ele, so ensaia e desfaz
#
# Fica de fora: Storage, Vault, Edge Functions, configuracao do painel (Data
# API, Auth, SMTP) e dono dos objetos.
# =============================================
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import argparse
import uuid

import psycopg
import psycopg.sql as S

import lib_dscs as dl
from exportar import contar_objetos, conectar, estrutura_em_lista, gerar_estrutura

NOME_APP = "copiar_schema"

SQL_TABELAS = """
select c.relname,
       array_agg(a.attname order by a.attnum) filter (where a.attnum > 0 and not a.attisdropped
                                                       and a.attgenerated = '')
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  join pg_attribute a on a.attrelid = c.oid
 where n.nspname = %s and c.relkind in ('r', 'p')
 group by c.relname order by c.relname
"""

# Colunas que apontam para auth.users (FK): as contas que o schema usa.
SQL_COLUNAS_CONTA = """
select c.relname, a.attname
  from pg_constraint k
  join pg_class c on c.oid = k.conrelid
  join pg_namespace n on n.oid = c.relnamespace
  join pg_attribute a on a.attrelid = c.oid and a.attnum = k.conkey[1]
 where n.nspname = %s and k.contype = 'f' and k.confrelid = 'auth.users'::regclass
"""

SQL_COLUNAS_UUID = """
select c.relname, a.attname
  from pg_attribute a join pg_class c on c.oid = a.attrelid join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = %s and c.relkind in ('r', 'p') and a.attnum > 0 and not a.attisdropped
   and a.atttypid = 'uuid'::regtype
"""

SQL_COLUNAS_DESTINO = """
select a.attname from pg_attribute a
 where a.attrelid = to_regclass(%s) and a.attnum > 0 and not a.attisdropped and a.attgenerated = ''
"""


def _ler(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _copiar(origem, destino, nome: S.Composable, colunas: list[str], filtro: S.Composable | None = None) -> None:
    """COPY da origem direto para o destino, sem arquivo no meio."""
    lista = S.SQL(", ").join(S.Identifier(c) for c in colunas)
    consulta = (S.SQL("(SELECT {} FROM {} WHERE {})").format(lista, nome, filtro) if filtro
                else S.SQL("{} ({})").format(nome, lista))
    with origem.cursor() as co, destino.cursor() as cd:
        with co.copy(S.SQL("COPY {} TO STDOUT (FORMAT binary)").format(consulta)) as saida, \
             cd.copy(S.SQL("COPY {} ({}) FROM STDIN (FORMAT binary)").format(nome, lista)) as entrada:
            for bloco in saida:
                entrada.write(bloco)


def _contas_usadas(origem, schema: str) -> list[str]:
    ids: set[str] = set()
    for tabela, coluna in _ler(origem, SQL_COLUNAS_CONTA, (schema,)):
        q = S.SQL("select distinct {c} from {t} where {c} is not null").format(
            c=S.Identifier(coluna), t=S.Identifier(schema, tabela))
        ids |= {str(r[0]) for r in _ler(origem, q)}
    return sorted(ids)


def _copiar_contas(origem, destino, ids: list[str], log: list[str]) -> None:
    """auth.users e auth.identities com os mesmos IDs, so as colunas que existem
    nos dois lados. Conta que ja existe no destino com o mesmo ID e pulada;
    mesmo e-mail com outro ID estoura (unique do Auth)."""
    ja = {str(r[0]) for r in _ler(destino, "select id from auth.users where id = any(%s::uuid[])", (ids,))}
    novas = [i for i in ids if i not in ja]
    if ja:
        log.append(f"contas que ja existiam no destino: {len(ja)}")
    if not novas:
        return
    for tabela, chave in (("users", "id"), ("identities", "user_id")):
        nome = S.Identifier("auth", tabela)
        col_o = [r[0] for r in _ler(origem, SQL_COLUNAS_DESTINO, (f"auth.{tabela}",))]
        col_d = {r[0] for r in _ler(destino, SQL_COLUNAS_DESTINO, (f"auth.{tabela}",))}
        comuns = [c for c in col_o if c in col_d]
        if set(col_o) - col_d:
            log.append(f"auth.{tabela}: colunas so na origem, ignoradas: {', '.join(sorted(set(col_o) - col_d))}")
        filtro = S.SQL("{} = any(ARRAY[{}]::uuid[])").format(
            S.Identifier(chave), S.SQL(", ").join(S.Literal(i) for i in novas))
        _copiar(origem, destino, nome, comuns, filtro)
    log.append(f"contas copiadas com o mesmo ID: {len(novas)}")


def copiar(origem_url: str, destino_url: str, schema: str, trocar: tuple[str, str] | None,
           copiar_contas: bool, substituir: bool, confirmar: bool) -> list[str]:
    log: list[str] = []
    with conectar(origem_url, NOME_APP) as origem, conectar(destino_url, NOME_APP, leitura=False) as destino:
        if not _ler(origem, "select 1 from pg_namespace where nspname = %s", (schema,)):
            raise RuntimeError(f"schema {schema} nao existe na origem")
        estrutura = gerar_estrutura(origem, [schema])
        tabelas = _ler(origem, SQL_TABELAS, (schema,))
        objetos_origem = contar_objetos(origem, [schema])
        linhas_origem = {}

        with destino.transaction() as tx:
            destino.execute("SET LOCAL statement_timeout = '10min'")
            existe = bool(_ler(destino, "select 1 from pg_namespace where nspname = %s", (schema,)))
            if existe and not substituir:
                raise RuntimeError(f"schema {schema} ja existe no destino (use --substituir para apagar)")
            if existe:
                destino.execute(S.SQL("DROP SCHEMA {} CASCADE").format(S.Identifier(schema)))
                log.append(f"schema {schema} antigo apagado no destino")

            if copiar_contas:
                _copiar_contas(origem, destino, _contas_usadas(origem, schema), log)

            for comando in estrutura_em_lista(estrutura["antes"]):
                destino.execute(comando)

            # Dados antes das FKs, triggers e policies: nada dispara na carga.
            for tabela, colunas in tabelas:
                nome = S.Identifier(schema, tabela)
                _copiar(origem, destino, nome, list(colunas))
                linhas_origem[tabela] = _ler(origem, S.SQL("select count(*) from {}").format(nome))[0][0]

            if trocar:
                de, para = trocar
                if not _ler(destino, "select 1 from auth.users where id = %s", (para,)):
                    raise RuntimeError("a conta de destino do --trocar-usuario nao existe no destino")
                total = 0
                for tabela, coluna in _ler(destino, SQL_COLUNAS_UUID, (schema,)):
                    q = S.SQL("update {} set {c} = %s where {c} = %s").format(
                        S.Identifier(schema, tabela), c=S.Identifier(coluna))
                    with destino.cursor() as cur:
                        cur.execute(q, (para, de))
                        total += cur.rowcount
                log.append(f"conta trocada em {total} linhas")

            for comando in estrutura_em_lista(estrutura["depois"]):
                destino.execute(comando)

            # Conferencia: linhas por tabela e objetos por tipo.
            erros = []
            for tabela, esperado in linhas_origem.items():
                n = _ler(destino, S.SQL("select count(*) from {}").format(S.Identifier(schema, tabela)))[0][0]
                if n != esperado:
                    erros.append(f"{tabela}: {n} linhas no destino, {esperado} na origem")
            objetos_destino = contar_objetos(destino, [schema])
            for tipo, esperado in objetos_origem.items():
                if objetos_destino.get(tipo) != esperado:
                    erros.append(f"objetos {tipo}: {objetos_destino.get(tipo)} no destino, {esperado} na origem")
            if erros:
                raise RuntimeError("conferencia falhou: " + "; ".join(erros))
            log.append(f"{len(linhas_origem)} tabelas e {sum(linhas_origem.values())} linhas conferidas; "
                       f"objetos iguais: {objetos_destino}")

            if confirmar:
                destino.execute("NOTIFY pgrst, 'reload schema'")
                log.append("GRAVADO")
            else:
                log.append("ensaio: tudo desfeito (use --confirmar para gravar)")
                raise psycopg.Rollback(tx)
        origem.rollback()
    return log


def main() -> int:
    p = argparse.ArgumentParser(description="Copia um schema entre projetos Supabase.")
    p.add_argument("--origem", required=True, help="variavel do .env com a conexao de origem")
    p.add_argument("--destino", required=True, help="variavel do .env com a conexao de destino")
    p.add_argument("--schema", required=True)
    p.add_argument("--trocar-usuario", help="ID_ORIGEM=ID_DESTINO")
    p.add_argument("--copiar-contas", action="store_true")
    p.add_argument("--substituir", action="store_true")
    p.add_argument("--confirmar", action="store_true")
    a = p.parse_args()

    env = dl.ler_env()
    urls = []
    for var in (a.origem, a.destino):
        if not env.get(var):
            print(f"variavel {var} nao configurada")
            return 2
        urls.append(env[var])
    trocar = None
    if a.trocar_usuario:
        de, _, para = a.trocar_usuario.partition("=")
        trocar = (str(uuid.UUID(de)), str(uuid.UUID(para)))

    for linha in copiar(urls[0], urls[1], a.schema, trocar, a.copiar_contas, a.substituir, a.confirmar):
        print(linha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
