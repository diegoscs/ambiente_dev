// Helpers das funcoes do hub do servidor. Arquivo com "_" na pasta api/ nao
// vira rota na Vercel.
//
// Credenciais so aqui, nas variaveis da Vercel (nunca na pagina):
//   SUPABASE_URL, SUPABASE_SERVICE_KEY  leitura/escrita das tabelas minecraft_*
//   GCP_SA_KEY  JSON da conta hub-minecraft: o papel minecraftHub so permite
//               consultar e ligar as VMs "minecraft" e "pixelmon" (nada de
//               desligar/apagar)
const crypto = require("crypto");

const PROJETO = "serverminecasaonly";
const ZONA = "southamerica-east1-b";
// Os dois servidores: mesma pagina, mesmas tabelas (coluna servidor), uma VM cada.
// create e o padrao (o servidor de sempre).
const SERVIDORES = {
  create: { vm: "minecraft", dominio: "servercasaonlymine.duckdns.org", disco_gb: 30, desde: "2026-10-19T00:00:00-03:00" },
  pixelmon: { vm: "pixelmon", dominio: null, disco_gb: 20, desde: "2026-10-28T18:00:00-03:00" },
};
const servidorDe = (valor) => (Object.hasOwn(SERVIDORES, valor) ? valor : "create");
const instancia = (servidor) =>
  `https://compute.googleapis.com/compute/v1/projects/${PROJETO}/zones/${ZONA}/instances/${SERVIDORES[servidor].vm}`;

async function supa(caminho, opcoes = {}) {
  const chave = process.env.SUPABASE_SERVICE_KEY;
  const r = await fetch(`${process.env.SUPABASE_URL}/rest/v1/${caminho}`, {
    ...opcoes,
    headers: { apikey: chave, Authorization: `Bearer ${chave}`, "Content-Type": "application/json", ...(opcoes.headers || {}) },
  });
  if (!r.ok) throw new Error(`Supabase ${caminho.split("?")[0]} HTTP ${r.status}`);
  return r.status === 201 || r.status === 204 ? null : r.json();
}

// Token do Google pela chave da conta de servico (JWT assinado aqui, sem SDK).
// Vale 1 h; fica guardado enquanto a funcao estiver quente.
let tokenGuardado = null;
async function tokenGoogle() {
  if (tokenGuardado && tokenGuardado.expira > Date.now() + 60000) return tokenGuardado.token;
  const chave = JSON.parse(process.env.GCP_SA_KEY);
  const agora = Math.floor(Date.now() / 1000);
  const b64 = (obj) => Buffer.from(JSON.stringify(obj)).toString("base64url");
  const corpo = `${b64({ alg: "RS256", typ: "JWT" })}.${b64({
    iss: chave.client_email,
    scope: "https://www.googleapis.com/auth/compute",
    aud: "https://oauth2.googleapis.com/token",
    iat: agora,
    exp: agora + 3600,
  })}`;
  const assinatura = crypto.createSign("RSA-SHA256").update(corpo).sign(chave.private_key, "base64url");
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion: `${corpo}.${assinatura}` }),
  });
  if (!r.ok) throw new Error(`Google token HTTP ${r.status}`);
  const j = await r.json();
  tokenGuardado = { token: j.access_token, expira: Date.now() + j.expires_in * 1000 };
  return j.access_token;
}

// GET = estado da VM; POST "/start" = liga.
async function vm(servidor, metodo = "GET", sufixo = "") {
  const r = await fetch(instancia(servidor) + sufixo, { method: metodo, headers: { Authorization: `Bearer ${await tokenGoogle()}` } });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`Google ${metodo} HTTP ${r.status}: ${(j.error && j.error.message) || "sem detalhe"}`);
  return j;
}

module.exports = { supa, vm, SERVIDORES, servidorDe };
