# Radar de ofertas

Lê canais públicos de promoção do Telegram e avisa no Discord quando sai
oferta de um produto da lista. Pedido de 27/11/2026 (Black Friday): o usuário
não tem notificação do Telegram no celular e quer saber na hora quando o
Ryzen 7 5700X entrar em promoção.

- **Tipo:** pessoal (só o DMP).
- **Onde roda:** dentro do DMP, com `pg_cron` a cada 20 s e `pg_net`, igual à
  sentinela de sites. Não usa o Actions: ali o aviso levaria minutos, só para
  subir a máquina.
- **Sem número de robô:** não passa pelo `controle_cargas` (seriam 4.300
  execuções por dia no hub). A saúde dele é a própria `radar_fontes`, e uma
  falha longa avisa no `#alertas`.
- **Código:** [20261127170000_robos_radar_ofertas.sql](../supabase/migrations/20261127170000_robos_radar_ofertas.sql)
  (tabelas e funções) e [20261127170100_robos_radar_ofertas_agenda.sql](../supabase/migrations/20261127170100_robos_radar_ofertas_agenda.sql)
  (liga o job).

## Como funciona

1. A cada 20 s, `private.radar_rodada()` pede
   `https://t.me/s/<canal>?after=<último post lido>`. É a página pública do
   canal, sem login, e ela traz até 20 posts seguintes, do mais antigo para o
   mais novo.
2. Na rodada seguinte, ela lê a resposta, separa os posts e confere cada um
   contra `private.radar_produtos`.
3. Quando um produto bate, grava em `private.radar_avisos` e manda um embed
   no Discord com o título, o preço, o texto do post (com o link da loja) e o
   link do post.
4. A unique `(produto, canal, post)` garante um aviso por oferta.

O aviso chega **20 a 40 s depois do post**. Se o canal postar mais de 20 por
rodada, a próxima página vem na rodada seguinte: atrasa um pouco, mas nada se
perde.

### Regra dos termos

O texto do post é comparado em minúsculas e sem acento.

| Campo | Regra |
|---|---|
| `termos` | **todos** precisam aparecer. `'a\|b'` = um ou outro |
| `excluir` | se **qualquer um** aparecer, o post é descartado |
| `preco_max` | só avisa se o primeiro "R$" do post for menor ou igual a ele (post sem preço avisa mesmo assim). `null` = qualquer preço |

Um termo não casa no meio de outra palavra ou número: `5700x` pega "5700X",
"5700 x" e "R7 5700X", mas não "5700X3D" nem "5700G". O `5700x3d` no
`excluir` cobre o "5700X 3D" escrito separado.

## Uso no dia a dia (SQL Editor do DMP)

```sql
-- produto novo
insert into private.radar_produtos (nome, termos, excluir, preco_max)
values ('RTX 4060', '{4060}', '{4060 ti|notebook}', 1800);

-- não quer kit (placa-mãe + processador) do 5700X
update private.radar_produtos set excluir = '{5700x3d,placa mae|kit}' where nome = 'Ryzen 7 5700X';

-- pausar / voltar um produto
update private.radar_produtos set ativo = false where nome = 'Ryzen 7 5700X';

-- outro canal do Telegram (precisa ser público: t.me/s/<nome> abre no navegador)
insert into private.radar_fontes (canal_telegram) values ('NomeDoCanal');

-- o que já foi avisado
select a.avisado_em, p.nome, a.preco, a.canal_telegram, a.id_post
  from private.radar_avisos a join private.radar_produtos p on p.id = a.id_produto
 order by a.avisado_em desc limit 20;

-- saúde da leitura
select canal_telegram, estado, falhas_seguidas, ultimo_post, lido_em from private.radar_fontes;

-- desligar tudo
select cron.unschedule('radar_ofertas');
```

Canal novo do Telegram começa pelos 20 posts mais recentes (`ultimo_post`
nulo), e o que bater entre eles já avisa.

## Canal do Discord

Hoje tudo vai para o `#alertas`. Para ter um `#ofertas`:

1. Criar o canal e um webhook nele.
2. No Vault do DMP, criar o segredo `discord_webhook_ofertas` com a URL. Essa
   parte é do usuário: a URL é segredo e não passa pelo Claude.
3. Rodar `update private.radar_produtos set canal = 'ofertas';`

Enquanto o segredo não existir, o aviso cai no `#alertas`.

## Limites conhecidos

- **Só canal público.** Grupo ou canal privado precisa de login com a conta
  do Telegram (Telethon, chave de sessão) e de um processo ligado o tempo
  todo, coisa que não temos.
- **Depende do HTML do t.me/s.** Se o Telegram mudar a página, a rodada não
  acha o cabeçalho do canal e conta como falha. Em 5 min seguidos chega o
  aviso "Radar de ofertas sem ler" no `#alertas`.
- **O pg_net não confirma se o Discord recebeu.** Se o webhook falhar, aquele
  aviso se perde. A oferta continua registrada em `radar_avisos`.
- **O preço é o primeiro "R$" do post.** Em posts com "de R$ X por R$ Y", ele
  pega o X.

## Estado

- **27/11/2026:** parse testado no DMP com a resposta real do canal
  (`?after=49530`): 13 posts, preços certos, e só os posts 49539 (5700X a
  R$ 855) e 49543 (kit com 5700X a R$ 1569) marcariam aviso. As migrations
  ainda **não estão aplicadas**: o MCP do Supabase recusou o
  `apply_migration` nesta sessão, e falta aplicar pelo SQL Editor. Com
  `ultimo_post` = 49530, a primeira rodada manda esses dois avisos de
  verdade, que servem de teste do caminho todo.
