"""Permanent cosmetic ownership: starter themes are free, collectible themes drop from gameplay."""

from dataclasses import dataclass
import random

from utils import misc as rpgtools
from .themes import THEMES, resolve_theme


@dataclass(frozen=True)
class UnlockRule:
    stat: str
    target: int = 0
    god: str = ""

    @property
    def label(self):
        if self.stat == "free":
            return "Available to every adventurer"
        if self.stat == "drop":
            return "Found during gameplay"
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
        return self.stat in ("free", "drop") or (
            int(facts.get(self.stat, 0) or 0) >= self.target
            and (not self.god or str(facts.get("god") or "").casefold() == self.god.casefold())
        )

    def progress(self, facts):
        if self.stat == "free":
            return self.label
        if self.stat == "drop":
            return "Must be discovered"
        value = max(0, int(facts.get(self.stat, 0) or 0))
        progress = f"{min(value, self.target):,}/{self.target:,}"
        if self.god:
            return f"Level {progress} · Following {facts.get('god') or 'no god'}"
        return f"{self.label} · {progress}"


# ---------------------------------------------------------------------------
# Drop rarity tiers — higher weight = more common
# ---------------------------------------------------------------------------

RARITY_WEIGHTS = {
    "Common": 48,
    "Uncommon": 36,
    "Rare": 10,
    "Epic": 4,
    "Legendary": 1.25,
    "Mythic": 0.75,
}

RARITY_EMOJI = {
    "Common": "🟢",
    "Uncommon": "🔵",
    "Rare": "🟣",
    "Epic": "🟠",
    "Legendary": "🔴",
    "Mythic": "💠",
}

# Per-source drop chance: the probability that a roll happens at all.
# The calling cog decides WHEN to call roll_theme_drop; these defaults
# are available if you want a shared constant.
DROP_CHANCES = {
    "pve": 0.05,
    "adventure": 0.06,
    "bt": 0.05,
    "pvp": 0.05,
    "boss": 0.05,
}


@dataclass(frozen=True)
class ThemeDrop:
    """Describes how a collectible theme is earned through gameplay drops."""
    unlock: UnlockRule
    rarity: str
    weight: float
    drop_sources: frozenset[str]
    hint: str = ""


# ---------------------------------------------------------------------------
# Collectible theme catalogue — edit one line to rebalance
# ---------------------------------------------------------------------------

