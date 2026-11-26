# Padrão dos robôs do ambiente_dev

Todo robô novo segue este documento. Ele resume as decisões que já custaram
caro uma vez (dias em branco, projeto pausado, `SUCCESS` mentiroso) e o
esqueleto que o hub, o vigia e a `vw_saude_robos` esperam.

Ponto de partida: a pasta [`_modelo/`](_modelo).

## 0. Que tipo de processo é

Decisão de 24/11/2026: nada feito do lado pessoal (DMP) pode prejudicar cliente
(DMC). Ler o DMC é livre; **alterar** o DMC é só para processo de cliente. Todo
processo novo é de um destes três tipos, e o tipo decide onde ele mora:

| Tipo | Onde roda | Pode tocar | Exemplos |
|---|---|---|---|
| **Pessoal** | armazém (este repo, Actions) | só o DMP e os seus serviços | 001, 003, 007 (saúde do DMP), fim do Minecraft |
| **Neutro** | armazém (este repo, Actions, ou pg_cron do DMP) | lê os dois bancos; no DMC **só lê** (manter acordado, copiar, conferir) | 002, 005, 006 (saúde do DMC), vigia, sentinela de sites |
| **De clientes** | **dentro do DMC** (pg_cron do DMC) | só o DMC | monitor dos apps, teste de isolamento, avisos ao cliente |

- Robô do armazém **não altera** o DMC. Mudança no DMC só por migration, com o
  backup do dia e o teste de isolamento do app antes e depois.
- Processo de clientes não depende do DMP: se o DMP cair, ele continua.
- O tipo vai no README do robô e na página central (Mapa do ambiente_dev).

## 1. Onde roda

- **GitHub Actions, modo `CLOUD`, é o padrão.** O PC não é agendador: se o robô
  depende da máquina ligada, ele para quando ela desliga, e ninguém percebe.
- Modo `LOCAL` só quando o robô precisa de algo que só existe no PC (arquivo
  local, rede interna, Postgres `dm`). Nesse caso ele continua registrando no
  Supabase, e o README explica por que não roda na nuvem.

## 2. Estrutura

| Item | Padrão |
|---|---|
| Número | `NNN` sequencial, três dígitos. É ao mesmo tempo a pasta, o `IDCARGA` e o `id_carga` no banco. **Só ganha número o robô que existe** (cadastrado e com horário no pg_cron): ideia ou proposta fica sem número, para a lista bater com o que roda |
| Pasta | `automacoes/NNN_nome_robo/` com `NNN_nome_robo.py` e `README.md` |
| Workflow | `.github/workflows/robo_NNN_nome_robo.yml` |
| Cadastro | migration `supabase/migrations/<versão>_robos_cadastro_robo_NNN.sql` |
| Módulos próprios | só se o arquivo passar de ~400 linhas: `config_robo.py`, etc., na pasta do robô |
| Infra | sempre da [`lib_dscs`](../lib_dscs/README.md). Robô não abre conexão, não lê `.env` e não faz HTTP na mão |

## 3. Controle de cargas (obrigatório)

O registro oficial é o Supabase. Três chamadas, sempre as mesmas:

```python
dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, dta_ini, fechar=False)
# ... carga ...
dl.registrar_carga_supabase(IDCARGA, dl.STATUS_SUCESSO, dta_ini, fechar=True,
                            mensagem=resumo, qtd_itens=qtd)
# no except:
dl.registrar_carga_supabase(IDCARGA, dl.STATUS_ERRO, dta_ini, fechar=True,
                            mensagem=str(e)[:500], qtd_itens=ITENS_FEITOS)
```

- **`qtd_itens` é o trabalho que chegou ao destino.** `0` significa "não
  precisou fazer nada". No erro, vai o que foi feito até quebrar: é isso que
  impede a próxima execução de refazer um lote parcial.
