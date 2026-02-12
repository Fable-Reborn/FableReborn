import datetime
from operator import truediv
import discord
from discord.ext import commands
from discord.ui import Button, View
import asyncio
from typing import Optional, List, Dict, Tuple, Union
from discord import ButtonStyle, SelectOption, ui
from discord.ui import Button, View, Select
import firebase_admin
from firebase_admin import credentials, storage
import random
import json
import aiohttp
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils.checks import has_char, is_gm, is_patreon
# New imports for OpenAI integration
import os
import base64
import tempfile
from io import BytesIO
import pathlib
from openai import OpenAI
from PIL import Image
import secrets

# Constants for auto splice persistence
AUTO_SPLICE_SAVE_FILE = "auto_splice_saves.json"


class AutoSpliceReview(View):
    """Interactive review system for auto splice"""
    def __init__(self, ctx, pets, openai_client, timeout=300, save_id=None):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.pets = pets
        self.openai_client = openai_client
        self.message = None
        self.confirmed = False
        self.save_id = save_id
        
        # Add edit buttons for each pet (limited by Discord's component limit)
        for i in range(min(len(pets), 10)):
            button = Button(
                label=f"Edit {i+1}", 
                style=ButtonStyle.secondary, 
                emoji="✏️",
                custom_id=f"edit_{i}"
            )
            button.callback = self.create_edit_callback(i)
            self.add_item(button)
    
    async def on_timeout(self):
        """Save data when timeout occurs"""
        if not self.confirmed and self.pets:
            await self.save_auto_splice_data()
            try:
                await self.message.edit(content="⏰ **Auto splice timed out!** Data has been saved. Use `$resume_auto_splice` to continue later.", embed=None, view=None)
            except:
                pass
    
    async def save_auto_splice_data(self):
        """Save auto splice data to JSON file"""
        if not self.save_id:
            self.save_id = f"auto_splice_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"
        
        save_data = {
            "save_id": self.save_id,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "ctx_author_id": self.ctx.author.id,
            "ctx_channel_id": self.ctx.channel.id,
            "pets": self.pets
        }
        
        # Load existing saves
        saves = {}
        if os.path.exists(AUTO_SPLICE_SAVE_FILE):
            try:
                with open(AUTO_SPLICE_SAVE_FILE, 'r') as f:
                    saves = json.load(f)
            except:
                saves = {}
        
        # Add new save
        saves[self.save_id] = save_data
        
        # Write back to file
        try:
            with open(AUTO_SPLICE_SAVE_FILE, 'w') as f:
                json.dump(saves, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving auto splice data: {e}")
    
    async def remove_save_data(self):
        """Remove save data after successful completion"""
        if self.save_id and os.path.exists(AUTO_SPLICE_SAVE_FILE):
            try:
                with open(AUTO_SPLICE_SAVE_FILE, 'r') as f:
                    saves = json.load(f)
                
                if self.save_id in saves:
                    del saves[self.save_id]
                    
                    with open(AUTO_SPLICE_SAVE_FILE, 'w') as f:
                        json.dump(saves, f, indent=2, default=str)
            except Exception as e:
                print(f"Error removing save data: {e}")
    
    def create_edit_callback(self, index):
        async def edit_callback(interaction):
            await self.edit_pet(interaction, index)
        return edit_callback
    
    async def get_review_embed(self):
        embed = discord.Embed(
            title="🧬 Auto Splice Review",
            description=f"Review your {len(self.pets)} spliced pets below. You have 5 minutes to confirm or edit.",
            color=0x9C44DC
        )
        
        for i, pet in enumerate(self.pets, 1):
            embed.add_field(
                name=f"{i}. {pet['name']}",
                value=(
                    f"**HP**: {pet['hp']} | **ATK**: {pet['attack']} | **DEF**: {pet['defense']}\n"
                    f"**Element**: {pet['element']}\n"
                    f"[🖼️ Image Link]({pet['url']})"
                ),
                inline=False
            )
        
        embed.set_footer(text="Use the buttons below to confirm or edit specific pets.")
        return embed
    
    @discord.ui.button(label="Confirm All", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Confirmed! Creating pets...", embed=None, view=None)
        self.confirmed = True
        # Remove save data since we're confirming
        await self.remove_save_data()
        self.stop()
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Auto splice cancelled.", embed=None, view=None)
        self.pets.clear()  # Signal to cancel
        self.stop()
    
    async def edit_pet(self, interaction: discord.Interaction, index: int):
        pet = self.pets[index]
        
        # Create edit submenu
        edit_view = PetEditView(self.ctx, pet, self, index, self.openai_client)
        
        embed = discord.Embed(
            title=f"Edit Pet #{index + 1}: {pet['name']}",
            description="Choose what to edit:",
            color=0x9C44DC
        )
        embed.add_field(
            name="Current Details",
            value=(
                f"**Name**: {pet['name']}\n"
                f"**HP**: {pet['hp']} | **ATK**: {pet['attack']} | **DEF**: {pet['defense']}\n"
                f"**Element**: {pet['element']}"
            ),
            inline=False
        )
        embed.set_image(url=pet['url'])
        
        await interaction.response.edit_message(embed=embed, view=edit_view)

class PetEditView(View):
    """Edit submenu for individual pets"""
    def __init__(self, ctx, pet, parent_view, pet_index, openai_client, timeout=300):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.pet = pet
        self.parent_view = parent_view
        self.pet_index = pet_index
        self.openai_client = openai_client
    
    @discord.ui.button(label="1. Edit Name", style=discord.ButtonStyle.primary, emoji="📝")
    async def edit_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Please type the new name in chat, or type 'generate' to get AI suggestions:",
            embed=None,
            view=None
        )
        
        def check(m):
            return m.author.id == self.ctx.author.id and m.channel.id == self.ctx.channel.id
        
        try:
            msg = await self.ctx.bot.wait_for('message', check=check, timeout=60)
            
            if msg.content.lower() == 'generate':
                # Generate name suggestions using vision
                await self.ctx.send("🤖 Generating name suggestions...")
                
                base_prompt = (
                    "Look at this picture and propose exactly five unique "
                    "names related to its features (max two words, do not place numbers next to each name ex. 1. <name> 2. <name> etc. 1 name per line)."
                )

                vision_msg = [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": base_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": self.pet["url"], "detail": "auto"},
                        },
                    ],
                }]

                resp = await asyncio.to_thread(
                    self.openai_client.chat.completions.create,
                    model="gpt-4o",
                    messages=vision_msg,
                )
                raw_text = resp.choices[0].message.content

                names = [
                    x.strip(" .-")
                    for x in raw_text.replace("\r", "").split("\n")
                    if x.strip()
                ][:5]
                
                if names:
                    names_text = "\n".join(f'`{n + 1}` {nm}' for n, nm in enumerate(names))
                    names_text += "\n\nChoose a number (1-5) or type a custom name:"
                    
                    await self.ctx.send(names_text)
                    
                    choice_msg = await self.ctx.bot.wait_for('message', check=check, timeout=60)
                    choice = choice_msg.content.strip()
                    
                    if choice.isdigit() and 1 <= int(choice) <= len(names):
                        self.pet['name'] = names[int(choice) - 1]
                    else:
                        self.pet['name'] = choice
                else:
                    await self.ctx.send("Failed to generate names. Please type a custom name:")
                    custom_msg = await self.ctx.bot.wait_for('message', check=check, timeout=60)
                    self.pet['name'] = custom_msg.content.strip()
            else:
                self.pet['name'] = msg.content.strip()
            
            await self.ctx.send(f"✅ Name updated to: **{self.pet['name']}**")
            
        except asyncio.TimeoutError:
            await self.ctx.send("⏰ Timed out. Name not changed.")
        
        # Return to review
        embed = await self.parent_view.get_review_embed()
        await self.ctx.send(embed=embed, view=self.parent_view)
    
    @discord.ui.button(label="2. Edit Stats", style=discord.ButtonStyle.primary, emoji="⚔️")
    async def edit_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=f"Enter new stats for **{self.pet['name']}** in the format:\n`hp,attack,defense,element`\n\nCurrent: {self.pet['hp']},{self.pet['attack']},{self.pet['defense']},{self.pet['element']}",
            embed=None,
            view=None
        )
        
        def check(m):
            return m.author.id == self.ctx.author.id and m.channel.id == self.ctx.channel.id
        
        try:
            msg = await self.ctx.bot.wait_for('message', check=check, timeout=120)
            parts = msg.content.split(",")
            
            if len(parts) >= 3:
                self.pet['hp'] = int(parts[0].strip())
                self.pet['attack'] = int(parts[1].strip())
                self.pet['defense'] = int(parts[2].strip())
                if len(parts) >= 4:
                    self.pet['element'] = parts[3].strip().title()
                
                await self.ctx.send(f"✅ Stats updated for **{self.pet['name']}**!")
            else:
                await self.ctx.send("❌ Invalid format. Stats not changed.")
                
        except (asyncio.TimeoutError, ValueError):
            await self.ctx.send("⏰ Timed out or invalid input. Stats not changed.")
        
        # Return to review
        embed = await self.parent_view.get_review_embed()
        await self.ctx.send(embed=embed, view=self.parent_view)
    
    @discord.ui.button(label="3. Edit Image", style=discord.ButtonStyle.primary, emoji="🖼️")
    async def edit_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Please upload a new image or paste an image URL:",
            embed=None,
            view=None
        )
        
        def check(m):
            return m.author.id == self.ctx.author.id and m.channel.id == self.ctx.channel.id
        
        try:
            msg = await self.ctx.bot.wait_for('message', check=check, timeout=120)
            
            if msg.attachments:
                # Handle file upload
                attachment = msg.attachments[0]
                if attachment.height:  # Verify it's an image
                    self.pet['url'] = attachment.url
                    await self.ctx.send(f"✅ Image updated for **{self.pet['name']}**!")
                else:
                    await self.ctx.send("❌ Invalid image file.")
            else:
                # Handle URL
                self.pet['url'] = msg.content.strip()
                await self.ctx.send(f"✅ Image URL updated for **{self.pet['name']}**!")
                
        except asyncio.TimeoutError:
            await self.ctx.send("⏰ Timed out. Image not changed.")
        
        # Return to review
        embed = await self.parent_view.get_review_embed()
        await self.ctx.send(embed=embed, view=self.parent_view)
    
    @discord.ui.button(label="Back to Review", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def back_to_review(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.parent_view.get_review_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class SpliceRequestPaginator(View):
    """A paginator for viewing pending splice requests"""
    def __init__(self, ctx, splices, per_page=8):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.splices = splices
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = (len(splices) + per_page - 1) // per_page
        self.message = None
        self.current_time = datetime.datetime.now(datetime.timezone.utc)
        
        # Add navigation buttons
        self.add_buttons()
    
    def add_buttons(self):
        """Add navigation buttons to the view"""
        # Previous button
        prev_button = Button(style=ButtonStyle.primary, emoji="⬅️", disabled=self.current_page == 0)
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        # Next button
        next_button = Button(style=ButtonStyle.primary, emoji="➡️", disabled=self.current_page == self.total_pages - 1)
        next_button.callback = self.next_page
        self.add_item(next_button)
        
        # Close button
        close_button = Button(style=ButtonStyle.danger, emoji="❌")
        close_button.callback = self.close_view
        self.add_item(close_button)
    
    def get_current_page_embed(self):
        """Generate the embed for the current page"""
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        current_splices = self.splices[start_idx:end_idx]
        
        embed = discord.Embed(
            title="🧬 Pending Splice Requests",
            description=(
                f"Page {self.current_page + 1}/{self.total_pages} • "
                f"{len(self.splices)} total request{'s' if len(self.splices) != 1 else ''}"
            ),
            color=0x9C44DC
        )
        
        for splice in current_splices:
            user = self.ctx.bot.get_user(splice["user_id"]) or f"Unknown User ({splice['user_id']})"
            
            # Handle time difference
            created_at = splice["created_at"]
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=datetime.timezone.utc)
                
            time_diff = self.current_time - created_at
            hours_ago = time_diff.total_seconds() / 3600
            
            if hours_ago < 1:
                time_str = f"{int(hours_ago * 60)}m ago"
            elif hours_ago < 24:
                time_str = f"{int(hours_ago)}h ago"
            else:
                days = int(hours_ago / 24)
                time_str = f"{days}d ago"
            
            embed.add_field(
                name=f"#{splice['id']} • {user} • {time_str}",
                value=(
                    f"🐾 **{splice['pet1_name']}** (`{splice['pet1_default']}`) + "
                    f"**{splice['pet2_name']}** (`{splice['pet2_default']}`)\n"
                    f"🔗 [Pet 1]({splice['pet1_url']}) • [Pet 2]({splice['pet2_url']})"
                ),
                inline=False
            )
        
        # Add a field with all suggested names for the current page if they exist
        suggested_names = [
            s['temp_name']
            for s in current_splices 
            if s.get('temp_name')
        ]
        
        if suggested_names:
            embed.add_field(
                name="Suggested Names",
                value=", ".join(suggested_names),
                inline=False
            )
        
        return embed
    
    async def update_message(self):
        """Update the message with current page"""
        for child in self.children:
            if child.emoji == "⬅️":
                child.disabled = self.current_page == 0
            elif child.emoji == "➡️":
                child.disabled = self.current_page == self.total_pages - 1
        
        await self.message.edit(embed=self.get_current_page_embed(), view=self)
    
    async def previous_page(self, interaction):
        """Go to the previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message()
        await interaction.response.defer()
    
    async def next_page(self, interaction):
        """Go to the next page"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_message()
        await interaction.response.defer()
    
    async def close_view(self, interaction):
        """Close the paginator"""
        await interaction.message.delete()
        self.stop()
    
    async def start(self):
        """Start the paginator"""
        self.message = await self.ctx.send(embed=self.get_current_page_embed(), view=self)
        return self.message




class ProcessSplice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    async def get_player_data(self, user_id):
        """Get player's quest progress and character data"""
        async with self.bot.pool.acquire() as conn:
            # Check if player has started the quest
            quest_data = await conn.fetchrow(
                "SELECT * FROM splicing_quest WHERE user_id = $1", user_id)
            
            character = await conn.fetchrow(
                "SELECT name, god, money FROM profile WHERE profile.user = $1", user_id)
            
            if not character:
                return None
                
            if not quest_data:
                return {
                    "quest_started": False,
                    "name": character["name"],
                    "god": character["god"],
                    "money": character["money"],
                    "shards": 0,
                    "primer": False,
                    "forge_built": False
                }
            
            return {
                "quest_started": True,
                "name": character["name"],
                "god": character["god"],
                "money": character["money"],
                "shards": quest_data["shards_collected"],
                "primer": quest_data["primer_found"],
                "forge_built": quest_data["crucible_built"]
            }

    async def suggest_element(self, element1, element2):
        """Suggest an element for the spliced pet based on parent elements"""
        # Normalize elements to consistent case
        e1 = element1.title() if element1 else "Unknown"
        e2 = element2.title() if element2 else "Unknown"
        
        # List of standard elements
        standard_elements = [
            "Fire", "Water", "Wind", "Earth", "Nature", 
            "Electric", "Corrupted", "Dark", "Light", "Ice"
        ]
        
        # If both parents have valid elements, just pick one of them
        if e1 != "Unknown" and e2 != "Unknown":
            # If both have the same element, always keep it
            if e1 == e2:
                return e1
            # Otherwise randomly choose one of the parent elements
            return random.choice([e1, e2])
        
        # If one parent has an unknown element, use the known one
        if e1 != "Unknown":
            return e1
        if e2 != "Unknown":
            return e2
        
        # If both are unknown, pick a random standard element
        return random.choice(standard_elements)
    
    async def allocate_iv_points(self, total_points):
        """Distribute IV points between HP, Attack, and Defense"""
        # Get three random values that sum to total_points
        r1 = random.random()
        r2 = random.random()
        r3 = random.random()
        
        # Normalize so they sum to 1
        total = r1 + r2 + r3
        if total == 0:  # Avoid division by zero
            r1, r2, r3 = 0.33, 0.33, 0.34
        else:
            r1, r2, r3 = r1/total, r2/total, r3/total
        
        # Distribute points according to normalized values
        hp_iv = int(r1 * total_points)
        attack_iv = int(r2 * total_points)
        defense_iv = int(r3 * total_points)
        
        # Ensure all points are allocated by assigning any remainder to HP
        remainder = total_points - (hp_iv + attack_iv + defense_iv)
        hp_iv += remainder
        
        return hp_iv, attack_iv, defense_iv

    def _load_default_pve_monster_names(self):
        """Load base monster names from monsters.json used by PvE."""
        with open("monsters.json", "r", encoding="utf-8") as f:
            monsters_data = json.load(f)

        base_names = set()
        if isinstance(monsters_data, dict):
            for monster_list in monsters_data.values():
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

    def _build_splice_generation_map(self, base_monster_names, completed_rows):
        """
        Build a generation map where:
        - Base PvE monsters are treated as generation -1 parents.
        - Child generation = max(parent_generations) + 1.
        """
        generation_by_name = {name: -1 for name in base_monster_names}
        max_passes = max(1, len(completed_rows) + 1)

        for _ in range(max_passes):
            changed = False
            for row in completed_rows:
                pet1_default = row["pet1_default"]
                pet2_default = row["pet2_default"]
                result_name = row["result_name"]

                if not pet1_default or not pet2_default or not result_name:
                    continue

                if not isinstance(pet1_default, str) or not isinstance(pet2_default, str) or not isinstance(result_name, str):
                    continue

                pet1_default = pet1_default.strip()
                pet2_default = pet2_default.strip()
                result_name = result_name.strip()
                if not pet1_default or not pet2_default or not result_name:
                    continue

                parent1_gen = generation_by_name.get(pet1_default)
                parent2_gen = generation_by_name.get(pet2_default)
                if parent1_gen is None or parent2_gen is None:
                    continue

                child_gen = max(parent1_gen, parent2_gen) + 1
                existing = generation_by_name.get(result_name)

                # Keep canonical base-monster mapping untouched.
                if existing == -1:
                    continue

                if existing is None or child_gen < existing:
                    generation_by_name[result_name] = child_gen
                    changed = True

            if not changed:
                break

        return generation_by_name

    @is_gm()
    @commands.command(
        name="splicegenstats",
        aliases=["splicegen", "splicegens", "splicegencount"],
        hidden=True,
    )
    async def splice_generation_stats(self, ctx: commands.Context):
        """
        Count splice generation combinations.
        Gen 0: default PvE + default PvE
        Gen 1: any combo whose parents resolve to generation 1
        """
        try:
            base_monster_names = self._load_default_pve_monster_names()
        except FileNotFoundError:
            return await ctx.send("Could not read `monsters.json` to determine default PvE monsters.")
        except Exception as e:
            return await ctx.send(f"Failed to load base monster data: {e}")

        if not base_monster_names:
            return await ctx.send("No base PvE monster names were found in `monsters.json`.")

        try:
            async with self.bot.pool.acquire() as conn:
                completed_rows = await conn.fetch(
                    """
                    SELECT id, pet1_default, pet2_default, result_name, created_at
                    FROM splice_combinations
                    ORDER BY created_at ASC, id ASC
                    """
                )
                pending_rows = await conn.fetch(
                    """
                    SELECT id, pet1_default, pet2_default, created_at
                    FROM splice_requests
                    WHERE status = 'pending'
                    ORDER BY created_at ASC, id ASC
                    """
                )
        except Exception as e:
            return await ctx.send(f"Failed to query splice tables: {e}")

        generation_by_name = self._build_splice_generation_map(base_monster_names, completed_rows)

        def classify_generation(parent1_name, parent2_name):
            if not isinstance(parent1_name, str) or not isinstance(parent2_name, str):
                return None, None, None

            p1 = parent1_name.strip()
            p2 = parent2_name.strip()
            if not p1 or not p2:
                return None, None, None

            p1_gen = generation_by_name.get(p1)
            p2_gen = generation_by_name.get(p2)
            if p1_gen is None or p2_gen is None:
                return None, p1_gen, p2_gen

            return max(p1_gen, p2_gen) + 1, p1_gen, p2_gen

        def add_gen_count(gen_counts, generation):
            gen_counts[generation] = gen_counts.get(generation, 0) + 1

        completed_gen_counts = {}
        pending_gen_counts = {}
        completed_unresolved = 0
        pending_unresolved = 0

        for row in completed_rows:
            row_gen, _, _ = classify_generation(row["pet1_default"], row["pet2_default"])
            if row_gen is None:
                completed_unresolved += 1
                continue
            add_gen_count(completed_gen_counts, row_gen)

        for row in pending_rows:
            row_gen, _, _ = classify_generation(row["pet1_default"], row["pet2_default"])
            if row_gen is None:
                pending_unresolved += 1
                continue
            add_gen_count(pending_gen_counts, row_gen)

        all_gen_counts = dict(completed_gen_counts)
        for gen, count in pending_gen_counts.items():
            all_gen_counts[gen] = all_gen_counts.get(gen, 0) + count

        completed_total_resolved = sum(completed_gen_counts.values())
        pending_total_resolved = sum(pending_gen_counts.values())
        all_total_resolved = completed_total_resolved + pending_total_resolved
        all_total_unresolved = completed_unresolved + pending_unresolved

        beyond_30_count = sum(count for gen, count in all_gen_counts.items() if gen > 30)
        furthest_generation = max(all_gen_counts.keys()) if all_gen_counts else None
        furthest_generation_count = (
            all_gen_counts.get(furthest_generation, 0) if furthest_generation is not None else 0
        )

        generation_lines = []
        for gen in range(0, 31):
            generation_lines.append(f"Gen {gen}: **{all_gen_counts.get(gen, 0)}**")
        generation_text = "\n".join(generation_lines)

        embed = discord.Embed(
            title="🧬 Splice Generation Stats",
            description="Counts based on default PvE monsters from `monsters.json`.",
            color=discord.Color.teal(),
        )
        embed.add_field(
            name="Generation Counts 0-30 (`completed + pending`)",
            value=generation_text,
            inline=False,
        )
        embed.add_field(
            name="Totals",
            value=(
                f"Completed resolved: **{completed_total_resolved}**\n"
                f"Pending resolved: **{pending_total_resolved}**\n"
                f"All resolved: **{all_total_resolved}**\n"
                f"All unresolved: **{all_total_unresolved}**\n"
                f"Beyond Gen 30: **{beyond_30_count}**\n"
                f"Furthest generation: **Gen {furthest_generation if furthest_generation is not None else 'N/A'}** "
                f"(**{furthest_generation_count}** combo(s))"
            ),
            inline=False,
        )
        embed.set_footer(
            text=(
                f"Base monsters: {len(base_monster_names)} | "
                f"Completed rows: {len(completed_rows)} | Pending rows: {len(pending_rows)}"
            )
        )
        await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────
    #  AUTO S P L I C E   (automated version of batch splice)
    # ──────────────────────────────────────────────────────────────────────
    @is_gm()
    @commands.command(hidden=True)
    async def auto_splice(self, ctx: commands.Context, count: int = 5):
        """Automated batch splice with default settings and interactive review"""
        
        import aiohttp, asyncio, base64, datetime, io, json, os, random, traceback, secrets
        from firebase_admin import credentials, storage
        import firebase_admin
        from openai import OpenAI

        MAX_BATCH = 21
        DEFAULT_IMG = "https://i.imgur.com/nJYMPOQ.png"
        BUCKET = "fablerpg-f74c2.appspot.com"
        PIXELCUT_URL = "https://api.developer.pixelcut.ai/v1/remove-background"
        PIXELCUT_KEY = os.getenv("PIXELCUT_KEY") or ""

        # ──────────────────────────────────────────────────────────
        # helper wrappers
        # ──────────────────────────────────────────────────────────
        async def download_bytes(url: str) -> bytes:
            async with aiohttp.ClientSession() as s:
                async with s.get(url) as r:
                    return await r.read()

        async def has_transparency(image_bytes: bytes) -> bool:
            """Check if image has transparency"""
            try:
                image = Image.open(io.BytesIO(image_bytes))
                
                # Check if image has alpha channel
                if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                    # Convert to RGBA if not already
                    if image.mode != 'RGBA':
                        image = image.convert('RGBA')
                    
                    # Check if any pixels are actually transparent
                    for pixel in image.getdata():
                        if len(pixel) == 4 and pixel[3] < 255:  # Alpha channel exists and is not fully opaque
                            return True
                
                return False
            except Exception:
                return False  # If we can't determine, assume no transparency

        async def remove_background(
                ctx: commands.Context,
                *,
                img_url: str | None = None,
                img_bytes: bytes | None = None,
                filename: str = "temp.png",
        ) -> bytes:
            """Remove background with Pixelcut"""
            if not img_url and not img_bytes:
                raise ValueError("Need either img_url or img_bytes")

            # 1. make sure we end up with a publicly reachable URL
            temp_msg = None
            if not img_url:
                temp_msg = await ctx.channel.send(
                    file=discord.File(io.BytesIO(img_bytes), filename)
                )
                img_url = temp_msg.attachments[0].url

            # 2. call Pixelcut with the URL
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-API-KEY": PIXELCUT_KEY,
            }
            payload = json.dumps({"image_url": img_url, "format": "png"})

            async with aiohttp.ClientSession() as s:
                async with s.post(PIXELCUT_URL, headers=headers, data=payload) as r:
                    if r.status != 200:
                        raise RuntimeError(f"PixelCut status {r.status}")
                    data = await r.json()

                async with s.get(data["result_url"]) as r2:
                    result_bytes = await r2.read()

            # 3. clean up the temp message if we created one
            if temp_msg:
                try:
                    await temp_msg.delete()
                except Exception:
                    pass

            return result_bytes

        def get_firebase_bucket():
            """Return a google.cloud.storage.bucket.Bucket object"""
            if not firebase_admin._apps:
                firebase_admin.initialize_app(credentials.Certificate("acc.json"))
            return storage.bucket(BUCKET)

        async def firebase_upload(data: bytes, filename: str) -> str:
            bucket = get_firebase_bucket()
            blob = bucket.blob(filename)
            blob.upload_from_string(data)
            blob.make_public()
            return blob.public_url

        # Helper to generate a unique filename
        def unique_filename(base: str, ext: str = ".png") -> str:
            ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
            rand = secrets.token_hex(4)
            return f"{base}_{ts}_{rand}{ext}"

        # ──────────────────────────────────────────────────────────
        # 0) limit batch + create OpenAI client
        # ──────────────────────────────────────────────────────────
        if count > MAX_BATCH:
            count = MAX_BATCH
            await ctx.send(f"Batch size limited to {MAX_BATCH}")

        try:
            openai_client = OpenAI(api_key="")
            await ctx.send("🤖 **AUTO SPLICE INITIATED**\n✅ OpenAI client ready – processing with default settings...")
        except Exception as e:
            return await ctx.send(f"⚠️ OpenAI init failed ({e}) – cannot proceed with auto splice.")

        # ──────────────────────────────────────────────────────────
        # 1) pull pending requests
        # ──────────────────────────────────────────────────────────
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT  id, user_id, pet1_name, pet2_name,
                        pet1_default, pet2_default, created_at,
                        pet1_url, pet2_url,
                        pet1_hp, pet1_attack, pet1_defense,
                        pet2_hp, pet2_attack, pet2_defense,
                        pet1_element, pet2_element, temp_name
                FROM    splice_requests
                WHERE   status='pending'
                ORDER BY created_at
                LIMIT   $1
                """,
                count,
            )

        if not rows:
            return await ctx.send("No pending splice requests.")

        # ──────────────────────────────────────────────────────────
        # 2) build working objects
        # ──────────────────────────────────────────────────────────
        pets = []
        for r in rows:
            pets.append(
                dict(
                    splice_id=r["id"],
                    user_id=r["user_id"],
                    name=r["temp_name"],
                    pet1_default=r["pet1_default"],
                    pet2_default=r["pet2_default"],
                    pet1_hp=r["pet1_hp"],
                    pet1_attack=r["pet1_attack"],
                    pet1_defense=r["pet1_defense"],
                    pet2_hp=r["pet2_hp"],
                    pet2_attack=r["pet2_attack"],
                    pet2_defense=r["pet2_defense"],
                    pet1_element=r["pet1_element"],
                    pet2_element=r["pet2_element"],
                    pet1_url=r["pet1_url"],
                    pet2_url=r["pet2_url"],
                    url=None,
                    hp=None,
                    attack=None,
                    defense=None,
                    element=None,
                    is_destabilised="[DESTABILISED]" in r["temp_name"],
                    divine_suggestion=0,
                    forge_suggestion=0,
                )
            )
        
        # Check for splice final potion effect for each user
        user_splice_final_effects = {}
        for pet in pets:
            if pet['user_id'] not in user_splice_final_effects:
                # Check if user has splice final potion active
                async with self.bot.pool.acquire() as conn:
                    has_effect = await conn.fetchval(
                        'SELECT splice_final_active FROM profile WHERE "user" = $1;',
                        pet['user_id']
                    )
                    user_splice_final_effects[pet['user_id']] = has_effect or False

        # ──────────────────────────────────────────────────────────
        # 3) STEP-1 AUTO IMAGE GENERATION
        # ──────────────────────────────────────────────────────────
        await ctx.send("🎨 **AUTO-GENERATING IMAGES** (using gpt-image-1 with enhanced creative prompts...)")
        
        # Define creative elements for dynamic prompt generation
        creature_types = ['mythical', 'elemental', 'celestial', 'abyssal', 'arcane', 'primordial', 'ethereal', 'fey',
            'crystalline', 'fungal', 'biomechanical', 'astral', 'geomantic', 'phantasmal', 'insectoid',
            'draconic', 'shadow', 'prismatic', 'eldritch', 'botanical', 'amorphous', 'aquatic', 'volcanic'
        ]
        art_styles = ['vibrant', 'detailed', 'mystical', 'elegant', 'dynamic', 'striking',
            'surreal', 'luminous', 'bioluminescent', 'fractal', 'iridescent', 'ornate',
            'ink-style', 'glyph-marked', 'runic', 'neon-edged', 'watercolor', 'geometric'
        ]
        special_traits = ['glowing', 'shimmering', 'spectral', 'crystalline', 'shadowy', 'radiant', 'phantasmal',
            'kaleidoscopic', 'reality-defying', 'dimension-shifting', 'void-touched', 'time-warped',
            'dream-woven', 'soul-bound', 'elder', 'mutated', 'phase-shifting', 'mana-infused'
        ]
        
        # Define anatomical features for uniqueness
        anatomical_features = [
            'segmented exoskeleton', 'multiple symmetrical eyes', 'bioluminescent patterns',
            'floating appendages', 'translucent membranes', 'spiraling horns', 'crystalline growths',
            'energy-channeling tendrils', 'armored scales', 'reality-fracturing limbs', 'hypnotic markings',
            'phase-shifting wings', 'smoke-emitting vents', 'liquid metal skin', 'floating energy cores',
            'rune-inscribed hide', 'geometric shell segments', 'prismatic feathers'
        ]
        
        # Define specific dos and don'ts
        dos_and_donts = [
            "DO: Create exactly ONE unified creature, not multiple separate entities.",
            "DO: Ensure the fusion appears genetically coherent, not a collage of parts.",
            "DO: Include unexpected anatomical features that neither parent possesses.",
            "DO: Give it asymmetrical or unusual anatomical proportions.",
            "DON'T: Show humanoid faces or human-like expressions.",
            "DON'T: Create a simple mashup of overlaid parts - truly integrate the elements.",
            "DON'T: Include backgrounds, environments, or other creatures.",
            "DON'T: Add weapons, clothing, or artificial accessories unless they're fused into anatomy."
        ]

        for idx, pet in enumerate(pets, 1):
            await ctx.send(f"🔄 Processing {idx}/{len(pets)}: {pet['name']}...")
            
            try:
                # Check if user has splice final potion effect
                has_splice_final_effect = user_splice_final_effects.get(pet['user_id'], False)
                
                # Decide if this is a special type of splice based on probabilities
                if has_splice_final_effect:
                    # 25% chance for FINAL with splice final potion
                    is_final = random.random() < 0.15
                else:
                    # Normal 3% chance for FINAL
                    is_final = random.random() < 0.03
                
                is_special = not is_final and random.random() < 0.07  # 7% chance
                is_unstable = not (is_final or is_special) and random.random() < 0.06  # 6% chance
                
                # Check if any parent has [UNSTABLE] in the name
                has_unstable_parent = ('[UNSTABLE]' in pet['pet1_default'].upper() or 
                                      '[UNSTABLE]' in pet['pet2_default'].upper())
                    
                # 40% chance of DESTABILIZED if parent is unstable (overrides other types)
                is_destabilized = has_unstable_parent and random.random() < 0.4
                
                # Store the tag in the pet object
                if is_destabilized:
                    pet['splice_type'] = 'DESTABILIZED'
                    pet['is_destabilised'] = True
                elif is_final:
                    pet['splice_type'] = 'FINAL'
                elif is_special:
                    pet['splice_type'] = 'SPECIAL'
                elif is_unstable:
                    pet['splice_type'] = 'UNSTABLE'
                else:
                    pet['splice_type'] = 'NORMAL'
                
                # Clear splice final effect if user had it active (regardless of outcome)
                if has_splice_final_effect:
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            'UPDATE profile SET splice_final_active = FALSE WHERE "user" = $1;',
                            pet['user_id']
                        )
                    # Update the local cache
                    user_splice_final_effects[pet['user_id']] = False
                    
                    # Notify if the effect was successful
                    if is_final:
                        await ctx.send(f"🔮 **Splice Final Potion activated!** {pet['name']} became a [FINAL] form!")
                    else:
                        await ctx.send(f"🔮 **Splice Final Potion used** - The effect has expired.")
                
                # Get random unique elements for this specific creature
                creature_type = random.choice(creature_types)
                art_style = random.choice(art_styles)
                special_trait = random.choice(special_traits)
                anatomical_feature = random.choice(anatomical_features)
                
                # Select 3 random dos/don'ts
                selected_guidelines = random.sample(dos_and_donts, 3)
                
                # Generate a unique random seed for this creature to ensure distinctiveness
                unique_seed = random.randint(10000, 99999)
                
                # Base prompt with highly specific creativity elements
                prompt = (
                    f"Create a single, unified {art_style} {creature_type} hybrid creature by intricately fusing two monsters. "
                    f"This is creature design #{unique_seed}. "
                    f"Include a distinctive {anatomical_feature} as its most striking feature. "
                    "Artfully integrate the most distinctive anatomical elements, textures, and coloration from both parent creatures. "
                    "The fusion MUST appear as a single, cohesive, evolved being - NOT a simple combination or mashup. "
                    "Show the ENTIRE creature in a dynamic pose that highlights its unique anatomy. "
                    f"The result should exude a {special_trait}, otherworldly quality. "
                    "Create on pure white/transparent background with NO environment elements. "
                    f"Guidelines: {selected_guidelines[0]} {selected_guidelines[1]} {selected_guidelines[2]}"
                )
                
                # Enhance prompt based on splice type
                if is_final:
                    prompt += (
                        "This is a [FINAL] tier creature of immense power. Give it majestic, god-like qualities "
                        "with impossible anatomical features that transcend reality. Add cosmic elements, "
                        "multiple energy sources, and reality-bending visual effects integrated into its form."
                    )
                    # Add the tag to the name (at end)
                    pet['name'] = f"{pet['name']} [FINAL]"
                elif is_special:
                    prompt += (
                        "This is a [SPECIAL] tier creature with extraordinary qualities. Give it unique, "
                        "unexpected anatomical features that surprise and delight. Include visual elements "
                        "that suggest magical abilities, ancient wisdom, or elemental mastery."
                    )
                    # Add the tag to the name (at end)
                    pet['name'] = f"{pet['name']} [SPECIAL]"
                elif is_unstable:
                    prompt += (
                        "This is an [UNSTABLE] tier creature with volatile energy. Include visual elements "
                        "of instability like asymmetry, shifting forms, energy leakage, or partial transparency. "
                        "Suggest power that is barely contained within its form."
                    )
                    # Add the tag to the name (at end)
                    pet['name'] = f"{pet['name']} [UNSTABLE]"
                elif is_destabilized:
                    prompt += (
                        "This is a [DESTABILIZED] creature that is breaking down at a molecular level. "
                        "Visualize this with fragmentation, particle effects, glitching anatomy, or partial dissolution. "
                        "It should appear weakened but still holding onto its essence."
                    )
                    # Add the tag to the name (at end)
                    pet['name'] = f"{pet['name']} [DESTABILISED]"
                
                # Download parent images
                p1_bytes = await download_bytes(pet["pet1_url"])
                p2_bytes = await download_bytes(pet["pet2_url"])
                p1_file = f"p1_{pet['splice_id']}.png"
                p2_file = f"p2_{pet['splice_id']}.png"
                
                with open(p1_file, "wb") as f:
                    f.write(p1_bytes)
                with open(p2_file, "wb") as f:
                    f.write(p2_bytes)

                # Generate with gpt-image-1
                def _edit():
                    return openai_client.images.edit(
                        model="gpt-image-1",
                        image=[open(p1_file, "rb"), open(p2_file, "rb")],
                        prompt=prompt,
                    )

                result = await asyncio.to_thread(_edit)
                img_b64 = result.data[0].b64_json
                gen_bytes = base64.b64decode(img_b64)

                # Check for transparency and remove background if needed
                if not "[SPECIAL]" in pet["name"].upper():
                    if not await has_transparency(gen_bytes):
                        try:
                            await ctx.send(f"🎭 Removing background for {pet['name']}...")
                            gen_bytes = await remove_background(ctx, img_bytes=gen_bytes, filename="ai.png")
                        except Exception as e:
                            await ctx.send(f"⚠️ Background removal failed: {e}")

                # Upload to Firebase
                pet["url"] = await firebase_upload(
                    gen_bytes, unique_filename(f"{ctx.author.id}_{pet['name']}_auto")
                )

                # Clean up temp files
                try:
                    os.remove(p1_file)
                    os.remove(p2_file)
                except Exception:
                    pass

            except Exception as e:
                await ctx.send(f"⚠️ Image generation failed for {pet['name']}: {e}")
                pet["url"] = DEFAULT_IMG

        # ──────────────────────────────────────────────────────────
        # 4) STEP-2 AUTO STAT GENERATION (with tag-based caps)
        # ──────────────────────────────────────────────────────────
        await ctx.send("⚔️ **AUTO-GENERATING STATS** (using tag-based caps for each splice type)...")

        for pet in pets:
            try:
                p1hp, p1atk, p1def = pet["pet1_hp"], pet["pet1_attack"], pet["pet1_defense"]
                p2hp, p2atk, p2def = pet["pet2_hp"], pet["pet2_attack"], pet["pet2_defense"]
                
                # Set stat cap based on splice type
                if pet["splice_type"] == "FINAL":
                    CAP = 3500  # FINAL splice cap
                    def avg(a, b):
                        m = max(a, b)
                        # FINAL splices get higher boost chance
                        if m > CAP * 0.75:  # If already high, apply smaller increase
                            return min(int(m * random.uniform(1.02, 1.08)), CAP)
                        else:  # Otherwise give more significant boost
                            return min(int(m * random.uniform(1.10, 1.18)), CAP)
                    
                    # Generate stats with higher boost
                    hp = avg(p1hp, p2hp)
                    atk = avg(p1atk, p2atk)
                    dfs = avg(p1def, p2def)
                    
                elif pet["splice_type"] == "SPECIAL":
                    CAP = 3000  # SPECIAL splice cap
                    def avg(a, b):
                        m = max(a, b)
                        # SPECIAL splices get moderate boost
                        if m > CAP * 0.8:
                            return min(int(m * random.uniform(1.01, 1.05)), CAP)
                        else:
                            return min(int(m * random.uniform(1.05, 1.12)), CAP)
                    
                    # Generate stats
                    hp = avg(p1hp, p2hp)
                    atk = avg(p1atk, p2atk)
                    dfs = avg(p1def, p2def)
                    
                elif pet["splice_type"] == "UNSTABLE":
                    CAP = 2850  # UNSTABLE splice cap
                    def avg(a, b):
                        m = max(a, b)
                        # UNSTABLE splices get randomly varying boosts
                        volatility = random.random() * 0.2  # 0 to 0.2 volatility
                        return min(int(m * random.uniform(0.95 + volatility, 1.08 + volatility)), CAP)
                    
                    # Generate potentially volatile stats
                    hp = avg(p1hp, p2hp)
                    atk = avg(p1atk, p2atk) 
                    dfs = avg(p1def, p2def)
                    
                elif pet["splice_type"] == "DESTABILIZED":
                        # DESTABILIZED splices get much weaker stats
                    CAP = 1500  # Lower cap for DESTABILIZED
                    pet['is_destabilised'] = True  # Ensure this flag is set for compatibility
                    
                    def d(x, y):
                        return min(int(max(x, y) * random.uniform(0.10, 0.30)), CAP)

                    hp = d(p1hp, p2hp)
                    atk = d(p1atk, p2atk)
                    dfs = d(p1def, p2def)
                    
                else:  # NORMAL splice
                    CAP = 2700  # Default cap

                    def avg(a, b):
                        m = max(a, b)
                        if m > CAP:
                            return min(int(((a + b) / 2) * random.uniform(1.05, 1.10)), CAP)
                        return min(int(m * random.uniform(0.92, 0.98)), CAP)

                    hp = avg(p1hp, p2hp)
                    atk = avg(p1atk, p2atk) 
                    dfs = avg(p1def, p2def)

                elm = await self.suggest_element(pet["pet1_element"], pet["pet2_element"])
                pet.update(dict(hp=hp, attack=atk, defense=dfs, element=elm))

                mx = max(hp, atk, dfs)
                
                # Set divine/forge suggestions based on splice type and stats
                if pet["splice_type"] == "DESTABILIZED":
                    # DESTABILIZED pets give no quest progress
                    div, frg = 0, 0
                elif pet["splice_type"] == "FINAL":
                    # FINAL pets give significant quest progress
                    div, frg = random.randint(40, 70), random.randint(40, 70)
                elif pet["splice_type"] == "SPECIAL":
                    # SPECIAL pets give good quest progress
                    div, frg = random.randint(30, 60), random.randint(30, 60)
                elif pet["splice_type"] == "UNSTABLE":
                    # UNSTABLE pets give variable quest progress
                    div, frg = random.randint(10, 40), random.randint(10, 40)
                elif mx > 2000:  # Normal splice with high stats
                    div, frg = random.randint(20, 50), random.randint(20, 50)
                elif mx > 1500:
                    div, frg = random.randint(5, 20), random.randint(5, 20)
                else:
                    div, frg = 0, 0
                    
                pet["divine_suggestion"], pet["forge_suggestion"] = div, frg

            except Exception as e:
                await ctx.send(f"⚠️ Stat generation error for {pet['name']}: {e}")
                pet.update(dict(hp=100, attack=100, defense=100, element="Unknown"))

        # ──────────────────────────────────────────────────────────
        # 5) STEP-3 AUTO NAME GENERATION
        # ──────────────────────────────────────────────────────────
        await ctx.send("📝 **AUTO-GENERATING NAMES** (using vision AI with enhanced creative prompts)...")

        # Define creative keywords for dynamic name generation
        name_themes = [
            # Foundational & Elemental
            'Celestial', 'Abyssal', 'Verdant', 'Arcane', 'Volcanic', 'Glacial', 'Ethereal', 'Tempest', 'Infernal', 'Sylvan',
            'Aquatic', 'Zephyrian', 'Cthonic', 'Empyrean', 'Galactic', 'Cosmic', 'Quantum', 'Ashen', 'Crystalline', 'Obsidian',
            'Metallic', 'Rusted', 'Blighted', 'Fungal', 'Geomantic', 'Kinetic', 'Psionic', 'Magnetic', 'Radioactive', 'Seismic',
            # Abstract & Emotional
            'Dread', 'Sanctified', 'Corrupted', 'Hallowed', 'Warped', 'Sovereign', 'Feral', 'Silent', 'Screaming', 'Weeping',
            'Joyful', 'Sorrowful', 'Wrathful', 'Peaceful', 'Chaotic', 'Lawful', 'Neutral', 'Vengeful', 'Merciful', 'Hopeful',
            # State & Condition
            'Chimeric', 'Prismatic', 'Nocturnal', 'Solar', 'Lunar', 'Miasmic', 'Auroral', 'Phantasmal', 'Grave-born', 'Dream-forged',
            'Nightmare', 'Mirage', 'Sunken', 'Plague-ridden', 'Symbiotic', 'Parasitic', 'Apex', 'Alpha', 'Omega', 'Prime',
            'Ancestral', 'Forgotten', 'Forbidden', 'Timeless', 'Ephemeral', 'Cyclical', 'Shattered', 'Mended', 'Wounded', 'Grotesque',
            # Mythical & Class-based
            'Seraphic', 'Demonic', 'Angelic', 'Diabolic', 'Draconic', 'Wyrm', 'Titan', 'Undead', 'Lich', 'Vampiric',
            'Elemental', 'Golem', 'Automaton', 'Cybernetic', 'Biomechanical', 'Clockwork', 'Eldritch', 'Outsider', 'Primordial', 'Ancient'
        ]
        name_concepts = [
            # Roles & Titles
            'Sentinel', 'Warden', 'Oracle', 'Goliath', 'Leviathan', 'Behemoth', 'Juggernaut', 'Specter', 'Phantom', 'Revenant',
            'Harbinger', 'Warden', 'Arbiter', 'Avatar', 'Champion', 'Guardian', 'Herald', 'Martyr', 'Master', 'Nemesis',
            'Paladin', 'Prodigy', 'Protector', 'Scion', 'Scourge', 'Seer', 'Sovereign', 'Tyrant', 'Vanguard', 'Victor',
            'Watcher', 'Warlord', 'Zealot', 'Adept', 'Ascendant', 'Barbarian', 'Cleric', 'Druid', 'Monk', 'Ranger',
            # Objects & Artifacts
            'Nexus', 'Vortex', 'Cipher', 'Fragment', 'Aegis', 'Altar', 'Anchor', 'Artifact', 'Beacon', 'Blade',
            'Codex', 'Core', 'Crown', 'Crucible', 'Curse', 'Diadem', 'Effigy', 'Elixir', 'Emblem', 'Font',
            'Forge', 'Gate', 'Gauntlet', 'Gem', 'Glyph', 'Grail', 'Grimoire', 'Idol', 'Keystone', 'Labyrinth',
            'Maw', 'Monolith', 'Orb', 'Pylon', 'Relic', 'Rune', 'Scepter', 'Shard', 'Shield', 'Shrine',
            'Sigil', 'Talisman', 'Tome', 'Totem', 'Veil', 'Weapon', 'Sanctum', 'Sarcophagus', 'Throne', 'Spire',
            # Events & Phenomena
            'Echo', 'Riddle', 'Mirage', 'Legacy', 'Paradox', 'Omen', 'Whisper', 'Requiem', 'Genesis', 'Apex',
            'Enigma', 'Chimera', 'Lament', 'Solitude', 'Fury', 'Serenity', 'Epoch', 'Aeon', 'Momentum', 'Catalyst',
            'Anomaly', 'Bastion', 'Conflux', 'Dirge', 'Flux', 'Calamity', 'Cascade', 'Deluge', 'Demise', 'Destiny',
            'Eclipse', 'Exodus', 'Finale', 'Fissure', 'Maelstrom', 'Nova', 'Oblivion', 'Onslaught', 'Rapture', 'Rift'
        ]
        name_origins = [
            # Forged & Wrought
            'Star-forged', 'Flame-wrought', 'Frost-forged', 'Chaos-forged', 'Grave-risen', 'Core-fused', 'Steel-forged', 'Iron-clad', 'Bone-crushed', 'Flesh-molded',
            'Mind-shattered', 'Will-bent', 'Fire-tempered', 'Titan-forged', 'Gold-plated', 'Bronze-cast', 'Spell-cast', 'Glory-won', 'War-torn', 'Battle-hardened',
            # Woven & Stitched
            'Dream-woven', 'Shadow-stitched', 'Fate-spun', 'Sinew-laced', 'Spider-spun', 'Light-woven', 'Nether-stitched', 'Vine-laced', 'Story-woven', 'Myth-spun',
            # Touched & Kissed
            'Void-touched', 'Angel-touched', 'Moon-kissed', 'Sun-scorched', 'Plague-touched', 'Hell-touched', 'Fey-touched', 'God-touched', 'Sorrow-touched', 'Winter-kissed',
            # Carved & Etched
            'Rune-carved', 'Pain-etched', 'Stone-hewn', 'Wood-carved', 'Gem-cut', 'Fear-etched', 'Hope-carved', 'Glory-etched', 'Despair-carved', 'Victory-etched',
            # Bound & Sworn
            'Soul-bound', 'Light-blessed', 'Blood-sworn', 'Order-bound', 'Ice-bound', 'Demon-bound', 'Honor-bound', 'Vow-kept', 'Oath-broken', 'Curse-bound',
            # Born & Spawned
            'Storm-born', 'Abyss-born', 'Sky-fallen', 'Thought-spawn', 'Fear-made', 'Myth-born', 'God-slain', 'Dragon-spawn', 'Slime-born', 'Hate-fueled',
            # Written & Told
            'Truth-spoken', 'Lie-whispered', 'Song-sung', 'Tale-told', 'Legend-written', 'Prophecy-fulfilled', 'Prayer-answered', 'Doom-sealed', 'Secret-kept', 'Last-word',
            # Lost & Found
            'Time-lost', 'Reality-bent', 'Hope-lost', 'Faith-given', 'Love-lost', 'Gamble-lost', 'Victory-claimed', 'Defeat-suffered', 'Glory-found', 'Wisdom-gained',
            # Ender & Bringer
            'World-ender', 'Life-bringer', 'Dawn-bringer', 'Dusk-ender', 'Peace-bringer', 'War-ender', 'Hope-bringer', 'Doom-bringer', 'Light-bringer', 'Night-ender'
        ]

        for i, pet in enumerate(pets, 1):
            try:
                # Add 1 to 3 random keywords for inspiration
                keywords_to_add = random.randint(1, 3)
                inspiration_keywords = random.sample(name_themes + name_concepts + name_origins, keywords_to_add)
                inspiration_text = f"Hint for inspiration: {', '.join(inspiration_keywords)}. "

                base_prompt = (
                    "You are a master myth-maker. A new legendary creature stands before you. "
                    "Gaze upon its form and essence. What is its true name, a name for legends? "
                    f"{inspiration_text}"
                    "Consider its powers, temperament, and the story it tells. "
                    "Forge a unique, resonant name (one or two words). "
                    "Avoid common fantasy names (e.g., Nyx, Umbra, Shadow, Luna, Ember). "
                    "Draw inspiration from myths, celestial bodies, rare minerals, or abstract concepts. "
                    "Deliver only the name. No titles, no explanations. Just the name."
                )

                vision_msg = [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": base_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": pet["url"]}
                        },
                    ],
                }]

                resp = await asyncio.to_thread(
                    openai_client.chat.completions.create,  # Fixed: was responses.create
                    model="o3",  # Fixed: was "o3-2025-04-16"
                    messages=vision_msg,  # Fixed: was input=vision_msg
                )

                # Get the AI-generated name
                generated_name = resp.choices[0].message.content.strip()
                
                # Preserve the splice tag if it exists
                if pet["splice_type"] != "NORMAL":
                    # Re-add the appropriate tag to the end of the AI-generated name
                    if pet["splice_type"] == "FINAL":
                        tagged_name = f"{generated_name} [FINAL]"
                    elif pet["splice_type"] == "SPECIAL":
                        tagged_name = f"{generated_name} [SPECIAL]"
                    elif pet["splice_type"] == "UNSTABLE":
                        tagged_name = f"{generated_name} [UNSTABLE]"
                    elif pet["splice_type"] == "DESTABILIZED":
                        tagged_name = f"{generated_name} [DESTABILISED]"
                    else:
                        tagged_name = generated_name
                    
                    # Update the pet name with tag preserved
                    pet["name"] = tagged_name
                    await ctx.send(f"✨ {i}/{len(pets)}: {pet['pet1_default']}+{pet['pet2_default']} → **{tagged_name}**")
                else:
                    # Normal pet with no tag
                    pet["name"] = generated_name
                    await ctx.send(f"✨ {i}/{len(pets)}: {pet['pet1_default']}+{pet['pet2_default']} → **{generated_name}**")

            except Exception as e:
                await ctx.send(f"⚠️ Name generation failed for pet {i}: {e}")

        # ──────────────────────────────────────────────────────────
        # 6) INTERACTIVE REVIEW SYSTEM
        # ──────────────────────────────────────────────────────────
        await ctx.send("📋 **REVIEW PHASE** - Check your spliced pets below...")

        # Generate unique save ID for this auto splice session
        save_id = f"auto_splice_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"
        
        review_view = AutoSpliceReview(ctx, pets, openai_client, timeout=300, save_id=save_id)
        embed = await review_view.get_review_embed()
        
        message = await ctx.send(embed=embed, view=review_view)
        review_view.message = message

        # Wait for review completion
        await review_view.wait()

        # Check if cancelled
        if not pets:
            return await ctx.send("Auto splice cancelled.")

        if not review_view.confirmed:
            return await ctx.send("⏰ Review timed out. Auto splice cancelled.")

        # ──────────────────────────────────────────────────────────
        # 7) CREATE PETS IN DATABASE
        # ──────────────────────────────────────────────────────────
        await ctx.send("🔨 **CREATING PETS IN DATABASE**...")

        completed = []
        for pet in pets:
            try:
                iv_pct = random.uniform(30, 70)
                iv_pts = (iv_pct / 100) * 100
                hp_iv, atk_iv, def_iv = await self.allocate_iv_points(iv_pts)

                baby_hp = round(pet["hp"] * 0.25) + hp_iv
                baby_atk = round(pet["attack"] * 0.25) + atk_iv
                baby_def = round(pet["defense"] * 0.25) + def_iv
                growth_t = datetime.datetime.utcnow() + datetime.timedelta(days=2)

                async with self.bot.pool.acquire() as conn:
                    new_id = await conn.fetchval(
                        """
                        INSERT INTO monster_pets
                        (user_id,name,hp,attack,defense,element,default_name,
                         url,growth_stage,growth_time,"IV")
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id
                        """,
                        pet["user_id"], pet["name"],
                        baby_hp, baby_atk, baby_def,
                        pet["element"], pet["name"], pet["url"],
                        "baby", growth_t, iv_pct,
                    )
                    
                    await conn.execute(
                        "UPDATE splice_requests SET status='completed' WHERE id=$1",
                        pet["splice_id"],
                    )
                    
                    await conn.execute(
                        """
                        INSERT INTO splice_combinations
                        (pet1_default,pet2_default,result_name,hp,attack,defense,element,url)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        """,
                        pet["pet1_default"], pet["pet2_default"], pet["name"],
                        pet["hp"], pet["attack"], pet["defense"], pet["element"], pet["url"],
                    )
                    
                completed.append((new_id, pet))

                # Update forge/divine
                async with self.bot.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT forge_condition, divine_attention FROM splicing_quest WHERE user_id=$1",
                        pet["user_id"],
                    )
                forge_c = row["forge_condition"] if row else 100
                divine = row["divine_attention"] if row else 0
                forge_c = max(0, forge_c - pet["forge_suggestion"])
                divine = min(100, divine + pet["divine_suggestion"])

                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO splicing_quest (user_id, forge_condition, divine_attention)
                        VALUES ($1,$2,$3)
                        ON CONFLICT (user_id)
                        DO UPDATE SET forge_condition=$2, divine_attention=$3
                        """,
                        pet["user_id"], forge_c, divine,
                    )

                # DM owner
                owner = self.bot.get_user(pet["user_id"])
                if owner:
                    try:
                        await owner.send(
                            f"🧬 Your new creature **{pet['name']}** is born! Check `$pets`."
                        )
                    except Exception:
                        pass

            except Exception as e:
                await ctx.send(f"⚠️ Error creating {pet['name']}: {e}")

        # ──────────────────────────────────────────────────────────
        # 8) SUMMARY
        # ──────────────────────────────────────────────────────────
        if not completed:
            return await ctx.send("No pets were created.")

        summ = discord.Embed(
            title="🎉 Auto Splice Complete!",
            description=f"Successfully created {len(completed)} pet(s) automatically.",
            color=0x00FF00,
        )
        for pid, p in completed:
            summ.add_field(
                name=p['name'], 
                value=f"ID `{pid}` • <@{p['user_id']}>\nHP: {p['hp']} | ATK: {p['attack']} | DEF: {p['defense']}", 
                inline=True
            )
        
        await ctx.send(embed=summ)

    @is_gm()
    @commands.command(hidden=True)
    async def resume_auto_splice(self, ctx: commands.Context, save_id: str = None):
        """Resume a saved auto splice session"""
        
        from openai import OpenAI
        
        # Load saved auto splice data
        if not os.path.exists(AUTO_SPLICE_SAVE_FILE):
            return await ctx.send("❌ No saved auto splice sessions found.")
        
        try:
            with open(AUTO_SPLICE_SAVE_FILE, 'r') as f:
                saves = json.load(f)
        except Exception as e:
            return await ctx.send(f"❌ Error loading saved data: {e}")
        
        if not saves:
            return await ctx.send("❌ No saved auto splice sessions found.")
        
        # If no save_id provided, show available saves
        if not save_id:
            embed = discord.Embed(
                title="📋 Saved Auto Splice Sessions",
                description="Available sessions to resume:",
                color=0x9C44DC
            )
            
            for sid, data in saves.items():
                created_at = datetime.datetime.fromisoformat(data["created_at"])
                time_ago = datetime.datetime.utcnow() - created_at
                hours_ago = time_ago.total_seconds() / 3600
                
                embed.add_field(
                    name=f"Session: {sid}",
                    value=f"Created: {hours_ago:.1f} hours ago\nPets: {len(data['pets'])}\nAuthor: <@{data['ctx_author_id']}>",
                    inline=False
                )
            
            embed.set_footer(text="Use: $resume_auto_splice <save_id>")
            return await ctx.send(embed=embed)
        
        # Check if save_id exists
        if save_id not in saves:
            return await ctx.send(f"❌ Save ID '{save_id}' not found.")
        
        save_data = saves[save_id]
        
        # Check if user is authorized (original author or GM)
        if save_data["ctx_author_id"] != ctx.author.id:
            # Check if user is GM (you might want to add a GM check here)
            pass
        
        # Initialize OpenAI client
        try:
            openai_client = OpenAI(api_key="")
        except Exception as e:
            return await ctx.send(f"❌ OpenAI client initialization failed: {e}")
        
        # Load pets from save data
        pets = save_data["pets"]
        
        await ctx.send(f"🔄 **Resuming Auto Splice Session**\n📋 Found {len(pets)} pets ready for review...")
        
        # Create review view with the saved data
        review_view = AutoSpliceReview(ctx, pets, openai_client, timeout=300, save_id=save_id)
        embed = await review_view.get_review_embed()
        
        message = await ctx.send(embed=embed, view=review_view)
        review_view.message = message
        
        # Wait for review completion
        await review_view.wait()
        
        # Check if cancelled
        if not pets:
            return await ctx.send("Auto splice cancelled.")
        
        if not review_view.confirmed:
            return await ctx.send("⏰ Review timed out. Auto splice cancelled.")
        
        # Create pets in database (same logic as auto_splice)
        await ctx.send("🔨 **CREATING PETS IN DATABASE**...")
        
        completed = []
        for pet in pets:
            try:
                iv_pct = random.uniform(30, 70)
                iv_pts = (iv_pct / 100) * 100
                hp_iv, atk_iv, def_iv = await self.allocate_iv_points(iv_pts)
                
                baby_hp = round(pet["hp"] * 0.25) + hp_iv
                baby_atk = round(pet["attack"] * 0.25) + atk_iv
                baby_def = round(pet["defense"] * 0.25) + def_iv
                growth_t = datetime.datetime.utcnow() + datetime.timedelta(days=2)
                
                async with self.bot.pool.acquire() as conn:
                    new_id = await conn.fetchval(
                        """
                        INSERT INTO monster_pets
                        (user_id,name,hp,attack,defense,element,default_name,
                         url,growth_stage,growth_time,"IV")
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id
                        """,
                        pet["user_id"], pet["name"],
                        baby_hp, baby_atk, baby_def,
                        pet["element"], pet["name"], pet["url"],
                        "baby", growth_t, iv_pct,
                    )
                    
                    await conn.execute(
                        "UPDATE splice_requests SET status='completed' WHERE id=$1",
                        pet["splice_id"],
                    )
                    
                    await conn.execute(
                        """
                        INSERT INTO splice_combinations
                        (pet1_default,pet2_default,result_name,hp,attack,defense,element,url)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        """,
                        pet["pet1_default"], pet["pet2_default"], pet["name"],
                        pet["hp"], pet["attack"], pet["defense"], pet["element"], pet["url"],
                    )
                    
                completed.append((new_id, pet))
                
                # Update forge/divine
                async with self.bot.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT forge_condition, divine_attention FROM splicing_quest WHERE user_id=$1",
                        pet["user_id"],
                    )
                forge_c = row["forge_condition"] if row else 100
                divine = row["divine_attention"] if row else 0
                forge_c = max(0, forge_c - pet["forge_suggestion"])
                divine = min(100, divine + pet["divine_suggestion"])
                
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO splicing_quest (user_id, forge_condition, divine_attention)
                        VALUES ($1,$2,$3)
                        ON CONFLICT (user_id)
                        DO UPDATE SET forge_condition=$2, divine_attention=$3
                        """,
                        pet["user_id"], forge_c, divine,
                    )
                
                # DM owner
                owner = self.bot.get_user(pet["user_id"])
                if owner:
                    try:
                        await owner.send(
                            f"🧬 Your new creature **{pet['name']}** is born! Check `$pets`."
                        )
                    except Exception:
                        pass
                        
            except Exception as e:
                await ctx.send(f"⚠️ Error creating {pet['name']}: {e}")
        
        # Summary
        if not completed:
            return await ctx.send("No pets were created.")
        
        summ = discord.Embed(
            title="🎉 Auto Splice Resumed and Complete!",
            description=f"Successfully created {len(completed)} pet(s) from saved session.",
            color=0x00FF00,
        )
        for pid, p in completed:
            summ.add_field(
                name=p['name'], 
                value=f"ID `{pid}` • <@{p['user_id']}>\nHP: {p['hp']} | ATK: {p['attack']} | DEF: {p['defense']}", 
                inline=True
            )
        
        await ctx.send(embed=summ)

    @is_gm()
    @commands.command(hidden=True)
    async def list_auto_splices(self, ctx: commands.Context):
        """List all saved auto splice sessions"""
        
        if not os.path.exists(AUTO_SPLICE_SAVE_FILE):
            return await ctx.send("❌ No saved auto splice sessions found.")
        
        try:
            with open(AUTO_SPLICE_SAVE_FILE, 'r') as f:
                saves = json.load(f)
        except Exception as e:
            return await ctx.send(f"❌ Error loading saved data: {e}")
        
        if not saves:
            return await ctx.send("❌ No saved auto splice sessions found.")
        
        embed = discord.Embed(
            title="📋 Saved Auto Splice Sessions",
            description=f"Found {len(saves)} saved session(s):",
            color=0x9C44DC
        )
        
        for sid, data in saves.items():
            created_at = datetime.datetime.fromisoformat(data["created_at"])
            time_ago = datetime.datetime.utcnow() - created_at
            hours_ago = time_ago.total_seconds() / 3600
            
            embed.add_field(
                name=f"Session: {sid}",
                value=f"Created: {hours_ago:.1f} hours ago\nPets: {len(data['pets'])}\nAuthor: <@{data['ctx_author_id']}>",
                inline=False
            )
        
        embed.set_footer(text="Use: $resume_auto_splice <save_id> to resume | $delete_auto_splice <save_id> to delete")
        await ctx.send(embed=embed)

    @is_gm()
    @commands.command(hidden=True)
    async def delete_auto_splice(self, ctx: commands.Context, save_id: str):
        """Delete a saved auto splice session"""
        
        if not os.path.exists(AUTO_SPLICE_SAVE_FILE):
            return await ctx.send("❌ No saved auto splice sessions found.")
        
        try:
            with open(AUTO_SPLICE_SAVE_FILE, 'r') as f:
                saves = json.load(f)
        except Exception as e:
            return await ctx.send(f"❌ Error loading saved data: {e}")
        
        if save_id not in saves:
            return await ctx.send(f"❌ Save ID '{save_id}' not found.")
        
        # Remove the save
        del saves[save_id]
        
        # Write back to file
        try:
            with open(AUTO_SPLICE_SAVE_FILE, 'w') as f:
                json.dump(saves, f, indent=2, default=str)
            await ctx.send(f"✅ Successfully deleted save session: {save_id}")
        except Exception as e:
            await ctx.send(f"❌ Error deleting save: {e}")

    @is_gm()
    @commands.command(hidden=True)
    async def clear_auto_splices(self, ctx: commands.Context):
        """Clear all saved auto splice sessions"""
        
        if not os.path.exists(AUTO_SPLICE_SAVE_FILE):
            return await ctx.send("❌ No saved auto splice sessions found.")
        
        try:
            with open(AUTO_SPLICE_SAVE_FILE, 'r') as f:
                saves = json.load(f)
        except Exception as e:
            return await ctx.send(f"❌ Error loading saved data: {e}")
        
        if not saves:
            return await ctx.send("❌ No saved auto splice sessions found.")
        
        count = len(saves)
        
        # Clear all saves
        try:
            with open(AUTO_SPLICE_SAVE_FILE, 'w') as f:
                json.dump({}, f)
            await ctx.send(f"✅ Successfully cleared {count} saved auto splice session(s)")
        except Exception as e:
            await ctx.send(f"❌ Error clearing saves: {e}")

    # ──────────────────────────────────────────────────────────────────────
    #  BATCH S P L I C E   (full command – gpt-image-1, retry loops, etc.)
    # ──────────────────────────────────────────────────────────────────────
    @is_gm()
    @commands.command(hidden=True)
    async def batch_splice(self, ctx: commands.Context, count: int = 5):

        import aiohttp, asyncio, base64, datetime, io, json, os, random, traceback
        from firebase_admin import credentials, storage
        import firebase_admin
        from openai import OpenAI

        MAX_BATCH = 21
        DEFAULT_IMG = "https://i.imgur.com/nJYMPOQ.png"
        BUCKET = "fablerpg-f74c2.appspot.com"
        PIXELCUT_URL = "https://api.developer.pixelcut.ai/v1/remove-background"
        PIXELCUT_KEY = os.getenv("PIXELCUT_KEY") or ""

        # ──────────────────────────────────────────────────────────
        # helper wrappers  (only used inside this command)
        # ──────────────────────────────────────────────────────────
        async def admin_wait(timeout=60):
            return await self.bot.wait_for(
                "message",
                timeout=timeout,
                check=lambda m: m.author.id == ctx.author.id and m.channel.id == ctx.channel.id,
            )

        async def download_bytes(url: str) -> bytes:
            async with aiohttp.ClientSession() as s:
                async with s.get(url) as r:
                    return await r.read()

        async def remove_background(
                ctx: commands.Context,
                *,
                img_url: str | None = None,
                img_bytes: bytes | None = None,
                filename: str = "temp.png",
        ) -> bytes:
            """
            Remove background with Pixelcut.
            – If `img_url` is given, that URL is sent straight to Pixelcut.
            – If `img_bytes` is given, the bot uploads the file to Discord,
              obtains the CDN URL, then calls Pixelcut and finally deletes the
              temporary Discord message.
            Returns: PNG bytes with background removed.
            Raises RuntimeError on a non-200 response.
            """
            if not img_url and not img_bytes:
                raise ValueError("Need either img_url or img_bytes")

            # 1. make sure we end up with a publicly reachable URL
            temp_msg = None
            if not img_url:
                temp_msg = await ctx.channel.send(
                    file=discord.File(io.BytesIO(img_bytes), filename)
                )
                img_url = temp_msg.attachments[0].url

            # 2. call Pixelcut with the URL
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-API-KEY": PIXELCUT_KEY,
            }
            payload = json.dumps({"image_url": img_url, "format": "png"})

            async with aiohttp.ClientSession() as s:
                async with s.post(PIXELCUT_URL, headers=headers, data=payload) as r:
                    if r.status != 200:
                        raise RuntimeError(f"PixelCut status {r.status}")
                    data = await r.json()

                async with s.get(data["result_url"]) as r2:
                    result_bytes = await r2.read()

            # 3. clean up the temp message if we created one
            if temp_msg:
                try:
                    await temp_msg.delete()
                except Exception:
                    pass

            return result_bytes

        BUCKET_NAME = "fablerpg-f74c2.appspot.com"

        def get_firebase_bucket():
            """
            Return a google.cloud.storage.bucket.Bucket object.
            initialise exactly ONE firebase app – never duplicated.
            """
            if not firebase_admin._apps:
                firebase_admin.initialize_app(credentials.Certificate("acc.json"))

            # works even if the app was started without storageBucket in its options
            return storage.bucket(BUCKET_NAME)

        async def firebase_upload(data: bytes, filename: str) -> str:
            bucket = get_firebase_bucket()
            blob = bucket.blob(filename)
            blob.upload_from_string(data)
            blob.make_public()
            return blob.public_url

        # ──────────────────────────────────────────────────────────
        # 0) limit batch + create OpenAI client
        # ──────────────────────────────────────────────────────────
        if count > MAX_BATCH:
            count = MAX_BATCH
            await ctx.send(f"Batch size limited to {MAX_BATCH}")

        try:
            openai_client = OpenAI(api_key="")
            await ctx.send("✅ OpenAI client initialised – gpt-image-1 enabled.")
        except Exception as e:
            openai_client = None
            await ctx.send(f"⚠️  OpenAI init failed ({e}) – AI disabled.")

        # ──────────────────────────────────────────────────────────
        # 1) pull pending requests
        # ──────────────────────────────────────────────────────────
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT  id, user_id, pet1_name, pet2_name,
                        pet1_default, pet2_default, created_at,
                        pet1_url, pet2_url,
                        pet1_hp, pet1_attack, pet1_defense,
                        pet2_hp, pet2_attack, pet2_defense,
                        pet1_element, pet2_element, temp_name
                FROM    splice_requests
                WHERE   status='pending'
                ORDER BY created_at
                LIMIT   $1
                """,
                count,
            )

        if not rows:
            return await ctx.send("No pending splice requests.")

        # ──────────────────────────────────────────────────────────
        # 2) build working objects
        # ──────────────────────────────────────────────────────────
        pets = []
        for r in rows:
            pets.append(
                dict(
                    splice_id=r["id"],
                    user_id=r["user_id"],
                    name=r["temp_name"],
                    pet1_default=r["pet1_default"],
                    pet2_default=r["pet2_default"],
                    pet1_hp=r["pet1_hp"],
                    pet1_attack=r["pet1_attack"],
                    pet1_defense=r["pet1_defense"],
                    pet2_hp=r["pet2_hp"],
                    pet2_attack=r["pet2_attack"],
                    pet2_defense=r["pet2_defense"],
                    pet1_element=r["pet1_element"],
                    pet2_element=r["pet2_element"],
                    pet1_url=r["pet1_url"],
                    pet2_url=r["pet2_url"],
                    url=None,
                    hp=None,
                    attack=None,
                    defense=None,
                    element=None,
                    is_destabilised="[DESTABILISED]" in r["temp_name"],
                    divine_suggestion=0,
                    forge_suggestion=0,
                )
            )

        # ──────────────────────────────────────────────────────────
        # 3) STEP-1  IMAGE  (with retry loop + gpt-image-1 edit)
        # ──────────────────────────────────────────────────────────
        await ctx.send("__**STEP-1  – choose / create an image for each pet**__")

        for idx, pet in enumerate(pets, 1):
            while True:
                try:
                    menu = (
                        f"**{idx}/{len(pets)} – {pet['name']}**\n"
                        "Choose:\n"
                        "`1` upload attachment\n`2` paste URL\n"
                        "`3` generate with gpt-image-1 (parent pictures merged)\n"
                        "`cancel` abort batch"
                    )
                    await ctx.send(menu)
                    msg = await admin_wait()
                    choice = msg.content.lower().strip()

                    if choice == "cancel":
                        await ctx.send("Batch cancelled.")
                        return

                    # ── 1) attachment
                    if choice == "1":
                        await ctx.send("Upload the image:")
                        up = await admin_wait()
                        if not up.attachments:
                            await ctx.send("No attachment – try again.")
                            continue
                        att = up.attachments[0]
                        data = await att.read()

                        if "[SPECIAL]" not in pet["name"].upper():
                            await ctx.send("Remove background? (`yes`/`no`)")
                            try:
                                if (await admin_wait()).content.lower().startswith("y"):
                                    data = await remove_background(ctx, img_url=att.url)
                            except asyncio.TimeoutError:
                                pass

                        pet["url"] = await firebase_upload(
                            data, f"{ctx.author.id}_{pet['name']}_{att.filename}"
                        )
                        break

                    # ── 2) direct URL
                    if choice == "2":
                        await ctx.send("Paste direct image URL:")
                        pet["url"] = (await admin_wait()).content.strip()
                        break

                    # ── 3) gpt-image-1  (merge parents)
                    if choice == "3" and openai_client:
                        # download parent images to temp files
                        p1_bytes = await download_bytes(pet["pet1_url"])
                        p2_bytes = await download_bytes(pet["pet2_url"])
                        p1_file = f"p1_{pet['splice_id']}.png"
                        p2_file = f"p2_{pet['splice_id']}.png"
                        with open(p1_file, "wb") as f:
                            f.write(p1_bytes)
                        with open(p2_file, "wb") as f:
                            f.write(p2_bytes)

                        default_prompt = (
                            "Fuse these two monsters into one impossible hybrid creature. Merge their most striking features into a single, otherworldly beast that combines the essence of both. Create a seamless genetic splice with no background - just the pure, evolved fusion floating in white/transparent space."
                        )
                        await ctx.send(
                            f"Default prompt:\n`{default_prompt}`\nAdd anything? (`yes`/`no`)"
                        )
                        extra = (await admin_wait()).content.lower().startswith("y")
                        if extra:
                            await ctx.send("Enter extra prompt:")
                            default_prompt += " " + (await admin_wait(timeout=120)).content.strip()

                        await ctx.send("Creating image with gpt-image-1…")

                        def _edit():
                            return openai_client.images.edit(
                                model="gpt-image-1",
                                image=[open(p1_file, "rb"), open(p2_file, "rb")],
                                prompt=default_prompt,
                            )

                        try:
                            result = await asyncio.to_thread(_edit)
                            img_b64 = result.data[0].b64_json
                            gen_bytes = base64.b64decode(img_b64)
                        except Exception as e:
                            await ctx.send(f"⚠️  AI edit failed: {e}")
                            gen_bytes = None

                        try:
                            result = await asyncio.to_thread(_edit)
                            img_b64 = result.data[0].b64_json
                            gen_bytes = base64.b64decode(img_b64)
                        except Exception as e:
                            await ctx.send(f"⚠️  AI edit failed: {e}")
                            gen_bytes = None


                        # remove temp files
                        try:
                            os.remove(p1_file)
                            os.remove(p2_file)
                        except Exception:
                            pass

                        if not gen_bytes:
                            pet["url"] = DEFAULT_IMG
                            break

                        # preview
                        await ctx.send(file=discord.File(io.BytesIO(gen_bytes), "preview.png"))
                        await ctx.send("`yes` accept   `retry` redo   anything else = default")
                        try:
                            dec = await admin_wait()
                        except asyncio.TimeoutError:
                            dec = None

                        if dec and dec.content.lower().startswith("y"):
                            pet["url"] = await firebase_upload(
                                gen_bytes, f"{ctx.author.id}_{pet['name']}_ai.png"
                            )
                            if gen_bytes:
                                await ctx.send("Remove background from AI image? (`yes`/`no`)")
                                try:
                                    if (await admin_wait()).content.lower().startswith("y"):
                                        gen_bytes = await remove_background(ctx, img_bytes=gen_bytes, filename="ai.png")
                                except asyncio.TimeoutError:
                                    pass
                            break
                        if dec and dec.content.lower().startswith("retry"):
                            continue  # restart image step
                        pet["url"] = DEFAULT_IMG
                        break

                    await ctx.send("Invalid choice – try again.")
                except asyncio.TimeoutError:
                    await ctx.send("⌛ timeout – default image used.")
                    pet["url"] = DEFAULT_IMG
                    break
                except Exception as e:
                    await ctx.send(f"⚠️  image step error: {e}")
                    pet["url"] = DEFAULT_IMG
                    break

        # ──────────────────────────────────────────────────────────
        # 4) STEP-2  STAT SUGGESTION  (your logic unchanged)
        # ──────────────────────────────────────────────────────────

        # ─── ask whether to post-process the AI image ───


        await ctx.send("__**STEP-2  – generating suggested stats**__")
        for pet in pets:
            try:
                p1hp, p1atk, p1def = pet["pet1_hp"], pet["pet1_attack"], pet["pet1_defense"]
                p2hp, p2atk, p2def = pet["pet2_hp"], pet["pet2_attack"], pet["pet2_defense"]

                if pet["is_destabilised"]:
                    def d(x, y):
                        return int(max(x, y) * random.uniform(0.10, 0.30))

                    hp, atk, dfs = d(p1hp, p2hp), d(p1atk, p2atk), d(p1def, p2def)
                else:
                    CAP = 1500

                    def avg(a, b):
                        m = max(a, b)
                        if m > CAP:
                            return min(int(((a + b) / 2) * random.uniform(1.05, 1.10)), CAP)
                        return min(int(m * random.uniform(0.92, 0.98)), CAP)

                    hp, atk, dfs = avg(p1hp, p2hp), avg(p1atk, p2atk), avg(p1def, p2def)

                elm = await self.suggest_element(pet["pet1_element"], pet["pet2_element"])
                pet.update(dict(hp=hp, attack=atk, defense=dfs, element=elm))

                mx = max(hp, atk, dfs)
                if pet["is_destabilised"]:
                    div, frg = 0, 0
                elif mx > 1200:
                    div, frg = random.randint(20, 50), random.randint(20, 50)
                elif mx > 800:
                    div, frg = random.randint(5, 20), random.randint(5, 20)
                else:
                    div, frg = 0, 0
                pet["divine_suggestion"], pet["forge_suggestion"] = div, frg

            except Exception as e:
                await ctx.send(f"⚠️  stat generation error: {e}")
                pet.update(dict(hp=100, attack=100, defense=100, element="Unknown"))

        # ──────────────────────────────────────────────────────────
        # 2b)  allow GM to review / edit stats
        # ──────────────────────────────────────────────────────────
        embed = discord.Embed(
            title="🧬 Review suggested stats",
            description=(
                "Type **confirm** to accept all, a **number** (1-{0}) to edit, "
                "or **cancel** to abort."
            ).format(len(pets)),
            color=0x9C44DC,
        )
        for n, p in enumerate(pets, 1):
            embed.add_field(
                name=f"{n}. {p['name']}",
                value=f"HP {p['hp']}\nATK {p['attack']}\nDEF {p['defense']}\nELM {p['element']}",
                inline=True,
            )
        await ctx.send(embed=embed)

        while True:
            try:
                msg = await admin_wait(timeout=90)
            except asyncio.TimeoutError:
                await ctx.send("⌛ timed out – keeping current stats.")
                break

            txt = msg.content.lower().strip()
            if txt == "confirm":
                break
            if txt == "cancel":
                await ctx.send("Batch aborted.")
                return
            if txt.isdigit() and 1 <= int(txt) <= len(pets):
                idx = int(txt) - 1
                p = pets[idx]
                await ctx.send(
                    f"Send new stats for **{p['name']}** in the form "
                    "`hp,attack,defense,element`  or type `back`."
                )
                try:
                    edit = await admin_wait(timeout=120)
                except asyncio.TimeoutError:
                    continue
                if edit.content.lower().startswith("back"):
                    continue
                parts = edit.content.split(",", 3)
                if len(parts) < 3:
                    await ctx.send("Need at least hp,atk,def.  Try again.")
                    continue
                try:
                    p["hp"] = int(parts[0])
                    p["attack"] = int(parts[1])
                    p["defense"] = int(parts[2])
                    if len(parts) == 4:
                        p["element"] = parts[3].title().strip()
                except ValueError:
                    await ctx.send("Numbers were not valid – try again.")
                    continue
                # redisplay the embed
                embed.set_field_at(
                    idx,
                    name=f"{idx + 1}. {p['name']}",
                    value=(
                        f"HP {p['hp']}\nATK {p['attack']}\n"
                        f"DEF {p['defense']}\nELM {p['element']}"
                    ),
                    inline=True,
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("Please type `confirm`, `cancel` or a valid number.")

        # ─── STEP-3  NAME (Vision) ───────────────────────────
        await ctx.send("__**STEP-3  – naming**__")
        if openai_client:
            for i, pet in enumerate(pets, 1):
                while True:
                    try:
                        base_prompt = (
                            "Look at this picture and propose exactly five unique "
                            "names related to its features (max two words, do not place numbers next to each name ex. 1. <name> 2. <name> etc. 1 name per line)."
                        )

                        vision_msg = [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": base_prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": pet["url"], "detail": "auto"},
                                    },
                                ],
                            }
                        ]

                        resp = await asyncio.to_thread(
                            openai_client.chat.completions.create,
                            model="gpt-4o",
                            messages=vision_msg,
                        )
                        raw_text = resp.choices[0].message.content

                        names = [
                                    x.strip(" .-")
                                    for x in raw_text.replace("\r", "").split("\n")
                                    if x.strip()
                                ][:5]

                        if not names:
                            raise RuntimeError("Vision returned no names")

                        # present the list to the GM
                        await ctx.send(
                            f"**{i}/{len(pets)} – "
                            f"{pet['pet1_default']}+{pet['pet2_default']}**\n"
                            + "\n".join(f'`{n + 1}` {nm}' for n, nm in enumerate(names))
                            + "\nChoose a number, type `retry <extra prompt>` "
                              "or enter a custom name."
                        )

                        msg = await admin_wait(timeout=120)
                        choice = msg.content.strip()

                        if choice.lower().startswith("retry"):
                            extra = choice[5:].strip()
                            if extra:
                                base_prompt += "\nExtra: " + extra
                            continue

                        if choice.isdigit() and 1 <= int(choice) <= len(names):
                            pet["name"] = names[int(choice) - 1]
                        else:
                            pet["name"] = choice
                        break

                    except Exception as e:
                        await ctx.send(f"⚠️  Vision naming error: {e}")
                        break
        else:
            await ctx.send("GPT unavailable – keeping temporary names.")

        # ──────────────────────────────────────────────────────────
        # 6) STEP-4  REVIEW & CONFIRM
        # ──────────────────────────────────────────────────────────
        emb = discord.Embed(
            title="🧬 Final review",
            description="`confirm` to create pets, anything else to abort.",
            color=0x00FF00,
        )
        for i, p in enumerate(pets, 1):
            emb.add_field(
                name=f"{i}. {p['name']}",
                value=f"HP {p['hp']}  ATK {p['attack']}  DEF {p['defense']}  ELM {p['element']}",
                inline=True,
            )
        await ctx.send(embed=emb)

        try:
            if (await admin_wait()).content.lower() != "confirm":
                await ctx.send("Batch aborted.")
                return
        except asyncio.TimeoutError:
            await ctx.send("⌛ no answer – batch aborted.")
            return

        # ──────────────────────────────────────────────────────────
        # 7) STEP-5  INSERT INTO DB  (unchanged)
        # ──────────────────────────────────────────────────────────
        completed = []
        for pet in pets:
            try:
                iv_pct = random.uniform(30, 70)
                iv_pts = (iv_pct / 100) * 100
                hp_iv, atk_iv, def_iv = await self.allocate_iv_points(iv_pts)

                baby_hp = round(pet["hp"] * 0.25) + hp_iv
                baby_atk = round(pet["attack"] * 0.25) + atk_iv
                baby_def = round(pet["defense"] * 0.25) + def_iv
                growth_t = datetime.datetime.utcnow() + datetime.timedelta(days=2)

                async with self.bot.pool.acquire() as conn:
                    new_id = await conn.fetchval(
                        """
                        INSERT INTO monster_pets
                        (user_id,name,hp,attack,defense,element,default_name,
                         url,growth_stage,growth_time,"IV")
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id
                        """,
                        pet["user_id"], pet["name"],
                        baby_hp, baby_atk, baby_def,
                        pet["element"], pet["name"], pet["url"],
                        "baby", growth_t, iv_pct,
                    )
                    await conn.execute(
                        "UPDATE splice_requests SET status='completed' WHERE id=$1",
                        pet["splice_id"],
                    )
                    await conn.execute(
                        """
                        INSERT INTO splice_combinations
                        (pet1_default,pet2_default,result_name,hp,attack,defense,element,url)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        """,
                        pet["pet1_default"], pet["pet2_default"], pet["name"],
                        pet["hp"], pet["attack"], pet["defense"], pet["element"], pet["url"],
                    )
                completed.append((new_id, pet))

                # forge / divine
                async with self.bot.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT forge_condition, divine_attention FROM splicing_quest WHERE user_id=$1",
                        pet["user_id"],
                    )
                forge_c = row["forge_condition"] if row else 100
                divine = row["divine_attention"] if row else 0
                forge_c = max(0, forge_c - pet["forge_suggestion"])
                divine = min(100, divine + pet["divine_suggestion"])

                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO splicing_quest (user_id, forge_condition, divine_attention)
                        VALUES ($1,$2,$3)
                        ON CONFLICT (user_id)
                        DO UPDATE SET forge_condition=$2, divine_attention=$3
                        """,
                        pet["user_id"], forge_c, divine,
                    )

                # DM owner
                owner = self.bot.get_user(pet["user_id"])
                if owner:
                    try:
                        await owner.send(
                            f"🧬 Your new creature **{pet['name']}** is born! Check `$pets`."
                        )
                    except Exception:
                        pass

            except Exception as e:
                await ctx.send(f"⚠️  error creating {pet['name']}: {e}")
                await ctx.send(f"```{traceback.format_exc()[:1500]}```")

        # ──────────────────────────────────────────────────────────
        # 8) summary
        # ──────────────────────────────────────────────────────────
        if not completed:
            return await ctx.send("No pets were created.")

        summ = discord.Embed(
            title="🎉 Batch splice complete",
            description=f"{len(completed)} pet(s) created.",
            color=0x00FF00,
        )
        for pid, p in completed:
            summ.add_field(
                name=p['name'], value=f"ID `{pid}` • owner <@{p['user_id']}>", inline=True
            )
        await ctx.send(embed=summ)



    @commands.command(hidden=True)
    @commands.is_owner()
    async def process_splice(self, ctx, splice_id: int = None):
        """Process a splice request (owner only)"""
        try:
            if not splice_id:
                # List pending splice requests
                async with self.bot.pool.acquire() as conn:
                    splices = await conn.fetch(
                        """
                        SELECT 
                            id, user_id, pet1_name, pet2_name, 
                            pet1_default, pet2_default, created_at,
                            pet1_url, pet2_url, temp_name
                        FROM splice_requests 
                        WHERE status = 'pending' 
                        ORDER BY created_at ASC
                        """
                    )

                if not splices:
                    return await ctx.send("No pending splice requests.")
                
                # Create and start the paginator
                paginator = SpliceRequestPaginator(ctx, splices)
                await paginator.start()
                return
        except Exception as e:
            await ctx.send(f"Error: {e}")
    
    @commands.command(hidden=True)
    @commands.is_owner()
    async def process_splice(self, ctx, splice_id: int = None):
        """Process a splice request (owner only)"""
        try:
            if not splice_id:
                # List pending splice requests
                async with self.bot.pool.acquire() as conn:
                    splices = await conn.fetch(
                        """
                        SELECT 
                            id, user_id, pet1_name, pet2_name, 
                            pet1_default, pet2_default, created_at,
                            pet1_url, pet2_url, temp_name
                        FROM splice_requests 
                        WHERE status = 'pending' 
                        ORDER BY created_at ASC
                        """
                    )

                if not splices:
                    return await ctx.send("No pending splice requests.")
                
                # Create and start the paginator
                paginator = SpliceRequestPaginator(ctx, splices)
                await paginator.start()
                return
        except Exception as e:
            await ctx.send(f"Error: {e}")


        # Get splice request details
        async with self.bot.pool.acquire() as conn:
            splice = await conn.fetchrow(
                "SELECT * FROM splice_requests WHERE id = $1 AND status = 'pending'",
                splice_id
            )

        if not splice:
            return await ctx.send(f"No pending splice request found with ID {splice_id}.")

        # Send information about the splice
        embed = discord.Embed(
            title=f"Process Splice #{splice['id']}",
            description=f"User: {self.bot.get_user(splice['user_id']) or splice['user_id']}\n"
                        f"Pets: {splice['pet1_name']} + {splice['pet2_name']}\n"
                        f"Default Names: {splice['pet1_default']} + {splice['pet2_default']}\n"
                        f"Suggested Name: {splice['temp_name']}",
            color=0x00ff00
        )

        embed.add_field(name="Pet 1 Stats",
                        value=f"HP: {splice['pet1_hp']}, ATK: {splice['pet1_attack']}, DEF: {splice['pet1_defense']}, Element: {splice['pet1_element']}\nURL: {splice['pet1_url']}",
                        inline=True)
        embed.add_field(name="Pet 2 Stats",
                        value=f"HP: {splice['pet2_hp']}, ATK: {splice['pet2_attack']}, DEF: {splice['pet2_defense']}, Element: {splice['pet2_element']}\nURL: {splice['pet2_url']}",
                        inline=True)

        await ctx.send(embed=embed)

        # Start the interactive creation process
        await ctx.send("Please enter a name for the spliced creature:")

        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            name_msg = await self.bot.wait_for('message', check=check, timeout=60)
            new_name = name_msg.content.strip()
            
            # Get both pets' stats for suggestion calculation
            pet1_hp = splice['pet1_hp']
            pet1_attack = splice['pet1_attack']
            pet1_defense = splice['pet1_defense']
            pet2_hp = splice['pet2_hp']
            pet2_attack = splice['pet2_attack']
            pet2_defense = splice['pet2_defense']
            
            # Function to calculate stats that are slightly under the max parent stat
            def calc_slightly_under(stat1, stat2, max_allowed=1500):
                # Get the effective max (respecting the original stat if it exceeds max_allowed)
                effective_max = max(stat1, stat2)
                cap = effective_max if effective_max > max_allowed else max_allowed
                
                # Calculate a value slightly under the max (90-99% of max)
                under_percentage = random.uniform(0.90, 0.99)
                suggested = int(effective_max * under_percentage)
                
                # Ensure we don't exceed the cap
                return min(suggested, cap)
            
            # Function to calculate a stat that slightly exceeds the max parent stat
            def calc_slightly_over(stat1, stat2, max_allowed=1500):
                # Get the effective max (respecting the original stat if it exceeds max_allowed)
                effective_max = max(stat1, stat2)
                cap = effective_max if effective_max > max_allowed else max_allowed
                
                # Calculate a value slightly over the max (1-15% boost)
                over_percentage = random.uniform(1.01, 1.15)
                suggested = int(effective_max * over_percentage)
                
                # Ensure we don't exceed the cap
                return min(suggested, cap)
            
            # Check if this is a destabilized creature
            is_destabilised = "[DESTABILISED]" in new_name
            
            if is_destabilised:
                # For destabilized pets, all stats are severely reduced (10-30% of parent max)
                def calc_destabilised(stat1, stat2):
                    effective_max = max(stat1, stat2)
                    reduction = random.uniform(0.10, 0.30)  # 10-30% of original
                    return int(effective_max * reduction)
                
                suggested_hp = calc_destabilised(pet1_hp, pet2_hp)
                suggested_attack = calc_destabilised(pet1_attack, pet2_attack)
                suggested_defense = calc_destabilised(pet1_defense, pet2_defense)
                
                # Add warning about destabilized status
                destabilised_warning = "⚠️ **DESTABILIZED GENETIC STRUCTURE DETECTED** ⚠️\nThe forging process has encountered severe arcane instability! The resulting creature will manifest with diminished capabilities."
            else:
                # Define 1.5k cap for normal stats
                standard_cap = 1500
                
                # Calculate stats based on 60/40 chance
                random_chance = random.random()
                
                # Helper functions for the two different calculation methods
                def calc_averaged_stats(stat1, stat2):
                    """60% chance: Calculate stats close to parents' strongest stats within reason"""
                    max_stat = max(stat1, stat2)
                    
                    # Always respect the hard cap of 1500
                    if max_stat > standard_cap:
                        # Calculate a weighted average favoring the higher stat
                        average = (stat1 + stat2) / 2
                        # Add 5-10% to the average
                        boost = random.uniform(1.05, 1.10)
                        # Apply but ensure it doesn't exceed the cap
                        return min(int(average * boost), standard_cap)
                    else:
                        # Otherwise, stay close to the stronger parent within the cap
                        close_percentage = random.uniform(0.92, 0.98)  # 92-98% of max
                        return min(int(max_stat * close_percentage), standard_cap)

