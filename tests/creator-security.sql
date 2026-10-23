begin;
insert into auth.users(id,email) values('10000000-0000-4000-8000-000000000101','zynora-test-creator@example.invalid'),('20000000-0000-4000-8000-000000000102','zynora-test-viewer@example.invalid');
select set_config('request.jwt.claims','{"sub":"10000000-0000-4000-8000-000000000101","role":"authenticated"}',true);
set local role authenticated;
insert into public.episodes(id,drama_id,series_title,drama_title,episode_title,episode_number,coin_cost,video_url)
values('00000000-0000-4000-8000-000000000201','zynora-transaction-test','Test','Test','Test',1,20,'https://ozshekxpuvganemaajms.supabase.co/storage/v1/object/public/zynora-videos/10000000-0000-4000-8000-000000000101/test.mp4');
do $$ begin
 begin update public.episodes set creator_id='20000000-0000-4000-8000-000000000102' where id='00000000-0000-4000-8000-000000000201'; raise exception 'FAIL: ownership writable'; exception when insufficient_privilege then null; end;
 begin update public.episodes set is_published=true where id='00000000-0000-4000-8000-000000000201'; raise exception 'FAIL: self publication permitted'; exception when insufficient_privilege then null; end;
 if not exists(select 1 from public.episodes where id='00000000-0000-4000-8000-000000000201' and not is_published and review_status='pending') then raise exception 'FAIL: submission bypassed moderation'; end if;
 begin
 insert into public.episodes(drama_id,series_title,episode_title,episode_number,coin_cost,video_url) values('zynora-second-test','Second','Second',1,0,'https://ozshekxpuvganemaajms.supabase.co/storage/v1/object/public/zynora-videos/10000000-0000-4000-8000-000000000101/test.mp4');
 raise exception 'FAIL: monthly limit bypassed';
 exception when others then if sqlerrm not like 'Your free plan includes%' then raise; end if; end;
end $$;
select set_config('request.jwt.claims','{"sub":"20000000-0000-4000-8000-000000000102","role":"authenticated"}',true);
do $$ begin
 if exists(select 1 from public.episodes where id='00000000-0000-4000-8000-000000000201') then raise exception 'FAIL: other creator draft visible'; end if;
 if exists(select 1 from public.creator_series where drama_id='zynora-transaction-test') then raise exception 'FAIL: private creator series visible'; end if;
end $$;
reset role;
select set_config('request.jwt.claims','{}',true);
update public.episodes set is_published=true where id='00000000-0000-4000-8000-000000000201';
select set_config('request.jwt.claims','{"role":"anon"}',true);
set local role anon;
do $$ begin
 if exists(select 1 from public.episodes where id='00000000-0000-4000-8000-000000000201') then raise exception 'FAIL: locked video visible to guest'; end if;
 if not public.get_episode_catalog('zynora-transaction-test') @> '[{"id":"00000000-0000-4000-8000-000000000201"}]'::jsonb then raise exception 'FAIL: catalog missing published episode'; end if;
end $$;
reset role;
select set_config('request.jwt.claims','{}',true);
select public.credit_paypal_purchase('20000000-0000-4000-8000-000000000102','coins_250',250,4.99,'USD','TEST-ROLLBACK-ORDER','TEST-ROLLBACK-CAPTURE');
update public.paypal_purchases set net_amount_usd=4 where paypal_capture_id='TEST-ROLLBACK-CAPTURE';
select set_config('request.jwt.claims','{"sub":"20000000-0000-4000-8000-000000000102","role":"authenticated"}',true);
set local role authenticated;
select public.unlock_episode('00000000-0000-4000-8000-000000000201');
select public.unlock_episode('00000000-0000-4000-8000-000000000201');
do $$ begin
 if not exists(select 1 from public.episodes where id='00000000-0000-4000-8000-000000000201') then raise exception 'FAIL: unlocked video unavailable'; end if;
 if exists(select 1 from public.creator_earnings where episode_id='00000000-0000-4000-8000-000000000201') then raise exception 'FAIL: viewer can see creator earnings'; end if;
end $$;
select set_config('request.jwt.claims','{"sub":"10000000-0000-4000-8000-000000000101","role":"authenticated"}',true);
do $$ begin
 if (select count(*) from public.creator_earnings where episode_id='00000000-0000-4000-8000-000000000201')<>1 then raise exception 'FAIL: duplicate earnings'; end if;
 if not exists(select 1 from public.creator_earnings where episode_id='00000000-0000-4000-8000-000000000201' and creator_usd=0.256 and platform_usd=0.064 and paid_coins=20) then raise exception 'FAIL: wrong 80/20 split'; end if;
end $$;
reset role;
select set_config('request.jwt.claims','{}',true);
update public.paypal_purchases set net_amount_usd=0 where paypal_capture_id='TEST-ROLLBACK-CAPTURE';
do $$ begin
 if exists(select 1 from public.creator_earnings where episode_id='00000000-0000-4000-8000-000000000201' and creator_usd<>0) then raise exception 'FAIL: refund reconciliation'; end if;
end $$;
rollback;
select 'PASS: creator isolation, moderation, monthly quota, catalog, locked playback, unlock idempotency, 80/20 earnings and refund reconciliation; all test data rolled back' as result;
