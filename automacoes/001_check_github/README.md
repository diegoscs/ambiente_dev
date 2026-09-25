# Robô 001 — Check GitHub (registro diário de atividade)

Faz **commits reais** em um repositório próprio no GitHub, via API REST
(*Contents API*), acrescentando uma linha em `registro/atividades.md`.
Como são commits no branch padrão de um repo do próprio usuário, eles alimentam
o **calendário de contribuições** do perfil.

> ⚠️ A atividade é sintética. O calendário fica verde de verdade, mas os commits
> não representam trabalho — não use o gráfico como evidência de entrega.

---

## Fluxo

1. Lê o `GITHUB_TOKEN` do `.env` da **raiz do ambiente** (`D:\ambiente_dev\.env`).
2. Descobre o dono do token (`GET /user`) quando `GITHUB_OWNER` está vazio.
3. Confere `temp\estado.json`: se o dia já foi processado, **encerra sem commitar**.
4. Sorteia quantos commits fazer (4 a 8). **Não decide se o dia é de commit** —
   se foi chamado, commita.
5. Lê o arquivo remoto para pegar o `sha` atual.
6. Para cada commit: acrescenta uma linha, `PUT` na Contents API, pausa de 2 a 6s.
7. Grava `temp\estado.json` e a cópia local do arquivo em `temp\atividades.md`.

## Origem / Destino

| | |
|---|---|
| API | `https://api.github.com` (Contents API) |
| Token | `GITHUB_TOKEN` em `D:\ambiente_dev\.env` |
| Repositório | `<owner>/daily-log`, branch `main` |
| Arquivo | `registro/atividades.md` — uma linha acrescentada por commit |

O token precisa ser **clássico com scope `repo`** ou **fine-grained com
`Contents: Read and write`** no repositório de destino. Gere em
<https://github.com/settings/tokens>.

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

## Estado e travamento diário

`temp\estado.json` guarda o último dia processado, quantos commits saíram, o
motivo e o último `sha` **do arquivo** (o blob da Contents API, não o sha do
commit — é esse que a API pede para a próxima atualização):

```json
{
  "ultima_execucao": "2026-09-04",
  "commits": 2,
  "motivo": "dia de commit",
  "ultimo_sha": "a1b2c3d..."
}
```

**O Task Scheduler pode disparar a tarefa mais de uma vez no mesmo dia**
(retry da tarefa, máquina que ligou tarde, execução manual). Sem esse arquivo o
robô dobraria os commits do dia. Com ele, a segunda execução sai no ato.
`--force` é a única coisa que ignora a trava.

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
Nada acusou: `SUCCESS` na `dbo.controle_cargas`, `estado.json` marcando 24/09
como processado, nenhum log de erro. É a mesma armadilha dos 7 dias em branco de
setembro — o robô jura que deu certo e o gráfico discorda. Pior: no dia seguinte
a trava barrava a execução ("24/09 já processado") justamente quando ela encheria
o quadrado vazio.

A correção é a função `dia_github()`, que devolve `datetime.now(timezone.utc)` e
alimenta a trava, o `marcar_execucao` e a linha gravada no arquivo remoto. A
`ja_executou_hoje` da `lib_dscs` já aceitava o parâmetro `hoje`, então **a lib não
mudou**: o padrão dela continua sendo hora local, que é o certo para um robô cujo
"dia" é o daqui. Aqui o dia é o da GitHub.

Com isso, "uma execução por dia" passa a significar "uma execução por
quadradinho". O gatilho de logon ajuda no mesmo sentido: logon de manhã cai no
meio do dia UTC, longe da virada.

> Na migração o `estado.json` foi de `2026-09-24` para `2026-09-25` — o dia UTC
> em que aqueles commits de fato caíram. Sem isso o robô faria um segundo lote
> no mesmo quadrado.

### Quem decide o dia é o Agendador

O robô **não tem regra de calendário**: nada de sorteio de folga, nada de "pular
fim de semana". Se ele foi chamado, ele commita. Quando rodar é responsabilidade
exclusiva da tarefa do Windows — um lugar só para mexer, em vez de dois que
podem discordar entre si.

Até 08/09/2026 existia um `PROBABILIDADE_FOLGA = 0.20` que sorteava dias de
folga para o gráfico não ficar uniforme demais. Foi removido a pedido: o efeito
prático era quadrado branco no meio da semana sem motivo aparente (foi o que
aconteceu em 08/09, com sorteio 0.09). Junto saiu o `PULAR_FIM_DE_SEMANA`, que
duplicava em código a decisão que já está no gatilho da tarefa.

