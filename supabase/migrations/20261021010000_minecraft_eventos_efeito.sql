-- Efeito de cada comando de jogador, para o hub mostrar se ele mudou algo:
--   ok          aceito pelo jogo (efeito nao verificado)
--   sem_efeito  recusado (sem permissao, comando invalido) ou nao mudou nada
--   mudou:<x>   verificado: mudou de verdade (ex.: mudou:creative no /gamemode)
-- Vem do kubejs/server_scripts/monitor_comandos.js. Nulo nos eventos antigos.
alter table public.minecraft_eventos add column if not exists efeito text;

comment on column public.minecraft_eventos.efeito is 'So em tipo=comando: ok, sem_efeito ou mudou:<valor> (ver monitor_comandos.js).';
