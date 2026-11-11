"""A short raid-stat card.

Shows the modifiers already on a player's gear. The buttons change a weapon's
damage (or a shield's armor) and the $rs attack and defense upgrades.
"""
from __future__ import annotations

import copy
import logging

import discord
from discord.ext import commands

from classes.endgame import soulbound_level_from_xp
from utils import misc as rpgtools
from utils import statcalc
from utils.i18n import _, locale_doc

log = logging.getLogger(__name__)


class SetValueModal(discord.ui.Modal):
    def __init__(self, view: "StatCalcView"):
        label = dict(statcalc.knobs(view.sheet)).get(view.field, "Value")
        super().__init__(title=f"Set {label}"[:45])
        self.view = view
        self.entry = discord.ui.TextInput(
            label=label[:45],
            default=statcalc.editable_value(view.sheet, view.field)[:400],
            max_length=20,
            required=True,
        )
        self.add_item(self.entry)

    async def on_submit(self, interaction: discord.Interaction):
        error = statcalc.apply_text(self.view.sheet, self.view.field, str(self.entry.value))
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        self.view.sync()
        try:
            await interaction.response.edit_message(embed=self.view.embed(), view=self.view)
        except discord.HTTPException:
            await interaction.response.send_message("The calculator closed.", ephemeral=True)


class StatCalcView(discord.ui.View):
    def __init__(self, cog, author_id: int, target_id: int, hero_name: str, sheet: statcalc.Sheet):
        super().__init__(timeout=600)
        self.cog = cog
        self.author_id = author_id
        self.target_id = target_id
        self.hero_name = hero_name
        self.sheet = sheet
        self.baseline = copy.copy(sheet)
        self.field = statcalc.knobs(sheet)[0][0]
        self.message: discord.Message | None = None
        self.pick = discord.ui.Select(
            placeholder="Weapon or $rs",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label="Weapon damage", value="right_damage")],
            row=0,
        )
        self.pick.callback = self.on_pick
        self.add_item(self.pick)
        self.sync()

    def embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Stat calculator",
            description=statcalc.card(self.sheet, self.field, self.baseline),
            colour=0xC4A35A,
        )
        embed.set_footer(text="Changes nothing on your character. My gear reloads what you have equipped.")
        return embed

    def sync(self) -> None:
        options = []
        for key, label in statcalc.knobs(self.sheet):
            options.append(discord.SelectOption(
                label=label[:100],
                value=key,
                description=statcalc.editable_value(self.sheet, key)[:100],
                default=key == self.field,
            ))
        if self.field not in {key for key, _label in statcalc.knobs(self.sheet)}:
            self.field = options[0].value
            options[0].default = True
        self.pick.options = options
        small, big = statcalc.knob_steps(self.field)
        self._set_step(self.down_big, big, -1)
        self._set_step(self.down_small, small, -1)
        self._set_step(self.up_small, small, 1)
        self._set_step(self.up_big, big, 1)
        self.my_gear.label = "My gear" if self.target_id == self.author_id else "Reload"

    def _set_step(self, button: discord.ui.Button, amount, sign: int) -> None:
        button.label = statcalc.step_label(amount, "-" if sign < 0 else "+")
        button.disabled = not statcalc.can_move(self.sheet, self.field, amount * sign)

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This calculator belongs to the person who opened it.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is None:
            return
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass

    async def on_pick(self, interaction: discord.Interaction):
        chosen = self.pick.values or (interaction.data or {}).get("values") or []
        if not chosen:
            await interaction.response.defer()
            return
        self.field = chosen[0]
        await self.refresh(interaction)

    async def _nudge(self, interaction: discord.Interaction, which: str, sign: int):
        small, big = statcalc.knob_steps(self.field)
        amount = small if which == "small" else big
        statcalc.move(self.sheet, self.field, amount * sign)
        await self.refresh(interaction)

    @discord.ui.button(label="-10", style=discord.ButtonStyle.secondary, row=1)
    async def down_big(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, "big", -1)

    @discord.ui.button(label="-1", style=discord.ButtonStyle.secondary, row=1)
    async def down_small(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, "small", -1)

    @discord.ui.button(label="+1", style=discord.ButtonStyle.primary, row=1)
    async def up_small(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, "small", 1)

    @discord.ui.button(label="+10", style=discord.ButtonStyle.primary, row=1)
    async def up_big(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, "big", 1)

    @discord.ui.button(label="Type", style=discord.ButtonStyle.primary, row=1)
    async def type_number(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetValueModal(self))

    @discord.ui.button(label="My gear", style=discord.ButtonStyle.success, row=2)
    async def my_gear(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            sheet = await self.cog.load_sheet(self.target_id, self.hero_name)
        except Exception:
            log.exception("statcalc load failed for %s", self.target_id)
            await interaction.followup.send("Couldn't read that hero.", ephemeral=True)
            return
        if sheet is None:
            await interaction.followup.send("No character on that account yet.", ephemeral=True)
            return
        self.sheet = sheet
        self.baseline = copy.copy(sheet)
        self.field = statcalc.knobs(sheet)[0][0]
        self.sync()
        await interaction.edit_original_response(embed=self.embed(), view=self)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary, row=2)
    async def reset_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.sheet = copy.copy(self.baseline)
        self.field = statcalc.knobs(self.sheet)[0][0]
        await self.refresh(interaction)