## Controle de cargas

O robô registra a execução em `dbo.controle_cargas` (Postgres `dm`), **`id_carga = 1`**,
via `lib_dscs`:

| Momento | Status gravado |
|---|---|
| Antes de processar | `RUNNING`, `dta_ini=now()`, `dta_fim=NULL` |
| Fim sem erro | `SUCCESS`, `dta_fim=now()` |
| Exceção | `ERROR`, `dta_fim=now()` |

**Não registram status:** `--setup`, `--status`, `--dry-run` e `DEBUG=True`. Os
dois primeiros são manutenção, não a carga diária — marcar `SUCCESS` neles
mentiria no monitoramento.

O `status_erro` roda dentro de um `try` próprio: se o Postgres estiver fora do ar
junto, o log continua mostrando o erro real do robô em vez de ser substituído
pelo erro de conexão. Nesse caso a linha fica em `RUNNING` com `dta_fim` nulo —
que é justamente o sinal de "morreu no meio".

A tabela **não tem coluna de mensagem**: o motivo do erro fica no log do dia.

## Execução

```powershell
# dev — mostra o que faria, sem tocar no GitHub
C:\Users\ferna\AppData\Local\Python\bin\python.exe .\001_check_github.py --dry-run

# cria o repositorio (uma vez so)
C:\Users\ferna\AppData\Local\Python\bin\python.exe .\001_check_github.py --setup

# execucao normal
C:\Users\ferna\AppData\Local\Python\bin\python.exe .\001_check_github.py
```

Pelo `.bat` (é o que o Agendador chama). Ele usa `pythonw.exe` e manda stdout
para `NUL`. **Para rodar na mão e ver a saída na tela, chame `python.exe`
direto**, como nos exemplos acima.

### Log: só em caso de erro

