-- nse-ranker: data pushed from the local tool after each run, read by the dashboard.
-- Applied to Supabase project "nse-ranker" (auqlsgcloziyrugkerxr) on 28 Oct 2026.
-- Row-level security is on with no policies: nothing is readable or writable through the public API.
-- The tool writes with the secret key; the dashboard reads through the owner's Supabase connection.

create table public.stocks (
  ticker   text primary key,
  name     text not null,
  sector   text not null,
  type     text not null,
  currency text not null,
  status   text not null,          -- rank | watch | out
  notes    text
);

create table public.prices (
  ticker text not null,
  day    date not null,
  close  numeric not null,
  volume bigint not null default 0,
  primary key (ticker, day)
);

create table public.rankings (
  run_date          date not null,
  ticker            text not null,
  position          int,
  formula_position  int,
  move              int not null default 0,
  name              text,
  sector            text,
  score             numeric,
  "case"            text,
  explanation       text,
  evidence          text,
  reasons           text,
  hold              text,
  price             numeric,
  price_date        date,
  ret_6m            numeric,
  pe                numeric,
  div_yield         numeric,
  daily_move        numeric,
  f_momentum        int,
  f_value           int,
  f_dividend        int,
  f_quality         int,
  f_risk            int,
  f_news            int,
  f_opinion         int,
  opinion_summary   text,
  opinion_posts     int,
  primary key (run_date, ticker)
);

create table public.stats (
  run_date              date not null,
  ticker                text not null,
  ret_1m                numeric,
  ret_3m                numeric,
  ret_6m                numeric,
  ret_12m               numeric,
  high_52w              numeric,
  low_52w               numeric,
  from_high             numeric,   -- how far below the 52-week high (negative)
  ma50                  numeric,
  ma200                 numeric,
  volatility_yr         numeric,   -- annualised standard deviation of daily returns
  max_drawdown_12m      numeric,
  traded_value_60d      numeric,   -- average KES traded a day
  traded_days_share     numeric,
  sector_rank           int,
  sector_size           int,
  sector_median_pe      numeric,
  sector_median_yield   numeric,
  news_good             int,
  news_bad              int,
  news_neutral          int,
  articles_30d          int,
  posts_reddit          int,
  posts_x               int,
  primary key (run_date, ticker)
);

create table public.news_tags (
  id        text primary key,
  day       date not null,
  ticker    text,
  sector    text,
  about     text not null,
  event     text not null,
  direction int not null,
  strength  int not null,
  title     text not null,
  url       text not null
);

create table public.articles (
  key    text primary key,     -- ticker|url
  ticker text not null,
  day    date not null,
  title  text not null,
  source text not null,
  url    text not null
);

create table public.posts (
  id       text primary key,   -- hash of ticker, platform and text
  ticker   text not null,
  platform text not null,      -- Reddit | X
  posted   date,
  text     text not null       -- no usernames, no links
);

create table public.not_ranked (
  ticker text primary key,
  name   text,
  status text not null,
  reason text
);

create table public.method (
  key      text primary key,
  factor   text not null,
  weight   int not null,
  measures text not null,
  hold     text
);

create index prices_day_idx on public.prices (day);
create index rankings_ticker_idx on public.rankings (ticker, run_date);
create index stats_ticker_idx on public.stats (ticker, run_date);
create index news_tags_ticker_idx on public.news_tags (ticker, day);
create index articles_ticker_idx on public.articles (ticker, day);
create index posts_ticker_idx on public.posts (ticker, posted);

alter table public.stocks     enable row level security;
alter table public.prices     enable row level security;
alter table public.rankings   enable row level security;
alter table public.stats      enable row level security;
alter table public.news_tags  enable row level security;
alter table public.articles   enable row level security;
alter table public.posts      enable row level security;
alter table public.not_ranked enable row level security;
alter table public.method     enable row level security;
