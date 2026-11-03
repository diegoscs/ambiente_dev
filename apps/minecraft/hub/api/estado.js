// Tudo que a pagina mostra, numa chamada so: VM (Google), servidor, eventos,
// sessoes, backups, pedidos e o custo estimado. ?servidor=create (padrao) ou
// pixelmon. Publico (sem login), por isso fica em cache na Vercel por 15 s
// (por URL): atualizar a pagina sem parar nao chega ao Supabase nem ao Google.
const dns = require("dns").promises;
const { supa, vm, SERVIDORES, servidorDe } = require("./_comum");

// ─── custo estimado ───
// US$/hora com a VM ligada. Fonte: catalogo de SKUs do Cloud Billing para
// southamerica-east1 (core + RAM, 02/11/2026). O valor oficial e o do relatorio
// de faturamento do Google; isto e para acompanhar no celular.
const PRECO_HORA_USD = {
  "t2d-standard-4": 0.2683, "c2d-standard-4": 0.2884, "n2d-standard-4": 0.2683, "n2d-standard-2": 0.1341,
  "e2-standard-4": 0.2127, "e2-standard-2": 0.1064,
};
const PRECO_HORA_SPOT_USD = {
  "t2d-standard-4": 0.0929, "c2d-standard-4": 0.0437, "n2d-standard-4": 0.0797, "n2d-standard-2": 0.0399,
  "e2-standard-4": 0.0421, "e2-standard-2": 0.0210,
};
const IP_HORA_USD = 0.005;              // IP externo, so com a VM ligada
const DISCO_GB_DIA_USD = 0.15 / 30;     // SSD balanceado por GB, cobra sempre (ligada ou nao)
// Cambio da propria conta: o Google converteu os US$ 300 do teste em R$ 1.779
// (console, 20/10/2026) = 5,93. O teste termina em 18/01/2027 (91 dias).
const USD_BRL = Number(process.env.USD_BRL || 5.93);
const CREDITO_USD = 300;
const INICIO_TESTE = Date.parse("2026-10-19T00:00:00-03:00");
const DIAS_TESTE = 91;
const SP = -3 * 3600000;                // Sao Paulo, sem horario de verao
const DIA = 86400000;

const diaSP = (ms) => new Date(ms + SP).toISOString().slice(0, 10);
const inicioDiaSP = (ms) => Math.floor((ms + SP) / DIA) * DIA - SP;

// Custo de um servidor (USD). `sessoes` so dele, mais recente primeiro.
function custoServidor(servidor, sessoes, vmLigada, agora, spot) {
  const precos = spot ? PRECO_HORA_SPOT_USD : PRECO_HORA_USD;
  const horasDia = {};    // "AAAA-MM-DD" (SP) -> horas ligada
  let usdTeste = 0, usdMes = 0, usdHoje = 0, horasMes = 0;
  const mesAtual = diaSP(agora).slice(0, 7), hoje = diaSP(agora);
  sessoes.forEach((s, i) => {
    const ini = Date.parse(s.dta_ligou);
    const aberta = !s.dta_desligou;
    // Sessao aberta: ate agora se e a atual e a VM esta ligada; senao, ate o ultimo sinal.
    const fim = aberta ? (i === 0 && vmLigada ? agora : Date.parse(s.dta_ultimo_sinal || s.dta_ligou)) : Date.parse(s.dta_desligou);
    const porHora = (precos[s.maquina] ?? PRECO_HORA_USD["n2d-standard-4"]) + IP_HORA_USD;
    // Quebra a sessao nos dias de Sao Paulo (uma noite de jogo cai em dois dias).
    for (let t = ini; t < fim; ) {
      const corte = Math.min(fim, inicioDiaSP(t) + DIA);
      const h = (corte - t) / 3600000, d = diaSP(t);
      horasDia[d] = (horasDia[d] || 0) + h;
      usdTeste += h * porHora;
      if (d.slice(0, 7) === mesAtual) { usdMes += h * porHora; horasMes += h; }
      if (d === hoje) usdHoje += h * porHora;
      t = corte;
    }
  });
  // O disco cobra todo dia, desde que existe (o do Create, desde o inicio do teste).
  const cfg = SERVIDORES[servidor], desde = Math.max(INICIO_TESTE, Date.parse(cfg.desde));
  const discoDia = cfg.disco_gb * DISCO_GB_DIA_USD;
  const inicioMes = Date.parse(`${mesAtual}-01T00:00:00-03:00`);
  usdTeste += Math.max(1, Math.ceil((agora - desde) / DIA)) * discoDia;
  usdMes += Math.max(1, Math.ceil((agora - Math.max(inicioMes, desde)) / DIA)) * discoDia;
  usdHoje += discoDia;
  return { usdTeste, usdMes, usdHoje, horasMes, horasDia, discoDia };
}

