
revoke execute on function public.add_coins(uuid,integer,text,text), public.spend_coins(uuid,integer,text,text), public.claim_reward(text), public.claim_ad_reward(), public.unlock_episode_with_ad(uuid,text,text) from public,anon,authenticated;
grant execute on function public.add_coins(uuid,integer,text,text), public.spend_coins(uuid,integer,text,text) to service_role;
revoke execute on function public.claim_daily_reward(),public.get_remaining_ad_unlocks(),public.unlock_episode(uuid) from public,anon;
grant execute on function public.claim_daily_reward(),public.get_remaining_ad_unlocks(),public.unlock_episode(uuid) to authenticated;

create or replace function public.get_episode_catalog(p_drama_id text default null)
returns jsonb language sql stable security definer set search_path=public,pg_temp as $$
select coalesce(jsonb_agg((to_jsonb(e)-'video_url') || jsonb_build_object('has_video',nullif(e.video_url,'') is not null) order by e.drama_id,e.episode_number),'[]'::jsonb)
from public.episodes e
where (e.is_published=true or e.creator_id=(select auth.uid()))
and (p_drama_id is null or e.drama_id=p_drama_id);
$$;
revoke execute on function public.get_episode_catalog(text) from public;
grant execute on function public.get_episode_catalog(text) to anon,authenticated;

create or replace function public.unlock_episode(p_episode_id uuid)
returns bigint language plpgsql security definer set search_path=public,pg_temp as $$
declare
v_user_id uuid:=auth.uid();
v_cost integer;
v_balance bigint;
begin
if v_user_id is null then raise exception 'You must be logged in.';end if;
select case when is_free then 0 else greatest(coin_cost,0) end into v_cost from public.episodes where id=p_episode_id and is_published=true;
if not found then raise exception 'Published episode not found.';end if;
insert into public.wallets(user_id,balance) values(v_user_id,0) on conflict(user_id) do nothing;
select balance into v_balance from public.wallets where user_id=v_user_id for update;
if exists(select 1 from public.unlocked_episodes where user_id=v_user_id and episode_id=p_episode_id) then return v_balance;end if;
if v_balance<v_cost then raise exception 'Not enough Zynora Coins.';end if;
if v_cost>0 then
update public.wallets set balance=balance-v_cost,updated_at=now() where user_id=v_user_id returning balance into v_balance;
insert into public.coin_transactions(user_id,transaction_type,amount,balance_after,reference_type,reference_id,description)
values(v_user_id,'EPISODE_UNLOCK',-v_cost,v_balance,'EPISODE_UNLOCK',v_user_id::text||':'||p_episode_id::text,'Episode unlock');
end if;
insert into public.unlocked_episodes(user_id,episode_id,unlocked_at) values(v_user_id,p_episode_id,now());
return v_balance;
end;$$;

