-- Creator accounts, moderation, private playback, and revenue attribution.
-- Existing paid/bonus coin balances are preserved. New paid coin lots are tracked
-- from deployment onward; historical coins are not assigned an invented USD value.
begin;
create schema if not exists zynora_private;
revoke all on schema zynora_private from public,anon,authenticated;

create table if not exists public.creator_series (
 drama_id text primary key,
 creator_id uuid not null references auth.users(id),
 title text not null check(length(btrim(title)) between 1 and 150),
 created_at timestamptz not null default now()
);
alter table public.creator_series enable row level security;
grant select on public.creator_series to authenticated;
create policy creator_series_own_read on public.creator_series for select to authenticated using(creator_id=(select auth.uid()));
insert into public.creator_series(drama_id,creator_id,title,created_at)
select distinct on(drama_id) drama_id,creator_id,coalesce(nullif(series_title,''),nullif(drama_title,''),'Untitled drama'),created_at
from public.episodes where creator_id is not null and drama_id is not null order by drama_id,created_at
on conflict do nothing;

alter table public.episodes add column if not exists review_status text not null default 'pending';
alter table public.episodes add column if not exists review_note text;
update public.episodes set review_status='approved' where is_published=true;

create or replace function zynora_private.guard_creator_episode()
returns trigger language plpgsql security definer set search_path='' as $$
declare uid uuid:=auth.uid(); owner_id uuid; n integer;
begin
 if uid is null then
   if new.is_published then new.review_status:='approved'; end if;
   return new;
 end if;
 if new.creator_id is distinct from uid then raise exception 'You can manage only your own episodes.'; end if;
 if tg_op='UPDATE' and (new.creator_id is distinct from old.creator_id or new.drama_id is distinct from old.drama_id or new.id is distinct from old.id) then raise exception 'Episode ownership and series cannot be changed.'; end if;
 if new.drama_id is null or length(new.drama_id)>100 or length(btrim(coalesce(new.episode_title,''))) not between 1 and 150 or new.episode_number<1 or new.coin_cost<0 or new.coin_cost>10000 then raise exception 'Check the series, title, episode number and coin cost.'; end if;
 perform pg_advisory_xact_lock(hashtextextended(uid::text,0));
 select creator_id into owner_id from public.creator_series where drama_id=new.drama_id;
 if found then
   if owner_id<>uid then raise exception 'This drama belongs to another creator.'; end if;
 else
   select count(*) into n from public.creator_series where creator_id=uid and created_at>=date_trunc('month',now() at time zone 'UTC') at time zone 'UTC';
   if n>=1 then raise exception 'Your free plan includes one new drama series per calendar month (UTC). You can still add episodes to existing series.'; end if;
   insert into public.creator_series(drama_id,creator_id,title) values(new.drama_id,uid,new.series_title);
 end if;
 if exists(select 1 from public.episodes where drama_id=new.drama_id and episode_number=new.episode_number and id<>new.id) then raise exception 'This episode number is already used in this series.'; end if;
 if new.video_url is null or new.video_url not like 'https://ozshekxpuvganemaajms.supabase.co/storage/v1/object/public/zynora-videos/'||uid::text||'/%' then raise exception 'Upload a video from your own account.'; end if;
 if new.thumbnail_url is not null and new.thumbnail_url not like 'https://ozshekxpuvganemaajms.supabase.co/storage/v1/object/public/zynora-thumbnails/'||uid::text||'/%' then raise exception 'Upload a cover from your own account.'; end if;
 new.is_free:=(new.coin_cost=0);
 new.is_published:=false;
 new.review_status:='pending';
 new.review_note:=null;
 return new;
end;$$;
create trigger guard_creator_episode before insert or update on public.episodes for each row execute function zynora_private.guard_creator_episode();

drop policy if exists "Anyone can view episodes" on public.episodes;
drop policy if exists "Public can view published episodes" on public.episodes;
create policy episode_playback_access on public.episodes for select to anon,authenticated using(
 creator_id=(select auth.uid()) or (is_published and (is_free or coin_cost=0 or exists(select 1 from public.unlocked_episodes u where u.episode_id=episodes.id and u.user_id=(select auth.uid()))))
);
-- The catalog RPC returns metadata only; playback remains protected by RLS.
alter table public.episodes enable row level security;
drop policy if exists "Public can view Zynora videos" on storage.objects;
create policy zynora_video_playback on storage.objects for select to anon,authenticated using(
 bucket_id='zynora-videos' and ((storage.foldername(name))[1]=(select auth.uid())::text or exists(
 select 1 from public.episodes e where e.video_url='https://ozshekxpuvganemaajms.supabase.co/storage/v1/object/public/zynora-videos/'||storage.objects.name
 ))
);
-- Published media is immutable for creators; changes require a new submission.
drop policy if exists "Users can update Zynora videos" on storage.objects;
drop policy if exists "Users can delete Zynora videos" on storage.objects;
create policy creator_cleanup_unused_video on storage.objects for delete to authenticated using(
 bucket_id='zynora-videos' and (storage.foldername(name))[1]=(select auth.uid())::text and not exists(select 1 from public.episodes e where e.creator_id=(select auth.uid()) and e.video_url='https://ozshekxpuvganemaajms.supabase.co/storage/v1/object/public/zynora-videos/'||storage.objects.name)
);
update storage.buckets set public=false,file_size_limit=52428800,allowed_mime_types=array['video/mp4','video/webm'] where id='zynora-videos';
update storage.buckets set file_size_limit=5242880,allowed_mime_types=array['image/jpeg','image/png','image/webp'] where id='zynora-thumbnails';