- **`mensagem` é uma linha que alguém entende no celular:** `"6 commits em
  daily-log"`, `"ping ok: postgres 180 ms"`. No erro, a mensagem da exceção.
- **Registro nunca derruba o robô.** A função não levanta; se falhar, vira log.
- `--dry-run`, `--status` e `DEBUG=True` **não registram**. Não são a carga, e
  `SUCCESS` neles mentiria no monitoramento.

## 4. Uma vez por dia (quando se aplica)

- A trava é o histórico no Supabase: `dl.trabalho_feito_no_dia(IDCARGA, hoje_utc)`.
  Arquivo local (`estado.json`) não serve na nuvem: a máquina nasce vazia.
- **Na nuvem, se a trava não puder ser lida, o robô não faz o trabalho.** Sem
  saber se o dia já foi feito, o seguro é não repetir.
- **"Dia" é UTC**, a menos que o README diga outra coisa e explique por quê.

## 5. Erros, retry e log

- `validar_configuracao()` antes de qualquer rede: variável faltando estoura
  com o nome da chave, uma vez só, sem retry.
- `dl.executar_com_retry` **só** em etapa de rede (falha transitória).
  Credencial, permissão e dado inválido estouram na primeira.
- `try/except` explícito no `main()`: no `except`, registra `ERROR`, chama
  `dl.alertar_erro_robo`, `dl.salvar_log_erro()` e faz `raise` (exit 1 deixa o
  run vermelho e o GitHub manda e-mail).

### Avisos (Discord)

Decisão de 25/11/2026: o hub é o painel e o **Discord só avisa** (o Telegram
saiu da lib na 2.5.0). Canais e secrets:

| Canal | Secret | O que chega |
|---|---|---|
| `#alertas` | `DISCORD_WEBHOOK_ALERTAS` | erro de robô, atraso, site fora do ar, aviso que pede ação |
| `#resumo-diario` | `DISCORD_WEBHOOK_RESUMO` | só o vigia (resumo de manhã e de tarde) |
| `#cliente-<app>` | `DISCORD_WEBHOOK_<APP>` | o que afeta o app do cliente (hoje `#cliente-estoque`) |

- Erro: `dl.alertar_erro_robo(IDCARGA, NOME_ROBO, str(e))`, que vai para o
  `#alertas`. Se o robô cuida de um app de cliente, passe também
  `canal_cliente="estoque"`.
- Aviso que não é erro: `dl.notificar_discord(canal, titulo, detalhe)`, e
  **só quando muda**. A memória é a própria execução anterior (a `mensagem` do
  último registro no histórico), sem tabela nova. Aviso repetido todo dia vira
  ruído e ninguém lê.
- A URL do webhook é segredo: nunca vai para log, mensagem ou repositório. A
  lib não levanta exceção se o Discord falhar.
- **Log só em caso de erro.** Execução boa não deixa arquivo. No Actions, o
  `temp/erro_*.txt` sobe como artifact do run.

### Robô de saúde (só leitura)

Robô que confere um banco ou um app (como o 006 e o 007) **não altera nada**:
só `select`, chamadas de API sem efeito e páginas abertas. O que ele achar vira
aviso; a correção é uma migration revisada, nunca o próprio robô. `qtd_itens` é
o número de checagens que passaram, e `SUCCESS` com aviso é normal: `ERROR` fica para
quando a checagem em si não pôde rodar.

## 6. Workflow

Copie [`_modelo/robo_NNN_nome_robo.yml`](_modelo/robo_NNN_nome_robo.yml). O que não muda:

- Só `workflow_dispatch`, **sem `schedule`**: o do GitHub atrasa 2 a 7 h. O
  horário entra numa migration com `cron.schedule(...)` chamando
  `private.disparar_workflow('diegoscs/ambiente_dev', 'robo_NNN_nome_robo.yml')`
  ([exemplo](../supabase/migrations/20261027233340_robos_disparo_pg_cron.sql)).
  O mesmo `workflow_dispatch` é o que o botão "Rodar agora" usa.