Não há pasta `logs\`. As linhas ficam **em memória** durante a execução e só
viram arquivo se a execução falhar:

```
temp\erro_001_check_github_20260905_005043.txt
```

Um arquivo por falha, com carimbo de hora — duas falhas no mesmo dia não se
sobrescrevem. Ele contém o log inteiro daquela execução, do cabeçalho de contexto
até o traceback. **Execução bem-sucedida não deixa rastro em disco.**

O caminho do arquivo também é impresso no `stderr` quando o robô quebra (visível
ao rodar na mão; pelo `.bat` vai para `NUL`, então o arquivo em `temp\` é a única
via).

> O `.bat` usa `cd /d` (e não só `cd`, como o 205): a pasta está no `D:`, e sem o
> `/d` o `cmd` troca de diretório mas não de unidade.
>
> O Python é a instalação de usuário (`C:\Users\ferna\AppData\Local\Python\bin\`),
> Python 3.14.3 — **decisão fechada**, não há plano de migrar para uma instalação
> padrão em `C:\Automacao\Python\`, como a da VM do trabalho.
>
> **A chamada do `pythonw.exe` tem que ser a última linha do `.bat`.** Qualquer
> comando depois dela — um `REM` inclusive — zera o `ERRORLEVEL`, e o Agendador
> passa a marcar como sucesso uma execução que terminou em erro. Isso chegou a
> acontecer aqui durante os testes.

### Flags

| | Efeito |
|---|---|
| `DEBUG = False` | **valor atual.** Commita e grava o estado do dia. |
| `DEBUG = True` | não commita e não grava estado — só loga o que faria. |
| `--dry-run` | igual ao `DEBUG = True`, sem editar o arquivo. |
| `--force` | ignora o travamento diário (permite um segundo lote no mesmo dia). |
| `--setup` | cria o repositório no GitHub, se ainda não existir. Não commita. |
| `--status` | mostra configuração e estado atual. Não commita. |

### Parâmetros de comportamento

| Constante | Valor | O que faz |
|---|---|---|
| `MIN_COMMITS` / `MAX_COMMITS` | 4 / 8 | quantos commits no dia, sorteado |
| `PAUSA_ENTRE_COMMITS` | (2, 6) | segundos entre commits, sorteado |
| `TENTATIVAS_API` | 3 | tentativas por etapa de rede |
| `SEGUNDOS_ENTRE_TENTATIVAS` | 30 | espera entre as tentativas |

## Agendamento

O robô **não tem tarefa própria** desde 25/09/2026. Quem o chama é a tarefa
única [`ambiente_dev - Robos`](../README.md), disparada **a cada logon** com 3
minutos de atraso, através do [`iniciar_robos.bat`](../iniciar_robos.bat).

Antes era uma tarefa diária às 20:40. A troca foi pedida para amarrar a execução
ao uso real da máquina em vez de um horário fixo: se o PC está ligado, o robô
rodou; se não está, nenhum horário salvaria mesmo.

Horário nunca importou muito aqui — o commit conta no dia em que é feito. O que
importa é rodar **uma vez por dia**, e é a trava do `estado.json` que garante
isso: você loga cinco vezes no dia, o robô commita na primeira e sai no ato nas
outras quatro. Se o dia for perdido (máquina desligada o dia inteiro), ele
**não** repõe retroativamente (ver Pendências).

## Validações que abortam a execução

- `GITHUB_TOKEN` ausente no `.env` da raiz.
- Token inválido ou sem permissão (`HTTP 401` em `GET /user`).
- `MIN_COMMITS`/`MAX_COMMITS` fora da faixa válida.
- Repositório de destino inexistente — a mensagem manda rodar com `--setup`.

Erros `5xx` e falha de rede passam pelo `_executar_com_retry` (3 tentativas,
30s entre elas). Erros `4xx` **não** são repetidos: token, permissão e nome de
repositório não melhoram com insistência.

## Decisões

### Por que API REST e não `git commit` + `git push`

O push exigiria credencial disponível para a conta que roda a tarefa agendada —
Credential Manager, chave SSH ou PAT embutido na URL do remote —, além de um
clone local para manter sincronizado. Com a Contents API é uma requisição HTTP
com o token no header: sem clone, sem credencial de push, sem repositório local
para dessincronizar. A máquina também não tem o `gh` instalado, por isso o
`--setup` cria o repositório pela própria API.

### Por que tudo fica em `temp\`

`temp\` guarda o `estado.json` (a trava do dia), o `atividades.md` (cópia do que
foi enviado, para conferir sem abrir o GitHub) e os logs de erro. Apagar a pasta
inteira só faz o robô perder a trava do dia — e o pior caso é uma rodada extra de
commits.

Log de execução bem-sucedida não é gravado por decisão sua: em robô que roda todo
dia sem falhar, o arquivo diário só acumula lixo. Quem responde "rodou e como
terminou" é a `dbo.controle_cargas`; o arquivo de erro em `temp\` responde "por
quê", e só existe quando é preciso.

### `lib_dscs` no lugar da `marche_lib`

Mesma mecânica do 205: `sys.path.insert` da pasta que contém o pacote, e
`import lib_dscs as dl`. `IDROBO` é ao mesmo tempo o número da pasta e o
`id_carga` na tabela de controle — como o `IDCARGA` lá.

A `lib_dscs` fica em `D:\ambiente_dev\lib_dscs` e tem README próprio.

## Diagnóstico: 7 dias em branco (09/09 a 15/09/2026)

O robô **não falhou — ele nunca foi chamado**. Duas configurações da tarefa:

| Evento | Data | Mensagem |
|---|---|---|
| **332** | 13/09 12:38 | *"o usuário `PcDiego\ferna` não estava conectado quando as condições de inicialização foram atendidas"* |
| **153** | 15/09 18:41 | *"não iniciou porque perdeu a agenda. Convém usar a opção de iniciar a tarefa quando disponível"* |

Causas: `LogonType = Interactive` (só roda com o usuário logado) e
`StartWhenAvailable = False` (execução perdida é descartada, não recuperada).

### A lição: robô que não roda é silencioso

Nenhum dos registros do próprio robô acusou o problema, e isso é esperado:

- `dbo.controle_cargas` marcava `SUCCESS` — **verdade**, era o resultado da
  última execução, de 08/09. O status não envelhece sozinho.
- `temp\` não tinha log de erro — **correto**, não houve erro.
- `estado.json` apontava `ultima_execucao: 2026-09-08`.

O sinal de "parou de rodar" não está em nada que o robô escreve, e sim no
**`dta_fim` velho** na tabela e no log de eventos do Windows. Para monitorar
isso, a consulta é por atraso, não por status:

```sql
select id_carga, nome_carga, status, dta_fim,
       now() - dta_fim as tempo_desde_a_ultima_execucao
  from dbo.controle_cargas
 where flg_ativo is true
   and (dta_fim is null or dta_fim < now() - interval '2 days');
