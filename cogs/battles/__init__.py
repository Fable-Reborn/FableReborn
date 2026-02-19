import asyncio
import datetime
import json
import math
import os
import random
import traceback
from decimal import Decimal, ROUND_HALF_UP
from collections import deque

import discord
from utils import misc as rpgtools
from discord.ext import commands, tasks
from discord.ui import View, Button, Select, select
from discord.enums import ButtonStyle

from .factory import BattleFactory
from .settings import BattleSettings
from .utils import create_hp_bar
from .core.team import Team
from .core.combatant import Combatant
from classes.classes import from_string as class_from_string
from classes.converters import IntGreaterThan
from classes.items import ItemType, Hand
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils.checks import has_char, has_money, is_gm
from utils.i18n import _, locale_doc
from utils.joins import JoinView, SingleJoinView

class PetEggSelect(Select):
    def __init__(self, items, page=0):
        self.items = items
        self.total_pages = max(1, (len(items) + 24) // 25)  # Calculate total pages (25 items per page)
        self.current_page = min(page, self.total_pages - 1)  # Ensure page is valid
        
        # Get items for current page
        start_idx = self.current_page * 25
        end_idx = min(start_idx + 25, len(items))
        page_items = items[start_idx:end_idx]
        
        options = [
            discord.SelectOption(
                label=f"{start_idx + i + 1}. {item['type'].title()}",
                description=self._safe_description(item),
                value=str(start_idx + i)
            ) for i, item in enumerate(page_items)
        ]
        
        super().__init__(
            placeholder=f"Select a pet/egg to release... (Page {self.current_page + 1}/{self.total_pages})",
            min_values=1,
            max_values=1,
            options=options
        )
    
    def _safe_description(self, item):
        """Create a safe description that won't cause Discord API issues"""
        try:
            # Use a safe default if display_name is missing
            display_name = item.get('display_name', 'Unknown')
            
            # Ensure it's a string
            if not isinstance(display_name, str):
                display_name = str(display_name)
                
            # Limit length and strip any problematic characters
            return display_name[:50].strip()
        except Exception as e:
            print(f"Error creating description: {e}")
            return "Unknown"
    
    async def callback(self, interaction: discord.Interaction):
        # Update the view with the selected item's details
        view = self.view
        if interaction.user.id != view.author.id:
            return await interaction.response.send_message("This is not your selection.", ephemeral=True)
        
        try:
            selected_index = int(self.values[0])
            if selected_index < 0 or selected_index >= len(self.items):
                return await interaction.response.send_message("Invalid selection. Please try again.", ephemeral=True)
                
            item = self.items[selected_index]
            
            # Create an embed with the selected item's details
            embed = self.create_item_embed(item)
            
            # Update the message with the new embed
            try:
                if interaction.response.is_done():
                    if interaction.message:
                        await interaction.message.edit(embed=embed, view=view)
                else:
                    await interaction.response.edit_message(embed=embed, view=view)
            except Exception as e:
                print(f"Error updating message: {e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"There was an error updating the selection. Please try again. {e}", ephemeral=True)
        except Exception as e:
            print(f"Error in PetEggSelect callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"An error occurred while processing your selection. Please try again. {e}", ephemeral=True)
    
    def create_item_embed(self, item):
        if item.get('type') == 'pet':
            return self.create_pet_embed(item)
        else:  # egg
            return self.create_egg_embed(item)
    
    def create_pet_embed(self, pet):
        # Safely get pet name with fallback
        pet_name = pet.get('name') or pet.get('display_name', 'Unnamed Pet')
        
        # Safely get growth stage with fallback
        growth_stage = pet.get('growth_stage', 'baby').lower()
        
        # Stage emoji with fallback
        if growth_stage == "baby":
            stage_emoji = "🍼"
        elif growth_stage == "juvenile":
            stage_emoji = "🌱"
        elif growth_stage == "young":
            stage_emoji = "🐕"
        else:  # adult or any other stage
            stage_emoji = "🦁"
            
        # Element emoji with fallback
        element = pet.get('element', 'Unknown')
        element_emoji = {
            "Fire": "🔥",
            "Water": "💧",
            "Electric": "⚡",
            "Nature": "🌿",
            "Wind": "💨",
            "Light": "✨",
            "Dark": "🌑",
            "Corrupted": "☠️"
        }.get(element, "❓")
        
        # Safely get level with fallback
        level = pet.get('level', 1)
        
        # Create embed with safe attribute access
        embed = discord.Embed(
            title=f"{element_emoji} {pet_name} (Lv. {level})",
            description=f"A {element} type pet",
            color=discord.Color.blue()
        )
        
        # Add fields with safe attribute access
        embed.add_field(name="Growth Stage", value=f"{stage_emoji} {growth_stage.capitalize()}", inline=True)
        embed.add_field(name="IV", value=f"{pet.get('IV', 0)}%", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Empty field for spacing
        
        # Stats with fallbacks
        embed.add_field(name="HP", value=str(pet.get('hp', 0)), inline=True)
        embed.add_field(name="Attack", value=str(pet.get('attack', 0)), inline=True)
        embed.add_field(name="Defense", value=str(pet.get('defense', 0)), inline=True)
        
        # Additional info with safe access
        if 'happiness' in pet:
            embed.add_field(name="Happiness", value=f"{pet['happiness']}%", inline=True)
        if 'hunger' in pet:
            embed.add_field(name="Hunger", value=f"{pet['hunger']}%", inline=True)
        if 'equipped' in pet:
            status = "✅" if pet['equipped'] else "❌"
            embed.add_field(name="Equipped", value=status, inline=True)
            
        # Set thumbnail if URL is available
        if 'url' in pet and pet['url']:
            embed.set_thumbnail(url=pet['url'])
            
        return embed
    
    def create_egg_embed(self, egg):
        # Safely get egg type and element with fallbacks
        egg_type = egg.get('display_name', egg.get('egg_type', 'Unknown Egg'))
        element = egg.get('element', 'Unknown')
        
        # Element emoji with fallback
        element_emoji = {
            "Fire": "🔥",
            "Water": "💧",
            "Electric": "⚡",
            "Nature": "🌿",
            "Wind": "💨",
            "Light": "✨",
            "Dark": "🌑",
            "Corrupted": "☠️"
        }.get(element, "❓")
        
        # Create embed with safe attribute access
        embed = discord.Embed(
            title=f"{element_emoji} {egg_type} Egg",
            description=f"A {element} type egg",
            color=0xADD8E6
        )
        
        # Calculate time until hatch with safe access
        hatch_time = egg.get('hatch_time')
        if hatch_time and isinstance(hatch_time, datetime.datetime):
            time_left = hatch_time - datetime.datetime.utcnow()
            if time_left.total_seconds() > 0:
                hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                time_str = f"{hours}h {minutes}m {seconds}s"
            else:
                time_str = "Ready to hatch!"
        else:
            time_str = "Not specified"
        
        # Add fields with safe attribute access
        embed.add_field(
            name="📊 Stats",
            value=(
                f"**IV:** {egg.get('IV', 0)}%\n"
                f"**HP:** {int(egg.get('hp', 0))}\n"
                f"**Attack:** {int(egg.get('attack', 0))}\n"
                f"**Defense:** {int(egg.get('defense', 0))}"
            ),
            inline=True
        )
        
        embed.add_field(
            name="⏳ Hatch Time",
            value=time_str,
            inline=True
        )
        
        # Add ID if available
        if 'id' in egg:
            embed.set_footer(text=f"ID: {egg['id']}")
        
        # Set thumbnail if URL is available
        if 'url' in egg and egg['url']:
            embed.set_thumbnail(url=egg['url'])
            
        return embed


class PetEggReleaseView(View):
    def __init__(self, author, items, **kwargs):
        super().__init__(**kwargs)
        self.author = author
        self.items = items
        self.value = None
        self.message = None  # Store the message reference
        self.current_page = 0
        self.total_pages = max(1, (len(items) + 24) // 25)  # Calculate total pages (25 items per page)
        
        # Add the select dropdown for the first page
        self.update_select()
        
        # Only add page buttons if there are multiple pages
        if self.total_pages > 1:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="◀️ Previous Page",
                custom_id="prev_page",
                row=2,
                disabled=self.current_page == 0
            ))
            self.prev_page_button = self.children[-1]  # Store reference to the button
            self.prev_page_button.callback = self.prev_page_callback
            
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Next Page ▶️",
                custom_id="next_page",
                row=2,
                disabled=self.current_page >= self.total_pages - 1
            ))
            self.next_page_button = self.children[-1]  # Store reference to the button
            self.next_page_button.callback = self.next_page_callback
    
    def update_select(self):
        # Remove existing select if any
        for item in self.children[:]:
            if isinstance(item, PetEggSelect):
                self.remove_item(item)
        
        # Add new select for current page
        self.select = PetEggSelect(self.items, self.current_page)
        self.add_item(self.select)
    
    async def prev_page_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("This is not your selection.", ephemeral=True)
        
        if self.current_page > 0:
            self.current_page -= 1
            self.update_select()
            
            # Update button states
            if hasattr(self, 'prev_page_button'):
                self.prev_page_button.disabled = self.current_page == 0
            if hasattr(self, 'next_page_button'):
                self.next_page_button.disabled = self.current_page >= self.total_pages - 1
            
            await interaction.response.edit_message(view=self)
    
    async def next_page_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("This is not your selection.", ephemeral=True)
        
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_select()
            
            # Update button states
            if hasattr(self, 'prev_page_button'):
                self.prev_page_button.disabled = self.current_page == 0
            if hasattr(self, 'next_page_button'):
                self.next_page_button.disabled = self.current_page >= self.total_pages - 1
            
            await interaction.response.edit_message(view=self)
    
    @discord.ui.button(label="Release", style=discord.ButtonStyle.danger, row=1, emoji="🗑️")
    async def confirm_release(self, interaction: discord.Interaction, button: Button):
        try:
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("This is not your selection.", ephemeral=True)
                
            if not hasattr(self.select, 'values') or not self.select.values:
                return await interaction.response.send_message("Please select a pet/egg to release first.", ephemeral=True)
                
            # Get the selected item for the confirmation message
            try:
                selected_index = int(self.select.values[0])
                if selected_index < 0 or selected_index >= len(self.items):
                    return await interaction.response.send_message("Invalid selection. Please try again.", ephemeral=True)
                    
                selected_item = self.items[selected_index]
                
                # Get the appropriate name based on item type
                if selected_item.get('type') == 'egg':
                    item_name = selected_item.get('egg_type', selected_item.get('display_name', 'Unknown Egg'))
                    item_type = 'Egg'
                else:
                    item_name = selected_item.get('name', selected_item.get('display_name', 'Unknown Pet'))
                    item_type = selected_item.get('type', 'item').capitalize()
                
                # Show confirmation dialog with item details
                confirm_embed = discord.Embed(
                    title=f"⚠️ Release {item_type}",
                    description=f"Are you sure you want to release **{item_name}**?\n\nThis action cannot be undone!",
                    color=discord.Color.orange()
                )
                
                # Add item details to the confirmation
                if selected_item['type'] == 'pet':
                    confirm_embed.add_field(
                        name="Pet Details",
                        value=f"**Level:** {selected_item.get('growth_stage', 'Unknown')}\n"
                              f"**IV:** {selected_item.get('IV', '?')}%",
                        inline=False
                    )
                else:  # egg
                    confirm_embed.add_field(
                        name="Egg Details",
                        value=f"**Type:** {selected_item.get('egg_type', 'Unknown')}\n"
                              f"**IV:** {selected_item.get('IV', '?')}%",
                        inline=False
                    )
                
                confirm_view = ConfirmView(self.author)
                
                # Send the confirmation message
                await interaction.response.send_message(
                    embed=confirm_embed,
                    view=confirm_view,
                    ephemeral=True
                )
                
                # Wait for confirmation
                await confirm_view.wait()
                
                if confirm_view.value is None:
                    # Timeout
                    await interaction.followup.send("Release timed out. No action taken.", ephemeral=True)
                    return
                    
                if confirm_view.value:  # Confirmed
                    self.value = selected_index
                    self.stop()
                else:  # Cancelled
                    await interaction.followup.send("Release cancelled.", ephemeral=True)
                    
            except Exception as e:
                print(f"Error in confirm_release: {e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message("An error occurred. Please try again.", ephemeral=True)
                
        except Exception as e:
            print(f"Error in confirm_release: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("An error occurred while processing your request. Please try again.", ephemeral=True)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your selection.", ephemeral=True)
            return
            
        self.value = "cancel"
        self.stop()
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your selection.", ephemeral=True)
            return False
        return True
        
    async def on_timeout(self):
        # Disable all buttons on timeout
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass


class ConfirmView(View):
    def __init__(self, author, **kwargs):
        super().__init__(**kwargs)
        self.author = author
        self.value = None
        
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id == self.author.id:
            self.value = True
            self.stop()
            await interaction.message.delete()
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id == self.author.id:
            self.value = False
            self.stop()
            await interaction.message.delete()
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your confirmation.", ephemeral=True)
            return False
        return True

class DialogueView(discord.ui.View):
    def __init__(
        self,
        pages: list[discord.Embed],
        author: discord.User,
        allowed_user_ids: set[int] | None = None,
    ):
        super().__init__(timeout=60)
        self.pages = pages
        self.current_page = 0
        self.author = author
        self.allowed_user_ids = set(allowed_user_ids or {author.id})
        self.allowed_user_ids.add(int(author.id))

    async def update_message(self, interaction: discord.Interaction):
        # If the response hasn't been sent yet, use response.edit_message.
        # Otherwise, use followup.edit_message.
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            # You must supply the message ID of the message that contains the view.
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=self.pages[self.current_page],
                view=self
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow permitted users (author or alt invoker when applicable).
        if interaction.user.id in self.allowed_user_ids:
            return True
        await interaction.response.send_message(
            _("This command was not initiated by you."),
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
        await self.update_message(interaction)

    @discord.ui.button(label="Start Battle", style=discord.ButtonStyle.success)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # End dialogue immediately
        await interaction.response.defer()
        self.stop()

class CouplesDialogueView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], author: discord.User, partner: discord.User):
        super().__init__(timeout=300)  # 5 minute timeout
        self.pages = pages
        self.current_page = 0
        self.author = author
        self.partner = partner
        self.total_pages = len(pages)
        
        # Add page numbers to all embeds and update button states
        self.update_page_footer()
        self.update_button_states()
        
    def update_page_footer(self):
        """Add page numbers to the current embed footer"""
        current_embed = self.pages[self.current_page]
        page_text = f"Page {self.current_page + 1} of {self.total_pages}"
        
        # Preserve existing footer text if any
        if current_embed.footer.text:
            if "Page" not in current_embed.footer.text:
                current_embed.set_footer(text=f"{current_embed.footer.text} | {page_text}")
        else:
            current_embed.set_footer(text=page_text)
    
    def update_button_states(self):
        """Update button disabled states based on current page"""
        # Find the Previous and Next buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.emoji and str(item.emoji) == "⬅️":  # Previous button
                    item.disabled = (self.current_page == 0)
                elif item.emoji and str(item.emoji) == "➡️":  # Next button
                    item.disabled = (self.current_page == self.total_pages - 1)
    
    async def update_message(self, interaction: discord.Interaction):
        """Update the message with the current page"""
        self.update_page_footer()
        self.update_button_states()
        
        if interaction.response.is_done():
            if interaction.message:
                await interaction.message.edit(embed=self.pages[self.current_page], view=self)
        else:
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the couple to interact with these buttons"""
        return interaction.user.id in (self.author.id, self.partner.id)
    
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, emoji="⬅️", row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, emoji="➡️", row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_message(interaction)
    
    @discord.ui.button(label="Begin Battle Together", style=discord.ButtonStyle.success, emoji="💕", row=1)
    async def start_battle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start the battle immediately"""
        self.stop()
        await interaction.response.edit_message(
            content="💕 **The Tower of Eternal Bonds resonates with your love! The battle begins!** 💕", 
            embed=None, 
            view=None
        )

class CouplesDialogueViewOnly(discord.ui.View):
    """View for dialogue-only viewing without battle buttons"""
    def __init__(self, pages: list[discord.Embed], author: discord.User, partner: discord.User):
        super().__init__(timeout=300)  # Longer timeout since it's just for viewing
        self.pages = pages
        self.current_page = 0
        self.author = author
        self.partner = partner
        self.total_pages = len(pages)
        
        # Add page numbers to all embeds and update button states
        self.update_page_footer()
        self.update_button_states()
        
    def update_page_footer(self):
        """Add page numbers to the current embed footer"""
        current_embed = self.pages[self.current_page]
        page_text = f"Page {self.current_page + 1} of {self.total_pages}"
        
        # Preserve existing footer text if any
        if current_embed.footer.text:
            if "Page" not in current_embed.footer.text:
                current_embed.set_footer(text=f"{current_embed.footer.text} | {page_text}")
        else:
            current_embed.set_footer(text=page_text)
    
    def update_button_states(self):
        """Update button disabled states based on current page"""
        # Find the Previous and Next buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.emoji and str(item.emoji) == "⬅️":  # Previous button
                    item.disabled = (self.current_page == 0)
                elif item.emoji and str(item.emoji) == "➡️":  # Next button
                    item.disabled = (self.current_page == self.total_pages - 1)
        
    async def update_message(self, interaction: discord.Interaction):
        """Update the message with the current page"""
        self.update_page_footer()
        self.update_button_states()
        
        if interaction.response.is_done():
            if interaction.message:
                await interaction.message.edit(embed=self.pages[self.current_page], view=self)
        else:
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the couple to interact with these buttons"""
        return interaction.user.id in (self.author.id, self.partner.id)
    
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, emoji="⬅️", row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, emoji="➡️", row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_message(interaction)
    
    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary, emoji="❌", row=0)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close the dialogue viewer"""
        self.stop()
        await interaction.response.edit_message(
            content="📖 **Dialogue closed.** Use `$cbt start` when you're ready to battle together! 💕", 
            embed=None, 
            view=None
        )

class CouplesTowerView(discord.ui.View):
    def __init__(self, author, partner, on_join, on_cancel):
        super().__init__(timeout=120)
        self.author = author
        self.partner = partner
        self.on_join = on_join
        self.on_cancel = on_cancel
        self.joined = False

    @discord.ui.button(label="Join Battle", style=discord.ButtonStyle.success, emoji="⚔️")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.partner.id:
            return await interaction.response.send_message("You are not the partner in this battle.", ephemeral=True)
        
        self.joined = True
        button.disabled = True
        self.children[1].disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()
        await self.on_join()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.author.id, self.partner.id):
            return await interaction.response.send_message("This is not your battle to cancel.", ephemeral=True)
        
        self.joined = False
        self.children[0].disabled = True
        button.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()
        if self.on_cancel:
            await self.on_cancel()

    async def on_timeout(self):
        if not self.joined:
            for item in self.children:
                item.disabled = True
            if self.on_cancel:
                await self.on_cancel()


