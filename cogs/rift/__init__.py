import asyncio
import random
import time
from datetime import datetime, timedelta

import discord
from discord.ext import commands

from cogs.battles.core.team import Team
from cogs.battles.types.tower import TowerBattle
from utils import misc as rpgtools
from utils.checks import has_char


RIFT_ADJECTIVES = (
    "Screaming",
    "Hollow",
    "Sunless",
    "Weeping",
    "Molten",
    "Frostbitten",
    "Umbral",
    "Shattered",
    "Verdant",
    "Static",
)
RIFT_PREFIXES = ("Riftspawn", "Voidtouched", "Echo of the", "Fractured", "Gleaming")
RIFT_CREATURES = ("Stalker", "Colossus", "Weaver", "Husk", "Sentinel", "Marauder", "Shade")
RIFT_ELEMENTS = ("Fire", "Water", "Nature", "Dark", "Light", "Electric", "Wind", "Corrupted")

RIFT_DIFFICULTIES = {
    "normal": {
        "label": "Normal",
        "min_level": 30,
        "score_multiplier": 1.00,
        "reward_multiplier": 1.00,
        "full_clear_lp": 100,
        "fortune_crates": 1,
        "pet_damage_weight": 0.90,
        "hp_floor_multiplier": 1.00,
        "damage_floor_multiplier": 1.00,
        "room_rounds_start": 2.0,
        "room_rounds_step": 0.22,
        "boss_rounds": 5.5,
        "room_pressure_start": 0.035,
        "room_pressure_step": 0.004,
        "boss_pressure": 0.085,
        "armor_pct": 0.12,
        "boss_armor_pct": 0.18,
    },
    "heroic": {
        "label": "Heroic",
        "min_level": 60,
        "score_multiplier": 1.25,
        "reward_multiplier": 1.25,
        "full_clear_lp": 125,
        "fortune_crates": 1,
        "pet_damage_weight": 0.95,
        "hp_floor_multiplier": 1.45,
        "damage_floor_multiplier": 1.35,
        "room_rounds_start": 3.0,
        "room_rounds_step": 0.35,
        "boss_rounds": 8.0,
        "room_pressure_start": 0.060,
        "room_pressure_step": 0.006,
        "boss_pressure": 0.130,
        "armor_pct": 0.18,
        "boss_armor_pct": 0.26,
    },
    "mythic": {
        "label": "Mythic",
        "min_level": 90,
        "score_multiplier": 1.65,
        "reward_multiplier": 1.60,
        "full_clear_lp": 150,
        "fortune_crates": 2,
        "pet_damage_weight": 1.00,
        "hp_floor_multiplier": 2.00,
        "damage_floor_multiplier": 1.80,
        "room_rounds_start": 4.2,
        "room_rounds_step": 0.55,
        "boss_rounds": 11.5,
        "room_pressure_start": 0.090,
        "room_pressure_step": 0.008,
        "boss_pressure": 0.180,
        "armor_pct": 0.24,
        "boss_armor_pct": 0.34,
    },
}
RIFT_DIFFICULTY_ALIASES = {
    "n": "normal",
    "norm": "normal",
    "normal": "normal",
    "h": "heroic",
    "hard": "heroic",
    "heroic": "heroic",
    "m": "mythic",
    "myth": "mythic",
    "mythic": "mythic",
}


def current_rift_week(now=None):
    now = now or datetime.utcnow()
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]}"


def next_rift_reset(now=None):
    now = now or datetime.utcnow()
    today_zero = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return today_zero + timedelta(days=7 - now.weekday())


def format_duration(seconds):
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def normalize_rift_difficulty(value):
    normalized = str(value or "normal").strip().lower()
    return RIFT_DIFFICULTY_ALIASES.get(normalized)


