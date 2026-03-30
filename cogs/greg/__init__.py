import asyncio
import math

import discord

from discord.ext import commands, tasks
from discord.ui import Button, View

from classes.badges import Badge
from utils.april_fools import APRIL_FOOLS_GREG_FLAG
from utils.checks import has_char, is_gm


GREG_LORE_PAGES = [
    {
        "title": "Gregapocalypse",
        "text": (
            "At first, they thought it was grave-robbers.\n\n"
            "Then came the bells.\n\n"
            "One by one, from village crypts, roadside tombs, and forgotten churchyards, "
            "the dead clawed their way back into the moonlight. They did not howl. They did "
            "not hunt. They rose as if answering some distant summons, stumbling through the "
            "fog with earth in their mouths and one sound upon their tongues.\n\n"
            "A single name.\n\n"
            "Greg."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_bf7f8806-d8d5-4599-8632-2554eef5039c.png"
        ),
    },
    {
        "title": "The Curse Spreads",
        "text": (
            "By dawn, it was no longer only the dead.\n\n"
            "Hounds turned at their masters' voices as though hearing strangers. Stable-beasts "
            "stamped and wailed. Familiars, companions, and battle-pets stared with hollow eyes, "
            "as if some hand within them had begun to scrape away what they once were.\n\n"
            "In the square, before witnesses, one poor soul watched their own companion shudder, "
            "stiffen, and begin to change.\n\n"
            "Not into some beast of fang or plague.\n\n"
            "Into a Greg."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_29_2026_09_11_33_PM.png"
        ),
    },
    {
        "title": "The Black Ledger",
        "text": (
            "The abbey keepers searched the burial rolls for answers.\n\n"
            "They found only terror.\n\n"
            "Every death record, no matter how old, had been rewritten in the same hand. "
            "Knights, beggars, children, beasts, wanderers, stillborn babes, plague-dead, "
            "nameless bones pulled from riverbeds, all of them now bore the same inscription.\n\n"
            "Greg.\n\n"
            "And where the ink had not changed, the parchment had blackened as if scorched from within."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_d8a2cdb4-5c83-474c-be9b-33cb060e05a6.png"
        ),
    },
    {
        "title": "What Was Forgotten",
        "text": (
            "There are old whispers beneath Fable's soil.\n\n"
            "They speak of a keeper of graves, a scribe of the unremembered dead, who would not "
            "suffer the lost to vanish from the world without a name. In secret, he gathered the "
            "names of the buried, the forsaken, and the forgotten, and set them down in a book no "
            "fire should have touched.\n\n"
            "But some rites are not meant for mortal hands.\n\n"
            "Something answered.\n\n"
            "And where there had once been thousands of names, only one remained."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_29_2026_09_23_39_PM.png"
        ),
    },
    {
        "title": "Now the Bells Toll for Us",
        "text": (
            "The curse no longer sleeps in crypt and graveyard alone.\n\n"
            "It moves through pet and tower, through ruin and road, through the living and the dead "
            "alike. Those struck by it do not merely sicken. They are unmade, little by little, until "
            "their own true name slips from them like ash in rain.\n\n"
            "The grave-priests beg for aid. The villages bar their doors. The towers murmur with voices "
            "that are no longer their own.\n\n"
            "If this blight is not cut out at its root, Fable will soon be a realm of one name and a "
            "thousand empty faces."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_29_2026_09_28_11_PM.png"
        ),
    },
    {
        "title": "Your Charge",
        "text": (
            "Go forth into the dark places.\n\n"
            "Gather the remnants of what has been stolen.\n\n"
            "Hunt the Gregbound dead.\n\n"
            "Find the buried source of the curse.\n\n"
            "And before the final bell is rung, restore the names of the lost.\n\n"
            "Or join them."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_29_2026_09_34_05_PM.png"
        ),
    },
]

GREG_BOSS_CUTSCENE_PAGES = [
    {
        "title": "The Greg of All Gregs",
        "subtitle": "The Black Crypt",
        "text": (
            "The doors of the crypt drag open.\n\n"
            "Rows of the dead kneel in silence.\n\n"
            "At the far end of the chamber, a lone figure sits upon a throne of broken "
            "grave-stone and blackened ledgers.\n\n"
            "Then it lifts its head.\n\n"
            "“Another one,” it says."
        ),
        "image": "",
    },
    {
        "title": "The Greg of All Gregs",
        "subtitle": "The One Upon the Throne",
        "text": (
            "Your pet bristles at your side.\n\n"
            "The figure rises slowly, candlelight catching on a crown of bent grave-nails.\n\n"
            "“All this way,” it murmurs, “just to die protecting a name that will not "
            "outlive your bones.”\n\n"
            "From the dark around you comes a whisper, low and endless.\n\n"
            "`Greg. Greg. Greg.`"
        ),
        "image": "",
    },
    {
        "title": "The Greg of All Gregs",
        "subtitle": "The Exchange",
        "text": (
            "You tighten your grip on your weapon.\n\n"
            "“So this is your doing?”\n\n"
            "The figure tilts its head, almost amused.\n\n"
            "“My doing?” it says. “No.”\n\n"
            "It takes one step down from the throne.\n\n"
            "“My correction.”"
        ),
        "image": "",
    },
    {
        "title": "The Greg of All Gregs",
        "subtitle": "The Name Revealed",
        "text": (
            "The candles flare bright.\n\n"
            "The dead rise as one.\n\n"
            "All around you, hollow voices murmur from the dark.\n\n"
            "`Greg. Greg. Greg.`\n\n"
            "The figure spreads its arms.\n\n"
            "“I am the last name they will ever need.”"
        ),
        "image": "",
    },
    {
        "title": "The Greg of All Gregs",
        "subtitle": "The Greg of All Gregs",
        "text": (
            "Its eyes burn with pale fire.\n\n"
            "“I am the Greg of All Gregs.”\n\n"
            "Then it smiles.\n\n"
            "“Come, hero. Let us see if your name survives mine.”"
        ),
        "image": "",
    },
]