# ... (rest of the code remains the same)
                def calc_one_boosted(stat1, stat2, boost_this=False):
                    """40% chance: One stat higher than parent, others slightly lower"""
                    max_stat = max(stat1, stat2)
                    
                    # For the boosted stat - ALWAYS respect the absolute 1500 cap
                    if boost_this:
                        # Calculate boosted value
                        boost = random.uniform(1.02, 1.07)  # 2-7% boost
                        boosted_value = int(max_stat * boost)
                        # Strict enforcement of 1500 cap regardless of parent stats
                        return min(boosted_value, standard_cap)
                    # For non-boosted stats
                    else:
                        # Slightly lower than max parent
                        lower_percentage = random.uniform(0.85, 0.95)  # 85-95% of max
                        # Still respect the cap, though this should always be under it
                        return min(int(max_stat * lower_percentage), standard_cap)
                
                # Apply the appropriate calculation based on random chance
                if random_chance < 0.60:  # 60% chance
                    # All stats close to parents' strongest stats
                    suggested_hp = calc_averaged_stats(pet1_hp, pet2_hp)
                    suggested_attack = calc_averaged_stats(pet1_attack, pet2_attack)
                    suggested_defense = calc_averaged_stats(pet1_defense, pet2_defense)
                    calc_method = "✨ The forge has analyzed both genetic structures and created a balanced splice."
                else:  # 40% chance
                    # One stat will be higher than parent
                    exceed_stat = random.choice(['hp', 'attack', 'defense'])
                    
                    if exceed_stat == 'hp':
                        suggested_hp = calc_one_boosted(pet1_hp, pet2_hp, True)
                        suggested_attack = calc_one_boosted(pet1_attack, pet2_attack, False)
                        suggested_defense = calc_one_boosted(pet1_defense, pet2_defense, False)
                        calc_method = "⚡ The forge has enhanced this creature's vitality essence! Stronger HP potential detected."
                    elif exceed_stat == 'attack':
                        suggested_hp = calc_one_boosted(pet1_hp, pet2_hp, False)
                        suggested_attack = calc_one_boosted(pet1_attack, pet2_attack, True)
                        suggested_defense = calc_one_boosted(pet1_defense, pet2_defense, False)
                        calc_method = "⚡ The forge has enhanced this creature's offensive essence! Stronger Attack potential detected."
                    else:  # defense
                        suggested_hp = calc_one_boosted(pet1_hp, pet2_hp, False)
                        suggested_attack = calc_one_boosted(pet1_attack, pet2_attack, False)
                        suggested_defense = calc_one_boosted(pet1_defense, pet2_defense, True)
                        calc_method = "⚡ The forge has enhanced this creature's defensive essence! Stronger Defense potential detected."
                
                # No warning needed for normal splices
                destabilised_warning = None
            
            # Create functions to generate different types of suggestions
            def generate_balanced_stats():
                """Generate balanced stats (close to parents' strongest stats)"""
                hp = calc_averaged_stats(pet1_hp, pet2_hp)
                attack = calc_averaged_stats(pet1_attack, pet2_attack)
                defense = calc_averaged_stats(pet1_defense, pet2_defense)
                method = "✨ The forge has analyzed both genetic structures and created a balanced splice."
                return hp, attack, defense, method
                
            def generate_specialized_stats(boost_stat=None):
                """Generate specialized stats with one boosted stat"""
                if boost_stat is None:
                    boost_stat = random.choice(['hp', 'attack', 'defense'])
                    
                if boost_stat == 'hp':
                    hp = calc_one_boosted(pet1_hp, pet2_hp, True)
                    attack = calc_one_boosted(pet1_attack, pet2_attack, False)
                    defense = calc_one_boosted(pet1_defense, pet2_defense, False)
                    method = "⚡ The forge has enhanced this creature's vitality essence! Stronger HP potential detected."
                elif boost_stat == 'attack':
                    hp = calc_one_boosted(pet1_hp, pet2_hp, False)
                    attack = calc_one_boosted(pet1_attack, pet2_attack, True)
                    defense = calc_one_boosted(pet1_defense, pet2_defense, False)
                    method = "⚡ The forge has enhanced this creature's offensive essence! Stronger Attack potential detected."
                else:  # defense
                    hp = calc_one_boosted(pet1_hp, pet2_hp, False)
                    attack = calc_one_boosted(pet1_attack, pet2_attack, False)
                    defense = calc_one_boosted(pet1_defense, pet2_defense, True)
                    method = "⚡ The forge has enhanced this creature's defensive essence! Stronger Defense potential detected."
                    
                return hp, attack, defense, method
            
            # Initial suggestion generation based on 60/40 chance for normal pets
            if is_destabilised:
                # For destabilized pets, all stats are severely reduced (10-30% of parent max)
                def calc_destabilised(stat1, stat2):
                    effective_max = max(stat1, stat2)
                    reduction = random.uniform(0.10, 0.30)  # 10-30% of original
                    return int(effective_max * reduction)
                
                suggested_hp = calc_destabilised(pet1_hp, pet2_hp)
                suggested_attack = calc_destabilised(pet1_attack, pet2_attack)
                suggested_defense = calc_destabilised(pet1_defense, pet2_defense)
                
                # Add warning about destabilized status
                calc_method = "⚠️ **DESTABILIZED GENETIC STRUCTURE DETECTED** ⚠️\nThe forging process has encountered severe arcane instability! The resulting creature will manifest with diminished capabilities."
                can_switch_method = False  # Can't switch for destabilized pets
            else:
                # Normal pet, start with random method based on 60/40 chance
                if random.random() < 0.60:  # 60% chance for balanced
                    suggested_hp, suggested_attack, suggested_defense, calc_method = generate_balanced_stats()
                    current_method = "balanced"
                else:  # 40% chance for specialized
                    suggested_hp, suggested_attack, suggested_defense, calc_method = generate_specialized_stats()
                    current_method = "specialized"
                can_switch_method = True
                
            # Interactive stat suggestion loop
            suggestion_accepted = False
            custom_stats = False
            
            while not suggestion_accepted:
                # Show suggestions to the user
                embed_color = 0xDD2222 if is_destabilised else 0x9C44DC  # Red for destabilized, purple for normal
                
                description = "Based on the parent pets, here are the suggested stats for your spliced pet:"
                if 'calc_method' in locals():
                    description = f"**{calc_method}**\n\n{description}"
                    
                suggestion_embed = discord.Embed(
                    title=f"Suggested Stats for {new_name}",
                    description=description,
                    color=embed_color
                )
                
                suggestion_embed.add_field(
                    name="Parent 1 Stats",
                    value=f"HP: {pet1_hp}\nAttack: {pet1_attack}\nDefense: {pet1_defense}",
                    inline=True
                )
                
                suggestion_embed.add_field(
                    name="Parent 2 Stats",
                    value=f"HP: {pet2_hp}\nAttack: {pet2_attack}\nDefense: {pet2_defense}",
                    inline=True
                )
                
                suggestion_embed.add_field(
                    name="Suggested Stats",
                    value=f"**HP**: {suggested_hp}\n**Attack**: {suggested_attack}\n**Defense**: {suggested_defense}",
                    inline=False
                )
                
                # Show appropriate options based on pet type
                if can_switch_method:
                    footer_text = "Commands: 'yes' (accept) | 'no' (custom) | 'reroll' | 'switch' (method) | 'boost hp/attack/defense'"
                else:
                    footer_text = "Commands: 'yes' (accept) | 'no' (custom) | 'reroll'"
                suggestion_embed.set_footer(text=footer_text)
                
                await ctx.send(embed=suggestion_embed)
                
                # Wait for user response
                response_msg = await self.bot.wait_for('message', check=check, timeout=60)
                response = response_msg.content.strip().lower()
                
                if response == 'yes':
                    # Use suggested stats
                    hp = suggested_hp
                    attack = suggested_attack
                    defense = suggested_defense
                    await ctx.send(f"Great! Using the suggested stats for {new_name}.")
                    suggestion_accepted = True
                elif response == 'no':
                    # Manual entry
                    await ctx.send(f"Enter HP value for {new_name} (adult form):")
                    hp_msg = await self.bot.wait_for('message', check=check, timeout=60)
                    hp = int(hp_msg.content.strip())
                    
                    await ctx.send(f"Enter attack value for {new_name} (adult form):")
                    attack_msg = await self.bot.wait_for('message', check=check, timeout=60)
                    attack = int(attack_msg.content.strip())
                    
                    await ctx.send(f"Enter defense value for {new_name} (adult form):")
                    defense_msg = await self.bot.wait_for('message', check=check, timeout=60)
                    defense = int(defense_msg.content.strip())
                    
                    suggestion_accepted = True
                    custom_stats = True
                elif response == 'reroll':
                    # Regenerate stats using same method
                    if is_destabilised:
                        suggested_hp = calc_destabilised(pet1_hp, pet2_hp)
                        suggested_attack = calc_destabilised(pet1_attack, pet2_attack)
                        suggested_defense = calc_destabilised(pet1_defense, pet2_defense)
                        await ctx.send("🎲 Recalculating destabilized genetic structure...")
                    elif current_method == "balanced":
                        suggested_hp, suggested_attack, suggested_defense, calc_method = generate_balanced_stats()
                        await ctx.send("🎲 Recalculating balanced splice...")
                    else:
                        suggested_hp, suggested_attack, suggested_defense, calc_method = generate_specialized_stats()
                        await ctx.send("🎲 Recalculating specialized splice...")
                elif response == 'switch' and can_switch_method:
                    # Switch between balanced and specialized methods
                    if current_method == "balanced":
                        suggested_hp, suggested_attack, suggested_defense, calc_method = generate_specialized_stats()
                        current_method = "specialized"
                        await ctx.send("🔄 Switching to specialized calculation...")
                    else:
                        suggested_hp, suggested_attack, suggested_defense, calc_method = generate_balanced_stats()
                        current_method = "balanced"
                        await ctx.send("🔄 Switching to balanced calculation...")
                elif response.startswith('boost ') and can_switch_method:
                    # Boost a specific stat
                    stat_to_boost = response.split(' ')[1]
                    if stat_to_boost in ['hp', 'attack', 'defense']:
                        suggested_hp, suggested_attack, suggested_defense, calc_method = generate_specialized_stats(stat_to_boost)
                        current_method = "specialized"
                        await ctx.send(f"🔆 Focusing splice on {stat_to_boost.upper()} enhancement...")
                    else:
                        await ctx.send("Invalid stat. Choose 'hp', 'attack', or 'defense'.")

            await ctx.send(f"Enter element for {new_name}:")
            element_msg = await self.bot.wait_for('message', check=check, timeout=60)
            element = element_msg.content.strip()

            await ctx.send(f"Enter image URL for {new_name} (or upload an image):")
            try:
                # Wait for response
                url_msg = await self.bot.wait_for('message', check=check, timeout=60)
                
                # If there's an attachment, process it as an upload
                if url_msg.attachments:
                    try:
                        # Initialize Firebase
                        cred = credentials.Certificate("acc.json")
                        if not firebase_admin._apps:
                            firebase_app = firebase_admin.initialize_app(cred)
                        else:
                            firebase_app = firebase_admin.get_app()

                        firebase_storage = storage.bucket("fablerpg-f74c2.appspot.com")
                        
                        attachment = url_msg.attachments[0]
                        if attachment.height:  # Verify it's an image
                            # Create user-specific filename
                            user_filename = f"{ctx.author.id}_{new_name}_{attachment.filename}"
                            
                            # Download image data
                            image_data = await attachment.read()
                            
                            # Ask if user wants to remove the background
                            await ctx.send("Do you want to remove the background from the image? (yes/no)")
                            bg_response_msg = await self.bot.wait_for('message', check=check, timeout=60)
                            remove_bg = bg_response_msg.content.strip().lower() == 'yes'
                            
                            # Remove background using PixelCut API if user wants it
                            if remove_bg:
                                # Ask for confirmation before proceeding with background removal
                                await ctx.send("Are you sure you want to remove the background? This process cannot be undone. (yes/no)")
                                confirm_bg_msg = await self.bot.wait_for('message', check=check, timeout=60)
                                confirm_bg = confirm_bg_msg.content.strip().lower() == 'yes'
                                
                                if not confirm_bg:
                                    await ctx.send("Background removal cancelled. Keeping original image with background.")
                                    remove_bg = False
                                
                                # Proceed with background removal if confirmed
                                if remove_bg:
                                    try:
                                        # First, upload the image to Firebase temporarily
                                        temp_filename = f"temp_{user_filename}"
                                        temp_blob = firebase_storage.blob(temp_filename)
                                        temp_blob.upload_from_string(image_data)
                                        
                                        # Make the blob publicly accessible
                                        temp_blob.make_public()
                                        
                                        # Get temporary public URL
                                        temp_url = temp_blob.public_url
                                        await ctx.send(f"Processing image for background removal...")
                                    
                                        # Call PixelCut API to remove background
                                        await ctx.send("Removing background from image...")
                                        pixelcut_api_key = ""
                                        pixelcut_url = "https://api.developer.pixelcut.ai/v1/remove-background"
                                        headers = {
                                            "Content-Type": "application/json",
                                            "Accept": "application/json",
                                            "X-API-KEY": pixelcut_api_key
                                        }
                                        
                                        # Prepare payload with json.dumps as required by the API
                                        payload_data = {
                                            "image_url": temp_url,
                                            "format": "png"
                                        }
                                        payload = json.dumps(payload_data)
                                        
                                        async with aiohttp.ClientSession() as session:
                                            async with session.post(pixelcut_url, headers=headers, data=payload) as response:
                                                if response.status == 200:
                                                    response_data = await response.json()
                                                    # Get the background-removed image URL
                                                    bg_removed_url = response_data.get("result_url")
                                                    
                                                    if bg_removed_url:
                                                        # Download the background-removed image
                                                        async with session.get(bg_removed_url) as img_response:
                                                            if img_response.status == 200:
                                                                # Replace the original image_data with background-removed image
                                                                image_data = await img_response.read()
                                                                await ctx.send("Background removed successfully!")
                                                            else:
                                                                await ctx.send(f"Failed to download background-removed image. Using original image instead.")
                                                    else:
                                                        await ctx.send(f"Background removal API didn't return an image URL. Using original image instead.")
                                                else:
                                                    await ctx.send(f"Background removal failed with status {response.status}. Using original image instead.")
                                        
                                        # Clean up temporary file
                                        temp_blob.delete()
                                    except Exception as e:
                                        await ctx.send(f"Background removal failed: {str(e)}. Using original image instead.")
                            else:
                                await ctx.send("Keeping original image with background.")
                            
                            # Upload the final image (either background-removed or original) to Firebase
                            blob = firebase_storage.blob(user_filename)
                            blob.upload_from_string(image_data)
                            blob.make_public()
                            
                            # Get public URL
                            url = blob.public_url
                            
                            await ctx.send(f"Image uploaded successfully!")
                        else:
                            await ctx.send("The attachment doesn't appear to be an image. Using as URL directly.")
                            url = url_msg.content.strip()
                    except Exception as e:
                        await ctx.send(f"Error uploading image: {e}. Please provide a URL instead.")
                        url_msg = await self.bot.wait_for('message', check=check, timeout=60)
                        url = url_msg.content.strip()
                else:
                    # Use the message content as URL
                    url = url_msg.content.strip()
            except asyncio.TimeoutError:
                await ctx.send("You took too long to respond.")
                return

            # Check for special conditions that might suggest stat increases
            is_special = "[SPECIAL]" in new_name
            max_stat = max(hp, attack, defense)
            
            # Initialize suggestions
            divine_suggestion = 0
            forge_suggestion = 0
            
            # Check for special conditions
            if is_special:
                divine_suggestion = random.randint(30, 50)
                forge_suggestion = random.randint(20, 40)
                await ctx.send(
                    f"🔮 **Special Creature Detected!** 🔮\n"
                    f"This unique being radiates with extraordinary energy. "
                    f"Suggested increases:\n"
                    f"- Divine Attention: +{divine_suggestion}%\n"
                    f"- Forge Damage: +{forge_suggestion}%"
                )
            # Check for high stats
            elif max_stat > 1200:
                divine_suggestion = random.randint(20, 50)
                forge_suggestion = random.randint(20, 50)
                await ctx.send(
                    f"🌟 **Exceptional Stats Detected!** 🌟\n"
                    f"This creature's power is remarkable. "
                    f"Suggested increases:\n"
                    f"- Divine Attention: +{divine_suggestion}%\n"
                    f"- Forge Damage: +{forge_suggestion}%"
                )
            elif max_stat > 800:
                divine_suggestion = random.randint(5, 20)
                forge_suggestion = random.randint(5, 20)
                await ctx.send(
                    f"✨ **Notable Stats Detected!** ✨\n"
                    f"This creature shows impressive potential. "
                    f"Suggested increases:\n"
                    f"- Divine Attention: +{divine_suggestion}%\n"
                    f"- Forge Damage: +{forge_suggestion}%"
                )

            # Get current values from database
            forge_condition = 100
            divine_attention = 0
            
            # Ask if they want to edit additional stats
            await ctx.send(f"Do you want to edit any additional stats? (yes/no)")
            edit_stats_msg = await self.bot.wait_for('message', check=check, timeout=60)
            edit_stats = edit_stats_msg.content.strip().lower() == 'yes'

            if edit_stats:
                # Get current forge condition value
                async with self.bot.pool.acquire() as conn:
                    current_forge = await conn.fetchrow(
                        "SELECT forge_condition, divine_attention FROM splicing_quest WHERE user_id = $1",
                        splice["user_id"]
                    )

                if current_forge:
                    forge_condition = current_forge["forge_condition"]
                    divine_attention = current_forge["divine_attention"]

                # Suggest forge damage increase with current and suggested values
                current_forge_damage = 100 - forge_condition
                suggested_forge_damage = min(100, current_forge_damage + forge_suggestion) if forge_suggestion > 0 else current_forge_damage
                await ctx.send(
                    f"Increase forge damage (current: {current_forge_damage}%"
                    f"{' (suggested: ' + str(suggested_forge_damage) + '%)' if forge_suggestion > 0 else ''}):"
                )
                forge_damage_msg = await self.bot.wait_for('message', check=check, timeout=60)
                try:
                    forge_damage = int(forge_damage_msg.content.strip())
                    forge_condition = max(0, 100 - forge_damage)  # Convert damage to condition
                except ValueError:
                    if forge_suggestion > 0 and forge_damage_msg.content.strip().lower() in ['suggested', 'suggest', 'yes', 'y']:
                        forge_condition = 100 - suggested_forge_damage
                    else:
                        await ctx.send("Invalid input. Using current forge condition.")
                
                # Suggest divine attention increase with current and suggested values
                suggested_divine = min(100, divine_attention + divine_suggestion) if divine_suggestion > 0 else divine_attention
                await ctx.send(
                    f"Increase divine attention (current: {divine_attention}%"
                    f"{' (suggested: ' + str(suggested_divine) + '%)' if divine_suggestion > 0 else ''}):"
                )
                divine_msg = await self.bot.wait_for('message', check=check, timeout=60)
                try:
                    divine_attention = int(divine_msg.content.strip())
                except ValueError:
                    if divine_suggestion > 0 and divine_msg.content.strip().lower() in ['suggested', 'suggest', 'yes', 'y']:
                        divine_attention = suggested_divine
                    else:
                        await ctx.send("Invalid input. Using current divine attention.")
            # Define growth stages
            growth_stages = {
                1: {"stage": "baby", "growth_time": 2, "stat_multiplier": 0.25, "hunger_modifier": 1.0},
                2: {"stage": "juvenile", "growth_time": 2, "stat_multiplier": 0.50, "hunger_modifier": 0.8},
                3: {"stage": "young", "growth_time": 1, "stat_multiplier": 0.75, "hunger_modifier": 0.6},
                4: {"stage": "adult", "growth_time": None, "stat_multiplier": 1.0, "hunger_modifier": 0.0},
            }
            
            # Generate IVs using the allocate_iv_points method
            iv_percentage = random.uniform(40, 90)
            total_iv_points = (iv_percentage / 100) * 75  # Total IV points to distribute
            
            # Distribute IVs between stats
            hp_iv, attack_iv, defense_iv = await self.allocate_iv_points(total_iv_points)
            
            # Get the baby stage data
            baby_stage = growth_stages[1]
            stat_multiplier = baby_stage["stat_multiplier"]
            growth_time_interval = datetime.timedelta(days=baby_stage["growth_time"])
            growth_time = datetime.datetime.utcnow() + growth_time_interval
            
            # Calculate baby stats
            baby_hp = round(hp * stat_multiplier)
            baby_attack = round(attack * stat_multiplier)
            baby_defense = round(defense * stat_multiplier)
            
            # Apply IVs to baby stats
            baby_hp = baby_hp + hp_iv
            baby_attack = baby_attack + attack_iv
            baby_defense = baby_defense + defense_iv

            # Confirmation message with forge details
            confirm_msg = (f"Create spliced creature with these details?\n\n"
                           f"Name: {new_name}\n"
                           f"Adult HP: {hp} (Baby HP: {baby_hp})\n"
                           f"Adult Attack: {attack} (Baby Attack: {baby_attack})\n"
                           f"Adult Defense: {defense} (Baby Defense: {baby_defense})\n"
                           f"Element: {element}\n"
                           f"URL: {url}")

            if edit_stats:
                confirm_msg += f"\nForge Condition: {forge_condition}%\nDivine Attention: {divine_attention}%"

            confirmed = await ctx.confirm(confirm_msg)

            if not confirmed:
                return await ctx.send("Creation canceled.")

            # Generate a random IV percentage between 30% and 100% (or other logic as needed)
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
                # Fix: Make sure we set a valid IV percentage when value is 700 or higher
                iv_percentage = random.uniform(30, 50)
            # Still get the Firebase app if needed
            firebase_app = firebase_admin.get_app()

            firebase_storage = storage.bucket("fablerpg-f74c2.appspot.com")
            baby_defense = baby_defense + defense_iv

            # Create the spliced pet
            async with self.bot.pool.acquire() as conn:
                # Insert the new pet
                new_pet_id = await conn.fetchval(
                    """
                    INSERT INTO monster_pets 
                    (user_id, name, hp, attack, defense, element, default_name, url, growth_stage, growth_time, "IV") 
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) 
                    RETURNING id
                    """,
                    splice["user_id"],
                    new_name,
                    baby_hp,
                    baby_attack,
                    baby_defense,
                    element,
                    new_name,
                    url,
                    'baby',
                    growth_time,
                    iv_percentage
                )

                # Update the splice request status
                await conn.execute(
                    "UPDATE splice_requests SET status = 'completed' WHERE id = $1",
                    splice_id
                )

                # Update forge condition and divine attention if they were edited
                if edit_stats:
                    await conn.execute(
                        'UPDATE splicing_quest SET forge_condition = $1, divine_attention = $2 WHERE user_id = $3',
                        forge_condition, divine_attention, splice["user_id"]
                    )

                # Store the combination for future automatic splices
                await conn.execute(
                    """
                    INSERT INTO splice_combinations 
                    (pet1_default, pet2_default, result_name, hp, attack, defense, element, url) 
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    splice["pet1_default"],
                    splice["pet2_default"],
                    new_name,
                    hp,  # Store adult stats
                    attack,
                    defense,
                    element,
                    url
                )

                # Find and process any other pending requests with the same pet combination
                pending_requests = await conn.fetch(
                    """
                    SELECT * FROM splice_requests 
                    WHERE status = 'pending' AND 
                    ((pet1_default = $1 AND pet2_default = $2) OR (pet1_default = $2 AND pet2_default = $1))
                    AND id != $3
                    """,
                    splice["pet1_default"], splice["pet2_default"], splice_id
                )

                # Process each pending request
                for pending in pending_requests:
                    # Generate random IVs for this user
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
                        # This one was already set correctly
                        iv_percentage = random.uniform(30, 50)

                    total_iv_points = (iv_percentage / 100) * 100
                    pending_hp_iv, pending_attack_iv, pending_defense_iv = await self.allocate_iv_points(total_iv_points)

                    this_baby_hp = round(hp * stat_multiplier) + pending_hp_iv
                    this_baby_attack = round(attack * stat_multiplier) + pending_attack_iv
                    this_baby_defense = round(defense * stat_multiplier) + pending_defense_iv

                    # Create pet for this user
                    await conn.execute(
                        """
                        INSERT INTO monster_pets 
                        (user_id, name, hp, attack, defense, element, default_name, url, growth_stage, growth_time, "IV") 
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        """,
                        pending["user_id"],
                        new_name,
                        this_baby_hp,
                        this_baby_attack,
                        this_baby_defense,
                        element,
                        new_name,
                        url,
                        'baby',
                        datetime.datetime.utcnow() + growth_time_interval,
                        iv_percentage
                    )

                    # Mark request as completed
                    await conn.execute(
                        "UPDATE splice_requests SET status = 'completed' WHERE id = $1",
                        pending["id"]
                    )

                    # Prepare notification message for pending users
                    pending_notification_msg = f"Congratulations! Your pets have successfully been spliced into a new creature: **{new_name}**! Check your pets with `$pets`."

                    # Notify user
                    pending_user = self.bot.get_user(pending["user_id"])
                    if pending_user:
                        await pending_user.send(pending_notification_msg)

                    # Let the admin know about these auto-processed requests
                    await ctx.send(
                        f"Also auto-processed splice request #{pending['id']} for user {pending['user_id']} with the same pet combination.")

            # Prepare notification message
            notification_msg = f"Congratulations! Your pets have successfully been spliced into a new creature: **{new_name}**! Check your pets with `$pets`."

            # Add special effects based on forge condition and divine attention if they were edited
            if edit_stats:
                if forge_condition < 50:
                    notification_msg += f"\n\nThe forge was stressed during the splice, operating at only {forge_condition}% capacity!"
                if divine_attention > 30:
                    notification_msg += f"\n\nSky storms were observed during the splicing process, with {divine_attention}% divine intervention!"

            # Notify the original user
            user = self.bot.get_user(splice["user_id"])
            if user:
                await user.send(notification_msg)

            await ctx.send(f"Successfully created spliced creature {new_name} for user {splice['user_id']}!")

        except asyncio.TimeoutError:
            await ctx.send("Creation process timed out.")
        except ValueError:
            await ctx.send("Invalid input. Please provide valid numbers for stats.")
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")



async def setup(bot):
    await bot.add_cog(ProcessSplice(bot))

    
