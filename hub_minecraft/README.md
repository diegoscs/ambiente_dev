# Hub do servidor (Server da Galera)

Página pública, para celular, do servidor de Minecraft da galera.

**https://server-galera.vercel.app** · sem login · instalável no iPhone
(Safari → Compartilhar → Adicionar à Tela de Início)

## O que mostra

- **Status**: ONLINE, LIGANDO, DESLIGANDO, DESLIGADO, FORA DO AR ou SEM SINAL,
  juntando o estado da VM (API do Google) com a linha do monitor.
- **Endereço** com botão de copiar: o DuckDNS quando aponta para o IP atual da
  VM; senão, o IP de agora.
- **Ligar o servidor** (só com a VM desligada) e **contagem regressiva** do
  desligamento automático: 5 min depois que o último sai, 15 min logo após
  ligar ("vazio há 2 min, desliga sozinho em ~3 min").
- Jogadores online e **quem jogou hoje**, com o tempo de cada um.
- **Hora, dia e clima do jogo** no card de status ("🕐 15:41 no jogo · dia 63 · ☀️ sol").
- **Chat e comandos** (abas Tudo, Chat, Comandos, Mortes, Entradas). Mortes
  com ☠ e as frases mais comuns traduzidas. Comandos de senha nunca aparecem;
  mensagem privada aparece sem o conteúdo; comando do console/RCON (admin)
  não aparece. Todo comando de jogador aparece com o **efeito** verificado
  pelo servidor: "nada foi alterado" (recusado, ex.: sem permissão) ou
  "✓ virou criativo" (no `/gamemode`, o modo antes e depois é conferido).
- **Ranking da galera**: tempo, mortes, mobs, distância, blocos, conquistas e
  PvP, das estatísticas do próprio Minecraft (`minecraft_jogadores`).
- **Desempenho**: TPS com rótulo (sem lag / lag leve / lag forte), tempo por
  tick, CPU e memória, e gráfico de ms/tick das últimas 6 h com a linha de
  50 ms (`minecraft_desempenho`, 7 dias).
- **Custo** estimado: mês, hoje, por hora, créditos do teste e horas ligado
  por dia (14 dias).
- **Backups** do mundo e um **registro** de liga/desliga/backup.
- **Como entrar** (TLauncher, `/register`, `/login`).

## Como funciona sem login

A página não fala com o banco nem com o Google. Ela chama duas funções da
Vercel, que guardam as credenciais:

| Função | O quê | Proteção |
|---|---|---|
| [`api/estado.js`](api/estado.js) | Junta VM, status, eventos, sessões, backups, pedidos e custo | Cache de 15 s na Vercel: atualizar sem parar não chega ao Supabase/Google |
| [`api/ligar.js`](api/ligar.js) | Liga a VM | Só com a VM desligada; 2 min entre pedidos; até 8 por dia. A conta do Google só liga e consulta essa VM |

Mesmo com abuso do botão, a VM desliga sozinha se ninguém entrar em 15 min. Todo
texto do jogo entra na página como texto puro (`textContent`), nunca HTML.
O CSP só deixa a página falar com o próprio site.

**Privacidade:** quem tiver o link vê o chat. A página não é indexada
(`noindex`), mas não tem senha.

## Configuração (Vercel, projeto `server-galera`)

| Variável | O quê |
|---|---|
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_SERVICE_KEY` | Chave de serviço (lê/escreve `minecraft_*`) |
| `GCP_SA_KEY` | JSON da chave da conta `hub-minecraft` (papel `minecraftHub`: get + start na VM) |
| `USD_BRL` | (opcional) cotação para o custo; padrão 5,4 |

Preços do custo estimado: constantes no topo de `api/estado.js` (fonte:
tabelas públicas do GCP para São Paulo, out/2026).

## Deploy

```powershell
cd D:\ambiente_dev\hub_minecraft
vercel deploy --prod
```

Detalhes da VM, do monitor e da trava de 15 min:
[automacoes/minecraft_gcp](../automacoes/minecraft_gcp/README.md).
