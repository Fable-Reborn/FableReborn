"""Permanent cosmetic ownership: starter themes are free, collectible themes drop from gameplay."""

from dataclasses import dataclass
import random

from utils import misc as rpgtools
from .themes import EVENT_THEMES, THEMES, resolve_theme

# Boolean profile columns that unlock event themes (see EVENT_THEMES).
PROFILE_FLAG_COLUMNS = tuple(sorted({theme.unlock_flag for theme in EVENT_THEMES if theme.unlock_flag}))


@dataclass(frozen=True)
class UnlockRule:
    stat: str
    target: int = 0
    god: str = ""
    flag: str = ""

    @property
    def label(self):
        if self.stat == "free":
            return "Available to every adventurer"
        if self.stat == "drop":
            return "Found during gameplay"
        if self.stat == "event":
            return "Awarded during events"
        if self.god:
            return f"Reach level {self.target} while following {self.god}"
        return {
            "level": f"Reach level {self.target}",
            "pvpwins": f"Win {self.target:,} PvP battles",
            "money": f"Hold ${self.target:,} on your character",
            "pet_count": f"Own {self.target} pet{'s' if self.target != 1 else ''}",
            "pet_trust": f"Have a pet with {self.target}% trust",
        }[self.stat]

    def met(self, facts):
        if self.stat == "event":
            # Granted explicitly, or claimed when its boolean profile column is true.
            return bool(self.flag) and facts.get(self.flag) is True
        return self.stat in ("free", "drop") or (
            int(facts.get(self.stat, 0) or 0) >= self.target
            and (not self.god or str(facts.get("god") or "").casefold() == self.god.casefold())
        )

    def progress(self, facts):
        if self.stat == "free":
            return self.label
        if self.stat == "drop":
            return "Must be discovered"
        if self.stat == "event":
            return self.label
        value = max(0, int(facts.get(self.stat, 0) or 0))
        progress = f"{min(value, self.target):,}/{self.target:,}"
        if self.god:
            return f"Level {progress} · Following {facts.get('god') or 'no god'}"
        return f"{self.label} · {progress}"


# ---------------------------------------------------------------------------
# Drop rarity tiers — higher weight = more common
# ---------------------------------------------------------------------------

RARITY_WEIGHTS = {
    "Common": 68,
    "Uncommon": 26,
    "Rare": 10,
    "Epic": 4,
    "Legendary": 1.25,
    "Mythic": 0.75,
    "Transcendent": 0.30,
}

RARITY_EMOJI = {
    "Common": "🟢",
    "Uncommon": "🔵",
    "Rare": "🟣",
    "Epic": "🟠",
    "Legendary": "🔴",
    "Mythic": "💠",
    "Transcendent": "🌟",
    "Event": "🎟️",
}

# Per-source drop chance: the probability that a roll happens at all.
# The calling cog decides WHEN to call roll_theme_drop; these defaults
# are available if you want a shared constant.
DROP_CHANCES = {
    "pve": 0.10,
    "adventure": 0.20,
    "bt": 0.15,
    "pvp": 0.05,
    "boss": 0.08,
}


RANDOM_DROP_SOURCES = frozenset({"pve", "adventure", "bt", "boss"})


@dataclass(frozen=True)
class ThemeDrop:
    """Describes how a collectible theme is earned through gameplay drops."""
    unlock: UnlockRule
    rarity: str
    weight: float
    drop_sources: frozenset[str] = RANDOM_DROP_SOURCES
    hint: str = "Drops from adventures, PvE, Battle Tower, and Ice Dragon"


# ---------------------------------------------------------------------------
# Collectible theme catalogue — edit one line to rebalance
# ---------------------------------------------------------------------------

