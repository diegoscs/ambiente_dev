-- App "Sol nas praias" (robo 004) hospedado na Vercel: a pagina e estatica e
-- busca aqui o pacote de dados que o robo grava a cada execucao (ranking,
-- graficos hora a hora e mapa de chuva). Uma linha por cidade, sobrescrita.
--
-- Leitura PUBLICA de proposito: e previsao do tempo, nada pessoal, e o app
-- abre sem login. So esta tabela fica aberta; a escrita continua so com a
-- service_role do robo.
create table if not exists public.painel_praias (
  cidade           text primary key,
  dados            jsonb not null,
  dta_atualizacao  timestamptz not null default now()
);

comment on table public.painel_praias is 'Pacote de dados do app Sol nas praias (robo 004), lido pela pagina publica na Vercel. Leitura publica (anon); escrita so service_role.';

alter table public.painel_praias enable row level security;

revoke all on public.painel_praias from anon, authenticated;
grant select on public.painel_praias to anon, authenticated;

create policy leitura_publica on public.painel_praias
  for select to anon, authenticated using (true);
