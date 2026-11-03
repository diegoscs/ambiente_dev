# Tutorial: servidor da galera no Google Cloud

O servidor saiu do PC de casa e roda numa máquina virtual (VM) do Google em
São Paulo. Não precisa mais de Radmin VPN.

---

## Parte 1: entrar no servidor (todo mundo)

### Uma vez só

1. **TLauncher:** o mesmo modpack de sempre, **Create Chronicles: The Endventure**
   (aba Pacotes de mod). Nada muda no jogo de ninguém.
2. **RAM:** engrenagem do TLauncher → Memória → **6144 MB** ou mais.
2b. **Mod extra, obrigatório: Tom's Simple Storage 1.21-2.4.2.** Baixe em
   https://modrinth.com/mod/toms-storage/version/WQAMoIMC e coloque o
   `toms_storage-1.21-2.4.2.jar` em
   `%APPDATA%\.minecraft\versions\Create Chronicles The End Create Chronicles- The En\mods`
   (cole o caminho na barra do Explorador de Arquivos). Sem ele, o servidor recusa a entrada.
   Mesma versão para todo mundo: o servidor tem a 2.4.2 desde 20/10/2026.
3. **Multijogador → Adicionar servidor:**
   - Nome: `Server da galera`
   - Endereço: **`servercasaonlymine.duckdns.org`**
     (enquanto o DuckDNS não estiver ligado, use o IP que o Diego passar no
     grupo; o IP muda cada vez que a máquina liga)
4. **Pode desligar a Radmin VPN:** não precisa mais.

### Primeira vez que entrar

O servidor agora pede senha, porque o TLauncher não tem login da Mojang e
qualquer um poderia entrar com o seu nick. Ao entrar, a tela fica escura e
aparece um aviso. Digite no chat (tecla `T`):

```
/register suaSenha suaSenha
```

(a mesma senha duas vezes). Você tem **60 segundos**; se demorar, é expulso e
é só entrar de novo.

### Das próximas vezes

```
/login suaSenha
```

Esqueceu a senha? O Diego apaga pelo console (`/loadmin delete NICK`) e você
registra de novo.

### Ficou parado? É desconectado

Quem fica **10 minutos sem mexer a câmera, falar ou mexer em blocos** é
desconectado (com aviso no chat aos 8 minutos), para o servidor não ficar
ligado à toa. É só entrar de novo. Farm AFK não funciona por causa disso.

### O servidor está desligado?

Ele **desliga sozinho 5 minutos depois que o último sai**, para economizar
(logo depois de ligar, espera até 15 minutos pelo primeiro).
Para ligar, peça ao Diego (ou use o botão Ligar do hub, quando estiver pronto).
Leva uns **2 minutos** até dar para entrar.

---

## Parte 1b: servidor Pixelmon (desde 28/10/2026)

É um servidor separado: outro mundo, outra máquina, outro botão Ligar (aba
**Pixelmon** no hub, ou o link `https://server-galera.vercel.app/?s=pixelmon`).

### Uma vez só

1. **TLauncher → Pacotes de mod → The Pixelmon Modpack, versão 9.4.1.**
   Tem que ser a 9.4.1: o servidor é 9.4.1 e o jogo recusa versão diferente.
   O pack já traz tudo (Pixelmon, Waystones, bússolas, mapa, biomas). Os mods
   só de tela (JEI, Essential, menu) ficam só no seu PC; tudo bem.
