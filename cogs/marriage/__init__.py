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
from datetime import datetime

import discord

from discord.ext import commands

from classes.converters import IntFromTo, MemberWithCharacter, UserWithCharacter
from cogs.help import chunks
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import misc as rpgtools
from utils import random
from utils.checks import has_char
from utils.i18n import _, locale_doc


class Marriage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        with open("assets/data/boynames.txt") as boy_names:
            self.boynames = boy_names.readlines()
        with open("assets/data/girlnames.txt") as girl_names:
            self.girlnames = girl_names.readlines()

    def get_max_kids(self, lovescore):
        max_, missing = divmod(lovescore, 250_000)
        return 10 + max_, 250_000 - missing

    @has_char()
    @commands.guild_only()
    @commands.command(aliases=["marry"], brief=_("Propose to a player"))
    @locale_doc
    async def propose(self, ctx, partner: MemberWithCharacter):
        _(
            """`<partner>` - A discord User with a character who is not yet married

            Propose to a player for marriage. Once they accept, you are married.

            When married, your partner will get bonuses from your adventures, you can have children, which can do different things (see `{prefix}help familyevent`) and increase your lovescore, which has an effect on the [adventure bonus](https://wiki.idlerpg.xyz/index.php?title=Family#Adventure_Bonus).
            If any of you has children, they will be brought together to one family.

            Only players who are not already married can use this command."""
        )
        if partner == ctx.author:
            return await ctx.send(
                _("You should have a better friend than only yourself.")
            )
        if ctx.character_data["marriage"] != 0 or ctx.user_data["marriage"] != 0:
            return await ctx.send(_("One of you is married."))
        msg = await ctx.send(
            embed=discord.Embed(
                title=_("{author} has proposed for a marriage!").format(
                    author=ctx.disp,
                ),
                description=_(
                    "{author} wants to marry you, {partner}! React with :heart: to"
                    " marry them!"
                ).format(author=ctx.author.mention, partner=partner.mention),
                colour=0xFF0000,
            )
            .set_image(url=ctx.author.display_avatar.url)
            .set_thumbnail(
                url="http://www.maasbach.com/wp-content/uploads/The-heart.png"
            )
        )
        await msg.add_reaction("\U00002764")

        def reactioncheck(reaction, user):
            return (
                str(reaction.emoji) == "\U00002764"
                and reaction.message.id == msg.id
                and user.id == partner.id
            )

        try:
            _reaction, _user = await self.bot.wait_for(
                "reaction_add", timeout=120.0, check=reactioncheck
            )
        except asyncio.TimeoutError:
            return await ctx.send(_("They didn't want to marry."))
        async with self.bot.pool.acquire() as conn:
            check1 = await conn.fetchval(
                'SELECT marriage FROM profile WHERE "user"=$1;', ctx.author.id
            )
            check2 = await conn.fetchval(
                'SELECT marriage FROM profile WHERE "user"=$1;', partner.id
            )
            if check1 or check2:
                return await ctx.send(
                    _(
                        "Either you or your lovee married in the meantime... :broken_heart:"
                    )
                )
            async with conn.transaction():
                await conn.execute(
                    'UPDATE profile SET "marriage"=$1 WHERE "user"=$2;',
                    partner.id,
                    ctx.author.id,
                )
                await conn.execute(
                    'UPDATE profile SET "marriage"=$1 WHERE "user"=$2;',
                    ctx.author.id,
                    partner.id,
                )
                await conn.execute(
                    'UPDATE children SET "father"=$1 WHERE "father"=0 AND "mother"=$2;',
                    partner.id,
                    ctx.author.id,
                )
                await conn.execute(
                    'UPDATE children SET "father"=$1 WHERE "father"=0 AND "mother"=$2;',
                    ctx.author.id,
                    partner.id,
                )
        # we give familyevent cooldown to the new partner to avoid exploitation
        await self.bot.set_cooldown(partner.id, 1800, "familyevent")
        await ctx.send(
            _("Aww! :heart: {author} and {partner} are now married!").format(
                author=ctx.author.mention, partner=partner.mention
            )
        )

    @has_char()
    @commands.command(brief=_("Break up with your partner"))
    @locale_doc
    async def divorce(self, ctx):
        _(
            """Divorce your partner, effectively un-marrying them.

            When divorcing, any kids you have will be split between you and your partner. Each partner will get the children born with their `{prefix}child` commands.
            You can marry another person right away, if you so choose. Divorcing has no negative consequences on gameplay.

            Both players' lovescore will be reset.

            Only married players can use this command."""
        )
        if not ctx.character_data["marriage"]:
            return await ctx.send(_("You are not married yet."))
        if not await ctx.confirm(
            _(
                "Are you sure you want to divorce your partner? Some of your children"
                " may be given to your partner and your lovescore will be reset."
            )
        ):
            return await ctx.send(
                _("Cancelled the divorce. I guess the marriage is safe for now?")
            )
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "marriage"=0, "lovescore"=0 WHERE "user"=$1;',
                ctx.author.id,
            )
            await conn.execute(
                'UPDATE profile SET "marriage"=0, "lovescore"=0 WHERE "user"=$1;',
                ctx.character_data["marriage"],
            )
            await conn.execute(
                'UPDATE children SET "father"=0 WHERE "mother"=$1;', ctx.author.id
            )
            await conn.execute(
                'UPDATE children SET "father"=0 WHERE "mother"=$1;',
                ctx.character_data["marriage"],
            )
        await ctx.send(_("You are now divorced."))

    @has_char()
    @commands.command(brief=_("Show your partner"))
    @locale_doc
    async def relationship(self, ctx):
        _(
            """Show your partner's Discord Tag. This works fine across server.

            Only married players can use this command."""
        )
        if not ctx.character_data["marriage"]:
            return await ctx.send(_("You are not married yet."))
        partner = await rpgtools.lookup(self.bot, ctx.character_data["marriage"])
        await ctx.send(
            _("You are currently married to **{partner}**.").format(partner=partner)
        )

    @has_char()
    @commands.command(brief=_("Show a player's lovescore"))
    @locale_doc
    async def lovescore(self, ctx, user: UserWithCharacter = None):
        _(
            """`[user]` - The user whose lovescore to show; defaults to oneself

            Show the lovescore a player has. Lovescore can be increased by their partner spoiling them or going on dates.

            Lovescore affects the [adventure bonus](https://wiki.idlerpg.xyz/index.php?title=Family#Adventure_Bonus) and the amount of children you can have."""
        )
        user = user or ctx.author
        data = ctx.character_data if user == ctx.author else ctx.user_data
        if data["marriage"]:
            partner = await rpgtools.lookup(self.bot, data["marriage"])
        else:
            partner = _("noone")
        await ctx.send(
            _(
                "{user}'s overall love score is **{score}**. {user} is married to"
                " **{partner}**."
            ).format(user=user.name, score=data["lovescore"], partner=partner)
        )

    @has_char()
    @commands.command(brief=_("Increase your partner's lovescore"))
    @locale_doc
    async def spoil(self, ctx, item: IntFromTo(1, 40) = None):
        _(
            """`[item]` - The item to buy, a whole number from 1 to 40; if not given, displays the list of items

            Buy something for your partner to increase *their* lovescore. To increase your own lovescore, your partner should spoil you.

            Please note that these items are not usable and do not have an effect on gameplay, beside increasing lovescore.

            Only players who are married can use this command."""
        )
        lovescore_multiplier = 1

        query = '''
            SELECT "user", "tier"
            FROM profile
            WHERE "user" = $1 AND "tier" >= $2;
        '''

        result = await self.bot.pool.fetchrow(query, ctx.author.id, 3)

        if result:
            lovescore_multiplier = 1
        items = [
            (_("Dog :dog2:"), 50),
            (_("Cat :cat2:"), 50),
            (_("Cow :cow2:"), 75),
            (_("Penguin :penguin:"), 100),
            (_("Unicorn :unicorn:"), 1000),
            (_("Potato :potato:"), 1),
            (_("Sweet potato :sweet_potato:"), 2),
            (_("Peach :peach:"), 5),
            (_("Ice Cream :ice_cream:"), 10),
            (_("Bento Box :bento:"), 50),
            (_("Movie Night :ticket:"), 75),
            (_("Video Game Night :video_game:"), 10),
            (_("Camping Night :fishing_pole_and_fish:"), 15),
            (_("Couple Competition :trophy:"), 30),
            (_("Concert Night :musical_keyboard:"), 100),
            (_("Bicycle :bike:"), 100),
            (_("Motorcycle :motorcycle:"), 250),
            (_("Car :red_car:"), 300),
            (_("Private Jet :airplane:"), 1000),
            (_("Space Rocket :rocket:"), 10000),
            (_("Credit Card :credit_card:"), 20),
            (_("Watch :watch:"), 100),
            (_("Phone :iphone:"), 100),
            (_("Bed :bed:"), 500),
            (_("Home films :projector:"), 750),
            (_("Satchel :school_satchel:"), 25),
            (_("Purse :purse:"), 30),
            (_("Shoes :athletic_shoe:"), 150),
            (_("Casual Attire :shirt:"), 200),
            (_("Ring :ring:"), 1000),
            (_("Balloon :balloon:"), 10),
            (_("Flower Bouquet :bouquet:"), 25),
            (_("Expensive Chocolates :chocolate_bar:"), 40),
            (_("Declaration of Love :love_letter:"), 50),
            (_("Key to Heart :key2:"), 100),
            (_("Ancient Vase :amphora:"), 15000),
            (_("House :house:"), 25000),
            (_("Super Computer :computer:"), 50000),
            (_("Precious Gemstone Collection :gem:"), 75000),
            (_("Planet :earth_americas:"), 1_000_000),
        ]
        text = _("Price")
        items_str = "\n".join(
            [
                f"{idx + 1}.) {item} ... {text}: **${price}**"
                for idx, (item, price) in enumerate(items)
            ]
        )
        if not item:
            text = _(
                "To buy one of these items for your partner, use `{prefix}spoil shopid`"
            ).format(prefix=ctx.clean_prefix)
            return await ctx.send(f"{items_str}\n\n{text}")
        item = items[item - 1]
        if ctx.character_data["money"] < item[1]:
            return await ctx.send(_("You are too poor to buy this."))
        if not ctx.character_data["marriage"]:
            return await ctx.send(_("You're not married yet."))
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "lovescore"="lovescore"+$1 WHERE "user"=$2;',
                round(item[1] * lovescore_multiplier),
                ctx.character_data["marriage"],
            )
            await conn.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                item[1],
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="spoil",
                data={"Gold": item[1]},
                conn=conn,
            )
        await ctx.send(
            _(
                "You bought a **{item}** for your partner and increased their love"
                " score by **{points}** points!"
            ).format(item=item[0], points=round(item[1] * lovescore_multiplier))
        )
        user = await self.bot.get_user_global(ctx.character_data["marriage"])
        if not user:
            return await ctx.send(
                _("Failed to DM your spouse, could not find their Discord account")
            )
        await user.send(
            "**{author}** bought you a **{item}** and increased your love score by"
            " **{points}** points!".format(
                author=ctx.author, item=item[0], points=item[1]
            )
        )

    @has_char()
    @commands.command(brief=_("Take your partner on a date"))
    @locale_doc
    @user_cooldown(43200)
    async def date(self, ctx):
        _(
            """Take your partner on a date to increase *their* lovescore. To increase your own lovescore, your partner should go on a date with you.

            The lovescore gained from dates can range from 10 to 150 in steps of 10.

            Only players who are married can use this command.
            (This command has a cooldown of 12 hours.)"""
        )

        num = random.randint(50, 600) * 10
        marriage = ctx.character_data["marriage"]
        if not marriage:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You are not married yet."))
        await self.bot.pool.execute(
            'UPDATE profile SET "lovescore"="lovescore"+$1 WHERE "user"=$2;',
            num,
            marriage,
        )

        partner = await self.bot.get_user_global(marriage)
        scenario = random.choice(
            [
                _("You and {partner} went on a nice candlelit dinner."),
                _("You and {partner} had stargazed all night."),
                _("You and {partner} went to a circus that was in town."),
                _("You and {partner} went out to see a romantic movie."),
                _("You and {partner} went out to get ice cream."),
                _("You and {partner} had an anime marathon."),
                _("You and {partner} went for a spontaneous hiking trip."),
                _("You and {partner} decided to visit Paris."),
                _("You and {partner} went ice skating together."),
            ]
        ).format(partner=(partner.mention if partner else _("Unknown User")))
        text = _("This increased their lovescore by {num}").format(num=num)
        await ctx.send(f"{scenario} {text}")

    async def get_random_name(self, gender, avoid):
        if gender == "f":
            data = self.girlnames
        else:
            data = self.boynames
        name = random.choice(data).strip("\n")
        while name in avoid:
            name = random.choice(data)  # avoid duplicate names
        return name

    async def lovescore_up(self, ctx, marriage, max_, missing, toomany):
        additional = (
            ""
            if not toomany
            else _(
                "You already have {max_} children. You can increase this limit"
                " by increasing your lovescores to get {amount} more."
            ).format(max_=max_, amount=f"{missing:,}")
        )
        ls = random.randint(10, 50)
        await self.bot.pool.execute(
            'UPDATE profile SET "lovescore"="lovescore"+$1 WHERE "user"=$2 OR'
            ' "user"=$3;',
            ls,
            ctx.author.id,
            marriage,
        )
        return await ctx.send(
            _(
                "You had a lovely night and gained {ls} lovescore. 😏\n\n{additional}".format(
                    ls=ls, additional=additional
                )
            )
        )

    @has_char()
    @commands.guild_only()
    @user_cooldown(3600)
    @commands.command(
        aliases=["fuck", "sex", "breed"], brief=_("Have a child with your partner")
    )
    @locale_doc
    async def child(self, ctx):
        _(
            # xgettext: no-python-format
            """Have a child with your partner.

            Children on their own don't do much, but `{prefix}familyevent` can effect your money and crates.
            To have a child, your partner has to be on the server to accept the checkbox.

            There is a 50% chance that you will have a child, and a 50% chance to just *have fun* (if you know what I'm saying) and gain between 10 and 50 lovescore.
            When you have a child, there is a 50% chance for it to be a boy and a 50% chance to be a girl.

            Your partner and you can enter a name for your child once the bot prompts you to. (Do not include `{prefix}`)
            If you fail to choose a name in time, the bot will choose one for you from about 500 pre-picked ones.

            For identification purposes, you cannot have two children with the same name in your family, so make sure to pick a unique one.

            Only players who are married can use this command.
            (This command has a cooldown of 1 hour.)"""
        )
        marriage = ctx.character_data["marriage"]
        if not marriage:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("Can't produce a child alone, can you?"))
        async with self.bot.pool.acquire() as conn:
            names = await conn.fetch(
                'SELECT name FROM children WHERE "mother"=$1 OR "father"=$1;',
                ctx.author.id,
            )
            spouse = await conn.fetchval(
                'SELECT lovescore FROM profile WHERE "user"=$1;', marriage
            )
        max_, missing = self.get_max_kids(ctx.character_data["lovescore"] + spouse)
        names = [name["name"] for name in names]
        user = await self.bot.get_user_global(marriage)
        if not await ctx.confirm(
            _("{user}, do you want to make a child with {author}?").format(
                user=user.mention, author=ctx.author.mention
            ),
            user=user,
        ):
            return await ctx.send(_("O.o not in the mood today?"))

        if len(names) >= max_:
            return await self.lovescore_up(ctx, marriage, max_, missing, True)

        if random.choice([True, False]):
            return await self.lovescore_up(ctx, marriage, max_, missing, False)
        gender = random.choice(["m", "f"])
        if gender == "m":
            await ctx.send(
                _(
                    "It's a boy! Your night of love was successful! Please enter a name"
                    " for your child."
                )
            )
        elif gender == "f":
            await ctx.send(
                _(
                    "It's a girl! Your night of love was successful! Please enter a"
                    " name for your child."
                )
            )

        def check(msg):
            return (
                msg.author.id in [ctx.author.id, marriage]
                and 1 <= len(msg.content) <= 20
                and msg.channel.id == ctx.channel.id
            )

        name = None
        while not name:
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30)
                name = msg.content.replace("@", "@\u200b")
            except asyncio.TimeoutError:
                name = await self.get_random_name(gender, names)
                await ctx.send(
                    _("You didn't enter a name, so we chose {name} for you.").format(
                        name=name
                    )
                )
                break
            if name in names:
                await ctx.send(
                    _(
                        "One of your children already has that name, please choose"
                        " another one."
                    )
                )
                name = None
        now = datetime.now()

        # Format the date as dd/mm/yyyy
        formatted_date = now.strftime("%d/%m/%Y")
        await self.bot.pool.execute(
            'INSERT INTO children ("mother", "father", "name", "age", "gender", "birth")'
            " VALUES ($1, $2, $3, $4, $5, $6);",
            ctx.author.id,
            marriage,
            name,
            0,
            gender,
            formatted_date,
        )
        await ctx.send(_("{name} was born.").format(name=name))

    @has_char()
    @commands.command(brief=_("View your children"))
    @locale_doc
    async def family(self, ctx):
        _("""View your children. This will display their name, age and gender.""")
        try:
            marriage = ctx.character_data["marriage"]
            children = await self.bot.pool.fetch(
                'SELECT * FROM children WHERE ("mother"=$1 AND "father"=$2) OR ("father"=$1'
                ' AND "mother"=$2);',
                ctx.author.id,
                marriage,
            )

            additional = (
                _("{amount} children").format(amount=len(children))
                if len(children) != 1
                else _("one child")
            )
            em = discord.Embed(
                title=_("Your family, {additional}.").format(additional=additional),
                description=_("{author}'s family").format(author=ctx.author.mention)
                if not marriage
                else _("Family of {author} and <@{marriage}>").format(
                    author=ctx.author.mention, marriage=marriage
                ),
            )
            if not children:
                em.add_field(
                    name=_("No children yet"),
                    value=_("Use `{prefix}child` to make one!").format(
                        prefix=ctx.clean_prefix
                    )
                    if marriage
                    else _(
                        "Get yourself a partner and use `{prefix}child` to make one!"
                    ).format(prefix=ctx.clean_prefix),
                )
            if len(children) <= 5:
                for child in children:
                    em.add_field(
                        name=child["name"],
                        value=_("Gender: {gender}, Age: {age}, Born: {born}").format(
                            gender=child["gender"], age=child["age"], born=child["birth"]
                        ),
                        inline=False,
                    )
                em.set_thumbnail(url=ctx.author.display_avatar.url)
                await ctx.send(embed=em)
            else:
                embeds = []
                children_lists = list(chunks(children, 9))
                for small_list in children_lists:
                    em = discord.Embed(
                        title=_("Your family, {additional}.").format(additional=additional),
                        description=_("{author}'s family").format(author=ctx.author.mention)
                        if not marriage
                        else _("Family of {author} and <@{marriage}>").format(
                            author=ctx.author.mention, marriage=marriage
                        ),
                    )
                    for child in small_list:
                        em.add_field(
                            name=child["name"],
                            value=_("Gender: {gender}, Age: {age}, Born: {born}").format(
                                gender=child["gender"], age=child["age"], born=child["birth"]
                            ),
                            inline=True,
                        )
                    em.set_footer(
                        text=_("Page {cur} of {max}").format(
                            cur=children_lists.index(small_list) + 1,
                            max=len(children_lists),
                        )
                    )
                    embeds.append(em)
                await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    @has_char()
    @user_cooldown(1800)
    @commands.command(aliases=["fe"], brief=_("Events happening to your family"))
    @locale_doc
    async def familyevent(self, ctx):
        _(
            """Allow your children to do something, this includes a multitude of events.

            Every time you or your partner uses this command, your children:
              - have an 8/23 chance to grow older by one year
              - have a 5/23 chance to be renamed
              - have a 2/23 chance to take up to 1/64 of your money
              - have a 5/23 chance to give you up to 1/64 of your current money extra
              - have a 2/23 chance to find a random crate for you:
                + 500/761 (65%) chance for a common crate
                + 200/761 (26%) chance for an uncommon crate
                + 50/761 (6%) chance for a rare crate
                + 10/761 (1%) chance for a magic crate
                + 1/761 (0.1%) chance for a legendary crate
                + 1/761 (0.1%) chance for a fortune crate
                + 1/761 (0.1%) chance for a divine crate
              - have a 1/23 chance to die

            In each event you will know what happened.

            Only players who are married and have children can use this command.
            (This command has a cooldown of 30 minutes.)"""
        )
        name = ctx.character_data["name"]
        children = await self.bot.pool.fetch(
            'SELECT * FROM children WHERE ("mother"=$1 AND "father"=$2) OR ("father"=$1'
            ' AND "mother"=$2);',
            ctx.author.id,
            ctx.character_data["marriage"],
        )
        if not children:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_(f"{name}, you don't have kids yet."))
        target = random.choice(children)

        event = random.choice(
            ["death"]
            + ["age"] * 6
            + ["namechange"] * 6
            + ["crate"] * 2
            + ["moneylose"] * 4
            + ["moneygain"] * 4
        )
        if event == "death":
            cause = random.choice(
                [
                    _("They died after challenging a dragon to a 'who can breathe fire better' contest."),
                    _("They attempted to use a mimic as a backpack. It wasn't pleased."),
                    _("They tried to teach a beholder proper eye care. All 11 eyes were unimpressed."),
                    _("They accidentally insulted a wizard's beard and got turned into a rather stylish ottoman."),
                    _("Turns out 'Summon Bigger Fish' was not the right spell for their fishing trip."),
                    _("They asked a lich for skincare tips. The consultation was terminal."),
                    _("They tried to start a hug-a-werewolf charity on a full moon night."),
                    _("They died after asking the necromancer if they could practice resurrection magic 'just this once'."),
                    _("They attempted to use Cure Wounds on a zombie. It took offense."),
                    _("They tragically perished after challenging a sphinx to a riddle contest with 'What's in my pocket?' as their only riddle."),
                    _("They insisted that gelatinous cubes were 'just big friendly slimes' and tried to tame one."),
                    _("They died after suggesting that maybe orcs just need group therapy."),
                    _("They attempted to 'borrow' scales from a sleeping dragon for their arts and crafts project."),
                    _("They tried proving mimics aren't so bad by showing one affection. It reciprocated... too enthusiastically."),
                    _("They accidentally attended a drow dinner party thinking it was a costume event."),
                    _("Turns out 'Hey, pull my finger' isn't a joke when said to a golem."),
                    _("They sold their soul to a devil for a copper piece and 'the realm's greatest meat pie.' The pie wasn't worth it."),
                    _("They suffocated while trying to smell what The Rock Elemental was cooking."),
                    _("They attempted to pet what they thought was a dog. It was a displacer beast with excellent camouflage."),
                    _("They died challenging a sphinx to a staring contest, forgetting sphinxes don't need to blink."),
                    _("They wrote a strongly worded letter to a lich about grave robbery. The response was deadly."),
                    _("They thought 'rust monster' meant it was just a bit tarnished and would make a lovely pet."),
                    _("They argued philosophy with a mind flayer, who found their brain particularly compelling."),
                    _("They died after asking a doppelganger 'Do you think this outfit makes me look fat?'"),
                    _("They tried to start a goblin rehabilitation program. First and only participant: Stabby McStabface."),
                    _("They insulted a bard's lute playing and became the tragic hero of a surprisingly catchy funeral ballad."),
                    _("They didn't heed the 'Beware of Mimic' sign. In their defense, the sign was also a mimic."),
                    _("They offered fashion advice to a flumph. Turns out they're very sensitive about their appearance."),
                    _("They wrote a romance novel starring a lich and a vampire. Both objected to the characterization."),
                    _("Their plan to corner the market on mimic-based storage solutions ended predictably."),
                    _("They tried to prove that mind flayers couldn't possibly eat ALL brains by presenting theirs as evidence."),
                    _("They proposed a swimming race to a kraken. Both their ambition and their limbs were quickly separated from them."),
                    _("They asked a medusa for her hairstylist's contact information while maintaining aggressive eye contact."),
                    _("They attempted to determine if a gelatinous cube was 'jelly or jam' with a taste test."),
                    _("They tried convincing a group of kobolds that they were a dragon. The kobolds brought them to a real dragon for confirmation."),
                    _("They enchanted a deck of cards to always win at poker. Unfortunately, they played against an archfey."),
                    _("They tried to prove owlbears were just misunderstood by opening an 'owlbear hugging booth.'"),
                    _("They attempted to teach a hydra that cutting off heads isn't the answer. The hydra had several counterpoints."),
                    _("They thought the suspicious book bound in human skin with 'DO NOT READ ALOUD' on the cover had some excellent vocal exercises."),
                    _("They tried to sell life insurance to a vampire. The sales pitch ended with an unexpected policy claim."),
                    _("They insisted that mimics just needed more hugs as children, and volunteered to be a mimic therapist."),
                    _("They tried to prove that black puddings were just misunderstood desserts with an ill-advised taste test."),
                    _("They conducted a seance to contact dead ancestors but accidentally reached an annoyed elder god on its day off."),
                    _("They tried using a bag of devouring as a weight loss solution."),
                    _("They died after starting a support group for misunderstood monsters called 'Fiends Without Foes.' First meeting attendance: one hungry tarrasque."),
                    _("They attempted to introduce democracy to a goblin tribe. The first and last vote was about what to have for dinner."),
                    _("Their pyramid scheme selling 'genuine' basilisk eye drops for eternal youth attracted actual basilisks."),
                    _("They tried to host a roast battle with a red dragon. Both they and their comedy career went down in flames."),
                    _("They wrote a negative review of a lich's phylactery on 'RateMyImmortalityVessel.com'. One star was their last rating."),
                    _("They tried to answer the question 'If a Gelatinous Cube consumes a Bag of Holding, what happens?' Empirically."),
                ]
            )

            await self.bot.pool.execute(
                'DELETE FROM children WHERE "name"=$1 AND (("mother"=$2 AND'
                ' "father"=$4) OR ("father"=$2 AND "mother"=$4)) AND "age"=$3;',
                target["name"],
                ctx.author.id,
                target["age"],
                ctx.character_data["marriage"],
            )
            return await ctx.send(
                _("{name} died at the age of {age}! {cause}").format(
                    name=target["name"], age=target["age"], cause=cause
                )
            )
        elif event == "moneylose":
            cause = random.choice(
                [
                    _("invested in a wizard's scheme to turn copper into gold. The wizard disappeared with their gold instead."),
                    _("paid a bard to write an epic about their heroic deeds, but the ballad was about their embarrassing childhood instead."),
                    _("bought a 'genuine' intellect devourer in a jar from a suspicious merchant. It was a pickled turnip with googly eyes."),
                    _("fell for the old 'I'm a polymorphed princess' trick from a particularly crafty talking toad."),
                    _("invested in a dwarf's plan to mine chocolate from the 'Elemental Plane of Desserts'."),
                    _("paid for an 'undetectable' invisibility potion that just made their eyelids transparent."),
                    _("bought a map to a dragon's hoard from a suspiciously wealthy halfling with singed eyebrows."),
                    _("invested in a goblin's plan to breed dire-kittens for the adventurer companion market."),
                    _("paid a hefty sum for 'cloud giant repellent', which was just regular water in a fancy bottle."),
                    _("purchased a 'genuine' bag of holding that turned out to be a normal sack with 'HOLDING' embroidered on it."),
                    _("bought a 'pet rock elemental' that was just a regular rock with googly eyes."),
                    _("invested in the Gnomish expedition to discover the legendary 'Fountain of Ale'."),
                    _("funded an expedition to the Elemental Plane of Ranch Dressing. The sage said it would be a 'saucy venture'."),
                    _("purchased a potion of 'Speak With Plants' that just makes them hear imaginary plant voices."),
                    _("paid for an expensive course in 'draconic language' that only taught them how to say 'please don't eat me' with different inflections."),
                    _("bought an 'enchanted compass' that always points toward the nearest tavern (actually just a regular broken compass)."),
                    _("invested in 'underwater real estate' in a desert region. The seller promised water levels would rise 'any century now'."),
                    _("purchased a spell of 'Summon Better Financial Decisions' that failed to materialize."),
                    _("paid a necromancer for 'zombie labor' garden helpers that just dug up and ate all their vegetables."),
                    _("bought a 'Portable Hole' that was actually just a circle of black cloth that stains everything it touches."),
                    _("invested in a pixie's business plan to bottle and sell 'invisible cloth' for the emperor's new wardrobe line."),
                    _("purchased a 'Ring of Three Wishes' where the wishes were limited to 'wishing they hadn't bought the ring'."),
                    _("paid for a full set of 'dragonproof armor' made entirely of paper mache and hope."),
                    _("bought a 'magic mirror' that supposedly shows the future but actually just displays insults in fancy script."),
                    _("invested in a halfling's pyramid scheme selling 'genuine dragon scale weight loss supplements'."),
                    _("purchased a scroll of 'Summon Immense Wealth' that summoned an immense whelk instead."),
                    _("bought a 'Potion of Giant Strength' that just makes them feel emotionally stronger about their poor decisions."),
                    _("hired a bard to enhance their reputation, but the bard only composed songs about their most embarrassing moments."),
                    _("paid a fortune for a 'trained mimic pet' that was just a regular chest until it ate all their other possessions."),
                    _("invested in magically breeding square chickens 'for more efficient egg storage'."),
                    _("purchased an expensive 'bag of infinite holding' that actually just had a hole in the bottom."),
                    _("bought a 'captured fairy in a jar' that was actually just a firefly with glitter glued to it."),
                    _("paid a fortune teller for advice, who just told them to 'stop spending money on fortune tellers'."),
                    _("invested in a gnome's invention called 'automated monster slayer' that only slayed their savings account."),
                    _("purchased a 'guaranteed luck potion' that made them lucky enough to find more people willing to sell them fake potions."),
                    _("hired a wizard to enchant their weapon, but the wizard just drew a smiley face on it and called it 'The Happymaker'."),
                    _("bought a 'genuine unicorn horn' that was suspiciously narwhal-shaped and smelled of fish."),
                    _("invested in 'phoenix egg futures' from a merchant with mysteriously singed eyebrows."),
                    _("paid for an intensive course in 'draconic diplomacy' that just taught them how to say 'I am delicious with ketchup' in draconic."),
                    _("purchased an 'anti-mimic detection rod' that was itself a mimic."),
                    _("invested in a scheme to extract gold from goblin droppings after a very convincing alchemist's presentation."),
                    _("bought a 'wand of detect wands' that could amazingly detect itself but nothing else."),
                    _("paid for a cursed monkey paw, then used all three wishes trying to get rid of the monkey paw."),
                    _("purchased 'goblin repellent' which was actually goblin attractant with the label changed."),
                    _("funded a dwarf's expedition to find 'The Beer Elemental' in the Plane of Intoxication."),
                    _("bought an 'invisibility cloak' that just has 'YOU CAN'T SEE ME' embroidered on the back."),
                    _("invested in a scheme to sell 'dehydrated water tablets' to desert travelers. Add water to activate!"),
                    _("purchased a 'trained mimic guard dog' that kept eating their doorknobs and pretending to be their chamber pot."),
                    _("bought a 'speak with dead' scroll but it only lets the dead speak with them, usually at night, about extended warranty options."),
                    _("paid a wizard for a 'love potion' that just makes food taste better. Now they're in love with bread."),
                ]
            )
            money = random.randint(0, int(ctx.character_data["money"] / 64))
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                    money,
                    ctx.author.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=2,
                    subject="Family Event",
                    data={"Gold": -money},
                    conn=conn,
                )

            return await ctx.send(
                _("{nameuser}, you lost ${money} because {name} {cause}").format(
                    nameuser=name, money=money, name=target["name"], cause=cause
                )
            )
        elif event == "moneygain":
            cause = random.choice([
                _("discovered a dragon's hoard while playing hide and seek. The dragon was apparently very bad at hiding gold."),
                _("sold a 'genuine mimic egg' to a collector. It was actually just a wooden box with teeth drawn on it."),
                _("started a successful business selling 'bottled dungeon atmosphere' to homesick adventurers."),
                _("convinced a cyclops that an ordinary grape was a 'rare miniature healing potion' and sold it for a fortune."),
                _("won a bet that they could out-riddle a sphinx. Turns out the sphinx had heard all the classics already."),
                _("found a loophole in a devil's contract and got paid to NOT sell their soul."),
                _("started a lucrative business selling 'dragon repellent' in a region with no dragons."),
                _("convinced a gullible noble they were a long-lost heir to a fictional kingdom."),
                _("wrote and sold an unauthorized biography of a local lich titled 'Unlife Crisis: Eternity and Still No Hobbies'."),
                _("organized the realm's first 'Goblin Beauty Pageant' and made a fortune in entry fees."),
                _("sold 'invisible ink' (empty bottles) to aspiring rogues for their 'secret missions'."),
                _("started a matchmaking service for lonely trolls called 'Bridges of Love'."),
                _("sold tickets to see a 'petrified medusa' that was actually just a very convincing stone statue."),
                _("convinced a tribe of kobolds they were the prophesied 'Scale Shiner' and received tribute."),
                _("invented 'hydra shampoo' marketed with the slogan 'For every head you cut off, two more will shine!'"),
                _("started a lucrative business selling 'genuine wizard beard clippings' (actually just dyed goat hair)."),
                _("won a high-stakes belching contest against a brewer's guild. The prize was their annual production."),
                _("published a bestselling cookbook titled 'To Serve Dragon: Recipes They'll Flame Over'."),
                _("organized tours of 'authentic ghost locations' which were just abandoned buildings where they paid servants to make spooky noises."),
                _("sold 'monster protection amulets' that were just painted rocks on string. Coincidentally, no buyers have been eaten yet!"),
                _("won a drinking contest against a dwarf after secretly switching the dwarf's ale with extra-strong stuff."),
                _("convinced a cyclops that each eye needs its own monocle, then sold them a 'rare giant monocle collection'."),
                _("started a successful business selling 'genuine hero bathwater' to aspiring adventurers."),
                _("discovered they had a talent for 'dragon therapy' and charged by the hour. Mostly just nodding and asking 'How does that make you feel?'"),
                _("invented 'Essence of Courage' perfume for adventurers (mostly alcohol and cat urine) that sold remarkably well."),
                _("sold 'pixie dust' (just glitter) as a magical enhancer to gullible wizards."),
                _("published 'The Necromancer's Cookbook: Meals To Die For' which was suspiciously just regular recipes with spooky names."),
                _("started a successful palm-reading business despite having no magical abilities whatsoever."),
                _("organized 'mimic hunting expeditions' where they just led rich nobles around pointing at regular furniture saying 'not a mimic'."),
                _("won a bet that they could eat an entire roasted owlbear in one sitting. (It was actually just a large chicken.)"),
                _("convinced an orc tribe they were cursed with 'weakness' and sold them blessed water (regular water) as the cure."),
                _("started a luxury 'pet rock' business for busy nobles, offering 'the most low-maintenance familiar possible'."),
                _("sold 'mermaid scales' (actually just painted fish scales) as a rare beauty treatment."),
                _("organized the realm's first 'Ugly Bugbear Contest' with an entry fee. Every bugbear won something."),
                _("invented 'gnome tossing' as a tavern sport and made a fortune before the Gnome Rights Association shut it down."),
                _("started a business selling 'unicorn horn powder' which was just crushed-up seashells and glitter."),
                _("convinced a village that their chicken was actually a polymorphed phoenix and charged admission to see it."),
                _("wrote a bestselling etiquette book titled 'Dining with Dragons: How to Avoid Becoming the Main Course'."),
                _("sold 'guaranteed weight loss' potions that were just labeled 'Stop eating so much, you glutton' on the inside."),
                _("started a successful business selling 'goblin repellent' (ordinary water in fancy bottles)."),
                _("convinced a wealthy merchant they could speak with his deceased grandfather (actually just a hired actor hiding in the ceiling)."),
                _("organized a 'cursed item identification service' where they just made up random curses for ordinary objects."),
                _("published an unauthorized cookbook called 'Fantastic Beasts and How to Cook Them' that sold surprisingly well."),
                _("started a rent-a-familiar business using regular animals in tiny wizard hats."),
                _("won a fortune in a high-stakes game of 'Dragon, Wyrmling, Kobold' (like rock, paper, scissors but with more fire)."),
                _("sold 'authentic owlbear eggs' (painted chicken eggs) to gullible collectors."),
                _("discovered a talent for 'magical aura readings' that always found 'concerning energies' that cost extra to cleanse."),
                _("started a subscription service delivering 'monthly mystery potions' which were just different colored fruit juices."),
                _("wrote a popular self-help book titled 'How to Win Friends and Charm Dragons' despite having neither friends nor charmed dragons."),
                _("sold tickets to a 'guaranteed wizard duel' that was just two people in pointy hats throwing glitter at each other."),
            ])

            money = random.randint(0, int(ctx.character_data["money"] / 64))
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    ctx.author.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=ctx.author.id,
                    subject="FamilyEvent Money",
                    data={"Gold": money},
                    conn=conn,
                )
            return await ctx.send(
                _("{name} gave you ${money}, they {cause}").format(
                    name=target["name"], money=money, cause=cause
                )
            )
        elif event == "crate":
            type_ = random.choice(
                ["common"] * 497
                + ["uncommon"] * 199
                + ["rare"] * 50
                + ["magic"] * 7
                + ["fortune"] * 3
                + ["legendary"]
                + ["divine"]
            )
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    f'UPDATE profile SET "crates_{type_}"="crates_{type_}"+1 WHERE'
                    ' "user"=$1;',
                    ctx.author.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=2,
                    subject="FamilyEvent Crate",
                    data={"Rarity": type_, "Amount": 1},
                    conn=conn,
                )
            emoji = getattr(self.bot.cogs["Crates"].emotes, type_)
            return await ctx.send(
                _("{name} found a {emoji} {type_} crate for you!").format(
                    name=target["name"], emoji=emoji, type_=type_
                )
            )
        elif event == "age":
            await self.bot.pool.execute(
                'UPDATE children SET "age"="age"+1 WHERE "name"=$1 AND (("mother"=$2'
                ' AND "father"=$4) OR ("father"=$2 AND "mother"=$4)) AND "age"=$3;',
                target["name"],
                ctx.author.id,
                target["age"],
                ctx.character_data["marriage"],
            )
            return await ctx.send(
                _("{name} is now {age} years old.").format(
                    name=target["name"], age=target["age"] + 1
                )
            )
        elif event == "namechange":

            names = [c["name"] for c in children]
            names.remove(target["name"])
            oldname = target["name"]

            try:
                if not await ctx.confirm(
                        _(
                            '{author} you can rename {old_name}! Would you like to rename them?'
                        ).format(
                            author=ctx.author.mention,
                            old_name=target["name"],

                        )
                ):
                    await self.bot.set_cooldown(ctx, 1800)
                    return await ctx.send(_(f"You chose not to rename {oldname}."))


            except self.bot.paginator.NoChoice:
                await ctx.send(_("You didn't confirm."))
                return

            def check(msg):
                return (
                        msg.author.id in [ctx.author.id, ctx.character_data["marriage"]]
                        and msg.channel.id == ctx.channel.id
                )

            name = None
            while not name:
                await self.bot.set_cooldown(ctx, 1800)
                await ctx.send(
                    _(
                        "{name} can be renamed! Within 30 seconds, enter a new"
                        " name:\nType `cancel` to leave the name unchanged."
                    ).format(name=target["name"])
                )
                try:
                    msg = await self.bot.wait_for("message", check=check, timeout=30)
                    name = msg.content.replace("@", "@\u200b")
                except asyncio.TimeoutError:
                    return await ctx.send(_(f"{name}, you didn't enter a name."))
                if name.lower() == "cancel":
                    return await ctx.send(_(f"{name}, you didn't want to rename."))
                if len(name) == 0 or len(name) > 20:
                    await ctx.send(_(f"{name}, you must be 1 to 20 characters only."))
                    name = None
                    continue
                if name in names:
                    await ctx.send(
                        _(
                            "One of your children already has that name, please choose"
                            " another one."
                        )
                    )
                    name = None
                    continue
                try:
                    if not await ctx.confirm(
                            _(
                                '{author} Are you sure you want to rename "{old_name}" to'
                                ' "{new_name}"?'
                            ).format(
                                author=ctx.author.mention,
                                old_name=target["name"],
                                new_name=name,
                            )
                    ):
                        await ctx.send(
                            _('You didn\'t change the name to "{new_name}".').format(
                                new_name=name
                            )
                        )
                        name = None

                except self.bot.paginator.NoChoice:
                    await ctx.send(_(f"{name}, you didn't confirm."))
                    name = None

            if name == target["name"]:
                return await ctx.send(_(f"{name}, you didn't change their name."))
            await self.bot.pool.execute(
                'UPDATE children SET "name"=$1 WHERE "name"=$2 AND (("mother"=$3 AND'
                ' "father"=$5) OR ("father"=$3 AND "mother"=$5)) AND "age"=$4;',
                name,
                target["name"],
                ctx.author.id,
                target["age"],
                ctx.character_data["marriage"],
            )
            return await ctx.send(
                _("{old_name} is now called {new_name}.").format(
                    old_name=target["name"], new_name=name
                )
            )


async def setup(bot):
    await bot.add_cog(Marriage(bot))
