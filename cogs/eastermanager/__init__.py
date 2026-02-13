import discord
from discord.ext import commands
import copy
import pickle
import asyncio
from utils.checks import has_char, is_gm
import datetime

class EasterManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.saved_state = None

    @is_gm()
    @commands.command()
    async def save_easter_state(self, ctx):
        """Save the current state of the Easter cog"""
        easter_cog = self.bot.get_cog("Easter")
        if not easter_cog:
            return await ctx.send("Easter cog not found!")

        try:
            # Save important attributes with sanitization for pickling
            state = {
                'enabled': easter_cog.enabled,
                'join_phase': easter_cog.join_phase,
                'customization_phase': easter_cog.customization_phase,
                'event_active': easter_cog.event_active,
                'pending_participants': copy.deepcopy(easter_cog.pending_participants),
                'per_user_stat_points': copy.deepcopy(easter_cog.per_user_stat_points),
                'ongoing_team_battles': list(easter_cog.ongoing_team_battles),  # Convert set to list
                'teams': self.sanitize_teams(easter_cog.teams),
                # Skip boss_battles completely as they contain unpicklable objects
                'current_hp': copy.deepcopy(easter_cog.current_hp),
                'player_hit_counters': copy.deepcopy(easter_cog.player_hit_counters),
                'team_battle_cooldowns': self.sanitize_cooldowns(easter_cog.team_battle_cooldowns),
                'player_collect_cooldowns': self.sanitize_cooldowns(easter_cog.player_collect_cooldowns),
                'last_reset': (easter_cog.last_reset if isinstance(easter_cog.last_reset, (int, float))
                              else easter_cog.last_reset.timestamp() if easter_cog.last_reset
                              else None),
                'total_customization_points': easter_cog.total_customization_points,
                'placement_order': copy.deepcopy(easter_cog.placement_order),
                'leaderboard_message_id': easter_cog.leaderboard_message_id,
                'player_battle_cooldowns': self.sanitize_cooldowns(easter_cog.player_battle_cooldowns),
                'player_vote_cooldowns': self.sanitize_cooldowns(easter_cog.player_vote_cooldowns),
                'team_ability_unlocked': self.sanitize_cooldowns(easter_cog.team_ability_unlocked),
                'players_in_battle_formation': list(easter_cog.players_in_battle_formation),  # Convert set to list
            }

            # Add marker for data format
            state['cooldown_format'] = 'timestamp'
            state['set_format'] = 'list'

            # We'll extract minimal key information from boss_battles if possible
            try:
                battle_keys = {}
                for battle_key, battle_data in easter_cog.boss_battles.items():
                    battle_keys[battle_key] = {
                        'attacker_team': battle_data.get('attacker_team', ''),
                        'defender_team': battle_data.get('defender_team', ''),
                        'action_number': battle_data.get('action_number', 0)
                    }
                state['boss_battle_keys'] = battle_keys
            except Exception:
                state['boss_battle_keys'] = {}

            self.saved_state = state
            await ctx.send("Easter state saved in memory!")

            # Backup to file
            with open('easter_state_backup.pkl', 'wb') as f:
                pickle.dump(state, f)
            await ctx.send("Backup file created as easter_state_backup.pkl")
            
            # Create a JSON summary file for easy inspection (optional)
            try:
                import json
                with open('easter_state_summary.json', 'w') as f:
                    # Convert to a JSON-friendly format
                    summary = {
                        'teams': list(state['teams'].keys()),
                        'participants': len(state['per_user_stat_points']),
                        'phases': {
                            'join_phase': state['join_phase'],
                            'customization_phase': state['customization_phase'],
                            'event_active': state['event_active'],
                        },
                        'battle_keys': list(state.get('boss_battle_keys', {}).keys()),
                        'current_timestamp': datetime.datetime.now().isoformat()
                    }
                    json.dump(summary, f, indent=2)
                await ctx.send("Summary file created as easter_state_summary.json")
            except Exception as e:
                await ctx.send(f"Error creating summary file: {e}")
                
        except Exception as e:
            await ctx.send(f"Error creating backup file: {e}")
            import traceback
            await ctx.send(f"```{traceback.format_exc()[:1500]}```")

    def sanitize_teams(self, teams_data):
        """Sanitize team data to make it picklable"""
        cleaned_teams = {}
        for team_name, team_data in teams_data.items():
            # Create a deep copy to avoid modifying the original
            cleaned_team = copy.deepcopy(team_data)
            
            # Convert sets to lists for pickling
            if 'members' in cleaned_team and isinstance(cleaned_team['members'], set):
                cleaned_team['members'] = list(cleaned_team['members'])
                
            # Handle any other unpicklable objects
            # (None needed for current structure)
                
            cleaned_teams[team_name] = cleaned_team
        return cleaned_teams

    def sanitize_cooldowns(self, cooldown_dict):
        """Convert datetime objects to timestamps for pickling"""
        if not cooldown_dict:
            return {}
            
        result = {}
        for key, value in cooldown_dict.items():
            if hasattr(value, 'timestamp'):  # If it's a datetime
                result[key] = value.timestamp()
            else:
                result[key] = value
        return result

    def restore_cooldowns(self, timestamp_dict):
        """Convert timestamps back to datetime objects"""
        if not timestamp_dict:
            return {}
            
        result = {}
        for key, value in timestamp_dict.items():
            if isinstance(value, (int, float)):  # If it's a timestamp
                result[key] = datetime.datetime.fromtimestamp(value)
            else:
                result[key] = value
        return result

    @is_gm()
    @commands.command()
    async def restore_easter_state_from_file(self, ctx, file_path: str = 'easter_state_backup.pkl'):
        """Restore the Easter cog state from a pickle file"""
        import pickle
        
        easter_cog = self.bot.get_cog("Easter")
        if not easter_cog:
            return await ctx.send("Easter cog not found!")
        
        try:
            # Load the state from the file
            with open(file_path, 'rb') as f:
                loaded_state = pickle.load(f)
            
            # Convert timestamps back to datetime objects
            if 'last_reset' in loaded_state and loaded_state['last_reset']:
                loaded_state['last_reset'] = datetime.datetime.fromtimestamp(loaded_state['last_reset'])
            
            # Convert cooldown timestamps back to datetime
            cooldown_keys = [
                'team_battle_cooldowns', 
                'player_collect_cooldowns',
                'player_battle_cooldowns', 
                'player_vote_cooldowns', 
                'team_ability_unlocked'
            ]
            
            for key in cooldown_keys:
                if key in loaded_state:
                    loaded_state[key] = self.restore_cooldowns(loaded_state[key])
            
            # Convert lists back to sets
            if 'ongoing_team_battles' in loaded_state:
                loaded_state['ongoing_team_battles'] = set(loaded_state['ongoing_team_battles'])
            if 'players_in_battle_formation' in loaded_state:
                loaded_state['players_in_battle_formation'] = set(loaded_state['players_in_battle_formation'])
            
            # Note: We don't restore boss_battles - they will need to be recreated
            # Handle cleanup of active battles if present
            if easter_cog.boss_battles and len(easter_cog.boss_battles) > 0:
                await ctx.send("⚠️ Warning: There are active boss battles that might be interrupted by this restoration.")
            
            # Metadata to exclude from restoration
            metadata_keys = ['boss_battle_keys', 'cooldown_format', 'set_format']
            
            # Restore all saved attributes except metadata
            restore_count = 0
            for key, value in loaded_state.items():
                if key not in metadata_keys:  # Skip our metadata
                    setattr(easter_cog, key, value)
                    restore_count += 1
            
            # EXTRA TYPE VERIFICATION - Make absolutely sure these are sets
            easter_cog.ongoing_team_battles = set(easter_cog.ongoing_team_battles)
            easter_cog.players_in_battle_formation = set(easter_cog.players_in_battle_formation)
            
            # Ensure all cooldowns are datetime objects
            cooldown_fixed = 0
            for key in cooldown_keys:
                cooldown_dict = getattr(easter_cog, key, {})
                for user_id, time_value in list(cooldown_dict.items()):
                    if isinstance(time_value, (int, float)):
                        cooldown_dict[user_id] = datetime.datetime.fromtimestamp(time_value)
                        cooldown_fixed += 1
            
            # Save to in-memory state too
            self.saved_state = loaded_state
            
            await ctx.send(f"Easter state restored from file {file_path}! Restored {restore_count} attributes.")
            
            # Verification
            team_names = list(easter_cog.teams.keys())
            user_count = len(easter_cog.per_user_stat_points)
            event_phase = "Customization" if easter_cog.customization_phase else "Event" if easter_cog.event_active else "Join" if easter_cog.join_phase else "Unknown"
            
            await ctx.send(f"Verification: {len(team_names)} teams, {user_count} users, phase: {event_phase}")
            
            if cooldown_fixed > 0:
                await ctx.send(f"Fixed {cooldown_fixed} cooldown values that were still in timestamp format")
            
            # Update leaderboard to ensure it shows correctly
            try:
                await easter_cog.update_leaderboard_embed(ctx.guild)
                await ctx.send("Leaderboard has been updated with restored data!")
            except Exception as e:
                await ctx.send(f"Warning: Could not update leaderboard: {e}")
            
        except FileNotFoundError:
            await ctx.send(f"Error: File {file_path} not found.")
        except Exception as e:
            import traceback
            error_text = traceback.format_exc()
            await ctx.send(f"Error restoring state: {e}\n```{error_text[:1500]}```")

    @is_gm()
    @commands.command()
    async def fix_cooldown_types(self, ctx):
        """Fix any cooldown values that are still in timestamp format"""
        easter_cog = self.bot.get_cog("Easter")
        if not easter_cog:
            return await ctx.send("Easter cog not found!")
            
        cooldown_dicts = [
            ('team_battle_cooldowns', easter_cog.team_battle_cooldowns),
            ('player_collect_cooldowns', easter_cog.player_collect_cooldowns),
            ('player_battle_cooldowns', easter_cog.player_battle_cooldowns),
            ('player_vote_cooldowns', easter_cog.player_vote_cooldowns),
            ('team_ability_unlocked', easter_cog.team_ability_unlocked)
        ]
        
        fixed_count = 0
        for name, cooldown_dict in cooldown_dicts:
            for key, value in list(cooldown_dict.items()):  # Use list() to avoid modification during iteration
                if isinstance(value, (int, float)):
                    cooldown_dict[key] = datetime.datetime.fromtimestamp(value)
                    fixed_count += 1
        
        if fixed_count > 0:
            await ctx.send(f"Fixed {fixed_count} cooldown timestamps by converting them to datetime objects")
            
            # Show samples for verification
            for name, cooldown_dict in cooldown_dicts:
                if cooldown_dict:
                    sample_key = next(iter(cooldown_dict))
                    sample_value = cooldown_dict[sample_key]
                    await ctx.send(f"Sample from {name}: {sample_key} = {type(sample_value).__name__} ({sample_value})")
        else:
            await ctx.send("All cooldown values are already in correct datetime format")

    @is_gm()
    @commands.command()
    async def fix_team_battles_set(self, ctx):
        """Fix the ongoing_team_battles attribute to be a set"""
        easter_cog = self.bot.get_cog("Easter")
        if not easter_cog:
            return await ctx.send("Easter cog not found!")
        
        # Check and fix ongoing_team_battles
        if isinstance(easter_cog.ongoing_team_battles, list):
            current_value = easter_cog.ongoing_team_battles.copy()
            easter_cog.ongoing_team_battles = set(easter_cog.ongoing_team_battles)
            await ctx.send(f"Fixed: ongoing_team_battles converted from list to set")
        else:
            await ctx.send(f"ongoing_team_battles is already a {type(easter_cog.ongoing_team_battles).__name__}")
            
        # Also check and fix players_in_battle_formation
        if isinstance(easter_cog.players_in_battle_formation, list):
            easter_cog.players_in_battle_formation = set(easter_cog.players_in_battle_formation)
            await ctx.send(f"Fixed: players_in_battle_formation converted from list to set")
        else:
            await ctx.send(f"players_in_battle_formation is already a {type(easter_cog.players_in_battle_formation).__name__}")
        
        # Report current status
        await ctx.send(f"Current state:\n"
                      f"- ongoing_team_battles: {type(easter_cog.ongoing_team_battles).__name__} with {len(easter_cog.ongoing_team_battles)} items\n"
                      f"- players_in_battle_formation: {type(easter_cog.players_in_battle_formation).__name__} with {len(easter_cog.players_in_battle_formation)} items")

    @is_gm()
    @commands.command()
    async def view_easter_data(self, ctx, source: str = "file", detail_level: int = 3):
        """
        View detailed Easter event data from the saved state
        
        Sources:
        - file: Use data from the backup file (default)
        - memory: Use data from memory
        
        Detail Level:
        - 1: Basic overview
        - 2: Medium detail
        - 3: Full detail (default)
        """
        easter_cog = self.bot.get_cog("Easter")
        if not easter_cog and source == "memory":
            return await ctx.send("Easter cog not found!")
        
        try:
            # Get data either from file or memory
            data = None
            if source.lower() == "file":
                with open('easter_state_backup.pkl', 'rb') as f:
                    data = pickle.load(f)
            else:
                if not self.saved_state:
                    return await ctx.send("No saved state found in memory!")
                data = self.saved_state
            
            if not data:
                return await ctx.send("No data found to display!")
                
            # Start sending data in multiple embeds
            await ctx.send("📊 **Easter Event Data - Comprehensive View**")
            
            # 1. Event Status Overview
            status_embed = discord.Embed(
                title="Event Status Overview",
                description="Current state of the Easter Egg Guardian Trials",
                color=discord.Color.gold()
            )
            
            # Determine current phase
            phase = "Unknown"
            if data.get('customization_phase'):
                phase = "Customization Phase"
            elif data.get('event_active'):
                phase = "Main Event Active"
            elif data.get('join_phase'):
                phase = "Join Phase"
                
            status_embed.add_field(
                name="Basic Status",
                value=f"**Enabled:** {data.get('enabled', False)}\n"
                    f"**Current Phase:** {phase}\n"
                    f"**Teams:** {len(data.get('teams', {}))}\n"
                    f"**Participants:** {len(data.get('per_user_stat_points', {}))}\n"
                    f"**Last Reset:** {datetime.datetime.fromtimestamp(data['last_reset']).strftime('%Y-%m-%d %H:%M:%S') if data.get('last_reset') else 'None'}"
            )
            
            # Add placement info
            placement_order = data.get('placement_order', [])
            if placement_order:
                placement_text = "\n".join([f"{i+1}. {team}" for i, team in enumerate(placement_order)])
                status_embed.add_field(
                    name="Current Placement Order",
                    value=placement_text or "No placements yet",
                    inline=False
                )
                
            await ctx.send(embed=status_embed)
            
            # 2. Teams Overview
            for team_name, team_data in data.get('teams', {}).items():
                team_embed = discord.Embed(
                    title=f"{team_data.get('emoji', '')} {team_name} Team Data",
                    color=discord.Color.blue()
                )
                
                # Team stats
                guardian = team_data.get('guardian', {})
                
                team_embed.add_field(
                    name="Team Stats",
                    value=f"**Members:** {len(team_data.get('members', []))}\n"
                        f"**Eggs Collected:** {team_data.get('eggs_collected', 0)}\n"
                        f"**Victories:** {team_data.get('victories', 0)}\n"
                        f"**Defeats:** {team_data.get('defeats', 0)}",
                    inline=True
                )
                
                # Guardian info
                guardian_status = "🟢 Active" if not guardian.get('defeated', False) else "🔴 Defeated"
                base_hp = guardian.get('base_hp', 0)
                current_hp_key = f"guardian_{team_name}"
                
                # Calculate full HP with bonuses
                hp_bonus_custom = team_data.get('customization', {}).get('points_allocated', {}).get('hp', 0) * 0.05
                hp_bonus_upgrades = team_data.get('upgrades', {}).get('hp_boost', 0) * 0.05
                max_hp = base_hp * (1 + hp_bonus_custom + hp_bonus_upgrades)
                
                current_hp = data.get('current_hp', {}).get(current_hp_key, max_hp)
                if guardian.get('defeated', False):
                    current_hp = 0
                    
                team_embed.add_field(
                    name=f"Guardian: {guardian.get('name', 'Unknown')}",
                    value=f"**Status:** {guardian_status}\n"
                        f"**HP:** {current_hp:,.0f}/{max_hp:,.0f}\n"
                        f"**Attack:** {guardian.get('base_attack', 0):,.0f}\n"
                        f"**Defense:** {guardian.get('base_defense', 0):,.0f}\n"
                        f"**Kills:** {guardian.get('kills', 0)}",
                    inline=True
                )
                
                # Customization
                custom = team_data.get('customization', {}).get('points_allocated', {})
                team_embed.add_field(
                    name="Stat Allocations",
                    value=f"**HP:** {custom.get('hp', 0)} points (+{custom.get('hp', 0)*5}%)\n"
                        f"**Attack:** {custom.get('attack', 0)} points (+{custom.get('attack', 0)*5}%)\n"
                        f"**Defense:** {custom.get('defense', 0)} points (+{custom.get('defense', 0)*5}%)",
                    inline=False
                )
                
                # Upgrades
                upgrades = team_data.get('upgrades', {})
                team_embed.add_field(
                    name="Upgrades",
                    value=f"**HP Boost:** +{upgrades.get('hp_boost', 0)*5}%\n"
                        f"**Attack Boost:** +{upgrades.get('attack_boost', 0)*5}%\n"
                        f"**Defense Boost:** +{upgrades.get('defense_boost', 0)*5}%",
                    inline=True
                )
                
                # Guardian abilities (only if detail level > 1)
                if detail_level > 1:
                    abilities = guardian.get('abilities', [])
                    unlocked = [a.get('name') for a in abilities if a.get('unlocked', False)]
                    locked = [a.get('name') for a in abilities if not a.get('unlocked', False)]
                    
                    if unlocked:
                        team_embed.add_field(
                            name="Unlocked Abilities",
                            value="\n".join([f"✅ {name}" for name in unlocked]),
                            inline=True
                        )
                    
                    if locked and detail_level > 2:
                        team_embed.add_field(
                            name="Locked Abilities",
                            value="\n".join([f"🔒 {name}" for name in locked]),
                            inline=True
                        )
                        
                    # Show ability votes
                    ability_votes = upgrades.get('ability_votes', {})
                    if ability_votes and detail_level > 2:
                        votes_text = "\n".join([f"{ability}: {votes}/5" for ability, votes in ability_votes.items()])
                        team_embed.add_field(
                            name="Ability Votes",
                            value=votes_text or "No votes yet",
                            inline=False
                        )
                
                # Team members (only if detail level is maximum)
                if detail_level > 2:
                    members = team_data.get('members', [])
                    if members:
                        member_sample = members[:5]  # Show first 5
                        member_text = "\n".join([f"<@{member_id}>" for member_id in member_sample])
                        if len(members) > 5:
                            member_text += f"\n... and {len(members) - 5} more"
                            
                        team_embed.add_field(
                            name=f"Team Members ({len(members)})",
                            value=member_text,
                            inline=False
                        )
                
                await ctx.send(embed=team_embed)
            
            # 3. Player Stat Allocations (only if detail level > 1)
            if detail_level > 1:
                per_user_stats = data.get('per_user_stat_points', {})
                
                # Group by team
                team_players = {}
                for user_id, stats in per_user_stats.items():
                    team = stats.get('team', 'Unknown')
                    if team not in team_players:
                        team_players[team] = []
                    team_players[team].append((user_id, stats))
                
                for team, players in team_players.items():
                    # Create a summary instead of listing all players
                    total_allocated = sum(p[1].get('allocated', 0) for p in players)
                    max_possible = sum(p[1].get('max', 0) for p in players)
                    hp_allocated = sum(p[1].get('hp', 0) for p in players)
                    atk_allocated = sum(p[1].get('attack', 0) for p in players)
                    def_allocated = sum(p[1].get('defense', 0) for p in players)
                    
                    stats_embed = discord.Embed(
                        title=f"{team} - Player Stat Allocations",
                        description=f"Summary of {len(players)} players' allocations",
                        color=discord.Color.blue()
                    )
                    
                    stats_embed.add_field(
                        name="Team Totals",
                        value=f"**Total Allocated:** {total_allocated}/{max_possible} points\n"
                            f"**HP:** {hp_allocated} points\n"
                            f"**Attack:** {atk_allocated} points\n"
                            f"**Defense:** {def_allocated} points",
                        inline=False
                    )
                    
                    # Only show detailed player breakdowns at highest detail level
                    if detail_level > 2:
                        # Sort by allocation percentage
                        players.sort(key=lambda p: p[1].get('allocated', 0) / max(p[1].get('max', 1), 1), reverse=True)
                        
                        # Show top 10 players
                        for i, (user_id, stats) in enumerate(players[:10]):
                            try:
                                user = self.bot.get_user(int(user_id))
                                username = user.name if user else f"User {user_id}"
                                
                                alloc_text = f"HP: {stats.get('hp', 0)}, "
                                alloc_text += f"ATK: {stats.get('attack', 0)}, "
                                alloc_text += f"DEF: {stats.get('defense', 0)}\n"
                                alloc_text += f"Total: {stats.get('allocated', 0)}/{stats.get('max', 0)}"
                                
                                stats_embed.add_field(
                                    name=f"{i+1}. {username}",
                                    value=alloc_text,
                                    inline=True
                                )
                            except:
                                continue
                    
                    await ctx.send(embed=stats_embed)
            
            # 4. Cooldowns (only if highest detail level)
            if detail_level > 2:
                cooldown_embed = discord.Embed(
                    title="Active Cooldowns",
                    description="Currently active cooldowns in the event",
                    color=discord.Color.red()
                )
                
                now = datetime.datetime.now()
                
                # Battle cooldowns
                battle_cooldowns = data.get('player_battle_cooldowns', {})
                active_battles = 0
                for user_id, timestamp in battle_cooldowns.items():
                    expires = datetime.datetime.fromtimestamp(timestamp) if isinstance(timestamp, (int, float)) else timestamp
                    if expires > now:
                        active_battles += 1
                
                # Collection cooldowns
                collect_cooldowns = data.get('player_collect_cooldowns', {})
                active_collects = 0
                for user_id, timestamp in collect_cooldowns.items():
                    expires = datetime.datetime.fromtimestamp(timestamp) if isinstance(timestamp, (int, float)) else timestamp
                    if expires > now:
                        active_collects += 1
                
                # Vote cooldowns
                vote_cooldowns = data.get('player_vote_cooldowns', {})
                active_votes = 0
                for user_id, timestamp in vote_cooldowns.items():
                    expires = datetime.datetime.fromtimestamp(timestamp) if isinstance(timestamp, (int, float)) else timestamp
                    if expires > now:
                        active_votes += 1
                        
                # Team cooldowns
                team_cooldowns = data.get('team_battle_cooldowns', {})
                active_team_cooldowns = 0
                for battle_key, timestamp in team_cooldowns.items():
                    expires = datetime.datetime.fromtimestamp(timestamp) if isinstance(timestamp, (int, float)) else timestamp
                    if expires > now:
                        active_team_cooldowns += 1
                
                # Team ability unlock cooldowns
                team_ability_cooldowns = data.get('team_ability_unlocked', {})
                active_ability_cooldowns = 0
                for team, timestamp in team_ability_cooldowns.items():
                    expires = datetime.datetime.fromtimestamp(timestamp) if isinstance(timestamp, (int, float)) else timestamp
                    if expires > now:
                        active_ability_cooldowns += 1
                
                cooldown_embed.add_field(
                    name="Cooldown Summary",
                    value=f"**Battle Cooldowns:** {active_battles}\n"
                        f"**Collection Cooldowns:** {active_collects}\n"
                        f"**Vote Cooldowns:** {active_votes}\n"
                        f"**Team Battle Cooldowns:** {active_team_cooldowns}\n"
                        f"**Team Ability Cooldowns:** {active_ability_cooldowns}",
                    inline=False
                )
                
                # List teams in battles
                ongoing_battles = list(data.get('ongoing_team_battles', []))
                if ongoing_battles:
                    cooldown_embed.add_field(
                        name="Teams Currently in Battle",
                        value="\n".join(ongoing_battles) or "None",
                        inline=False
                    )
                
                await ctx.send(embed=cooldown_embed)
                
            # Final verification message
            await ctx.send(f"✅ **Data verification complete!** Detail level: {detail_level}/3")
            
        except Exception as e:
            await ctx.send(f"Error reading event data: {e}")
            import traceback
            await ctx.send(f"```{traceback.format_exc()[:1500]}```")

    @is_gm()
    @commands.command()
    async def restore_easter_state(self, ctx):
        """Restore the saved state to the Easter cog"""
        if not self.saved_state:
            return await ctx.send("No saved state found!")
            
        easter_cog = self.bot.get_cog("Easter")
        if not easter_cog:
            return await ctx.send("Easter cog not found!")
            
        # Convert any necessary data types before restoring
        if 'ongoing_team_battles' in self.saved_state and isinstance(self.saved_state['ongoing_team_battles'], list):
            self.saved_state['ongoing_team_battles'] = set(self.saved_state['ongoing_team_battles'])
            
        if 'players_in_battle_formation' in self.saved_state and isinstance(self.saved_state['players_in_battle_formation'], list):
            self.saved_state['players_in_battle_formation'] = set(self.saved_state['players_in_battle_formation'])
        
        # Restore all saved attributes
        metadata_keys = ['boss_battle_keys', 'cooldown_format', 'set_format']
        for key, value in self.saved_state.items():
            if key not in metadata_keys:  # Skip metadata
                setattr(easter_cog, key, value)
                
        # Fix the cooldown dictionaries
        cooldown_dicts = [
            easter_cog.team_battle_cooldowns,
            easter_cog.player_collect_cooldowns,
            easter_cog.player_battle_cooldowns, 
            easter_cog.player_vote_cooldowns,
            easter_cog.team_ability_unlocked
        ]
        
        fixed_count = 0
        for cooldown_dict in cooldown_dicts:
            for key, value in list(cooldown_dict.items()):
                if isinstance(value, (int, float)):
                    cooldown_dict[key] = datetime.datetime.fromtimestamp(value)
                    fixed_count += 1
            
        await ctx.send(f"Easter state restored! Fixed {fixed_count} cooldown values.")

    @is_gm()
    @commands.command()
    async def fix_easter_cooldown(self, ctx, new_hours: float = 2.0):
        """Fix the Easter egg collect cooldown without reloading"""
        easter_cog = self.bot.get_cog("Easter")
        if not easter_cog:
            return await ctx.send("Easter cog not found!")
        
        # Replace the original collect command
        collect_cmd = easter_cog.collect
        
        # Save original implementation
        original_callback = collect_cmd.callback
        
        # Create new wrapper function with longer cooldown
        async def longer_cooldown_wrapper(cog, ctx):
            # Check if on cooldown
            now = datetime.datetime.utcnow()
            user_id = ctx.author.id
            
            # If player has cooldown record and it's not expired
            if user_id in cog.player_collect_cooldowns:
                expires = cog.player_collect_cooldowns[user_id]
                if now < expires:
                    # Still on cooldown
                    time_left = expires - now
                    hours, remainder = divmod(time_left.total_seconds(), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    cog.bot.reset_cooldown(ctx)
                    await ctx.send(f"You can collect eggs again in **{int(hours)}h {int(minutes)}m**.")
                    return
                    
            # Set new cooldown 
            new_cooldown = new_hours * 3600  # hours to seconds
            cog.player_collect_cooldowns[user_id] = now + datetime.timedelta(seconds=new_cooldown)
            
            # Run original function
            await original_callback(cog, ctx)
        
        # Install wrapper
        collect_cmd.callback = lambda cog, ctx: longer_cooldown_wrapper(cog, ctx)
        
        await ctx.send(f"Easter egg collection cooldown set to {new_hours} hours")

    @is_gm()
    @commands.command()
    async def fix_leaderboard_hp(self, ctx):
        """Fix the leaderboard HP display to include stat allocations"""
        easter_cog = self.bot.get_cog("Easter")
        if not easter_cog:
            return await ctx.send("Easter cog not found!")
        
        # Save original method
        if not hasattr(easter_cog, '_original_update_leaderboard'):
            easter_cog._original_update_leaderboard = easter_cog.update_leaderboard_embed
        
        # Create fixed version
        async def fixed_update_leaderboard(guild):
            """Fixed version that properly calculates HP with stat allocations"""
            channel = easter_cog.bot.get_channel(easter_cog.announcement_channel_id)
            if channel is None:
                return
            
            debug_channel = (
                easter_cog.bot.get_channel(getattr(easter_cog, "debug_channel_id", None))
                if getattr(easter_cog, "debug_channel_id", None)
                else None
            )
            
            try:
                # First, sync guardian HP values from battle stats
                for team_name in easter_cog.teams:
                    # For each defending team, find their current HP in battles
                    defending_battles = [k for k in easter_cog.current_hp.keys() if '_' in k and k.split('_')[1] == team_name]
                    for battle_key in defending_battles:
                        if battle_key in easter_cog.current_hp:
                            # Update the guardian HP to match battle HP
                            easter_cog.current_hp[f"guardian_{team_name}"] = easter_cog.current_hp[battle_key]
                
                # Build the leaderboard embed
                embed = discord.Embed(
                    title="🏆 Guardian Race Leaderboard",
                    description="Live standings for the Easter Egg Guardian Trials!",
                    color=discord.Color.gold()
                )
                
                placement_emojis = ["🥇", "🥈", "🥉"]
                for idx, team_name in enumerate(easter_cog.teams):
                    team = easter_cog.teams[team_name]
                    guardian = team["guardian"]
                    
                    # FIXED: Calculate max HP including customization and upgrades
                    max_hp = guardian["base_hp"] * (1 + (team["upgrades"]["hp_boost"] * 0.05) + 
                                                (team["customization"]["points_allocated"]["hp"] * 0.05))
                    
                    # Get the current HP (prefer guardian-specific key, fallback to calculated max_hp)
                    hp = easter_cog.current_hp.get(f"guardian_{team_name}", max_hp)
                    
                    # If guardian is defeated, show 0 HP
                    if guardian["defeated"]:
                        hp = 0
                        
                    hp_bar = easter_cog.create_hp_bar(hp, max_hp)
                    
                    # Determine placement display
                    placement = ""
                    if team_name in easter_cog.placement_order:
                        place_index = easter_cog.placement_order.index(team_name)
                        emoji = placement_emojis[place_index] if place_index < len(placement_emojis) else "🏅"
                        placement = f"{emoji} {place_index+1} Place"
                    else:
                        placement = "Racing..."
                        
                    status = "🔴 Defeated" if guardian["defeated"] else "🟢 Active"
                    
                    # Format the field with HP and other stats
                    embed.add_field(
                        name=f"{team['emoji']} {guardian['name']} ({team_name})",
                        value=(
                            f"HP: {hp_bar} {hp:,.0f}/{max_hp:,.0f}\n"
                            f"Defeated Combatants: {guardian.get('kills', 0)}\n"
                            f"Status: {status}\n"
                            f"Placement: {placement}"
                        ),
                        inline=False
                    )
                
                # Update or send the leaderboard message
                if easter_cog.leaderboard_message_id:
                    try:
                        msg = await channel.fetch_message(easter_cog.leaderboard_message_id)
                        await msg.edit(embed=embed)
                        await debug_channel.send("Successfully updated leaderboard message")
                    except Exception as e:
                        await debug_channel.send(f"Error updating leaderboard embed: {e}")
                        # Try deleting the old message and posting a new one
                        try:
                            msg = await channel.fetch_message(easter_cog.leaderboard_message_id)
                            await msg.delete()
                        except Exception as delete_e:
                            await debug_channel.send(f"Could not delete old leaderboard embed: {delete_e}")
                        
                        # Create a new message
                        msg = await channel.send(embed=embed)
                        easter_cog.leaderboard_message_id = msg.id
                        await debug_channel.send(f"Created new leaderboard message ID: {easter_cog.leaderboard_message_id}")
                else:
                    msg = await channel.send(embed=embed)
                    easter_cog.leaderboard_message_id = msg.id
                    await debug_channel.send(f"Created initial leaderboard message ID: {easter_cog.leaderboard_message_id}")
                    
            except Exception as e:
                await debug_channel.send(f"Error in update_leaderboard_embed: {e}")
                import traceback
                await debug_channel.send(f"```{traceback.format_exc()}```")
        
        # Replace the method
        easter_cog.update_leaderboard_embed = fixed_update_leaderboard
        
        # Force an update
        await easter_cog.update_leaderboard_embed(ctx.guild)
        
        await ctx.send("Leaderboard HP display fixed and updated! Now includes stat allocations.")

    @is_gm()
    @commands.command()
    async def grant_channel_role(self, ctx, channel_id: int, role_id: int):
        """Grant a role to all members who can access a specific channel"""
        # Get the channel and role
        channel = ctx.guild.get_channel(channel_id)
        role = ctx.guild.get_role(role_id)
        
        # Validate inputs
        if not channel:
            return await ctx.send(f"Channel with ID {channel_id} not found!")
        if not role:
            return await ctx.send(f"Role with ID {role_id} not found!")
        
        # Find all members with access to the channel
        members_with_access = []
        for member in ctx.guild.members:
            # Skip bots
            if member.bot:
                continue
                
            # Check if member can view the channel
            channel_perms = channel.permissions_for(member)
            if channel_perms.read_messages:
                members_with_access.append(member)
        
        # Assign role to members
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        status_message = await ctx.send(f"Processing {len(members_with_access)} members...")
        
        for i, member in enumerate(members_with_access):
            # Skip if they already have the role
            if role in member.roles:
                skipped_count += 1
                continue
                
            try:
                await member.add_roles(role, reason=f"Granted by {ctx.author} based on channel access")
                success_count += 1
            except Exception as e:
                failed_count += 1
                print(f"Failed to add role to {member.name}: {e}")
                
            # Update status every 10 members
            if i % 10 == 0:
                await status_message.edit(content=f"Processing {i+1}/{len(members_with_access)} members...")
                
            # Add a small delay to avoid rate limits
            await asyncio.sleep(0.5)
        
        # Create summary embed
        embed = discord.Embed(
            title="Role Assignment Complete",
            description=f"Role: {role.mention}\nChannel: {channel.mention}",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Results",
            value=f"✅ Successfully assigned: {success_count}\n"
                f"⏭️ Already had role: {skipped_count}\n"
                f"❌ Failed to assign: {failed_count}\n"
                f"Total members processed: {len(members_with_access)}"
        )
        
        await ctx.send(embed=embed)

    @is_gm()
    @commands.command()
    async def check_easter_allocations(self, ctx):
        """Check if the Easter state backup contains user allocations and votes"""
        import pickle
        import copy
        
        try:
            # Load from file
            with open('easter_state_backup.pkl', 'rb') as f:
                loaded_state = pickle.load(f)
            
            # Create status summary
            has_user_stats = 'per_user_stat_points' in loaded_state and loaded_state['per_user_stat_points']
            has_teams = 'teams' in loaded_state and loaded_state['teams']
            
            status_summary = [
                f"✅ User stat allocations: {'Found' if has_user_stats else '❌ MISSING'}",
                f"✅ Teams data: {'Found' if has_teams else '❌ MISSING'}"
            ]
            
            # Create response embed
            embed = discord.Embed(
                title="Easter State Allocation Check",
                description="**Status Summary:**\n" + "\n".join(status_summary),
                color=discord.Color.green() if has_user_stats and has_teams else discord.Color.red()
            )
            
            # Check user stat point allocations
            if has_user_stats:
                count = len(loaded_state['per_user_stat_points'])
                
                # Count stats by team
                team_counts = {}
                for user_id, stats in loaded_state['per_user_stat_points'].items():
                    team = stats.get('team', 'Unknown')
                    if team not in team_counts:
                        team_counts[team] = {'count': 0, 'hp': 0, 'attack': 0, 'defense': 0}
                    
                    team_counts[team]['count'] += 1
                    team_counts[team]['hp'] += stats.get('hp', 0)
                    team_counts[team]['attack'] += stats.get('attack', 0)
                    team_counts[team]['defense'] += stats.get('defense', 0)
                
                # Create report
                user_report = f"Found {count} user stat allocations\n\n"
                user_report += "**Stats by team:**\n"
                
                for team, data in team_counts.items():
                    user_report += f"**{team}**: {data['count']} members\n"
                    user_report += f"Total HP: {data['hp']}, ATK: {data['attack']}, DEF: {data['defense']}\n\n"
                
                # Sample some users
                sample_count = min(3, count)
                user_report += f"**Sample of {sample_count} user allocations:**\n"
                
                for user_id, stats in list(loaded_state['per_user_stat_points'].items())[:sample_count]:
                    try:
                        user = self.bot.get_user(int(user_id))
                        username = user.name if user else f"User {user_id}"
                        
                        user_report += f"**{username}**: "
                        user_report += f"Team: {stats.get('team')}, "
                        user_report += f"HP: {stats.get('hp', 0)}, "
                        user_report += f"ATK: {stats.get('attack', 0)}, "
                        user_report += f"DEF: {stats.get('defense', 0)}, "
                        user_report += f"Alloc: {stats.get('allocated', 0)}/{stats.get('max', 0)}\n"
                    except:
                        continue
                    
                embed.add_field(
                    name="User Stat Point Allocations",
                    value=user_report[:1024],
                    inline=False
                )
            
            # Check ability votes
            if has_teams:
                votes_report = ""
                
                for team_name, team_data in loaded_state['teams'].items():
                    votes = team_data.get('customization', {}).get('ability_votes', {})
                    vote_count = len(votes)
                    votes_report += f"**Team {team_name}**: {vote_count} ability votes\n"
                    
                    if vote_count > 0:
                        # Count votes per ability
                        ability_count = {}
                        for voter_id, ability in votes.items():
                            ability_count[ability] = ability_count.get(ability, 0) + 1
                        
                        votes_report += "Votes: "
                        votes_list = []
                        for ability, count in ability_count.items():
                            votes_list.append(f"{ability}: {count}")
                        votes_report += ", ".join(votes_list) + "\n"
                    votes_report += "\n"
                    
                embed.add_field(
                    name="Team Ability Votes",
                    value=votes_report[:1024] or "No ability votes found",
                    inline=False
                )
            
            # Check team stat allocations (final customization)
            if has_teams:
                alloc_report = ""
                
                for team_name, team_data in loaded_state['teams'].items():
                    custom = team_data.get('customization', {}).get('points_allocated', {})
                    alloc_report += f"**Team {team_name}**: "
                    alloc_report += f"HP: {custom.get('hp', 0)}, "
                    alloc_report += f"ATK: {custom.get('attack', 0)}, "
                    alloc_report += f"DEF: {custom.get('defense', 0)}\n"
                    
                embed.add_field(
                    name="Team Stat Allocations (Sum of Player Points)",
                    value=alloc_report,
                    inline=False
                )
            
            await ctx.send(embed=embed)
                    
        except Exception as e:
            await ctx.send(f"Error reading state file: {e}")

async def setup(bot):
    await bot.add_cog(EasterManager(bot))