```

## Pendências

- [ ] Não há reposição retroativa: se a máquina ficar desligada o dia inteiro,
      aquele dia fica em branco no calendário. Backfill exigiria a Git Data API
      (criar commit com `author.date` no passado), que é bem mais código.

### Resolvido

- **Trava passou a usar o dia UTC** — 25/09/2026. Fecha o buraco que deixou
  24/09 branco no calendário apesar do `SUCCESS`. Ver "A trava usa o dia UTC".

- **Tarefa do Agendador corrigida** — conferido em 21/09/2026:
  `LogonType = S4U` e `StartWhenAvailable = True`, que é o que fecha os 7
  dias em branco de 09–15/09. A execução de 20/09 às 20:40 voltou `0x0`,
  com 6 commits e `SUCCESS` na `dbo.controle_cargas`.

- Tarefa `001 - Check_GitHub` cadastrada no Agendador em 05/09/2026: seg–sex às
  20:40 (`DaysOfWeek 62`, batendo com o `dias_semana={1,2,3,4,5}` da tabela),
  usuário `ferna`, "Iniciar em" preenchido. Última execução retornou `0`, o que
  confirma a propagação do exit code pelo `.bat`.

- Execução completa validada em **05/09/2026 00:21**: `--setup` criou
  `diegoscs/daily-log`, o `--force` gerou 1 commit (`docs: registra progresso
  diario`) e o `registro/atividades.md` foi criado no primeiro commit.
- **Atribuição confirmada** — `author.login = diegoscs` e e-mail
  `91844526+diegoscs@users.noreply.github.com`. É o que faz o commit contar no
  calendário; a API assina com a conta do token, sem depender do `user.email`
  do git local.
- Travamento diário testado: a segunda execução no mesmo dia saiu em
  `[ESTADO] dia 2026-09-05 ja processado (1 commit(s)) — nada a fazer`.
- `.bat` validado como ponto de entrada do Agendador (exit 0 no caminho de
  sucesso, exit 1 quando o robô termina em erro).
- Integração com `dbo.controle_cargas` validada em 05/09/2026: ciclo
  `RUNNING → SUCCESS` na execução normal e `RUNNING → ERROR` forçando um token
  inválido. `id_carga` inexistente estoura `ValueError` como esperado.
- Os valores de status são `RUNNING`/`SUCCESS`/`ERROR`, exigidos pela check
  constraint `ck_status` da tabela — a primeira versão da lib usava
  `Inicio`/`Sucesso`/`Erro` e era rejeitada pelo banco.
- Refatoração de 05/09/2026: log, retry, trava diária, leitura do `.env` e o
  cliente HTTP saíram do robô para a `lib_dscs`. O arquivo caiu de **519 para
  380 linhas** (219 de código, o resto comentário e espaçamento) e a duplicação
  do leitor de `.env` — que existia no robô e na lib — foi eliminada.
  O que sobrou é lógica da Contents API e a configuração.
- Em 08/09/2026 saíram o `PROBABILIDADE_FOLGA` e o `PULAR_FIM_DE_SEMANA`, e com
  eles a função `decidir_execucao`: quem define o dia passou a ser só o
  Agendador. Commits por dia subiram de 1–3 para 4–8. O arquivo foi de 380 para
  348 linhas.
- Log passou a ser gravado só em caso de erro, em `temp\`. Validado nos dois
  caminhos: falha gera `erro_001_check_github_<carimbo>.txt` com o log completo
  e o traceback; execução bem-sucedida não cria arquivo.

## Arquivos

```
001_check_github\
├─ 001_check_github.py     o robô
├─ 001_check_github.bat    caminhos da máquina local
└─ README.md
```

A pasta guarda só esses três. `temp\` é **criada pelo próprio robô** e contém
`estado.json` e `atividades.md` (sobrescritos a cada execução) e, quando há
falha, `erro_001_check_github_<AAAAMMDD_HHMMSS>.txt`.

A infra (log, retry, trava diária, `.env`, controle de cargas) vem toda da
[`lib_dscs`](../../lib_dscs/README.md) — o robô só tem a lógica do GitHub.

O token fica fora da pasta, no `.env` da raiz do ambiente
(`D:\ambiente_dev\.env`), junto com as demais variáveis do ambiente.
