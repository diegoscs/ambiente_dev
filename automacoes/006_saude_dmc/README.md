# 006 · Saúde do DMC

Confere todo dia, **só lendo**, se os apps de clientes no DMC (o banco
`oaqhgdewlfjtepjfaiml`) estão de pé e seguros. Problema grave deixa o run
vermelho e o robô em ERROR no hub e no vigia; aviso vira notificação no hub.

| | |
|---|---|
| Lê | site de cada app, API, Auth e Edge Functions do DMC, e o banco (somente leitura) |
| Grava | nada no DMC. No DMP: o registro do robô (`id_carga = 6`) e as notificações |
| Quando | 05:00 de São Paulo, pelo `pg_cron` do DMP (depois do backup, antes do vigia) |
| `qtd_itens` | checagens que passaram |

## Checagens

| Checagem | Erro (run vermelho) | Aviso (notificação) |
|---|---|---|
| Site de cada app | não abre (HTTP ≠ 200, DNS, certificado) | mais de 5 s |
| API do DMC | não responde 200 | |
| Auth do DMC | cadastro aberto **ligado** | |
| Edge Functions | sumiu (404), quebrada (5xx) ou **aceitou chamada sem login** | resposta inesperada |
| RLS | alguma tabela do app sem RLS | |
| Tamanho do banco | | acima de 400 MB (o grátis tem 500) |
| Assinaturas | | negócio vencido (só leitura) ou vencendo em até 7 dias |
| Último lançamento | | (informativo) |

A regra de "vencido" é a mesma de `estoque.pode_escrever()`: não bloqueado e
fora da cortesia, do teste e do pago + 5 dias de folga.

As notificações só saem quando a lista de avisos **muda** (não repete todo
dia); quando os avisos somem, sai um "resolvido".

## Uso

```powershell
$py = "C:\Users\ferna\AppData\Local\Python\bin\python.exe"
& $py automacoes\006_saude_dmc\006_saude_dmc.py --dry-run   # checa tudo, não registra nem notifica
& $py automacoes\006_saude_dmc\006_saude_dmc.py --status
```

Secrets (`ambiente_dev`): `SUPABASE_URL`, `SUPABASE_KEY` (registro no DMP) e
`SUPABASE_DMC_URL`, `SUPABASE_DMC_KEY`, `SUPABASE_DMC_DB_URL`.

## Decisões

- **Só leitura no DMC** (regra dos ambientes isolados, 24/11/2026): robô do
  `ambiente_dev` lê o DMC à vontade, mas só processo de cliente altera o DMC.
- **Log só com contagens.** O `ambiente_dev` é público, e o log do Actions também:
  nome de cliente ou de negócio nunca aparece. A mensagem no hub também usa só números.
- **Lista de apps no código** (`APPS`): cliente novo = uma linha. Vira leitura de
  um cadastro no DMC (`plataforma.apps`) quando ele existir (kit de cliente novo).
- **Edge Function testada sem login:** a chave `apikey` passa o portão da
  Supabase, e a própria função tem que recusar. Se um dia aceitar, é erro.
- **Uma vez por dia**, para começar. O monitor de hora em hora, de dentro do
  DMC, é o próximo passo do kit de cliente novo.

## Estado

- **24/11/2026**: criado. Dry-run no DMC: site 0,7 s, API, função recusa sem
  login, Auth fechado, 13 MB, RLS em 13/13 tabelas; 1 aviso real (um negócio com
  teste/assinatura vencendo em até 7 dias).
