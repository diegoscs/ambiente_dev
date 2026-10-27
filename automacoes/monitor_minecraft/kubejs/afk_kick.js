// Kicka jogador AFK, para a VM nao ficar ligada (e cobrando) com alguem parado.
// Depois do kick, se nao sobrar ninguem, o monitor da VM desliga a maquina em
// 5 min (automacoes/minecraft_gcp/vm/monitor_vm.py).
//
// Atividade = mexer a camera, falar no chat, quebrar/colocar/clicar em bloco.
// Andar NAO conta: AFK em agua corrente ou carrinho tambem se move.
// O monitor le as linhas "[monitor_minecraft] AFK..." do logs/kubejs/server.log:
//   AFK <iso> nick=min,nick=min   quem esta parado ha 2+ min (hub: "AFK 6 min")
//   AFKKICK <iso> <nick> <min>    desconectado por inatividade (feed do hub)
const AFK_MIN = 10            // parado por isso -> kick
const AVISO_MIN = 8           // aviso no chat do jogador
const MOSTRAR_A_PARTIR_MIN = 2
const EXCECOES = []           // nicks que podem ficar AFK (ex.: farm), vazio = ninguem
const CHECAR_TICKS = 20 * 30  // a cada 30 s

const estado = {}             // nick -> { yaw, pitch, desde (ms), avisado }
let ticks = 0

function nomeDe(p) {
  try { return String(p.username) } catch (e) { return null }
}
function ativo(p) {
  const n = p && nomeDe(p)
  if (n && estado[n]) { estado[n].desde = Date.now(); estado[n].avisado = false }
}

PlayerEvents.chat(e => ativo(e.player))
BlockEvents.broken(e => ativo(e.player))
BlockEvents.rightClicked(e => ativo(e.player))
BlockEvents.placed(e => { try { ativo(e.player || e.entity) } catch (err) {} })
PlayerEvents.loggedIn(e => { const n = nomeDe(e.player); if (n) delete estado[n] })
PlayerEvents.loggedOut(e => { const n = nomeDe(e.player); if (n) delete estado[n] })

ServerEvents.tick(e => {
  ticks++
  if (ticks % CHECAR_TICKS !== 0) return
  const agora = Date.now()
  const parados = []
  e.server.players.forEach(p => {
    const n = nomeDe(p)
    if (!n || EXCECOES.indexOf(n) >= 0) return
    let yaw, pitch
    try { yaw = p.getYRot(); pitch = p.getXRot() } catch (err) { return }
    const s = estado[n]
    if (!s || Math.abs(s.yaw - yaw) > 0.5 || Math.abs(s.pitch - pitch) > 0.5) {
      // Primeira leitura ou a camera mexeu: o tempo parado volta a zero.
      estado[n] = { yaw: yaw, pitch: pitch, desde: agora, avisado: false }
      return
    }
    const min = (agora - estado[n].desde) / 60000
    if (min >= AFK_MIN) {
      console.info(`[monitor_minecraft] AFKKICK ${new Date().toISOString()} ${n} ${Math.floor(min)}`)
      e.server.runCommandSilent(`kick ${n} AFK por ${AFK_MIN} minutos. Pode entrar de novo quando voltar!`)
      delete estado[n]
      return
    }
    if (min >= AVISO_MIN && !estado[n].avisado) {
      try { p.tell(`§eVocê está parado há ${Math.floor(min)} min. Mexa a câmera ou será desconectado em ${AFK_MIN - Math.floor(min)} min (servidor economizando).`) } catch (err) {}
      estado[n].avisado = true
    }
    if (min >= MOSTRAR_A_PARTIR_MIN) parados.push(`${n}=${Math.floor(min)}`)
  })
  if (parados.length) console.info(`[monitor_minecraft] AFK ${new Date().toISOString()} ${parados.join(',')}`)
})
