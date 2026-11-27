"""Gear crafting menu, laid out like the amulet available screen."""
from __future__ import annotations

import discord

from classes.equipment.access import require_menu_actor
from classes.equipment.definitions import (
    ARCHETYPE_NOUN,
    CRAFT_QUALITY_CAP,
    MATERIAL_LINES,
    MAX_REFINEMENT,
    OPEN_SLOTS,
    RARITIES,
    SLOT_NOUN,
    format_material,
)
from classes.equipment.economy import (
    craft_cost,
    known_recipe_keys,
    parse_recipe_key,
    recipe_progress,
)
from classes.equipment.repository import craft_chest, fetch_discovered_recipes, fetch_materials
from classes.equipment.stats import contribution


LINE_LABELS = {
    "guardian": "Guardian",
    "slayer": "Slayer",
    "vanguard": "Vanguard",
}


def _counts(recipes: list[dict]) -> tuple[int, int]:
    ready = sum(1 for recipe in recipes if recipe["progress"]["state"] == "ready")
    close = sum(1 for recipe in recipes if recipe["progress"]["state"] == "close")
    return ready, close


def _trim(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _blessing(value) -> str:
    return f"+{_trim(float(value) * 100)}%"


def _ward(value) -> str:
    return f"+{_trim(float(value))}"


def _range(low: str, high: str) -> str:
    return f"{low}–{high.lstrip('+')}"


def _craft_preview(recipe: dict) -> str:
    """Short Blessing/Ward range for the selected pattern. Mobile-friendly."""
    rarity = recipe["rarity"]
    archetype = recipe["archetype"]
    slot = recipe["slot"]
    forged_low = contribution(rarity, archetype, 1, 0, slot)
    forged_high = contribution(rarity, archetype, CRAFT_QUALITY_CAP, 0, slot)
    finished = contribution(rarity, archetype, CRAFT_QUALITY_CAP, MAX_REFINEMENT, slot)
    slot_name = SLOT_NOUN.get(slot, slot)
    return (
        f"**{rarity.title()} {slot_name}**\n"
        f"Forged · Blessing {_range(_blessing(forged_low[0]), _blessing(forged_high[0]))} · "
        f"Ward {_range(_ward(forged_low[1]), _ward(forged_high[1]))}\n"
        f"At {CRAFT_QUALITY_CAP} / +{MAX_REFINEMENT} · Blessing {_blessing(finished[0])} · Ward {_ward(finished[1])}\n"
        f"Crafted quality rolls 1–{CRAFT_QUALITY_CAP}. Higher only from crates. Temper later. No crafted enchantments."
    )


class GearRecipeSelect(discord.ui.Select):
    def __init__(self, menu: "GearCraftView"):
        options = []
        for recipe in menu.recipes_for_line():
            state = recipe["progress"]["state"]
            if state == "ready":
                emoji, description = "✅", "Ready to craft"
            elif state == "close":
                emoji, description = "🟡", f"Missing {', '.join(recipe['progress']['missing'])}"
            else:
                emoji, description = "🔴", f"Need {', '.join(recipe['progress']['missing'])}"
            options.append(
                discord.SelectOption(
                    label=f"{recipe['rarity'].title()} {SLOT_NOUN.get(recipe['slot'], recipe['slot'])}",
                    value=recipe["key"],
                    description=description[:100],
                    emoji=emoji,
                    default=recipe["key"] == menu.selected_key,
                )
            )
        if not options:
            options.append(
                discord.SelectOption(
                    label="No patterns discovered",
                    value="none",
                    description="Find a piece in a crate to learn its pattern",
                )
            )
        super().__init__(placeholder="Choose a discovered pattern", options=options[:25], row=1)
        self.menu = menu

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] != "none":
            self.menu.selected_key = self.values[0]
        self.menu.rebuild()
        await interaction.response.edit_message(embed=self.menu.line_embed(), view=self.menu)


