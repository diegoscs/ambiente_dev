# automacoes — ponto de entrada único dos robôs

Desde **25/09/2026** existe **uma tarefa só** no Agendador do Windows, disparada
**a cada logon**, no lugar das duas tarefas por horário que havia antes.

```
Agendador
└─ ambiente_dev - Robos        gatilho: logon + 3 min
   └─ automacoes\iniciar_robos.bat
      ├─ call 001_check_github\001_check_github.bat    (commits no GitHub)
      └─ call 002_check_supabase\002_check_supabase.bat (keepalive Supabase)
```

| | Antes (até 24/09/2026) | Agora |
|---|---|---|
| Tarefas | 2 (`001 - Check_GitHub` 20:40, `002 - Check_Supabase` 08:00) | 1 (`ambiente_dev - Robos`) |
| Gatilho | diário, horário fixo | ao fazer logon, +3 min |
| `LogonType` | `S4U` | `Interactive` |
| `RunLevel` | `Highest` | `Limited` |
| Precisa de admin | sim, para criar | **não** |
| Senha armazenada | sim | **não** |
| `StartWhenAvailable` | `True` | não se aplica |

## Por que logon, e não "ao inicializar o sistema"

O gatilho de boot dispara antes do login, com a rede e o Postgres local ainda
subindo — e os dois robôs dependem de rede (API do GitHub, pooler do Supabase).
Rodar na sessão do usuário também é o que dispensa o `S4U`, o `RunLevel Highest`
e a senha armazenada: a tarefa passa a ser registrável sem administrador.

O atraso de 3 min é a margem para a rede terminar de subir depois do logon.

`StartWhenAvailable` sumiu porque só vale para gatilho de horário (recuperar
execução perdida). Com logon não existe execução perdida: ou você logou, ou a
máquina estava desligada — e nesse caso nenhum horário teria salvado.

## Logar várias vezes no dia não duplica nada

O 001 tem trava diária em `temp\estado.json`: commita no primeiro logon do dia e
sai no ato nos seguintes. O 002 é ping — rodar mais vezes só ajuda o keepalive.

## O que o `.bat` unificado garante

- **Independência**: o 002 roda mesmo se o 001 falhar (é `call`, não `&&`).
- **Exit code honesto**: devolve `1` se *qualquer* um dos dois falhar, `0` se os
  dois passarem. É o que aparece na coluna "Resultado da última execução".
- **Diagnóstico separado**: cada robô continua com o próprio arquivo de erro em
  `temp\` e a própria linha em `dbo.controle_cargas` (`id_carga` 1 e 2).

Os argumentos são repassados aos dois, então dá para testar a cadeia inteira sem
efeito colateral:

```powershell
cmd /c D:\ambiente_dev\automacoes\iniciar_robos.bat --dry-run
```

## Criar / recriar a tarefa

```powershell
powershell -ExecutionPolicy Bypass -File D:\ambiente_dev\automacoes\criar_tarefa_robos.ps1
```

Sem administrador ele cria a tarefa nova normalmente, mas **não consegue apagar
as duas antigas** (foram criadas com `RunLevel Highest`, e removê-las devolve
*Acesso negado*). Nesse caso rode uma vez como administrador — ou apague as duas
na mão no Agendador.

## Arquivos

```
automacoes\
├─ iniciar_robos.bat        chamado pela tarefa; roda os dois em sequência
├─ criar_tarefa_robos.ps1   cria a tarefa de logon e remove as antigas
├─ 001_check_github\        robô 001 + README próprio
└─ 002_check_supabase\      robô 002 + README próprio
```

O `002_check_supabase\criar_tarefa.ps1` está **obsoleto** — é o criador da tarefa
das 08:00. Ficou na pasta como registro da configuração antiga; não rode.
