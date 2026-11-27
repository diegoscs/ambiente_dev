-- Radar de ofertas: liga a rodada a cada 20 s (pg_cron 1.6 aceita segundos).
-- Separado de 20261127170000 para testar a leitura antes de ligar.
-- Desligar: select cron.unschedule('radar_ofertas');
select cron.schedule('radar_ofertas', '20 seconds', $$select private.radar_rodada()$$);
