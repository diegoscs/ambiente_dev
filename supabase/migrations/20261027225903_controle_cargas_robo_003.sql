-- Robo 003 (sync Open Finance do financas-app) no controle de cargas. A linha
-- foi criada em 09/10/2026 junto com o registro externo; esta migration so
-- documenta o cadastro (on conflict do nothing: o banco nao muda).
-- O token do robo (private.tokens_carga) nunca entra no repositorio.
insert into public.controle_cargas (id_carga, nome_carga, descricao, tempo_min, dias_semana, flg_ativo, origem, script, atraso_max_horas, workflow)
values (3, '003 - Sync Open Finance',
        'Sync Open Finance (Pluggy -> Supabase OpenFinance) do financas-app. Roda 2x/dia no proprio repo; o botao do hub dispara via robo_003',
        20, '{1,2,3,4,5,6,7}', true, 'Node/API', 'financas-app: scripts/sync-openfinance.mts', 20, 'robo_003_sync_openfinance.yml')
on conflict (id_carga) do nothing;
