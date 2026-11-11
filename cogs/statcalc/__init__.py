"""A slider for raid attack, raid defense, and health.

Discord has no slider component, so the bar in the embed is the slider and the
buttons under it move the selected number. The math lives in utils/statcalc.py
and follows get_raidstats plus battle health.
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
        field = statcalc.FIELDS[view.field]
        super().__init__(title=f"Set {field.label}"[:45])
        self.view = view
        self.entry = discord.ui.TextInput(
            label=field.label[:45],
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
    def __init__(self, cog, author_id: int, target_id: int, hero_name: str, sheet: statcalc.Sheet, prefix: str):
        super().__init__(timeout=600)
        self.cog = cog
        self.author_id = author_id
        self.target_id = target_id
        self.hero_name = hero_name
        self.sheet = sheet
        self.baseline = copy.copy(sheet)
        self.prefix = prefix
        self.page = "weapons"
        self.field = "right_damage"
        if sheet.right_damage == 0 and sheet.right_armor == 0 and (sheet.left_damage or sheet.left_armor):
            self.field = "left_damage"
        self.message: discord.Message | None = None
        self.field_select = discord.ui.Select(
            placeholder="Choose what the slider moves",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label="Right weapon damage", value="right_damage")],
            row=0,
        )
        self.field_select.callback = self.on_field
        self.amulet_select = discord.ui.Select(
            placeholder="Drop in a crafted amulet",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label="No amulet", value="clear")],
            row=4,
        )
        self.amulet_select.callback = self.on_amulet
        self.add_item(self.field_select)
        self.add_item(self.amulet_select)
        self.sync()

    def embed(self) -> discord.Embed:
        text = statcalc.explain(self.sheet, self.field, self.baseline, self.prefix)
        if len(text) > 4096:
            text = text[:4093].rstrip() + "..."
        embed = discord.Embed(title="Stat calculator", description=text, colour=0xC4A35A)
        embed.set_author(name=statcalc.clean(self.sheet.hero_name, 64, "Hero"))
        embed.set_footer(
            text="Matches raid attack, raid defense, and battle health. Skills, pets, and luck are left out. Sliders last 10 minutes."
        )
        return embed

    def sync(self) -> None:
        self.down_large.label, self.down_large.disabled = statcalc.control_state(self.sheet, self.field, 2, -1)
        self.down_small.label, self.down_small.disabled = statcalc.control_state(self.sheet, self.field, 1, -1)
        self.down_tiny.label, self.down_tiny.disabled = statcalc.control_state(self.sheet, self.field, 0, -1)
        self.up_tiny.label, self.up_tiny.disabled = statcalc.control_state(self.sheet, self.field, 0, 1)
        self.up_small.label, self.up_small.disabled = statcalc.control_state(self.sheet, self.field, 1, 1)
        self.down_huge.label, self.down_huge.disabled = statcalc.control_state(self.sheet, self.field, 3, -1)
        self.up_huge.label, self.up_huge.disabled = statcalc.control_state(self.sheet, self.field, 3, 1)
        self.page_button.label = "Hero stats" if self.page == "weapons" else "Weapons"
        self.load_button.label = "Load my hero" if self.target_id == self.author_id else "Reload hero"
        options = []
        for key in statcalc.FIELD_KEYS[self.page]:
            field = statcalc.FIELDS[key]
            options.append(discord.SelectOption(
                label=field.label[:100],
                value=key,
                description=statcalc.shown_value(self.sheet, key)[:100],
                default=key == self.field,
            ))
        self.field_select.options = options
        chosen = statcalc.matching_preset(self.sheet)
        amulet_options = []
        for value, label, description in statcalc.preset_choices():
            amulet_options.append(discord.SelectOption(
                label=label[:100],
                value=value,
                description=description[:100],
                default=value == chosen,
            ))
        self.amulet_select.options = amulet_options

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "These sliders belong to the person who opened the calculator.",
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

    async def on_field(self, interaction: discord.Interaction):
        chosen = self.field_select.values or (interaction.data or {}).get("values") or []
        if not chosen or chosen[0] not in statcalc.FIELDS:
            await interaction.response.defer()
            return
        self.field = chosen[0]
        self.page = statcalc.FIELDS[self.field].page
        await self.refresh(interaction)

    async def on_amulet(self, interaction: discord.Interaction):
        chosen = self.amulet_select.values or (interaction.data or {}).get("values") or []
        if not chosen:
            await interaction.response.defer()
            return
        statcalc.apply_preset(self.sheet, chosen[0])
        self.page = "hero"
        self.field = "amulet_atk"
        await self.refresh(interaction)

    async def _nudge(self, interaction: discord.Interaction, index: int, sign: int):
        field = statcalc.FIELDS[self.field]
        statcalc.move(self.sheet, self.field, field.steps[index] * sign)
        await self.refresh(interaction)

    @discord.ui.button(label="-100", style=discord.ButtonStyle.secondary, row=1)
    async def down_large(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, 2, -1)

    @discord.ui.button(label="-10", style=discord.ButtonStyle.secondary, row=1)
    async def down_small(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, 1, -1)

    @discord.ui.button(label="-1", style=discord.ButtonStyle.secondary, row=1)
    async def down_tiny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, 0, -1)

    @discord.ui.button(label="+1", style=discord.ButtonStyle.primary, row=1)
    async def up_tiny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, 0, 1)

    @discord.ui.button(label="+10", style=discord.ButtonStyle.primary, row=1)
    async def up_small(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, 1, 1)

    @discord.ui.button(label="-1k", style=discord.ButtonStyle.secondary, row=2)
    async def down_huge(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, 3, -1)

    @discord.ui.button(label="Type number", style=discord.ButtonStyle.primary, row=2)
    async def type_number(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetValueModal(self))

    @discord.ui.button(label="+1k", style=discord.ButtonStyle.primary, row=2)
    async def up_huge(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, 3, 1)

    @discord.ui.button(label="Undo", style=discord.ButtonStyle.secondary, row=2)
    async def undo_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        statcalc.restore_field(self.sheet, self.baseline, self.field)
        await self.refresh(interaction)

    @discord.ui.button(label="Hero stats", style=discord.ButtonStyle.secondary, row=2)
    async def page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = "hero" if self.page == "weapons" else "weapons"
        if self.field not in statcalc.FIELD_KEYS[self.page]:
            self.field = statcalc.FIELD_KEYS[self.page][0]
        await self.refresh(interaction)

    @discord.ui.button(label="Load my hero", style=discord.ButtonStyle.success, row=3)
    async def load_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            sheet = await self.cog.load_sheet(self.target_id, self.hero_name)
        except Exception:
            log.exception("statcalc load failed for %s", self.target_id)
            await interaction.followup.send(
                "Couldn't read that hero. The sliders stay where they are.",
                ephemeral=True,
            )
            return
        if sheet is None:
            await interaction.followup.send(
                "No character on that account yet. The example stays up.",
                ephemeral=True,
            )
            return
        self.sheet = sheet
        self.baseline = copy.copy(sheet)
        self.page = "weapons"
        self.field = "right_damage"
        if sheet.right_damage == 0 and sheet.right_armor == 0 and (sheet.left_damage or sheet.left_armor):
            self.field = "left_damage"
        await self.refresh_deferred(interaction)

    async def refresh_deferred(self, interaction: discord.Interaction) -> None:
        self.sync()
        await interaction.edit_original_response(embed=self.embed(), view=self)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=3)
    async def reset_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.sheet = copy.copy(self.baseline)
        await self.refresh(interaction)

    @discord.ui.button(label="Right dmg", style=discord.ButtonStyle.secondary, row=3)
    async def jump_right(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = "weapons"
        self.field = "right_damage"
        await self.refresh(interaction)

    @discord.ui.button(label="Atk points", style=discord.ButtonStyle.secondary, row=3)
    async def jump_points(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = "hero"
        self.field = "stat_atk"
        await self.refresh(interaction)

    @discord.ui.button(label="Amulet", style=discord.ButtonStyle.secondary, row=3)
    async def jump_amulet(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = "hero"
        self.field = "amulet_atk"
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
        brief=_("See what multiplies your raid stats"),
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    @locale_doc
    async def statcalc(self, ctx, player: discord.User = None):
        _(
            """Open a raid-stat calculator and move the numbers yourself.

            The bar in the message is the slider. The buttons move the selected
            value, and Type number sets a weapon's damage exactly.

            Stars and soulbound multiply that weapon. Class fit, race, and class
            grade are added on. Profile multiplier, attack points, and the raid
            hall are added into one multiplier, and that multiplier is applied to
            all of the gear. Amulet attack and defense are added after it.
            Health is a sum: 200, plus profile HP, plus 15 per level, plus 200 per
            health point, plus the amulet.

            `{prefix}statcalc` starts from your equipped gear.
            `{prefix}statcalc @someone` starts from theirs. Only the person who
            opened it can move the sliders.

            Skills, pets, and luck are left out. This matches raid attack, raid
            defense, and battle health.
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
            prefix=ctx.clean_prefix,
        )
        message = await ctx.send(embed=view.embed(), view=view)
        view.message = message


async def setup(bot):
    await bot.add_cog(StatCalc(bot))
