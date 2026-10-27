# Robô 001 — Check GitHub (registro diário de atividade)

Faz **commits reais** em um repositório próprio no GitHub, via API REST
(*Contents API*), acrescentando uma linha em `registro/atividades.md`.
Como são commits no branch padrão de um repo do próprio usuário, eles alimentam
o **calendário de contribuições** do perfil.

Roda no **GitHub Actions**, todo dia às 07:00 de São Paulo (10:00 UTC),
disparado pelo `pg_cron` do Supabase
([workflow](../../.github/workflows/robo_001_check_github.yml)), com trava e
registro no Supabase (`id_carga = 1`).

> ⚠️ A atividade é sintética. O calendário fica verde de verdade, mas os commits
> não representam trabalho — não use o gráfico como evidência de entrega.

---

## Fluxo

1. Valida a configuração: token (`GH_PAT`, ou `GITHUB_TOKEN` no `.env` do PC) e
   `SUPABASE_URL`/`SUPABASE_KEY`.
2. Descobre o dono do token (`GET /user`).
3. **Trava do dia**: `dl.trabalho_feito_no_dia(1, dia_utc)` soma o `qtd_itens`
   do dia UTC em `public.historico_cargas`. Maior que zero → **encerra sem
   commitar** e registra a execução com `qtd_itens = 0`.
4. Sorteia quantos commits fazer (4 a 8). **Não decide se o dia é de commit** —
   se foi chamado, commita.
5. Lê o arquivo remoto para pegar o `sha` atual.
6. Para cada commit: acrescenta uma linha, `PUT` na Contents API, pausa de 2 a 6s.
7. Registra `SUCCESS` com o número de commits em `qtd_itens`.

```
[ESTADO] dia 2026-09-26 (UTC) ja processado (5 commit(s)) - nada a fazer
```

## Origem / Destino

| | |
|---|---|
| API | `https://api.github.com` (Contents API) |
| Token | secret `GH_PAT` no Actions; `GITHUB_TOKEN` no `.env` da raiz, no PC |
| Repositório | `<owner>/daily-log`, branch `main` |
| Arquivo | `registro/atividades.md` — uma linha acrescentada por commit |

O token precisa ser **clássico com scope `repo`** ou **fine-grained com
`Contents: Read and write`** no repositório de destino. O GitHub recusa secret
com prefixo `GITHUB_`, por isso `GH_PAT` (o robô lê ele antes do `GITHUB_TOKEN`).

### Por que o `sha` é lido antes de cada commit

A Contents API exige o `sha` do arquivo para atualizá-lo — é a trava de
concorrência dela. O robô lê uma vez no começo e depois **encadeia** o `sha`
devolvido por cada commit no commit seguinte, sem reler o arquivo a cada volta.

### O que faz o commit contar no calendário

- Precisa ser no **branch padrão** do repositório (`GITHUB_BRANCH`).
- O commit é atribuído ao dono do token (a API assina com a conta autenticada),
  então não depende do `user.email` do git local.
- Repositório **privado** só aparece com *Private contributions* habilitado no
  perfil. Por isso `REPO_PRIVADO = False` é o padrão.

## Trava diária

- **É o Supabase.** A máquina do Actions nasce vazia a cada execução; arquivo
  local não lembra de nada.
- **Sem Supabase, não commita.** Se a leitura da trava falhar, a execução
  termina em `ERROR`. Sem saber se o dia já foi feito, o seguro é não dobrar.
- **Lote parcial conta.** Um lote que quebra no meio registra os commits que
  chegaram ao GitHub (`qtd_itens` no `ERROR`), e a trava soma também execuções
  com erro — a próxima não faz outro lote inteiro.
- `--force` é a única coisa que ignora a trava.

### A trava usa o dia **UTC**, não o de São Paulo

Corrigido em **25/09/2026**. O calendário de contribuições conta o commit pela
data do carimbo do próprio commit, e a Contents API carimba em **UTC** (offset
`Z`). O quadradinho que fica verde é o do dia UTC — o fuso da máquina não entra
na conta.

