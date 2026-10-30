"""Battle elixirs, brewed in the Fables Library and drunk here.

Readers brew elixirs in a cauldron in their Library home from crops they grew and fish they
caught; battle elixirs land in `user_consumables` (written by the Fables game server, type
"elixir_<id>_<plain|silver|gold>"), so they trade like any consumable. A reader holds at most
STACK of each. Drinking one (`$elixir drink`) starts it for ACTIVE_MINUTES of real time: every
battle in that window gets its effect, in PvE and PvP alike. At most ACTIVE_MAX at once, never
two of the same elixir. Quality comes from the crops: silver is 1.5x plain, gold 2x.

The effects live on the player's Combatant (`combatant.elixirs`), set when the battle factory
builds it (HP, damage, opening shield fold straight into its stats). The rest are applied by
the shared battle hooks: the canonical attack path (lifesteal, thorns, regen, crits, wards,
burn, chill, lightning), the lethal-damage path (Phoenix Pepper) and the battle's teams
(Feast Pot shields, Beast Broth pets). Modes that resolve attacks their own way still get the
stat effects, the shields, Phoenix Pepper and the team effects.

The recipes (what each takes to brew) are the game server's: src/homes/elixirs.json. The
numbers here must match its "values".

Discord-free so battles, cogs and tests can share it.
"""
from __future__ import annotations

import datetime
import random
from decimal import Decimal

STACK = 99
ACTIVE_MAX = 2
ACTIVE_MINUTES = 120
QUALITIES = ("plain", "silver", "gold")
QUALITY_NAMES = ("Plain", "Silver", "Gold")

# Custom emotes for each elixir (uploaded 2026-10-25). An emote called elixir_<id> in any server the
# bot is in replaces its entry when the bot starts (see learn_emojis); one with none falls back to
# the flask.
ELIXIR_EMOJI: dict[str, str] = {
    "giants_stew": "<:elixir_giants_stew:1563875781019570197>",
    "ironbark_tonic": "<:elixir_ironbark_tonic:1563875783225638932>",
    "berserker_brew": "<:elixir_berserker_brew:1563875758345289728>",
    "leechroot_brew": "<:elixir_leechroot_brew:1563875785314664458>",
    "thornwine": "<:elixir_thornwine:1563875809062682634>",
    "vigor_broth": "<:elixir_vigor_broth:1563875812095303791>",
    "sharpleaf_cordial": "<:elixir_sharpleaf_cordial:1563875800166440980>",
    "ember_draught": "<:elixir_ember_draught:1563875769522983025>",
    "frost_fizz": "<:elixir_frost_fizz:1563875778398130177>",
    "storm_pop": "<:elixir_storm_pop:1563875806617276486>",
    "beast_broth": "<:elixir_beast_broth:1563875755799216348>",
    "feast_pot": "<:elixir_feast_pot:1563875772337234030>",
    "phoenix_pepper": "<:elixir_phoenix_pepper:1563876463651061880>",
    "fire_ward": "<:elixir_fire_ward:1563875776221155468>",
    "water_ward": "<:elixir_water_ward:1563875814360096898>",
    "nature_ward": "<:elixir_nature_ward:1563875789601112158>",
    "earth_ward": "<:elixir_earth_ward:1563875765018296390>",
    "electric_ward": "<:elixir_electric_ward:1563875767128162334>",
    "wind_ward": "<:elixir_wind_ward:1563875753890680922>",
    "light_ward": "<:elixir_light_ward:1563875787503829132>",
    "dark_ward": "<:elixir_dark_ward:1563875762459770931>",
    "corrupted_ward": "<:elixir_corrupted_ward:1563875760509296761>",
}
DEFAULT_EMOJI = "\U0001F9EA"