2. **RAM:** 6144 MB ou mais (engrenagem do TLauncher).
3. **Único mod extra: Tom's Simple Storage 1.21-2.4.2**, o mesmo arquivo do
   Create (https://modrinth.com/mod/toms-storage/version/WQAMoIMC). Coloque o
   `toms_storage-1.21-2.4.2.jar` em
   `%APPDATA%\.minecraft\versions\The Pixelmon Modpack 9.4.1\mods`.
   Sem ele, o servidor recusa a entrada.
4. **Multijogador → Adicionar servidor:** nome `Pixelmon da galera`, endereço
   = o IP da aba Pixelmon do hub (botão Copiar). **O IP muda cada vez que liga:**
   se não conectar, copie de novo e edite o servidor.

### Ao entrar

Igual ao Create: `/register senha senha` na primeira vez (senha nova, não é
a do Create), depois `/login senha`. Desliga sozinho 5 min depois que o último
sai (15 min logo depois de ligar). Quem fica 10 min parado é desconectado
pelo próprio Minecraft, **sem aviso antes**. Leva ~3 min para dar para entrar
depois de apertar Ligar.

---

## Parte 2: administrar pelo Google Cloud (Diego)

Console do Pixelmon pelo PC: `apps\minecraft\gcp\console_pixelmon.bat`
(pelo site: linha **`pixelmon`** em Instâncias de VM → SSH, mesmos comandos).
A whitelist dele já tem os seis nicks; nick novo precisa do UUID offline
(mesma armadilha do Create).

Tudo fica no projeto **`serverminecasaonly`**, em
https://console.cloud.google.com (conta `ds023203@gmail.com`).

### Ligar e desligar a máquina pelo site

1. Menu ☰ → **Compute Engine → Instâncias de VM**.
2. Linha **`minecraft`**:
   - **Iniciar/retomar** (▶): liga. O servidor sobe sozinho em ~1 minuto.
   - **Parar** (■): desliga. O sistema manda `stop` ao servidor e salva o
     mundo antes de cair.
   - **IP externo:** aparece na coluna da direita com a VM ligada.
3. Status `Em execução` = ligada e cobrando por hora; `Encerrada` = desligada,
   só o disco cobra (centavos por dia).

> **Nunca use "Excluir"** na VM nem no disco: o mundo está lá. A VM tem trava
> contra exclusão justamente por isso.

### Abrir o console do servidor (como a janela do start.bat)

**Pelo PC:** dois cliques em `apps\minecraft\gcp\console.bat`.

**Pelo site (de qualquer computador):**
1. Instâncias de VM → linha `minecraft` → botão **SSH**. Abre um terminal
   no navegador.
2. Digite:
   ```
   sudo -u minecraft tmux attach -t mc
   ```
3. Pronto: é o console. Comandos normais (`list`, `whitelist add NICK`,
   `say oi`, `op NICK`...).
4. **Para sair sem desligar o servidor:** `Ctrl+B`, solta, depois `D`.
   (Fechar a aba também só sai do console.) **Não use `Ctrl+C`**: derruba o
   servidor (ele volta sozinho em 15 s).

### Comandos úteis no console

| Comando | O que faz |
|---|---|
| `list` | Quem está online |
| `whitelist add NICK` | Libera um jogador novo (nick idêntico ao do TLauncher). **Atenção:** se existir uma conta original da Mojang com esse nick, o servidor grava o ID dela e o jogador do TLauncher é barrado. Confira no `whitelist.json`: o ID certo tem `3` no começo do terceiro bloco (ex.: `...-36f7-...`). Se vier com `4`, peça ao Claude para corrigir (foi o caso do Darak) |
| `loadmin delete NICK` | Apaga a senha de alguém que esqueceu |
| `save-all` | Força salvar o mundo |
| `stop` | Para o servidor (a VM continua ligada e cobrando!) |

### Comandos úteis no terminal SSH (fora do console)

| Comando | O que faz |
|---|---|
| `sudo systemctl status minecraft` | O servidor está rodando? |
| `sudo systemctl restart minecraft` | Reinicia o servidor |
| `sudo tail -f /opt/minecraft/server/logs/latest.log` | Log ao vivo (`Ctrl+C` sai) |
| `sudo ls -lh /opt/minecraft/backups` | Backups locais do mundo |

### Quanto está custando

- Menu ☰ → **Faturamento → Relatórios**: gasto por dia (atualiza com algumas
  horas de atraso).
- **Faturamento → Créditos**: quanto sobra dos US$ 300 do teste.
- Alerta por e-mail configurado em **R$ 550/mês**
  (Faturamento → Orçamentos e alertas).
- Referência: ligada ≈ **US$ 0,25/hora**; desligada ≈ US$ 0,15/dia (disco).

### Onde fica cada coisa na VM

| Caminho | O quê |
|---|---|
| `/opt/minecraft/server` | O servidor (mods, configs, `world`) |
| `/opt/minecraft/backups` | Backups do mundo, um a cada start (guarda 10) |
| `/opt/minecraft/iniciar.sh` | O "start.bat" do Linux |
| `/etc/systemd/system/minecraft.service` | Serviço que sobe o servidor quando a VM liga |

### Voltar para o PC de casa (se um dia precisar)

1. Baixe o mundo da VM (peça ao Claude, ou copie `/opt/minecraft/server/world`).
2. Reinstale o servidor em `apps\minecraft\local\server` (o do PC foi apagado
   em 02/11/2026: pacote "Create Chronicles The Endventure 2.0.0 SERVER" do
   CurseForge) e coloque o mundo em `server\world`.
3. Reative as tarefas no Agendador do Windows: "Monitor Minecraft (hub)" e
   "Minecraft Server (hub)".
