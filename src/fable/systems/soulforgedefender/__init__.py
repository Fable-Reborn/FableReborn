import discord
from discord.ext import commands, tasks
import asyncio
import random
import datetime
import json
from decimal import Decimal
from collections import deque
from fable.systems.shard_communication import user_on_cooldown as user_cooldown

from fable.utils.checks import is_gm

class SoulforgeDefender(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_divine_wrath.start()
        self.forced_interventions = set()  # Track forced interventions
        
    def cog_unload(self):
        self.check_divine_wrath.cancel()
    
    @tasks.loop(hours=12)
    async def check_divine_wrath(self):
        """Check twice daily for divine intervention against players with high scrutiny"""
        await self.bot.wait_until_ready()
        
        async with self.bot.pool.acquire() as conn:
            # Find players with high divine attention but NO pending intervention
            high_scrutiny_players = await conn.fetch("""
                SELECT sq.user_id, sq.divine_attention, p.name, p.god 
                FROM splicing_quest sq 
                JOIN profile p ON sq.user_id = p.user
                WHERE sq.crucible_built = TRUE 
                AND sq.divine_attention >= 80
                AND (sq.divine_intervention_pending = FALSE OR sq.divine_intervention_pending IS NULL)
            """)
            
            for player in high_scrutiny_players:
                # Scale intervention chance based on divine attention
                base_chance = 0
                if player['divine_attention'] >= 95:
                    base_chance = 1  # 40% chance at very high scrutiny
                elif player['divine_attention'] >= 90:
                    base_chance = 0.75  # 25% chance at high scrutiny
                elif player['divine_attention'] >= 80:
                    base_chance = 0.50  # 15% chance at moderate scrutiny
                
                if random.random() < base_chance:
                    user = self.bot.get_user(player['user_id'])
                    if user:
                        # Notify the player
                        await user.send(
                            f"⚠️ **DIVINE WRATH APPROACHES!** ⚠️\n\n"
                            f"*Morrigan appears in a flurry of panicked feathers!*\n\n"
                            f"\"**{player['name']}!** The gods have discovered your Soulforge! "
                            f"Their servants approach to destroy what they see as blasphemy. "
                            f"We must defend the forge immediately or all will be lost!\"\n\n"
                            f"Use `$defendforge` to make your stand against the divine forces! Ignoring this threat will result in severe damage to your forge."
                        )
                        
                        # Flag this player for intervention in the database
                        # Also set the time when intervention was triggered
                        await conn.execute("""
                            UPDATE splicing_quest 
                            SET divine_intervention_pending = TRUE,
                                intervention_triggered_at = NOW()
                            WHERE user_id = $1
                        """, player['user_id'])
    
    async def ensure_columns_exist(self):
        """Make sure the necessary columns exist in the database"""
        async with self.bot.pool.acquire() as conn:
            try:
                # First check if divine_intervention_pending column exists
                column_exists = await conn.fetchval("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'splicing_quest' 
                    AND column_name = 'divine_intervention_pending'
                """)
                
                if not column_exists:
                    print("Adding divine_intervention_pending column")
                    await conn.execute("""
                        ALTER TABLE splicing_quest 
                        ADD COLUMN divine_intervention_pending BOOLEAN DEFAULT FALSE
                    """)
                
                # Check if intervention_triggered_at column exists
                column_exists = await conn.fetchval("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'splicing_quest' 
                    AND column_name = 'intervention_triggered_at'
                """)
                
                if not column_exists:
                    print("Adding intervention_triggered_at column")
                    await conn.execute("""
                        ALTER TABLE splicing_quest 
                        ADD COLUMN intervention_triggered_at TIMESTAMP
                    """)
                
                # Add other columns if needed
                await conn.execute("""
                    ALTER TABLE splicing_quest 
                    ADD COLUMN IF NOT EXISTS forge_defenders JSON DEFAULT '[]',
                    ADD COLUMN IF NOT EXISTS last_intervention_date TIMESTAMP
                """)
                
                # Create defenders table if it doesn't exist
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS soulforge_defenders (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        defender_type TEXT NOT NULL,
                        hp INTEGER NOT NULL,
                        max_hp INTEGER NOT NULL,
                        damage INTEGER NOT NULL,
                        defense INTEGER NOT NULL,
                        element TEXT,
                        abilities TEXT,
                        hired_until TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                
            except Exception as e:
                print(f"Error ensuring columns exist: {e}")


    async def check_pending_intervention(self, user_id):
        """Check if user has a pending divine intervention"""
        async with self.bot.pool.acquire() as conn:
            intervention_data = await conn.fetchrow("""
                SELECT divine_intervention_pending, intervention_triggered_at
                FROM splicing_quest 
                WHERE user_id = $1
            """, user_id)
            
            if not intervention_data or not intervention_data['divine_intervention_pending']:
                return False, None
                
            # Check if it's been over 24 hours since the intervention was triggered
            if intervention_data['intervention_triggered_at']:
                time_elapsed = datetime.datetime.utcnow() - intervention_data['intervention_triggered_at']
                if time_elapsed.total_seconds() > 86400:  # 24 hours
                    # Auto-resolve with severe consequences
                    await self.auto_resolve_intervention(user_id)
                    return False, "Your continued defiance has resulted in catastrophic damage to your Soulforge."
                    
            return True, "Divine servants are attacking your Soulforge! Use $defendforge to protect it before it's destroyed."


    async def auto_resolve_intervention(self, user_id):
        """Apply consequences for ignoring a divine intervention"""
        async with self.bot.pool.acquire() as conn:
            # Get current forge condition
            forge_data = await conn.fetchrow("""
                SELECT forge_condition, divine_attention
                FROM splicing_quest
                WHERE user_id = $1
            """, user_id)
            
            if not forge_data:
                return
                
            # Critical damage - set to 10% or less to ensure it's unusable
            # Either 10% flat or 10% of current value, whichever is lower
            new_condition = min(10, int(forge_data['forge_condition'] * 0.1))
            
            # Update database
            await conn.execute("""
                UPDATE splicing_quest
                SET forge_condition = $1,
                    divine_intervention_pending = FALSE,
                    divine_attention = $2,
                    last_intervention_date = NOW()
                WHERE user_id = $3
            """, new_condition, 50, user_id)
            
            # Try to notify the user
            user = self.bot.get_user(user_id)
            if user:
                await user.send(
                    "⚠️ **SOULFORGE CRITICALLY DAMAGED!** ⚠️\n\n"
                    "*Morrigan's spectral form wavers before you, her voice weak with exertion.*\n\n"
                    "\"I... tried to hold them back as long as I could. The divine forces have ravaged your Soulforge "
                    f"while you were away. Its condition has plummeted to a critical {new_condition}%.\"\n\n"
                    "\"The crucible is critically damaged. It must be repaired with `$repairforge` before we can continue our work, or the results could be catastrophic.\""
                )


    
    @commands.command()
    @user_cooldown(86400)
    async def defendforge(self, ctx):
        """Defend your Soulforge from divine attackers"""
        try:
            await self.ensure_columns_exist()
            
            # Check if this user has a forced intervention
            force_intervention = ctx.author.id in self.forced_interventions
            
            async with self.bot.pool.acquire() as conn:
                # Check if player has a Soulforge
                forge_data = await conn.fetchrow("""
                    SELECT sq.*, p.name, p.god, p.money 
                    FROM splicing_quest sq 
                    JOIN profile p ON sq.user_id = p.user
                    WHERE sq.user_id = $1 AND sq.crucible_built = TRUE
                """, ctx.author.id)
                
                if not forge_data:
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send("You don't have a Soulforge to defend.")
                    
                    
                # Check if intervention is pending in database
                intervention_pending = forge_data.get('divine_intervention_pending')
                
                # Print debug info (can remove in production)
                print(f"User: {ctx.author.id}, DB Pending: {intervention_pending}, Force: {force_intervention}")
                    
                # Check if intervention is pending or being forced
                if not intervention_pending and not force_intervention:
                    if forge_data.get('divine_attention', 0) < 70:
                        await self.bot.reset_cooldown(ctx)
                        return await ctx.send("*Morrigan looks around cautiously.* \"The veil between realms remains intact. No divine forces threaten your forge at this time.\"")
                    else:
                        await self.bot.reset_cooldown(ctx)
                        return await ctx.send(f"*Morrigan's feathers ruffle with concern.* \"Divine scrutiny is at {forge_data.get('divine_attention', 0)}%. While we aren't under immediate attack, we should prepare our defenses. Consider performing a `$eidolithmask` ritual to lower our profile.\"")
                
                # If we get here, proceed with intervention
                # Clear from forced interventions set if it was there
                if ctx.author.id in self.forced_interventions:
                    self.forced_interventions.remove(ctx.author.id)
                
                # Get the player's hired defenders
                defenders = await conn.fetch("""
                    SELECT * FROM soulforge_defenders 
                    WHERE user_id = $1 AND hired_until > NOW()
                """, ctx.author.id)
                
                # Create the divine force based on player's god
                
                god = forge_data.get("god") or "no god"
                divine_attention = forge_data.get('divine_attention', 100)
                divine_force = self.create_divine_force(god, divine_attention)
                
                # Start the battle
                await self.start_defense_battle(ctx, forge_data, defenders, divine_force)
        except Exception as e:
            await ctx.send(e)
            await self.bot.reset_cooldown(ctx)
    
    def create_divine_force(self, god, divine_attention):
        """Create appropriate divine attackers based on player's deity and threat level"""
        force_size = 1
        if divine_attention >= 90:
            force_size = 2
        if divine_attention >= 95:
            force_size = 3
        
        attackers = []
        
        if "asterea" in god or "light" in god:
            # Light-based attackers
            attackers.append({
                "name": "Radiant Arbiter",
                "hp": 8000,
                "max_hp": 8000,
                "damage": 250,
                "defense": 150,
                "element": "Light",
                "abilities": ["purifying_blast", "blinding_flash"]
            })
            
            if force_size > 1:
                attackers.append({
                    "name": "Justicar of Dawn",
                    "hp": 6000,
                    "max_hp": 6000,
                    "damage": 200,
                    "defense": 180,
                    "element": "Light",
                    "abilities": ["holy_judgment", "divine_shield"]
                })
                
            if force_size > 2:
                attackers.append({
                    "name": "Asterea's Herald",
                    "hp": 10000,
                    "max_hp": 10000,
                    "damage": 300,
                    "defense": 200,
                    "element": "Light",
                    "abilities": ["smite", "healing_light", "divine_authority"]
                })
                
        elif "sepulchure" in god or "dark" in god:
            # Dark-based attackers
            attackers.append({
                "name": "Shadow Inquisitor",
                "hp": 7000,
                "max_hp": 7000,
                "damage": 280,
                "defense": 170,
                "element": "Dark",
                "abilities": ["soul_drain", "necrotic_touch"]
            })
            
            if force_size > 1:
                attackers.append({
                    "name": "Void Executioner",
                    "hp": 5500,
                    "max_hp": 5500,
                    "damage": 320,
                    "defense": 150,
                    "element": "Dark",
                    "abilities": ["executioner's_call", "shadowbind"]
                })
                
            if force_size > 2:
                attackers.append({
                    "name": "Sepulchure's Emissary",
                    "hp": 9000,
                    "max_hp": 9000,
                    "damage": 350,
                    "defense": 180,
                    "element": "Dark",
                    "abilities": ["oblivion_strike", "darkforge_armor", "decree_of_shadows"]
                })
                
        else:  # Drakath or other god
            # Chaos-based attackers
            attackers.append({
                "name": "Chaos Warper",
                "hp": 6500,
                "max_hp": 6500,
                "damage": 270,
                "defense": 160,
                "element": "Corrupted",
                "abilities": ["reality_shift", "chaotic_surge"]
            })
            
            if force_size > 1:
                attackers.append({
                    "name": "Paradox Bender",
                    "hp": 7000,
                    "max_hp": 7000,
                    "damage": 240,
                    "defense": 140,
                    "element": "Corrupted",
                    "abilities": ["possibility_storm", "entropy_wave"]
                })
                
            if force_size > 2:
                attackers.append({
                    "name": "Drakath's Avatar",
                    "hp": 8500,
                    "max_hp": 8500,
                    "damage": 330,
                    "defense": 190,
                    "element": "Corrupted",
                    "abilities": ["chaotic_transformation", "random_blessing", "avatar_of_change"]
                })
        
        return attackers
    
    def create_soulforge_combatant(self, forge_condition):
        """Create a combatant entity for the Soulforge itself"""
        max_hp = 15000
        current_hp = max_hp * (forge_condition / 100)
        
        return {
            "name": "Soulforge",
            "hp": current_hp,
            "max_hp": max_hp,
            "damage": 0,  # The forge doesn't attack
            "defense": 100,
            "element": "Earth",
            "is_forge": True  # Special flag to identify the forge
        }
    
    async def create_player_combatant(self, ctx):
        """Create a combatant entity for the player based on their RPG stats"""
        try:
            async with self.bot.pool.acquire() as conn:
                # First check if player has a shield equipped
                shield_check = await conn.fetchrow(
                    "SELECT ai.* FROM profile p JOIN allitems ai ON (p.user=ai.owner) "
                    "JOIN inventory i ON (ai.id=i.item) WHERE p.user=$1 AND "
                    "i.equipped IS TRUE AND ai.type='Shield';",
                    ctx.author.id
                )
                has_shield = bool(shield_check)

                # Fetch stats
                query = 'SELECT "luck", "health", "stathp", "class" FROM profile WHERE "user" = $1;'
                result = await conn.fetchrow(query, ctx.author.id)
                if result:
                    luck_value = float(result['luck'])
                    if luck_value <= 0.3:
                        Luck = 20.0
                    else:
                        Luck = ((luck_value - 0.3) / (1.5 - 0.3)) * 80 + 20
                    Luck = round(Luck, 2)

                    # Apply luck booster
                    luck_booster = await self.bot.get_booster(ctx.author, "luck")
                    if luck_booster:
                        Luck += Luck * 0.25
                        Luck = min(Luck, 100.0)

                    base_health = 200.0
                    health = float(result['health']) + base_health
                    stathp = float(result['stathp']) * 50.0
                    player_classes = result['class']
                    dmg, deff = await self.bot.get_raidstats(ctx.author, conn=conn)

                    # Ensure dmg and deff are floats
                    dmg = float(dmg)
                    deff = float(deff)

                    # For Soulforge battles, we'll use level 100 as default
                    level = 100
                    total_health = health + level * 15.0 + stathp

                    # Get tank evolution level from player classes
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

                    for class_name in player_classes:
                        if class_name in tank_evolution_levels:
                            level = tank_evolution_levels[class_name]
                            if tank_evolution is None or level > tank_evolution:
                                tank_evolution = level

                    # Only apply tank bonuses if they have a shield equipped
                    damage_reflection = 0.0
                    if tank_evolution and has_shield:
                        # Health bonus: +5% per evolution
                        health_multiplier = 1 + (0.04 * tank_evolution)
                        total_health *= health_multiplier

                        # Damage reflection: +3% per evolution
                        damage_reflection = 0.03 * tank_evolution
                    elif tank_evolution and not has_shield:
                        # If they're a tank but don't have a shield, still give them a smaller health bonus
                        # but no reflection
                        health_multiplier = 1 + (0.01 * tank_evolution)  # Half the normal bonus
                        total_health *= health_multiplier

                    # Also check for mage evolution
                    mage_evolution = None
                    mage_evolution_levels = {
                        "Arcanist": 1,
                        "Spellweaver": 2,
                        "Conjurer": 3,
                        "Magus": 4,
                        "Archmage": 5,
                        "Sorcerer": 6,
                        "Archsorcerer": 7
                    }
                    
                    for class_name in player_classes:
                        if class_name in mage_evolution_levels:
                            level = mage_evolution_levels[class_name]
                            if mage_evolution is None or level > mage_evolution:
                                mage_evolution = level

                    # Get highest element from equipped items - FIXED QUERY
                    highest_element_query = """
                    SELECT a.element 
                    FROM profile p
                    JOIN allitems a ON p.user = a.owner
                    JOIN inventory i ON a.id = i.item
                    WHERE i.equipped = TRUE AND p.user = $1 AND a.element IS NOT NULL
                    GROUP BY a.element
                    ORDER BY COUNT(*) DESC
                    LIMIT 1;
                    """
                    
                    highest_element = await conn.fetchval(highest_element_query, ctx.author.id)
                    if not highest_element:
                        highest_element = "Earth"  # Default element

                    # Create combatant dictionary
                    combatant = {
                        "user": ctx.author,
                        "hp": total_health,
                        "max_hp": total_health,
                        "damage": dmg,
                        "defense": deff,
                        "luck": Luck,
                        "mage_evolution": mage_evolution,
                        "tank_evolution": tank_evolution,
                        "has_shield": has_shield,
                        "damage_reflection": damage_reflection,
                        "element": highest_element,
                        "is_player": True
                    }

                    return combatant
                else:
                    # Default combatant if no profile found
                    return {
                        "user": ctx.author,
                        "hp": 1000,
                        "max_hp": 1000,
                        "damage": 200,
                        "defense": 150,
                        "luck": 50,
                        "element": "Fire",
                        "is_player": True
                    }
        except Exception as e:
            import traceback
            print(f"Error in create_player_combatant: {str(e)}")
            print(traceback.format_exc())
            # Fallback to default values
            return {
                "user": ctx.author,
                "hp": 1000,
                "max_hp": 1000,
                "damage": 200,
                "defense": 150,
                "luck": 50,
                "element": "Fire",
                "is_player": True
            }
    
    def format_defender_stats(self, defender):
        """Format defender stats for display"""
        abilities = []
        if isinstance(defender['abilities'], str):
            try:
                abilities = json.loads(defender['abilities'])
            except:
                abilities = defender['abilities'].split(',')
        else:
            abilities = defender['abilities'] or []
            
        return {
            "name": defender['defender_type'],
            "hp": defender['hp'],
            "max_hp": defender['max_hp'],
            "damage": defender['damage'],
            "defense": defender['defense'],
            "element": defender['element'],
            "abilities": abilities,
            "is_defender": True
        }

    
        
    async def start_defense_battle(self, ctx, forge_data, defenders, divine_force):
        """Start the defense battle against divine attackers with improved turn sequence"""
        try:
            # Create the player combatant
            player_combatant = await self.create_player_combatant(ctx)
            player_team = [player_combatant]
            
            # Add the Soulforge itself as a combatant
            forge_condition = forge_data.get('forge_condition', 100)
            forge_combatant = self.create_soulforge_combatant(forge_condition)
            player_team.append(forge_combatant)
            
            # Add hired defenders
            for defender in defenders:
                player_team.append(self.format_defender_stats(defender))
            
            # Initialize combat variables
            battle_log = deque(
                [(0, f"*Divine forces have arrived to destroy your Soulforge! {len(divine_force)} attackers approach!*")],
                maxlen=10  # Increased log size
            )
            
            # Define elements and element strengths
            element_to_emoji = {
                "Light": "🌟", "Dark": "🌑", "Corrupted": "🌀", "Nature": "🌿",
                "Electric": "⚡", "Water": "💧", "Fire": "🔥", "Wind": "💨", "Earth": "🌍",
            }
            
            # Create initial embed
            embed = discord.Embed(
                title="🛡️ Divine Intervention Battle 🛡️",
                description=f"The gods have sent {len(divine_force)} divine servants to destroy your Soulforge!",
                color=discord.Color.red()
            )
            
            # Display player team
            team_display = ""
            for combatant in player_team:
                hp_bar = self.create_hp_bar(combatant["hp"], combatant["max_hp"])
                element_emoji = element_to_emoji.get(combatant.get("element"), "❓")
                
                if combatant.get("is_player"):
                    team_display += f"**{combatant['user'].display_name}** {element_emoji}\n"
                else:
                    team_display += f"**{combatant['name']}** {element_emoji}\n"
                    
                team_display += f"HP: {int(combatant['hp'])}/{int(combatant['max_hp'])}\n{hp_bar}\n\n"
                
            embed.add_field(name="Defenders", value=team_display, inline=True)
            
            # Display attackers
            attackers_display = ""
            for attacker in divine_force:
                hp_bar = self.create_hp_bar(attacker["hp"], attacker["max_hp"])
                element_emoji = element_to_emoji.get(attacker["element"], "❓")
                attackers_display += f"**{attacker['name']}** {element_emoji}\n"
                attackers_display += f"HP: {int(attacker['hp'])}/{int(attacker['max_hp'])}\n{hp_bar}\n\n"
                
            embed.add_field(name="Divine Attackers", value=attackers_display, inline=True)
            
            # Display battle log
            battle_log_text = battle_log[0][1]
            embed.add_field(name="Battle Log", value=battle_log_text, inline=False)
            
            battle_message = await ctx.send(embed=embed)
            await asyncio.sleep(2)
            
            # Battle initialization
            battle_round = 1
            action = 1  # Initialize action counter starting at 1
            battle_start_time = datetime.datetime.utcnow()
            battle_timeout = battle_start_time + datetime.timedelta(minutes=10)
            
            # Create a turn order by combining all combatants (excluding the forge)
            # and then randomizing their order
            all_combatants = []
            
            # Add player team first (except the forge)
            for combatant in player_team:
                if not combatant.get("is_forge", False):
                    all_combatants.append({"combatant": combatant, "team": "player"})
            
            # Then add divine attackers
            for attacker in divine_force:
                all_combatants.append({"combatant": attacker, "team": "divine"})
            
            # Randomize the turn order
            random.shuffle(all_combatants)
            
            # Main battle loop
            current_turn_index = 0
            
            while datetime.datetime.utcnow() < battle_timeout:
                # Check if battle is over
                if all(attacker["hp"] <= 0 for attacker in divine_force):
                    # All attackers defeated - victory!
                    await self.handle_battle_victory(ctx, forge_data, player_team, battle_message)
                    return
                    
                if forge_combatant["hp"] <= 0:
                    # Forge destroyed - defeat!
                    await self.handle_battle_defeat(ctx, forge_data, battle_message)
                    return
                    
                # Check if all player combatants (except forge) are defeated
                all_player_combatants_defeated = all(
                    combatant["hp"] <= 0 
                    for combatant in player_team 
                    if not combatant.get("is_forge", False)
                )
                
                if all_player_combatants_defeated:
                    # All defenders defeated but forge still stands
                    battle_log.append((
                        battle_round,
                        "*All defenders have fallen! The divine attackers turn their full attention to the Soulforge!*"
                    ))
                    
                    # Update the battle log in the embed
                    battle_log_text = ""
                    for line in battle_log:
                        battle_log_text += f"**Round {line[0]}**\n{line[1]}\n\n"
                        
                    embed.set_field_at(2, name="Battle Log", value=battle_log_text, inline=False)
                    await battle_message.edit(embed=embed)
                    await asyncio.sleep(2)
                    
                    # Direct all attacks at the forge
                    for attacker in divine_force:
                        if attacker["hp"] <= 0:
                            continue
                            
                        damage = self.calculate_damage(attacker, forge_combatant)
                        forge_combatant["hp"] -= damage
                        forge_combatant["hp"] = max(0, forge_combatant["hp"])
                        
                        battle_log.append((
                            battle_round,
                            f"*{attacker['name']} strikes the undefended Soulforge for **{damage}** damage!*"
                        ))
                        
                        # Update the HP display
                        self.update_combatant_hp(player_team, divine_force, embed)
                        
                        # Update the battle log
                        battle_log_text = ""
                        for line in battle_log:
                            battle_log_text += f"**Round {line[0]}**\n{line[1]}\n\n"
                            
                        embed.set_field_at(2, name="Battle Log", value=battle_log_text, inline=False)
                        await battle_message.edit(embed=embed)
                        await asyncio.sleep(2)
                        
                        if forge_combatant["hp"] <= 0:
                            await self.handle_battle_defeat(ctx, forge_data, battle_message)
                            return
                    
                    # If we get here, proceed to next round
                    battle_round += 1
                    continue
                
                # Get the current combatant's turn
                current_turn = all_combatants[current_turn_index]
                current_combatant = current_turn["combatant"]
                team = current_turn["team"]
                
                # Skip if this combatant is defeated
                if current_combatant["hp"] <= 0:
                    current_turn_index = (current_turn_index + 1) % len(all_combatants)
                    action += 1  # Increment action counter
                    continue
                
                # Check if all defenders except forge are defeated
                living_defenders = [c for c in player_team if c["hp"] > 0 and not c.get("is_forge", False)]
                if len(living_defenders) == 0 and forge_combatant["hp"] > 0:
                    # All defenders are defeated, only forge remains
                    forge_combatant["hp"] = 0
                    battle_log.append((battle_round, f"*With no defenders remaining, the divine attackers focus all their power on the Soulforge... It crumbles under the assault!*"))
                    
                    # Update the battle display
                    self.update_combatant_hp(player_team, divine_force, embed)
                    
                    # Update the battle log
                    battle_log_text = ""
                    visible_logs = list(battle_log)[-5:]  # Show only the most recent 5 log entries
                    for line in visible_logs:
                        battle_log_text += f"**Round {line[0]}**\n{line[1]}\n\n"
                        
                    embed.set_field_at(2, name="Battle Log", value=battle_log_text, inline=False)
                    await battle_message.edit(embed=embed)
                    await asyncio.sleep(2)
                    
                    await self.handle_battle_defeat(ctx, forge_data, battle_message)
                    return
                
                # Process the combatant's action based on their team
                if team == "player":
                    # Player team member's turn
                    # Select a target from the divine force
                    living_attackers = [attacker for attacker in divine_force if attacker["hp"] > 0]
                    if not living_attackers:
                        # No targets left, battle is over
                        await self.handle_battle_victory(ctx, forge_data, player_team, battle_message)
                        return
                        
                    target = random.choice(living_attackers)
                    
                    # Calculate and apply damage
                    damage = self.calculate_damage(current_combatant, target)
                    target["hp"] -= damage
                    target["hp"] = max(0, target["hp"])
                    
                    # Log the attack
                    if current_combatant.get("is_player"):
                        attacker_name = current_combatant["user"].display_name
                    else:
                        attacker_name = current_combatant["name"]
                        
                    battle_log.append((
                        battle_round,
                        f"*{attacker_name} attacks {target['name']} for **{damage}** damage!*"
                    ))
                    
                    # Special ability check for hired defenders (simplified)
                    if random.random() < 0.3 and current_combatant.get("is_defender", False):
                        # NPC defenders have special abilities
                        ability_damage = int(damage * 0.5)
                        target["hp"] -= ability_damage
                        target["hp"] = max(0, target["hp"])
                        
                        ability_name = random.choice(current_combatant["abilities"]) if current_combatant["abilities"] else "special attack"
                        ability_name = ability_name.replace("_", " ").title()
                        
                        battle_log.append((
                            battle_round,
                            f"*{attacker_name} uses {ability_name}, dealing an additional **{ability_damage}** damage!*"
                        ))
                    
                    # Check if target is defeated
                    if target["hp"] <= 0:
                        battle_log.append((
                            battle_round,
                            f"*{target['name']} has been defeated!*"
                        ))
                else:
                    # Divine attacker's turn
                    # Select a target
                    # 30% chance to target the forge directly
                    if random.random() < 0.3:
                        target = forge_combatant
                    else:
                        # Otherwise target a random defender (not the forge)
                        living_defenders = [combatant for combatant in player_team 
                                        if combatant["hp"] > 0 and not combatant.get("is_forge", False)]
                        
                        if not living_defenders:
                            target = forge_combatant  # All defenders down, target forge
                        else:
                            target = random.choice(living_defenders)
                    
                    # Calculate and apply damage
                    damage = self.calculate_damage(current_combatant, target)
                    target["hp"] -= damage
                    target["hp"] = max(0, target["hp"])
                    
                    # Log the attack
                    if target.get("is_player"):
                        target_name = target["user"].display_name
                    else:
                        target_name = target["name"]
                        
                    battle_log.append((
                        battle_round,
                        f"*{current_combatant['name']} attacks {target_name} for **{damage}** damage!*"
                    ))
                    
                    # Special ability check for divine attackers (simplified)
                    if random.random() < 0.25:
                        ability_name = random.choice(current_combatant["abilities"])
                        
                        if "shield" in ability_name or "armor" in ability_name:
                            # Defensive ability
                            current_combatant["defense"] += 20
                            battle_log.append((
                                battle_round,
                                f"*{current_combatant['name']} uses {ability_name.replace('_', ' ').title()}, increasing its defense!*"
                            ))
                        elif "heal" in ability_name or "blessing" in ability_name:
                            # Healing ability
                            heal_amount = int(current_combatant["max_hp"] * 0.1)
                            current_combatant["hp"] += heal_amount
                            current_combatant["hp"] = min(current_combatant["hp"], current_combatant["max_hp"])
                            battle_log.append((
                                battle_round,
                                f"*{current_combatant['name']} uses {ability_name.replace('_', ' ').title()}, healing for **{heal_amount}** HP!*"
                            ))
                        else:
                            # Offensive ability - do extra damage to target
                            ability_damage = int(current_combatant["damage"] * 0.3)
                            target["hp"] -= ability_damage
                            target["hp"] = max(0, target["hp"])
                            
                            battle_log.append((
                                battle_round,
                                f"*{current_combatant['name']} uses {ability_name.replace('_', ' ').title()}, dealing an additional **{ability_damage}** damage to {target_name}!*"
                            ))
                    
                    # Check if target is defeated
                    if target["hp"] <= 0:
                        if target.get("is_forge"):
                            # Game over - forge destroyed
                            await self.handle_battle_defeat(ctx, forge_data, battle_message)
                            return
                        elif target.get("is_player"):
                            battle_log.append((
                                battle_round,
                                f"*{target['user'].display_name} has been defeated and can no longer defend the Soulforge!*"
                            ))
                        else:
                            battle_log.append((
                                battle_round,
                                f"*{target['name']} has been defeated!*"
                            ))
                
                # Update the battle display
                self.update_combatant_hp(player_team, divine_force, embed)
                
                # Update the battle log
                battle_log_text = ""
                visible_logs = list(battle_log)[-5:]  # Show only the most recent 5 log entries
                for line in visible_logs:
                    battle_log_text += f"**Round {line[0]}**\n{line[1]}\n\n"
                    
                embed.set_field_at(2, name="Battle Log", value=battle_log_text, inline=False)
                await battle_message.edit(embed=embed)
                
                # Move to the next combatant's turn
                current_turn_index = (current_turn_index + 1) % len(all_combatants)
                action += 1  # Increment action counter
                
                # If we've gone through all combatants, increment the round number
                if current_turn_index == 0:
                    battle_round += 1
                    
                    # Re-check battle ending conditions before starting a new round
                    if all(attacker["hp"] <= 0 for attacker in divine_force):
                        await self.handle_battle_victory(ctx, forge_data, player_team, battle_message)
                        return
                    elif forge_combatant["hp"] <= 0:
                        await self.handle_battle_defeat(ctx, forge_data, battle_message)
                        return
                
                # Pause between turns
                await asyncio.sleep(2)
            
            # If we get here, battle timed out
            battle_log.append((
                battle_round,
                "*The battle has raged too long! The divine forces retreat, but they'll return...*"
            ))
            
            battle_log_text = ""
            visible_logs = list(battle_log)[-5:]  # Show only the most recent 5 log entries
            for line in visible_logs:
                battle_log_text += f"**Round {line[0]}**\n{line[1]}\n\n"
                
            embed.set_field_at(2, name="Battle Log", value=battle_log_text, inline=False)
            await battle_message.edit(embed=embed)
            
            # Handle stalemate result - some forge damage but not destroyed
            forge_damage_percent = 1 - (forge_combatant["hp"] / forge_combatant["max_hp"])
            condition_damage = int(forge_condition * forge_damage_percent * 0.5)
            
            new_condition = max(0, forge_condition - condition_damage)
            
            async with self.bot.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE splicing_quest 
                    SET forge_condition = $1,
                        divine_attention = $2,
                        divine_intervention_pending = FALSE,
                        last_intervention_date = NOW()
                    WHERE user_id = $3
                """, new_condition, 70, ctx.author.id)
            
            await ctx.send(
                f"*The divine forces withdraw for now, but they'll return.*\n\n"
                f"Your Soulforge suffered partial damage in the battle. Its condition has dropped from "
                f"{forge_condition}% to {new_condition}%.\n\n"
                f"Divine scrutiny has temporarily decreased to 70%, but will rise again if you continue splicing."
            )
        
        except Exception as e:
            import traceback
            error_message = f"Error in battle: {e}\n"
            error_message += traceback.format_exc()
            print(error_message)
            await ctx.send(f"An error occurred during the battle: {e}")
        
    async def handle_battle_victory(self, ctx, forge_data, player_team, battle_message):
        """Handle victory outcome"""
        forge_combatant = next(c for c in player_team if c.get("is_forge", False))
        # Calculate new forge condition based on remaining HP percentage
        forge_hp_percent = int((forge_combatant["hp"] / forge_combatant["max_hp"]) * 100)
        forge_condition = forge_data.get('forge_condition', 100)
        
        # Set the new condition based on HP percentage
        new_condition = forge_hp_percent
        
        # Update the database
        async with self.bot.pool.acquire() as conn:
            await conn.execute("""
                UPDATE splicing_quest 
                SET forge_condition = $1,
                    divine_attention = $2,
                    divine_intervention_pending = FALSE,
                    last_intervention_date = NOW()
                WHERE user_id = $3
            """, new_condition, 50, ctx.author.id)
            
            # Award some gold as reward
            reward = random.randint(50000, 150000)
            await conn.execute("""
                UPDATE profile 
                SET money = money + $1 
                WHERE "user" = $2
            """, reward, ctx.author.id)
        
        # Create a completely new embed that preserves the current HP values
        element_to_emoji = {
            "Light": "🌟", "Dark": "🌑", "Corrupted": "🌀", "Nature": "🌿",
            "Electric": "⚡", "Water": "💧", "Fire": "🔥", "Wind": "💨", "Earth": "🌍",
        }
        
        # First, extract the battle log from the current embed
        current_embed = battle_message.embeds[0]
        battle_log_field = current_embed.fields[2]
        battle_log_content = battle_log_field.value
        
        # Create a new embed with the same title and description
        new_embed = discord.Embed(
            title=current_embed.title,
            description=current_embed.description,
            color=discord.Color.red()
        )
        
        # Build the defender display with CURRENT HP values
        team_display = ""
        for combatant in player_team:
            hp_bar = self.create_hp_bar(combatant["hp"], combatant["max_hp"])
            element_emoji = element_to_emoji.get(combatant.get("element"), "❓")
            
            if combatant.get("is_player"):
                team_display += f"**{combatant['user'].display_name}** {element_emoji}\n"
            else:
                team_display += f"**{combatant['name']}** {element_emoji}\n"
                
            team_display += f"HP: {int(combatant['hp'])}/{int(combatant['max_hp'])}\n{hp_bar}\n\n"
        
        new_embed.add_field(name="Defenders", value=team_display, inline=True)
        
        # Divine attackers should all be defeated (0 HP)
        # Extract the divine attacker names from the current embed
        attackers_field = current_embed.fields[1]
        attackers_text = attackers_field.value
        
        # Find all attacker names with regex
        import re
        attacker_names = re.findall(r"\*\*(.*?)\*\*", attackers_text)
        
        # Build the attackers display with 0 HP
        attackers_display = ""
        for name in attacker_names:
            # Extract the emoji if available
            emoji_match = re.search(f"\\*\\*{name}\\*\\* (.)\\n", attackers_text)
            element_emoji = emoji_match.group(1) if emoji_match else "❓"
            
            # Get max HP from the text
            hp_match = re.search(f"\\*\\*{name}\\*\\* {element_emoji}\\nHP: \\d+/(\\d+)", attackers_text)
            max_hp = int(hp_match.group(1)) if hp_match else 1000  # Default if not found
            
            # Create a zero HP bar
            hp_bar = self.create_hp_bar(0, max_hp)
            
            attackers_display += f"**{name}** {element_emoji}\n"
            attackers_display += f"HP: 0/{max_hp}\n{hp_bar}\n\n"
        
        new_embed.add_field(name="Divine Attackers", value=attackers_display, inline=True)
        
        # Add the battle log
        new_embed.add_field(name="Battle Log", value=battle_log_content, inline=False)
        
        # Add victory field
        new_embed.add_field(
            name="Victory!",
            value=f"*You have defeated the divine attackers! Your Soulforge stands, though somewhat damaged.*\n\n"
                f"*Forge condition decreased from {forge_condition}% to {new_condition}%*\n"
                f"*Divine scrutiny has dropped to 50%*\n"
                f"*You've earned {reward:,} gold for your victory!*",
            inline=False
        )
        
        # Replace the old embed with the new one
        await battle_message.edit(embed=new_embed)
        
        # Also send a separate victory message for clarity
        victory_embed = discord.Embed(
            title="🛡️ Divine Forces Repelled! 🛡️",
            description=f"*Morrigan circles above, cawing triumphantly!*\n\n"
                        f"\"We've driven them back, {ctx.author.display_name}! The gods will think twice before sending such"
                        f" weak forces against us again. Though they'll surely try once more when they sense our activities.\"\n\n"
                        f"\"We should repair the forge when possible - it took some damage in the battle.\"",
            color=discord.Color.green()
        )
        
        victory_embed.add_field(
            name="Rewards",
            value=f"• {reward:,} gold coins\n"
                f"• Divine scrutiny reduced to 50%\n"
                f"• Temporary safety from divine intervention",
            inline=False
        )
        
        await ctx.send(embed=victory_embed)

    async def handle_battle_defeat(self, ctx, forge_data, battle_message):
        """Handle defeat outcome"""
        # Get the forge combatant details from the battle_message embed
        forge_condition = forge_data.get('forge_condition', 100)
        # Set to 0 for complete defeat
        new_condition = 0
        
        # Update the database
        async with self.bot.pool.acquire() as conn:
            await conn.execute("""
                UPDATE splicing_quest 
                SET forge_condition = $1,
                    divine_attention = $2,
                    divine_intervention_pending = FALSE,
                    last_intervention_date = NOW()
                WHERE user_id = $3
            """, new_condition, 60, ctx.author.id)
        
        # Get the current embed and extract data
        current_embed = battle_message.embeds[0]
        defender_field = current_embed.fields[0]
        attackers_field = current_embed.fields[1]
        battle_log_field = current_embed.fields[2]
        
        # Create a new embed with the same title and description
        new_embed = discord.Embed(
            title=current_embed.title,
            description=current_embed.description,
            color=discord.Color.red()
        )
        
        # Preserve all the fields exactly as they are - with their current HP values
        new_embed.add_field(
            name=defender_field.name, 
            value=defender_field.value,
            inline=defender_field.inline
        )
        
        new_embed.add_field(
            name=attackers_field.name,
            value=attackers_field.value,
            inline=attackers_field.inline
        )
        
        new_embed.add_field(
            name=battle_log_field.name,
            value=battle_log_field.value,
            inline=battle_log_field.inline
        )
        
        # Add defeat field
        new_embed.add_field(
            name="Defeat!",
            value=f"*The divine attackers have critically damaged your Soulforge!*\n\n"
                f"*Forge condition has plummeted from {forge_condition}% to {new_condition}%*\n"
                f"*Divine scrutiny has settled at 60%*\n"
                f"*The forge is temporarily inoperable until repaired*",
            inline=False
        )
        
        # Replace the old embed with the new one
        await battle_message.edit(embed=new_embed)
        
        # Also send a separate defeat message for clarity
        defeat_embed = discord.Embed(
            title="⚠️ Soulforge Critically Damaged! ⚠️",
            description=f"*Morrigan materializes in a cloud of dark feathers, her form flickering with distress!*\n\n"
                        f"\"They've crippled the forge, {ctx.author.display_name}! The divine servants have dealt a serious blow to"
                        f" our work. The fundamental patterns are intact, but the physical structure is heavily damaged.\"\n\n"
                        f"\"We must use `$repairforge` to restore it before we can continue our work. The gods believe they've"
                        f" stopped us for now - we can use this time to recover and prepare better defenses.\"",
            color=discord.Color.red()
        )
        
        defeat_embed.add_field(
            name="Consequences",
            value=f"• Forge condition reduced to {new_condition}%\n"
                f"• Cannot perform splicing until repairs are made\n"
                f"• Divine scrutiny remains at 60%\n",
            inline=False
        )
        
        await ctx.send(embed=defeat_embed)
    
    def calculate_damage(self, attacker, defender):
        """Calculate damage based on attacker and defender stats with improved scaling"""
        # Base damage is a percentage of attacker's damage stat plus a small random value
        base_damage = attacker["damage"] * (0.8 + random.random() * 0.4)  # 80-120% of damage stat
        
        # Defense mitigates damage proportionally rather than directly
        defense_factor = 100 / (100 + defender["defense"])  # This creates diminishing returns
        damage_after_defense = base_damage * defense_factor
        
        # Ensure minimum damage (5% of original damage)
        min_damage = base_damage * 0.05
        damage_after_defense = max(min_damage, damage_after_defense)
        
        # Element-based modifiers
        if attacker.get("element") and defender.get("element"):
            if self.is_element_strong_against(attacker["element"], defender["element"]):
                damage_after_defense *= 1.3  # 30% bonus damage
            elif self.is_element_strong_against(defender["element"], attacker["element"]):
                damage_after_defense *= 0.7  # 30% damage reduction
        
        # Additional small random factor for variety (±10%)
        damage_after_defense *= random.uniform(0.9, 1.1)
        
        # Ensure damage is reasonable relative to defender HP
        # Average battle should last 5-8 turns, so typical damage should be 12-20% of max HP
        hp_based_cap = defender["max_hp"] * 0.25  # Cap at 25% of max HP per hit
        damage_after_defense = min(damage_after_defense, hp_based_cap)
        
        return int(damage_after_defense)
    
    def is_element_strong_against(self, attacker_element, defender_element):
        """Check if attacker's element is strong against defender's element"""
        element_strengths = {
            "Light": "Corrupted",
            "Dark": "Light",
            "Corrupted": "Dark",
            "Nature": "Electric",
            "Electric": "Water",
            "Water": "Fire",
            "Fire": "Nature",
            "Wind": "Electric"
        }
        
        return element_strengths.get(attacker_element) == defender_element
    
    def create_hp_bar(self, current_hp, max_hp, length=20):
        """Create a visual bar representation"""
        ratio = current_hp / max_hp if max_hp > 0 else 0
        ratio = max(0, min(1, ratio))  # Ensure ratio is between 0 and 1
        filled_length = int(length * ratio)
        bar = '█' * filled_length + '░' * (length - filled_length)
        return bar
    
    def update_combatant_hp(self, player_team, divine_force, embed):
        """Update HP displays in the embed"""
        # Define element emojis
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
        
        # Update player team display
        team_display = ""
        for combatant in player_team:
            hp_bar = self.create_hp_bar(combatant["hp"], combatant["max_hp"])
            element_emoji = element_to_emoji.get(combatant.get("element"), "❓")
            
            if combatant.get("is_player"):
                team_display += f"**{combatant['user'].display_name}** {element_emoji}\n"
            else:
                team_display += f"**{combatant['name']}** {element_emoji}\n"
                
            team_display += f"HP: {int(combatant['hp'])}/{int(combatant['max_hp'])}\n{hp_bar}\n\n"
            
        embed.set_field_at(0, name="Defenders", value=team_display, inline=True)
        
        # Update attackers display
        attackers_display = ""
        for attacker in divine_force:
            hp_bar = self.create_hp_bar(attacker["hp"], attacker["max_hp"])
            element_emoji = element_to_emoji.get(attacker["element"], "❓")
            attackers_display += f"**{attacker['name']}** {element_emoji}\n"
            attackers_display += f"HP: {int(attacker['hp'])}/{int(attacker['max_hp'])}\n{hp_bar}\n\n"
            
        embed.set_field_at(1, name="Divine Attackers", value=attackers_display, inline=True)
    

    @commands.command()
    @user_cooldown(120)
    async def recruitdefender(self, ctx):
        """Recruit defenders to help protect your Soulforge"""
        await self.ensure_columns_exist()
        
        async with self.bot.pool.acquire() as conn:
            # Check if player has a Soulforge
            forge_data = await conn.fetchrow("""
                SELECT sq.*, p.name, p.god, p.money 
                FROM splicing_quest sq 
                JOIN profile p ON sq.user_id = p.user
                WHERE sq.user_id = $1 AND sq.crucible_built = TRUE
            """, ctx.author.id)
            
            if not forge_data:
                return await ctx.send("You don't have a Soulforge to defend.")
            
            # Get current defenders
            current_defenders = await conn.fetch("""
                SELECT * FROM soulforge_defenders 
                WHERE user_id = $1 AND hired_until > NOW()
            """, ctx.author.id)
            
            # Check if player has reached the defender limit (max 3)
            if len(current_defenders) >= 3:
                return await ctx.send(
                    "*Morrigan shakes her head.* \"You already have three defenders in your employ. "
                    "The forge can't sustain more arcane connections than that. Wait until their "
                    "contracts expire if you wish to hire different guardians.\""
                )
        
        # Available defenders
        defenders = [
            {
                "name": "Brynhilde the Forgemaster",
                "description": "The last apprentice of the Wyrdweaver smiths. A tank-type defender with high HP and defense.",
                "hp": 8000,
                "max_hp": 8000,
                "damage": 150,
                "defense": 300,
                "element": "Earth",
                "abilities": ["forge_reinforcement", "molten_shield"],
                "cost": 500000,
                "duration_days": 7
            },
            {
                "name": "Vaedrith's Echo",
                "description": "A fragment of the Wyrdweaver founder's consciousness. High damage but lower HP.",
                "hp": 5000,
                "max_hp": 5000,
                "damage": 350,
                "defense": 120,
                "element": "Dark",
                "abilities": ["essence_drain", "pattern_disruption", "arcane_surge"],
                "cost": 750000,
                "duration_days": 7
            },
            {
                "name": "Guardian Chimera",
                "description": "A sentient spliced creature with balanced stats and elemental adaptability.",
                "hp": 6500,
                "max_hp": 6500,
                "damage": 220,
                "defense": 220,
                "element": "Corrupted",
                "abilities": ["adaptive_evolution", "multielemental_strike"],
                "cost": 400000,
                "duration_days": 5
            },
            {
                "name": "Wyrdweaver Specter",
                "description": "The lingering spirit of a fallen Wyrdweaver. Moderate stats but affordable.",
                "hp": 4000,
                "max_hp": 4000,
                "damage": 180,
                "defense": 150,
                "element": "Light",
                "abilities": ["spectral_shield", "memory_flash"],
                "cost": 250000,
                "duration_days": 3
            }
        ]
        
        # Display available defenders
        embed = discord.Embed(
            title="🛡️ Recruit Forge Defenders 🛡️",
            description=f"*Morrigan gestures to the shadows around your forge.*\n\n"
                        f"\"Even now, entities drawn to the Wyrdweavers' legacy linger in the spaces between. "
                        f"For the right price, they will manifest to defend our work against divine retribution.\"",
            color=discord.Color.blue()
        )
        
        for i, defender in enumerate(defenders, 1):
            embed.add_field(
                name=f"{i}. {defender['name']} - {defender['cost']:,} gold",
                value=f"*{defender['description']}*\n\n"
                      f"HP: {defender['hp']}\n"
                      f"Damage: {defender['damage']}\n"
                      f"Defense: {defender['defense']}\n"
                      f"Element: {defender['element']}\n"
                      f"Duration: {defender['duration_days']} days",
                inline=False
            )
        
        embed.set_footer(text="To recruit a defender, type the number of your choice, or 'cancel' to exit.")
        
        await ctx.send(embed=embed)
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            response = await self.bot.wait_for('message', check=check, timeout=60.0)
            
            if response.content.lower() == 'cancel':
                return await ctx.send("Recruitment canceled.")
            
            try:
                choice = int(response.content.strip())
                if not 1 <= choice <= len(defenders):
                    return await ctx.send("Invalid selection. Recruitment canceled.")
                
                selected = defenders[choice - 1]
                
                # Confirm purchase
                confirm_msg = f"Recruiting **{selected['name']}** will cost **{selected['cost']:,} gold**. They will defend your forge for **{selected['duration_days']} days**. Proceed?"
                confirmed = await ctx.confirm(confirm_msg)
                
                if not confirmed:
                    return await ctx.send("Recruitment canceled.")
                
                # Process the hire
                async with self.bot.pool.acquire() as conn:
                    # Check if player has enough money
                    player_money = await conn.fetchval(
                        'SELECT money FROM profile WHERE "user" = $1',
                        ctx.author.id
                    )
                    
                    if player_money < selected['cost']:
                        return await ctx.send(f"You don't have enough gold. You need {selected['cost']:,} gold.")
                    
                    # Deduct gold
                    await conn.execute(
                        'UPDATE profile SET money = money - $1 WHERE "user" = $2',
                        selected['cost'], ctx.author.id
                    )
                    
                    # Calculate end date
                    end_date = datetime.datetime.utcnow() + datetime.timedelta(days=selected['duration_days'])
                    
                    # Insert defender
                    await conn.execute("""
                        INSERT INTO soulforge_defenders (
                            user_id, defender_type, hp, max_hp, damage, defense, 
                            element, abilities, hired_until
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """, 
                    ctx.author.id, selected['name'], selected['hp'], selected['max_hp'],
                    selected['damage'], selected['defense'], selected['element'], 
                    json.dumps(selected['abilities']), end_date
                    )
                
                # Success message
                success_embed = discord.Embed(
                    title="🛡️ Defender Recruited! 🛡️",
                    description=f"*A contract of essence binds {selected['name']} to your service!*\n\n"
                                f"\"I am sworn to guard the Soulforge until the contract expires. My essence stands ready to repel divine servants who would destroy your work.\"",
                    color=discord.Color.green()
                )
                
                success_embed.add_field(
                    name="Contract Details",
                    value=f"• Duration: {selected['duration_days']} days (until {end_date.strftime('%Y-%m-%d %H:%M')} UTC)\n"
                          f"• Cost: {selected['cost']:,} gold\n"
                          f"• The defender will automatically assist when divine forces attack your forge",
                    inline=False
                )
                
                await ctx.send(embed=success_embed)
                
            except ValueError:
                await ctx.send("Invalid input. Please enter a number next time.")
                
        except asyncio.TimeoutError:
            await ctx.send("Recruitment timed out.")
    

    @commands.command()
    @user_cooldown(60)
    async def mydefenders(self, ctx):
        """View your currently hired Soulforge defenders"""
        await self.ensure_columns_exist()
        
        async with self.bot.pool.acquire() as conn:
            defenders = await conn.fetch("""
                SELECT * FROM soulforge_defenders 
                WHERE user_id = $1 AND hired_until > NOW()
                ORDER BY hired_until
            """, ctx.author.id)
            
            if not defenders:
                return await ctx.send("You don't have any active defenders. Use `$recruitdefender` to hire protection for your Soulforge.")
            
            embed = discord.Embed(
                title="🛡️ Your Soulforge Defenders 🛡️",
                description=f"You have {len(defenders)} active defenders guarding your Soulforge.",
                color=discord.Color.blue()
            )
            
            for defender in defenders:
                time_remaining = defender['hired_until'] - datetime.datetime.utcnow()
                days = time_remaining.days
                hours = time_remaining.seconds // 3600
                minutes = (time_remaining.seconds % 3600) // 60
                
                abilities = json.loads(defender['abilities']) if isinstance(defender['abilities'], str) else []
                abilities_text = ", ".join(ability.replace("_", " ").title() for ability in abilities)
                
                embed.add_field(
                    name=defender['defender_type'],
                    value=f"HP: {defender['hp']}/{defender['max_hp']}\n"
                          f"Damage: {defender['damage']}\n"
                          f"Defense: {defender['defense']}\n"
                          f"Element: {defender['element']}\n"
                          f"Abilities: {abilities_text}\n"
                          f"Contract expires in: {days}d {hours}h {minutes}m",
                    inline=False
                )
            
            await ctx.send(embed=embed)
    
    @commands.command()
    @commands.is_owner()
    async def forcedivineintervention(self, ctx, user_id: int = None):
        """Force a divine intervention event for testing (GM only)"""
        await self.ensure_columns_exist()
        target_id = user_id or ctx.author.id
        
        # Store in forced interventions set
        self.forced_interventions.add(target_id)
        
        async with self.bot.pool.acquire() as conn:
            # Also set the database flag
            try:
                await conn.execute("""
                    UPDATE splicing_quest 
                    SET divine_intervention_pending = TRUE,
                        intervention_triggered_at = NOW()
                    WHERE user_id = $1 AND crucible_built = TRUE
                """, target_id)
            except Exception as e:
                await ctx.send(f"Error setting intervention flag: {e}")
                # Continue anyway since we have the forced_interventions set
        
        # Send confirmation message and notification to target user
        if user_id and user_id != ctx.author.id:
            await ctx.send(f"Divine intervention has been forced for user ID {user_id}.")
            
            # Try to DM the target user
            target_user = self.bot.get_user(user_id)
            if target_user:
                try:
                    await target_user.send(
                        f"⚠️ **DIVINE WRATH APPROACHES!** ⚠️\n\n"
                        f"*Morrigan appears in a flurry of panicked feathers!*\n\n"
                        f"\"**{target_user.display_name}!** The gods have discovered your Soulforge! "
                        f"Their servants approach to destroy what they see as blasphemy. "
                        f"We must defend the forge immediately or all will be lost!\"\n\n"
                        f"Use `$defendforge` to make your stand against the divine forces!"
                    )
                except:
                    await ctx.send("Could not send notification to the target user.")
        else:
            await ctx.send("Divine intervention has been forced for your Soulforge. Use `$defendforge` to begin the battle.")

async def setup(bot):
    await bot.add_cog(SoulforgeDefender(bot))