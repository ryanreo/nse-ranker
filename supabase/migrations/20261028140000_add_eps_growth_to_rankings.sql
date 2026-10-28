-- Quality factor: EPS growth at the latest reported results, read from results news.
alter table public.rankings add column if not exists eps_growth numeric;
alter table public.rankings add column if not exists eps_period text;
