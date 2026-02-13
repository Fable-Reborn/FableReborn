import datetime
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

class SpliceStatusPaginator(discord.ui.View):
    """A paginator for splice status entries using a dropdown menu for navigation"""
    
    def __init__(self, ctx, splices, splices_per_page=8):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.splices = splices
        self.splices_per_page = splices_per_page
        self.current_page = 0
        self.total_pages = max(1, (len(splices) + splices_per_page - 1) // splices_per_page)
        self.message = None
        
        # Add page select dropdown if multiple pages
        if self.total_pages > 1:
            self.add_page_selector()
            
    def add_page_selector(self):
        """Add a dropdown menu for page selection"""
        select = discord.ui.Select(placeholder=f"Page Selection (1-{self.total_pages})")
        
        for i in range(self.total_pages):
            page_num = i + 1
            start_idx = i * self.splices_per_page
            end_idx = min((i + 1) * self.splices_per_page - 1, len(self.splices) - 1)
            select.add_option(
                label=f"Page {page_num}", 
                value=str(i),
                description=f"Splices {start_idx + 1}-{end_idx + 1}"
            )
            
        async def select_callback(interaction):
            if interaction.user.id != self.ctx.author.id:
                return await interaction.response.send_message("This isn't your splice status menu.", ephemeral=True)
            
            self.current_page = int(interaction.data["values"][0])
            await interaction.response.defer()
            await self.update_page()
            
        select.callback = select_callback
        self.add_item(select)
    
    def get_current_page_embed(self):
        """Generate the embed for the current page"""
        start_idx = self.current_page * self.splices_per_page
        end_idx = min((self.current_page + 1) * self.splices_per_page, len(self.splices))
        current_splices = self.splices[start_idx:end_idx]
        
        embed = discord.Embed(
            title="Your Splice Requests",
            description="Here are your recent splice requests:",
            color=0x00ff00
        )
        
        if self.total_pages > 1:
            embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages}")
            
        for splice in current_splices:
            status_emoji = "🕒" if splice["status"] == "pending" else "✅"
            embed.add_field(
                name=f"ID: {splice['id']} {status_emoji}",
                value=f"{splice['pet1_name']} + {splice['pet2_name']}\nStatus: {splice['status'].capitalize()}\nRequested: {splice['created_at'].strftime('%Y-%m-%d %H:%M')}\n",
                inline=False
            )
            
        return embed
    
    async def start(self):
        """Send the initial paginator message"""
        self.message = await self.ctx.send(embed=self.get_current_page_embed(), view=self)
        return self.message
    
    async def update_page(self):
        """Update the message with the current page"""
        await self.message.edit(embed=self.get_current_page_embed(), view=self)
    
    async def interaction_check(self, interaction):
        """Ensure only the command author can interact with the paginator"""
        return interaction.user.id == self.ctx.author.id
    
    async def on_timeout(self):
        """When the view times out, remove all interactable components"""
        if self.message:
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)


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


class LoreView(View):
    def __init__(self, pages, user_id):
        super().__init__(timeout=300)
        self.pages = pages
        self.current_page = 0
        self.user_id = user_id
        self.update_buttons()
        
    def update_buttons(self):
        self.clear_items()
        prev_button = Button(style=discord.ButtonStyle.secondary, emoji="◀️", disabled=self.current_page == 0)
        prev_button.callback = self.prev_callback
        
        next_button = Button(style=discord.ButtonStyle.secondary, emoji="▶️", disabled=self.current_page >= len(self.pages)-1)
        next_button.callback = self.next_callback
        
        self.add_item(prev_button)
        self.add_item(Button(style=discord.ButtonStyle.gray, label=f"{self.current_page+1}/{len(self.pages)}", disabled=True))
        self.add_item(next_button)
    
    async def interaction_check(self, interaction):
        return interaction.user.id == self.user_id
    
    async def prev_callback(self, interaction):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    async def next_callback(self, interaction):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

class MorriganConversationView(View):
    def __init__(self, cog, ctx, player_data):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.player_data = player_data
        self.add_conversation_buttons()
        
    def add_conversation_buttons(self):
        # Add lore topic buttons
        wyrdweavers_button = Button(style=discord.ButtonStyle.primary, label="The Rise & Fall of Wyrdweavers", custom_id="wyrdweavers")
        wyrdweavers_button.callback = self.wyrdweavers_callback
        self.add_item(wyrdweavers_button)
        
        battletower_button = Button(style=discord.ButtonStyle.primary, label="The Truth of Battle Tower", custom_id="battletower")
        battletower_button.callback = self.battletower_callback
        self.add_item(battletower_button)
        
        gods_button = Button(style=discord.ButtonStyle.primary, label="The Three Divine Powers", custom_id="gods")
        gods_button.callback = self.gods_callback
        self.add_item(gods_button)
        
        creatures_button = Button(style=discord.ButtonStyle.primary, label="The Creatures of Fable", custom_id="creatures")
        creatures_button.callback = self.creatures_callback
        self.add_item(creatures_button)
        
        # Add quest completion button if requirements met
        if (self.player_data["shards"] >= 10 and 
            self.player_data["primer"] and 
            self.player_data["money"] >= 2500000 and 
            not self.player_data["forge_built"]):
            complete_button = Button(style=discord.ButtonStyle.success, label="Begin the Forge Ritual", custom_id="complete")
            complete_button.callback = self.complete_callback
            self.add_item(complete_button)
        
        # Add exit button
        exit_button = Button(style=discord.ButtonStyle.danger, label="End Conversation", custom_id="exit")
        exit_button.callback = self.exit_callback
        self.add_item(exit_button)
    
    async def interaction_check(self, interaction):
        return interaction.user.id == self.ctx.author.id
    
    async def wyrdweavers_callback(self, interaction):
        await interaction.response.defer()
        pages = self.cog.create_wyrdweavers_lore(self.player_data)
        view = LoreView(pages, self.ctx.author.id)
        await interaction.followup.send(embed=pages[0], view=view)
    
    async def battletower_callback(self, interaction):
        await interaction.response.defer()
        pages = self.cog.create_battletower_lore(self.player_data)
        view = LoreView(pages, self.ctx.author.id)
        await interaction.followup.send(embed=pages[0], view=view)
    
    async def gods_callback(self, interaction):
        await interaction.response.defer()
        pages = self.cog.create_gods_lore(self.player_data)
        view = LoreView(pages, self.ctx.author.id)
        await interaction.followup.send(embed=pages[0], view=view)
    
    async def creatures_callback(self, interaction):
        await interaction.response.defer()
        pages = self.cog.create_creatures_lore(self.player_data)
        view = LoreView(pages, self.ctx.author.id)
        await interaction.followup.send(embed=pages[0], view=view)
    
    async def complete_callback(self, interaction):
        await interaction.response.defer()
        await self.cog.forgesoulforge(self.ctx)
    
    async def exit_callback(self, interaction):
        await interaction.response.defer()
        await interaction.followup.send("*Morrigan's eyes gleam one final time before she dissolves into shadow, her voice lingering in the air: \"The ancient knowledge awaits when you are ready to seek it again...\"*")

