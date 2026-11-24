# Kit de cliente novo

Objetivo para começar 2027: ganhou um cliente, o app dele nasce pronto. Banco,
monitoramento e canal no Discord, sem passos esquecidos. Decidido em 24/11/2026;
a construir.

**Regra (24/11/2026): tudo de cliente fica dentro do DMC.** O DMP é pessoal
(hub, robôs, finanças) e não guarda nada de cliente.

## Dentro do DMC

Schema **`plataforma`** (o nome que você já tinha dado a esse assunto; cobrança
e assinaturas entram aqui quando chegar a hora):

| Tabela | O que guarda |
|---|---|
| `plataforma.apps` | o cadastro: `slug` (ex.: `estoque`), nome, url, schema, repo, Edge Functions, ativo |
| `plataforma.saude` | um retrato por app por checagem: site no ar e tempo de resposta, funções respondendo, métricas do app, situação (ok, atenção, erro) |
| `plataforma.avisos` | o que já foi avisado, para não repetir o mesmo aviso toda hora |

Cada app expõe uma função **`<schema>.saude()`** que devolve as métricas dele
(no estoque: negócios ativos, assinaturas vencendo, último lançamento). O
monitor não precisa conhecer as tabelas de cada app.

## O monitor roda no próprio DMC

```
pg_cron (DMC), de hora em hora
  ├─ :00  para cada app ativo: pg_net acessa o site e as Edge Functions
  └─ :05  lê as respostas, chama <schema>.saude(), grava plataforma.saude
          └─ problema novo? pg_net manda no #cliente-<slug> (webhook no Vault do DMC)
```

Sem GitHub Actions e sem chave do DMC fora dele.

**Onde você vê:** aba "Saúde" no `/admin` da plataforma (já existe, já mora no
DMC, já é só seu). O hub continua só com os seus robôs.

## Cliente novo: `novo_cliente.py`

Um comando que:
1. gera a migration da linha em `plataforma.apps` e o esqueleto do schema do
   cliente (com `saude()` já pronta);
2. cria o canal `#cliente-<slug>` e o webhook dele (bot do Discord) e guarda o
   webhook no Vault do DMC;
3. imprime o que continua manual, com os valores prontos para colar: projeto na
   Vercel, variáveis e Data API → Exposed schemas.

## As duas pontes com o lado de fora (e por quê)

| Ponte | Por que não fica no DMC | O que toca |
|---|---|---|
| **002 · keepalive** | projeto grátis precisa de acesso de fora para não pausar; e um monitor dentro do DMC não consegue avisar que o DMC caiu | lê no DMC a hora da última checagem do monitor: velha = alerta no `#alertas` |
| **005 · backup** | backup dentro do próprio projeto não protege de nada | copia o DMC para o repo privado |

Nenhuma das duas guarda dado de cliente no DMP; o DMP só registra que o robô
rodou.

## O que continua manual

- Projeto na Vercel e domínio (sua conta, repositório certo).
- Data API → Exposed schemas no DMC (só pelo painel).

## Ordem

1. `plataforma` no DMC (apps, saude, avisos) + `estoque.saude()` + monitor no
   pg_cron do DMC, com o estoque como primeiro app (antes de 12/12).
2. 002 lendo a hora da última checagem (antes de 12/12).
3. Discord: servidor, bot, `#alertas`, `#resumo-diario`, `#cliente-estoque`.
4. Aba "Saúde" no `/admin`.
5. `novo_cliente.py`.
6. App modelo (janeiro): template a partir do estoque, com login, `/admin`,
   assinatura, RLS por negócio e `saude()` prontos.
