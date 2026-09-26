# Hub dos Robôs

Painel de celular com a saúde dos robôs, lido ao vivo do Supabase. Publicado
como **artefato do Claude**: abre no claude.ai ou no app do Claude, no celular
inclusive.

## O que mostra

- **Status por robô**, vindo da `vw_saude_robos`: `OK`, `ERRO`, `ATRASADO`,
  `TRAVADO`, `RODANDO` ou `NUNCA RODOU`. Uma faixa no topo resume tudo.
- **Calendário dos últimos 14 dias UTC** por robô: verde com execução `SUCCESS`,
  vermelho com `ERROR`. É o mesmo "dia" que o calendário de contribuições usa.
- **Últimas execuções**, de `historico_cargas`: onde rodou (PC ou nuvem),
  resumo e duração.
- Links para o **log do último run** no Actions e para **rodar o workflow agora**.

Atualiza sozinho a cada 2 minutos com a página visível, e na volta para a aba.

## Como lê os dados sem expor chave

A página não tem chave nenhuma. Ela declara a capacidade `mcp` do artefato e
chama a ferramenta `execute_sql` do **conector do Supabase da conta de quem
abre**, com uma consulta fixa, só de leitura. As tabelas continuam com RLS
ligada e sem policy: a chave pública do projeto não lê nada.

A consequência é que só quem tem o conector do Supabase com acesso ao projeto
consegue ver os dados. Para qualquer outra pessoa a página mostra o aviso de
conector ausente.

## Arquivo

[`hub_robos.html`](hub_robos.html) é a fonte publicada. Fora do Claude a página
abre, mas mostra só o aviso: `window.claude` não existe num navegador comum.