class Soulforge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        ids_section = getattr(self.bot.config, "ids", None)
        soulforge_ids = getattr(ids_section, "soulforge", {}) if ids_section else {}
        if not isinstance(soulforge_ids, dict):
            soulforge_ids = {}
        self.splice_admin_user_id = soulforge_ids.get("splice_admin_user_id")
        
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

    @commands.command()
    @user_cooldown(30)
    async def soulforge(self, ctx):
        """Begin your journey into the forbidden art of soul splicing"""
        try:
            player_data = await self.get_player_data(ctx.author.id)
            
            if not player_data:
                return await ctx.send("You must create a character first!")
            
            player_name = player_data["name"]
            player_god = player_data.get("god") or "mysterious god"  # Fixed to handle None values
            
            if not player_data["quest_started"]:
                # First encounter with the mysterious Raven
                pages = self.create_first_encounter_pages(player_name, player_god)
                view = LoreView(pages, ctx.author.id)
                await ctx.send(embed=pages[0], view=view)
                
                # Initialize quest in database
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        '''INSERT INTO splicing_quest 
                        (user_id, shards_collected, primer_found, crucible_built) 
                        VALUES ($1, 0, FALSE, FALSE)''',
                        ctx.author.id
                    )
                return
                
            # Player has already started the quest
            if player_data["forge_built"]:
                return await self.display_active_forge(ctx, player_data)
                
            # Show quest progress and offer to speak with Morrigan
            await self.display_quest_status(ctx, player_data)

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    async def display_quest_status(self, ctx, player_data):
        """Shows current quest progress and offers to speak with Morrigan"""
        name = player_data["name"]
        shards = player_data["shards"]
        primer = player_data["primer"]
        money = player_data["money"]
        
        # Progress indicators
        shard_progress = "🟣" * shards + "⚫" * (10 - shards)
        primer_status = "✅" if primer else "❌"
        gold_status = "✅" if money >= 2500000 else "❌"
        
        embed = discord.Embed(
            title="🔮 The Wyrdweaver's Path 🔮",
            description=f"The raven Morrigan appears in a swirl of shadows, golden eyes fixed upon {name}.",
            color=0x7d2aad
        )
        
        embed.add_field(
            name="Your Progress",
            value=f"**Eidolith Shards:** {shards}/10 [{shard_progress}]\n**Alchemist's Primer:** {primer_status}\n**Gold (2.5M):** {gold_status} ({money:,} gold available)",
            inline=False
        )
        
        # Status message based on progress
        if shards < 10 and not primer:
            status = f"*\"Your journey has barely begun, {name}. The shards await discovery in the bodies of powerful creatures, while the Primer hides in a place of ancient knowledge. Seek both with determination.\"*"
        elif shards < 10:
            status = f"*\"The Primer recognizes you as worthy, {name}, but the forge requires more essence. Continue to battle powerful monsters - listen for the crystalline song of shards calling to you.\"*"
        elif not primer:
            status = f"*\"The shards you've gathered resonate beautifully, {name}, but without the Primer's guiding knowledge, they are merely pretty trinkets. The tome awaits in a place of forgotten power.\"*"
        elif money < 2500000:
            status = f"*\"Knowledge and essence we have, {name}, but creation demands material sacrifice. Gather wealth sufficient to commission the Soulforge's construction. The wait has been centuries - patience for a few more days seems reasonable.\"*"
        else:
            status = f"*\"Everything is prepared, {name}! The time has come to rebuild the Soulforge and reclaim the ancient art. Speak with me to begin the ritual that will forever change your path.\"*"
            
        embed.add_field(name="Morrigan's Assessment", value=status, inline=False)
        embed.add_field(
            name="Next Steps", 
            value="Use `$speaktomorrigan` to learn the ancient lore and ask questions about the Wyrdweavers, the Battle Tower's secrets, the Divine Council, and the creatures of Fable.",
            inline=False
        )
        
        await ctx.send(embed=embed)


    @commands.command()
    @user_cooldown(60)
    async def speaktomorrigan(self, ctx):
        """Speak with Morrigan about the ancient lore of Fable"""
        player_data = await self.get_player_data(ctx.author.id)
        
        if not player_data or not player_data["quest_started"]:
            return await ctx.send("You have not begun the Wyrdweaver's path. Use `$soulforge` to start your journey.")
        
        name = player_data["name"]
        god = player_data["god"].lower()
        
        # Create initial greeting based on player's god
        if "drakath" in god or "chaos" in god:
            greeting = f"*\"Ah, {name}, disciple of Chaos itself. How fitting that you seek to unravel the ordered boundaries between beings. Drakath must be pleased to see his follower dabble in transformation.\"*"
        elif "asterea" in god or "light" in god:
            greeting = f"*\"Greetings, {name}, child of the Light. Does Asterea know her faithful one consorts with forbidden knowledge? Perhaps she understands that creation requires both light and shadow.\"*"
        elif "sepulchure" in god or "dark" in god:
            greeting = f"*\"Well met, {name}. Sepulchure's shadow falls long over your path. The Dark One appreciates the power of binding souls to new purpose - it is not so different from his own... experiments.\"*"
        else:
            greeting = f"*\"Welcome back, {name}. The ancient knowledge awaits your questions.\"*"
        
        embed = discord.Embed(
            title="🦅 Morrigan Awaits Your Questions 🦅",
            description=f"The raven materializes on a nearby perch, regarding you with intelligent eyes that hold memories spanning centuries.",
            color=0x3d2b3d
        )
        embed.add_field(
            name="The Raven Speaks",
            value=greeting + "\n\n*\"What knowledge do you seek today? The past contains many secrets, not all of them comforting.\"*",
            inline=False
        )
        
        # Quest status
        if not player_data["forge_built"]:
            shards = player_data["shards"]
            primer = player_data["primer"]
            money = player_data["money"]
            
            shard_progress = "🟣" * shards + "⚫" * (10 - shards)
            primer_status = "✅" if primer else "❌"
            gold_status = "✅" if money >= 2500000 else "❌"
            
            embed.add_field(
                name="Your Progress",
                value=f"**Eidolith Shards:** {shards}/10 [{shard_progress}]\n**Alchemist's Primer:** {primer_status}\n**Gold (2.5M):** {gold_status} ({money:,} gold available)",
                inline=False
            )
        
        view = MorriganConversationView(self, ctx, player_data)
        await ctx.send(embed=embed, view=view)

    def create_first_encounter_pages(self, player_name, player_god):
        """Creates the initial lore pages when a player discovers the soulforge quest"""
        pages = []
        
        # Page 1: The Dream
        embed = discord.Embed(
            title="🌃 A Dreadful Dream 🌃",
            description=f"The night after your latest adventure, your sleep is troubled by visions...",
            color=0x2b1d30
        )
        embed.add_field(
            name="Shattered Forms",
            value=f"You stand atop a mountain of broken statues. Each fragment pulses with a faint light, and whispers fill your mind with forgotten knowledge. A voice calls to you:\n\n*\"Mortal child of {player_god}, the world you know is built upon corpses of greater beings.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 2: The Raven Appears
        embed = discord.Embed(
            title="🦅 The Midnight Messenger 🦅",
            description="You jolt awake to find a raven perched at your window, its eyes unnaturally intelligent. Moonlight catches on something metallic embedded in its feathers—tiny gears and fragments of crystal.",
            color=0x3d2b3d
        )
        embed.add_field(
            name="Morrigan Speaks",
            value=f"*\"I am Morrigan, last servant of the Wyrdweavers. For centuries I have sought one who might restore what was broken.\"*\n\nThe raven tilts its head, studying you with golden eyes that reflect no light.\n\n*\"{player_name}, you bear the mark of one who can hear the Eidolith's song. The forgotten essence calls to you through the veil of time.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 3: The History Lesson
        embed = discord.Embed(
            title="📜 The Forbidden History 📜",
            description="The raven's voice changes, becoming dozens of voices speaking in unison—old and young, male and female, all speaking with reverent dread...",
            color=0x4a3b5d
        )
        embed.add_field(
            name="The Eidolons",
            value="*\"Before gods, before mortals, there existed the Eidolons - perfect embodiments of nature's forces. They were neither alive nor dead, but pure essence given form. The Fire Eidolon danced across continents, leaving volcanic ranges in its wake. The Ocean Eidolon's thoughts were the tides, its memory the abyssal depths.\"*\n\n*\"When Drakath, Asterea, and Sepulchure warred for dominion, the Eidolons were shattered, their essence scattered into all living things. What mortals call 'souls' are merely fragments of these greater beings—like shards of a broken mirror, each reflecting a tiny portion of a greater whole.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 4: The Wyrdweavers
        embed = discord.Embed(
            title="⚗️ The Soul Alchemists ⚗️",
            description="Images flood your mind: robed figures working at strange forges filled with quicksilver, their hands tracing patterns that bend reality...",
            color=0x5d3a7a
        )
        embed.add_field(
            name="Forbidden Knowledge",
            value="*\"The Wyrdweavers discovered the truth. Led by the brilliant Vaedrith, they built great Soulforges to extract and recombine these fragments, creating new life forms of impossible design. Beasts with the essence of many creatures. Plants that could grow in the void. Metals that remembered their previous shapes.\"*\n\n*\"The gods, threatened by such power, destroyed the Wyrdweavers and scattered their knowledge. The divine jealously guard the power over souls—though they themselves merely inherited it from the shattered Eidolons. But fragments remain, waiting to be reforged.\"*",
            inline=False
        )
        pages.append(embed)
        
        embed = discord.Embed(
            title="🔮 Your Destiny Awaits 🔮",
            description="Morrigan fixes you with an expectant stare, her form seeming to grow larger in the moonlight.",
            color=0x6e4799
        )
        embed.add_field(
            name="The Path Forward",
            value=f"*\"To rebuild the Soulforge, you will need:\"*\n\n• 10 Eidolith Shards (crystals found in powerful creatures)\n• The Alchemist's Primer (a tome of forbidden knowledge that instructs the creation of the forge)\n• 2,500,000 gold to commission the forge's construction\n\n*\"The Alchemist's Primer can be uncovered through Adventure, Guild Adventure, or Battle Tower challenges. Eidolith Shards must be extracted from monsters throughout Fable, though not all creatures harbor these precious fragments of power.\"*\n\n*\"What say you, {player_name}? Will you walk the Wyrdweaver's path and reclaim what the gods sought to erase from history? Will you dare to reforge what was broken—to splice together what divine wrath tore asunder?\"*",
            inline=False
        )
        embed.set_footer(text="The raven awaits your decision... but it seems you've already made it.")
        pages.append(embed)
        
        return pages

    def create_quest_progress_pages(self, player_data):
        """Creates pages showing quest progress"""
        pages = []
        
        name = player_data["name"]
        shards = player_data["shards"]
        primer = player_data["primer"]
        money = player_data["money"]
        
        # Page 1: Quest Status
        embed = discord.Embed(
            title="🔍 The Wyrdweaver's Path 🔍",
            description=f"Morrigan appears, as if from nowhere, settling on a branch near you.",
            color=0x7d2aad
        )
        
        # Show progress with visual indicators
        shard_progress = "🟣" * shards + "⚫" * (10 - shards)
        primer_status = "✅" if primer else "❌"
        gold_status = "✅" if money >= 2500000 else "❌"
        
        embed.add_field(
            name="Requirements",
            value=f"**Eidolith Shards:** {shards}/10 [{shard_progress}]\n**Alchemist's Primer:** {primer_status}\n**Gold (2.5M):** {gold_status} ({money:,} gold available)",
            inline=False
        )
        
        # Contextual guidance based on progress
        if shards < 10 and not primer:
            guidance = f"*\"You must continue your hunt, {name}. The shards lurk within powerful beasts, while the Primer lies hidden in places of ancient magic. Both call to you... listen for their whispers.\"*"
        elif shards < 10:
            guidance = f"*\"The Primer hums with anticipation, {name}. Now you must complete your collection of Eidolith Shards. They are drawn to your battles - defeat mighty foes and listen for their crystalline song.\"*"
        elif not primer:
            guidance = f"*\"Your shards sing in harmony, {name}, but without the Primer's knowledge, they are merely pretty crystals. Seek ruins of unusual design or creatures of profound magic - the tome will call to its rightful wielder.\"*"
        elif money < 2500000:
            guidance = f"*\"All knowledge is gathered, {name}, but creation requires sacrifice. Amass the required wealth, and the Soulforge shall rise again. The wait has been centuries - what's a few more days to an immortal?\"*"
        else:
            guidance = f"*\"You have gathered all that is needed, {name}! The time has come to rebuild what was lost. Use the command `$forgesoulforge` to begin the ritual.\"*"
            
        embed.add_field(name="Morrigan's Guidance", value=guidance, inline=False)
        pages.append(embed)
        
        # Page 2: About Eidolith Shards
        embed = discord.Embed(
            title="💎 Eidolith Shards 💎",
            description="The crystallized fragments of shattered Eidolons.",
            color=0x57068c
        )
        embed.add_field(
            name="Nature of the Shards",
            value="*\"Each shard contains a fragment of the original Eidolon's essence. Fire shards burn with inner flame, earth shards pulse with deep rhythms, water shards flow within their crystalline prisons. They are not merely magical items but pieces of consciousness—memories and powers of beings that once shaped continents with their thoughts.\"*",
            inline=False
        )
        embed.add_field(
            name="Finding the Shards",
            value="*\"The shards are drawn to power. They embed themselves in mighty beasts and magical creatures, granting these beings unusual abilities. When such creatures are defeated, the shards may be released—usually found in their hearts, eyes, or brain.\"*\n\n*\"Bosses and elemental creatures have the highest chance of yielding these precious fragments. The Battle Tower, particularly, houses many shard-bearing entities.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 3: About the Alchemist's Primer
        embed = discord.Embed(
            title="📕 The Alchemist's Primer 📕",
            description="The last surviving tome of Wyrdweaver knowledge.",
            color=0x8c0606
        )
        embed.add_field(
            name="Nature of the Tome",
            value="*\"When the gods destroyed the Wyrdweavers, Archmagus Vaedrith encoded their knowledge into a single, semi-sentient book. Its pages shift and change, revealing different secrets depending on the reader's needs and worthiness. It contains the complete methodology of soul-splicing, from basic principles to the most advanced techniques.\"*\n\n*\"The book itself is bound in leather made from the skin of a metamorphic dragon, with pages of pressed silver and ink distilled from the essence of memory spirits. It hides itself from those unworthy and reveals itself only to those with the potential to restore the old ways.\"*",
            inline=False
        )
        embed.add_field(
            name="Finding the Primer",
            value="*\"The Primer is drawn to places of scholarly magic or ancient ruins. It may be found in the possession of powerful mages or hidden in forgotten libraries. Sometimes it disguises itself as a seemingly worthless book until touched by one who can hear the Eidolith's song.\"*\n\n*\"Listen for whispers of forbidden knowledge when exploring ancient places—particularly those predating the Divine Council's current configuration. The Battle Tower's deepest chambers sometimes yield such treasures to those who defeat its guardians.\"*",
            inline=False
        )
        pages.append(embed)
        
        return pages
        
    async def display_active_forge(self, ctx, player_data):
        """Displays interface for players who have built the Soulforge"""
        name = player_data["name"]
        god = player_data.get("god") or "mysterious god"  # Fixed to handle None values
        
        # Divine commentary based on player's god
        if "drakath" in god.lower() or "chaos" in god.lower():
            divine_note = "*The forge's patterns constantly shift as if influenced by Drakath's chaotic nature, never settling into a fixed form.*"
        elif "asterea" in god.lower() or "light" in god.lower():
            divine_note = "*Rays of golden light occasionally pierce through the forge's mercurial surface, as if Asterea herself watches your work with cautious curiosity.*"
        elif "sepulchure" in god.lower() or "dark" in god.lower():
            divine_note = "*Shadows gather unusually thick around the forge, occasionally forming what appears to be an approving smile—Sepulchure's distant acknowledgment of your power.*"
        else:
            divine_note = "*The forge pulses with power that predates the gods themselves, drawing strength from ancient foundations of reality.*"
        
        embed = discord.Embed(
            title="🧪 The Awakened Soulforge 🧪",
            description=f"Your Soulforge pulses with forbidden energy, awaiting your command. {divine_note}",
            color=0x4cc9f0
        )
        embed.add_field(
            name="Morrigan's Greeting",
            value=f"The raven materializes from the shadows, settling on the rim of the mercurial basin.\n\n*\"What shall we create today, {name}? Which souls shall we unite in your crucible of transformation? The possibilities are limited only by your imagination and courage.\"*",
            inline=False
        )
        embed.add_field(
            name="Available Commands",
            value="• `$splice [pet1] [pet2]` - Combine two of your pets into a new form\n• `$soullorebook` - Review the ancient knowledge of soul manipulation\n• `$speaktomorrigan` - Learn deeper secrets of Fable's past\n",
            inline=False
        )
        await ctx.send(embed=embed)


    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def forgesoulforge(self, ctx):
        """Begin the ritual to create your Soulforge"""
        player_data = await self.get_player_data(ctx.author.id)
        
        if not player_data or not player_data["quest_started"]:
            return await ctx.send("You have not yet begun the Wyrdweaver's path. Use `$soulforge` to start your journey.")
            
        if player_data["forge_built"]:
            return await ctx.send("You have already constructed the Soulforge. Use `$soulforge` to access it.")
            
        # Check requirements
        if player_data["shards"] < 10:
            return await ctx.send("*\"You have not gathered enough Eidolith Shards,\"* Morrigan caws. *\"The forge requires a full resonance. Each shard is a cornerstone of the structure we must build.\"*")
            
        if not player_data["primer"]:
            return await ctx.send("*\"Without the Alchemist's Primer, you would build merely a fancy cauldron,\"* Morrigan scoffs. *\"The tome contains the binding words and precise measurements. Find it first.\"*")
            
        if player_data["money"] < 2500000:
            return await ctx.send(f"*\"The forging requires great sacrifice,\"* Morrigan reminds you. *\"2,500,000 gold must be offered to the flames. The materials must be of the highest quality, and the craftsmanship beyond mortal standard.\"*")
            
        # All requirements met! Start the ritual
        forging_sequence = self.create_forging_sequence(player_data)
        view = LoreView(forging_sequence, ctx.author.id)
        await ctx.send(embed=forging_sequence[0], view=view)
        
        # Update database
        async with self.bot.pool.acquire() as conn:
            # Deduct gold
            await conn.execute(
                'UPDATE profile SET money = money - 2500000 WHERE profile.user = $1',
                ctx.author.id
            )
            # Mark forge as built and initialize new fields
            await conn.execute(
                'UPDATE splicing_quest SET crucible_built = TRUE, forge_condition = 100, divine_attention = 0 WHERE user_id = $1',
                ctx.author.id
            )

    def create_forging_sequence(self, player_data):
        """Creates the sequence of forging the Soulforge"""
        pages = []
        
        name = player_data["name"]
        god = player_data["god"]
        
        # Page 1: The Ritual Begins
        embed = discord.Embed(
            title="🌙 Ritual of Awakening 🌙",
            description="Under Morrigan's guidance, you travel to a secluded clearing beneath the twin moons of Fable.",
            color=0x1a0033
        )
        embed.add_field(
            name="Sacred Preparations",
            value=f"Following ancient diagrams from the Primer, you arrange your gold coins in a complex pattern that resembles a constellation not seen in the night sky for millennia. At specific points, you place the Eidolith Shards, which begin to pulse in rhythmic harmony like beating hearts.\n\n*\"The stars align,\"* Morrigan whispers, her feathers vibrating with excitement. *\"The veil between what is and what could be grows thin. We stand at the threshold of power that predates {god} himself.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 2: The Blacksmith Arrives
        embed = discord.Embed(
            title="⚒️ The Last Apprentice ⚒️",
            description="A figure emerges from the forest - a woman with arms corded with muscle and eyes like molten bronze. Strange tattoos of shifting gears and mathematical equations cover her skin.",
            color=0x402a12
        )
        embed.add_field(
            name="Brynhilde the Forgemaster",
            value=f"*\"I am Brynhilde, last apprentice of the Wyrdweaver smiths. Seven generations I have waited for the call, preserving the techniques in my bloodline while hiding from divine sight.\"*\n\nShe examines your offerings with a practiced eye, her fingers tracing patterns above the shards that leave trails of golden light.\n\n*\"You have gathered well, disciple of {god}. Let us begin what cannot be undone. Once forged, the Soulforge binds to its creator for all time—in this life and beyond.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 3: The Construction
        embed = discord.Embed(
            title="🔥 Sacred Metallurgy 🔥",
            description="Brynhilde produces ancient tools from her pack and begins her work. Her hammer makes no sound when it strikes, yet each blow sends ripples through the air itself.",
            color=0xb44401
        )
        embed.add_field(
            name="Alchemical Mastery",
            value="As she works, Brynhilde recites incantations from the Primer in a language that causes pain to your ears yet feels strangely familiar. Your gold melts unnaturally quickly, flowing like water into strange molds that appear to have more dimensions than should be possible. The Eidolith Shards hover above the molten metal, occasionally dipping beneath the surface with soft sighs of completion.\n\nThe forest grows silent, as if holding its breath. Even the insects and night birds cease their calls in reverence to what transpires.",
            inline=False
        )
        embed.add_field(
            name="Divine Attention",
            value=f"The sky darkens as clouds obscure the moons. A distant rumble of thunder suggests that {god} is watching with interest - or concern. Morrigan caws excitedly, flying in increasingly tight circles around the emerging forge. From the corner of your eye, you glimpse figures watching from the treeline—then they're gone, leaving only the impression of robed scholars observing their legacy reborn.",
            inline=False
        )
        pages.append(embed)
        
        # Page 4: The Blood Price
        embed = discord.Embed(
            title="💉 The Final Component 💉",
            description="Hours pass as Brynhilde shapes the Soulforge with superhuman precision, her movements becoming increasingly fluid until she seems to be dancing rather than forging.",
            color=0x8c0101
        )
        embed.add_field(
            name="Blood Bond",
            value=f"*\"It is nearly complete,\"* Brynhilde murmurs, wiping sweat from her brow that sizzles and transforms into tiny butterflies of light before fading. *\"But it requires one final ingredient - a fragment of your own essence. The forge must recognize its master, must know the pattern of your soul to properly bind with your will.\"*\n\nShe produces a silver needle that seems to both exist and not exist simultaneously.\n\n*\"Your blood, {name}. Freely given. A covenant between you and powers older than the gods themselves. The Eidolons' remnants will remember this offering for eternity.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 5: The Awakening
        embed = discord.Embed(
            title="✨ The Soulforge Awakens ✨",
            description="Without hesitation, you prick your finger and let a drop of blood fall into the central basin. The moment it touches the silvery surface, time itself seems to pause.",
            color=0xffd700
        )
        embed.add_field(
            name="Transformation",
            value="The entire structure resonates with power that feels ancient yet new—as if something long dormant has suddenly remembered its purpose. The Eidolith Shards dissolve completely, merging with the metal in a dance of colors too beautiful to comprehend. A blinding flash erupts, and when your vision clears, a beautiful device sits before you - part cauldron, part mechanical wonder, part living crystal.\n\nThe basin at its center swirls with quicksilver that occasionally forms into faces or landscapes before dissolving again. Surrounding it, an intricate framework of metals unknown to modern smiths glows with inner light that pulses in rhythm with your heartbeat.",
            inline=False
        )
        embed.add_field(
            name="Completion",
            value=f"*\"It is done,\"* Brynhilde says with satisfaction, though exhaustion lines her face. *\"The Soulforge lives again. Use it wisely, {name}, for each creation ripples through the fabric of existence. The essence you combine carries memories and powers from the dawn of time—treat them with the respect they deserve.\"*\n\nMorrigan settles on your shoulder, uncomfortably heavy, her feathers no longer looking quite so much like feathers but like pages of an ancient text.\n\n*\"When you wish to splice creatures, simply call upon me with the command `$splice [pet1] [pet2]`, and I shall guide the transformation. Together we shall restore what was lost and perhaps create what has never been.\"*",
            inline=False
        )
        embed.set_footer(text="Your gold has been consumed in the forging. The Soulforge is now available!")
        pages.append(embed)
        
        # NEW Page 6: Divine Risks and Maintenance
        embed = discord.Embed(
            title="⚠️ Divine Scrutiny and Maintenance ⚠️",
            description="As you admire your creation, Brynhilde's expression turns serious. She places a protective hand on the forge's edge.",
            color=0x990000
        )
        embed.add_field(
            name="The Gods' Wrath",
            value=f"*\"There is something vital you must understand,\"* Brynhilde says, her voice lowered. *\"The gods jealously guard their power to shape life. As you use this forge, it will draw their attention - particularly that of {god}, whose domain you now partially trespass upon.\"*\n\nMorrigan nods gravely. *\"Each splice sends ripples through the divine realms. The more you use the forge, especially for powerful creations, the more attention it draws. If scrutiny becomes too great, they will send servants to destroy your work.\"*",
            inline=False
        )
        embed.add_field(
            name="Maintenance and Protection",
            value=f"*\"The forge requires care,\"* Brynhilde continues. *\"Its condition will deteriorate with use and time. You must repair it regularly to ensure stable splicing. And you would be wise to perform rituals to divert divine attention when it grows too great.\"*\n\nMorrigan flutters to perch on the forge's rim. *\"You may also wish to recruit defenders - there are entities drawn to the Wyrdweaver legacy who will protect your forge from divine servants, for a price.\"*",
            inline=False
        )
        pages.append(embed)
        
        # NEW Page 7: Command Summary
        embed = discord.Embed(
            title="📜 Soulforge Command Guide 📜",
            description="Before departing, Brynhilde gives you a small scroll containing instructions for maintaining your Soulforge.",
            color=0x4cc9f0
        )
        embed.add_field(
            name="Basic Commands",
            value="• `$splice [pet1] [pet2]` - Combine two creatures into a new form\n"
                "• `$forgestatus` - Check your forge's condition and divine scrutiny level",
            inline=False
        )
        embed.add_field(
            name="Maintenance",
            value="• `$repairforge` - Restore your forge's condition (costs gold)\n"
                "• `$diversion` - Perform a ritual to reduce divine attention (costs gold)",
            inline=False
        )
        embed.add_field(
            name="Protection",
            value="• `$defendforge` - Defend your forge when divine forces attack\n"
                "• `$recruitdefender` - Hire entities to help protect your forge\n"
                "• `$mydefenders` - View your currently hired defenders",
            inline=False
        )
        embed.set_footer(text="Remember: The more powerful your creations, the more divine attention you'll attract. Maintain your forge and be prepared to defend it!")
        pages.append(embed)
        
        return pages



    @commands.command()
    @user_cooldown(120)
    async def soullorebook(self, ctx):
        """Study the ancient knowledge of the Wyrdweavers"""
        player_data = await self.get_player_data(ctx.author.id)
        
        if not player_data or not player_data["quest_started"]:
            return await ctx.send("You have not begun the Wyrdweaver's path. Use `$soulforge` to start your journey.")
            
        if not player_data["primer"]:
            return await ctx.send("Without the Alchemist's Primer, this knowledge remains hidden from you. The ancient tome must be found before its secrets can be studied.")
        
        await ctx.send(f"*As you open the Alchemist's Primer, you notice the pages shift and reorganize themselves. The tome seems to sense your novice understanding, revealing only certain chapters that you can comprehend at your current level of knowledge. Morrigan explains that the book reveals its secrets gradually as your understanding grows—these fundamental chapters will guide your initial work with the Soulforge.*")

        
        lore_pages = self.create_lore_book_pages(player_data)
        view = LoreView(lore_pages, ctx.author.id)
        await ctx.send(embed=lore_pages[0], view=view)
        
    def create_lore_book_pages(self, player_data):
        """Creates detailed lore pages about soul splicing"""
        pages = []
        
        # Page 1: Nature of Souls
        embed = discord.Embed(
            title="🌟 The Essence of Being 🌟",
            description="Excerpt from the Alchemist's Primer, Chapter I",
            color=0x070221
        )
        embed.add_field(
            name="On Souls and Fragments",
            value="*\"What mortals call 'souls' are in truth fragments of the Eidolons - primordial beings who embodied perfect concepts. When shattered during the Godswar, these fragments scattered across all living things.*\n\n*\"Each creature's soul consists of a Core Essence (its fundamental nature) and Attribute Clusters (specific traits and abilities). These are held together by a unique Binding Pattern. When a being dies naturally, this pattern dissolves, and the essence returns to the greater flow—but when captured at the moment of dissolution, essence can be preserved and reshaped.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 2: The Splicing Process
        embed = discord.Embed(
            title="⚗️ Principles of Transmutation ⚗️",
            description="Excerpt from the Alchemist's Primer, Chapter IV",
            color=0x0a4858
        )
        embed.add_field(
            name="The Art of Splicing",
            value="*\"The Soulforge dissolves the Binding Patterns of both creatures, separating their Core Essences and Attribute Clusters. This process must be conducted with precision—essence yearns to reassemble in its original pattern and will resist new configurations. A new Binding Pattern is created from the caster's own essence, serving as the framework upon which selected fragments are recombined.*\n\n*\"The resulting creation inherits traits from both sources, but in proportions determined by resonance and stability. The stronger the affinity between fragments, the more harmonious the result. Fire essence combines easily with fire, but when forced to bind with water, creates unstable but fascinating steam beings.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 3: Resonance and Compatibility
        embed = discord.Embed(
            title="🎵 Soul Resonance 🎵",
            description="Excerpt from the Alchemist's Primer, Chapter VI",
            color=0x2e8b57
        )
        embed.add_field(
            name="Harmonic Principles",
            value="*\"Not all essences combine with equal ease. Those with similar natures - fire with fire, predator with predator - merge most readily. Opposing natures create dissonance and risk unstable mutations. This is not merely metaphysical resistance but a fundamental property of Eidolith essence—fragments remember their original whole and seek similar fragments.*\n\n*\"Yet opposition can yield the most fascinating results. Water and fire may struggle to unite, but if successful, create steam essence - something neither parent possessed alone. Many Wyrdweavers devoted their lives to a single perfect opposition splice, believing that the tension between opposing forces creates the greatest potential for transcendence.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 4: Risks and Rewards
        embed = discord.Embed(
            title="⚠️ The Splicing Perils ⚠️",
            description="Excerpt from the Alchemist's Primer, Chapter IX",
            color=0x9e4321
        )
        embed.add_field(
            name="Dangers of the Art",
            value="*\"Soul-splicing carries inherent risks. Occasional Binding Failures can cause:*\n\n*• Unstable Mutations: Unpredictable traits emerging in the creation—sometimes beneficial, often not*\n*• Essence Backlash: Damage to the Soulforge or caster as unbound essence lashes out in resistance*\n*• Corrupted Forms: Physically perfect but spiritually fractured beings, suffering from internal dissonance*\n*• Essence Leakage: Partial binding that allows essence to slowly escape, creating temporary creations that eventually dissolve*\n\n*\"These risks increase with creature rarity and with attempts to combine fundamentally opposed natures. The Wyrdweaver Thalassa lost her sanity attempting to combine dragon and deep sea leviathan essences—the resulting creation lived for only moments but spoke prophecies that drove her to madness.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 5: Advanced Techniques
        embed = discord.Embed(
            title="🧠 Mastery of Forms 🧠",
            description="Excerpt from the Alchemist's Primer, Final Chapter",
            color=0x4b0082
        )
        embed.add_field(
            name="For the Adept Wyrdweaver",
            value="*\"The greatest Wyrdweavers learned to guide the splicing process with precision, selecting which traits would be dominant and which recessive. This required rare catalysts:*\n\n*• Dominant Binding: Use Celestial Essence to ensure primary traits from one source*\n*• Selective Inheritance: Use Ley Crystal to preserve specific abilities*\n*• Stabilized Mutation: Use Chaos Amber to safely introduce novel traits*\n*• Perfect Resonance: Use Harmonic Silver to ensure complete integration of disparate essences*\n\n*\"Such materials are exceptionally rare but may still be found in forgotten places. The legendary Wyrdweaver Vaedrith himself discovered a method to create new essence from nothing—a feat previously thought impossible, as it essentially created fragments of Eidolons that had never existed. The secret died with him during the Purge, though rumors persist that he encoded this knowledge somewhere beyond divine reach.\"*",
            inline=False
        )
        pages.append(embed)
        
        return pages

    def create_wyrdweavers_lore(self, player_data):
        """Creates lore pages about the Wyrdweavers"""
        pages = []
        god = player_data["god"]
        
        # Page 1: Origins
        embed = discord.Embed(
            title="📜 The Wyrdweavers' Genesis 📜",
            description="*Morrigan's eyes glow with ancient memories as she begins the tale...*",
            color=0x2e0854
        )
        embed.add_field(
            name="The First Discovery",
            value="*\"In the First Age, when the gods still walked freely among mortals, there lived a gifted alchemist named Vaedrith. Neither loyal to Light nor Dark, he served only Knowledge. Others called him mad when he spoke of patterns beneath reality, of music in the movements of souls.*\n\n*\"During the early skirmishes of what would become the Godswar, Vaedrith witnessed something extraordinary - when Sepulchure's blade of darkness struck a fire elemental allied with Asterea, the being did not simply die. Its essence crystallized, forming the first Eidolith Shard. While others looted the battlefield for conventional treasures, Vaedrith claimed this seemingly worthless crystal and began the studies that would change Fable forever.\"*",
            inline=False
        )
        embed.add_field(
            name="The Hidden Truth",
            value="*\"Upon studying this fragment, Vaedrith made a discovery that would forever change history: what mortals called 'souls' were merely fragments of the Eidolons - primordial beings who existed before the gods themselves. Each living creature carried within it a spark of these ancient entities, worn down and dimmed by countless cycles of death and rebirth, but still bearing the fundamental patterns of powers that shaped the cosmos.*\n\n*\"This knowledge drove Vaedrith to obsession. If souls were fragments of greater beings, could they be recombined? Could the original patterns be recovered or even improved upon? The implications were both terrifying and exhilarating.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 2: The Order's Formation
        embed = discord.Embed(
            title="🕯️ The Order of the Wyrd 🕯️",
            description="*The raven's voice deepens, as if multiple voices speak through her...*",
            color=0x3c1361
        )
        embed.add_field(
            name="Gathering of Minds",
            value="*\"Vaedrith shared his findings with eight other scholars from across Fable - those whose minds he deemed capable of comprehending the significance. There was Thalassa, the sea witch who spoke the language of tides; Korvik, the blind mathematician who calculated in dimensionalities beyond mortal comprehension; Lysandra, the botanist who first realized plants had souls distinct from animals; and five others whose names I safeguard still.*\n\n*\"Together, they formed the Wyrdweavers - an order dedicated to understanding and manipulating soul-essence. Their headquarters was built in a place now lost to time, where the veil between realms was thin - though you know it by another name today.\"*",
            inline=False
        )
        embed.add_field(
            name="The First Soulforge",
            value="*\"For forty years they labored in secret, gathering Eidolith Shards and experimenting with methods to manipulate essence. Their breakthrough came when Lyrane, a metallurgist among them, discovered how quicksilver could be enchanted to dissolve and reconstitute soul-matter without destroying the underlying patterns. The First Soulforge was built, harnessing this principle.*\n\n*\"Their first success was modest - combining the essence of two songbirds to create one with plumage of unusual color and a song of heartbreaking beauty. But this simple creation proved the concept, leading to decades of increasingly ambitious experimentation.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 3: The Golden Age
        embed = discord.Embed(
            title="🌄 The Age of Wonders 🌄",
            description="*Morrigan's feathers shimmer with unnatural colors as she recounts their triumphs...*",
            color=0x571089
        )
        embed.add_field(
            name="Marvelous Creations",
            value="*\"For nearly a century, the Wyrdweavers created wonders. They healed mortal ailments by reshaping damaged souls. They created guardian beasts by splicing predator essence with the loyalty of companion animals. Their greatest achievement was the restoration of lands blighted by the Godswar, using spliced plant essences resistant to divine corruption.*\n\n*\"The griffins that still roam Fable's mountains? Wyrdweaver creations, designed as guardians for remote settlements. The luminous trees of the Whispering Forest? Born from spliced essences of mundane trees and light spirits. Even some human bloodlines carry traces of Wyrdweaver enhancement - families known for unusual longevity or resistance to disease.\"*",
            inline=False
        )
        embed.add_field(
            name="Growth and Secrecy",
            value="*\"The order grew to hundreds of initiates, with seven great Soulforges operating across Fable. Yet they maintained secrecy, aware that their manipulation of essence might be seen as blasphemy by the gods. They operated through fronts - healing houses, magical research enclaves, botanical gardens - hiding their true work behind seemingly innocent facades.*\n\n*\"They were right to fear divine retribution. The power to reshape souls struck at the very heart of divine authority - for what are gods but beings who claim sole dominion over souls? The Wyrdweavers had found a path to power that bypassed divine blessing entirely.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 4: The Fall (with god-specific content)
        embed = discord.Embed(
            title="⚡ Divine Wrath ⚡",
            description="*Morrigan's voice grows hushed, almost fearful...*",
            color=0x4a0d67
        )
        
        if "drakath" in god.lower() or "chaos" in god.lower():
            discovery = "*\"It was Drakath who first discovered their work - not yet the Chaos God you know, but still a deity of transformation and change. He observed the Wyrdweavers with curiosity rather than anger, even granting them insights that advanced their craft. Yet in his chaotic nature, he could not keep secrets. During a divine revel, intoxicated on nectar that even gods should handle cautiously, he boasted of mortals who 'create as we create, without our permission.'\"*"
        elif "asterea" in god.lower() or "light" in god.lower():
            discovery = "*\"It was Asterea who first discovered their work, when she noticed souls in her realm bearing unnatural patterns. Though initially she appreciated their healing arts, she grew concerned when they began creating new life forms that had never existed in her grand design. She sent agents disguised as supplicants seeking healing, who reported back the full scope of Wyrdweaver activities.\"*"
        elif "sepulchure" in god.lower() or "dark" in god.lower():
            discovery = "*\"It was Sepulchure who first discovered their work, recognizing in it echoes of his own dark necromancy. For a time, he extracted tribute from the Wyrdweavers in exchange for his silence, demanding they create weapons for his armies. But secrets between gods never last. Asterea's spies uncovered the arrangement, and she confronted Sepulchure before the Divine Council, forcing him to reveal everything he knew about these 'soul manipulators.'\"*"
        else:
            discovery = "*\"When the gods finally discovered the Wyrdweavers' work, opinion was divided. Some saw their creations as abominations, others as natural evolution. But all agreed that mortals wielding such power threatened divine authority. The gods had built their entire hierarchy on the premise that they alone determined the flow of souls—that they alone could create and transform living essence.\"*"
        
        embed.add_field(
            name="Discovery",
            value=discovery,
            inline=False
        )
        embed.add_field(
            name="The Council's Judgment",
            value="*\"The Divine Council convened - Asterea, Sepulchure, and others now forgotten. Drakath, in his mercurial nature, argued both for the Wyrdweavers' preservation and destruction in the same breath. In the end, they voted for annihilation. Their reasoning was simple: the power to reshape souls belonged to gods alone.*\n\n*\"Yet even in this judgment, their divine politics played out. Asterea insisted on complete destruction, while Sepulchure argued for assimilating the knowledge. Drakath suggested a game of chance to decide their fate. The debate lasted seven days and nights, while the Wyrdweavers, sensing divine attention, frantically prepared contingencies.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 5: The Destruction
        embed = discord.Embed(
            title="🔥 The Purge 🔥",
            description="*Morrigan trembles slightly as she recounts the devastation...*",
            color=0x67032f
        )
        embed.add_field(
            name="Divine Strike",
            value="*\"The attack came at midnight. Seven lighting bolts - one for each Soulforge - struck simultaneously across Fable. Thousands died instantly. The Wyrdweavers' sanctums were reduced to ash, their libraries incinerated, their knowledge scattered. In places where Soulforges had stood, reality itself was scorched, creating the blighted regions that persist to this day.*\n\n*\"Vaedrith, foreseeing the end, had prepared. While his physical body was destroyed with the others, he had bound his consciousness to his familiar - a raven. His last act was preserving the Primer, encoding all their knowledge into an artifact that could survive divine wrath. That raven was me, though I remember little of my existence before becoming vessel to his fragmented mind.\"*",
            inline=False
        )
        embed.add_field(
            name="The Aftermath",
            value="*\"The gods erased the Wyrdweavers from history so thoroughly that even their name became just a whispered myth. Libraries found themselves missing volumes with no memory of their existence. Those who had been healed by Wyrdweaver arts forgot the source of their restoration. Within a generation, they were legends at best, forgotten at worst.*\n\n*\"Yet their legacy persists. Many creatures you see today in Fable - griffins, chimeras, even some dragons - are distant descendants of Wyrdweaver creations. And fragments of their knowledge survived in alchemy, metallurgy, and the occasional splicing that occurs naturally when creatures are exposed to raw magic. Even the Battle Tower itself, though twisted by divine power, preserves more than the gods intended.\"*\n\n*\"And I... I have carried Vaedrith's memories through the centuries, waiting for one who could restore what was lost. Now I have found you.\"*",
            inline=False
        )
        pages.append(embed)
        
        return pages

    def create_battletower_lore(self, player_data):
        """Creates lore pages connecting the Battle Tower to the Wyrdweavers"""
        pages = []
        god = player_data["god"]
        
        # Page 1: The Tower's True Origin
        embed = discord.Embed(
            title="🗼 The Forgotten Sanctum 🗼",
            description="*Morrigan's eyes narrow as you mention the Battle Tower...*",
            color=0x342056
        )
        embed.add_field(
            name="A Familiar Structure",
            value="*\"So you have visited the Battle Tower? Interesting. That structure is no ordinary tower - it was once the Central Sanctum of the Wyrdweavers, housing their greatest Soulforge and most precious knowledge. It was there that Vaedrith and the original eight performed their most ambitious experiments, there that the principles of soul-splicing were perfected.*\n\n*\"After the Purge, the gods couldn't completely destroy it - the tower was built on a nexus of ley lines and had become part of Fable's metaphysical structure. Instead, they twisted its purpose, converting it into a place of combat rather than creation. What was once a sanctuary of knowledge became a gauntlet of trials, what was once a place of healing transformed into an arena of violence.\"*",
            inline=False
        )
        embed.add_field(
            name="Layers of Illusion",
            value="*\"The illusions you experienced there are multiple and layered. Yes, you believed you were cleansing corruption, when in truth you were fighting innocents under a spell. But there is an even deeper deception.*\n\n*\"The Tower itself is an illusion - what you see as a battle arena is actually the ancient Soulforge, still operational but disguised. The central combat platform? That is the primary crucible, where essence was mixed and reforged. The multiple levels represent different stages of the splicing process. And the 'monsters' you fight are manifestations of soul fragments preserved within the forge. When you defeat them, you are unwittingly extracting Eidolith essence - performing the very work the gods sought to erase.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 2: The Divine Deception
        embed = discord.Embed(
            title="🎭 The Gods' Grand Illusion 🎭",
            description="*Morrigan hops closer, her voice dropping to a near-whisper...*",
            color=0x42217a
        )
        
        if "drakath" in god.lower() or "chaos" in god.lower():
            divine_role = "*\"Your patron, Drakath, plays a curious role in this deception. As the God of Chaos, he simultaneously maintains and undermines the illusion. The Tower's chaotic nature - how it seems different to each visitor - is his touch. Sometimes he remembers it is a disguised Soulforge and intentionally weakens the illusion, allowing fragments of true knowledge to slip through. Other times he forgets entirely, adding new layers of randomness that even he cannot predict. In this way, the Wyrdweavers' legacy survives within the very structure meant to erase it.\"*"
        elif "asterea" in god.lower() or "light" in god.lower():
            divine_role = "*\"Your patron, Asterea, believes the Tower serves justice. In her light-touched perception, the illusion cleanses souls of darkness through righteous combat. She genuinely believes the Tower was always a place of trial and judgment. She doesn't fully comprehend that the Tower preserves Wyrdweaver knowledge she once voted to destroy. Through this blind spot, the ancient arts survive beneath her very gaze. Her own light, brilliantly blinding, creates the perfect shadow in which forbidden knowledge hides.\"*"
        elif "sepulchure" in god.lower() or "dark" in god.lower():
            divine_role = "*\"Your patron, Sepulchure, permits the Tower's existence for his own ends. While other gods see it as a test of combat prowess, he recognizes its true nature and siphons fragments of soul-essence from it. After all, his own necromancy shares principles with soul-splicing. He has no interest in exposing the illusion when it serves his collection of power. In truth, he preserved more Wyrdweaver knowledge than the others suspect, integrating it into his own dark arts.\"*"
        else:
            divine_role = "*\"The gods each interpret the Tower according to their nature. To Asterea, it is justice. To Sepulchure, power. To Drakath, beautiful chaos. All are deceived in some measure by their own expectations. This multiple perception is its greatest protection - no single divine vision perceives all its layers simultaneously.\"*"
        
        embed.add_field(
            name="Divine Perspectives",
            value=divine_role,
            inline=False
        )
        embed.add_field(
            name="The Hidden Truth",
            value="*\"The Tower's guardians - those you believe are villains - are actually fragments of Wyrdweaver consciousness, preserved in the same manner as I was. They maintain the forge's operation under the guise of 'corrupting' the tower. When adventurers like you defeat them, you are actually helping them extract and preserve Eidolith essence. Your combat provides the necessary energy to activate the ancient mechanisms.*\n\n*\"Each monster defeated in the Tower contributes to a reservoir of essence. When enough accumulates, it forms what adventurers call 'rare pet eggs' - but these are actually condensed Eidolith fragments with predetermined forms, created by the Tower's hidden mechanisms. The pets you receive are not random rewards but deliberately designed vessels of ancient power, waiting for someone who could reactivate a Soulforge.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 3: The Tower's Secret Purpose
        embed = discord.Embed(
            title="⚙️ The Grand Design ⚙️",
            description="*Morrigan spreads her wings in excitement as she reveals the final truth...*",
            color=0x52318f
        )
        embed.add_field(
            name="The Ultimate Goal",
            value="*\"The Battle Tower serves a purpose none of the gods suspect. Vaedrith designed it as a self-perpetuating mechanism to preserve and distribute Wyrdweaver knowledge. Each adventurer who claims a 'pet' from the Tower carries with them a fragment of ancient essence, prepared for the day when the Soulforges would return.*\n\n*\"That is why your pets can be spliced so effectively - they were created with this purpose in mind. They are not merely companions but vessels of primordial essence, waiting to be recombined. The Battle Tower is not just preserving knowledge - it is actively continuing the Wyrdweavers' work under a perfect disguise.\"*",
            inline=False
        )
        embed.add_field(
            name="Your Role",
            value="*\"Now you understand why I sought you. By rebuilding the Soulforge, you complete a plan set in motion centuries ago. The Tower has been preparing champions like you, distributing the necessary essence throughout Fable, waiting for one who would rediscover the art of splicing.*\n\n*\"When you splice your pets, you are not merely creating new companions. You are rebuilding fragments of the original Eidolons, restoring what was shattered during the Godswar. Each splice brings us one step closer to mending the broken foundations of our world. And perhaps, though Vaedrith never spoke this aloud, to creating power that could challenge the gods themselves - not through opposition, but by reconnecting with what came before them.\"*",
            inline=False
        )
        pages.append(embed)
        
        return pages

    def create_gods_lore(self, player_data):
        """Creates lore pages about the Divine Council and the three main gods"""
        pages = []
        god = player_data["god"]
        
        # Page 1: The Divine Council
        embed = discord.Embed(
            title="👑 The Triumvirate of Power 👑",
            description="*Morrigan's feathers bristle as she speaks of the gods...*",
            color=0x4d1d93
        )
        embed.add_field(
            name="The Balance of Power",
            value="*\"The Divine Council that rules Fable today is a shadow of what once existed. In the earliest days, dozens of deities governed different aspects of existence - gods of rivers and mountains, patrons of crafts and emotions, embodiments of abstract concepts. All drawing their power from fragments of Eidolons, though few acknowledge this origin.*\n\n*\"After the Godswar, only three major powers remained - Asterea of Light, Sepulchure of Darkness, and Drakath of Chaos. The others were destroyed, absorbed, or diminished to such extent that they exist now only as minor spirits or forgotten names in ancient texts.*\n\n*\"These three exist in a precarious balance. None can overcome the others, for reality itself depends on the tension between them. Light without darkness is blinding; darkness without light is oblivion; and without chaos, both would stagnate into meaninglessness.\"*",
            inline=False
        )
        embed.add_field(
            name="The Council's Function",
            value="*\"They meet at the turning of ages in the Nexus of Divinity, a realm between realms. There they negotiate the fundamental laws of existence for the coming era. They debate, threaten, and occasionally ally against the third when power shifts too dramatically. Their decisions manifest as natural laws, cosmic constants, and the boundaries of magical possibility.*\n\n*\"The Eidolons existed before this Council - indeed, before the concept of divinity as mortals understand it. That is why the gods feared the Wyrdweavers; manipulation of Eidolith essence could potentially create power that predates divine authority. The gods are mighty, but they are not primordial - they emerged from the same cosmic soup that produced all things, simply rising to dominance through cunning and strength.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 2: Asterea, Goddess of Light
        embed = discord.Embed(
            title="☀️ Asterea, The Radiant Judge ☀️",
            description="*Morrigan's tone becomes formal, almost reverential despite herself...*",
            color=0xffd700
        )
        
        if "asterea" in god.lower() or "light" in god.lower():
            perspective = "*\"Your patron is the embodiment of order, justice, and illumination. She believes all things must have their proper place in a harmonious cosmos. You know her compassionate aspect well, but perhaps not how utterly inflexible her concept of 'good' can be. Her light reveals truth but casts stark shadows - there is no room for ambiguity in her vision. What she deems wrong must be completely eliminated, not reformed or understood.\"*"
        else:
            perspective = "*\"Asterea presents herself as benevolence incarnate - the compassionate mother, the fair judge, the bringer of light to darkness. This is not entirely false, but it is incomplete. Her justice can be merciless, her order stifling, her light blinding to subtlety and nuance. She categorizes all things as light or darkness, leaving no space for the vital shadows between.\"*"
        
        embed.add_field(
            name="Nature and Domain",
            value=perspective + "\n\n*\"She rules over healing, protection, truth, and the revealing light of knowledge. Her realm, the Empyrean Halls, exists in perpetual golden dawn, where souls loyal to her cause are rewarded with endless illumination and clarity. Her followers seek to bring her perfect order to all aspects of existence, often unable to recognize when their rigid justice becomes tyranny.\"*",
            inline=False
        )
        embed.add_field(
            name="Relationship with Eidolons",
            value="*\"When the Eidolons existed in their complete form, Asterea respected them as elder entities but believed they lacked purpose and moral direction. She saw them as beautiful but amoral forces - raw potential requiring divine guidance. She saw the Godswar's shattering of these beings as regrettable but necessary - creating space for light to bring order to primordial chaos.*\n\n*\"Her opposition to the Wyrdweavers stemmed from her belief that mortals lack the moral perfection to reshape souls. Only divine judgment should determine a being's nature - or so she proclaimed while sanctioning the destruction of an entire order of scholars. There is perhaps no greater irony than her insistence on mercy while showing none to those who challenged divine authority.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 3: Sepulchure, God of Darkness
        embed = discord.Embed(
            title="🌑 Sepulchure, The Shadow Sovereign 🌑",
            description="*Morrigan's eyes gleam with cautious respect...*",
            color=0x3d0a1f
        )
        
        if "sepulchure" in god.lower() or "dark" in god.lower():
            perspective = "*\"Your patron embodies inevitability, ambition, and the hidden truths that light fears to illuminate. While others see only his cruelty, you understand his necessity - without endings, nothing new begins; without ambition, nothing evolves; without darkness, light has no meaning. His methods may be harsh, but he never pretends to be what he is not.\"*"
        else:
            perspective = "*\"Sepulchure is commonly painted as a villain by Asterea's followers, but existence needs his darkness as surely as it needs light. He represents necessary endings, the courage to face uncomfortable truths, and the ambition that drives evolution. Yes, he can be cruel, but there is a cold honesty to his approach that Asterea's blinding righteousness often lacks.\"*"
        
        embed.add_field(
            name="Nature and Domain",
            value=perspective + "\n\n*\"He rules over death, secrets, necessity, and transformation through trial. His realm, the Umbral Dominion, exists in perpetual twilight - not lightless, but illuminated by the stars and moon, where souls learn the strength found in darkness. His followers recognize that creation requires destruction, that growth demands pruning, that facing darkness rather than denying it creates true strength.\"*",
            inline=False
        )
        embed.add_field(
            name="Relationship with Eidolons",
            value="*\"Sepulchure admired the Eidolons' primal nature and was less eager than others to see them shattered. In their essence, he recognized power unconcerned with moral pretense - beings that existed according to their nature without apology or justification. During the Godswar, he sought to absorb their essence rather than destroy it, understanding its fundamental value.*\n\n*\"His opposition to the Wyrdweavers was pragmatic rather than moral - he believed such power should belong solely to divinity, not mortals. Yet he was the only god who preserved some Wyrdweaver knowledge, keeping forbidden texts in his dark libraries. His necromancy draws upon principles not unlike soul-splicing, though focused on binding rather than transformation. In truth, had the Wyrdweavers pledged themselves to him alone, he might have protected them.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 4: Drakath, God of Chaos
        embed = discord.Embed(
            title="🌀 Drakath, The Chaos Incarnate 🌀",
            description="*Morrigan's speech becomes momentarily disjointed, as if influenced by the subject...*",
            color=0x9900ff
        )
        
        if "drakath" in god.lower() or "chaos" in god.lower():
            perspective = "*\"Your patron defies... definition. Even... attempting to describe... Drakath changes him. You understand... this fluidity, this... beautiful contradiction. Where others see madness... you recognize... the ultimate freedom. The blessing... and curse... of infinite possibility.\"*"
        else:
            perspective = "*\"Drakath represents... the untamable. The random... chance that creates... both disaster and miracle. Neither good... nor evil, but the wild... possibility that exists... before moral judgment. He is... creation and destruction... simultaneously, the cosmic... roll of dice that determines... what might be.\"*"
        
        embed.add_field(
            name="Nature and Domain",
            value=perspective + "\n\n*\"He rules over... transformation, possibility, inspiration, and... the unknown. His realm... if it can be called such... the Flux Labyrinth... constantly rearranges itself. Time flows... differently there. Forwards, backwards... sideways. His followers embrace... unpredictability, finding freedom... in surrendering to... chance and change.\"*",
            inline=False
        )
        embed.add_field(
            name="Relationship with Eidolons",
            value="*\"Drakath and the Eidolons... kindred in essence. Both... predating rigid order. During the Godswar... sometimes he fought them... sometimes became them... momentarily. The boundaries... blurred. He understood... better than others... that the Eidolons represented... not just power but... possibility unrealized.*\n\n*\"His stance on Wyrdweavers... inconsistent. In council... argued both for... and against their destruction... sometimes simultaneously. Secretly... fascinated by their work. The Soulforge's unpredictable results... delighted him. Some suspect... he preserved some Wyrdweavers... hidden within chaos realms... where other gods cannot... perceive clearly. If true... even he may have... forgotten their location... in his shifting mind.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 5: The Gods and the Soulforge
        embed = discord.Embed(
            title="⚔️ Divine Attention ⚔️",
            description="*Morrigan looks over her shoulder, as if worried about being overheard...*",
            color=0x7209b7
        )
        embed.add_field(
            name="Current Divine Awareness",
            value="*\"As you rebuild the Soulforge, know this: the gods will sense its activation. Their reaction will depend on their nature and current concerns. Asterea may seek to destroy it again, believing it violates the natural order. Sepulchure might demand tribute for his silence. Drakath...well, his response is inherently unpredictable - he might champion your work one moment and send assassins the next, perhaps both simultaneously.*\n\n*\"The gods' attention is divided among countless concerns across multiple realms. They may not immediately notice a single Soulforge's activation, especially if you work with subtlety. But as your creations multiply and grow in power, divine scrutiny becomes inevitable.\"*",
            inline=False
        )
        
        if "drakath" in god.lower() or "chaos" in god.lower():
            divine_protection = "*\"Your connection to Chaos offers some protection. Drakath's nature makes him resistant to consistent action - he may alert the other gods to your work, then immediately help you hide it. His followers exist in his blindspot - too chaotic for even him to track consistently. Use this to your advantage. When creating your spliced beings, incorporate elements of unpredictability and transformation to align them with Chaotic principles - this resonance may camouflage them from divine attention.\"*"
        elif "asterea" in god.lower() or "light" in god.lower():
            divine_protection = "*\"Your devotion to Asterea creates both risk and opportunity. She will be slower to suspect her own follower of 'heresy,' giving you time to establish your work. If discovered, appeal to the healing potential of the Soulforge - the restoration of broken beings aligns with her purported values, even if the method disturbs her. Focus your splicing on creating beings that embody her principles of beauty, order, and benevolence. Such creations might earn her reluctant tolerance, if not approval.\"*"
        elif "sepulchure" in god.lower() or "dark" in god.lower():
            divine_protection = "*\"Your allegiance to Sepulchure provides a certain protection. He appreciates power and ambition in his followers. If he detects your Soulforge, offer him tribute - certain spliced creations pledged to his service. His practical nature makes him open to negotiation where Asterea would offer only judgment. The Dark One respects those who seize forbidden knowledge, even as he punishes those who fail to properly exploit it. Create beasts of shadow and death, and he may view your work as an extension of his own.\"*"
        else:
            divine_protection = "*\"Without direct divine patronage, you walk a precarious path. Yet this independence may be its own protection - you do not register as strongly on divine awareness. Keep your work subtle and your ambitions modest, at least until your understanding grows. Without a god's mark upon you, your creations bear no divine signature that might draw attention. This anonymity is both vulnerability and shield.\"*"
        
        embed.add_field(
            name="Your Divine Connection",
            value=divine_protection + "\n\n*\"Remember, the Soulforge represents power from before the gods. Use it wisely, for it may draw attention from realms even I cannot perceive. The Eidolons were not the only entities from the dawn of creation, and some ancient powers still slumber, dreaming of the days before divine dominion.\"*",
            inline=False
        )
        pages.append(embed)
        
        return pages

    def create_creatures_lore(self, player_data):
        """Creates lore pages about the creatures of Fable and their connection to the Eidolons"""
        pages = []
        
        # Page 1: Origins of Fable's Creatures
        embed = discord.Embed(
            title="🐾 The First Beasts 🐾",
            description="*Morrigan begins what feels like an ancient creation story...*",
            color=0x0a6e0a
        )
        embed.add_field(
            name="The Primordial Ecosystem",
            value="*\"Before the coming of gods or mortals, the Eidolons dominated Fable. These were not gods but embodiments of concepts and elements - living mountains that thought in eons, sentient oceans that dreamed, dancing flames with memories, winds that sang with consciousness. They did not rule as much as they simply existed, their very being shaping reality around them.*\n\n*\"The first animals evolved in their shadow, shaped by proximity to these primordial forces. Creatures near the Fire Eidolon developed flame-resistant hides; those dwelling in the Earthen Eidolon's valleys acquired traits of stone and crystal. Birds that soared through the Wind Eidolon's domain learned languages now forgotten; fish that swam the depths of the Ocean Eidolon gained the ability to breathe memories instead of water.\"*",
            inline=False
        )
        embed.add_field(
            name="The First Natural Splicing",
            value="*\"Where Eidolons' territories overlapped, the most fascinating creatures emerged. In the borderlands between the Storm and Earth Eidolons, griffins evolved - combining avian and feline traits to navigate both rocky terrain and turbulent skies. In the twilight zone where Ocean and Darkness Eidolons met, the first leviathans formed - carrying both aquatic adaptations and shadow-manipulation abilities.*\n\n*\"These natural hybridizations were the world's first 'splicing' - essence combining through environmental influence rather than deliberate manipulation. Each such creature was a living record of Eidolons' overlapping domains, physical forms reflecting cosmic geography.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 2: The Godswar's Impact
        embed = discord.Embed(
            title="💥 The Shattering 💥",
            description="*Morrigan's voice trembles with the memory of cosmic violence...*",
            color=0x1a5e0a
        )
        embed.add_field(
            name="Collateral Damage",
            value="*\"When the newly emerged gods warred with each other, the Eidolons were caught in their crossfire. Divine weapons - concepts like 'banishment' and 'unmaking' given form - struck the ancient beings. But the Eidolons could not simply die; their essence was too fundamental to reality.*\n\n*\"Instead, they shattered. Their consciousness fragmented into countless shards that scattered across Fable. Many embedded themselves in living creatures, drawn to compatible hosts. A shard of the Flame Eidolon might seek a desert predator, while Water Eidolith would drift toward aquatic beings. The greater the shard, the more dramatic the transformation of the host.\"*",
            inline=False
        )
        embed.add_field(
            name="The First Monsters",
            value="*\"This is the origin of what mortals now call 'monsters' - ordinary creatures transformed by Eidolith fragments. A common wolf hosting a fragment of the Storm Eidolon might gain the ability to summon lightning or move with wind's speed. A turtle touched by Earth Eidolith might develop an impenetrable crystalline shell and the ability to reshape stone with its thoughts.*\n\n*\"These transformations were often unstable, creating unnatural and sometimes aggressive beings that passed their altered essence to offspring. The host's consciousness would sometimes struggle against the fragment's alien memories, creating internal conflict that manifested as aggression or madness. The 'monsters' you battle are not evil, merely unbalanced - their forms struggling to contain power never meant for them. When defeated, this essence can be extracted as what adventurers call 'pet eggs' - concentrated, stabilized fragments that can develop into companions.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 3: The Wyrdweavers' Contributions
        embed = discord.Embed(
            title="🧪 Deliberate Creation 🧪",
            description="*Morrigan speaks with pride of mortal achievement...*",
            color=0x2a7e1a
        )
        embed.add_field(
            name="Studying the Fragments",
            value="*\"When the Wyrdweavers discovered Eidolith Shards, they realized these fragments could be deliberately extracted, purified, and recombined. Where natural evolution had created griffins over thousands of years, they could achieve similar results in a single ritual. They learned to stabilize the merging process, preventing the madness that afflicted wild monsters.*\n\n*\"Many creatures familiar to you were Wyrdweaver creations - the majestic phoenixes (combining Fire and Rebirth Eidolith), the intelligent mimics (Memory and Form Eidolith), the ever-shifting chameleon dragons (combining draconic essence with Transformation Eidolith). These were not abominations but carefully balanced beings, designed to be stable and harmonious unlike the accidental monsters born of raw Eidolith exposure.\"*",
            inline=False
        )
        embed.add_field(
            name="Legacy Creatures",
            value="*\"After the Wyrdweavers' destruction, many of their creations survived and bred true, becoming established species. Others reverted to wild states, their careful essence-balance degrading over generations into the more dangerous forms encountered today. Some became guardians of Wyrdweaver ruins - the chimeras that protect ancient laboratories, the sphinxes that speak in riddles preserving forgotten knowledge.*\n\n*\"The pets you collect and nurture are often descendants of these deliberate creations, their essence more stable and receptive to further manipulation. This is why they can be spliced more successfully than wild creatures - they were born of the very arts you now seek to revive. Each one carries a whisper of Wyrdweaver knowledge in its very cells, waiting to be awakened through the Soulforge.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 4: The Battle Tower's Ecosystem
        embed = discord.Embed(
            title="🗼 The Living Museum 🗼",
            description="*Morrigan reveals the Tower's deeper purpose...*",
            color=0x3a9e2a
        )
        embed.add_field(
            name="Preservation Through Illusion",
            value="*\"The Battle Tower you know serves as a living archive of Eidolith combinations. Each 'monster' encountered there is actually a projected form - an illusion given substance through the Tower's magic. These projections are based on Wyrdweaver records of successful and failed combinations, recreated from preserved essence samples.*\n\n*\"When you defeat these projections, you are not truly killing anything, but completing an extraction ritual designed by the Wyrdweavers. The combat serves as the energetic catalyst needed to separate and preserve specific essence combinations. The Tower's guardians orchestrate these challenges to ensure the right forms manifest for harvest.\"*",
            inline=False
        )
        embed.add_field(
            name="Why Pets Can Be Spliced",
            value="*\"The pets obtained from the Tower are particularly suitable for splicing because they are already perfect distillations of specific Eidolith essence. They represent pure, stable expressions of ancient power, carefully balanced by the Tower's mechanisms. When you bring these pets to the Soulforge, you are working with refined materials rather than raw, unpredictable fragments.*\n\n*\"This is why the Tower and the Soulforge are complementary technologies - one preserves and distributes essence, while the other recombines it. Together, they form a complete system for essence manipulation, deliberately separated to prevent divine detection. The Tower creates the components; your Soulforge allows you to assemble them into new configurations, continuing the work the gods sought to end.\"*",
            inline=False
        )
        pages.append(embed)
        
        # Page 5: The Future of Splicing
        embed = discord.Embed(
            title="✨ Unlimited Potential ✨",
            description="*Morrigan's eyes shine with possibilities as she concludes...*",
            color=0x4abe3a
        )
        embed.add_field(
            name="Beyond Simple Combinations",
            value="*\"As your understanding of the Soulforge grows, you will discover that splicing extends far beyond creating hybrid beasts. The Wyrdweavers eventually learned to extract specific traits - a creature's longevity, resistance to elements, or unique abilities - and transfer these to other beings without fully combining their forms.*\n\n*\"Advanced practitioners could create specialized creatures for specific purposes - guardians attuned to particular threats, companions with complementary abilities to their bonded mortals, even beings that could heal blighted lands or purify corrupted essence. The most accomplished Wyrdweavers could even splice non-living materials with living essence, creating sentient objects or plants with metallic properties.\"*",
            inline=False
        )
        embed.add_field(
            name="The Ultimate Purpose",
            value="*\"What few understand is that all this work serves a greater goal. Each successful splice recombines fragments of the original Eidolons. With enough time and knowledge, it may be possible to reconstruct these primordial beings - or at least, new entities of similar fundamental power.*\n\n*\"Some Wyrdweavers believed this was the path to transcending divine authority altogether - not by opposing the gods, but by reconnecting with the foundations upon which godhood itself was built. Vaedrith's most secret writings suggested that the Eidolons were not destroyed by accident during the Godswar, but deliberately shattered by gods who feared competition from these elder powers.*\n\n*\"Whether you pursue such lofty ambitions or simply create magnificent companions is your choice - the Soulforge cares not for the morals of its wielder, only the harmony of its creations. But know that with each splice, you rebuild a fragment of the world that existed before gods claimed dominion over souls.\"*",
            inline=False
        )
        pages.append(embed)
        
        return pages


    @commands.command()
    @user_cooldown(108000)
    async def splice(self, ctx, pet1_id: int = None, pet2_id: int = None):
        try:
            """Splice two pets together to create a new being"""
            player_data = await self.get_player_data(ctx.author.id)
            
            if not player_data or not player_data["forge_built"]:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send("You have not yet constructed a Soulforge. Begin the journey with `$soulforge`.")
            
            # NEW: Check forge condition
            async with self.bot.pool.acquire() as conn:
                forge_data = await conn.fetchrow(
                    "SELECT forge_condition, divine_attention FROM splicing_quest WHERE user_id = $1 AND crucible_built = TRUE",
                    ctx.author.id
                )
                
                if not forge_data:
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send("Error retrieving forge data. Please contact an administrator.")
                    
                forge_condition = forge_data["forge_condition"]
                current_divine_attention = forge_data["divine_attention"]
                
                # Check if forge is too damaged to use
                if forge_condition <= 10:
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send("*The Soulforge sputters weakly, its silvery basin clouded and dull. The runes flicker erratically before going dark.*\n\n*\"The crucible is critically damaged,\"* Morrigan warns. *\"It must be repaired with `$repairforge` before we can continue our work, or the results could be catastrophic.\"*")
                    
            if not pet1_id or not pet2_id:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send("You must specify two pet IDs to splice. Usage: `$splice [pet1_id] [pet2_id]`")
            
            # Check if player owns both pets
            async with self.bot.pool.acquire() as conn:
                pet1_data = await conn.fetchrow(
                    "SELECT * FROM monster_pets WHERE id = $1 AND user_id = $2",
                    pet1_id, ctx.author.id
                )
                
                pet2_data = await conn.fetchrow(
                    "SELECT * FROM monster_pets WHERE id = $1 AND user_id = $2",
                    pet2_id, ctx.author.id
                )

            unspliceable_pets = ["Sepulchure", "Elysia", "Drakath", "Ultra Sepulchure", "Ultra Elysia",
                                 "Ultra Drakath"]

            if not pet1_data:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(f"You don't own a pet with ID {pet1_id}.")

            if not pet2_data:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(f"You don't own a pet with ID {pet2_id}.")

            if pet1_data["default_name"] in unspliceable_pets or "[FINAL]" in pet1_data["default_name"]:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(f"**{pet1_data['default_name']}** cannot be spliced due to its mythical nature.")

            if pet2_data["default_name"] in unspliceable_pets or "[FINAL]" in pet2_data["default_name"]:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(f"**{pet2_data['default_name']}** cannot be spliced due to its mythical nature.")

            if pet2_data["default_name"] == pet1_data["default_name"]:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send("Your two pets must be different species.")

            if pet1_data["growth_stage"] != "adult" or pet2_data["growth_stage"] != "adult":
                await self.bot.reset_cooldown(ctx)
                return await ctx.send("Both pets must be at the adult stage to proceed.")

            # NEW: Determine the rarity of the splice based on pet stats
            def determine_pet_rarity(pet):
                """Determine a pet's rarity based on stats"""
                total_stats = pet["hp"] + pet["attack"] + pet["defense"]
                
                if total_stats > 2000:
                    return "legendary"
                elif total_stats > 1500:
                    return "epic"
                elif total_stats > 1000:
                    return "rare"
                elif total_stats > 500:
                    return "uncommon"
                else:
                    return "common"
                    
            # Calculate rarity of both pets
            pet1_rarity = determine_pet_rarity(pet1_data)
            pet2_rarity = determine_pet_rarity(pet2_data)
            
            # Rarity hierarchy for comparison
            rarity_order = ["common", "uncommon", "rare", "epic", "legendary"]
            
            # Determine overall splice rarity (taking the higher of the two)
            splice_rarity = pet1_rarity if rarity_order.index(pet1_rarity) > rarity_order.index(pet2_rarity) else pet2_rarity
            
            # NEW: Calculate condition reduction and divine attention increase
            condition_reduction = 1  # Base value for common pets
            attention_increase = 2   # Base value for common pets

            if splice_rarity == "uncommon":
                condition_reduction = 2
                attention_increase = 3
            elif splice_rarity == "rare":
                condition_reduction = 3
                attention_increase = 5
            elif splice_rarity == "epic":
                condition_reduction = 4
                attention_increase = 8
            elif splice_rarity == "legendary":
                condition_reduction = 5
                attention_increase = 12
            
            # Check if this combination has been spliced before
            async with self.bot.pool.acquire() as conn:
                # Create table if it doesn't exist
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS splice_combinations (
                        id SERIAL PRIMARY KEY,
                        pet1_default TEXT,
                        pet2_default TEXT,
                        result_name TEXT,
                        hp INTEGER,
                        attack INTEGER,
                        defense INTEGER,
                        element TEXT,
                        url TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                
                existing_splice = await conn.fetchrow(
                    """
                    SELECT * FROM splice_combinations 
                    WHERE (pet1_default = $1 AND pet2_default = $2) OR (pet1_default = $2 AND pet2_default = $1)
                    """,
                    pet1_data["default_name"], pet2_data["default_name"]
                )
            if existing_splice and "[FINAL]" in existing_splice["result_name"]:
                self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    "The Crucible shudders violently, its mercurial surface hardening into impenetrable obsidian. "
                    "Morrigan's voice echoes with finality: \"This union has already birthed a [FINAL] form. "
                    "The forge refuses to reweave what has been perfected.\""
                )
            if existing_splice and "[Event]" in existing_splice["result_name"]:
                self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    "The Crucible shudders violently, its mercurial surface hardening into impenetrable obsidian. "
                    "Morrigan's voice echoes with finality: \"This union has already birthed a [Event] form. "
                    "The forge refuses to reweave what has been perfected.\""
                )
            
            # Ask for confirmation
            confirm_msg = f"Are you sure you want to splice {pet1_data['name']} and {pet2_data['name']} together into a new beast? This action cannot be undone."
            confirmed = await ctx.confirm(confirm_msg)
            
            if not confirmed:
                return await ctx.send("Splice canceled.")
            
            # Generate narrative sequence
            name = player_data["name"]
            god = player_data["god"]
            
            # Define growth stages
            growth_stages = {
                1: {"stage": "baby", "growth_time": 2, "stat_multiplier": 0.25, "hunger_modifier": 1.0},
                2: {"stage": "juvenile", "growth_time": 2, "stat_multiplier": 0.50, "hunger_modifier": 0.8},
                3: {"stage": "young", "growth_time": 1, "stat_multiplier": 0.75, "hunger_modifier": 0.6},
                4: {"stage": "adult", "growth_time": None, "stat_multiplier": 1.0, "hunger_modifier": 0.0},
            }
            
            # Get the baby stage data
            baby_stage = growth_stages[1]
            stat_multiplier = baby_stage["stat_multiplier"]
            growth_time_interval = datetime.timedelta(days=baby_stage["growth_time"])
            growth_time = datetime.datetime.utcnow() + growth_time_interval
            
            # Create sequence of splicing ritual
            pages = []
            
            # Page 1: Beginning the ritual
            embed = discord.Embed(
                title="🧪 The Crucible Calls 🧪",
                description=f"You approach your Soulforge with {pet1_data['name']} and {pet2_data['name']}, feeling the device's hunger resonating in your bones.",
                color=0x480ca8
            )
            embed.add_field(
                name="Morrigan's Return",
                value=f"The raven descends from nowhere, settling on the rim of the forge. Her eyes reflect the swirling quicksilver of the central basin.\n\n*\"An interesting choice, {name}. The essence of {pet1_data['name']} carries strong currents of primal energy, while {pet2_data['name']} possesses unusual stability. Let us see what their combined patterns might become when woven together.\"*",
                inline=False
            )
            embed.add_field(
                name="The Sacrifice",
                value=f"You place both creatures into the mercurial basin. They enter a trance-like state and sink beneath the silvery surface without struggle, as if returning to a primordial womb. The liquid begins to churn and bubble as the forge's runes illuminate with arcane fire, pulsing in patterns that hurt your eyes if you look at them directly.\n\nThe air grows thick with potential, smelling of ozone and ancient stone. Your Soulforge seems larger somehow, as if the interior space expands beyond what its exterior dimensions should allow.",
                inline=False
            )
            
            # NEW: Add forge condition feedback
            if forge_condition < 30:
                embed.add_field(
                    name="Forge Strain",
                    value=f"*You notice the forge's energies fluctuate erratically, the runes pulsing unevenly. Tiny fissures appear along the basin's edge, leaking wisps of silvery vapor.*\n\n*\"The forge strains under the weight of this working,\"* Morrigan cautions. *\"Its condition at {forge_condition}% is concerning. We should repair it soon after this splice is complete.\"*",
                    inline=False
                )
            
            pages.append(embed)
            
            # Page 2: The transformation
            embed = discord.Embed(
                title="🌀 Unmaking and Reweaving 🌀",
                description="The Soulforge's power surges as it separates essence from form, dissolving physical matter into pure pattern.",
                color=0x3a0ca3
            )
            embed.add_field(
                name="Dissolution",
                value=f"Morrigan chants in an ancient tongue as the forge dissolves the physical forms of your pets. Their essence remains visible as swirling motes of colored light - {pet1_data['name']}'s core glows with amber radiance while {pet2_data['name']}'s pulses with azure energy. You see fragments of memories not your own: {pet1_data['name']} hunting beneath moonlight, {pet2_data['name']} soaring through misty mountains.\n\nAs the chant continues, these essence clouds begin to intermingle, creating new colors and patterns never seen in nature. Occasionally they resist, pulling apart before being drawn together again by the forge's power.",
                inline=False
            )
            
            # NEW: Add divine attention narrative based on rarity
            divine_desc = ""
            if splice_rarity == "common" or splice_rarity == "uncommon":
                divine_desc = f"You feel a momentary flutter of attention from {god}, your divine patron - a brief acknowledgment of the minor boundaries being crossed."
            elif splice_rarity == "rare":
                divine_desc = f"A distinct pressure descends upon the room as {god}'s awareness focuses more intently on your work. The air feels heavier, charged with divine scrutiny."
            elif splice_rarity == "epic":
                divine_desc = f"The very air crackles with tension as {god}'s attention fixes sharply upon your work. For a moment, shadows gather unnaturally in the corners of the room, and you hear distant whispers of concern from the divine realms."
            elif splice_rarity == "legendary":
                divine_desc = f"Reality itself seems to bend as {god}'s full attention bears down upon your work. The walls of your sanctuary briefly become translucent, showing glimpses of divine realms beyond. You feel the weight of immortal judgment upon you."
            
            new_divine_attention = min(100, current_divine_attention + attention_increase)
            divine_risk = ""
            if new_divine_attention > 70:
                divine_risk = f" At {new_divine_attention}% divine scrutiny, the risk of intervention grows concerning."
            elif new_divine_attention > 90:
                divine_risk = f" At {new_divine_attention}% divine scrutiny, divine intervention is almost certain without protective measures."
            
            embed.add_field(
                name="Divine Interest",
                value=f"{divine_desc} The splicing of souls is an act that draws notice from the higher realms.\n\n*\"This working will increase divine scrutiny by approximately {attention_increase}%,\"* Morrigan warns quietly.{divine_risk}",
                inline=False
            )
            pages.append(embed)
            
            # First, set pets to user_id 0 to prevent trading while request is processed
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE monster_pets SET user_id = 0 WHERE id IN ($1, $2)",
                    pet1_id, pet2_id
                )
                
                # NEW: Update forge condition and divine attention
                new_condition = max(0, forge_condition - condition_reduction)
                await conn.execute("""
                    UPDATE splicing_quest 
                    SET forge_condition = $1,
                        divine_attention = $2
                    WHERE user_id = $3 AND crucible_built = TRUE
                """, new_condition, new_divine_attention, ctx.author.id)
            
            if existing_splice:
                # If this combination has been spliced before, use the existing data
                new_pet_name = existing_splice["result_name"]
                
                # Page 3: The emergence (automatic creation)
                embed = discord.Embed(
                    title="✨ A New Creation Emerges ✨",
                    description="With a final surge of power that momentarily darkens all other lights in the vicinity, the Soulforge completes its work.",
                    color=0x4cc9f0
                )
                embed.add_field(
                    name="Birth of the Hybrid",
                    value=f"From the shimmering liquid rises a new creature - **{new_pet_name}**. It bears traits of both parent beings but is something entirely unique. Its body incorporates the strength of {pet1_data['name']} and the grace of {pet2_data['name']}, yet the combination has produced features neither possessed. Its eyes open, revealing an intelligence that recognizes you as its creator and master, yet contains memories of lives never lived in this form.\n\nIt steps from the basin, quicksilver dripping from its form and returning to the forge. As it approaches you, its essence stabilizes, colors becoming more vibrant, movements more confident. It makes a sound that combines aspects of both parent creatures, yet is harmonious rather than discordant.",
                    inline=False
                )
                embed.add_field(
                    name="Morrigan's Assessment",
                    value=f"*\"Fascinating,\"* Morrigan croons, examining the creation with analytical eyes. *\"It carries the strength of {pet1_data['name']} and the agility of {pet2_data['name']}, yet has developed qualities neither possessed alone. See how the essence patterns have created entirely new capabilities where they overlap? This is not mere combination but true transformation - the essence remembers its origin in greater beings.*\n\n*\"Treat it well, {name}. It is born of sacrifice and ancient power - a new link in the chain of being. In some ways, it is closer to the original Eidolons than either of its parents, for it represents the recombination of what was sundered. Each such creation heals, in some small measure, the wound inflicted upon reality during the Godswar.\"*",
                    inline=False
                )
                
                # NEW: Add forge aftermath information
                embed.add_field(
                    name="Forge Status",
                    value=f"*The Soulforge dims slightly as the ritual completes, the strain of the working evident. Fine cracks appear along the edge of the basin that slowly seal themselves, though not completely.*\n\n*\"The forge's condition has decreased to {new_condition}%,\"* Morrigan notes. *\"And divine scrutiny has increased to {new_divine_attention}%. We should be mindful of both as we continue our work.\"*",
                    inline=False
                )
                pages.append(embed)
                
                view = LoreView(pages, ctx.author.id)
                await ctx.send(embed=pages[0], view=view)
                
                # Create the spliced pet immediately using existing data
                async with self.bot.pool.acquire() as conn:
                    # Calculate baby stats
                    # Generate a random IV percentage between 50% and 100% (or other logic as needed)
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

                    # Calculate total IV points (for instance, 100% IV corresponds to 100 points we have halved this to slow the process of creating overpowered splices.)
                    total_iv_points = (iv_percentage / 100) * 100

                    def allocate_iv_points(total_points):
                        a = random.random()
                        b = random.random()
                        c = random.random()
                        total = a + b + c
                        hp_iv = total_points * (a / total)
                        attack_iv = total_points * (b / total)
                        defense_iv = total_points * (c / total)
                        hp_iv = int(round(hp_iv))
                        attack_iv = int(round(attack_iv))
                        defense_iv = int(round(defense_iv))
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

                    base_hp = existing_splice["hp"]
                    base_attack = existing_splice["attack"]
                    base_defense = existing_splice["defense"]
                    baby_hp = base_hp * stat_multiplier
                    baby_attack = base_attack * stat_multiplier
                    baby_defense = base_defense * stat_multiplier

                    baby_hp = baby_hp + hp_iv
                    baby_attack = baby_attack + attack_iv
                    baby_defense = baby_defense + defense_iv
                    
                    # Insert the new pet using data from the existing splice
                    new_pet_id = await conn.fetchval(
                        """
                        INSERT INTO monster_pets 
                        (user_id, name, hp, attack, defense, element, default_name, url, growth_stage, growth_time, "IV") 
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) 
                        RETURNING id
                        """,
                        ctx.author.id, 
                        new_pet_name, 
                        baby_hp,
                        baby_attack,
                        baby_defense,
                        existing_splice["element"],
                        new_pet_name, 
                        existing_splice["url"], 
                        'baby',
                        growth_time,
                        total_iv_points
                    )
                    
                
                # Send success message
                await ctx.author.send(f"You have successfully spliced your pets into a {new_pet_name}! Check your pets with `$pets`. Your forge's condition is now at {new_condition}% and divine scrutiny is at {new_divine_attention}%.")
                
            else:
                # If this is a new combination, create a request for admin approval
                temp_name = pet1_data["name"][:len(pet1_data["name"])//2] + pet2_data["name"][len(pet2_data["name"])//2:]
                
                # Page 3: The emergence with waiting message
                embed = discord.Embed(
                    title="✨ A New Creation Taking Form ✨",
                    description="The Soulforge's power surges, but the creature's form remains unstable and needs time to fully manifest.",
                    color=0x4cc9f0
                )
                embed.add_field(
                    name="Birth of the Hybrid",
                    value=f"The mercurial liquid begins to form a shape - a new being that will bear traits of both {pet1_data['name']} and {pet2_data['name']}. However, the creature's form seems to waver and shift, not yet fully committed to a final shape.\n\nThis unique combination will require time for the pattern to stabilize completely.",
                    inline=False
                )
                embed.add_field(
                    name="Morrigan's Instruction",
                    value=f"*\"This particular weaving is complex,\"* Morrigan explains, her dark eyes fixed on the swirling form. *\"The essence patterns need time to find their equilibrium. Return later to see what has emerged from your work. These creatures cannot be rushed into being - each is unique and must find its own path into existence.*\n\n*\"The forge will continue its work even in your absence, {name}. The patterns you have set in motion will resolve themselves in time.\"*",
                    inline=False
                )
                
                # NEW: Add forge aftermath information
                embed.add_field(
                    name="Forge Status",
                    value=f"*The Soulforge dims as the ritual completes, the strain of creating something entirely new evident in its slightly dulled glow.*\n\n*\"The forge's condition has decreased to {new_condition}%,\"* Morrigan notes. *\"And divine scrutiny has increased to {new_divine_attention}%. The gods take particular interest in novel creations - they fear what they cannot predict.\"*",
                    inline=False
                )
                pages.append(embed)
                
                view = LoreView(pages, ctx.author.id)
                await ctx.send(embed=pages[0], view=view)
                
                # Store the splice request
                async with self.bot.pool.acquire() as conn:
                    # Create table if it doesn't exist
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS splice_requests (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT,
                            pet1_id INTEGER,
                            pet2_id INTEGER,
                            pet1_name TEXT,
                            pet2_name TEXT,
                            pet1_default TEXT,
                            pet2_default TEXT,
                            temp_name TEXT,
                            pet1_hp INTEGER,
                            pet1_attack INTEGER,
                            pet1_defense INTEGER,
                            pet1_element TEXT,
                            pet1_url TEXT,
                            pet2_hp INTEGER,
                            pet2_attack INTEGER,
                            pet2_defense INTEGER,
                            pet2_element TEXT,
                            pet2_url TEXT,
                            status TEXT DEFAULT 'pending',
                            created_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    
                    splice_id = await conn.fetchval(
                        """
                        INSERT INTO splice_requests 
                        (user_id, pet1_id, pet2_id, pet1_name, pet2_name, pet1_default, pet2_default, temp_name,
                        pet1_hp, pet1_attack, pet1_defense, pet1_element, pet1_url,
                        pet2_hp, pet2_attack, pet2_defense, pet2_element, pet2_url) 
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18) 
                        RETURNING id
                        """,
                        ctx.author.id,
                        pet1_id, 
                        pet2_id, 
                        pet1_data["name"], 
                        pet2_data["name"],
                        pet1_data["default_name"],
                        pet2_data["default_name"],
                        temp_name,
                        pet1_data["hp"],
                        pet1_data["attack"],
                        pet1_data["defense"],
                        pet1_data["element"],
                        pet1_data["url"],
                        pet2_data["hp"],
                        pet2_data["attack"],
                        pet2_data["defense"],
                        pet2_data["element"],
                        pet2_data["url"]
                    )
                
                # Notify the admin
                admin = self.bot.get_user(self.splice_admin_user_id) if self.splice_admin_user_id else None
                if admin is None and self.splice_admin_user_id:
                    try:
                        admin = await self.bot.fetch_user(self.splice_admin_user_id)
                    except Exception:
                        admin = None
                if admin:
                    embed = discord.Embed(
                        title="New Splice Request",
                        description=f"User {ctx.author.name} (ID: {ctx.author.id}) has requested a splice.",
                        color=0x00ff00
                    )
                    embed.add_field(name="Splice ID", value=splice_id, inline=False)
                    embed.add_field(name="Pet 1", value=f"{pet1_data['name']} (Default: {pet1_data['default_name']})", inline=True)
                    embed.add_field(name="Pet 2", value=f"{pet2_data['name']} (Default: {pet2_data['default_name']})", inline=True)
                    embed.add_field(name="Temporary Name", value=temp_name, inline=False)
                    embed.add_field(name="Pet 1 Stats", value=f"HP: {pet1_data['hp']}, ATK: {pet1_data['attack']}, DEF: {pet1_data['defense']}, Element: {pet1_data['element']}\nURL: {pet1_data['url']}", inline=True)
                    embed.add_field(name="Pet 2 Stats", value=f"HP: {pet2_data['hp']}, ATK: {pet2_data['attack']}, DEF: {pet2_data['defense']}, Element: {pet2_data['element']}\nURL: {pet2_data['url']}", inline=True)
                    embed.add_field(name="Command", value=f"Splice ID {splice_id}`", inline=False)
                    embed.add_field(name="Forge Impact", value=f"Splice Rarity: {splice_rarity}\nForge Condition: {forge_condition}% → {new_condition}%\nDivine Attention: {current_divine_attention}% → {new_divine_attention}%", inline=False)
                    
                    await admin.send(embed=embed)
                
                # Let the player know they can check status
                await ctx.send(
                    f"*The Soulforge begins pulsing with purple and blue energies as primordial forces embrace your offering. The essence of your creatures slowly dissolves into the ancient crucible, where Eidolith fragments commence their delicate dance of transformation.*\n\n"
                    f"As Vaedrith's ancient texts warn: soul-binding cannot be rushed. The patterns must align naturally, following rhythms older than the gods themselves.\n\n"
                    f"Check your creation's progress: `$splicestatus {splice_id}`\n\n"
                    f"*Note: This splicing has reduced your forge's condition to {new_condition}% and increased divine scrutiny to {new_divine_attention}%.*"
                )

                await ctx.send("Splicing might take up to 2 days currently as we await support from the provider. ETA Monday")
        
        except Exception as e:
            await ctx.send(e)


    @commands.command()
    @user_cooldown(30)
    async def splicestatus(self, ctx, splice_id: int = None):
        """Check the status of your splice request"""
        await ctx.send("Splicing might take up to 2 days currently as we await support from the provider. ETA Monday")
        if not splice_id:
            # If no ID provided, list all pending splices for the user
            async with self.bot.pool.acquire() as conn:
                splices = await conn.fetch(
                    "SELECT id, pet1_name, pet2_name, status, created_at FROM splice_requests WHERE user_id = $1 ORDER BY created_at DESC",
                    ctx.author.id
                )
            
            if not splices:
                return await ctx.send("You don't have any splice requests.")
            
            # Use the paginator when there are splices to display
            paginator = SpliceStatusPaginator(ctx, splices)
            await paginator.start()
            return
        
        # Check specific splice status
        async with self.bot.pool.acquire() as conn:
            splice = await conn.fetchrow(
                "SELECT * FROM splice_requests WHERE id = $1 AND user_id = $2",
                splice_id, ctx.author.id
            )
        
        if not splice:
            return await ctx.send(f"No splice request found with ID {splice_id} for your account.")
        
        embed = discord.Embed(
            title=f"Splice Request #{splice['id']}",
            description=f"Status: **{splice['status'].capitalize()}**",
            color=0x00ff00 if splice["status"] == "completed" else 0xffaa00
        )
        
        embed.add_field(name="Pets Being Spliced", value=f"{splice['pet1_name']} + {splice['pet2_name']}", inline=False)
        embed.add_field(name="Requested", value=splice["created_at"].strftime("%Y-%m-%d %H:%M"), inline=False)
        
        
        if splice["status"] == "pending":
            embed.add_field(
                name="Morrigan's Update",
                value="*\"The essence patterns continue to swirl and intertwine within the Soulforge. This particular combination is finding its equilibrium. Such things cannot be rushed - the creation forms at its own pace, guided by ancient principles beyond mortal understanding.\"*",
                inline=False
            )
        elif splice["status"] == "completed":
            embed.add_field(
                name="Morrigan's Message",
                value="*\"Your creation has stabilized and emerged from the Soulforge. It awaits your guidance in this new existence. Every such being represents a unique pattern in the tapestry of life - nurture it well.\"*",
                inline=False
            )

        await ctx.send(embed=embed)


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
        """Distribute IV points between HP, Attack, and Defense
        
        Args:
            total_points: Total IV points to distribute
            
        Returns:
            Tuple of (hp_iv, attack_iv, defense_iv)
        """
        # Get three random values that sum to total_points
        # Use a weighted approach to avoid extremely unbalanced stats
        
        # First get 3 random values between 0 and 1
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
    
            
    def get_shard_discovery_dialogue(self, player_name, shard_count, crucible_built):
        """Returns varied dialogue for shard discovery based on progress"""
        dialogue_data = {}


        if crucible_built:
                titles = [
                    "Shard Fragment Recovered",
                    "Crystalline Essence Found",
                    "Eidolith Shard Acquired"
                ]
                
                descriptions = [
                    "A familiar crystalline fragment emerges from the defeated foe.",
                    "The creature's essence forms into a shard, similar to those you've collected before.",
                    "A glint of crystal catches your eye among the remains."
                ]
                
                dialogues = [
                    f"*\"Another shard for your collection,\"* Morrigan remarks. *\"Though the crucible is complete, these fragments may yet prove useful. Store it wisely, {player_name}.\"*",
                    f"*\"The essence still gathers,\"* Morrigan observes. *\"Even with the Soulforge built, these shards hold residual power. Perhaps we'll find a use for them in time.\"*",
                    f"*\"A shard, though our need is fulfilled,\"* Morrigan caws. *\"{player_name}, keep it secure - such concentrated essence is never without purpose.\"*"
                ]

                dialogue_data["title"] = random.choice(titles)
                dialogue_data["description"] = random.choice(descriptions)
                dialogue_data["dialogue"] = random.choice(dialogues)
                return dialogue_data

        
        # Early collection (shards 1-3)
        if shard_count <= 3:
            # Choose random title
            titles = [
                "💎 Eidolith Shard Discovered! 💎",
                "✨ Crystal Fragment Revealed! ✨",
                "🔮 Essence Shard Obtained! 🔮"
            ]
            
            # Choose random description
            descriptions = [
                "As your foe falls, a crystalline fragment emerges from its dissolving form, pulsing with inner light!",
                "The creature's final breath crystallizes in the air, forming a gleaming shard that drops to the ground.",
                "Something catches your eye in the remains of your foe - a glittering crystal that seems to sing a faint melody."
            ]
            
            # Choose random dialogue
            dialogues = [
                f"*\"Well done, {player_name}!\"* Morrigan caws, appearing suddenly on your shoulder. *\"Another piece of the puzzle. This shard bears the essence of your defeated enemy - I can sense its nature singing through the crystal. Keep it safe until we have gathered enough to begin the forging.\"*",
                
                f"*\"Ah! The essence reveals itself,\"* Morrigan observes, materializing from the shadows. *\"Each shard has its own song, {player_name}. This one speaks of {random.choice(['primal fury', 'ancient wisdom', 'elemental power', 'shifting form', 'hidden knowledge'])}. We need more to complete the pattern.\"*",
                
                f"*\"The Eidolith responds to your strength,\"* Morrigan notes, her form shimmering into existence. *\"You've claimed your {shard_count}{'st' if shard_count == 1 else 'nd' if shard_count == 2 else 'rd' if shard_count == 3 else 'th'} shard, {player_name}. The ancient essence recognizes a worthy vessel. Continue your hunt - the forge awaits completion.\"*"
            ]
        
        # Mid collection (shards 4-7)
        elif shard_count <= 7:
            titles = [
                "💠 Resonant Crystal Unearthed! 💠",
                "🔷 Pulsing Eidolith Acquired! 🔷",
                "💎 Vibrant Soul Shard Claimed! 💎"
            ]
            
            descriptions = [
                "Your defeated foe's essence doesn't dissipate but instead crystallizes into a shard that hovers momentarily before you catch it.",
                "A pulse of energy escapes your enemy as it falls, coalescing into a crystal that resonates with the other shards you've collected.",
                "The fallen creature's form seems to ripple, a portion of its essence separating to form a perfectly faceted crystal of unusual color."
            ]
            
            dialogues = [
                f"*\"Our collection grows,\"* Morrigan says with satisfaction. *\"This shard complements the others nicely. I can sense the patterns forming, {player_name} - the beginnings of a harmony that could remake what was broken. {10-shard_count} more will complete our needs.\"*",
                
                f"*\"The essence within this crystal seems particularly potent,\"* Morrigan observes, her feathers ruffling with excitement. *\"The shards call to each other now, {player_name}. Can you hear their distant song? It grows stronger with each addition.\"*",
                
                f"*\"We make good progress,\"* the raven notes, studying the new acquisition. *\"This is shard number {shard_count}, and it bears traces of {random.choice(['fire and shadow', 'earth and growth', 'water and memory', 'air and voice', 'time and potential'])}. The Soulforge will use these varied essences to create possibilities beyond imagination.\"*"
            ]
        
        # Late collection (shards 8-9)
        elif shard_count < 10:
            titles = [
                "🌟 Powerful Eidolith Manifested! 🌟",
                "✴️ Brilliant Soul Crystal Found! ✴️",
                "💠 Ancient Fragment Recovered! 💠"
            ]
            
            descriptions = [
                "The crystal that emerges from your defeated foe is larger and more intricate than previous shards, suggesting your collection nears completion.",
                "The air around you darkens momentarily as a gleaming shard tears itself from your enemy's essence, vibrating with potent energy.",
                "Your fallen opponent dissolves into pure light that condenses into a complex crystalline structure, more defined than earlier shards."
            ]
            
            dialogues = [
                f"*\"We near completion!\"* Morrigan exclaims, her voice resonating with unusual depth. *\"With {shard_count} shards in our possession, the possibility of rebuilding the Soulforge becomes tangible. The essences grow restless, {player_name} - they sense their purpose approaching.\"*",
                
                f"*\"The pattern clarifies,\"* Morrigan whispers, her eyes glowing with ancient light. *\"This shard bears powerful resonance with the others. The veil between what is and what could be grows thin. Only {10-shard_count} more to gather, {player_name}, before we can begin the great work.\"*",
                
                f"*\"I can almost see the completed Soulforge,\"* Morrigan says, her form seemingly larger in the shadows. *\"These shards vibrate in harmony now - each new addition strengthens the potential. {player_name}, we stand on the precipice of power that predates the gods themselves. Can you feel it calling to you?\"*"
            ]
        
        # Final shard (10th)
        else:
            titles = ["🌌 THE FINAL EIDOLITH SHARD! 🌌"]
            
            descriptions = [
                "The final shard erupts from your fallen foe in a brilliant cascade of light! The crystal is larger than the others, pulsing with complex patterns that seem to reflect the nine shards you've already collected."
            ]
            
            dialogues = [
                f"*\"AT LAST!\"* Morrigan's voice booms with uncharacteristic volume, echoing with multiple tones beneath her own. *\"The circle is complete, {player_name}! Ten shards of perfect resonance, enough to anchor the Soulforge's construction. Now we need only the Primer's knowledge and sufficient resources to begin the ritual. The power of creation draws near - gods themselves will take notice of what we undertake.\"*"
            ]
        
        dialogue_data["title"] = random.choice(titles)
        dialogue_data["description"] = random.choice(descriptions)  
        dialogue_data["dialogue"] = random.choice(dialogues)
        
        return dialogue_data
    
    

    @commands.Cog.listener()
    async def on_PVE_completion(self, ctx, success):
        """Listener for when a player completes PVE content"""
        if not success:
            return
            
        # Check if player is on the quest
        player_data = await self.get_player_data(ctx.author.id)
        if not player_data or not player_data["quest_started"]:
            return
            
        # Random chance to find a shard (10% chance)
        if random.random() <= 0.2:
            # Get current shard count before incrementing
            current_shards = player_data["shards"]
            
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE splicing_quest SET shards_collected = shards_collected + 1 WHERE user_id = $1',
                    ctx.author.id
                )
            
            # Get appropriate dialogue based on progress
            shard_dialogue = self.get_shard_discovery_dialogue(
                player_name=player_data["name"],
                shard_count=current_shards + 1,
                crucible_built=player_data["crucible_built"]
            )
            
            embed = discord.Embed(
                title=shard_dialogue["title"],
                description=shard_dialogue["description"],
                color=0x9d4edd
            )
            embed.add_field(
                name="Morrigan Appears",
                value=shard_dialogue["dialogue"],
                inline=False
            )
            await ctx.send(embed=embed)



    def get_primer_discovery_dialogue(self, player_name):
        """Returns varied dialogue for Alchemist's Primer discovery"""
        dialogue_data = {}
        
        # Choose random title
        titles = [
            "📕 The Alchemist's Primer Discovered! 📕",
            "📚 Ancient Tome of Soul-Binding Revealed! 📚",
            "📖 The Wyrdweaver Codex Uncovered! 📖",
            "🧮 The Book of Primal Patterns Found! 🧮",
            "📜 Vaedrith's Lost Grimoire Recovered! 📜"
        ]
        
        # Choose random description
        descriptions = [
            f"Hidden among ancient treasures, you find a leather-bound tome that seems to vibrate with arcane energy. As you touch it, the cover shifts and changes, briefly showing your reflection before settling into ornate patterns.",
            
            f"A book calls to you from amidst the raid's spoils - its binding made from materials you cannot identify. When you approach, its pages flip of their own accord, displaying diagrams that seem to move and breathe.",
            
            f"Something compels you to reach into a forgotten corner where a dust-covered volume lies hidden. When your fingers touch its spine, the book emits a soft sigh, as if awakening from a long slumber.",
            
            f"A strange weight draws your attention to what appears to be an ordinary journal. When you lift it, the pages glow with shifting text and illustrations of impossible mechanisms.",
            
            f"As you sort through the remnants of battle, a tome opens itself before you. Its pages are made of impossibly thin silver, inscribed with writing that changes depending on the angle from which you view it."
        ]
        
        # Choose random dialogue
        dialogues = [
            f"*\"AT LAST!\"* Morrigan caws, appearing suddenly on your shoulder, her feathers bristling with excitement. *\"The Primer reveals itself to you! It recognizes your potential, your connection to the ancient arts. With this, half our work is done. Guard it with your life, {player_name}. The secrets of ages rest in your hands - knowledge the gods themselves sought to erase from history.\"*",
            
            f"*\"The Book of Binding!\"* Morrigan's voice trembles with emotion as she materializes beside you. *\"Vaedrith's masterwork, preserved through centuries of hiding. It waited for one worthy of its secrets. Study it carefully, {player_name} - within its pages lie techniques that reshape the very fabric of souls. Some passages will only reveal themselves when you possess the necessary understanding.\"*",
            
            f"*\"The Codex returns to the world!\"* Morrigan circles above you in tight, excited spirals before landing. *\"I had almost forgotten its true appearance. This book is semi-sentient, {player_name} - it adapts to its reader, revealing knowledge as you become ready to comprehend it. The binding ritual for the Soulforge should now be accessible to you. The remaining instructions will appear when we gather sufficient shards.\"*",
            
            f"*\"After centuries of waiting...\"* Morrigan whispers, her form seeming to flicker between raven and shadowy human silhouette. *\"The Primer contains not just instructions, but the distilled consciousness of Wyrdweavers who preserved their knowledge within its pages. They will guide you, {player_name}, speaking through symbols and dreams as you progress in the art. Listen carefully to their whispered wisdom.\"*"
        ]
        
        dialogue_data["title"] = random.choice(titles)
        dialogue_data["description"] = random.choice(descriptions)
        dialogue_data["dialogue"] = random.choice(dialogues)
        
        return dialogue_data



    @commands.Cog.listener()
    async def on_raid_completion(self, ctx, success, participant):
        """Listener for when a player completes a raid"""
        if not success:
            return
            
        # Check if player is on the quest
        player_data = await self.get_player_data(participant)
        if not player_data or not player_data["quest_started"] or player_data["forge_built"] or player_data["primer"]:
            return
            

        elif random.random() < 0.05:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE splicing_quest SET primer_found = TRUE WHERE user_id = $1',
                    participant
                )
            
            primer_dialogue = self.get_primer_discovery_dialogue(player_data["name"])
            
            embed = discord.Embed(
                title=primer_dialogue["title"],
                description=primer_dialogue["description"],
                color=0xc77dff
            )
            embed.add_field(
                name="Morrigan's Revelation",
                value=primer_dialogue["dialogue"],
                inline=False
            )
            await ctx.send(embed=embed)




    @commands.Cog.listener()
    async def on_adventure_completion(self, ctx, success):
        """Listener for when a player completes an adventure"""
        
        try:
            if not success:
                return
                
            # Check if player has a character but hasn't started the quest yet
            player_data = await self.get_player_data(ctx.author.id)
            if not player_data or player_data["quest_started"]:
                return
            
            # Track how many hints this player has received
            async with self.bot.pool.acquire() as conn:
                hint_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM soulforge_hints WHERE user_id = $1 AND stat_name = 'soulforge_hints'", 
                    ctx.author.id
                )
                if hint_count is None:
                    hint_count = 0
                    
            # Determine hint frequency - more common as player encounters more adventures
            base_chance = 0.40
            chance_modifier = min(0.10, hint_count * 0.01)  # Up to +10% chance based on previous hints
            hint_chance = base_chance
            
            if random.random() < hint_chance:
                # Categorized hint types
                raven_sightings = [
                    "*A raven with eyes like molten gold watches you from a nearby branch. When your eyes meet, it tilts its head as if assessing your worthiness.*",
                    
                    "*The same raven again? You're certain you've seen this particular bird following you on multiple adventures. Its feathers seem to shimmer with an unnatural iridescence.*",
                    
                    "*A raven lands on your fallen enemy, pecking once at the corpse. It looks up at you and nods, as if approving of your combat technique.*",
                    
                    "*You glimpse a raven with what appears to be tiny gears embedded in its wings, glinting in the light before it vanishes into the shadows.*",
                    
                    "*A raven circles overhead three times before landing on a strange pattern in the ground that you hadn't noticed before. The pattern fades when the bird takes flight.*",
                    
                    "*While resting after battle, a raven approaches and seems to study your weapons with intelligent curiosity before flying away with a knowing caw.*",
                    
                    "*The raven's shadow doesn't match its form - it stretches into a humanoid shape before snapping back to normal when you blink.*"
                ]
                
                strange_sounds = [
                    "*You hear whispers just at the edge of comprehension, speaking of 'fragments,' 'essence,' and 'the forge awaits.' They fade when you focus on them.*",
                    
                    "*A discordant melody plays faintly on the wind - notes that shouldn't exist together yet somehow form a haunting harmony.*",
                    
                    "*The dying breath of your enemy crystallizes into a brief chime, like perfectly tuned glass bells, before dissipating.*",
                    
                    "*Your own heartbeat momentarily syncs with a deeper rhythm emanating from the earth beneath you, creating a strange resonance that makes your vision blur.*",
                    
                    "*Words form in your mind: 'The pattern requires completion.' The thought doesn't feel like your own.*",
                    
                    "*The wind carries fragments of a conversation: '...not ready yet...' '...stronger than the others...' '...soon, Vaedrith, soon...'*",
                    
                    "*Your weapons briefly hum with an unusual harmony when you clean your enemy's blood from them, as if recognizing something in the essence.*"
                ]
                
                strange_phenomena = [
                    "*For a split second, you can see the connections between all living things around you - glowing threads of varied colors linking predator to prey, tree to soil, and strangely, you to something very distant.*",
                    
                    "*Your shadow performs actions seconds before you do, then snaps back to normal. No one else seems to notice.*",
                    
                    "*The blood of your fallen foe briefly arranges itself into complex geometric patterns before soaking into the ground.*",
                    
                    "*You experience a moment of déjà vu so powerful that you can predict exactly how a nearby leaf will fall from its branch.*",
                    
                    "*Your reflection in a puddle of water shows someone else standing behind you - a robed figure with knowing eyes. You spin around to find nothing there.*",
                    
                    "*For a heartbeat, you perceive the world as pure patterns of energy rather than solid matter. The sensation is both enlightening and terrifying.*",
                    
                    "*The stars above briefly rearrange themselves into an unfamiliar constellation that resembles a crucible or cauldron before returning to their proper places.*",
                    
                    "*A nearby plant grows visibly when exposed to your enemy's final breath, its form taking on unusual properties before settling back to apparent normalcy.*"
                ]
                
                dreams_and_visions = [
                    "*You blink and see a momentary vision: a silver basin filled with quicksilver, reflecting faces that aren't your own.*",
                    
                    "*Between one heartbeat and the next, you dream of a tower where scholars in strange robes combine essences of different creatures into new, impossible forms.*",
                    
                    "*A flash of insight shows you the creature you just defeated not as flesh and bone, but as patterns of light held in temporary configuration.*",
                    
                    "*You briefly perceive your own body as a container of swirling light, with brighter concentrations in your head, heart, and hands.*",
                    
                    "*For a moment, you understand that the soul is not singular but composite - a mosaic of experiences and essences collected over many lifetimes.*",
                    
                    "*A whispered revelation comes to you: the gods themselves are not creators but collectors, gathering power from older sources now forgotten.*",
                    
                    "*You see your own hands working at a strange forge, combining elements that shouldn't exist. The vision feels like both memory and prophecy.*"
                ]
                
                environmental_reactions = [
                    "*Your magical items briefly pulse with unexpected energy, as if responding to something unseen in the vicinity.*",
                    
                    "*Animals in the area grow unnaturally quiet, watching you with unusual intensity as you collect your rewards.*",
                    
                    "*The temperature around you drops suddenly, your breath fogging in the chill air before returning to normal temperatures.*",
                    
                    "*A perfect circle of small mushrooms has grown around the site of your battle. They seem to have sprouted in the time it took to defeat your enemy.*",
                    
                    "*Your weapon briefly shimmers with unfamiliar runes that fade when you try to examine them closely.*",
                    
                    "*The ground beneath the fallen creature briefly turns crystalline and transparent, revealing glimpses of chambers deep underground before returning to normal earth.*",
                    
                    "*The sky above momentarily displays two moons instead of one, the second bearing patterns you somehow recognize despite never having seen them before.*"
                ]
                
                # Special hints that appear based on hint count (increasing specificity)
                progression_hints = []
                
                if hint_count >= 3:
                    progression_hints.extend([
                        "*The raven lands nearby and speaks directly into your mind: 'Your progress is noted. Continue to grow stronger.' Its voice feels ancient and composite, as if many beings speak through one form.*",
                        
                        "*You notice strange symbols temporarily etched into your skin that fade within moments. They resembled diagrams of soul patterns and ancient forge designs.*",
                        
                        "*Your dreams have begun to feature the same symbols repeatedly - a forge, a raven, shattered crystals, and a book that writes itself.*"
                    ])
                    
                if hint_count >= 7:
                    progression_hints.extend([
                        "*The raven appears larger each time you see it, its feathers now containing what appear to be pages of text that shift and change when you try to read them.*",
                        
                        "*You find yourself automatically sketching complex patterns in the dirt while resting - designs for some kind of forge or crucible that you don't consciously understand.*",
                        
                        "*When you close your eyes after battle, you see diagrams of what appears to be a soul's structure - complex lattices of light with points of concentrated energy.*"
                    ])
                    
                if hint_count >= 12:
                    progression_hints.extend([
                        "*'Seek the Tower's true purpose,' whispers the raven before dissolving into a cloud of mathematical equations that hang in the air momentarily.*",
                        
                        "*You awaken from a momentary daydream with the complete understanding of how to extract a soul's essence from a living being. The knowledge fades quickly, leaving only a lingering sense of loss.*",
                        
                        "*For one perfect moment, you perceive the world through the raven's eyes - seeing not physical forms but patterns of essence flowing through all things, some brighter than others, yours among the brightest.*"
                    ])
                
                # Special context hints based on location or enemy type
                special_hints = [
                    "*As the powerful creature falls, its essence doesn't dissipate normally. Instead, it briefly crystallizes before shattering into fragments that vanish into the air. The raven's distant call sounds almost frustrated.*",
                    
                    "*Your reflection in a nearby puddle shows not your face but a robed figure wearing a mask shaped like a raven's head. It places a finger to its lips before the water ripples, returning your normal reflection.*",
                    
                    "*The trees around you briefly transform into towering crystalline structures humming with inner light, their branches forming complex mathematical patterns. You blink, and they're normal trees again.*",
                    
                    "*Under moonlight, you notice that the shadows cast by ordinary objects form unfamiliar symbols on the ground - diagrams similar to alchemical formulas but far more complex.*",
                    
                    "*The fallen creature's body momentarily becomes transparent, revealing a swirling core of light that seems to be trying to escape its physical form before fading away.*",
                    
                    "*You hear a voice in perfect clarity: 'The Wyrdweavers' legacy awaits those who can hear the crystals sing.' The words seem to come from everywhere and nowhere.*"
                ]
                
                # Add hints about the Battle Tower if the player has been there
                tower_hints = [
                    "*You suddenly recall your time in the Battle Tower with new clarity - were those patterns on the walls actually diagrams rather than mere decoration?*",
                    
                    "*A fleeting thought crosses your mind: what if the Battle Tower isn't what it appears to be? The thought disappears before you can examine it closely.*",
                    
                    "*The raven caws three times and flies in a perfect spiral. For some reason, this reminds you of the Battle Tower's structure.*",
                    
                    "*You briefly remember a detail from the Battle Tower that seemed insignificant before - a recurring symbol that resembled a forge or crucible embedded in the architecture.*"
                ]
                
                # Combine all hint types and select one
                all_hints = raven_sightings + strange_sounds + strange_phenomena + dreams_and_visions + environmental_reactions
                
                # If player has seen enough hints, add progression hints
                if progression_hints and random.random() < 0.3:  # 30% chance of a progression hint when available
                    all_hints.extend(progression_hints)
                
                # Small chance for special hints
                if random.random() < 0.15:  # 15% chance for a special hint
                    all_hints.extend(special_hints)
                    
                # Add Battle Tower hints occasionally
                if random.random() < 0.2:  # 20% chance for a tower hint
                    all_hints.extend(tower_hints)
                    
                hint = random.choice(all_hints)
                
                # Special formatting for more mysterious presentation
                embed = discord.Embed(
                    description=hint,
                    color=0x7209b7  # A mysterious purple color
                )
                
                # Occasionally add a cryptic title (30% chance)
                if random.random() < 0.3:
                    cryptic_titles = [
                        "A Momentary Glimpse",
                        "Between Heartbeats",
                        "Whispers of the Pattern",
                        "Echoes of Forgotten Knowledge",
                        "The Veil Thins",
                        "Fragments of Understanding",
                        "The Observer",
                        "Patterns in Shadow",
                        "A Distant Call",
                        "Memories Not Your Own"
                    ]
                    embed.title = random.choice(cryptic_titles)
                
                await ctx.send(embed=embed)
                
                # Record this hint for the player to affect future hint chances
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO soulforge_hints (user_id, stat_name, stat_value, created_at) 
                        VALUES ($1, 'soulforge_hints', 1, NOW())
                        ON CONFLICT (user_id, stat_name) DO NOTHING""",
                        ctx.author.id
                    )
        except Exception as e:
            await ctx.send(e)




async def setup(bot):
    await bot.add_cog(Soulforge(bot))
    await bot.load_extension("cogs.soulforge.test_bg_removal")

    
