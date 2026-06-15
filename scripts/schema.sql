-- Branching campaign content imported by the offline campaign editor.
CREATE TABLE IF NOT EXISTS campaign_content (
    campaign_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    start_node_key TEXT NOT NULL,
    campaign_json TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS player_campaigns (
    user_id BIGINT NOT NULL,
    campaign_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    current_node_key TEXT NOT NULL,
    history_json TEXT NOT NULL DEFAULT '[]',
    choices_json TEXT NOT NULL DEFAULT '{}',
    unlocks_json TEXT NOT NULL DEFAULT '[]',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, campaign_key)
);

CREATE TABLE IF NOT EXISTS player_reputation (
    user_id BIGINT NOT NULL,
    reputation_key TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 0,
    rank INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, reputation_key)
);

CREATE TABLE IF NOT EXISTS content_monsters (
    monster_key TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    tier INTEGER NOT NULL DEFAULT 1,
    hp INTEGER NOT NULL,
    attack INTEGER NOT NULL,
    defense INTEGER NOT NULL,
    element TEXT NOT NULL DEFAULT 'Nature',
    url TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
