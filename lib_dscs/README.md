# lib_dscs — biblioteca compartilhada dos robôs

Mesmo papel da `marche_lib` do trabalho: **conexão com o banco, credenciais e
controle de cargas em um lugar só**. Robô não abre conexão na mão nem lê
credencial direto do arquivo — tudo passa por aqui.

---

## Uso

No topo do robô, junto do bootstrap de encoding:

```python
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import lib_dscs as dl
```

`parent.parent.parent` sai de `automacoes\<robo>\` e chega em `D:\ambiente_dev`,
que é a pasta que contém o pacote — é o `lib_dscs` que entra no `import`, não o
caminho. Mesma mecânica do `sys.path.insert(... / "Config")` + `import marche_lib`
do 205.

No `main()`:

```python
if not DEBUG:
    dl.status_inicio(IDCARGA)

processar()

if not DEBUG:
    dl.status_sucesso(IDCARGA)
```

E no `except`, `dl.status_erro(IDCARGA)` — dentro de um `try` próprio, para o
banco fora do ar não engolir o traceback original.

## API

### Configuração (`config.py`)

| Função | O que faz |
|---|---|
| `ler_env()` | dicionário com o `.env` da raiz |
| `obter_variavel(chave, padrao=None)` | uma variável; estoura se faltar e não houver padrão |
| `obter_configuracao()` | parâmetros de conexão do Postgres, validados |
| `descrever_conexao()` | `usuario@host:porta/banco` para log — **sem a senha** |

### Log (`log.py`)

| Função | O que faz |
|---|---|
| `configurar_logger(id_carga, nome_robo, base_dir)` | prepara o log — **não cria arquivo** |
| `log(msg)` / `log_erro(msg)` | uma linha no log |
| `logar_contexto(modo, extras={...})` | cabeçalho padrão (usuário, host, Python, executável) + o que o robô passar em `extras` |
| `logar_traceback(contexto)` | traceback completo, sem derrubar a execução |
| `salvar_log_erro()` | **só aqui vira arquivo**: `temp\erro_<id>_<nome>_<AAAAMMDD_HHMMSS>.txt` |

**As linhas ficam em memória durante a execução.** Dia normal não deixa arquivo
nenhum em disco — só o `except` do robô chama `salvar_log_erro()`. Um arquivo por
falha, com carimbo de hora no nome, então duas falhas no mesmo dia não se
sobrescrevem.

O console continua ligado, para quem roda na mão com `python.exe`. Pelo `.bat`
(que usa `pythonw.exe` e manda a saída para `NUL`) isso não custa nada.

### API (`api.py`)

| Função | O que faz |
|---|---|
| `chamar_api_json(url, metodo, corpo, cabecalhos, token, timeout)` | requisição HTTP com corpo e resposta em JSON → `(status, payload)` |

Só `urllib` da biblioteca padrão, sem `requests`. O tratamento de erro é
**assimétrico de propósito**:

- **5xx** → levanta `RuntimeError`. É falha do outro lado, transitória — normalmente
  você envolve a chamada em `executar_com_retry`.
- **4xx** → devolve `(status, payload)` sem levantar. É erro de configuração
  (token, permissão, recurso inexistente) e insistir não ajuda; além disso um
  `404` às vezes é esperado — o robô 001 usa isso para saber que o arquivo ainda
  não existe no repositório.

O payload de erro volta decodificado: quase toda API põe o motivo em
`{"message": ...}`, e engolir isso deixaria o log só com o número do status.

**Não faz retry** — isso é do `executar_com_retry`, que sabe o nome da etapa e
loga cada tentativa.

### Retry (`retry.py`)

| Função | O que faz |
|---|---|
| `executar_com_retry(etapa, funcao, tentativas=3, espera=30)` | repete a etapa, logando cada tentativa; falha final vira `RuntimeError` |

Use só onde a falha é transitória — rede, SFTP, API fora do ar. Credencial,
permissão e layout errado não melhoram com insistência: ali o certo é estourar
na primeira.

### Estado local (`estado.py`)

| Função | O que faz |
|---|---|
| `ja_executou_hoje(base_dir)` | a trava diária: `True` se já rodou hoje |
| `marcar_execucao(base_dir, **campos)` | grava a data de hoje + os campos do robô |
| `ler_estado(base_dir)` / `gravar_estado(base_dir, dados)` | acesso direto ao `temp\estado.json` |

Arquivo corrompido vira `{}` com aviso no log, não exceção: o pior caso é perder
a trava e rodar de novo — melhor do que a carga parar por causa do arquivo de
controle local.

### Supabase (`supabase.py`)

O registro oficial das cargas desde a migração para o GitHub Actions
(26/09/2026). Fala com o PostgREST pelo `chamar_api_json`, sem `supabase-py`.

| Função | O que faz |
|---|---|
| `modo_execucao()` | `LOCAL` (padrão) ou `CLOUD`, de `MODO_EXECUCAO` |
| `supabase_configurado()` | `True` com `SUPABASE_URL` e `SUPABASE_KEY` presentes |
| `registrar_carga_supabase(id, status, dta_ini, fechar, mensagem, qtd_itens)` | atualiza `public.controle_cargas`; com `fechar=True` também insere em `public.historico_cargas`. **Nunca levanta** |
| `trabalho_feito_no_dia(id, dia_utc)` | soma de `qtd_itens` das execuções do dia UTC (inclusive lote parcial que quebrou): a trava diária que funciona na nuvem. **Levanta** se o Supabase não responder |
| `url_execucao_actions()` | link do run atual no Actions, ou `None` fora dele |
| `ler_saude_robos()` | linhas da `vw_saude_robos`; `SAUDE_BOA` = `("OK", "RODANDO")`. **Levanta** |
| `notificar_hub(nivel, titulo, detalhe, origem)` | grava em `public.notificacoes_hub` (`info`/`atencao`/`resolvido`). **Nunca levanta** |
| `ultima_notificacao(origem)` | a notificação mais recente de uma origem, ou `None` |

`registrar_carga_supabase` grava também `ambiente` (`LOCAL`/`CLOUD`) e o link do
run, que o hub usa para abrir o log. `id_carga` inexistente vira erro no log, e
não uma linha nova, pelo mesmo motivo do `controle_cargas.py`.

A chave precisa ser a `service_role`: as tabelas têm RLS ligada e sem policy.

### Banco (`banco.py`)

| Função | O que faz |
|---|---|
| `conexao(autocommit=True)` | context manager, fecha sempre — **é o preferido** |
| `abrir_conexao_banco(autocommit=True)` | conexão crua; quem chama fecha |
| `executar_query(sql, params)` | SELECT → lista de tuplas |
| `executar_query_dict(sql, params)` | SELECT → lista de dicionários |
| `executar_comando(sql, params)` | INSERT/UPDATE/DELETE → nº de linhas |
| `testar_conexao()` | versão + banco + usuário; use para validar o `.env` |

### Controle de cargas (`controle_cargas.py`)

| Função | Efeito em `dbo.controle_cargas` |
|---|---|
| `status_inicio(id_carga)` | `status='RUNNING'`, `dta_ini=now()`, **`dta_fim=NULL`** |
| `status_sucesso(id_carga)` | `status='SUCCESS'`, `dta_fim=now()` |
| `status_erro(id_carga)` | `status='ERROR'`, `dta_fim=now()` |
| `obter_carga(id_carga)` | a linha como dicionário, ou `None` |
| `listar_cargas(somente_ativas=False)` | todas as cargas cadastradas |

> Os valores vêm da check constraint da tabela — não invente outros:
> ```sql
> CHECK (status = ANY (ARRAY['RUNNING', 'SUCCESS', 'ERROR']))
> ```
> Use as constantes `dl.STATUS_INICIO`, `dl.STATUS_SUCESSO` e `dl.STATUS_ERRO`
> em vez das strings soltas.

Todas atualizam `dta_modif`. **`id_carga` inexistente estoura `ValueError`** — de
propósito: silenciar esconderia um número digitado errado, e o sintoma seria um
monitoramento vazio que ninguém liga ao robô.

## Credenciais

Tudo no `.env` da **raiz** (`D:\ambiente_dev\.env`), fora das pastas dos robôs:

```
PG_HOST=localhost
PG_PORT=5432
PG_DB=dm
PG_USER=postgres
PG_PASSWORD=...