# id: name, what it does ("{v}" is the quality's value), the effect key and its value per quality
# (percent). "element" for the wards.
ELIXIRS: dict[str, dict] = {
    "giants_stew": dict(name="Giant's Stew", effect="+{v}% max HP", key="hp", values=(10, 15, 20)),
    "ironbark_tonic": dict(name="Ironbark Tonic", effect="Start every fight with a shield of {v}% of your max HP", key="shield", values=(10, 15, 20)),
    "berserker_brew": dict(name="Berserker's Brew", effect="+{v}% damage", key="damage", values=(10, 15, 20)),
    "leechroot_brew": dict(name="Leechroot Brew", effect="Heal {v}% of the damage you deal", key="leech", values=(6, 9, 12)),
    "thornwine": dict(name="Thornwine", effect="Reflect {v}% of the damage you take", key="thorns", values=(6, 9, 12)),
    "vigor_broth": dict(name="Vigor Broth", effect="Heal {v}% of your max HP on each of your first 10 attacks", key="vigor", values=(3, 4.5, 6)),
    "sharpleaf_cordial": dict(name="Sharpleaf Cordial", effect="{v}% chance for a critical hit (+50% damage)", key="crit", values=(8, 12, 16)),
    "ember_draught": dict(name="Ember Draught", effect="{v}% chance to set your target burning (a quarter of the hit again, for 3 turns)", key="burn", values=(10, 15, 20)),
    "frost_fizz": dict(name="Frostmint Fizz", effect="{v}% chance to chill your target (its next attack does half damage)", key="chill", values=(10, 15, 20)),
    "storm_pop": dict(name="Stormberry Pop", effect="{v}% chance for lightning to strike again (40% of the hit)", key="storm", values=(10, 15, 20)),
    "beast_broth": dict(name="Beast Broth", effect="Your pet gets +{v}% damage and max HP", key="beast", values=(10, 15, 20)),
    "feast_pot": dict(name="Feast Pot", effect="Your whole team starts every fight with a shield of {v}% of their max HP", key="feast", values=(8, 12, 16), rare=True),
    "phoenix_pepper": dict(name="Phoenix Pepper Elixir", effect="Once per fight, rise from a killing blow with {v}% of your max HP", key="phoenix", values=(30, 40, 50), rare=True),
}
for _id, _name, _element in (
    ("fire_ward", "Emberward Salve", "Fire"), ("water_ward", "Tideward Salve", "Water"),
    ("nature_ward", "Blightward Salve", "Nature"), ("earth_ward", "Stoneward Salve", "Earth"),
    ("electric_ward", "Stormward Salve", "Electric"), ("wind_ward", "Galeward Salve", "Wind"),
    ("light_ward", "Dimward Salve", "Light"), ("dark_ward", "Dawnward Salve", "Dark"),
    ("corrupted_ward", "Purity Salve", "Corrupted"),
):
    ELIXIRS[_id] = dict(name=_name, effect=f"Take {{v}}% less damage from {_element}", key="ward",
                        element=_element, values=(15, 22.5, 30), ward=True)

ACTIVE_SQL = """CREATE TABLE IF NOT EXISTS elixir_active (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  elixir TEXT NOT NULL,
  quality SMALLINT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS elixir_active_user ON elixir_active (user_id, expires_at)"""

# The emotes found by name, shared between clusters (each sees only its own shards' servers).
EMOJI_SQL = """CREATE TABLE IF NOT EXISTS elixir_emojis (
  elixir TEXT PRIMARY KEY,
  markup TEXT NOT NULL
)"""

# A chug (one player's joke: every elixir at once, gold, for their next battle). Taken when that battle starts.
CHUG_SQL = """CREATE TABLE IF NOT EXISTS elixir_chug (
  user_id BIGINT PRIMARY KEY,
  armed_at TIMESTAMPTZ NOT NULL DEFAULT now()
)"""

MARKET_SQL = """CREATE TABLE IF NOT EXISTS elixir_market (
  id BIGSERIAL PRIMARY KEY,
  seller BIGINT NOT NULL,
  consumable_type TEXT NOT NULL,
  quantity INTEGER NOT NULL CHECK (quantity >= 0),
  price BIGINT NOT NULL CHECK (price > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS elixir_market_type ON elixir_market (consumable_type, price)"""


def emoji(elixir_id: str) -> str:
    return ELIXIR_EMOJI.get(elixir_id) or DEFAULT_EMOJI


def learn_emojis(emojis) -> int:
    """Takes the emotes called elixir_<id> (any objects with .name, rendering as "<:name:id>")
    as the elixirs' icons. Returns how many elixirs now have one."""
    for e in emojis:
        name = str(getattr(e, "name", "") or "")
        if name.startswith("elixir_") and name[len("elixir_"):] in ELIXIRS:
            ELIXIR_EMOJI[name[len("elixir_"):]] = str(e)
    return len(ELIXIR_EMOJI)


