create table if not exists public.watchlist_symbols (
    symbol text primary key,
    name_ko text not null,
    market text not null,
    enabled boolean not null default true,
    created_at timestamptz not null default now()
);

create table if not exists public.news_items (
    id text primary key,
    symbol text not null references public.watchlist_symbols(symbol),
    published_at timestamptz,
    source text,
    title text not null,
    url text,
    summary_ko text not null,
    sentiment_score integer not null check (sentiment_score between -3 and 3),
    impact_score integer not null check (impact_score between 0 and 3),
    relevance_score integer not null check (relevance_score between 0 and 3),
    novelty text not null check (novelty in ('NEW', 'REPEAT', 'UNKNOWN')),
    risk_tags jsonb not null default '[]'::jsonb,
    confidence text not null check (confidence in ('LOW', 'MEDIUM', 'HIGH')),
    collected_at timestamptz not null default now(),
    prompt_version text not null,
    model text,
    input_tokens integer,
    output_tokens integer,
    estimated_cost_usd double precision
);

create table if not exists public.daily_news_scores (
    symbol text not null references public.watchlist_symbols(symbol),
    date date not null,
    item_count integer not null,
    weighted_score double precision not null,
    positive_count integer not null,
    negative_count integer not null,
    high_impact_count integer not null,
    negative_shock_count integer not null,
    top_summaries jsonb not null default '[]'::jsonb,
    risk_tags jsonb not null default '[]'::jsonb,
    primary key (symbol, date)
);

create index if not exists news_items_symbol_published_at_idx
    on public.news_items (symbol, published_at desc);

create index if not exists daily_news_scores_symbol_date_idx
    on public.daily_news_scores (symbol, date desc);

alter table public.watchlist_symbols enable row level security;
alter table public.news_items enable row level security;
alter table public.daily_news_scores enable row level security;

-- No public policies are created. The frontend reads through the engine API,
-- while backend ingestion uses a Supabase secret/service-role credential.
