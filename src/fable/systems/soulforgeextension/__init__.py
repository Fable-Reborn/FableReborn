import discord
from discord.ext import commands, tasks
import asyncio
import random
import datetime
from fable.systems.shard_communication import user_on_cooldown as user_cooldown

from fable.utils.checks import is_gm

class SoulforgeExtension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_soulforges.start()  # Background task to naturally degrade soulforges
    
    def cog_unload(self):
        self.check_soulforges.cancel()
    
    @tasks.loop(hours=24)
    async def check_soulforges(self):
        """Daily task to naturally degrade soulforge condition"""
        await self.bot.wait_until_ready()
        
        async with self.bot.pool.acquire() as conn:
            # Create columns if they don't exist
            
            # Natural degradation of soulforge condition (1% per day)
            await conn.execute("""
                UPDATE splicing_quest 
                SET forge_condition = GREATEST(0, forge_condition - 1)
                WHERE crucible_built = TRUE AND forge_condition > 0
            """)


    async def get_soulforge_data(self, user_id):
        """Get detailed data about a player's soulforge"""
        async with self.bot.pool.acquire() as conn:
            data = await conn.fetchrow("""
                SELECT sq.*, p.name, p.god, p.money
                FROM splicing_quest sq
                JOIN profile p ON sq.user_id = p.user
                WHERE sq.user_id = $1
            """, user_id)

            if data:
                return {
                    "quest_started": True,
                    "forge_built": data["crucible_built"],
                    "name": data["name"],
                    "god": data["god"],
                    "money": data["money"],
                    "condition": data.get("forge_condition", 100),
                    "divine_attention": data.get("divine_attention", 0),
                    "last_repair": data.get("last_repair_date"),
                    "last_ritual": data.get("last_ritual_date")
                }

            return None

    def create_status_bar(self, current, maximum, length=20, fill_char='█', empty_char='░'):
        """Create a visual bar representation"""
        ratio = current / maximum if maximum > 0 else 0
        ratio = max(0, min(1, ratio))  # Ensure ratio is between 0 and 1
        filled_length = int(length * ratio)
        bar = fill_char * filled_length + empty_char * (length - filled_length)
        return bar

    @commands.command()
    @user_cooldown(10)
    async def forgestatus(self, ctx):
        """View the status of your soulforge"""
        try:
            soulforge_data = await self.get_soulforge_data(ctx.author.id)

            if not soulforge_data or not soulforge_data["quest_started"]:
                return await ctx.send("You have not begun the Wyrdweaver's path. Use `$soulforge` to start your journey.")

            if not soulforge_data["forge_built"]:
                return await ctx.send(
                    "You have not yet constructed a Soulforge. Continue gathering the required materials.")

            # Get status values
            condition = soulforge_data["condition"]
            divine_attention = soulforge_data["divine_attention"]
            name = soulforge_data["name"]
            god = soulforge_data.get("god") or "no god"

            # Create status bars
            condition_bar = self.create_status_bar(condition, 100)
            attention_bar = self.create_status_bar(divine_attention, 100)

            # Generate descriptions based on status
            condition_desc = self.get_condition_description(condition)
            attention_desc = self.get_divine_attention_description(divine_attention, god)

            # Create embed
            embed = discord.Embed(
                title="🧪 Soulforge Status 🧪",
                description=f"*Morrigan circles your soulforge, her keen eyes assessing its state.*",
                color=0x4cc9f0
            )

            embed.add_field(
                name="Arcane Integrity",
                value=f"**{condition}%** [{condition_bar}]\n{condition_desc}",
                inline=False
            )

            embed.add_field(
                name="Divine Scrutiny",
                value=f"**{divine_attention}%** [{attention_bar}]\n{attention_desc}",
                inline=False
            )

            # Add maintenance options
            maintenance_text = []

            # Check if repair is needed and available
            if condition < 100:
                repair_cost = self.calculate_repair_cost(condition)
                maintenance_text.append(f"• `$repairforge` - Restore the forge's integrity ({repair_cost:,} gold)")

            # Check if ritual is needed and available
            if divine_attention > 0:
                # For Eidolith mask, we don't show gold cost but rather shard requirement
                maintenance_text.append(
                    f"• `$eidolithmask [shards]` - Create a masking fog to reduce divine scrutiny (requires Eidolith Shards)")

            if maintenance_text:
                embed.add_field(
                    name="Maintenance Options",
                    value="\n".join(maintenance_text),
                    inline=False
                )

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(e)

    def get_condition_description(self, condition):
        """Get description based on forge condition"""
        if condition > 90:
            return "*\"Your forge functions perfectly, its patterns in perfect harmony. The quicksilver basin gleams with pristine energy, ready to receive essence and shape it to your will.\"*"
        elif condition > 70:
            return "*\"Minor fluctuations in the binding matrices - nothing concerning, but I notice the quicksilver ripples slightly even at rest. There are small imperfections in the transformation algorithms.\"*"
        elif condition > 50:
            return "*\"The forge shows clear signs of wear. The flow of essence stutters occasionally, and the binding matrices flicker. You should consider repairs before attempting complex splices.\"*"
        elif condition > 30:
            return "*\"I am concerned about the forge's stability. The quicksilver seems sluggish, and the runes pulse erratically. Essence leakage is becoming visible around the rim. Splice at your own risk.\"*"
        elif condition > 10:
            return "*\"The forge teeters on the edge of failure! The binding matrices suffer frequent disruptions, and the crucible struggles to maintain coherent patterns. Splicing in this state is extremely dangerous.\"*"
        else:
            return "*\"Your forge is critically damaged! The quicksilver barely responds to commands, and the runes are nearly dark. Attempting to splice in this condition could have catastrophic consequences for both the creation and the creator.\"*"

    def get_divine_attention_description(self, attention, god):
        """Get description based on divine attention level and player's god"""
        if attention < 10:
            return "*\"The veil between realms remains thick - your work goes unnoticed by higher powers. The forge's activities register merely as background noise in the cosmic symphony.\"*"
        elif attention < 30:
            return "*\"Minor ripples in the divine awareness. Occasionally, the stars seem to focus their gaze here, but only briefly before turning to more interesting events.\"*"
        elif attention < 50:
            return "*\"The divine realms have taken note of your activities. Nothing concerning yet, but your manipulations of soul essence create distinct patterns that the gods may recognize.\"*"
        elif attention < 70:
            return "*\"I sense definite divine scrutiny. The boundary between realms thins when you work. You should proceed with caution and consider creating a masking fog to obscure your activities.\"*"
        elif attention < 90:
            base = "*\"The eyes of the gods are upon you! Your forge's energies penetrate multiple realms, and divine servants likely observe your work. Significant intervention may be imminent without protective measures.\"*"

            if "drakath" in god.lower() or "chaos" in god.lower():
                return base + " *\"Drakath's chaotic nature provides some protection, but even he has limits to what he'll permit.\"*"
            elif "asterea" in god.lower() or "light" in god.lower():
                return base + " *\"Asterea's gaze is particularly keen - she abhors manipulation of the soul's natural order.\"*"
            elif "sepulchure" in god.lower() or "dark" in god.lower():
                return base + " *\"Sepulchure watches with interest rather than immediate hostility, but his tolerance for rivals is notoriously thin.\"*"
            else:
                return base
        else:
            base = "*\"DIVINE INTERVENTION IS IMMINENT! The barrier between realms has worn perilously thin. I sense immortal presences gathering, drawn to the disturbance your forge creates. Act quickly to avert their wrath!\"*"

            if "drakath" in god.lower() or "chaos" in god.lower():
                return base + " *\"Even Drakath's chaotic nature cannot shield you from such blatant metaphysical disturbance. His curiosity battles with his jealousy of your power.\"*"
            elif "asterea" in god.lower() or "light" in god.lower():
                return base + " *\"Asterea prepares judgment - I see golden light gathering at the corners of reality. Her followers may soon be dispatched to investigate this 'corruption.'\"*"
            elif "sepulchure" in god.lower() or "dark" in god.lower():
                return base + " *\"Sepulchure's shadow stretches toward your forge. He may claim your work as tribute rather than destroy it, but neither outcome leaves the forge in your control.\"*"
            else:
                return base

    def calculate_repair_cost(self, current_condition):
        """Calculate the cost to repair the forge"""
        # The lower the condition, the higher the cost
        missing_condition = 100 - current_condition
        base_cost = 10000  # Base cost for minor repairs
        return base_cost + (missing_condition * missing_condition * 100)  # Exponential cost increase
    
    @commands.command()
    @user_cooldown(3600)
    async def repairforge(self, ctx):
        """Repair your soulforge to restore its condition"""
        # Get soulforge data
        soulforge_data = await self.get_soulforge_data(ctx.author.id)
        
        if not soulforge_data or not soulforge_data["forge_built"]:
            return await ctx.send("You don't have a Soulforge to repair.")
        
        current_condition = soulforge_data["condition"]
        
        if current_condition >= 100:
            return await ctx.send("*Morrigan tilts her head quizzically.* \"Your forge is already in perfect condition. There is nothing to repair.\"")
        
        # Calculate repair cost
        repair_cost = self.calculate_repair_cost(current_condition)
        player_money = soulforge_data["money"]
        
        if player_money < repair_cost:
            return await ctx.send(f"*\"The materials required for repairs cost {repair_cost:,} gold,\"* Morrigan explains. *\"You have only {player_money:,}. The forge's damage will worsen if left untended.\"*")
        
        # Ask for confirmation
        confirm_msg = f"Repairing your Soulforge will cost {repair_cost:,} gold. This will restore it to perfect condition. Proceed?"
        confirmed = await ctx.confirm(confirm_msg)
        
        if not confirmed:
            return await ctx.send("Repair canceled.")
        
        # Process the repair
        repair_amount = 100 - current_condition
        
        async with self.bot.pool.acquire() as conn:
            # Update forge condition and deduct gold
            await conn.execute("""
                UPDATE splicing_quest SET forge_condition = 100, last_repair_date = NOW()
                WHERE user_id = $1
            """, ctx.author.id)
            
            await conn.execute("""
                UPDATE profile SET money = money - $1
                WHERE "user" = $2
            """, repair_cost, ctx.author.id)
        
        # Success message with repair narrative
        embed = discord.Embed(
            title="🔧 Soulforge Repairs Complete 🔧",
            description=f"You spend {repair_cost:,} gold on rare materials needed to restore your Soulforge.",
            color=0x4cc9f0
        )
        
        # Different repair narratives based on how damaged it was
        if repair_amount > 50:
            narrative = f"*The repairs are extensive. You replace damaged binding matrices, reseal essence containment fields, and completely refresh the quicksilver in the central basin. Morrigan guides you through ancient maintenance rituals that weren't in the Primer, adjusting connections between dimensional anchor points with surgical precision.*\n\n*\"The damage was severe,\"* she notes as the forge begins to hum with renewed energy. *\"We've managed to restore the original configurations, but take better care in the future. Each time a forge is rebuilt, it loses some of the patterns imprinted by its original creators.\"*"
        elif repair_amount > 20:
            narrative = f"*You carefully realign the transformation matrices and replenish the depleted reagents with fresh materials. Several runes need to be recarved and energized, which Morrigan oversees with critical attention to detail.*\n\n*\"The damage was moderate but repairable,\"* she observes as the forge's light strengthens. *\"The essence flow stabilizes, and the quicksilver regains its perfect reflectivity. Your forge should now function at peak efficiency again.\"*"
        else:
            narrative = f"*The repairs are relatively minor - polishing worn surfaces, replacing spent catalysts, and recalibrating the essence flow regulators. Morrigan directs you to weak points in the binding patterns that needed reinforcement.*\n\n*\"Good as new,\"* she confirms as the forge's runes brighten to their original luster. *\"Regular maintenance is far easier than major repairs. Consider setting aside resources for upkeep - it's more economical in the long term.\"*"
        
        embed.add_field(name="Restoration Process", value=narrative, inline=False)
        
        await ctx.send(embed=embed)

    @commands.command(name="eshards", aliases=["myshards", "eidolith"])
    async def check_Eshards(self, ctx):
        """Check how many Eidolith Shards you have collected"""
        try:
            async with self.bot.pool.acquire() as conn:
                shard_count = await conn.fetchval("""
                    SELECT shards_collected
                    FROM splicing_quest
                    WHERE user_id = $1
                """, ctx.author.id)

                if shard_count is None:
                    await ctx.send(f"{ctx.author.mention}, you haven't collected any Eidolith Shards yet.")
                else:
                    await ctx.send(f"{ctx.author.mention}, you have **{shard_count}** Eidolith Shards collected.")
        except Exception as e:
            await ctx.send(e)
    @commands.command()
    @user_cooldown(21600)
    async def eidolithmask(self, ctx, shards: int = 1):
        """Use Eidolith Shards to create a masking fog that reduces divine scrutiny of your Soulforge"""
        # Check for valid soulforge
        soulforge_data = await self.get_soulforge_data(ctx.author.id)
        
        if not soulforge_data or not soulforge_data["forge_built"]:

            await self.bot.reset_cooldown(ctx)

            return await ctx.send("You don't have a Soulforge to protect.")
        
        divine_attention = soulforge_data["divine_attention"]
        god = soulforge_data["god"].lower() if soulforge_data["god"] is not None else ""

        
        if divine_attention <= 0:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send("*Morrigan shakes her head.* \"There is no divine scrutiny to divert at this time. The veil between realms remains thick around your forge.\"")
        
        # Check if the player has the required shards
        async with self.bot.pool.acquire() as conn:
            eidolith_count = await conn.fetchval("""
                SELECT shards_collected
                FROM splicing_quest
                WHERE user_id = $1
            """, ctx.author.id)
        
        # Validate shard count
        if eidolith_count < shards:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(f"*Morrigan gestures to your pouch.* \"You need at least {shards} Eidolith Shards for this ritual, but you only have {eidolith_count}. The essence contained within is essential to create the masking fog.\"")
        
        if shards < 1:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send("You must use at least 1 Eidolith Shard.")
        
        # Calculate reduction amount based on shards used
        # Each shard provides 8-12% reduction, with diminishing returns at higher divine attention
        base_reduction_per_shard = 5
        
        # Apply reduction factor based on current divine attention
        if divine_attention > 90:
            reduction_factor = 0.7  # 70% effectiveness at very high scrutiny
        elif divine_attention > 70:
            reduction_factor = 0.85  # 85% effectiveness at high scrutiny
        else:
            reduction_factor = 1.0  # 100% effectiveness at normal scrutiny
        
        # Calculate total reduction with some randomness
        total_reduction = 0
        for i in range(shards):
            # Each shard has slightly random effectiveness
            shard_reduction = random.randint(
                int(base_reduction_per_shard * 0.8 * reduction_factor),
                int(base_reduction_per_shard * 1.2 * reduction_factor)
            )
            total_reduction += shard_reduction
        
        # Cap the maximum possible reduction to prevent abuse
        max_possible_reduction = min(80, divine_attention)
        total_reduction = min(total_reduction, max_possible_reduction)
        
        final_attention = max(0, divine_attention - total_reduction)
        
        # Ask for confirmation
        confirm_msg = f"This ritual will consume {shards} Eidolith Shard{'s' if shards > 1 else ''} to create a divine masking fog. It could reduce divine scrutiny by approximately {total_reduction}%. Proceed?"
        confirmed = await ctx.confirm(confirm_msg)
        
        if not confirmed:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send("Ritual canceled.")
        
        # Process the ritual: remove shards and update divine attention
        async with self.bot.pool.acquire() as conn:
            # Get the IDs of the shards to remove
            await conn.execute("""
                UPDATE splicing_quest
                SET shards_collected = shards_collected - $2
                WHERE user_id = $1
            """, ctx.author.id, shards)
            
            # Update divine attention and set ritual date
            await conn.execute("""
                UPDATE splicing_quest SET divine_attention = $1, last_ritual_date = NOW()
                WHERE user_id = $2
            """, final_attention, ctx.author.id)
        
        # Success message with ritual narrative
        embed = discord.Embed(
            title="🌫️ Eidolith Masking Fog Ritual 🌫️",
            description=f"You utilize {shards} Eidolith Shard{'s' if shards > 1 else ''} to create a divine masking fog.",
            color=0x9d4edd
        )
        
        # Different ritual narratives based on divine affiliation
        if "drakath" in god or "chaos" in god:
            narrative = f"*Morrigan guides you to crush the Eidolith Shards into a fine powder. As you release the essence, it erupts into a swirling, chaotic fog that defies the natural laws of diffusion. The mist forms impossible patterns, constantly shifting between states of matter.*\n\n*\"The essence of primordial chaos contained in these shards confounds even divine perception,\"* Morrigan explains. *\"Each fragment contains a small piece of the world before the gods imposed order upon it. They cannot easily perceive what predates their own consciousness.\"*"
        elif "asterea" in god or "light" in god:
            narrative = f"*Under Morrigan's instruction, you dissolve the Eidolith Shards in sacred water. The solution transforms into a luminous mist that refracts light in impossible ways, creating miniature rainbows that bend back upon themselves.*\n\n*\"These shards contain the essence of pure light - the first radiance that existed before Asterea claimed dominion over illumination,\"* Morrigan explains. *\"Their primordial light confuses and dilutes the targeting of divine sight, much as staring at the sun blinds mortal eyes.\"*"
        elif "sepulchure" in god or "dark" in god:
            narrative = f"*Following Morrigan's guidance, you heat the Eidolith Shards until they sublimate directly from solid to gas, creating a dark mist that seems to absorb all light around it. The darkness feels ancient, predating the concept of shadow itself.*\n\n*\"These shards contain fragments of the void that existed before creation,\"* Morrigan whispers. *\"Even Sepulchure's vision cannot easily penetrate darkness this absolute - it is the absence that existed before he claimed dominion over shadow.\"*"
        else:
            narrative = f"*With Morrigan's instruction, you carefully release the essence contained within the Eidolith Shards. They dissolve into a shimmering mist that settles around your forge, bending reality slightly where it touches surfaces.*\n\n*\"The essence in these shards predates the gods themselves,\"* Morrigan explains. *\"It resonates on frequencies that divine perception was never designed to detect, creating a natural blind spot in their awareness.\"*"
        
        embed.add_field(name="The Ritual", value=narrative, inline=False)
        embed.add_field(name="Result", value=f"Divine Scrutiny reduced from {divine_attention}% to {final_attention}%", inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        """Listen for splice commands to update soulforge metrics"""
        if ctx.command and ctx.command.name == "splice" and hasattr(ctx, 'command_failed') and not ctx.command_failed:
            await self.update_soulforge_metrics(ctx.author.id)  # Default to common rarity

    async def update_soulforge_metrics(self, user_id):
        """Update soulforge condition and divine attention after a splice"""
        

        condition_reduction = random.rantint(4, 10)
        attention_increase = random.rantint(7, 17)
        
        async with self.bot.pool.acquire() as conn:
            
            # Update the values
            await conn.execute("""
                UPDATE splicing_quest 
                SET forge_condition = GREATEST(0, forge_condition - $1),
                    divine_attention = LEAST(100, divine_attention + $2)
                WHERE user_id = $3 AND crucible_built = TRUE
            """, condition_reduction, attention_increase, user_id)

async def setup(bot):
    await bot.add_cog(SoulforgeExtension(bot))