class GearCraftView(discord.ui.View):
    def __init__(self, cog, ctx, balances: dict[str, int], discovered: set[str], *, preview: bool = False):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.balances = balances
        self.discovered = discovered
        self.preview = preview
        self.line = None
        self.selected_key = None
        self.message = None
        self.recipes = self._build_recipes()

    def _build_recipes(self) -> list[dict]:
        recipes = []
        for key in known_recipe_keys(self.discovered):
            slot, archetype, rarity = parse_recipe_key(key)
            if slot not in OPEN_SLOTS or rarity not in RARITIES:
                continue
            cost = craft_cost(rarity, archetype)
            recipes.append(
                {
                    "key": key,
                    "slot": slot,
                    "archetype": archetype,
                    "rarity": rarity,
                    "cost": cost,
                    "progress": recipe_progress(cost, self.balances),
                }
            )
        return recipes

    def recipes_for_line(self) -> list[dict]:
        return [recipe for recipe in self.recipes if recipe["archetype"] == self.line]

    def selected_recipe(self) -> dict | None:
        for recipe in self.recipes_for_line():
            if recipe["key"] == self.selected_key:
                return recipe
        return None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await require_menu_actor(self.ctx, interaction, "This crafting menu is not yours.")

    def summary_embed(self) -> discord.Embed:
        ready, close = _counts(self.recipes)
        lines = [f"**Discovered patterns:** {len(self.recipes)}"]
        if ready:
            lines.append(f"🟢 **{ready}** ready to craft")
        if close:
            lines.append(f"🟡 **{close}** almost ready")
        if not ready and not close:
            lines.append("🔴 No discovered armor is ready to craft")
        title = f"{self.ctx.author.display_name}'s Gear Crafting"
        if self.preview:
            title += " — preview"
            lines.insert(0, "Sample wallet. Nothing on this screen is your real stock, and Craft does not forge.")
        embed = discord.Embed(
            title=title,
            description="\n".join(lines),
            color=0x846236,
        )
        if self.preview:
            for line, material_ids in MATERIAL_LINES.items():
                sample = "\n".join(
                    f"{format_material(material_id)}: {self.balances.get(material_id, 0)}"
                    for material_id in material_ids
                )
                embed.add_field(name=f"Example {line.title()}", value=sample, inline=False)
        embed.add_field(
            name="How to use",
            value="Choose an armor line below. Only patterns you have discovered are listed; each found piece teaches its own slot.",
            inline=False,
        )
        return embed

    def line_embed(self) -> discord.Embed:
        noun = ARCHETYPE_NOUN.get(self.line, self.line.title())
        embed = discord.Embed(
            title=f"{LINE_LABELS.get(self.line, self.line.title())} — {noun} armor",
            description="Patterns you have not found yet stay hidden.",
            color=0x846236,
        )
        shown = self.recipes_for_line()
        if not shown:
            embed.add_field(name="None discovered", value="Find a piece of this line to learn that piece's pattern. Each slot is learned on its own.")
            return embed
        grouped: dict[str, list[dict]] = {}
        for recipe in shown:
            grouped.setdefault(recipe["rarity"], []).append(recipe)
        blocks = []
        for rarity in RARITIES:
            recipes = grouped.get(rarity)
            if not recipes:
                continue
            slots = ", ".join(SLOT_NOUN.get(recipe["slot"], recipe["slot"]) for recipe in recipes)
            selected = next((recipe for recipe in recipes if recipe["key"] == self.selected_key), None)
            progress = recipes[0]["progress"]
            block = f"{'▶ ' if selected else ''}**{rarity.title()}** — {slots}\n" + "\n".join(progress["lines"])
            if progress["state"] == "ready":
                block += "\n🟢 **Ready to craft!**"
            elif progress["state"] == "close":
                block += f"\n🟡 **Close!** Missing: {', '.join(progress['missing'])}"
            else:
                block += f"\n🔴 **Need:** {', '.join(progress['missing'])}"
            blocks.append(block)
        field = []
        field_length = 0
        field_index = 0
        for block in blocks:
            addition = len(block) + (2 if field else 0)
            if field and field_length + addition > 900:
                embed.add_field(
                    name="Discovered" if field_index == 0 else "Discovered, continued",
                    value="\n\n".join(field),
                    inline=False,
                )
                field_index += 1
                field = [block]
                field_length = len(block)
            else:
                field.append(block)
                field_length += addition
        if field:
            embed.add_field(
                name="Discovered" if field_index == 0 else "Discovered, continued",
                value="\n\n".join(field),
                inline=False,
            )
        selected = self.selected_recipe()
        if selected:
            embed.add_field(
                name="Craft preview",
                value=_craft_preview(selected)[:1024],
                inline=False,
            )
        return embed

    def rebuild(self):
        for child in list(self.children):
            if isinstance(child, GearRecipeSelect):
                self.remove_item(child)
        if self.line:
            self.add_item(GearRecipeSelect(self))
        recipe = self.selected_recipe()
        self.craft_button.disabled = not recipe or recipe["progress"]["state"] != "ready"

    @discord.ui.select(
        placeholder="Choose an armor line...",
        options=[
            discord.SelectOption(label="Guardian", value="guardian", description="Defensive armor", emoji="🛡️"),
            discord.SelectOption(label="Slayer", value="slayer", description="Offensive armor", emoji="⚔️"),
            discord.SelectOption(label="Vanguard", value="vanguard", description="Balanced armor", emoji="⚖️"),
        ],
        row=0,
    )
    async def select_line(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.line = select.values[0]
        line_recipes = self.recipes_for_line()
        ready = [recipe for recipe in line_recipes if recipe["progress"]["state"] == "ready"]
        self.selected_key = (ready or line_recipes or [{"key": None}])[0]["key"]
        self.rebuild()
        await interaction.response.edit_message(embed=self.line_embed(), view=self)

    @discord.ui.button(label="Craft", style=discord.ButtonStyle.green, disabled=True, row=2)
    async def craft_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        recipe = self.selected_recipe()
        if recipe is None or recipe["progress"]["state"] != "ready":
            return await interaction.response.send_message(
                "That pattern is not ready.",
                ephemeral=True,
            )
        if self.preview:
            return await interaction.response.send_message(
                f"Preview only. {recipe['rarity'].title()} {recipe['archetype'].title()} would forge here. No materials were spent.",
                ephemeral=True,
            )
        await interaction.response.defer()
        async with self.cog.bot.pool.acquire() as conn:
            status, item = await craft_chest(
                conn,
                self.ctx.author.id,
                recipe["rarity"],
                recipe["archetype"],
                slot=recipe["slot"],
            )
        if status == "unknown":
            return await interaction.followup.send("You have not discovered that pattern.", ephemeral=True)
        if status != "crafted":
            return await interaction.followup.send("You no longer have the materials.", ephemeral=True)
        async with self.cog.bot.pool.acquire() as conn:
            self.balances = await fetch_materials(conn, self.ctx.author.id)
            self.discovered = await fetch_discovered_recipes(conn, self.ctx.author.id)
        self.recipes = self._build_recipes()
        self.rebuild()
        await interaction.message.edit(embed=self.line_embed(), view=self)
        await interaction.followup.send(
            f"You forge **{item['name']}** (`{item['id']}`). "
            f"Quality {item['quality']}."
        )

    @discord.ui.button(label="Materials", style=discord.ButtonStyle.blurple, row=3)
    async def materials_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        command = self.ctx.bot.get_command("gear materials")
        await interaction.response.defer()
        await self.ctx.invoke(command)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, row=3)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Gear crafting closed",
            description="Use `$gear available` to open this menu again.",
            color=0x846236,
        )
        await interaction.response.edit_message(embed=embed, view=None)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