GREG_BOSS_MONSTER_DATA = {
    "name": "The Greg of All Gregs",
    "hp": 17500,
    "attack": 3650,
    "defense": 2800,
    "element": "Corrupted",
    "url": "",
    "encounter_level": 100,
    "pve_tier": 11,
    "ispublic": False,
}

GREG_BOSS_OPENING_LINES = (
    "The Greg of All Gregs rises from the throne of blackened ledgers.",
    "A thousand hollow throats answer in chorus: Greg. Greg. Greg.",
    "Your own name feels suddenly fragile in your chest.",
)


class GregLoreView(View):
    def __init__(self, pages, user_id):
        super().__init__(timeout=300)
        self.pages = pages
        self.current_page = 0
        self.user_id = user_id
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        prev_button = Button(
            style=discord.ButtonStyle.secondary,
            emoji="◀️",
            disabled=self.current_page == 0,
        )
        prev_button.callback = self.prev_callback

        next_button = Button(
            style=discord.ButtonStyle.secondary,
            emoji="▶️",
            disabled=self.current_page >= len(self.pages) - 1,
        )
        next_button.callback = self.next_callback

        self.add_item(prev_button)
        self.add_item(
            Button(
                style=discord.ButtonStyle.gray,
                label=f"{self.current_page + 1}/{len(self.pages)}",
                disabled=True,
            )
        )
        self.add_item(next_button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This lore view is not yours.",
                ephemeral=True,
            )
            return False
        return True

    async def prev_callback(self, interaction):
        self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.current_page],
            view=self,
        )

    async def next_callback(self, interaction):
        self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.current_page],
            view=self,
        )


