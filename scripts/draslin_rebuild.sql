
CREATE TABLE IF NOT EXISTS rebuild_towns (
    town text PRIMARY KEY,
    round int NOT NULL DEFAULT 1,
    scale numeric NOT NULL DEFAULT 1 CHECK (scale > 0),   
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    board_channel_id bigint,
    board_message_id bigint
);

ALTER TABLE rebuild_towns ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT false;
ALTER TABLE rebuild_towns ADD COLUMN IF NOT EXISTS activated_at timestamptz;

ALTER TABLE rebuild_towns ADD COLUMN IF NOT EXISTS daily_cap int NOT NULL DEFAULT 90;


CREATE TABLE IF NOT EXISTS rebuild_projects (
    town text NOT NULL REFERENCES rebuild_towns(town),
    id text NOT NULL,
    ord int NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'ballot', 'building', 'done')),
    progress int NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    round int,                    
    started_at timestamptz,
    finished_at timestamptz,
    announced_at timestamptz,      
    PRIMARY KEY (town, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS rebuild_one_building ON rebuild_projects (town) WHERE status = 'building';


CREATE TABLE IF NOT EXISTS rebuild_needs (
    town text NOT NULL,
    project_id text NOT NULL,
    material text NOT NULL,
    needed int NOT NULL CHECK (needed > 0),
    delivered int NOT NULL DEFAULT 0 CHECK (delivered BETWEEN 0 AND needed),
    PRIMARY KEY (town, project_id, material),
    FOREIGN KEY (town, project_id) REFERENCES rebuild_projects (town, id)
);


CREATE TABLE IF NOT EXISTS rebuild_stockpile (
    town text NOT NULL REFERENCES rebuild_towns(town),
    material text NOT NULL,
    amount int NOT NULL DEFAULT 0 CHECK (amount >= 0),
    PRIMARY KEY (town, material)
);


CREATE TABLE IF NOT EXISTS rebuild_contributions (
    id bigserial PRIMARY KEY,
    town text NOT NULL REFERENCES rebuild_towns(town),
    discord_id bigint NOT NULL,
    source text NOT NULL CHECK (source IN ('discord', 'tiamat')),
    kind text NOT NULL CHECK (kind IN ('gather', 'donate', 'hands', 'grant')),
    project_id text,               
    material text NOT NULL,
    amount int NOT NULL CHECK (amount > 0),
    applied int NOT NULL DEFAULT 0, 
    crowns_spent bigint NOT NULL DEFAULT 0,  
    request_id uuid,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rebuild_contributions_user ON rebuild_contributions (discord_id, created_at);
CREATE INDEX IF NOT EXISTS rebuild_contributions_town ON rebuild_contributions (town, created_at);
CREATE INDEX IF NOT EXISTS rebuild_contributions_project ON rebuild_contributions (town, project_id);


CREATE TABLE IF NOT EXISTS rebuild_expeditions (
    discord_id bigint PRIMARY KEY,
    town text NOT NULL REFERENCES rebuild_towns(town),
    destination text NOT NULL,
    hours int NOT NULL CHECK (hours > 0),
    started_at timestamptz NOT NULL DEFAULT now(),
    returns_at timestamptz NOT NULL
);


CREATE TABLE IF NOT EXISTS rebuild_votes (
    town text NOT NULL REFERENCES rebuild_towns(town),
    round int NOT NULL,
    discord_id bigint NOT NULL,
    project_id text NOT NULL,
    source text NOT NULL DEFAULT 'discord' CHECK (source IN ('discord', 'tiamat')),
    voted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (town, round, discord_id)
);


CREATE TABLE IF NOT EXISTS rebuild_inbox (
    id bigserial PRIMARY KEY,
    town text NOT NULL REFERENCES rebuild_towns(town),
    discord_id bigint NOT NULL,
    activity text NOT NULL,               
    ref text NOT NULL,                    
    material text NOT NULL,
    amount int NOT NULL CHECK (amount > 0 AND amount <= 150),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    applied_at timestamptz,
    applied int,                          
    result text,                          
    UNIQUE (discord_id, ref)
);
CREATE INDEX IF NOT EXISTS rebuild_inbox_pending ON rebuild_inbox (id) WHERE applied_at IS NULL;


CREATE TABLE IF NOT EXISTS rebuild_hunt_finds (
    discord_id bigint NOT NULL,
    day date NOT NULL,
    slot int NOT NULL CHECK (slot BETWEEN 1 AND 3),
    map_id int NOT NULL,
    x int NOT NULL,
    y int NOT NULL,
    material text NOT NULL,
    amount int NOT NULL,
    found_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (discord_id, day, slot)
);

CREATE TABLE IF NOT EXISTS rebuild_haul_runs (
    id uuid PRIMARY KEY,
    discord_id bigint NOT NULL,
    name text,
    day date NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz NOT NULL,
    seconds numeric(7,1) NOT NULL CHECK (seconds > 0),
    medal text CHECK (medal IN ('gold', 'silver', 'bronze')),
    paid boolean NOT NULL,
    amount int NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS rebuild_haul_runs_week ON rebuild_haul_runs (finished_at);
CREATE INDEX IF NOT EXISTS rebuild_haul_runs_player ON rebuild_haul_runs (discord_id, day);


CREATE TABLE IF NOT EXISTS rebuild_rescues (
    discord_id bigint NOT NULL,
    person text NOT NULL,
    name text,
    rescued_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (discord_id, person)
);

.
CREATE TABLE IF NOT EXISTS rebuild_raid_sites (
    site text PRIMARY KEY,
    cleared_at timestamptz NOT NULL,
    battle_id text
);


CREATE TABLE IF NOT EXISTS rebuild_events (
    id bigserial PRIMARY KEY,
    town text NOT NULL REFERENCES rebuild_towns(town),
    kind text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    posted_at timestamptz
);
CREATE INDEX IF NOT EXISTS rebuild_events_pending ON rebuild_events (id) WHERE posted_at IS NULL;