Até 24/09 a trava usava `datetime.now()` (hora local). Com a tarefa às 20:40 de
São Paulo isso dá **23:40 UTC**: vinte minutos de margem até a virada do dia.
Em 24/09 a tarefa atrasou e rodou 22:06 local — **01:06 UTC do dia 25**:

```
2026-09-25  8 commits  UTC 01:06    <- a rodada "de 24/09"
2026-09-23  4 commits  UTC 23:40
2026-09-22  4 commits  UTC 23:40
```

Os oito commits caíram inteiros no quadrado do dia 25, e **24/09 ficou branco**.
Nada acusou: `SUCCESS` gravado, a trava marcando 24/09 como processado, nenhum
log de erro. O robô jura que deu certo e o gráfico discorda. Pior: no dia
seguinte a trava barrava a execução justamente quando ela encheria o quadrado
vazio.

A correção é a função `dia_github()`, que devolve `datetime.now(timezone.utc)` e
alimenta a trava e a linha gravada no arquivo remoto. "Uma execução por dia"
passa a significar "uma execução por quadradinho". O disparo às 10:00 UTC fica
longe da virada, então nenhum atraso empurra o lote para o dia seguinte.

### Quem decide o dia é o cron

O robô **não tem regra de calendário**: nada de sorteio de folga, nada de "pular
fim de semana". Se ele foi chamado, ele commita. Quando rodar é responsabilidade
exclusiva do agendamento — um lugar só para mexer.

Até 08/09/2026 existia um `PROBABILIDADE_FOLGA = 0.20` que sorteava dias de
folga para o gráfico não ficar uniforme demais. Foi removido a pedido: o efeito
prático era quadrado branco no meio da semana sem motivo aparente (foi o que
aconteceu em 08/09, com sorteio 0.09). Junto saiu o `PULAR_FIM_DE_SEMANA`.

## Controle de cargas

`public.controle_cargas` + `public.historico_cargas`, **`id_carga = 1`**, pela
`lib_dscs` (`dl.registrar_carga_supabase`):

| Momento | Registro |
|---|---|
| Antes de processar | `RUNNING` |
| Fim sem erro | `SUCCESS`, `qtd_itens` = commits, `mensagem` = `"6 commit(s) em diegoscs/daily-log (ultimo abc1234)"` |
| Exceção | `ERROR`, `qtd_itens` = commits já enviados, `mensagem` = erro |

**Não registram status:** `--setup`, `--status`, `--dry-run` e `DEBUG=True`. Não
são a carga diária — marcar `SUCCESS` neles mentiria no monitoramento.

**Falha:** `ERROR` + histórico no Supabase, alerta no Telegram (se os secrets
existirem), e-mail do GitHub e o `erro_*.txt` como artifact `log-erro-001`.

## Execução

```powershell
$py = "C:\Users\ferna\AppData\Local\Python\bin\python.exe"

# mostra o que faria, sem tocar no GitHub nem registrar
& $py automacoes\001_check_github\001_check_github.py --dry-run

# configuracao e commits do dia, sem commitar
& $py automacoes\001_check_github\001_check_github.py --status

# cria o repositorio (uma vez so)
& $py automacoes\001_check_github\001_check_github.py --setup
```

Disparo real: pelo botão *Rodar agora* do hub ou `workflow_dispatch` no GitHub.
Rodar de verdade no PC também funciona (registra `ambiente = LOCAL`) e respeita a
mesma trava.

### Log: só em caso de erro

As linhas ficam **em memória** durante a execução e só viram arquivo se ela
falhar: `temp\erro_001_check_github_<AAAAMMDD_HHMMSS>.txt`, com o log inteiro e o
traceback. No Actions esse arquivo sobe como artifact do run. **Execução
bem-sucedida não deixa rastro em disco.**

### Flags

| | Efeito |
|---|---|
| `DEBUG = False` | **valor atual.** Commita e registra. |
| `DEBUG = True` | não commita e não registra — só loga o que faria. |
| `--dry-run` | igual ao `DEBUG = True`, sem editar o arquivo. |
| `--force` | ignora o travamento diário (permite um segundo lote no mesmo dia). |
| `--setup` | cria o repositório no GitHub, se ainda não existir. Não commita. |
| `--status` | mostra configuração e commits do dia. Não commita. |

