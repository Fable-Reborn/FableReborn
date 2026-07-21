"""
Profile Position Customization Cog
Allows players to customize X,Y positions of elements in their profile images.
"""
import asyncio
import discord
from discord.ext import commands
from typing import Optional, Dict, Any
import json

from classes.bot import Bot
from classes.context import Context
from utils.i18n import _, locale_doc

# Default positions for all customizable elements
DEFAULT_POSITIONS = {
    # Icon positions
    "race_icon_x": 6, "race_icon_y": 150,
    "class_icon_1_x": 6, "class_icon_1_y": 244,
    "class_icon_2_x": 6, "class_icon_2_y": 300,
    "profession_icon_x": 6, "profession_icon_y": 359,
    "guild_rank_icon_x": 610, "guild_rank_icon_y": 3,
    "right_hand_item_icon_x": 262, "right_hand_item_icon_y": 117,
    "left_hand_item_icon_x": 262, "left_hand_item_icon_y": 188,
    "badges_y": 482,  # Badges share Y, but have different X values
    
    # Text positions
    "character_name_x": 12, "character_name_y": 12,
    "level_x": 720, "level_y": 16,
    "marriage_x": 180, "marriage_y": 76,
    "race_x": 70, "race_y": 168,
    "class1_x": 70, "class1_y": 263,
    "class2_x": 70, "class2_y": 320,
    "profession_text_x": 70, "profession_text_y": 379,
    "money_x": 650, "money_y": 283,
    "pvp_wins_x": 650, "pvp_wins_y": 332,
    "god_x": 650, "god_y": 381,
    "adventure_name_x": 345, "adventure_name_y": 298,
    "adventure_time_x": 345, "adventure_time_y": 369,
    "right_hand_item_name_x": 345, "right_hand_item_name_y": 135,
    "right_hand_item_stat_x": 720, "right_hand_item_stat_y": 135,
    "left_hand_item_name_x": 345, "left_hand_item_name_y": 206,
    "left_hand_item_stat_x": 720, "left_hand_item_stat_y": 206,
}

# Human-readable names for the dropdown
ELEMENT_NAMES = {
    "race_icon": "Race Icon",
    "class_icon_1": "Class Icon 1",
    "class_icon_2": "Class Icon 2", 
    "profession_icon": "Profession Icon",
    "guild_rank_icon": "Guild Rank Icon",
    "right_hand_item_icon": "Right Hand Item Icon",
    "left_hand_item_icon": "Left Hand Item Icon",
    "badges": "Badges (Y position only)",
    "character_name": "Character Name Text",
    "level": "Level Text",
    "marriage": "Marriage Text",
    "race": "Race Text",
    "class1": "Class 1 Text",
    "class2": "Class 2 Text",
    "profession_text": "Profession Text",
    "money": "Money Text",
    "pvp_wins": "PVP Wins Text",
    "god": "God Text",
    "adventure_name": "Adventure Name Text",
    "adventure_time": "Adventure Time Text",
    "right_hand_item_name": "Right Hand Item Name",
    "right_hand_item_stat": "Right Hand Item Stat",
    "left_hand_item_name": "Left Hand Item Name",
    "left_hand_item_stat": "Left Hand Item Stat",
}