def type_for(elixir_id: str, quality: int) -> str:
    return f"elixir_{elixir_id}_{QUALITIES[quality]}"


def parse_type(consumable_type: str) -> tuple[str, int] | None:
    """("giants_stew", 2) for "elixir_giants_stew_gold"; None for anything else."""
    text = str(consumable_type or "").strip().casefold()
    if not text.startswith("elixir_"):
        return None
    body, _, quality = text[len("elixir_"):].rpartition("_")
    if body not in ELIXIRS or quality not in QUALITIES:
        return None
    return body, QUALITIES.index(quality)


def is_elixir_type(consumable_type: str) -> bool:
    return parse_type(consumable_type) is not None


def value(elixir_id: str, quality: int) -> float:
    return float(ELIXIRS[elixir_id]["values"][quality])


def label(elixir_id: str, quality: int, *, with_emoji: bool = True) -> str:
    name = f"{QUALITY_NAMES[quality]} {ELIXIRS[elixir_id]['name']}"
    return f"{emoji(elixir_id)} {name}" if with_emoji else name


def effect_text(elixir_id: str, quality: int | None = None) -> str:
    e = ELIXIRS[elixir_id]
    shown = "/".join(_num(v) for v in e["values"]) if quality is None else _num(e["values"][quality])
    return e["effect"].replace("{v}", shown)


def _num(v: float) -> str:
    return f"{v:g}"


def parse_quality(word: str) -> int | None:
    w = str(word or "").strip().casefold()
    for i, q in enumerate(QUALITIES):
        if w in (q, q[0], QUALITY_NAMES[i].casefold()):
            return i
    return None


def find(query: str) -> tuple[str | None, int | None]:
    """An elixir and (if named) a quality from what a player typed: "gold giants stew",
    "giant's stew gold", "fire ward", "elixir_thornwine_plain"... (None, None) when nothing fits;
    raises LookupError with the candidates when several do."""
    parsed = parse_type(query)
    if parsed:
        return parsed
    words = [w for w in str(query or "").casefold().replace("'", "").replace("_", " ").split() if w]
    quality = None
    rest = []
    for w in words:
        if quality is None and w in QUALITIES:
            quality = QUALITIES.index(w)
        else:
            rest.append(w)
    wanted = " ".join(rest)
    if not wanted:
        return None, quality

    def norm(text: str) -> str:
        return text.casefold().replace("'", "").replace("_", " ")

    exact = [i for i, e in ELIXIRS.items() if wanted in (norm(i), norm(e["name"]))]
    if exact:
        return exact[0], quality
    loose = [i for i, e in ELIXIRS.items() if all(w in norm(e["name"]) + " " + norm(i) for w in rest)]
    if len(loose) == 1:
        return loose[0], quality
    if len(loose) > 1:
        raise LookupError([ELIXIRS[i]["name"] for i in loose])
    return None, quality


# ---- active elixirs ------------------------------------------------------------------------------

def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def active(conn, user_id: int) -> list[dict]:
    """The elixirs working for a player now: [{elixir, quality, expires_at}], soonest to end first."""
    try:
        rows = await conn.fetch(
            "SELECT elixir, quality, expires_at FROM elixir_active WHERE user_id = $1 AND expires_at > now() ORDER BY expires_at",
            int(user_id),
        )
    except Exception:
        return []
    return [dict(r) for r in rows if r["elixir"] in ELIXIRS]


def effects_from(rows: list[dict], *, limit: int = ACTIVE_MAX) -> dict:
    """What a player's active elixirs add up to: {key: fraction}, wards as {"ward": {element: fraction}}."""
    out: dict = {"names": []}
    for row in rows[:limit]:
        e = ELIXIRS.get(row["elixir"])
        if not e:
            continue
        q = int(row["quality"])
        v = Decimal(str(e["values"][q])) / Decimal(100)
        if e["key"] == "ward":
            out.setdefault("ward", {})[e["element"]] = max(out.get("ward", {}).get(e["element"], Decimal(0)), v)
        else:
            out[e["key"]] = max(out.get(e["key"], Decimal(0)), v)
        out["names"].append(label(row["elixir"], q))
    if "vigor" in out:
        out["vigor_left"] = 10
    return out


