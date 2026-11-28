# 007 · Saúde do DMP

Irmão do [006](../006_saude_dmc/README.md), para o banco **pessoal** (DMP:
hub, robôs, Minecraft e finanças). Confere todo dia, **só lendo**, se está de pé
e seguro. Erro deixa o run vermelho e avisa em `#alertas`; aviso vai para
`#alertas` só quando muda.

| | |
|---|---|
| Quando | 03:00 de São Paulo, pelo `pg_cron` (única hora cheia livre antes do vigia) |
| `qtd_itens` | checagens que passaram |

| Checagem | Erro | Aviso |
|---|---|---|
| Sites (hub-robos, server-galera, financas-app) | não abre | mais de 5 s |
| Auth do DMP | cadastro aberto ligado | |
| RLS em `public`, `private`, `openfinance` | tabela sem RLS | |
| Papel anônimo | com escrita em tabela ou view | |
| Tamanho do banco | | acima de 400 MB |
| pg_cron | | job que falhou nas últimas 24 h e não voltou a rodar com sucesso |
| Vault | sem `github_dispatch_token` | |

A API e o banco respondendo já são conferidos pelo keepalive (002), e os
disparos do pg_cron recusados pelo GitHub, pelo vigia.

O título do aviso no Discord é curto (é ele que decide se o aviso mudou); o
corpo explica cada um. No pg_cron: quantas falhas, de quando a quando (horário
de Brasília), o erro do Postgres, a provável causa e se o job está pausado.
Falha que já normalizou (houve sucesso depois) não avisa: fica como ok na
mensagem do histórico. O "✅ avisos resolvidos" diz quais eram.

```powershell
& $py automacoes\007_saude_dmp\007_saude_dmp.py --dry-run
```

## Estado

- **25/11/2026**: criado. O primeiro dry-run achou dois pontos: o Auth do DMP
  aceitava cadastro de qualquer pessoa (corrigir no painel) e o papel anônimo
  tinha escrita na `vw_saude_robos` (migration `20261125020300_robos_views_sem_escrita`).
- **28/11/2026**: alertas detalhados. Motivo: "pg_cron: 11 falha(s) em 24 h
  (radar_ofertas)" não dizia o que houve. Eram 11 rodadas de 27/11 entre 13:52
  e 13:56, com `function private.radar_rodada() does not exist`: na criação do
  radar, o agendamento entrou no banco antes da função (no repositório a ordem
  está certa). Depois rodou 668 vezes sem erro até a pausa.
