-- Radar de ofertas: resumo diario as 22:00 de Sao Paulo (01:00 UTC), pedido
-- de 27/11/2026 para acompanhar a variacao de precos. Uma mensagem por
-- produto ativo, no canal dele, com as ofertas das ultimas 24 h (22:00 de
-- ontem as 22:00 de hoje): menor e maior preco, menor preco das 24 h
-- anteriores e a lista com hora, preco, cupom, titulo e link.
-- Le so private.radar_avisos (30 dias de retencao).
-- Desligar: select cron.unschedule('radar_resumo_diario');

-- 855 -> '855'; 1549.9 -> '1549,90'
create or replace function private.radar_fmt(p_valor numeric)
returns text
language sql
immutable
set search_path = pg_catalog, pg_temp
as $$
  select regexp_replace(replace(to_char(p_valor, 'FM9999999990.00'), '.', ','), ',00$', '')
$$;

create or replace function private.radar_resumo_diario()
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
declare
  pr record;
  a record;
  v_fim timestamptz := now();
  v_ini timestamptz := now() - interval '24 hours';
  v_n integer;
  v_min numeric;
  v_max numeric;
  v_ontem numeric;
  v_variacao text;
  v_linhas text;
  v_txt text;
  v_rodape text;
  v_produtos integer := 0;
  v_ofertas integer := 0;
begin
  select case when bool_or(estado = 'falha') then '⚠️ O radar está com falha de leitura: veja o #alertas.'
              else 'Radar lendo normalmente.' end
    into v_rodape
    from private.radar_fontes where ativo;
  v_rodape := format(E'\n_%s Janela: 22:00 de ontem às 22:00 de hoje (Brasília)._', coalesce(v_rodape, ''));

  for pr in select * from private.radar_produtos where ativo order by nome loop
    v_produtos := v_produtos + 1;

    select count(*), min(preco), max(preco) into v_n, v_min, v_max
      from private.radar_avisos
     where id_produto = pr.id and dta_post >= v_ini and dta_post < v_fim;

    select min(preco) into v_ontem
      from private.radar_avisos
     where id_produto = pr.id and dta_post >= v_ini - interval '24 hours' and dta_post < v_ini;

    v_ofertas := v_ofertas + v_n;

    if v_n = 0 then
      v_txt := 'Nenhuma oferta nas últimas 24 h.'
               || coalesce(format(' No dia anterior, o menor preço foi R$ %s.', private.radar_fmt(v_ontem)), '');
    else
      v_variacao := case
        when v_ontem is null or v_min is null then ''
        when v_min < v_ontem then format(E'\n▼ R$ %s mais barato que o dia anterior (R$ %s)',
                                         private.radar_fmt(v_ontem - v_min), private.radar_fmt(v_ontem))
        when v_min > v_ontem then format(E'\n▲ R$ %s mais caro que o dia anterior (R$ %s)',
                                         private.radar_fmt(v_min - v_ontem), private.radar_fmt(v_ontem))
        else format(E'\n= mesmo menor preço do dia anterior (R$ %s)', private.radar_fmt(v_ontem)) end;

      v_linhas := '';
      for a in select dta_post, preco, canal_telegram, id_post,
                      (regexp_match(texto, 'cupom:?\s*([A-Z0-9]{4,})'))[1] as cupom,
                      left(regexp_replace(split_part(texto, E'\n', 1), '^[^[:alnum:]]+', ''), 70) as titulo,
                      (regexp_match(texto, 'https?://\S+'))[1] as link
                 from private.radar_avisos
                where id_produto = pr.id and dta_post >= v_ini and dta_post < v_fim
                order by dta_post
                limit 15 loop
        v_linhas := v_linhas || format(E'• %s · **%s**%s · %s\n%s[post](https://t.me/%s/%s)\n',
          to_char(a.dta_post at time zone 'America/Sao_Paulo', 'HH24:MI'),
          coalesce('R$ ' || private.radar_fmt(a.preco), 'sem preço'),
          coalesce(' · cupom `' || a.cupom || '`', ''),
          a.titulo,
          coalesce(a.link || ' · ', ''),
          a.canal_telegram, a.id_post);
      end loop;
      if v_n > 15 then
        v_linhas := v_linhas || format(E'… e mais %s oferta(s).\n', v_n - 15);
      end if;

      v_txt := format(E'**%s oferta(s)** · menor **R$ %s** · maior R$ %s%s\n\n%s',
                      v_n, coalesce(private.radar_fmt(v_min), '?'), coalesce(private.radar_fmt(v_max), '?'),
                      v_variacao, v_linhas);
    end if;

    perform private.radar_avisar(pr.canal,
      format('📋 %s · resumo de %s', pr.nome, to_char(v_fim at time zone 'America/Sao_Paulo', 'DD/MM')),
      v_txt || v_rodape, null, v_fim, 15114812);
  end loop;

  return jsonb_build_object('produtos', v_produtos, 'ofertas', v_ofertas);
end;
$$;

revoke all on function private.radar_fmt(numeric) from public, anon, authenticated;
revoke all on function private.radar_resumo_diario() from public, anon, authenticated;

-- 22:00 de Sao Paulo = 01:00 UTC (hora livre no pg_cron do DMP).
select cron.schedule('radar_resumo_diario', '0 1 * * *', $$select private.radar_resumo_diario()$$);
