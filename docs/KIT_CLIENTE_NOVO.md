# Kit de cliente novo

Objetivo para começar 2027: ganhou um cliente, o app dele nasce pronto. Banco
no DMC, monitoramento no hub e no vigia, canal no Discord e a página central
atualizada, sem passos esquecidos. Decidido em 24/11/2026; a construir.

## A ideia central: um cadastro de apps

Hoje o monitoramento conhece robôs (`controle_cargas`). Ele passa a conhecer
**apps de clientes** também, por uma tabela pequena no DMP:

| Coluna | Exemplo | Para quê |
|---|---|---|
| `slug` | `estoque` | nome curto: schema no DMC, canal `#cliente-estoque`, secrets |
| `nome` | Estoque | como aparece no hub e no Discord |
| `url` | https://estoque-tattoo-rho.vercel.app | o que o robô de saúde acessa |
| `projeto` | `DMC` | banco onde mora (hoje sempre o DMC) |
| `schema` | `estoque` | schema do app no banco |
| `repo` | diegoscs/estoque-tattoo | onde está o código |
| `funcoes` | `{estoque-admin}` | Edge Functions que precisam responder |
| `ativo` | true | desligar o monitoramento sem apagar |

Cliente novo = **uma linha nessa tabela** (por migration). Daí em diante, tudo
o que lê o cadastro passa a cuidar do app sozinho.

```
cadastro (DMP) ──> robô 006 · Saúde dos apps ──> saude_apps (DMP) ──> hub (card Clientes)
                         │                                       └──> vigia
                         └──> Discord: #cliente-<slug> e #alertas
```

## Peças

1. **`public.apps_clientes`** (cadastro) e **`public.saude_apps`** (um retrato
   por app por dia: site no ar e tempo de resposta, banco respondendo, tamanho,
   negócios ativos, assinaturas vencendo, último uso, Edge Functions ok).
   RLS ligada, leitura só para o hub (`eh_leitor_hub`), escrita só pela chave de
   serviço.
2. **Robô 006 · Saúde dos apps** (Actions, pg_cron, no padrão): para cada app
   ativo do cadastro, confere tudo acima e grava em `saude_apps`. Problema vira
   aviso no hub e no canal do app. Registra em `controle_cargas` como os outros.
   Só ele tem a chave do DMC; o hub continua sem nenhuma.
3. **Vigia**: além dos robôs, lê o retrato do dia de cada app.
4. **Hub**: card "Clientes", um bloco por app (verde, amarelo, vermelho).
5. **Discord** ([plano](PLANO_DISCORD.md)): para criar canal sozinho, o webhook
   não basta. Entra um **bot** com permissão de criar canais e webhooks; o
   token dele fica em secret.
6. **`novo_cliente.py`** (o kit): um comando que
   - cria a linha no cadastro (gera a migration);
   - cria o canal `#cliente-<slug>` e o webhook dele no Discord;
   - lista o que falta fazer à mão (projeto na Vercel, variáveis, Data API) com
     os valores certos já preenchidos.
7. **App modelo** (depois): repositório template a partir do estoque, com
   login, `/admin`, assinatura e RLS por negócio prontos. O schema do cliente
   nasce de uma migration base, com o nome dele na frente.

## O que continua manual (e por quê)

- **Projeto na Vercel e domínio**: precisa da sua conta e do repositório certo;
  o kit imprime os valores para colar.
- **Data API → Exposed schemas** no DMC: só pelo painel (sem token de
  gerenciamento no PC). O kit lembra e o 006 acusa se ficou faltando.

## Ordem

1. Cadastro + `saude_apps` + robô 006, com o estoque como primeiro app (antes de 12/12).
2. Vigia e card no hub lendo o retrato (antes de 12/12).
3. Discord: servidor, bot, `#alertas`, `#resumo-diario`, `#cliente-estoque`.
4. `novo_cliente.py`.
5. App modelo (janeiro).