- **Exceção: reserva.** Robô que protege os outros pode ter um `schedule`
  *a mais*, independente do pg_cron do DMP, para o caso de o próprio DMP ou o
  token do Vault falharem. Hoje: o vigia (todo dia, `--reserva`) e o keepalive
  002 (seg/qui, porque o DMC não pode dormir). Rodar a mais não pode fazer mal
  (trava diária ou trabalho idempotente) e o motivo fica num comentário no yml.
- `concurrency` por robô, `timeout-minutes`, `MODO_EXECUCAO: CLOUD`.
- Upload do log de erro com `if: failure()`.
- **Hora cheia** de São Paulo (o cron do `pg_cron` é em UTC: SP + 3), sem
  repetir a de outro robô e **antes do vigia** (09:00 e 16:00).
- **Processo leve sem Python** (só abrir uma URL, apagar linha antiga) pode
  ser função SQL + `pg_cron` (+ `pg_net`) no próprio DMP, sem gastar Actions.
  Ex.: a sentinela de sites e a retenção. Mesmo assim entra por migration, e o
  segredo que ele usar fica no Vault do DMP.

## 7. Segredos

- Nunca no código nem no repositório. No PC, `.env` da raiz (e o
  `.env.example` ganha a chave vazia com comentário). Na nuvem, secret do Actions.
- **Nome de secret não pode começar com `GITHUB_`** (o GitHub recusa).
- Prefixo novo de variável entra em `PREFIXOS_AMBIENTE` (`lib_dscs/config.py`),
  senão o robô não enxerga o valor no Actions.
- Token com o **menor escopo possível**: fine-grained, só no repositório e só
  com a permissão que o robô usa.

## 8. Banco

- Toda mudança de schema é **migration** em `supabase/migrations/`, com o nome
  igual à versão registrada no Supabase. Nada de SQL solto no painel.
- O nome da migration começa pelo schema que ela mexe: `robos_` (hub e robôs),
  `openfinance_`, `estoque_`. Ex.: `20261126190000_robos_sentinela_sites.sql`.
- Tabela nova: RLS ligada; `revoke` explícito de escrita para `anon` e
  `authenticated` (o Supabase concede tudo por padrão, e grant de coluna não
  restringe nada enquanto o de tabela existir). Se o hub precisar ler, policy
  `for select to authenticated using ((select private.eh_leitor_hub()))`.
- Horários em `timestamptz`, gravados em UTC.
- Histórico e tabelas que crescem guardam **30 dias** (`private.aplicar_retencao()`,
  todo dia). Tabela nova que cresce entra nessa função.
- Cadastro do robô em `controle_cargas` com `tempo_min`, `atraso_max_horas` e
  `workflow`. Com isso ele aparece sozinho no hub, no vigia e no botão
  "Rodar agora", sem mexer no código do hub.

## 9. Documentação

- `README.md` do robô: o que faz, origem/destino, fluxo, configuração
  (variáveis e secrets), flags, decisões e o porquê delas, estado atual com data.
- Linha nova na tabela do [README da raiz](../README.md).
- A página central (Mapa do ambiente_dev) é atualizada na mesma hora e precisa
  **bater com o `cron.job` ativo**: robô novo, horário mudado ou robô desligado
  muda o mapa.
- Incidente ou decisão que mudou o comportamento vai no README com data e
  causa, como nos READMEs do 001 e do 002.

## 10. Pronto é quando

- [ ] `--dry-run` local passa
- [ ] execução local com `MODO_EXECUCAO=CLOUD` registra no Supabase
- [ ] migration de cadastro aplicada e salva no repositório
- [ ] workflow disparado na mão termina verde, com `url_execucao` gravada
- [ ] robô aparece `OK` no hub e o vigia passa
- [ ] README do robô e da raiz atualizados
- [ ] mapa do ambiente atualizado (bate com o pg_cron)
