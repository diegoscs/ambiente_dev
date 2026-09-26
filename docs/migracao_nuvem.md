# Migração dos robôs para a nuvem

**Feita em 26/09/2026.** Os robôs 001 e 002 saíram do Agendador do Windows e
passaram a rodar no GitHub Actions, com o controle de cargas no Supabase.

## Por que

| | Antes (PC + nuvem) | Depois (tudo na nuvem) |
|---|---|---|
| Roda com o PC desligado | só o 002 | os dois |
| Onde fica o status | Postgres local `dm`, com cópia no Supabase | só no Supabase |
| Peças para manter | Agendador, `.bat`, Postgres `dm`, cópia com fila de pendências, `cadastro_carga.sql`, `.env` e o workflow | 2 workflows e os secrets |
| Como descobrir falha | `verificar_robos.ps1`, só no PC | hub no celular, e-mail do GitHub e Telegram |
| Histórico | nenhum (uma linha por robô, sobrescrita) | `historico_cargas`, uma linha por execução |
| Custo | zero | zero (repo privado tem 2.000 min/mês; isso usa uns 60) |

O que motivou: o lado do PC não cobria o caso que realmente aconteceu, que foi
a máquina desligada. O 001 teve 7 dias em branco em setembro, e o projeto do
Supabase foi pausado em 21/09 mesmo com o robô 002 "funcionando".

## O que mudou

**Supabase** ([migration](../supabase/migrations/20260926121254_robos_nuvem_historico_e_saude.sql))
- `controle_cargas` ganhou `ambiente`, `mensagem`, `url_execucao` e `atraso_max_horas`.
- `historico_cargas` nova, uma linha por execução fechada. `qtd_itens` guarda o
  trabalho feito (commits no 001, pings no 002); `0` é uma execução que saiu
  pela trava.
- `vw_saude_robos` calcula `OK`, `ERRO`, `ATRASADO`, `TRAVADO`, `RODANDO` ou
  `NUNCA_RODOU` na hora da leitura.
- Linha do robô 001 cadastrada (antes só o 002 existia lá).

**Código**
- [`lib_dscs/supabase.py`](../lib_dscs/supabase.py): `registrar_carga_supabase`
  (status e histórico), `trabalho_feito_no_dia` (trava diária), `modo_execucao`.
- 001: modo CLOUD. A trava do dia soma o que o Supabase e o `estado.json` sabem.
  Token vem de `GH_PAT` na nuvem e de `GITHUB_TOKEN` no PC. Ganhou alerta no Telegram.
- 002: grava direto no Supabase nos dois modos. O `sync_supabase.py` (cópia da
  linha local com fila de pendências) foi removido.

**GitHub Actions**
- [`robo_001_check_github.yml`](../.github/workflows/robo_001_check_github.yml): novo, diário às 03:17 UTC.
- [`robo_002_check_supabase.yml`](../.github/workflows/robo_002_check_supabase.yml):
  era o `supabase_keepalive.yml`, que rodava a cada 2 dias; agora é diário.
- Secret `GH_PAT` criado. O GitHub não aceita secret com prefixo `GITHUB_`.

**Hub**
- Artefato do Claude que lê a `vw_saude_robos` e o histórico pelo conector do
  Supabase: status por robô, calendário de 14 dias e últimas execuções, com link
  para o log de cada run e para disparar o workflow.

## Checklist

### Fase 0 · preparar
- [x] Linha `id_carga = 1` no Supabase
- [x] Secret `GH_PAT` (mesmo token do `.env`, com escrita no `daily-log`)
- [ ] Secrets `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`. Sem eles, falha na nuvem só avisa pelo e-mail do GitHub

### Fase 1 · código
- [x] Registro no Supabase na `lib_dscs`, usado pelos dois robôs
- [x] Modo CLOUD no 001, com a trava pelo histórico
- [x] Teste local em modo CLOUD: o 001 viu os 5 commits do dia pelo Supabase e não commitou de novo

### Fase 2 · workflows
- [x] Workflow do 001, disparado na mão: [run 36241476925](https://github.com/diegoscs/ambiente_dev/actions/runs/36241476925), sucesso, saiu pela trava
- [x] Workflow do 002 diário, disparado na mão: [run 36241478211](https://github.com/diegoscs/ambiente_dev/actions/runs/36241478211), sucesso
- [ ] Primeiro lote real de commits feito pela nuvem (27/09, 03:17 UTC). Conferir no hub e no calendário do perfil

### Fase 3 · tirar o PC do caminho
- [ ] Uma semana em paralelo (PC + nuvem), conferindo o hub. PC e nuvem usam a mesma trava, então não há commit dobrado
- [ ] Desativar a tarefa `ambiente_dev - Robos` no Agendador (desativar, não apagar)
- [ ] Decidir o destino do `verificar_robos.ps1`: o hub já responde "rodou? como terminou?"

### Fase 4 · alerta de "não rodou"
- [x] `vw_saude_robos` com `ATRASADO` (mais de 26 h sem execução fechada)
- [x] Hub lendo a view

## Riscos que continuam

- **O cron do GitHub atrasa.** Normalmente são minutos, às vezes uma hora; em
  picos raros um horário é pulado. Os horários ficam longe da virada do dia UTC,
  e o `ATRASADO` aparece no hub com 26 h sem execução.
- **Workflow que não roda não avisa.** O e-mail do GitHub só chega quando um run
  falha. O caso "nem rodou" é o `ATRASADO`, e só aparece para quem abre o hub.
- **Supabase fora do ar.** O 002 falha e o registro também; o run fica vermelho
  no Actions e o GitHub manda e-mail. Na nuvem o 001 **não commita** sem
  conseguir ler a trava, de propósito: sem saber se o dia já foi feito, o
  seguro é não dobrar.
