"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2023-2024 Lunar (PrototypeX37)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import asyncio
from copy import copy
from decimal import Decimal

import discord

from discord.ext import commands

from classes.ascension import (
    ASCENSION_MANTLES,
    ASCENSION_MANTLE_ORDER,
    ASCENSION_TABLE_NAME,
    ASCENSION_UNLOCK_LEVEL,
    get_ascension_mantle,
)
from classes.classes import (
    ALL_CLASSES_TYPES,
    Mage,
    Paragon,
    Raider,
    Ranger,
    Ritualist,
    Thief,
    Warrior,
    Paladin,
    Reaper,
    SantasHelper,
    Tank,
)
from classes.classes import from_string as class_from_string
from classes.classes import get_class_evolves, get_first_evolution, get_name
from classes.converters import ImageFormat, ImageUrl
from cogs.shard_communication import next_day_cooldown
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import misc as rpgtools
from utils import random
from utils.checks import has_char, has_money, is_class, update_pet, user_is_patron, is_gm
from utils.i18n import _, locale_doc


class Classes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._ascension_tables_ready = False
        self._ascension_table_lock = asyncio.Lock()
        self.bot.loop.create_task(self._warm_ascension_tables())

    @staticmethod
    def _classes_include_ranger(class_names) -> bool:
        classes = [class_from_string(name) for name in class_names]
        return any(class_ and class_.in_class_line(Ranger) for class_ in classes)

    async def _warm_ascension_tables(self) -> None:
        try:
            await self._ensure_ascension_tables()
        except Exception:
            pass

    async def _ensure_ascension_tables(self) -> None:
        if self._ascension_tables_ready:
            return
        async with self._ascension_table_lock:
            if self._ascension_tables_ready:
                return
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {ASCENSION_TABLE_NAME} (
                        user_id bigint PRIMARY KEY,
                        mantle text NOT NULL,
                        enabled boolean NOT NULL DEFAULT true,
                        chosen_at timestamp with time zone NOT NULL DEFAULT now()
                    );
                    """
                )
                await conn.execute(
                    f"""
                    ALTER TABLE {ASCENSION_TABLE_NAME}
                    ADD COLUMN IF NOT EXISTS enabled boolean NOT NULL DEFAULT true;
                    """
                )
                await conn.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {ASCENSION_TABLE_NAME}_mantle_idx
                    ON {ASCENSION_TABLE_NAME} (mantle);
                    """
                )
            self._ascension_tables_ready = True

    async def _fetch_ascension_record(self, user_id: int):
        await self._ensure_ascension_tables()
        async with self.bot.pool.acquire() as conn:
            return await conn.fetchrow(
                f'SELECT mantle, enabled FROM {ASCENSION_TABLE_NAME} WHERE user_id = $1;',
                user_id,
            )

    async def _fetch_ascension_choice(self, user_id: int) -> str | None:
        record = await self._fetch_ascension_record(user_id)
        return None if record is None else record["mantle"]

    def _build_ascension_embed(self, mantle_key: str, *, enabled: bool = True) -> discord.Embed:
        mantle = ASCENSION_MANTLES[mantle_key]
        embed = discord.Embed(
            title=f"{mantle.title} of {mantle.god}",
            description=mantle.lore,
            color=mantle.color,
        )
        embed.add_field(
            name=mantle.signature_name,
            value=mantle.signature_summary,
            inline=False,
        )
        embed.add_field(
            name="Battle Traits",
            value="\n".join(f"- {line}" for line in mantle.passive_lines),
            inline=False,
        )
        embed.add_field(
            name="State",
            value="Active" if enabled else "Dormant",
            inline=False,
        )
        embed.set_footer(
            text="Ascension Mantles are permanent level-100 choices. Use ascension on/off to toggle."
        )
        return embed

    @has_char()
    @commands.command(
        name="ascension",
        aliases=["ascend", "mantle"],
        brief=_("Choose your level-100 ascension mantle"),
    )
    @locale_doc
    async def ascension(self, ctx, state: str = None):
        _(
            """Choose your level-100 ascension mantle.

            At level 100, you may bind yourself to one Ascension Mantle:
            Thronekeeper, Grave Sovereign, or Cyclebreaker.

            This choice is permanent and grants powerful automated battle effects.
            Use `{prefix}ascension on` or `{prefix}ascension off` to toggle it later."""
        )
        await self._ensure_ascension_tables()

        record = await self._fetch_ascension_record(ctx.author.id)
        normalized_state = None if state is None else state.strip().lower()

        if normalized_state in {"on", "off"}:
            if record is None:
                return await ctx.send(_("You have not claimed an Ascension Mantle yet."))
            desired_state = normalized_state == "on"
            if bool(record["enabled"]) == desired_state:
                return await ctx.send(
                    _(
                        "Your ascension mantle is already **{state}**."
                    ).format(state="active" if desired_state else "dormant")
                )
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    f'UPDATE {ASCENSION_TABLE_NAME} SET enabled = $1 WHERE user_id = $2;',
                    desired_state,
                    ctx.author.id,
                )
            return await ctx.send(
                _(
                    "Your ascension mantle is now **{state}**."
                ).format(state="active" if desired_state else "dormant")
            )

        if normalized_state not in {None, "status"}:
            return await ctx.send(_("Use `{prefix}ascension on` or `{prefix}ascension off`.").format(prefix=ctx.clean_prefix))

        existing_choice = None if record is None else record["mantle"]
        enabled = True if record is None else bool(record["enabled"])
        if existing_choice is not None:
            mantle = get_ascension_mantle(existing_choice)
            if mantle is None:
                return await ctx.send(_("Your ascension record is invalid. Contact a GM."))
            embed = self._build_ascension_embed(mantle.key, enabled=enabled)
            embed.set_footer(text=f"Your ascension mantle is locked in. Current state: {'Active' if enabled else 'Dormant'}.")
            return await ctx.send(embed=embed)

        level = int(rpgtools.xptolevel(ctx.character_data["xp"]))
        if level < ASCENSION_UNLOCK_LEVEL:
            return await ctx.send(
                _(
                    "You must reach level **{level}** before you can claim an Ascension Mantle."
                ).format(level=ASCENSION_UNLOCK_LEVEL)
            )

        entries = [self._build_ascension_embed(key) for key in ASCENSION_MANTLE_ORDER]
        index = await self.bot.paginator.ChoosePaginator(
            extras=entries,
            placeholder=_("Choose your ascension mantle"),
            choices=[ASCENSION_MANTLES[key].title for key in ASCENSION_MANTLE_ORDER],
            return_index=True,
        ).paginate(ctx)
        chosen_key = ASCENSION_MANTLE_ORDER[index]
        chosen_mantle = ASCENSION_MANTLES[chosen_key]

        if not await ctx.confirm(
            _(
                "Bind yourself to **{mantle}**? This choice is permanent."
            ).format(mantle=chosen_mantle.title)
        ):
            return await ctx.send(_("Ascension cancelled."))

        async with self.bot.pool.acquire() as conn:
            inserted = await conn.fetchval(
                f"""
                INSERT INTO {ASCENSION_TABLE_NAME} (user_id, mantle, enabled)
                VALUES ($1, $2, true)
                ON CONFLICT (user_id) DO NOTHING
                RETURNING mantle;
                """,
                ctx.author.id,
                chosen_key,
            )

        if inserted is None:
            current_choice = await self._fetch_ascension_choice(ctx.author.id)
            mantle = get_ascension_mantle(current_choice)
            if mantle is None:
                return await ctx.send(_("Your ascension choice was not changed."))
            return await ctx.send(
                _(
                    "Your ascension is already fixed as **{mantle}**."
                ).format(mantle=mantle.title)
            )

        await ctx.send(
            _(
                "The throne answers. You are now bound to **{mantle}**. Use"
                " `{prefix}ascension off` to suppress its powers, or"
                " `{prefix}ascension on` to awaken them again."
            ).format(mantle=chosen_mantle.title, prefix=ctx.clean_prefix)
        )

    @has_char()
    @user_cooldown(86400)
    @commands.command(name="class", brief=_("Choose or change your class(es)"))
    @locale_doc
    async def _class(self, ctx):
        _(
            """Change or select your primary or secondary class.

            - Warriors gain added defense (awaiting update)
            - Thieves gain access to `{prefix}steal`
            - Mages gain added damage and build arcane charge in battle, gaining shields until they unleash a fireball.
            - Rangers gain access to a pet which can hunt for gear items
            - Raiders build Raid Mark in battle; every third hit detonates the mark for bonus damage.
            - Paladins can bless a user to gain additional XP in adventures and build Faith in battle to unleash Divine Smite with Holy Shield.
            - Reapers have a change to cheat death and survive a fatal hit in raid battles. (Seasonal)
            - Santas Helper can gift users a present and have a life steal effect in raid battles (Seasonal)
            - Ritualists gain additional favor from sacrificing items, are twice as likely to receive loot from adventures, and weave Doom Sigils in battle
            - Paragons gain added damage *and* defense and use Adaptive Mastery in battle; the class is only available to donators

            The second class unlocks at level 12. Selecting a class the first time is free (No Class -> Class), but changing it later will cost $5,000 (Class -> another Class)

            (This command has a cooldown of 24 hours)"""
        )
        if rpgtools.xptolevel(ctx.character_data["xp"]) >= 12:
            val = await self.bot.paginator.Choose(
                title=_("Select class to change"),
                entries=[_("Primary Class"), _("Secondary Class")],
                return_index=True,
            ).paginate(ctx)
        else:
            val = 0
        embeds = [
            #discord.Embed(
                #title=_("Warrior"),
                #description=_(
                #    "The Warrior class. Charge into battle with additional defense!\n+1"
               #     " defense per evolution."
              #  ),
            #    color=self.bot.config.game.primary_colour,
           # ),
            discord.Embed(
                title=_("Paladin"),
                description=_(
                    # xgettext: no-python-format
                    "The Paladin is a devout warrior, wielding a Hammer and dedicated to upholding justice and safeguarding the innocent. "
                    "With an unwavering commitment to righteousness, they possess the unique ability to bestow blessings upon their allies, "
                    "granting them a temporary boost in XP gain. In battle, successful hits build Faith; every third hit unleashes "
                    "Divine Smite and grants Holy Shield. (unlocks `$bless`)"
                ).format(prefix=ctx.clean_prefix),
                color=self.bot.config.game.primary_colour
            ),
            discord.Embed(
                title=_("Thief"),
                description=_(
                    # xgettext: no-python-format
                    "The sneaky money stealer...\nGet access to `{prefix}steal` to"
                    " steal 10% of a random player's money, if successful.\n+8% success"
                    " chance per evolution."
                ).format(prefix=ctx.clean_prefix),
                color=self.bot.config.game.primary_colour,
            ),
            discord.Embed(
                title=_("Mage"),
                description=_(
                    "Utilise powerful magic for stronger attacks.\n+1 damage per"
                    " evolution. Normal battle hits build arcane charge and Arcane Shield"
                    " until a fireball is unleashed for a massive damage boost."
                ),
                color=self.bot.config.game.primary_colour,
            ),
            discord.Embed(
                title=_("Ranger"),
                description=_(
                    "Steeped in the mysteries of the wilderness, Rangers are adept trackers and loyal companions to their pets.\n"
                    "They excel at uncovering rare resources and preparing for impending threats.\n"
                    "Unlocks `{prefix}scout` to survey upcoming challenges to adjust your PVE engagements for strategic advantages. (1-4 rerolls)\n"
                    "You also have increased chances of finding eggs! (Up to 25% bonus)"
                ).format(prefix=ctx.clean_prefix),
                colour=self.bot.config.game.primary_colour,
            ),
            discord.Embed(
                title=_("Raider"),
                description=_(
                    "⚔️ **Raider**\n"
                    "A fearless warrior forged in the heat of battle against Ragnarok. Raiders lead the charge with unmatched bravery and strategic prowess.\n\n"
                    "**Battle Trait:**\n"
                    "- Successful hits place **Raid Mark** on the target.\n"
                    "- Every third mark detonates for bonus damage that scales with your attack and the target's vitality.\n"
                    "- Best used in longer boss fights where you can stay on one target."
                ),
                colour=self.bot.config.game.primary_colour,
            ),

            discord.Embed(
                title=_("Ritualist"),
                description=_(
                    "A seer, a sacrificer and a follower.\nThe Ritualist devotes their"
                    " life to the god they follow. For every evolution, their"
                    " sacrifices are 5% more effective. They have twice the chance to"
                    " get loot from adventures.\n\nIn battle, Ritualists weave **Doom"
                    " Sigils** onto enemies. When the sigils align, they erupt in a"
                    " curse burst, cling for follow-up Doom Echo strikes, and grant"
                    " **Favor Ward** when a doomed foe falls."
                ),
                colour=self.bot.config.game.primary_colour,
            ),
            discord.Embed(
                title=_("Paragon"),
                description=_(
                    "Absorb the appreciation of the devs into your soul to power"
                    " up.\n+1 damage and defense per evolution.\n\nIn battle,"
                    " **Adaptive Mastery** studies the opponent and answers with"
                    " extra damage against armored foes, barriers against dangerous"
                    " attackers, or a balanced mix against even matchups."
                ),
                color=self.bot.config.game.primary_colour,
            ),
            discord.Embed(
                title=_("Tank"),
                description=_(
                    "In the heart of the battlefield stands the Tank, the team's unwavering protector. "
                    "Wielding a formidable shield, the Tank can raise a protective barrier that absorbs incoming damage, significantly enhancing their armor and safeguarding allies.\n\n"
                    "**Enhancements per Evolution:**\n"
                    "• **+10 Shield Proficiency** – Mastery over shields increases armor effectiveness, allowing you to absorb more damage.\n"
                    "• **+5% Health** – Greater resilience ensures you can withstand prolonged battles. - Evolves\n"
                    "• **+5% Damage Reflection** – Your shield not only protects but also retaliates, reflecting a portion of the damage back to attackers. - Evolves\n"
                    "• **60% Target Priority** – In Ice Dragon Challenge, your defensive prowess draws more attention, making you more likely to be targeted.\n\n"
                    "🔒 *Requires a shield to function.*"
                ).format(prefix=ctx.clean_prefix),
                colour=self.bot.config.game.primary_colour,
            )

        ]
        choices = [Tank, Paladin, Thief, Mage, Ranger, Raider, Ritualist, Paragon]
        async with self.bot.pool.acquire() as conn:
            profile_data = await conn.fetchrow(
                'SELECT spookyclass, chrissy2023, easter2025, tier FROM profile WHERE "user"=$1;', ctx.author.id
            )

        if profile_data:
            # Check if they have unlocked the Reaper class or if their tier is 4
            if profile_data['spookyclass'] or profile_data['tier'] == 4:
                embeds.append(
                    discord.Embed(
                        title=_("Reaper"),
                        description=_(
                            "Embrace the grim power of the Reaper, absorbing the souls of the departed to grow stronger.\n\n"
                            "unlocks `Undying Loyalty` (cheat death in raid & raid battles) ability"
                        ),
                        color=self.bot.config.game.primary_colour,
                    )
                )
                choices.append(Reaper)

            # Check if they have unlocked the SantasHelper class or if their tier is 4
            if profile_data['chrissy2023'] or profile_data['tier'] == 4:
                embeds.append(
                    discord.Embed(
                        title=_("SantasHelper"),
                        description=_(
                            "Spread joy and aid allies with a festive touch. Evolve into a formidable Yuletide Guardian, "
                            "safeguarding the holiday spirit.\n\n"
                            "Unlocks `$gift` - Once per 6 hours, gift a player a random crate (Increased changes of higher rarities)\n\n"
                            "Unlocks `Peppermint Vitality Drain` - Infuse your weapon with the essence of enchanted "
                            "peppermints, allowing your attacks to steal a portion of the enemy's life force. Each "
                            "successful strike replenishes your health, providing sustain during battles."
                        ),
                        color=self.bot.config.game.primary_colour,
                    )
                )
                choices.append(SantasHelper)

            #if profile_data['easter2025']: # or profile_data['tier'] == 4:
                #embeds.append(
                    #discord.Embed(
                        #title=_("Egg Guardian"),
                        #description=_(
                            #"Protector of spring's sacred eggs, wielding the magic of renewal to weaken foes with elemental afflictions.\n\n"
                            #"Unlocks `Vernal Elemental Burden` - Your weapon's element applies debilitating effects:\n"
                            #"• 🔥 **Fire**: Burns enemies over time\n"
                            #"• 💧 **Water**: Slows movement\n"
                            #"• 🌱 **Earth**: Reduces armor\n"
                            #"• ⚡ **Lightning**: Chance to stun\n"
                            #"• ✨ **Light**: Increases damage taken\n"
                            #"• 🌑 **Shadow**: Lowers accuracy"
                        #),
                        #color=self.bot.config.game.primary_colour,
                    #)
                #)
                #choices.append(EggGuardian)
        classes = [class_from_string(c) for c in ctx.character_data["class"]]
        lines = [c.get_class_line() for c in classes if c]
        for line in lines:
            for e in embeds:
                if _(get_name(line)) == e.title:
                    embeds.remove(e)
            try:
                choices.remove(line)
            except ValueError:
                pass
        idx = await self.bot.paginator.ChoosePaginator(
            extras=embeds,
            placeholder=_("Choose a class"),
            choices=[line.__name__ for line in choices],
            return_index=True,
        ).paginate(ctx)
        profession = choices[idx]
        profession_ = get_first_evolution(profession).class_name()
        new_classes = copy(ctx.character_data["class"])
        new_classes[val] = profession_
        if not await ctx.confirm(
                _(
                    "You are about to select the `{profession}` class for yourself."
                    " {textaddon} Proceed?"
                ).format(
                    textaddon=_(
                        "This **costs nothing**, but changing it later will cost **$5000**."
                    )
                    if ctx.character_data["class"][val] == "No Class"
                    else _("This will cost **$5000**."),
                    profession=get_name(profession),
                )
        ):
            return await ctx.send(_("Class selection cancelled."))
        if ctx.character_data["class"][val] == "No Class":
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "class"=$1 WHERE "user"=$2;',
                    new_classes,
                    ctx.author.id,
                )
                if not self._classes_include_ranger(new_classes):
                    await conn.execute(
                        "UPDATE pet_daycares SET is_open = FALSE WHERE owner_user_id = $1;",
                        ctx.author.id,
                    )
                if profession == Ranger:
                    await conn.execute(
                        'INSERT INTO pets ("user") VALUES ($1);', ctx.author.id
                    )
            await ctx.send(
                _("Your new class is now `{profession}`.").format(
                    profession=_(get_name(profession))
                )
            )
        else:
            if not await self.bot.has_money(ctx.author.id, 5000):
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _("You're too poor for a class change, it costs **$5000**.")
                )

            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "class"=$1, "money"="money"-$2 WHERE'
                    ' "user"=$3;',
                    new_classes,
                    5000,
                    ctx.author.id,
                )
                if not self._classes_include_ranger(new_classes):
                    await conn.execute(
                        "UPDATE pet_daycares SET is_open = FALSE WHERE owner_user_id = $1;",
                        ctx.author.id,
                    )
                await conn.execute('DELETE FROM pets WHERE "user"=$1;', ctx.author.id)
                if profession == Ranger:
                    await conn.execute(
                        'INSERT INTO pets ("user") VALUES ($1);', ctx.author.id
                    )
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=2,
                    subject="class change",
                    data={"Gold": 5000},
                    conn=conn,
                )
            await ctx.send(
                _(
                    "You selected the class `{profession}`. **$5000** was taken off"
                    " your balance."
                ).format(profession=_(get_name(profession)))
            )

    @has_char()
    @commands.command(brief=_("View your class(es)"))
    @locale_doc
    async def myclass(self, ctx):
        _("""Show your class(es) and their added benefits, sent as images. (Not complete)""")
        if (classes := ctx.character_data["class"]) == ["No Class", "No Class"]:
            return await ctx.send("You haven't got a class yet.")
        for class_ in classes:
            if class_ != "No Class":
                try:
                    await ctx.send(
                        file=discord.File(
                            f"assets/classes/{class_.lower().replace(' ', '_')}.png"
                        )
                    )
                except FileNotFoundError:
                    await ctx.send(
                        _(
                            "The image for your class **{class_}** hasn't been added"
                            " yet."
                        ).format(class_=class_)
                    )

    @has_char()
    @commands.command(brief=_("Evolve your class(es)"))
    @locale_doc
    async def evolve(self, ctx):
        _(
            # xgettext: no-python-format
            """Evolve your class, bringing it to the next level and giving better class bonuses.

            You can evolve every 5 levels, i.e. at level 5, level 10, level 15, level 20, level 25 and finally level 30.

"""
        )
        level = rpgtools.xptolevel(ctx.character_data["xp"])
        if level < 5:
            return await ctx.send(_("Your level isn't high enough to evolve."))
        if level > 30:
            await ctx.send("New evolutions shortly (Expect them roughly end of feb)")
            level = 30
        newindex = int(level / 5)
        updated = 0
        new_classes = []
        for class_ in ctx.character_data["class"]:
            c = class_from_string(class_)
            if c:
                evolves = get_class_evolves(c.get_class_line())
                new_classes.append(evolves[newindex].class_name())
                updated += 1
            else:
                new_classes.append("No Class")
        if updated == 0:
            return await ctx.send(_("You haven't got a class yet."))
        if ctx.character_data["class"] == new_classes:
            return await ctx.send(_("Nothing to evolve."))
        await self.bot.pool.execute(
            'UPDATE profile SET "class"=$1 WHERE "user"=$2;', new_classes, ctx.author.id
        )
        await ctx.send(
            _("You are now a `{class1}` and a `{class2}`.").format(
                class1=new_classes[0], class2=new_classes[1]
            )
        )

    @commands.command(brief=_("Shows the evolution tree"))
    @locale_doc
    async def tree(self, ctx):
        _(
            """Shows the evolution tree for each class.
            This will only show the names, not the respective benefits."""
        )
        embeds = []
        for name, class_ in ALL_CLASSES_TYPES.items():
            evos = [
                f"Level {idx * 5}: {evo.class_name()}"
                for idx, evo in enumerate(get_class_evolves(class_))
            ]
            embed = discord.Embed(
                title=name,
                description="\n".join(evos),
                colour=self.bot.config.game.primary_colour,
            )
            embeds.append(embed)
        await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

    @is_class(Thief)
    @has_char()
    @commands.command(brief=_("Steal steel"))
    @locale_doc
    async def steel(self, ctx):
        _(
            # xgettext: no-python-format
            """Steel lmao"""
        )
        await ctx.send("Steel..? Sure here.. I guess: <:steel:1158572795022802964>")

    @is_class(Thief)
    @has_char()
    @user_cooldown(3600)
    @commands.command(brief=_("Steal money"))
    @locale_doc
    async def steal(self, ctx):
        _(
            # xgettext: no-python-format
            """Steal money from a random user.

            Your steal chance is increased by evolving your class and your alliance's thief buildings, if you have an alliance that owns a city.
            If you succeed in stealing, you will steal 10% of a random player's money (including money in their buy orders).

            You *cannot* choose your target, it is always a random player. If the bot can't find the player's name, it will be replaced with "a traveller passing by".
            The random player cannot be anyone with money less than $10, yourself, or one of the bot owners.

            Only thieves can use this command.
            (This command has a cooldown of 1 hour.)"""
        )

        try:
            # Calculate success chance based on class grade and buildings
            if buildings := await self.bot.get_city_buildings(ctx.character_data["guild"]):
                bonus = buildings["thief_building"] * 5
            else:
                bonus = 0
                
            grade = 0  # Initialize grade outside the loop
            for class_ in list(ctx.character_data["class"]):
                c = class_from_string(class_)
                if c and c.in_class_line(Thief):
                    grade = c.class_grade()
                    break  # Break out of the loop once a match is found

            success_chance = grade * 8 + 1 + bonus
            random_number = random.randint(1, 100)
            
            if random_number <= success_chance:
                async with self.bot.pool.acquire() as conn:
                    # Fetch all valid targets with wallet + buy orders money >= 10 in a single query
                    valid_targets = await conn.fetch(
                        """
                        WITH potential_targets AS (
                            SELECT 
                                p."user", 
                                p."money",
                                COALESCE((SELECT SUM(
                                    CASE WHEN active = TRUE THEN (quantity - quantity_filled) * price ELSE 0 END
                                ) FROM weapon_buy_orders WHERE user_id = p."user"), 0) AS weapon_money,
                                COALESCE((SELECT SUM(
                                    CASE WHEN active = TRUE THEN (quantity - quantity_filled) * price_each ELSE 0 END
                                ) FROM crate_buy_orders WHERE user_id = p."user"), 0) AS crate_money
                            FROM profile p
                            WHERE p."user" != $1 AND p."tier" = 0
                        )
                        SELECT 
                            "user", 
                            "money", 
                            weapon_money, 
                            crate_money,
                            "money" + weapon_money + crate_money AS total_money
                        FROM potential_targets
                        WHERE "money" + weapon_money + crate_money >= 10
                        """,
                        ctx.author.id
                    )
                    
                    # Filter out bot owners
                    valid_targets = [
                        target for target in valid_targets 
                        if target["user"] not in self.bot.owner_ids
                    ]
                    
                    if not valid_targets:
                        return await ctx.send(_("No suitable targets found with at least $10 total wealth."))
                    
                    # Select a random target
                    usr = random.choice(valid_targets)
                    total_money = usr["total_money"]
                    
                    # Calculate theft amount (10% of total wealth)
                    steal_amount = int(total_money * Decimal('0.1'))
                    
                    # How much we've actually stolen so far
                    stolen_so_far = 0
                    order_modifications = []
                    wallet_refunded_from_orders = 0
                    
                    # Start by taking from wallet
                    wallet_stolen = min(steal_amount, int(usr["money"]))
                    stolen_so_far += wallet_stolen
                    
                    # Take from wallet first
                    await conn.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                        wallet_stolen,
                        usr["user"],
                    )
                    
                    # If we need more, start modifying buy orders
                    remaining_to_steal = steal_amount - stolen_so_far
                    
                    if remaining_to_steal > 0:
                        # Get all active orders at once with a single query
                        weapon_orders = []
                        crate_orders = []
                        
                        if usr["weapon_money"] > 0:
                            weapon_orders = await conn.fetch(
                                """
                                SELECT 
                                    id, 
                                    weapon_type,
                                    price, 
                                    quantity, 
                                    quantity_filled
                                FROM weapon_buy_orders 
                                WHERE user_id = $1 AND active = TRUE
                                  AND quantity > quantity_filled
                                ORDER BY price ASC, created_at DESC;
                                """,
                                usr["user"]
                            )
                        
                        if usr["crate_money"] > 0 and remaining_to_steal > 0:
                            crate_orders = await conn.fetch(
                                """
                                SELECT 
                                    id, 
                                    crate_type,
                                    price_each, 
                                    quantity, 
                                    quantity_filled
                                FROM crate_buy_orders 
                                WHERE user_id = $1 AND active = TRUE
                                  AND quantity > quantity_filled
                                ORDER BY price_each ASC, created_at DESC;
                                """,
                                usr["user"]
                            )
                        
                        # Prepare batch updates
                        weapon_cancels = []
                        weapon_updates = []
                        crate_cancels = []
                        crate_updates = []
                        
                        # Process weapon orders first
                        for order in weapon_orders:
                            if remaining_to_steal <= 0:
                                break
                                
                            unit_price = int(order['price'])
                            unfilled_quantity = order['quantity'] - order['quantity_filled']
                            order_value = unfilled_quantity * unit_price
                            
                            if order_value <= 0:
                                continue
                                
                            # Reduce by as many units as needed; if one unit exceeds remaining,
                            # still take one and refund surplus back to victim wallet.
                            units_for_remaining = remaining_to_steal // unit_price
                            items_to_reduce = min(
                                unfilled_quantity,
                                max(1, int(units_for_remaining))
                            )
                            released_amount = items_to_reduce * unit_price
                            thief_take = min(released_amount, remaining_to_steal)
                            refund_amount = released_amount - thief_take
                            
                            # Update order
                            new_quantity = order['quantity'] - items_to_reduce
                            
                            # If reducing to zero or below filled amount, cancel the order
                            if new_quantity <= order['quantity_filled']:
                                weapon_cancels.append(order['id'])
                                order_modifications.append(f"Cancelled weapon order for {order['weapon_type']}")
                            else:
                                weapon_updates.append((new_quantity, order['id']))
                                order_modifications.append(f"Reduced weapon order for {order['weapon_type']}")
                            
                            stolen_so_far += thief_take
                            remaining_to_steal -= thief_take
                            wallet_refunded_from_orders += refund_amount
                        
                        # Process crate orders if still need more
                        for order in crate_orders:
                            if remaining_to_steal <= 0:
                                break
                                
                            unit_price = int(order['price_each'])
                            unfilled_quantity = order['quantity'] - order['quantity_filled']
                            order_value = unfilled_quantity * unit_price
                            
                            if order_value <= 0:
                                continue
                                
                            # Reduce by as many units as needed; if one unit exceeds remaining,
                            # still take one and refund surplus back to victim wallet.
                            units_for_remaining = remaining_to_steal // unit_price
                            items_to_reduce = min(
                                unfilled_quantity,
                                max(1, int(units_for_remaining))
                            )
                            released_amount = items_to_reduce * unit_price
                            thief_take = min(released_amount, remaining_to_steal)
                            refund_amount = released_amount - thief_take
                            
                            # Update order
                            new_quantity = order['quantity'] - items_to_reduce
                            
                            # If reducing to zero or below filled amount, cancel the order
                            if new_quantity <= order['quantity_filled']:
                                crate_cancels.append(order['id'])
                                order_modifications.append(f"Cancelled crate order for {order['crate_type']} crates")
                            else:
                                crate_updates.append((new_quantity, order['id']))
                                order_modifications.append(f"Reduced crate order for {order['crate_type']} crates")
                            
                            stolen_so_far += thief_take
                            remaining_to_steal -= thief_take
                            wallet_refunded_from_orders += refund_amount
                        
                        # Execute updates in batches
                        if weapon_cancels:
                            await conn.execute(
                                'UPDATE weapon_buy_orders SET active = FALSE WHERE id = ANY($1);',
                                weapon_cancels
                            )
                            
                        if weapon_updates:
                            await conn.executemany(
                                'UPDATE weapon_buy_orders SET quantity = $1 WHERE id = $2;',
                                weapon_updates
                            )
                            
                        if crate_cancels:
                            await conn.execute(
                                'UPDATE crate_buy_orders SET active = FALSE WHERE id = ANY($1);',
                                crate_cancels
                            )
                            
                        if crate_updates:
                            await conn.executemany(
                                'UPDATE crate_buy_orders SET quantity = $1 WHERE id = $2;',
                                crate_updates
                            )

                        if wallet_refunded_from_orders > 0:
                            await conn.execute(
                                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                wallet_refunded_from_orders,
                                usr["user"],
                            )
                    
                    # Give stolen money to thief
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        stolen_so_far,
                        ctx.author.id,
                    )
                    
                    # Prepare logs
                    log_data = {
                        "Gold": stolen_so_far,
                        "Total Money": total_money,
                        "From Wallet": wallet_stolen
                    }
                    if stolen_so_far > wallet_stolen:
                        log_data["From Buy Orders"] = stolen_so_far - wallet_stolen
                    if wallet_refunded_from_orders > 0:
                        log_data["Refunded To Victim Wallet"] = wallet_refunded_from_orders
                    
                    # Add order modifications to log if any
                    if order_modifications:
                        log_data["Order Modifications"] = ", ".join(order_modifications)
                    
                    await self.bot.log_transaction(
                        ctx,
                        from_=usr["user"],
                        to=ctx.author.id,
                        subject="steal",
                        data=log_data,
                        conn=conn,
                    )
                    
                    # Send notification to victim about buy order changes if any were modified
                    victim = await self.bot.get_user_global(usr["user"])
                    if victim and order_modifications:
                        try:
                            orders_msg = "\n- " + "\n- ".join(order_modifications)
                            await victim.send(
                                _("A thief stole **${amount}** from you! As part of the theft, the following buy orders were modified:{orders}").format(
                                    amount=stolen_so_far,
                                    orders=orders_msg
                                )
                            )
                        except discord.Forbidden:
                            pass
                
                # Get victim username
                user = await self.bot.get_user_global(usr["user"])
                username = f"**{user}**" if user else _("a traveller just passing by")
                
                # Simplified success message
                await ctx.send(
                    _("You stole **${stolen}** from {user}.").format(
                        stolen=stolen_so_far,
                        user=username
                    )
                )
            else:
                await ctx.send(_("Your attempt to steal money wasn't successful."))
        except Exception as e:
            await ctx.send(e)



async def setup(bot):
    await bot.add_cog(Classes(bot))