class GregBossStartView(View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.user_id = ctx.author.id
        self.started = False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This confrontation is not yours.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Begin Battle", style=discord.ButtonStyle.danger)
    async def begin_battle(self, interaction: discord.Interaction, button: Button):
        if self.started:
            return await interaction.response.send_message(
                "The battle has already been called forth.",
                ephemeral=True,
            )

        self.started = True
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await self.cog._run_greg_boss_battle(self.ctx)
        self.stop()


class Greg(commands.Cog):
    GREG_SKULL_GOAL = 25000
    BADGE_SKULL_REQUIREMENT = 25
    GREG_BOSS_TIER = 11
    GREG_FINALE_EVENT_KEY = "greg_finale_open"
    GREG_BADGE = Badge.GREGAPOCALYPSE_SURVIVOR
    GREG_BADGE_NAME = "Gregapocalypse Survivor"
    COMMUNITY_STAGES = (
        (0, "The Empty Graves"),
        (6250, "The Black Ledger"),
        (12500, "The Bells Toll"),
        (18750, "The Black Crypt"),
        (25000, "The Final Seal"),
    )
    OUTBREAK_TIERS = (
        (0, "Tier I - The Graves Stir"),
        (250, "Tier II - Churchyard Murmurs"),
        (600, "Tier III - Nameblight Rising"),
        (1200, "Tier IV - Bell of Ruin"),
        (2000, "Tier V - Gregbound Night"),
    )

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        await self._init_tables()
        if not self.death_toll_loop.is_running():
            self.death_toll_loop.start()
        await self._sync_finale_event_flag()

    def cog_unload(self):
        if self.death_toll_loop.is_running():
            self.death_toll_loop.cancel()

    async def _init_tables(self):
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS greg_event_global (
                    id SMALLINT PRIMARY KEY,
                    total_skulls BIGINT NOT NULL DEFAULT 0,
                    death_toll BIGINT NOT NULL DEFAULT 0,
                    outbreak_tier INTEGER NOT NULL DEFAULT 1,
                    boss_unlocked BOOLEAN NOT NULL DEFAULT FALSE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS greg_event_players (
                    user_id BIGINT PRIMARY KEY,
                    skulls BIGINT NOT NULL DEFAULT 0,
                    badge_claimed BOOLEAN NOT NULL DEFAULT FALSE,
                    boss_cleared BOOLEAN NOT NULL DEFAULT FALSE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                ALTER TABLE greg_event_players
                ADD COLUMN IF NOT EXISTS boss_cleared BOOLEAN NOT NULL DEFAULT FALSE
                """
            )
            await conn.execute(
                """
                INSERT INTO greg_event_global (id, total_skulls, death_toll, outbreak_tier, boss_unlocked)
                VALUES (1, 0, 0, 1, FALSE)
                ON CONFLICT (id) DO NOTHING
                """
            )

    async def _sync_finale_event_flag(self, *, boss_unlocked: bool | None = None):
        if boss_unlocked is None:
            async with self.bot.pool.acquire() as conn:
                boss_unlocked = bool(
                    await conn.fetchval(
                        """
                        SELECT boss_unlocked
                        FROM greg_event_global
                        WHERE id = 1
                        """
                    )
                    or False
                )

        enabled = self._greg_event_enabled() and bool(boss_unlocked)
        gm_cog = self.bot.get_cog("GameMaster")
        if gm_cog and hasattr(gm_cog, "set_event_enabled"):
            current = bool((getattr(self.bot, "event_flags", {}) or {}).get(self.GREG_FINALE_EVENT_KEY, False))
            if current != enabled:
                await gm_cog.set_event_enabled(self.GREG_FINALE_EVENT_KEY, enabled)
            return

        event_flags = dict(getattr(self.bot, "event_flags", {}) or {})
        event_flags[self.GREG_FINALE_EVENT_KEY] = enabled
        self.bot.event_flags = event_flags

    def _greg_event_enabled(self) -> bool:
        flags = getattr(self.bot, "april_fools_flags", {}) or {}
        return bool(flags.get(APRIL_FOOLS_GREG_FLAG, False))

    def _parse_bool(self, raw: str | None) -> bool | None:
        if raw is None:
            return None
        value = str(raw).strip().lower()
        if value in {"on", "true", "enable", "enabled", "1", "yes", "y"}:
            return True
        if value in {"off", "false", "disable", "disabled", "0", "no", "n"}:
            return False
        return None

    def _build_progress_bar(self, current: int, total: int, *, length: int = 10) -> str:
        current = max(0, int(current or 0))
        total = max(1, int(total or 1))
        filled = min(length, int(math.floor((current / total) * length)))
        return f"[{'█' * filled}{'░' * (length - filled)}]"

    def _community_stage(self, total_skulls: int) -> str:
        current_stage = self.COMMUNITY_STAGES[0][1]
        for threshold, stage_name in self.COMMUNITY_STAGES:
            if total_skulls >= threshold:
                current_stage = stage_name
            else:
                break
        return current_stage

    def _outbreak_tier_data(self, death_toll: int) -> tuple[int, str, int | None]:
        tier_number = 1
        tier_name = self.OUTBREAK_TIERS[0][1]
        next_threshold = None

        for index, (threshold, label) in enumerate(self.OUTBREAK_TIERS, start=1):
            if death_toll >= threshold:
                tier_number = index
                tier_name = label
                next_threshold = (
                    self.OUTBREAK_TIERS[index][0]
                    if index < len(self.OUTBREAK_TIERS)
                    else None
                )
            else:
                break

        return tier_number, tier_name, next_threshold

    def _skulls_for_pve(self, levelchoice: int) -> int:
        if levelchoice >= 11:
            return 3
        if levelchoice >= 8:
            return 2
        return 1

    def _hourly_death_toll_gain(self, total_skulls: int) -> int:
        progress_ratio = min(1.0, max(0.0, total_skulls / self.GREG_SKULL_GOAL))
        return max(3, 12 - int(progress_ratio * 8))

    async def _get_event_state(self, user_id: int):
        async with self.bot.pool.acquire() as conn:
            global_row = await conn.fetchrow(
                """
                SELECT total_skulls, death_toll, outbreak_tier, boss_unlocked
                FROM greg_event_global
                WHERE id = 1
                """
            )
            player_row = await conn.fetchrow(
                """
                SELECT skulls, badge_claimed, boss_cleared
                FROM greg_event_players
                WHERE user_id = $1
                """,
                user_id,
            )

        return (
            global_row or {
                "total_skulls": 0,
                "death_toll": 0,
                "outbreak_tier": 1,
                "boss_unlocked": False,
            },
            player_row or {
                "skulls": 0,
                "badge_claimed": False,
                "boss_cleared": False,
            },
        )

    async def _award_pve_skulls(self, user_id: int, skulls: int):
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                global_row = await conn.fetchrow(
                    """
                    SELECT total_skulls, death_toll, outbreak_tier, boss_unlocked
                    FROM greg_event_global
                    WHERE id = 1
                    FOR UPDATE
                    """
                )
                player_row = await conn.fetchrow(
                    """
                    SELECT skulls, badge_claimed, boss_cleared
                    FROM greg_event_players
                    WHERE user_id = $1
                    FOR UPDATE
                    """,
                    user_id,
                )

                previous_total = int(global_row["total_skulls"] if global_row else 0)
                previous_player = int(player_row["skulls"] if player_row else 0)
                death_toll = int(global_row["death_toll"] if global_row else 0)

                new_total = previous_total + skulls
                new_player = previous_player + skulls
                boss_unlocked = bool(global_row["boss_unlocked"] if global_row else False)
                newly_unlocked = not boss_unlocked and new_total >= self.GREG_SKULL_GOAL
                if newly_unlocked:
                    boss_unlocked = True

                outbreak_tier, _, _ = self._outbreak_tier_data(death_toll)

                await conn.execute(
                    """
                    INSERT INTO greg_event_players (user_id, skulls, badge_claimed, updated_at)
                    VALUES ($1, $2, FALSE, NOW())
                    ON CONFLICT (user_id)
                    DO UPDATE SET skulls = $2, updated_at = NOW()
                    """,
                    user_id,
                    new_player,
                )
                await conn.execute(
                    """
                    UPDATE greg_event_global
                    SET total_skulls = $1,
                        outbreak_tier = $2,
                        boss_unlocked = $3,
                        updated_at = NOW()
                    WHERE id = 1
                    """,
                    new_total,
                    outbreak_tier,
                    boss_unlocked,
                )

        await self._sync_finale_event_flag(boss_unlocked=boss_unlocked)

        previous_stage = self._community_stage(previous_total)
        current_stage = self._community_stage(new_total)

        return {
            "previous_total": previous_total,
            "new_total": new_total,
            "previous_player": previous_player,
            "new_player": new_player,
            "newly_unlocked": newly_unlocked,
            "crossed_stage": current_stage != previous_stage,
            "current_stage": current_stage,
            "badge_requirement_hit": (
                previous_player < self.BADGE_SKULL_REQUIREMENT
                and new_player >= self.BADGE_SKULL_REQUIREMENT
            ),
        }

    async def _set_global_progress(
        self,
        *,
        total_skulls: int | None = None,
        death_toll: int | None = None,
        boss_unlocked: bool | None = None,
    ):
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT total_skulls, death_toll, outbreak_tier, boss_unlocked
                    FROM greg_event_global
                    WHERE id = 1
                    FOR UPDATE
                    """
                )

                current_total = int(row["total_skulls"] if row else 0)
                current_death = int(row["death_toll"] if row else 0)
                current_boss = bool(row["boss_unlocked"] if row else False)

                next_total = current_total if total_skulls is None else max(0, int(total_skulls))
                next_death = current_death if death_toll is None else max(0, int(death_toll))
                next_boss = current_boss if boss_unlocked is None else bool(boss_unlocked)
                outbreak_tier, _, _ = self._outbreak_tier_data(next_death)

                await conn.execute(
                    """
                    UPDATE greg_event_global
                    SET total_skulls = $1,
                        death_toll = $2,
                        outbreak_tier = $3,
                        boss_unlocked = $4,
                        updated_at = NOW()
                    WHERE id = 1
                    """,
                    next_total,
                    next_death,
                    outbreak_tier,
                    next_boss,
                )

        await self._sync_finale_event_flag(boss_unlocked=next_boss)

        return {
            "total_skulls": next_total,
            "death_toll": next_death,
            "outbreak_tier": outbreak_tier,
            "boss_unlocked": next_boss,
        }

    async def _grant_greg_badge(self, user_id: int, *, conn) -> bool:
        raw_badges = await conn.fetchval(
            'SELECT "badges" FROM profile WHERE "user" = $1;',
            user_id,
        )
        if raw_badges is None:
            current_badges = Badge(0)
        else:
            try:
                current_badges = Badge.from_db(raw_badges)
            except Exception:
                current_badges = Badge(0)

        if current_badges & self.GREG_BADGE:
            return False

        await conn.execute(
            'UPDATE profile SET "badges" = $1 WHERE "user" = $2;',
            (current_badges | self.GREG_BADGE).to_db(),
            user_id,
        )
        return True

    async def _record_boss_clear(self, user_id: int, *, conn) -> tuple[bool, bool]:
        row = await conn.fetchrow(
            """
            SELECT skulls, badge_claimed, boss_cleared
            FROM greg_event_players
            WHERE user_id = $1
            FOR UPDATE
            """,
            user_id,
        )

        player_skulls = int(row["skulls"] if row else 0)
        badge_claimed = bool(row["badge_claimed"] if row else False)
        already_cleared = bool(row["boss_cleared"] if row else False)

        granted_badge = False
        if not badge_claimed and player_skulls >= self.BADGE_SKULL_REQUIREMENT:
            granted_badge = await self._grant_greg_badge(user_id, conn=conn)
            badge_claimed = True

        await conn.execute(
            """
            INSERT INTO greg_event_players (user_id, skulls, badge_claimed, boss_cleared, updated_at)
            VALUES ($1, $2, $3, TRUE, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET badge_claimed = $3, boss_cleared = TRUE, updated_at = NOW()
            """,
            user_id,
            player_skulls,
            badge_claimed,
        )

        return already_cleared, granted_badge

    async def _remove_greg_badge(self, user_id: int, *, conn) -> bool:
        raw_badges = await conn.fetchval(
            'SELECT "badges" FROM profile WHERE "user" = $1;',
            user_id,
        )
        if raw_badges is None:
            current_badges = Badge(0)
        else:
            try:
                current_badges = Badge.from_db(raw_badges)
            except Exception:
                current_badges = Badge(0)

        if not current_badges & self.GREG_BADGE:
            return False

        await conn.execute(
            'UPDATE profile SET "badges" = $1 WHERE "user" = $2;',
            (current_badges & ~self.GREG_BADGE).to_db(),
            user_id,
        )
        return True

    async def _get_admin_counts(self):
        async with self.bot.pool.acquire() as conn:
            player_count = await conn.fetchval(
                "SELECT COUNT(*) FROM greg_event_players"
            )
            claimed_count = await conn.fetchval(
                "SELECT COUNT(*) FROM greg_event_players WHERE badge_claimed = TRUE"
            )
            cleared_count = await conn.fetchval(
                "SELECT COUNT(*) FROM greg_event_players WHERE boss_cleared = TRUE"
            )
        return int(player_count or 0), int(claimed_count or 0), int(cleared_count or 0)

    def _build_greg_boss_monster(self) -> dict:
        return dict(GREG_BOSS_MONSTER_DATA)

    def _create_story_pages(self, story_pages, footer_prefix: str):
        pages = []
        page_total = len(story_pages)

        for index, page in enumerate(story_pages, start=1):
            description = page["text"]
            subtitle = str(page.get("subtitle") or "").strip()
            if subtitle:
                description = f"**{subtitle}**\n\n{description}"
            embed = discord.Embed(
                title=page["title"],
                description=description,
                color=0x1F0D0D,
            )
            image_url = str(page.get("image") or "").strip()
            if image_url:
                embed.set_image(url=image_url)
            embed.set_footer(text=f"{footer_prefix} {index}/{page_total}")
            pages.append(embed)

        return pages

    def create_lore_pages(self):
        return self._create_story_pages(GREG_LORE_PAGES, "Gregapocalypse")

    def create_boss_cutscene_pages(self):
        return self._create_story_pages(
            GREG_BOSS_CUTSCENE_PAGES,
            "Gregapocalypse Boss",
        )

    async def send_lore(self, ctx):
        quests_cog = self.bot.get_cog("Quests")
        if quests_cog is not None and await quests_cog.play_cutscene(ctx, "greg_intro_lore"):
            return
        lore_pages = self.create_lore_pages()
        view = GregLoreView(lore_pages, ctx.author.id)
        await ctx.send(embed=lore_pages[0], view=view)

    async def send_boss_cutscene(self, ctx):
        quests_cog = self.bot.get_cog("Quests")
        if quests_cog is not None and await quests_cog.play_cutscene(ctx, "greg_boss_intro"):
            return
        cutscene_pages = self.create_boss_cutscene_pages()
        view = GregLoreView(cutscene_pages, ctx.author.id)
        await ctx.send(embed=cutscene_pages[0], view=view)

    async def _get_greg_boss_gate_error(self, ctx, *, require_uncleared: bool) -> str | None:
        if not self._greg_event_enabled():
            return "Greg mode is not enabled. Turn on `$gmapril greg` before entering the Black Crypt."

        global_state, player_state = await self._get_event_state(ctx.author.id)
        if not bool(global_state["boss_unlocked"]):
            return "The final seal is still intact. The realm must gather more Greg Skulls first."

        player_skulls = int(player_state["skulls"] or 0)
        if player_skulls < self.BADGE_SKULL_REQUIREMENT:
            remaining = self.BADGE_SKULL_REQUIREMENT - player_skulls
            return (
                f"You need **{remaining}** more Greg Skulls before you can challenge "
                "**The Greg of All Gregs**."
            )

        quests_cog = self.bot.get_cog("Quests")
        has_scripted_finale = False
        if quests_cog is not None and hasattr(quests_cog, "has_active_custom_source_objective"):
            has_scripted_finale = await quests_cog.has_active_custom_source_objective(
                ctx.author.id,
                "scripted",
                candidate_names=("The Greg of All Gregs",),
            )

        if require_uncleared and bool(player_state.get("boss_cleared")) and not has_scripted_finale:
            return "You have already defeated **The Greg of All Gregs**."

        if (
            quests_cog is not None
            and not has_scripted_finale
            and not await quests_cog.is_quest_completed(
                ctx.author.id,
                "gregapocalypse",
            )
        ):
            return (
                "You are not ready to enter the Black Crypt yet. Either finish the built-in "
                "Greg investigation with `$quests turnin gregapocalypse`, or accept your custom "
                "finale quest in `$quests` first."
            )

        return None

    async def _run_greg_boss_battle(self, ctx):
        gate_error = await self._get_greg_boss_gate_error(ctx, require_uncleared=True)
        if gate_error:
            await ctx.send(gate_error)
            return False

        battles_cog = self.bot.get_cog("Battles")
        if battles_cog is None:
            await ctx.send("The battle system is unavailable right now.")
            return False

        if await battles_cog.is_player_in_fight(ctx.author.id):
            await ctx.send("You are already in a fight.")
            return False

        ctx = battles_cog._guard_battle_context(ctx)
        monster_data = self._build_greg_boss_monster()

        intro_embed = discord.Embed(
            title="The Greg of All Gregs",
            description=(
                "The Black Crypt groans open. Beneath the abbey, the last stolen name rises to meet you."
            ),
            color=0x5C0F0F,
        )
        if monster_data.get("url"):
            intro_embed.set_image(url=str(monster_data["url"]))
        await ctx.send(embed=intro_embed)

        await battles_cog.add_player_to_fight(ctx.author.id)
        try:
            battle = await battles_cog.battle_factory.create_battle(
                "pve",
                ctx,
                player=ctx.author,
                monster_data=monster_data,
                monster_level=self.GREG_BOSS_TIER,
                macro_penalty_level=0,
            )
            await battle.start_battle()

            for boss_line in GREG_BOSS_OPENING_LINES:
                await battle.add_to_log(boss_line)
            await battle.update_display()
            await asyncio.sleep(1)

            while not await battle.is_battle_over():
                await battle.process_turn()
                await asyncio.sleep(1)

            result = await battle.end_battle()
        except Exception as exc:
            import traceback

            print(traceback.format_exc())
            await ctx.send(f"An error occurred starting the Greg boss battle: {exc}")
            return False
        finally:
            await battles_cog.remove_player_from_fight(ctx.author.id)

        if not result or result.name != "Player":
            await ctx.send(
                "The Greg of All Gregs still stands. The crypt seals itself around its laughter."
            )
            return False

        quests_cog = self.bot.get_cog("Quests")
        if quests_cog and hasattr(quests_cog, "process_external_source_completion"):
            await quests_cog.process_external_source_completion(
                ctx,
                "scripted",
                candidate_names=(monster_data.get("name"),),
            )

        async with self.bot.pool.acquire() as conn:
            already_cleared, granted_badge = await self._record_boss_clear(
                ctx.author.id,
                conn=conn,
            )

        if already_cleared:
            await ctx.send(
                "The Greg of All Gregs falls again, though the realm had already marked your victory."
            )
            return True

        reward_embed = discord.Embed(
            title="The Greg of All Gregs Falls",
            description=(
                "The throne of ledgers cracks apart, and the chorus of stolen names finally breaks."
            ),
            color=0x7A1212,
        )
        if granted_badge:
            reward_embed.add_field(
                name="Reward Claimed",
                value=f"**{self.GREG_BADGE_NAME}** has been added to your profile.",
                inline=False,
            )
        else:
            reward_embed.add_field(
                name="Reward Recorded",
                value=(
                    f"Your clear has been recorded. If needed, you can still use `$greg claim` "
                    f"for **{self.GREG_BADGE_NAME}**."
                ),
                inline=False,
            )
        await ctx.send(embed=reward_embed)
        return True

    async def send_status(self, ctx):
        global_state, player_state = await self._get_event_state(ctx.author.id)
        total_skulls = int(global_state["total_skulls"] or 0)
        death_toll = int(global_state["death_toll"] or 0)
        boss_unlocked = bool(global_state["boss_unlocked"])
        player_skulls = int(player_state["skulls"] or 0)
        badge_claimed = bool(player_state["badge_claimed"])
        boss_cleared = bool(player_state.get("boss_cleared"))
        event_enabled = self._greg_event_enabled()

        _, outbreak_label, next_threshold = self._outbreak_tier_data(death_toll)
        community_bar = self._build_progress_bar(total_skulls, self.GREG_SKULL_GOAL)
        death_total_for_bar = next_threshold if next_threshold is not None else max(death_toll, 1)
        death_bar = self._build_progress_bar(death_toll, death_total_for_bar)

        if badge_claimed:
            badge_status = f"Claimed: **{self.GREG_BADGE_NAME}**"
        elif not boss_unlocked:
            badge_status = (
                f"Locked until the realm gathers **{self.GREG_SKULL_GOAL:,} Greg Skulls**."
            )
        elif player_skulls < self.BADGE_SKULL_REQUIREMENT:
            remaining = self.BADGE_SKULL_REQUIREMENT - player_skulls
            badge_status = f"Need **{remaining}** more Greg Skulls before you can face the finale."
        elif boss_cleared:
            badge_status = f"Boss defeated. Use `$greg claim` if the reward was not marked automatically."
        elif not event_enabled:
            badge_status = "Greg mode is off. Turn it back on to claim the badge."
        else:
            badge_status = "The seal is broken. Use `$greg boss` to enter the Black Crypt."

        description = (
            "The Gregbound are on the march."
            if event_enabled
            else "Greg mode is currently disabled. Gregapocalypse progress is frozen."
        )

        embed = discord.Embed(
            title="Gregapocalypse Status",
            description=description,
            color=0x3D1010 if event_enabled else 0x4A4A4A,
        )
        embed.add_field(
            name="Community Purge",
            value=f"{community_bar} **{total_skulls:,} / {self.GREG_SKULL_GOAL:,} Greg Skulls**",
            inline=False,
        )
        if next_threshold is None:
            death_value = f"{death_bar} **{death_toll:,} Fallen**"
        else:
            death_value = f"{death_bar} **{death_toll:,} / {next_threshold:,} Fallen**"
        embed.add_field(
            name="Death Toll",
            value=death_value,
            inline=False,
        )
        embed.add_field(
            name="Outbreak Tier",
            value=outbreak_label,
            inline=True,
        )
        embed.add_field(
            name="Your Contribution",
            value=f"**{player_skulls:,} Greg Skulls**",
            inline=True,
        )
        embed.add_field(
            name="Current Front",
            value=self._community_stage(total_skulls),
            inline=True,
        )
        embed.add_field(
            name="Final Seal",
            value="Broken for the realm." if boss_unlocked else "Still sealed.",
            inline=True,
        )
        embed.add_field(
            name="Your Finale",
            value="Cleared." if boss_cleared else "Not yet defeated.",
            inline=True,
        )
        embed.add_field(
            name="Badge Reward",
            value=badge_status,
            inline=False,
        )
        embed.set_footer(
            text=(
                "Only active while $gmapril greg is on."
                if event_enabled
                else "Progress resumes when $gmapril greg is turned back on."
            )
        )
        await ctx.send(embed=embed)

    @tasks.loop(hours=1)
    async def death_toll_loop(self):
        if not self._greg_event_enabled():
            return

        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT total_skulls, death_toll
                FROM greg_event_global
                WHERE id = 1
                """
            )
            if not row:
                return

            total_skulls = int(row["total_skulls"] or 0)
            death_toll = int(row["death_toll"] or 0)
            death_toll += self._hourly_death_toll_gain(total_skulls)
            outbreak_tier, _, _ = self._outbreak_tier_data(death_toll)

            await conn.execute(
                """
                UPDATE greg_event_global
                SET death_toll = $1,
                    outbreak_tier = $2,
                    updated_at = NOW()
                WHERE id = 1
                """,
                death_toll,
                outbreak_tier,
            )

    @death_toll_loop.before_loop
    async def before_death_toll_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_PVE_completion(
        self,
        ctx,
        success,
        monster_name=None,
        element=None,
        levelchoice=None,
        battle_id=None,
    ):
        if not success or not self._greg_event_enabled():
            return
        if levelchoice is None:
            # Ignore the lightweight duplicate dispatch from the PvE battle class.
            return

        skulls = self._skulls_for_pve(int(levelchoice or 1))
        award_state = await self._award_pve_skulls(ctx.author.id, skulls)

        try:
            if award_state["newly_unlocked"]:
                embed = discord.Embed(
                    title="The Final Seal Breaks",
                    description=(
                        f"The realm has gathered **{award_state['new_total']:,} Greg Skulls**. "
                        "The Black Crypt stirs, and the final seal has broken."
                    ),
                    color=0x7A1212,
                )
                embed.add_field(
                    name="The Crypt Opens",
                    value=(
                        f"Anyone with at least **{self.BADGE_SKULL_REQUIREMENT} Greg Skulls** "
                        "and a completed Gregapocalypse investigation can now face "
                        "**The Greg of All Gregs** with `$greg boss`."
                    ),
                    inline=False,
                )
                await ctx.send(embed=embed)
            elif award_state["badge_requirement_hit"]:
                await ctx.send(
                    f"💀 You now have **{award_state['new_player']} Greg Skulls**. "
                    "When the final seal breaks, you will qualify to face "
                    "**The Greg of All Gregs**."
                )
            elif award_state["crossed_stage"]:
                await ctx.send(
                    f"🔔 The Gregapocalypse worsens. Community progress has reached "
                    f"**{award_state['current_stage']}**."
                )
        except Exception:
            pass

    @commands.group(
        name="greg",
        aliases=["gregapocalypse", "gregapoc", "gregapoclypse"],
        invoke_without_command=True,
    )
    async def greg(self, ctx):
        await self.send_lore(ctx)

    @greg.command(name="lore", aliases=["intro", "story"])
    async def greg_lore(self, ctx):
        await self.send_lore(ctx)

    @has_char()
    @greg.command(
        name="bossintro",
        aliases=["cutscene", "bossscene", "finaleintro", "gregofallgregs"],
    )
    async def greg_bossintro(self, ctx):
        if not self._greg_event_enabled():
            return await ctx.send(
                "Greg mode is not enabled. Turn on `$gmapril greg` before entering the Black Crypt."
            )

        global_state, _ = await self._get_event_state(ctx.author.id)
        if not bool(global_state["boss_unlocked"]):
            return await ctx.send(
                "The final seal is still intact. The realm must gather more Greg Skulls first."
            )

        gate_error = await self._get_greg_boss_gate_error(ctx, require_uncleared=False)
        if gate_error:
            return await ctx.send(gate_error)

        await self.send_boss_cutscene(ctx)

    @has_char()
    @greg.command(name="boss", aliases=["fight", "crypt", "finalboss"])
    async def greg_boss(self, ctx):
        gate_error = await self._get_greg_boss_gate_error(ctx, require_uncleared=True)
        if gate_error:
            return await ctx.send(gate_error)

        await self.send_boss_cutscene(ctx)

        monster_data = self._build_greg_boss_monster()
        prompt_embed = discord.Embed(
            title="The Black Crypt",
            description=(
                "The confrontation lies before you. When you are ready, press **Begin Battle** "
                "to face **The Greg of All Gregs**."
            ),
            color=0x5C0F0F,
        )
        if monster_data.get("url"):
            prompt_embed.set_image(url=str(monster_data["url"]))
        prompt_embed.set_footer(text="Use `$greg bossintro` any time if you want to rewatch the cutscene.")
        await ctx.send(embed=prompt_embed, view=GregBossStartView(self, ctx))

    @has_char()
    @greg.command(name="status", aliases=["progress"])
    async def greg_status(self, ctx):
        await self.send_status(ctx)

    @has_char()
    @greg.command(name="claim", aliases=["badge", "claimbadge"])
    async def greg_claim(self, ctx):
        if not self._greg_event_enabled():
            return await ctx.send(
                "Greg mode is not enabled. Turn on `$gmapril greg` before claiming event rewards."
            )

        global_state, player_state = await self._get_event_state(ctx.author.id)
        boss_unlocked = bool(global_state["boss_unlocked"])
        player_skulls = int(player_state["skulls"] or 0)
        badge_claimed = bool(player_state["badge_claimed"])
        boss_cleared = bool(player_state.get("boss_cleared"))

        if badge_claimed:
            return await ctx.send(f"You already claimed **{self.GREG_BADGE_NAME}**.")
        if not boss_unlocked:
            return await ctx.send(
                f"The realm has not gathered the required **{self.GREG_SKULL_GOAL:,} Greg Skulls** yet."
            )
        if player_skulls < self.BADGE_SKULL_REQUIREMENT:
            remaining = self.BADGE_SKULL_REQUIREMENT - player_skulls
            return await ctx.send(
                f"You need **{remaining}** more Greg Skulls before you can claim the badge."
            )
        if not boss_cleared:
            return await ctx.send(
                "You must defeat **The Greg of All Gregs** with `$greg boss` before claiming the badge."
            )

        async with self.bot.pool.acquire() as conn:
            granted = await self._grant_greg_badge(ctx.author.id, conn=conn)
            await conn.execute(
                """
                INSERT INTO greg_event_players (user_id, skulls, badge_claimed, boss_cleared, updated_at)
                VALUES ($1, $2, TRUE, TRUE, NOW())
                ON CONFLICT (user_id)
                DO UPDATE SET badge_claimed = TRUE, boss_cleared = TRUE, updated_at = NOW()
                """,
                ctx.author.id,
                player_skulls,
            )

        if granted:
            await ctx.send(
                f"You claim **{self.GREG_BADGE_NAME}** for surviving the Gregapocalypse."
            )
        else:
            await ctx.send(
                f"Your profile already had **{self.GREG_BADGE_NAME}**. The event reward is now marked as claimed."
            )

    @is_gm()
    @greg.group(name="gm", aliases=["admin"], invoke_without_command=True)
    async def greg_gm(self, ctx):
        global_state, _player_state = await self._get_event_state(ctx.author.id)
        player_count, claimed_count, cleared_count = await self._get_admin_counts()
        embed = discord.Embed(
            title="Gregapocalypse Admin",
            color=0x6E1212,
        )
        embed.add_field(
            name="Greg Mode",
            value="enabled" if self._greg_event_enabled() else "disabled",
            inline=True,
        )
        embed.add_field(
            name="Community Skulls",
            value=f"{int(global_state['total_skulls'] or 0):,}",
            inline=True,
        )
        embed.add_field(
            name="Death Toll",
            value=f"{int(global_state['death_toll'] or 0):,}",
            inline=True,
        )
        embed.add_field(
            name="Boss Unlocked",
            value="yes" if bool(global_state["boss_unlocked"]) else "no",
            inline=True,
        )
        embed.add_field(
            name="Tracked Players",
            value=f"{player_count:,}",
            inline=True,
        )
        embed.add_field(
            name="Badges Claimed",
            value=f"{claimed_count:,}",
            inline=True,
        )
        embed.add_field(
            name="Boss Clears",
            value=f"{cleared_count:,}",
            inline=True,
        )
        embed.set_footer(
            text=(
                "$greg gm setskulls <n> | $greg gm setdeathtoll <n> | "
                "$greg gm boss on/off | $greg gm resetall [revokebadge]"
            )
        )
        await ctx.send(embed=embed)

    @is_gm()
    @greg_gm.command(name="status")
    async def greg_gm_status(self, ctx):
        await self.greg_gm(ctx)

    @is_gm()
    @greg_gm.command(name="setskulls", aliases=["skulls"])
    async def greg_gm_setskulls(self, ctx, amount: int):
        amount = max(0, int(amount))
        state = await self._set_global_progress(
            total_skulls=amount,
            boss_unlocked=amount >= self.GREG_SKULL_GOAL,
        )
        await ctx.send(
            f"Greg Skulls set to **{state['total_skulls']:,}**. "
            f"Boss is now **{'unlocked' if state['boss_unlocked'] else 'locked'}**."
        )

    @is_gm()
    @greg_gm.command(name="setdeathtoll", aliases=["deathtoll", "toll"])
    async def greg_gm_setdeathtoll(self, ctx, amount: int):
        amount = max(0, int(amount))
        state = await self._set_global_progress(death_toll=amount)
        _, outbreak_label, _ = self._outbreak_tier_data(state["death_toll"])
        await ctx.send(
            f"Death Toll set to **{state['death_toll']:,}**. "
            f"Outbreak now reads **{outbreak_label}**."
        )

    @is_gm()
    @greg_gm.command(name="boss", aliases=["unlockboss", "seal"])
    async def greg_gm_boss(self, ctx, enabled: str | None = None):
        parsed = self._parse_bool(enabled)
        if parsed is None:
            global_state, _ = await self._get_event_state(ctx.author.id)
            parsed = not bool(global_state["boss_unlocked"])

        state = await self._set_global_progress(boss_unlocked=parsed)
        await ctx.send(
            f"The final seal is now **{'broken' if state['boss_unlocked'] else 'sealed'}**."
        )

    @is_gm()
    @greg_gm.command(name="player")
    async def greg_gm_player(self, ctx, user: discord.User):
        _global_state, player_state = await self._get_event_state(user.id)
        badge_claimed = bool(player_state["badge_claimed"])
        boss_cleared = bool(player_state.get("boss_cleared"))
        skulls = int(player_state["skulls"] or 0)
        await ctx.send(
            f"**{user}**: **{skulls:,}** Greg Skulls, "
            f"badge claimed: **{'yes' if badge_claimed else 'no'}**, "
            f"boss cleared: **{'yes' if boss_cleared else 'no'}**."
        )

    @is_gm()
    @greg_gm.command(name="setplayer", aliases=["playerskulls"])
    async def greg_gm_setplayer(self, ctx, user: discord.User, amount: int):
        amount = max(0, int(amount))
        async with self.bot.pool.acquire() as conn:
            badge_claimed = await conn.fetchval(
                """
                SELECT badge_claimed
                FROM greg_event_players
                WHERE user_id = $1
                """,
                user.id,
            )
            await conn.execute(
                """
                INSERT INTO greg_event_players (user_id, skulls, badge_claimed, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id)
                DO UPDATE SET skulls = $2, updated_at = NOW()
                """,
                user.id,
                amount,
                bool(badge_claimed),
            )

        await ctx.send(
            f"Set **{user}** to **{amount:,} Greg Skulls**. Community total unchanged."
        )

    @is_gm()
    @greg_gm.command(name="resetplayer", aliases=["clearplayer"])
    async def greg_gm_resetplayer(
        self,
        ctx,
        user: discord.User,
        revokebadge: str | None = None,
    ):
        revoke = self._parse_bool(revokebadge)
        if revoke is None:
            revoke = False

        removed_badge = False
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM greg_event_players
                WHERE user_id = $1
                """,
                user.id,
            )
            if revoke:
                removed_badge = await self._remove_greg_badge(user.id, conn=conn)

        suffix = ""
        if revoke:
            suffix = (
                f" Badge {'removed' if removed_badge else 'was not present'}."
            )
        await ctx.send(f"Reset Gregapocalypse progress for **{user}**.{suffix}")

    @is_gm()
    @greg_gm.command(name="resetall", aliases=["resetevent", "wipe"])
    async def greg_gm_resetall(self, ctx, revokebadge: str | None = None):
        revoke = self._parse_bool(revokebadge)
        if revoke is None:
            revoke = False

        removed_badges = 0
        async with self.bot.pool.acquire() as conn:
            user_ids = []
            if revoke:
                rows = await conn.fetch(
                    """
                    SELECT user_id
                    FROM greg_event_players
                    WHERE badge_claimed = TRUE
                    """
                )
                user_ids = [int(row["user_id"]) for row in rows]

            await conn.execute("DELETE FROM greg_event_players")
            await conn.execute(
                """
                UPDATE greg_event_global
                SET total_skulls = 0,
                    death_toll = 0,
                    outbreak_tier = 1,
                    boss_unlocked = FALSE,
                    updated_at = NOW()
                WHERE id = 1
                """
            )

            if revoke:
                for user_id in user_ids:
                    if await self._remove_greg_badge(user_id, conn=conn):
                        removed_badges += 1

        await self._sync_finale_event_flag(boss_unlocked=False)

        message = "Gregapocalypse progress has been fully reset."
        if revoke:
            message += f" Removed **{removed_badges}** Greg badges."
        await ctx.send(message)


async def setup(bot):
    await bot.add_cog(Greg(bot))
