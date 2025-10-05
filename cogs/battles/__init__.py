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
from discord.ext import commands
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
<<<<<<< HEAD
from classes.errors import NoChoice

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
=======

class PetEggSelect(Select):
    def __init__(self, items):
        self.items = items
        options = [
            discord.SelectOption(
                label=f"{i+1}. {item['type'].title()}",
                description=item['display_name'][:50],  # Limit description length
                value=str(i)
            ) for i, item in enumerate(items)
        ]
        
        super().__init__(
            placeholder="Select a pet/egg to release...",
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            min_values=1,
            max_values=1,
            options=options
        )
    
<<<<<<< HEAD
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
    
=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
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
<<<<<<< HEAD
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
=======
        
        # Add the select dropdown
        self.select = PetEggSelect(items)
        self.add_item(self.select)
        
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
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
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
    def __init__(self, pages: list[discord.Embed], author: discord.User):
        super().__init__(timeout=60)
        self.pages = pages
        self.current_page = 0
        self.author = author

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
        # Only allow the view author to interact with these buttons.
        return interaction.user.id == self.author.id

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

<<<<<<< HEAD
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

=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
class Battles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.forceleg = False
        self.battle_factory = BattleFactory(bot)
        self.fighting_players = {}
<<<<<<< HEAD
        
        self.dragon_party_views = []  # Track active dragon party views
        self.battle_settings = BattleSettings(bot)
        self.active_battles = {}
        self.settings = BattleSettings(bot)
        self.currently_in_fight = set()
        
        # Macro detection storage
        self.pve_macro_detection = {}  # {user_id: {"count": int, "timestamp": float}}
        
        self.load_data_files()
=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e

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
<<<<<<< HEAD
        
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

    def load_data_files(self):
        """Load all necessary data files for battles"""
        # Load battle tower data
        with open(os.path.join(os.path.dirname(__file__), 'battle_tower_data.json'), 'r') as f:
            self.battle_data = json.load(f)

        # Load game levels
        with open(os.path.join(os.path.dirname(__file__), 'game_levels.json'), 'r') as f:
            data = json.load(f)
            self.levels = data['levels']

        # Load dialogue data
        with open(os.path.join(os.path.dirname(__file__), 'battle_tower_dialogues.json'), 'r') as f:
            self.dialogue_data = json.load(f)

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
    
=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e

    def load_data_files(self):
        """Load all necessary data files for battles"""
        # Load battle tower data
        with open(os.path.join(os.path.dirname(__file__), 'battle_tower_data.json'), 'r') as f:
            self.battle_data = json.load(f)

<<<<<<< HEAD
    
    async def is_player_in_fight(self, player_id):
        """Check if the player is in a fight based on the dictionary"""
        return player_id in self.fighting_players

=======
        # Load game levels
        with open(os.path.join(os.path.dirname(__file__), 'game_levels.json'), 'r') as f:
            data = json.load(f)
            self.levels = data['levels']

        # Load dialogue data
        with open(os.path.join(os.path.dirname(__file__), 'battle_tower_dialogues.json'), 'r') as f:
            self.dialogue_data = json.load(f)

        # Load monsters if file exists
        try:
            with open("monsters.json", "r") as f:
                self.monsters_data = json.load(f)
        except FileNotFoundError:
            self.monsters_data = {}
            
        # Initialize element extension
        from .extensions.elements import ElementExtension
        self.element_ext = ElementExtension()

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
    
    async def is_player_in_fight(self, player_id):
        """Check if the player is in a fight based on the dictionary"""
        return player_id in self.fighting_players

>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
    async def add_player_to_fight(self, player_id):
        """Add the player to the fight dictionary with a lock"""
        self.fighting_players[player_id] = asyncio.Lock()
        await self.fighting_players[player_id].acquire()

    async def remove_player_from_fight(self, player_id):
        """Release the lock and remove the player from the fight dictionary"""
        if player_id in self.fighting_players:
            self.fighting_players[player_id].release()
            del self.fighting_players[player_id]