def chugged_effects() -> dict:
    """Every elixir at once, all gold: the chug."""
    rows = [{"elixir": elixir_id, "quality": 2} for elixir_id in ELIXIRS]
    out = effects_from(rows, limit=len(rows))
    out["chugged"] = True
    return out


async def take_chug(conn, user_id: int) -> bool:
    """Whether the player had a chug waiting (it's used up now)."""
    try:
        return bool(await conn.fetchval("DELETE FROM elixir_chug WHERE user_id = $1 RETURNING 1", int(user_id)))
    except Exception:
        return False


async def load_effects(conn, user_id: int) -> dict | None:
    if await take_chug(conn, user_id):
        return chugged_effects()
    rows = await active(conn, user_id)
    return effects_from(rows) if rows else None


# ---- in battle -----------------------------------------------------------------------------------

def _dec(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x or 0))


def apply_to_combatant(combatant, effects: dict | None) -> None:
    """Fold a player's elixirs into the Combatant the factory just built."""
    if not effects:
        return
    combatant.elixirs = effects
    hp = effects.get("hp")
    if hp:
        combatant.max_hp = _dec(combatant.max_hp) * (1 + hp)
        combatant.hp = _dec(combatant.hp) * (1 + hp)
    dmg = effects.get("damage")
    if dmg:
        combatant.damage = _dec(combatant.damage) * (1 + dmg)
    shield = effects.get("shield")
    if shield:
        combatant.shield = _dec(getattr(combatant, "shield", 0)) + _dec(combatant.max_hp) * shield


def battle_opening(battle) -> list[str]:
    """Team effects when a battle starts (Feast Pot, Beast Broth), and the lines that announce
    everyone's elixirs."""
    lines = []
    for team in getattr(battle, "teams", []) or []:
        members = list(getattr(team, "combatants", []) or [])
        players = [c for c in members if not getattr(c, "is_pet", False) and getattr(c, "elixirs", None)]
        for c in players:
            if getattr(c, "_elixirs_announced", False):
                continue
            c._elixirs_announced = True
            if c.elixirs.get("chugged"):
                lines.append(f"\U0001F37A The drunk idiot **{c.name}** thought it was a good idea to drink all elixirs.")
            else:
                lines.append(f"{DEFAULT_EMOJI} **{c.name}** uncorked {', '.join(c.elixirs['names'])}.")
        feast = max((c.elixirs.get("feast", Decimal(0)) for c in players), default=Decimal(0))
        if feast and not getattr(team, "_elixir_feast", False):
            team._elixir_feast = True
            for c in members:
                if not getattr(c, "is_pet", False):
                    c.shield = _dec(getattr(c, "shield", 0)) + _dec(c.max_hp) * feast
            lines.append(f"\U0001F372 A Feast Pot shields the whole team ({_num(float(feast * 100))}% of their max HP).")
        for pet in (c for c in members if getattr(c, "is_pet", False) and not getattr(c, "_elixir_beast", False)):
            owner = getattr(pet, "owner", None)
            keeper = next((c for c in players if c.user == owner or getattr(c.user, "id", None) == getattr(owner, "id", object())), None)
            beast = keeper and keeper.elixirs.get("beast")
            if beast:
                pet._elixir_beast = True
                pet.damage = _dec(pet.damage) * (1 + beast)
                pet.max_hp = _dec(pet.max_hp) * (1 + beast)
                pet.hp = _dec(pet.hp) * (1 + beast)
                lines.append(f"\U0001F356 **{pet.name}** gulps down the Beast Broth.")
    return lines


