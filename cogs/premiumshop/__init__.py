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
import datetime
import re
import discord

from discord.ext import commands

from utils.checks import has_char, is_gm, user_is_patron
from utils.i18n import _, locale_doc
from classes.converters import IntGreaterThan
from cogs.shard_communication import user_on_cooldown as user_cooldown


class PetMindWipeModeSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label="All Pets",
                value="all",
                description="Use 1 wipe on every pet you currently own.",
                emoji="🌪️",
            ),
            discord.SelectOption(
                label="Batch Select",
                value="batch",
                description="Pick multiple pets from dropdown pages.",
                emoji="📚",
            ),
            discord.SelectOption(
                label="Single Pet",
                value="single",
                description="Pick exactly one pet, then confirm it.",
                emoji="🎯",
            ),
        ]
        super().__init__(
            placeholder="Choose how to use your Pet Mind Wipe...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.handle_mode_selection(interaction, self.values[0])


class PetMindWipePetSelect(discord.ui.Select):
    def __init__(self, parent_view, pets, *, multi: bool):
        self.parent_view = parent_view
        self.multi = multi
        options = []

        for pet in pets:
            pet_id = int(pet["id"])
            learned_count = len(
                parent_view.cog._normalize_learned_skills_for_preview(
                    parent_view.pets_cog,
                    pet.get("learned_skills"),
                )
            )
            options.append(
                discord.SelectOption(
                    label=parent_view.format_pet_option_label(str(pet.get("name") or "Unknown"), pet_id),
                    value=str(pet_id),
                    description=(
                        f"Lv {int(pet.get('level') or 1)} | "
                        f"{str(pet.get('element') or 'Unknown')} | "
                        f"{learned_count} learned"
                    )[:100],
                    default=pet_id in parent_view.selected_ids,
                )
            )

        placeholder = (
            "Select one pet to wipe..."
            if not multi
            else "Select pets on this page, then review your batch..."
        )
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1 if not multi else max(1, len(options)),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.handle_pet_selection(
            interaction,
            {int(value) for value in self.values},
        )


class PetMindWipeFlowView(discord.ui.View):
    PAGE_SIZE = 25

    def __init__(self, cog, ctx, pets_cog, pets, wipe_quantity: int, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.ctx = ctx
        self.pets_cog = pets_cog
        self.pets = [dict(pet) for pet in pets]
        self.wipe_quantity = max(0, int(wipe_quantity or 0))
        self.stage = "mode"
        self.mode = None
        self.page = 0
        self.selected_ids = set()
        self.message = None
        self.finished = False
        self._rebuild_items()

    @property
    def max_pages(self):
        return max(1, ((len(self.pets) - 1) // self.PAGE_SIZE) + 1) if self.pets else 1

    def format_pet_option_label(self, pet_name: str, pet_id: int):
        suffix = f" (ID: {pet_id})"
        available = max(1, 100 - len(suffix))
        safe_name = (pet_name or "Unknown").strip() or "Unknown"
        if len(safe_name) > available:
            safe_name = safe_name[: max(1, available - 1)].rstrip() + "…"
        return f"{safe_name}{suffix}"

    def get_current_page_pets(self):
        start_index = self.page * self.PAGE_SIZE
        end_index = start_index + self.PAGE_SIZE
        return self.pets[start_index:end_index]

    def get_selected_pets(self):
        if self.mode == "all":
            return list(self.pets)

        pets_by_id = {int(pet["id"]): pet for pet in self.pets}
        return [
            pets_by_id[pet_id]
            for pet_id in sorted(self.selected_ids)
            if pet_id in pets_by_id
        ]

    def get_preview(self):
        selected_pets = self.get_selected_pets()
        if not selected_pets:
            return None
        return self.cog._build_pet_mind_wipe_plan(self.pets_cog, selected_pets)

    def fit_lines_to_field(self, lines, limit: int = 1000):
        output = []
        used = 0
        for index, line in enumerate(lines):
            addition = len(line) + (1 if output else 0)
            if used + addition > limit:
                remaining = len(lines) - index
                if remaining > 0:
                    overflow_line = f"• ... and {remaining} more"
                    if used + len(overflow_line) + (1 if output else 0) <= limit:
                        output.append(overflow_line)
                break
            output.append(line)
            used += addition
        return output

    def build_embed(self, notice: str = None):
        embed = discord.Embed(
            title="🧠 Pet Mind Wipe",
            color=discord.Color.blurple(),
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(
            name="Inventory",
            value=f"You currently have **{self.wipe_quantity}** Pet Mind Wipe(s).",
            inline=False,
        )

        if notice:
            embed.add_field(name="Notice", value=notice, inline=False)

        if self.stage == "mode":
            embed.description = (
                "Choose whether you want to wipe **all pets**, a **batch**, or a **single** pet."
            )
            embed.add_field(
                name="Modes",
                value=(
                    "🌪️ **All Pets**: targets every pet you currently own.\n"
                    "📚 **Batch Select**: choose multiple pets across dropdown pages.\n"
                    "🎯 **Single Pet**: choose one pet, then confirm it."
                ),
                inline=False,
            )
            embed.set_footer(text="Select a mode below or cancel.")
            return embed

        if self.stage == "select":
            page_pets = self.get_current_page_pets()
            embed.description = (
                "Select one pet from the dropdown."
                if self.mode == "single"
                else "Select any pets on this page, then review the batch when ready."
            )

            if page_pets:
                lines = []
                for pet in page_pets:
                    learned_count = len(
                        self.cog._normalize_learned_skills_for_preview(
                            self.pets_cog,
                            pet.get("learned_skills"),
                        )
                    )
                    marker = "✅ " if int(pet["id"]) in self.selected_ids else ""
                    lines.append(
                        f"{marker}**{pet['name']}** (`{pet['id']}`) - "
                        f"Lv {int(pet.get('level') or 1)} {pet.get('element') or 'Unknown'} - "
                        f"{learned_count} learned"
                    )
                embed.add_field(
                    name=f"Pets Page {self.page + 1}/{self.max_pages}",
                    value="\n".join(self.fit_lines_to_field(lines)),
                    inline=False,
                )

            if self.mode == "batch":
                selected_pets = self.get_selected_pets()
                if selected_pets:
                    selected_lines = [
                        f"• **{pet['name']}** (`{pet['id']}`)"
                        for pet in selected_pets[:10]
                    ]
                    if len(selected_pets) > 10:
                        selected_lines.append(f"• ... and {len(selected_pets) - 10} more")
                    embed.add_field(
                        name=f"Current Batch ({len(selected_pets)} selected)",
                        value="\n".join(self.fit_lines_to_field(selected_lines)),
                        inline=False,
                    )
                embed.set_footer(text="Selections on each page are kept while you browse.")
            else:
                embed.set_footer(text="Pick one pet, or cancel.")

            return embed

        preview = self.get_preview()
        selection_count = len(self.get_selected_pets())
        embed.description = (
            f"Are you sure you want to use **1 Pet Mind Wipe** on **{selection_count}** pet(s)?"
        )

        if preview:
            embed.add_field(
                name="Preview",
                value=(
                    f"Affected: **{preview['affected_count']}**\n"
                    f"Skipped: **{preview['skipped_count']}**\n"
                    f"Refunded: **{preview['refunded_total']} SP**"
                ),
                inline=True,
            )
            if preview["unknown_skill_entries"] > 0:
                embed.add_field(
                    name="Legacy Recovery",
                    value=f"Unknown entries recovered: **{preview['unknown_skill_entries']}**",
                    inline=True,
                )

            target_lines = list(preview["summary_lines"])
            if len(target_lines) > 10:
                target_lines = target_lines[:10] + [
                    f"• ... and {preview['affected_count'] - 10} more pets"
                ]
            if target_lines:
                embed.add_field(
                    name="Target Preview",
                    value="\n".join(self.fit_lines_to_field(target_lines)),
                    inline=False,
                )
            elif preview["skipped_count"] > 0:
                embed.add_field(
                    name="Target Preview",
                    value="All selected pets currently have no learned skills to wipe.",
                    inline=False,
                )

        embed.set_footer(text="Ownership and inventory are checked again on confirm.")
        return embed

    def _add_button(self, *, label: str, style, callback, row: int = 1, disabled: bool = False):
        button = discord.ui.Button(label=label, style=style, row=row, disabled=disabled)
        button.callback = callback
        self.add_item(button)

    def _rebuild_items(self):
        self.clear_items()

        if self.stage == "mode":
            self.add_item(PetMindWipeModeSelect(self))
            self._add_button(
                label="Cancel",
                style=discord.ButtonStyle.secondary,
                callback=self.cancel_flow,
                row=1,
            )
            return

        if self.stage == "select":
            page_pets = self.get_current_page_pets()
            if page_pets:
                self.add_item(
                    PetMindWipePetSelect(
                        self,
                        page_pets,
                        multi=self.mode == "batch",
                    )
                )

            self._add_pagination_buttons()

            if self.mode == "batch":
                self._add_button(
                    label="Review Selection",
                    style=discord.ButtonStyle.success,
                    callback=self.review_batch_selection,
                    row=2,
                    disabled=not self.selected_ids,
                )
                self._add_button(
                    label="Clear Selection",
                    style=discord.ButtonStyle.secondary,
                    callback=self.clear_selection,
                    row=2,
                    disabled=not self.selected_ids,
                )

            self._add_button(
                label="Back",
                style=discord.ButtonStyle.secondary,
                callback=self.back_to_mode,
                row=3,
            )
            self._add_button(
                label="Cancel",
                style=discord.ButtonStyle.danger,
                callback=self.cancel_flow,
                row=3,
            )
            return

        preview = self.get_preview()
        self._add_button(
            label="Confirm Wipe",
            style=discord.ButtonStyle.success,
            callback=self.confirm_wipe,
            row=1,
            disabled=not preview or preview["affected_count"] <= 0,
        )
        self._add_button(
            label="Back",
            style=discord.ButtonStyle.secondary,
            callback=self.back_to_selection,
            row=1,
        )
        self._add_button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            callback=self.cancel_flow,
            row=1,
        )

    def _add_pagination_buttons(self):
        if self.max_pages <= 1:
            return

        self._add_button(
            label="<",
            style=discord.ButtonStyle.primary,
            callback=self.previous_page,
            row=1,
            disabled=self.page <= 0,
        )
        self._add_button(
            label=f"Page {self.page + 1}/{self.max_pages}",
            style=discord.ButtonStyle.secondary,
            callback=self.noop_button,
            row=1,
            disabled=True,
        )
        self._add_button(
            label=">",
            style=discord.ButtonStyle.primary,
            callback=self.next_page,
            row=1,
            disabled=self.page >= self.max_pages - 1,
        )

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "This Pet Mind Wipe menu is not for you.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        if self.finished:
            return

        self.finished = True
        await self.ctx.bot.reset_cooldown(self.ctx)
        for child in self.children:
            child.disabled = True

        if self.message:
            try:
                await self.message.edit(
                    embed=self.build_embed(notice="This Pet Mind Wipe selection expired."),
                    view=self,
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

    async def refresh(self, interaction: discord.Interaction, notice: str = None):
        self._rebuild_items()
        await interaction.response.edit_message(embed=self.build_embed(notice=notice), view=self)

    async def handle_mode_selection(self, interaction: discord.Interaction, mode: str):
        self.mode = mode
        self.page = 0
        self.selected_ids.clear()
        self.stage = "confirm" if mode == "all" else "select"
        await self.refresh(interaction)

    async def handle_pet_selection(self, interaction: discord.Interaction, selected_ids):
        if self.mode == "single":
            self.selected_ids = set(selected_ids)
            self.stage = "confirm"
        else:
            page_ids = {int(pet["id"]) for pet in self.get_current_page_pets()}
            self.selected_ids = (self.selected_ids - page_ids) | set(selected_ids)
        await self.refresh(interaction)

    async def previous_page(self, interaction: discord.Interaction):
        if self.page > 0:
            self.page -= 1
        await self.refresh(interaction)

    async def next_page(self, interaction: discord.Interaction):
        if self.page < self.max_pages - 1:
            self.page += 1
        await self.refresh(interaction)

    async def noop_button(self, interaction: discord.Interaction):
        await interaction.response.defer()

    async def review_batch_selection(self, interaction: discord.Interaction):
        self.stage = "confirm"
        await self.refresh(interaction)

    async def clear_selection(self, interaction: discord.Interaction):
        self.selected_ids.clear()
        await self.refresh(interaction)

    async def back_to_mode(self, interaction: discord.Interaction):
        self.stage = "mode"
        self.mode = None
        self.page = 0
        self.selected_ids.clear()
        await self.refresh(interaction)

    async def back_to_selection(self, interaction: discord.Interaction):
        if self.mode == "all":
            self.stage = "mode"
            self.mode = None
        else:
            self.stage = "select"
        await self.refresh(interaction)

    async def cancel_flow(self, interaction: discord.Interaction):
        self.finished = True
        self.stop()
        await self.ctx.bot.reset_cooldown(self.ctx)
        await interaction.response.edit_message(
            content="Pet Mind Wipe cancelled.",
            embed=None,
            view=None,
        )

    async def confirm_wipe(self, interaction: discord.Interaction):
        pet_ids = None if self.mode == "all" else sorted(self.selected_ids)
        success, message = await self.cog._consume_pet_mind_wipe_targets(
            self.ctx,
            mode=self.mode or "single",
            pet_ids=pet_ids,
        )
        if not success:
            await interaction.response.send_message(f"Error: {message}", ephemeral=True)
            return

        self.finished = True
        self.stop()
        await interaction.response.edit_message(content=message, embed=None, view=None)


class PremiumShop(commands.Cog):
    WEAPON_ELEMENTS = (
        "Light",
        "Dark",
        "Corrupted",
        "Fire",
        "Water",
        "Electric",
        "Nature",
        "Wind",
        "Earth",
    )
    PET_ELEMENTS = (
        "Light",
        "Dark",
        "Corrupted",
        "Fire",
        "Water",
        "Electric",
        "Nature",
        "Wind",
    )

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["dcshop"], brief=_("Show the premium shop"), hidden=True)
    @locale_doc
    async def dragoncoinshop(self, ctx):
        _(
            """Show the premium shop. For a detailed explanation of premium items, check `{prefix}help dragoncoinshop`."""
        )
        # Get user's Dragon Coins from database
        async with self.bot.pool.acquire() as conn:
            dragoncoins = await conn.fetchval(
                'SELECT dragoncoins FROM profile WHERE "user" = $1;',
                ctx.author.id
            )
        
        dragoncoins = dragoncoins or 0
        
        shopembed = discord.Embed(
            title=_("Dragon Coin Shop"),
            description=_(
                "Welcome to the Dragon Coin Shop!\n\n"
                "**Buy:** `{prefix}dragoncoinbuy <item> [amount]`\n"
                "**Currency:** <:dragoncoin:1404860657366728788> Dragon Coins\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ).format(prefix=ctx.clean_prefix),
            colour=discord.Colour.purple(),
        )
        
        shopembed.add_field(
            name=_("Your Dragon Coins"),
            value=_(f"**{dragoncoins}** <:dragoncoin:1404860657366728788>"),
            inline=False,
        )

        def chunk_paragraphs(paragraphs, limit=1024):
            chunks = []
            current = ""
            for paragraph in paragraphs:
                addition = paragraph if not current else f"\n\n{paragraph}"
                if len(current) + len(addition) > limit:
                    if current:
                        chunks.append(current)
                        current = paragraph
                    else:
                        # Fallback: hard-truncate impossible-long single paragraph.
                        chunks.append(paragraph[:limit])
                        current = ""
                else:
                    current += addition
            if current:
                chunks.append(current)
            return chunks

        item_paragraphs = [
            "<:ageup:1473265287238385797> **Pet Age Potion** - 200 <:dragoncoin:1404860657366728788> (`petage`)\n*Instantly age your pet to the next growth stage*",
            "<:finalpotion:1473265347581710346> **Pet Speed Growth Potion** - 300 <:dragoncoin:1404860657366728788> (`petspeed`)\n*Doubles growth speed for a specific pet*",
            "<:SplicePotion:1473266873612107836> **Pet XP Potion** - 1200 <:dragoncoin:1404860657366728788> (`petxp`)\n*Gives a pet permanent x2 pet-care XP multiplier*",
            "🧠 **Pet Mind Wipe** - 1500 <:dragoncoin:1404860657366728788> (`petmindwipe`)\n*Opens a dropdown flow to wipe one pet, a batch, or all pets you own*",
            "🔄 **Pet Element Scroll** - 2200 <:dragoncoin:1404860657366728788> (`petelement`)\n*Changes one pet's element, resets learned skills, and refunds SP. Cannot be used on god pets.*",
            "📜 **Weapon Element Scroll** - 800 <:dragoncoin:1404860657366728788> (`weapelement`)\n*Changes the element of one weapon in your inventory*",
            "<:F_Legendary:1139514868400132116> **Legendary Crate** - 500 <:dragoncoin:1404860657366728788> (`legendary`)\n*Contains items with stats ranging from 41 to 80, may also in rare cases contain dragon coins*",
            "<:f_divine:1169412814612471869> **Divine Crate** - 1000 <:dragoncoin:1404860657366728788> (`divine`)\n*Contains items with stats ranging from 47 to 100*",
            "<:c_mats:1403797590335819897> **Materials Crate** - 450 <:dragoncoin:1404860657366728788> (`materials`)\n*Contains 3-10 random crafting materials*",
            "*More items coming soon...*",
        ]
        item_chunks = chunk_paragraphs(item_paragraphs, limit=1024)
        for index, chunk in enumerate(item_chunks, start=1):
            if index == 1:
                field_name = _("Available Items")
            else:
                field_name = _("Available Items (Page {page})").format(page=index)
            shopembed.add_field(
                name=field_name,
                value=_(chunk),
                inline=False,
            )
        
        shopembed.set_footer(
            text=_("Premium Shop • Use {prefix}dcbuy to purchase").format(
                prefix=ctx.clean_prefix
            )
        )
        # Set thumbnail
        shopembed.set_thumbnail(url="https://i.ibb.co/27724pjY/Chat-GPT-Image-Jan-30-2026-11-06-50-PM-1.png")
        
        await ctx.send(embed=shopembed)



    @has_char()
    @commands.command(aliases=["dcbuy"], brief=_("Buy premium items"), hidden=True)
    @locale_doc
    async def dragoncoinbuy(self, ctx, item: str.lower, *, amount: IntGreaterThan(0) = 1):
        _(
            """`[amount]` - The amount of items to buy; defaults to 1
            `<item>` - The premium item to buy

            Buy one or more premium items from the shop."""
        )
        
        # Get user's Dragon Coins
        async with self.bot.pool.acquire() as conn:
            dragoncoins = await conn.fetchval(
                'SELECT dragoncoins FROM profile WHERE "user" = $1;',
                ctx.author.id
            )
        
        dragoncoins = dragoncoins or 0
        
        # Define available items and their prices with both long and short names
        items = {
            # Short names
            "petage": {"name": "Pet Age Potion", "price": 200, "description": "Instantly age your pet", "short": "petage"},
            "petspeed": {"name": "Pet Speed Growth Potion", "price": 300, "description": "Doubles growth speed for a specific pet", "short": "petspeed"},
            "petxp": {"name": "Pet XP Potion", "price": 1200, "description": "Gives a pet permanent x2 pet-care XP multiplier", "short": "petxp"},
            "petmindwipe": {"name": "Pet Mind Wipe", "price": 1500, "description": "Resets learned pet skills and refunds pet SP", "short": "petmindwipe"},
            "mindwipe": {"name": "Pet Mind Wipe", "price": 1500, "description": "Resets learned pet skills and refunds pet SP", "short": "petmindwipe"},
            "petelement": {"name": "Pet Element Scroll", "price": 2200, "description": "Changes one pet's element and resets pet skills", "short": "petelement"},
            "petelementscroll": {"name": "Pet Element Scroll", "price": 2200, "description": "Changes one pet's element and resets pet skills", "short": "petelement"},
            "weapelement": {"name": "Weapon Element Scroll", "price": 800, "description": "Changes the element of one weapon", "short": "weapelement"},
            "elementscroll": {"name": "Weapon Element Scroll", "price": 800, "description": "Changes the element of one weapon", "short": "weapelement"},
            "legendary": {"name": "Legendary Crate", "price": 500, "description": "Contains items with stats 41-80, may also in rare cases contain dragon coins", "short": "legendary"},
            "divine": {"name": "Divine Crate", "price": 1000, "description": "Contains items with stats 47-100, may also in rare cases contain dragon coins", "short": "divine"},
            "materials": {"name": "Materials Crate", "price": 450, "description": "Contains 3-10 random crafting materials", "short": "materials"},
            # Long names
            "pet age potion": {"name": "Pet Age Potion", "price": 200, "description": "Instantly age your pet", "short": "petage"},
            "pet speed growth potion": {"name": "Pet Speed Growth Potion", "price": 300, "description": "Doubles growth speed for a specific pet", "short": "petspeed"},
            "pet xp potion": {"name": "Pet XP Potion", "price": 1200, "description": "Gives a pet permanent x2 pet-care XP multiplier", "short": "petxp"},
            "pet mind wipe": {"name": "Pet Mind Wipe", "price": 1500, "description": "Resets learned pet skills and refunds pet SP", "short": "petmindwipe"},
            "pet element scroll": {"name": "Pet Element Scroll", "price": 2200, "description": "Changes one pet's element and resets pet skills", "short": "petelement"},
            "pet element change": {"name": "Pet Element Scroll", "price": 2200, "description": "Changes one pet's element and resets pet skills", "short": "petelement"},
            "weapon element scroll": {"name": "Weapon Element Scroll", "price": 800, "description": "Changes the element of one weapon", "short": "weapelement"},
            "legendary crate": {"name": "Legendary Crate", "price": 500, "description": "Contains items with stats 41-80, may also in rare cases contain dragon coins", "short": "legendary"},
            "divine crate": {"name": "Divine Crate", "price": 1000, "description": "Contains items with stats 47-100, may also in rare cases contain dragon coins", "short": "divine"},
            "materials crate": {"name": "Materials Crate", "price": 450, "description": "Contains 3-10 random crafting materials", "short": "materials"}
        }
        
        # Normalize the item input (lowercase and remove extra spaces)
        normalized_item = " ".join(item.lower().split())

        if normalized_item not in items:
            return await ctx.send(_("Invalid item. Available items: petage/pet age potion, petspeed/pet speed growth potion, petxp/pet xp potion, petmindwipe/pet mind wipe, petelement/pet element scroll, weapelement/weapon element scroll, legendary/legendary crate, divine/divine crate, materials/materials crate"))
        
        # Get the short name for processing
        item_data = items[normalized_item]
        item = item_data["short"]
        
        item_data = items[item]
        total_cost = item_data["price"] * amount
        
        if dragoncoins < total_cost:
            return await ctx.send(_("You don't have enough Dragon Coins. You need {cost} but have {current}.").format(
                cost=total_cost, current=dragoncoins
            ))
        
        # Deduct Dragon Coins and add item to inventory
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET dragoncoins = dragoncoins - $1 WHERE "user" = $2;',
                total_cost, ctx.author.id
            )
            
            # Handle different item types
            if item in ["petage", "petspeed", "petxp", "petmindwipe", "petelement", "weapelement"]:
                # Add consumables to user_consumables table
                if item == "petage":
                    consumable_type = 'pet_age_potion'
                elif item == "petspeed":
                    consumable_type = 'pet_speed_growth_potion'
                elif item == "petxp":
                    consumable_type = 'pet_xp_potion'
                elif item == "petmindwipe":
                    consumable_type = 'pet_mind_wipe'
                elif item == "petelement":
                    consumable_type = 'pet_element_scroll'
                elif item == "weapelement":
                    consumable_type = 'weapon_element_scroll'
                else:
                    return await ctx.send(_("Unknown item type."))
                
                # Check if user already has this consumable
                existing = await conn.fetchrow(
                    'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                    ctx.author.id, consumable_type
                )
                
                if existing:
                    # Update existing record
                    await conn.execute(
                        'UPDATE user_consumables SET quantity = quantity + $1 WHERE id = $2;',
                        amount, existing['id']
                    )
                else:
                    # Create new record
                    await conn.execute(
                        'INSERT INTO user_consumables (user_id, consumable_type, quantity) VALUES ($1, $2, $3);',
                        ctx.author.id, consumable_type, amount
                    )
            elif item in ["legendary", "divine", "materials"]:
                # Add crates directly to profile table
                crate_column = f"crates_{item}"
                await conn.execute(
                    f'UPDATE profile SET "{crate_column}" = "{crate_column}" + $1 WHERE "user" = $2;',
                    amount, ctx.author.id
                )
            else:
                return await ctx.send(_("Unknown item type."))
        
        await ctx.send(_("Successfully purchased **{amount}x {item_name}** for **{cost} <:dragoncoin:1404860657366728788>**!").format(
            amount=amount, item_name=item_data["name"], cost=total_cost
        ))


    # ========================================
    # PET CONSUMABLES SECTION
    # ========================================

    def _normalize_learned_skills_for_preview(self, pets_cog, learned_skills):
        return pets_cog.normalize_learned_skills(learned_skills) if pets_cog else []

    def _parse_pet_mind_wipe_targets(self, raw_target_spec: str):
        normalized = " ".join(str(raw_target_spec or "").replace("，", ",").split())
        if not normalized:
            return None, _("Please provide `all`, a pet ID, or a comma-separated list of pet IDs.")

        if normalized.lower() == "all":
            return {"mode": "all", "ids": []}, None

        tokens = [token for token in re.split(r"[\s,]+", normalized) if token]
        if not tokens:
            return None, _("Please provide `all`, a pet ID, or a comma-separated list of pet IDs.")
        if any(token.lower() == "all" for token in tokens):
            return None, _("Use either `all` or specific pet IDs, not both together.")

        pet_ids = []
        seen = set()
        for token in tokens:
            if not token.isdigit():
                return None, _("Pet Mind Wipe targets must be `all` or numeric pet IDs separated by commas/spaces.")
            pet_id = int(token)
            if pet_id <= 0:
                return None, _("Pet IDs must be positive numbers.")
            if pet_id in seen:
                continue
            seen.add(pet_id)
            pet_ids.append(pet_id)

        if not pet_ids:
            return None, _("Please provide at least one valid pet ID.")

        return {"mode": "ids", "ids": pet_ids}, None

    def _normalize_pet_element(self, raw_element: str):
        if not raw_element:
            return None
        normalized = str(raw_element).strip().lower()
        aliases = {
            "corruption": "Corrupted",
            "corrupted": "Corrupted",
            "light": "Light",
            "dark": "Dark",
            "fire": "Fire",
            "water": "Water",
            "electric": "Electric",
            "electricity": "Electric",
            "lightning": "Electric",
            "nature": "Nature",
            "wind": "Wind",
        }
        candidate = aliases.get(normalized)
        if not candidate:
            return None
        return candidate if candidate in self.PET_ELEMENTS else None

    def _canonical_god_pet_name(self, raw_name: str):
        if not raw_name:
            return None

        cleaned = " ".join(
            re.sub(r"\[[^\]]+\]", "", str(raw_name).replace("_", " ").replace("-", " ")).lower().split()
        )
        if cleaned.startswith("ultra "):
            cleaned = cleaned[6:].strip()

        elysia_aliases = {"elysia", "astraea", "asterea"}
        if cleaned in elysia_aliases:
            return "Elysia"
        if cleaned == "sepulchure":
            return "Sepulchure"
        if cleaned == "drakath":
            return "Drakath"
        return None

    def _calculate_pet_skill_reset(self, pets_cog, pet):
        learned_skills = self._normalize_learned_skills_for_preview(
            pets_cog,
            pet.get("learned_skills"),
        )
        skill_tree = pets_cog.SKILL_TREES.get(str(pet.get("element") or ""), {})
        skill_lookup = {}
        for branch_skills in skill_tree.values():
            for skill_data in branch_skills.values():
                skill_name = str(skill_data.get("name", "")).strip()
                if not skill_name:
                    continue
                skill_lookup[skill_name.lower()] = {
                    "cost": max(0, int(skill_data.get("cost", 0) or 0)),
                    "is_battery": "battery life" in skill_name.lower(),
                }

        spent_skill_points = 0
        unknown_count = 0
        battery_active = False
        for learned_name in learned_skills:
            meta = skill_lookup.get(learned_name.lower())
            if not meta:
                unknown_count += 1
                continue

            skill_cost = int(meta["cost"])
            if battery_active:
                if skill_cost >= 4:
                    skill_cost = max(1, skill_cost - 2)
                else:
                    skill_cost = max(1, skill_cost - 1)

            spent_skill_points += skill_cost
            if meta["is_battery"]:
                battery_active = True

        current_skill_points = max(0, int(pet.get("skill_points") or 0))
        pet_level = max(1, int(pet.get("level") or 1))
        earned_skill_points = pet_level // pets_cog.PET_SKILL_POINT_INTERVAL
        rebuilt_skill_points = max(
            int(earned_skill_points),
            int(current_skill_points + spent_skill_points),
        )
        refunded_delta = max(0, int(rebuilt_skill_points - current_skill_points))

        return {
            "learned_skills": learned_skills,
            "spent_skill_points": int(spent_skill_points),
            "unknown_count": int(unknown_count),
            "current_skill_points": current_skill_points,
            "rebuilt_skill_points": int(rebuilt_skill_points),
            "refunded_delta": int(refunded_delta),
        }

    def _build_pet_mind_wipe_plan(self, pets_cog, pets):
        plan = {
            "updates": [],
            "refunded_total": 0,
            "affected_count": 0,
            "skipped_count": 0,
            "unknown_skill_entries": 0,
            "summary_lines": [],
        }

        for pet in pets:
            reset_data = self._calculate_pet_skill_reset(pets_cog, pet)
            plan["unknown_skill_entries"] += reset_data["unknown_count"]

            if not reset_data["learned_skills"] and reset_data["unknown_count"] <= 0:
                plan["skipped_count"] += 1
                continue

            plan["updates"].append((reset_data["rebuilt_skill_points"], int(pet["id"])))
            plan["refunded_total"] += reset_data["refunded_delta"]
            plan["affected_count"] += 1
            plan["summary_lines"].append(
                f"• **{pet['name']}** (`{pet['id']}`): +{reset_data['refunded_delta']} SP -> "
                f"**{reset_data['rebuilt_skill_points']} SP**"
            )

        return plan

    def _format_pet_mind_wipe_success_message(self, plan):
        summary_lines = list(plan["summary_lines"])
        if len(summary_lines) > 10:
            summary_lines = summary_lines[:10] + [
                f"• ... and {plan['affected_count'] - 10} more pets"
            ]

        success_message = (
            f"🧠 **Pet Mind Wipe consumed!**\n\n"
            f"Reset **{plan['affected_count']}** pet(s) and refunded **{plan['refunded_total']} SP** total.\n"
            f"Skipped **{plan['skipped_count']}** pet(s) with no learned skills.\n"
            + ("\n".join(summary_lines))
        )
        if plan["unknown_skill_entries"] > 0:
            success_message += (
                f"\n\nRecovered around **{plan['unknown_skill_entries']}** legacy/unknown skill "
                f"entries while rebuilding SP."
            )

        return success_message

    async def _fetch_owned_pets_for_mind_wipe(self, conn, user_id: int):
        return await conn.fetch(
            """
            SELECT id, name, level, element, skill_points, learned_skills
            FROM monster_pets
            WHERE user_id = $1
            ORDER BY id;
            """,
            user_id,
        )

    async def _consume_pet_mind_wipe_targets(self, ctx, *, mode: str, pet_ids=None):
        pets_cog = self.bot.get_cog("Pets")
        if pets_cog is None:
            return False, _("Pet system is not available right now.")

        async with self.bot.pool.acquire() as conn:
            wipe_item = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id,
                'pet_mind_wipe',
            )
            if not wipe_item or wipe_item['quantity'] < 1:
                return False, _("You don't have any Pet Mind Wipes.")

            if mode == "all":
                pets = await self._fetch_owned_pets_for_mind_wipe(conn, ctx.author.id)
            else:
                normalized_ids = []
                seen = set()
                for pet_id in pet_ids or []:
                    pet_id = int(pet_id)
                    if pet_id <= 0 or pet_id in seen:
                        continue
                    seen.add(pet_id)
                    normalized_ids.append(pet_id)

                if not normalized_ids:
                    return False, _("Please choose at least one pet for this Pet Mind Wipe.")

                pets = await conn.fetch(
                    """
                    SELECT id, name, level, element, skill_points, learned_skills
                    FROM monster_pets
                    WHERE user_id = $1 AND id = ANY($2::bigint[])
                    ORDER BY id;
                    """,
                    ctx.author.id,
                    normalized_ids,
                )

                found_ids = {int(pet["id"]) for pet in pets}
                missing_ids = [str(pid) for pid in normalized_ids if pid not in found_ids]
                if missing_ids:
                    return False, _("These pet IDs were not found in your stable: {ids}").format(
                        ids=", ".join(missing_ids)
                    )

            if not pets:
                return False, _("No matching pets were found for this Pet Mind Wipe.")

            plan = self._build_pet_mind_wipe_plan(pets_cog, pets)
            if not plan["updates"]:
                return False, _("None of the selected pets currently have learned skills to wipe.")

            async with conn.transaction():
                await conn.executemany(
                    """
                    UPDATE monster_pets
                    SET learned_skills = '[]'::jsonb, skill_tree_progress = '{}'::jsonb, skill_points = $1
                    WHERE id = $2;
                    """,
                    plan["updates"],
                )
                await conn.execute(
                    'UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;',
                    wipe_item['id'],
                )

        return True, self._format_pet_mind_wipe_success_message(plan)

    async def start_pet_mind_wipe_flow(self, ctx):
        pets_cog = self.bot.get_cog("Pets")
        if pets_cog is None:
            return False, _("Pet system is not available right now.")

        async with self.bot.pool.acquire() as conn:
            wipe_item = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id,
                'pet_mind_wipe',
            )
            if not wipe_item or wipe_item['quantity'] < 1:
                return False, _("You don't have any Pet Mind Wipes.")

            pets = await self._fetch_owned_pets_for_mind_wipe(conn, ctx.author.id)

        if not pets:
            return False, _("You do not own any pets.")

        view = PetMindWipeFlowView(
            self,
            ctx,
            pets_cog,
            pets,
            wipe_item["quantity"],
        )
        message = await ctx.send(embed=view.build_embed(), view=view)
        view.message = message
        return True, None
    
    async def consume_pet_age_potion(self, ctx, pet_id: int):
        """
        Function to handle pet age potion consumption.
        Called by the consume command in profile cog.
        """
        # Check if user has the potion
        async with self.bot.pool.acquire() as conn:
            potion = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id, 'pet_age_potion'
            )
            
            if not potion or potion['quantity'] < 1:
                return False, _("You don't have any Pet Age Potions.")
            
            # Check if pet exists and belongs to user
            pet = await conn.fetchrow(
                "SELECT * FROM monster_pets WHERE id = $1 AND user_id = $2",
                pet_id, ctx.author.id
            )
            
            if not pet:
                return False, _("Pet not found or doesn't belong to you.")
            
            # Check if pet is already adult
            if pet["growth_stage"] == "adult":
                return False, _("This pet is already fully grown!")
            
            # Define growth stages (same as in pets cog)
            growth_stages = {
                1: {"stage": "baby", "growth_time": 2, "stat_multiplier": 0.25, "hunger_modifier": 1.0},
                2: {"stage": "juvenile", "growth_time": 2, "stat_multiplier": 0.50, "hunger_modifier": 0.8},
                3: {"stage": "young", "growth_time": 1, "stat_multiplier": 0.75, "hunger_modifier": 0.6},
                4: {"stage": "adult", "growth_time": None, "stat_multiplier": 1.0, "hunger_modifier": 0.0},
            }
            
            current_index = pet["growth_index"]
            next_stage_index = current_index + 1
            
            if next_stage_index not in growth_stages:
                return False, _("Pet cannot grow further.")
            
            stage_data = growth_stages[next_stage_index]
            
            # Calculate new stats based on multiplier ratio
            old_multiplier = growth_stages[current_index]["stat_multiplier"]
            new_multiplier = stage_data["stat_multiplier"]
            multiplier_ratio = new_multiplier / old_multiplier
            
            new_hp = pet["hp"] * multiplier_ratio
            new_attack = pet["attack"] * multiplier_ratio
            new_defense = pet["defense"] * multiplier_ratio
            
            # Calculate new growth time if not adult
            if stage_data["growth_time"] is not None:
                import datetime
                growth_time_interval = datetime.timedelta(days=stage_data["growth_time"])
                new_growth_time = datetime.datetime.utcnow() + growth_time_interval
            else:
                new_growth_time = None
            
            # Update the pet
            if new_growth_time is not None:
                await conn.execute(
                    """
                    UPDATE monster_pets
                    SET 
                        growth_stage = $1,
                        growth_time = $2,
                        hp = $3,
                        attack = $4,
                        defense = $5,
                        growth_index = $6
                    WHERE 
                        "id" = $7
                    """,
                    stage_data["stage"],
                    new_growth_time,
                    new_hp,
                    new_attack,
                    new_defense,
                    next_stage_index,
                    pet_id,
                )
            else:
                await conn.execute(
                    """
                    UPDATE monster_pets
                    SET 
                        growth_stage = $1,
                        growth_time = NULL,
                        hp = $2,
                        attack = $3,
                        defense = $4,
                        growth_index = $5
                    WHERE 
                        "id" = $6
                    """,
                    stage_data["stage"],
                    new_hp,
                    new_attack,
                    new_defense,
                    next_stage_index,
                    pet_id,
                )
            
            # Consume one potion
            await conn.execute(
                'UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;',
                potion['id']
            )
            
            # Return success with message
            success_message = (
                f"**{pet['name']}** has grown into a **{stage_data['stage'].capitalize()}**!\n\n"
                f"**New Stats:**\n"
                f"• HP: {round(new_hp)}\n"
                f"• Attack: {round(new_attack)}\n"
                f"• Defense: {round(new_defense)}"
            )
            
            return True, success_message

    async def consume_pet_xp_potion(self, ctx, pet_id: int):
        """
        Function to handle pet XP potion consumption.
        Called by the consume command in profile cog.
        """
        # Check if user has the potion
        async with self.bot.pool.acquire() as conn:
            potion = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id, 'pet_xp_potion'
            )
            
            if not potion or potion['quantity'] < 1:
                return False, _("You don't have any Pet XP Potions.")
            
            # Check if pet exists and belongs to user
            pet = await conn.fetchrow(
                "SELECT * FROM monster_pets WHERE id = $1 AND user_id = $2",
                pet_id, ctx.author.id
            )
            
            if not pet:
                return False, _("Pet not found or doesn't belong to you.")
            
            # Check if pet already has XP multiplier
            if pet.get('xp_multiplier', 1.0) > 1.0:
                return False, _("This pet already has an XP multiplier active!")
            
            # Consume one potion
            await conn.execute(
                'UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;',
                potion['id']
            )
            
            # Apply x2 XP multiplier to the pet permanently
            await conn.execute(
                'UPDATE monster_pets SET xp_multiplier = 2.0 WHERE id = $1;',
                pet_id
            )
        
        success_message = (
            f"🔮 **Pet XP Potion consumed!**\n\n"
            f"**{pet['name']}** now has **x2 XP permanently!**\n"
            f"This pet will gain double XP from pet care activities (feed/play/treat/train)."
        )
        
        return True, success_message

    async def consume_pet_speed_growth_potion(self, ctx, pet_id: int):
        """
        Function to handle pet speed growth potion consumption.
        Called by the consume command in profile cog.
        """
        # Check if user has the potion
        async with self.bot.pool.acquire() as conn:
            potion = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id, 'pet_speed_growth_potion'
            )
            
            if not potion or potion['quantity'] < 1:
                return False, _("You don't have any Pet Speed Growth Potions.")
            
            # Check if pet exists and belongs to user
            pet = await conn.fetchrow(
                "SELECT * FROM monster_pets WHERE id = $1 AND user_id = $2",
                pet_id, ctx.author.id
            )
            
            if not pet:
                return False, _("Pet not found or doesn't belong to you.")
            
            # Check if pet is already adult (can't apply speed boost to adult pets)
            if pet['growth_stage'] == 'adult':
                return False, _("This pet is already an adult and cannot grow further.")
            
            # Consume one potion
            await conn.execute(
                'UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;',
                potion['id']
            )
            
            # Apply speed growth effect to the pet and recalculate current growth time
            if pet['growth_time'] is not None:
                # Calculate remaining time and cut it in half
                remaining_time = pet['growth_time'] - datetime.datetime.utcnow()
                if remaining_time.total_seconds() > 0:
                    # Cut remaining time in half
                    new_growth_time = datetime.datetime.utcnow() + (remaining_time / 2)
                    
                    await conn.execute(
                        'UPDATE monster_pets SET speed_growth_active = TRUE, growth_time = $1 WHERE id = $2;',
                        new_growth_time, pet_id
                    )
                else:
                    # Pet is already ready to grow, just set the flag
                    await conn.execute(
                        'UPDATE monster_pets SET speed_growth_active = TRUE WHERE id = $1;',
                        pet_id
                    )
            else:
                # Pet has no growth time (shouldn't happen for non-adult pets)
                await conn.execute(
                    'UPDATE monster_pets SET speed_growth_active = TRUE WHERE id = $1;',
                    pet_id
                )
        
        success_message = (
            f"<:finalpotion:1398721503268438169> **Pet Speed Growth Potion consumed!**\n\n"
            f"**{pet['name']}** will now grow **2x faster** starting immediately!\n"
            f"Current stage: **{pet['growth_stage'].capitalize()}** - Growth time cut in half!"
        )
        
        return True, success_message

    async def consume_pet_mind_wipe(self, ctx, target_spec: str = None):
        """
        Reset pet skills and refund skill points for one pet, selected pets, or all owned pets.
        Called by the consume command in profile cog.
        """
        if not target_spec:
            return await self.start_pet_mind_wipe_flow(ctx)

        parsed_targets, parse_error = self._parse_pet_mind_wipe_targets(target_spec)
        if parse_error:
            return False, parse_error

        return await self._consume_pet_mind_wipe_targets(
            ctx,
            mode="all" if parsed_targets["mode"] == "all" else "batch",
            pet_ids=parsed_targets["ids"],
        )

    async def consume_pet_element_scroll(self, ctx, pet_id: int, new_element: str):
        """
        Change a pet's element, wipe learned skills, and refund SP for a single owned pet.
        Cannot be used on god pets.
        """
        desired_element = self._normalize_pet_element(new_element)
        if not desired_element:
            valid = ", ".join(self.PET_ELEMENTS)
            return False, _(f"Invalid pet element. Valid elements: {valid}")

        pets_cog = self.bot.get_cog("Pets")
        if pets_cog is None:
            return False, _("Pet system is not available right now.")

        async with self.bot.pool.acquire() as conn:
            scroll = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id,
                'pet_element_scroll',
            )
            if not scroll or scroll['quantity'] < 1:
                return False, _("You don't have any Pet Element Scrolls.")

            pet = await conn.fetchrow(
                """
                SELECT id, name, default_name, level, element, skill_points, learned_skills
                FROM monster_pets
                WHERE id = $1 AND user_id = $2;
                """,
                pet_id,
                ctx.author.id,
            )
            if not pet:
                return False, _("Pet not found or doesn't belong to you.")

            canonical_god_name = self._canonical_god_pet_name(
                pet.get("default_name") or pet.get("name")
            )
            if canonical_god_name:
                return False, _(
                    "Pet Element Scroll cannot be used on god pets like {name}."
                ).format(name=canonical_god_name)

            current_element = self._normalize_pet_element(str(pet.get("element") or ""))
            if current_element == desired_element:
                return False, _("That pet already has this element.")

            reset_data = self._calculate_pet_skill_reset(pets_cog, pet)

            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE monster_pets
                    SET element = $1,
                        learned_skills = '[]'::jsonb,
                        skill_tree_progress = '{}'::jsonb,
                        skill_points = $2
                    WHERE id = $3;
                    """,
                    desired_element,
                    reset_data["rebuilt_skill_points"],
                    pet_id,
                )
                await conn.execute(
                    'UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;',
                    scroll['id'],
                )

        source_element = current_element or str(pet.get("element") or "Unknown")
        success_message = _(
            f"🔄 **Pet Element Scroll consumed!**\n\n"
            f"**{pet['name']}** (ID: `{pet['id']}`) changed from **{source_element}** to **{desired_element}**.\n"
            f"Learned pet skills were wiped and **+{reset_data['refunded_delta']} SP** was refunded."
            f" New total: **{reset_data['rebuilt_skill_points']} SP**."
        )
        if reset_data["unknown_count"] > 0:
            success_message += _(
                f"\nRecovered around **{reset_data['unknown_count']}** legacy/unknown skill entries while rebuilding SP."
            )

        return True, success_message

    @user_cooldown(2764800)  # 32 days cooldown
    @has_char()
    @commands.command(hidden=True, brief=_("Redeem dragon coins based on your tier"))
    @locale_doc
    async def redeemdc(self, ctx):
        _(
            """Redeem dragon coins based on your tier level.
            
            **Tier Rewards:**
            • Tier 1: 350 <:dragoncoin:1404860657366728788>
            • Tier 2: 800 <:dragoncoin:1404860657366728788>
            • Tier 3: 1600 <:dragoncoin:1404860657366728788>
            • Tier 4: 3500 <:dragoncoin:1404860657366728788>
            """
        )
        
        # Get user's tier and current dragon coins
        async with self.bot.pool.acquire() as conn:
            profile = await conn.fetchrow(
                'SELECT tier, dragoncoins FROM profile WHERE "user" = $1;',
                ctx.author.id
            )
            
            if not profile:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You don't have a character profile."))
            
            try:
                tier = int(profile["tier"] or 0)
            except (TypeError, ValueError):
                tier = 0
            current_dragoncoins = profile['dragoncoins'] or 0

        if tier < 1 and await user_is_patron(self.bot, ctx.author, "basic"):
            tier = 1
        
        # Define tier rewards
        tier_rewards = {
            1: 350,
            2: 800,
            3: 1600,
            4: 3500
        }
        
        if tier not in tier_rewards:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You need to be at least Tier 1 to redeem dragon coins."))
        
        coins_to_add = tier_rewards[tier]
        new_total = current_dragoncoins + coins_to_add
        
        # Update dragon coins in database
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET dragoncoins = $1 WHERE "user" = $2;',
                new_total, ctx.author.id
            )
        
        # Create success embed
        embed = discord.Embed(
            title=_("🎉 Dragon Coins Redeemed!"),
            description=_(
                "You have successfully redeemed your tier rewards!\n\n"
                "**Tier {tier} Reward:** +{coins} <:dragoncoin:1404860657366728788>\n"
                "**Previous Balance:** {previous} <:dragoncoin:1404860657366728788>\n"
                "**New Balance:** {new} <:dragoncoin:1404860657366728788>"
            ).format(
                tier=tier,
                coins=coins_to_add,
                previous=current_dragoncoins,
                new=new_total
            ),
            colour=discord.Colour.gold(),
            timestamp=datetime.datetime.utcnow()
        )
        
        embed.set_footer(text=_("Use {prefix}dragoncoinshop to view the shop").format(prefix=ctx.clean_prefix))
        
        await ctx.send(embed=embed)

    @has_char()
    @commands.command(hidden=True, brief=_("Show tier rewards information"))
    @locale_doc
    async def tierrewards(self, ctx):
        _(
            """Show information about tier rewards and dragon coin redemption.
            
            **Tier Rewards:**
            • Tier 1: 300 <:dragoncoin:1404860657366728788>
            • Tier 2: 700 <:dragoncoin:1404860657366728788>
            • Tier 3: 1300 <:dragoncoin:1404860657366728788>
            • Tier 4: 3000 <:dragoncoin:1404860657366728788>
            """
        )
        
        # Get user's current tier
        async with self.bot.pool.acquire() as conn:
            tier = await conn.fetchval(
                'SELECT tier FROM profile WHERE "user" = $1;',
                ctx.author.id
            )

        try:
            tier = int(tier or 0)
        except (TypeError, ValueError):
            tier = 0

        if tier < 1 and await user_is_patron(self.bot, ctx.author, "basic"):
            tier = 1
        
        embed = discord.Embed(
            title=_("🏆 Tier Rewards Information"),
            description=_(
                "Redeem dragon coins based on your tier level!\n\n"
                "**Available Rewards:**\n"
                "• **Tier 1:** 300 <:dragoncoin:1404860657366728788>\n"
                "• **Tier 2:** 700 <:dragoncoin:1404860657366728788>\n"
                "• **Tier 3:** 1300 <:dragoncoin:1404860657366728788>\n"
                "• **Tier 4:** 3000 <:dragoncoin:1404860657366728788>\n\n"
                "**Your Current Tier:** {tier}\n"
                "**Command:** `{prefix}redeemcoins`\n"
                "**Cooldown:** 32 days"
            ).format(tier=tier, prefix=ctx.clean_prefix),
            colour=discord.Colour.gold(),
            timestamp=datetime.datetime.utcnow()
        )
        
        embed.set_footer(text=_("Use {prefix}redeemcoins to claim your rewards").format(prefix=ctx.clean_prefix))
        embed.set_thumbnail(url=f"{self.bot.BASE_URL}/business.png")
        
        await ctx.send(embed=embed)

    async def open_materials_crate(self, ctx, return_details: bool = False):
        """
        Function to handle materials crate opening.
        Called by the open command in crates cog.
        """
        # Check if user has materials crates
        async with self.bot.pool.acquire() as conn:         
            # Get amuletcrafting cog to access resource generation
            amulet_cog = self.bot.get_cog('AmuletCrafting')
            if not amulet_cog:
                if return_details:
                    return False, "AmuletCrafting system not available.", []
                return False, "AmuletCrafting system not available."
            
            # Generate 3-10 random materials
            import random
            material_count = random.randint(3, 10)
            
            # Get random materials using the amuletcrafting system
            materials_gained = []
            for _ in range(material_count):
                resource = amulet_cog.get_random_resource()
                if resource:
                    # Give the material to the user
                    await amulet_cog.give_crafting_resource(ctx.author.id, resource, 1)
                    materials_gained.append(resource)
            
        material_count = len(materials_gained)
        materials_display = [resource.replace('_', ' ').title() for resource in materials_gained]
        
        success_message = (
            f"<:c_mats:1398983405516882002> **Materials Crate opened!**\n\n"
            f"You found **{material_count}** crafting materials:\n"
            f"• {', '.join(materials_display)}"
        )

        if return_details:
            return True, success_message, materials_gained
        return True, success_message

    def _normalize_weapon_element(self, raw_element: str):
        if not raw_element:
            return None
        normalized = str(raw_element).strip().lower()
        aliases = {
            "corruption": "Corrupted",
            "corrupted": "Corrupted",
            "light": "Light",
            "dark": "Dark",
            "fire": "Fire",
            "water": "Water",
            "electric": "Electric",
            "electricity": "Electric",
            "nature": "Nature",
            "wind": "Wind",
            "earth": "Earth",
        }
        candidate = aliases.get(normalized)
        if not candidate:
            return None
        return candidate if candidate in self.WEAPON_ELEMENTS else None

    async def consume_weapon_element_scroll(self, ctx, item_id: int, new_element: str):
        """
        Function to handle weapon element scroll consumption.
        Called by the consume command in profile cog.
        """
        desired_element = self._normalize_weapon_element(new_element)
        if not desired_element:
            valid = ", ".join(self.WEAPON_ELEMENTS)
            return False, _(f"Invalid element. Valid elements: {valid}")

        async with self.bot.pool.acquire() as conn:
            scroll = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id,
                'weapon_element_scroll'
            )
            if not scroll or scroll['quantity'] < 1:
                return False, _("You don't have any Weapon Element Scrolls.")

            weapon = await conn.fetchrow(
                'SELECT id, name, type, element FROM allitems WHERE id = $1 AND owner = $2;',
                item_id,
                ctx.author.id
            )
            if not weapon:
                return False, _("Weapon not found or doesn't belong to you.")
            if str(weapon["type"]).lower() == "shield":
                return False, _("That item is a shield. Weapon Element Scroll can only be used on weapons.")

            current_element = (weapon["element"] or "Unknown").capitalize()
            if current_element == desired_element:
                return False, _("That weapon already has this element.")

            async with conn.transaction():
                await conn.execute(
                    'UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;',
                    scroll['id']
                )
                await conn.execute(
                    'UPDATE allitems SET element = $1 WHERE id = $2;',
                    desired_element,
                    item_id
                )

        success_message = _(
            f"📜 **Weapon Element Scroll consumed!**\n\n"
            f"**{weapon['name']}** (ID: `{weapon['id']}`) changed from **{current_element}** to **{desired_element}**."
        )
        return True, success_message


async def setup(bot):
    await bot.add_cog(PremiumShop(bot)) 
