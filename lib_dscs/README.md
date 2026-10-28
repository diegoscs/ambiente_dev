# lib_dscs — biblioteca compartilhada dos robôs

Mesmo papel da `marche_lib` do trabalho: **credenciais, log, HTTP e controle de
cargas em um lugar só**. Robô não fala com o Supabase na mão nem lê credencial
direto do arquivo — tudo passa por aqui.

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

No `main()`, o registro no Supabase com `dl.registrar_carga_supabase` — o miolo
completo está em [Esqueleto de um robô novo](#esqueleto-de-um-robô-novo).

> **2.1.0 (28/10/2026):** as funções `*_minecraft` recebem `servidor`
> (`create`, o padrão, ou `pixelmon`): são dois servidores nas tabelas `minecraft_*`.

> **2.0.0 (27/10/2026):** saíram `banco.py`, `controle_cargas.py` e `estado.py`
> (Postgres local `dm`, `dbo.controle_cargas` e a trava em `temp\estado.json`).
> Desde 02/10/2026 nenhum robô usava. As constantes `STATUS_*` passaram para o
> `supabase.py`, com o mesmo nome em `dl.`. O código antigo está no histórico do
> Git (`git show 17c1b5c:lib_dscs/banco.py`).

## API

### Configuração (`config.py`)

| Função | O que faz |
|---|---|
| `ler_env()` | dicionário com o `.env` da raiz + variáveis de ambiente com prefixo em `PREFIXOS_AMBIENTE` |
| `obter_variavel(chave, padrao=None)` | uma variável; estoura se faltar e não houver padrão |

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

O console continua ligado: é o que aparece no log do run no Actions e na tela de
quem roda na mão.

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
| `supabase_ler(consulta)` / `supabase_inserir(tabela, linhas, conflito)` / `supabase_atualizar(tabela, filtro, campos)` / `supabase_apagar(tabela, filtro)` | CRUD genérico no PostgREST; `conflito` vira upsert; filtro vazio no apagar é recusado. **Levantam** |
| `gravar_status_minecraft`, `gravar_eventos_minecraft`, `ultimo_evento_minecraft`, `comandos_minecraft_abertos`, `fechar_comando_minecraft` | tabelas `minecraft_*` do monitor do server. **Levantam** |

Status: use `dl.STATUS_INICIO` (`RUNNING`), `dl.STATUS_SUCESSO` (`SUCCESS`) e
`dl.STATUS_ERRO` (`ERROR`), os valores da check constraint das tabelas, em vez
de strings soltas.

`registrar_carga_supabase` grava também `ambiente` (`LOCAL`/`CLOUD`) e o link do
run, que o hub usa para abrir o log. **`id_carga` inexistente vira erro no log, e
não uma linha nova** — de propósito: silenciar esconderia um número digitado
errado, e o sintoma seria um monitoramento vazio que ninguém liga ao robô.

A chave precisa ser a `service_role`: as tabelas têm RLS ligada e sem policy.

## Credenciais

No PC, tudo no `.env` da **raiz** (`D:\ambiente_dev\.env`), fora das pastas dos
robôs; o modelo é o [`.env.example`](../.env.example). No Actions não existe
`.env`: os secrets chegam como variável de ambiente, e só entram os prefixos de
`PREFIXOS_AMBIENTE` (`config.py`).

Variável de ambiente tem prioridade sobre o arquivo, para sobrescrever numa
execução pontual sem editar o `.env`.

> A `marche_lib` usa `credenciais.json`; aqui é `.env` por decisão sua, e porque
> o `GITHUB_TOKEN` do robô 001 já morava lá.

## Decisões

### Por que `dta_fim = NULL` no início

`status='RUNNING'` **com `dta_fim` nulo** significa "rodando agora, ou morreu no
meio sem fechar". É assim que se descobre robô que caiu sem registrar o erro
(run cancelado, timeout do Actions). Se o registro de início não limpasse o
`dta_fim`, a linha ficaria com a data da execução anterior e o estado pareceria
consistente. A `vw_saude_robos` cruza isso com o `tempo_min` e mostra `TRAVADO`.

### Colunas que a lib não usa

`tempo_min`, `dias_semana`, `flg_ativo`, `origem` e `script` são **documentação
por decisão sua** — quem decide se e quando o robô roda é o cron do workflow e o
código. `tempo_min` e `atraso_max_horas` alimentam a `vw_saude_robos`, e
`workflow` é o que o botão do hub dispara.

## Arquivos

```
lib_dscs\
├─ __init__.py           API pública (é o que o robô importa)
├─ config.py             .env da raiz + variáveis de ambiente
├─ log.py                log em memória, arquivo só em caso de erro
├─ api.py                cliente HTTP/JSON dos robôs de API
├─ retry.py              executar_com_retry
├─ notificacao.py        alerta no Telegram
├─ supabase.py           controle de cargas, trava diária, hub e Minecraft
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

O `try/except` fica **explícito em cada robô**, por decisão sua — a alternativa
era um `with dl.execucao(...)` que escondesse isso. Mais linhas, porém o fluxo
inteiro fica visível no arquivo do robô, como no 205.

## Teste rápido

```powershell
cd D:\ambiente_dev
& "C:\Users\ferna\AppData\Local\Python\bin\python.exe" -c "import lib_dscs as dl; print(dl.ler_saude_robos())"
```