class PVELocationSelect(Select):
    def __init__(self, locations: list[dict], allowed_user_ids):
        if isinstance(allowed_user_ids, int):
            allowed_ids = {int(allowed_user_ids)}
        else:
            allowed_ids = {
                int(user_id)
                for user_id in (allowed_user_ids or [])
                if user_id is not None
            }
        self.allowed_user_ids = allowed_ids
        self.locations_by_id = {location["id"]: location for location in locations}
        options = []
        for location in locations:
            is_locked = bool(location.get("is_locked", False))
            tier_keys = sorted(
                int(tier) for tier in (location.get("tier_weights", {}) or {}).keys()
            )
            if tier_keys:
                tier_band = (
                    f"T{tier_keys[0]}"
                    if len(tier_keys) == 1
                    else f"T{tier_keys[0]}-T{tier_keys[-1]}"
                )
            else:
                tier_band = "T?"
            god_chance = location.get("god_chance", 0)
            try:
                god_text = f"{float(god_chance):g}%"
            except (TypeError, ValueError):
                god_text = f"{god_chance}%"
            desc = f"Lv {location['unlock_level']}+ | {tier_band} | God {god_text}"
            label = f"🔒 {location['name']}" if is_locked else f"🟢 {location['name']}"
            options.append(
                discord.SelectOption(
                    label=label,
                    value=location["id"],
                    description=desc[:100],
                )
            )

        super().__init__(
            placeholder="Choose a location to hunt...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.allowed_user_ids:
            await interaction.response.send_message(
                "This location selection isn't yours.",
                ephemeral=True,
            )
            return

        view = self.view
        if not isinstance(view, PVELocationView):
            await interaction.response.send_message(
                "Something went wrong with this selection.",
                ephemeral=True,
            )
            return

        selected_id = self.values[0]
        selected_location = self.locations_by_id.get(selected_id)

        if not selected_location:
            await interaction.response.edit_message(
                content="Invalid location selection.",
                view=view,
            )
            return

        if selected_location.get("is_locked"):
            await interaction.response.send_message(
                f"🔒 **{selected_location['name']}** unlocks at level {selected_location['unlock_level']}.",
                ephemeral=True,
            )
            return

        view.selected_location = selected_location
        for child in view.children:
            child.disabled = True

        await interaction.response.edit_message(
            content=f"Searching in **{view.selected_location['name']}**...",
            view=view,
        )
        view.stop()


class PVELocationView(View):
    def __init__(
        self,
        author_id: int,
        locations: list[dict],
        timeout: float = 60.0,
        allowed_user_ids=None,
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        if isinstance(allowed_user_ids, int):
            allowed_ids = {int(allowed_user_ids)}
        else:
            allowed_ids = {
                int(user_id)
                for user_id in (allowed_user_ids or [])
                if user_id is not None
            }
        allowed_ids.add(int(author_id))
        self.allowed_user_ids = allowed_ids
        self.locations = locations
        self.selected_location = None
        self.cancelled = False
        self.message = None
        self.add_item(PVELocationSelect(locations, self.allowed_user_ids))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in self.allowed_user_ids:
            await interaction.response.send_message(
                "This location selection isn't yours.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        emoji="❌",
        row=1,
    )
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        self.cancelled = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="PvE search cancelled.", view=self)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass


class ScoutLocationChoiceSelect(Select):
    RANDOM_VALUE = "__random__"

    def __init__(self, locations: list[dict], allowed_user_ids):
        if isinstance(allowed_user_ids, int):
            allowed_ids = {int(allowed_user_ids)}
        else:
            allowed_ids = {
                int(user_id)
                for user_id in (allowed_user_ids or [])
                if user_id is not None
            }
        self.allowed_user_ids = allowed_ids
        self.locations_by_id = {location["id"]: location for location in locations}

        options = [
            discord.SelectOption(
                label="🎲 Random Unlocked",
                value=self.RANDOM_VALUE,
                description="Roll from any unlocked location each scout.",
            )
        ]

        for location in locations:
            tier_keys = sorted(
                int(tier) for tier in (location.get("tier_weights", {}) or {}).keys()
            )
            if tier_keys:
                tier_band = (
                    f"T{tier_keys[0]}"
                    if len(tier_keys) == 1
                    else f"T{tier_keys[0]}-T{tier_keys[-1]}"
                )
            else:
                tier_band = "T?"
            god_chance = location.get("god_chance", 0)
            try:
                god_text = f"{float(god_chance):g}%"
            except (TypeError, ValueError):
                god_text = f"{god_chance}%"
            desc = f"Lv {location['unlock_level']}+ | {tier_band} | God {god_text}"
            options.append(
                discord.SelectOption(
                    label=location["name"][:100],
                    value=location["id"],
                    description=desc[:100],
                )
            )

        super().__init__(
            placeholder="Choose your scouting location mode...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.allowed_user_ids:
            await interaction.response.send_message(
                "This location selection isn't yours.",
                ephemeral=True,
            )
            return

        view = self.view
        if not isinstance(view, ScoutLocationChoiceView):
            await interaction.response.send_message(
                "Something went wrong with this selection.",
                ephemeral=True,
            )
            return

        selected_value = self.values[0]
        if selected_value == self.RANDOM_VALUE:
            view.use_random_location = True
            view.selected_location = None
            mode_text = "Scouting mode set to **Random Unlocked**."
        else:
            selected_location = self.locations_by_id.get(selected_value)
            if not selected_location:
                await interaction.response.send_message(
                    "Invalid location selection.",
                    ephemeral=True,
                )
                return
            view.use_random_location = False
            view.selected_location = selected_location
            mode_text = (
                f"Scouting mode locked to **{selected_location['name']}**."
            )

        for child in view.children:
            child.disabled = True
        await interaction.response.edit_message(content=mode_text, view=view)
        view.stop()


class ScoutLocationChoiceView(View):
    def __init__(
        self,
        author_id: int,
        locations: list[dict],
        timeout: float = 60.0,
        allowed_user_ids=None,
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        if isinstance(allowed_user_ids, int):
            allowed_ids = {int(allowed_user_ids)}
        else:
            allowed_ids = {
                int(user_id)
                for user_id in (allowed_user_ids or [])
                if user_id is not None
            }
        allowed_ids.add(int(author_id))
        self.allowed_user_ids = allowed_ids
        self.locations = locations
        self.selected_location = None
        self.use_random_location = None
        self.cancelled = False
        self.message = None
        self.add_item(ScoutLocationChoiceSelect(locations, self.allowed_user_ids))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in self.allowed_user_ids:
            await interaction.response.send_message(
                "This location selection isn't yours.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        emoji="❌",
        row=1,
    )
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        self.cancelled = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Scouting cancelled.", view=self)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

class Battles(commands.Cog):
    DRAGON_COIN_DROP_CHANCE_PERCENT = 10
    DRAGON_COIN_DROP_MIN = 2
    DRAGON_COIN_DROP_MAX = 5
    PVE_LEVEL_BRACKET_SIZE = 10
    PVE_MAX_TIER = 10
    PVE_GOD_TIER = 11
    PVE_GOD_ENCOUNTER_LEVEL = 100
    PVE_PER_LEVEL_STAT_SCALE = Decimal("0.02")
    PVE_LEGENDARY_SPAWN_CHANCE = 0.01
    PVE_SPLICE_SAMPLE_PER_GENERATION = 75
    PVE_SPLICE_GENERATIONS = (0,)
    PVE_LOCATIONS = (
        {
            "id": "verdant_outskirts",
            "name": "Verdant Outskirts",
            "unlock_level": 1,
            "god_chance": 0,
            "tier_weights": {1: 65, 2: 30, 3: 5},
        },
        {
            "id": "whisperwood",
            "name": "Whisperwood",
            "unlock_level": 10,
            "god_chance": 0,
            "tier_weights": {2: 55, 3: 35, 4: 10},
        },
        {
            "id": "ashfall_crags",
            "name": "Ashfall Crags",
            "unlock_level": 20,
            "god_chance": 0,
            "tier_weights": {3: 50, 4: 35, 5: 15},
        },
        {
            "id": "sunken_ruins",
            "name": "Sunken Ruins",
            "unlock_level": 30,
            "god_chance": 0,
            "tier_weights": {4: 45, 5: 35, 6: 20},
        },
        {
            "id": "stormfront_ridge",
            "name": "Stormfront Ridge",
            "unlock_level": 40,
            "god_chance": 0,
            "tier_weights": {5: 40, 6: 35, 7: 25},
        },
        {
            "id": "blightfen",
            "name": "Blightfen",
            "unlock_level": 50,
            "god_chance": 1,
            "tier_weights": {6: 43, 7: 35, 8: 20, 10: 2},
        },
        {
            "id": "crystal_expanse",
            "name": "Crystal Expanse",
            "unlock_level": 60,
            "god_chance": 2,
            "tier_weights": {7: 42, 8: 32, 9: 18, 10: 8},
        },
        {
            "id": "voidscar_wastes",
            "name": "Voidscar Wastes",
            "unlock_level": 70,
            "god_chance": 4,
            "tier_weights": {8: 40, 9: 42, 10: 18},
        },
        {
            "id": "pantheon_approach",
            "name": "Pantheon Approach",
            "unlock_level": 80,
            "god_chance": 10,
            "tier_weights": {8: 30, 9: 31, 10: 39},
        },
        {
            "id": "apex_of_ascension",
            "name": "Apex of Ascension",
            "unlock_level": 95,
            "god_chance": 25,
            "tier_weights": {9: 30, 10: 70},
        },
        {
            "id": "omnithrone_sanctum",
            "name": "Omnithrone Sanctum",
            "unlock_level": 100,
            "god_chance": 0,
            "tier_weights": {12: 100},
        },
    )
    GOD_SHARD_ALIGNMENT_EMOJIS = {
        "Chaos": "<:ChaosShard:1472140674215444521>",
        "Evil": "<:EvilShard:1472140682759110716>",
        "Good": "<:GoodShard:1472140691667816479>",
    }
    GOD_SHARD_CANONICAL_NAMES = {
        "Astraea": "Elysia",
        "Asterea": "Elysia",
    }
    GOD_SHARD_DROP_RATES = (0.15, 0.40, 0.10, 0.15, 0.10, 0.10)
    GOD_SHARD_DEFINITIONS = {
        "Elysia": {
            "alignment": "Good",
            "shards": [
                "Dawnheart Shard",
                "Mercy Prism Shard",
                "Sunveil Shard",
                "Lifebloom Shard",
                "Aegis Grace Shard",
                "Seraphic Echo Shard",
            ],
        },
        "Sepulchure": {
            "alignment": "Evil",
            "shards": [
                "Deathmark Shard",
                "Gravebone Shard",
                "Nightveil Shard",
                "Bloodcurse Shard",
                "Ruin Sigil Shard",
                "Voidmourne Shard",
            ],
        },
        "Drakath": {
            "alignment": "Chaos",
            "shards": [
                "Entropy Shard",
                "Wildspark Shard",
                "Riftlash Shard",
                "Discord Shard",
                "Paradox Shard",
                "Tempest Fracture Shard",
            ],
        },
    }
    BATTLE_TOWER_THUMBNAIL_TOKENS = {
        "GOD_ELYSIA": "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/295173706496475136_Elysia_BT12.png",
        "GOD_SEPULCHURE": "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/295173706496475136_Sep_BT12.png",
        "GOD_DRAKATH": "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/295173706496475136_Drakath_BT12.png",
        # Fallback narrator icon for system/voice lines.
        "SYSTEM": "https://i.ibb.co/CWTp4xf/download.jpg",
    }
    DEFAULT_DIALOGUE_AVATAR = "https://ia803204.us.archive.org/4/items/discordprofilepictures/discordblue.png"
    TOWER_KEY_FLOOR_BITS = {22: 1, 23: 2, 25: 4}
    TOWER_KEY_DROP_CHANCE = 0.55
    TOWER_FREEDOM_MILESTONE_GAINS = {10: 1, 20: 1, 25: 1}
    TOWER_FREEDOM_FINALE_MISS_GAIN = 2
    TOWER_FREEDOM_UNLOCK_THRESHOLD = 6

    def __init__(self, bot):
        self.bot = bot
        ids_section = getattr(self.bot.config, "ids", None)
        battles_ids = getattr(ids_section, "battles", {}) if ids_section else {}
        if not isinstance(battles_ids, dict):
            battles_ids = {}
        self.macro_alert_user_id = battles_ids.get("macro_alert_user_id")
        self.debug_user_id = battles_ids.get("debug_user_id")
        self.forceleg = False
        self.battle_factory = BattleFactory(bot)
        self.fighting_players = {}
        
        self.dragon_party_views = []  # Track active dragon party views
        self.battle_settings = BattleSettings(bot)
        self.active_battles = {}
        self.settings = BattleSettings(bot)
        self.currently_in_fight = set()
        
        # Macro detection storage
        self.pve_macro_detection = {}  # {user_id: {"count": int, "timestamp": float}}
        
        self.load_data_files()

        # Element mappings
        self.emoji_to_element = {
            "<:f_corruption:1170192253256466492>": "Corrupted",
            "<:f_water:1170191321571545150>": "Water",
            "<:f_electric:1170191219926777936>": "Electric",
            "<:f_light:1170191258795376771>": "Light",
            "<:f_dark:1170191180164771920>": "Dark",
            "<:f_wind:1170191149802213526>": "Wind",
            "<:f_nature:1170191288361033806>": "Nature",
            "<:f_fire:1170192046632468564>": "Fire"
        }

        # Load data files
        self.load_data_files()
        
        # Initialize database tables
        asyncio.create_task(self.initialize_tables())
    
    async def initialize_tables(self):
        """Initialize database tables for battles"""
        async with self.bot.pool.acquire() as conn:
            # Create couples battle tower table if it doesn't exist
            
            # Create battletower table if it doesn't exist (for regular battle tower)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS battletower (
                    id BIGINT PRIMARY KEY,
                    level INTEGER DEFAULT 1,
                    prestige INTEGER DEFAULT 0,
                    dialoguetoggle BOOLEAN DEFAULT FALSE
                )
            """)
            await conn.execute(
                "ALTER TABLE battletower ADD COLUMN IF NOT EXISTS run_key_bits INTEGER NOT NULL DEFAULT 0;"
            )
            await conn.execute(
                "ALTER TABLE battletower ADD COLUMN IF NOT EXISTS freedom_meter INTEGER NOT NULL DEFAULT 0;"
            )

            # Ice Dragon tables
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ice_dragon_abilities (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    ability_type TEXT NOT NULL,
                    description TEXT,
                    dmg INTEGER,
                    effect TEXT,
                    chance DOUBLE PRECISION,
                    UNIQUE (name, ability_type)
                );
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ice_dragon_stages (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    min_level INTEGER NOT NULL,
                    max_level INTEGER NOT NULL,
                    base_multiplier DOUBLE PRECISION NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    element TEXT NOT NULL DEFAULT 'Water',
                    move_names TEXT[] NOT NULL DEFAULT '{}',
                    passive_names TEXT[] NOT NULL DEFAULT '{}'
                );
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ice_dragon_drops (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    item_type TEXT NOT NULL,
                    min_stat INTEGER NOT NULL,
                    max_stat INTEGER NOT NULL,
                    base_chance DOUBLE PRECISION NOT NULL,
                    max_chance DOUBLE PRECISION NOT NULL,
                    is_global BOOLEAN NOT NULL DEFAULT TRUE,
                    dragon_stage_id INTEGER,
                    element TEXT NOT NULL DEFAULT 'Water',
                    min_level INTEGER,
                    max_level INTEGER
                );
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ice_dragon_presets (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ice_dragon_preset_stages (
                    preset_id INTEGER NOT NULL REFERENCES ice_dragon_presets(id) ON DELETE CASCADE,
                    stage_id INTEGER NOT NULL REFERENCES ice_dragon_stages(id) ON DELETE CASCADE,
                    UNIQUE (preset_id, stage_id)
                );
                """
            )
            await conn.execute("ALTER TABLE ice_dragon_stages ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE;")
            await conn.execute("ALTER TABLE ice_dragon_drops ADD COLUMN IF NOT EXISTS is_global BOOLEAN NOT NULL DEFAULT TRUE;")
            await conn.execute("ALTER TABLE ice_dragon_drops ADD COLUMN IF NOT EXISTS dragon_stage_id INTEGER;")
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS god_pve_shards (
                    user_id BIGINT NOT NULL,
                    god_name TEXT NOT NULL,
                    alignment TEXT NOT NULL,
                    shard_number SMALLINT NOT NULL CHECK (shard_number BETWEEN 1 AND 6),
                    shard_name TEXT NOT NULL,
                    obtained_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, god_name, shard_number)
                );
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_god_pve_shards_user_id ON god_pve_shards(user_id);"
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS god_pet_ownership_locks (
                    user_id BIGINT NOT NULL,
                    god_name TEXT NOT NULL,
                    source_pet_id BIGINT,
                    first_locked_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, god_name)
                );
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_god_pet_ownership_locks_user_id ON god_pet_ownership_locks(user_id);"
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS godofgods (
                    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                    name TEXT NOT NULL,
                    hp INTEGER NOT NULL CHECK (hp > 0),
                    attack INTEGER NOT NULL CHECK (attack > 0),
                    defense INTEGER NOT NULL CHECK (defense > 0),
                    element TEXT NOT NULL,
                    image_url TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pve_preferences (
                    user_id BIGINT PRIMARY KEY,
                    include_splice BOOLEAN NOT NULL DEFAULT FALSE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            monster_pets_exists = await conn.fetchval(
                "SELECT to_regclass('public.monster_pets') IS NOT NULL;"
            )
            if monster_pets_exists:
                await conn.execute(
                    "DROP TRIGGER IF EXISTS trg_track_god_pet_ownership_lock ON monster_pets;"
                )
            await conn.execute("DROP FUNCTION IF EXISTS track_god_pet_ownership_lock();")

            ability_seed = [
                    ("Ice Breath", "move", "Effect: freeze. Damage: 600. Chance: 30%", 600, "freeze", 0.3),
                    ("Tail Sweep", "move", "Effect: aoe. Damage: 400. Chance: 40%", 400, "aoe", 0.4),
                    ("Frost Bite", "move", "Effect: dot. Damage: 300. Chance: 30%", 300, "dot", 0.3),
                    ("Frosty Ice Burst", "move", "Effect: random_debuff. Damage: 800. Chance: 30%", 800, "random_debuff", 0.3),
                    ("Minion Army", "move", "Effect: summon_adds. Damage: 200. Chance: 30%", 200, "summon_adds", 0.3),
                    ("Frost Spears", "move", "Effect: dot. Damage: 500. Chance: 40%", 500, "dot", 0.4),
                    ("Soul Reaver", "move", "Effect: stun. Damage: 1000. Chance: 30%", 1000, "stun", 0.3),
                    ("Death Note", "move", "Effect: curse. Damage: 700. Chance: 30%", 700, "curse", 0.3),
                    ("Dark Shadows", "move", "Effect: aoe_dot. Damage: 900. Chance: 40%", 900, "aoe_dot", 0.4),
                    ("Void Blast", "move", "Effect: aoe_stun. Damage: 1200. Chance: 30%", 1200, "aoe_stun", 0.3),
                    ("Soul Crusher", "move", "Effect: death_mark. Damage: 1000. Chance: 30%", 1000, "death_mark", 0.3),
                    ("Armageddon", "move", "Effect: global_dot. Damage: 800. Chance: 40%", 800, "global_dot", 0.4),
                    ("Reality Shatter", "move", "Effect: dimension_tear. Damage: 1500. Chance: 30%", 1500, "dimension_tear", 0.3),
                    ("Soul Harvest", "move", "Effect: soul_drain. Damage: 1200. Chance: 30%", 1200, "soul_drain", 0.3),
                    ("Void Storm", "move", "Effect: void_explosion. Damage: 1000. Chance: 40%", 1000, "void_explosion", 0.4),
                    ("Time Freeze", "move", "Effect: time_stop. Damage: 2000. Chance: 30%", 2000, "time_stop", 0.3),
                    ("Eternal Damnation", "move", "Effect: eternal_curse. Damage: 1500. Chance: 30%", 1500, "eternal_curse", 0.3),
                    ("Apocalypse", "move", "Effect: world_ender. Damage: 1200. Chance: 40%", 1200, "world_ender", 0.4),
                    ("Ice Armor", "passive", "Reduces all damage by 20%.", None, None, None),
                    ("Corruption", "passive", "Reduces shields/armor by 20%.", None, None, None),
                    ("Void Fear", "passive", "Reduces attack power by 20%.", None, None, None),
                    ("Aspect of death", "passive", "Reduces attack and defense by 30%.", None, None, None),
                    ("Void Corruption", "passive", "Reduces all stats by 25% and inflicts void damage.", None, None, None),
                    ("Soul Devourer", "passive", "Steals 15% of damage dealt as health.", None, None, None),
                    ("Eternal Winter", "passive", "Freezes all healing and reduces damage by 40%.", None, None, None),
                    ("Death's Embrace", "passive", "10% chance to instantly kill on any hit.", None, None, None),
                    ("Reality Bender", "passive", "Randomly negates 50% of attacks and reflects damage.", None, None, None),
                    ("Puppet Strings", "move", "Effect: possess_player. Damage: 400. Chance: 25%", 400, "possess_player", 0.25),
                    ("Beastmind Override", "move", "Effect: possess_pet. Damage: 600. Chance: 20%", 600, "possess_pet", 0.2),
                    ("Dominion of the Void", "move", "Effect: possess_player_and_pet_permanent. Damage: 1200. Chance: 10%", 1200, "possess_player_and_pet_permanent", 0.1),
                    ("Fractured Will", "move", "Effect: shatter_armor. Damage: 650. Chance: 30%", 650, "shatter_armor", 0.3),
                    ("Soul Tax", "move", "Effect: drain_max_hp. Damage: 250. Chance: 30%", 250, "drain_max_hp", 0.3),
                    ("Dread Inversion", "move", "Effect: invert_healing. Damage: 300. Chance: 30%", 300, "invert_healing", 0.3),
                    ("Terror Link", "move", "Effect: damage_link. Damage: 500. Chance: 30%", 500, "damage_link", 0.3),
                    ("Panic Cascade", "move", "Effect: turn_skip_chance. Damage: 300. Chance: 35%", 300, "turn_skip_chance", 0.35),
                    ("Null Phase", "move", "Effect: true_damage_window. Damage: 500. Chance: 20%", 500, "true_damage_window", 0.2),
                    ("Riftstep", "move", "Effect: extra_dragon_turn. Damage: 350. Chance: 25%", 350, "extra_dragon_turn", 0.25),
                ]
            await conn.executemany(
                "INSERT INTO ice_dragon_abilities (name, ability_type, description, dmg, effect, chance) "
                "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (name, ability_type) DO NOTHING",
                ability_seed,
            )

            stages_count = await conn.fetchval("SELECT COUNT(*) FROM ice_dragon_stages")
            if stages_count == 0:
                stage_seed = [
                    ("Frostbite Wyrm", 1, 5, 1.0, "Water", ["Ice Breath", "Tail Sweep", "Frost Bite"], ["Ice Armor"]),
                    ("Corrupted Ice Dragon", 6, 10, 1.15, "Water", ["Frosty Ice Burst", "Minion Army", "Frost Spears"], ["Corruption"]),
                    ("Permafrost", 11, 15, 1.25, "Water", ["Soul Reaver", "Death Note", "Dark Shadows"], ["Void Fear"]),
                    ("Absolute Zero", 16, 20, 1.5, "Water", ["Void Blast", "Soul Crusher", "Armageddon"], ["Aspect of death"]),
                    ("Void Tyrant", 21, 25, 2.0, "Water", ["Reality Shatter", "Soul Harvest", "Void Storm"], ["Void Corruption", "Soul Devourer"]),
                    ("Eternal Frost", 26, 30, 3.0, "Water", ["Time Freeze", "Eternal Damnation", "Apocalypse"], ["Eternal Winter", "Death's Embrace", "Reality Bender"]),
                ]
                await conn.executemany(
                    "INSERT INTO ice_dragon_stages (name, min_level, max_level, base_multiplier, element, move_names, passive_names) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (name) DO NOTHING",
                    stage_seed,
                )

            drops_count = await conn.fetchval("SELECT COUNT(*) FROM ice_dragon_drops")
            if drops_count == 0:
                drops_seed = [
                    ("Frostbite Blade", "Sword", 20, 70, 0.001, 0.005, "Water"),
                    ("Ice Shard Dagger", "Dagger", 20, 70, 0.001, 0.005, "Water"),
                    ("Glacial Axe", "Axe", 20, 70, 0.001, 0.005, "Water"),
                    ("Frozen Spear", "Spear", 20, 70, 0.001, 0.005, "Water"),
                    ("Permafrost Hammer", "Hammer", 20, 70, 0.001, 0.005, "Water"),
                    ("Crystal Wand", "Wand", 20, 70, 0.001, 0.005, "Water"),
                    ("Arctic Shield", "Shield", 20, 70, 0.001, 0.005, "Water"),
                    ("Dragon's Breath Bow", "Bow", 40, 150, 0.0005, 0.0025, "Water"),
                    ("Frost Giant's Scythe", "Scythe", 40, 150, 0.0005, 0.0025, "Water"),
                    ("Absolute Zero Mace", "Mace", 40, 150, 0.0005, 0.0025, "Water"),
                ]
                await conn.executemany(
                    "INSERT INTO ice_dragon_drops (name, item_type, min_stat, max_stat, base_chance, max_chance, element) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (name) DO NOTHING",
                    drops_seed,
                )

    def load_data_files(self):
        """Load all necessary data files for battles"""
        battles_dir = os.path.dirname(__file__)

        # Load battle tower data (base + optional remastered override)
        with open(os.path.join(battles_dir, "battle_tower_data.json"), "r", encoding="utf-8") as f:
            battle_data = json.load(f)

        remastered_battle_path = os.path.join(battles_dir, "battle_tower_data_remastered.json")
        if os.path.exists(remastered_battle_path):
            with open(remastered_battle_path, "r", encoding="utf-8") as f:
                remastered_battle_data = json.load(f)
            for key, value in remastered_battle_data.items():
                if key == "victories" and isinstance(value, dict):
                    battle_data.setdefault("victories", {})
                    battle_data["victories"].update(value)
                else:
                    battle_data[key] = value
        self.battle_data = battle_data

        # Load game levels
        with open(os.path.join(battles_dir, 'game_levels.json'), 'r') as f:
            data = json.load(f)
            self.levels = data['levels']

        # Load dialogue data (base + optional remastered override)
        with open(os.path.join(battles_dir, "battle_tower_dialogues.json"), "r", encoding="utf-8") as f:
            dialogue_data = json.load(f)

        remastered_dialogue_path = os.path.join(battles_dir, "battle_tower_dialogues_remastered.json")
        if os.path.exists(remastered_dialogue_path):
            with open(remastered_dialogue_path, "r", encoding="utf-8") as f:
                remastered_dialogue_data = json.load(f)
            if isinstance(remastered_dialogue_data.get("dialogues"), dict):
                dialogue_data.setdefault("dialogues", {})
                dialogue_data["dialogues"].update(remastered_dialogue_data["dialogues"])
        self.dialogue_data = dialogue_data

        # Load monsters if file exists
        try:
            with open("monsters.json", "r") as f:
                self.monsters_data = json.load(f)
        except FileNotFoundError:
            self.monsters_data = {}

        # Initialize element extension
        from .extensions.elements import ElementExtension
        self.element_ext = ElementExtension()

        # Load couples battle tower data
        with open("cogs/battles/couples_battletower_data.json", "r") as f:
            self.couples_battle_tower_data = json.load(f)
        with open("cogs/battles/couples_game_levels.json", "r") as f:
            self.couples_game_levels = json.load(f)

    def _canonical_god_shard_name(self, god_name: str) -> str:
        return self.GOD_SHARD_CANONICAL_NAMES.get(god_name, god_name)
    
    def _is_god_shard_monster(self, monster) -> bool:
        if not monster:
            return False
        monster_name = self._canonical_god_shard_name((monster.get("name") or "").strip())
        return monster_name in self.GOD_SHARD_DEFINITIONS

    def _tower_required_key_mask(self) -> int:
        mask = 0
        for bit in self.TOWER_KEY_FLOOR_BITS.values():
            mask |= bit
        return mask

    def _tower_key_count(self, run_key_bits: int) -> int:
        return sum(
            1 for bit in self.TOWER_KEY_FLOOR_BITS.values() if (int(run_key_bits) & int(bit))
        )

    def _tower_key_label_for_floor(self, level: int) -> str:
        return {
            22: "First Key",
            23: "Second Key",
            25: "Third Key",
        }.get(level, "Tower Key")

    def _tower_door_label(self, door_key: str) -> str:
        return {
            "door_1_elysia": "Door 1 - Elysia",
            "door_2_sepulchure": "Door 2 - Sepulchure",
            "door_3_drakath": "Door 3 - Drakath",
            "door_4_freedom": "Door 4 - Hidden Freedom Door",
        }.get(door_key, door_key.replace("_", " ").title())

    async def _update_tower_run_progress(self, ctx, level: int):
        freedom_gain = int(self.TOWER_FREEDOM_MILESTONE_GAINS.get(level, 0) or 0)
        has_key_roll = level in self.TOWER_KEY_FLOOR_BITS
        if not freedom_gain and not has_key_roll:
            return

        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(run_key_bits, 0) AS run_key_bits, COALESCE(freedom_meter, 0) AS freedom_meter
                FROM battletower
                WHERE id = $1
                """,
                ctx.author.id,
            )
            if not row:
                return

            old_bits = int(row["run_key_bits"] or 0)
            new_bits = old_bits
            old_meter = int(row["freedom_meter"] or 0)
            new_meter = old_meter + freedom_gain
            key_message = None

            if has_key_roll:
                bit = int(self.TOWER_KEY_FLOOR_BITS[level])
                key_label = self._tower_key_label_for_floor(level)
                if old_bits & bit:
                    key_message = f"🔑 **{key_label}** is already resonating for this run."
                elif random.random() < self.TOWER_KEY_DROP_CHANCE:
                    new_bits = old_bits | bit
                    key_message = (
                        f"🔑 **{key_label}** resonates with your soul. "
                        f"Keys this run: **{self._tower_key_count(new_bits)}/3**."
                    )
                else:
                    key_message = (
                        f"🗝️ **{key_label}** slips away this cycle. "
                        f"Keys this run: **{self._tower_key_count(new_bits)}/3**."
                    )

            if new_bits != old_bits or freedom_gain:
                await conn.execute(
                    """
                    UPDATE battletower
                    SET run_key_bits = $1,
                        freedom_meter = GREATEST(0, COALESCE(freedom_meter, 0) + $2)
                    WHERE id = $3
                    """,
                    new_bits,
                    freedom_gain,
                    ctx.author.id,
                )

        if freedom_gain:
            shown_meter = min(new_meter, self.TOWER_FREEDOM_UNLOCK_THRESHOLD)
            await ctx.send(
                f"🧭 Hidden Door resonance +{freedom_gain} "
                f"(**{shown_meter}/{self.TOWER_FREEDOM_UNLOCK_THRESHOLD}**)."
            )
        if key_message:
            await ctx.send(key_message)

    async def _get_tower_unlock_state(self, user_id: int) -> dict:
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(run_key_bits, 0) AS run_key_bits, COALESCE(freedom_meter, 0) AS freedom_meter
                FROM battletower
                WHERE id = $1
                """,
                user_id,
            )

        run_key_bits = int(row["run_key_bits"]) if row else 0
        freedom_meter = int(row["freedom_meter"]) if row else 0
        key_count = self._tower_key_count(run_key_bits)
        full_key_unlock = (run_key_bits & self._tower_required_key_mask()) == self._tower_required_key_mask()
        meter_unlock = freedom_meter >= self.TOWER_FREEDOM_UNLOCK_THRESHOLD
        door4_unlocked = full_key_unlock or meter_unlock

        return {
            "run_key_bits": run_key_bits,
            "freedom_meter": freedom_meter,
            "key_count": key_count,
            "full_key_unlock": full_key_unlock,
            "meter_unlock": meter_unlock,
            "door4_unlocked": door4_unlocked,
        }

    async def _prompt_finale_door_choice(self, ctx, available_door_keys, endings):
        entries = []
        choices = []

        for door_key in available_door_keys:
            ending = endings.get(door_key)
            if not ending:
                continue
            label = self._tower_door_label(door_key)
            title = ending.get("title", "Unknown Ending")
            entries.append(f"**{label}**\n{title}")
            choices.append(label)

        if not entries:
            return None

        try:
            selected_idx = await self.bot.paginator.Choose(
                title="Choose Your Door",
                placeholder="Pick one door",
                entries=entries,
                choices=choices,
                return_index=True,
                timeout=60,
            ).paginate(ctx)
            return available_door_keys[int(selected_idx)]
        except self.bot.paginator.NoChoice:
            chosen = random.choice(available_door_keys)
            await ctx.send(
                f"You hesitated too long. The tower chooses for you: **{self._tower_door_label(chosen)}**."
            )
            return chosen
        except Exception:
            return random.choice(available_door_keys)

    async def handle_god_shard_drop(self, ctx, monster):
        """Roll and award up to 6 unique god shards on god PvE victories."""
        monster_name_raw = (monster.get("name") or "").strip()
        monster_name = self._canonical_god_shard_name(monster_name_raw)
        definition = self.GOD_SHARD_DEFINITIONS.get(monster_name)
        if not definition:
            return

        alignment = definition["alignment"]
        shard_names = definition["shards"]
        dropped_shards = []

        async with self.bot.pool.acquire() as conn:
            has_god_pet_ownership_lock = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM god_pet_ownership_locks
                    WHERE user_id = $1
                      AND god_name = $2
                )
                """,
                ctx.author.id,
                monster_name,
            )
            if has_god_pet_ownership_lock:
                return

            owned_rows = await conn.fetch(
                """
                SELECT shard_number
                FROM god_pve_shards
                WHERE user_id = $1 AND god_name = $2
                """,
                ctx.author.id,
                monster_name,
            )
            owned_numbers = {row["shard_number"] for row in owned_rows}

            for idx, (shard_name, drop_rate) in enumerate(
                zip(shard_names, self.GOD_SHARD_DROP_RATES), start=1
            ):
                if idx in owned_numbers:
                    continue
                if random.random() >= drop_rate:
                    continue

                inserted = await conn.fetchrow(
                    """
                    INSERT INTO god_pve_shards (
                        user_id, god_name, alignment, shard_number, shard_name
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (user_id, god_name, shard_number) DO NOTHING
                    RETURNING shard_number, shard_name
                    """,
                    ctx.author.id,
                    monster_name,
                    alignment,
                    idx,
                    shard_name,
                )
                if inserted:
                    dropped_shards.append(inserted)

        if dropped_shards:
            dropped_shards.sort(key=lambda s: s["shard_number"])
            lines = [
                f"**Shard {row['shard_number']}**: {row['shard_name']}"
                for row in dropped_shards
            ]
            alignment_emoji = self.GOD_SHARD_ALIGNMENT_EMOJIS.get(alignment, "🧩")
            await ctx.send(
                f"{alignment_emoji} **{monster_name} ({alignment}) Shards Obtained**\n"
                + "\n".join(lines)
                + "\nUse `$inventory` to view your collected shards."
            )

    async def _backfill_god_pet_ownership_locks(self, conn) -> int:
        monster_pets_exists = await conn.fetchval(
            "SELECT to_regclass('public.monster_pets') IS NOT NULL;"
        )
        if not monster_pets_exists:
            return 0

        inserted_count = await conn.fetchval(
            """
            WITH lock_candidates AS (
                SELECT
                    id,
                    user_id,
                    growth_stage,
                    hp,
                    COALESCE(NULLIF(BTRIM(default_name), ''), NULLIF(BTRIM(name), '')) AS raw_name
                FROM monster_pets
            ),
            canonical_candidates AS (
                SELECT
                    user_id,
                    id AS source_pet_id,
                    CASE
                        WHEN raw_name IN ('Astraea', 'Asterea') THEN 'Elysia'
                        ELSE raw_name
                    END AS god_name
                FROM lock_candidates
                WHERE user_id > 0
                  AND growth_stage = 'adult'
                  AND COALESCE(hp, 0) > 10000
                  AND raw_name IS NOT NULL
            ),
            ins AS (
                INSERT INTO god_pet_ownership_locks (user_id, god_name, source_pet_id)
                SELECT user_id, god_name, source_pet_id
                FROM canonical_candidates
                WHERE god_name IN ('Elysia', 'Sepulchure', 'Drakath')
                ON CONFLICT (user_id, god_name) DO NOTHING
                RETURNING 1
            )
            SELECT COUNT(*) FROM ins;
            """
        )
        return int(inserted_count or 0)

    @commands.command(hidden=True, name="lockexistinggodpets")
    @is_gm()
    async def lockexistinggodpets(self, ctx):
        """One-time backfill: lock current qualifying god pet owners."""
        if ctx.author.id != 295173706496475136:
            return await ctx.send("You are not allowed to run this command.")

        async with self.bot.pool.acquire() as conn:
            lock_table_exists = await conn.fetchval(
                "SELECT to_regclass('public.god_pet_ownership_locks') IS NOT NULL;"
            )
            if not lock_table_exists:
                return await ctx.send(
                    "❌ `god_pet_ownership_locks` does not exist yet. Reload `cogs.battles` first."
                )

            inserted = await self._backfill_god_pet_ownership_locks(conn)

        await ctx.send(
            f"✅ Added **{inserted}** ownership lock record(s). "
            "This command is safe to run again; duplicates are ignored."
        )

    @commands.command(name="godlocks", aliases=["godlock"])
    @user_cooldown(10)
    async def godlocks(self, ctx):
        """View your own shard/god lock status."""
        target_user = ctx.author

        async with self.bot.pool.acquire() as conn:
            lock_table_exists = await conn.fetchval(
                "SELECT to_regclass('public.god_pet_ownership_locks') IS NOT NULL;"
            )
            if not lock_table_exists:
                return await ctx.send(
                    "❌ `god_pet_ownership_locks` does not exist yet. Reload `cogs.battles` first."
                )

            locked_rows = await conn.fetch(
                """
                SELECT god_name
                FROM god_pet_ownership_locks
                WHERE user_id = $1
                ORDER BY god_name ASC
                """,
                target_user.id,
            )

            shards_table_exists = await conn.fetchval(
                "SELECT to_regclass('public.god_pve_shards') IS NOT NULL;"
            )
            shard_rows = []
            if shards_table_exists:
                shard_rows = await conn.fetch(
                    """
                    SELECT god_name, shard_number
                    FROM god_pve_shards
                    WHERE user_id = $1
                    ORDER BY god_name ASC, shard_number ASC
                    """,
                    target_user.id,
                )

        locked_gods = {row["god_name"] for row in locked_rows}
        shards_by_god = {}
        for row in shard_rows:
            god_name = row["god_name"]
            shard_num = int(row["shard_number"])
            shards_by_god.setdefault(god_name, set()).add(shard_num)
        embed = discord.Embed(
            title="God Shard Progress",
            description=f"{target_user.mention}\n✅ Owned/locked  |  ❌ Missing",
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"User ID: {target_user.id}")
        embed.set_thumbnail(url=target_user.display_avatar.url)

        for god_name, definition in self.GOD_SHARD_DEFINITIONS.items():
            god_locked = god_name in locked_gods
            owned_numbers = set(range(1, 7)) if god_locked else shards_by_god.get(god_name, set())

            alignment = definition.get("alignment", "Unknown")
            alignment_emoji = self.GOD_SHARD_ALIGNMENT_EMOJIS.get(alignment, "")
            god_mark = "✅" if god_locked else "❌"
            progress_text = "6/6" if god_locked else f"{len(owned_numbers)}/6"

            shard_lines = []
            shard_names = definition.get("shards", [])
            for idx, shard_name in enumerate(shard_names, start=1):
                shard_mark = "✅" if (god_locked or idx in owned_numbers) else "❌"
                shard_lines.append(f"{shard_mark} Shard {idx}: {shard_name}")

            field_name = f"{alignment_emoji} {god_name} [{progress_text}]".strip()
            field_value = f"God Pet: {god_mark}\n" + "\n".join(shard_lines)
            embed.add_field(name=field_name, value=field_value, inline=False)

        await ctx.send(embed=embed)

    @commands.command(hidden=True, name="gmsetgodofgods")
    @is_gm()
    async def gmsetgodofgods(
        self,
        ctx,
        hp: int,
        attack: int,
        defense: int,
        element: str,
        image_url: str,
        *,
        name: str,
    ):
        """[GM only] Upsert the tier-12 God of Gods record in database."""
        if hp <= 0 or attack <= 0 or defense <= 0:
            return await ctx.send("HP, Attack, and Defense must all be positive integers.")

        clean_name = (name or "").strip()
        clean_element = (element or "").strip()
        clean_url = (image_url or "").strip()
        if not clean_name or not clean_element or not clean_url:
            return await ctx.send("Name, element, and image URL are required.")

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO godofgods (id, name, hp, attack, defense, element, image_url, updated_at)
                VALUES (1, $1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    hp = EXCLUDED.hp,
                    attack = EXCLUDED.attack,
                    defense = EXCLUDED.defense,
                    element = EXCLUDED.element,
                    image_url = EXCLUDED.image_url,
                    updated_at = NOW();
                """,
                clean_name,
                int(hp),
                int(attack),
                int(defense),
                clean_element,
                clean_url,
            )

        await ctx.send(
            f"✅ godofgods updated: **{clean_name}** | HP {hp:,} | ATK {attack:,} | DEF {defense:,} | {clean_element}"
        )

    @commands.command()
    @commands.is_owner()
    async def element_debug(self, ctx):
        """View element debug information (Owner only)"""
        try:
            debug_info = self.element_ext.get_debug_info()
            if not debug_info:
                return await ctx.send("No debug information available yet. Try running a battle first.")
                
            # Split into chunks that fit in Discord messages
            for i in range(0, len(debug_info), 1900):
                chunk = debug_info[i:i+1900]
                await ctx.send(f"```\n{chunk}\n```")
        except Exception as e:
            await ctx.send(f"Error getting debug info: {str(e)}")

    @commands.command()
    @commands.is_owner()
    async def macro_debug(self, ctx):
        """View macro detection data (Owner only)"""
        if not self.pve_macro_detection:
            await ctx.send("No macro detection data available yet.")
            return
        
        debug_info = "PVE Macro Detection Data (Count > 12):\n"
        filtered_data = False
        
        for user_id, data in self.pve_macro_detection.items():
            if data["count"] > 48:
                timestamp_str = datetime.datetime.fromtimestamp(data["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
                debug_info += f"User {user_id}: Count={data['count']}, Last Run={timestamp_str}\n"
                filtered_data = True
        
        if not filtered_data:
            await ctx.send("No users with macro detection count > 48 found.")
            return
        
        # Split into chunks if too long
        for i in range(0, len(debug_info), 1900):
            chunk = debug_info[i:i+1900]
            await ctx.send(f"```\n{chunk}\n```")
    
    @commands.command(hidden=True)
    @commands.is_owner()
    async def macro_set(self, ctx, user_id: int, count: int):
        """Manually set macro detection count for a user (Owner only)"""
        current_time = datetime.datetime.now().timestamp()
        
        self.pve_macro_detection[user_id] = {
            "count": count,
            "timestamp": current_time
        }
        
        await ctx.send(f"Set macro detection count for user {user_id} to {count}")
    


    
    async def is_player_in_fight(self, player_id):
        """Check if the player is in a fight based on the dictionary"""
        return player_id in self.fighting_players

    async def add_player_to_fight(self, player_id):
        """Add the player to the fight dictionary with a lock"""
        self.fighting_players[player_id] = asyncio.Lock()
        await self.fighting_players[player_id].acquire()

    async def remove_player_from_fight(self, player_id):
        """Release the lock and remove the player from the fight dictionary"""
        if player_id in self.fighting_players:
            self.fighting_players[player_id].release()
            del self.fighting_players[player_id]

    async def check_pve_macro_detection(self, user_id):
        """
        Check and update PVE macro detection for a user.
        Returns True if macro detected (count >= 12), False otherwise.
        """
        current_time = datetime.datetime.now().timestamp()
        
        if user_id not in self.pve_macro_detection:
            # First time running PVE
            self.pve_macro_detection[user_id] = {
                "count": 1,
                "timestamp": current_time
            }
            return False
        
        user_data = self.pve_macro_detection[user_id]
        time_diff = current_time - user_data["timestamp"]
        
        # Convert minutes to seconds
        thirty_minutes = 30 * 60  # 30 minutes in seconds
        forty_minutes = 40 * 60   # 40 minutes in seconds
        
        if time_diff <= thirty_minutes:
            # Within 30 minutes, increment count by 2
            user_data["count"] += 1
            user_data["timestamp"] = current_time
        elif time_diff <= forty_minutes:
            # Between 30-40 minutes, increment count by 2
            user_data["count"] += 1
            user_data["timestamp"] = current_time
        else:
            # More than 40 minutes, reset counter to 1
            user_data["count"] = 1
            user_data["timestamp"] = current_time
        
        # Check if macro detected (count >= 48)
        if user_data["count"] >= 48:
            print(f"Macro detected for user {user_id}: count={user_data['count']}")
            return True
        
        return False
    
    def get_pve_macro_penalty_level(self, user_id):
        """
        Get the macro penalty level for a user.
        Returns the count if >= 48, otherwise 0.
        """
        if user_id not in self.pve_macro_detection:
            return 0
        
        user_data = self.pve_macro_detection[user_id]
        return user_data["count"] if user_data["count"] >= 48 else 0

    def _get_pve_tier_for_player_level(self, player_level: int) -> int:
        """Map player levels into 10-level PvE tiers."""
        normalized_level = max(1, int(player_level))
        return min(
            self.PVE_MAX_TIER,
            ((normalized_level - 1) // self.PVE_LEVEL_BRACKET_SIZE) + 1,
        )

    def _get_unlocked_pve_locations(self, player_level: int) -> list[dict]:
        """Return all PvE locations unlocked at the player's current level."""
        normalized_level = max(1, int(player_level))
        return [
            dict(location)
            for location in self.PVE_LOCATIONS
            if normalized_level >= int(location["unlock_level"])
        ]

    def _get_pve_location_by_id(self, location_id: str | None) -> dict | None:
        """Look up a PvE location by id."""
        if not location_id:
            return None
        for location in self.PVE_LOCATIONS:
            if location["id"] == location_id:
                return dict(location)
        return None

    def _get_pve_tier_rates_for_location(self, location: dict) -> list[tuple[int, float]]:
        """Return exact encounter rates (percent) per tier for a location."""
        god_chance = float(location.get("god_chance", 0) or 0)
        god_chance = max(0.0, min(100.0, god_chance))

        tier_weights: dict[int, float] = {}
        for tier, weight in (location.get("tier_weights", {}) or {}).items():
            tier_int = int(tier)
            weight_float = float(weight)
            if weight_float <= 0:
                continue
            tier_weights[tier_int] = tier_weights.get(tier_int, 0.0) + weight_float

        rates: list[tuple[int, float]] = []
        non_god_budget = max(0.0, 100.0 - god_chance)
        total_weight = sum(tier_weights.values())

        if total_weight > 0:
            for tier in sorted(tier_weights):
                rate = non_god_budget * (tier_weights[tier] / total_weight)
                rates.append((tier, rate))
        elif non_god_budget > 0:
            fallback_tier = self._get_pve_tier_for_player_level(
                int(location.get("unlock_level", 1))
            )
            rates.append((fallback_tier, non_god_budget))

        if god_chance > 0:
            rates.append((self.PVE_GOD_TIER, god_chance))

        return sorted(rates, key=lambda entry: entry[0])

    def _format_pve_rate_percent(self, value: float) -> str:
        """Format a percentage value for PvE display."""
        rounded = round(float(value), 1)
        if float(rounded).is_integer():
            return f"{int(rounded)}%"
        return f"{rounded:.1f}%"

    def _resolve_pve_location_query(self, query: str | None) -> dict | None:
        """Resolve location by id or name (exact first, then contains match)."""
        if not query:
            return None

        normalized = str(query).strip().lower()
        if not normalized:
            return None

        for location in self.PVE_LOCATIONS:
            if normalized == str(location.get("id", "")).lower():
                return dict(location)

        for location in self.PVE_LOCATIONS:
            if normalized == str(location.get("name", "")).lower():
                return dict(location)

        matches = [
            dict(location)
            for location in self.PVE_LOCATIONS
            if normalized in str(location.get("id", "")).lower()
            or normalized in str(location.get("name", "")).lower()
        ]
        if not matches:
            return None
        return matches[0]

    async def _get_godofgods_monster_data(self) -> dict | None:
        """Fetch the real tier-12 monster data from database storage."""
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT name, hp, attack, defense, element, image_url
                FROM godofgods
                WHERE id = 1
                """
            )
        if not row:
            return None

        return {
            "name": row["name"],
            "hp": int(row["hp"]),
            "attack": int(row["attack"]),
            "defense": int(row["defense"]),
            "element": row["element"],
            "url": row["image_url"],
            "ispublic": True,
        }

    async def _get_public_monsters_by_level(self) -> dict[int, list[dict]]:
        """Load public monster pools, resolving tier-12 combat data from DB."""
        if not self.monsters_data:
            with open("monsters.json", "r") as f:
                self.monsters_data = json.load(f)

        monsters: dict[int, list[dict]] = {}
        tier12_data = await self._get_godofgods_monster_data()

        for level_str, monster_list in self.monsters_data.items():
            try:
                level = int(level_str)
            except (TypeError, ValueError):
                continue

            if level == 12:
                monsters[level] = [dict(tier12_data)] if tier12_data else []
                continue

            public_monsters = [
                dict(monster)
                for monster in monster_list
                if monster.get("ispublic", True)
            ]
            monsters[level] = public_monsters

        return monsters

    def _load_base_pve_monster_names(self) -> set[str]:
        """Load base monsters from monsters.json for splice generation mapping."""
        if not self.monsters_data:
            with open("monsters.json", "r", encoding="utf-8") as f:
                self.monsters_data = json.load(f)

        base_names = set()
        if isinstance(self.monsters_data, dict):
            for monster_list in self.monsters_data.values():
                if not isinstance(monster_list, list):
                    continue
                for monster in monster_list:
                    if not isinstance(monster, dict):
                        continue
                    name = monster.get("name")
                    if isinstance(name, str):
                        cleaned = name.strip()
                        if cleaned:
                            base_names.add(cleaned)
        return base_names

    def _build_splice_generation_map_for_pve(
        self,
        base_monster_names: set[str],
        completed_rows,
    ) -> dict[str, int]:
        """
        Build generation map matching splicegenstats rules.
        Base monsters are generation -1; child generation is max(parent gens) + 1.
        """
        generation_by_name = {name: -1 for name in base_monster_names}
        max_passes = max(1, len(completed_rows) + 1)

        for _ in range(max_passes):
            changed = False
            for row in completed_rows:
                parent1 = row["pet1_default"]
                parent2 = row["pet2_default"]
                result_name = row["result_name"]

                if not isinstance(parent1, str) or not isinstance(parent2, str) or not isinstance(result_name, str):
                    continue

                parent1 = parent1.strip()
                parent2 = parent2.strip()
                result_name = result_name.strip()
                if not parent1 or not parent2 or not result_name:
                    continue

                parent1_gen = generation_by_name.get(parent1)
                parent2_gen = generation_by_name.get(parent2)
                if parent1_gen is None or parent2_gen is None:
                    continue

                child_gen = max(parent1_gen, parent2_gen) + 1
                existing_gen = generation_by_name.get(result_name)

                # Keep canonical base monster mapping untouched.
                if existing_gen == -1:
                    continue

                if existing_gen is None or child_gen < existing_gen:
                    generation_by_name[result_name] = child_gen
                    changed = True

            if not changed:
                break

        return generation_by_name

    def _classify_splice_row_generation(
        self,
        generation_by_name: dict[str, int],
        parent1_name,
        parent2_name,
    ) -> int | None:
        if not isinstance(parent1_name, str) or not isinstance(parent2_name, str):
            return None

        parent1 = parent1_name.strip()
        parent2 = parent2_name.strip()
        if not parent1 or not parent2:
            return None

        parent1_gen = generation_by_name.get(parent1)
        parent2_gen = generation_by_name.get(parent2)
        if parent1_gen is None or parent2_gen is None:
            return None

        return int(max(parent1_gen, parent2_gen) + 1)

    async def _get_splice_pve_monsters_by_level(
        self,
        sample_per_generation: int | None = None,
    ) -> dict[int, list[dict]]:
        """
        Build a splice-only PvE pool from splice_combinations.
        Samples up to N monsters from Gen0, then buckets by power into tiers 1-10.
        """
        try:
            base_monster_names = self._load_base_pve_monster_names()
        except Exception:
            return {}

        if not base_monster_names:
            return {}

        try:
            async with self.bot.pool.acquire() as conn:
                completed_rows = await conn.fetch(
                    """
                    SELECT id, pet1_default, pet2_default, result_name, hp, attack, defense, element, url, created_at
                    FROM splice_combinations
                    ORDER BY created_at ASC, id ASC
                    """
                )
        except Exception:
            return {}

        if not completed_rows:
            return {}

        generation_map = self._build_splice_generation_map_for_pve(
            base_monster_names,
            completed_rows,
        )

        target_sample = int(sample_per_generation or self.PVE_SPLICE_SAMPLE_PER_GENERATION)
        target_sample = max(1, target_sample)

        generation_buckets = {generation: [] for generation in self.PVE_SPLICE_GENERATIONS}
        seen_by_generation = {generation: set() for generation in self.PVE_SPLICE_GENERATIONS}

        for row in completed_rows:
            row_generation = self._classify_splice_row_generation(
                generation_map,
                row["pet1_default"],
                row["pet2_default"],
            )
            if row_generation not in generation_buckets:
                continue

            result_name = row["result_name"]
            if not isinstance(result_name, str):
                continue
            result_name = result_name.strip()
            if not result_name:
                continue

            dedupe_key = result_name.casefold()
            if dedupe_key in seen_by_generation[row_generation]:
                continue
            seen_by_generation[row_generation].add(dedupe_key)

            try:
                hp = int(row["hp"])
                attack = int(row["attack"])
                defense = int(row["defense"])
            except (TypeError, ValueError):
                continue

            if hp <= 0 or attack <= 0 or defense <= 0:
                continue

            generation_buckets[row_generation].append(
                {
                    "name": result_name,
                    "hp": hp,
                    "attack": attack,
                    "defense": defense,
                    "element": (row["element"] or "Unknown"),
                    "url": row["url"] or "",
                    "ispublic": True,
                    "splice_generation": int(row_generation),
                    "splice_source_id": int(row["id"]),
                }
            )

        selected_monsters = []
        for generation in self.PVE_SPLICE_GENERATIONS:
            candidates = generation_buckets[generation]
            random.shuffle(candidates)
            selected_monsters.extend(candidates[:target_sample])

        if not selected_monsters:
            return {}

        # Spread splice monsters across tiers by total power, weakest -> strongest.
        random.shuffle(selected_monsters)
        selected_monsters.sort(key=lambda monster: monster["hp"] + monster["attack"] + monster["defense"])

        total_count = len(selected_monsters)
        tier_buckets = {tier: [] for tier in range(1, self.PVE_MAX_TIER + 1)}
        for index, monster in enumerate(selected_monsters):
            tier = min(
                self.PVE_MAX_TIER,
                max(1, ((index * self.PVE_MAX_TIER) // total_count) + 1),
            )
            monster_copy = dict(monster)
            monster_copy["pve_pool"] = "splice"
            tier_buckets[tier].append(monster_copy)

        return {tier: bucket for tier, bucket in tier_buckets.items() if bucket}

    def _merge_pve_monster_pools(
        self,
        default_pool: dict[int, list[dict]],
        splice_pool: dict[int, list[dict]],
    ) -> dict[int, list[dict]]:
        """Merge splice monsters into the normal PvE pool by tier."""
        merged: dict[int, list[dict]] = {
            int(tier): [dict(monster) for monster in monster_list]
            for tier, monster_list in (default_pool or {}).items()
        }
        for tier, monster_list in (splice_pool or {}).items():
            tier_key = int(tier)
            merged.setdefault(tier_key, [])
            merged[tier_key].extend(dict(monster) for monster in monster_list)
        return merged

    async def _get_user_pve_splice_toggle(self, user_id: int) -> bool:
        """Return whether a user has splice injection enabled for PvE."""
        async with self.bot.pool.acquire() as conn:
            enabled = await conn.fetchval(
                "SELECT include_splice FROM pve_preferences WHERE user_id = $1;",
                user_id,
            )
        return bool(enabled)

    async def _set_user_pve_splice_toggle(self, user_id: int, enabled: bool):
        """Persist user preference for splice injection into PvE pool."""
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO pve_preferences (user_id, include_splice, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (user_id)
                DO UPDATE SET include_splice = EXCLUDED.include_splice, updated_at = NOW();
                """,
                user_id,
                bool(enabled),
            )

    async def _get_pve_monster_pool_for_user(
        self,
        user_id: int,
        force_include_splice: bool | None = None,
    ) -> tuple[dict[int, list[dict]], bool]:
        """
        Build PvE pool for a user.
        Returns (pool, splice_injected).
        """
        default_pool = await self._get_public_monsters_by_level()

        include_splice = (
            bool(force_include_splice)
            if force_include_splice is not None
            else await self._get_user_pve_splice_toggle(user_id)
        )
        if not include_splice:
            return default_pool, False

        splice_pool = await self._get_splice_pve_monsters_by_level()
        if not splice_pool:
            return default_pool, False

        return self._merge_pve_monster_pools(default_pool, splice_pool), True

    def _roll_pve_tier_for_location(self, location: dict) -> int:
        """
        Roll a tier using location-specific weights and god chance.
        God chance is a percentage.
        """
        god_chance = float(location.get("god_chance", 0) or 0)
        god_chance = max(0.0, min(100.0, god_chance))

        if god_chance > 0 and random.random() < (god_chance / 100):
            return self.PVE_GOD_TIER

        tier_weights = location.get("tier_weights", {})
        tiers = []
        weights = []
        for tier, weight in tier_weights.items():
            tier_int = int(tier)
            weight_float = float(weight)
            if weight_float <= 0:
                continue
            tiers.append(tier_int)
            weights.append(weight_float)

        if not tiers:
            return self._get_pve_tier_for_player_level(location.get("unlock_level", 1))
        return int(random.choices(tiers, weights=weights, k=1)[0])

    def _roll_pve_tier(self, player_level: int, allow_legendary: bool = True) -> int:
        """Roll the PvE tier for an encounter, with optional legendary god chance."""
        if (
            allow_legendary
            and player_level >= 5
            and random.random() < self.PVE_LEGENDARY_SPAWN_CHANCE
        ):
            return self.PVE_GOD_TIER
        return self._get_pve_tier_for_player_level(player_level)

    def _get_encounter_level_range_for_tier(self, tier: int) -> tuple[int, int]:
        """Return encounter-level range for a given PvE tier."""
        normalized_tier = int(tier)
        if normalized_tier >= self.PVE_GOD_TIER:
            return self.PVE_GOD_ENCOUNTER_LEVEL, self.PVE_GOD_ENCOUNTER_LEVEL

        normalized_tier = max(1, min(self.PVE_MAX_TIER, normalized_tier))
        range_min = (normalized_tier - 1) * self.PVE_LEVEL_BRACKET_SIZE
        range_max = normalized_tier * self.PVE_LEVEL_BRACKET_SIZE
        return range_min, range_max

    def _scale_monster_for_encounter(
        self, monster: dict, tier: int, encounter_level: int | None = None
    ) -> dict:
        """
        Scale monster stats by encounter level inside its tier range.
        The range minimum keeps base stats, then each level step adds +2%.
        """
        range_min, range_max = self._get_encounter_level_range_for_tier(tier)

        if encounter_level is None:
            encounter_level = random.randint(range_min, range_max)
        encounter_level = max(range_min, min(range_max, int(encounter_level)))

        scale_steps = max(0, encounter_level - range_min)
        scale_multiplier = Decimal("1") + (
            self.PVE_PER_LEVEL_STAT_SCALE * Decimal(scale_steps)
        )

        scaled_monster = dict(monster)
        for stat_key in ("hp", "attack", "defense"):
            base_value = Decimal(str(monster.get(stat_key, 0)))
            scaled_value = int(
                (base_value * scale_multiplier).to_integral_value(
                    rounding=ROUND_HALF_UP
                )
            )
            scaled_monster[stat_key] = max(1, scaled_value)

        scaled_monster["encounter_level"] = encounter_level
        scaled_monster["pve_tier"] = int(tier)
        scaled_monster["pve_stat_multiplier"] = float(scale_multiplier)
        return scaled_monster
    
    async def display_dialogue(self, ctx, level, name_value, dialoguetoggle=False, god_value=None):
        """Display dialogue for battle tower levels"""
        # Skip dialogue if toggle is on
        if dialoguetoggle:
            await ctx.send("The battle begins!")
            return
        
        # Get the dialogue for this level
        level_str = str(level)
        if level_str not in self.dialogue_data["dialogues"]:
            await ctx.send("The battle begins!")
            return
        
        dialogue_info = self.dialogue_data["dialogues"][level_str]
        
        # Handle special case for level 16 (random users)
        random_user_objects = []
        if "special" in dialogue_info and dialogue_info["special"] == "random_users":
            async with self.bot.pool.acquire() as connection:
                query = 'SELECT "user" FROM profile WHERE "user" != $1 ORDER BY RANDOM() LIMIT 2'
                random_users = await connection.fetch(query, ctx.author.id)
                for user in random_users:
                    user_id = user['user']
                    fetched_user = await self.bot.fetch_user(user_id)
                    if fetched_user:
                        random_user_objects.append(fetched_user)
                if len(random_user_objects) < 2:
                    await ctx.send("The battle begins!")
                    return
        
        # Process dialogue lines
        processed_lines = []
        player_god = god_value if isinstance(god_value, str) and god_value else "an unknown god"
        for line in dialogue_info["lines"]:
            speaker = line["speaker"]
            text = (
                line["text"]
                .replace("{PLAYER_GOD}", player_god)
                .replace("PLAYER_GOD", player_god)
                .replace("PLAYER", name_value)
            )
            thumbnail = line["thumbnail"]

            if speaker == "PLAYER":
                speaker = name_value
            
            # Replace placeholder thumbnails
            if thumbnail in self.BATTLE_TOWER_THUMBNAIL_TOKENS:
                thumbnail = self.BATTLE_TOWER_THUMBNAIL_TOKENS[thumbnail]
            elif thumbnail == "PLAYER_AVATAR":
                thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            elif thumbnail == "RANDOM_USER_1_AVATAR":
                if random_user_objects:
                    thumbnail = random_user_objects[0].avatar.url if random_user_objects[0].avatar else self.DEFAULT_DIALOGUE_AVATAR
                else:
                    thumbnail = self.DEFAULT_DIALOGUE_AVATAR
            elif thumbnail == "RANDOM_USER_2_AVATAR":
                if len(random_user_objects) > 1:
                    thumbnail = random_user_objects[1].avatar.url if random_user_objects[1].avatar else self.DEFAULT_DIALOGUE_AVATAR
                else:
                    thumbnail = self.DEFAULT_DIALOGUE_AVATAR
            elif "special" in dialogue_info and dialogue_info["special"] == "random_users":
                if speaker == "RANDOM_USER_1" and random_user_objects:
                    speaker = random_user_objects[0].display_name
                    text = text.replace("RANDOM_USER_1", speaker)
                    thumbnail = random_user_objects[0].avatar.url if random_user_objects[0].avatar else self.DEFAULT_DIALOGUE_AVATAR
                elif speaker == "RANDOM_USER_2" and len(random_user_objects) > 1:
                    speaker = random_user_objects[1].display_name
                    text = text.replace("RANDOM_USER_2", speaker)
                    thumbnail = random_user_objects[1].avatar.url if random_user_objects[1].avatar else self.DEFAULT_DIALOGUE_AVATAR
            
            processed_lines.append({
                "speaker": speaker,
                "text": text,
                "thumbnail": thumbnail
            })
        
        # Create dialogue pages
        def create_dialogue_page(page_idx):
            line = processed_lines[page_idx]
            embed = discord.Embed(
                title=line["speaker"],
                color=0x003366,
                description=line["text"]
            )
            embed.set_thumbnail(url=line["thumbnail"])
            return embed
        
        # Create all pages
        pages = [create_dialogue_page(i) for i in range(len(processed_lines))]
        
        # Show dialogue
        allowed_dialogue_users = {int(ctx.author.id)}
        alt_invoker_id = getattr(ctx, "alt_invoker_id", None)
        if alt_invoker_id is not None:
            allowed_dialogue_users.add(int(alt_invoker_id))

        view = DialogueView(
            pages,
            ctx.author,
            allowed_user_ids=allowed_dialogue_users,
        )
        await ctx.send(embed=pages[0], view=view)
        await view.wait()
        
        await ctx.send("The battle begins!")

    @has_char()
    @user_cooldown(90)
    #@commands.command(brief=_("Battle against another player"))
    @locale_doc
    async def battle(self, ctx, money: IntGreaterThan(-1) = 0, enemy: discord.Member = None):
        _(
            """`[money]` - A whole number that can be 0 or greater; defaults to 0
            `[enemy]` - A user who has a profile; defaults to anyone

            Fight against another player while betting money.
            To decide the fight, the players' items, race and class bonuses and an additional number from 1 to 7 are evaluated, this serves as a way to give players with lower stats a chance at winning.

            The money is removed from both players at the start of the battle. Once a winner has been decided, they will receive their money, plus the enemy's money.
            The battle lasts 30 seconds, after which the winner and loser will be mentioned.

            If both players' stats + random number are the same, the winner is decided at random.
            The battle's winner will receive a PvP win, which shows on their profile.
            (This command has a cooldown of 90 seconds.)"""
        )
        if enemy == ctx.author:
            return await ctx.send(_("You can't battle yourself."))
        if ctx.character_data["money"] < money:
            return await ctx.send(_("You are too poor."))

        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
            money,
            ctx.author.id,
        )

        if not enemy:
            text = _("{author} seeks a battle! The price is **${money}**.").format(
                author=ctx.author.mention, money=money
            )
        else:
            text = _(
                "{author} seeks a battle with {enemy}! The price is **${money}**."
            ).format(author=ctx.author.mention, enemy=enemy.mention, money=money)

        async def check(user: discord.User) -> bool:
            return await has_money(self.bot, user.id, money)

        future = asyncio.Future()
        view = SingleJoinView(
            future,
            Button(
                style=ButtonStyle.primary,
                label=_("Join the battle!"),
                emoji="\U00002694",
            ),
            allowed=enemy,
            prohibited=ctx.author,
            timeout=60,
            check=check,
            check_fail_message=_("You don't have enough money to join the battle."),
        )

        await ctx.send(text, view=view)

        try:
            enemy_ = await future
        except asyncio.TimeoutError:
            await self.bot.reset_cooldown(ctx)
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )
            return await ctx.send(
                _("Noone wanted to join your battle, {author}!").format(
                    author=ctx.author.mention
                )
            )

        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;', money, enemy_.id
        )

        await ctx.send(
            _(
                "Battle **{author}** vs **{enemy}** started! 30 seconds of fighting"
                " will now start!"
            ).format(author=ctx.disp, enemy=enemy_.display_name)
        )

        # Use the simple battle mechanics from the original implementation
        stats = [
            sum(await self.bot.get_damage_armor_for(ctx.author)) + random.randint(1, 7),
            sum(await self.bot.get_damage_armor_for(enemy_)) + random.randint(1, 7),
        ]
        players = [ctx.author, enemy_]
        if stats[0] == stats[1]:
            winner = random.choice(players)
        else:
            winner = players[stats.index(max(stats))]
        looser = players[players.index(winner) - 1]
        
        # Let the battle animation run for 30 seconds
        await asyncio.sleep(30)
        
        # Update the database with results
        async with self.bot.pool.acquire() as conn:
            # Award PvP wins regardless of money
            await conn.execute(
                'UPDATE profile SET "pvpwins"="pvpwins"+1 WHERE "user"=$1;',
                winner.id,
            )
            
            # Handle money rewards if there's money involved
            if money > 0:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money * 2,
                    winner.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=looser.id,
                    to=winner.id,
                    subject="Battle Bet",
                    data={"Gold": money},
                    conn=conn,
                )
        
        await ctx.send(
            _("{winner} won the battle vs {looser}! Congratulations!").format(
                winner=winner.mention, looser=looser.mention
            )
        )

    @commands.group(aliases=["bt"])
    async def battletower(self, ctx):
        """Battle tower commands."""
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.progress)

    @is_gm()
    @commands.command(hidden=True)
    async def setbtlevel(self, ctx, user_id: int, prestige: int, level: int):
        """[GM only] Set a user's battle tower level and prestige."""
        try:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE battletower SET "level"=$1, prestige=$2 WHERE "id"=$3;',
                    level,
                    prestige,
                    user_id,
                )
            await ctx.send(f"Successfully updated level for user {user_id} to {level}.")
        except Exception as e:
            await ctx.send(f"An error occurred while updating the level: {e}")

    @battletower.command()
    @locale_doc
    async def toggle_dialogue(self, ctx):
        _(
            """Toggle battle dialogue on or off.

            When enabled, you'll see story dialogue before battles in the Battle Tower.
            When disabled, battles will start immediately without dialogue.
            """
        )
        async with self.bot.pool.acquire() as conn:
            # Toggle the dialoguetoggle value
            await conn.execute(
                'UPDATE battletower SET dialoguetoggle = NOT COALESCE(dialoguetoggle, false) WHERE id = $1',
                ctx.author.id
            )
            # Get the new value
            new_value = await conn.fetchval(
                'SELECT dialoguetoggle FROM battletower WHERE id = $1',
                ctx.author.id
            )
        
        status = "enabled" if new_value else "disabled"
        await ctx.send(f"Battle dialogue has been {status} for your Battle Tower runs.")

    @battletower.command()
    async def start(self, ctx):
        """Start your journey in the Battle Tower."""
        try:
            async with self.bot.pool.acquire() as connection:
                user_exists = await connection.fetchval('SELECT 1 FROM battletower WHERE id = $1', ctx.author.id)

            if not user_exists:
                # User doesn't exist in the database
                prologue_embed = discord.Embed(
                    title="Welcome to the Battle Tower",
                    description=(
                        "You stand at the foot of the imposing Battle Tower, a colossal structure that pierces the heavens. "
                        "It is said that the tower was once a place of valor, but it has since fallen into darkness. "
                        "Now, it is a domain of malevolence, home to powerful bosses and their loyal minions."
                    ),
                    color=0xFF5733
                )

                prologue_embed.set_image(url="https://i.ibb.co/s1xx83h/download-3-1.jpg")

                await ctx.send(embed=prologue_embed)

                confirm = await ctx.confirm(
                    message="Do you want to enter the Battle Tower and face its challenges?", timeout=60)

                if confirm is not None:
                    if confirm:
                        # User confirmed to enter the tower
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute('INSERT INTO battletower (id) VALUES ($1)', ctx.author.id)

                        await ctx.send("You have entered the Battle Tower. Good luck on your quest!")
                        return
                    else:
                        await ctx.send("You chose not to enter the Battle Tower. Perhaps another time.")
                        return
                else:
                    # User didn't make a choice within the specified time
                    await ctx.send("You didn't respond in time. Please try again when you're ready.")
                    return
            else:
                await ctx.send("You have already started your journey in the Battle Tower. Use `$battletower progress` to see your current level.")

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @has_char()
    @battletower.command()
    async def progress(self, ctx):
        """View your progress in the Battle Tower."""
        try:
            async with self.bot.pool.acquire() as connection:
                user_exists = await connection.fetchval('SELECT 1 FROM battletower WHERE id = $1', ctx.author.id)

                if not user_exists:
                    await ctx.send("You have not started Battletower. You can start by using `$battletower start`")
                    return

                try:
                    progress_row = await connection.fetchrow(
                        """
                        SELECT
                            level,
                            prestige,
                            COALESCE(run_key_bits, 0) AS run_key_bits,
                            COALESCE(freedom_meter, 0) AS freedom_meter
                        FROM battletower
                        WHERE id = $1
                        """,
                        ctx.author.id,
                    )
                    if not progress_row:
                        await ctx.send("You have not started Battletower. You can start by using `$battletower start`")
                        return

                    user_level = int(progress_row["level"] or 1)
                    prestige_level = int(progress_row["prestige"] or 0)
                    run_key_bits = int(progress_row["run_key_bits"] or 0)
                    freedom_meter = int(progress_row["freedom_meter"] or 0)
                    keys_this_run = self._tower_key_count(run_key_bits)
                    hidden_door_ready = (
                        keys_this_run == 3
                        or freedom_meter >= self.TOWER_FREEDOM_UNLOCK_THRESHOLD
                    )

                    level_names_1 = self.battle_data.get("level_names") or []

                    # Function to generate the formatted level list
                    def generate_level_list(levels, start_level=1):
                        result = "```\n"
                        for level, level_name in enumerate(levels, start=start_level):
                            checkbox = "❌" if level == user_level else "✅" if level < user_level else "❌"
                            result += f"Level {level:<2} {checkbox} {level_name}\n"
                        result += "```"
                        return result

                    # Create embed for levels 1-30
                    embed_1 = discord.Embed(
                        title="Battle Tower Progress (Levels 1-30)",
                        description=(
                            f"Level: {user_level}\n"
                            f"Prestige Level: {prestige_level}\n"
                            f"Keys This Run: {keys_this_run}/3\n"
                            f"Hidden Door Resonance: "
                            f"{min(freedom_meter, self.TOWER_FREEDOM_UNLOCK_THRESHOLD)}/{self.TOWER_FREEDOM_UNLOCK_THRESHOLD}\n"
                            f"Hidden Door Ready: {'✅' if hidden_door_ready else '❌'}"
                        ),
                        color=0x0000FF
                    )
                    embed_1.add_field(name="Level Progress", value=generate_level_list(level_names_1), inline=False)
                    embed_1.set_footer(text="**Rewards are granted every 5 levels**")

                    # Send the embeds to the current context (channel)
                    await ctx.send(embed=embed_1)

                except Exception as e:
                    await ctx.send(f"An error occurred while fetching your level: {e}")

        except Exception as e:
            await ctx.send(f"An error occurred while accessing the database: {e}")

    def _get_other_god_message(self, victory_data, player_god=None):
        """Pick a god message, preferring one that is not the player's god."""
        god_messages = victory_data.get("god_messages")
        if not isinstance(god_messages, dict) or not god_messages:
            return None

        normalized_player_god = (
            player_god.strip().lower()
            if isinstance(player_god, str) and player_god.strip()
            else None
        )

        filtered_messages = [
            msg
            for god_name, msg in god_messages.items()
            if isinstance(msg, str)
            and msg.strip()
            and (normalized_player_god is None or god_name.lower() != normalized_player_god)
        ]

        if not filtered_messages:
            filtered_messages = [
                msg for msg in god_messages.values() if isinstance(msg, str) and msg.strip()
            ]

        return random.choice(filtered_messages) if filtered_messages else None

    async def handle_victory(
        self,
        ctx,
        level,
        name_value,
        dialoguetoggle,
        minion1_name=None,
        minion2_name=None,
        emotes=None,
        player_balance=0,
        victory_description=None,
        player_god=None,
    ):
        """Handle victory rewards for battle tower."""
        if victory_description:
            await ctx.send(victory_description)
            return
            
        level_str = str(level)
        if level_str not in self.battle_data["victories"]:
            await ctx.send("You won the battle!")
            return
            
        # Get level data
        victory_data = self.battle_data["victories"][level_str]
        level_name = self.battle_data["level_names"][level - 1] if level <= len(self.battle_data["level_names"]) else "Unknown Level"
        
        # Handle any special flash events (like in level 18)
        if "flash" in victory_data:
            flash_embed = discord.Embed(
                title=victory_data["flash"]["title"],
                description=victory_data["flash"]["description"],
                color=0xffd700  # Gold color for mystical elements
            )
            await ctx.send(embed=flash_embed)
        
        # Format the victory description with variables
        description = victory_data["description"]
        description = description.replace("{level_name}", level_name)
        if minion1_name:
            description = description.replace("{minion1_name}", minion1_name)
        if minion2_name:
            description = description.replace("{minion2_name}", minion2_name)
        if "{OTHER_GOD_MESSAGE}" in description:
            other_god_message = self._get_other_god_message(victory_data, player_god)
            if not other_god_message:
                other_god_message = "A divine warning echoes in your mind, then vanishes."
            description = description.replace("{OTHER_GOD_MESSAGE}", other_god_message)
        
        # Create and send the victory embed
        victory_embed = discord.Embed(
            title=victory_data["title"],
            description=description,
            color=0x00ff00  # Green color for success
        )
        await ctx.send(embed=victory_embed)

        # Track run-based hidden-door progress (key rolls + resonance milestones).
        await self._update_tower_run_progress(ctx, level)
        
        # Handle chest rewards if this level has them
        if "has_chest" in victory_data and victory_data["has_chest"]:
            await self.handle_chest_rewards(ctx, level, name_value, emotes)
        # Handle finale rewards for level 30
        elif "finale" in victory_data and victory_data["finale"]:
            await self.handle_finale_rewards(ctx, level)
        else:
            # Just advance to the next level
            newlevel = level + 1
            async with self.bot.pool.acquire() as connection:
                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
            await ctx.send(f'You have advanced to floor: {newlevel}')
    
    async def handle_chest_rewards(self, ctx, level, name_value, emotes):
        """Handle chest rewards for battle tower victories."""

        level_str = str(level)
        victory_data = self.battle_data["victories"][level_str]
        chest_rewards = victory_data["chest_rewards"]
        
        # Create an embed for the treasure chest options
        chest_embed = discord.Embed(
            title="Choose Your Treasure",
            description=(
                "You have a choice to make: Before you lie two treasure chests, each shimmering with an otherworldly aura. "
                "The left chest appears ancient and ornate, while the right chest is smaller but radiates a faint magical glow."
                f"{ctx.author.mention}, Type `left` or `right` to make your decision. You have 60 seconds!"
            ),
            color=0x0055ff  # Blue color for options
        )
        chest_embed.set_footer(text=f"Type left or right to make your decision.")
        await ctx.send(embed=chest_embed)
        
        # Get prestige level
        async with self.bot.pool.acquire() as connection:
            prestige_level = await connection.fetchval('SELECT prestige FROM battletower WHERE id = $1', ctx.author.id)
            
        # Define check function for user response
        def check(m):
            return m.author == ctx.author and m.content.lower() in ['left', 'right']
        
        # Generate rewards based on prestige level
        if prestige_level >= 1:
            await self.handle_prestige_chest_rewards(ctx, level, emotes)
        else:
            await self.handle_default_chest_rewards(ctx, level, chest_rewards["default"], emotes)

    
    async def handle_prestige_chest_rewards(self, ctx, level, emotes):
        """Handle randomized rewards for prestige players in battle tower."""
        async with self.bot.pool.acquire() as connection:
            # Generate random rewards for both chests
            left_reward_type = random.choice(['crate', 'money'])
            right_reward_type = random.choice(['crate', 'money'])
            
            # Get options from config
            chest_options = self.battle_data["chest_options"]["random"]
            
            # Generate the specific rewards
            if left_reward_type == 'crate':
                left_options = [opt["value"] for opt in chest_options["crate_options"]]
                left_weights = [opt["weight"] for opt in chest_options["crate_options"]]
                left_crate_type = random.choices(left_options, left_weights)[0]
            else:
                left_money_amount = random.choice(chest_options["money_options"])
                
            if right_reward_type == 'crate':
                right_options = [opt["value"] for opt in chest_options["crate_options"]]
                right_weights = [opt["weight"] for opt in chest_options["crate_options"]]
                right_crate_type = random.choices(right_options, right_weights)[0]
            else:
                right_money_amount = random.choice(chest_options["money_options"])
            
            # Process user choice
            def check(m):
                return m.author == ctx.author and m.content.lower() in ['left', 'right']
                
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                choice = msg.content.lower()
            except asyncio.TimeoutError:
                choice = random.choice(["left", "right"])
                await ctx.send('You took too long to decide. The chest will be chosen at random.')
            
            # Process the reward based on choice
            new_level = level + 1
            if choice == 'left':
                if left_reward_type == 'crate':
                    await ctx.send(f'You open the chest on the left and find a {emotes[left_crate_type]} crate!')
                    await connection.execute(
                        f'UPDATE profile SET crates_{left_crate_type} = crates_{left_crate_type} + 1 WHERE "user" = $1',
                        ctx.author.id)
                    
                    # Show what they missed
                    if right_reward_type == 'crate':
                        await ctx.send(f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                    else:
                        await ctx.send(f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                else:
                    await ctx.send(f'You open the chest on the left and find **${left_money_amount}**!')
                    await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                            left_money_amount, ctx.author.id)
                    
                    # Show what they missed
                    if right_reward_type == 'crate':
                        await ctx.send(f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                    else:
                        await ctx.send(f'You could have gotten **${right_money_amount}** if you chose the right chest.')
            else:  # right choice
                if right_reward_type == 'crate':
                    await ctx.send(f'You open the chest on the right and find a {emotes[right_crate_type]} crate!')
                    await connection.execute(
                        f'UPDATE profile SET crates_{right_crate_type} = crates_{right_crate_type} + 1 WHERE "user" = $1',
                        ctx.author.id)
                    
                    # Show what they missed
                    if left_reward_type == 'crate':
                        await ctx.send(f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                    else:
                        await ctx.send(f'You could have gotten **${left_money_amount}** if you chose the left chest.')
                else:
                    await ctx.send(f'You open the chest on the right and find **${right_money_amount}**!')
                    await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                            right_money_amount, ctx.author.id)
                    
                    # Show what they missed
                    if left_reward_type == 'crate':
                        await ctx.send(f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                    else:
                        await ctx.send(f'You could have gotten **${left_money_amount}** if you chose the left chest.')
            
            # Update level and clean up
            await ctx.send(f'You have advanced to floor: {new_level}')
            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
            try:
                await self.remove_player_from_fight(ctx.author.id)
            except Exception as e:
                pass
    
    async def handle_default_chest_rewards(self, ctx, level, rewards, emotes):
        """Handle fixed rewards for non-prestige players in battle tower."""
        def check(m):
            return m.author == ctx.author and m.content.lower() in ['left', 'right']
            
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            choice = msg.content.lower()
        except asyncio.TimeoutError:
            newlevel = level + 1
            choice = random.choice(["left", "right"])
            await ctx.send('You took too long to decide. The chest will be chosen at random.')
        
        # Process the reward based on choice
        if choice is not None:
            newlevel = level + 1
            if choice == 'left':
                left_reward = rewards["left"]
                if left_reward["type"] == "crate":
                    message = f'You open the chest on the left and find: {emotes[left_reward["value"]]} '
                    if left_reward["amount"] > 1:
                        message += f'{left_reward["amount"]} {left_reward["value"].capitalize()} Crates!'
                    else:
                        message += f'A {left_reward["value"].capitalize()} Crate!'
                    
                    await ctx.send(message)
                    await ctx.send(f'You have advanced to floor: {newlevel}')
                    
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute(
                            f'UPDATE profile SET crates_{left_reward["value"]} = crates_{left_reward["value"]} + {left_reward["amount"]} WHERE "user" = $1',
                            ctx.author.id)
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
                elif left_reward["type"] == "money":
                    extra_msg = f" {left_reward.get('message', '')}" if "message" in left_reward else ""
                    await ctx.send(f'You open the chest on the left and find: **${left_reward["value"]}**!{extra_msg}')
                    await ctx.send(f'You have advanced to floor: {newlevel}')
                    
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute(
                            f'UPDATE profile SET money = money + {left_reward["value"]} WHERE "user" = $1',
                            ctx.author.id)
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
                elif left_reward["type"] == "nothing":
                    await ctx.send('You open the chest on the left and find: Nothing, bad luck!')
                    await ctx.send(f'You have advanced to floor: {newlevel}')
                    
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
                elif left_reward["type"] == "random":
                    # Handle special random case for level 15
                    legran = random.randint(1, 2)
                    if legran == 1:
                        await ctx.send('You open the chest on the left and find: Nothing, bad luck!')
                        await ctx.send(f'You have advanced to floor: {newlevel}')
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
                    else:
                        await ctx.send('You open the chest on the left and find: <:F_Legendary:1139514868400132116> A Legendary Crate!')
                        await ctx.send(f'You have advanced to floor: {newlevel}')
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute(
                                'UPDATE profile SET crates_legendary = crates_legendary + 1 WHERE "user" = $1',
                                ctx.author.id)
                            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
            else:  # right choice
                right_reward = rewards["right"]
                if right_reward["type"] == "crate":
                    message = f'You open the chest on the right and find: {emotes[right_reward["value"]]} '
                    if right_reward["amount"] > 1:
                        message += f'{right_reward["amount"]} {right_reward["value"].capitalize()} Crates!'
                    else:
                        message += f'A {right_reward["value"].capitalize()} Crate!'
                    
                    await ctx.send(message)
                    await ctx.send(f'You have advanced to floor: {newlevel}')
                    
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute(
                            f'UPDATE profile SET crates_{right_reward["value"]} = crates_{right_reward["value"]} + {right_reward["amount"]} WHERE "user" = $1',
                            ctx.author.id)
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
                elif right_reward["type"] == "money":
                    extra_msg = f" {right_reward.get('message', '')}" if "message" in right_reward else ""
                    await ctx.send(f'You open the chest on the right and find: **${right_reward["value"]}**!{extra_msg}')
                    await ctx.send(f'You have advanced to floor: {newlevel}')
                    
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute(
                            f'UPDATE profile SET money = money + {right_reward["value"]} WHERE "user" = $1',
                            ctx.author.id)
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
                elif right_reward["type"] == "nothing":
                    await ctx.send('You open the chest on the right and find: Nothing, bad luck!')
                    await ctx.send(f'You have advanced to floor: {newlevel}')
                    
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
                elif right_reward["type"] == "random":
                    # Handle special random case for level 15
                    legran = random.randint(1, 2)
                    if legran == 2:
                        await ctx.send('You open the chest on the right and find: Nothing, bad luck!')
                        await ctx.send(f'You have advanced to floor: {newlevel}')
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
                    else:
                        await ctx.send('You open the chest on the right and find: <:F_Legendary:1139514868400132116> A Legendary Crate!')
                        await ctx.send(f'You have advanced to floor: {newlevel}')
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute(
                                'UPDATE profile SET crates_legendary = crates_legendary + 1 WHERE "user" = $1',
                                ctx.author.id)
                            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
    
    async def handle_finale_rewards(self, ctx, level):
        """Handle level 30 finale rewards for battle tower."""
        victory_data = self.battle_data["victories"].get("30", {})
        unlock_state = await self._get_tower_unlock_state(ctx.author.id)
        keys_this_run = int(unlock_state["key_count"])
        freedom_meter = int(unlock_state["freedom_meter"])
        hidden_door_ready = bool(unlock_state["door4_unlocked"])
        hidden_ready_reason = (
            "All 3 keys resonated this run."
            if unlock_state["full_key_unlock"]
            else "Your resonance meter reached the hidden threshold."
            if unlock_state["meter_unlock"]
            else "Not unlocked this cycle."
        )

        # Create and send cosmic embed
        cosmic_embed = discord.Embed(
            title=victory_data.get("title", self.battle_data["victories"]["30"]["title"]),
            description=victory_data.get("description", self.battle_data["victories"]["30"]["description"]),
            color=0xff0000,  # Red color for the climax
        )
        cosmic_embed.add_field(
            name="Hidden Door Status",
            value=(
                f"Keys This Run: **{keys_this_run}/3**\n"
                f"Resonance Meter: **{min(freedom_meter, self.TOWER_FREEDOM_UNLOCK_THRESHOLD)}/{self.TOWER_FREEDOM_UNLOCK_THRESHOLD}**\n"
                f"Door 4 Ready: {'✅' if hidden_door_ready else '❌'}\n"
                f"{hidden_ready_reason}"
            ),
            inline=False,
        )
        await ctx.send(embed=cosmic_embed)

        endings = victory_data.get("endings", {})
        selected_door_key = None
        if isinstance(endings, dict) and endings:
            ordered_doors = [
                "door_1_elysia",
                "door_2_sepulchure",
                "door_3_drakath",
                "door_4_freedom",
            ]
            available_door_keys = [
                door_key
                for door_key in ordered_doors
                if door_key in endings and (door_key != "door_4_freedom" or hidden_door_ready)
            ]
            if available_door_keys:
                selected_door_key = await self._prompt_finale_door_choice(
                    ctx, available_door_keys, endings
                )
                if not selected_door_key:
                    selected_door_key = random.choice(available_door_keys)

                selected_ending = endings.get(selected_door_key)
                if selected_ending:
                    ending_embed = discord.Embed(
                        title=selected_ending.get("title", self._tower_door_label(selected_door_key)),
                        description=selected_ending.get("description", "The path forward is unclear."),
                        color=0x8B0000,
                    )
                    await ctx.send(embed=ending_embed)

        # Door 4 bonus: if the run had all 3 keys, finale rewards are always doubled.
        door4_double_rewards = (
            selected_door_key == "door_4_freedom"
            and bool(unlock_state.get("full_key_unlock"))
        )
        reward_multiplier = 2 if door4_double_rewards else 1

        # Check prestige level
        async with self.bot.pool.acquire() as connection:
            prestige_level = await connection.fetchval(
                'SELECT prestige FROM battletower WHERE id = $1',
                ctx.author.id,
            )
            prestige_level = int(prestige_level or 0)

        # Get emoji mapping for display
        emotes = {
            "common": "<:c_common:1403797578197368923>",
            "uncommon": "<:c_uncommon:1403797597532983387>",
            "rare": "<:c_rare:1403797594827657247>",
            "magic": "<:c_Magic:1403797589169541330>",
            "legendary": "<:c_Legendary:1403797587236225044>",
            "mystery": "<:c_mystspark:1403797593129222235>",
            "fortune": "<:c_money:1403797585411575971>",
            "divine": "<:c_divine:1403797579635884202>",
        }

        if prestige_level >= 1:
            premium_options = self.battle_data["chest_options"]["random_premium"]
            crate_options = premium_options["types"]
            weights = premium_options["weights"]
            selected_crate = random.choices(crate_options, weights)[0]
            async with self.bot.pool.acquire() as connection:
                await connection.execute(
                    f'UPDATE profile SET crates_{selected_crate} = crates_{selected_crate} + $1 WHERE "user" = $2',
                    reward_multiplier,
                    ctx.author.id,
                )
            reward_message = (
                f"You have received {reward_multiplier} {emotes[selected_crate]} crate"
                f"{'' if reward_multiplier == 1 else 's'} for completing the battletower "
                f"on prestige level: {prestige_level}. Congratulations!"
            )
        else:
            async with self.bot.pool.acquire() as connection:
                await connection.execute(
                    'UPDATE profile SET crates_divine = crates_divine + $1 WHERE "user" = $2',
                    reward_multiplier,
                    ctx.author.id,
                )
            reward_message = (
                f"You have received {reward_multiplier} <:f_divine:1169412814612471869> crate"
                f"{'' if reward_multiplier == 1 else 's'} "
                "for completing the battletower, congratulations."
            )

        # Progression updates after floor 30:
        # - always advance to level 31 (prestige prompt remains in `fight`)
        # - reset run keys for the next cycle
        # - apply hidden-door resonance gain/consumption
        freedom_delta = 0
        if not hidden_door_ready:
            freedom_delta += self.TOWER_FREEDOM_FINALE_MISS_GAIN
        elif (
            selected_door_key == "door_4_freedom"
            and unlock_state["meter_unlock"]
            and not unlock_state["full_key_unlock"]
        ):
            freedom_delta -= self.TOWER_FREEDOM_UNLOCK_THRESHOLD

        async with self.bot.pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE battletower
                SET level = level + 1,
                    run_key_bits = 0,
                    freedom_meter = GREATEST(0, COALESCE(freedom_meter, 0) + $1)
                WHERE id = $2
                """,
                freedom_delta,
                ctx.author.id,
            )

        await ctx.send(f'This is the end for you... {ctx.author.mention}.. or is it..?')
        if door4_double_rewards:
            await ctx.send("🔓 The hidden fourth door recognizes your 3 keys. Finale rewards are **doubled**.")
        await ctx.send(reward_message)

        if not hidden_door_ready:
            new_meter = max(0, freedom_meter + self.TOWER_FREEDOM_FINALE_MISS_GAIN)
            await ctx.send(
                f"🧭 The hidden door stayed sealed this cycle. "
                f"Resonance +{self.TOWER_FREEDOM_FINALE_MISS_GAIN} "
                f"(**{min(new_meter, self.TOWER_FREEDOM_UNLOCK_THRESHOLD)}/{self.TOWER_FREEDOM_UNLOCK_THRESHOLD}**)."
            )
        elif (
            selected_door_key == "door_4_freedom"
            and unlock_state["meter_unlock"]
            and not unlock_state["full_key_unlock"]
        ):
            remaining_meter = max(0, freedom_meter - self.TOWER_FREEDOM_UNLOCK_THRESHOLD)
            await ctx.send(
                f"🗝️ Hidden-door resonance consumed: "
                f"{self.TOWER_FREEDOM_UNLOCK_THRESHOLD}. Remaining: **{remaining_meter}**."
            )

        # Complete the raid
        self.bot.dispatch("raid_completion", ctx, True, ctx.author.id)
        try:
            await self.remove_player_from_fight(ctx.author.id)
        except Exception as e:
            pass

    @has_char()
    @battletower.command()
    @user_cooldown(600)
    async def fight(self, ctx):
        """Fight the current level in the battle tower."""
        try:
            # Check if user has started the battle tower
            async with self.bot.pool.acquire() as connection:
                user_exists = await connection.fetchval('SELECT 1 FROM battletower WHERE id = $1', ctx.author.id)
                if not user_exists:
                    await ctx.send("You have not started Battletower. You can start by using `$battletower start`")
                    await self.bot.reset_cooldown(ctx)
                    return

                # Get user's level and other data

                level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)
                if level == 0:
                    await connection.execute('UPDATE battletower SET level = 1 WHERE id = $1', ctx.author.id)
                    level = 1

                player_balance = await connection.fetchval('SELECT money FROM profile WHERE "user" = $1', ctx.author.id)
                god_value = await connection.fetchval('SELECT god FROM profile WHERE "user" = $1', ctx.author.id)
                name_value = await connection.fetchval('SELECT name FROM profile WHERE "user" = $1', ctx.author.id)
                dialoguetoggle = await connection.fetchval('SELECT dialoguetoggle FROM battletower WHERE id = $1', ctx.author.id)

            # Check for prestige at level 31+
            if level >= 31:
                confirm_message = "Are you sure you want to prestige? This action will reset your level. Your next run rewards will be completely randomized."
                try:
                    confirm = await ctx.confirm(confirm_message)
                    if confirm:
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute(
                                'UPDATE battletower SET level = 1, prestige = prestige + 1, run_key_bits = 0 WHERE id = $1',
                                ctx.author.id)
                        await ctx.send(
                            "You have prestiged. Your level has been reset to 1. The rewards for your next run will be completely randomized.")
                        await self.bot.reset_cooldown(ctx)
                        return
                    else:
                        await ctx.send("Prestige canceled.")
                        await self.bot.reset_cooldown(ctx)
                        return
                except asyncio.TimeoutError:
                    await ctx.send("Prestige canceled due to timeout.")
                    await self.bot.reset_cooldown(ctx)
                    return

            # Display dialogue for the current level
            await self.display_dialogue(ctx, level, name_value, dialoguetoggle, god_value)

            # Check if player is already in a fight
            if await self.is_player_in_fight(ctx.author.id):
                await ctx.send("You are already in a battle!")
                await self.bot.reset_cooldown(ctx)
                return

            # Add player to fight
            await self.add_player_to_fight(ctx.author.id)

            # Get level data
            try:
                level_data = self.levels[str(level)]
            except KeyError:
                await ctx.send(f"No data found for level {level}. Please contact an administrator.")
                await self.remove_player_from_fight(ctx.author.id)
                await self.bot.reset_cooldown(ctx)
                return

            # Special handling for level 16 - use random players as minions
            if level == 16:
                async with self.bot.pool.acquire() as connection:
                    query = 'SELECT "user" FROM profile WHERE "user" != $1 ORDER BY RANDOM() LIMIT 2'
                    random_users = await connection.fetch(query, ctx.author.id)

                    random_user_objects = []
                    for user in random_users:
                        user_id = user['user']
                        try:
                            fetched_user = await self.bot.fetch_user(user_id)
                            if fetched_user:
                                random_user_objects.append(fetched_user)
                        except:
                            continue

                    if len(random_user_objects) >= 2:
                        random_user_object_1 = random_user_objects[0]
                        random_user_object_2 = random_user_objects[1]
                        async with self.bot.pool.acquire() as conn:
                            minion1atk, minion1def = await self.bot.get_raidstats(random_user_object_1, conn=conn)
                            minion2atk, minion2def = await self.bot.get_raidstats(random_user_object_2, conn=conn)

                            # Calculate HP for minion 1
                            minion1_result = await conn.fetchrow('SELECT "health", "stathp", "xp" FROM profile WHERE "user" = $1', random_user_object_1.id)
                            if minion1_result:
                                from utils import misc as rpgtools
                                minion1_level = rpgtools.xptolevel(minion1_result['xp'])
                                base_health = 200
                                minion1_health = minion1_result['health'] + base_health
                                minion1_stathp = minion1_result['stathp'] * 50
                                minion1_total_hp = minion1_health + (minion1_level * 15) + minion1_stathp
                            else:
                                minion1_total_hp = 250  # fallback

                            # Calculate HP for minion 2
                            minion2_result = await conn.fetchrow('SELECT "health", "stathp", "xp" FROM profile WHERE "user" = $1', random_user_object_2.id)
                            if minion2_result:
                                minion2_level = rpgtools.xptolevel(minion2_result['xp'])
                                base_health = 200
                                minion2_health = minion2_result['health'] + base_health
                                minion2_stathp = minion2_result['stathp'] * 50
                                minion2_total_hp = minion2_health + (minion2_level * 15) + minion2_stathp
                            else:
                                minion2_total_hp = 150  # fallback

                        level_data = level_data.copy()
                        level_data["minion1_name"] = random_user_object_1.display_name
                        level_data["minion2_name"] = random_user_object_2.display_name
                        level_data["minion1"] = {
                            "hp": minion1_total_hp,
                            "damage": minion1atk,
                            "armor": minion1def,
                            "element": "unknown"
                        }
                        level_data["minion2"] = {
                            "hp": minion2_total_hp,
                            "damage": minion2atk,
                            "armor": minion2def,
                            "element": "unknown"
                        }
                    else:
                        await ctx.send("Warning: Could not find enough players for special level 16 battle. Using default enemies.")

            # Create and start the battle
            battle = await self.battle_factory.create_battle(
                "tower",
                ctx,
                player=ctx.author,
                level=level,
                level_data=level_data
            )

            # Start the battle
            await battle.start_battle()

            # Run the battle until completion
            while not await battle.is_battle_over():
                await battle.process_turn()
                await asyncio.sleep(2)  # 2 second delay between turns for battle tower

            # Get the result (winner team)
            result = await battle.end_battle()
            
            # Check for explicit timeout (new attribute)
            battle_timed_out = hasattr(battle, 'battle_timed_out') and battle.battle_timed_out

            # Define emoji map for rewards
            emotes = {
                "common": "<:c_common:1403797578197368923>",
                "uncommon": "<:c_uncommon:1403797597532983387>",
                "rare": "<:c_rare:1403797594827657247>",
                "magic": "<:c_Magic:1403797589169541330>",
                "legendary": "<:c_Legendary:1403797587236225044>",
                "mystery": "<:c_mystspark:1403797593129222235>",
                "fortune": "<:c_money:1403797585411575971>",
                "divine": "<:c_divine:1403797579635884202>",
            }

            # Handle victory or defeat
            if result:
                winner_team_id = result.name
                
                # Check if the player team won AND the character (not just pets) is still alive
                player_alive = any(not c.is_pet and c.is_alive() for c in battle.player_team.combatants)
                if winner_team_id == "Player" and (player_alive or battle.config.get("pets_continue_battle", False)):
                    # Get minion names for victory message
                    minion1_name = level_data.get("minion1_name", "Minion")
                    minion2_name = level_data.get("minion2_name", "Minion")

                    # Handle victory rewards
                    await self.handle_victory(
                        ctx=ctx,
                        level=level,
                        name_value=name_value,
                        dialoguetoggle=dialoguetoggle,
                        minion1_name=minion1_name,
                        minion2_name=minion2_name,
                        emotes=emotes,
                        player_balance=player_balance,
                        player_god=god_value,
                    )
                else:
                    await ctx.send(f"**{ctx.author.mention}**, you have been defeated. Better luck next time!")
            else:
                # Check if it was a timeout or defeat
                if battle_timed_out:
                    # It was a timeout
                    await ctx.send("The battle timed out. Try again later.")
                else:
                    # It was a defeat
                    await ctx.send(f"**{ctx.author.mention}**, you have been defeated. Better luck next time!")

            # Remove player from fight tracking
            await self.remove_player_from_fight(ctx.author.id)

        except Exception as e:
            import traceback
            error_message = f"An error occurred during the battletower battle: {e}\n{traceback.format_exc()}"
            await ctx.send(error_message)
            print(error_message)
            await self.remove_player_from_fight(ctx.author.id)
            await self.bot.reset_cooldown(ctx)

    @has_char()
    @user_cooldown(100)
    @commands.command(brief=_("Battle against a player (includes raidstats)"))
    @locale_doc
    async def raidbattle(self, ctx, money: IntGreaterThan(-1) = 0, enemy: discord.Member = None):
        _(
            """`[money]` - A whole number that can be 0 or greater; defaults to 0
            `[enemy]` - A user who has a profile; defaults to anyone

            Fight against another player while betting money.
            To decide the players' stats, their items, race and class bonuses and raidstats are evaluated.

            You also have a chance of tripping depending on your luck.

            The money is removed from both players at the start of the battle. Once a winner has been decided, they will receive their money, plus the enemy's money.
            The battle is divided into turns, in which each combatant (player or pet) takes an action.

            The battle ends if one side's all combatants' HP drop to 0 (winner decided), or if 5 minutes after the battle started pass (tie).
            In case of a tie, both players will get their money back.

            The battle's winner will receive a PvP win, which shows on their profile.
            (This command has a cooldown of 5 minutes)"""
        )
        try:
            if enemy == ctx.author:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You can't battle yourself."))

            if ctx.character_data["money"] < money:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You are too poor."))

            # Deduct money from the author
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )

            # Prepare battle initiation message
            if not enemy:
                
                text = _("{author} - **LVL {level}** seeks a raidbattle! The price is **${money}**.").format(
                    author=ctx.author.mention, level=rpgtools.xptolevel(ctx.character_data["xp"]), money=money
                )
            else:
                async with self.bot.pool.acquire() as conn:
                    query = 'SELECT xp FROM profile WHERE "user" = $1;'
                    xp_value = await conn.fetchval(query, enemy.id)
                
                
                text = _(
                    "{author} - **LVL {level}** seeks a raidbattle with {enemy} - LVL **{levelen}**! The price is **${money}**."
                ).format(
                    author=ctx.author.mention,
                    level=rpgtools.xptolevel(ctx.character_data["xp"]),
                    enemy=enemy.mention,
                    levelen=rpgtools.xptolevel(xp_value) if xp_value else "Unknown",
                    money=money
                )

            # Define a check for the join view
            async def check(user: discord.User) -> bool:
                return await has_money(self.bot, user.id, money)

            # Create the join view
            future = asyncio.Future()
            view = SingleJoinView(
                future,
                Button(
                    style=discord.ButtonStyle.primary,
                    label=_("Join the raidbattle!"),
                    emoji="\U00002694",
                ),
                allowed=enemy,
                prohibited=ctx.author,
                timeout=60,
                check=check,
                check_fail_message=_("You don't have enough money to join the raidbattle."),
            )

            await ctx.send(text, view=view)

            try:
                enemy_ = await future
            except asyncio.TimeoutError:
                await self.bot.reset_cooldown(ctx)
                # Refund money to the author
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    ctx.author.id,
                )
                return await ctx.send(
                    _("No one wanted to join your raidbattle, {author}!").format(
                        author=ctx.author.mention
                    )
                )

            # Deduct money from the enemy
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                enemy_.id
            )

            # Create and start the battle using the factory
            battle = await self.battle_factory.create_battle(
                "raid", 
                ctx, 
                player1=ctx.author,
                player2=enemy_,
                money=money
            )
            
            # Start the battle
            await battle.start_battle()
            
            # Run the battle until completion
            while not await battle.is_battle_over():
                await battle.process_turn()
                await asyncio.sleep(2)  # 2 second delay between turns
            
            # Get the result
            result = await battle.end_battle()
            
            if result:
                winner, loser = result
                await ctx.send(
                    _("{winner} won the raidbattle vs {loser}! Congratulations!").format(
                        winner=winner.mention, loser=loser.mention
                    )
                )
            else:
                # Battle ended in a tie
                await ctx.send(
                    _("The raidbattle between {p1} and {p2} ended in a tie! Money has been refunded.").format(
                        p1=ctx.author.mention, p2=enemy_.mention
                    )
                )
                # Refund money to both players
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user" IN ($2, $3);',
                        money,
                        ctx.author.id,
                        enemy_.id
                    )
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    @has_char()
    @user_cooldown(100)
    @commands.command(brief=_("Battle in teams of two against another team (includes raidstats)"))
    @locale_doc
    async def raidbattle2v2(self, ctx, money: IntGreaterThan(-1) = 0, teammate: discord.Member = None, opponents: commands.Greedy[discord.Member] = None):
        _(
            """`[money]` - A whole number that can be 0 or greater; defaults to 0
            `[teammate]` - A user who will join your team
            `[opponents]` - Two users who will be the opposing team

            Fight in teams of two against another team while betting money.
            To decide the players' stats, their items, race and class bonuses and raidstats are evaluated.

            You also have a chance of tripping depending on your luck.

            The money is removed from all players at the start of the battle. Once a winning team has been decided, they will receive their money, plus the opposing team's money.
            The battle is divided into rounds, where each team takes turns attacking.

            The battle ends if all players on a team have their HP drop to 0 (winner decided), or if 5 minutes after the battle started pass (tie).
            In case of a tie, all players will get their money back.

            Each member of the winning team will receive a PvP win, which shows on their profile.
            (This command has a cooldown of 5 minutes)"""
        )
        # Check if the initiator has enough money
        if ctx.character_data["money"] < money:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You are too poor."))

        # Determine if we're using open enrollment
        open_enrollment = teammate is None and (not opponents or len(opponents) == 0)

        if not open_enrollment:
            # Validate specific player configuration
            if teammate == ctx.author:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You can't be your own teammate."))

            if not opponents or len(opponents) != 2:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You must specify exactly two opponents."))

            if ctx.author in opponents or teammate in opponents:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("Invalid team configuration."))

        # Deduct money from initiating player
        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
            money,
            ctx.author.id,
        )

        # Function to check if a user has enough money and a character
        async def check_character_and_money(user: discord.User) -> bool:
            # Check if user has a character
            if not await self.bot.pool.fetchrow('SELECT 1 FROM profile WHERE "user"=$1', user.id):
                return False
            # Check if user has enough money (if bet amount > 0)
            if money > 0:
                return await has_money(self.bot, user.id, money)
            return True

        # Handle open or specific enrollment
        if open_enrollment:
            # Open enrollment implementation
            participants = [ctx.author]
            participant_ids = {ctx.author.id}
            
            battle_msg = None
            
            class OpenBattleView(discord.ui.View):
                def __init__(self, bot):
                    super().__init__(timeout=60)
                    self.bot = bot
                    self.is_complete = False
                
                @discord.ui.button(label=_("Join Battle"), style=discord.ButtonStyle.primary, emoji="⚔️")
                async def join_battle(self, interaction: discord.Interaction, button: discord.ui.Button):
                    user = interaction.user
                    
                    # Check if user is already in the battle
                    if user.id in participant_ids:
                        return await interaction.response.send_message(
                            _("You have already joined this battle."), ephemeral=True
                        )
                    
                    # Check if user has a character and enough money
                    if not await check_character_and_money(user):
                        if not await self.bot.pool.fetchrow('SELECT 1 FROM profile WHERE "user"=$1', user.id):
                            return await interaction.response.send_message(
                                _("You don't have a character to participate."), ephemeral=True
                            )
                        else:
                            return await interaction.response.send_message(
                                _("You don't have enough money to join this battle."), ephemeral=True
                            )
                    
                    # Deduct money from the player
                    if money > 0:
                        await self.bot.pool.execute(
                            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                            money,
                            user.id,
                        )
                    
                    # Add user to participants
                    participants.append(user)
                    participant_ids.add(user.id)
                    
                    # Acknowledge the interaction
                    await interaction.response.send_message(_("You have joined the battle!"), ephemeral=True)
                    
                    # Update the battle message
                    joined_text = "\n".join([f"• {p.mention}" for p in participants])
                    needed = 4 - len(participants)
                    
                    await battle_msg.edit(content=_(
                        "{author} has started a 2v2 raidbattle! The price is **${money}** per player.\n"
                        "**Participants ({count}/4):**\n{participants}\n\n"
                        "{needed_text}"
                    ).format(
                        author=ctx.author.mention,
                        money=money,
                        count=len(participants),
                        participants=joined_text,
                        needed_text=_("Need {more} more players to start!").format(more=needed) if needed > 0 else _("Battle ready to begin!")
                    ))
                    
                    # If we have 4 players, start the battle
                    if len(participants) >= 4:
                        self.is_complete = True
                        for item in self.children:
                            item.disabled = True
                        await battle_msg.edit(view=self)
                        self.stop()
            
            # Create the view and send the initial message
            view = OpenBattleView(self.bot)
            battle_msg = await ctx.send(
                _("{author} has started a 2v2 raidbattle! The price is **${money}** per player.\n"
                "**Participants (1/4):**\n• {author}\n\n"
                "Need 3 more players to start!").format(
                    author=ctx.author.mention,
                    money=money
                ),
                view=view
            )
            
            # Wait for the view to complete or timeout
            await view.wait()
            
            # Check if we have enough players
            if not view.is_complete:
                await self.bot.reset_cooldown(ctx)
                # Refund money to all participants
                for participant in participants:
                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        participant.id,
                    )
                return await ctx.send(_("Not enough players joined the battle. Money has been refunded."))
            
            # Randomly assign teams
            random.shuffle(participants)
            team_a = participants[:2]
            team_b = participants[2:]
            
        else:
            # Specific player enrollment
            # Create future for teammate
            teammate_future = asyncio.Future()
            view = SingleJoinView(
                teammate_future,
                Button(
                    style=ButtonStyle.primary,
                    label=_("Join the team!"),
                    emoji="🤝",
                ),
                allowed=teammate,
                prohibited=ctx.author,
                timeout=60,
                check=check_character_and_money,
                check_fail_message=_("You don't have a character or enough money to join the raidbattle."),
            )
            
            # Send invitation to teammate
            await ctx.send(
                _("{teammate}, {author} has invited you to join their team in a 2v2 raidbattle! The price is **${money}** per player.").format(
                    teammate=teammate.mention,
                    author=ctx.author.mention,
                    money=money
                ),
                view=view
            )
            
            # Wait for teammate to join
            try:
                teammate_ = await asyncio.wait_for(teammate_future, timeout=60)
            except asyncio.TimeoutError:
                await self.bot.reset_cooldown(ctx)
                # Refund money to author
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    ctx.author.id,
                )
                return await ctx.send(
                    _("Your teammate did not join in time, {author}.").format(
                        author=ctx.author.mention
                    )
                )
            
            # Take money from teammate
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                teammate_.id,
            )
            
            # Invite opponents
            opponent_futures = []
            for opponent in opponents:
                future = asyncio.Future()
                view = SingleJoinView(
                    future,
                    Button(
                        style=ButtonStyle.primary,
                        label=_("Accept Challenge"),
                        emoji="⚔️",
                    ),
                    allowed=opponent,
                    prohibited=[ctx.author, teammate_],
                    timeout=60,
                    check=check_character_and_money,
                    check_fail_message=_("You don't have a character or enough money to join the raidbattle."),
                )
                
                await ctx.send(
                    _("{opponent}, you have been challenged to a 2v2 raidbattle by {author} and {teammate}! The price is **${money}** per player.").format(
                        opponent=opponent.mention,
                        author=ctx.author.mention,
                        teammate=teammate_.mention,
                        money=money
                    ),
                    view=view
                )
                opponent_futures.append(future)
            
            # Wait for both opponents to join
            opponents_ = []
            try:
                for future in opponent_futures:
                    opponent = await asyncio.wait_for(future, timeout=60)
                    opponents_.append(opponent)
                    
                    # Take money from opponent
                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                        money,
                        opponent.id,
                    )
            except asyncio.TimeoutError:
                await self.bot.reset_cooldown(ctx)
                # Refund money to all participants so far
                participants = [ctx.author, teammate_] + opponents_
                for participant in participants:
                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        participant.id,
                    )
                return await ctx.send(
                    _("Not all opponents joined in time. Money has been refunded.")
                )
            
            # Set teams
            team_a = [ctx.author, teammate_]
            team_b = opponents_

        # Announce teams
        await ctx.send(
            _("**Team A**: {team_a_members}\n**Team B**: {team_b_members}\n\nLet the battle begin!").format(
                team_a_members=", ".join(member.mention for member in team_a),
                team_b_members=", ".join(member.mention for member in team_b)
            )
        )

        # Create and start the battle
        battle = await self.battle_factory.create_battle(
            "team",
            ctx,
            team_a=team_a,
            team_b=team_b,
            money=money
        )
        
        # Start the battle
        await battle.start_battle()
        
        # Run the battle until completion
        while not await battle.is_battle_over():
            await battle.process_turn()
            await asyncio.sleep(4)  # Delay between turns for readability
        
        # Get the result
        result = await battle.end_battle()
        
        if result:
            # Battle has a winner
            winning_team, losing_team = result
            await ctx.send(
                _("Team {winning_team} won the battle against Team {losing_team}! Congratulations!").format(
                    winning_team=winning_team,
                    losing_team=losing_team
                )
            )
        else:
            # Battle ended in a tie
            await ctx.send(_("The battle ended in a tie! All money has been refunded."))
            # Refund money to all players
            for player in team_a + team_b:
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    player.id,
                )

    @has_char()
    @commands.command(
        brief=_("Toggle splice monsters in your PvE pool"),
        aliases=["pvesplices", "pvepoolsplice", "splicepve"],
    )
    @locale_doc
    async def pvesplice(self, ctx, mode: str = "toggle"):
        """
        Toggle splice monster injection in your regular PvE pool.

        Usage:
        - `$pvesplice` (toggle)
        - `$pvesplice on`
        - `$pvesplice off`
        - `$pvesplice status`
        """
        normalized = str(mode or "toggle").strip().lower()
        current = await self._get_user_pve_splice_toggle(ctx.author.id)

        if normalized in {"status", "state", "show"}:
            new_state = current
            changed = False
        elif normalized in {"on", "enable", "enabled", "yes", "true", "1"}:
            new_state = True
            changed = new_state != current
        elif normalized in {"off", "disable", "disabled", "no", "false", "0"}:
            new_state = False
            changed = new_state != current
        elif normalized in {"toggle", "flip", "switch"}:
            new_state = not current
            changed = True
        else:
            await ctx.send("Usage: `$pvesplice [on|off|toggle|status]`")
            return

        if changed:
            await self._set_user_pve_splice_toggle(ctx.author.id, new_state)

        if new_state:
            await ctx.send(
                "✅ Splice injection is **ON**. Your `$pve` and `$scout` pools now include sampled Gen 0 splice monsters."
            )
        else:
            await ctx.send(
                "✅ Splice injection is **OFF**. Your `$pve` and `$scout` use only the default monster pool."
            )

    @has_char()
    @commands.command(
        brief=_("Show PvE location unlocks and tier highlights"),
        aliases=["pvelocs", "pvemap"],
    )
    @locale_doc
    async def pvelocations(self, ctx):
        _(
            """Show all PvE locations, their unlock levels, and strongest tier rates.
            Use `$pveinfo <location>` for exact tier-by-tier odds."""
        )
        player_level = rpgtools.xptolevel(ctx.character_data.get("xp", 0))
        lines = []

        for location in self.PVE_LOCATIONS:
            unlock_level = int(location.get("unlock_level", 1))
            unlocked = player_level >= unlock_level
            status_icon = "✅" if unlocked else "🔒"

            rates = self._get_pve_tier_rates_for_location(location)
            if rates:
                tier_ids = [tier for tier, _ in rates]
                min_tier = min(tier_ids)
                max_tier = max(tier_ids)
                tier_band = f"T{min_tier}" if min_tier == max_tier else f"T{min_tier}-T{max_tier}"
                top_tier, top_rate = max(rates, key=lambda entry: entry[1])
                top_label = "God" if top_tier == self.PVE_GOD_TIER else f"T{top_tier}"
                top_rate_text = self._format_pve_rate_percent(top_rate)
            else:
                tier_band = "T?"
                top_label = "T?"
                top_rate_text = "0%"

            lines.append(
                f"{status_icon} **{location['name']}** (`{location['id']}`) "
                f"- Lv {unlock_level}+ - {tier_band} - Top {top_label} {top_rate_text}"
            )

        if not lines:
            await ctx.send("No PvE locations are configured.")
            return

        embed = discord.Embed(
            title="PvE Locations",
            description=f"Your level: **{player_level}**",
            color=self.bot.config.game.primary_colour,
        )

        # Keep each field below Discord's 1024-char limit.
        chunk: list[str] = []
        chunk_len = 0
        section_index = 1
        for line in lines:
            projected = chunk_len + len(line) + 1
            if chunk and projected > 980:
                field_name = "Locations" if section_index == 1 else f"Locations ({section_index})"
                embed.add_field(name=field_name, value="\n".join(chunk), inline=False)
                section_index += 1
                chunk = [line]
                chunk_len = len(line) + 1
            else:
                chunk.append(line)
                chunk_len = projected
        if chunk:
            field_name = "Locations" if section_index == 1 else f"Locations ({section_index})"
            embed.add_field(name=field_name, value="\n".join(chunk), inline=False)

        embed.set_footer(text="Use `$pveinfo <location name or id>` for exact odds.")
        await ctx.send(embed=embed)

    @has_char()
    @commands.command(
        brief=_("Show exact encounter rates for one PvE location"),
        aliases=["pvelocinfo", "locationinfo"],
    )
    @locale_doc
    async def pveinfo(self, ctx, *, location_query: str = ""):
        _(
            """`<location>` - location name or id
            Show exact tier encounter odds for a PvE location."""
        )
        player_level = rpgtools.xptolevel(ctx.character_data.get("xp", 0))
        query = str(location_query or "").strip()
        if not query:
            location_list = ", ".join(f"`{loc['id']}`" for loc in self.PVE_LOCATIONS)
            await ctx.send(
                "Usage: `$pveinfo <location name or id>`\n"
                f"Available ids: {location_list}"
            )
            return

        location = self._resolve_pve_location_query(query)
        if not location:
            await ctx.send(
                "Unknown location. Use `$pvelocations` to view ids, then run `$pveinfo <id>`."
            )
            return

        unlock_level = int(location.get("unlock_level", 1))
        unlocked = player_level >= unlock_level
        rates = self._get_pve_tier_rates_for_location(location)
        if rates:
            rate_lines = []
            for tier, rate in rates:
                if tier == self.PVE_GOD_TIER:
                    tier_name = "Tier 11 (God)"
                elif tier == 12:
                    tier_name = "Tier 12 (Level X)"
                else:
                    tier_name = f"Tier {tier}"
                rate_lines.append(
                    f"• {tier_name}: **{self._format_pve_rate_percent(rate)}**"
                )
            rates_text = "\n".join(rate_lines)
        else:
            rates_text = "No tier rates configured."

        splice_enabled = await self._get_user_pve_splice_toggle(ctx.author.id)
        pool_text = (
            "Default + sampled Gen 0 splice monsters (`$pvesplice` is ON)."
            if splice_enabled
            else "Default monster pool only (`$pvesplice` is OFF)."
        )

        embed = discord.Embed(
            title=f"PvE Info: {location['name']}",
            description=(
                f"ID: `{location['id']}`\n"
                f"Unlock: **Lv {unlock_level}+** "
                f"({'Unlocked' if unlocked else '🔒 Locked'})"
            ),
            color=self.bot.config.game.primary_colour,
        )
        embed.add_field(name="Encounter Rates", value=rates_text, inline=False)
        embed.add_field(name="Monster Pool", value=pool_text, inline=False)
        embed.add_field(
            name="How This Works",
            value=(
                "Location first rolls a tier using these odds, then picks a random "
                "monster from your current tier pool."
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @has_char()
    @commands.command(brief=_("Battle against a monster and gain XP"))
    @user_cooldown(1800)  # 30-minute cooldown
    @locale_doc
    async def pve(self, ctx, pool_option: str = "default"):
        """Battle against a monster and gain experience points.

        Optional legacy override:
        - `$pve splice` to force splice injection for this run
        - `$pve normal` to force default-only pool for this run
        """
        pool_override = getattr(ctx, "pve_pool_override", None)
        requested_pool = str(pool_override or pool_option or "").strip().lower()
        if requested_pool in {"", "default"}:
            include_splice_override = None
        elif requested_pool in {"splice", "splices", "sp"}:
            include_splice_override = True
        elif requested_pool in {"normal", "base", "off", "nosplice"}:
            include_splice_override = False
        else:
            await ctx.send(
                "Unknown PvE option. Use `$pve` normally, `$pvesplice on/off`, "
                "or one-run overrides `$pve splice` / `$pve normal`."
            )
            await self.bot.reset_cooldown(ctx)
            return

        # Check for macro detection
        macro_detected = await self.check_pve_macro_detection(ctx.author.id)
        if macro_detected:
            try:
                if self.macro_alert_user_id:
                    user = await self.bot.fetch_user(self.macro_alert_user_id)
                    await user.send(f"User {ctx.author.id} detected using macros in PVE command!")
            except:
                pass  # Silently fail if DM fails
        
        # Debug: Log macro detection data
        if ctx.author.id in self.pve_macro_detection:
            user_data = self.pve_macro_detection[ctx.author.id]
            print(f"Macro debug - User {ctx.author.id}: count={user_data['count']}, macro_detected={macro_detected}")

        
        # Check for monster override from scout command
        monster_override = getattr(ctx, 'monster_override', None)
        levelchoice_override = getattr(ctx, 'levelchoice_override', None)
        locationchoice_override = getattr(ctx, 'locationchoice_override', None)

        # Load monsters data
        try:
            monsters, splice_injected = await self._get_pve_monster_pool_for_user(
                ctx.author.id,
                force_include_splice=include_splice_override,
            )
        except Exception as e:
            await ctx.send(_("Error loading monsters data. Please contact the admin."))
            await self.bot.reset_cooldown(ctx)
            return

        # Fetch the player's XP and determine level
        player_xp = ctx.character_data.get("xp", 0)
        player_level = rpgtools.xptolevel(player_xp)
        selected_location = None

        if not monster_override:
            all_locations = []
            for location in self.PVE_LOCATIONS:
                location_entry = dict(location)
                location_entry["is_locked"] = player_level < int(location_entry["unlock_level"])
                all_locations.append(location_entry)

            unlocked_locations = [
                location for location in all_locations if not location.get("is_locked")
            ]
            if not unlocked_locations:
                await ctx.send(_("No PvE locations are unlocked for your level yet."))
                await self.bot.reset_cooldown(ctx)
                return

            def format_god_percent(value):
                try:
                    return f"{float(value):g}%"
                except (TypeError, ValueError):
                    return f"{value}%"

            def build_location_block(location, icon):
                tier_keys = sorted(int(tier) for tier in location["tier_weights"].keys())
                if tier_keys:
                    tier_band = (
                        f"T{tier_keys[0]}"
                        if len(tier_keys) == 1
                        else f"T{tier_keys[0]}-T{tier_keys[-1]}"
                    )
                else:
                    tier_band = "T?"
                god_text = format_god_percent(location.get("god_chance", 0))
                return (
                    f"{icon} **{location['name']}**\n"
                    f"`Lv {location['unlock_level']}+`  `Tiers {tier_band}`  `God {god_text}`"
                )

            unlocked_blocks = []
            locked_blocks = []
            for location in all_locations:
                if location.get("is_locked"):
                    locked_blocks.append(build_location_block(location, "🔒"))
                else:
                    unlocked_blocks.append(build_location_block(location, "🟢"))

            location_embed = discord.Embed(
                title=_("Choose a PvE Location"),
                description=(
                    f"Your level: **{player_level}**\n"
                    "Pick a location from the dropdown below.\n"
                    "Preview key: `Lv` unlock level, `Tiers` encounter band, `God` god encounter chance."
                ),
                color=self.bot.config.game.primary_colour,
            )

            def add_location_fields(embed, title, blocks):
                if not blocks:
                    return
                chunk = []
                chunk_len = 0
                section_index = 1
                for block in blocks:
                    projected = chunk_len + len(block) + 2
                    if chunk and projected > 980:
                        suffix = "" if section_index == 1 else f" ({section_index})"
                        embed.add_field(
                            name=f"{title}{suffix}",
                            value="\n\n".join(chunk),
                            inline=False,
                        )
                        section_index += 1
                        chunk = [block]
                        chunk_len = len(block)
                    else:
                        chunk.append(block)
                        chunk_len = projected
                if chunk:
                    suffix = "" if section_index == 1 else f" ({section_index})"
                    embed.add_field(
                        name=f"{title}{suffix}",
                        value="\n\n".join(chunk),
                        inline=False,
                    )

            add_location_fields(
                location_embed,
                f"Unlocked ({len(unlocked_blocks)})",
                unlocked_blocks,
            )
            add_location_fields(
                location_embed,
                f"Locked ({len(locked_blocks)})",
                locked_blocks,
            )

            location_embed.add_field(
                name=_("Need Exact Odds?"),
                value=_("Use `$pveinfo <location>` for full tier rates."),
                inline=False,
            )
            if splice_injected:
                location_embed.set_footer(
                    text="Splice injection active: sampled Gen 0 splice monsters are mixed into your pool."
                )
            else:
                location_embed.set_footer(
                    text="Tip: Use `$pvelocations` for a quick overview of all zones."
                )

            allowed_location_users = {ctx.author.id}
            alt_invoker_id = getattr(ctx, "alt_invoker_id", None)
            if alt_invoker_id is not None:
                allowed_location_users.add(int(alt_invoker_id))

            location_view = PVELocationView(
                author_id=ctx.author.id,
                locations=all_locations,
                timeout=60.0,
                allowed_user_ids=allowed_location_users,
            )
            location_message = await ctx.send(embed=location_embed, view=location_view)
            location_view.message = location_message

            await location_view.wait()

            if location_view.cancelled:
                await self.bot.reset_cooldown(ctx)
                return

            if not location_view.selected_location:
                await ctx.send(_("⏱️ Location selection timed out."))
                await self.bot.reset_cooldown(ctx)
                return

            selected_location = location_view.selected_location

        # Send an embed indicating that the player is searching for a monster
        if selected_location:
            searching_description = _(
                "You head toward **{location}** in search of a worthy foe."
            ).format(location=selected_location["name"])
        else:
            searching_description = _(
                "Your journey begins as you venture into the unknown to find a worthy foe."
            )

        searching_embed = discord.Embed(
            title=_("Searching for a monster..."),
            description=searching_description,
            color=self.bot.config.game.primary_colour,
        )
        searching_message = await ctx.send(embed=searching_embed)

        # Determine monster to fight
        if not monster_override:
            # Simulate searching time
            await asyncio.sleep(random.randint(3, 8))
            levelchoice = self._roll_pve_tier_for_location(selected_location)
            monster_pool = monsters.get(levelchoice, [])
            if not monster_pool:
                await ctx.send(_("No public monsters are configured for this tier."))
                await self.bot.reset_cooldown(ctx)
                return

            base_monster = random.choice(monster_pool)
            forced_level = (
                self.PVE_GOD_ENCOUNTER_LEVEL
                if levelchoice == self.PVE_GOD_TIER
                else None
            )
            monster = self._scale_monster_for_encounter(
                base_monster,
                levelchoice,
                encounter_level=forced_level,
            )
            if base_monster.get("pve_pool"):
                monster["pve_pool"] = base_monster["pve_pool"]
            monster["pve_location_id"] = selected_location["id"]
            monster["pve_location_name"] = selected_location["name"]

            if levelchoice == self.PVE_GOD_TIER:
                legendary_embed = discord.Embed(
                    title=_("A Legendary God Appears!"),
                    description=_(
                        "Behold! **Level {level} {monster}** has descended to challenge you! Prepare for an epic battle!"
                    ).format(
                        level=monster["encounter_level"],
                        monster=monster["name"],
                    ),
                    color=discord.Color.gold(),
                )
                if selected_location:
                    legendary_embed.add_field(
                        name=_("Location"),
                        value=selected_location["name"],
                        inline=False,
                    )
                await searching_message.edit(embed=legendary_embed)
                await asyncio.sleep(4)
        else:
            # Use override from scout command
            monster = dict(monster_override)
            levelchoice = int(
                levelchoice_override
                or monster.get("pve_tier")
                or self._get_pve_tier_for_player_level(player_level)
            )
            if "encounter_level" not in monster:
                monster = self._scale_monster_for_encounter(monster, levelchoice)
            selected_location = self._get_pve_location_by_id(
                monster.get("pve_location_id")
            )
            if not selected_location:
                selected_location = self._get_pve_location_by_id(locationchoice_override)
            if not selected_location and monster.get("pve_location_name"):
                selected_location = {
                    "name": monster["pve_location_name"],
                    "id": monster.get("pve_location_id", "unknown"),
                }

        encounter_level = int(monster.get("encounter_level", levelchoice))

        # Update embed with found monster
        is_splice_pool = monster.get("pve_pool") == "splice"
        if selected_location:
            found_description = (
                _(
                    "In **{location}**, a Spliced Level {level} **{monster}** has appeared! Prepare to fight.."
                ).format(
                    location=selected_location["name"],
                    level=encounter_level,
                    monster=monster["name"],
                )
                if is_splice_pool
                else _(
                    "In **{location}**, a Level {level} **{monster}** has appeared! Prepare to fight.."
                ).format(
                    location=selected_location["name"],
                    level=encounter_level,
                    monster=monster["name"],
                )
            )
        else:
            found_description = (
                _(
                    "A Spliced Level {level} **{monster}** has appeared! Prepare to fight.."
                ).format(
                    level=encounter_level,
                    monster=monster["name"],
                )
                if is_splice_pool
                else _(
                    "A Level {level} **{monster}** has appeared! Prepare to fight.."
                ).format(
                    level=encounter_level,
                    monster=monster["name"],
                )
            )

        found_embed = discord.Embed(
            title=_("Monster Found!"),
            description=found_description,
            color=self.bot.config.game.primary_colour,
        )
        await searching_message.edit(embed=found_embed)
        await asyncio.sleep(4)

        # Check for macro penalty
        macro_penalty_level = self.get_pve_macro_penalty_level(ctx.author.id)
        
        # Create and start the battle
        try:
            battle = await self.battle_factory.create_battle(
                "pve",
                ctx,
                player=ctx.author,
                monster_data=monster,
                monster_level=levelchoice,
                macro_penalty_level=macro_penalty_level
            )
            
            # Start the battle
            await battle.start_battle()
            
            # Run the battle until completion
            while not await battle.is_battle_over():
                await battle.process_turn()
                await asyncio.sleep(1)  # 1 second delay between turns
            
            # End the battle and determine the outcome
            result = await battle.end_battle()
            
            # Handle egg drops and other PvE-specific outcomes
            if result and result.name == "Player":
                # Player won - handle PvE drops (skip if macro penalty is active)
                if levelchoice < 12 and macro_penalty_level == 0:
                    # God fights now roll alignment shards directly (not affected by ranger bonuses).
                    if self._is_god_shard_monster(monster):
                        await self.handle_god_shard_drop(ctx, monster)
                    else:
                        # Non-god fights retain egg drop behavior.
                        if levelchoice == 11:
                            base_egg_chance = 0.02
                        else:
                            base_egg_chance = 0.50 - ((levelchoice - 1) / 9) * 0.45
                        final_egg_chance = base_egg_chance
                        
                        # Check for Ranger class bonus
                        ranger_egg_bonuses = {
                            "Caretaker": 0.02,  # +2% (total 7%)
                            "Tamer": 0.04,      # +4% (total 9%)
                            "Trainer": 0.06,    # +6% (total 11%)
                            "Bowman": 0.08,     # +8% (total 13%)
                            "Hunter": 0.10,     # +10% (total 15%)
                            "Warden": 0.13,     # +13% (total 18%)
                            "Ranger": 0.15,     # +15% (total 25%)
                        }
                        
                        # Apply ranger bonus if player has the class
                        async with self.bot.pool.acquire() as conn:
                            profile = await conn.fetchrow('SELECT class FROM profile WHERE "user"=$1;', ctx.author.id)
                            if profile and profile['class']:
                                # Find the highest ranger bonus
                                ranger_bonus = 0
                                for class_name in profile['class']:
                                    if class_name in ranger_egg_bonuses:
                                        class_bonus = ranger_egg_bonuses[class_name]
                                        ranger_bonus = max(ranger_bonus, class_bonus)
                                        
                                # Apply ranger bonus with scaling
                                bonus_multiplier = 1.0 - ((levelchoice - 1) / 9) * (1/3)
                                adjusted_ranger_bonus = ranger_bonus * bonus_multiplier
                                final_egg_chance += adjusted_ranger_bonus
                        
                        # Check for egg drop
                        if random.random() < final_egg_chance:
                            await self.handle_egg_drop(ctx, monster, levelchoice)
            
                # Dispatch PVE completion event
                success = True
                self.bot.dispatch(
                    "PVE_completion",
                    ctx,
                    success,
                    monster["name"],
                    monster.get("element", "Unknown"),
                    levelchoice,
                    getattr(battle, "battle_id", None),
                )
            
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)
            await self.bot.reset_cooldown(ctx)

    async def handle_egg_drop(self, ctx, monster, levelchoice):
        """Handle monster egg drops from PVE battles."""
        async with self.bot.pool.acquire() as conn:
            # Count pets, unhatched eggs, and pending splice requests
            pet_and_egg_count = await conn.fetchval(
                """
                SELECT 
                    (SELECT COUNT(*) FROM monster_pets WHERE user_id = $1) +
                    (SELECT COUNT(*) FROM monster_eggs WHERE user_id = $1 AND hatched = FALSE) +
                    (SELECT COUNT(*) FROM splice_requests WHERE user_id = $1 AND status = 'pending')
                """,
                ctx.author.id
            )
            
            # Determine max allowed based on tier
            total_allowed = 10
            if ctx.character_data["tier"] == 1:
                total_allowed = 12
            elif ctx.character_data["tier"] == 2:
                total_allowed = 14
            elif ctx.character_data["tier"] == 3:
                total_allowed = 17
            elif ctx.character_data["tier"] == 4:
                total_allowed = 25
            
            # Check if player has reached the limit
            if pet_and_egg_count >= total_allowed:
                # Get detailed pet and egg information for the dropdown
                pet_and_egg_list = []
                
                # Get detailed pet information
                pets = await conn.fetch(
                    """
                    SELECT id, name as display_name, 'pet' as type, 
                           element, growth_stage, growth_index, hp, attack, defense, 
                           "IV", happiness, hunger, equipped, url
                    FROM monster_pets 
                    WHERE user_id = $1
                    """,
                    ctx.author.id
                )
                
                # Get detailed egg information
                eggs = await conn.fetch(
                    """
                    SELECT id, egg_type as display_name, 'egg' as type,
                           element, hatch_time, "IV", hp, attack, defense, url
                    FROM monster_eggs 
                    WHERE user_id = $1 AND hatched = FALSE
                    """,
                    ctx.author.id
                )
                
                # Combine and format the results
                for pet in pets:
                    pet_dict = dict(pet)
                    pet_dict['growth_stage'] = pet.get('growth_stage', 'unknown')
                    pet_dict['growth_index'] = pet.get('growth_index', 1)
                    pet_dict['happiness'] = pet.get('happiness', 50)
                    pet_dict['hunger'] = pet.get('hunger', 50)
                    pet_dict['equipped'] = pet.get('equipped', False)
                    pet_and_egg_list.append(pet_dict)
                    
                for egg in eggs:
                    egg_dict = dict(egg)
                    egg_dict['egg_type'] = egg.get('egg_type', 'Unknown Egg')
                    egg_dict['hatch_time'] = egg.get('hatch_time')
                    egg_dict['IV'] = egg.get('IV', 0)
                    egg_dict['hp'] = egg.get('hp', 0)
                    egg_dict['attack'] = egg.get('attack', 0)
                    egg_dict['defense'] = egg.get('defense', 0)
                    pet_and_egg_list.append(egg_dict)
                
                if not pet_and_egg_list:
                    await ctx.send(_("Something went wrong retrieving your pets/eggs."))
                    return
                
                # Create a view with dropdown and buttons
                view = PetEggReleaseView(
                    ctx.author,
                    pet_and_egg_list,
                    timeout=120.0
                )
                
                # Create an initial embed for the release prompt
                embed = discord.Embed(
                    title=_("Release a Pet/Egg"),
                    description=_("You've reached the maximum number of pets/eggs. Please select one to release to make room for the new egg."),
                    color=discord.Color.orange()
                )
                
                # Add a field with instructions
                embed.add_field(
                    name="How to proceed",
                    value="Use the dropdown below to select a pet/egg to release. You'll see its details before confirming.",
                    inline=False
                )
                
                # Send the message with the view
                message = await ctx.send(embed=embed, view=view)
                view.message = message  # Store the message reference in the view
                
                # Wait for the user to make a selection
                try:
                    await view.wait()
                    if view.value is None:
                        await message.edit(content=_("⏱️ Timed out. No egg awarded."), embed=None, view=None)
                        return
                    if view.value == "cancel":
                        await message.edit(content=_("❌ No egg awarded."), embed=None, view=None)
                        return
                    choice = view.value + 1  # Adjust for 0-based index
                except asyncio.TimeoutError:
                    await message.edit(content=_("Timed out. No egg awarded."), embed=None, view=None)
                    return
                
                if not 1 <= choice <= len(pet_and_egg_list):
                    await ctx.send(_("That number is not in the list. No egg awarded."))
                    return
                
                # Identify the record to remove
                record_to_remove = pet_and_egg_list[choice - 1]
                
                # Remove the chosen pet/egg from its table
                try:
                    # Check if the item exists in the user's collection
                    table = "monster_pets" if record_to_remove["type"] == "pet" else "monster_eggs"
                    item = await conn.fetchrow(f"SELECT * FROM {table} WHERE user_id = $1 AND id = $2;",
                                               ctx.author.id, record_to_remove["id"])

                    if not item:
                        await ctx.send(_("❌ No {type} with ID `{id}` found in your collection.").format(
                            type=record_to_remove["type"], id=record_to_remove["id"]))
                        return

                    # Delete the item
                    await conn.execute(f"DELETE FROM {table} WHERE id = $1;", record_to_remove["id"])

                    await ctx.send(
                        _(f"Released {record_to_remove['type']} '{record_to_remove['display_name']}' to make room."))

                except Exception as e:
                    await ctx.send(_("An error occurred while releasing the pet/egg: ") + str(e))
                    return
            
            # Generate random IV percentage
            iv_percentage = random.uniform(10, 1000)
            if iv_percentage < 20:
                iv_percentage = random.uniform(90, 100)
            elif iv_percentage < 70:
                iv_percentage = random.uniform(80, 90)
            elif iv_percentage < 150:
                iv_percentage = random.uniform(70, 80)
            elif iv_percentage < 350:
                iv_percentage = random.uniform(60, 70)
            elif iv_percentage < 700:
                iv_percentage = random.uniform(50, 60)
            else:
                iv_percentage = random.uniform(30, 50)
            
            # Calculate IVs
            total_iv_points = (iv_percentage / 100) * 200
            
            # Allocate IV points
            def allocate_iv_points(total_points):
                a = random.random()
                b = random.random()
                c = random.random()
                total = a + b + c
                hp_iv = int(round(total_points * (a / total)))
                attack_iv = int(round(total_points * (b / total)))
                defense_iv = int(round(total_points * (c / total)))
                
                # Ensure sum matches total
                iv_sum = hp_iv + attack_iv + defense_iv
                if iv_sum != int(round(total_points)):
                    diff = int(round(total_points)) - iv_sum
                    max_iv = max(hp_iv, attack_iv, defense_iv)
                    if hp_iv == max_iv:
                        hp_iv += diff
                    elif attack_iv == max_iv:
                        attack_iv += diff
                    else:
                        defense_iv += diff
                return hp_iv, attack_iv, defense_iv
            
            hp_iv, attack_iv, defense_iv = allocate_iv_points(total_iv_points)
            
            # Calculate base stats with IVs
            hp = monster["hp"] + hp_iv
            attack = monster["attack"] + attack_iv
            defense = monster["defense"] + defense_iv
            
            # Set hatch time (36 hours from now)
            egg_hatch_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=2160)
            
            # Insert egg into database
            try:
                await conn.execute(
                    """
                    INSERT INTO monster_eggs (
                        user_id, egg_type, hp, attack, defense, element, url, hatch_time,
                        "IV", hp_iv, attack_iv, defense_iv
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12);
                    """,
                    ctx.author.id,
                    monster["name"],
                    hp,
                    attack,
                    defense,
                    monster["element"],
                    monster["url"],
                    egg_hatch_time,
                    iv_percentage,
                    hp_iv,
                    attack_iv,
                    defense_iv
                )
                
                await ctx.send(
                    _(f"{ctx.author.mention}! You found a **{monster['name']} Egg** with an IV of {iv_percentage:.2f}%! It will hatch in 36 hours.")
                )
                
                # Log high IV eggs
                if iv_percentage > 95:
                    await self.bot.public_log(
                        f"**{ctx.author}** obtained a {monster['name']} egg with {iv_percentage:.2f}% IV!"
                    )
            except Exception as e:
                await ctx.send(str(e))

    @commands.command(brief="Scout ahead to see what monster you'll face")
    @has_char()
    @user_cooldown(1800)  # 30 minute cooldown
    async def scout(self, ctx):
        """Scout ahead to see what monster you'll face in PVE."""
        # Element emoji mapping
        element_to_emoji = {
            "Light": "🌟",
            "Dark": "🌑",
            "Corrupted": "🌀",
            "Nature": "🌿",
            "Electric": "⚡",
            "Water": "💧",
            "Fire": "🔥",
            "Wind": "💨",
            "Earth": "🌍",
        }
        
        # Load monsters data
        try:
            monsters, _ = await self._get_pve_monster_pool_for_user(ctx.author.id)
        except Exception as e:
            await ctx.send(_("Error loading monsters data. Please contact the admin."))
            await self.bot.reset_cooldown(ctx)
            return
        
        try:
            # Check if user is a Ranger class
            async with self.bot.pool.acquire() as conn:
                profile = await conn.fetchrow('SELECT class FROM profile WHERE "user"=$1;', ctx.author.id)
                if not profile or not profile['class']:
                    await ctx.send("You need to be a Ranger to use this ability!")
                    await self.bot.reset_cooldown(ctx)
                    return
                
                is_ranger = False
                ranger_class = None
                ranger_classes = ["Caretaker", "Tamer", "Trainer", "Bowman", "Hunter", "Warden", "Ranger"]
                for class_name in profile['class']:
                    if class_name in ranger_classes:
                        is_ranger = True
                        ranger_class = class_name
                        break
                
                if not is_ranger:
                    await ctx.send("You need to be a Ranger to use this ability!")
                    await self.bot.reset_cooldown(ctx)
                    return
                
                # Check if PVE is on cooldown
                pve_command = self.bot.get_command("pve")
                if pve_command is not None:
                    pve_ttl = await ctx.bot.redis.execute_command(
                        "TTL", f"cd:{ctx.author.id}:{pve_command.qualified_name}"
                    )
                    
                    if pve_ttl != -2:  # If cooldown exists
                        hours, remainder = divmod(pve_ttl, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        time_str = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
                        await ctx.send(f"You must wait **{time_str}** before you can scout for monsters!")
                        await self.bot.reset_cooldown(ctx)  # Reset scout cooldown since we couldn't use it
                        return
                
                # Define reroll chances based on ranger evolution
                reroll_chances = {
                    "Caretaker": 1,
                    "Tamer": 1,
                    "Trainer": 2,
                    "Bowman": 2,
                    "Hunter": 3,
                    "Warden": 3,
                    "Ranger": 4
                }
                
                max_rerolls = reroll_chances[ranger_class]
                rerolls_left = max_rerolls
                
                # Get player level for monster selection
                player_xp = ctx.character_data.get("xp", 0)
                player_level = rpgtools.xptolevel(player_xp)
                unlocked_locations = self._get_unlocked_pve_locations(player_level)
                if not unlocked_locations:
                    await ctx.send("No PvE locations are unlocked for your level yet.")
                    await self.bot.reset_cooldown(ctx)
                    return

                allowed_scout_user_ids = {ctx.author.id}
                alt_invoker_id = getattr(ctx, "alt_invoker_id", None)
                if alt_invoker_id is not None:
                    allowed_scout_user_ids.add(int(alt_invoker_id))

                location_choice_embed = discord.Embed(
                    title="Choose Scout Location",
                    description=(
                        "Pick a specific location to focus your scout rolls, or select "
                        "**Random Unlocked** to keep randomizing between unlocked zones."
                    ),
                    color=self.bot.config.game.primary_colour,
                )
                location_choice_embed.add_field(
                    name="Tip",
                    value=(
                        "Choosing one location prevents rerolls from landing in zones "
                        "you don't want."
                    ),
                    inline=False,
                )

                location_choice_view = ScoutLocationChoiceView(
                    author_id=ctx.author.id,
                    locations=unlocked_locations,
                    timeout=60.0,
                    allowed_user_ids=allowed_scout_user_ids,
                )
                location_choice_message = await ctx.send(
                    embed=location_choice_embed,
                    view=location_choice_view,
                )
                location_choice_view.message = location_choice_message

                await location_choice_view.wait()

                if location_choice_view.cancelled:
                    await self.bot.reset_cooldown(ctx)
                    return

                if location_choice_view.use_random_location is None:
                    await ctx.send("⏱️ Scout location selection timed out.")
                    await self.bot.reset_cooldown(ctx)
                    return

                forced_scout_location = (
                    None
                    if location_choice_view.use_random_location
                    else location_choice_view.selected_location
                )
                
                # Create scouting view
                class ScoutingView(discord.ui.View):
                    def __init__(
                        self,
                        ctx,
                        monster_data,
                        rerolls_left,
                        max_rerolls,
                        allowed_user_ids,
                    ):
                        super().__init__(timeout=30)
                        self.ctx = ctx
                        self.monster = monster_data
                        self.rerolls = rerolls_left
                        self.max_rerolls = max_rerolls
                        self.result = None
                        if isinstance(allowed_user_ids, int):
                            self.allowed_user_ids = {int(allowed_user_ids)}
                        else:
                            self.allowed_user_ids = {
                                int(user_id)
                                for user_id in (allowed_user_ids or [])
                                if user_id is not None
                            }
                        
                        # Add buttons
                        self.engage_button = discord.ui.Button(
                            label="Engage",
                            style=discord.ButtonStyle.success,
                            custom_id="engage"
                        )
                        self.engage_button.callback = self.engage_callback
                        self.add_item(self.engage_button)
                        
                        self.reroll_button = discord.ui.Button(
                            label="Reroll",
                            style=discord.ButtonStyle.primary,
                            custom_id="reroll"
                        )
                        self.reroll_button.callback = self.reroll_callback
                        self.add_item(self.reroll_button)
                        
                        self.retreat_button = discord.ui.Button(
                            label="Retreat",
                            style=discord.ButtonStyle.danger,
                            custom_id="retreat"
                        )
                        self.retreat_button.callback = self.retreat_callback
                        self.add_item(self.retreat_button)
                        
                        self.update_button_states()

                    def can_interact(self, interaction: discord.Interaction) -> bool:
                        return interaction.user.id in self.allowed_user_ids
                    
                    async def engage_callback(self, interaction: discord.Interaction):
                        if not self.can_interact(interaction):
                            await interaction.response.send_message("This isn't your battle!", ephemeral=True)
                            return
                        
                        await interaction.response.defer()
                        self.result = "engage"
                        self.stop()
                    
                    async def reroll_callback(self, interaction: discord.Interaction):
                        if not self.can_interact(interaction):
                            await interaction.response.send_message("This isn't your battle!", ephemeral=True)
                            return
                        
                        if self.rerolls > 0:
                            await interaction.response.defer()
                            self.rerolls -= 1
                            self.result = "reroll"
                            self.stop()
                    
                    async def retreat_callback(self, interaction: discord.Interaction):
                        if not self.can_interact(interaction):
                            await interaction.response.send_message("This isn't your battle!", ephemeral=True)
                            return
                        
                        await interaction.response.defer()
                        self.result = "retreat"
                        self.stop()
                    
                    def update_button_states(self):
                        self.reroll_button.disabled = self.rerolls <= 0
                
                # Function to select monster based on location and tier
                async def select_monster(location_data, level):
                    monster_pool = monsters.get(level, [])
                    if not monster_pool:
                        return None
                    base_monster = random.choice(monster_pool)
                    forced_level = (
                        self.PVE_GOD_ENCOUNTER_LEVEL
                        if level == self.PVE_GOD_TIER
                        else None
                    )
                    scaled_monster = self._scale_monster_for_encounter(
                        base_monster,
                        level,
                        encounter_level=forced_level,
                    )
                    if base_monster.get("pve_pool"):
                        scaled_monster["pve_pool"] = base_monster["pve_pool"]
                    scaled_monster["pve_location_id"] = location_data["id"]
                    scaled_monster["pve_location_name"] = location_data["name"]
                    return scaled_monster
                
                # Function to create monster info embed
                async def show_monster_info(monster_data, location_data, monster_tier, rerolls, max_rerolls):
                    encounter_level = int(monster_data.get("encounter_level", monster_tier))
                    embed = discord.Embed(
                        title="🔍 Monster Scouting Report",
                        description=(
                            f"Location: **{location_data['name']}**\n"
                            f"You spot a Level {encounter_level} **{monster_data['name']}** ahead!"
                        ),
                        color=discord.Color.blue()
                    )
                    
                    element_emoji = element_to_emoji.get(monster_data["element"], "❓")
                    stats_text = (
                        f"**Tier:** {monster_tier}\n"
                        f"**Element:** {element_emoji} {monster_data['element']}\n"
                        f"**HP:** {monster_data['hp']}\n"
                        f"**Attack:** {monster_data['attack']}\n"
                        f"**Defense:** {monster_data['defense']}"
                    )
                    embed.add_field(name="Stats", value=stats_text, inline=False)
                    embed.add_field(
                        name="Location Effects",
                        value=f"God chance here: **{location_data.get('god_chance', 0)}%**",
                        inline=False,
                    )
                    
                    embed.add_field(
                        name="Scouting Options",
                        value=f"Rerolls remaining: {rerolls}/{max_rerolls}",
                        inline=False
                    )
                    
                    return embed
                
                # Main scouting loop
                while True:
                    scout_location = (
                        forced_scout_location
                        if forced_scout_location is not None
                        else random.choice(unlocked_locations)
                    )
                    levelchoice = self._roll_pve_tier_for_location(scout_location)
                    
                    # Select and display monster
                    monster_data = await select_monster(scout_location, levelchoice)
                    if not monster_data:
                        await ctx.send("No public monsters are configured for this tier.")
                        await self.bot.reset_cooldown(ctx)
                        return
                    embed = await show_monster_info(
                        monster_data,
                        scout_location,
                        levelchoice,
                        rerolls_left,
                        max_rerolls
                    )
                    
                    # Show scouting view
                    view = ScoutingView(
                        ctx,
                        monster_data,
                        rerolls_left,
                        max_rerolls,
                        allowed_scout_user_ids,
                    )
                    message = await ctx.send(embed=embed, view=view)
                    
                    await view.wait()
                    
                    if view.result == "engage":
                        # Check PVE cooldown one more time to prevent exploits
                        pve_ttl = await ctx.bot.redis.execute_command(
                            "TTL", f"cd:{ctx.author.id}:{pve_command.qualified_name}"
                        )
                        
                        if pve_ttl != -2:  # Cooldown exists
                            # Format the remaining time
                            hours, remainder = divmod(pve_ttl, 3600)
                            minutes, seconds = divmod(remainder, 60)
                            time_str = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
                            
                            await message.delete()
                            await ctx.send(f"Ha! Nice try. You must wait {time_str} before engaging in combat again!")
                            break
                        
                        # Set a temporary cooldown to prevent race conditions
                        await ctx.bot.redis.execute_command(
                            "SET", f"cd:{ctx.author.id}:pve",
                            "pve",
                            "EX", 60 * 30
                        )
                        
                        await message.delete()
                        ctx.monster_override = monster_data
                        ctx.levelchoice_override = levelchoice
                        ctx.locationchoice_override = scout_location["id"]
                        await ctx.invoke(self.bot.get_command("pve"))
                        break
                    elif view.result == "reroll":
                        rerolls_left = view.rerolls
                        await message.delete()
                        continue
                    elif view.result == "retreat":
                        await message.delete()
                        await ctx.send("You decide to retreat and look for another opportunity.")
                        break
                    else:
                        await message.delete()
                        await ctx.send("Scouting timed out.")
                        break
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
            await self.bot.reset_cooldown(ctx)

    @commands.command()
    @is_gm()
    @has_char()
    async def custom_battle(self, ctx, battle_type: str = "pve", *, options: str = ""):
        """Create a custom battle with specified options.
        
        Available battle types: pvp, pve, raid, tower, team
        Options format: key1=value1 key2=value2
        Example: $custom_battle pve pets=true elements=true
        """
        # Parse options from string (format: key1=value1 key2=value2)
        options_dict = {}
        if options:
            for option in options.split():
                if "=" in option:
                    key, value = option.split("=", 1)
                    options_dict[key] = value
        
        # Convert string values to appropriate types
        if "money" in options_dict:
            try:
                money_value = int(options_dict["money"])
                # Prevent negative money values
                if money_value < 0:
                    return await ctx.send("Money cannot be negative.")
                options_dict["money"] = money_value
            except ValueError:
                return await ctx.send("Money must be a number.")
            
            # Check if player has enough money
            if money_value > 0 and ctx.character_data["money"] < money_value:
                return await ctx.send(_("You don't have enough money for this battle."))

        if "level" in options_dict:
            try:
                options_dict["level"] = int(options_dict["level"])
            except ValueError:
                return await ctx.send("Level must be a number.")
        
        # Convert boolean options
        for bool_option in ["allow_pets", "class_buffs", "element_effects", "luck_effects", "reflection_damage"]:
            if bool_option in options_dict:
                options_dict[bool_option] = options_dict[bool_option].lower() == "true"
        
        # Add player to battle options
        options_dict["player"] = ctx.author
        
        # Try to create and start the battle
        try:
            battle = await self.battle_factory.create_battle(
                battle_type.lower(),
                ctx,
                **options_dict
            )
            
            # Start the battle
            success = await battle.start_battle()
            if not success:
                return await ctx.send(f"Failed to start {battle_type} battle.")
            
            # Process turns until battle is over
            while not await battle.is_battle_over():
                await battle.process_turn()
                await asyncio.sleep(1)  # 1 second delay between turns
            
            # End the battle and handle result
            result = await battle.end_battle()
            
            if result:
                await ctx.send(f"Battle ended with result: {result}")
            else:
                await ctx.send("The battle ended in a draw.")
        
        except ValueError as e:
            await ctx.send(f"Error creating battle: {e}")
        except Exception as e:
            import traceback
            error_message = f"An unexpected error occurred: {e}\n{traceback.format_exc()}"
            await ctx.send(error_message[:1900] + "..." if len(error_message) > 1900 else error_message)

    @commands.group(name="battlesettings", aliases=["battleconfig", "bconfig"])
    @is_gm()
    async def battle_settings(self, ctx):
        """Manage battle system settings
        
        This command group allows you to configure various aspects of the battle system.
        Use subcommands to view and modify settings.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send("Please specify a subcommand. Use `help battlesettings` for more information.")

    @battle_settings.command(name="view")
    async def view_settings(self, ctx, battle_type: str = None):
        """View current battle settings
        
        battle_type: Optional, the type of battle to view settings for (pve, pvp, raid, tower, team, global)
        If no battle type is specified, shows settings for all battle types.
        """
        settings = await self.battle_factory.settings.get_all_settings(battle_type)
        
        embed = discord.Embed(
            title="Battle System Settings",
            color=discord.Color.blue(),
            description="Current configuration for the battle system."
        )
        
        if battle_type:
            settings_dict = {battle_type: settings}
        else:
            settings_dict = settings
        
        for bt, config in settings_dict.items():
            field_value = "\n".join([f"**{k}**: {v}" for k, v in config.items()])
            embed.add_field(name=f"{bt.upper()} Battle Settings", value=field_value or "Using defaults", inline=False)
        
        await ctx.send(embed=embed)

    @battle_settings.command(name="set")
    async def set_setting(self, ctx, battle_type: str, setting: str, *, value: str):
        """Set a battle setting
        
        battle_type: The type of battle (pve, pvp, raid, tower, team, global)
        setting: The setting to change (allow_pets, class_buffs, element_effects, etc.)
        value: The new value (true/false for boolean settings, numbers for numeric settings)
        """
        # Validate battle type
        valid_battle_types = ["pve", "pvp", "raid", "tower", "team", "global", "dragon"]
        if battle_type.lower() not in valid_battle_types:
            return await ctx.send(f"Invalid battle type. Must be one of: {', '.join(valid_battle_types)}")
        
        # Validate setting
        valid_settings = self.battle_factory.settings.get_configurable_settings()
        if setting not in valid_settings:
            return await ctx.send(f"Invalid setting. Must be one of: {', '.join(valid_settings)}")
        
        # Parse value based on setting type
        parsed_value = value.lower()
        if parsed_value in ["true", "yes", "on", "1"]:
            parsed_value = True
        elif parsed_value in ["false", "no", "off", "0"]:
            parsed_value = False
        elif setting == "fireball_chance":
            try:
                parsed_value = float(value)
            except ValueError:
                return await ctx.send("Fireball chance must be a number between 0 and 1.")
        
        # Set the setting
        success = await self.battle_factory.settings.set_setting(battle_type.lower(), setting, parsed_value)
        
        if success:
            # Force a refresh of the settings cache to ensure changes take effect immediately
            await self.battle_factory.settings.force_refresh()
            await ctx.send(f"✅ Successfully set **{setting}** to **{parsed_value}** for **{battle_type}** battles.")
        else:
            await ctx.send("❌ Failed to update setting. Please check your inputs and try again.")

    @battle_settings.command(name="reset")
    async def reset_setting(self, ctx, battle_type: str, setting: str):
        """Reset a battle setting to its default value
        
        battle_type: The type of battle (pve, pvp, raid, tower, team, global)
        setting: The setting to reset (allow_pets, class_buffs, element_effects, etc.)
        """
        # Validate battle type
        valid_battle_types = ["pve", "pvp", "raid", "tower", "team", "dragon", "global"]
        if battle_type.lower() not in valid_battle_types:
            return await ctx.send(f"Invalid battle type. Must be one of: {', '.join(valid_battle_types)}")
        
        # Reset the setting
        success = await self.battle_factory.settings.reset_setting(battle_type.lower(), setting)
        
        if success:
            # Force a refresh of the settings cache to ensure changes take effect immediately
            await self.battle_factory.settings.force_refresh()
            
            # Get the new value (which will be the default)
            new_value = await self.battle_factory.settings.get_setting(battle_type.lower(), setting)
            await ctx.send(f"✅ Reset **{setting}** to default value **{new_value}** for **{battle_type}** battles.")
        else:
            await ctx.send("❌ Failed to reset setting. Please check your inputs and try again.")
            
    @commands.group(name="dragonchallenge", aliases=["dragon", "idc", "d"])
    @has_char()
    async def dragon_challenge(self, ctx):
        """Ice Dragon Challenge - a powerful boss battle where players can team up
        
        The Ice Dragon grows stronger over time as players defeat it, with each evolution
        introducing new powerful abilities and passives. Form a party and challenge
        this formidable foe!
        """
        try:
            if ctx.invoked_subcommand is None:
                await self._show_dragon_status(ctx)
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
    
    async def _show_dragon_status(self, ctx):
        """Show the current status of the Ice Dragon Challenge"""
        # Get current dragon stats
        dragon_stats = await self.battle_factory.dragon_ext.get_dragon_stats_from_database(self.bot)
        dragon_level = dragon_stats.get("level", 1)
        weekly_defeats = dragon_stats.get("weekly_defeats", 0)
        
        # Get dragon stage information
        stage = await self.battle_factory.dragon_ext.get_dragon_stage(self.bot, dragon_level)
        stage_name = stage["name"]
        stage_info = stage["info"]
        
        # Create status embed
        embed = discord.Embed(
            title="Ice Dragon Challenge",
            description=f"The **{stage_name}** awaits challengers...",
            color=discord.Color.blue()
        )
        
        # Add dragon information
        embed.add_field(
            name="Dragon Level",
            value=f"Level {dragon_level}",
            inline=True
        )
        
        embed.add_field(
            name="Weekly Defeats",
            value=f"{weekly_defeats}",
            inline=True
        )
        
        # Add passive effects
        passives = stage_info.get("passives", [])
        if passives:
            passive_text = "\n".join([f"• {passive}" for passive in passives])
            embed.add_field(
                name="Passive Effects",
                value=passive_text,
                inline=False
            )
        
        # Add available moves
        moves = stage_info.get("moves", {})
        if moves:
            move_text = "\n".join([f"• {move}" for move in moves.keys()])
            embed.add_field(
                name="Special Moves",
                value=move_text,
                inline=False
            )
        
        # Add call to action
        embed.add_field(
            name="Challenge the Dragon",
            value="Use `$dragonchallenge party` to create a party and challenge the dragon!",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @dragon_challenge.command(name="party", aliases=["p"])
    @has_char()
    @user_cooldown(7200)
    async def dragon_party(self, ctx):
        """Start forming a party to challenge the Ice Dragon
        
        **Aliases**: `p`
        """
        try:
            # Check if the user is already in a party
            if any(view.is_complete is False and ctx.author in view.party_members 
                for view in self.dragon_party_views):
                return await ctx.send("You are already in a party formation!")
                
            # Create party formation view
            class DragonPartyView(discord.ui.View):
                def __init__(self, bot):
                    super().__init__(timeout=120)  # Full 60-second timeout
                    self.bot = bot
                    self.party_members = [ctx.author]  # Author automatically joins
                    self.is_complete = False
                    self._warning_task = None
                    self._warning_sent = False
                    self.message = None  # Will be set after view is sent
                    self.ctx = ctx  # Store context for sending warning message

                async def _is_linked_to_leader(self, user_id: int) -> bool:
                    leader_id = self.ctx.author.id
                    if user_id == leader_id:
                        return True
                    async with self.bot.pool.acquire() as conn:
                        linked = await conn.fetchval(
                            """
                            SELECT 1
                            FROM alt_links
                            WHERE (main = $1 AND alt = $2) OR (main = $2 AND alt = $1)
                            """,
                            user_id,
                            leader_id,
                        )
                    return bool(linked)
                    
                async def update_embed(self):
                    embed = discord.Embed(
                        title="Ice Dragon Challenge - Party Formation",
                        description="Form a party to challenge the Ice Dragon!",
                        color=discord.Color.blue()
                    )
                    
                    # List party members
                    member_list = "\n".join([f"• {member.mention}" for member in self.party_members])
                    embed.add_field(
                        name=f"Party Members ({len(self.party_members)}/4)",
                        value=member_list or "No members yet",
                        inline=False
                    )
                    
                    return embed
                    
                @discord.ui.button(label="Join Party", style=discord.ButtonStyle.primary, emoji="⚔️")
                async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
                    # Check if user has a character
                    if not await self.bot.pool.fetchrow('SELECT 1 FROM profile WHERE "user"=$1', interaction.user.id):
                        return await interaction.response.send_message("You don't have a character to join the party!", ephemeral=True)
                        
                    # Check if user is already in the party
                    if interaction.user in self.party_members:
                        return await interaction.response.send_message("You are already in the party!", ephemeral=True)
                        
                    # Add user to party
                    if len(self.party_members) < 4:
                        self.party_members.append(interaction.user)
                        await interaction.response.send_message("You have joined the party!", ephemeral=True)
                        
                        # Update the embed
                        await interaction.message.edit(embed=await self.update_embed())
                    else:
                        await interaction.response.send_message("The party is already full!", ephemeral=True)
                
                @discord.ui.button(label="Leave Party", style=discord.ButtonStyle.danger, emoji="🚪")
                async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
                    # Check if user is in the party
                    if interaction.user not in self.party_members:
                        return await interaction.response.send_message("You are not in the party!", ephemeral=True)
                        
                    # Don't allow the party leader to leave
                    if interaction.user == ctx.author:
                        return await interaction.response.send_message("As the party leader, you cannot leave the party!", ephemeral=True)
                        
                    # Remove user from party
                    self.party_members.remove(interaction.user)
                    await interaction.response.send_message("You have left the party!", ephemeral=True)
                    
                    # Update the embed
                    await interaction.message.edit(embed=await self.update_embed())
                
                @discord.ui.button(label="Start Challenge", style=discord.ButtonStyle.success, emoji="🐉")
                async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
                    # Only the party leader can start the challenge
                    if not await self._is_linked_to_leader(interaction.user.id):
                        return await interaction.response.send_message(
                            "Only the party leader (or their linked main/alt) can start the challenge!",
                            ephemeral=True,
                        )
                        
                    # At least one member needed to start
                    if not self.party_members:
                        return await interaction.response.send_message("You need at least one member to start the challenge!", ephemeral=True)
                    
                    # Acknowledge the interaction
                    await interaction.response.defer()
                    
                    # Mark as complete to start the challenge
                    self.is_complete = True
                    self.stop()
                
                async def on_timeout(self):
                    # This runs after the full 60 seconds
                    if not self.is_complete:
                        self.is_complete = False
                        self.stop()
                
                async def start_warning_timer(self):
                    # Schedule the warning for 50 seconds in
                    await asyncio.sleep(110)
                    if not self.is_complete and not self.is_finished():
                        self._warning_sent = True
                        warning_embed = discord.Embed(
                            title="⚠️ Party Formation Expiring Soon",
                            description="The party formation will time out in 10 seconds. Start the challenge now or the party will be disbanded.",
                            color=discord.Color.orange()
                        )
                        try:
                            await self.ctx.send(embed=warning_embed, delete_after=10)
                        except Exception as e:
                            print(f"Error sending warning message: {e}")
                
                async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
                    if self._timeout_task:
                        self._timeout_task.cancel()
                        self._timeout_task = None
                    await super().on_error(interaction, error, item)
                
                def stop(self):
                    # Cancel any pending warning task
                    if hasattr(self, '_warning_task') and self._warning_task:
                        self._warning_task.cancel()
                    super().stop()
                
                async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
                    # Cancel warning task on error
                    if hasattr(self, '_warning_task') and self._warning_task:
                        self._warning_task.cancel()
                    await super().on_error(interaction, error, item)
            
            # Create and send the party view
            view = DragonPartyView(self.bot)
            message = await ctx.send(embed=await view.update_embed(), view=view)
            view.message = message  # Store message reference
            # Start the warning timer
            view._warning_task = asyncio.create_task(view.start_warning_timer())
            
            # Wait for the view to complete
            await view.wait()
            
            # Check if party formation was successful
            if view.is_complete:
                await message.edit(content="Party formed! Starting the challenge...", embed=None, view=None)
                
                # Add all party members to the fighting players
                for member in view.party_members:
                    await self.add_player_to_fight(member.id)
                    
                try:
                    # Create and start the dragon battle
                    try:
                        battle = await self.battle_factory.create_battle(
                            "dragon",
                            ctx,
                            party_members=view.party_members
                        )
                        
                        # Start the battle
                        success = await battle.start_battle()
                        if not success:
                            # Remove players from fighting
                            for member in view.party_members:
                                await self.remove_player_from_fight(member.id)
                            return await ctx.send("Failed to start the dragon challenge!")
                        
                        # Process battle turns
                        turn_count = 0
                        battle_msg = await ctx.send("⚔️ Battle started! Dragons and adventurers clash...")
                        
                        while not await battle.is_battle_over():
                            try:
                                turn_count += 1
                                result = await battle.process_turn()
                                
                                # Only update message every 5 turns to reduce spam
                                if turn_count % 5 == 0:
                                    await battle_msg.edit(content=f"⚔️ Battle in progress - Turn {turn_count} - The dragon and party continue to battle...")
                                
                                await asyncio.sleep(1)  # 1 second delay between turns for faster battles
                            except Exception as e:
                                await ctx.send(f"⚠️ Error in turn {turn_count}: {str(e)}\n```{traceback.format_exc()}```")
                                break
                        
                        # Get the battle result
                        await ctx.send("Battle completed. Processing result...")
                        victory = await battle.end_battle()
                        
                    except Exception as e:
                        await ctx.send(f"⚠️ Error in dragon battle: {str(e)}\n```{traceback.format_exc()}```")
                        return
                    
                    # Handle rewards
                    if victory is True:  # Players won
                        stage_id = getattr(battle, "dragon_stage_id", None)
                        await self._handle_dragon_victory(ctx, view.party_members, stage_id=stage_id)
                    elif victory is False:  # Players lost
                        await self._handle_dragon_defeat(ctx, view.party_members)
                    else:  # Draw
                        await ctx.send("The battle ended in a draw!")
                        
                finally:
                    # Always remove players from fighting status
                    for member in view.party_members:
                        await self.remove_player_from_fight(member.id)
                        
            else:
                await message.edit(content="Party formation timed out!", embed=None, view=None)
                await self.bot.reset_cooldown(ctx)
        except Exception as e:
            await ctx.send(e)
    
    async def _get_ice_dragon_drops(self):
        async with self.bot.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT id, name, item_type, min_stat, max_stat, base_chance, max_chance, is_global, dragon_stage_id, "
                "element, min_level, max_level "
                "FROM ice_dragon_drops ORDER BY id ASC"
            )

    async def _handle_dragon_victory(self, ctx, party_members, stage_id=None):
        """Handle rewards for defeating the dragon"""
        # Get current dragon level
        dragon_stats = await self.battle_factory.dragon_ext.get_dragon_stats_from_database(self.bot)
        old_level = dragon_stats.get("level", 1)
        weekly_defeats = dragon_stats.get("weekly_defeats", 0)
        
        # Update dragon progress in database
        level_up = False
        try:
            updated_stats = await self.battle_factory.dragon_ext.update_dragon_progress(
                self.bot,
                old_level,
                weekly_defeats,
                victory=True
            )
            # Check if dragon actually leveled up
            new_level = updated_stats.get("level", old_level)
            level_up = new_level > old_level
        except Exception:
            # Continue with rewards even if update fails
            pass
        
        # Calculate rewards
        base_money = 1000 * old_level
        base_xp = 500 * old_level
        
        # Create reward embed
        embed = discord.Embed(
            title="Dragon Challenge Victory!",
            description=f"Your party has defeated the Level {old_level} Dragon!",
            color=discord.Color.green()
        )
        
        # Add level up information only if the dragon actually leveled up
        if level_up:
            embed.add_field(
                name="Dragon Level Up",
                value=f"The Dragon has grown stronger and is now Level {old_level + 1}!",
                inline=False
            )
        else:
            # Show progress information instead
            # Always 40 defeats needed per level
            next_level_threshold = 40
            current_progress = weekly_defeats + 1  # Add this victory
            remaining = next_level_threshold - current_progress
            embed.add_field(
                name="Dragon Progress",
                value=f"Dragon remains at Level {old_level}. Progress: {current_progress}/40 defeats (need {remaining} more for level up).",
                inline=False
            )
        
        # Give rewards to each party member
        reward_text = ""
        weapon_rewards_text = ""
        level_bonus = min(0.08, (old_level - 1) * 0.003)  # 0.3% bonus per level, max 8%
        if stage_id is None:
            try:
                stage = await self.battle_factory.dragon_ext.get_dragon_stage(self.bot, old_level)
                stage_id = stage.get("id")
            except Exception:
                stage_id = None
        try:
            all_drops = await self._get_ice_dragon_drops()
        except Exception:
            all_drops = []
        eligible_drops = []
        for drop in all_drops:
            if not drop["is_global"] and stage_id is not None and drop["dragon_stage_id"] != stage_id:
                continue
            if not drop["is_global"] and stage_id is None:
                continue
            min_level = drop["min_level"]
            max_level = drop["max_level"]
            if min_level is not None and old_level < min_level:
                continue
            if max_level is not None and old_level > max_level:
                continue
            eligible_drops.append(drop)
        dragon_coin_reward = 0
        try:
            async with self.bot.pool.acquire() as conn:
                party_member_ids = list(dict.fromkeys(member.id for member in party_members))
                if (
                    party_member_ids
                    and random.randint(1, 100) <= self.DRAGON_COIN_DROP_CHANCE_PERCENT
                ):
                    dragon_coin_reward = random.randint(
                        self.DRAGON_COIN_DROP_MIN, self.DRAGON_COIN_DROP_MAX
                    )
                    await conn.execute(
                        'UPDATE profile SET dragoncoins = dragoncoins + $1 WHERE "user" = ANY($2);',
                        dragon_coin_reward,
                        party_member_ids,
                    )
                for idx, member in enumerate(party_members):
                    try:
                        # Calculate individual rewards with diminishing returns
                        member_money = base_money // (idx + 1)
                        member_xp = base_xp // (idx + 1)
                        
                        current_data = await conn.fetchrow(
                            'SELECT "xp" FROM profile WHERE "user"=$1',
                            member.id
                        )
                        current_xp = current_data["xp"]
                        current_level = int(rpgtools.xptolevel(current_xp))

                        # Award money and XP
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1, "xp"="xp"+$2 WHERE "user"=$3;',
                            member_money, member_xp, member.id
                        )

                        # Calculate new level and check for level-up
                        new_level = int(rpgtools.xptolevel(current_xp + member_xp))

                        # Debug output for specific member
                        if self.debug_user_id and member.id == self.debug_user_id:
                            await ctx.send(
                                f"**Debug Info for {member.display_name}:**\n"
                                f"Current XP: {current_xp}\n"
                                f"Current Level: {current_level}\n"
                                f"Member Money Awarded: {member_money}\n"
                                f"Member XP Awarded: {member_xp}\n"
                                f"New XP Total: {current_xp + member_xp}\n"
                                f"New Level: {new_level}\n"
                                f"Level Up: {current_level != new_level}"
                            )

                        if current_level != new_level:
                            await self.bot.process_guildlevelup(ctx, member.id, new_level, current_level)
                        
                        # Record in reward text
                        reward_text += f"• {member.mention}: {member_money} 💰, {member_xp} XP\n"
                        
                        # ICE DRAGON WEAPON REWARDS (DB-driven)
                        try:
                            for drop in eligible_drops:
                                effective_chance = min(drop["max_chance"], drop["base_chance"] + level_bonus)
                                if random.random() < effective_chance:
                                    try:
                                        stat = random.randint(drop["min_stat"], drop["max_stat"])
                                        item_type = ItemType.from_string(drop["item_type"])
                                        if not item_type:
                                            continue
                                        hand = item_type.get_hand().value
                                        element = drop["element"] or "Water"
                                        
                                        # Create the weapon
                                        await self.bot.create_item(
                                            name=drop["name"],
                                            value=10000,
                                            type_=item_type.value,
                                            damage=stat if item_type != ItemType.Shield else 0,
                                            armor=stat if item_type == ItemType.Shield else 0,
                                            hand=hand,
                                            owner=member,
                                            element=element,
                                            conn=conn
                                        )
                                        
                                        weapon_type_display = "2H" if hand == "both" else "1H"
                                        rarity_emoji = "🌟" if hand == "both" else "⭐"
                                        weapon_rewards_text += f"{rarity_emoji} **{member.mention}** found **{drop['name']}** ({weapon_type_display}) with {stat} stats!\n"
                                    except Exception as e:
                                        print(f"Error creating ice dragon weapon for {member.display_name}: {e}")
                                        continue
                        except Exception as e:
                            await ctx.send(f"Error creating ice dragon weapon for {member.display_name}: {e}")
                            continue
                        
                        # Update dragon_contributions for this player
                        player_count = await conn.fetchval(
                            'SELECT COUNT(*) FROM dragon_contributions WHERE "user_id"=$1',
                            member.id
                        )
                        
                        if player_count > 0:
                            # Update existing record
                            await conn.execute(
                                'UPDATE dragon_contributions SET total_defeats=total_defeats+1, weekly_defeats=weekly_defeats+1, last_defeat=NOW() WHERE "user_id"=$1',
                                member.id
                            )
                        else:
                            # Insert new record
                            await conn.execute(
                                'INSERT INTO dragon_contributions ("user_id", total_defeats, weekly_defeats, last_defeat) VALUES ($1, 1, 1, NOW())',
                                member.id
                            )
                    except Exception:
                        # Continue with next member even if this one fails
                        continue
                if dragon_coin_reward > 0:
                    reward_text += (
                        f"🐉 Dragon Coin Bonus: Each party member also received {dragon_coin_reward} <:dragoncoin:1398714322372395008> Dragon Coins\n"
                    )
        except Exception:
            # Try to continue with embed even if rewards failed
            reward_text = "Error processing rewards."
        
        # Add rewards to embed
        try:
            embed.add_field(
                name="Rewards",
                value=reward_text,
                inline=False
            )
            
            # Add weapon rewards if any were found
            if weapon_rewards_text:
                embed.add_field(
                    name="❄️ Ice Dragon Weapon Drops",
                    value=weapon_rewards_text,
                    inline=False
                )
            else:
                # Add a note about the weapon drop system with drop rate info
                total_chance_1h = 0.0
                total_chance_2h = 0.0
                for drop in eligible_drops:
                    item_type = ItemType.from_string(drop["item_type"])
                    if not item_type:
                        continue
                    effective_chance = min(drop["max_chance"], drop["base_chance"] + level_bonus)
                    if item_type.get_hand().value == "both":
                        total_chance_2h += effective_chance
                    else:
                        total_chance_1h += effective_chance
                embed.add_field(
                    name="❄️ Ice Dragon Loot",
                    value=f"No legendary weapons were found this time. Keep challenging the dragon for a chance at rare ice-themed weapons!\n\n**Drop Rates:**\n• 1H Total: {total_chance_1h:.1%}\n• 2H Total: {total_chance_2h:.1%}",
                    inline=False
                )
            
            await ctx.send(embed=embed)
        except Exception:
            # Try a simple text message as fallback
            await ctx.send("Victory! The dragon has been defeated and rewards have been distributed.")
            pass

    def _get_dragon_stage_name(self, level: int) -> str:
        """Get the dragon stage name for a given level"""
        if level <= 5:
            return "Frostbite Wyrm"
        elif level <= 10:
            return "Corrupted Ice Dragon"
        elif level <= 15:
            return "Permafrost"
        elif level <= 20:
            return "Absolute Zero"
        elif level <= 25:
            return "Void Tyrant"
        elif level <= 30:
            return "Eternal Frost"
        else:
            return "Eternal Frost"

    
    async def _handle_dragon_defeat(self, ctx, party_members):
        """Handle the case where the party is defeated by the dragon"""
        # Create defeat embed
        embed = discord.Embed(
            title="Dragon Challenge Defeat",
            description="Your party has been defeated by the Dragon!",
            color=discord.Color.red()
        )
        
        # Add consolation rewards
        embed.add_field(
            name="Consolation",
            value="Each party member receives a small amount of XP for their efforts.",
            inline=False
        )

        # Get current dragon level
        dragon_stats = await self.battle_factory.dragon_ext.get_dragon_stats_from_database(self.bot)
        dragon_level = dragon_stats.get("level", 1)

        # Give small XP reward for trying
        async with self.bot.pool.acquire() as conn:
            for member in party_members:
                # Get current XP and level before update
                current_data = await conn.fetchrow(
                    'SELECT "xp" FROM profile WHERE "user"=$1;',
                    member.id
                )

                if current_data:
                    current_xp = current_data["xp"]
                    current_level = int(rpgtools.xptolevel(current_xp))

                    # Small XP consolation
                    consolation_xp = 50 * dragon_level

                    await conn.execute(
                        'UPDATE profile SET "xp"="xp"+$1 WHERE "user"=$2;',
                        consolation_xp, member.id
                    )

                    # Calculate new level and check for level-up
                    new_level = int(rpgtools.xptolevel(current_xp + consolation_xp))

                    # Debug output for specific member (if needed)
                    if self.debug_user_id and member.id == self.debug_user_id:
                        await ctx.send(
                            f"**Debug Info for {member.display_name}:**\n"
                            f"Current XP: {current_xp}\n"
                            f"Current Level: {current_level}\n"
                            f"Consolation XP: {consolation_xp}\n"
                            f"New XP Total: {current_xp + consolation_xp}\n"
                            f"New Level: {new_level}\n"
                            f"Level Up: {current_level != new_level}"
                        )

                    if current_level != new_level:
                        await self.bot.process_guildlevelup(ctx, member.id, new_level, current_level, conn)

        await ctx.send(embed=embed)
    
    @dragon_challenge.command(name="leaderboard", aliases=["lb"])
    async def dragon_leaderboard(self, ctx):
        """View the Ice Dragon Challenge leaderboard"""
        embed = discord.Embed(
            title="Ice Dragon Challenge Leaderboard",
            color=discord.Color.blue()
        )
        
        # Get top dragon killers
        async with self.bot.pool.acquire() as conn:
            result = await conn.fetch(
                'SELECT "user", "dragon_kills" FROM profile ORDER BY "dragon_kills" DESC LIMIT 10'
            )
        
        if result:
            leaderboard_text = ""
            for idx, row in enumerate(result, start=1):
                user_id = row["user"]
                kills = row["dragon_kills"]
                
                # Skip users with 0 kills
                if kills <= 0:
                    continue
                    
                # Try to get username
                try:
                    user = await self.bot.fetch_user(user_id)
                    username = user.name
                except:
                    username = f"Unknown User ({user_id})"
                    
                leaderboard_text += f"**{idx}.** {username} - {kills} dragon kills\n"
                
            if leaderboard_text:
                embed.add_field(
                    name="Top Dragon Slayers",
                    value=leaderboard_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="No Data",
                    value="No one has defeated the dragon yet!",
                    inline=False
                )
        else:
            embed.add_field(
                name="No Data",
                value="No one has defeated the dragon yet!",
                inline=False
            )
            
        # Add current dragon level
        dragon_stats = await self.battle_factory.dragon_ext.get_dragon_stats_from_database(self.bot)
        dragon_level = dragon_stats.get("level", 1)
        weekly_defeats = dragon_stats.get("weekly_defeats", 0)
        
        embed.add_field(
            name="Current Dragon Stats",
            value=f"Level: {dragon_level}\nWeekly Defeats: {weekly_defeats}",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @dragon_challenge.command(name="reset")
    @is_gm()
    async def reset_dragon(self, ctx, level: int = 1):
        """[GM] Reset the Ice Dragon Challenge progress"""
        async with self.bot.pool.acquire() as conn:
            # Check if record exists
            exists = await conn.fetchval(
                'SELECT 1 FROM dragon_progress WHERE id = 1'
            )
            
            if exists:
                # Reset to specified level
                await conn.execute(
                    'UPDATE dragon_progress SET current_level = $1, weekly_defeats = 0, last_reset = NOW() WHERE id = 1',
                    level
                )
            else:
                # Create new record
                await conn.execute(
                    'INSERT INTO dragon_progress (id, current_level, weekly_defeats, last_reset, last_update) VALUES (1, $1, 0, NOW(), NOW())',
                    level
                )
                
        await ctx.send(f"✅ Ice Dragon Challenge reset to level {level}!")
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Check for weekly reset when bot starts"""
        # Check for weekly dragon reset
        try:
            reset_happened = await self.battle_factory.dragon_ext.check_and_perform_weekly_reset(self.bot)
            if reset_happened:
                print("[INFO] Ice Dragon Challenge weekly reset performed")
        except Exception as e:
            print(f"[ERROR] Failed to check dragon weekly reset: {e}")

    @commands.group(aliases=["cbt"])
    async def couples_battletower(self, ctx):
        """Commands for the Couples Battle Tower."""
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.cbt_progress)

    async def reset_couples_cooldown(self, user1_id, user2_id, command_type="both"):
        """Reset couples battle tower cooldown for both partners."""
        try:
            if command_type == "both":
                # Reset both start and begin cooldowns
                await self.bot.redis.execute_command("DEL", f"cd:{user1_id}:couples_battletower start")
                await self.bot.redis.execute_command("DEL", f"cd:{user2_id}:couples_battletower start")
                await self.bot.redis.execute_command("DEL", f"cd:{user1_id}:couples_battletower begin")
                await self.bot.redis.execute_command("DEL", f"cd:{user2_id}:couples_battletower begin")
            else:
                # Reset specific command cooldown
                await self.bot.redis.execute_command("DEL", f"cd:{user1_id}:couples_battletower {command_type}")
                await self.bot.redis.execute_command("DEL", f"cd:{user2_id}:couples_battletower {command_type}")
        except Exception:
            pass  # Ignore redis errors

    async def get_couple_progress(self, user_id, partner_id):
        """Fetch couple's battle tower progress from the database."""
        id1, id2 = sorted((user_id, partner_id))
        query = "SELECT current_level, prestige FROM couples_battle_tower WHERE partner1_id = $1 AND partner2_id = $2"
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(query, id1, id2)
        if row:
            return dict(row)
        return None

    async def update_couple_progress(self, user_id, partner_id, level, prestige_up=False):
        """Update or insert a couple's battle tower progress."""
        id1, id2 = sorted((user_id, partner_id))
        prestige_change = 1 if prestige_up else 0
        query = """
            INSERT INTO couples_battle_tower (partner1_id, partner2_id, current_level, prestige, last_attempt_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (partner1_id, partner2_id)
            DO UPDATE SET
                current_level = GREATEST(couples_battle_tower.current_level, $3),
                prestige = couples_battle_tower.prestige + $4,
                last_attempt_at = NOW();
        """
        async with self.bot.pool.acquire() as conn:
            await conn.execute(query, id1, id2, level, prestige_change)
            
    @couples_battletower.command(name="start", aliases=["fight"])
    @has_char()
    @user_cooldown(3600)
    async def cbt_start(self, ctx):
        """Starts a Couples Battle Tower fight."""
        try:
            author = ctx.author
            query = "SELECT marriage FROM profile WHERE profile.user = $1"
            result = await self.bot.pool.fetchval(query, ctx.author.id)
            partner_id = result  # This will be the marriage partner's ID, or None if not married

            if not partner_id:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You are not married. This challenge is for couples only!"))
            

            partner = await self.bot.fetch_user(partner_id)

            
            # Apply cooldown to both partners at the start
            await self.bot.redis.execute_command(
                "SET", f"cd:{ctx.author.id}:couples_battletower start",
                "couples_battletower start",
                "EX", 3600
            )
            await self.bot.redis.execute_command(
                "SET", f"cd:{partner_id}:couples_battletower start", 
                "couples_battletower start",
                "EX", 3600
            )




            progress = await self.get_couple_progress(author.id, partner.id)
            if not progress:
                progress = {'current_level': 1, 'prestige': 0}
                await self.update_couple_progress(author.id, partner.id, 1) # Create initial record

            level = progress['current_level']

            if level > len(self.couples_game_levels["levels"]):
                return await ctx.send(_("You have already conquered the tower!"))

            level_info = self.couples_game_levels["levels"][level - 1]

            embed = discord.Embed(
                title=f"💕 The Tower of Eternal Bonds - Floor {level} 💕",
                description=f"**{level_info['title']}**\n\n{level_info['story']}",
                color=discord.Color.magenta()
            )
            embed.add_field(name="💑 Your Partner", value=f"{partner.display_name}, please join the battle!", inline=False)
            embed.set_footer(text=f"Your love will be tested on this floor...")
            try:
                await ctx.send(partner.mention)
            except:
                pass

            original_message = await ctx.send(embed=embed)

            async def on_join():
                await original_message.edit(content=_("💕 Your partner has joined! Preparing for battle..."), embed=None, view=None)
                
                # Show couples dialogue
                await self.display_couples_dialogue(ctx, level, author, partner)
                
                await self.add_player_to_fight(author.id)
                await self.add_player_to_fight(partner.id)

                try:
                    battle = await self.battle_factory.create_battle(
                        "couples_tower",
                        ctx,
                        player=author,
                        level=level,
                        game_levels=self.couples_game_levels,
                    )
                    
                    # Start the battle
                    await battle.start_battle()
                    
                    # Run the battle until completion
                    while not await battle.is_battle_over():
                        await battle.process_turn()
                        await asyncio.sleep(2)  # 2 second delay between turns
                    
                    # Get the result (winner team)
                    result = await battle.end_battle()

                    if result and result.name == "Player":
                        victory_data = self.couples_battle_tower_data["victories"].get(str(level), {})
                        vic_embed = discord.Embed(title=f"🏆 Floor {level} Conquered! - {victory_data.get('title', 'Victory!')} 🏆",
                                                  description=victory_data.get('description', 'You are victorious!'),
                                                  color=discord.Color.gold())
                        await ctx.send(embed=vic_embed)
                        
                        # Check if this level has chest rewards (every 5 levels)
                        if victory_data.get('has_chest', False):
                            # Get emotes for crate display
                            emotes = {
                                "common": "<:c_common:1403797578197368923>",
                                "uncommon": "<:c_uncommon:1403797597532983387>",
                                "rare": "<:c_rare:1403797594827657247>",
                                "magic": "<:c_Magic:1403797589169541330>",
                                "legendary": "<:c_Legendary:1403797587236225044>",
                                "mystery": "<:c_mystspark:1403797593129222235>",
                                "fortune": "<:c_money:1403797585411575971>",
                                "divine": "<:c_divine:1403797579635884202>",
                            }
                            await self.handle_couples_chest_rewards(ctx, level, author, partner, emotes)
                        # Check if this is the finale (level 30)
                        elif victory_data.get('finale', False):
                            await self.handle_couples_finale_rewards(ctx, level, author, partner)
                        else:
                            # Regular level completion - just update progress
                            await self.update_couple_progress(author.id, partner.id, level + 1)
                    else:
                        await ctx.send("💔 You have been defeated. Train harder and try again!")

                finally:
                    await self.remove_player_from_fight(author.id)
                    await self.remove_player_from_fight(partner.id)


            async def on_cancel():
                await original_message.edit(content=_("💔 The battle was cancelled or your partner did not respond in time."), embed=None, view=None)
                # Reset cooldown for both partners since battle didn't start
                await self.reset_couples_cooldown(author.id, partner.id)

            view = CouplesTowerView(author, partner, on_join, on_cancel)
            await original_message.edit(embed=embed, view=view)
        except Exception as e:
            await ctx.send(e)

    @couples_battletower.command(name="progress")
    @has_char()
    async def cbt_progress(self, ctx):
        """Shows your Couples Battle Tower progress."""
        try:
            author = ctx.author
            query = "SELECT marriage FROM profile WHERE profile.user = $1"
            result = await self.bot.pool.fetchval(query, ctx.author.id)
            partner_id = result

            if not partner_id:
                return await ctx.send(_("You are not married. This challenge is for couples only!"))

            partner = await self.bot.fetch_user(partner_id)
            progress = await self.get_couple_progress(author.id, partner.id)
            
            if not progress:
                progress = {'current_level': 1, 'prestige': 0}
                await self.update_couple_progress(author.id, partner.id, 1)

            level = progress['current_level']
            prestige = progress['prestige']

            # Get level names from the couples game levels
            level_names = []
            for i, level_info in enumerate(self.couples_game_levels["levels"], 1):
                level_names.append(level_info['title'])

            # Function to generate the formatted level list (similar to regular battle tower)
            def generate_couples_level_list(levels, start_level=1):
                result = "```\n"
                for level_num, level_name in enumerate(levels, start=start_level):
                    checkbox = "❌" if level_num == level else "✅" if level_num < level else "❌"
                    result += f"Floor {level_num:<2} {checkbox} {level_name}\n"
                result += "```"
                return result

            embed = discord.Embed(
                title="💕 Couples Battle Tower Progress 💕",
                description=f"**{author.display_name}** & **{partner.display_name}**\nLevel: {level}\nPrestige Level: {prestige}",
                color=discord.Color.magenta()
            )
            
            if level <= len(level_names):
                embed.add_field(
                    name="Floor Progress", 
                    value=generate_couples_level_list(level_names), 
                    inline=False
                )
                
                # Show next challenge info
                level_info = self.couples_game_levels["levels"][level - 1]
                embed.add_field(
                    name="Next Challenge",
                    value=f"**{level_info['title']}**\n{level_info['story'][:150]}...",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Status",
                    value="🏆 **You have conquered the Tower of Eternal Bonds!** 🏆",
                    inline=False
                )

            embed.set_footer(text="💕 **Your love grows stronger with each floor conquered** 💕")

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @couples_battletower.command(name="dialogue")
    @has_char()
    async def cbt_dialogue(self, ctx, level: int = None):
        """View the dialogue for a specific level of the Couples Battle Tower."""
        try:
            author = ctx.author
            query = "SELECT marriage FROM profile WHERE profile.user = $1"
            result = await self.bot.pool.fetchval(query, ctx.author.id)
            partner_id = result

            if not partner_id:
                return await ctx.send(_("You are not married. This challenge is for couples only!"))

            partner = await self.bot.fetch_user(partner_id)

            if not partner:
                return await ctx.send(_("Your partner is not online. Please try again later."))

            # If no level specified, show current level
            if not level:
                progress = await self.get_couple_progress(author.id, partner.id)
                if not progress:
                    return await ctx.send(_("You haven't started the Couples Battle Tower yet. Use `$couples_battletower begin` to begin!"))
                level = progress['current_level']
            
            # Validate level
            if level < 1 or level > len(self.couples_game_levels["levels"]):
                return await ctx.send(_(f"Invalid level. Please choose a level between 1 and {len(self.couples_game_levels['levels'])}."))

            # Show dialogue for the specified level
            await self.display_couples_dialogue(ctx, level, author, partner, dialogue_only=True)
            
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @couples_battletower.command(name="preview")
    @has_char()
    async def cbt_preview(self, ctx, level: int):
        """Preview the dialogue for a specific level without starting a battle."""
        try:
            author = ctx.author
            query = "SELECT marriage FROM profile WHERE profile.user = $1"
            result = await self.bot.pool.fetchval(query, ctx.author.id)
            partner_id = result

            if not partner_id:
                return await ctx.send(_("You are not married. This challenge is for couples only!"))

            partner = await self.bot.fetch_user(partner_id)

            if not partner:
                return await ctx.send(_("Your partner is not online. Please try again later."))

            # Validate level
            if level < 1 or level > len(self.couples_game_levels["levels"]):
                return await ctx.send(_(f"Invalid level. Please choose a level between 1 and {len(self.couples_game_levels['levels'])}."))

            level_info = self.couples_game_levels["levels"][level - 1]
            
            # Get full story text, but limit to embed field limits
            story_text = level_info['story']
            if len(story_text) > 900:
                story_text = story_text[:900] + "..."
            
            dialogue_text = level_info['dialogue_start']
            if len(dialogue_text) > 900:
                dialogue_text = dialogue_text[:900] + "..."
            
            embed = discord.Embed(
                title=f"💕 Preview: Floor {level} - {level_info['title']} 💕",
                description=f"**Story Preview:**\n{story_text}",
                color=discord.Color.magenta()
            )
            embed.add_field(name="Challenge", value=dialogue_text, inline=False)
            
            # Show mechanics if available
            mechanics_desc = self.get_level_mechanics_description(level)
            if len(mechanics_desc) > 1000:
                mechanics_desc = mechanics_desc[:1000] + "..."
            embed.add_field(name="⚙️ Floor Mechanics", value=mechanics_desc, inline=False)
            
            # Enemy info
            if "enemies" in level_info:
                enemy_count = len(level_info['enemies'])
                enemy_names = [enemy.get('name', 'Unknown') for enemy in level_info['enemies'][:3]]  # Show first 3
                enemy_text = f"**{enemy_count} enemies await:** {', '.join(enemy_names)}"
                if enemy_count > 3:
                    enemy_text += f" and {enemy_count - 3} more..."
                embed.add_field(name="👹 Enemies", value=enemy_text, inline=False)
            
            embed.set_footer(text=f"Use $couples_battletower dialogue {level} to see the full story!")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @couples_battletower.command(name="begin")
    @has_char()
    @user_cooldown(300)
    async def cbt_begin(self, ctx):
        """Starts a Couples Battle Tower fight."""
        try:
            author = ctx.author
            query = "SELECT marriage FROM profile WHERE profile.user = $1"
            result = await self.bot.pool.fetchval(query, ctx.author.id)
            partner_id = result  # This will be the marriage partner's ID, or None if not married

            if not partner_id:
                return await ctx.send(_("You are not married. This challenge is for couples only!"))

            partner = await self.bot.fetch_user(partner_id)

            # Check if either partner is already on couples battle tower cooldown (check both commands)
            author_start_cooldown = await user_cooldown(self.bot, ctx.author.id, "couples_battletower start", 3600)
            partner_start_cooldown = await user_cooldown(self.bot, partner_id, "couples_battletower start", 3600)
            author_begin_cooldown = await user_cooldown(self.bot, ctx.author.id, "couples_battletower begin", 300)
            partner_begin_cooldown = await user_cooldown(self.bot, partner_id, "couples_battletower begin", 300)
            
            if author_start_cooldown or partner_start_cooldown or author_begin_cooldown or partner_begin_cooldown:
                if author_start_cooldown or author_begin_cooldown:
                    cooldown_partner = "You are"
                else:
                    cooldown_partner = f"{partner.display_name} is"
                return await ctx.send(f"{cooldown_partner} still on cooldown for the couples battle tower. Please wait before starting another challenge.")

            # Check if either is currently in a fight
            if await self.is_player_in_fight(author.id) or await self.is_player_in_fight(partner.id):
                 return await ctx.send(_("One of you is already in a fight."))

            # Apply cooldown to both partners at the start
            await self.bot.redis.execute_command(
                "SET", f"cd:{ctx.author.id}:couples_battletower begin",
                "couples_battletower begin",
                "EX", 300
            )
            await self.bot.redis.execute_command(
                "SET", f"cd:{partner_id}:couples_battletower begin", 
                "couples_battletower begin",
                "EX", 300
            )

            progress = await self.get_couple_progress(author.id, partner.id)
            if not progress:
                progress = {'current_level': 1, 'prestige': 0}
                await self.update_couple_progress(author.id, partner.id, 1) # Create initial record

            level = progress['current_level']

            if level > len(self.couples_game_levels["levels"]):
                return await ctx.send(_("You have already conquered the tower!"))

            level_info = self.couples_game_levels["levels"][level - 1]

            embed = discord.Embed(
                title=f"💕 The Tower of Eternal Bonds - Floor {level} 💕",
                description=f"**{level_info['title']}**\n\n{level_info['story']}",
                color=discord.Color.magenta()
            )
            embed.add_field(name="💑 Your Partner", value=f"{partner.display_name}, please join the battle!", inline=False)
            embed.set_footer(text=f"Your love will be tested on this floor...")
            try: 
                await ctx.send(partner.mention)
            except:
                pass

            original_message = await ctx.send(embed=embed)

            async def on_join():
                await original_message.edit(content=_("💕 Your partner has joined! Preparing for battle..."), embed=None, view=None)
                
                # Show couples dialogue
                await self.display_couples_dialogue(ctx, level, author, partner)
                
                await self.add_player_to_fight(author.id)
                await self.add_player_to_fight(partner.id)

                try:
                    battle = await self.battle_factory.create_battle(
                        "couples_tower",
                        ctx,
                        player=author,
                        level=level,
                        game_levels=self.couples_game_levels,
                    )
                    
                    # Start the battle
                    await battle.start_battle()
                    
                    # Run the battle until completion
                    while not await battle.is_battle_over():
                        await battle.process_turn()
                        await asyncio.sleep(2)  # 2 second delay between turns
                    
                    # Get the result (winner team)
                    result = await battle.end_battle()

                    if result and result.name == "Player":
                        victory_data = self.couples_battle_tower_data["victories"].get(str(level), {})
                        vic_embed = discord.Embed(title=f"🏆 Floor {level} Conquered! - {victory_data.get('title', 'Victory!')} 🏆",
                                                  description=victory_data.get('description', 'You are victorious!'),
                                                  color=discord.Color.gold())
                        await ctx.send(embed=vic_embed)
                        
                        # Check if this level has chest rewards (every 5 levels)
                        if victory_data.get('has_chest', False):
                            # Get emotes for crate display
                            emotes = {
                                "common": "<:c_common:1403797578197368923>",
                                "uncommon": "<:c_uncommon:1403797597532983387>",
                                "rare": "<:c_rare:1403797594827657247>",
                                "magic": "<:c_Magic:1403797589169541330>",
                                "legendary": "<:c_Legendary:1403797587236225044>",
                                "mystery": "<:c_mystspark:1403797593129222235>",
                                "fortune": "<:c_money:1403797585411575971>",
                                "divine": "<:c_divine:1403797579635884202>",
                            }
                            await self.handle_couples_chest_rewards(ctx, level, author, partner, emotes)
                        # Check if this is the finale (level 30)
                        elif victory_data.get('finale', False):
                            await self.handle_couples_finale_rewards(ctx, level, author, partner)
                        else:
                            # Regular level completion - just update progress
                            await self.update_couple_progress(author.id, partner.id, level + 1)
                    else:
                        await ctx.send("💔 You have been defeated. Train harder and try again!")

                finally:
                    await self.remove_player_from_fight(author.id)
                    await self.remove_player_from_fight(partner.id)


            async def on_cancel():
                await original_message.edit(content=_("💔 The battle was cancelled or your partner did not respond in time."), embed=None, view=None)
                # Reset cooldown for both partners since battle didn't start
                await self.reset_couples_cooldown(author.id, partner.id)

            view = CouplesTowerView(author, partner, on_join, on_cancel)
            await original_message.edit(embed=embed, view=view)
        except Exception as e:
            await ctx.send(e)

    async def display_couples_dialogue(self, ctx, level, author, partner, dialogue_only=False):
        """Display dialogue for couples battle tower levels"""
        try:
            level_info = self.couples_game_levels["levels"][level - 1]
            
            # Create dialogue pages
            pages = []
            
            # Page 1: Level introduction with romantic theme
            intro_embed = discord.Embed(
                title=f"💕 Floor {level}: {level_info['title']} 💕",
                description=f"*The Tower of Eternal Bonds hums with ancient magic as you and your beloved step forward...*\n\n{level_info['story']}",
                color=discord.Color.magenta()
            )
            intro_embed.set_footer(text=f"💑 Together, you face the challenge ahead... 💑")
            intro_embed.add_field(name="💕 Your Bond", value=f"**{author.display_name}** & **{partner.display_name}**\n*United in love and purpose*", inline=False)
            pages.append(intro_embed)
            
            # Page 2: The challenge with dramatic presentation
            challenge_embed = discord.Embed(
                title=f"⚔️ The Challenge That Awaits ⚔️",
                description=f"*The air crackles with anticipation as the tower's guardians prepare to test your love...*\n\n{level_info['dialogue_start']}",
                color=discord.Color.dark_red()
            )
            challenge_embed.set_footer(text=f"🔥 Your love will be tested... 🔥")
            challenge_embed.add_field(name="💪 Your Strength", value="*The power of your bond will guide you through this trial*", inline=False)
            pages.append(challenge_embed)
            
            # Page 3: Special Floor Mechanics (NEW!)
            mechanics_embed = discord.Embed(
                title=f"⚙️ Floor {level} Special Mechanics ⚙️",
                description="*The tower's magic imbues this floor with unique challenges...*",
                color=discord.Color.orange()
            )
            
            # Add level-specific mechanics explanation
            mechanics_text = self.get_level_mechanics_description(level)
            mechanics_embed.add_field(name="🎯 How This Floor Works", value=mechanics_text, inline=False)
            mechanics_embed.set_footer(text=f"⚡ Understanding the mechanics is key to victory! ⚡")
            pages.append(mechanics_embed)
            
            # Page 4: Enemy information with strategic presentation (only if there are enemies)
            if "enemies" in level_info and level_info.get("type") != "reward":
                enemy_embed = discord.Embed(
                    title=f"👹 Your Adversaries 👹",
                    description="*The tower's guardians emerge from the shadows, ready to challenge your unity...*",
                    color=discord.Color.dark_purple()
                )
                
                enemy_text = ""
                for i, enemy in enumerate(level_info['enemies'], 1):
                    enemy_text += f"**{i}. {enemy['name']}**\n"
                    enemy_text += f"   ❤️ HP: {enemy['hp']} | ⚔️ Attack: {enemy['attack']} | 🛡️ Defense: {enemy['defense']}\n"
                    if 'special' in enemy:
                        enemy_text += f"   ✨ *Special: {enemy['special']}*\n"
                    enemy_text += "\n"
                
                enemy_embed.description += f"\n\n{enemy_text}"
                enemy_embed.set_footer(text=f"💪 Face them together as one... 💪")
                enemy_embed.add_field(name="🤝 Strategy", value="*Remember: your love is your greatest weapon. Fight as one, not as two.*", inline=False)
                pages.append(enemy_embed)
            else:
                # For Level 30 and other reward levels, show special reward page instead
                reward_embed = discord.Embed(
                    title=f"🌟 The Ultimate Reward 🌟",
                    description="*At the tower's peak, you find not enemies to fight, but a divine altar surrounded by pure light...*",
                    color=discord.Color.gold()
                )
                reward_embed.add_field(name="✨ Divine Choice", value="*You will be offered three sacred blessings: Power, Wealth, or Youth. But remember - the greatest treasure is what you already possess.*", inline=False)
                reward_embed.set_footer(text=f"💖 Your love has already conquered all... 💖")
                pages.append(reward_embed)
            
            # Page 4: Final preparation with romantic motivation
            final_embed = discord.Embed(
                title=f"💑 Ready to Fight Together 💑",
                description=f"**{author.display_name}** and **{partner.display_name}**,\n\n"
                           f"*Your bond has brought you to Floor {level} of the Tower of Eternal Bonds. "
                           f"Every step you've taken together has strengthened your love, every challenge overcome has deepened your connection.*\n\n"
                           f"*Now, face this challenge as one. Remember why you're here - "
                           f"not just to conquer the tower, but to prove that your love can overcome any obstacle, "
                           f"that together you are stronger than any force that would try to separate you.*\n\n"
                           f"**💕 When you're ready, begin your battle together. 💕**",
                color=discord.Color.gold()
            )
            final_embed.set_footer(text=f"💖 Your love is your greatest weapon... 💖")
            final_embed.add_field(name="💕 Final Words", value="*May your love guide you to victory, and may this trial only strengthen the bond you share.*", inline=False)
            pages.append(final_embed)
            
            # Show dialogue with enhanced presentation
            await ctx.send("💕 **The Tower of Eternal Bonds welcomes you both...** 💕")
            
            # Choose the appropriate view based on the dialogue_only parameter
            if dialogue_only:
                view = CouplesDialogueViewOnly(pages, author, partner) 
            else:
                view = CouplesDialogueView(pages, author, partner)
                
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            
            return True
            
        except Exception as e:
            await ctx.send(f"Error displaying dialogue: {e}")
            return False
    
    def get_level_mechanics_description(self, level):
        """Get a description of the special mechanics for each level."""
        mechanics = {
            1: "**✨ Standard Combat**: Basic couples combat with coordination bonuses for teamwork!",
            2: "**🫥 Blind Combat**: HP bars are hidden! Fight by faith and trust, not sight.",
            3: "**🪞 Twisted Reflections**: Face the demons of false jealousy - they attack with poisonous words!",
            4: "**🌪️ Storm Push**: Dynamic weather effects that show the fury of doubt battering your love!",
            5: "**🗡️ Split Combat**: You must fight separate enemies - each partner protects a different target!",
            6: "**💕 Shared Hearts**: Partners share each other's pain - 25% of damage to one is felt by both!",
            7: "**💎 Memory Shield**: Generate memory fragments each successful hit, use them to reduce incoming damage by 25% per fragment!",
            8: "**😠 Friendly Fire**: Your anger has a 15% chance to make you accidentally strike your partner!",
            9: "**⏰ Patience Test**: All actions take twice as long - test your patience and commitment!",
            10: "**💪 Unity Mode**: Deal +50% damage when your partner is critically wounded (below 25% HP)!",
            11: "**💃 Ballroom Dancing**: Combat becomes an elegant dance - all attacks are described as dance moves!",
            12: "**🧊 Frozen Stiff**: 20% chance each turn to be too frozen to act (Frost Giants are immune)!",
            13: "**🗣️ Miscommunication**: Fight 5 enemies at once with 30% chance to hit wrong targets due to confusion!",
            14: "**📊 Pride Tracking**: Your damage dealt is tracked and displayed - beware competitive feelings!",
            15: "**💔 Betrayal Illusions**: 25% chance to see false visions of betrayal, reducing your damage by 25%!",
            16: "**😠 Grudge Mechanics**: Taking damage builds grudges (+1 per hit), each grudge gives +10% damage but 5% friendly fire chance!",
            17: "**🤐 Hidden Secrets**: All damage numbers are hidden in the battle log - fight without knowing the impact!",
            18: "**😈 Temptation**: 30% chance to be charmed each turn, reducing your damage by half when distracted!",
            19: "**💥 Exposed Vulnerabilities**: 25% chance for critical hits that deal double damage by exploiting insecurities!",
            20: "**🛡️ Guardian's Test**: Every 5 turns, pause for coordination challenges to test your unity!",
            21: "**🔥 Heat Shield Sacrifice**: Every round, forge heat damages both partners (starts at 50, increases by 8). Each partner can 'shield' the other by taking 2.5x damage to protect them completely. Mutual sacrifice = normal damage, one-sided sacrifice = full protection + 2.5x damage to shielder, mutual selfishness = 1.5x damage to both!",
            22: "**😞 Valley of Despair**: Taking damage, missing attacks, and Despair Wraith strikes build despair stacks. Each stack reduces your damage by 8% and accuracy by 5% (max 80%/50%). Partners can encourage each other (20% chance when despair ≥5) to remove 2-4 stacks. Successful attacks have a 20% chance to reduce despair by 1!",
            23: "**🪞 Mirror of Truth**: One partner gets randomly possessed by a Truth Demon and attacks the other! The defender must survive 20 turns without killing their possessed partner. **Strategy Tip**: Consider unequipping weapons to reduce damage and avoid accidentally killing your beloved!",
            24: "**⚡ Storm of Chaos**: Environmental chaos every round! Damage variance becomes extreme (-150 to +250 for attacks, -200 to +300 for fireballs). Partners can anchor each other (25% chance per turn) for stable damage. Turn order randomizes every 3 rounds. Chaos intensity escalates over time. Chaos Elementals use reality-warping special attacks!",
            25: "**😨 Paralyzing Fear**: 30% chance each turn to be too terrified to act!",
            26: "**💢 Pain Fury**: Taking damage builds pain bonuses that increase your damage output! Each 25 damage taken = +1% damage bonus (capped at 50%). The more you suffer, the stronger you become! Pain bonuses apply to all attacks and show milestone messages at 10%, 25%, and 40% fury!",
            27: "**⏳ Aging Effect**: You age rapidly - all stats reduce by 3% each turn as time accelerates! Only affects partners, not pets or enemies. Milestone aging messages at turns 5, 10, and 15!",
            28: "**🌱 Growth Requirement**: You must heal each other before the final enemy becomes vulnerable!",
            29: "**👻 Spirit Healing**: Dead partners become spirits that can heal their living partner! Battle only ends when BOTH partners are dead. 80% chance for successful spirit healing (15-25% of target's max HP). Spirits provide emotional support and can keep fights going longer!",
            30: "**🌟 Divine Ceremony**: No combat - pure reward ceremony at the tower's peak!"
        }
        return mechanics.get(level, "**⚔️ Standard Combat**: No special mechanics - pure skill and teamwork!")

    async def handle_couples_chest_rewards(self, ctx, level, author, partner, emotes):
        """Handle chest rewards for couples battle tower victories."""
        try:
            level_str = str(level)
            victory_data = self.couples_battle_tower_data["victories"][level_str]
            chest_rewards = victory_data["chest_rewards"]
            
            # Create an embed for the treasure chest options
            chest_embed = discord.Embed(
                title="💕 Choose Your Treasure Together 💕",
                description=(
                    "Before you lie two treasure chests, each shimmering with an otherworldly aura. "
                    "The left chest appears ancient and ornate, while the right chest is smaller but radiates a faint magical glow.\n\n"
                    f"**{author.display_name}** and **{partner.display_name}**, you must decide together which chest to open. "
                    f"**Both of you must type the same choice** (`left` or `right`) to proceed. You have 60 seconds to agree!"
                ),
                color=0xff69b4  # Pink color for couples
            )
            chest_embed.set_footer(text=f"💑 Both partners must choose the same option... 💑")
            await ctx.send(embed=chest_embed)
            

            
            # Get prestige level for the couple
            async with self.bot.pool.acquire() as connection:
                prestige_level = await connection.fetchval('SELECT prestige FROM couples_battle_tower WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)
                
            # Track both partners' choices
            author_choice = None
            partner_choice = None
            choices_made = set()
            
            # Define check function for user response - either partner can respond
            def check(m):
                # Simple check without async calls
                return (m.author == author or m.author == partner) and m.content.lower() in ['left', 'right']
            
            # Collect choices from both partners
            start_time = asyncio.get_event_loop().time()
            timeout = 120.0
            

            
            while asyncio.get_event_loop().time() - start_time < timeout:
                try:
                    remaining_time = timeout - (asyncio.get_event_loop().time() - start_time)

                    
                    msg = await asyncio.wait_for(self.bot.wait_for('message', check=check), timeout=remaining_time)
                    choice = msg.content.lower()
                    

                    
                    if msg.author == author:
                        if author_choice is None:
                            author_choice = choice
                            choices_made.add(author.id)
                            await ctx.send(f"💕 **{author.display_name}** chose: **{choice}**")
                        else:
                            await ctx.send(f"💭 **{author.display_name}**, you already chose **{author_choice}**. You cannot change your choice!")
                            
                    elif msg.author == partner:
                        if partner_choice is None:
                            partner_choice = choice
                            choices_made.add(partner.id)
                            await ctx.send(f"💕 **{partner.display_name}** chose: **{choice}**")
                        else:
                            await ctx.send(f"💭 **{partner.display_name}**, you already chose **{partner_choice}**. You cannot change your choice!")
                    
                    # Check if both partners have made their choices
                    if author_choice is not None and partner_choice is not None:
                        if author_choice == partner_choice:
                            # They agree! Process the reward
                            await ctx.send(f"💕 **Perfect!** You both chose **{author_choice}**! Opening the chest...")
                            break
                        else:
                            # They disagree - show current choices and ask them to try again
                            await ctx.send(f"💔 **You disagree!** {author.display_name} chose **{author_choice}** and {partner.display_name} chose **{partner_choice}**. Please try to agree on the same choice!")
                            # Reset choices to allow them to try again
                            author_choice = None
                            partner_choice = None
                            choices_made.clear()
                            continue
                            
                except asyncio.TimeoutError:
                    break
        
            # Handle timeout or no agreement
            if author_choice != partner_choice:
                choice = random.choice(["left", "right"])
                chooser = "The tower"
                await ctx.send('💔 You could not agree on a choice in time. The tower will choose randomly for you.')
            else:
                choice = author_choice
                chooser = f"{author.display_name} & {partner.display_name}"
            
            
            # Generate rewards based on prestige level
            if prestige_level and prestige_level >= 1:
                await self.handle_couples_prestige_chest_rewards(ctx, level, author, partner, emotes, choice, chooser)
            else:
                await self.handle_couples_default_chest_rewards(ctx, level, chest_rewards["default"], author, partner, emotes, choice, chooser)
        except Exception as e:
            await ctx.send(f"An error occurred while handling chest rewards: {e}")
    
    async def handle_couples_prestige_chest_rewards(self, ctx, level, author, partner, emotes, choice, chooser):
        """Handle randomized rewards for prestige couples in battle tower."""
        async with self.bot.pool.acquire() as connection:
            # Generate random rewards for both chests
            left_reward_type = random.choice(['crate', 'money'])
            right_reward_type = random.choice(['crate', 'money'])
            
            # Get options from config
            chest_options = self.couples_battle_tower_data["chest_options"]["random"]
            
            # Generate the specific rewards
            if left_reward_type == 'crate':
                left_options = [opt["value"] for opt in chest_options["crate_options"]]
                left_weights = [opt["weight"] for opt in chest_options["crate_options"]]
                left_crate_type = random.choices(left_options, left_weights)[0]
            else:
                left_money_amount = random.choice(chest_options["money_options"])
                
            if right_reward_type == 'crate':
                right_options = [opt["value"] for opt in chest_options["crate_options"]]
                right_weights = [opt["weight"] for opt in chest_options["crate_options"]]
                right_crate_type = random.choices(right_options, right_weights)[0]
            else:
                right_money_amount = random.choice(chest_options["money_options"])
            
            # Process the reward based on choice
            new_level = level + 1
            if choice == 'left':
                if left_reward_type == 'crate':
                    await ctx.send(f'💕 **{chooser}** chose the left chest! You both find {emotes[left_crate_type]} crates!')
                    await connection.execute(
                        f'UPDATE profile SET crates_{left_crate_type} = crates_{left_crate_type} + 1 WHERE "user" = $1',
                        author.id)
                    await connection.execute(
                        f'UPDATE profile SET crates_{left_crate_type} = crates_{left_crate_type} + 1 WHERE "user" = $1',
                        partner.id)
                    
                    # Show what they missed
                    if right_reward_type == 'crate':
                        await ctx.send(f'💭 You could have both gotten {emotes[right_crate_type]} crates if you chose the right chest.')
                    else:
                        await ctx.send(f'💭 You could have both gotten **${right_money_amount}** if you chose the right chest.')
                else:
                    await ctx.send(f'💕 **{chooser}** chose the left chest! You both find **${left_money_amount}**!')
                    await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                            left_money_amount, author.id)
                    await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                            left_money_amount, partner.id)
                    
                    # Show what they missed
                    if right_reward_type == 'crate':
                        await ctx.send(f'💭 You could have both gotten {emotes[right_crate_type]} crates if you chose the right chest.')
                    else:
                        await ctx.send(f'💭 You could have both gotten **${right_money_amount}** if you chose the right chest.')
            else:  # right choice
                if right_reward_type == 'crate':
                    await ctx.send(f'💕 **{chooser}** chose the right chest! You both find {emotes[right_crate_type]} crates!')
                    await connection.execute(
                        f'UPDATE profile SET crates_{right_crate_type} = crates_{right_crate_type} + 1 WHERE "user" = $1',
                        author.id)
                    await connection.execute(
                        f'UPDATE profile SET crates_{right_crate_type} = crates_{right_crate_type} + 1 WHERE "user" = $1',
                        partner.id)
                    
                    # Show what they missed
                    if left_reward_type == 'crate':
                        await ctx.send(f'💭 You could have both gotten {emotes[left_crate_type]} crates if you chose the left chest.')
                    else:
                        await ctx.send(f'💭 You could have both gotten **${left_money_amount}** if you chose the left chest.')
                else:
                    await ctx.send(f'💕 **{chooser}** chose the right chest! You both find **${right_money_amount}**!')
                    await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                            right_money_amount, author.id)
                    await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                            right_money_amount, partner.id)
                    
                    # Show what they missed
                    if left_reward_type == 'crate':
                        await ctx.send(f'💭 You could have both gotten {emotes[left_crate_type]} crates if you chose the left chest.')
                    else:
                        await ctx.send(f'💭 You could have both gotten **${left_money_amount}** if you chose the left chest.')
            
            # Update level and clean up
            await ctx.send(f'💕 You have both advanced to floor: {new_level}')
            await connection.execute('UPDATE couples_battle_tower SET current_level = current_level + 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)
            try:
                await self.remove_player_from_fight(author.id)
                await self.remove_player_from_fight(partner.id)
            except Exception as e:
                pass

    @couples_battletower.command(name="help")
    @has_char()
    async def cbt_help(self, ctx):
        """Get comprehensive help about the Couples Battle Tower system"""
        # Check if user is married
        query = "SELECT marriage FROM profile WHERE profile.user = $1"
        result = await self.bot.pool.fetchval(query, ctx.author.id)
        partner_id = result

        if partner_id:
            partner = await self.bot.fetch_user(partner_id)
            partner_name = partner.display_name
        else:
            partner_name = "your beloved"

        embed = discord.Embed(
            title="💕 Couples Battle Tower 💕",
            description="**The Tower of Eternal Bonds**\n30-floor challenge for married couples!",
            color=discord.Color.magenta()
        )
        
        # Requirements & Commands - merged for mobile
        embed.add_field(
            name="📋 Basics",
            value=(
                "**Requirements:** Must be married, both participate\n"
                "**Cooldown:** 5 minutes between attempts\n\n"
                "**Commands:**\n"
                "`$cbt start` - Begin battle\n"
                "`$cbt progress` - View progress\n"
                "`$cbt preview <level>` - Preview level"
            ),
            inline=False
        )
        
        # Tower & Rewards - merged for mobile
        embed.add_field(
            name="🏗️ Tower & Rewards",
            value=(
                "**30 Floors** - Each floor is unique!\n"
                "• Floors 1-29: Combat + special mechanics\n"
                "• Floor 30: Divine ceremony (no combat)\n"
                "• Rewards every 5 floors\n"
                "• Partners choose rewards together\n"
                "• Prestige system for multiple completions"
            ),
            inline=False
        )
        
        # Important info - more prominent
        embed.add_field(
            name="⚠️ IMPORTANT: Pre-Battle Dialogue",
            value=(
                "**LAST PAGE shows floor mechanics!**\n"
                "• Read dialogue pages carefully\n"
                "• Mechanics are crucial for victory\n"
                "• Use `$cbt preview <level>` to review"
            ),
            inline=False
        )
        
        # Getting Started - compact
        if not partner_id:
            getting_started = (
                "1. Get married first! 💒\n"
                "2. `$cbt start` to begin\n"
                "3. Partner joins battle\n"
                "4. Conquer all floors! 🏆"
            )
        else:
            getting_started = (
                f"1. `$cbt start` with **{partner_name}** 💕\n"
                "2. Wait for partner to join\n"
                "3. Face unique mechanics together\n"
                "4. Reach divine ceremony! 🌟"
            )
        embed.add_field(name="🚀 Quick Start", value=getting_started, inline=False)
        
        # Love Quote - shorter
        if partner_id:
            embed.add_field(
                name="💕 Remember",
                value=f"*\"{ctx.author.display_name} and {partner_name}, your love has already conquered the greatest challenge - finding each other. The tower simply celebrates that bond.\"*",
                inline=False
            )
        else:
            embed.add_field(
                name="💕 Remember", 
                value="*\"Love is not about finding someone to live with, it's about finding someone you can't live without. Find your partner and face the tower together.\"*",
                inline=False
            )
        
        embed.set_footer(text="💖 May your love guide you to victory! 💖")
        
        await ctx.send(embed=embed)
    
    async def handle_couples_default_chest_rewards(self, ctx, level, rewards, author, partner, emotes, choice, chooser):
        """Handle fixed rewards for non-prestige couples in battle tower."""
        # Process the reward based on choice
        newlevel = level + 1
        if choice == 'left':
            left_reward = rewards["left"]
            if left_reward["type"] == "crate":
                message = f'💕 **{chooser}** chose the left chest! You both find: {emotes[left_reward["value"]]} '
                if left_reward["amount"] > 1:
                    message += f'{left_reward["amount"]} {left_reward["value"].capitalize()} Crates!'
                else:
                    message += f'A {left_reward["value"].capitalize()} Crate!'
                
                await ctx.send(message)
                await ctx.send(f'💕 You have both advanced to floor: {newlevel}')
                
                async with self.bot.pool.acquire() as connection:
                    await connection.execute(
                        f'UPDATE profile SET crates_{left_reward["value"]} = crates_{left_reward["value"]} + {left_reward["amount"]} WHERE "user" = $1',
                        author.id)
                    await connection.execute(
                        f'UPDATE profile SET crates_{left_reward["value"]} = crates_{left_reward["value"]} + {left_reward["amount"]} WHERE "user" = $1',
                        partner.id)
                    await connection.execute('UPDATE couples_battle_tower SET current_level = current_level + 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)
            elif left_reward["type"] == "money":
                extra_msg = f" {left_reward.get('message', '')}" if "message" in left_reward else ""
                await ctx.send(f'💕 **{chooser}** chose the left chest! You both find: **${left_reward["value"]}**!{extra_msg}')
                await ctx.send(f'💕 You have both advanced to floor: {newlevel}')
                
                async with self.bot.pool.acquire() as connection:
                    await connection.execute(
                        f'UPDATE profile SET money = money + {left_reward["value"]} WHERE "user" = $1',
                        author.id)
                    await connection.execute(
                        f'UPDATE profile SET money = money + {left_reward["value"]} WHERE "user" = $1',
                        partner.id)
                    await connection.execute('UPDATE couples_battle_tower SET current_level = current_level + 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)
            elif left_reward["type"] == "nothing":
                await ctx.send(f'💔 **{chooser}** chose the left chest! You both find: Nothing, bad luck!')
                await ctx.send(f'💕 You have both advanced to floor: {newlevel}')
                
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE couples_battle_tower SET current_level = current_level + 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)
            elif left_reward["type"] == "random":
                # Handle special random case for level 15
                legran = random.randint(1, 2)
                if legran == 1:
                    await ctx.send(f'💔 **{chooser}** chose the left chest! You both find: Nothing, bad luck!')
                    await ctx.send(f'💕 You have both advanced to floor: {newlevel}')
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute('UPDATE couples_battle_tower SET current_level = current_level + 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)
                else:
                    await ctx.send(f'💕 **{chooser}** chose the left chest! You both find: <:F_Legendary:1139514868400132116> A Legendary Crate!')
                    await ctx.send(f'💕 You have both advanced to floor: {newlevel}')
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute(
                            'UPDATE profile SET crates_legendary = crates_legendary + 1 WHERE "user" = $1',
                            author.id)
                        await connection.execute(
                            'UPDATE profile SET crates_legendary = crates_legendary + 1 WHERE "user" = $1',
                            partner.id)
                        await connection.execute('UPDATE couples_battle_tower SET current_level = current_level + 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)
        else:  # right choice
            right_reward = rewards["right"]
            if right_reward["type"] == "crate":
                message = f'💕 **{chooser}** chose the right chest! You both find: {emotes[right_reward["value"]]} '
                if right_reward["amount"] > 1:
                    message += f'{right_reward["amount"]} {right_reward["value"].capitalize()} Crates!'
                else:
                    message += f'A {right_reward["value"].capitalize()} Crate!'
                
                await ctx.send(message)
                await ctx.send(f'💕 You have both advanced to floor: {newlevel}')
                
                async with self.bot.pool.acquire() as connection:
                    await connection.execute(
                        f'UPDATE profile SET crates_{right_reward["value"]} = crates_{right_reward["value"]} + {right_reward["amount"]} WHERE "user" = $1',
                        author.id)
                    await connection.execute(
                        f'UPDATE profile SET crates_{right_reward["value"]} = crates_{right_reward["value"]} + {right_reward["amount"]} WHERE "user" = $1',
                        partner.id)
                    await connection.execute('UPDATE couples_battle_tower SET current_level = current_level + 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)
            elif right_reward["type"] == "money":
                extra_msg = f" {right_reward.get('message', '')}" if "message" in right_reward else ""
                await ctx.send(f'💕 **{chooser}** chose the right chest! You both find: **${right_reward["value"]}**!{extra_msg}')
                await ctx.send(f'💕 You have both advanced to floor: {newlevel}')
                
                async with self.bot.pool.acquire() as connection:
                    await connection.execute(
                        f'UPDATE profile SET money = money + {right_reward["value"]} WHERE "user" = $1',
                        author.id)
                    await connection.execute(
                        f'UPDATE profile SET money = money + {right_reward["value"]} WHERE "user" = $1',
                        partner.id)
                    await connection.execute('UPDATE couples_battle_tower SET current_level = current_level + 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)
            elif right_reward["type"] == "nothing":
                await ctx.send(f'💔 **{chooser}** chose the right chest! You both find: Nothing, bad luck!')
                await ctx.send(f'💕 You have both advanced to floor: {newlevel}')
                
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE couples_battle_tower SET current_level = current_level + 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)
            elif right_reward["type"] == "random":
                # Handle special random case for level 15
                legran = random.randint(1, 2)
                if legran == 1:
                    await ctx.send(f'💔 **{chooser}** chose the right chest! You both find: Nothing, bad luck!')
                    await ctx.send(f'💕 You have both advanced to floor: {newlevel}')
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute('UPDATE couples_battle_tower SET current_level = current_level + 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)
                else:
                    await ctx.send(f'💕 **{chooser}** chose the right chest! You both find: <:F_Legendary:1139514868400132116> A Legendary Crate!')
                    await ctx.send(f'💕 You have both advanced to floor: {newlevel}')
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute(
                            'UPDATE profile SET crates_legendary = crates_legendary + 1 WHERE "user" = $1',
                            author.id)
                        await connection.execute(
                            'UPDATE profile SET crates_legendary = crates_legendary + 1 WHERE "user" = $1',
                            partner.id)
                        await connection.execute('UPDATE couples_battle_tower SET current_level = current_level + 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)

    async def handle_couples_finale_rewards(self, ctx, level, author, partner):
        """Handle finale rewards for couples battle tower completion."""
        async with self.bot.pool.acquire() as connection:
            # Get prestige level
            prestige_level = await connection.fetchval('SELECT prestige FROM couples_battle_tower WHERE (user_id = $1 AND partner_id = $2) OR (user_id = $2 AND partner_id = $1)', author.id, partner.id)
            
            # Get reward configuration
            victory_data = self.couples_battle_tower_data["victories"][str(level)]
            rewards = victory_data["rewards"]
            
            if prestige_level and prestige_level >= 1:
                # Prestige rewards
                if rewards["prestige"]["type"] == "random_premium":
                    chest_options = self.couples_battle_tower_data["chest_options"]["random_premium"]
                    reward_type = random.choices(chest_options["types"], chest_options["weights"])[0]
                    reward_amount = 1
                else:
                    reward_type = rewards["prestige"]["type"]
                    reward_amount = rewards["prestige"]["amount"]
            else:
                # Default rewards
                reward_type = rewards["default"]["type"]
                reward_amount = rewards["default"]["amount"]
            
            # Apply rewards to both partners
            if reward_type == "crate":
                crate_type = rewards["default"]["value"]
                await ctx.send(f'💕 **Congratulations!** You both receive {reward_amount} {crate_type.capitalize()} Crate(s)!')
                await connection.execute(
                    f'UPDATE profile SET crates_{crate_type} = crates_{crate_type} + {reward_amount} WHERE "user" = $1',
                    author.id)
                await connection.execute(
                    f'UPDATE profile SET crates_{crate_type} = crates_{crate_type} + {reward_amount} WHERE "user" = $1',
                    partner.id)
            elif reward_type == "divine":
                await ctx.send(f'💕 **Congratulations!** You both receive {reward_amount} Divine Crate(s)!')
                await connection.execute(
                    f'UPDATE profile SET crates_divine = crates_divine + {reward_amount} WHERE "user" = $1',
                    author.id)
                await connection.execute(
                    f'UPDATE profile SET crates_divine = crates_divine + {reward_amount} WHERE "user" = $1',
                    partner.id)
            elif reward_type == "legendary":
                await ctx.send(f'💕 **Congratulations!** You both receive {reward_amount} Legendary Crate(s)!')
                await connection.execute(
                    f'UPDATE profile SET crates_legendary = crates_legendary + {reward_amount} WHERE "user" = $1',
                    author.id)
                await connection.execute(
                    f'UPDATE profile SET crates_legendary = crates_legendary + {reward_amount} WHERE "user" = $1',
                    partner.id)
            elif reward_type == "fortune":
                await ctx.send(f'💕 **Congratulations!** You both receive {reward_amount} Fortune Crate(s)!')
                await connection.execute(
                    f'UPDATE profile SET crates_fortune = crates_fortune + {reward_amount} WHERE "user" = $1',
                    author.id)
                await connection.execute(
                    f'UPDATE profile SET crates_fortune = crates_fortune + {reward_amount} WHERE "user" = $1',
                    partner.id)
            
            # Update prestige and reset level
            await connection.execute('UPDATE couples_battle_tower SET prestige = prestige + 1, current_level = 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', author.id, partner.id)
            await ctx.send(f'💕 **You have both achieved Prestige {prestige_level + 1 if prestige_level else 1}!** The tower resets to Floor 1 with increased difficulty.')

async def setup(bot):
    await bot.add_cog(BattleSettings(bot))
    
    battles = Battles(bot)
    await battles.battle_factory.initialize()
    await bot.add_cog(battles)
