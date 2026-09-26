// Funcao serverless da Vercel: dispara o workflow de um robo no GitHub Actions.
//
// O token do GitHub fica so aqui (variavel GH_DISPATCH_TOKEN na Vercel), nunca
// na pagina. Quem pode disparar e decidido pelo Supabase: a chamada a
// hub_acesso() com o token de login do usuario so devolve true para quem esta
// em private.hub_leitores.

const SUPABASE_URL = process.env.SUPABASE_URL || "https://mthipdxpedlfnkzddlar.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_PUBLISHABLE_KEY || "sb_publishable_Y3utSlAXuOl3vzrMeJWr1Q_Rq6Xbz-D";
const REPO = "diegoscs/ambiente_dev";

// Lista branca: a pagina manda so o id; o nome do workflow sai daqui.
const WORKFLOWS = { 1: "robo_001_check_github.yml", 2: "robo_002_check_supabase.yml" };

async function podeDisparar(tokenUsuario) {
  const r = await fetch(`${SUPABASE_URL}/rest/v1/rpc/hub_acesso`, {
    method: "POST",
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${tokenUsuario}`,
      "Content-Type": "application/json",
    },
    body: "{}",
  });
  if (!r.ok) return false;
  return (await r.json()) === true;
}

module.exports = async (req, res) => {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ erro: "use POST" });
  }

  const token = (req.headers.authorization || "").replace(/^Bearer\s+/i, "");
  if (!token) return res.status(401).json({ erro: "faça login de novo" });

  let corpo = req.body;
  if (typeof corpo === "string") {
    try { corpo = JSON.parse(corpo); } catch { corpo = {}; }
  }
  const workflow = WORKFLOWS[Number(corpo && corpo.id_carga)];
  if (!workflow) return res.status(400).json({ erro: "robô desconhecido" });

  try {
    if (!(await podeDisparar(token))) return res.status(403).json({ erro: "sem acesso" });
  } catch {
    return res.status(502).json({ erro: "Supabase não respondeu" });
  }

  const gh = process.env.GH_DISPATCH_TOKEN;
  if (!gh) return res.status(503).json({ erro: "botão não configurado: falta GH_DISPATCH_TOKEN na Vercel" });

  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${gh}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "hub-robos",
    },
    body: JSON.stringify({ ref: "main" }),
  });

  if (r.status === 204) return res.status(200).json({ ok: true, workflow });
  const detalhe = await r.json().catch(() => ({}));
  return res.status(502).json({ erro: `GitHub recusou (HTTP ${r.status}): ${detalhe.message || "sem detalhe"}` });
};
