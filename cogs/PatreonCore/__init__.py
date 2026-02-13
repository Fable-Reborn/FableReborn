import discord
from discord.ext import commands, tasks
import patreon
from datetime import datetime, timedelta
import aiohttp
import asyncio
import json
import os

from utils.checks import is_gm
from cogs.shard_communication import user_on_cooldown as user_cooldown


class PatreonCore(commands.Cog):
    """Cog for syncing Patreon pledges with Discord roles"""

    def __init__(self, bot):
        self.bot = bot
        ids_section = getattr(self.bot.config, "ids", None)
        patreoncore_ids = getattr(ids_section, "patreoncore", {}) if ids_section else {}
        if not isinstance(patreoncore_ids, dict):
            patreoncore_ids = {}
        self.debug_user_id = patreoncore_ids.get("debug_user_id")

        # Patreon API credentials
        self.client_id = ""
        self.client_secret = ""
        self.access_token = ""
        self.refresh_token = ""
        self.token_expires_at = datetime.now() + timedelta(days=30)  # Assuming token expires in 30 days

        # Campaign and guild settings
        self.patreon_campaign_id = 11352402  # Will be populated on first API call
        self.guild_id = patreoncore_ids.get("guild_id")
        self.check_interval = 60 * 30  # Check every 30 minutes

        # Role mapping - map Patreon tier IDs to Discord role IDs
        # You'll need to populate this with your actual tier IDs and role IDs
        self.tier_role_mapping = {}

        # Store patron data
        self.patrons_data = {}
        self.last_updated = None

        # Configurable log channel
        self.log_channel_id = None

        # Config file path
        self.config_file = "patreon_config.json"
        self._load_config()

        # Start the update task
        self.update_roles.start()

    def _load_config(self):
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)

                # Load basic settings
                self.guild_id = config.get('guild_id', self.guild_id)
                self.log_channel_id = config.get('log_channel_id', self.log_channel_id)
                self.check_interval = config.get('check_interval', self.check_interval)

                # Load token info
                self.access_token = config.get('access_token', self.access_token)
                self.refresh_token = config.get('refresh_token', self.refresh_token)
                expires_at = config.get('token_expires_at')
                if expires_at:
                    self.token_expires_at = datetime.fromisoformat(expires_at)

                # Load tier-role mapping
                self.tier_role_mapping = config.get('tier_role_mapping', {})

                print("[PatreonCore] Configuration loaded successfully.")
        except Exception as e:
            print(f"[PatreonCore] Error loading config: {e}")

    def _save_config(self):
        """Save configuration to file"""
        try:
            config = {
                'guild_id': self.guild_id,
                'log_channel_id': self.log_channel_id,
                'check_interval': self.check_interval,
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'token_expires_at': self.token_expires_at.isoformat(),
                'tier_role_mapping': self.tier_role_mapping
            }

            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)

            print("[PatreonCore] Configuration saved successfully.")
        except Exception as e:
            print(f"[PatreonCore] Error saving config: {e}")

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.update_roles.cancel()
        self._save_config()

    async def refresh_access_token(self):
        """Refresh the Patreon access token"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    'grant_type': 'refresh_token',
                    'refresh_token': self.refresh_token,
                    'client_id': self.client_id,
                    'client_secret': self.client_secret
                }

                async with session.post('https://www.patreon.com/api/oauth2/token', data=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.access_token = data['access_token']
                        self.refresh_token = data['refresh_token']
                        # Set expiration time (usually 30 days)
                        self.token_expires_at = datetime.now() + timedelta(seconds=data.get('expires_in', 2592000))
                        self._save_config()
                        print("[PatreonCore] Token refreshed successfully")
                        return True
                    else:
                        error_text = await response.text()
                        print(f"[PatreonCore] Failed to refresh token: {response.status} - {error_text}")
                        return False
        except Exception as e:
            print(f"[PatreonCore] Error refreshing token: {e}")
            return False

    async def get_api_client(self):
        """Get a valid Patreon API client, refreshing the token if needed"""
        # Check if token needs refreshing (with 1-hour buffer)
        if datetime.now() + timedelta(hours=1) >= self.token_expires_at:
            success = await self.refresh_access_token()
            if not success:
                print("[PatreonCore] Could not refresh token. Using existing token.")

        # Return API client
        return patreon.API(self.access_token)

    async def get_campaign_id(self):
        """Get the campaign ID if not already set"""
        campid = 11352402
        return campid

    async def fetch_patrons(self):
        """Fetch patrons directly using Patreon's V2 API with correct include parameters"""
        user = self.bot.get_user(self.debug_user_id) if self.debug_user_id else None

        try:
            if user:
                print("[PatreonCore] Starting patron fetch process using direct API")

            campaign_id = await self.get_campaign_id()
            if not campaign_id:
                if user:
                    print("[PatreonCore] No campaign ID available. Cannot fetch patrons.")
                return [], []

            # Get all patrons using direct API calls
            all_patrons = []
            included_data = []

            async with aiohttp.ClientSession() as session:
                # Build the URL with CORRECTED includes and fields
                base_url = f"https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}/members"
                params = {
                    # Simplified include parameter - removed the nested relationship
                    "include": "user,currently_entitled_tiers",
                    "fields[member]": "patron_status,full_name,email",
                    "fields[user]": "social_connections,email",
                    "fields[tier]": "title,description,amount_cents",
                    "page[count]": 100
                }

                headers = {"Authorization": f"Bearer {self.access_token}"}

                if user:
                    print(f"[PatreonCore] Using params: {params}")

                next_url = base_url
                page_count = 0

                while next_url:
                    page_count += 1
                    if user:
                        print(f"[PatreonCore] Fetching page {page_count} of members...")

                    try:
                        async with session.get(next_url, params=params if page_count == 1 else None,
                                               headers=headers) as response:
                            # Print response status for debugging
                            if user:
                                print(f"[PatreonCore] Response status: {response.status}")

                            if response.status != 200:
                                if user:
                                    print(f"[PatreonCore] API error: {response.status}")
                                    error_text = await response.text()
                                    print(f"Error details: {error_text[:500]}...")
                                break

                            data = await response.json()

                            # Print some of the response structure for debugging
                            if user:
                                keys = list(data.keys())
                                print(f"[PatreonCore] Response keys: {keys}")

                            # Extract patrons from the data
                            members = data.get("data", [])
                            if user:
                                print(f"[PatreonCore] Fetched {len(members)} members in page {page_count}")
                                if members:
                                    print(f"[PatreonCore] First member keys: {list(members[0].keys())}")

                            # Debug first member
                            if members and len(members) > 0 and user:
                                sample = members[0]
                                attributes = sample.get("attributes", {})
                                status = attributes.get("patron_status")
                                print(f"[PatreonCore] Sample member status: {status}")

                                # Check for user relationship
                                relationships = sample.get("relationships", {})
                                print(f"[PatreonCore] Relationship keys: {list(relationships.keys())}")

                                user_rel = relationships.get("user", {}).get("data", {})
                                if user_rel:
                                    print(
                                        f"[PatreonCore] Sample member has user relationship: {user_rel.get('id')}")
                                else:
                                    print("[PatreonCore] Sample member has NO user relationship")

                            # Get included data
                            included = data.get("included", [])
                            if user:
                                print(
                                    f"[PatreonCore] Fetched {len(included)} included objects in page {page_count}")
                                if included:
                                    types = set([inc.get("type") for inc in included])
                                    print(f"[PatreonCore] Included object types: {types}")

                            all_patrons.extend(members)
                            included_data.extend(included)

                            # Check for pagination
                            links = data.get("links", {})
                            next_url = links.get("next")
                            if not next_url:
                                if user:
                                    print("[PatreonCore] No more pages to fetch")
                                break

                            # Remove params as they're included in the next_url
                            params = None

                    except Exception as e:
                        if user:
                            print(f"[PatreonCore] Error in API request: {e}")
                        break

                if user:
                    print(
                        f"[PatreonCore] Total patrons fetched: {len(all_patrons)} with {len(included_data)} included objects")

                # Debug what types of data we got
                status_counts = {}
                for patron in all_patrons:
                    status = patron.get("attributes", {}).get("patron_status")
                    status_counts[status] = status_counts.get(status, 0) + 1

                if user:
                    print(f"[PatreonCore] Patron status counts: {status_counts}")

                return all_patrons, included_data

        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            if user:
                print(f"[PatreonCore] Error fetching patrons: {e}")
                print(error_traceback)
            return [], []

    def process_patrons(self, patron_data, included_data):
        """Process patron data and extract Discord IDs with tier information"""
        result = {}
        debug_info = []

        user = self.bot.get_user(self.debug_user_id) if self.debug_user_id else None

        try:
            debug_info.append(f"Processing {len(patron_data)} patrons and {len(included_data)} included items")

            # Create mappings from included data
            user_discord_map = {}  # Maps user_id to discord_id
            tier_map = {}  # Maps tier_id to tier_info

            # Process included data first
            debug_info.append("Processing included data...")
            for included in included_data:
                try:
                    inc_type = included.get("type")
                    inc_id = included.get("id")

                    if inc_type == "user":
                        # Extract social connections
                        attrs = included.get("attributes", {})
                        debug_info.append(f"User {inc_id} attributes keys: {list(attrs.keys())}")

                        social = attrs.get("social_connections", {})
                        debug_info.append(f"User {inc_id} social connections: {social}")
                        discord_data = social.get("discord")

                        if discord_data and "user_id" in discord_data:
                            discord_id = discord_data["user_id"]
                            if discord_id:
                                user_discord_map[inc_id] = discord_id
                                debug_info.append(f"Found Discord ID {discord_id} for user {inc_id}")

                    elif inc_type == "tier":
                        tier_title = included.get("attributes", {}).get("title", "Unknown Tier")
                        tier_map[inc_id] = {
                            "title": tier_title,
                            "amount_cents": included.get("attributes", {}).get("amount_cents", 0)
                        }
                        debug_info.append(f"Found tier: {tier_title} (ID: {inc_id})")

                except Exception as e:
                    debug_info.append(f"Error processing included item: {e}")

            if user:
                print(f"[PatreonCore] Found {len(user_discord_map)} users with Discord connections")
                print(f"[PatreonCore] Found {len(tier_map)} tiers")

            # Process patrons
            debug_info.append("Processing patron data...")
            patron_count = 0
            active_patrons = 0

            for patron in patron_data:
                try:
                    patron_count += 1

                    # Get patron status
                    attributes = patron.get("attributes", {})
                    patron_status = attributes.get("patron_status")

                    # Only process active patrons
                    if patron_status != "active_patron":
                        continue

                    active_patrons += 1

                    # Get user ID and Discord ID
                    relationships = patron.get("relationships", {})
                    user_rel = relationships.get("user", {}).get("data", {})
                    user_id = user_rel.get("id") if user_rel else None

                    if not user_id:
                        debug_info.append(f"No user ID for patron {patron_count}")
                        continue

                    if user_id not in user_discord_map:
                        debug_info.append(f"No Discord ID for user {user_id}")
                        continue

                    discord_id = user_discord_map[user_id]

                    # Get entitled tiers
                    entitled_tiers = []
                    tier_rels = relationships.get("currently_entitled_tiers", {}).get("data", [])

                    for tier_rel in tier_rels:
                        tier_id = tier_rel.get("id")
                        if tier_id:
                            entitled_tiers.append(tier_id)

                    # Add this patron to the result with their entitled tiers
                    result[discord_id] = entitled_tiers

                    # Debug info
                    if entitled_tiers:
                        tier_names = [tier_map.get(tier_id, {}).get("title", f"Unknown ({tier_id})") for tier_id in
                                      entitled_tiers]
                        debug_info.append(f"Patron {discord_id} entitled to tiers: {', '.join(tier_names)}")
                    else:
                        debug_info.append(f"Patron {discord_id} has no entitled tiers")

                except Exception as e:
                    debug_info.append(f"Error processing patron {patron_count}: {e}")

            if user:
                print(
                    f"[PatreonCore] Successfully mapped {len(result)} Discord users out of {active_patrons} active patrons")

            debug_info.append(
                f"Successfully processed {len(result)} patrons with Discord accounts out of {active_patrons} active patrons")
            self.last_processing_debug = debug_info
            return result

        except Exception as e:
            import traceback
            error_text = traceback.format_exc()
            if user:
                print(f"[PatreonCore] Error processing patrons: {e}")
                print(error_text)
            debug_info.append(f"Error processing patrons: {e}")
            debug_info.append(error_text)
            self.last_processing_debug = debug_info
            return {}

    # Then add a new command to report on the processing
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def patrondebug(self, ctx):
        """Display detailed debug info about the last patron processing"""
        if not hasattr(self, 'last_processing_debug') or not self.last_processing_debug:
            await ctx.send("No patron processing debug information available.")
            return

        # Send in chunks to avoid message size limits
        chunks = []
        current_chunk = "### Patron Processing Debug Info:\n"

        for line in self.last_processing_debug:
            if len(current_chunk) + len(line) + 1 > 1900:
                chunks.append(current_chunk)
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"

        if current_chunk:
            chunks.append(current_chunk)

        for i, chunk in enumerate(chunks):
            await ctx.send(f"{chunk}\n[Part {i + 1}/{len(chunks)}]")

    async def log_message(self, message):
        """Send a log message to the configured log channel"""
        if not self.log_channel_id:
            return

        try:
            channel = self.bot.get_channel(self.log_channel_id)
            if channel:
                await channel.send(message)
        except Exception as e:
            print(f"[PatreonCore] Error sending log message: {e}")

    async def update_patron_tier_in_db(self, discord_id, tier_level):
        """Update the patron's tier in the database"""
        try:
            # Convert discord_id to int if it's a string
            user_id = int(discord_id) if isinstance(discord_id, str) else discord_id

            # Try to update the tier in the database

                # Using the bot's connection pool
            async with self.bot.pool.acquire() as conn:
                    # First check if the user exists in the database
                user_exists = await conn.fetchval(
                    'SELECT EXISTS(SELECT 1 FROM profile WHERE "user" = $1)',
                    user_id
                )

                if user_exists:
                    await conn.execute(
                        'UPDATE profile SET "tier" = $1 WHERE "user" = $2',
                        tier_level, user_id
                    )
                    print(f"[PatreonCore] Updated tier for user {user_id} to {tier_level}")

        except Exception as e:
            print(f"[PatreonCore] Error updating database for user {discord_id}: {e}")
            import traceback
            print(traceback.format_exc())

    @tasks.loop(minutes=30)
    async def update_roles(self):
        """Regular task to update roles based on Patreon data"""
        user = self.bot.get_user(self.debug_user_id) if self.debug_user_id else None
        await self.bot.wait_until_ready()

        # Skip if guild ID is not set
        if not self.guild_id:
            print("[PatreonCore] Guild ID not set. Skipping role update!")
            return

        print(f"[PatreonCore] [{datetime.now()}] Updating Patreon roles...")

        try:
            # Fetch and process patron data
            patrons, included = await self.fetch_patrons()
            if not patrons:
                if user:
                    print("[PatreonCore] No patrons fetched. Skipping role update!!")
                return

            new_data = self.process_patrons(patrons, included)

            # Get the guild
            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                print(f"[PatreonCore] Could not find guild with ID {self.guild_id}!")
                return

            # Update roles for all members
            roles_added = 0
            roles_removed = 0

            for member_id, tier_ids in new_data.items():
                try:
                    member = await guild.fetch_member(int(member_id))
                    if not member:
                        print(f"[PatreonCore] Could not find member {member_id}")
                        continue

                    # Determine which roles the member should have
                    should_have_roles = set()
                    for tier_id in tier_ids:
                        if tier_id in self.tier_role_mapping:
                            should_have_roles.add(int(self.tier_role_mapping[tier_id]))  # Convert to int here

                    # Determine which patron roles the member currently has
                    has_roles = set()
                    for role_id in self.tier_role_mapping.values():
                        role = guild.get_role(int(role_id))
                        if role and role in member.roles:
                            has_roles.add(int(role_id))

                    # Add missing roles
                    for role_id in should_have_roles - has_roles:
                        role = guild.get_role(int(role_id))
                        if role:
                            await member.add_roles(role)
                            print(f"[PatreonCore] Added role {role.name} to {member.display_name}")
                            roles_added += 1

                    # Remove roles they should no longer have
                    for role_id in has_roles - should_have_roles:
                        role = guild.get_role(int(role_id))
                        if role:
                            await member.remove_roles(role)
                            print(f"[PatreonCore] Removed role {role.name} from {member.display_name}")
                            roles_removed += 1

                    # Determine tier level based on role names
                    tier_level = 0
                    for role_id in should_have_roles:
                        role = guild.get_role(int(role_id))
                        if role:
                            # Check role name to determine tier level
                            if "Ragnarok" in role.name:
                                tier_level = max(tier_level, 4)
                            elif "Legendary" in role.name:
                                tier_level = max(tier_level, 3)
                            elif "Warrior" in role.name:
                                tier_level = max(tier_level, 2)
                            elif "Adventurer" in role.name:
                                tier_level = max(tier_level, 1)

                    # Update the database with tier level
                    await self.update_patron_tier_in_db(member_id, tier_level)

                except discord.errors.NotFound:
                    print(f"[PatreonCore] Member {member_id} not found in server")
                except Exception as e:
                    print(f"[PatreonCore] Error updating roles for member {member_id}: {e}")

            # Update stored data
            self.patrons_data = new_data
            self.last_updated = datetime.now()

            # Log results
            update_msg = (f"Patreon sync complete! Processed {len(self.patrons_data)} patrons. "
                          f"Added {roles_added} roles and removed {roles_removed} roles.")
            print(f"[PatreonCore] {update_msg}")
            

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            print(error_message)

    async def fetch_tiers(self):
        """Fetch tier information with proper names using the V2 API"""
        try:
            # First ensure we have the campaign ID
            if not self.patreon_campaign_id:
                await self.get_campaign_id()

            if not self.patreon_campaign_id:
                print("[PatreonCore] No campaign ID available. Cannot fetch tiers.")
                return {}

            # First get all tier IDs
            tier_ids = []
            async with aiohttp.ClientSession() as session:
                # Get campaign with tier relationship data
                url = f"https://www.patreon.com/api/oauth2/v2/campaigns/{self.patreon_campaign_id}?include=tiers"
                headers = {"Authorization": f"Bearer {self.access_token}"}

                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Extract tier IDs from included data
                        if "included" in data:
                            for item in data["included"]:
                                if item.get("type") == "tier":
                                    tier_id = item.get("id")
                                    if tier_id:
                                        tier_ids.append(tier_id)

                        # If no tiers found in included, try relationships
                        if not tier_ids and "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                            relationships = data["data"][0].get("relationships", {})
                            if "tiers" in relationships and "data" in relationships["tiers"]:
                                for tier in relationships["tiers"]["data"]:
                                    tier_id = tier.get("id")
                                    if tier_id:
                                        tier_ids.append(tier_id)
                    else:
                        print(f"[PatreonCore] Error fetching campaign: {response.status}")
                        return {}

            # Now get tier details with separate API calls
            tiers = {}
            async with aiohttp.ClientSession() as session:
                for tier_id in tier_ids:
                    url = f"https://www.patreon.com/api/oauth2/v2/tiers/{tier_id}?fields%5Btier%5D=title,description,amount_cents"
                    headers = {"Authorization": f"Bearer {self.access_token}"}

                    try:
                        async with session.get(url, headers=headers) as response:
                            if response.status == 200:
                                tier_data = await response.json()

                                # Extract tier title
                                tier_title = tier_data.get("data", {}).get("attributes", {}).get("title")
                                if tier_title:
                                    tiers[tier_id] = tier_title
                                    print(f"[PatreonCore] Found tier: {tier_id} - {tier_title}")
                                else:
                                    # Fallback to generic name if title not found
                                    tiers[tier_id] = f"Tier {tier_id}"
                                    print(f"[PatreonCore] Found tier with no title: {tier_id}")
                            else:
                                print(f"[PatreonCore] Error fetching tier {tier_id}: {response.status}")
                                # Use fallback name
                                tiers[tier_id] = f"Tier {tier_id}"
                    except Exception as e:
                        print(f"[PatreonCore] Error processing tier {tier_id}: {e}")
                        # Use fallback name
                        tiers[tier_id] = f"Tier {tier_id}"

            # If no tiers found at all, use hardcoded values as fallback
            if not tiers:
                print("[PatreonCore] Using fallback tier IDs")
                tiers = {
                    "21626836": "Tier 21626836",
                    "21626838": "Tier 21626838",
                    "22117682": "Tier 22117682",
                    "22117697": "Tier 22117697",
                    "22117706": "Tier 22117706"
                }

            return tiers

        except Exception as e:
            print(f"[PatreonCore] Error in fetch_tiers: {e}")
            import traceback
            traceback.print_exc()
            return {}

    @commands.command()
    @is_gm()
    async def forcesync(self, ctx):
        """Force synchronization of Patreon pledges with Discord roles"""
        try:
            await ctx.send("🔄 Forcing Patreon role sync... This may take a minute.")

            # Cancel existing task if running
            if self.update_roles.is_running():
                self.update_roles.cancel()

            # Run update immediately
            await self.update_roles()

            if self.last_updated:
                await ctx.send(
                    f"✅ Patreon role sync complete! Last updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                await ctx.send("⚠️ Patreon role sync attempted but may have failed. Check logs for details.")

            # Restart the task
            if not self.update_roles.is_running():
                self.update_roles.start()
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)

    @commands.command()
    @is_gm()
    async def patronstatus(self, ctx):
        """Show status of Patreon integration"""
        embed = discord.Embed(
            title="Patreon Bot Status",
            color=0xFF5441
        )

        # Check if configured
        if not self.guild_id:
            embed.description = "⚠️ Patreon integration is not fully configured. Use `!patreonsetup` to configure."
            await ctx.send(embed=embed)
            return

        # Basic info
        embed.add_field(name="Guild ID", value=str(self.guild_id), inline=True)
        embed.add_field(name="Update Interval", value=f"{self.check_interval // 60} minutes", inline=True)

        if self.log_channel_id:
            log_channel = self.bot.get_channel(self.log_channel_id)
            embed.add_field(name="Log Channel", value=log_channel.mention if log_channel else "Invalid Channel",
                            inline=True)
        else:
            embed.add_field(name="Log Channel", value="Not set", inline=True)

        # Token info
        now = datetime.now()
        if self.token_expires_at > now:
            expires_in = self.token_expires_at - now
            token_status = f"Valid (Expires in {expires_in.days} days, {expires_in.seconds // 3600} hours)"
        else:
            token_status = "Expired! Will try to refresh on next update."

        embed.add_field(name="Token Status", value=token_status, inline=False)

        # Tier mappings
        if self.tier_role_mapping:
            tier_mappings = []
            guild = self.bot.get_guild(self.guild_id)

            for tier_id, role_id in self.tier_role_mapping.items():
                role = guild.get_role(int(role_id)) if guild else None
                role_name = role.name if role else "Invalid Role"
                tier_mappings.append(f"• Tier {tier_id} → {role_name}")

            embed.add_field(name="Tier Mappings", value="\n".join(tier_mappings), inline=False)
        else:
            embed.add_field(name="Tier Mappings", value="No tier mappings configured", inline=False)

        # Patron info
        if self.last_updated:
            embed.add_field(name="Patrons Tracked", value=str(len(self.patrons_data)), inline=True)
            embed.add_field(name="Last Updated", value=self.last_updated.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
            embed.set_footer(
                text=f"Next update in approximately {self.update_roles.next_iteration - datetime.now()} (HH:MM:SS)")
        else:
            embed.add_field(name="Status", value="No patron data fetched yet", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    @is_gm()
    async def patronlist(self, ctx):
        """List all patrons with their roles"""
        if not self.patrons_data:
            await ctx.send("❌ No patron data available.")
            return

        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            await ctx.send("❌ Could not find guild!")
            return

        # Create a reverse mapping from role IDs to tier names
        role_to_tier = {}
        for tier_id, role_id in self.tier_role_mapping.items():
            role = guild.get_role(int(role_id))
            if role:
                role_to_tier[int(role_id)] = role.name

        embed = discord.Embed(
            title="Patreon Supporters",
            description=f"Total patrons: {len(self.patrons_data)}",
            color=0xFF5441
        )

        # Limit to 25 patrons to avoid hitting embed limits
        count = 0
        for discord_id, tier_ids in list(self.patrons_data.items())[:25]:
            try:
                member = await guild.fetch_member(int(discord_id))
                if member:
                    role_names = []
                    for tier_id in tier_ids:
                        if tier_id in self.tier_role_mapping:
                            role_id = int(self.tier_role_mapping[tier_id])
                            if role_id in role_to_tier:
                                role_names.append(role_to_tier[role_id])

                    embed.add_field(
                        name=member.display_name,
                        value=", ".join(role_names) if role_names else "No tier",
                        inline=True
                    )
                    count += 1
            except:
                pass

        if count == 0:
            await ctx.send("❌ No patron data could be displayed.")
        else:
            if count < len(self.patrons_data):
                embed.set_footer(text=f"Showing {count} of {len(self.patrons_data)} patrons")
            await ctx.send(embed=embed)

    @commands.command()
    @is_gm()
    async def refreshtoken(self, ctx):
        """Manually refresh the Patreon access token"""
        await ctx.send("🔄 Attempting to refresh Patreon access token...")

        success = await self.refresh_access_token()

        if success:
            await ctx.send(
                f"✅ Token refreshed successfully! New expiration: {self.token_expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            await ctx.send("❌ Failed to refresh token. Check logs for details.")
            
    @commands.command()
    @is_gm()
    async def check_tiers(self, ctx):
        """Manually check all patron tiers and provide detailed debugging output"""
        await ctx.send("🔍 Beginning manual tier check...")
        
        if not self.guild_id:
            return await ctx.send("❌ Guild ID not set. Cannot check tiers!")
            
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return await ctx.send(f"❌ Could not find guild with ID {self.guild_id}!")
            
        status_msg = await ctx.send("📊 Fetching patron data...")
        
        try:
            # Fetch latest data if needed
            if not self.patrons_data:
                patrons, included = await self.fetch_patrons()
                if not patrons:
                    return await status_msg.edit(content="❌ No patrons fetched. Check logs for details.")
                self.patrons_data = self.process_patrons(patrons, included)
                
            await status_msg.edit(content=f"📊 Processing {len(self.patrons_data)} patrons...")
            
            debug_output = ["**Tier Check Debug Report**"]
            total_members = 0
            tier_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
            role_debug = []
            
            # Check each member's roles and determine tier
            for member_id, tier_ids in self.patrons_data.items():
                try:
                    member = await guild.fetch_member(int(member_id))
                    if not member:
                        role_debug.append(f"⚠️ Member not found: {member_id}")
                        continue
                        
                    total_members += 1
                    member_debug = [f"**Member:** {member.display_name} ({member_id})\n**Tier IDs:** {tier_ids}"]
                    
                    # Find assigned roles
                    should_have_roles = set()
                    for tier_id in tier_ids:
                        if tier_id in self.tier_role_mapping:
                            role_id = int(self.tier_role_mapping[tier_id])
                            should_have_roles.add(role_id)
                            role = guild.get_role(role_id)
                            member_debug.append(f"- Should have role: {role.name if role else 'Unknown'} ({role_id})")
                    
                    # Check current roles
                    has_roles = set()
                    patron_roles = []
                    for role_id in self.tier_role_mapping.values():
                        role = guild.get_role(int(role_id))
                        if role and role in member.roles:
                            has_roles.add(int(role_id))
                            patron_roles.append(role.name)
                    
                    member_debug.append(f"- Current patron roles: {', '.join(patron_roles) if patron_roles else 'None'}")
                    
                    # Determine tier level based on role names
                    tier_level = 0
                    roles_checked = []
                    for role in member.roles:
                        role_name = role.name
                        roles_checked.append(role_name)
                        if "Ragnarok" in role_name:
                            tier_level = max(tier_level, 4)
                            member_debug.append(f"- Found Ragnarok role: {role_name}")
                        elif "Legendary" in role_name:
                            tier_level = max(tier_level, 3)
                            member_debug.append(f"- Found Legendary role: {role_name}")
                        elif "Warrior" in role_name:
                            tier_level = max(tier_level, 2)
                            member_debug.append(f"- Found Warrior role: {role_name}")
                        elif "Adventurer" in role_name:
                            tier_level = max(tier_level, 1)
                            member_debug.append(f"- Found Adventurer role: {role_name}")
                    
                    member_debug.append(f"- All roles checked: {', '.join(roles_checked)}")
                    tier_counts[tier_level] += 1
                    member_debug.append(f"- **Calculated tier level: {tier_level}**")
                    
                    # Check if database update would work
                    try:
                        await self.bot.pool.execute(
                            'SELECT 1 FROM profile WHERE "user"=$1', int(member_id)
                        )
                        member_debug.append(f"- Database record exists: ✅")
                    except Exception as db_error:
                        member_debug.append(f"- Database check failed: ❌ ({str(db_error)})")
                    
                    # Add this member's debug info
                    role_debug.append("\n".join(member_debug))
                    
                except Exception as e:
                    role_debug.append(f"❌ Error processing {member_id}: {str(e)}")
            
            # Create summary
            debug_output.append(f"**Total members processed:** {total_members}")
            debug_output.append(f"**Tier level counts:**")
            debug_output.append(f"- Tier 0 (No tier): {tier_counts[0]}")
            debug_output.append(f"- Tier 1 (Adventurer): {tier_counts[1]}")
            debug_output.append(f"- Tier 2 (Warrior): {tier_counts[2]}")
            debug_output.append(f"- Tier 3 (Legendary): {tier_counts[3]}")
            debug_output.append(f"- Tier 4 (Ragnarok): {tier_counts[4]}")
            
            # Send summary
            await status_msg.edit(content="✅ Tier check complete!")
            await ctx.send("\n".join(debug_output))
            
            # Send member details in chunks to avoid message length limits
            chunks = []
            current_chunk = []
            current_length = 0
            
            for item in role_debug:
                # Discord has a 2000 character limit
                if current_length + len(item) + 2 > 1900:  # Add some buffer
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = [item]
                    current_length = len(item)
                else:
                    current_chunk.append(item)
                    current_length += len(item) + 2  # +2 for the newlines
            
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
            
            for i, chunk in enumerate(chunks):
                await ctx.send(f"**Member Details ({i+1}/{len(chunks)}):**\n\n{chunk}")
                
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(f"❌ Error during tier check: ```{error_message[:1500]}```")
            print(error_message)
            
    @commands.command()
    @user_cooldown(2764800)  # 32 days in seconds (32 * 24 * 60 * 60)
    async def redeemweapontokens(self, ctx):
        """Redeem 5 weapon tokens if you're a patron (tier 1 or higher)."""
        # Check if the user has tier 1 or higher in the database
        async with self.bot.pool.acquire() as conn:
            patron_tier = await conn.fetchval(
                'SELECT "tier" FROM profile WHERE "user"=$1',
                ctx.author.id
            )
            
            # If tier is None or less than 1, deny the request and reset cooldown
            if patron_tier is None or patron_tier < 1:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send("❌ You need to be a patron (tier 1 or higher) to redeem weapon tokens!")
            
            # Add 5 weapon tokens to their account
            try:
                # Update weapon tokens
                await conn.execute(
                    'UPDATE profile SET "weapontoken"="weapontoken"+5 WHERE "user"=$1',
                    ctx.author.id
                )
                
                # Get new weapon token balance for confirmation message
                new_balance = await conn.fetchval(
                    'SELECT "weapontoken" FROM profile WHERE "user"=$1',
                    ctx.author.id
                )
                
                # Log the redemption if log channel is set
                if self.log_channel_id:
                    log_channel = self.bot.get_channel(self.log_channel_id)
                    if log_channel:
                        await log_channel.send(f"⚔️ **Weapon Token Redemption**: {ctx.author.mention} ({ctx.author.id}) redeemed 5 weapon tokens as a Tier {patron_tier} Patron.")
                
                # Create an embed for a nice response
                embed = discord.Embed(
                    title="⚔️ Weapon Tokens Redeemed!",
                    description=f"Thank you for supporting us as a patron!",
                    color=0x3CB371  # Medium sea green
                )
                embed.add_field(name="Tokens Added", value="5", inline=True)
                embed.add_field(name="New Balance", value=f"{new_balance:,}", inline=True)
                embed.add_field(name="Patron Tier", value=f"Tier {patron_tier}", inline=True)
                embed.set_footer(text="You can redeem weapon tokens once every 32 days.")
                
                await ctx.send(embed=embed)
                
            except Exception as e:
                # Reset cooldown so they can try again if error occurs
                self.bot.reset_cooldown(ctx)
                await ctx.send(f"❌ Error updating your weapon tokens: {e}")
                # Log the error
                print(f"[PatreonCore] Error in redeemweapontokens for {ctx.author.id}: {e}")


# Function to add this cog to your bot
async def setup(bot):
    await bot.add_cog(PatreonCore(bot))
