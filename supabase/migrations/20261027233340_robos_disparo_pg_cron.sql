-- Disparo dos robos em hora cheia pelo pg_cron do Supabase.
--
-- O schedule do GitHub Actions atrasou os robos de 2 a 7 h (medido de 20 a
-- 27/10/2026), e o horario que aparece no hub e o do run, nao o do cron. O
-- workflow_dispatch, ao contrario, comeca em segundos. Entao o relogio passa a
-- ser o pg_cron: na hora cheia ele chama a API do GitHub e o run sai na hora.
--
-- Token: fine-grained PAT com "Actions: Read and write" em ambiente_dev e
-- financas-app, guardado no Vault com o nome github_dispatch_token (nunca no
-- repositorio). Sem ele, cada disparo so deixa um warning no log do banco.
--
-- Reserva: o vigia continua com schedule no GitHub (--reserva). Se o vigia das
-- 09:00 nao passou no dia, o disparo falhou e a reserva avisa no hub/Telegram.
create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists pg_net with schema extensions;

create or replace function private.disparar_workflow(p_repo text, p_workflow text)
returns bigint
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
declare
  v_token text;
begin
  select decrypted_secret into v_token
    from vault.decrypted_secrets
   where name = 'github_dispatch_token';

  if v_token is null or v_token = '' then
    raise warning 'disparar_workflow(%, %): segredo github_dispatch_token ausente no Vault', p_repo, p_workflow;
    return null;
  end if;

  -- Assincrono: a resposta (204 = disparado) fica em net._http_response por 6 h.
  return net.http_post(
    url := format('https://api.github.com/repos/%s/actions/workflows/%s/dispatches', p_repo, p_workflow),
    body := jsonb_build_object('ref', 'main'),
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || v_token,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'ambiente_dev-pg_cron',
      'Content-Type', 'application/json'
    ),
    timeout_milliseconds := 10000
  );
end;
$$;

revoke all on function private.disparar_workflow(text, text) from public, anon, authenticated;

-- Horarios em UTC (o pg_cron do Supabase roda em UTC). Sao Paulo = UTC-3.
--   06:00 SP  sync Open Finance (app atualizado antes das 7h)
--   07:00 SP  robo 001 - commits do dia
--   08:00 SP  robo 002 - keepalive do Supabase
--   09:00 SP  vigia - confere todo mundo
--   15:00 SP  sync Open Finance (depois da atualizacao do Pluggy, ~14:30 SP)
-- cron.schedule com o mesmo nome substitui o job: rodar de novo e seguro.
select cron.schedule('robo_003_sync_manha', '0 9 * * *',
  $$select private.disparar_workflow('diegoscs/financas-app', 'sync-openfinance.yml')$$);
select cron.schedule('robo_001_check_github', '0 10 * * *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'robo_001_check_github.yml')$$);
select cron.schedule('robo_002_check_supabase', '0 11 * * *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'robo_002_check_supabase.yml')$$);
select cron.schedule('vigia_robos', '0 12 * * *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'vigia_robos.yml')$$);
select cron.schedule('robo_003_sync_tarde', '0 18 * * *',
  $$select private.disparar_workflow('diegoscs/financas-app', 'sync-openfinance.yml')$$);

-- O pg_cron guarda cada execucao em cron.job_run_details sem limite: 7 dias bastam.
select cron.schedule('limpar_historico_pg_cron', '30 3 * * *',
  $$delete from cron.job_run_details where end_time < now() - interval '7 days'$$);