class CoordinateModal(discord.ui.Modal):
    def __init__(self, customization_view: "ElementSelectView", element_key: str, x: int, y: int):
        super().__init__(title=f"Position {ELEMENT_NAMES[element_key]}"[:45])
        self.customization_view = customization_view
        self.element_key = element_key
        self.x_input = None
        if element_key != "badges":
            self.x_input = discord.ui.TextInput(label="X coordinate (0-800)", default=str(x), max_length=4)
            self.add_item(self.x_input)
        self.y_input = discord.ui.TextInput(label="Y coordinate (0-533)", default=str(y), max_length=4)
        self.add_item(self.y_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            x = int(str(self.x_input.value)) if self.x_input else None
            y = int(str(self.y_input.value))
        except ValueError:
            return await interaction.response.send_message("Coordinates must be whole numbers.", ephemeral=True)
        if y < 0 or y > 533 or (x is not None and (x < 0 or x > 800)):
            return await interaction.response.send_message(
                "Coordinates must remain inside the 800×533 profile canvas.", ephemeral=True
            )
        updates = {"badges_y": y} if self.element_key == "badges" else {
            f"{self.element_key}_x": x,
            f"{self.element_key}_y": y,
        }
        await self.customization_view.update_position(updates)
        await interaction.response.edit_message(
            embed=await self.customization_view.build_embed(
                notice=f"Saved {ELEMENT_NAMES[self.element_key]} at "
                + (f"X {x}, Y {y}." if x is not None else f"Y {y}."),
            ),
            view=self.customization_view,
        )


class ElementSelectView(discord.ui.View):
    def __init__(self, ctx: Context):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.selected_element = None
        
    @discord.ui.select(
        placeholder="Choose an element to customize...",
        options=[
            discord.SelectOption(label=name, value=key) 
            for key, name in list(ELEMENT_NAMES.items())[:25]  # Discord limit
        ]
    )
    async def select_element(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command author can use this.", ephemeral=True)
            return
        
        try:
            self.selected_element = select.values[0]
            x, y = await self.get_current_coordinates(self.selected_element)
            await interaction.response.send_modal(CoordinateModal(self, self.selected_element, x, y))
        except Exception as e:
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This customization panel is not yours.", ephemeral=True)
            return False
        return True

    async def _load_positions(self):
        async with self.ctx.bot.pool.acquire() as conn:
            raw = await conn.fetchval(
                'SELECT custom_positions FROM profile WHERE "user"=$1;',
                self.ctx.author.id,
            )
        return json.loads(raw) if raw else {}

    async def get_current_coordinates(self, element_key):
        positions = await self._load_positions()
        if element_key == "badges":
            return 0, int(positions.get("badges_y", DEFAULT_POSITIONS["badges_y"]))
        return (
            int(positions.get(f"{element_key}_x", DEFAULT_POSITIONS.get(f"{element_key}_x", 0))),
            int(positions.get(f"{element_key}_y", DEFAULT_POSITIONS.get(f"{element_key}_y", 0))),
        )

    async def build_embed(self, notice=None):
        description = "Select an element to edit it in a validated coordinate form."
        if notice:
            description = f"✅ {notice}\n\n{description}"
        embed = discord.Embed(title="🎨 Profile Layout Editor", description=description, color=0x7289DA)
        if self.selected_element:
            x, y = await self.get_current_coordinates(self.selected_element)
            value = f"Y: **{y}**" if self.selected_element == "badges" else f"X: **{x}** • Y: **{y}**"
            embed.add_field(name=ELEMENT_NAMES[self.selected_element], value=value, inline=False)
        embed.add_field(
            name="Controls",
            value="The arrow buttons nudge the selected element by 5 pixels. Preview renders your profile in the channel.",
            inline=False,
        )
        return embed

    async def nudge(self, interaction, dx, dy):
        if not self.selected_element:
            return await interaction.response.send_message("Select an element first.", ephemeral=True)
        x, y = await self.get_current_coordinates(self.selected_element)
        x = max(0, min(800, x + dx))
        y = max(0, min(533, y + dy))
        updates = {"badges_y": y} if self.selected_element == "badges" else {
            f"{self.selected_element}_x": x,
            f"{self.selected_element}_y": y,
        }
        await self.update_position(updates)
        await interaction.response.edit_message(embed=await self.build_embed(notice="Position nudged."), view=self)

    @discord.ui.button(label="←", style=discord.ButtonStyle.secondary, row=1)
    async def left(self, interaction, button):
        await self.nudge(interaction, -5, 0)

    @discord.ui.button(label="↑", style=discord.ButtonStyle.secondary, row=1)
    async def up(self, interaction, button):
        await self.nudge(interaction, 0, -5)

    @discord.ui.button(label="↓", style=discord.ButtonStyle.secondary, row=1)
    async def down(self, interaction, button):
        await self.nudge(interaction, 0, 5)

    @discord.ui.button(label="→", style=discord.ButtonStyle.secondary, row=1)
    async def right(self, interaction, button):
        await self.nudge(interaction, 5, 0)

    @discord.ui.button(label="Reset Element", style=discord.ButtonStyle.secondary, row=2)
    async def reset_element_button(self, interaction, button):
        if not self.selected_element:
            return await interaction.response.send_message("Select an element first.", ephemeral=True)
        await self.reset_to_default()
        await interaction.response.edit_message(embed=await self.build_embed(notice="Element reset to default."), view=self)

    @discord.ui.button(label="Preview Profile", style=discord.ButtonStyle.primary, row=2)
    async def preview_button(self, interaction, button):
        command = self.ctx.bot.get_command("profile")
        await interaction.response.defer()
        await self.ctx.invoke(command)

    @discord.ui.button(label="Reset All", style=discord.ButtonStyle.danger, row=2)
    async def reset_all_button(self, interaction, button):
        command = self.ctx.bot.get_command("profilereset")
        await interaction.response.defer()
        await self.ctx.invoke(command)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary, row=2)
    async def close_button(self, interaction, button):
        await interaction.response.edit_message(view=None)
        self.stop()
    
    async def get_current_position(self, element_key: str) -> str:
        """Get current position for an element"""
        async with self.ctx.bot.pool.acquire() as conn:
            custom_positions_json = await conn.fetchval(
                'SELECT custom_positions FROM profile WHERE "user" = $1',
                self.ctx.author.id
            )
        
        # Parse JSON string to dict
        positions = json.loads(custom_positions_json) if custom_positions_json else {}
        
        if element_key == "badges":
            y = positions.get("badges_y", DEFAULT_POSITIONS["badges_y"])
            return f"Y: {y} (Badges use preset X positions)"
        else:
            x_key = f"{element_key}_x"
            y_key = f"{element_key}_y"
            x = positions.get(x_key, DEFAULT_POSITIONS.get(x_key, 0))
            y = positions.get(y_key, DEFAULT_POSITIONS.get(y_key, 0))
            return f"X: {x}, Y: {y}"
    
    async def process_coordinates(self, input_text: str, element_name: str):
        """Process user coordinate input"""
        if input_text.lower() == "default":
            # Reset to default
            await self.reset_to_default()
            await self.ctx.send(f"✅ {element_name} position reset to default!")
            return
        
        # Parse coordinates
        parts = input_text.split()
        
        if self.selected_element == "badges":
            # Badges only need Y coordinate
            if len(parts) != 1:
                await self.ctx.send("❌ Badges only need Y coordinate. Example: `482`")
                return
            try:
                y = int(parts[0])
                await self.update_position({"badges_y": y})
                await self.ctx.send(f"✅ {element_name} Y position set to {y}!")
            except ValueError:
                await self.ctx.send("❌ Invalid Y coordinate. Please enter a number.")
        else:
            # Regular elements need X,Y
            if len(parts) != 2:
                await self.ctx.send("❌ Please provide X and Y coordinates. Example: `150 200`")
                return
            try:
                x, y = int(parts[0]), int(parts[1])
                x_key = f"{self.selected_element}_x"
                y_key = f"{self.selected_element}_y"
                await self.update_position({x_key: x, y_key: y})
                await self.ctx.send(f"✅ {element_name} position set to X: {x}, Y: {y}!")
            except ValueError:
                await self.ctx.send("❌ Invalid coordinates. Please enter numbers only.")
    
    async def reset_to_default(self):
        """Reset selected element to default position"""
        async with self.ctx.bot.pool.acquire() as conn:
            custom_positions_json = await conn.fetchval(
                'SELECT custom_positions FROM profile WHERE "user" = $1',
                self.ctx.author.id
            ) or '{}'
            
            # Parse JSON string to dict
            custom_positions = json.loads(custom_positions_json)
            
            # Remove custom positions for this element
            if self.selected_element == "badges":
                custom_positions.pop("badges_y", None)
            else:
                x_key = f"{self.selected_element}_x"
                y_key = f"{self.selected_element}_y"
                custom_positions.pop(x_key, None)
                custom_positions.pop(y_key, None)
            
            await conn.execute(
                'UPDATE profile SET custom_positions = $1 WHERE "user" = $2',
                json.dumps(custom_positions), self.ctx.author.id
            )
    
    async def update_position(self, new_positions: Dict[str, int]):
        """Update position in database"""
        async with self.ctx.bot.pool.acquire() as conn:
            custom_positions_json = await conn.fetchval(
                'SELECT custom_positions FROM profile WHERE "user" = $1',
                self.ctx.author.id
            ) or '{}'
            
            # Parse JSON string to dict
            custom_positions = json.loads(custom_positions_json)
            
            custom_positions.update(new_positions)
            
            await conn.execute(
                'UPDATE profile SET custom_positions = $1 WHERE "user" = $2',
                json.dumps(custom_positions), self.ctx.author.id
            )


class ProfileCustomization(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command(name="profilecustom", aliases=["pc"])
    @locale_doc
    async def profile_customize(self, ctx: Context):
        """
        Customize the position of elements in your profile image.
        
        This allows you to move icons and text to different X,Y coordinates
        on your profile background. You can reset any element back to default.
        """
        # Check if user has a character
        async with self.bot.pool.acquire() as conn:
            profile = await conn.fetchrow(
                'SELECT "user" FROM profile WHERE "user" = $1',
                ctx.author.id
            )
        
        if not profile:
            return await ctx.send(_("You don't have a character yet! Use `{prefix}create` first.").format(prefix=ctx.prefix))
        
        view = ElementSelectView(ctx)
        await ctx.send(embed=await view.build_embed(), view=view)

    @commands.command(name="profilereset")
    @locale_doc
    async def profile_reset_all(self, ctx: Context):
        """
        Reset all profile customizations back to default positions.
        """
        async with self.bot.pool.acquire() as conn:
            profile = await conn.fetchrow(
                'SELECT custom_positions FROM profile WHERE "user" = $1',
                ctx.author.id
            )
        
        if not profile:
            return await ctx.send(_("You don't have a character yet!"))
        
        if not profile['custom_positions']:
            return await ctx.send("You don't have any custom positions set!")
        
        # Confirm reset
        embed = discord.Embed(
            title="⚠️ Reset All Customizations?",
            description="This will reset **all** your profile element positions back to defaults.\n\n"
                       "This action cannot be undone!",
            color=0xFF6B6B
        )
        
        view = discord.ui.View(timeout=30)
        
        async def confirm_reset(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("Only the command author can use this.", ephemeral=True)
                return
            
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET custom_positions = $1 WHERE "user" = $2',
                    '{}', ctx.author.id
                )
            
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="✅ Reset Complete",
                    description="All profile customizations have been reset to defaults!",
                    color=0x77DD77
                ),
                view=None
            )
        
        async def cancel_reset(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("Only the command author can use this.", ephemeral=True)
                return
            await interaction.response.edit_message(
                embed=discord.Embed(title="❌ Reset Cancelled", color=0x888888),
                view=None
            )
        
        confirm_btn = discord.ui.Button(label="Yes, Reset All", style=discord.ButtonStyle.danger)
        cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        
        confirm_btn.callback = confirm_reset
        cancel_btn.callback = cancel_reset
        
        view.add_item(confirm_btn)
        view.add_item(cancel_btn)
        
        await ctx.send(embed=embed, view=view)

    @staticmethod
    def get_positions_for_user(custom_positions: Optional[Dict[str, Any]]) -> Dict[str, tuple[int, int]]:
        """
        Get final positions for a user, merging custom with defaults,
        and transforming them into the (x, y) tuple format expected by Okapi.
        This is used by the profile generation code.
        """
        merged_positions = DEFAULT_POSITIONS.copy()
        if custom_positions:
            # Ensure custom_positions also uses string keys if loaded from JSON
            # (though json.loads should handle this if the DB stores it correctly)
            str_key_custom_positions = {str(k): v for k, v in custom_positions.items()} 
            merged_positions.update(str_key_custom_positions)

        transformed_positions: Dict[str, tuple[int, int]] = {}
        for base_name in ELEMENT_NAMES.keys():
            if base_name == "badges":  # Badges only have a Y, Okapi handles X based on index
                # Okapi's `positions` field expects (i64, i64) tuples.
                # If badges_y is the only customizable part and Okapi handles X internally,
                # it shouldn't be in *this* map if it doesn't fit the (x,y) tuple structure.
                # For now, we will omit it from the transformed_positions to avoid type errors.
                # The Rust code seems to look for `body.positions.get("badges_y").map_or(482, |p| p.1))`
                # which suggests it might look for `badges_y` as a key with a tuple value where it uses the .1 (y).
                # This is still a bit ambiguous. Safest is to not send it if it's not a clear (x,y) pair from DEFAULT_POSITIONS.
                # If Okapi needs `badges_y` explicitly in the `positions` map with a tuple, 
                # we might need a dummy X or a different handling.
                # Given the error, let's skip it if it's not a clear (x,y) pair from DEFAULT_POSITIONS.
                continue

            x_key = f"{base_name}_x"
            y_key = f"{base_name}_y"

            # Check if both _x and _y versions exist in merged_positions
            if x_key in merged_positions and y_key in merged_positions:
                x_val = merged_positions[x_key]
                y_val = merged_positions[y_key]
                # Ensure they are integers, as DEFAULT_POSITIONS has ints
                try:
                    transformed_positions[base_name] = (int(x_val), int(y_val))
                except (ValueError, TypeError):
                    # Handle case where conversion might fail, though unlikely with current setup
                    # Log this or raise a more specific error if it happens
                    print(f"Warning: Could not convert positions for {base_name} ({x_val}, {y_val}) to int tuple.")
                    continue # Skip this element if conversion fails
            # else: element might not have separate x/y (e.g. old format) or is intentionally not in DEFAULT_POSITIONS with _x/_y

        return transformed_positions


async def setup(bot: Bot):
    await bot.add_cog(ProfileCustomization(bot))