def damage_multiplier(attacker, defender, hit_element) -> tuple[Decimal, list[str]]:
    """Elixir effects on one hit's damage: the attacker's chill and crit, the defender's ward."""
    mult, messages = Decimal(1), []
    if getattr(attacker, "elixir_chilled", False):
        attacker.elixir_chilled = False
        mult *= Decimal("0.5")
        messages.append(f"❄️ **{attacker.name}** is chilled: the blow lands at half strength.")
    mine = getattr(attacker, "elixirs", None) or {}
    crit = mine.get("crit")
    if crit and random.random() < float(crit):
        mult *= Decimal("1.5")
        messages.append(f"\U0001F33F **{attacker.name}** finds a weak spot: a critical hit!")
    ward = (getattr(defender, "elixirs", None) or {}).get("ward", {})
    element = str(hit_element or "").strip().capitalize()
    if element in ward:
        mult *= 1 - ward[element]
        messages.append(f"\U0001F6E1️ **{defender.name}**'s salve turns aside {_num(float(ward[element] * 100))}% of the {element}.")
    return mult, messages


def after_hit(attacker, defender, damage) -> list[str]:
    """Elixir effects once a hit has landed: lifesteal, thorns, regen, the burn the attacker is
    carrying, and the chances to burn, chill or strike again."""
    messages: list[str] = []
    damage = _dec(damage)
    # A burning attacker smoulders on its own turn.
    burn = getattr(attacker, "elixir_burn", None)
    if burn and attacker.is_alive():
        tick, turns = burn
        attacker.take_damage(tick)
        messages.append(f"\U0001F525 **{attacker.name}** burns for **{tick:,.0f} HP**.")
        attacker.elixir_burn = (tick, turns - 1) if turns > 1 else None
    if damage <= 0:
        return messages
    mine = getattr(attacker, "elixirs", None) or {}
    leech = mine.get("leech")
    if leech and attacker.is_alive():
        heal = damage * leech
        attacker.heal(heal)
        messages.append(f"\U0001FA78 **{attacker.name}** drinks back **{heal:,.0f} HP** (Leechroot).")
    if mine.get("vigor") and mine.get("vigor_left", 0) > 0 and attacker.is_alive():
        mine["vigor_left"] -= 1
        heal = _dec(attacker.max_hp) * mine["vigor"]
        attacker.heal(heal)
        messages.append(f"\U0001F331 Vigor Broth mends **{attacker.name}** for **{heal:,.0f} HP**.")
    theirs = getattr(defender, "elixirs", None) or {}
    thorns = theirs.get("thorns")
    if thorns and attacker.is_alive():
        back = damage * thorns
        attacker.take_damage(back)
        messages.append(f"\U0001F339 Thornwine bites back: **{attacker.name}** takes **{back:,.0f} HP**.")
    if defender.is_alive():
        if mine.get("storm") and random.random() < float(mine["storm"]):
            extra = damage * Decimal("0.4")
            defender.take_damage(extra)
            messages.append(f"⚡ Lightning strikes **{defender.name}** again for **{extra:,.0f} HP**!")
        if mine.get("burn") and random.random() < float(mine["burn"]):
            defender.elixir_burn = (damage * Decimal("0.25"), 3)
            messages.append(f"\U0001F525 **{defender.name}** is set ablaze!")
        if mine.get("chill") and random.random() < float(mine["chill"]):
            defender.elixir_chilled = True
            messages.append(f"❄️ **{defender.name}** is chilled to the bone!")
    return messages


def phoenix_save(combatant) -> bool:
    """Phoenix Pepper: once per battle, a lethal blow leaves the drinker standing with part of
    their HP. True when it fired."""
    mine = getattr(combatant, "elixirs", None) or {}
    share = mine.get("phoenix")
    if not share or getattr(combatant, "is_pet", False) or mine.get("phoenix_used"):
        return False
    mine["phoenix_used"] = True
    combatant.hp = max(Decimal(1), _dec(combatant.max_hp) * share)
    pending = getattr(combatant, "pending_class_messages", None)
    if not isinstance(pending, list):
        pending = []
        combatant.pending_class_messages = pending
    pending.append(f"\U0001F525\U0001F426 **{combatant.name}** rises from the ashes with **{combatant.hp:,.0f} HP** (Phoenix Pepper)!")
    return True


def simple_stat_multipliers(combatant) -> tuple[Decimal, Decimal]:
    """For one-roll battles (classic $battle): elixirs as damage and armor multipliers."""
    mine = getattr(combatant, "elixirs", None) or {}
    damage = 1 + mine.get("damage", Decimal(0))
    armor = (1 + mine.get("hp", Decimal(0))) * (1 + mine.get("shield", Decimal(0)))
    return Decimal(damage), Decimal(armor)
