import discord
from discord.ext import commands, tasks
import asyncpg
from datetime import datetime, time, timedelta
import asyncio

class PatreonStuff(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        ids_section = getattr(self.bot.config, "ids", None)
        patreonstuff_ids = getattr(ids_section, "patreonstuff", {}) if ids_section else {}
        if not isinstance(patreonstuff_ids, dict):
            patreonstuff_ids = {}
        self.guild_id = patreonstuff_ids.get("guild_id")

        # Start tasks after the database is initialized
        self.periodic_tier_assignment.start()
        self.monthly_token_increment.start()

        # Define excluded user IDs
        excluded_ids = patreonstuff_ids.get("excluded_user_ids", [])
        if isinstance(excluded_ids, list):
            self.EXCLUDED_USER_IDS = set(excluded_ids)
        else:
            self.EXCLUDED_USER_IDS = set()

        # Role to Tier mapping
        role_tier_mapping = patreonstuff_ids.get("role_tier_mapping", {})
        self.ROLE_TIER_MAPPING = {}
        if isinstance(role_tier_mapping, dict):
            for role_id, tier in role_tier_mapping.items():
                try:
                    self.ROLE_TIER_MAPPING[int(role_id)] = int(tier)
                except (TypeError, ValueError):
                    continue

        # Role to Token Increment mapping for monthly updates
        role_token_updates = patreonstuff_ids.get("role_token_updates", {})
        self.ROLE_TOKEN_UPDATES = {}
        if isinstance(role_token_updates, dict):
            for role_id, token_increment in role_token_updates.items():
                try:
                    self.ROLE_TOKEN_UPDATES[int(role_id)] = int(token_increment)
                except (TypeError, ValueError):
                    continue

    def cog_unload(self):
        self.periodic_tier_assignment.cancel()
        self.monthly_token_increment.cancel()


    @tasks.loop(minutes=5)
    async def periodic_tier_assignment(self):
        print('PatreonStuff Cog: Running periodic tier assignment task.')

        guild = self.bot.get_guild(self.guild_id) if self.guild_id else None
        if guild is None:
            print('PatreonStuff Cog: Guild not found.')
            return

        async with self.bot.pool.acquire() as connection:
            try:
                # Fetch all members to minimize API calls
                async for member in guild.fetch_members(limit=None):
                    if member.id in self.EXCLUDED_USER_IDS:
                        continue

                    # Determine the highest tier based on roles
                    user_tier = 0
                    for role_id, tier in self.ROLE_TIER_MAPPING.items():
                        role = guild.get_role(role_id)
                        if role and role in member.roles:
                            if tier > user_tier:
                                user_tier = tier

                    # Fetch current tier from the database
                    record = await connection.fetchrow(
                        'SELECT "tier" FROM profile WHERE "user" = $1',
                        member.id
                    )

                    current_tier = record['tier'] if record else 0

                    if user_tier != current_tier:
                        # Update tier in the database
                        if record:
                            await connection.execute(
                                'UPDATE profile SET "tier" = $1 WHERE "user" = $2',
                                user_tier, member.id
                            )


                        print(f'PatreonStuff Cog: Updated tier for user {member.id} to {user_tier}')
            except Exception as e:
                print(f'PatreonStuff Cog: Error in periodic_tier_assignment: {e}')

        print('PatreonStuff Cog: Periodic tier assignment task completed.')

    @periodic_tier_assignment.before_loop
    async def before_periodic_tier_assignment(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=time(0, 0))  # Runs daily at midnight UTC
    async def monthly_token_increment(self):
        now = datetime.utcnow()
        if now.day != 1:
            return  # Only proceed on the 1st day of the month

        print(f'PatreonStuff Cog: Running monthly token increment on {now.strftime("%Y-%m-%d")}')

        guild = self.bot.get_guild(self.guild_id) if self.guild_id else None
        if guild is None:
            print('PatreonStuff Cog: Guild not found.')
            return

        async with self.bot.pool.acquire() as connection:
            try:
                for role_id, token_increment in self.ROLE_TOKEN_UPDATES.items():
                    role = guild.get_role(role_id)
                    if role is None:
                        print(f'PatreonStuff Cog: Role with ID {role_id} not found.')
                        continue

                    for member in role.members:
                        if member.id in self.EXCLUDED_USER_IDS:
                            continue

                        await connection.execute(
                            '''UPDATE profile
                               SET weapontoken = weapontoken + $1
                               WHERE "user" = $2''',
                            token_increment, member.id
                        )
                        print(f'PatreonStuff Cog: Incremented {token_increment} tokens for user {member.id}')
            except Exception as e:
                print(f'PatreonStuff Cog: Error in monthly_token_increment: {e}')

        print('PatreonStuff Cog: Monthly token increment completed.')

    @monthly_token_increment.before_loop
    async def before_monthly_token_increment(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(PatreonStuff(bot))