GITHUB_TOKEN=...
```

Variável de ambiente do Windows tem prioridade sobre o arquivo, para sobrescrever
numa execução pontual sem editar o `.env`. `PG_HOST` e `PG_PORT` têm padrão
(`localhost:5432`); banco, usuário e senha **não têm** — sem eles o erro diz
qual chave falta, em vez de "conexão recusada".

> A `marche_lib` usa `credenciais.json`; aqui é `.env` por decisão sua, e porque
> o `GITHUB_TOKEN` do robô 001 já morava lá.

## Decisões

### Por que `dta_fim = NULL` no início

`status='RUNNING'` **com `dta_fim` nulo** significa "rodando agora, ou morreu no
meio sem fechar". É assim que se descobre robô que caiu sem registrar o erro —
máquina desligada, processo morto, queda de energia. Se o `status_inicio` não
limpasse o `dta_fim`, a linha ficaria com a data da execução anterior e o estado
pareceria consistente.

Consulta de robô travado (cruze o `tempo_min` da própria tabela para saber se
já passou do tempo esperado):

```sql
select id_carga, nome_carga, dta_ini, tempo_min,
       round(extract(epoch from now() - dta_ini) / 60) as minutos_rodando
  from dbo.controle_cargas
 where status = 'RUNNING'
   and dta_fim is null
   and now() - dta_ini > (tempo_min || ' minutes')::interval;
