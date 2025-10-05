import discord
from discord.ext import commands
from discord import ui
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import asyncio
import functools
import logging

from utils.checks import is_gm

# Set up logging
logger = logging.getLogger('transaction_cog')

# The big list of all valid subjects
VALID_SUBJECTS = [
    "gambling BJ", "Chaos Raid Crate",  "Pet Item Fetch", "Active Battle Bet", "guild invest", "Family Event",
    "daily", "Level Up!", "shop buy", "guild pay", "item", "Pet Purchase", "exchange", "item = OFFER",
    "vote", "crates", "shop buy - bot give", "Tournament Prize", "gambling BJ-Insurance",
    "Battle Bet", "spoil", "FamilyEvent Crate", "FamilyEvent Money", "RaidBattle Bet",
    "Raid Stats Upgrade DEF", "crate open item", "raid bid winner", "gambling roulette",
    "crates offercrate", "Starting out", "money", "class change", "give money", "gambling coinflip",
    "adventure", "Raid Stats Upgrade ATK", "AA Reward", "bid", "crates trade", "steal",
    "Raid Stats Upgrade HEALTH", "Torunament Winner", "buy boosters", "merch", "offer",
    "alliance", "sacrifice", "gambling", "Memorial Item", "shop"
]

# Group subjects by category for faster filtering
SUBJECT_CATEGORIES = {
    "gambling": [s for s in VALID_SUBJECTS if "gambling" in s.lower()],
    "shop": [s for s in VALID_SUBJECTS if "shop" in s.lower()],
    "item": [s for s in VALID_SUBJECTS if "item" in s.lower() or "crate" in s.lower()],
    "guild": [s for s in VALID_SUBJECTS if "guild" in s.lower()],
    "Battle": [s for s in VALID_SUBJECTS if "battle" in s.lower() or "raid" in s.lower()],
    "Family Event": [s for s in VALID_SUBJECTS if "event" in s.lower() or "family" in s.lower()],
    "daily": ["daily", "vote"]
}

# Constants
MAX_TRANSACTIONS = 1000  # Limit number of transactions to prevent hanging
QUERY_TIMEOUT = 10.0  # Timeout for database queries (seconds)


class UserCache:
    """Cache for user data to reduce API calls"""

    def __init__(self, max_size=100):
        self.cache = {}
        self.max_size = max_size

    async def get_user(self, bot, user_id):
        """Get user from cache or fetch if not cached"""
        if user_id in self.cache:
            return self.cache[user_id]

        try:
            user = await bot.fetch_user(user_id)
            # If cache is full, remove oldest entry
            if len(self.cache) >= self.max_size:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
            self.cache[user_id] = user
            return user
        except discord.NotFound:
            # Cache negative results too to avoid repeated failed lookups
            self.cache[user_id] = None
            return None
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {str(e)}")
            return None


