drop table if exists public.daily_news_scores;
drop table if exists public.news_items;
drop table if exists public.watchlist_symbols;

create table if not exists public.instruments (
    symbol text primary key,
    name text not null,
    market text not null default 'KRX',
    enabled boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.external_analyses (
    id uuid primary key,
    symbol text not null,
    analysis_type text not null,
    source text not null,
    payload jsonb not null,
    observed_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.market_ticks (
    id bigint generated always as identity primary key,
    symbol text not null,
    occurred_at timestamptz not null,
    price double precision not null,
    trade_volume double precision not null,
    cumulative_volume double precision,
    source text not null default 'kis',
    raw jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.market_candles (
    symbol text not null,
    interval text not null check (interval in ('1m', '1d', '1w', '1mo')),
    opened_at timestamptz not null,
    open double precision not null,
    high double precision not null,
    low double precision not null,
    close double precision not null,
    volume double precision not null,
    source text not null default 'kis',
    updated_at timestamptz not null default now(),
    primary key (symbol, interval, opened_at)
);

create index if not exists external_analyses_symbol_observed_at_idx
    on public.external_analyses (symbol, observed_at desc);
create index if not exists market_ticks_symbol_occurred_at_idx
    on public.market_ticks (symbol, occurred_at desc);
create index if not exists market_candles_symbol_interval_opened_at_idx
    on public.market_candles (symbol, interval, opened_at desc);

alter table public.instruments enable row level security;
alter table public.external_analyses enable row level security;
alter table public.market_ticks enable row level security;
alter table public.market_candles enable row level security;

-- No public policies. Only the Engine backend credential accesses these tables.