```

### Por que autocommit no registro de status

O status precisa ficar gravado **mesmo que a carga estoure logo depois** — é
justamente o caso do `status_erro`. Com autocommit, cada `UPDATE` fecha sozinho.
Carga de dados é o oposto: `abrir_conexao_banco(autocommit=False)`, uma transação
só, commit/rollback na mão.

### Por que `status_erro` não grava a mensagem

`dbo.controle_cargas` não tem coluna de mensagem. O motivo do erro fica no log do
robô (`logs\robo_<id>_<nome>_AAAAMMDD.txt`, com traceback). A tabela responde
"quando rodou e como terminou"; o log responde "por quê".

### psycopg 3, não psycopg2

`psycopg[binary]` 3.3.5 — wheel com o driver embutido, sem precisar de compilador
nem do Postgres client instalado. `con.execute()` já devolve cursor, então não
precisa do `with con.cursor()` a cada query.

## Limitação conhecida: sem histórico (no Postgres local)

> Resolvido do lado do Supabase em 26/09/2026: `public.historico_cargas` guarda
> uma linha por execução, gravada por `registrar_carga_supabase`. O que segue
> vale só para a tabela local.

`dbo.controle_cargas` tem **uma linha por carga**, e cada execução sobrescreve
`status`/`dta_ini`/`dta_fim`. Você vê a última rodada, não as anteriores — não dá
para saber se o robô falhou três vezes essa semana.

No trabalho isso é resolvido com `Cargas` (config) + `CargaHistorico` (uma linha
por execução). Se um dia isso incomodar, o caminho é criar
`dbo.controle_cargas_historico` e fazer os `status_*` inserirem lá além de
atualizar aqui — a mudança fica **toda dentro de `controle_cargas.py`**, nenhum
robô precisa mudar.

## Colunas que a lib não usa

`tempo_min`, `dias_semana`, `flg_ativo`, `origem` e `script` são **documentação
por decisão sua** — quem decide se e quando o robô roda é o Agendador do Windows
e o código. Se um dia quiser inverter isso (o banco mandando), o gancho é ler
`obter_carga(id)` no começo do `main()` e encerrar se `flg_ativo` for falso ou o
dia da semana não estiver em `dias_semana`.

## Arquivos

```
lib_dscs\
├─ __init__.py           API pública (é o que o robô importa)
├─ config.py             .env da raiz + parâmetros de conexão
├─ banco.py              conexão psycopg e helpers de query
├─ controle_cargas.py    status_inicio / sucesso / erro
├─ log.py                log em memória, arquivo só em caso de erro
├─ api.py                cliente HTTP/JSON dos robôs de API
├─ retry.py              executar_com_retry
├─ estado.py             trava diária em temp\estado.json
├─ supabase.py           controle de cargas no Supabase + trava pela nuvem
└─ README.md
```

## Esqueleto de um robô novo

O esqueleto oficial é [`automacoes/_modelo/NNN_nome_robo.py`](../automacoes/_modelo/NNN_nome_robo.py),
e as regras estão em [`automacoes/PADRAO_ROBOS.md`](../automacoes/PADRAO_ROBOS.md).
O miolo do `main()`:

```python
registrar = not (DEBUG or DRY_RUN or STATUS)
try:
    validar_configuracao()
    if registrar:
        dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, dta_ini, fechar=False)

    qtd, resumo = processar()

    if registrar:
        dl.registrar_carga_supabase(IDCARGA, dl.STATUS_SUCESSO, dta_ini, fechar=True,
                                    mensagem=resumo, qtd_itens=qtd)
except Exception as e:
    if registrar:
        dl.registrar_carga_supabase(IDCARGA, dl.STATUS_ERRO, dta_ini, fechar=True,
                                    mensagem=str(e)[:500], qtd_itens=ITENS_FEITOS)
        dl.alertar_erro_robo(IDCARGA, NOME_ROBO, str(e))
    dl.salvar_log_erro()
    raise
```

Os `status_inicio`/`status_sucesso`/`status_erro` do Postgres local (`dm`) só
existem para o modo `LOCAL` dos robôs antigos; robô novo não usa.

O `try/except` fica **explícito em cada robô**, por decisão sua — a alternativa
era um `with dl.execucao(...)` que escondesse isso. Mais linhas, porém o fluxo
inteiro fica visível no arquivo do robô, como no 205.

## Teste rápido

```powershell
cd D:\ambiente_dev
& "C:\Users\ferna\AppData\Local\Python\bin\python.exe" -c "import lib_dscs as dl; print(dl.testar_conexao())"
```
