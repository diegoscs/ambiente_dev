# Plano: notificações no Discord

Decidido em 24/11/2026. Ainda não implementado.

## Papel de cada um

| | Hub dos robôs (hub-robos, Vercel) | Discord |
|---|---|---|
| Para quê | **investigar e acompanhar** | **avisar** |
| O que mostra | saúde de todos os robôs, histórico, métricas, Minecraft | erros, atrasos, resumo do dia, eventos de cliente |
| Ações | botão "rodar agora" | nenhuma (só leitura e aviso no celular) |
| Quando usar | quando quiser olhar o panorama ou chegou um aviso | chega sozinho |

O hub continua como está. O Discord ocupa o lugar do Telegram, que nunca foi
configurado (os workflows passam `TELEGRAM_*`, mas os secrets não existem).

## Canais

| Canal | O que chega | Quem manda |
|---|---|---|
| `#alertas` | qualquer robô em ERROR, robô ATRASADO, token de disparo perto de vencer | robôs (pela `lib_dscs`) e vigia |
| `#resumo-diario` | um resumo por dia: robôs ok/erro/atrasados, última execução de cada um | vigia (já roda todo dia) |
| `#cliente-estoque` | falha que afeta o app do estoque (keepalive/backup do DMC, Edge Function), cliente novo, Pix registrado, assinatura vencendo ou vencida | robôs do DMC e o próprio DMC |
| `#cliente-<nome>` | o mesmo, para cada cliente novo | idem |

Erro de um robô de cliente vai para `#alertas` **e** para o canal do cliente.

## Como funciona (sem servidor ligado, sem custo)

- **Um webhook do Discord por canal.** A URL do webhook é segredo: GitHub
  Secrets com prefixo novo `DISCORD_` (incluir em `PREFIXOS_AMBIENTE`) e, para o
  que sai do banco, o Vault do projeto.
  - `DISCORD_WEBHOOK_ALERTAS`, `DISCORD_WEBHOOK_RESUMO`, `DISCORD_WEBHOOK_ESTOQUE`
- **`lib_dscs`:** `dl.notificar_discord(canal, titulo, detalhe)` no lugar do
  Telegram em `alertar_erro_robo`. Sem webhook configurado, só loga (como hoje).
- **Canal do cliente por robô:** coluna `canal_discord` em `controle_cargas`
  (nulo = só `#alertas`; `estoque` = também `#cliente-estoque`). Robô novo de
  cliente já nasce com o canal no cadastro.
- **Resumo diário:** o vigia (`vigia_robos.py`, 12:00 UTC) monta a mensagem da
  `vw_saude_robos` e manda para `#resumo-diario`.
- **Eventos do estoque:** no DMC, trigger em `estoque.admin_eventos` (cliente
  criado, Pix, senha provisória) chama o webhook pelo `pg_net`, com a URL no
  Vault do DMC. Assinatura vencendo: robô de saúde do DMC (006), uma vez por dia.

## Ordem de implementação

1. Você cria o servidor, os 3 canais e um webhook em cada (Configurações do
   canal → Integrações → Webhooks) e cadastra as URLs como secrets.
2. `#alertas`: função na `lib_dscs` + vigia avisando atrasos. Teste com um robô
   de teste que termina em ERROR de propósito (o `--dry-run` não registra nem avisa).
3. `#resumo-diario` pelo vigia.
4. Robô 006 (saúde do DMC) + `#cliente-estoque` + trigger dos eventos do estoque.
5. Cliente novo = canal + webhook + secret + `canal_discord` no cadastro.

## Cuidados

- URL de webhook permite postar no canal: nunca no repositório (público) nem
  em log.
- Mensagem sem dado pessoal de cliente (nome do negócio pode, e-mail não).
- Discord limita a ~30 mensagens por minuto por webhook: o vigia agrupa os
  atrasos numa mensagem só.
