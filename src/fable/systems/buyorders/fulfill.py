"""
Fulfill commands for the buy orders system.
"""
import discord
from discord.ext import commands
from contextlib import suppress
from discord.http import handle_message_parameters

from fable.utils.checks import has_char
from fable.utils.i18n import _, locale_doc

class BuyOrderFulfill(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    async def get_crate_emoji(self, crate_type: str) -> str:
        """Get the emoji for a crate type."""
        if hasattr(self.bot.cogs.get("Crates", None), "emotes"):
            crate_emotes = self.bot.cogs["Crates"].emotes
            if hasattr(crate_emotes, crate_type.lower()):
                return getattr(crate_emotes, crate_type.lower())
        return "📦"
    
    @has_char()
    @commands.command(name="fulfillorder", aliases=["fillorder"], brief=_("Fulfill a buy order"))
    @locale_doc
    async def fulfill_order(self, ctx, order_id: int, item_id_or_amount: int = None):
        _("""Fulfill a buy order by selling your item or crates.
        
        For weapon orders:
        - `order_id` is the ID of the buy order
        - `item_id` is the ID of the item from your inventory to sell
        
        For crate orders:
        - `order_id` is the ID of the buy order
        - `amount` is the amount of crates to sell (defaults to 1 if not specified)
        
        The item must match the specifications of the buy order.
        You will immediately receive payment for the items you sell.
        """)
        
        async with self.bot.pool.acquire() as conn:
            # First check if this is a weapon order
            weapon_order = await conn.fetchrow(
                """
                SELECT wo.*, p.user as username, p.name as char_name 
                FROM weapon_buy_orders wo
                JOIN profile p ON wo.user_id = p.user
                WHERE wo.id = $1 AND wo.active = TRUE;
                """,
                order_id
            )
            
            if weapon_order:
                if not item_id_or_amount:
                    return await ctx.send(_("You need to specify the ID of the item you want to sell."))
                
                item_id = item_id_or_amount
                
                # Prevent self-fulfillment
                if weapon_order['user_id'] == ctx.author.id:
                    return await ctx.send(_("You cannot fulfill your own buy orders."))
                
                # Check if order is already filled
                if weapon_order['quantity_filled'] >= weapon_order['quantity']:
                    return await ctx.send(_("This buy order has already been completely filled."))
                
                # Check if item exists and belongs to the user
                item = await conn.fetchrow(
                    """
                    SELECT * FROM inventory i JOIN allitems ai ON (i.item=ai.id) 
                    WHERE ai.id = $1 AND ai.owner = $2;
                    """,
                    item_id,
                    ctx.author.id
                )
                
                if not item:
                    return await ctx.send(_("You don't own an item with the ID {id}.").format(id=item_id))
                
                # Check if item matches the order specifications
                if item['type'].lower() != weapon_order['weapon_type'].lower():
                    return await ctx.send(
                        _("This buy order is for {weapon_type}, but your item is a {item_type}.").format(
                            weapon_type=weapon_order['weapon_type'].title(),
                            item_type=item['type']
                        )
                    )
                
                # Check stat requirements
                item_stat = item['damage'] + item['armor']
                if item_stat < weapon_order['min_stat'] or item_stat > weapon_order['max_stat']:
                    return await ctx.send(
                        _("This buy order requires items with stats between {min_stat} and {max_stat}, but your item has {item_stat}.").format(
                            min_stat=weapon_order['min_stat'],
                            max_stat=weapon_order['max_stat'],
                            item_stat=item_stat
                        )
                    )
                
                # Cannot sell equipped items without confirmation
                if item['equipped']:
                    if not await ctx.confirm(
                        _("Are you sure you want to sell your equipped {item}?").format(
                            item=item["name"]
                        )
                    ):
                        return await ctx.send(_("Item selling cancelled."))
                
                # Check if item is modified (donator-modified items cannot be sold)
                if item['original_name'] or item['original_type']:
                    return await ctx.send(_("You may not sell donator-modified items."))
                
                # Process the sale
                price = weapon_order['price']
                
                # Update buyer's inventory and remove from seller's inventory
                await conn.execute(
                    """
                    UPDATE allitems SET owner = $1 WHERE id = $2;
                    """,
                    weapon_order['user_id'],
                    item_id
                )
                
                await conn.execute(
                    """
                    DELETE FROM inventory i USING allitems ai 
                    WHERE i.item = ai.id AND ai.id = $1 AND ai.owner = $2;
                    """,
                    item_id,
                    weapon_order['user_id']
                )
                
                await conn.execute(
                    """
                    INSERT INTO inventory (item, equipped) VALUES ($1, $2);
                    """,
                    item_id,
                    False
                )
                
                # Update order status
                await conn.execute(
                    """
                    UPDATE weapon_buy_orders 
                    SET quantity_filled = quantity_filled + 1 
                    WHERE id = $1;
                    """,
                    order_id
                )
                
                # Set order to inactive if completely filled
                if weapon_order['quantity_filled'] + 1 >= weapon_order['quantity']:
                    await conn.execute(
                        """
                        UPDATE weapon_buy_orders 
                        SET active = FALSE 
                        WHERE id = $1;
                        """,
                        order_id
                    )
                
                # Pay the seller
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    price,
                    ctx.author.id,
                )
                
                # Record the transaction
                await conn.execute(
                    """
                    INSERT INTO buy_order_fulfillments 
                    (order_id, order_type, seller_id, buyer_id, item_id, price, crate_type, crate_quantity)
                    VALUES ($1, $2, $3, $4, $5, $6, NULL, NULL);
                    """,
                    order_id,
                    "weapon",
                    ctx.author.id,
                    weapon_order['user_id'],
                    item_id,
                    price
                )
                
                # Log the transaction
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=weapon_order['user_id'],
                    subject="buy order fulfillment",
                    data={"Item": item_id, "Name": item['name'], "Price": price},
                    conn=conn,
                )
                
                # Send success message
                success_msg = _(
                    "You've successfully sold your **{item_name}** to fulfill buy order #{order_id}!\n"
                    "You received **${price}**."
                ).format(
                    item_name=item['name'],
                    order_id=order_id,
                    price=price
                )
                
                await ctx.send(success_msg)
                
                # Notify the buyer
                with suppress(discord.Forbidden, discord.HTTPException):
                    buyer_msg = _(
                        "Your buy order #{order_id} has been partially fulfilled!\n"
                        "You received **{item_name}** ({item_stat} {weapon_type}) from {seller}.\n"
                        "Order status: {filled}/{total} items"
                    ).format(
                        order_id=order_id,
                        item_name=item['name'],
                        item_stat=item_stat,
                        weapon_type=weapon_order['weapon_type'].title(),
                        seller=ctx.author.mention,
                        filled=weapon_order['quantity_filled'] + 1,
                        total=weapon_order['quantity']
                    )
                    
                    try:
                        dm_channel = await self.bot.http.start_private_message(weapon_order['user_id'])
                        with handle_message_parameters(content=buyer_msg) as params:
                            await self.bot.http.send_message(
                                dm_channel.get("id"),
                                params=params,
                            )
                    except:
                        # If DM fails, we don't need to handle it
                        pass
                
                return
            
            # Check if it's a crate order
            crate_order = await conn.fetchrow(
                """
                SELECT co.*, p.user as username, p.name as char_name 
                FROM crate_buy_orders co
                JOIN profile p ON co.user_id = p.user
                WHERE co.id = $1 AND co.active = TRUE;
                """,
                order_id
            )
            
            if crate_order:
                # Set default amount to 1 if not specified
                amount = item_id_or_amount if item_id_or_amount is not None else 1
                
                try:
                    amount = int(amount)
                    if amount <= 0:
                        return await ctx.send(_("Amount must be a positive number."))
                except ValueError:
                    return await ctx.send(_("Amount must be a number."))
                
                # Prevent self-fulfillment
                if crate_order['user_id'] == ctx.author.id:
                    return await ctx.send(_("You cannot fulfill your own buy orders."))
                
                # Check if order is already filled
                remaining = crate_order['quantity'] - crate_order['quantity_filled']
                if remaining <= 0:
                    return await ctx.send(_("This buy order has already been completely filled."))
                
                # Limit amount to remaining
                if amount > remaining:
                    amount = remaining
                
                # Check if user has enough crates
                crate_type = crate_order['crate_type']
                user_crates = await conn.fetchval(
                    f"""
                    SELECT crates_{crate_type} FROM profile WHERE "user" = $1;
                    """,
                    ctx.author.id
                )
                
                if user_crates < amount:
                    return await ctx.send(
                        _("You only have {user_amount} {crate_type} crates, but the order requires {amount}.").format(
                            user_amount=user_crates,
                            crate_type=crate_type,
                            amount=amount
                        )
                    )
                
                # Process the sale
                price_each = crate_order['price_each']
                total_price = price_each * amount
                
                # Update crates for both parties
                await conn.execute(
                    f"""
                    UPDATE profile
                    SET crates_{crate_type} = crates_{crate_type} - $1
                    WHERE "user" = $2;
                    """,
                    amount,
                    ctx.author.id
                )
                
                await conn.execute(
                    f"""
                    UPDATE profile
                    SET crates_{crate_type} = crates_{crate_type} + $1
                    WHERE "user" = $2;
                    """,
                    amount,
                    crate_order['user_id']
                )
                
                # Update order status
                await conn.execute(
                    """
                    UPDATE crate_buy_orders 
                    SET quantity_filled = quantity_filled + $1 
                    WHERE id = $2;
                    """,
                    amount,
                    order_id
                )
                
                # Set order to inactive if completely filled
                if crate_order['quantity_filled'] + amount >= crate_order['quantity']:
                    await conn.execute(
                        """
                        UPDATE crate_buy_orders 
                        SET active = FALSE 
                        WHERE id = $1;
                        """,
                        order_id
                    )
                
                # Pay the seller
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    total_price,
                    ctx.author.id,
                )
                
                # Record the transaction
                await conn.execute(
                    """
                    INSERT INTO buy_order_fulfillments 
                    (order_id, order_type, seller_id, buyer_id, item_id, price, crate_type, crate_quantity)
                    VALUES ($1, $2, $3, $4, NULL, $5, $6, $7);
                    """,
                    order_id,
                    "crate",
                    ctx.author.id,
                    crate_order['user_id'],
                    total_price,
                    crate_type,
                    amount
                )
                
                # Log the transaction
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=crate_order['user_id'],
                    subject="buy order fulfillment",
                    data={"Crate Type": crate_type, "Amount": amount, "Price": total_price},
                    conn=conn,
                )
                
                # Get crate emoji
                crate_emoji = await self.get_crate_emoji(crate_type)
                
                # Send success message
                success_msg = _(
                    "You've successfully sold **{amount}x {emoji} {crate_type}** crates to fulfill buy order #{order_id}!\n"
                    "You received **${price}**."
                ).format(
                    amount=amount,
                    emoji=crate_emoji,
                    crate_type=crate_type.title(),
                    order_id=order_id,
                    price=total_price
                )
                
                await ctx.send(success_msg)
                
                # Notify the buyer
                with suppress(discord.Forbidden, discord.HTTPException):
                    buyer_msg = _(
                        "Your buy order #{order_id} has been partially fulfilled!\n"
                        "You received **{amount}x {emoji} {crate_type}** crates from {seller}.\n"
                        "Order status: {filled}/{total} crates"
                    ).format(
                        order_id=order_id,
                        amount=amount,
                        emoji=crate_emoji,
                        crate_type=crate_type.title(),
                        seller=ctx.author.mention,
                        filled=crate_order['quantity_filled'] + amount,
                        total=crate_order['quantity']
                    )
                    
                    try:
                        dm_channel = await self.bot.http.start_private_message(crate_order['user_id'])
                        with handle_message_parameters(content=buyer_msg) as params:
                            await self.bot.http.send_message(
                                dm_channel.get("id"),
                                params=params,
                            )
                    except:
                        # If DM fails, we don't need to handle it
                        pass
                
                return
            
            # No order found
            await ctx.send(_("No active buy order found with ID {id}.").format(id=order_id))

    @has_char()
    @commands.command(name="orderhistory", brief=_("View your buy order history"))
    @locale_doc
    async def order_history(self, ctx):
        _("""View the history of your buy orders, both as a buyer and a seller.""")
        
        async with self.bot.pool.acquire() as conn:
            # Get orders where user is buyer
            buyer_history = await conn.fetch(
                """
                SELECT f.*, 
                       CASE 
                           WHEN f.order_type = 'weapon' THEN 
                               (SELECT id FROM weapon_buy_orders WHERE id = f.order_id)
                           WHEN f.order_type = 'crate' THEN 
                               (SELECT id FROM crate_buy_orders WHERE id = f.order_id)
                       END as original_order_id,
                       COALESCE(p.name, 'Unknown') as seller_name
                FROM buy_order_fulfillments f
                LEFT JOIN profile p ON f.seller_id = p.user
                WHERE f.buyer_id = $1
                ORDER BY f.fulfilled_at DESC
                LIMIT 15;
                """,
                ctx.author.id
            )
            
            # Get orders where user is seller
            seller_history = await conn.fetch(
                """
                SELECT f.*, 
                       CASE 
                           WHEN f.order_type = 'weapon' THEN 
                               (SELECT id FROM weapon_buy_orders WHERE id = f.order_id)
                           WHEN f.order_type = 'crate' THEN 
                               (SELECT id FROM crate_buy_orders WHERE id = f.order_id)
                       END as original_order_id,
                       COALESCE(p.name, 'Unknown') as buyer_name
                FROM buy_order_fulfillments f
                LEFT JOIN profile p ON f.buyer_id = p.user
                WHERE f.seller_id = $1
                ORDER BY f.fulfilled_at DESC
                LIMIT 15;
                """,
                ctx.author.id
            )
        
        if not buyer_history and not seller_history:
            return await ctx.send(_("You don't have any buy order history."))
        
        # Create embed for buyer history
        buyer_embed = discord.Embed(
            title=_("Your Buy Orders - Purchases"),
            color=discord.Color.green(),
            description=_("Items and crates you've purchased through buy orders.")
        )
        
        if buyer_history:
            for record in buyer_history:
                if record['order_type'] == 'weapon':
                    # Get item details if available
                    item_name = "Unknown Item"
                    item_stat = "?"
                    if record['item_id']:
                        item = await self.bot.pool.fetchrow(
                            "SELECT * FROM allitems WHERE id = $1",
                            record['item_id']
                        )
                        if item:
                            item_name = item['name']
                            item_stat = str(item['damage'] + item['armor'])
                    
                    value = _(
                        "**Item:** {item_name} ({stat})\n"
                        "**Seller:** {seller}\n"
                        "**Price:** ${price}\n"
                        "**Date:** {date}"
                    ).format(
                        item_name=item_name,
                        stat=item_stat,
                        seller=record['seller_name'],
                        price=record['price'],
                        date=record['fulfilled_at'].strftime("%Y-%m-%d %H:%M UTC")
                    )
                else:  # crate
                    crate_emoji = await self.get_crate_emoji(record['crate_type'])
                    
                    value = _(
                        "**Crates:** {amount}x {emoji} {crate_type}\n"
                        "**Seller:** {seller}\n"
                        "**Price:** ${price}\n"
                        "**Date:** {date}"
                    ).format(
                        amount=record['crate_quantity'],
                        emoji=crate_emoji,
                        crate_type=record['crate_type'].title(),
                        seller=record['seller_name'],
                        price=record['price'],
                        date=record['fulfilled_at'].strftime("%Y-%m-%d %H:%M UTC")
                    )
                
                buyer_embed.add_field(
                    name=_("Order #{id}").format(id=record['original_order_id']),
                    value=value,
                    inline=False
                )
        else:
            buyer_embed.add_field(
                name=_("No History"),
                value=_("You haven't purchased anything through buy orders yet."),
                inline=False
            )
        
        # Create embed for seller history
        seller_embed = discord.Embed(
            title=_("Your Buy Orders - Sales"),
            color=discord.Color.gold(),
            description=_("Items and crates you've sold to others' buy orders.")
        )
        
        if seller_history:
            for record in seller_history:
                if record['order_type'] == 'weapon':
                    # Get item details if available
                    item_name = "Unknown Item"
                    item_stat = "?"
                    if record['item_id']:
                        item = await self.bot.pool.fetchrow(
                            "SELECT * FROM allitems WHERE id = $1",
                            record['item_id']
                        )
                        if item:
                            item_name = item['name']
                            item_stat = str(item['damage'] + item['armor'])
                    
                    value = _(
                        "**Item:** {item_name} ({stat})\n"
                        "**Buyer:** {buyer}\n"
                        "**Price:** ${price}\n"
                        "**Date:** {date}"
                    ).format(
                        item_name=item_name,
                        stat=item_stat,
                        buyer=record['buyer_name'],
                        price=record['price'],
                        date=record['fulfilled_at'].strftime("%Y-%m-%d %H:%M UTC")
                    )
                else:  # crate
                    crate_emoji = await self.get_crate_emoji(record['crate_type'])
                    
                    value = _(
                        "**Crates:** {amount}x {emoji} {crate_type}\n"
                        "**Buyer:** {buyer}\n"
                        "**Price:** ${price}\n"
                        "**Date:** {date}"
                    ).format(
                        amount=record['crate_quantity'],
                        emoji=crate_emoji,
                        crate_type=record['crate_type'].title(),
                        buyer=record['buyer_name'],
                        price=record['price'],
                        date=record['fulfilled_at'].strftime("%Y-%m-%d %H:%M UTC")
                    )
                
                seller_embed.add_field(
                    name=_("Order #{id}").format(id=record['original_order_id']),
                    value=value,
                    inline=False
                )
        else:
            seller_embed.add_field(
                name=_("No History"),
                value=_("You haven't sold anything to buy orders yet."),
                inline=False
            )
        
        # Send embeds
        await ctx.send(embed=buyer_embed)
        await ctx.send(embed=seller_embed)
                
def setup(bot):
    bot.add_cog(BuyOrderFulfill(bot))
