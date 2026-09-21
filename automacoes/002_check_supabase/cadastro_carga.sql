-- =============================================
-- AUTOR        : Diego Candido
-- DATA CRIACAO : 15/09/2026
-- DESCRICAO    : Cadastro do robo 002 e colunas de controle do espelhamento.
--                Rodar como o DONO da tabela (postgres) - robo_app nao tem
--                privilegio de ALTER.
--
--   psql -U postgres -d dm -f cadastro_carga.sql
-- =============================================

-- 1) Colunas de controle do espelho no Supabase ------------------------------
-- Ficam na tabela local porque a pergunta que elas respondem e local:
-- "esta linha ja chegou no Supabase?". Toda execucao reenvia o que estiver
-- com flg_sincronizado = false.
ALTER TABLE dbo.controle_cargas
    ADD COLUMN IF NOT EXISTS flg_sincronizado boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS dta_sync         timestamptz;

COMMENT ON COLUMN dbo.controle_cargas.flg_sincronizado IS
    'false = linha ainda nao espelhada no Supabase; a proxima execucao reenvia';
COMMENT ON COLUMN dbo.controle_cargas.dta_sync IS
    'quando a linha foi espelhada no Supabase com sucesso';

GRANT SELECT, INSERT, UPDATE ON dbo.controle_cargas TO robo_app;

-- 2) Cadastro do robo --------------------------------------------------------
-- dias_semana com os 7 dias = frequencia DIARIA. Quem decide o dia de verdade
-- e o Agendador do Windows; a coluna e documentacao do esperado.
INSERT INTO dbo.controle_cargas
    (id_carga, nome_carga, descricao, tempo_min, dias_semana, flg_ativo, origem, script)
VALUES
    (2,
     '002 - Check Supabase',
     'Keepalive do projeto Supabase (plano free): consulta real via Postgres e REST para o projeto nao ser pausado por inatividade',
     5,
     '{1,2,3,4,5,6,7}',
     true,
     'Python/API',
     '002_check_supabase.py')
ON CONFLICT (id_carga) DO UPDATE
   SET nome_carga  = EXCLUDED.nome_carga,
       descricao   = EXCLUDED.descricao,
       tempo_min   = EXCLUDED.tempo_min,
       dias_semana = EXCLUDED.dias_semana,
       flg_ativo   = EXCLUDED.flg_ativo,
       origem      = EXCLUDED.origem,
       script      = EXCLUDED.script,
       dta_modif   = now();

-- 3) Conferencia -------------------------------------------------------------
SELECT id_carga, nome_carga, status, dias_semana, flg_ativo, flg_sincronizado, dta_sync
  FROM dbo.controle_cargas
 ORDER BY id_carga;
