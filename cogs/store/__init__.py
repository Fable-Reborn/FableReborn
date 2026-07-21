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
import discord

from discord.ext import commands

from classes.converters import IntGreaterThan
from utils.checks import has_char
from utils.i18n import _, locale_doc


BOOSTER_PRICES = {"time": 1000, "luck": 500, "money": 1000, "all": 2500}


class BoosterTypeSelect(discord.ui.Select):
    def __init__(self, store_view: "BoosterStoreView"):
        options = [
            discord.SelectOption(label="Time Booster", value="time", description="$1,000 • halves adventure time", emoji="⏱️"),
            discord.SelectOption(label="Luck Booster", value="luck", description="$500 • +25% adventure luck", emoji="🍀"),
            discord.SelectOption(label="Money Booster", value="money", description="$1,000 • +25% adventure money", emoji="💰"),
            discord.SelectOption(label="All Three", value="all", description="$2,500 per set", emoji="✨"),
        ]
        for option in options:
            option.default = option.value == store_view.booster
        super().__init__(placeholder="Choose a booster", options=options, row=0)
        self.store_view = store_view

    async def callback(self, interaction):
        self.store_view.booster = self.values[0]
        self.store_view.rebuild_components()
        await interaction.response.edit_message(embed=self.store_view.build_embed(), view=self.store_view)


class BoosterQuantitySelect(discord.ui.Select):
    def __init__(self, store_view: "BoosterStoreView"):
        options = [
            discord.SelectOption(label=f"Buy {amount}", value=str(amount), default=amount == store_view.amount)
            for amount in (1, 5, 10, 25)
        ]
        super().__init__(placeholder="Choose purchase quantity", options=options, row=1)
        self.store_view = store_view

    async def callback(self, interaction):
        self.store_view.amount = int(self.values[0])
        await interaction.response.edit_message(embed=self.store_view.build_embed(), view=self.store_view)


class BoosterActivationConfirmView(discord.ui.View):
    def __init__(self, store_view: "BoosterStoreView", booster: str):
        super().__init__(timeout=45)
        self.store_view = store_view
        self.booster = booster

    async def interaction_check(self, interaction):
        if interaction.user.id != self.store_view.ctx.author.id:
            await interaction.response.send_message("This activation is not yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Activation", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button):
        await interaction.response.defer()
        ok, message = await self.store_view.cog.activate_booster_selection(
            self.store_view.ctx,
            self.booster,
        )
        await self.store_view.refresh_data()
        self.store_view.rebuild_components()
        if self.store_view.message:
            await self.store_view.message.edit(embed=self.store_view.build_embed(message if ok else None), view=self.store_view)
        await interaction.edit_original_response(content=message, embed=None, view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="Activation cancelled.", embed=None, view=None)
        self.stop()


