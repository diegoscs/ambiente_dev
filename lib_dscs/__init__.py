# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 05/09/2026
# DESCRICAO      : Biblioteca compartilhada dos robos do ambiente_dev.
#                  Mesmo papel da marche_lib no trabalho: conexao com o banco,
#                  credenciais e controle de cargas em um lugar so.
#
# USO NO ROBO    : sys.path.insert(0, str(Path(__file__).parent.parent.parent))
#                  import lib_dscs as dl
#
#                  dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, ...)
#                  ...
#                  dl.registrar_carga_supabase(IDCARGA, dl.STATUS_SUCESSO, ...)
#                  Esqueleto completo em automacoes\_modelo.
# =============================================
from __future__ import annotations

from .api import chamar_api_json
from .banco import (
    abrir_conexao_banco,
    conexao,
    executar_comando,
    executar_query,
    executar_query_dict,
    testar_conexao,
)
from .config import (
    ENV_FILE,
    RAIZ,
    descrever_conexao,
    ler_env,
    obter_configuracao,
    obter_variavel,
)
from .controle_cargas import (
    STATUS_ERRO,
    STATUS_INICIO,
    STATUS_SUCESSO,
    TABELA_CONTROLE,
    listar_cargas,
    obter_carga,
    status_erro,
    status_inicio,
    status_sucesso,
)
from .estado import (
    caminho_estado,
    gravar_estado,
    ja_executou_hoje,
    ler_estado,
    marcar_execucao,
)
from .log import (
    configurar_logger,
    linhas_do_log,
    log,
    log_erro,
    logar_contexto,
    logar_traceback,
    salvar_log_erro,
)
from .notificacao import (
    alertar_erro_robo,
    alertar_telegram,
    telegram_configurado,
)
from .retry import executar_com_retry
from .supabase import (
    MODO_CLOUD,
    MODO_LOCAL,
    TABELA_CONTROLE_SUPABASE,
    SAUDE_BOA,
    TABELA_HISTORICO_SUPABASE,
    comandos_minecraft_abertos,
    fechar_comando_minecraft,
    gravar_eventos_minecraft,
    gravar_status_minecraft,
    ler_saude_robos,
    modo_execucao,
    notificar_hub,
    ultima_notificacao,
    ultimo_evento_minecraft,
    registrar_carga_supabase,
    supabase_apagar,
    supabase_atualizar,
    supabase_configurado,
    supabase_inserir,
    supabase_ler,
    trabalho_feito_no_dia,
    url_execucao_actions,
)

__version__ = "1.2.0"

__all__ = [
    # config
    "RAIZ",
    "ENV_FILE",
    "ler_env",
    "obter_variavel",
    "obter_configuracao",
    "descrever_conexao",
    # banco
    "abrir_conexao_banco",
    "conexao",
    "executar_query",
    "executar_query_dict",
    "executar_comando",
    "testar_conexao",
    # controle de cargas
    "TABELA_CONTROLE",
    "STATUS_INICIO",
    "STATUS_SUCESSO",
    "STATUS_ERRO",
    "status_inicio",
    "status_sucesso",
    "status_erro",
    "obter_carga",
    "listar_cargas",
    # log
    "configurar_logger",
    "log",
    "log_erro",
    "logar_contexto",
    "logar_traceback",
    "salvar_log_erro",
    "linhas_do_log",
    # notificacao
    "alertar_telegram",
    "alertar_erro_robo",
    "telegram_configurado",
    # retry
    "executar_com_retry",
    # api
    "chamar_api_json",
    # supabase (controle de cargas na nuvem)
    "MODO_LOCAL",
    "MODO_CLOUD",
    "TABELA_CONTROLE_SUPABASE",
    "TABELA_HISTORICO_SUPABASE",
    "modo_execucao",
    "supabase_configurado",
    "url_execucao_actions",
    "registrar_carga_supabase",
    "trabalho_feito_no_dia",
    "SAUDE_BOA",
    "ler_saude_robos",
    "notificar_hub",
    "ultima_notificacao",
    "gravar_status_minecraft",
    "gravar_eventos_minecraft",
    "ultimo_evento_minecraft",
    "comandos_minecraft_abertos",
    "fechar_comando_minecraft",
    "supabase_ler",
    "supabase_inserir",
    "supabase_atualizar",
    "supabase_apagar",
    # estado local
    "caminho_estado",
    "ler_estado",
    "gravar_estado",
    "ja_executou_hoje",
    "marcar_execucao",
]
