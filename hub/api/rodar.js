// Funcao serverless da Vercel: dispara o workflow de um robo no GitHub Actions.
//
// O token do GitHub fica so aqui (variavel GH_DISPATCH_TOKEN na Vercel), nunca
// na pagina. Quem pode disparar e qual workflow roda sao decididos pelo
// Supabase: a leitura de controle_cargas com o token de login do usuario so
// devolve a linha para quem esta em private.hub_leitores (RLS), e o nome do
// workflow vem dessa linha - a pagina manda so o id_carga.

const SUPABASE_URL = process.env.SUPABASE_URL || "https://mthipdxpedlfnkzddlar.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_PUBLISHABLE_KEY || "sb_publishable_Y3utSlAXuOl3vzrMeJWr1Q_Rq6Xbz-D";
const REPO = "diegoscs/ambiente_dev";
const NOME_WORKFLOW = /^[a-z0-9_]+\.yml$/;

// Workflow do robo, lido com as permissoes do proprio usuario.
// null = sem acesso, robo inexistente/inativo ou sem workflow cadastrado.
async function workflowDoRobo(tokenUsuario, idCarga) {
  const r = await fetch(
    `${SUPABASE_URL}/rest/v1/controle_cargas?select=workflow&flg_ativo=is.true&id_carga=eq.${idCarga}`,
    { headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${tokenUsuario}` } },
  );
  if (r.status === 401) return { status: 401 };
  if (!r.ok) throw new Error(`Supabase HTTP ${r.status}`);
  const linhas = await r.json();
  const wf = linhas[0] && linhas[0].workflow;
  return { workflow: wf && NOME_WORKFLOW.test(wf) ? wf : null };
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
  const idCarga = Number(corpo && corpo.id_carga);
  if (!Number.isInteger(idCarga) || idCarga <= 0) return res.status(400).json({ erro: "robô desconhecido" });

  let alvo;
  try {
    alvo = await workflowDoRobo(token, idCarga);
  } catch {
    return res.status(502).json({ erro: "Supabase não respondeu" });
  }
  if (alvo.status === 401) return res.status(401).json({ erro: "sessão expirada, entre de novo" });
  if (!alvo.workflow) return res.status(403).json({ erro: "sem acesso ou robô sem workflow" });

  const gh = process.env.GH_DISPATCH_TOKEN;
  if (!gh) return res.status(503).json({ erro: "botão não configurado: falta GH_DISPATCH_TOKEN na Vercel" });

  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${alvo.workflow}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${gh}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "hub-robos",
    },
    body: JSON.stringify({ ref: "main" }),
  });

  if (r.status === 204) return res.status(200).json({ ok: true, workflow: alvo.workflow });
  const detalhe = await r.json().catch(() => ({}));
  return res.status(502).json({ erro: `GitHub recusou (HTTP ${r.status}): ${detalhe.message || "sem detalhe"}` });
};