alter table public.paypal_purchases add column if not exists net_amount_usd numeric(18,6) check(net_amount_usd>=0 and net_amount_usd<=amount_usd);
create table zynora_private.paid_coin_lots (
 purchase_id uuid primary key references public.paypal_purchases(id),
 user_id uuid not null,
 remaining integer not null check(remaining>=0),
 created_at timestamptz not null default now()
);
alter table zynora_private.paid_coin_lots enable row level security;
create table public.creator_earnings (
 id uuid primary key default gen_random_uuid(),
 creator_id uuid not null references auth.users(id),
 episode_id uuid not null references public.episodes(id),
 purchase_id uuid not null references public.paypal_purchases(id),
 transaction_id uuid not null references public.coin_transactions(id),
 paid_coins integer not null check(paid_coins>0),
 net_revenue_usd numeric(18,6),
 creator_usd numeric(18,6) generated always as (round(net_revenue_usd*0.80,6)) stored,
 platform_usd numeric(18,6) generated always as (net_revenue_usd-round(net_revenue_usd*0.80,6)) stored,
 created_at timestamptz not null default now(),
 unique(transaction_id,purchase_id)
);
alter table public.creator_earnings enable row level security;
grant select on public.creator_earnings to authenticated;
create policy own_creator_earnings on public.creator_earnings for select to authenticated using(creator_id=(select auth.uid()));
create or replace function zynora_private.record_paid_lot()
returns trigger language plpgsql security definer set search_path='' as $$
begin
 if new.status='COMPLETED' then insert into zynora_private.paid_coin_lots(purchase_id,user_id,remaining) values(new.id,new.user_id,new.coins) on conflict do nothing; end if;
 return new;
end;$$;
create trigger record_paid_lot after insert on public.paypal_purchases for each row execute function zynora_private.record_paid_lot();
create or replace function zynora_private.attribute_creator_revenue()
returns trigger language plpgsql security definer set search_path='' as $$
declare remaining_cost integer; lot record; used integer; ep public.episodes; eid uuid;
begin
 if new.amount>=0 then return new; end if;
 remaining_cost:=-new.amount;
 if new.transaction_type='EPISODE_UNLOCK' then
   begin eid:=split_part(new.reference_id,':',2)::uuid; exception when invalid_text_representation then eid:=null; end;
   select * into ep from public.episodes where id=eid;
 end if;
 for lot in select l.*,p.coins,p.net_amount_usd from zynora_private.paid_coin_lots l join public.paypal_purchases p on p.id=l.purchase_id where l.user_id=new.user_id and l.remaining>0 order by l.created_at,l.purchase_id for update of l loop
   used:=least(lot.remaining,remaining_cost);
   update zynora_private.paid_coin_lots set remaining=remaining-used where purchase_id=lot.purchase_id;
   if ep.creator_id is not null and ep.creator_id<>new.user_id then
     insert into public.creator_earnings(creator_id,episode_id,purchase_id,transaction_id,paid_coins,net_revenue_usd)
     values(ep.creator_id,ep.id,lot.purchase_id,new.id,used,round(lot.net_amount_usd*used/lot.coins,6));
   end if;
   remaining_cost:=remaining_cost-used;
   exit when remaining_cost=0;
 end loop;
 return new;
end;$$;
create trigger attribute_creator_revenue after insert on public.coin_transactions for each row execute function zynora_private.attribute_creator_revenue();
create or replace function zynora_private.reconcile_creator_net()
returns trigger language plpgsql security definer set search_path='' as $$
begin
 perform 1 from public.wallets where user_id=new.user_id for update;
 update public.creator_earnings set net_revenue_usd=round(new.net_amount_usd*paid_coins/new.coins,6) where purchase_id=new.id;
 return new;
end;$$;
create trigger reconcile_creator_net after update of net_amount_usd on public.paypal_purchases for each row execute function zynora_private.reconcile_creator_net();
create index creator_series_owner_month on public.creator_series(creator_id,created_at);
create index creator_earnings_owner on public.creator_earnings(creator_id,created_at);
create index creator_earnings_purchase on public.creator_earnings(purchase_id);
create index paid_coin_lots_user on zynora_private.paid_coin_lots(user_id,created_at) where remaining>0;
-- Cash earnings remain subject to payment/refund review; this does not send payouts.
commit;