<<<<<<< HEAD

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
=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
    
    async def display_dialogue(self, ctx, level, name_value, dialoguetoggle=False):
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
        for line in dialogue_info["lines"]:
            speaker = line["speaker"]
            text = line["text"].replace("PLAYER", name_value)
            thumbnail = line["thumbnail"]
            
            # Replace placeholder thumbnails
            if thumbnail == "PLAYER_AVATAR":
                thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            elif "special" in dialogue_info and dialogue_info["special"] == "random_users":
                if speaker == "RANDOM_USER_1" and random_user_objects:
                    speaker = random_user_objects[0].display_name
                    text = text.replace("RANDOM_USER_1", speaker)
                    thumbnail = random_user_objects[0].avatar.url if random_user_objects[0].avatar else "https://ia803204.us.archive.org/4/items/discordprofilepictures/discordblue.png"
                elif speaker == "RANDOM_USER_2" and len(random_user_objects) > 1:
                    speaker = random_user_objects[1].display_name
                    text = text.replace("RANDOM_USER_2", speaker)
                    thumbnail = random_user_objects[1].avatar.url if random_user_objects[1].avatar else "https://ia803204.us.archive.org/4/items/discordprofilepictures/discordblue.png"
            
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
        view = DialogueView(pages, ctx.author)
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
<<<<<<< HEAD
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
=======
                'UPDATE profile SET "pvpwins"="pvpwins"+1, "money"="money"+$1 WHERE "user"=$2;',
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
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
        
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
                    user_level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)

                    level_names_1 = [
                        "The Tower's Foyer",
                        "Shadowy Staircase",
                        "Chamber of Whispers",
                        "Serpent's Lair",
                        "Halls of Despair",
                        "Crimson Abyss",
                        "Forgotten Abyss",
                        "Dreadlord's Domain",
                        "Gates of Twilight",
                        "Twisted Reflections",
                        "Voidforged Sanctum",
                        "Nexus of Chaos",
                        "Eternal Torment Halls",
                        "Abyssal Desolation",
                        "Cursed Citadel",
                        "The Spire of Shadows",
                        "Tempest's Descent",
                        "Roost of Doombringers",
                        "The Endless Spiral",
                        "Malevolent Apex",
                        "Apocalypse's Abyss",
                        "Chaosborne Throne",
                        "Supreme Darkness",
                        "The Tower's Heart",
                        "The Ultimate Test",
                        "Realm of Annihilation",
                        "Lord of Despair",
                        "Abyssal Overlord",
                        "The End of All",
                        "The Final Confrontation"
                    ]

                    # Function to generate the formatted level list
                    def generate_level_list(levels, start_level=1):
                        result = "```\n"
                        for level, level_name in enumerate(levels, start=start_level):
                            checkbox = "❌" if level == user_level else "✅" if level < user_level else "❌"
                            result += f"Level {level:<2} {checkbox} {level_name}\n"
                        result += "```"
                        return result

                    # Create embed for levels 1-30
                    prestige_level = await connection.fetchval('SELECT prestige FROM battletower WHERE id = $1',
                                                               ctx.author.id)

                    embed_1 = discord.Embed(
                        title="Battle Tower Progress (Levels 1-30)",
                        description=f"Level: {user_level}\nPrestige Level: {prestige_level}",
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

    async def handle_victory(self, ctx, level, name_value, dialoguetoggle, minion1_name=None, minion2_name=None, emotes=None, player_balance=0, victory_description=None):
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
        
        # Create and send the victory embed
        victory_embed = discord.Embed(
            title=victory_data["title"],
            description=description,
            color=0x00ff00  # Green color for success
        )
        await ctx.send(embed=victory_embed)
        
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
<<<<<<< HEAD

=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
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
<<<<<<< HEAD

=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
    
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
        # Create and send cosmic embed
        cosmic_embed = discord.Embed(
            title="The Cosmic Abyss: A Symphony of Despair",
            description=self.battle_data["victories"]["30"]["description"],
            color=0xff0000  # Red color for the climax
        )
        await ctx.send(embed=cosmic_embed)
        
        # Check prestige level
        async with self.bot.pool.acquire() as connection:
            prestige_level = await connection.fetchval('SELECT prestige FROM battletower WHERE id = $1', ctx.author.id)
            
        if prestige_level >= 1:
            # Update level
            async with self.bot.pool.acquire() as connection:
                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
                
            await ctx.send(f'This is the end for you... {ctx.author.mention}.. or is it..?')
            
            # Award a random premium crate
            success = True
            self.bot.dispatch("raid_completion", ctx, success, ctx.author.id)
            
            # Get premium crate options
            premium_options = self.battle_data["chest_options"]["random_premium"]
            crate_options = premium_options["types"]
            weights = premium_options["weights"]
            
            # Select random crate type
            selected_crate = random.choices(crate_options, weights)[0]
            
            # Award the crate
            async with self.bot.pool.acquire() as connection:
                await connection.execute(
                    f'UPDATE profile SET crates_{selected_crate} = crates_{selected_crate} + 1 WHERE "user" = $1',
                    ctx.author.id)
                    
            # Get emoji mapping for display
            emotes = {
<<<<<<< HEAD
                "common": "<:c_common:1403797578197368923>",
                "uncommon": "<:c_uncommon:1403797597532983387>",
                "rare": "<:c_rare:1403797594827657247>",
                "magic": "<:c_Magic:1403797589169541330>",
                "legendary": "<:c_Legendary:1403797587236225044>",
                "mystery": "<:c_mystspark:1403797593129222235>",
                "fortune": "<:c_money:1403797585411575971>",
                "divine": "<:c_divine:1403797579635884202>",
=======
                "common": "<:F_common:1139514874016309260>",
                "uncommon": "<:F_uncommon:1139514875828252702>",
                "rare": "<:F_rare:1139514880517484666>",
                "magic": "<:F_Magic:1139514865174720532>",
                "legendary": "<:F_Legendary:1139514868400132116>",
                "mystery": "<:F_mystspark:1139521536320094358>",
                "fortune": "<:f_money:1146593710516224090>",
                "divine": "<:f_divine:1169412814612471869>"
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            }
                    
            await ctx.send(f"You have received 1 {emotes[selected_crate]} crate for completing the battletower on prestige level: {prestige_level}. Congratulations!")
        else:
            # First-time completion gets divine crate
            async with self.bot.pool.acquire() as connection:
                await connection.execute(
                    'UPDATE profile SET crates_divine = crates_divine + 1 WHERE "user" = $1',
                    ctx.author.id)
                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1', ctx.author.id)
                
            await ctx.send(f'This is the end for you... {ctx.author.mention}.. or is it..?')
            await ctx.send("You have received 1 <:f_divine:1169412814612471869> crate for completing the battletower, congratulations.")
            
        # Complete the raid
        completed = True
        self.bot.dispatch("raid_completion", ctx, completed, ctx.author.id)
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
<<<<<<< HEAD

                level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)
                if level == 0:
                    await connection.execute('UPDATE battletower SET level = 1 WHERE id = $1', ctx.author.id)
                    level = 1

