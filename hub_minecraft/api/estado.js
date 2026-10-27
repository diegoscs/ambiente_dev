// Tudo que a pagina mostra, numa chamada so: VM (Google), servidor, eventos,
// sessoes, backups, pedidos e o custo estimado. Publico (sem login), por isso
// fica em cache na Vercel por 15 s: atualizar a pagina sem parar nao chega ao
// Supabase nem ao Google.
const dns = require("dns").promises;
const { supa, vm } = require("./_comum");

const DOMINIO = "servercasaonlymine.duckdns.org";

// ─── custo estimado ───
// US$/hora com a VM ligada. Fonte: tabelas publicas de precos do GCP para
// southamerica-east1 (out/2026). O valor oficial e o do relatorio de
// faturamento do Google; isto e para acompanhar no celular.
const PRECO_HORA_USD = { "n2d-standard-4": 0.268, "e2-standard-2": 0.1064, "e2-standard-4": 0.2128 };
const PRECO_HORA_SPOT_USD = { "n2d-standard-4": 0.053, "e2-standard-2": 0.0222, "e2-standard-4": 0.0444 };
const IP_HORA_USD = 0.005;              // IP externo, so com a VM ligada
const DISCO_DIA_USD = (30 * 0.15) / 30; // 30 GB SSD balanceado, cobra sempre
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

function custo(sessoes, vmLigada, agora, spot) {
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
  // O disco cobra todo dia, mas so existe desde o inicio do teste.
  const diasTeste = Math.max(1, Math.ceil((agora - INICIO_TESTE) / DIA));
  const inicioMes = Date.parse(`${mesAtual}-01T00:00:00-03:00`);
  const diasDiscoMes = Math.max(1, Math.ceil((agora - Math.max(inicioMes, INICIO_TESTE)) / DIA));
  usdTeste += diasTeste * DISCO_DIA_USD;
  usdMes += diasDiscoMes * DISCO_DIA_USD;
  usdHoje += DISCO_DIA_USD;
  const fimTeste = INICIO_TESTE + DIAS_TESTE * DIA;
  const ultimos = [];
  for (let i = 13; i >= 0; i--) { const d = diaSP(agora - i * DIA); ultimos.push({ dia: d, horas: +(horasDia[d] || 0).toFixed(2) }); }
  const brl = (usd) => +(usd * USD_BRL).toFixed(2);
  return {
    mes_brl: brl(usdMes), hoje_brl: brl(usdHoje), horas_mes: +horasMes.toFixed(1),
    hora_brl: brl(((spot ? PRECO_HORA_SPOT_USD : PRECO_HORA_USD)["n2d-standard-4"]) + IP_HORA_USD),
    credito_total_brl: brl(CREDITO_USD), credito_usado_brl: brl(usdTeste),
    credito_restante_brl: brl(Math.max(0, CREDITO_USD - usdTeste)),
    fim_teste: new Date(fimTeste).toISOString(), dias_restantes: Math.max(0, Math.floor((fimTeste - agora) / DIA)),  // como o console conta
    usd_brl: USD_BRL, horas_por_dia: ultimos,
  };
}

module.exports = async (req, res) => {
  const agora = Date.now();
  const desdeTeste = new Date(INICIO_TESTE).toISOString();
  const pegar = (p) => p.then((v) => ({ ok: true, v }), (e) => ({ ok: false, erro: String(e.message || e) }));

  const desde6h = new Date(agora - 6 * 3600000).toISOString();
  const [inst, status, eventos, sessoes, backups, pedidos, ipDominio, jogadores, desempenho] = await Promise.all([
    pegar(vm()),
    pegar(supa("minecraft_status?select=*")),
    pegar(supa("minecraft_eventos?select=dta_evento,tipo,jogador,texto,efeito&order=dta_evento.desc&limit=200")),
    pegar(supa(`minecraft_sessoes?select=maquina,dta_ligou,dta_ultimo_sinal,dta_desligou,motivo&dta_ligou=gte.${desdeTeste}&order=dta_ligou.desc`)),
    pegar(supa("minecraft_backups?select=dta,arquivo,bytes,duracao_s,ok,erro&order=dta.desc&limit=12")),
    pegar(supa("minecraft_comandos?select=acao,status,nome,mensagem,dta_pedido&order=dta_pedido.desc&limit=10")),
    pegar(dns.resolve4(DOMINIO)),
    pegar(supa("minecraft_jogadores?select=jogador,tempo_jogado_min,mortes,mobs_mortos,jogadores_mortos,distancia_km,blocos_minerados,conquistas,dta_atualizacao")),
    pegar(supa(`minecraft_desempenho?select=dta,tps,mspt,cpu_pct,jogadores&dta=gte.${desde6h}&order=dta`)),
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
  const listaSessoes = sessoes.ok ? sessoes.v : [];

  res.setHeader("Cache-Control", "public, s-maxage=15, stale-while-revalidate=30");
  res.status(200).json({
    agora: new Date(agora).toISOString(),
    vm: vmInfo,
    vm_erro: inst.ok ? null : inst.erro,
    servidor: status.ok ? status.v[0] || null : null,
    eventos: eventos.ok ? eventos.v : [],
    sessoes: listaSessoes.slice(0, 15),
    backups: backups.ok ? backups.v : [],
    pedidos: pedidos.ok ? pedidos.v : [],
    jogadores: jogadores.ok ? jogadores.v : [],
    desempenho: desempenho.ok ? desempenho.v : [],
    endereco: {
      dominio: DOMINIO,
      // O DuckDNS so serve se apontar para o IP de agora da VM.
      dominio_ok: !!(vmInfo && vmInfo.ip && ipDominio.ok && ipDominio.v.includes(vmInfo.ip)),
      ip: vmInfo ? vmInfo.ip : null,
    },
    custo: custo(listaSessoes, !!vmInfo && vmInfo.status === "RUNNING", agora, vmInfo && vmInfo.spot),
  });
};
