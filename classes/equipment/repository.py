"""Equipment persistence. The switch row starts on for FableDev and off everywhere else."""
from __future__ import annotations

import random
from decimal import Decimal

from classes.equipment.definitions import DEV_DATABASE, OPEN_SLOTS, display_name
from classes.equipment.economy import (
    STARTER_RECIPES,
    craft_cost,
    is_tradable,
    modifier_adjustments,
    offensive_properties,
    recipe_key,
    salvage_yield,
)
from classes.equipment.generation import roll_crate, roll_quality
from classes.equipment.stats import contribution

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS equipment_items (
        id BIGSERIAL PRIMARY KEY,
        owner_id BIGINT NOT NULL,
        slot TEXT NOT NULL,
        rarity TEXT NOT NULL,
        archetype TEXT NOT NULL,
        quality INTEGER NOT NULL,
        offense_value NUMERIC NOT NULL DEFAULT 0,
        defense_value NUMERIC NOT NULL DEFAULT 0,
        refinement INTEGER NOT NULL DEFAULT 0,
        attunement INTEGER NOT NULL DEFAULT 0,
        modification_state TEXT NOT NULL DEFAULT 'pristine',
        bound BOOLEAN NOT NULL DEFAULT FALSE,
        fully_rolled BOOLEAN NOT NULL DEFAULT FALSE,
        origin TEXT NOT NULL DEFAULT 'grant',
        name TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT equipment_items_slot_chk
            CHECK (slot IN ('head', 'chest', 'legs', 'feet', 'bracers', 'belt')),
        CONSTRAINT equipment_items_rarity_chk
            CHECK (rarity IN ('common', 'uncommon', 'rare', 'magic', 'legendary')),
        CONSTRAINT equipment_items_archetype_chk
            CHECK (archetype IN ('guardian', 'slayer', 'vanguard')),
        CONSTRAINT equipment_items_quality_chk
            CHECK (quality BETWEEN 1 AND 100),
        CONSTRAINT equipment_items_refinement_chk
            CHECK (refinement BETWEEN 0 AND 7),
        CONSTRAINT equipment_items_attunement_chk
            CHECK (attunement BETWEEN 0 AND 2500)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS equipment_modifiers (
        id BIGSERIAL PRIMARY KEY,
        equipment_id BIGINT NOT NULL REFERENCES equipment_items(id) ON DELETE CASCADE,
        modifier_id TEXT NOT NULL,
        magnitude NUMERIC NOT NULL,
        source TEXT NOT NULL DEFAULT 'natural',
        locked BOOLEAN NOT NULL DEFAULT FALSE,
        UNIQUE (equipment_id, modifier_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS equipment_loadout (
        user_id BIGINT NOT NULL,
        slot TEXT NOT NULL,
        equipment_id BIGINT NOT NULL UNIQUE REFERENCES equipment_items(id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, slot)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS equipment_materials (
        user_id BIGINT NOT NULL,
        material_id TEXT NOT NULL,
        amount BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, material_id),
        CONSTRAINT equipment_materials_amount_chk CHECK (amount >= 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS equipment_settings (
        key TEXT PRIMARY KEY,
        enabled BOOLEAN NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS equipment_items_owner_idx
        ON equipment_items (owner_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS equipment_market (
        id BIGSERIAL PRIMARY KEY,
        equipment_id BIGINT NOT NULL UNIQUE REFERENCES equipment_items(id) ON DELETE CASCADE,
        seller_id BIGINT NOT NULL,
        price INTEGER NOT NULL CHECK (price > 0),
        published TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS equipment_discoveries (
        user_id BIGINT NOT NULL,
        recipe_key TEXT NOT NULL,
        discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, recipe_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS equipment_reward_grants (
        grant_key TEXT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        rarity TEXT NOT NULL,
        equipment_id BIGINT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS attunement INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS temper_fails INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS refine_fails INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS inscribe_fails INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE equipment_items DROP CONSTRAINT IF EXISTS equipment_items_refinement_chk",
    "ALTER TABLE equipment_items ADD CONSTRAINT equipment_items_refinement_chk CHECK (refinement BETWEEN 0 AND 7)",
    "ALTER TABLE equipment_items DROP CONSTRAINT IF EXISTS equipment_items_attunement_chk",
    "ALTER TABLE equipment_items ADD CONSTRAINT equipment_items_attunement_chk CHECK (attunement BETWEEN 0 AND 2500)",
    """
    INSERT INTO equipment_discoveries (user_id, recipe_key)
    SELECT d.user_id, s.slot || substr(d.recipe_key, strpos(d.recipe_key, ':'))
      FROM equipment_discoveries d
     CROSS JOIN (VALUES ('head'), ('chest'), ('legs'), ('feet')) AS s (slot)
     WHERE d.recipe_key NOT LIKE '%:common'
    ON CONFLICT (user_id, recipe_key) DO NOTHING
    """,
    """
    CREATE TABLE IF NOT EXISTS equipment_preferences (
        user_id BIGINT PRIMARY KEY,
        theme TEXT NOT NULL DEFAULT 'chronicle'
    )
    """,
)


MAX_LISTING_PRICE = 2_147_483_647


async def database_name(conn) -> str:
    return str(await conn.fetchval("SELECT current_database()"))


async def ensure_schema(conn) -> None:
    """Create or update the equipment tables. Safe to repeat, and serialized across clusters."""
    dev = await database_name(conn) == DEV_DATABASE
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('equipment_schema'))")
        for statement in SCHEMA_STATEMENTS:
            await conn.execute(statement)
        await conn.execute(
            """
            INSERT INTO equipment_settings (key, enabled)
            VALUES ('equipment', $1)
            ON CONFLICT (key) DO NOTHING
            """,
            dev,
        )


async def feature_enabled(conn) -> bool:
    enabled = await conn.fetchval(
        "SELECT enabled FROM equipment_settings WHERE key = 'equipment'"
    )
    return bool(enabled)


async def set_feature_enabled(conn, enabled: bool) -> None:
    await conn.execute(
        """
        INSERT INTO equipment_settings (key, enabled) VALUES ('equipment', $1)
        ON CONFLICT (key) DO UPDATE SET enabled = EXCLUDED.enabled
        """,
        bool(enabled),
    )


async def _worn_rows(conn, user_id: int):
    return await conn.fetch(
        """
        SELECT i.id, i.offense_value, i.defense_value
          FROM equipment_loadout l
          JOIN equipment_items i
            ON i.id = l.equipment_id
           AND i.owner_id = l.user_id
         WHERE l.user_id = $1
           AND l.slot = ANY($2::text[])
        """,
        int(user_id),
        list(OPEN_SLOTS),
    )


async def equipped_combat_bonus(conn, user_id: int) -> tuple[Decimal, Decimal]:
    """Chest stats plus Fortified and Weapon Amplification. Vitality is separate."""
    rows = await _worn_rows(conn, user_id)
    modifiers = await fetch_modifiers(conn, [int(row["id"]) for row in rows])
    offense = Decimal("0")
    defense = Decimal("0")
    for row in rows:
        offense += Decimal(str(row["offense_value"] or 0))
        defense += Decimal(str(row["defense_value"] or 0))
        modifier_ids = [item["modifier_id"] for item in modifiers.get(int(row["id"]), [])]
        extra_weapon, extra_armor, _health = modifier_adjustments(row["defense_value"], modifier_ids)
        offense += extra_weapon
        defense += extra_armor
    return offense, defense


async def equipped_offense(conn, user_id: int):
    """Penetration and breakthrough from the worn chest. Both are capped."""
    rows = await _worn_rows(conn, user_id)
    modifiers = await fetch_modifiers(conn, [int(row["id"]) for row in rows])
    modifier_ids = []
    for row in rows:
        modifier_ids.extend(item["modifier_id"] for item in modifiers.get(int(row["id"]), []))
    return offensive_properties(modifier_ids)


async def equipped_vitality(conn, user_id: int) -> int:
    """Flat health from Vitality on the worn chest. It is not raid-multiplied."""
    rows = await _worn_rows(conn, user_id)
    modifiers = await fetch_modifiers(conn, [int(row["id"]) for row in rows])
    health = 0
    for row in rows:
        modifier_ids = [item["modifier_id"] for item in modifiers.get(int(row["id"]), [])]
        _weapon, _armor, extra_health = modifier_adjustments(row["defense_value"], modifier_ids)
        health += extra_health
    return health


async def attune_worn(conn, user_id: int, foe_hp=None, wearer_hp=None, amount=None) -> dict | None:
    """Add attunement to every worn armor piece. Health arguments enable the weak-foe check."""
    from classes.equipment.attunement import XP_BATTLE, victory_award

    if amount is None:
        amount = XP_BATTLE
    async with conn.transaction():
        rows = await conn.fetch(
            """
            SELECT i.id, i.name, i.attunement, i.bound
              FROM equipment_loadout l
              JOIN equipment_items i ON i.id = l.equipment_id
             WHERE l.user_id = $1
               AND l.slot = ANY($2::text[])
             ORDER BY l.slot
             FOR UPDATE OF i
            """,
            int(user_id),
            list(OPEN_SLOTS),
        )
        if not rows:
            return None
        if foe_hp is not None or wearer_hp is not None:
            sample = victory_award(0, foe_hp, wearer_hp, amount)
            if sample["reason"] == "trivial":
                return None
        decisions = []
        for row in rows:
            decision = victory_award(row["attunement"], amount=amount)
            if decision["gain"] == 0:
                continue
            await conn.execute(
                """
                UPDATE equipment_items
                   SET attunement = $2,
                       bound = CASE WHEN $3 THEN TRUE ELSE bound END,
                       updated_at = NOW()
                 WHERE id = $1
                """,
                int(row["id"]),
                int(decision["level"]),
                bool(decision["binds"]),
            )
            decision["name"] = row["name"]
            decision["newly_bound"] = bool(decision["binds"]) and not bool(row["bound"])
            decisions.append(decision)
        if not decisions:
            return None
        lead = dict(decisions[0])
        lead["pieces"] = decisions
        return lead


async def fetch_modifiers(conn, equipment_ids: list[int]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {int(item_id): [] for item_id in equipment_ids}
    if not equipment_ids:
        return grouped
    rows = await conn.fetch(
        """
        SELECT equipment_id, modifier_id, magnitude, source, locked
          FROM equipment_modifiers
         WHERE equipment_id = ANY($1::bigint[])
         ORDER BY id
        """,
        [int(item_id) for item_id in equipment_ids],
    )
    for row in rows:
        grouped.setdefault(int(row["equipment_id"]), []).append(dict(row))
    return grouped


async def fetch_inventory(conn, user_id: int) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT i.*, (l.equipment_id IS NOT NULL) AS equipped
          FROM equipment_items i
          LEFT JOIN equipment_loadout l ON l.equipment_id = i.id
         WHERE i.owner_id = $1
         ORDER BY equipped DESC, i.quality DESC, i.id DESC
        """,
        int(user_id),
    )
    items = [dict(row) for row in rows]
    modifiers = await fetch_modifiers(conn, [int(item["id"]) for item in items])
    for item in items:
        item["modifiers"] = modifiers.get(int(item["id"]), [])
    return items


async def fetch_loadout(conn, user_id: int) -> dict[str, dict]:
    rows = await conn.fetch(
        """
        SELECT i.*
          FROM equipment_loadout l
          JOIN equipment_items i ON i.id = l.equipment_id
         WHERE l.user_id = $1
           AND i.owner_id = l.user_id
        """,
        int(user_id),
    )
    equipped = {row["slot"]: dict(row) for row in rows}
    modifiers = await fetch_modifiers(conn, [int(item["id"]) for item in equipped.values()])
    for item in equipped.values():
        item["equipped"] = True
        item["modifiers"] = modifiers.get(int(item["id"]), [])
    return equipped


async def _with_weapon_progression(conn, user_id: int, weapons: list[dict]) -> list[dict]:
    """Add Starforge and Soulbound to the numbers shown for each worn weapon."""
    from classes.endgame import apply_item_progression_bonus, soulbound_level_from_xp

    if not weapons:
        return weapons
    item_ids = [int(item["id"]) for item in weapons if item.get("id") is not None]
    star_map: dict[int, int] = {}
    soulbound_item_id = None
    soulbound_level = 0
    try:
        if await conn.fetchval("SELECT to_regclass('public.starforged_items') IS NOT NULL;"):
            star_rows = await conn.fetch(
                "SELECT item_id, stars FROM starforged_items WHERE item_id = ANY($1)",
                item_ids,
            )
            star_map = {int(row["item_id"]): int(row["stars"] or 0) for row in star_rows}
        if await conn.fetchval("SELECT to_regclass('public.soulbound') IS NOT NULL;"):
            soulbound_row = await conn.fetchrow(
                """
                SELECT item_id, xp
                  FROM soulbound
                 WHERE user_id = $1
                   AND item_id = ANY($2)
                """,
                user_id,
                item_ids,
            )
            if soulbound_row:
                soulbound_item_id = int(soulbound_row["item_id"])
                soulbound_level = soulbound_level_from_xp(soulbound_row["xp"])
    except Exception:
        return weapons
    for item in weapons:
        item_id = int(item["id"])
        level = soulbound_level if item_id == soulbound_item_id else 0
        damage, armor, bonus = apply_item_progression_bonus(
            item.get("damage") or 0,
            item.get("armor") or 0,
            stars=star_map.get(item_id, 0),
            soulbound_level=level,
        )
        item["base_damage"] = item.get("damage") or 0
        item["base_armor"] = item.get("armor") or 0
        item["effective_damage"] = damage
        item["effective_armor"] = armor
        item["progression_bonus_pct"] = bonus
        item["starforge_stars"] = star_map.get(item_id, 0)
        item["soulbound_level"] = level
    return weapons


async def fetch_equipped_weapons(conn, user_id: int) -> list[dict]:
    """Weapons and shields currently in the player's hands."""
    rows = await conn.fetch(
        """
        SELECT ai.id, ai.name, ai.type, ai.damage, ai.armor, ai.hand, ai.element
          FROM inventory i
          JOIN allitems ai ON ai.id = i.item
         WHERE i.equipped IS TRUE
           AND ai.owner = $1
        """,
        int(user_id),
    )
    return await _with_weapon_progression(conn, int(user_id), [dict(row) for row in rows])


async def fetch_item(conn, user_id: int, equipment_id: int) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT i.*, (l.equipment_id IS NOT NULL) AS equipped
          FROM equipment_items i
          LEFT JOIN equipment_loadout l ON l.equipment_id = i.id
         WHERE i.id = $1
           AND i.owner_id = $2
        """,
        int(equipment_id),
        int(user_id),
    )
    if row is None:
        return None
    item = dict(row)
    modifiers = await fetch_modifiers(conn, [int(item["id"])])
    item["modifiers"] = modifiers.get(int(item["id"]), [])
    return item


async def grant_chest(
    conn,
    owner_id: int,
    rarity: str,
    archetype: str,
    quality: int,
    *,
    origin: str = "grant",
    bound: bool = False,
    fully_rolled: bool = False,
    slot: str = "chest",
) -> dict:
    """Insert one unbound piece unless the caller explicitly binds it."""
    rarity = str(rarity).lower()
    archetype = str(archetype).lower()
    slot = str(slot).lower()
    offense, defense = contribution(rarity, archetype, quality, 0, slot)
    name = display_name(rarity, archetype, slot)
    row = await conn.fetchrow(
        """
        INSERT INTO equipment_items (
            owner_id, slot, rarity, archetype, quality,
            offense_value, defense_value, refinement,
            bound, fully_rolled, origin, name
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, 0, $8, $9, $10, $11)
        RETURNING *
        """,
        int(owner_id),
        slot,
        rarity,
        archetype,
        int(quality),
        offense,
        defense,
        bool(bound),
        bool(fully_rolled),
        origin,
        name,
    )
    item = dict(row)
    item["modifiers"] = []
    item["equipped"] = False
    return item


async def equip_item(conn, user_id: int, equipment_id: int) -> tuple[str, dict | None]:
    """Equip a piece in its own slot. Wearing a piece does not bind it."""
    async with conn.transaction():
        item = await conn.fetchrow(
            """
            SELECT *
              FROM equipment_items
             WHERE id = $1
               AND owner_id = $2
             FOR UPDATE
            """,
            int(equipment_id),
            int(user_id),
        )
        if item is None:
            return "missing", None
        if item["slot"] not in OPEN_SLOTS:
            return "closed", dict(item)
        listed = await conn.fetchval(
            "SELECT 1 FROM equipment_market WHERE equipment_id = $1",
            int(equipment_id),
        )
        if listed:
            return "listed", dict(item)
        already = await conn.fetchval(
            """
            SELECT 1
              FROM equipment_loadout
             WHERE user_id = $1
               AND equipment_id = $2
            """,
            int(user_id),
            int(equipment_id),
        )
        if already:
            return "already", dict(item)
        await conn.execute(
            """
            DELETE FROM equipment_loadout
             WHERE equipment_id = $1
                OR (user_id = $2 AND slot = $3)
            """,
            int(equipment_id),
            int(user_id),
            item["slot"],
        )
        await conn.execute(
            """
            INSERT INTO equipment_loadout (user_id, slot, equipment_id)
            VALUES ($1, $2, $3)
            """,
            int(user_id),
            item["slot"],
            int(equipment_id),
        )
        bound_after = await conn.fetchval(
            "SELECT bound FROM equipment_items WHERE id = $1",
            int(equipment_id),
        )
        if bool(bound_after) != bool(item["bound"]):
            raise RuntimeError("equipping changed the binding state")
        equipped = dict(item)
        equipped["equipped"] = True
        return "equipped", equipped


async def unequip_item(conn, user_id: int, equipment_id: int | None = None) -> tuple[str, int | None]:
    async with conn.transaction():
        if equipment_id is None:
            removed_rows = await conn.fetch(
                """
                DELETE FROM equipment_loadout l
                 USING equipment_items i
                 WHERE l.equipment_id = i.id
                   AND l.user_id = $1
                   AND l.slot = ANY($2::text[])
                   AND i.owner_id = l.user_id
                RETURNING l.equipment_id
                """,
                int(user_id),
                list(OPEN_SLOTS),
            )
            if not removed_rows:
                return "missing", None
            return "removed", [int(row["equipment_id"]) for row in removed_rows]
        else:
            removed = await conn.fetchrow(
                """
                DELETE FROM equipment_loadout l
                 USING equipment_items i
                 WHERE l.equipment_id = i.id
                   AND l.user_id = $1
                   AND l.equipment_id = $2
                   AND i.owner_id = l.user_id
                RETURNING l.equipment_id
                """,
                int(user_id),
                int(equipment_id),
            )
        if removed is None:
            return "missing", None
        return "removed", int(removed["equipment_id"])


async def create_piece(conn, owner_id: int, piece, *, origin: str) -> dict:
    """Persist a rolled piece. Fully rolled discoveries are bound on insert."""
    slot = str(getattr(piece, "slot", None) or "chest").lower()
    if slot not in OPEN_SLOTS:
        slot = "chest"
    offense, defense = contribution(piece.rarity, piece.archetype, piece.quality, 0, slot)
    name = display_name(piece.rarity, piece.archetype, slot)
    row = await conn.fetchrow(
        """
        INSERT INTO equipment_items (
            owner_id, slot, rarity, archetype, quality,
            offense_value, defense_value, refinement,
            bound, fully_rolled, origin, name
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, 0, $8, $9, $10, $11)
        RETURNING *
        """,
        int(owner_id),
        slot,
        piece.rarity,
        piece.archetype,
        int(piece.quality),
        offense,
        defense,
        bool(piece.fully_rolled),
        bool(piece.fully_rolled),
        origin,
        name,
    )
    for modifier_id in piece.modifier_ids:
        await conn.execute(
            """
            INSERT INTO equipment_modifiers (equipment_id, modifier_id, magnitude, source)
            VALUES ($1, $2, 1, 'natural')
            """,
            row["id"],
            modifier_id,
        )
    item = dict(row)
    item["modifiers"] = [{"modifier_id": modifier_id} for modifier_id in piece.modifier_ids]
    item["equipped"] = False
    await record_discovery(conn, owner_id, piece.archetype, piece.rarity, piece_slot=slot)
    return item


async def record_discovery(conn, user_id: int, archetype: str, rarity: str, piece_slot: str = "chest") -> None:
    """Finding one piece teaches that line and rarity for every open slot."""
    keys = [
        recipe_key(archetype, rarity, slot)
        for slot in OPEN_SLOTS
        if recipe_key(archetype, rarity, slot) not in STARTER_RECIPES
    ]
    if not keys:
        return
    await conn.execute(
        """
        INSERT INTO equipment_discoveries (user_id, recipe_key)
        SELECT $1, key FROM unnest($2::text[]) AS key
        ON CONFLICT (user_id, recipe_key) DO NOTHING
        """,
        int(user_id),
        keys,
    )


async def worn_line(conn, user_id: int) -> str | None:
    """The armor line on most worn pieces, or None when nothing is worn."""
    return await conn.fetchval(
        """
        SELECT i.archetype
          FROM equipment_loadout l
          JOIN equipment_items i ON i.id = l.equipment_id AND i.owner_id = l.user_id
         WHERE l.user_id = $1
         GROUP BY i.archetype
         ORDER BY count(*) DESC, bool_or(i.rarity = 'legendary') DESC, i.archetype
         LIMIT 1
        """,
        int(user_id),
    )


async def fetch_discovered_recipes(conn, user_id: int) -> set[str]:
    rows = await conn.fetch(
        "SELECT recipe_key FROM equipment_discoveries WHERE user_id = $1",
        int(user_id),
    )
    return {row["recipe_key"] for row in rows}


async def fetch_materials(conn, user_id: int) -> dict[str, int]:
    rows = await conn.fetch(
        """
        SELECT material_id, amount
          FROM equipment_materials
         WHERE user_id = $1
           AND amount > 0
        """,
        int(user_id),
    )
    return {row["material_id"]: int(row["amount"]) for row in rows}


async def armory_rolls_left(conn, user_id: int, rarity: str) -> int:
    """Armory rolls still open for this rarity in the rolling 24-hour window."""
    from classes.equipment.definitions import ARMORY_DAILY_ROLLS

    allowance = ARMORY_DAILY_ROLLS.get(str(rarity).lower(), 0)
    if allowance <= 0:
        return 0
    used = await conn.fetchval(
        """
        SELECT count(*)
          FROM equipment_reward_grants
         WHERE user_id = $1
           AND rarity = $2
           AND created_at > NOW() - INTERVAL '24 hours'
        """,
        int(user_id),
        str(rarity).lower(),
    )
    return max(0, allowance - int(used or 0))


async def apply_crate_opening(conn, user_id: int, rarity: str, grant_key: str, rng) -> dict | None:
    """Grant one crate reward. The same grant key cannot pay twice."""
    roll = roll_crate(rarity, rng)
    if roll is None:
        return None
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('armory_rolls'), hashtext($1::text))", str(user_id))
        if await armory_rolls_left(conn, user_id, roll.rarity) <= 0:
            return None
        inserted = await conn.fetchrow(
            """
            INSERT INTO equipment_reward_grants (grant_key, user_id, rarity)
            VALUES ($1, $2, $3)
            ON CONFLICT (grant_key) DO NOTHING
            RETURNING grant_key
            """,
            grant_key,
            int(user_id),
            roll.rarity,
        )
        if inserted is None:
            return None
        item = None
        if roll.piece is not None:
            origin = "legendary_discovery" if roll.piece.fully_rolled else "crate"
            item = await create_piece(conn, user_id, roll.piece, origin=origin)
            await conn.execute(
                """
                UPDATE equipment_reward_grants
                   SET equipment_id = $2
                 WHERE grant_key = $1
                """,
                grant_key,
                item["id"],
            )
        for material_id, amount in roll.materials.items():
            await conn.execute(
                """
                INSERT INTO equipment_materials (user_id, material_id, amount)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, material_id)
                DO UPDATE SET amount = equipment_materials.amount + EXCLUDED.amount
                """,
                int(user_id),
                material_id,
                int(amount),
            )
        return {"item": item, "materials": dict(roll.materials)}


async def add_materials(conn, user_id: int, amounts: dict[str, int]) -> None:
    for material_id, amount in amounts.items():
        amount = int(amount)
        if amount <= 0:
            continue
        await conn.execute(
            """
            INSERT INTO equipment_materials (user_id, material_id, amount)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, material_id)
            DO UPDATE SET amount = equipment_materials.amount + EXCLUDED.amount
            """,
            int(user_id),
            material_id,
            amount,
        )


async def spend_materials(conn, user_id: int, amounts: dict[str, int]) -> bool:
    """Subtract materials. Returns False if any stack is too small.

    Call this inside a transaction so a later failure puts the materials back.
    """
    for material_id, amount in amounts.items():
        remaining = await conn.fetchval(
            """
            UPDATE equipment_materials
               SET amount = amount - $3
             WHERE user_id = $1
               AND material_id = $2
               AND amount >= $3
            RETURNING amount
            """,
            int(user_id),
            material_id,
            int(amount),
        )
        if remaining is None:
            return False
    return True


async def craft_chest(conn, owner_id: int, rarity: str, archetype: str, rng=None, slot: str = "chest") -> tuple[str, dict | None]:
    """Spend the craft cost and store one tradable piece. Quality is rolled."""
    rarity = str(rarity).lower()
    archetype = str(archetype).lower()
    slot = str(slot or "chest").lower()
    key = recipe_key(archetype, rarity, slot)
    cost = craft_cost(rarity, archetype)
    rng = rng or random.Random()
    async with conn.transaction():
        if key not in STARTER_RECIPES:
            known = await conn.fetchval(
                """
                SELECT 1
                  FROM equipment_discoveries
                 WHERE user_id = $1
                   AND recipe_key = $2
                """,
                int(owner_id),
                key,
            )
            if not known:
                return "unknown", None
        for material_id, amount in cost.items():
            have = await conn.fetchval(
                """
                SELECT amount
                  FROM equipment_materials
                 WHERE user_id = $1
                   AND material_id = $2
                 FOR UPDATE
                """,
                int(owner_id),
                material_id,
            )
            if have is None or int(have) < int(amount):
                return "poor", None
        if not await spend_materials(conn, owner_id, cost):
            raise RuntimeError("craft spend failed after the balance check")
        from classes.equipment.generation import RolledPiece

        piece = RolledPiece(
            rarity=rarity,
            archetype=archetype,
            quality=roll_quality(rng, rarity),
            fully_rolled=False,
            slot=slot,
        )
        item = await create_piece(conn, owner_id, piece, origin="craft")
        return "crafted", item


async def _locked_worn_piece(conn, owner_id: int, equipment_id: int):
    return await conn.fetchrow(
        """
        SELECT i.*
          FROM equipment_items i
          JOIN equipment_loadout l ON l.equipment_id = i.id AND l.user_id = i.owner_id
         WHERE i.id = $1
           AND i.owner_id = $2
         FOR UPDATE OF i
        """,
        int(equipment_id),
        int(owner_id),
    )


async def _charge(conn, owner_id: int, cost: dict[str, int], gold: int) -> str | None:
    """Spend materials and gold inside the caller's transaction. Returns a reason when short."""
    for material_id, amount in cost.items():
        have = await conn.fetchval(
            """
            SELECT amount
              FROM equipment_materials
             WHERE user_id = $1
               AND material_id = $2
             FOR UPDATE
            """,
            int(owner_id),
            material_id,
        )
        if have is None or int(have) < int(amount):
            return "materials"
    if gold:
        money = await conn.fetchval(
            'SELECT money FROM profile WHERE "user" = $1 FOR UPDATE',
            int(owner_id),
        )
        if money is None or int(money) < int(gold):
            return "gold"
        await conn.execute(
            'UPDATE profile SET money = money - $1 WHERE "user" = $2',
            int(gold),
            int(owner_id),
        )
    if not await spend_materials(conn, owner_id, cost):
        raise RuntimeError("forge spend failed after the balance check")
    return None


async def temper_piece(conn, owner_id: int, equipment_id: int, rng=None) -> tuple[str, dict | None]:
    """One temper attempt on a worn piece: a chance at the next star, with pity. It binds the piece."""
    from classes.equipment.attunement import refinement_cap
    from classes.equipment.economy import temper_step

    rng = rng or random.Random()
    async with conn.transaction():
        item = await _locked_worn_piece(conn, owner_id, equipment_id)
        if item is None:
            return "missing", None
        if await conn.fetchval("SELECT 1 FROM equipment_market WHERE equipment_id = $1", int(equipment_id)):
            return "listed", None
        current = int(item["refinement"] or 0)
        if current >= refinement_cap(item["attunement"]):
            return "maxed", None
        next_star = current + 1
        step = temper_step(item["archetype"], next_star)
        short = await _charge(conn, owner_id, step["cost"], step["gold"])
        if short:
            return "poor", {**step, "short": short}
        fails = int(item["temper_fails"] or 0)
        success = fails >= step["pity"] or rng.random() < step["chance"]
        stars = next_star if success else current
        offense, defense = contribution(
            item["rarity"], item["archetype"], int(item["quality"]), stars, item["slot"]
        )
        updated = await conn.fetchrow(
            """
            UPDATE equipment_items
               SET refinement = $2,
                   offense_value = $3,
                   defense_value = $4,
                   temper_fails = $5,
                   bound = TRUE,
                   updated_at = NOW()
             WHERE id = $1
            RETURNING *
            """,
            int(equipment_id),
            stars,
            offense,
            defense,
            0 if success else fails + 1,
        )
        result = dict(updated)
        result.update(step)
        result["success"] = success
        result["pity_used"] = success and fails >= step["pity"]
        result["refinement_cap"] = refinement_cap(item["attunement"])
        result["newly_bound"] = not bool(item["bound"])
        return "tempered", result


async def refine_piece(conn, owner_id: int, equipment_id: int, rng=None) -> tuple[str, dict | None]:
    """One refine attempt on a worn piece: a chance at +1 quality, with pity. It binds the piece."""
    from classes.equipment.economy import refine_step

    rng = rng or random.Random()
    async with conn.transaction():
        item = await _locked_worn_piece(conn, owner_id, equipment_id)
        if item is None:
            return "missing", None
        step = refine_step(item["archetype"], int(item["quality"]))
        if step is None:
            return "maxed", None
        short = await _charge(conn, owner_id, step["cost"], step["gold"])
        if short:
            return "poor", {**step, "short": short}
        fails = int(item["refine_fails"] or 0)
        success = fails >= step["pity"] or rng.random() < step["chance"]
        quality = int(item["quality"]) + (1 if success else 0)
        offense, defense = contribution(
            item["rarity"], item["archetype"], quality, int(item["refinement"] or 0), item["slot"]
        )
        updated = await conn.fetchrow(
            """
            UPDATE equipment_items
               SET quality = $2,
                   offense_value = $3,
                   defense_value = $4,
                   refine_fails = $5,
                   bound = TRUE,
                   updated_at = NOW()
             WHERE id = $1
            RETURNING *
            """,
            int(equipment_id),
            quality,
            offense,
            defense,
            0 if success else fails + 1,
        )
        result = dict(updated)
        result.update(step)
        result["success"] = success
        result["pity_used"] = success and fails >= step["pity"]
        result["newly_bound"] = not bool(item["bound"])
        return "refined", result


async def inscribe_piece(conn, owner_id: int, equipment_id: int, modifier_id: str, rng=None) -> tuple[str, dict | None]:
    """Try to set one enchantment on a worn Magic or Legendary piece. A success replaces its single enchantment."""
    from classes.equipment.definitions import INSCRIBE_RARITIES, MODIFIER_LINES
    from classes.equipment.economy import inscribe_step

    rng = rng or random.Random()
    async with conn.transaction():
        item = await _locked_worn_piece(conn, owner_id, equipment_id)
        if item is None:
            return "missing", None
        if item["fully_rolled"]:
            return "dual", None
        if item["rarity"] not in INSCRIBE_RARITIES:
            return "rarity", None
        if modifier_id not in MODIFIER_LINES[item["archetype"]]:
            return "line", None
        current = await conn.fetch(
            "SELECT modifier_id FROM equipment_modifiers WHERE equipment_id = $1",
            int(equipment_id),
        )
        if any(row["modifier_id"] == modifier_id for row in current):
            return "same", None
        step = inscribe_step(item["archetype"])
        short = await _charge(conn, owner_id, step["cost"], step["gold"])
        if short:
            return "poor", {**step, "short": short}
        fails = int(item["inscribe_fails"] or 0)
        success = fails >= step["pity"] or rng.random() < step["chance"]
        replaced = [row["modifier_id"] for row in current]
        if success:
            await conn.execute("DELETE FROM equipment_modifiers WHERE equipment_id = $1", int(equipment_id))
            await conn.execute(
                """
                INSERT INTO equipment_modifiers (equipment_id, modifier_id, magnitude, source)
                VALUES ($1, $2, 1, 'inscribed')
                """,
                int(equipment_id),
                modifier_id,
            )
        await conn.execute(
            """
            UPDATE equipment_items
               SET inscribe_fails = $2,
                   bound = TRUE,
                   updated_at = NOW()
             WHERE id = $1
            """,
            int(equipment_id),
            0 if success else fails + 1,
        )
        return "inscribed", {
            **step,
            "success": success,
            "pity_used": success and fails >= step["pity"],
            "replaced": replaced if success else [],
            "fails": 0 if success else fails + 1,
            "newly_bound": not bool(item["bound"]),
        }


async def trade_materials(conn, user_id: int, material_id: str, target_line: str, amount: int) -> tuple[str, dict | None]:
    """Garron's trade at the fixed ratio, same tier, into another line."""
    from classes.equipment.economy import trade_result

    deal = trade_result(material_id, target_line, amount)
    if deal is None:
        return "invalid", None
    received_id, received, spent = deal
    async with conn.transaction():
        if not await spend_materials(conn, user_id, {material_id: spent}):
            return "poor", {"spent": spent}
        await add_materials(conn, user_id, {received_id: received})
    return "traded", {"spent_id": material_id, "spent": spent, "received_id": received_id, "received": received}


async def salvage_piece(conn, owner_id: int, equipment_id: int) -> tuple[str, dict | None]:
    """Destroy a chest and pay less than it would cost to craft again."""
    async with conn.transaction():
        item = await conn.fetchrow(
            """
            SELECT *
              FROM equipment_items
             WHERE id = $1
               AND owner_id = $2
             FOR UPDATE
            """,
            int(equipment_id),
            int(owner_id),
        )
        if item is None:
            return "missing", None
        listed = await conn.fetchval(
            "SELECT 1 FROM equipment_market WHERE equipment_id = $1",
            int(equipment_id),
        )
        if listed:
            return "listed", None
        yield_amounts = salvage_yield(item["rarity"], item["archetype"], int(item["quality"]))
        await conn.execute(
            "DELETE FROM equipment_loadout WHERE equipment_id = $1",
            int(equipment_id),
        )
        deleted = await conn.fetchval(
            """
            DELETE FROM equipment_items
             WHERE id = $1
               AND owner_id = $2
            RETURNING id
            """,
            int(equipment_id),
            int(owner_id),
        )
        if deleted is None:
            return "missing", None
        await add_materials(conn, owner_id, yield_amounts)
        return "salvaged", {"name": item["name"], "materials": yield_amounts}


async def move_piece(conn, equipment_id: int, from_id: int, to_id: int) -> str:
    """Move a tradable chest. Unequip it and clear any gear listing."""
    row = await conn.fetchrow(
        """
        SELECT *
          FROM equipment_items
         WHERE id = $1
         FOR UPDATE
        """,
        int(equipment_id),
    )
    if row is None or int(row["owner_id"]) != int(from_id):
        return "missing"
    if not is_tradable(row):
        return "bound"
    await conn.execute(
        "DELETE FROM equipment_loadout WHERE equipment_id = $1",
        int(equipment_id),
    )
    await conn.execute(
        "DELETE FROM equipment_market WHERE equipment_id = $1",
        int(equipment_id),
    )
    await conn.execute(
        """
        UPDATE equipment_items
           SET owner_id = $2, updated_at = NOW()
         WHERE id = $1
        """,
        int(equipment_id),
        int(to_id),
    )
    return "moved"


async def list_piece(conn, owner_id: int, equipment_id: int, price: int) -> tuple[str, dict | None]:
    # equipment_market.price is INTEGER, so a larger number would fail in the database.
    if not 1 <= int(price) <= MAX_LISTING_PRICE:
        return "price", None
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT *
              FROM equipment_items
             WHERE id = $1
               AND owner_id = $2
             FOR UPDATE
            """,
            int(equipment_id),
            int(owner_id),
        )
        if row is None:
            return "missing", None
        if not is_tradable(row):
            return "bound", None
        await conn.execute(
            "DELETE FROM equipment_loadout WHERE equipment_id = $1",
            int(equipment_id),
        )
        await conn.execute(
            """
            INSERT INTO equipment_market (equipment_id, seller_id, price)
            VALUES ($1, $2, $3)
            ON CONFLICT (equipment_id)
            DO UPDATE SET price = EXCLUDED.price, published = NOW()
            """,
            int(equipment_id),
            int(owner_id),
            int(price),
        )
        return "listed", dict(row)


async def withdraw_listing(conn, owner_id: int, equipment_id: int) -> str:
    removed = await conn.fetchval(
        """
        DELETE FROM equipment_market
         WHERE equipment_id = $1
           AND seller_id = $2
        RETURNING equipment_id
        """,
        int(equipment_id),
        int(owner_id),
    )
    return "withdrawn" if removed else "missing"


async def buy_listing(conn, buyer_id: int, equipment_id: int) -> tuple[str, dict | None]:
    """Buy a gear listing. The weapon market is not used."""
    async with conn.transaction():
        listing = await conn.fetchrow(
            """
            SELECT m.price, m.seller_id, i.*
              FROM equipment_market m
              JOIN equipment_items i ON i.id = m.equipment_id
             WHERE m.equipment_id = $1
             FOR UPDATE OF m, i
            """,
            int(equipment_id),
        )
        if listing is None:
            return "missing", None
        if int(listing["seller_id"]) == int(buyer_id):
            return "self", None
        if not is_tradable(listing) or int(listing["owner_id"]) != int(listing["seller_id"]):
            await conn.execute(
                "DELETE FROM equipment_market WHERE equipment_id = $1",
                int(equipment_id),
            )
            return "bound", None
        price = int(listing["price"])
        paid = await conn.fetchval(
            """
            UPDATE profile
               SET money = money - $1
             WHERE "user" = $2
               AND money >= $1
            RETURNING money
            """,
            price,
            int(buyer_id),
        )
        if paid is None:
            return "poor", None
        await conn.execute(
            'UPDATE profile SET money = money + $1 WHERE "user" = $2',
            price,
            int(listing["seller_id"]),
        )
        status = await move_piece(conn, equipment_id, int(listing["seller_id"]), int(buyer_id))
        if status != "moved":
            raise RuntimeError("gear listing could not be delivered")
        return "bought", {"name": listing["name"], "price": price, "seller_id": int(listing["seller_id"])}


async def fetch_market(conn, limit: int = 15) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT i.id, i.name, i.rarity, i.archetype, i.quality, m.price, m.seller_id
          FROM equipment_market m
          JOIN equipment_items i ON i.id = m.equipment_id
         WHERE i.owner_id = m.seller_id
           AND i.bound = FALSE
           AND i.fully_rolled = FALSE
         ORDER BY m.published DESC
         LIMIT $1
        """,
        int(limit),
    )
    return [dict(row) for row in rows]


async def gear_theme(conn, user_id: int) -> str:
    """The player's chosen armory cover, or chronicle."""
    from classes.equipment.chronicle import THEMES

    key = await conn.fetchval("SELECT theme FROM equipment_preferences WHERE user_id = $1", user_id)
    return key if key in THEMES else "chronicle"


async def set_gear_theme(conn, user_id: int, key: str) -> bool:
    from classes.equipment.chronicle import THEMES

    if key not in THEMES:
        return False
    await conn.execute(
        """
        INSERT INTO equipment_preferences (user_id, theme) VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE SET theme = EXCLUDED.theme
        """,
        user_id,
        key,
    )
    return True