=======
                level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
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
                                'UPDATE battletower SET level = 1, prestige = prestige + 1 WHERE id = $1',
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
<<<<<<< HEAD
                except NoChoice:
                    await ctx.send("Prestige canceled - no choice was made.")
                    await self.bot.reset_cooldown(ctx)
                    return

            # Display dialogue for the current level
            await self.display_dialogue(ctx, level, name_value, dialoguetoggle)

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
                        player_balance=player_balance
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

=======

            # Display dialogue for the current level
            await self.display_dialogue(ctx, level, name_value, dialoguetoggle)

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
                "common": "<:F_common:1139514874016309260>",
                "uncommon": "<:F_uncommon:1139514875828252702>",
                "rare": "<:F_rare:1139514880517484666>",
                "magic": "<:F_Magic:1139514865174720532>",
                "legendary": "<:F_Legendary:1139514868400132116>",
                "mystery": "<:F_mystspark:1139521536320094358>",
                "fortune": "<:f_money:1146593710516224090>",
                "divine": "<:f_divine:1169412814612471869>"
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
                        player_balance=player_balance
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

>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
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
    @commands.command(brief=_("Battle against a monster and gain XP"))
    @user_cooldown(1800)  # 30-minute cooldown
    @locale_doc
    async def pve(self, ctx):
        """Battle against a monster and gain experience points."""