// O que a pagina mostra: mes, hoje e horas do servidor escolhido. Os creditos
// do teste sao um so para as duas VMs, entao a barra soma as duas.
function custo(servidor, sessoesPorServidor, vmLigada, maquina, agora, spot) {
  const deste = custoServidor(servidor, sessoesPorServidor[servidor] || [], vmLigada, agora, spot);
  let usdTeste = 0;
  for (const s of Object.keys(SERVIDORES)) {
    usdTeste += s === servidor ? deste.usdTeste : custoServidor(s, sessoesPorServidor[s] || [], false, agora, false).usdTeste;
  }
  const fimTeste = INICIO_TESTE + DIAS_TESTE * DIA;
  const ultimos = [];
  for (let i = 13; i >= 0; i--) { const d = diaSP(agora - i * DIA); ultimos.push({ dia: d, horas: +(deste.horasDia[d] || 0).toFixed(2) }); }
  const brl = (usd) => +(usd * USD_BRL).toFixed(2);
  const precos = spot ? PRECO_HORA_SPOT_USD : PRECO_HORA_USD;
  return {
    mes_brl: brl(deste.usdMes), hoje_brl: brl(deste.usdHoje), horas_mes: +deste.horasMes.toFixed(1),
    hora_brl: brl((precos[maquina] ?? precos["n2d-standard-4"]) + IP_HORA_USD),
    disco_dia_brl: brl(deste.discoDia),
    credito_total_brl: brl(CREDITO_USD), credito_usado_brl: brl(usdTeste),
    credito_restante_brl: brl(Math.max(0, CREDITO_USD - usdTeste)),
    fim_teste: new Date(fimTeste).toISOString(), dias_restantes: Math.max(0, Math.floor((fimTeste - agora) / DIA)),  // como o console conta
    usd_brl: USD_BRL, horas_por_dia: ultimos,
  };
}

module.exports = async (req, res) => {
  const agora = Date.now();
  const servidor = servidorDe(req.query && req.query.servidor);
  const cfg = SERVIDORES[servidor], so = `servidor=eq.${servidor}`;
  const desdeTeste = new Date(INICIO_TESTE).toISOString();
  const pegar = (p) => p.then((v) => ({ ok: true, v }), (e) => ({ ok: false, erro: String(e.message || e) }));

  const desde6h = new Date(agora - 6 * 3600000).toISOString();
  const [inst, status, eventos, sessoes, backups, pedidos, ipDominio, jogadores, desempenho] = await Promise.all([
    pegar(vm(servidor)),
    // Todas as linhas: a do servidor escolhido e o resumo dos outros (abas da pagina).
    pegar(supa("minecraft_status?select=*")),
    pegar(supa(`minecraft_eventos?select=dta_evento,tipo,jogador,texto,efeito&${so}&order=dta_evento.desc&limit=200`)),
    // Sessoes dos dois servidores: o credito do teste e um so.
    pegar(supa(`minecraft_sessoes?select=servidor,maquina,dta_ligou,dta_ultimo_sinal,dta_desligou,motivo&dta_ligou=gte.${desdeTeste}&order=dta_ligou.desc`)),
    pegar(supa(`minecraft_backups?select=dta,arquivo,bytes,duracao_s,ok,erro&${so}&order=dta.desc&limit=12`)),
    pegar(supa(`minecraft_comandos?select=acao,status,nome,mensagem,dta_pedido&${so}&order=dta_pedido.desc&limit=10`)),
    cfg.dominio ? pegar(dns.resolve4(cfg.dominio)) : Promise.resolve({ ok: false }),
    pegar(supa(`minecraft_jogadores?select=jogador,tempo_jogado_min,mortes,mobs_mortos,jogadores_mortos,distancia_km,blocos_minerados,conquistas,dta_atualizacao&${so}`)),
    pegar(supa(`minecraft_desempenho?select=dta,tps,mspt,cpu_pct,jogadores&${so}&dta=gte.${desde6h}&order=dta`)),
  ]);

  const v = inst.ok ? inst.v : null;
  const vmInfo = v && {
    status: v.status,                                   // RUNNING, TERMINATED, STAGING, STOPPING...
    maquina: (v.machineType || "").split("/").pop(),
    spot: (v.scheduling && v.scheduling.provisioningModel) === "SPOT",
    ip: (((v.networkInterfaces || [])[0] || {}).accessConfigs || [{}])[0].natIP || null,
    ultimo_start: v.lastStartTimestamp || null,
    ultimo_stop: v.lastStopTimestamp || null,
  };
  const porServidor = {};
  for (const s of sessoes.ok ? sessoes.v : []) (porServidor[s.servidor] ||= []).push(s);
  const listaSessoes = porServidor[servidor] || [];
  const linhas = status.ok ? status.v : [];

  res.setHeader("Cache-Control", "public, s-maxage=15, stale-while-revalidate=30");
  res.status(200).json({
    agora: new Date(agora).toISOString(),
    servidor_escolhido: servidor,
    // Resumo de cada servidor para as abas (so a linha do monitor, sem a VM).
    servidores: Object.keys(SERVIDORES).map((s) => {
      const l = linhas.find((x) => x.servidor === s);
      return { servidor: s, online: !!(l && l.online), jogadores_online: l ? l.jogadores_online : 0,
               estado_vm: l ? l.estado_vm : null, dta_verificacao: l ? l.dta_verificacao : null };
    }),
    vm: vmInfo,
    vm_erro: inst.ok ? null : inst.erro,
    servidor: linhas.find((x) => x.servidor === servidor) || null,
    eventos: eventos.ok ? eventos.v : [],
    sessoes: listaSessoes.slice(0, 15),
    backups: backups.ok ? backups.v : [],
    pedidos: pedidos.ok ? pedidos.v : [],
    jogadores: jogadores.ok ? jogadores.v : [],
    desempenho: desempenho.ok ? desempenho.v : [],
    endereco: {
      dominio: cfg.dominio,
      // O DuckDNS so serve se apontar para o IP de agora da VM.
      dominio_ok: !!(vmInfo && vmInfo.ip && ipDominio.ok && ipDominio.v.includes(vmInfo.ip)),
      ip: vmInfo ? vmInfo.ip : null,
    },
    custo: custo(servidor, porServidor, !!vmInfo && vmInfo.status === "RUNNING", vmInfo && vmInfo.maquina, agora, vmInfo && vmInfo.spot),
  });
};
