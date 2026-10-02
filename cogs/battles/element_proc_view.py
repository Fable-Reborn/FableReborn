"""Player-facing browser for elemental weapon effects."""

import discord

from utils.elements import ELEMENT_STRENGTHS, normalize_element

from .extensions.element_procs import (
    COMMON_MIN_STARS,
    MAX_STARS,
    MYTHIC_MIN_STARS,
    POWER_WORD_MIN_STARS,
    PROC_DESCRIPTIONS,
    PROC_EMOJI,
    PROC_NAMES,
    ElementProcExtension,
)


class ElementProcView(discord.ui.View):
    def __init__(self, *, author_id, enabled, stars_by_element, combat_elements,
                 equipped_items, emoji_to_element, prefix):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.enabled = enabled
        self.stars_by_element = stars_by_element
        self.prefix = prefix
        self.message = None
        self.emojis = {element: emoji for emoji, element in emoji_to_element.items()}
        self.attack_elements = combat_elements.get("dual_attack_elements") or [
            combat_elements.get("attack_element", "Unknown")
        ]
        current = combat_elements.get("attack_element", "Unknown")
        self.selected_element = current if current in PROC_NAMES else None
        self.weapon_elements = {
            normalize_element(item["element"])
            for item in equipped_items
            if str(item["type"]).lower() != "shield"
        }
        self.element_select = discord.ui.Select(
            placeholder="Choose an element to explore its effects",
            options=[
                discord.SelectOption(
                    label=element,
                    value=element,
                    emoji=self.emoji(element),
                    description=(
                        "Current battle element · " if element in self.attack_elements else ""
                    ) + f"{common} / {mythic}",
                    default=element == self.selected_element,
                )
                for element, (common, mythic) in PROC_NAMES.items()
            ],
        )
        self.element_select.callback = self.select_element
        self.add_item(self.element_select)

    def emoji(self, element):
        return self.emojis.get(element, PROC_EMOJI.get(element, "❔"))

    def element_label(self, element):
        return f"{self.emoji(element)} **{element}**"

    def build_embed(self):
        element = self.selected_element
        current = " / ".join(self.element_label(e) for e in self.attack_elements)
        embed = discord.Embed(
            title="Element Procs · " + (element or "Choose an element"),
            description=(
                f"**Status: {'ON' if self.enabled else 'OFF'}** · Test feature\n"
                f"Your battle attack element: {current}\n"
                "Choose an element below to see its weapon effects."
            ),
            color=discord.Color.gold() if self.enabled else discord.Color.dark_grey(),
        )
        if element:
            stars = min(MAX_STARS, max(0, int(self.stars_by_element.get(element, 0))))
            target = ELEMENT_STRENGTHS[element]
            if element not in self.weapon_elements:
                equipment = f"You have no {element} weapon equipped."
            elif stars < COMMON_MIN_STARS:
                equipment = f"Your equipped {element} weapon has no Starforge stars."
            else:
                equipment = f"Your best equipped {element} weapon: **★{stars}**."
            if element not in self.attack_elements:
                equipment += " This is not your current battle attack element."
            embed.add_field(
                name=f"{self.emoji(element)} {element} · When it activates",
                value=(
                    f"Only on normal attacks with elemental advantage: "
                    f"{self.element_label(element)} → {self.element_label(target)}.\n"
                    f"{equipment}\n"
                    + ("Procs are enabled." if self.enabled else
                       "Procs are OFF; the chances below apply after you enable them.")
                ),
                inline=False,
            )
            common, mythic = PROC_NAMES[element]
            common_rate = ElementProcExtension.common_chance(stars) * 100
            mythic_rate = ElementProcExtension.mythic_chance(element, stars) * 100
            mythic_min = POWER_WORD_MIN_STARS if element == "Light" else MYTHIC_MIN_STARS
            common_status = (
                f"**Your chance: {common_rate:.2f}%** per eligible hit."
                if stars >= COMMON_MIN_STARS else f"**Locked · requires ★{COMMON_MIN_STARS}.**"
            )
            mythic_status = (
                f"**Your chance: {mythic_rate:.2f}%** per eligible hit."
                if stars >= mythic_min else f"**Locked · requires ★{mythic_min}.**"
            )
            common_scale = (
                f"★{COMMON_MIN_STARS}: {ElementProcExtension.common_chance(COMMON_MIN_STARS) * 100:.2f}%"
                f" → ★{MAX_STARS}: {ElementProcExtension.common_chance(MAX_STARS) * 100:.2f}%."
            )
            mythic_scale = (
                f"★{mythic_min}: {ElementProcExtension.mythic_chance(element, mythic_min) * 100:.2f}%"
            )
            if mythic_min < MAX_STARS:
                mythic_scale += f" → ★{MAX_STARS}: {ElementProcExtension.mythic_chance(element, MAX_STARS) * 100:.2f}%"
            embed.add_field(
                name=f"{self.emoji(element)} {common} · Common",
                value=f"{PROC_DESCRIPTIONS[element][0]}\n\n{common_status}\n{common_scale}",
                inline=False,
            )
            embed.add_field(
                name=f"{self.emoji(element)} {mythic} · Mythic",
                value=f"{PROC_DESCRIPTIONS[element][1]}\n\n{mythic_status}\n{mythic_scale}.\n**Cannot trigger against bosses.**",
                inline=False,
            )
        else:
            embed.add_field(
                name="No battle element equipped",
                value="Equip an elemental weapon to use procs. You can still browse all nine elements below.",
                inline=False,
            )
        embed.add_field(
            name="How procs work",
            value=(
                "Only equipped weapons' Starforge stars count; shields do not. "
                "For matching weapons, the highest star level is used. "
                "Mythic is rolled first; if it fails or is unavailable, common is rolled. "
                "Only one new proc can trigger per hit. Pets cannot trigger procs, and class abilities do not trigger them.\n"
                "**PvP:** both players must opt in, including for effects targeting their pets. "
                "**Ice Dragon:** the host's setting applies to the party."
            ),
            inline=False,
        )
        embed.add_field(
            name="Your setting",
            value=f"Enable: `{self.prefix}elementprocs on` · Disable: `{self.prefix}elementprocs off`",
            inline=False,
        )
        embed.set_footer(text="Browsing changes only this guide. Your equipment and battle element stay the same.")
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                f"Open your own element guide with `{self.prefix}elementproc`.", ephemeral=True
            )
            return False
        return True

    async def select_element(self, interaction):
        self.selected_element = self.element_select.values[0]
        for option in self.element_select.options:
            option.default = option.value == self.selected_element
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        self.element_select.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