COLLECTIBLE_THEMES: dict[str, ThemeDrop] = {
    "cloverpony": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "breadandembers": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "silverhook": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "coalwhisker": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "patchworkcamp": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "thimbleguard": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "jadeapothecary": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "silkroadwyrm": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "bellkeeper": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "inkfin": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "gildedrook": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "auroraferry": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "rubyforge": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "opalunicorn": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "amethystbastion": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "honeycrown": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "duskmoth": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "thundercolossus": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "sableopera": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "coralcitadel": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "dawnpegasus": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "seraphimvault": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
    "winterregent": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
    "gravepony": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
    "opalodyssey": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
    "dreamsovereign": ThemeDrop(UnlockRule("drop"), "Mythic", RARITY_WEIGHTS["Mythic"]),
    "eternityloom": ThemeDrop(UnlockRule("drop"), "Mythic", RARITY_WEIGHTS["Mythic"]),
    "sunweaver": ThemeDrop(UnlockRule("drop"), "Transcendent", RARITY_WEIGHTS["Transcendent"]),
    "nightpalace": ThemeDrop(UnlockRule("drop"), "Transcendent", RARITY_WEIGHTS["Transcendent"]),
    "worldtreeheart": ThemeDrop(UnlockRule("drop"), "Transcendent", RARITY_WEIGHTS["Transcendent"]),
    "emberkettle": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "mossback": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "brassbeak": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "moonharvest": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "stormheron": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "velvetprowl": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "emberbloom": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "tideweaver": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "amberreliquary": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "frostgardener": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "leviathanswake": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "gravebloom": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "allworlds": ThemeDrop(UnlockRule("drop"), "Mythic", RARITY_WEIGHTS["Mythic"]),
    "tynfdarius": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "mechaknight": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "umbracrown": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
    "deimos": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
    "voiddragon": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
    "nullstar": ThemeDrop(UnlockRule("drop"), "Mythic", RARITY_WEIGHTS["Mythic"]),
    "boneglass": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "drownedpearl": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
    "worldheart": ThemeDrop(UnlockRule("drop"), "Mythic", RARITY_WEIGHTS["Mythic"]),
    "sandreign": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "lanternwake": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "glasswing": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "porcelain": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "firstflame": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
    "unwritten": ThemeDrop(UnlockRule("drop"), "Mythic", RARITY_WEIGHTS["Mythic"]),
    "laststar": ThemeDrop(UnlockRule("drop"), "Mythic", RARITY_WEIGHTS["Mythic"]),
    "moonbunny": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "slime": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "chickencow": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "mushroom": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "frogzard": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "lotus": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "woodelf": ThemeDrop(UnlockRule("drop"), "Common", RARITY_WEIGHTS["Common"]),
    "darkelf": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "highelf": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "kitsune": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "mimic": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "clockwork": ThemeDrop(UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"]),
    "elysia": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "sepulchure": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "drakath": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "storm": ThemeDrop(UnlockRule("drop"), "Rare", RARITY_WEIGHTS["Rare"]),
    "leviathan": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "phoenix": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "bloodmoon": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "astral": ThemeDrop(UnlockRule("drop"), "Epic", RARITY_WEIGHTS["Epic"]),
    "eclipse": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
    "elysia_ascendant": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
    "sepulchure_unbound": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
    "drakath_incarnate": ThemeDrop(UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"]),
}


# Unified rule catalog: free starters + collectible prerequisites.
RULES = {
    "classic": UnlockRule("free"),
    "dragon": UnlockRule("free"),
    "evil": UnlockRule("free"),
    "chaos": UnlockRule("free"),
    "good": UnlockRule("free"),
    "forest": UnlockRule("free"),
    "frost": UnlockRule("free"),
    **{key: drop.unlock for key, drop in COLLECTIBLE_THEMES.items()},
    **{theme.key: UnlockRule("event", flag=theme.unlock_flag) for theme in EVENT_THEMES},
}


@dataclass
class ThemeState:
    current: str
    unlocked: set[str]
    facts: dict
    newly_unlocked: tuple[str, ...] = ()


class ThemeLocked(Exception):
    def __init__(self, theme, state):
        self.theme = theme
        self.state = state
        super().__init__("Discover this theme through gameplay before using it.")


# ---------------------------------------------------------------------------
# Drop pool & rolling
# ---------------------------------------------------------------------------

def get_drop_pool(facts, source):
    """All active activities share the full collectible pool, including owned keys.

    Starters and event exclusives never enter this catalogue. Ownership, stats and
    collection progress must not change these per-theme probabilities. Source is
    validated here and recorded as award provenance; callers apply trigger rates.
    """
    if source not in RANDOM_DROP_SOURCES:
        return []
    return [(key, drop.weight) for key, drop in COLLECTIBLE_THEMES.items()]


def theme_drop_message(theme_key, prefix, recipient="You"):
    """Reveal only the theme just awarded, with commands the owner can use now."""
    theme = THEMES[theme_key]
    drop = COLLECTIBLE_THEMES[theme_key]
    return (
        f"🎉 **Profile Theme Unlocked!**\n"
        f"{recipient} discovered {RARITY_EMOJI[drop.rarity]} **{theme.name}** — **{drop.rarity}**!\n"
        f"Preview: `{prefix}prpg preview {theme.key}`\n"
        f"Equip: `{prefix}prpg theme {theme.key}`"
    )


async def roll_theme_drop(pool, user_id, source):
    """Roll for a random collectible theme drop from the given activity source.

    Returns the theme key (str) if one was won and granted, or None.
    Roll once against the full weighted collectible pool. An owned result returns
    None silently, without rerolling or recording a new award. The character row
    stays locked through the ownership check and insert to serialize parallel wins.

    Typical usage from a PvE / adventure / BT cog::

        import random
        from cogs.profile.theme_unlocks import roll_theme_drop, DROP_CHANCES

        if random.random() < DROP_CHANCES.get("pve", 0):
            theme_key = await roll_theme_drop(bot.pool, user_id, "pve")
            if theme_key:
                ...  # announce the drop to the player
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            profile = await conn.fetchrow(
                'SELECT xp, money, pvpwins, god, prpg_theme FROM profile WHERE "user" = $1 FOR UPDATE;', user_id,
            )
            if profile is None:
                return None
            rows = await conn.fetch('SELECT theme_key FROM profile_theme_unlocks WHERE user_id = $1;', user_id)
            owned = {row["theme_key"] for row in rows} | {"classic"}

            eligible = get_drop_pool({}, source)
            if not eligible:
                return None

            keys, weights = zip(*eligible)
            chosen = random.choices(keys, weights=weights, k=1)[0]
            if chosen in owned:
                return None

            await conn.execute(
                'INSERT INTO profile_theme_unlocks (user_id, theme_key, source) VALUES ($1, $2, $3) ON CONFLICT (user_id, theme_key) DO NOTHING;',
                user_id, chosen, f"drop:{source}",
            )
            return chosen


# ---------------------------------------------------------------------------
# Schema, claiming, saving, granting
# ---------------------------------------------------------------------------

async def ensure_theme_schema(pool):
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Serialize first-time DDL across bot shards.
            await conn.execute("SELECT pg_advisory_xact_lock($1);", 7372746801)
            await conn.execute("ALTER TABLE profile ADD COLUMN IF NOT EXISTS prpg_theme TEXT NOT NULL DEFAULT 'classic';")
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS profile_theme_unlocks (
                    user_id BIGINT NOT NULL REFERENCES profile ("user") ON DELETE CASCADE,
                    theme_key TEXT NOT NULL,
                    unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    source TEXT NOT NULL DEFAULT 'progression',
                    PRIMARY KEY (user_id, theme_key)
                );
            ''')
            # Existing equipped launch cosmetics are grandfathered in. Repeating
            # this on another shard/reload is safe and never overwrites provenance.
            await conn.execute('''
                INSERT INTO profile_theme_unlocks (user_id, theme_key, source)
                SELECT "user", prpg_theme, 'legacy-equipped' FROM profile
                WHERE prpg_theme = ANY($1::text[])
                ON CONFLICT (user_id, theme_key) DO NOTHING;
            ''', ["dragon", "evil", "chaos", "good", "forest", "frost"])
            # Event unlock flags; names are validated identifiers in event_theme().
            for column in PROFILE_FLAG_COLUMNS:
                await conn.execute(f'ALTER TABLE profile ADD COLUMN IF NOT EXISTS "{column}" BOOLEAN NOT NULL DEFAULT FALSE;')


async def _claim_locked(conn, user_id):
    """Caller holds a transaction; serialize grants/equips against this character."""
    flags = "".join(f', "{column}"' for column in PROFILE_FLAG_COLUMNS)
    profile = await conn.fetchrow(
        f'SELECT xp, money, pvpwins, god, prpg_theme{flags} FROM profile WHERE "user" = $1 FOR UPDATE;', user_id,
    )
    if profile is None:
        return None
    facts = dict(profile)
    facts["level"] = rpgtools.xptolevel(facts.get("xp") or 0)
    pets = await conn.fetchrow(
        'SELECT COUNT(*) AS pet_count, COALESCE(MAX(trust_level), 0) AS pet_trust FROM monster_pets WHERE user_id = $1;', user_id,
    )
    facts.update(dict(pets))
    rows = await conn.fetch('SELECT theme_key FROM profile_theme_unlocks WHERE user_id = $1;', user_id)
    owned = {row["theme_key"] for row in rows if row["theme_key"] in THEMES} | {"classic"}
    # Only auto-claim free (starter) themes; collectible themes come from drops.
    new = tuple(key for key, rule in RULES.items() if key not in owned and key not in COLLECTIBLE_THEMES and rule.met(facts))
    starters = [key for key in new if RULES[key].stat != "event"]
    if starters:
        await conn.executemany(
            'INSERT INTO profile_theme_unlocks (user_id, theme_key) VALUES ($1, $2) ON CONFLICT (user_id, theme_key) DO NOTHING;',
            [(user_id, key) for key in starters],
        )
    flagged = [key for key in new if RULES[key].stat == "event"]
    if flagged:
        await conn.executemany(
            'INSERT INTO profile_theme_unlocks (user_id, theme_key, source) VALUES ($1, $2, $3) ON CONFLICT (user_id, theme_key) DO NOTHING;',
            [(user_id, key, f"event-flag:{RULES[key].flag}") for key in flagged],
        )
    owned.update(new)
    current = resolve_theme(profile["prpg_theme"])
    current_key = current.key if current and current.key in owned else "classic"
    return ThemeState(current_key, owned, facts, new)


async def sync_theme_unlocks(pool, user_id):
    async with pool.acquire() as conn:
        async with conn.transaction():
            return await _claim_locked(conn, user_id)


async def save_theme(pool, user_id, theme):
    """Enforce ownership at the write boundary, including stale UI interactions."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            state = await _claim_locked(conn, user_id)
            if state is None:
                return False
            if theme.key in state.unlocked:
                await conn.execute('UPDATE profile SET prpg_theme = $1 WHERE "user" = $2;', theme.key, user_id)
    # Commit any other legitimately earned cosmetics even if this choice is locked.
    if theme.key not in state.unlocked:
        raise ThemeLocked(theme, state)
    return True


async def grant_theme(pool, user_id, theme, source):
    """GM/event reward entry point. Grants ownership without changing appearance."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            exists = await conn.fetchval('SELECT "user" FROM profile WHERE "user" = $1 FOR UPDATE;', user_id)
            if exists is None:
                return False
            await conn.execute(
                'INSERT INTO profile_theme_unlocks (user_id, theme_key, source) VALUES ($1, $2, $3) ON CONFLICT (user_id, theme_key) DO NOTHING;',
                user_id, theme.key, source,
            )
    return True


async def grant_random_theme(pool, user_id, rarity, source):
    """GM reward: grant one collectible of ``rarity`` the player does not own yet.

    Picks uniformly among the unowned themes of that rarity, so a gift is never a
    duplicate. Returns the granted key, "" when every theme of that rarity is
    already owned, or None when the player has no character. The character row
    stays locked through the ownership check and insert, as with drops.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            exists = await conn.fetchval('SELECT "user" FROM profile WHERE "user" = $1 FOR UPDATE;', user_id)
            if exists is None:
                return None
            rows = await conn.fetch('SELECT theme_key FROM profile_theme_unlocks WHERE user_id = $1;', user_id)
            owned = {row["theme_key"] for row in rows}
            choices = [key for key, drop in COLLECTIBLE_THEMES.items() if drop.rarity == rarity and key not in owned]
            if not choices:
                return ""
            chosen = random.choice(choices)
            await conn.execute(
                'INSERT INTO profile_theme_unlocks (user_id, theme_key, source) VALUES ($1, $2, $3) ON CONFLICT (user_id, theme_key) DO NOTHING;',
                user_id, chosen, source,
            )
            return chosen


# ---------------------------------------------------------------------------
# Theme Trade-In Contract
# ---------------------------------------------------------------------------

TRADE_CONTRACT_TYPE = "theme_trade_contract"
TRADE_CONTRACT_NAME = "Theme Trade-In Contract"


@dataclass(frozen=True)
class TradeInResult:
    """status: traded, no_character, no_contract, not_tradable, not_owned or complete."""
    status: str
    given: str | None = None
    received: str | None = None
    rarity: str | None = None
    unequipped: bool = False


def trade_in_options(owned, rarity):
    """Collectible themes of ``rarity`` the player could receive from a trade-in."""
    return [key for key, drop in COLLECTIBLE_THEMES.items() if drop.rarity == rarity and key not in owned]


async def trade_in_theme(pool, user_id, theme_key, rng=random):
    """Spend one contract: give up an owned collectible for a random unowned one of the same rarity.

    Nothing is consumed unless the trade happens, so a player who already owns every
    theme of that rarity keeps their contract. The character row stays locked through
    the checks and writes, and a traded-away equipped theme falls back to classic.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            profile = await conn.fetchrow('SELECT prpg_theme FROM profile WHERE "user" = $1 FOR UPDATE;', user_id)
            if profile is None:
                return TradeInResult("no_character")
            contract = await conn.fetchrow(
                'SELECT id FROM user_consumables WHERE user_id = $1 AND consumable_type = $2 AND quantity > 0 '
                'ORDER BY id LIMIT 1 FOR UPDATE;',
                user_id, TRADE_CONTRACT_TYPE,
            )
            if contract is None:
                return TradeInResult("no_contract")
            drop = COLLECTIBLE_THEMES.get(theme_key)
            if drop is None:
                return TradeInResult("not_tradable", given=theme_key)
            rows = await conn.fetch('SELECT theme_key FROM profile_theme_unlocks WHERE user_id = $1;', user_id)
            owned = {row["theme_key"] for row in rows}
            if theme_key not in owned:
                return TradeInResult("not_owned", given=theme_key, rarity=drop.rarity)
            choices = trade_in_options(owned, drop.rarity)
            if not choices:
                return TradeInResult("complete", given=theme_key, rarity=drop.rarity)

            chosen = rng.choice(choices)
            await conn.execute('UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;', contract["id"])
            await conn.execute(
                'DELETE FROM profile_theme_unlocks WHERE user_id = $1 AND theme_key = $2;', user_id, theme_key,
            )
            await conn.execute(
                'INSERT INTO profile_theme_unlocks (user_id, theme_key, source) VALUES ($1, $2, $3) ON CONFLICT (user_id, theme_key) DO NOTHING;',
                user_id, chosen, f"trade-in:{theme_key}",
            )
            unequipped = profile["prpg_theme"] == theme_key
            if unequipped:
                await conn.execute('UPDATE profile SET prpg_theme = $1 WHERE "user" = $2;', "classic", user_id)
            return TradeInResult("traded", theme_key, chosen, drop.rarity, unequipped)


async def grant_event_theme(pool, user_id, theme_key, event_id=None):
    """Event cog entry point: ``await grant_event_theme(bot.pool, user.id, "harvest2026")``.

    Returns False when the player has no character. Raises KeyError for a key
    that is not listed in EVENT_THEMES, so a typo fails loudly during testing.
    """
    theme = resolve_theme(theme_key)
    if theme is None or not theme.is_event:
        raise KeyError(f"{theme_key!r} is not an event theme. Add it to EVENT_THEMES in cogs/profile/themes.py.")
    return await grant_theme(pool, user_id, theme, f"event:{event_id or theme.key}")