def rift_score(rooms_cleared, hp_pct, seconds, difficulty="normal"):
    difficulty_key = normalize_rift_difficulty(difficulty) or "normal"
    base_score = rooms_cleared * 10000 + int(hp_pct) * 10 + max(0, 3600 - int(seconds))
    return int(round(base_score * RIFT_DIFFICULTIES[difficulty_key]["score_multiplier"]))


def scale_rift_rooms(rift_data, player_damage, player_hp, player_armor, pet_damage=0, difficulty="normal"):
    difficulty_key = normalize_rift_difficulty(difficulty) or "normal"
    tuning = RIFT_DIFFICULTIES[difficulty_key]
    player_damage = max(25.0, float(player_damage or 0))
    player_hp = max(500.0, float(player_hp or 0))
    player_armor = max(0.0, float(player_armor or 0))
    pet_damage = max(0.0, float(pet_damage or 0))

    party_damage = max(25.0, player_damage + (pet_damage * tuning["pet_damage_weight"]))
    armor_reference = max(player_damage, party_damage * 0.55)

    scaled_rooms = []
    for room in rift_data["rooms"]:
        room_number = int(room["room"])
        is_boss = bool(room["is_boss"])
        if is_boss:
            expected_rounds = tuning["boss_rounds"]
            pressure = tuning["boss_pressure"]
            armor_pct = tuning["boss_armor_pct"]
        else:
            expected_rounds = tuning["room_rounds_start"] + (
                tuning["room_rounds_step"] * (room_number - 1)
            )
            pressure = tuning["room_pressure_start"] + (
                tuning["room_pressure_step"] * (room_number - 1)
            )
            armor_pct = tuning["armor_pct"]

        hp = max(
            float(room["hp"]) * tuning["hp_floor_multiplier"],
            party_damage * expected_rounds,
        )
        damage = max(
            float(room["damage"]) * tuning["damage_floor_multiplier"],
            player_armor + (player_hp * pressure),
        )
        armor = max(float(room["armor"]) * 0.75, armor_reference * armor_pct)

        scaled_room = dict(room)
        scaled_room["hp"] = int(round(hp))
        scaled_room["damage"] = int(round(damage))
        scaled_room["armor"] = int(round(armor))
        scaled_room["difficulty"] = difficulty_key
        scaled_rooms.append(scaled_room)

    scaled_rift = dict(rift_data)
    scaled_rift["rooms"] = scaled_rooms
    scaled_rift["difficulty"] = difficulty_key
    return scaled_rift


def generate_weekly_rift(week_token=None):
    if week_token is None:
        week_token = current_rift_week()
    rng = random.Random(f"rift-{week_token}")
    adjective = rng.choice(RIFT_ADJECTIVES)
    rooms = []
    for room in range(1, 8):
        variance = rng.uniform(0.9, 1.1)
        if room == 7:
            name = f"Herald of the {adjective} Rift"
            hp = int(2050 * 2 * variance)
            damage = int(310 * variance)
            armor = int(220 * variance)
            is_boss = True
        else:
            name = f"{rng.choice(RIFT_PREFIXES)} {rng.choice(RIFT_CREATURES)}"
            hp = int((300 + 140 * room) * variance)
            damage = int((90 + 30 * room) * variance)
            armor = int((60 + 22 * room) * variance)
            is_boss = False
        rooms.append(
            {
                "room": room,
                "name": name,
                "hp": hp,
                "damage": damage,
                "armor": armor,
                "element": rng.choice(RIFT_ELEMENTS),
                "is_boss": is_boss,
            }
        )
    return {"week": week_token, "title": f"The {adjective} Rift", "adjective": adjective, "rooms": rooms}


