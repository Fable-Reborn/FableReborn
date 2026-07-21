import asyncio
import json
from datetime import datetime
from decimal import Decimal

import discord
from discord.ext import commands

from cogs.battles.extensions.elements import ElementExtension
from cogs.battles.core.team import Team
from cogs.battles.types.tower import TowerBattle
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils.checks import has_char


class Gauntlet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._tables_ready = False
        self._table_lock = asyncio.Lock()
        self._element_ext = ElementExtension()

    async def ensure_tables(self):
        if self._tables_ready:
            return
        async with self._table_lock:
            if self._tables_ready:
                return
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gauntlet_defenses (
                        user_id BIGINT PRIMARY KEY,
                        hp DOUBLE PRECISION NOT NULL,
                        damage DOUBLE PRECISION NOT NULL,
                        armor DOUBLE PRECISION NOT NULL,
                        attack_element TEXT NOT NULL DEFAULT 'Unknown',
                        defense_element TEXT NOT NULL DEFAULT 'Unknown',
                        pet_name TEXT,
                        pet_hp DOUBLE PRECISION,
                        pet_damage DOUBLE PRECISION,
                        pet_armor DOUBLE PRECISION,
                        pet_element TEXT NOT NULL DEFAULT 'Unknown',
                        class_snapshot TEXT NOT NULL DEFAULT '{}',
                        pet_snapshot TEXT NOT NULL DEFAULT '{}',
                        streak INT NOT NULL DEFAULT 0,
                        best_streak INT NOT NULL DEFAULT 0,
                        rating INT NOT NULL DEFAULT 0,
                        set_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
                await conn.execute(
                    """
                    ALTER TABLE gauntlet_defenses
                    ADD COLUMN IF NOT EXISTS attack_element TEXT NOT NULL DEFAULT 'Unknown',
                    ADD COLUMN IF NOT EXISTS defense_element TEXT NOT NULL DEFAULT 'Unknown',
                    ADD COLUMN IF NOT EXISTS pet_element TEXT NOT NULL DEFAULT 'Unknown',
                    ADD COLUMN IF NOT EXISTS class_snapshot TEXT NOT NULL DEFAULT '{}',
                    ADD COLUMN IF NOT EXISTS pet_snapshot TEXT NOT NULL DEFAULT '{}';
                    """
                )
            self._tables_ready = True

    async def cog_load(self):
        await self.ensure_tables()

    @classmethod
    def _json_safe(cls, value):
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, dict):
            return {str(k): cls._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._json_safe(v) for v in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @classmethod
    def _json_dumps(cls, value) -> str:
        return json.dumps(cls._json_safe(value or {}), sort_keys=True)

    @staticmethod
    def _json_loads(raw):
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _class_snapshot_from_combatant(self, combatant) -> dict:
        attrs = (
            "luck",
            "lifesteal_percent",
            "death_cheat_chance",
            "mage_evolution",
            "tank_evolution",
            "paladin_evolution",
            "raider_evolution",
            "ritualist_evolution",
            "paragon_evolution",
            "bard_evolution",
            "beastmaster_evolution",
            "reaper_evolution",
            "santa_evolution",
            "damage_reflection",
            "has_shield",
            "spec_effects",
            "ascension_mantle",
            "ascension_enabled",
            "ascension_signature_used",
            "ascension_opening_used",
            "ascension_survival_used",
            "display_level",
            "display_classes",
            "dual_attack_elements",
        )
        return {
            attr: self._json_safe(getattr(combatant, attr))
            for attr in attrs
            if hasattr(combatant, attr)
        }

    def _pet_snapshot_from_combatant(self, combatant) -> dict:
        if not combatant:
            return {}
        attrs = (
            "skill_effects",
            "passive_effects",
            "active_abilities",
            "happiness",
            "trust_level",
            "display_level",
            "pet_id",
            "ultimate_threshold",
            "ultimate_ready",
            "ultimate_activated",
            "flame_shield",
            "flame_shield_recharge",
            "energy_barrier",
            "energy_barrier_recharge",
        )
        return {
            attr: self._json_safe(getattr(combatant, attr))
            for attr in attrs
            if hasattr(combatant, attr)
        }

    def _apply_snapshot_attrs(self, combatant, raw_snapshot, *, owner=None, user_id=None):
        snapshot = self._json_loads(raw_snapshot)
        if not isinstance(snapshot, dict):
            return {}
        for attr, value in snapshot.items():
            if attr in {"pet_id"}:
                continue
            setattr(combatant, attr, value)
        if owner is not None:
            combatant.owner = owner
        if user_id is not None:
            combatant.user_id = int(user_id)
        return snapshot

    @staticmethod
    def _snapshot_skill_summary(raw_snapshot) -> str:
        snapshot = Gauntlet._json_loads(raw_snapshot)
        skill_effects = snapshot.get("skill_effects") if isinstance(snapshot, dict) else {}
        if not isinstance(skill_effects, dict) or not skill_effects:
            return "No saved pet skills"
        names = [str(name).replace("_", " ").title() for name in skill_effects.keys()]
        preview = ", ".join(names[:4])
        extra = len(names) - 4
        return f"{preview}{f' +{extra} more' if extra > 0 else ''}"

    @staticmethod
    def _snapshot_class_summary(raw_snapshot) -> str:
        snapshot = Gauntlet._json_loads(raw_snapshot)
        classes = snapshot.get("display_classes") if isinstance(snapshot, dict) else None
        if isinstance(classes, list) and classes:
            return " / ".join(str(c) for c in classes if c) or "No saved classes"
        return "No saved classes"

    async def _live_snapshot(self, ctx, member, conn, battles):
        profile = await conn.fetchrow(
            'SELECT health, stathp, xp FROM profile WHERE "user" = $1',
            member.id,
        )
        if not profile:
            return None
        player_combatant = await battles.battle_factory.create_player_combatant(
            ctx,
            member,
            include_pet=True,
        )
        pet_combatant = await battles.battle_factory.pet_ext.get_pet_combatant(
            ctx,
            member,
            conn=conn,
        )
        equipped_items = await conn.fetch(
            """
            SELECT ai.type, ai.damage, ai.armor, ai.element
            FROM profile p
            JOIN allitems ai ON (p.user = ai.owner)
            JOIN inventory i ON (ai.id = i.item)
            WHERE i.equipped IS TRUE AND p.user = $1;
            """,
            member.id,
        )
        element_data = self._element_ext.resolve_player_combat_elements(equipped_items)
        pet = await conn.fetchrow(
            """
            SELECT name, hp, attack, defense, element
            FROM monster_pets
            WHERE user_id = $1 AND equipped = TRUE
            """,
            member.id,
        )
        return {
            "hp": float(player_combatant.max_hp),
            "damage": float(player_combatant.damage),
            "armor": float(player_combatant.armor),
            "attack_element": getattr(
                player_combatant,
                "attack_element",
                element_data.get("attack_element", "Unknown"),
            ),
            "defense_element": getattr(
                player_combatant,
                "defense_element",
                element_data.get("defense_element", "Unknown"),
            ),
            "class_snapshot": self._class_snapshot_from_combatant(player_combatant),
            "pet_name": pet_combatant.name if pet_combatant else (pet["name"] if pet else None),
            "pet_hp": float(pet_combatant.max_hp) if pet_combatant else None,
            "pet_damage": float(pet_combatant.damage) if pet_combatant else None,
            "pet_armor": float(pet_combatant.armor) if pet_combatant else None,
            "pet_element": (
                getattr(pet_combatant, "element", None)
                if pet_combatant
                else str(pet["element"]).strip().capitalize()
                if pet and pet["element"]
                else "Unknown"
            ),
            "pet_snapshot": self._pet_snapshot_from_combatant(pet_combatant),
        }

    def _snapshot_age_text(self, set_at):
        if not set_at:
            return "unknown"
        if getattr(set_at, "tzinfo", None):
            set_at = set_at.replace(tzinfo=None)
        age = datetime.utcnow() - set_at
        days = age.days
        if days <= 0:
            return "today"
        return f"{days} day{'s' if days != 1 else ''} ago"

    @commands.group(name="gauntlet", invoke_without_command=True)
    @has_char()
    async def gauntlet(self, ctx):
        """View your Defense Gauntlet status."""
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM gauntlet_defenses WHERE user_id = $1",
                ctx.author.id,
            )
        if not row:
            return await ctx.send("You have no gauntlet defense set. Use `$gauntlet set` first.")
        age_days = (datetime.utcnow() - row["set_at"].replace(tzinfo=None)).days
        warning = "\n⚠️ Snapshot is older than 14 days. Refresh it with `$gauntlet set`." if age_days > 14 else ""
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Gauntlet",
            description=(
                f"Rating: **{row['rating']}**\n"
                f"Current defense streak: **{row['streak']}**\n"
                f"Best streak: **{row['best_streak']}**\n"
                f"Snapshot age: **{self._snapshot_age_text(row['set_at'])}**{warning}"
            ),
            color=0x34495E,
        )
        embed.add_field(
            name="Snapshot",
            value=(
                f"HP {row['hp']:,.0f} · Damage {row['damage']:,.0f} · "
                f"Armor {row['armor']:,.0f}\n"
                f"Attack element: **{row['attack_element']}** · "
                f"Defense element: **{row['defense_element']}**\n"
                f"Classes: **{self._snapshot_class_summary(row['class_snapshot'])}**"
            ),
            inline=False,
        )
        if row["pet_name"]:
            embed.add_field(
                name="Pet",
                value=(
                    f"{row['pet_name']} — HP {row['pet_hp']:,.0f} · "
                    f"Damage {row['pet_damage']:,.0f} · Armor {row['pet_armor']:,.0f} · "
                    f"Element **{row['pet_element']}**\n"
                    f"Skills: **{self._snapshot_skill_summary(row['pet_snapshot'])}**"
                ),
                inline=False,
            )
        await ctx.send(embed=embed)

    @gauntlet.command(name="set")
    @has_char()
    async def gauntlet_set(self, ctx):
        """Snapshot your current defense."""
        await self.ensure_tables()
        battles = self.bot.get_cog("Battles")
        if not battles:
            return await ctx.send("The battle system is unavailable right now.")
        async with self.bot.pool.acquire() as conn:
            snapshot = await self._live_snapshot(ctx, ctx.author, conn, battles)
            if not snapshot:
                return await ctx.send("You need a character before setting a gauntlet defense.")
            await conn.execute(
                """
                INSERT INTO gauntlet_defenses (
                    user_id, hp, damage, armor, attack_element, defense_element,
                    pet_name, pet_hp, pet_damage, pet_armor, pet_element,
                    class_snapshot, pet_snapshot, set_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    hp = EXCLUDED.hp,
                    damage = EXCLUDED.damage,
                    armor = EXCLUDED.armor,
                    attack_element = EXCLUDED.attack_element,
                    defense_element = EXCLUDED.defense_element,
                    pet_name = EXCLUDED.pet_name,
                    pet_hp = EXCLUDED.pet_hp,
                    pet_damage = EXCLUDED.pet_damage,
                    pet_armor = EXCLUDED.pet_armor,
                    pet_element = EXCLUDED.pet_element,
                    class_snapshot = EXCLUDED.class_snapshot,
                    pet_snapshot = EXCLUDED.pet_snapshot,
                    set_at = NOW()
                """,
                ctx.author.id,
                snapshot["hp"],
                snapshot["damage"],
                snapshot["armor"],
                snapshot["attack_element"],
                snapshot["defense_element"],
                snapshot["pet_name"],
                snapshot["pet_hp"],
                snapshot["pet_damage"],
                snapshot["pet_armor"],
                snapshot["pet_element"],
                self._json_dumps(snapshot["class_snapshot"]),
                self._json_dumps(snapshot["pet_snapshot"]),
            )
        class_text = self._snapshot_class_summary(snapshot["class_snapshot"])
        skill_text = self._snapshot_skill_summary(snapshot["pet_snapshot"])
        pet_text = (
            f"\nPet: **{snapshot['pet_name']}** ({snapshot['pet_hp']:,.0f} HP, "
            f"{snapshot['pet_damage']:,.0f} damage, {snapshot['pet_armor']:,.0f} armor, "
            f"{snapshot['pet_element']} element, skills: {skill_text})"
            if snapshot["pet_name"]
            else "\nPet: none"
        )
        await ctx.send(
            f"Gauntlet defense set: **{snapshot['hp']:,.0f} HP**, "
            f"**{snapshot['damage']:,.0f} damage**, **{snapshot['armor']:,.0f} armor**, "
            f"attack **{snapshot['attack_element']}**, defense **{snapshot['defense_element']}**."
            f"\nClasses: **{class_text}**."
            f"{pet_text}"
        )

    @gauntlet.command(name="attack")
    @has_char()
    @user_cooldown(1800)
    async def gauntlet_attack(self, ctx, member: discord.Member = None):
        """Attack another player's gauntlet defense."""
        await self.ensure_tables()
        battles = self.bot.get_cog("Battles")
        if not battles:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send("The battle system is unavailable right now.")
        ctx = battles._guard_battle_context(ctx)

        if await battles.is_player_in_fight(ctx.author.id):
            await self.bot.reset_cooldown(ctx)
            return await ctx.send("You are already in a battle!")

        async with self.bot.pool.acquire() as conn:
            attacker_row = await conn.fetchrow(
                "SELECT rating FROM gauntlet_defenses WHERE user_id = $1",
                ctx.author.id,
            )
            if not attacker_row:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send("Set your own defense first with `$gauntlet set`.")

            if member is not None:
                if member.id == ctx.author.id:
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send("You cannot attack your own gauntlet.")
                defender_row = await conn.fetchrow(
                    "SELECT * FROM gauntlet_defenses WHERE user_id = $1",
                    member.id,
                )
                if not defender_row:
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send("That player has no gauntlet defense set.")
                defender_id = member.id
                defender_name = member.display_name
            else:
                defender_row = await conn.fetchrow(
                    """
                    SELECT *
                    FROM gauntlet_defenses
                    WHERE user_id != $1
                    ORDER BY ABS(rating - $2), RANDOM()
                    LIMIT 1
                    """,
                    ctx.author.id,
                    int(attacker_row["rating"] or 0),
                )
                if not defender_row:
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send("No gauntlet defenses are available to attack.")
                defender_id = int(defender_row["user_id"])
                defender_name = f"<@{defender_id}>"

        await battles.add_player_to_fight(ctx.author.id)
        try:
            player = await battles.battle_factory.create_player_combatant(ctx, ctx.author, include_pet=True)
            pet = await battles.battle_factory.pet_ext.get_pet_combatant(ctx, ctx.author)
            player_team = Team("Player", [player])
            if pet:
                player_team.add_combatant(pet)

            enemy_team = Team("Enemy", [])
            defender_spec = {
                "name": str(defender_name),
                "hp": defender_row["hp"],
                "attack": defender_row["damage"],
                "defense": defender_row["armor"],
                "element": defender_row["attack_element"],
            }
            defender = await battles.battle_factory.create_monster_combatant(
                defender_spec,
                name=str(defender_name),
            )
            defender.user = defender_id
            defender.attack_element = defender_row["attack_element"]
            defender.defense_element = defender_row["defense_element"]
            defender.element = defender.attack_element
            self._apply_snapshot_attrs(defender, defender_row["class_snapshot"])
            enemy_team.add_combatant(defender)
            if defender_row["pet_name"]:
                pet_spec = {
                    "name": defender_row["pet_name"],
                    "hp": defender_row["pet_hp"],
                    "attack": defender_row["pet_damage"],
                    "defense": defender_row["pet_armor"],
                    "element": defender_row["pet_element"],
                }
                defender_pet = await battles.battle_factory.create_monster_combatant(
                    pet_spec,
                    name=pet_spec["name"],
                )
                defender_pet.is_pet = True
                self._apply_snapshot_attrs(
                    defender_pet,
                    defender_row["pet_snapshot"],
                    owner=defender,
                    user_id=defender_id,
                )
                enemy_team.add_combatant(defender_pet)

            hp_bar_style = "normal"
            if hasattr(battles, "_get_user_hp_bar_style"):
                hp_bar_style = await battles._get_user_hp_bar_style(ctx.author.id)
            hp_bar_style = TowerBattle.normalize_hp_bar_style(hp_bar_style)

            battle = TowerBattle(
                ctx,
                [player_team, enemy_team],
                level=1,
                level_data={},
                allow_pets=True,
                hp_bar_style=hp_bar_style,
                emoji_hp_bars=hp_bar_style != TowerBattle.HP_BAR_STYLE_NORMAL,
            )
            battle.config["allow_pets"] = True
            await battle.start_battle()
            while not await battle.is_battle_over():
                await battle.process_turn()
                await asyncio.sleep(1)
            result = await battle.end_battle()

            player_alive = any(not c.is_pet and c.is_alive() for c in player_team.combatants)
            attacker_won = bool(result and result.name == "Player" and player_alive)
            async with self.bot.pool.acquire() as conn:
                if attacker_won:
                    gain = 10 + 2 * int(defender_row["streak"] or 0)
                    await conn.execute(
                        "UPDATE gauntlet_defenses SET rating = rating + $1 WHERE user_id = $2",
                        gain,
                        ctx.author.id,
                    )
                    await conn.execute(
                        "UPDATE gauntlet_defenses SET streak = 0 WHERE user_id = $1",
                        defender_id,
                    )
                    await ctx.send(
                        f"⚔️ {ctx.author.mention} breached {defender_name}'s gauntlet (+{gain} rating)!"
                    )
                    self.bot.dispatch(
                        "gauntlet_completion",
                        ctx,
                        ctx.author.id,
                        int(defender_row["user_id"]),
                        True,
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE gauntlet_defenses
                        SET streak = streak + 1,
                            best_streak = GREATEST(best_streak, streak + 1),
                            rating = rating + 3
                        WHERE user_id = $1
                        """,
                        defender_id,
                    )
                    await ctx.send(
                        f"🛡️ {defender_name}'s gauntlet held against {ctx.author.mention} (+3 rating)!"
                    )
                    self.bot.dispatch(
                        "gauntlet_completion",
                        ctx,
                        ctx.author.id,
                        int(defender_row["user_id"]),
                        False,
                    )
        finally:
            await battles.remove_player_from_fight(ctx.author.id)

    @gauntlet.command(name="top")
    async def gauntlet_top(self, ctx):
        """Show the Defense Gauntlet ladder."""
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            ratings = await conn.fetch(
                """
                SELECT user_id, rating, streak, best_streak
                FROM gauntlet_defenses
                ORDER BY rating DESC, best_streak DESC
                LIMIT 10
                """
            )
            streaks = await conn.fetch(
                """
                SELECT user_id, streak, rating
                FROM gauntlet_defenses
                WHERE streak > 0
                ORDER BY streak DESC, rating DESC
                LIMIT 3
                """
            )
        rating_lines = [
            f"**#{idx}** <@{row['user_id']}> — **{row['rating']}** rating (best {row['best_streak']})"
            for idx, row in enumerate(ratings, start=1)
        ]
        streak_lines = [
            f"**#{idx}** <@{row['user_id']}> — **{row['streak']}** holds"
            for idx, row in enumerate(streaks, start=1)
        ]
        embed = discord.Embed(title="Defense Gauntlet Ladder", color=0x34495E)
        embed.add_field(name="Top Rating", value="\n".join(rating_lines) or "No defenses set.", inline=False)
        embed.add_field(name="Active Streaks", value="\n".join(streak_lines) or "No active streaks.", inline=False)
        embed.set_footer(text="No season resets or payouts in v1.")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Gauntlet(bot))
