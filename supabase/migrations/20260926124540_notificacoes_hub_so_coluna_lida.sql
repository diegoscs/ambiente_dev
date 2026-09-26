-- O Supabase concede ALL nas tabelas do public para anon/authenticated por
-- padrao, e o grant de coluna nao restringe nada enquanto o de tabela existir.
-- Aqui fica explicito: o leitor do hub so le e so mexe em "lida".
revoke insert, update, delete, truncate, references, trigger on public.notificacoes_hub from anon, authenticated;
revoke select on public.notificacoes_hub from anon;
grant select on public.notificacoes_hub to authenticated;
grant update (lida) on public.notificacoes_hub to authenticated;

-- Mesmo cuidado nas tabelas dos robos: escrita so pela service_role.
revoke insert, update, delete, truncate, references, trigger on public.controle_cargas, public.historico_cargas from anon, authenticated;
revoke select on public.controle_cargas, public.historico_cargas, public.vw_saude_robos from anon;
