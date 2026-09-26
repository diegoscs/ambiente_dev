-- Com os robos no GitHub Actions, a tabela deixa de ser espelho do Postgres local.
comment on table public.controle_cargas is
    'Ultima execucao de cada robo do ambiente_dev. Registro oficial desde a migracao para o GitHub Actions (26/09/2026); o historico fica em historico_cargas. Escrita apenas com a service_role.';