class UserSelectModal(ui.Modal, title='User Filter'):
    """Modal that asks for username/ID, then updates the parent view with the user filter."""

    def __init__(self, bot, update_callback):
        super().__init__()
        self.bot = bot
        self.update_callback = update_callback

    user_input = ui.TextInput(
        label='Enter Username, ID, or mention',
        placeholder='Example: johndoe#1234 or 123456789',
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not self.user_input.value:
            await interaction.response.defer(ephemeral=True)
            await self.update_callback(interaction, None)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Try different methods to find the user
            user_input = self.user_input.value.strip()

            # Remove mention formatting if present
            user_input = user_input.replace('<@!', '').replace('<@', '').replace('>', '')

            # Try to find by ID first
            if user_input.isdigit():
                user = await self.bot.fetch_user(int(user_input))
                await self.update_callback(interaction, user)
            else:
                # Try to find by name
                # This is harder with new Discord username system, but we'll try
                await interaction.followup.send(
                    "Sorry, searching by username is less reliable now. Please try using a user ID instead.",
                    ephemeral=True
                )
                await self.update_callback(interaction, None)
        except Exception as e:
            await interaction.followup.send(
                f"Error finding user: {str(e)}. Please try again with a valid user ID.",
                ephemeral=True
            )


class SubjectSelectView(ui.View):
    """
    A paginated view that shows a large list of valid subjects in a Select menu.
    When the user picks a subject, we pass it back to the original TransactionView.
    """

    def __init__(self, parent_view, interaction_user: discord.User, valid_subjects, per_page=25):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.interaction_user = interaction_user
        self.valid_subjects = valid_subjects
        self.per_page = per_page
        self.current_page = 0
        self.pages = [
            valid_subjects[i:i + per_page] for i in range(0, len(valid_subjects), per_page)
        ]
        self.update_subject_select()

    def update_subject_select(self):
        """Update the select menu with options for the current page"""
        # Remove existing select if it exists
        for item in self.children[:]:
            if isinstance(item, ui.Select):
                self.remove_item(item)

        # Create new select
        options = [discord.SelectOption(label=subject, value=subject)
                   for subject in self.pages[self.current_page]]

        select = ui.Select(
            placeholder="Choose a subject...",
            min_values=1,
            max_values=1,
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        # Only let the original user respond
        if interaction.user.id != self.interaction_user.id:
            await interaction.response.send_message(
                "You are not the user who opened this menu.",
                ephemeral=True
            )
            return

        chosen_subject = interaction.data['values'][0]
        self.parent_view.subject = chosen_subject
        self.parent_view.current_page = 0

        # Let user know we're working on it
        await interaction.response.defer(ephemeral=True)

        # Force a refresh of the parent view
        await self.parent_view.refresh_transactions()
        await interaction.delete_original_response()

    @ui.button(label="◀ Prev", style=discord.ButtonStyle.gray, row=1)
    async def previous_page(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.interaction_user.id:
            await interaction.response.defer(ephemeral=True)
            return

        if self.current_page > 0:
            self.current_page -= 1
            self.update_subject_select()

        await interaction.response.edit_message(
            content=f"Select a subject (Page {self.current_page + 1}/{len(self.pages)})",
            view=self
        )

    @ui.button(label="Next ▶", style=discord.ButtonStyle.gray, row=1)
    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.interaction_user.id:
            await interaction.response.defer(ephemeral=True)
            return

        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_subject_select()

        await interaction.response.edit_message(
            content=f"Select a subject (Page {self.current_page + 1}/{len(self.pages)})",
            view=self
        )

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.interaction_user.id:
            await interaction.response.defer(ephemeral=True)
            return
        await interaction.delete_original_response()

    async def on_timeout(self):
        # Selector view simply stops accepting interactions after timeout
        pass


class TransactionView(ui.View):
    def __init__(self, ctx, user1: discord.User):
        super().__init__(timeout=300)  # 5-minute timeout
        self.ctx = ctx
        self.user1 = user1
        self.user2 = None
        self.subject = "all"
        self.start_date = None
        self.end_date = None
        self.current_page = 0
        self.message = None
        self.transactions_cache = None
        self.total_pages = 0
        self.per_page = 5
        self.user_cache = UserCache()
        self.is_refreshing = False
        self.last_refresh = None
        self.refresh_lock = asyncio.Lock()
        self.is_initialized = False  # Flag to track initial data load

    def disable_all_controls(self):
        """Disable all buttons and dropdowns"""
        for item in self.children:
            item.disabled = True

    def enable_all_controls(self):
        """Enable all controls except pagination buttons which depend on page state"""
        for item in self.children:
            # For buttons, check if they're pagination buttons
            if isinstance(item, ui.Button):
                if not (item.label == "◀" or item.label == "▶"):
                    item.disabled = False
            # For other UI elements (Select menus, etc.)
            else:
                item.disabled = False

    @ui.select(
        placeholder="Select transaction category",
        options=[
            discord.SelectOption(label="All Transactions", value="all", emoji="📋"),
            discord.SelectOption(label="Gambling", value="gambling", emoji="🎲"),
            discord.SelectOption(label="Shop", value="shop", emoji="🛍️"),
            discord.SelectOption(label="Trading", value="item", emoji="🔄"),
            discord.SelectOption(label="Guild", value="guild", emoji="⚔️"),
            discord.SelectOption(label="Battle", value="Battle", emoji="⚔️"),
            discord.SelectOption(label="Events", value="Family Event", emoji="🎉"),
            discord.SelectOption(label="Daily/Vote", value="daily", emoji="📅"),
        ],
        row=0,
        disabled=True  # Start disabled until data loads
    )
    async def select_subject(self, interaction: discord.Interaction, select: ui.Select):
        # Immediately notify user we're handling this
        await interaction.response.defer()

        if self.is_refreshing:
            return

        old_subject = self.subject
        self.subject = select.values[0]
        self.current_page = 0

        # Only refresh if the value actually changed
        if old_subject != self.subject:
            await self.refresh_transactions(interaction)

    @ui.select(
        placeholder="Select time period",
        options=[
            discord.SelectOption(label="All Time", value="all", emoji="♾️"),
            discord.SelectOption(label="Last 24 Hours", value="24h", emoji="⏰"),
            discord.SelectOption(label="Last Week", value="7d", emoji="📅"),
            discord.SelectOption(label="Last Month", value="30d", emoji="📆"),
            discord.SelectOption(label="Last 3 Months", value="90d", emoji="🗓️"),
        ],
        row=1,
        disabled=True  # Start disabled until data loads
    )
    async def select_timeframe(self, interaction: discord.Interaction, select: ui.Select):
        await interaction.response.defer()

        if self.is_refreshing:
            return

        old_start = self.start_date
        old_end = self.end_date

        now = datetime.utcnow()
        if select.values[0] == "all":
            self.start_date = None
            self.end_date = None
        else:
            days_map = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}
            self.start_date = now - timedelta(days=days_map[select.values[0]])
            self.end_date = now

        # Only refresh if dates actually changed
        if old_start != self.start_date or old_end != self.end_date:
            self.current_page = 0
            await self.refresh_transactions(interaction)

    @ui.button(label="◀", style=discord.ButtonStyle.gray, row=2, disabled=True)
    async def previous_page(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()

        if self.is_refreshing:
            return

        if self.current_page > 0:
            self.current_page -= 1
            await self.update_embed(interaction)

    @ui.button(label="▶", style=discord.ButtonStyle.gray, row=2, disabled=True)
    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()

        if self.is_refreshing:
            return

        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_embed(interaction)

    @ui.button(label="🔍 Filter User", style=discord.ButtonStyle.primary, row=2, disabled=True)
    async def filter_user(self, interaction: discord.Interaction, button: ui.Button):
        if self.is_refreshing:
            await interaction.response.defer(ephemeral=True)
            return

        # Show a modal to get the user
        modal = UserSelectModal(self.ctx.bot, self.user_filter_callback)
        await interaction.response.send_modal(modal)

    async def user_filter_callback(self, interaction, user):
        """Callback from the user selection modal"""
        self.user2 = user
        self.current_page = 0

        if user:
            await interaction.followup.send(
                f"Filter set to user: {user.name}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Filter cleared - showing all users.",
                ephemeral=True
            )

        await self.refresh_transactions()

    @ui.button(label="❌ Clear Filter", style=discord.ButtonStyle.danger, row=2, disabled=True)
    async def clear_filter(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()

        if self.is_refreshing:
            return

        if self.user2 or self.subject != "all" or self.start_date or self.end_date:
            self.user2 = None
            self.subject = "all"
            self.current_page = 0
            self.start_date = None
            self.end_date = None
            await self.refresh_transactions(interaction)

    @ui.button(label="🔍 Filter Subject", style=discord.ButtonStyle.secondary, row=3, disabled=True)
    async def filter_subject(self, interaction: discord.Interaction, button: ui.Button):
        if self.is_refreshing:
            await interaction.response.defer(ephemeral=True)
            return

        view = SubjectSelectView(
            parent_view=self,
            interaction_user=interaction.user,
            valid_subjects=VALID_SUBJECTS
        )

        await interaction.response.send_message(
            content=f"Select a subject (Page 1/{len(view.pages)})",
            view=view,
            ephemeral=True
        )

    @ui.button(label="🗑️ Close", style=discord.ButtonStyle.secondary, row=3, disabled=True)
    async def cleanup_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        if self.message:
            await self.message.delete()
            self.stop()

    async def on_timeout(self):
        """Called when the view times out (after 300s of inactivity)."""
        try:
            # Disable all controls
            self.disable_all_controls()

            # Update the message if it still exists
            if self.message:
                try:
                    embed = self.message.embeds[0]
                    embed.set_footer(text="This menu has timed out. Use the command again to view transactions.")
                    await self.message.edit(view=self, embed=embed)
                except discord.NotFound:
                    pass
        except Exception:
            pass

    async def refresh_transactions(self, interaction=None):
        """Reload transactions from database with safeguards"""
        # Check if we're already refreshing
        if self.is_refreshing:
            return

        # Try to acquire the lock - but don't block if it's locked
        if self.refresh_lock.locked():
            return  # Another refresh is already in progress

        # Acquire the lock
        await self.refresh_lock.acquire()

        try:
            # Set flag to prevent button spamming
            self.is_refreshing = True
            self.transactions_cache = None

            # Show loading state
            loading_embed = discord.Embed(
                title="Transaction History",
                description=(
                    f"⏳ Loading transactions for **{self.user1.name}**...\n"
                    "Please wait while we fetch your data."
                ),
                color=discord.Color.orange()
            )

            # Disable all controls while loading
            self.disable_all_controls()

            # Update message with loading state
            if interaction and hasattr(interaction, 'edit_original_response'):
                await interaction.edit_original_response(embed=loading_embed, view=self)
            elif self.message:
                await self.message.edit(embed=loading_embed, view=self)

            # Fetch transactions with a timeout
            try:
                # Set a timeout for the database query
                async with asyncio.timeout(QUERY_TIMEOUT):
                    await self.fetch_transactions()
            except asyncio.TimeoutError:
                # Handle query timeout
                error_embed = discord.Embed(
                    title="Database Timeout",
                    description=(
                        "The database query took too long to complete.\n"
                        "Try applying more filters or using a shorter time period."
                    ),
                    color=discord.Color.red()
                )
                self.enable_all_controls()

                if interaction and hasattr(interaction, 'edit_original_response'):
                    await interaction.edit_original_response(embed=error_embed, view=self)
                elif self.message:
                    await self.message.edit(embed=error_embed, view=self)
                return

            # Enable controls now that data is ready
            self.enable_all_controls()

            # Now that data is loaded, we're initialized
            self.is_initialized = True

            # Update the UI
            if interaction:
                await self.update_embed(interaction)
            elif self.message:
                await self.update_embed(self.message)

        except Exception as e:
            # Create error embed
            error_embed = discord.Embed(
                title="Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )

            # Re-enable controls so the user can try again
            self.enable_all_controls()

            # Update message with error
            if interaction and hasattr(interaction, 'edit_original_response'):
                await interaction.edit_original_response(embed=error_embed, view=self)
            elif self.message:
                await self.message.edit(embed=error_embed, view=self)

        finally:
            self.is_refreshing = False
            self.last_refresh = datetime.utcnow()
            self.refresh_lock.release()  # Always release the lock

    async def fetch_transactions(self):
        """Fetch transactions from database with a row limit"""
        async with self.ctx.bot.pool.acquire() as connection:
            # Build base query
            params = []
            param_index = 1

            if self.user2:
                # Filter between two specific users
                query = """
                    SELECT * FROM transactions
                    WHERE (( "from" = $1 AND "to" = $2 ) OR ( "from" = $2 AND "to" = $1 ))
                """
                params.extend([self.user1.id, self.user2.id])
                param_index += 2
            else:
                # All transactions for one user
                query = """
                    SELECT * FROM transactions
                    WHERE ("from" = $1 OR "to" = $1)
                """
                params.append(self.user1.id)
                param_index += 1

            # Apply subject filter
            if self.subject != "all":
                if self.subject in VALID_SUBJECTS:
                    # Exact match
                    query += f" AND subject = ${param_index}"
                    params.append(self.subject)
                    param_index += 1
                elif self.subject in SUBJECT_CATEGORIES:
                    # Match any subject in the category
                    placeholders = [f"${i}" for i in
                                    range(param_index, param_index + len(SUBJECT_CATEGORIES[self.subject]))]
                    query += f" AND subject IN ({', '.join(placeholders)})"
                    params.extend(SUBJECT_CATEGORIES[self.subject])
                    param_index += len(SUBJECT_CATEGORIES[self.subject])
                else:
                    # Partial/LIKE match
                    query += f" AND subject ILIKE ${param_index}"
                    params.append(f"%{self.subject}%")
                    param_index += 1

            # Date filters
            if self.start_date:
                query += f" AND timestamp >= ${param_index}"
                params.append(self.start_date)
                param_index += 1
            if self.end_date:
                query += f" AND timestamp <= ${param_index}"
                params.append(self.end_date)
                param_index += 1

            # Order by newest first
            query += " ORDER BY timestamp DESC"

            # Add row limit to prevent hanging
            query += f" LIMIT {MAX_TRANSACTIONS}"

            # Execute the query
            self.transactions_cache = await connection.fetch(query, *params)

            # Calculate total pages
            self.total_pages = max(1, (len(self.transactions_cache) + self.per_page - 1) // self.per_page)

            # Ensure current page is within bounds
            if self.current_page >= self.total_pages:
                self.current_page = max(0, self.total_pages - 1)

    async def update_embed(self, interaction_or_message):
        """Update the embed with the current page of transactions"""
        try:
            # Create base embed
            embed = discord.Embed(
                title="Transaction History",
                color=discord.Color.blurple()
            )

            # Handle case of no transactions
            if not self.transactions_cache:
                if self.user2:
                    user_filter = f"📊 Transactions between **{self.user1.name}** and **{self.user2.name}**"
                else:
                    user_filter = f"📊 All transactions for **{self.user1.name}**"

                embed.description = (
                    f"{user_filter}\n\n"
                    "❌ No transactions found matching the criteria."
                )

                # Update the message based on what was passed in
                if isinstance(interaction_or_message, discord.Message):
                    await interaction_or_message.edit(embed=embed, view=self)
                elif hasattr(interaction_or_message, 'edit_original_response'):
                    await interaction_or_message.edit_original_response(embed=embed, view=self)
                else:
                    await interaction_or_message.response.edit_message(embed=embed, view=self)
                return

            # Get current page of transactions
            start_idx = self.current_page * self.per_page
            end_idx = min(start_idx + self.per_page, len(self.transactions_cache))
            current_transactions = self.transactions_cache[start_idx:end_idx]

            # Create header for embed
            if self.user2:
                user_filter = f"📊 Transactions between **{self.user1.name}** and **{self.user2.name}**"
            else:
                user_filter = f"📊 All transactions for **{self.user1.name}**"

            filter_info = []
            if self.subject != "all":
                filter_info.append(f"Type: {self.subject}")
            if self.start_date:
                date_str = f"{self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}"
                filter_info.append(f"Period: {date_str}")

            # Add notice if results were limited
            results_info = ""
            if len(self.transactions_cache) >= MAX_TRANSACTIONS:
                results_info = f"\n⚠️ Results limited to {MAX_TRANSACTIONS} most recent transactions. Apply filters for more specific results."

            embed.description = f"{user_filter}\n"
            if filter_info:
                embed.description += f"**Active Filters:** {' | '.join(filter_info)}\n"
            embed.description += results_info

            # Fetch user information for all transactions at once
            user_ids = set()
            for transaction in current_transactions:
                user_ids.add(transaction['from'])
                user_ids.add(transaction['to'])

            # Pre-fetch users in parallel for better performance
            await asyncio.gather(*[self.user_cache.get_user(self.ctx.bot, user_id) for user_id in user_ids])

            # Add transaction fields to embed
            for transaction in current_transactions:
                # Get user info from cache
                from_user = await self.user_cache.get_user(self.ctx.bot, transaction['from'])
                to_user = await self.user_cache.get_user(self.ctx.bot, transaction['to'])

                from_name = from_user.name if from_user else f"Unknown ({transaction['from']})"
                to_name = to_user.name if to_user else f"Unknown ({transaction['to']})"

                embed.add_field(
                    name="Transaction",
                    value=(
                        f"**From:** {from_name}\n"
                        f"**To:** {to_name}\n"
                        f"**Type:** {transaction['subject']}\n"
                        f"**Info:** {transaction.get('info', 'N/A')}\n"
                        f"**Time:** {transaction['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}"
                    ),
                    inline=False
                )

            # Add footer with page info
            embed.set_footer(
                text=(
                    f"Page {self.current_page + 1}/{self.total_pages} • "
                    f"Showing {start_idx + 1}-{end_idx} of {len(self.transactions_cache)} transactions • "
                    "Menu times out after 5m of inactivity."
                )
            )

            # Update buttons based on pagination state
            self.previous_page.disabled = (self.current_page == 0)
            self.next_page.disabled = (self.current_page >= self.total_pages - 1)

            # Update the message based on what was passed in
            if isinstance(interaction_or_message, discord.Message):
                await interaction_or_message.edit(embed=embed, view=self)
            elif hasattr(interaction_or_message, 'edit_original_response'):
                await interaction_or_message.edit_original_response(embed=embed, view=self)
            else:
                await interaction_or_message.response.edit_message(embed=embed, view=self)

        except Exception as e:
            # Create error embed
            error_embed = discord.Embed(
                title="Error",
                description=f"An error occurred updating the view: {str(e)}",
                color=discord.Color.red()
            )

            # Try to update the message
            try:
                if isinstance(interaction_or_message, discord.Message):
                    await interaction_or_message.edit(embed=error_embed, view=self)
                elif hasattr(interaction_or_message, 'edit_original_response'):
                    await interaction_or_message.edit_original_response(embed=error_embed, view=self)
                else:
                    await interaction_or_message.response.edit_message(embed=error_embed, view=self)
            except Exception:
                pass  # If we can't update, there's not much we can do


class TransactionsCog(commands.Cog):
    """A cog for viewing and managing transaction history."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="transactions", aliases=["trans"], hidden=True)
    @is_gm()
    async def view_transactions(self, ctx, user: Optional[discord.User] = None):
        """
        View transaction history with an interactive interface.

        Usage:
        !transactions [optional: @user]
        !trans [optional: @user]

        Examples:
        !transactions - View your own transactions
        !transactions @user - View transactions for a specific user
        """
        target_user = user or ctx.author

        # Create initial loading embed
        embed = discord.Embed(
            title="Transaction History",
            description=(
                f"⏳ Loading data for **{target_user.name}**...\n"
                "Please wait while we connect to the database."
            ),
            color=discord.Color.orange()
        )

        # Create view with all controls disabled initially
        view = TransactionView(ctx, target_user)

        # Send initial message with loading state
        try:
            sent_msg = await ctx.send(embed=embed, view=view)
            view.message = sent_msg

            # Now fetch data and update the view
            await view.refresh_transactions()
        except Exception as e:
            logger.error(f"Error in view_transactions command: {str(e)}")
            await ctx.send(f"An error occurred: {str(e)}")


async def setup(bot):
    await bot.add_cog(TransactionsCog(bot))