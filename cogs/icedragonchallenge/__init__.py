from decimal import Decimal

import discord
from discord.ext import commands
import asyncio
import random
from datetime import datetime, timedelta
from collections import deque

from cogs.shard_communication import user_on_cooldown
from utils.checks import has_char, is_gm, is_patreon
from utils.i18n import _
from utils import misc as rpgtools

class IceDragonChallenge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        ids_section = getattr(self.bot.config, "ids", None)
        dragon_ids = getattr(ids_section, "icedragonchallenge", {}) if ids_section else {}
        if not isinstance(dragon_ids, dict):
            dragon_ids = {}
        self.allowed_guild_id = dragon_ids.get(
            "allowed_guild_id", self.bot.config.game.support_server_id
        )
        self.reset_channel_id = dragon_ids.get("reset_channel_id")
        self.party_category_id = dragon_ids.get("party_category_id")
        self.party_deny_role_id = dragon_ids.get("party_deny_role_id")
        self.dragon_level = 1
        self.weekly_defeats = 0
        self.current_parties = {}
        self.unlocked = True
        self.last_reset = datetime.utcnow()

        # Dragon evolution stages
        self.DRAGON_STAGES = {
            "Frostbite Wyrm": {
                "level_range": (1, 5),
                "moves": {
                    "Ice Breath": {"dmg": 600, "effect": "freeze", "chance": 0.3},
                    "Tail Sweep": {"dmg": 400, "effect": "aoe", "chance": 0.4},
                    "Frost Bite": {"dmg": 300, "effect": "dot", "chance": 0.3}
                },
                "passives": ["Ice Armor"],
                "base_multiplier": 1.0
            },
            "Corrupted Ice Dragon": {
                "level_range": (6, 10),
                "moves": {
                    "Frosty Ice Burst": {"dmg": 800, "effect": "random_debuff", "chance": 0.3},
                    "Minion Army": {"dmg": 200, "effect": "summon_adds", "chance": 0.3},
                    "Frost Spears": {"dmg": 500, "effect": "dot", "chance": 0.4}
                },
                "passives": ["Corruption"],
                "base_multiplier": 1.15
            },
            "Permafrost": {
                "level_range": (11, 15),
                "moves": {
                    "Soul Reaver": {"dmg": 1000, "effect": "stun", "chance": 0.3},
                    "Death Note": {"dmg": 700, "effect": "curse", "chance": 0.3},
                    "Dark Shadows": {"dmg": 900, "effect": "aoe_dot", "chance": 0.4}
                },
                "passives": ["Void Fear"],
                "base_multiplier": 1.35
            },
            "Deathwing": {
                "level_range": (16, 20),
                "moves": {
                    "Spirit Drain": {"dmg": 1200, "effect": "steal_buffs", "chance": 0.3},
                    "Reaper's Verdic": {"dmg": 1500, "effect": "execute", "chance": 0.3},
                    "Voidrend Annihilation": {"dmg": 1000, "effect": "arena_hazard", "chance": 0.4}
                },
                "passives": ["Aspect of death"],
                "base_multiplier": 1.75
            }
        }

        # Stage-specific rewards
        self.STAGE_REWARDS = {
            "Frostbite Wyrm": {
                "items": [
                    ("Frozen Blade", "sword", 60, 80, 10000),
                    ("Ice Scale Shield", "shield", 60, 80, 10000),
                    ("Frost Warhammer", "hammer", 60, 80, 1000)
                ],
                "snowflakes": 175
            },
            "Corrupted Ice Dragon": {
                "items": [
                    ("Corrupted Present Sword", "sword", 65, 80, 10000),
                    ("Evil Toy Shield", "shield", 70, 80, 10000),
                    ("Dark Gift Bow", "bow", 170, 185, 10000)
                ],
                "snowflakes": 300
            },
            "Permafrost": {
                "items": [
                    ("Krampus Chain scythe", "scythe", 180, 185, 10000),
                    ("Punishment Plate", "shield", 80, 85, 10000),
                    ("fortune", "crate", 700)
                ],
                "snowflakes": 600
            },
            "Deathwing": {
                "items": [
                    ("World Ender", "wand", 80, 100, 10000),
                    ("Void Christmas shield", "shield", 80, 100, 10000),
                    ("Crown of Winter's Death", "axe", 80, 100, 10000)
                ],
                "snowflakes": 900
            }
        }

    async def get_current_stage(self, dragon_level=None):
        """Get current dragon stage based on level"""
        if dragon_level is None:
            async with self.bot.pool.acquire() as conn:
                result = await conn.fetchval(
                    'SELECT current_level FROM dragon_progress WHERE id = 1'
                )
                dragon_level = result if result else 1

        for stage, data in self.DRAGON_STAGES.items():
            min_level, max_level = data["level_range"]
            if min_level <= dragon_level <= max_level:
                return stage, data
        return list(self.DRAGON_STAGES.items())[-1]  # Return final stage if above all ranges


    async def calculate_dragon_stats(self):
        """Calculate dragon stats based on current level and stage"""
        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT current_level, weekly_defeats FROM dragon_progress WHERE id = 1'
            )
            if not result:
                # Initialize if not exists
                await conn.execute(
                    'INSERT INTO dragon_progress (id, current_level, weekly_defeats, last_reset) VALUES (1, 1, 0, $1)',
                    datetime.utcnow()
                )
                dragon_level = 1
            else:
                dragon_level = result['current_level']

        stage_name, stage_data = await self.get_current_stage(dragon_level)
        base_multiplier = stage_data["base_multiplier"]
        level_multiplier = 1 + (dragon_level * 0.15)  # 20% stronger each level

        # Add passive effects to dragon's stats
        passives = stage_data["passives"]
        passive_effects = {}
        if "Ice Armor" in passives:
            passive_effects["damage_reduction"] = 0.20
        if "Corruption" in passives:
            passive_effects["shield_reduction"] = 0.20
        if "Void Fear" in passives:
            passive_effects["attack_reduction"] = 0.20
        if "Aspect of death" in passives:
            passive_effects["attack_reduction"] = 0.30
            passive_effects["defense_reduction"] = 0.30

        return {
            "name": f"Level {dragon_level} {stage_name}",
            "hp": 3500 * base_multiplier * level_multiplier,
            "damage": 290 * level_multiplier,
            "armor": 220 * level_multiplier,
            "moves": stage_data["moves"],
            "passives": stage_data["passives"],
            "passive_effects": passive_effects,
            "stage": stage_name
        }

    async def check_weekly_reset(self):
        """Check and perform weekly reset if needed"""
        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT last_reset FROM dragon_progress WHERE id = 1'
            )

            if not result:
                return False

            now = datetime.utcnow()
            last_reset = result['last_reset']

            if now - last_reset >= timedelta(days=7):
                # Perform reset
                await conn.execute('''
                    UPDATE dragon_progress 
                    SET current_level = 1, 
                        weekly_defeats = 0, 
                        last_reset = $1 
                    WHERE id = 1
                ''', now)

                # Reset all players' weekly contributions
                await conn.execute('''
                    UPDATE dragon_contributions 
                    SET weekly_defeats = 0
                ''')

                # Send reset message
                reset_channel = (
                    self.bot.get_channel(self.reset_channel_id)
                    if self.reset_channel_id
                    else None
                )
                if reset_channel:
                    await reset_channel.send("❄️ **Weekly reset!** The Ice Dragon has been reset to level 1.")
                return True
            return False

    @is_gm()
    @commands.command()
    @has_char()
    async def unlockidc(self, ctx):
        if self.unlocked == True:
            await ctx.send("locked")
            self.unlocked = False
        else:
            self.unlocked = True
            await ctx.send("Ice Dragon Challenged has been successfully unlocked")

    @commands.group(invoke_without_command=True)
    @has_char()
    async def dragon(self, ctx):
        """Display current Ice Dragon status"""

        if self.unlocked == False:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send("This command is not ready yet.")
        await self.check_weekly_reset()

        dragon_stats = await self.calculate_dragon_stats()
        stage_name = dragon_stats["stage"]

        # Get current stats from DB
        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT current_level, weekly_defeats, last_reset FROM dragon_progress WHERE id = 1'
            )
            if not result:
                weekly_defeats = 0
                last_reset = datetime.utcnow()
            else:
                weekly_defeats = result['weekly_defeats']
                last_reset = result['last_reset']

        embed = discord.Embed(
            title=f"❄️ {dragon_stats['name']} ❄️",
            description=f"The **{stage_name}** awaits challengers...",
            color=0x87CEEB
        )

        # Add stats
        embed.add_field(
            name="**Dragon Stats**",
            value=f"**HP:** {dragon_stats['hp']:,.0f}\n"
                  f"**Damage:** {dragon_stats['damage']:,.0f}\n"
                  f"**Armor:** {dragon_stats['armor']:,.0f}"
        )

        # Add special moves
        moves_text = "\n".join([f"• {move}" for move in dragon_stats['moves'].keys()])
        embed.add_field(name="**Special Moves**", value=moves_text, inline=False)

        # Add progress
        next_level = 40 - (weekly_defeats % 40)
        embed.add_field(
            name="**Weekly Progress**",
            value=f"**Defeats:** {weekly_defeats}\n"
                  f"**Next Level:** {next_level} defeats\n"
                  f"**Weekly Reset:** {(last_reset + timedelta(days=7)).strftime('%Y-%m-%d')}",
            inline=False
        )

        await ctx.send(embed=embed)

    import asyncio
    import discord
    from discord.ext import commands

    @user_on_cooldown(7200)
    @is_patreon(min_tier=1)
    @dragon.command()
    async def channel(self, ctx, *members: discord.Member):
        """Creates a private channel for the specified members (1-3) and self-destructs after 20 minutes."""
        # Check guild ID
        if not self.allowed_guild_id or ctx.guild.id != self.allowed_guild_id:
            await ctx.send("This command can only be used in the specified guild.")
            self.bot.reset_cooldown(ctx)
            return


        # Define category and channel details
        category_id = self.party_category_id
        deny_role_id = self.party_deny_role_id

        # Fetch category
        category = discord.utils.get(ctx.guild.categories, id=category_id)
        if not category:
            await ctx.send("Category not found.")
            self.bot.reset_cooldown(ctx)
            return

        # Filter out the author and the bot if included
        valid_members = []
        for member in members:
            if member == ctx.author or member == ctx.guild.me:
                await ctx.send(f"You cannot add {member.mention} to the channel.")
                self.bot.reset_cooldown(ctx)
            else:
                valid_members.append(member)
        members = valid_members

        # Ensure at least one member and no more than 3 are specified
        if len(members) < 1:
            await ctx.send("You must specify at least one other user.")
            self.bot.reset_cooldown(ctx)
            return
        if len(members) > 6:
            await ctx.send("You can only specify up to 3 members.")
            self.bot.reset_cooldown(ctx)
            return

        # Create channel overwrites
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

        # Ensure the bot can manage the channel
        overwrites[ctx.guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            manage_messages=True
        )

        # Add specified members to overwrites
        for member in members:
            overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # Deny view permissions for specific role
        deny_role = ctx.guild.get_role(deny_role_id)
        if deny_role:
            overwrites[deny_role] = discord.PermissionOverwrite(view_channel=False)

        # Create channel
        channel_name = ctx.author.name.lower()
        channel = await category.create_text_channel(name=channel_name, overwrites=overwrites)

        # Send message in the newly created channel, mentioning the invited members
        member_mentions = ', '.join([m.mention for m in members])
        await channel.send(
            f"Private channel {channel.mention} created for {ctx.author.mention} "
            f"and {member_mentions}. It will self-destruct in 20 minutes."
        )

        # Wait 20 minutes and delete the channel
        await asyncio.sleep(20 * 60)

        for member in members:
            try:
                del self.current_parties[member.id]
            except KeyError:
                pass

            # If you also store the command author under self.current_parties,
            # delete them as well:
        try:
            del self.current_parties[ctx.author.id]
        except KeyError:
            pass

        await channel.delete(reason="Self-destruct timer expired")

    @is_patreon(min_tier=1)
    @user_on_cooldown(7200)
    @has_char()
    @dragon.command(name="party")
    async def create_party(self, ctx):
        """Create a dragon hunting party"""

        if not self.unlocked:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send("This command is not ready yet.")

        try:
            if isinstance(ctx.channel, discord.DMChannel) or ctx.guild.id != self.allowed_guild_id:
                #await self.bot.reset_cooldown(ctx)
                return await ctx.send("Dragon battles can only be started in the Fable server!")

            if ctx.author.id in self.current_parties:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send("You're already in a dragon hunting party!")

            party_members = [ctx.author]
            self.current_parties[ctx.author.id] = party_members
            embed = discord.Embed(title="🐉 Dragon Hunting Party", color=0x87CEEB)
            embed.description = f"Click ✅ to join the hunt! ({len(party_members)}/4 members)\n**Party Members:**"
            embed.add_field(name="1.", value=ctx.author.display_name, inline=False)

            # Define a custom View that accepts the cog instance
            class PartyView(discord.ui.View):
                def __init__(self, ctx, embed, party_members, cog):
                    super().__init__(timeout=60.0)
                    self.ctx = ctx
                    self.embed = embed
                    self.party_members = party_members
                    self.leader = ctx.author
                    self.msg = None
                    self.cog = cog  # store reference to the cog
                    self.battle_started = False  # new flag

                async def update_embed(self):
                    member_count = len(self.party_members)
                    self.embed.description = f"Click ✅ to join the hunt! ({member_count}/4 members)\n**Party Members:**"
                    self.embed.clear_fields()
                    for idx, member in enumerate(self.party_members, start=1):
                        self.embed.add_field(name=f"{idx}.", value=member.display_name, inline=False)
                    await self.msg.edit(embed=self.embed, view=self)

                @discord.ui.button(emoji="✅", style=discord.ButtonStyle.success, label="Join")
                async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user in self.party_members:
                        await interaction.response.send_message("You are already in the party!", ephemeral=True)
                        return
                    if len(self.party_members) >= 4:
                        await interaction.response.send_message("The party is already full!", ephemeral=True)
                        return
                    self.party_members.append(interaction.user)
                    await self.update_embed()
                    await interaction.response.send_message(f"{interaction.user.mention} joined the party!",
                                                            ephemeral=True)

                @discord.ui.button(emoji="❌", style=discord.ButtonStyle.danger, label="Leave")
                async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user == self.leader:
                        await interaction.response.send_message("You cannot leave your own party!", ephemeral=True)
                        return
                    if interaction.user not in self.party_members:
                        await interaction.response.send_message("You're not in the party!", ephemeral=True)
                        return
                    self.party_members.remove(interaction.user)
                    await self.update_embed()
                    await interaction.response.send_message(f"{interaction.user.mention} left the party.",
                                                            ephemeral=True)

                @discord.ui.button(emoji="⚔️", style=discord.ButtonStyle.primary, label="Start Battle")
                async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user != self.leader:
                        await interaction.response.send_message("Only the party leader can start the battle!",
                                                                ephemeral=True)
                        return

                    # Set flag and immediately stop the view so that its timeout is cancelled
                    self.battle_started = True
                    self.stop()

                    for child in self.children:
                        child.disabled = True
                    await interaction.response.edit_message(view=self)
                    await self.ctx.send("The battle is starting!")
                    try:
                        await self.cog.start_dragon_fight(self.ctx, self.party_members)
                    except Exception as e:
                        import traceback
                        error_message = f"Error while starting the battle: {e}\n" + traceback.format_exc()
                        await self.ctx.send(error_message)
                    finally:
                        try:
                            del self.cog.current_parties[self.leader.id]
                        except Exception:
                            pass

                async def on_timeout(self):
                    # Only run timeout code if the battle was never started
                    if self.battle_started:
                        return
                    try:
                        await self.ctx.send(f"{self.leader.mention}, party formation timed out!")
                        del self.cog.current_parties[self.leader.id]
                        await self.cog.bot.reset_cooldown(self.ctx)
                    except Exception:
                        pass


            # Instantiate view with the cog instance (self)
            view = PartyView(ctx, embed, party_members, cog=self)
            msg = await ctx.send(embed=embed, view=view)
            view.msg = msg

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n" + traceback.format_exc()
            await ctx.send(error_message)

    async def apply_effect(self, target, effect, damage, action_log):
        """Apply special effects from dragon moves"""
        effect_duration = 2  # rounds

        if effect == "freeze":
            target["frozen"] = effect_duration
            action_log.append(
                f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} is frozen solid! ❄️"
            )
        elif effect == "dot":
            dot_damage = round(float(damage) * 0.2, 2)
            target["dot"] = {"damage": dot_damage, "duration": effect_duration}
            action_log.append(
                f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} is taking frost damage over time! ☠️"
            )
        elif effect == "random_debuff":
            debuffs = ["damage_down", "armor_down"]
            debuff = random.choice(debuffs)

            # Store original stats before debuff
            if debuff == "damage_down":
                target["original_damage"] = target["damage"]  # Store original damage
                target["damage"] = round(float(target["damage"]) * 0.7, 2)  # Reduce damage by 30%
                debuff_text = "Damage heavily reduced%"
            elif debuff == "armor_down":
                target["original_armor"] = target["armor"]  # Store original armor
                target["armor"] = round(float(target["armor"]) * 0.7, 2)  # Reduce armor by 30%
                debuff_text = "Armor heavily reduced"

            # Store debuff info with duration
            target[debuff] = {
                "duration": effect_duration,
                "type": debuff
            }

            action_log.append(
                f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} is debuffed: {debuff_text}! ⚡"
            )
        elif effect == "summon_adds":
            num_soldiers = random.randint(1, 3)
            soldier_damage = round(float(damage) * 0.7 + 150, 2)  # Each soldier deals 70% of original damage
            total_soldier_damage = round(float(soldier_damage * num_soldiers), 2)
            target["hp"] = round(max(0, float(target["hp"]) - total_soldier_damage), 2)
            action_log.append(
                f"{num_soldiers} Minions appear and attack {target['user'].display_name if not target.get('is_pet') else target['pet_name']} for **{total_soldier_damage:,.2f}HP**!"
            )
        elif effect == "stun":
            target["stunned"] = effect_duration
            action_log.append(
                f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} is stunned! ⚡"
            )
        elif effect == "curse":
            target["cursed"] = effect_duration
            action_log.append(
                f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} is cursed! Defense is slightly reduced! 👻"
            )
        elif effect == "aoe_dot":
            dot_damage = round(float(damage) * 0.15, 2)  # 15% damage per turn
            target["dot"] = {"damage": dot_damage, "duration": effect_duration}
            action_log.append(
                f"🌀 Dark energy swirls around {target['user'].display_name if not target.get('is_pet') else target['pet_name']}, dealing damage over time!"
            )
        elif effect == "steal_buffs":
            target["buffs_stolen"] = effect_duration
            action_log.append(
                f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} had their buffs stolen! 💫"
            )
        elif effect == "aoe":
            # Don't log AOE message, it's handled in execute_dragon_move
            pass
        elif effect == "execute":
            if target["hp"] / target["max_hp"] <= 1.0:  # If target is below 20% HP
                damage = round(float(target["hp"]), 2)  # Instant kill
                target["hp"] = 0
                action_log.append(
                    f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} is executed! ⚰️"
                )
        elif effect == "arena_hazard":
            hazard_damage = round(float(damage) * 0.1, 2)
            target["arena_hazard"] = {"damage": hazard_damage, "duration": effect_duration}
            action_log.append(
                f"The arena is filled with deadly ice shards! ❄️"
            )

    async def execute_dragon_move(self, dragon_stats, targets, action_log):
        """Execute a special dragon move with clear damage messages"""
        stage_name, stage_data = await self.get_current_stage()
        moves = stage_data["moves"]

        selected_move = random.choices(
            list(moves.keys()),
            weights=[move["chance"] for move in moves.values()]
        )[0]
        move_data = moves[selected_move]

        if move_data["effect"] == "aoe":
            total_damage = []
            for target in targets:
                if target["hp"] <= 0:
                    continue
                bonus = Decimal(random.randint(0, 100))
                # Calculate damage and round to two decimal places
                damage = max(1, round(float(move_data["dmg"]) - float(target["armor"]) + float(bonus), 2))
                if target.get("damage_reduction"):
                    damage *= (1 - target["damage_reduction"])
                    damage = round(damage, 2)  # Round again after applying damage reduction
                target["hp"] = max(0, round(float(target["hp"]) - damage, 2))
                name = target['user'].display_name if not target.get('is_pet') else target['pet_name']
                total_damage.append(f"**{name}** ({damage:,.2f}HP)")
                # Apply effect without adding to action log
                await self.apply_effect(target, move_data["effect"], damage, [])

            action_log.append(f"Dragon unleashes **{selected_move}**!\nDamage dealt to: {' | '.join(total_damage)}")


        elif move_data["effect"] == "multihit":

            valid_targets = [t for t in targets if t["hp"] > 0]

            if valid_targets:

                target = random.choice(valid_targets)

                name = target['user'].display_name if not target.get('is_pet') else target['pet_name']

                hits = random.randint(2, 4)

                total_damage = 0

                for _ in range(hits):

                    base_damage = round(move_data["dmg"] / hits, 2)  # Ensure base damage is rounded

                    damage = max(1, round(base_damage - float(target["armor"]), 2))

                    if target.get("damage_reduction"):
                        damage *= (1 - target["damage_reduction"])

                        damage = round(damage, 2)  # Round after applying damage reduction

                    total_damage += damage

                    target["hp"] = max(0, round(float(target["hp"]) - damage, 2))

                action_log.append(f"Dragon unleashes **{selected_move}** on **{name}**!\n"

                                  f"Strikes {hits} times for **{total_damage:,.2f}HP** total damage!")

                # Apply effect after damage

                effect_log = []

                await self.apply_effect(target, move_data["effect"], total_damage, effect_log)

                # Add any effect messages to the action log

                action_log.extend(effect_log)



        else:  # Single target attacks

            valid_targets = [t for t in targets if t["hp"] > 0]

            if valid_targets:

                target = random.choice(valid_targets)

                name = target['user'].display_name if not target.get('is_pet') else target['pet_name']

                damage = max(1, round(move_data["dmg"] - float(target["armor"]), 2))

                if target.get("damage_reduction"):
                    damage *= (1 - target["damage_reduction"])

                    damage = round(damage, 2)  # Round after applying damage reduction

                target["hp"] = max(0, round(float(target["hp"]) - damage, 2))

                action_log.append(f"Dragon unleashes **{selected_move}** on **{name}**!\n"

                                  f"Deals **{damage:,.2f}HP** damage!")

                # Apply effect and collect any effect messages

                effect_log = []

                await self.apply_effect(target, move_data["effect"], damage, effect_log)

                # Add any effect messages to the action log

                action_log.extend(effect_log)

    def get_effect_text(self, effect):
        """Get descriptive text for effects"""
        effect_descriptions = {
            "freeze": " and is frozen",
            "dot": " and is bleeding",
            "random_debuff": " and is debuffed",
            "stun": " and is stunned",
            "curse": " and is cursed",
            "steal_buffs": " and loses buffs",
            "bleed": " and is bleeding",
            "arena_hazard": " from ice shards"
        }
        return effect_descriptions.get(effect, "")

    async def get_party_stats(self, ctx, party_members, conn):
        """Get raid stats for all party members"""
        party_combatants = []

        for member in party_members:
            try:
                # Get element first
                highest_element = await self.fetch_highest_element(member.id)

                # Get player's base stats and level
                query = 'SELECT class, xp, luck, health, stathp FROM profile WHERE "user" = $1;'
                result = await conn.fetchrow(query, member.id)

                if result:
                    # Get level from XP
                    xp = result["xp"]
                    level = rpgtools.xptolevel(xp)

                    # Get classes for special bonuses
                    classes = result["class"] if result["class"] else []

                    # Get luck
                    luck_value = float(result['luck'])
                    if luck_value <= 0.3:
                        Luck = 20.0
                    else:
                        Luck = ((luck_value - 0.3) / (1.5 - 0.3)) * 80 + 20
                    Luck = round(Luck, 2)

                    # Add luck booster if any
                    luck_booster = await self.bot.get_booster(member, "luck")
                    if luck_booster:
                        Luck += Luck * 0.25
                        Luck = min(Luck, 100.0)

                    # Get base health and stat HP
                    base_health = 200.0
                    health = float(result['health']) + base_health
                    stathp = float(result['stathp']) * 50.0

                    amulet_query = '''
                                        SELECT * 
                                        FROM amulets 
                                        WHERE user_id = $1 
                                        AND equipped = true 
                                        AND type = 'hp'
                                    '''
                    amulet_result = await conn.fetchrow(amulet_query, member.id)

                    # Add amulet HP bonus if equipped (implement your specific HP bonus logic here)
                    amulet_bonus = amulet_result["hp"] if amulet_result else 0  # bonus for HP amulet

                    # Get raid stats
                    dmg, deff = await self.bot.get_raidstats(member, conn=conn)

                    total_health = health + level * 15.0 + stathp + float(amulet_bonus)



                    # Calculate total health


                    # Create combatant
                    combatant = {
                        "user": member,
                        "hp": total_health,
                        "max_hp": total_health,
                        "armor": float(deff),
                        "damage": float(dmg),
                        "luck": Luck,
                        "level": level,
                        "element": highest_element,
                        "classes": classes,
                        "is_pet": False
                    }

                    # Get equipped pet if any
                    pet = await conn.fetchrow(
                        "SELECT * FROM monster_pets WHERE user_id = $1 AND equipped = TRUE;",
                        member.id
                    )

                    if pet:
                        pet_element = pet["element"].capitalize() if pet["element"] else "Unknown"
                        pet_combatant = {
                            "user": member,
                            "owner_id": member.id,
                            "pet_name": pet["name"],
                            "hp": float(pet["hp"]),
                            "max_hp": float(pet["hp"]),
                            "armor": float(pet["defense"]),
                            "damage": float(pet["attack"]),
                            "luck": 50.0,
                            "element": pet_element,
                            "is_pet": True
                        }
                        party_combatants.append((combatant, pet_combatant))
                    else:
                        party_combatants.append((combatant, None))

                else:
                    # Add default stats if no profile found
                    combatant = {
                        "user": member,
                        "hp": 500.0,
                        "max_hp": 500.0,
                        "armor": 50.0,
                        "damage": 50.0,
                        "luck": 50.0,
                        "level": 1,
                        "element": "Unknown",
                        "classes": [],
                        "is_pet": False
                    }
                    party_combatants.append((combatant, None))

            except Exception as e:
                await ctx.send(f"Error getting stats for {member.display_name}: {e}")
                # Add default stats in case of error
                combatant = {
                    "user": member,
                    "hp": 500.0,
                    "max_hp": 500.0,
                    "armor": 50.0,
                    "damage": 50.0,
                    "luck": 50.0,
                    "level": 1,
                    "element": "Unknown",
                    "classes": [],
                    "is_pet": False
                }
                party_combatants.append((combatant, None))

        return party_combatants

    async def update_battle_embed(self, battle_msg, dragon, battle_participants, battle_log):
        """Update the battle embed with the latest stats and battle log"""
        embed = discord.Embed(
            title=f"🐉 {dragon['name']} Battle",
            color=0x87CEEB
        )

        # Dragon HP
        hp_bar = self.create_hp_bar(dragon["hp"], dragon["max_hp"])
        embed.add_field(
            name=f"**[BOSS] {dragon['name']}**",
            value=f"**HP:** {dragon['hp']:,.1f}/{dragon['max_hp']:,.1f}\n{hp_bar}",
            inline=False
        )

        # Track which player each pet belongs to
        player_pets = {}
        for combatant in battle_participants:
            if combatant.get("is_pet"):
                player_pets[combatant["owner_id"]] = combatant

        # Track players in order of appearance to assign teams
        player_teams = {}  # Map player IDs to team letters
        team_letters = ['A', 'B', 'C', 'D']
        current_team = 0

        # First pass to assign teams to players
        for combatant in battle_participants:
            if not combatant.get("is_pet"):
                if combatant["user"].id not in player_teams and current_team < 4:
                    player_teams[combatant["user"].id] = team_letters[current_team]
                    current_team += 1

        # Display participants with proper team labels
        for combatant in battle_participants:
            current_hp = max(0, round(combatant["hp"], 1))
            max_hp = round(combatant["max_hp"], 1)
            hp_bar = self.create_hp_bar(current_hp, max_hp)

            # Gather status effects
            status_effects = []
            if combatant.get("frozen"): status_effects.append("❄️")
            if combatant.get("stunned"): status_effects.append("⚡")
            if combatant.get("dot"): status_effects.append("☠️")
            if combatant.get("cursed"): status_effects.append("👻")
            if combatant.get("damage_down"): status_effects.append("⬇️")
            if combatant.get("armor_down"): status_effects.append("🛡️")
            if combatant.get("buffs_stolen"): status_effects.append("💫")
            if combatant.get("healing_corrupted"): status_effects.append("🔻")
            if combatant.get("damage_reduction"): status_effects.append("🛡️")

            status = " ".join(status_effects)

            if not combatant.get("is_pet"):
                # For players, get their assigned team
                team = player_teams.get(combatant["user"].id, "?")
                name = f"**[TEAM {team}] {combatant['user'].display_name}** {status}"
            else:
                # For pets, use same team as their owner
                owner_id = combatant["owner_id"]
                team = player_teams.get(owner_id, "?")
                name = f"**[TEAM {team}] {combatant['pet_name']}** {status}"

            embed.add_field(
                name=name,
                value=f"**HP:** {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}",
                inline=False
            )

        # Add last 6 battle log entries
        last_logs = list(battle_log)[-6:]
        log_text = "\n\n".join(last_logs)
        embed.add_field(name="**Battle Log**", value=log_text, inline=False)

        await battle_msg.edit(embed=embed)


    async def fetch_highest_element(self, user_id):
        """Fetch highest element for a user"""
        try:
            highest_items = await self.bot.pool.fetch(
                "SELECT ai.element FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN "
                "inventory i ON (ai.id=i.item) WHERE i.equipped IS TRUE AND p.user=$1 "
                "ORDER BY GREATEST(ai.damage, ai.armor) DESC;",
                user_id,
            )
            highest_element = highest_items[0]["element"].capitalize() if highest_items and highest_items[0][
                "element"] else "Unknown"
            return highest_element
        except Exception as e:
            return "Unknown"

    async def create_battle_embed(self, dragon, battle_participants, battle_log):
        """Create the initial battle embed with stats and log"""
        embed = discord.Embed(
            title=f"🐉 {dragon['name']} Battle",
            color=0x87CEEB
        )

        # Dragon HP
        hp_bar = self.create_hp_bar(dragon["hp"], dragon["max_hp"])
        embed.add_field(
            name=f"**[BOSS] {dragon['name']}**",
            value=f"**HP:** {dragon['hp']:,.1f}/{dragon['max_hp']:,.1f}\n{hp_bar}",
            inline=False
        )

        # Track which player each pet belongs to
        player_pets = {}
        for combatant in battle_participants:
            if combatant.get("is_pet"):
                player_pets[combatant["owner_id"]] = combatant

        # Track players in order of appearance to assign teams
        player_teams = {}  # Map player IDs to team letters
        team_letters = ['A', 'B', 'C', 'D']
        current_team = 0

        # First pass to assign teams to players
        for combatant in battle_participants:
            if not combatant.get("is_pet"):
                if combatant["user"].id not in player_teams and current_team < 4:
                    player_teams[combatant["user"].id] = team_letters[current_team]
                    current_team += 1

        # Participants
        for combatant in battle_participants:
            current_hp = max(0, round(combatant["hp"], 1))
            max_hp = round(combatant["max_hp"], 1)
            hp_bar = self.create_hp_bar(current_hp, max_hp)

            # Gather all status effects
            status_effects = []
            if combatant.get("frozen"): status_effects.append("❄️")
            if combatant.get("stunned"): status_effects.append("⚡")
            if combatant.get("dot"): status_effects.append("☠️")
            if combatant.get("cursed"): status_effects.append("👻")
            if combatant.get("damage_down"): status_effects.append("⬇️")
            if combatant.get("armor_down"): status_effects.append("🛡️")
            if combatant.get("buffs_stolen"): status_effects.append("💫")
            if combatant.get("healing_corrupted"): status_effects.append("🔻")
            if combatant.get("damage_reduction"): status_effects.append("🛡️")

            status = " ".join(status_effects)

            if not combatant.get("is_pet"):
                # For players, get their assigned team
                team = player_teams.get(combatant["user"].id, "?")
                name = f"**[TEAM {team}] {combatant['user'].display_name}** {status}"
            else:
                # For pets, use same team as their owner
                owner_id = combatant["owner_id"]
                team = player_teams.get(owner_id, "?")
                name = f"**[TEAM {team}] {combatant['pet_name']}** {status}"

            embed.add_field(
                name=name,
                value=f"**HP:** {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}",
                inline=False
            )

        # Add battle log (initial log will only have the start message)
        embed.add_field(name="**Battle Log**", value="\n".join(list(battle_log)[-6:]), inline=False)

        return embed

    async def get_player_stats(self, playername, player_id):
        """Fetch player stats from the database."""

        async with self.bot.pool.acquire() as conn:


            query = 'SELECT "luck", "xp", "health", "stathp" FROM profile WHERE "user" = $1;'
            result = await conn.fetchrow(query, player_id)
            xp = result["xp"]
            base_health = 250
            health = result['health'] + base_health
            stathp = result['stathp'] * 50
            dmg, deff = await self.bot.get_raidstats(playername, conn=conn)
            player_level = rpgtools.xptolevel(xp)
            total_health = health + (player_level * 5)
            total_health += stathp

            amulet_query = '''
                                SELECT * 
                                FROM amulets 
                                WHERE user_id = $1 
                                AND equipped = true 
                                AND type = 'hp'
                            '''
            amulet_result = await conn.fetchrow(amulet_query, player_id)

            # Add amulet HP bonus if equipped
            amulet_bonus = amulet_result["hp"] if amulet_result else 0  # bonus for HP amulet

            total_health = amulet_bonus + total_health

            if query:
                return {
                    "hp": total_health,
                    "max_hp": total_health,
                    "damage": dmg,
                    "armor": deff
                }
            else:
                # Return default stats or handle as needed
                return {
                    "hp": 100,
                    "max_hp": 100,
                    "damage": 10,
                    "armor": 5
                }

    async def get_pet_stats(self, pet_id):
        """Fetch pet stats from the database."""
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT hp, attack, defense FROM monster_pets WHERE user_id = $1 AND equipped = true", pet_id)
            if row:
                return {
                    "hp": row["hp"],
                    "max_hp": row["hp"],
                    "damage": row["attack"],
                    "armor": row["defense"]
                }
            else:
                # Return default stats or handle as needed
                return {
                    "hp": 50,
                    "max_hp": 50,
                    "damage": 5,
                    "armor": 2
                }


    async def start_dragon_fight(self, ctx, party_members):
        """Start a fight with the Ice Dragon"""
        await self.check_weekly_reset()

        # Initialize dragon
        dragon_stats = await self.calculate_dragon_stats()
        dragon = {
            "name": dragon_stats["name"],
            "hp": dragon_stats["hp"],
            "max_hp": dragon_stats["hp"],
            "damage": dragon_stats["damage"],
            "armor": dragon_stats["armor"],
            "stage": dragon_stats["stage"],
            "passive_effects": dragon_stats["passive_effects"],
            "is_dragon": True
        }

        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT current_level, weekly_defeats, last_reset FROM dragon_progress WHERE id = 1'
            )
            if not result:
                weekly_defeats = 0
                current_level = 0
            else:
                current_level = result['current_level']
                weekly_defeats = result['weekly_defeats']
                last_reset = result['last_reset']
        #await ctx.send(f"Dragon initialized: {dragon['name']} with HP: {dragon['hp']}")

        # Get party stats
        async with self.bot.pool.acquire() as conn:
            party_stats = await self.get_party_stats(ctx, party_members, conn)

        # Debug: await ctx.send party_stats
        await ctx.send("Party Stats:")
        for idx, (player, pet) in enumerate(party_stats, start=1):
            player_name = player["user"].display_name if not player.get("is_pet", False) else player.get("pet_name",
                                                                                                         "Unknown Pet")
            pet_name = pet["pet_name"] if pet else "No Pet"
            #await ctx.send(f"  Member {idx}: Player: {player_name}, Pet: {pet_name}")




        # Ensure uniqueness in party members by converting to dictionaries
        unique_participants = {}
        battle_participants = []
        for player, pet in party_stats:
            # Handle player
            if not player.get("is_pet", False):
                player_id = player["user"].id
                playername = player["user"]
                if player_id not in unique_participants:
                    player_stats = await self.get_player_stats(playername, player_id)
                    # Get tank evolution level if any
                    async with self.bot.pool.acquire() as conn:
                        result = await conn.fetchrow('SELECT class FROM profile WHERE "user" = $1', player_id)
                        if result and result['class']:
                            classes = result['class'] if isinstance(result['class'], list) else [result['class']]

                            # Check for tank class
                            tank_evolution = None
                            tank_evolution_levels = {
                                "Protector": 1,
                                "Guardian": 2,
                                "Bulwark": 3,
                                "Defender": 4,
                                "Vanguard": 5,
                                "Fortress": 6,
                                "Titan": 7,
                            }

                            for class_name in classes:
                                if class_name in tank_evolution_levels:
                                    level = tank_evolution_levels[class_name]
                                    if tank_evolution is None or level > tank_evolution:
                                        tank_evolution = level

                            # Apply tank HP bonus if tank class found
                            if tank_evolution:
                                health_multiplier = 1 + (0.04 * tank_evolution)  # 5% per level
                                player_stats["hp"] *= health_multiplier
                                player_stats["max_hp"] *= health_multiplier

                    player_dict = {
                        "user": player["user"],
                        "hp": player_stats["hp"],
                        "max_hp": player_stats["max_hp"],
                        "damage": player_stats["damage"],
                        "armor": player_stats["armor"],
                        "is_dragon": False,
                        "is_pet": False,
                        "tank_evolution": tank_evolution if tank_evolution else None,
                    }
                    unique_participants[player_id] = player_dict
                    battle_participants.append(player_dict)

            else:
                # If player is already a pet or another type
                battle_participants.append(player)
                #await ctx.send(f"Added player (non-Member type) to battle: {player}")

            # Handle pet
            if pet:
                if pet.get("is_pet", False):
                    owner_id = pet.get("owner_id", "unknown_owner")
                    pet_name = pet.get("pet_name", "unknown_pet")
                    pet_unique_id = f"pet_{owner_id}_{pet_name}"
                    if pet_unique_id not in unique_participants:
                        pet_stats = await self.get_pet_stats(pet["user"].id)
                        pet_dict = {
                            "user": pet["user"],
                            "owner_id": owner_id,
                            "pet_name": pet_name,
                            "hp": pet_stats["hp"],
                            "max_hp": pet_stats["max_hp"],
                            "damage": pet_stats["damage"],
                            "armor": pet_stats["armor"],
                            "is_dragon": False,
                            "is_pet": True,
                            # Add other necessary attributes
                        }
                        unique_participants[pet_unique_id] = pet_dict
                        battle_participants.append(pet_dict)
                else:
                    # If pet is already a dictionary or another type
                    battle_participants.append(pet)
                    #await ctx.send(f"Added pet (non-Member type) to battle: {pet}")
            else:
                player_name = player["user"].display_name if not player.get("is_pet", False) else player.get("pet_name",
                                                                                                             "Unknown Pet")
                #await ctx.send(f"No pet for player: {player_name}")

        # Initialize battle turn order
        initial_turn_order = [dragon] + battle_participants
        random.shuffle(initial_turn_order)

        # Remove duplicates based on unique identifiers
        seen_ids = set()
        unique_turn_order = []
        for entity in initial_turn_order:
            if entity.get("is_dragon", False):
                entity_id = "dragon"
            elif entity.get("is_pet", False):
                owner_id = entity.get("owner_id", "unknown_owner")
                pet_name = entity.get("pet_name", "unknown_pet")
                entity_id = f"pet_{owner_id}_{pet_name}"
            else:
                entity_id = entity["user"].id

            if entity_id not in seen_ids:
                seen_ids.add(entity_id)
                unique_turn_order.append(entity)
                name = "Dragon" if entity.get("is_dragon", False) else (
                    entity["user"].display_name if not entity.get("is_pet", False) else entity["pet_name"]
                )
                #await ctx.send(f"Added to turn order: {name}")
        random.shuffle(unique_turn_order)

        battle_turn_order = unique_turn_order

        # Debug: await ctx.send final turn order
        #await ctx.send("Final battle turn order:")
        for entity in battle_turn_order:
            if entity.get("is_dragon", False):
                name = "Dragon"
            elif entity.get("is_pet", False):
                name = entity.get("pet_name", "Unknown Pet")
            else:
                name = entity["user"].display_name
            #await ctx.send(f"- {name}")

        # Initialize battle log and message
        battle_log = deque(maxlen=20)
        battle_log.append(f"**Action #1**\nThe battle against the Dragon has begun! 🐉")

        # Add passive effect descriptions
        passive_descriptions = []
        for passive in dragon_stats.get("passives", []):
            if passive == "Ice Armor":
                passive_descriptions.append("❄️ Ice Armor reduces all damage by 20%")
            elif passive == "Corruption":
                passive_descriptions.append("Corruption reduces shields/armor by 20%")
            elif passive == "Void Fear":
                passive_descriptions.append("😱 Void Fear reduces attack power by 20%")
            elif passive == "Aspect of death":
                passive_descriptions.append("💀 Aspect of death reduces attack and defense by 30%")

        if passive_descriptions:
            battle_log.append("**Dragon's Passive Effects:**\n" + "\n".join(passive_descriptions))

        # Create initial embed
        battle_msg = await ctx.send(embed=await self.create_battle_embed(dragon, battle_participants, battle_log))
        await asyncio.sleep(2)

        try:
            start_time = datetime.utcnow()
            action_number = 2
            battle_ongoing = True
            current_round = 1

            while battle_ongoing and datetime.utcnow() < start_time + timedelta(minutes=15):
                try:
                    #await ctx.send(f"--- Starting Round {current_round} ---")

                    # Reset turn order at start of each round to match initial order
                    active_turn_order = battle_turn_order.copy()
                    round_order_names = [
                        "Dragon" if entity.get("is_dragon", False) else (
                            entity["user"].display_name if not entity.get("is_pet", False) else entity["pet_name"]
                        )
                        for entity in active_turn_order
                    ]
                    #await ctx.send(f"Round {current_round} order: {round_order_names}")

                    # Process each participant's turn in the fixed order
                    for entity in active_turn_order:
                        if not battle_ongoing:
                            break

                        # Skip if entity died
                        if entity["hp"] <= 0:
                            name = "Dragon" if entity.get("is_dragon", False) else (
                                entity["user"].display_name if not entity.get("is_pet", False) else entity["pet_name"]
                            )
                            #await ctx.send(f"Skipping dead entity: {name}")
                            continue

                        # Check battle end conditions
                        if dragon["hp"] <= 0 or all(p["hp"] <= 0 for p in battle_participants):
                            battle_ongoing = False
                            break

                        # Rest of your turn processing code
                        current_action_log = []

                        if entity.get("is_dragon"):
                            # Dragon's turn
                            valid_targets = [p for p in battle_participants if p["hp"] > 0]
                            if not valid_targets:
                                battle_ongoing = False
                                break

                            use_special = random.random() < 0.4
                            if use_special:
                                await self.execute_dragon_move(dragon_stats, valid_targets, current_action_log)
                            else:
                                # Identify tanks among valid targets
                                tanks = [p for p in valid_targets if p.get("tank_evolution") is not None]

                                # 60% chance to target a tank if any exist
                                if tanks and random.random() < 0.85:
                                    target = random.choice(tanks)
                                else:
                                    target = random.choice(valid_targets)

                                bonus = Decimal(random.randint(0, 100))
                                # Calculate damage and round to two decimal places
                                damage = round(
                                    max(1, float(dragon["damage"]) - float(target["armor"]) + float(bonus), 2))
                                if target.get("damage_reduction"):
                                    damage *= (1 - target["damage_reduction"])
                                target["hp"] = max(0, target["hp"] - damage)
                                name = target["user"].display_name if not target.get("is_pet", False) else target[
                                    "pet_name"]
                                message = f"Dragon attacks **{name}** for **{damage:,.1f}HP** damage"

                                if target["hp"] <= 0:
                                    message += f"\n**{name}** has fallen! ☠️"
                                message += "!"
                                current_action_log.append(message)

                        else:
                            # Player/Pet turn
                            name = entity["user"].display_name if not entity.get("is_pet", False) else entity[
                                "pet_name"]

                            # Process status effects
                            can_attack = True
                            if entity.get("frozen") or entity.get("stunned"):
                                status = "frozen" if entity.get("frozen") else "stunned"
                                current_action_log.append(f"**{name}** is {status} and cannot move!")
                                can_attack = False

                                for status_effect in ["frozen", "stunned"]:
                                    if entity.get(status_effect):
                                        entity[status_effect] -= 1
                                        if entity[status_effect] <= 0:
                                            del entity[status_effect]

                            for debuff in ["damage_down", "armor_down"]:
                                if entity.get(debuff):
                                    entity[debuff]["duration"] -= 1
                                    if entity[debuff]["duration"] <= 0:
                                        # Restore original stats
                                        if debuff == "damage_down":
                                            entity["damage"] = entity["original_damage"]
                                            del entity["original_damage"]
                                        elif debuff == "armor_down":
                                            entity["armor"] = entity["original_armor"]
                                            del entity["original_armor"]
                                        del entity[debuff]
                                        current_action_log.append(
                                            f"**{name}**'s {debuff.replace('_', ' ')} effect has worn off!")

                            # Process DoTs
                            dot_damage = 0
                            for effect in ["dot", "arena_hazard"]:
                                if entity.get(effect):
                                    effect_data = entity[effect]
                                    damage = effect_data["damage"]
                                    entity["hp"] = max(0, entity["hp"] - damage)
                                    dot_damage += damage

                                    effect_data["duration"] -= 1
                                    if effect_data["duration"] <= 0:
                                        del entity[effect]

                            if can_attack and entity["hp"] > 0:
                                bonus = Decimal(random.randint(0, 100))
                                damage = max(1,
                                             round(float(entity["damage"]) - float(dragon["armor"]) + float(bonus), 2))

                                if entity.get("damage_down"):
                                    damage *= 0.7
                                dragon["hp"] = round(max(0, float(dragon["hp"]) - float(damage)), 2)

                                message = f"**{name}** attacks dragon for **{damage:,.1f}HP** damage"
                                if dot_damage > 0:
                                    message += f" and takes **{dot_damage:,.1f}HP** damage from bleeding"
                                if entity["hp"] <= 0:
                                    message += f"\n**{name}** has fallen! ☠️"
                                message += "!"
                                current_action_log.append(message)
                            elif dot_damage > 0:
                                message = f"**{name}** takes **{dot_damage:,.1f}HP** damage from bleeding"
                                if entity["hp"] <= 0:
                                    message += f"\n**{name}** has fallen! ☠️"
                                message += "!"
                                current_action_log.append(message)

                        # Log actions and update display
                        if current_action_log:
                            for log_entry in current_action_log:
                                battle_log.append(f"**Action #{action_number}**\n{log_entry}")
                                action_number += 1
                            await self.update_battle_embed(battle_msg, dragon, battle_participants, battle_log)
                            await asyncio.sleep(2)

                    #await ctx.send(f"--- End of Round {current_round} ---")
                    current_round += 1

                except Exception as e:
                    import traceback
                    error_message = f"Error occurred: {e}\n"
                    error_message += traceback.format_exc()
                    await ctx.send(error_message)
                    print(error_message)
                    continue

            # Handle battle end
            if dragon["hp"] <= 0:
                battle_log.append(f"**Action #{action_number}**\nThe dragon has been defeated! Victory! 🎉")
                await self.update_battle_embed(battle_msg, dragon, battle_participants, battle_log)
                await self.handle_victory(ctx, party_members, dragon, current_level, weekly_defeats)
            elif not any(p["hp"] > 0 for p in battle_participants):
                battle_log.append(f"**Action #{action_number}**\nThe party has been defeated! 💀")
                await self.update_battle_embed(battle_msg, dragon, battle_participants, battle_log)
                await self.handle_defeat(ctx, party_members)
            else:
                battle_log.append(f"**Action #{action_number}**\nTime's up! The battle was inconclusive! ⏰")
                await self.update_battle_embed(battle_msg, dragon, battle_participants, battle_log)
                await ctx.send("Time's up! The battle was inconclusive!")

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)


    def create_battle_log_entry(self, action_number, message):
        """Helper function to create properly formatted log entries"""
        return f"**Action #{action_number}**{message}"

    def create_hp_bar(self, current_hp, max_hp, length=20):
        """Create a visual HP bar"""
        ratio = max(0, min(1, current_hp / max_hp))
        filled = int(length * ratio)
        bar = "█" * filled + "░" * (length - filled)
        return bar

    @commands.hybrid_command(name="totalboard", description="Shows the top 10 dragon slayers and your rank")
    async def totalboard(self, ctx: commands.Context):
        async with self.bot.pool.acquire() as conn:
            # Get top 10
            top_10 = await conn.fetch('''
                SELECT user_id, total_defeats, 
                       RANK() OVER (ORDER BY total_defeats DESC) as rank
                FROM dragon_contributions 
                ORDER BY total_defeats DESC 
                LIMIT 10
            ''')
            # Get user's rank if not in top 10
            user_rank = await conn.fetchrow('''
                WITH rankings AS (
                    SELECT user_id, total_defeats,
                           RANK() OVER (ORDER BY total_defeats DESC) as rank
                    FROM dragon_contributions
                )
                SELECT * FROM rankings WHERE user_id = $1
            ''', ctx.author.id)

            embed = discord.Embed(title="🏆 Total Dragon Defeats Leaderboard", color=discord.Color.gold())
            # Format top 10
            leaderboard_text = ""
            for entry in top_10:
                leaderboard_text += f"{entry['rank']}. <@{entry['user_id']}> - {entry['total_defeats']} defeats\n"
            embed.description = leaderboard_text
            # Add user's rank if not in top 10
            if user_rank and not any(entry['user_id'] == ctx.author.id for entry in top_10):
                embed.add_field(
                    name="Your Rank",
                    value=f"#{user_rank['rank']} - {user_rank['total_defeats']} defeats",
                    inline=False
                )
            await ctx.send(embed=embed)

    @is_gm()
    @commands.hybrid_command()
    async def resetdragon(self, ctx, channel_id: int = None):
        """
        Reset the dragon progress and weekly contributions.
        Usage: $resetdragon [channel_id]
        """
        try:
            async with self.bot.pool.acquire() as conn:
                # Delete all rows from dragon_progress
                await conn.execute('DELETE FROM dragon_progress')

                # Insert fresh dragon_progress row
                await conn.execute('''
                    INSERT INTO dragon_progress (id, current_level, weekly_defeats, last_reset) 
                    VALUES (1, 1, 0, $1)
                ''', datetime.utcnow())

                # Reset weekly_defeats in dragon_contributions
                await conn.execute('''
                    UPDATE dragon_contributions 
                    SET weekly_defeats = 0
                ''')

                # Send confirmation to command user
                await ctx.send("✅ Dragon has been reset successfully!")

                # If channel_id is provided, send announcement
                if channel_id:
                    try:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            embed = discord.Embed(
                                title="🐉 Dragon Reset",
                                description="The Ice Dragon has been reset to level 1!\nAll weekly progress has been cleared.",
                                color=0x87CEEB
                            )
                            embed.add_field(
                                name="New Challenge Awaits!",
                                value="The Frostbite Wyrm awaits new challengers... Will you face the dragon?",
                                inline=False
                            )
                            await channel.send(embed=embed)
                        else:
                            await ctx.send("⚠️ Warning: Could not find the specified channel.")
                    except Exception as e:
                        await ctx.send(f"⚠️ Error sending announcement: {str(e)}")

        except Exception as e:
            await ctx.send(f"❌ Error resetting dragon: {str(e)}")

    @commands.hybrid_command(name="weeklyboard", description="Shows the top 10 weekly dragon slayers and your rank")
    async def weeklyboard(self, ctx: commands.Context):
        async with self.bot.pool.acquire() as conn:
            # Get top 10
            top_10 = await conn.fetch('''
                SELECT user_id, weekly_defeats,
                       RANK() OVER (ORDER BY weekly_defeats DESC) as rank
                FROM dragon_contributions 
                ORDER BY weekly_defeats DESC 
                LIMIT 10
            ''')
            # Get user's rank if not in top 10
            user_rank = await conn.fetchrow('''
                WITH rankings AS (
                    SELECT user_id, weekly_defeats,
                           RANK() OVER (ORDER BY weekly_defeats DESC) as rank
                    FROM dragon_contributions
                )
                SELECT * FROM rankings WHERE user_id = $1
            ''', ctx.author.id)


            reset_data = await conn.fetchrow('SELECT last_reset FROM dragon_progress WHERE id = 1')
            footer_text = "Reset time unavailable"
            if reset_data:
                last_reset = reset_data['last_reset']
                next_reset = last_reset + timedelta(days=7)
                now = datetime.utcnow()
                remaining = next_reset - now
                
                # Handle negative time (reset overdue)
                if remaining < timedelta(0):
                    remaining = timedelta(0)
                
                days = remaining.days
                seconds = remaining.seconds
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                footer_text = f"Time until next reset: {days}d {hours}h {minutes}m"


            embed = discord.Embed(title="🐉 Weekly Dragon Defeats Leaderboard", color=discord.Color.green())
            # Format top 10
            leaderboard_text = ""
            for entry in top_10:
                leaderboard_text += f"{entry['rank']}. <@{entry['user_id']}> - {entry['weekly_defeats']} defeats\n"
            embed.description = leaderboard_text
            # Add user's rank if not in top 10
            if user_rank and not any(entry['user_id'] == ctx.author.id for entry in top_10):
                embed.add_field(
                    name="Your Rank",
                    value=f"#{user_rank['rank']} - {user_rank['weekly_defeats']} defeats",
                    inline=False
                )
            embed.set_footer(text=footer_text)
            await ctx.send(embed=embed)

    async def handle_victory(self, ctx, party_members, dragon, old_level, weekly_defeats):
        """Handle victory rewards and progression"""
        dragon_stats = await self.calculate_dragon_stats()
        stage_name = dragon_stats["stage"]

        async with self.bot.pool.acquire() as conn:
            # Get the current timestamp
            current_time = datetime.now()

            # Iterate over party members
            for member in party_members:
                # Upsert query to update or insert a row
                await conn.execute(
                    '''
                    INSERT INTO dragon_contributions (user_id, weekly_defeats, total_defeats, last_defeat)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id) DO UPDATE
                    SET 
                        weekly_defeats = dragon_contributions.weekly_defeats + EXCLUDED.weekly_defeats,
                        total_defeats = dragon_contributions.total_defeats + EXCLUDED.total_defeats,
                        last_defeat = EXCLUDED.last_defeat
                    ''',
                    member.id,  # $1 - user_id
                    1,  # $2 - weekly_defeats
                    1,  # $3 - total_defeats
                    current_time  # $4 - last_defeat
                )

        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT current_level, weekly_defeats, last_reset FROM dragon_progress WHERE id = 1'
            )
            if not result:
                weekly_defeats = 0
                current_level = result['current_level']
            else:
                current_level = result['current_level']
                weekly_defeats = result['weekly_defeats']
                last_reset = result['last_reset']

        if old_level == current_level:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    '''
                    UPDATE dragon_progress
                    SET weekly_defeats = weekly_defeats + 1
                    '''
                )
            weekly_defeats = weekly_defeats + 1

            if weekly_defeats > 0 and weekly_defeats % 40 == 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute('''
                        UPDATE dragon_progress
                        SET current_level = current_level + 1
                    ''')
                await ctx.send(f"🐉 The dragon grows stronger! Now level **{current_level + 1}**! ⚔️")
        else:
            await ctx.send(
                "Someone beat the dragon and evolved it before you could kill it! You'll still receive your reward, but this fight will **not** count towards the weekly defeat.")

        rewards = self.STAGE_REWARDS[stage_name]

        async with self.bot.pool.acquire() as conn:
            for member in party_members:


                # Chance for special loot
                if random.random() < 0.01:  # 1% chance
                    item = random.choice(rewards["items"])
                    item_name, item_type, *stats = item

                    # Handle crate rewards
                    if item_type == "crate":
                        crate_type = item_name.lower()  # fortune or divine
                        await conn.execute(
                            f'UPDATE profile SET crates_{crate_type} = crates_{crate_type} + 1 WHERE "user"=$1;',
                            member.id
                        )
                        await ctx.send(f"{member.mention} found a **{item_name} crate**! 🎁")
                        continue

                    # Handle equipment rewards
                    item_type = item_type.capitalize()  # Capitalize first letter
                    element = random.choice(["water", "dark", "corrupted"])

                    # Determine hand based on item type
                    if item_type in ["Bow", "Scythe"]:
                        hand = "both"
                    elif item_type in ["Shield"]:
                        hand = "left"
                    else:  # Sword, Hammer, Axe, Wand <- Updated 2/2
                        hand = "any"

                    # Set damage or armor based on item type
                    damage = 0.0
                    armor = 0.0
                    if item_type == "Shield":
                        armor = round(random.uniform(stats[0], stats[1]))
                    else:
                        damage = round(random.uniform(stats[0], stats[1]))

                    # Create the item
                    await self.bot.create_item(
                        name=_(item_name),
                        value=stats[-1],  # Last number in tuple is value
                        type_=item_type,
                        element=element,
                        damage=damage,
                        armor=armor,
                        owner=member,
                        hand=hand,
                        equipped=False,
                        conn=conn,
                    )
                    await ctx.send(f"{member.mention} found a **{item_name}**! 🎁")

        victory_text = (
            f"🎉 **Victory!** The **{stage_name}** has been defeated!\n"
            #f"Each party member receives **{snowflakes_per_member:,} snowflakes**! ❄️"
        )
        await ctx.send(victory_text)

    async def handle_defeat(self, ctx, party_members):
        """Handle party defeat"""
        await ctx.send(
            f"💀 The **Dragon** was too powerful! "
            "The party has been defeated!"
        )

async def setup(bot):
    await bot.add_cog(IceDragonChallenge(bot))
    await bot.tree.sync()
