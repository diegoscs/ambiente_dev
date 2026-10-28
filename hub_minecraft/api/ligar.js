// Botao "Ligar" do hub do servidor. Publico (sem login), entao com travas:
//   - so liga se a VM estiver desligada (ligada/ligando = nada a fazer)
//   - no minimo 2 min entre pedidos e no maximo 8 por dia
//   - a credencial do Google so consegue ligar e consultar as VMs dos servidores
//   - cada servidor (create ou pixelmon, no corpo) tem os proprios limites
// E mesmo que alguem fique apertando: a VM se desliga sozinha se ninguem
// entrar em 15 min (e 5 min depois que o ultimo sair) - monitor_vm.py.
const { supa, vm, servidorDe } = require("./_comum");

const INTERVALO_MIN_MS = 2 * 60000;
const MAX_POR_DIA = 8;
// Quem pode aparecer como "quem ligou". Obrigatorio: a pagina so libera o
// botao depois de escolher, e aqui a funcao recusa quem chamar direto sem nome.
const GALERA = ["digoscs", "Marllonx12", "Xxkadu03xX", "darak2610", "watinha", "socasoca"];

module.exports = async (req, res) => {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ erro: "use POST" });
  }
  let corpo = req.body;
  if (typeof corpo === "string") { try { corpo = JSON.parse(corpo); } catch { corpo = {}; } }
  const nome = GALERA.find((n) => n === String((corpo && corpo.nome) || ""));
  if (!nome) return res.status(400).json({ erro: "Escolha quem está ligando." });
  const servidor = servidorDe(corpo && corpo.servidor);

  let inst;
  try { inst = await vm(servidor); } catch (e) { return res.status(502).json({ erro: `Google não respondeu: ${e.message}` }); }
  if (["RUNNING", "PROVISIONING", "STAGING", "REPAIRING"].includes(inst.status)) {
    return res.status(200).json({ ok: true, ja_ligada: true, mensagem: "O servidor já está ligado ou ligando." });
  }
  if (["STOPPING", "SUSPENDING"].includes(inst.status)) {
    return res.status(409).json({ erro: "O servidor está terminando de desligar. Tente de novo em 1 minuto." });
  }

  const desde = new Date(Date.now() - 86400000).toISOString();
  let recentes;
  try {
    recentes = await supa(`minecraft_comandos?select=dta_pedido&servidor=eq.${servidor}&acao=eq.ligar&dta_pedido=gte.${desde}&order=dta_pedido.desc`);
  } catch { return res.status(502).json({ erro: "Banco não respondeu. Tente de novo." }); }
  if (recentes.length >= MAX_POR_DIA) {
    return res.status(429).json({ erro: `Limite de ${MAX_POR_DIA} ligadas em 24 h atingido. Fale com o Diego.` });
  }
  if (recentes[0] && Date.now() - Date.parse(recentes[0].dta_pedido) < INTERVALO_MIN_MS) {
    return res.status(429).json({ erro: "Alguém acabou de pedir. Espere 2 minutos." });
  }

  const registro = { acao: "ligar", nome, servidor, dta_execucao: new Date().toISOString() };
  try {
    await vm(servidor, "POST", "/start");
  } catch (e) {
    await supa("minecraft_comandos", { method: "POST", body: JSON.stringify({ ...registro, status: "erro", mensagem: e.message.slice(0, 300) }) }).catch(() => {});
    return res.status(502).json({ erro: `O Google recusou ligar: ${e.message}` });
  }
  await supa("minecraft_comandos", { method: "POST", body: JSON.stringify({ ...registro, status: "feito", mensagem: "VM ligada pelo hub do servidor." }) }).catch(() => {});
  return res.status(200).json({ ok: true, mensagem: "Ligando! Em uns 2 minutos dá para entrar. Se ninguém entrar em 15 minutos, ele desliga de novo." });
};