class StatCalc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def load_sheet(self, user_id: int, hero_name: str) -> statcalc.Sheet | None:
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT "atkmultiply", "defmultiply", "statatk", "statdef", "stathp", '
                '"health", "xp", "class", "race", "guild" FROM profile WHERE "user"=$1',
                user_id,
            )
            if row is None:
                return None
            items = await conn.fetch(
                "SELECT ai.* FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN "
                "inventory i ON (ai.id=i.item) WHERE i.equipped IS TRUE AND p.user=$1",
                user_id,
            )
            star_map: dict[int, int] = {}
            soul_item = None
            soul_level = 0
            item_ids = []
            for item in items:
                try:
                    item_ids.append(int(item["id"]))
                except (KeyError, TypeError, ValueError):
                    continue
            if item_ids:
                try:
                    star_table = await conn.fetchval(
                        "SELECT to_regclass('public.starforged_items') IS NOT NULL;"
                    )
                    if star_table:
                        star_rows = await conn.fetch(
                            "SELECT item_id, stars FROM starforged_items WHERE item_id = ANY($1)",
                            item_ids,
                        )
                        star_map = {int(star["item_id"]): int(star["stars"] or 0) for star in star_rows}
                    soul_table = await conn.fetchval(
                        "SELECT to_regclass('public.soulbound') IS NOT NULL;"
                    )
                    if soul_table:
                        soul_row = await conn.fetchrow(
                            "SELECT item_id, xp FROM soulbound WHERE user_id = $1 AND item_id = ANY($2)",
                            user_id,
                            item_ids,
                        )
                        if soul_row:
                            soul_item = int(soul_row["item_id"])
                            soul_level = soulbound_level_from_xp(soul_row["xp"])
                except Exception:
                    star_map = {}
                    soul_item = None
                    soul_level = 0
            amulet = await conn.fetchrow(
                "SELECT attack, defense, hp FROM amulets WHERE user_id=$1 AND equipped=true",
                user_id,
            )
            city = 0
            if row["guild"]:
                buildings = await self.bot.get_city_buildings(row["guild"], conn=conn)
                if buildings:
                    city = int(buildings["raid_building"] or 0)
        classes = row["class"] or []
        if isinstance(classes, str):
            classes = [classes]
        prepared = []
        for item in items:
            try:
                item_id = int(item["id"])
            except (KeyError, TypeError, ValueError):
                item_id = 0
            prepared.append({
                "name": item["name"] if "name" in item else "",
                "type": item["type"] if "type" in item else "",
                "hand": item["hand"] if "hand" in item else "any",
                "damage": item["damage"] if "damage" in item else 0,
                "armor": item["armor"] if "armor" in item else 0,
                "stars": star_map.get(item_id, 0),
                "soul": soul_level if item_id == soul_item else 0,
            })
        return statcalc.sheet_from_equipped(
            hero_name=hero_name,
            race=row["race"] or "None",
            classes=list(classes),
            profile_atk=row["atkmultiply"] if row["atkmultiply"] is not None else 1,
            profile_def=row["defmultiply"] if row["defmultiply"] is not None else 1,
            stat_atk=row["statatk"] or 0,
            stat_def=row["statdef"] or 0,
            stat_hp=row["stathp"] or 0,
            city=city,
            level=rpgtools.xptolevel(row["xp"]),
            profile_hp=row["health"] or 0,
            amulet_attack=(amulet["attack"] if amulet else 0) or 0,
            amulet_defense=(amulet["defense"] if amulet else 0) or 0,
            amulet_hp=(amulet["hp"] if amulet else 0) or 0,
            items=prepared,
        )

    @commands.command(
        name="statcalc",
        aliases=["scalc", "statslider"],
        brief=_("Try weapon damage and $rs upgrades"),
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    @locale_doc
    async def statcalc(self, ctx, player: discord.User = None):
        _(
            """See your raid totals with a different weapon damage or $rs upgrade.

            The card lists the modifiers already on the equipped gear. The menu
            picks a weapon's damage or your $rs attack and defense. The buttons
            move that number, and Type sets it exactly.

            `{prefix}statcalc` uses your gear.
            `{prefix}statcalc @someone` uses theirs.
            """
        )
        target = player or ctx.author
        sheet = await self.load_sheet(target.id, target.display_name)
        if sheet is None:
            sheet = statcalc.example_sheet()
            if player is not None:
                sheet.origin = "missing"
                sheet.hero_name = statcalc.clean(target.display_name, 32, "Hero")
        view = StatCalcView(
            cog=self,
            author_id=ctx.author.id,
            target_id=target.id,
            hero_name=target.display_name,
            sheet=sheet,
        )
        message = await ctx.send(embed=view.embed(), view=view)
        view.message = message


async def setup(bot):
    await bot.add_cog(StatCalc(bot))