COLLECTIBLE_THEMES: dict[str, ThemeDrop] = {
    "lanternwake": ThemeDrop(
        UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"],
        frozenset({"pve", "adventure"}), "Drops from PvE battles and adventures",
    ),
    "glasswing": ThemeDrop(
        UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"],
        frozenset({"pve", "adventure"}), "Drops from PvE battles and adventures",
    ),
    "porcelain": ThemeDrop(
        UnlockRule("drop"), "Uncommon", RARITY_WEIGHTS["Uncommon"],
        frozenset({"pve", "adventure", "bt"}), "Drops from PvE, adventures, and Battle Tower",
    ),
    "firstflame": ThemeDrop(
        UnlockRule("drop"), "Legendary", RARITY_WEIGHTS["Legendary"],
        frozenset({"adventure", "bt", "boss"}), "Drops from adventures, Battle Tower, and bosses",
    ),
    "unwritten": ThemeDrop(
        UnlockRule("drop"), "Mythic", RARITY_WEIGHTS["Mythic"],
        frozenset({"boss"}), "Drops from boss encounters only",
    ),
    "laststar": ThemeDrop(
        UnlockRule("drop"), "Mythic", RARITY_WEIGHTS["Mythic"],
        frozenset({"bt", "boss"}), "Drops from Battle Tower and bosses",
    ),
    # ── Companions ──────────────────────────────────────────────
    "moonbunny": ThemeDrop(
        UnlockRule("drop"),
        "Common", RARITY_WEIGHTS["Common"],
        frozenset({"pve", "adventure"}),
        "Drops from PvE battles and adventures",
    ),
    "slime": ThemeDrop(
        UnlockRule("drop"),
        "Common", RARITY_WEIGHTS["Common"],
        frozenset({"pve", "adventure"}),
        "Drops from PvE battles and adventures",
    ),
    "chickencow": ThemeDrop(
        UnlockRule("drop"),
        "Common", RARITY_WEIGHTS["Common"],
        frozenset({"pve", "adventure"}),
        "Drops from PvE battles and adventures",
    ),
    "mushroom": ThemeDrop(
        UnlockRule("drop"),
        "Common", RARITY_WEIGHTS["Common"],
        frozenset({"pve", "adventure"}),
        "Drops from PvE battles and adventures",
    ),
    "frogzard": ThemeDrop(
        UnlockRule("drop"),
        "Uncommon", RARITY_WEIGHTS["Uncommon"],
        frozenset({"pve", "adventure"}),
        "Drops from PvE battles and adventures",
    ),
    "lotus": ThemeDrop(
        UnlockRule("drop"),
        "Uncommon", RARITY_WEIGHTS["Uncommon"],
        frozenset({"pve", "adventure", "bt"}),
        "Drops from PvE, adventures, and Battle Tower",
    ),
    # ── Elven ───────────────────────────────────────────────────
    "woodelf": ThemeDrop(
        UnlockRule("drop"),
        "Common", RARITY_WEIGHTS["Common"],
        frozenset({"pve", "adventure"}),
        "Drops from PvE battles and adventures",
    ),
    "darkelf": ThemeDrop(
        UnlockRule("drop"),
        "Uncommon", RARITY_WEIGHTS["Uncommon"],
        frozenset({"pve", "adventure", "bt"}),
        "Drops from PvE, adventures, and Battle Tower",
    ),
    "highelf": ThemeDrop(
        UnlockRule("drop"),
        "Rare", RARITY_WEIGHTS["Rare"],
        frozenset({"pve", "adventure", "bt"}),
        "Drops from PvE, adventures, and Battle Tower",
    ),
    # ── Wonders ─────────────────────────────────────────────────
    "kitsune": ThemeDrop(
        UnlockRule("drop"),
        "Rare", RARITY_WEIGHTS["Rare"],
        frozenset({"pve", "adventure", "bt"}),
        "Drops from PvE, adventures, and Battle Tower",
    ),
    "mimic": ThemeDrop(
        UnlockRule("drop"),
        "Rare", RARITY_WEIGHTS["Rare"],
        frozenset({"pve", "adventure", "bt"}),
        "Drops from PvE, adventures, and Battle Tower",
    ),
    "clockwork": ThemeDrop(
        UnlockRule("drop"),
        "Uncommon", RARITY_WEIGHTS["Uncommon"],
        frozenset({"pve", "adventure", "bt"}),
        "Drops from PvE, adventures, and Battle Tower",
    ),
    # ── Divine (base) ───────────────────────────────────────────
    "elysia": ThemeDrop(
        UnlockRule("drop"),
        "Rare", RARITY_WEIGHTS["Rare"],
        frozenset({"boss", "adventure", "bt"}),
        "Drops from bosses, adventures, and Battle Tower",
    ),
    "sepulchure": ThemeDrop(
        UnlockRule("drop"),
        "Rare", RARITY_WEIGHTS["Rare"],
        frozenset({"boss", "adventure", "bt"}),
        "Drops from bosses, adventures, and Battle Tower",
    ),
    "drakath": ThemeDrop(
        UnlockRule("drop"),
        "Rare", RARITY_WEIGHTS["Rare"],
        frozenset({"boss", "adventure", "bt"}),
        "Drops from bosses, adventures, and Battle Tower",
    ),
    # ── Mythic ──────────────────────────────────────────────────
    "storm": ThemeDrop(
        UnlockRule("drop"),
        "Rare", RARITY_WEIGHTS["Rare"],
        frozenset({"bt", "boss"}),
        "Drops from Battle Tower, and bosses",
    ),
    "leviathan": ThemeDrop(
        UnlockRule("drop"),
        "Epic", RARITY_WEIGHTS["Epic"],
        frozenset({"boss", "bt", "adventure"}),
        "Drops from bosses, Battle Tower, and adventures",
    ),
    "phoenix": ThemeDrop(
        UnlockRule("drop"),
        "Epic", RARITY_WEIGHTS["Epic"],
        frozenset({"boss", "bt", "adventure"}),
        "Drops from bosses, Battle Tower, and adventures",
    ),
    "bloodmoon": ThemeDrop(
        UnlockRule("drop"),
        "Epic", RARITY_WEIGHTS["Epic"],
        frozenset({"bt", "boss"}),
        "Drops from Battle Tower, and bosses",
    ),
    "astral": ThemeDrop(
        UnlockRule("drop"),
        "Epic", RARITY_WEIGHTS["Epic"],
        frozenset({"boss", "bt"}),
        "Drops from bosses and Battle Tower",
    ),
    "eclipse": ThemeDrop(
        UnlockRule("drop"),
        "Legendary", RARITY_WEIGHTS["Legendary"],
        frozenset({"boss", "bt"}),
        "Drops from bosses and Battle Tower",
    ),
    # ── Divine (Exalted) ────────────────────────────────────────
    "elysia_ascendant": ThemeDrop(
        UnlockRule("drop"),
        "Legendary", RARITY_WEIGHTS["Legendary"],
        frozenset({"boss"}),
        "Drops from boss encounters only",
    ),
    "sepulchure_unbound": ThemeDrop(
        UnlockRule("drop"),
        "Legendary", RARITY_WEIGHTS["Legendary"],
        frozenset({"boss"}),
        "Drops from boss encounters only",
    ),
    "drakath_incarnate": ThemeDrop(
        UnlockRule("drop"),
        "Legendary", RARITY_WEIGHTS["Legendary"],
        frozenset({"boss"}),
        "Drops from boss encounters only",
    ),
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
    """Return a list of (key, weight) pairs for eligible collectible themes for this source.

    Pure function; no I/O.  Used by roll_theme_drop and tests.

    A theme enters the pool when:
    1. The activity source is listed in the theme's drop_sources.
    2. The player's character meets the stat/god prerequisite.
    """
    pool = []
    for key, drop in COLLECTIBLE_THEMES.items():
        if source not in drop.drop_sources:
            continue
        if not drop.unlock.met(facts):
            continue
        pool.append((key, drop.weight))
    return pool


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
    Themes the player already owns are excluded from the roll pool.
    Only themes whose stat/god prerequisite is met are eligible.

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
            facts = dict(profile)
            facts["level"] = rpgtools.xptolevel(facts.get("xp") or 0)
            pets = await conn.fetchrow(
                'SELECT COUNT(*) AS pet_count, COALESCE(MAX(trust_level), 0) AS pet_trust FROM monster_pets WHERE user_id = $1;', user_id,
            )
            facts.update(dict(pets))
            rows = await conn.fetch('SELECT theme_key FROM profile_theme_unlocks WHERE user_id = $1;', user_id)
            owned = {row["theme_key"] for row in rows} | {"classic"}

            eligible = [(key, weight) for key, weight in get_drop_pool(facts, source) if key not in owned]
            if not eligible:
                return None

            keys, weights = zip(*eligible)
            chosen = random.choices(keys, weights=weights, k=1)[0]

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


async def _claim_locked(conn, user_id):
    """Caller holds a transaction; serialize grants/equips against this character."""
    profile = await conn.fetchrow(
        'SELECT xp, money, pvpwins, god, prpg_theme FROM profile WHERE "user" = $1 FOR UPDATE;', user_id,
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
    if new:
        await conn.executemany(
            'INSERT INTO profile_theme_unlocks (user_id, theme_key) VALUES ($1, $2) ON CONFLICT (user_id, theme_key) DO NOTHING;',
            [(user_id, key) for key in new],
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
