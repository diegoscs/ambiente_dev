-- Views do hub so para leitura (achado do robo 007 em 25/11/2026): o papel
-- anonimo tinha INSERT/UPDATE/DELETE/TRUNCATE na vw_saude_robos (grant padrao
-- da Supabase). Na pratica nao gravava nada (view nao atualizavel e RLS), mas
-- permissao que nao e usada nao fica.
revoke insert, update, delete, truncate on
  public.vw_saude_robos, public.vw_metricas_robos, public.vw_execucoes_diarias, public.vw_historico_legivel
  from anon, authenticated;
