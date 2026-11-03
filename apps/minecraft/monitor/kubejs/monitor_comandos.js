// Registra no log do KubeJS (logs/kubejs/server.log) os comandos digitados por
// jogador, para o monitor do hub (apps/minecraft/monitor).
// O Minecraft sozinho so registra comando de op com retorno para os admins.
// O horario vai na linha em UTC porque o log do KubeJS so tem hora, sem data.
//
// O hub e PUBLICO: comando de senha (mod Login System) NAO e registrado, e
// mensagem privada sai so com o destinatario. (Em 19/10/2026 o /register com a
// senha chegou ao hub por este script; o monitor tem um segundo filtro igual.)
//
// Cada linha leva o EFEITO do comando, para o hub mostrar se mudou algo:
//   [sem_efeito]  o jogo recusou (sem permissao/comando invalido) ou nada mudou
//   [mudou:x]     verificado que mudou (no /gamemode: o modo antes e depois)
//   [ok]          aceito pelo jogo, efeito nao verificado
// Formato: [monitor_minecraft] CMD <iso> <nick> [<efeito>] /<comando>
const SENHA = ['register', 'reg', 'login', 'l', 'changepassword', 'changepass', 'cp', 'loginadmin', 'loadmin', 'password', 'senha']
const PRIVADO = ['msg', 'tell', 'w', 'whisper', 'm', 'r', 'reply', 'teammsg', 'tm']

function modoDe(jogador) {
  try { return String(jogador.gameMode.getGameModeForPlayer().getName()) } catch (e) { return null }
}

ServerEvents.command(event => {
  const source = event.parseResults.context.source
  if (!source.player) return // console, RCON e bloco de comando ficam de fora
  const partes = String(event.input).trim().split(/\s+/)
  const nome = partes[0].replace(/^\//, '').toLowerCase().split(':').pop()
  if (SENHA.indexOf(nome) >= 0) return
  let comando = '/' + partes.join(' ').replace(/^\//, '')
  if (PRIVADO.indexOf(nome) >= 0) {
    const semAlvo = ['r', 'reply', 'teammsg', 'tm'].indexOf(nome) >= 0
    comando = '/' + nome + (semAlvo || partes.length < 2 ? '' : ' ' + partes[1]) + ' (mensagem privada)'
  }
  const quando = new Date().toISOString()
  const quem = source.textName
  const registrar = efeito => console.info(`[monitor_minecraft] CMD ${quando} ${quem} [${efeito}] ${comando}`)

  // O jogo nao conseguiu interpretar (sem permissao vira "comando desconhecido").
  let aceito = true
  try {
    const pr = event.parseResults
    aceito = !pr.reader.canRead() && pr.exceptions.isEmpty()
  } catch (e) { /* sem como saber: segue como aceito */ }
  if (!aceito) { registrar('sem_efeito'); return }

  // /gamemode: confere o modo de jogo do alvo antes e logo depois de executar.
  if (nome === 'gamemode') {
    let alvo = source.player
    if (partes.length > 2) {
      try { alvo = source.server.playerList.getPlayerByName(partes[2]) } catch (e) { alvo = null }
    }
    const antes = alvo ? modoDe(alvo) : null
    if (antes) {
      try {
        source.server.scheduleInTicks(2, () => {
          const depois = modoDe(alvo)
          registrar(!depois ? 'ok' : depois === antes ? 'sem_efeito' : 'mudou:' + depois)
        })
        return
      } catch (e) { /* sem agendador: registra sem verificar */ }
    }
  }
  registrar('ok')
})
