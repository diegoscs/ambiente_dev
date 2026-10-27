revoke all on public.vw_metricas_robos, public.vw_execucoes_diarias, public.vw_historico_legivel from anon, public;
revoke insert, update, delete, truncate, references, trigger on public.vw_metricas_robos, public.vw_execucoes_diarias, public.vw_historico_legivel from authenticated;
grant select on public.vw_metricas_robos, public.vw_execucoes_diarias, public.vw_historico_legivel to authenticated;
revoke execute on function public.fmt_quando(timestamptz), public.fmt_ha_quanto(timestamptz), public.fmt_duracao(numeric) from public, anon;
grant execute on function public.fmt_quando(timestamptz), public.fmt_ha_quanto(timestamptz), public.fmt_duracao(numeric) to authenticated;