class BoosterStoreView(discord.ui.View):
    def __init__(self, cog, ctx, *, counts, money, active):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.counts = counts
        self.money = money
        self.active = active
        self.booster = "time"
        self.amount = 1
        self.message = None
        self.rebuild_components()

    @classmethod
    async def create(cls, cog, ctx):
        row = await cog.bot.pool.fetchrow(
            'SELECT money, time_booster, luck_booster, money_booster FROM profile WHERE "user"=$1;',
            ctx.author.id,
        )
        active = {kind: await cog.bot.get_booster(ctx.author, kind) for kind in ("time", "luck", "money")}
        counts = {kind: int(row[f"{kind}_booster"] or 0) for kind in ("time", "luck", "money")}
        return cls(cog, ctx, counts=counts, money=int(row["money"] or 0), active=active)

    async def refresh_data(self):
        row = await self.cog.bot.pool.fetchrow(
            'SELECT money, time_booster, luck_booster, money_booster FROM profile WHERE "user"=$1;',
            self.ctx.author.id,
        )
        self.money = int(row["money"] or 0)
        self.counts = {kind: int(row[f"{kind}_booster"] or 0) for kind in ("time", "luck", "money")}
        self.active = {kind: await self.cog.bot.get_booster(self.ctx.author, kind) for kind in ("time", "luck", "money")}

    def build_embed(self, notice=None):
        description = f"Balance: **${self.money:,}**"
        if notice:
            description = f"✅ {notice}\n\n{description}"
        embed = discord.Embed(title="🚀 Booster Store & Inventory", description=description, color=discord.Color.blurple())
        details = {
            "time": ("⏱️ Time", "$1,000", "Halves adventure time"),
            "luck": ("🍀 Luck", "$500", "+25% adventure luck"),
            "money": ("💰 Money", "$1,000", "+25% adventure money rewards"),
        }
        for kind, (label, price, effect) in details.items():
            active = str(self.active[kind]).split(".")[0] if self.active[kind] else "Inactive"
            embed.add_field(
                name=label,
                value=f"Price: **{price}**\nOwned: **{self.counts[kind]}**\nActive: **{active}**\n{effect}",
                inline=True,
            )
        total_price = BOOSTER_PRICES[self.booster] * self.amount
        embed.add_field(
            name="Selected Purchase",
            value=f"**{self.amount}× {self.booster.title()}** — **${total_price:,}**\nBalance after: **${self.money - total_price:,}**",
            inline=False,
        )
        embed.set_footer(text="Boosters last 24 hours. Activating an active booster refreshes its timer after confirmation.")
        return embed

    def rebuild_components(self):
        self.clear_items()
        self.add_item(BoosterTypeSelect(self))
        self.add_item(BoosterQuantitySelect(self))
        for label, style, callback, disabled in [
            ("Buy Selected", discord.ButtonStyle.success, self.buy, False),
            ("Activate Selected", discord.ButtonStyle.primary, self.activate, self.booster != "all" and self.counts.get(self.booster, 0) <= 0),
            ("Activate All Owned", discord.ButtonStyle.primary, self.activate_all, not any(self.counts.values())),
            ("Refresh", discord.ButtonStyle.secondary, self.refresh, False),
            ("Close", discord.ButtonStyle.danger, self.close, False),
        ]:
            button = discord.ui.Button(label=label, style=style, disabled=disabled, row=2)
            button.callback = callback
            self.add_item(button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This booster panel is not yours.", ephemeral=True)
            return False
        return True

    async def buy(self, interaction):
        await interaction.response.defer()
        ok, message = await self.cog.purchase_boosters(self.ctx, self.booster, self.amount)
        await self.refresh_data()
        self.rebuild_components()
        await interaction.message.edit(embed=self.build_embed(message if ok else None), view=self)
        if not ok:
            await interaction.followup.send(message, ephemeral=True)

    async def _confirm_activation(self, interaction, booster):
        label = "all owned boosters" if booster == "all" else f"a {booster} booster"
        await interaction.response.send_message(
            f"Activate {label}? Any active matching timer will be refreshed.",
            view=BoosterActivationConfirmView(self, booster),
            ephemeral=True,
        )

    async def activate(self, interaction):
        await self._confirm_activation(interaction, self.booster)

    async def activate_all(self, interaction):
        await self._confirm_activation(interaction, "all")

    async def refresh(self, interaction):
        await self.refresh_data()
        self.rebuild_components()
        await interaction.response.edit_message(embed=self.build_embed("Booster data refreshed."), view=self)

    async def close(self, interaction):
        await interaction.response.edit_message(view=None)
        self.stop()


class Store(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def purchase_boosters(self, ctx, booster: str, amount: int):
        if booster not in BOOSTER_PRICES or amount <= 0:
            return False, "Invalid booster purchase."
        price = BOOSTER_PRICES[booster] * amount
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                money = await conn.fetchval(
                    'SELECT money FROM profile WHERE "user"=$1 FOR UPDATE;',
                    ctx.author.id,
                )
                if money is None:
                    return False, "Character data could not be found."
                if int(money) < price:
                    return False, f"You need ${price:,}, but only have ${int(money):,}."
                if booster == "all":
                    await conn.execute(
                        'UPDATE profile SET time_booster=time_booster+$1, luck_booster=luck_booster+$1, '
                        'money_booster=money_booster+$1, money=money-$2 WHERE "user"=$3;',
                        amount,
                        price,
                        ctx.author.id,
                    )
                else:
                    await conn.execute(
                        f'UPDATE profile SET "{booster}_booster"="{booster}_booster"+$1, money=money-$2 '
                        'WHERE "user"=$3;',
                        amount,
                        price,
                        ctx.author.id,
                    )
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=2,
                    subject="buy boosters",
                    data={"Gold": price, "Booster": booster, "Amount": amount},
                    conn=conn,
                )
        return True, f"Bought {amount}× {booster.title()} booster(s) for ${price:,}."

    async def activate_booster_selection(self, ctx, booster: str):
        kinds = ("time", "luck", "money") if booster == "all" else (booster,)
        if any(kind not in {"time", "luck", "money"} for kind in kinds):
            return False, "Invalid booster type."
        activated = []
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                for kind in kinds:
                    consumed = await conn.fetchval(
                        f'UPDATE profile SET "{kind}_booster"="{kind}_booster"-1 '
                        f'WHERE "user"=$1 AND "{kind}_booster">0 RETURNING "{kind}_booster";',
                        ctx.author.id,
                    )
                    if consumed is not None:
                        activated.append(kind)
        if not activated:
            return False, "You do not own any of the selected boosters."
        for kind in activated:
            await self.bot.activate_booster(ctx.author, kind)
        return True, f"Activated {', '.join(kind.title() for kind in activated)} for 24 hours."

    @has_char()
    @commands.command(brief=_("Show the booster store"))
    @locale_doc
    async def store(self, ctx):
        _(
            """Show the booster store. For a detailed explanation what the boosters do, check `{prefix}help boosters`."""
        )
        shopembed = discord.Embed(
            title=_("Fable Store"),
            description=_(
                "Welcome! Use `{prefix}purchase time/luck/money` to buy something."
            ).format(prefix=ctx.clean_prefix),
            colour=discord.Colour.blurple(),
        )
        shopembed.add_field(
            name=_("Boosters"),
            value=_(
                "`#1` Time Booster\t**$1000**\tBoosts adventure time by 50%\n`#2` Luck"
                " Booster\t**$500**\tBoosts adventure luck (not `{prefix}luck`) by"
                " 25%\n`#3` Money Booster\t**$1000**\tBoosts adventure money rewards"
                " by 25%"
            ).format(prefix=ctx.clean_prefix),
            inline=False,
        )
        shopembed.set_thumbnail(url=f"{self.bot.BASE_URL}/business.png")
        view = await BoosterStoreView.create(self, ctx)
        view.message = await ctx.send(embed=view.build_embed(), view=view)

    @has_char()
    @commands.command(brief=_("Buy some boosters"))
    @locale_doc
    async def purchase(self, ctx, booster: str.lower, amount: IntGreaterThan(0) = 1):
        _(
            """`<booster>` - The booster type to buy, can be time, luck, money or all
            `[amount]` - The amount of boosters to buy; defaults to 1

            Buy one or more booster from the store. For a detailed explanation what the boosters do, check `{prefix}help boosters`."""
        )
        if booster not in ["time", "luck", "money", "all"]:
            return await ctx.send(_("Please either buy `time`, `luck` or `money`."))
        ok, message = await self.purchase_boosters(ctx, booster, int(amount))
        return await ctx.send(message)

    @has_char()
    @commands.command(aliases=["b"], brief=_("View your boosters"))
    @locale_doc
    async def boosters(self, ctx):
        _(
            """View your boosters and the active ones' status. Each one has a different effect.

              - Time boosters halve the adventures' times (must be active before starting an adventure)
              - Luck boosters increase your adventure chances by 25%
              - Money boosters increase the amount of gold gained from adventures by 25%

            Each booster lasts 24 hours after activation."""
        )
        timeboosters = ctx.character_data["time_booster"]
        luckboosters = ctx.character_data["luck_booster"]
        moneyboosters = ctx.character_data["money_booster"]
        time = await self.bot.get_booster(ctx.author, "time")
        luck = await self.bot.get_booster(ctx.author, "luck")
        money = await self.bot.get_booster(ctx.author, "money")
        time = (
            _("Time booster - {time}").format(time=str(time).split(".")[0])
            if time
            else None
        )
        luck = (
            _("Luck booster - {time}").format(time=str(luck).split(".")[0])
            if luck
            else None
        )
        money = (
            _("Money booster - {time}").format(time=str(money).split(".")[0])
            if money
            else None
        )
        actives = "\n".join([b for b in [time, luck, money] if b])
        text = _("Currently active")
        if time or luck or money:
            desc = f"**{text}**\n{actives}"
        else:
            desc = ""
        a, b, c = _("Time Boosters"), _("Luck Boosters"), _("Money Boosters"),
        view = await BoosterStoreView.create(self, ctx)
        view.message = await ctx.send(embed=view.build_embed(), view=view)

    @has_char()
    @commands.command(brief=_("Activate a booster"))
    @locale_doc
    async def activate(self, ctx, boostertype: str.lower):
        _(
            """`<boostertype>` - The booster type to activate, can be time, luck, money or all

            Activate a booster. For a detailed explanation what the boosters do, check `{prefix}help boosters`."""
        )
        if boostertype not in ["time", "luck", "money", "all"]:
            return await ctx.send(
                _("That is not a valid booster type. Must be `time/luck/money/all`.")
            )
        if boostertype != "all":
            boosters = ctx.character_data[f"{boostertype}_booster"]
            if boosters <= 0:
                return await ctx.send(_("You don't have any of these boosters."))
            check = await self.bot.get_booster(ctx.author, boostertype)
            if check:
                if not await ctx.confirm(
                    _(
                        "This booster is already running. Do you want to refresh it"
                        " anyways?"
                    )
                ):
                    return

            await self.bot.pool.execute(
                f'UPDATE profile SET "{boostertype}_booster"="{boostertype}_booster"-1'
                ' WHERE "user"=$1;',
                ctx.author.id,
            )
            await self.bot.activate_booster(ctx.author, boostertype)
            await ctx.send(
                _(
                    "Successfully activated a **{booster} booster** for the next **24"
                    " hours**!"
                ).format(booster=boostertype.title())
            )
        else:
            if not await ctx.confirm(
                _(
                    "This will overwrite all active boosters and refresh them. Are you"
                    " sure?"
                )
            ):
                return

            reducible = [
                i
                for i in ("time", "luck", "money")
                if ctx.character_data[f"{i}_booster"]
            ]

            if not reducible:
                return await ctx.send(_("Nothing to activate."))

            to_reduce = ", ".join([f'"{i}_booster"="{i}_booster"-1' for i in reducible])

            await self.bot.pool.execute(
                f'UPDATE profile SET {to_reduce} WHERE "user"=$1;', ctx.author.id
            )

            for i in reducible:
                await self.bot.activate_booster(ctx.author, i)
            await ctx.send(
                _("Successfully activated {types} for the next **24 hours**!").format(
                    types=", ".join(reducible)
                )
            )


async def setup(bot):
    await bot.add_cog(Store(bot))
