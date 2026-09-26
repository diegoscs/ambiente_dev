# Padrão dos robôs do ambiente_dev

Todo robô novo segue este documento. Ele resume as decisões que já custaram
caro uma vez (dias em branco, projeto pausado, `SUCCESS` mentiroso) e o
esqueleto que o hub, o vigia e a `vw_saude_robos` esperam.

Ponto de partida: a pasta [`_modelo/`](_modelo).

## 1. Onde roda

- **GitHub Actions, modo `CLOUD`, é o padrão.** O PC não é agendador: se o robô
  depende da máquina ligada, ele para quando ela desliga, e ninguém percebe.
- Modo `LOCAL` só quando o robô precisa de algo que só existe no PC (arquivo
  local, rede interna, Postgres `dm`). Nesse caso ele continua registrando no
  Supabase, e o README explica por que não roda na nuvem.

## 2. Estrutura

| Item | Padrão |
|---|---|
| Número | `NNN` sequencial, três dígitos. É ao mesmo tempo a pasta, o `IDCARGA` e o `id_carga` no banco |
| Pasta | `automacoes/NNN_nome_robo/` com `NNN_nome_robo.py` e `README.md` |
| Workflow | `.github/workflows/robo_NNN_nome_robo.yml` |
| Cadastro | migration `supabase/migrations/<versão>_cadastro_robo_NNN.sql` |
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
- **Log só em caso de erro.** Execução boa não deixa arquivo. No Actions, o
  `temp/erro_*.txt` sobe como artifact do run.

## 6. Workflow

Copie [`_modelo/robo_NNN_nome_robo.yml`](_modelo/robo_NNN_nome_robo.yml). O que não muda:

- `schedule` com **minuto quebrado** e horário em UTC comentado com o de São
  Paulo, mais `workflow_dispatch` (é o que o botão "Rodar agora" usa).
- `concurrency` por robô, `timeout-minutes`, `MODO_EXECUCAO: CLOUD`.
- Upload do log de erro com `if: failure()`.
- Horário longe dos outros robôs e **antes do vigia** (13:07 UTC).

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
- Tabela nova: RLS ligada; `revoke` explícito de escrita para `anon` e
  `authenticated` (o Supabase concede tudo por padrão, e grant de coluna não
  restringe nada enquanto o de tabela existir). Se o hub precisar ler, policy
  `for select to authenticated using ((select private.eh_leitor_hub()))`.
- Horários em `timestamptz`, gravados em UTC.
- Cadastro do robô em `controle_cargas` com `tempo_min`, `atraso_max_horas` e
  `workflow`. Com isso ele aparece sozinho no hub, no vigia e no botão
  "Rodar agora", sem mexer no código do hub.

## 9. Documentação

- `README.md` do robô: o que faz, origem/destino, fluxo, configuração
  (variáveis e secrets), flags, decisões e o porquê delas, estado atual com data.
- Linha nova na tabela do [README da raiz](../README.md).
- Incidente ou decisão que mudou o comportamento vai no README com data e
  causa, como nos READMEs do 001 e do 002.

## 10. Pronto é quando

- [ ] `--dry-run` local passa
- [ ] execução local com `MODO_EXECUCAO=CLOUD` registra no Supabase
- [ ] migration de cadastro aplicada e salva no repositório
- [ ] workflow disparado na mão termina verde, com `url_execucao` gravada
- [ ] robô aparece `OK` no hub e o vigia passa
- [ ] README do robô e da raiz atualizados