### Parâmetros de comportamento

| Constante | Valor | O que faz |
|---|---|---|
| `MIN_COMMITS` / `MAX_COMMITS` | 4 / 8 | quantos commits no dia, sorteado |
| `PAUSA_ENTRE_COMMITS` | (2, 6) | segundos entre commits, sorteado |
| `TENTATIVAS_API` | 3 | tentativas por etapa de rede |
| `SEGUNDOS_ENTRE_TENTATIVAS` | 30 | espera entre as tentativas |

## Validações que abortam a execução

- Token ausente (`GH_PAT`/`GITHUB_TOKEN`) ou `SUPABASE_URL`/`SUPABASE_KEY` ausentes.
- Token inválido ou sem permissão (`HTTP 401` em `GET /user`).
- `MIN_COMMITS`/`MAX_COMMITS` fora da faixa válida.
- Trava do dia ilegível no Supabase.
- Repositório de destino inexistente — a mensagem manda rodar com `--setup`.

Erros `5xx` e falha de rede passam pelo `dl.executar_com_retry` (3 tentativas,
30s entre elas). Erros `4xx` **não** são repetidos: token, permissão e nome de
repositório não melhoram com insistência.

## Decisões

### Por que API REST e não `git commit` + `git push`

Com a Contents API é uma requisição HTTP com o token no header: sem clone, sem
credencial de push, sem repositório local para dessincronizar. O `--setup` cria
o repositório pela própria API.

### `lib_dscs`

`sys.path.insert` da pasta que contém o pacote e `import lib_dscs as dl`.
`IDCARGA` é ao mesmo tempo o número da pasta e o `id_carga` na tabela de
controle. Log, retry, `.env`, registro e trava vêm todos da
[`lib_dscs`](../../lib_dscs/README.md) — o robô só tem a lógica do GitHub.

## Histórico

### Diagnóstico: 7 dias em branco (09/09 a 15/09/2026)

Na época o robô rodava pelo Agendador do Windows. Ele **não falhou — nunca foi
chamado**: a tarefa tinha `LogonType = Interactive` (só roda com o usuário
logado) e `StartWhenAvailable = False` (execução perdida é descartada).

Nenhum registro do próprio robô acusou o problema: a tabela de controle marcava
`SUCCESS` (verdade, da última execução, de 08/09 — o status não envelhece
sozinho), não havia log de erro (não houve erro). **Robô que não roda é
silencioso.** Daí a `vw_saude_robos` medir **atraso** (`atraso_max_horas`) e o
vigia diário transformar isso em aviso.

### Linha do tempo

- **05/09/2026** — primeira versão. `--setup` criou `diegoscs/daily-log`;
  atribuição confirmada (`author.login = diegoscs`). Infra extraída para a
  `lib_dscs` (519 → 380 linhas).
- **08/09/2026** — saem `PROBABILIDADE_FOLGA` e `PULAR_FIM_DE_SEMANA`; 4 a 8
  commits por dia.
- **21/09/2026** — tarefa do Agendador corrigida (`S4U`, `StartWhenAvailable`).
- **25/09/2026** — trava passa a usar o dia UTC; tarefa única no logon.
- **26/09/2026** — migra para o GitHub Actions, trava e registro no Supabase.
  Run [36241476925](https://github.com/diegoscs/ambiente_dev/actions/runs/36241476925)
  leu os 5 commits do dia feitos pelo PC e saiu pela trava. Primeiro lote pela
  nuvem em 27/09.
- **02/10/2026** — modo `LOCAL` removido: sem `.bat`, sem `temp\estado.json`,
  sem `dbo.controle_cargas` e sem a cópia `temp\atividades.md`. A trava é só o
  Supabase.

## Pendências

- [ ] Não há reposição retroativa: se um dia inteiro passar sem execução,
      aquele dia fica em branco no calendário. O vigia avisa (`ATRASADO`), mas
      backfill exigiria a Git Data API (commit com `author.date` no passado).

## Arquivos

```
001_check_github\
├─ 001_check_github.py     o robô
└─ README.md
```

`temp\` só aparece quando há falha, com o `erro_001_check_github_*.txt`.