<<<<<<< HEAD
        # Check for macro detection
        macro_detected = await self.check_pve_macro_detection(ctx.author.id)
        if macro_detected:
            try:
                user = await self.bot.fetch_user(295173706496475136)
                await user.send(f"User {ctx.author.id} detected using macros in PVE command!")
            except:
                pass  # Silently fail if DM fails
        
        # Debug: Log macro detection data
        if ctx.author.id in self.pve_macro_detection:
            user_data = self.pve_macro_detection[ctx.author.id]
            print(f"Macro debug - User {ctx.author.id}: count={user_data['count']}, macro_detected={macro_detected}")

        
=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
        # Check for monster override from scout command
        monster_override = getattr(ctx, 'monster_override', None)
        levelchoice_override = getattr(ctx, 'levelchoice_override', None)

        # Load monsters data
        try:
            if not self.monsters_data:
                with open("monsters.json", "r") as f:
                    self.monsters_data = json.load(f)
            
            # Convert keys from strings to integers and filter out non-public monsters
            monsters = {}
            for level_str, monster_list in self.monsters_data.items():
                level = int(level_str)
                # Only keep monsters where ispublic is True (defaulting to True if key is missing)
                public_monsters = [monster for monster in monster_list if monster.get("ispublic", True)]
                monsters[level] = public_monsters
        except Exception as e:
            await ctx.send(_("Error loading monsters data. Please contact the admin."))
            await self.bot.reset_cooldown(ctx)
            return

        # Fetch the player's XP and determine level
        player_xp = ctx.character_data.get("xp", 0)
        player_level = rpgtools.xptolevel(player_xp)

        # Send an embed indicating that the player is searching for a monster
        searching_embed = discord.Embed(
            title=_("Searching for a monster..."),
            description=_("Your journey begins as you venture into the unknown to find a worthy foe."),
            color=self.bot.config.game.primary_colour,
        )
        searching_message = await ctx.send(embed=searching_embed)

        # Determine monster to fight
        if not monster_override:
            # Simulate searching time
            await asyncio.sleep(random.randint(3, 8))

            # Determine if a legendary monster should spawn
            legendary_spawn_chance = 0.01  # 1% chance
            spawn_legendary = False

            if player_level >= 5:
                if random.random() < legendary_spawn_chance:
                    spawn_legendary = True

<<<<<<< HEAD
=======
            if ctx.author.id == 295173706496475136 and self.forceleg:
                spawn_legendary = True
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e

            if spawn_legendary:
                # Select legendary monster
                monster = random.choice(monsters[11])
                legendary_embed = discord.Embed(
                    title=_("A Legendary God Appears!"),
                    description=_(
                        "Behold! **{monster}** has descended to challenge you! Prepare for an epic battle!"
                    ).format(monster=monster["name"]),
                    color=discord.Color.gold(),
                )
                await searching_message.edit(embed=legendary_embed)
                levelchoice = 11
                await asyncio.sleep(4)
            else:
                # Determine monster level based on player level
                if player_level <= 4:
                    levelchoice = random.randint(1, 2)
                elif player_level <= 8:
                    levelchoice = random.randint(1, 3)
                elif player_level <= 12:
                    levelchoice = random.randint(1, 4)
                elif player_level <= 15:
                    levelchoice = random.randint(1, 5)
                elif player_level <= 20:
                    levelchoice = random.randint(1, 6)
                elif player_level <= 25:
                    levelchoice = random.randint(1, 7)
                elif player_level <= 30:
                    levelchoice = random.randint(1, 8)
                elif player_level <= 35:
                    levelchoice = random.randint(1, 9)
                elif player_level <= 40:
<<<<<<< HEAD
                    # For levels 1-10, level 10 has half chance
                    level_weights = [10] * 10  # 10 weights for levels 1-10
                    level_weights[9] = 5  # Level 10 (index 9) gets half weight
                    levelchoice = random.choices(range(1, 11), weights=level_weights, k=1)[0]
                else:  # player_level > 40
                    # For levels 1-11, level 10 has half chance, level 11 much lower
                    level_weights = [10] * 11  # 11 weights for levels 1-11
                    level_weights[9] = 5  # Level 10 (index 9) gets half weight
                    level_weights[10] = 1  # Level 11 (index 10) gets much lower weight
=======
                    # For levels 1-40, levels 1-9 have normal chance, level 10 has half chance
                    level_weights = [10] * 10  # Default weight of 10 for all levels
                    level_weights[9] = 5  # Level 10 (index 9) gets half weight (5/10)
                    levelchoice = random.choices(range(1, 11), weights=level_weights, k=1)[0]
                else:  # player_level > 40
                    # For level 41+, levels 1-9 and 11 have normal chance, level 10 has half chance
                    level_weights = [10] * 11  # Default weight of 10 for all levels
                    level_weights[9] = 5  # Level 10 (index 9) gets half weight (5/10)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                    levelchoice = random.choices(range(1, 12), weights=level_weights, k=1)[0]

                monster = random.choice(monsters[levelchoice])
        else:
            # Use override from scout command
            monster = monster_override
            levelchoice = levelchoice_override

        # Update embed with found monster
        found_embed = discord.Embed(
            title=_("Monster Found!"),
            description=_("A Level {level} **{monster}** has appeared! Prepare to fight..").format(
                level=levelchoice, monster=monster["name"]
            ),
            color=self.bot.config.game.primary_colour,
        )
        await searching_message.edit(embed=found_embed)
        await asyncio.sleep(4)

<<<<<<< HEAD
        # Check for macro penalty
        macro_penalty_level = self.get_pve_macro_penalty_level(ctx.author.id)
        