class RiftDifficultySelect(discord.ui.Select):
    def __init__(self, view):
        self.rift_view = view
        options = [
            discord.SelectOption(
                label="Normal Rift",
                value="normal",
                description="Level 30+. Forgiving scaling, 1.00x score, 1 crate and 100 LP.",
            ),
            discord.SelectOption(
                label="Heroic Rift",
                value="heroic",
                description="Level 60+. Stronger scaling, 1.25x score, 1 crate and 125 LP.",
            ),
            discord.SelectOption(
                label="Mythic Rift",
                value="mythic",
                description="Level 90+. Veteran scaling, 1.65x score, 2 crates and 150 LP.",
            ),
        ]
        super().__init__(
            placeholder="Choose your Rift difficulty",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.rift_view.choose(interaction, self.values[0])


class RiftDifficultyView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.message = None
        self.add_item(RiftDifficultySelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Only the player who opened this Rift can choose the difficulty.",
                ephemeral=True,
            )
            return False
        return True

    def _disable(self):
        for item in self.children:
            item.disabled = True

    async def choose(self, interaction: discord.Interaction, difficulty_key: str):
        self._disable()
        difficulty_label = RIFT_DIFFICULTIES[difficulty_key]["label"]
        await interaction.response.edit_message(
            content=f"Starting the {difficulty_label} Rift...",
            view=self,
        )
        self.stop()
        await self.cog._run_rift_attempt(self.ctx, difficulty_key)

    async def on_timeout(self):
        self._disable()
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class Rift(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._tables_ready = False
        self._table_lock = asyncio.Lock()

    async def ensure_tables(self):
        if self._tables_ready:
            return
        async with self._table_lock:
            if self._tables_ready:
                return
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rift_runs (
                        week TEXT NOT NULL,
                        user_id BIGINT NOT NULL,
                        rooms_cleared INT NOT NULL DEFAULT 0,
                        hp_pct REAL NOT NULL DEFAULT 0,
                        seconds INT NOT NULL DEFAULT 0,
                        score BIGINT NOT NULL DEFAULT 0,
                        difficulty TEXT NOT NULL DEFAULT 'normal',
                        ran_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (week, user_id)
                    );
                    """
                )
                await conn.execute(
                    """
                    ALTER TABLE rift_runs
                    ADD COLUMN IF NOT EXISTS difficulty TEXT NOT NULL DEFAULT 'normal';
                    """
                )
            self._tables_ready = True

    async def cog_load(self):
        await self.ensure_tables()

    @staticmethod
    def _difficulty_label(difficulty):
        difficulty_key = normalize_rift_difficulty(difficulty) or "normal"
        return RIFT_DIFFICULTIES[difficulty_key]["label"]

    async def _top_rows(self, week, limit=5):
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT user_id, rooms_cleared, score, difficulty
                FROM rift_runs
                WHERE week = $1 AND score > 0
                ORDER BY score DESC, rooms_cleared DESC, hp_pct DESC,
                         seconds ASC, user_id ASC
                LIMIT $2
                """,
                week,
                limit,
            )

    def _format_rooms(self, rift_data):
        return "\n".join(
            f"`{room['room']}.` {room['name']} ({room['element']})"
            for room in rift_data["rooms"]
        )

    def _format_top(self, rows):
        if not rows:
            return "No scored runs yet."
        return "\n".join(
            f"**#{idx}** <@{row['user_id']}> — "
            f"**{self._difficulty_label(row['difficulty'])}** · "
            f"{row['rooms_cleared']}/7 rooms · **{row['score']:,}**"
            for idx, row in enumerate(rows, start=1)
        )

    def _format_difficulties(self):
        return "\n".join(
            (
                f"**{info['label']}** - level {info['min_level']}+, "
                f"{info['score_multiplier']:.2f}x score"
            )
            for info in RIFT_DIFFICULTIES.values()
        )

    @commands.group(name="rift", invoke_without_command=True)
    @has_char()
    async def rift(self, ctx):
        """View this week's Rift."""
        await self.ensure_tables()
        week = current_rift_week()
        rift_data = generate_weekly_rift(week)
        reset = next_rift_reset()
        async with self.bot.pool.acquire() as conn:
            own_row = await conn.fetchrow(
                """
                SELECT rooms_cleared, score, difficulty
                FROM rift_runs
                WHERE week = $1 AND user_id = $2
                """,
                week,
                ctx.author.id,
            )
        top_rows = await self._top_rows(week, limit=5)

        attempt_text = "Unused"
        if own_row:
            difficulty_key = normalize_rift_difficulty(own_row["difficulty"]) or "normal"
            difficulty_label = RIFT_DIFFICULTIES[difficulty_key]["label"]
            attempt_text = (
                f"Used ({difficulty_label}) - {own_row['rooms_cleared']}/7 rooms, "
                f"score **{own_row['score']:,}**"
            )

        embed = discord.Embed(
            title=rift_data["title"],
            description="A seven-room weekly gauntlet. One weekly attempt. Choose the tier before entering.",
            color=0x5B2C6F,
        )
        embed.add_field(name="Rooms", value=self._format_rooms(rift_data), inline=False)
        embed.add_field(name="Difficulty", value=self._format_difficulties(), inline=False)
        embed.add_field(name="Your Attempt", value=attempt_text, inline=False)
        embed.add_field(name="Top 5 This Week", value=self._format_top(top_rows), inline=False)
        embed.add_field(
            name="Next Rift",
            value=format_duration((reset - datetime.utcnow()).total_seconds()),
            inline=False,
        )
        await ctx.send(embed=embed)

    @rift.command(name="top")
    async def rift_top(self, ctx):
        """Show the combined weekly Rift leaderboard."""
        await self.ensure_tables()
        week = current_rift_week()
        async with self.bot.pool.acquire() as conn:
            ranked_rows = await conn.fetch(
                """
                WITH ranked AS (
                    SELECT user_id, rooms_cleared, score, hp_pct, seconds,
                           difficulty,
                           ROW_NUMBER() OVER (
                               ORDER BY score DESC, rooms_cleared DESC,
                                        hp_pct DESC, seconds ASC, user_id ASC
                           ) AS position
                    FROM rift_runs
                    WHERE week = $1 AND score > 0
                )
                SELECT user_id, rooms_cleared, score, hp_pct, seconds,
                       difficulty, position
                FROM ranked
                WHERE position <= 10 OR user_id = $2
                ORDER BY position ASC
                """,
                week,
                ctx.author.id,
            )

        rows = [row for row in ranked_rows if int(row["position"]) <= 10]
        caller = next(
            (
                row
                for row in ranked_rows
                if int(row["user_id"]) == ctx.author.id
            ),
            None,
        )
        lines = [
            f"**#{int(row['position'])}** <@{row['user_id']}> — "
            f"**{self._difficulty_label(row['difficulty'])}** · "
            f"{row['rooms_cleared']}/7 rooms · **{row['score']:,}**"
            for row in rows
        ]
        embed = discord.Embed(
            title=f"Weekly Rift Leaderboard - {week}",
            description="\n".join(lines) if lines else "No scored runs yet.",
            color=0x5B2C6F,
        )
        if caller and int(caller["position"]) > 10:
            embed.set_footer(
                text=(
                    f"Your position: #{int(caller['position'])} · "
                    f"{self._difficulty_label(caller['difficulty'])} · "
                    f"{caller['rooms_cleared']}/7 rooms · "
                    f"Score {caller['score']:,}"
                )
            )
        await ctx.send(embed=embed)

    def _difficulty_picker_embed(self):
        embed = discord.Embed(
            title="Choose Rift Difficulty",
            description=(
                "Your weekly attempt is only spent after you pick a difficulty. "
                "Enemies scale from your current combat snapshot, including pet damage."
            ),
            color=0x5B2C6F,
        )
        embed.add_field(
            name="Normal",
            value="Level 30+ · forgiving scaling · 1.00x score · full clear: 1 Fortune Crate, 100 LP",
            inline=False,
        )
        embed.add_field(
            name="Heroic",
            value="Level 60+ · stronger scaling · 1.25x score · full clear: 1 Fortune Crate, 125 LP",
            inline=False,
        )
        embed.add_field(
            name="Mythic",
            value="Level 90+ · veteran scaling · 1.65x score · full clear: 2 Fortune Crates, 150 LP",
            inline=False,
        )
        return embed

    async def _send_difficulty_picker(self, ctx):
        view = RiftDifficultyView(self, ctx)
        view.message = await ctx.send(embed=self._difficulty_picker_embed(), view=view)

    @rift.command(name="enter")
    @has_char()
    async def rift_enter(self, ctx, difficulty: str = None):
        """Spend this week's Rift attempt."""
        await self.ensure_tables()
        if difficulty is None:
            return await self._send_difficulty_picker(ctx)

        difficulty_key = normalize_rift_difficulty(difficulty)
        if not difficulty_key:
            valid = "|".join(RIFT_DIFFICULTIES.keys())
            return await ctx.send(f"Usage: `$rift enter` or `$rift enter [{valid}]`")
        return await self._run_rift_attempt(ctx, difficulty_key)

    async def _run_rift_attempt(self, ctx, difficulty_key):
        await self.ensure_tables()
        difficulty_info = RIFT_DIFFICULTIES[difficulty_key]
        difficulty_label = difficulty_info["label"]

        battles = self.bot.get_cog("Battles")
        if not battles:
            return await ctx.send("The battle system is unavailable right now.")

        ctx = battles._guard_battle_context(ctx)
        async with self.bot.pool.acquire() as conn:
            profile = await conn.fetchrow('SELECT xp FROM profile WHERE "user" = $1', ctx.author.id)
        player_level = rpgtools.xptolevel(profile["xp"]) if profile else 0
        if player_level < difficulty_info["min_level"]:
            return await ctx.send(
                f"The {difficulty_label} Rift rejects the unproven. "
                f"Return at level {difficulty_info['min_level']}."
            )

        if await battles.is_player_in_fight(ctx.author.id):
            return await ctx.send("You are already in a battle!")

        week = current_rift_week()
        async with self.bot.pool.acquire() as conn:
            inserted = await conn.fetchval(
                """
                INSERT INTO rift_runs (week, user_id, difficulty)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
                RETURNING TRUE
                """,
                week,
                ctx.author.id,
                difficulty_key,
            )
        if not inserted:
            return await ctx.send("You have already spent this week's Rift attempt.")

        rift_data = generate_weekly_rift(week)
        await battles.add_player_to_fight(ctx.author.id)
        try:
            player_combatant = await battles.battle_factory.create_player_combatant(
                ctx, ctx.author, include_pet=True
            )
            pet_combatant = await battles.battle_factory.pet_ext.get_pet_combatant(ctx, ctx.author)
            player_team = Team("Player", [player_combatant])
            if pet_combatant:
                player_team.add_combatant(pet_combatant)

            rift_data = scale_rift_rooms(
                rift_data,
                player_combatant.damage,
                player_combatant.max_hp,
                player_combatant.armor,
                getattr(pet_combatant, "damage", 0) if pet_combatant else 0,
                difficulty_key,
            )
            enemy_team = Team("Enemy", [])
            for room in rift_data["rooms"]:
                spec = {
                    "name": room["name"],
                    "hp": room["hp"],
                    "attack": room["damage"],
                    "defense": room["armor"],
                    "element": room["element"],
                }
                enemy = await battles.battle_factory.create_monster_combatant(spec, name=spec["name"])
                if room["is_boss"]:
                    setattr(enemy, "is_boss", True)
                enemy_team.add_combatant(enemy)

            await ctx.send(
                f"🌀 **{rift_data['title']} ({difficulty_label}) opens.** "
                f"{ctx.author.mention}, this attempt is final."
            )
            hp_bar_style = "normal"
            if hasattr(battles, "_get_user_hp_bar_style"):
                hp_bar_style = await battles._get_user_hp_bar_style(ctx.author.id)
            hp_bar_style = TowerBattle.normalize_hp_bar_style(hp_bar_style)

            battle = TowerBattle(
                ctx,
                [player_team, enemy_team],
                level=1,
                level_data={},
                max_duration=timedelta(minutes=10),
                allow_pets=True,
                hp_bar_style=hp_bar_style,
                emoji_hp_bars=hp_bar_style != TowerBattle.HP_BAR_STYLE_NORMAL,
            )
            battle.config["allow_pets"] = True

            start_time = time.monotonic()
            await battle.start_battle()
            while not await battle.is_battle_over():
                await battle.process_turn()
                await asyncio.sleep(1)
            await battle.end_battle()

            rooms_cleared = sum(1 for enemy in enemy_team.combatants if not enemy.is_alive())
            surviving_player = next(
                (c for c in player_team.combatants if not getattr(c, "is_pet", False) and c.is_alive()),
                None,
            )
            if surviving_player and float(surviving_player.max_hp) > 0:
                hp_pct = max(0.0, float(surviving_player.hp) / float(surviving_player.max_hp) * 100.0)
            else:
                hp_pct = 0.0
            seconds = int(time.monotonic() - start_time)
            score = rift_score(rooms_cleared, hp_pct, seconds, difficulty_key)

            async with self.bot.pool.acquire() as conn:
                previous_best = await conn.fetchval(
                    """
                    SELECT COALESCE(MAX(score), 0)
                    FROM rift_runs
                    WHERE week = $1 AND difficulty = $2 AND user_id != $3
                    """,
                    week,
                    difficulty_key,
                    ctx.author.id,
                )
                await conn.execute(
                    """
                    UPDATE rift_runs
                    SET rooms_cleared = $3, hp_pct = $4, seconds = $5, score = $6,
                        difficulty = $7, ran_at = NOW()
                    WHERE week = $1 AND user_id = $2
                    """,
                    week,
                    ctx.author.id,
                    rooms_cleared,
                    hp_pct,
                    seconds,
                    score,
                    difficulty_key,
                )

            await ctx.send(
                f"{difficulty_label} Rift run complete: **{rooms_cleared}/7** rooms, "
                f"**{int(hp_pct)}%** HP, **{seconds}s**, score **{score:,}**."
            )
            self.bot.dispatch(
                "rift_completion",
                ctx,
                rooms_cleared,
                score,
                rooms_cleared == 7,
                difficulty_key,
            )

            try:
                money = int(round(rooms_cleared * 8000 * difficulty_info["reward_multiplier"]))
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET money = money + $1 WHERE "user" = $2',
                        money,
                        ctx.author.id,
                    )
                    if rooms_cleared == 7:
                        await conn.execute(
                            'UPDATE profile SET crates_fortune = crates_fortune + $1 WHERE "user" = $2',
                            difficulty_info["fortune_crates"],
                            ctx.author.id,
                        )
                if rooms_cleared == 7:
                    legacy = self.bot.get_cog("Legacy")
                    if legacy:
                        await legacy.award_points(ctx.author.id, difficulty_info["full_clear_lp"])
                    crate_word = "Crate" if difficulty_info["fortune_crates"] == 1 else "Crates"
                    await ctx.send(
                        "🌀 **THE RIFT IS SEALED!** Fortune bends around the victor: "
                        f"+{difficulty_info['fortune_crates']} Fortune {crate_word} and "
                        f"+{difficulty_info['full_clear_lp']} Legacy Points."
                    )
                if score > int(previous_best or 0):
                    await ctx.send(
                        f"👑 **New {difficulty_label} Rift record this week:** "
                        f"{ctx.author.mention} leads with **{score:,}**!"
                    )
            except Exception:
                pass
        finally:
            await battles.remove_player_from_fight(ctx.author.id)


async def setup(bot):
    await bot.add_cog(Rift(bot))
