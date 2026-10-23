-- Creators can submit content; the server supplies ownership and review state.
alter table public.episodes alter column creator_id set default auth.uid();
alter table public.episodes alter column is_published set default false;
grant insert(id,drama_id,series_title,drama_title,episode_title,episode_number,coin_cost,description,genre,video_url,thumbnail_url) on public.episodes to authenticated;
grant update(episode_title) on public.episodes to authenticated;
-- Guests must not query the private unlock table while evaluating playback.
alter policy episode_playback_access on public.episodes to authenticated;
create policy guest_free_episode_playback on public.episodes for select to anon using(is_published and (is_free or coin_cost=0));