=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
        # Create and start the battle
        try:
            battle = await self.battle_factory.create_battle(
                "pve",
                ctx,
                player=ctx.author,
                monster_data=monster,
<<<<<<< HEAD
                monster_level=levelchoice,
                macro_penalty_level=macro_penalty_level
=======
                monster_level=levelchoice
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
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
                # Player won - check for egg drops based on level
<<<<<<< HEAD
                # Skip egg drops if macro penalty is active (count >= 12)
                if levelchoice < 12 and macro_penalty_level == 0:
=======
                if levelchoice < 12:
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                    # Calculate base egg chance
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
                        # Handle egg drop logic
                        await self.handle_egg_drop(ctx, monster, levelchoice)
            
                # Dispatch PVE completion event
                success = True
                self.bot.dispatch("PVE_completion", ctx, success)
            
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
<<<<<<< HEAD
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

=======
                    if record_to_remove["type"] == "pet":
                        await conn.execute("DELETE FROM monster_pets WHERE id = $1;",
                                          record_to_remove["id"])
                    else:
                        await conn.execute("DELETE FROM monster_eggs WHERE id = $1;",
                                          record_to_remove["id"])
                    await ctx.send(
                        _(f"Released {record_to_remove['type']} '{record_to_remove['display_name']}' to make room."))
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
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
            if not self.monsters_data:
                with open("monsters.json", "r") as f:
                    self.monsters_data = json.load(f)
            
            # Convert keys from strings to integers and filter out non-public monsters
            monsters = {}
            for level_str, monster_list in self.monsters_data.items():
                level = int(level_str)
                # Only keep monsters where ispublic is True (defaulting to True if key is missing)
                public_monsters = [monster for monster in monster_list if monster.get("ispublic", True)]
                monsters[level] = public_monsters
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
                
                # Create scouting view
                class ScoutingView(discord.ui.View):
                    def __init__(self, ctx, monster_data, rerolls_left, max_rerolls):
                        super().__init__(timeout=30)
                        self.ctx = ctx
                        self.monster = monster_data
                        self.rerolls = rerolls_left
                        self.max_rerolls = max_rerolls
                        self.result = None
                        
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
                    
                    async def engage_callback(self, interaction: discord.Interaction):
                        if interaction.user.id != self.ctx.author.id:
                            await interaction.response.send_message("This isn't your battle!", ephemeral=True)
                            return
                        
                        await interaction.response.defer()
                        self.result = "engage"
                        self.stop()
                    
                    async def reroll_callback(self, interaction: discord.Interaction):
                        if interaction.user.id != self.ctx.author.id:
                            await interaction.response.send_message("This isn't your battle!", ephemeral=True)
                            return
                        
                        if self.rerolls > 0:
                            await interaction.response.defer()
                            self.rerolls -= 1
                            self.result = "reroll"
                            self.stop()
                    
                    async def retreat_callback(self, interaction: discord.Interaction):
                        if interaction.user.id != self.ctx.author.id:
                            await interaction.response.send_message("This isn't your battle!", ephemeral=True)
                            return
                        
                        await interaction.response.defer()
                        self.result = "retreat"
                        self.stop()
                    
                    def update_button_states(self):
                        self.reroll_button.disabled = self.rerolls <= 0
                
                # Function to select monster based on level
                async def select_monster(level):
                    return random.choice(monsters[level])
                
                # Function to create monster info embed
                async def show_monster_info(monster_data, rerolls, max_rerolls):
                    embed = discord.Embed(
                        title="🔍 Monster Scouting Report",
                        description=f"You spot a Level {levelchoice} **{monster_data['name']}** ahead!",
                        color=discord.Color.blue()
                    )
                    
                    element_emoji = element_to_emoji.get(monster_data["element"], "❓")
                    stats_text = (
                        f"**Element:** {element_emoji} {monster_data['element']}\n"
                        f"**HP:** {monster_data['hp']}\n"
                        f"**Attack:** {monster_data['attack']}\n"
                        f"**Defense:** {monster_data['defense']}"
                    )
                    embed.add_field(name="Stats", value=stats_text, inline=False)
                    
                    embed.add_field(
                        name="Scouting Options",
                        value=f"Rerolls remaining: {rerolls}/{max_rerolls}",
                        inline=False
                    )
                    
                    return embed
                
                # Main scouting loop
                while True:
                    # Determine monster level with weighted random (same as pve command)
                    if player_level <= 4:
                        levelchoice = random.randint(1, 2)
                    elif player_level <= 8:
                        levelchoice = random.randint(1, 3)
                    elif player_level <= 12:
                        levelchoice = random.randint(1, 4)
                    elif player_level <= 15:
                        levelchoice = random.randint(1, 5)
                    elif player_level <= 20:
                        levelchoice = random.randint(1, 6)
                    elif player_level <= 25:
                        levelchoice = random.randint(1, 7)
                    elif player_level <= 30:
                        levelchoice = random.randint(1, 8)
                    elif player_level <= 35:
                        levelchoice = random.randint(1, 9)
                    elif player_level <= 40:
<<<<<<< HEAD
                        # For levels 1-10, level 10 has half chance
                        level_weights = [10] * 10  # 10 weights for levels 1-10
                        level_weights[9] = 5  # Level 10 (index 9) gets half weight
                        levelchoice = random.choices(range(1, 11), weights=level_weights, k=1)[0]
                    else:  # player_level > 40
                        # For levels 1-11, level 10 has half chance, level 11 much lower
                        level_weights = [10] * 11  # 11 weights for levels 1-11
                        level_weights[9] = 5  # Level 10 (index 9) gets half weight
                        level_weights[10] = 1  # Level 11 (index 10) gets much lower weight
=======
                        # For levels 1-40, levels 1-9 have normal chance, level 10 has half chance
                        level_weights = [10] * 10  # Default weight of 10 for all levels
                        level_weights[9] = 5  # Level 10 (index 9) gets half weight (5/10)
                        levelchoice = random.choices(range(1, 11), weights=level_weights, k=1)[0]
                    else:  # player_level > 40
                        # For level 41+, levels 1-9 and 11 have normal chance, level 10 has half chance
                        level_weights = [10] * 11  # Default weight of 10 for all levels
                        level_weights[9] = 5  # Level 10 (index 9) gets half weight (5/10)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                        levelchoice = random.choices(range(1, 12), weights=level_weights, k=1)[0]
                    
                    # Select and display monster
                    monster_data = await select_monster(levelchoice)
                    embed = await show_monster_info(monster_data, rerolls_left, max_rerolls)
                    
                    # Show scouting view
                    view = ScoutingView(ctx, monster_data, rerolls_left, max_rerolls)
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
<<<<<<< HEAD

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

=======

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

>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
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
<<<<<<< HEAD
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
        stage = await self.battle_factory.dragon_ext.get_dragon_stage(dragon_level)
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
                    if interaction.user != ctx.author:
                        return await interaction.response.send_message("Only the party leader can start the challenge!", ephemeral=True)
                        
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
                        await self._handle_dragon_victory(ctx, view.party_members)
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
    
    async def _handle_dragon_victory(self, ctx, party_members):
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
        try:
            async with self.bot.pool.acquire() as conn:
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
                        if member.id == 295173706496475136:
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
                        
                        # ICE DRAGON WEAPON REWARDS
                        # Roll for weapon rewards for each player
                        
                        # Define ice dragon themed weapon names and types
                        # Drop rates increase slightly with dragon level (max +8% at level 30+)
                        level_bonus = min(0.08, (old_level - 1) * 0.003)  # 0.3% bonus per level, max 8%
                        
                        ice_dragon_weapons = [
                            # 1-handed weapons (90-100 stats) - 1% chance each + level bonus (max 5% total)
                            {"name": "Frostbite Blade", "type": ItemType.Sword, "min_stat": 20, "max_stat": 70, "chance": min(0.005, 0.001 + level_bonus)},
                            {"name": "Ice Shard Dagger", "type": ItemType.Dagger, "min_stat": 20, "max_stat": 70, "chance": min(0.005, 0.001 + level_bonus)},
                            {"name": "Glacial Axe", "type": ItemType.Axe, "min_stat": 20, "max_stat": 70, "chance": min(0.005, 0.001 + level_bonus)},
                            {"name": "Frozen Spear", "type": ItemType.Spear, "min_stat": 20, "max_stat": 70, "chance": min(0.005, 0.001 + level_bonus)},
                            {"name": "Permafrost Hammer", "type": ItemType.Hammer, "min_stat": 20, "max_stat": 70, "chance": min(0.005, 0.001 + level_bonus)},
                            {"name": "Crystal Wand", "type": ItemType.Wand, "min_stat": 20, "max_stat": 70, "chance": min(0.005, 0.001 + level_bonus)},
                            {"name": "Arctic Shield", "type": ItemType.Shield, "min_stat": 20, "max_stat": 70, "chance": min(0.005, 0.001 + level_bonus)},
                            
                            # 2-handed weapons (100-200 stats) - 0.5% chance each + level bonus (max 2.5% total)
                            {"name": "Dragon's Breath Bow", "type": ItemType.Bow, "min_stat": 40, "max_stat": 150, "chance": min(0.0025, 0.0005 + level_bonus)},
                            {"name": "Frost Giant's Scythe", "type": ItemType.Scythe, "min_stat": 40, "max_stat": 150, "chance": min(0.0025, 0.0005 + level_bonus)},
                            {"name": "Absolute Zero Mace", "type": ItemType.Mace, "min_stat": 40, "max_stat": 150, "chance": min(0.0025, 0.0005 + level_bonus)},
                        ]
                        
                        # Calculate total drop chance for display
                        total_chance_1h = min(0.05, 0.01 + level_bonus) * 7
                        total_chance_2h = min(0.025, 0.005 + level_bonus) * 3
                        total_chance = total_chance_1h + total_chance_2h
                        try:
                        # Roll for each weapon type
                            for weapon in ice_dragon_weapons:
                                if random.random() < weapon["chance"]:
                                    try:
                                        # Player won this weapon!
                                        stat = random.randint(weapon["min_stat"], weapon["max_stat"])
                                        hand = weapon["type"].get_hand().value
                                        
                                        # Create the weapon
                                        item = await self.bot.create_item(
                                            name=weapon["name"],
                                            value=10000,  # Value based on stat
                                            type_=weapon["type"].value,
                                            damage=stat if weapon["type"] != ItemType.Shield else 0,
                                            armor=stat if weapon["type"] == ItemType.Shield else 0,
                                            hand=hand,
                                            owner=member,
                                            element="Water",  # Ice dragon weapons are Water element
                                            conn=conn
                                        )
                                        
                                        # Add to weapon rewards text with rarity indicator
                                        weapon_type_display = "2H" if hand == "both" else "1H"
                                        rarity_emoji = "🌟" if hand == "both" else "⭐"  # 2H weapons are rarer
                                        weapon_rewards_text += f"{rarity_emoji} **{member.mention}** found **{weapon['name']}** ({weapon_type_display}) with {stat} stats!\n"
                                    except Exception as e:
                                        # Log error but continue with other rewards
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
                level_bonus = min(0.08, (old_level - 1) * 0.003)
                base_chance_1h = min(0.09, 0.01 + level_bonus)
                base_chance_2h = min(0.045, 0.005 + level_bonus)
                total_chance = base_chance_1h * 7 + base_chance_2h * 3
                embed.add_field(
                    name="❄️ Ice Dragon Loot",
                    value=f"No legendary weapons were found this time. Keep challenging the dragon for a chance at rare ice-themed weapons!\n\n**Drop Rates:**\n• 1H Weapons: {base_chance_1h:.1%} each (7 types, 90-100 stats)\n• 2H Weapons: {base_chance_2h:.1%} each (3 types, 100-200 stats)",
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
=======
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
        if ctx.invoked_subcommand is None:
            await self._show_dragon_status(ctx)
    
    async def _show_dragon_status(self, ctx):
        """Show the current status of the Ice Dragon Challenge"""
        # Get current dragon stats
        dragon_stats = await self.battle_factory.dragon_ext.get_dragon_stats_from_database(self.bot)
        dragon_level = dragon_stats.get("level", 1)
        weekly_defeats = dragon_stats.get("weekly_defeats", 0)
        
        # Get dragon stage information
        stage = await self.battle_factory.dragon_ext.get_dragon_stage(dragon_level)
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
        # Check if the user is already in a party
        if any(view.is_complete is False and ctx.author in view.party_members 
               for view in self.dragon_party_views):
            return await ctx.send("You are already in a party formation!")
            
        # Create party formation view
        class DragonPartyView(discord.ui.View):
            def __init__(self, bot):
                super().__init__(timeout=60)  # Full 60-second timeout
                self.bot = bot
                self.party_members = [ctx.author]  # Author automatically joins
                self.is_complete = False
                self._warning_task = None
                self._warning_sent = False
                self.message = None  # Will be set after view is sent
                self.ctx = ctx  # Store context for sending warning message
                
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
                if interaction.user != ctx.author:
                    return await interaction.response.send_message("Only the party leader can start the challenge!", ephemeral=True)
                    
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
                await asyncio.sleep(50)
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
                    await self._handle_dragon_victory(ctx, view.party_members)
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
    
    async def _handle_dragon_victory(self, ctx, party_members):
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
        try:
            async with self.bot.pool.acquire() as conn:
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
                        if current_level != new_level:
                            await self.bot.process_levelup(ctx, new_level, current_level)
                        
                        # Record in reward text
                        reward_text += f"• {member.mention}: {member_money} 💰, {member_xp} XP\n"
                        
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
            
            await ctx.send(embed=embed)
        except Exception:
            # Try a simple text message as fallback
            await ctx.send("Victory! The dragon has been defeated and rewards have been distributed.")
            pass

    
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
                # Small XP consolation
                consolation_xp = 50 * dragon_level
                
                await conn.execute(
                    'UPDATE profile SET "xp"="xp"+$1 WHERE "user"=$2;',
                    consolation_xp, member.id
                )
        
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
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
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
                    if member.id == 295173706496475136:
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
            
    @couples_battletower.command(name="start")
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
<<<<<<< HEAD
    await bot.add_cog(BattleSettings(bot))
    
    battles = Battles(bot)
    await battles.battle_factory.initialize()
    await bot.add_cog(battles)
=======
    battles = Battles(bot)
    await battles.battle_factory.initialize()
    await bot.add_cog(battles)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
