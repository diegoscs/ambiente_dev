# Hub dos Robôs

Painel de celular com a saúde dos robôs, lido ao vivo do Supabase.

**https://hub-robos.vercel.app** · privado, com login

## O que mostra

- **Status por robô**, vindo da `vw_saude_robos`: `OK`, `ERRO`, `ATRASADO`,
  `TRAVADO`, `RODANDO` ou `NUNCA RODOU`. Uma faixa no topo resume tudo.
- **Calendário dos últimos 14 dias UTC** por robô: verde com execução `SUCCESS`,
  vermelho com `ERROR`. É o mesmo "dia" que o calendário de contribuições usa.
- **Últimas execuções**, de `historico_cargas`: onde rodou (PC ou nuvem),
  resumo e duração.
- **▶ Rodar agora**, que dispara o workflow do robô no GitHub Actions, e o link
  para o log do último run. O workflow vem da coluna `workflow` de
  `controle_cargas`: robô novo cadastrado aparece com o botão sem mexer no hub.
- **Notificações** do [vigia](../automacoes/vigia_robos.py): uma por
  verificação diária (em dia, atenção ou resolvido), com contador de não lidas
  e "Marcar como lidas".
- **Troca de senha** pelo botão *Senha* no topo.

Atualiza sozinho a cada 2 minutos com a página visível, e na volta para a aba.
Instalável na tela inicial do celular (manifesto + ícone).

## Como a segurança funciona

```mermaid
flowchart LR
    P["Página<br/>chave pública"] -- "login e-mail + senha" --> AUTH["Supabase Auth"]
    P -- "SELECT com o token do login" --> RLS{"RLS:<br/>eh_leitor_hub()?"}
    RLS -- sim --> DADOS[("vw_saude_robos<br/>historico_cargas")]
    P -- "POST /api/rodar + token" --> F["Função da Vercel"]
    F -- "lê o workflow do robô<br/>com o token" --> RLS
    F -- "GH_DISPATCH_TOKEN<br/>(só no servidor)" --> GA["GitHub Actions<br/>workflow_dispatch"]
```

- **A página só tem a chave pública** do Supabase, que foi feita para ficar no
  navegador. Sem login ela não lê nada: as tabelas têm RLS, e a policy
  `hub_leitura` só libera `SELECT` para quem está em `private.hub_leitores`.
- **Quem entra em `hub_leitores`:** só por SQL. O primeiro login se cadastrou
  sozinho uma vez; depois disso o autocadastro foi removido
  (`hub_acesso_sem_autocadastro`), para que apagar a conta do dono não deixe a
  vaga aberta para o próximo cadastro. Contas novas recebem "sem acesso".
- **O leitor só lê**, e nas notificações só pode mexer na coluna `lida`. A
  escrita geral que o Supabase concede por padrão foi revogada
  (`notificacoes_hub_so_coluna_lida`); testado com um usuário simulado.
- **O token do GitHub nunca vai para a página.** Ele fica na variável
  `GH_DISPATCH_TOKEN` da Vercel. A função [`api/rodar.js`](api/rodar.js) confere
  o login no Supabase antes de disparar: lê o `workflow` do robô com o token
  do usuário (a RLS só devolve a linha para o leitor) e valida o nome do arquivo.
- **Escrita** nas tabelas continua só com a `service_role`, que só os robôs têm.
- **Página:** a biblioteca do Supabase vem do CDN com hash de integridade (SRI),
  e a Vercel manda `Content-Security-Policy` restringindo scripts, conexões e
  frames ([`vercel.json`](vercel.json)).

Migration: [`supabase/migrations/20260926123000_hub_leitura_autenticada.sql`](../supabase/migrations/20260926123000_hub_leitura_autenticada.sql).

## Configuração

| Onde | O quê |
|---|---|
| Vercel · Environment Variables | `GH_DISPATCH_TOKEN`: token **fine-grained** só do repo `ambiente_dev`, com *Actions: Read and write*. Sem ele, o botão responde "não configurado" e o resto funciona |
| Supabase · Auth | Login por e-mail e senha. Vale ligar a *Leaked password protection* |

## Deploy

Projeto `hub-robos` na Vercel (time `diegoscs-projects`), com esta pasta como
raiz. Hoje o deploy é pela CLI:

```powershell
cd D:\ambiente_dev\hub
vercel deploy --prod
```

Para deploy automático a cada push: na Vercel, **Settings → Git**, conectar
`diegoscs/ambiente_dev` e em **Settings → Build and Deployment** definir
*Root Directory* = `hub`.

## Arquivos

```
hub\
├─ index.html              a página (HTML + JS, sem build)
├─ api\rodar.js            função serverless do "Rodar agora"
├─ manifest.webmanifest    instalação na tela inicial
├─ icone.svg
├─ vercel.json             cabeçalhos de segurança
└─ .vercelignore
```

A primeira versão do hub foi um artefato do Claude que lia o Supabase pelo
conector; foi aposentada em 26/09/2026 e o código fica no histórico do git.
