import asyncio
import datetime
import decimal
import random
from typing import Union, Optional

from discord import Embed, Member, Object

import fable.utils.misc as rpgtools
from collections import deque
from decimal import Decimal
from decimal import Decimal, ROUND_HALF_UP

import discord
import random as randomm
from discord.enums import ButtonStyle
from discord.ui import Select
from discord import SelectOption
from discord.ext import commands
from discord.ui.button import Button

from fable.core.classes import Ranger, Reaper
from fable.core.classes import from_string as class_from_string
from fable.core.converters import IntGreaterThan
from fable.systems.shard_communication import user_on_cooldown as user_cooldown
import random
from fable.utils.checks import has_char, has_money, is_gm
from fable.utils.i18n import _, locale_doc
from fable.utils.joins import SingleJoinView


# AI Opponent class to simulate a Discord member
class AIOpponent:
    # Class-level counter for unique IDs
    next_id = -1

    def __init__(self, bot, name=None):
        # Assign a unique negative ID
        self.id = AIOpponent.next_id
        AIOpponent.next_id -= 1  # Decrement for the next AI

        self.bot = bot

        # Generate fantasy name if none provided
        if name is None:
            self.name = self.generate_fantasy_name()
        else:
            self.name = name

        self.display_name = self.name
        self.mention = f"**{self.name}**"
        self.is_ai = True

    def __eq__(self, other):
        if isinstance(other, AIOpponent):
            return self.id == other.id
        return False

    def __hash__(self):
        # Return a hash based on the id - essential for dictionary keys
        return hash(self.id)

    def generate_fantasy_name(self):
        """Generate a fantasy name for the AI opponent."""
        titles = ["Archmage", "Guardian", "Warlord", "Sentinel", "Oracle", 
                 "Shadowmaster", "Dragonslayer", "Battlemage", "Runekeeper", "Spellblade"]
        
        descriptors = ["Ancient", "Eternal", "Mystic", "Forbidden", "Celestial", 
                      "Infernal", "Arcane", "Vengeful", "Relentless", "Thunderous"]
        
        names = ["Tharion", "Zephyra", "Kaldroth", "Seraphina", "Vexus", 
                "Malachai", "Drakonir", "Astrael", "Nyx", "Valorian"]
        
        # Combine elements to create a unique name
        if random.random() < 0.5:
            return f"{random.choice(titles)} {random.choice(names)}"
        else:
            return f"{random.choice(descriptors)} {random.choice(titles)}"


class Shotgunroulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Existing help command remains unchanged
    @commands.command(aliases=['srhelp'], help='Displays how to play Shotgun Roulette')
    @locale_doc
    async def shotgunroulettehelp(self, ctx):
        # Code remains the same as in the original
        _(
            """Display instructions on how to play Shotgun Roulette.

        This command provides detailed information and rules about the Shotgun Roulette game, including explanations of the gameplay, ammunition types, items, round mechanics, and item descriptions.

        Usage:
          `$shotgunroulettehelp`

        Note:
        - Use this command if you're new to the game or need a refresher on how to play."""
        )

        embed = discord.Embed(title="How to Play Shotgun Roulette",
                              description="A high-stakes game of chance and strategy for 2 players.",
                              color=discord.Color.dark_red())

        # Basic game explanation
        embed.add_field(name="👥 Players",
                        value="2 players take turns with a shotgun. Choose to shoot yourself or your opponent.",
                        inline=False)

        embed.add_field(name="🔫 Ammunition",
                        value="Ammo types: Blue <:shotgun_shell_blue:1225730810582405190> (blanks), Red <:shotgun_shell_red:1225730812826222632> (live). Aim to shoot the opponent with red and yourself with blue.",
                        inline=False)

        embed.add_field(name="🎁 Items",
                        value="At the start of each round, players are given a random set of items to use to their advantage.",
                        inline=False)

        embed.add_field(name="🔄 Round Mechanics",
                        value="Rounds continue with players taking turns. A round ends and resets once all rounds have been fired, and new items are distributed.",
                        inline=False)

        embed.add_field(name="⚖️ Turn Mechanics",
                        value="Shooting yourself with live ammo or the opponent with a blank passes the turn.\n\n\n**Items:**",
                        inline=False)

        # Detailed item explanations
        embed.add_field(name="🗡 Sawn Off",
                        value="Deal double damage for one round. Use it wisely to gain the upper hand.",
                        inline=False)

        embed.add_field(name="🩸 Bloodbag",
                        value="Gain one HP but cannot exceed your max HP. A second chance at life.",
                        inline=False)

        embed.add_field(name="🔗 Handcuffs",
                        value="Skip the opponent's next turn. Can't use repeatedly to chain stun.",
                        inline=False)

        embed.add_field(name="🍺 Beer",
                        value="Removes the current bullet in the shotgun. A gamble that can save you or doom you.",
                        inline=False)

        embed.add_field(name="🔎 Magnifying Glass",
                        value="Peek at the next bullet. Knowledge is power, use it to plan your next move.",
                        inline=False)

        await ctx.send(embed=embed)

    async def initilise(self, ctx, enemy_):
        # Your asynchronous code here
        initilise = True
        await ctx.send("Initializing game...")  # Example action
        hp_tracker = {}
        hp = random.randint(5, 8)
        if ctx.author not in hp_tracker:
            hp_tracker[ctx.author] = hp
        if enemy_ not in hp_tracker:
            hp_tracker[enemy_] = hp
        round = 1

        return hp_tracker, hp

    def subtract_hp(self, player, hp_tracker, amount):
        """Subtracts a specified amount of HP from a player in the hp_tracker."""
        if player in hp_tracker:
            hp_tracker[player] -= amount
            # Ensure HP does not go below 0
            hp_tracker[player] = max(hp_tracker[player], 0)
        else:
            print(f"Player {player} not found in HP tracker.")  # For debugging, replace with appropriate handling

        amount = 1
        return amount

    async def add_hp(self, ctx, player, hp_tracker, maxhp):
        amount = 1
        """Adds a specified amount of HP to a player in the hp_tracker without exceeding maxhp."""
        try:
            if player in hp_tracker:
                # Calculate potential new HP
                potential_hp = hp_tracker[player] + amount
                if potential_hp > maxhp:
                    # If adding HP would exceed the maxhp, do not add HP and return False.
                    print(
                        f"Adding {amount} HP to {player} would exceed max HP of {maxhp}. Operation not performed.")  # For debugging, replace with appropriate handling
                    return False
                else:
                    # Add HP but ensure it does not exceed maxhp
                    hp_tracker[player] += amount
                    return True
            else:
                print(f"Player {player} not found in HP tracker.")  # For debugging, replace with appropriate handling
                return False
        except Exception as e:
            await ctx.send(e)

    # AI strategy function
    async def ai_choose_action(self, ctx, player_items, bullet_color, hptracker, enemy, maxhp, known_bullet=None):
        """
        AI decision making logic for choosing an action in the game.
        Returns the best action based on the current game state.
        """
        ai_hp = hptracker.get(enemy, 0)
        player_hp = hptracker.get(ctx.author, 0)
        
        # Initialize weights for actions
        actions = {
            "shoot_player": 0,
            "shoot_self": 0
        }
        
        # Add item actions with 0 weight
        for emote, item in player_items:
            item_key = f"use_{item.lower().replace(' ', '_')}"
            actions[item_key] = 0
        
        # Base strategy based on bullet color
        if known_bullet or bullet_color:
            actual_bullet = known_bullet if known_bullet else bullet_color
            
            if actual_bullet == "Red":
                # With a live round, prefer shooting the player
                actions["shoot_player"] += 8
                actions["shoot_self"] -= 5
            else:  # Blue (blank)
                # With a blank, prefer shooting self
                actions["shoot_self"] += 8
                actions["shoot_player"] -= 5
        else:
            # Default probabilities if bullet unknown
            actions["shoot_player"] += 3
            actions["shoot_self"] += 2
        
        # Item usage strategies
        for emote, item in player_items:
            item_lower = item.lower()
            item_key = f"use_{item_lower.replace(' ', '_')}"
            
            if item_lower == "magnifying glass" and not known_bullet:
                # Highly value checking bullet if unknown
                actions[item_key] += 10
                
            elif item_lower == "bloodbag" and ai_hp < maxhp:
                # Use bloodbag when low on health
                health_deficit = maxhp - ai_hp
                actions[item_key] += min(7, health_deficit * 3)
                
            elif item_lower == "beer" and bullet_color == "Red":
                # Use beer to remove a known live round
                actions[item_key] += 9
                
            elif item_lower == "sawn off" and bullet_color == "Red":
                # Use sawn off with live rounds to maximize damage
                actions[item_key] += 7
                
            elif item_lower == "cuffs" and player_hp <= 2:
                # Use cuffs when opponent is in a critical state
                actions[item_key] += 8
        
        # Adjust strategy based on health states
        if ai_hp <= 2:
            # Desperate measures when low on health
            actions["shoot_player"] += 3  # Take more risks
            
            # Prioritize bloodbag if available
            for emote, item in player_items:
                if item.lower() == "bloodbag":
                    actions[f"use_{item.lower().replace(' ', '_')}"] += 10
        
        if player_hp <= 2:
            # Go for the kill when opponent is low
            actions["shoot_player"] += 4
        
        # Choose the action with the highest weight
        best_action = max(actions, key=actions.get)
        
        # Log the decision process (for debugging)
        # print(f"AI decision weights: {actions}, chose: {best_action}")
        
        return best_action

    async def get_action(self, ctx, player_items, attacker: Union[discord.Member, AIOpponent], anticuffstunlock, bullet_color,
                         turncounter, hptracker, maxhp, last_used_cuffs):
        # Check if the attacker is an AI
        if hasattr(attacker, 'is_ai') and attacker.is_ai:
            # Use AI logic to determine the action
            action = await self.ai_choose_action(
                ctx, 
                player_items, 
                bullet_color, 
                hptracker, 
                attacker, 
                maxhp
            )
            
            # Handle item usage for AI
            if action.startswith("use_"):
                item_used = action.replace("use_", "").replace("_", " ")
                
                # Handle bloodbag separately
                if item_used == "bloodbag" and not await self.add_hp(ctx, attacker, hptracker, maxhp):
                    await ctx.send(f"**{attacker.display_name}** tried to use a bloodbag but is already at max HP.")
                    # Choose another action instead
                    if bullet_color == "Red":
                        action = "shoot_player"
                    else:
                        action = "shoot_self"
                else:
                    # Remove the used item from AI's inventory
                    for i, (emote, item) in enumerate(player_items):
                        if item.lower() == item_used:
                            del player_items[i]
                            await ctx.send(f"**{attacker.display_name}** uses {emote} {item}")
                            break
            
            # Short delay to make it feel like the AI is thinking
            await asyncio.sleep(1.5)
            
            return action, anticuffstunlock, player_items
            
        else:
            # Human player logic (original code)
            class UniqueActionSelect(discord.ui.Select):
                def __init__(self, options, **kwargs):
                    super().__init__(placeholder="Choose an action", min_values=1, max_values=1, options=options, **kwargs)

                async def callback(self, interaction: discord.Interaction):
                    # Check if the user interacting is the attacker
                    if interaction.user.id != attacker.id:
                        # Directly respond to unauthorized users without deferring since we're immediately responding
                        await interaction.response.send_message("You're not the attacker!", ephemeral=True)
                        return

                    self.view.result = self.values[0]
                    # Respond to the attacker's interaction

                    self.disabled = True  # Optionally disable the select after a choice is made
                    self.view.stop()
                    await interaction.message.delete()
                    # Note: Deleting the message here would remove the entire interaction context, consider this action carefully.

            class ActionView(discord.ui.View):
                def __init__(self, *args, timeout=60, **kwargs):
                    super().__init__(*args, timeout=timeout, **kwargs)
                    self.result = None
                    self.message = None  # Placeholder for the message reference

                async def on_timeout(self):
                    self.result = "none"
                    for item in self.children:
                        item.disabled = True
                    self.stop()
                    if self.message:  # Check if the message reference exists
                        await self.message.delete()  # Attempt to delete the message

            # Prepare the options for the dropdown menu
            options = [
                discord.SelectOption(label="Shoot Player", value="shoot_player"),
                discord.SelectOption(label="Shoot Self", value="shoot_self")
            ]

            seen_items = set()
            # Assuming `last_used_cuffs` is a variable that tracks the member object of the last user of cuffs
            # and `anticuffstunlock` tracks the cooldown

            for emote, item in player_items:
                # Adjust the check to incorporate `last_used_cuffs`
                # Skip adding "Cuffs" to the options if anticuffstunlock > 0 and the attacker was the last to use cuffs
                if item.lower() == "cuffs" and anticuffstunlock > 0 and attacker == last_used_cuffs:
                    continue
                if item not in seen_items:
                    seen_items.add(item)
                    option_label = f"{emote} {item}"
                    # Normalize the item name for the value, replacing spaces with underscores and lowercasing
                    option_value = f"use_{item.replace(' ', '_').lower()}"
                    options.append(discord.SelectOption(label=option_label, value=option_value))

            select = UniqueActionSelect(options=options)
            view = ActionView(timeout=60)  # No longer passing author_id since we're not using interaction_check
            view.add_item(select)

            # Send the message with the dropdown menu and wait for interaction
            message = await ctx.send(f"**{attacker.display_name}**, select an action:", view=view)
            view.message = message  # Store the message reference in the view
            await view.wait()

            if view.result is None or view.result == "none":
                # Handle the case where no action was selected or the view timed out
                await ctx.send(f"**{attacker.display_name}** did not select an action in time. Take 1 DMG and skip turn.")
                anticuffstunlock = 0

                return "none", anticuffstunlock, player_items
            else:
                selected_action = view.result
                item_used = None  # Placeholder for the used item's name
                # Assume this part happens after the action is selected but before the final inventory update
                if selected_action.startswith("use_"):
                    item_used = selected_action.replace("use_", "").replace("_", " ")
                    # Let's assume add_hp returns False if the action is unsuccessful (like exceeding maxHP)
                    if item_used == "bloodbag" and not await self.add_hp(ctx, attacker, hptracker, maxhp):
                        # If the bloodbag use is unsuccessful, inform the player and do not remove the bloodbag
                        await ctx.send(
                            f"**{attacker.display_name}**, using a bloodbag would exceed your max HP. Bloodbag not used.")
                    else:
                        # If it's not a bloodbag or if the action is successful, proceed to remove the item
                        item_found = False  # Flag to check if the item was found and removed
                        for i, (emote, item) in enumerate(player_items):
                            # Ensure the first letter of each word is capitalized for comparison
                            formatted_item = " ".join(word.capitalize() for word in item.split())
                            formatted_item_used = " ".join(word.capitalize() for word in item_used.split())

                            if formatted_item == formatted_item_used:
                                del player_items[i]
                                item_found = True
                                break

                        if not item_found:
                            await ctx.send(
                                f"Item **{formatted_item_used}** not found in {attacker.display_name}'s inventory or already used.")

                        # If the action was a successful use of a bloodbag, send a confirmation message
                        if item_used == "bloodbag":
                            # await self.add_hp(ctx, attacker, hptracker, maxhp)
                            await ctx.send(
                                f"**{attacker.display_name}** successfully used a bloodbag and now has: {hptracker[attacker]} ❤️")

                # After waiting, the select may be disabled and the response collected
                return view.result, anticuffstunlock, player_items

    async def roundsettings(self, ctx, hptracker, enemy_: Union[discord.Member, AIOpponent], round):
        try:
            try:
                await ctx.send("Round Settings")
                import random
                player1 = ctx.author  # The command issuer
                player2 = enemy_  # The other participant
                if round == 1:
                    attacker, defender = random.sample([player1, player2], 2)

                # Initialize the embed
                embed = discord.Embed(title=f"Round {round}")

                # Define bullet types
                bullets = [
                    {"emote": "<:shotgun_shell_blue:1225730810582405190>", "color": "Blue"},
                    {"emote": "<:shotgun_shell_red:1225730812826222632>", "color": "Red"}
                ]

                # Ensure at least one of each color, then distribute the rest
                async def generate_bullets():
                    # Minimum 1 bullet of each color to start
                    bullet_counts = {"Blue": 1, "Red": 1}

                    # Randomly choose total number of bullets (2-8), ensuring minimum 2 accounted for above
                    total_bullets = random.randint(2, 8)

                    # Distribute remaining bullets randomly, up to a maximum of 4 per color
                    for _ in range(total_bullets - 2):  # Adjust for the initial 2 bullets already added
                        chosen_color = random.choice(["Blue", "Red"])
                        if bullet_counts[chosen_color] < 4:
                            bullet_counts[chosen_color] += 1

                    # Build the final list of bullets based on the counts
                    random_bullets = []
                    for bullet in bullets:
                        random_bullets.extend([bullet] * bullet_counts[bullet["color"]])

                    # Shuffle to avoid predictable order
                    random.shuffle(random_bullets)

                    return random_bullets

                # Generate bullets with the new constraints
                random_bullets = await generate_bullets()

                bullet_list = "\n".join(
                    [f"{i + 1}. {bullet['emote']} {bullet['color']}" for i, bullet in enumerate(random_bullets)])

                # Add bullets section to the embed
                embed.add_field(name="Bullets", value=bullet_list, inline=False)

                # Items generation corrected to generate items for each player separately
                emotes_items = {
                    "🩸": "Bloodbag",
                    "🔗": "Cuffs",
                    "🔎": "Magnifying glass",
                    "🍺": "Beer",
                    "🗡️": "Sawn Off"
                }

                # Assuming each player should have a randomly generated, possibly overlapping set of items
                player_items_dict = {
                    player: [(emote, item) for emote, item in
                             random.choices(list(emotes_items.items()), k=random.randint(1, 5))]
                    for player in [ctx.author, enemy_]
                }

                # Add items section to the embed, corrected for each player
                for player, items in player_items_dict.items():
                    item_list_str = "\n".join([f"- {emote} {item}" for emote, item in items])
                    embed.add_field(name=f"{player.display_name}'s Items",
                                    value=item_list_str if item_list_str else "No Items", inline=False)

                # HP Display
                player_hp = hptracker.get(ctx.author, 'Unknown')
                enemy_hp = hptracker.get(enemy_, 'Unknown')
                hp_display = f"{player1.display_name}: {player_hp}\n{player2.display_name}: {enemy_hp}"
                embed.add_field(name="Current HP", value=hp_display, inline=False)

                # Send the embed
                await ctx.send(embed=embed)
                random.shuffle(random_bullets)  # Shuffle the bullets
                if round == 1:
                    return random_bullets, player_items_dict, attacker, defender
                else:
                    return random_bullets, player_items_dict
            except Exception as e:
                await ctx.send(e)
        except Exception as e:
            await ctx.send(e)

    async def gamelogic(self, ctx, random_bullets, attacker: Union[discord.Member, AIOpponent], 
                       defender: Union[discord.Member, AIOpponent], player_items_dict, 
                       hptracker, enemy_: Union[discord.Member, AIOpponent], maxhp):
        turncounter = 0
        anticuffstunlock = 0

        use_magnifying_glass = False
        use_cuffs = False
        use_beer = False
        use_sawn_off = False
        last_used_cuffs = None
        damage = 1
        known_bullet = None  # For AI to remember magnifying glass results
        
        while random_bullets:
            bullet_color = random_bullets[0]['color']
            
            # If attacker is AI and has used magnifying glass, remember the bullet
            if hasattr(attacker, 'is_ai') and attacker.is_ai:
                action, anticuffstunlock, updated_items = await self.get_action(
                    ctx, player_items_dict[attacker], attacker,
                    anticuffstunlock, bullet_color, turncounter,
                    hptracker, maxhp, last_used_cuffs
                )
            else:
                action, anticuffstunlock, updated_items = await self.get_action(
                    ctx, player_items_dict[attacker], attacker,
                    anticuffstunlock, bullet_color, turncounter,
                    hptracker, maxhp, last_used_cuffs
                )
                
            player_items_dict[attacker] = updated_items

            # Determining which action was selected
            if action == "use_magnifying_glass":
                if bullet_color == "Blue":
                    await ctx.send(f"{attacker.display_name} looks inside the loading port..")
                    await ctx.send("<:shotgun_shell_blue:1225730810582405190>")
                    if hasattr(attacker, 'is_ai') and attacker.is_ai:
                        known_bullet = "Blue"
                else:
                    await ctx.send(f"{attacker.display_name} looks inside the loading port..")
                    await ctx.send("<:shotgun_shell_red:1225730812826222632>")
                    if hasattr(attacker, 'is_ai') and attacker.is_ai:
                        known_bullet = "Red"

            elif action == "use_beer":
                if bullet_color == "Blue":
                    await ctx.send(
                        f"{attacker.display_name} cocked the shotgun.. a <:shotgun_shell_blue:1225730810582405190> flew out")
                else:
                    await ctx.send(
                        f"{attacker.display_name} cocked the shotgun.. a <:shotgun_shell_red:1225730812826222632> flew out")

                random_bullets.pop(0)
                known_bullet = None  # Reset known bullet after beer

            elif action == "none":
                dmg = 1
                self.subtract_hp(attacker, hptracker, dmg)
                use_cuffs = False
                damage = 1
                attacker, defender = defender, attacker
                known_bullet = None  # Reset known bullet on turn change

            elif action == "use_sawn_off":
                await ctx.send(
                    f"**{attacker.display_name}** sawn the end of the shotgun off! it now will deal **x2** damage until the next turn.")
                damage = 2
                
            # Inside your gamelogic or get_action method, when checking the action
            elif action == "use_cuffs":
                if last_used_cuffs == attacker and anticuffstunlock > 0:
                    # Handcuffs are on cooldown for this player
                    await ctx.send("Cuffs are still on cooldown and cannot be used this turn.")
                else:
                    # Apply handcuffs, set the user of handcuffs, and initiate cooldown
                    await ctx.send(f"Cuffs have been used by {attacker.display_name}!")
                    use_cuffs = True
                    last_used_cuffs = attacker
                    anticuffstunlock = 2  # Starting cooldown

            elif action == "shoot_self":
                bullet_color = random_bullets[0]['color']
                if bullet_color == "Blue":
                    random_bullets.pop(0)
                    await ctx.send(f"**{attacker.display_name}** turns the shotgun to themselves and pulls the trigger..")
                    await asyncio.sleep(2)
                    await ctx.send(f"‍💨 It was a blank! **{attacker.display_name}** gets another turn.")
                    damage = 1
                    known_bullet = None  # Reset known bullet
                else:
                    random_bullets.pop(0)
                    await ctx.send(f"**{attacker.display_name}** turns the shotgun to themselves and pulls the trigger..")
                    await asyncio.sleep(2)
                    # To subtract 1 HP from enemy_
                    damage = self.subtract_hp(attacker, hptracker, damage)
                    heart_emoji = "❤️"
                    # Assuming hp_tracker is correctly updated with the current HP of ctx.author and enemy_
                    hp_message = (
                        f"{heart_emoji} {ctx.author.display_name}'s HP: {hptracker[ctx.author]} **__vs__** "
                        f"{enemy_.display_name}'s HP: {hptracker[enemy_]} {heart_emoji}")

                    await ctx.send(hp_message)
                    if not use_cuffs:
                        await ctx.send("‍💥 You shot yourself! You pass the gun to the next player")
                        attacker, defender = defender, attacker
                        known_bullet = None  # Reset known bullet on turn change
                    else:
                        await ctx.send(f"‍💥 You shot yourself! **{defender.display_name}** is now free from handcuffs")
                        if attacker == last_used_cuffs and anticuffstunlock > 0:
                            anticuffstunlock -= 1
                        damage = 1
                        use_cuffs = False
                        known_bullet = None  # Reset known bullet

            elif action == "shoot_player":
                bullet_color = random_bullets[0]['color']
                if bullet_color == "Blue":
                    await ctx.send(f"{attacker.display_name} turns the shotgun to **{defender.display_name}** and pulls the trigger..")
                    await asyncio.sleep(2)
                    random_bullets.pop(0)
                    if not use_cuffs:
                        await ctx.send(f"‍💨 It was a blank! You pass the gun to **{defender.display_name}**")
                        attacker, defender = defender, attacker
                        damage = 1
                        known_bullet = None  # Reset known bullet on turn change
                    else:
                        await ctx.send(f"‍💨 It was a blank! **{defender.display_name}** is free from handcuffs")
                        if attacker == last_used_cuffs and anticuffstunlock > 0:
                            anticuffstunlock -= 1
                        use_cuffs = False
                        damage = 1
                        known_bullet = None  # Reset known bullet
                else:
                    await ctx.send(f"{attacker.display_name} turns the shotgun to **{defender.display_name}** and pulls the trigger..")
                    await asyncio.sleep(2)
                    # To subtract 1 HP from enemy_
                    damage = self.subtract_hp(defender, hptracker, damage)
                    heart_emoji = "❤️"
                    # Assuming hp_tracker is correctly updated with the current HP of ctx.author and enemy_
                    hp_message = (
                        f"{heart_emoji} {ctx.author.display_name}'s HP: {hptracker[ctx.author]} **__vs__** "
                        f"{enemy_.display_name}'s HP: {hptracker[enemy_]} {heart_emoji}")

                    await ctx.send(hp_message)
                    if not use_cuffs:
                        await ctx.send(f"‍💥 You shot **{defender.display_name}**! You pass the gun to **{defender.display_name}**")
                        random_bullets.pop(0)
                        attacker, defender = defender, attacker
                        damage = 1
                        known_bullet = None  # Reset known bullet on turn change
                    else:
                        await ctx.send(f"‍💥 You shot **{defender.display_name}**! {defender.display_name} is free from handcuffs")
                        random_bullets.pop(0)
                        if attacker == last_used_cuffs and anticuffstunlock > 0:
                            anticuffstunlock -= 1
                        use_cuffs = False
                        damage = 1
                        known_bullet = None  # Reset known bullet

            if hptracker[ctx.author] > 0 >= hptracker[enemy_]:
                break
            elif hptracker[enemy_] > 0 >= hptracker[ctx.author]:
                break

        return attacker, defender

    async def startgame(self, ctx, hptracker, enemy_: Union[discord.Member, AIOpponent], round, maxhp, money):
        attacker = None
        defender = None
        while hptracker[ctx.author] >= 1 and hptracker[enemy_] >= 1:
            if round != 1:
                # For rounds after the first, reuse the existing attacker and defender roles
                random_bullets, player_items_dict = await self.roundsettings(ctx, hptracker, enemy_, round)
            else:
                # Only for the first round, determine attacker and defender roles
                random_bullets, player_items_dict, attacker, defender = await self.roundsettings(ctx, hptracker, enemy_,
                                                                                                 round)

            await ctx.send(f"**{attacker.display_name}** is first up!")
            attacker, defender = await self.gamelogic(ctx, random_bullets, attacker, defender, player_items_dict,
                                                      hptracker, enemy_, maxhp)

            # Check the outcome of the game or increment the round
            if hptracker[ctx.author] > 0 >= hptracker[enemy_]:
                await ctx.send(f"{ctx.author.display_name} wins!")
                # Always reward the player for winning
                money = money * 2
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    ctx.author.id,
                )
                break
            elif hptracker[enemy_] > 0 >= hptracker[ctx.author]:
                await ctx.send(f"{enemy_.display_name} wins!")
                if not hasattr(enemy_, 'is_ai'):  # Only pay human opponents (not AI)
                    money = money * 2
                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        enemy_.id,
                    )
                break

            round += 1
            await ctx.send("Round over! Starting new round")
            await asyncio.sleep(5)

    @user_cooldown(240)
    @commands.command(
        aliases=["sr"], hidden=True, brief=_("Shotgun Roulette")
    )
    @has_char()
    @locale_doc
    async def shotgunroulette(self, ctx, money: IntGreaterThan(-1) = 0, enemy: Optional[discord.Member] = None, *, ai_name: str = None):
        _(
            """`[money]` - The amount of money to bet; must be 0 or greater.
        `[enemy]` - The member to challenge; optional.
        `[ai_name]` - Name for the AI opponent (if no enemy specified); optional.

        Start a game of Shotgun Roulette with another player or against an AI opponent.

        Usage:
          `$shotgunroulette 5000 @username` - Play against a user
          `$shotgunroulette 5000` - Play against an AI
          `$shotgunroulette 5000 ai Dragonslayer Zephyra` - Play against AI with a custom name

        In Shotgun Roulette, two players take turns with a shotgun, choosing to shoot themselves or their opponent. Each player starts with a random amount of HP and a set of random items that can be used strategically.

        **Objective:**
        - Reduce your opponent's HP to zero while keeping yours above zero.

        **Game Mechanics:**
        - Players take turns performing actions such as shooting or using items.
        - Ammunition types include Blue (blanks) and Red (live) shells.
        - Players have items like Bloodbag, Cuffs, Magnifying Glass, Beer, and Sawn Off to influence the game.

        **Notes:**
        - If no enemy is specified, you'll play against an AI opponent.
        - Both players must have enough money to cover the bet.
        - You cannot challenge yourself.
        - This command requires you to have a character."""
        )

        future = None
        hptracker = {}
        try:
            if enemy == ctx.author:
                await self.bot.reset_cooldown(ctx)
                await ctx.send(_("You can't battle yourself."))
                return

            if money > 50000:
                return await ctx.send("Max bet is 50000.")


            try:
                if ctx.character_data["money"] < money:
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send(_("You cannot afford this."))
            except Exception as e:
                await ctx.send(e)
                return

            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )
            
            # If no enemy specified, create an AI opponent
            if enemy is None:
                ai_opponent = AIOpponent(self.bot, ai_name)
                enemy_ = ai_opponent
                
                # Show AI opponent information
                await ctx.send(f"**{ctx.author.display_name}** will face **{ai_opponent.name}** in Shotgun Roulette!")
                
                # Initialize the game
                hptracker, maxhp = await self.initilise(ctx, enemy_)
                round = 1
                
                # Start the game against AI
                await self.startgame(ctx, hptracker, enemy_, round, maxhp, money)
                return
                
            else:
                # Existing human opponent logic
                if enemy == None:
                    text = _(
                        "{author} seeks a **Shotgun Roulette** Open Challenge! The price is **${money}**."
                    ).format(author=ctx.author.mention, money=money)
                else:
                    text = _(
                        "{author} challenges {enemy} to a game of **Shotgun Roulette!** The price is **${money}**."
                    ).format(author=ctx.author.mention, enemy=enemy.mention, money=money)

                async def check(user: discord.User) -> bool:
                    return await has_money(self.bot, user.id, money)

                future = asyncio.Future()  # Properly assign `future`
                view = SingleJoinView(
                    future,
                    Button(
                        style=ButtonStyle.primary,
                        label=_("Join the roulette!"),
                        emoji="\U0001f52b",
                    ),

                    allowed=enemy,
                    prohibited=ctx.author,
                    timeout=60,
                    check=check,
                    check_fail_message=_("You don't have enough money to join."),
                )

                await ctx.send(text, view=view)

                if future:  # Check if `future` has been assigned
                    try:
                        enemy_ = await future
                        await self.bot.pool.execute(
                            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                            money,
                            enemy_.id,
                        )

                        hptracker, maxhp = await self.initilise(ctx, enemy_)  # Call initilise function and capture hp_tracker
                    except asyncio.TimeoutError:
                        await self.bot.reset_cooldown(ctx)
                        await self.bot.pool.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                            money,
                            ctx.author.id,
                        )
                        if enemy is not None:
                            return await ctx.send(
                                _("{enemy_} did not want to join your shotgun roulette, {author}!").format(
                                    enemy_=enemy,
                                    author=ctx.author.mention
                                )
                            )
                        else:
                            if enemy is None:
                                return await ctx.send(
                                    _("Nobody wanted to join your shotgun roulette, {author}!").format(
                                        author=ctx.author.mention,
                                    )
                                )
                    round = 1
                    await self.startgame(ctx, hptracker, enemy_, round, maxhp, money)

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")


async def setup(bot):
    await bot.add_cog(Shotgunroulette(bot))