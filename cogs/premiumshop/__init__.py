"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2023-2024 Lunar (PrototypeX37)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import datetime
import re
import discord

from discord.ext import commands

from utils.checks import has_char, is_gm
from utils.i18n import _, locale_doc
from classes.converters import IntGreaterThan
from cogs.shard_communication import user_on_cooldown as user_cooldown


class PremiumShop(commands.Cog):
    WEAPON_ELEMENTS = (
        "Light",
        "Dark",
        "Corrupted",
        "Fire",
        "Water",
        "Electric",
        "Nature",
        "Wind",
        "Earth",
    )
    PET_ELEMENTS = (
        "Light",
        "Dark",
        "Corrupted",
        "Fire",
        "Water",
        "Electric",
        "Nature",
        "Wind",
    )

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["dcshop"], brief=_("Show the premium shop"), hidden=True)
    @locale_doc
    async def dragoncoinshop(self, ctx):
        _(
            """Show the premium shop. For a detailed explanation of premium items, check `{prefix}help dragoncoinshop`."""
        )
        # Get user's Dragon Coins from database
        async with self.bot.pool.acquire() as conn:
            dragoncoins = await conn.fetchval(
                'SELECT dragoncoins FROM profile WHERE "user" = $1;',
                ctx.author.id
            )
        
        dragoncoins = dragoncoins or 0
        
        shopembed = discord.Embed(
            title=_("Dragon Coin Shop"),
            description=_(
                "Welcome to the Dragon Coin Shop!\n\n"
                "**Buy:** `{prefix}dragoncoinbuy <item> [amount]`\n"
                "**Currency:** <:dragoncoin:1404860657366728788> Dragon Coins\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ).format(prefix=ctx.clean_prefix),
            colour=discord.Colour.purple(),
        )
        
        shopembed.add_field(
            name=_("Your Dragon Coins"),
            value=_(f"**{dragoncoins}** <:dragoncoin:1404860657366728788>"),
            inline=False,
        )

        def chunk_paragraphs(paragraphs, limit=1024):
            chunks = []
            current = ""
            for paragraph in paragraphs:
                addition = paragraph if not current else f"\n\n{paragraph}"
                if len(current) + len(addition) > limit:
                    if current:
                        chunks.append(current)
                        current = paragraph
                    else:
                        # Fallback: hard-truncate impossible-long single paragraph.
                        chunks.append(paragraph[:limit])
                        current = ""
                else:
                    current += addition
            if current:
                chunks.append(current)
            return chunks

        item_paragraphs = [
            "<:ageup:1473265287238385797> **Pet Age Potion** - 200 <:dragoncoin:1404860657366728788> (`petage`)\n*Instantly age your pet to the next growth stage*",
            "<:finalpotion:1473265347581710346> **Pet Speed Growth Potion** - 300 <:dragoncoin:1404860657366728788> (`petspeed`)\n*Doubles growth speed for a specific pet*",
            "<:SplicePotion:1473266873612107836> **Pet XP Potion** - 1200 <:dragoncoin:1404860657366728788> (`petxp`)\n*Gives a pet permanent x2 pet-care XP multiplier*",
            "🧠 **Pet Mind Wipe** - 1500 <:dragoncoin:1404860657366728788> (`petmindwipe`)\n*Resets learned pet skills and refunds SP for one pet, selected pet IDs, or all pets you own*",
            "🔄 **Pet Element Scroll** - 2200 <:dragoncoin:1404860657366728788> (`petelement`)\n*Changes one pet's element, resets learned skills, and refunds SP. Cannot be used on god pets.*",
            "📜 **Weapon Element Scroll** - 800 <:dragoncoin:1404860657366728788> (`weapelement`)\n*Changes the element of one weapon in your inventory*",
            "<:F_Legendary:1139514868400132116> **Legendary Crate** - 500 <:dragoncoin:1404860657366728788> (`legendary`)\n*Contains items with stats ranging from 41 to 80, may also in rare cases contain dragon coins*",
            "<:f_divine:1169412814612471869> **Divine Crate** - 1000 <:dragoncoin:1404860657366728788> (`divine`)\n*Contains items with stats ranging from 47 to 100*",
            "<:c_mats:1403797590335819897> **Materials Crate** - 450 <:dragoncoin:1404860657366728788> (`materials`)\n*Contains 3-10 random crafting materials*",
            "*More items coming soon...*",
        ]
        item_chunks = chunk_paragraphs(item_paragraphs, limit=1024)
        for index, chunk in enumerate(item_chunks, start=1):
            if index == 1:
                field_name = _("Available Items")
            else:
                field_name = _("Available Items (Page {page})").format(page=index)
            shopembed.add_field(
                name=field_name,
                value=_(chunk),
                inline=False,
            )
        
        shopembed.set_footer(
            text=_("Premium Shop • Use {prefix}dcbuy to purchase").format(
                prefix=ctx.clean_prefix
            )
        )
        # Set thumbnail
        shopembed.set_thumbnail(url="https://i.ibb.co/27724pjY/Chat-GPT-Image-Jan-30-2026-11-06-50-PM-1.png")
        
        await ctx.send(embed=shopembed)



    @has_char()
    @commands.command(aliases=["dcbuy"], brief=_("Buy premium items"), hidden=True)
    @locale_doc
    async def dragoncoinbuy(self, ctx, item: str.lower, *, amount: IntGreaterThan(0) = 1):
        _(
            """`[amount]` - The amount of items to buy; defaults to 1
            `<item>` - The premium item to buy

            Buy one or more premium items from the shop."""
        )
        
        # Get user's Dragon Coins
        async with self.bot.pool.acquire() as conn:
            dragoncoins = await conn.fetchval(
                'SELECT dragoncoins FROM profile WHERE "user" = $1;',
                ctx.author.id
            )
        
        dragoncoins = dragoncoins or 0
        
        # Define available items and their prices with both long and short names
        items = {
            # Short names
            "petage": {"name": "Pet Age Potion", "price": 200, "description": "Instantly age your pet", "short": "petage"},
            "petspeed": {"name": "Pet Speed Growth Potion", "price": 300, "description": "Doubles growth speed for a specific pet", "short": "petspeed"},
            "petxp": {"name": "Pet XP Potion", "price": 1200, "description": "Gives a pet permanent x2 pet-care XP multiplier", "short": "petxp"},
            "petmindwipe": {"name": "Pet Mind Wipe", "price": 1500, "description": "Resets learned pet skills and refunds pet SP", "short": "petmindwipe"},
            "mindwipe": {"name": "Pet Mind Wipe", "price": 1500, "description": "Resets learned pet skills and refunds pet SP", "short": "petmindwipe"},
            "petelement": {"name": "Pet Element Scroll", "price": 2200, "description": "Changes one pet's element and resets pet skills", "short": "petelement"},
            "petelementscroll": {"name": "Pet Element Scroll", "price": 2200, "description": "Changes one pet's element and resets pet skills", "short": "petelement"},
            "weapelement": {"name": "Weapon Element Scroll", "price": 800, "description": "Changes the element of one weapon", "short": "weapelement"},
            "elementscroll": {"name": "Weapon Element Scroll", "price": 800, "description": "Changes the element of one weapon", "short": "weapelement"},
            "legendary": {"name": "Legendary Crate", "price": 500, "description": "Contains items with stats 41-80, may also in rare cases contain dragon coins", "short": "legendary"},
            "divine": {"name": "Divine Crate", "price": 1000, "description": "Contains items with stats 47-100, may also in rare cases contain dragon coins", "short": "divine"},
            "materials": {"name": "Materials Crate", "price": 450, "description": "Contains 3-10 random crafting materials", "short": "materials"},
            # Long names
            "pet age potion": {"name": "Pet Age Potion", "price": 200, "description": "Instantly age your pet", "short": "petage"},
            "pet speed growth potion": {"name": "Pet Speed Growth Potion", "price": 300, "description": "Doubles growth speed for a specific pet", "short": "petspeed"},
            "pet xp potion": {"name": "Pet XP Potion", "price": 1200, "description": "Gives a pet permanent x2 pet-care XP multiplier", "short": "petxp"},
            "pet mind wipe": {"name": "Pet Mind Wipe", "price": 1500, "description": "Resets learned pet skills and refunds pet SP", "short": "petmindwipe"},
            "pet element scroll": {"name": "Pet Element Scroll", "price": 2200, "description": "Changes one pet's element and resets pet skills", "short": "petelement"},
            "pet element change": {"name": "Pet Element Scroll", "price": 2200, "description": "Changes one pet's element and resets pet skills", "short": "petelement"},
            "weapon element scroll": {"name": "Weapon Element Scroll", "price": 800, "description": "Changes the element of one weapon", "short": "weapelement"},
            "legendary crate": {"name": "Legendary Crate", "price": 500, "description": "Contains items with stats 41-80, may also in rare cases contain dragon coins", "short": "legendary"},
            "divine crate": {"name": "Divine Crate", "price": 1000, "description": "Contains items with stats 47-100, may also in rare cases contain dragon coins", "short": "divine"},
            "materials crate": {"name": "Materials Crate", "price": 450, "description": "Contains 3-10 random crafting materials", "short": "materials"}
        }
        
        # Normalize the item input (lowercase and remove extra spaces)
        normalized_item = " ".join(item.lower().split())

        if normalized_item not in items:
            return await ctx.send(_("Invalid item. Available items: petage/pet age potion, petspeed/pet speed growth potion, petxp/pet xp potion, petmindwipe/pet mind wipe, petelement/pet element scroll, weapelement/weapon element scroll, legendary/legendary crate, divine/divine crate, materials/materials crate"))
        
        # Get the short name for processing
        item_data = items[normalized_item]
        item = item_data["short"]
        
        item_data = items[item]
        total_cost = item_data["price"] * amount
        
        if dragoncoins < total_cost:
            return await ctx.send(_("You don't have enough Dragon Coins. You need {cost} but have {current}.").format(
                cost=total_cost, current=dragoncoins
            ))
        
        # Deduct Dragon Coins and add item to inventory
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET dragoncoins = dragoncoins - $1 WHERE "user" = $2;',
                total_cost, ctx.author.id
            )
            
            # Handle different item types
            if item in ["petage", "petspeed", "petxp", "petmindwipe", "petelement", "weapelement"]:
                # Add consumables to user_consumables table
                if item == "petage":
                    consumable_type = 'pet_age_potion'
                elif item == "petspeed":
                    consumable_type = 'pet_speed_growth_potion'
                elif item == "petxp":
                    consumable_type = 'pet_xp_potion'
                elif item == "petmindwipe":
                    consumable_type = 'pet_mind_wipe'
                elif item == "petelement":
                    consumable_type = 'pet_element_scroll'
                elif item == "weapelement":
                    consumable_type = 'weapon_element_scroll'
                else:
                    return await ctx.send(_("Unknown item type."))
                
                # Check if user already has this consumable
                existing = await conn.fetchrow(
                    'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                    ctx.author.id, consumable_type
                )
                
                if existing:
                    # Update existing record
                    await conn.execute(
                        'UPDATE user_consumables SET quantity = quantity + $1 WHERE id = $2;',
                        amount, existing['id']
                    )
                else:
                    # Create new record
                    await conn.execute(
                        'INSERT INTO user_consumables (user_id, consumable_type, quantity) VALUES ($1, $2, $3);',
                        ctx.author.id, consumable_type, amount
                    )
            elif item in ["legendary", "divine", "materials"]:
                # Add crates directly to profile table
                crate_column = f"crates_{item}"
                await conn.execute(
                    f'UPDATE profile SET "{crate_column}" = "{crate_column}" + $1 WHERE "user" = $2;',
                    amount, ctx.author.id
                )
            else:
                return await ctx.send(_("Unknown item type."))
        
        await ctx.send(_("Successfully purchased **{amount}x {item_name}** for **{cost} <:dragoncoin:1398714322372395008>**!").format(
            amount=amount, item_name=item_data["name"], cost=total_cost
        ))


    # ========================================
    # PET CONSUMABLES SECTION
    # ========================================

    def _parse_pet_mind_wipe_targets(self, raw_target_spec: str):
        normalized = " ".join(str(raw_target_spec or "").replace("，", ",").split())
        if not normalized:
            return None, _("Please provide `all`, a pet ID, or a comma-separated list of pet IDs.")

        if normalized.lower() == "all":
            return {"mode": "all", "ids": []}, None

        tokens = [token for token in re.split(r"[\s,]+", normalized) if token]
        if not tokens:
            return None, _("Please provide `all`, a pet ID, or a comma-separated list of pet IDs.")
        if any(token.lower() == "all" for token in tokens):
            return None, _("Use either `all` or specific pet IDs, not both together.")

        pet_ids = []
        seen = set()
        for token in tokens:
            if not token.isdigit():
                return None, _("Pet Mind Wipe targets must be `all` or numeric pet IDs separated by commas/spaces.")
            pet_id = int(token)
            if pet_id <= 0:
                return None, _("Pet IDs must be positive numbers.")
            if pet_id in seen:
                continue
            seen.add(pet_id)
            pet_ids.append(pet_id)

        if not pet_ids:
            return None, _("Please provide at least one valid pet ID.")

        return {"mode": "ids", "ids": pet_ids}, None

    def _normalize_pet_element(self, raw_element: str):
        if not raw_element:
            return None
        normalized = str(raw_element).strip().lower()
        aliases = {
            "corruption": "Corrupted",
            "corrupted": "Corrupted",
            "light": "Light",
            "dark": "Dark",
            "fire": "Fire",
            "water": "Water",
            "electric": "Electric",
            "electricity": "Electric",
            "lightning": "Electric",
            "nature": "Nature",
            "wind": "Wind",
        }
        candidate = aliases.get(normalized)
        if not candidate:
            return None
        return candidate if candidate in self.PET_ELEMENTS else None

    def _canonical_god_pet_name(self, raw_name: str):
        if not raw_name:
            return None

        cleaned = " ".join(
            re.sub(r"\[[^\]]+\]", "", str(raw_name).replace("_", " ").replace("-", " ")).lower().split()
        )
        if cleaned.startswith("ultra "):
            cleaned = cleaned[6:].strip()

        elysia_aliases = {"elysia", "astraea", "asterea"}
        if cleaned in elysia_aliases:
            return "Elysia"
        if cleaned == "sepulchure":
            return "Sepulchure"
        if cleaned == "drakath":
            return "Drakath"
        return None

    def _calculate_pet_skill_reset(self, pets_cog, pet):
        learned_skills = pets_cog.normalize_learned_skills(pet.get("learned_skills"))
        spent_skill_points, unknown_count = pets_cog.estimate_spent_skill_points(
            str(pet.get("element") or ""),
            pet.get("learned_skills"),
        )

        current_skill_points = max(0, int(pet.get("skill_points") or 0))
        pet_level = max(1, int(pet.get("level") or 1))
        earned_skill_points = pet_level // pets_cog.PET_SKILL_POINT_INTERVAL
        rebuilt_skill_points = max(
            int(earned_skill_points),
            int(current_skill_points + spent_skill_points),
        )
        refunded_delta = max(0, int(rebuilt_skill_points - current_skill_points))

        return {
            "learned_skills": learned_skills,
            "spent_skill_points": int(spent_skill_points),
            "unknown_count": int(unknown_count),
            "current_skill_points": current_skill_points,
            "rebuilt_skill_points": int(rebuilt_skill_points),
            "refunded_delta": int(refunded_delta),
        }
    
    async def consume_pet_age_potion(self, ctx, pet_id: int):
        """
        Function to handle pet age potion consumption.
        Called by the consume command in profile cog.
        """
        # Check if user has the potion
        async with self.bot.pool.acquire() as conn:
            potion = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id, 'pet_age_potion'
            )
            
            if not potion or potion['quantity'] < 1:
                return False, _("You don't have any Pet Age Potions.")
            
            # Check if pet exists and belongs to user
            pet = await conn.fetchrow(
                "SELECT * FROM monster_pets WHERE id = $1 AND user_id = $2",
                pet_id, ctx.author.id
            )
            
            if not pet:
                return False, _("Pet not found or doesn't belong to you.")
            
            # Check if pet is already adult
            if pet["growth_stage"] == "adult":
                return False, _("This pet is already fully grown!")
            
            # Define growth stages (same as in pets cog)
            growth_stages = {
                1: {"stage": "baby", "growth_time": 2, "stat_multiplier": 0.25, "hunger_modifier": 1.0},
                2: {"stage": "juvenile", "growth_time": 2, "stat_multiplier": 0.50, "hunger_modifier": 0.8},
                3: {"stage": "young", "growth_time": 1, "stat_multiplier": 0.75, "hunger_modifier": 0.6},
                4: {"stage": "adult", "growth_time": None, "stat_multiplier": 1.0, "hunger_modifier": 0.0},
            }
            
            current_index = pet["growth_index"]
            next_stage_index = current_index + 1
            
            if next_stage_index not in growth_stages:
                return False, _("Pet cannot grow further.")
            
            stage_data = growth_stages[next_stage_index]
            
            # Calculate new stats based on multiplier ratio
            old_multiplier = growth_stages[current_index]["stat_multiplier"]
            new_multiplier = stage_data["stat_multiplier"]
            multiplier_ratio = new_multiplier / old_multiplier
            
            new_hp = pet["hp"] * multiplier_ratio
            new_attack = pet["attack"] * multiplier_ratio
            new_defense = pet["defense"] * multiplier_ratio
            
            # Calculate new growth time if not adult
            if stage_data["growth_time"] is not None:
                import datetime
                growth_time_interval = datetime.timedelta(days=stage_data["growth_time"])
                new_growth_time = datetime.datetime.utcnow() + growth_time_interval
            else:
                new_growth_time = None
            
            # Update the pet
            if new_growth_time is not None:
                await conn.execute(
                    """
                    UPDATE monster_pets
                    SET 
                        growth_stage = $1,
                        growth_time = $2,
                        hp = $3,
                        attack = $4,
                        defense = $5,
                        growth_index = $6
                    WHERE 
                        "id" = $7
                    """,
                    stage_data["stage"],
                    new_growth_time,
                    new_hp,
                    new_attack,
                    new_defense,
                    next_stage_index,
                    pet_id,
                )
            else:
                await conn.execute(
                    """
                    UPDATE monster_pets
                    SET 
                        growth_stage = $1,
                        growth_time = NULL,
                        hp = $2,
                        attack = $3,
                        defense = $4,
                        growth_index = $5
                    WHERE 
                        "id" = $6
                    """,
                    stage_data["stage"],
                    new_hp,
                    new_attack,
                    new_defense,
                    next_stage_index,
                    pet_id,
                )
            
            # Consume one potion
            await conn.execute(
                'UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;',
                potion['id']
            )
            
            # Return success with message
            success_message = (
                f"**{pet['name']}** has grown into a **{stage_data['stage'].capitalize()}**!\n\n"
                f"**New Stats:**\n"
                f"• HP: {round(new_hp)}\n"
                f"• Attack: {round(new_attack)}\n"
                f"• Defense: {round(new_defense)}"
            )
            
            return True, success_message

    async def consume_pet_xp_potion(self, ctx, pet_id: int):
        """
        Function to handle pet XP potion consumption.
        Called by the consume command in profile cog.
        """
        # Check if user has the potion
        async with self.bot.pool.acquire() as conn:
            potion = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id, 'pet_xp_potion'
            )
            
            if not potion or potion['quantity'] < 1:
                return False, _("You don't have any Pet XP Potions.")
            
            # Check if pet exists and belongs to user
            pet = await conn.fetchrow(
                "SELECT * FROM monster_pets WHERE id = $1 AND user_id = $2",
                pet_id, ctx.author.id
            )
            
            if not pet:
                return False, _("Pet not found or doesn't belong to you.")
            
            # Check if pet already has XP multiplier
            if pet.get('xp_multiplier', 1.0) > 1.0:
                return False, _("This pet already has an XP multiplier active!")
            
            # Consume one potion
            await conn.execute(
                'UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;',
                potion['id']
            )
            
            # Apply x2 XP multiplier to the pet permanently
            await conn.execute(
                'UPDATE monster_pets SET xp_multiplier = 2.0 WHERE id = $1;',
                pet_id
            )
        
        success_message = (
            f"🔮 **Pet XP Potion consumed!**\n\n"
            f"**{pet['name']}** now has **x2 XP permanently!**\n"
            f"This pet will gain double XP from pet care activities (feed/play/treat/train)."
        )
        
        return True, success_message

    async def consume_pet_speed_growth_potion(self, ctx, pet_id: int):
        """
        Function to handle pet speed growth potion consumption.
        Called by the consume command in profile cog.
        """
        # Check if user has the potion
        async with self.bot.pool.acquire() as conn:
            potion = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id, 'pet_speed_growth_potion'
            )
            
            if not potion or potion['quantity'] < 1:
                return False, _("You don't have any Pet Speed Growth Potions.")
            
            # Check if pet exists and belongs to user
            pet = await conn.fetchrow(
                "SELECT * FROM monster_pets WHERE id = $1 AND user_id = $2",
                pet_id, ctx.author.id
            )
            
            if not pet:
                return False, _("Pet not found or doesn't belong to you.")
            
            # Check if pet is already adult (can't apply speed boost to adult pets)
            if pet['growth_stage'] == 'adult':
                return False, _("This pet is already an adult and cannot grow further.")
            
            # Consume one potion
            await conn.execute(
                'UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;',
                potion['id']
            )
            
            # Apply speed growth effect to the pet and recalculate current growth time
            if pet['growth_time'] is not None:
                # Calculate remaining time and cut it in half
                remaining_time = pet['growth_time'] - datetime.datetime.utcnow()
                if remaining_time.total_seconds() > 0:
                    # Cut remaining time in half
                    new_growth_time = datetime.datetime.utcnow() + (remaining_time / 2)
                    
                    await conn.execute(
                        'UPDATE monster_pets SET speed_growth_active = TRUE, growth_time = $1 WHERE id = $2;',
                        new_growth_time, pet_id
                    )
                else:
                    # Pet is already ready to grow, just set the flag
                    await conn.execute(
                        'UPDATE monster_pets SET speed_growth_active = TRUE WHERE id = $1;',
                        pet_id
                    )
            else:
                # Pet has no growth time (shouldn't happen for non-adult pets)
                await conn.execute(
                    'UPDATE monster_pets SET speed_growth_active = TRUE WHERE id = $1;',
                    pet_id
                )
        
        success_message = (
            f"<:finalpotion:1398721503268438169> **Pet Speed Growth Potion consumed!**\n\n"
            f"**{pet['name']}** will now grow **2x faster** starting immediately!\n"
            f"Current stage: **{pet['growth_stage'].capitalize()}** - Growth time cut in half!"
        )
        
        return True, success_message

    async def consume_pet_mind_wipe(self, ctx, target_spec: str):
        """
        Reset pet skills and refund skill points for one pet, selected pets, or all owned pets.
        Called by the consume command in profile cog.
        """
        parsed_targets, parse_error = self._parse_pet_mind_wipe_targets(target_spec)
        if parse_error:
            return False, parse_error

        pets_cog = self.bot.get_cog("Pets")
        if pets_cog is None:
            return False, _("Pet system is not available right now.")

        async with self.bot.pool.acquire() as conn:
            wipe_item = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id,
                'pet_mind_wipe',
            )
            if not wipe_item or wipe_item['quantity'] < 1:
                return False, _("You don't have any Pet Mind Wipes.")

            if parsed_targets["mode"] == "all":
                pets = await conn.fetch(
                    """
                    SELECT id, name, level, element, skill_points, learned_skills
                    FROM monster_pets
                    WHERE user_id = $1
                    ORDER BY id;
                    """,
                    ctx.author.id,
                )
            else:
                pets = await conn.fetch(
                    """
                    SELECT id, name, level, element, skill_points, learned_skills
                    FROM monster_pets
                    WHERE user_id = $1 AND id = ANY($2::bigint[])
                    ORDER BY id;
                    """,
                    ctx.author.id,
                    parsed_targets["ids"],
                )

            if not pets:
                return False, _("No matching pets were found for this Pet Mind Wipe.")

            if parsed_targets["mode"] == "ids":
                found_ids = {int(pet["id"]) for pet in pets}
                missing_ids = [str(pid) for pid in parsed_targets["ids"] if pid not in found_ids]
                if missing_ids:
                    return False, _("These pet IDs were not found in your stable: {ids}").format(
                        ids=", ".join(missing_ids)
                    )

            updates = []
            refunded_total = 0
            affected_count = 0
            skipped_count = 0
            unknown_skill_entries = 0
            summary_lines = []

            for pet in pets:
                reset_data = self._calculate_pet_skill_reset(pets_cog, pet)
                unknown_skill_entries += reset_data["unknown_count"]

                if not reset_data["learned_skills"] and reset_data["unknown_count"] <= 0:
                    skipped_count += 1
                    continue

                updates.append((reset_data["rebuilt_skill_points"], int(pet["id"])))
                refunded_total += reset_data["refunded_delta"]
                affected_count += 1
                summary_lines.append(
                    f"• **{pet['name']}** (`{pet['id']}`): +{reset_data['refunded_delta']} SP -> **{reset_data['rebuilt_skill_points']} SP**"
                )

            if not updates:
                return False, _("None of the selected pets currently have learned skills to wipe.")

            async with conn.transaction():
                await conn.executemany(
                    """
                    UPDATE monster_pets
                    SET learned_skills = '[]'::jsonb, skill_tree_progress = '{}'::jsonb, skill_points = $1
                    WHERE id = $2;
                    """,
                    updates,
                )
                await conn.execute(
                    'UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;',
                    wipe_item['id'],
                )

        if len(summary_lines) > 10:
            summary_lines = summary_lines[:10] + [f"• ... and {affected_count - 10} more pets"]

        success_message = (
            f"🧠 **Pet Mind Wipe consumed!**\n\n"
            f"Reset **{affected_count}** pet(s) and refunded **{refunded_total} SP** total.\n"
            f"Skipped **{skipped_count}** pet(s) with no learned skills.\n"
            + ("\n".join(summary_lines))
        )
        if unknown_skill_entries > 0:
            success_message += (
                f"\n\nRecovered around **{unknown_skill_entries}** legacy/unknown skill entries while rebuilding SP."
            )

        return True, success_message

    async def consume_pet_element_scroll(self, ctx, pet_id: int, new_element: str):
        """
        Change a pet's element, wipe learned skills, and refund SP for a single owned pet.
        Cannot be used on god pets.
        """
        desired_element = self._normalize_pet_element(new_element)
        if not desired_element:
            valid = ", ".join(self.PET_ELEMENTS)
            return False, _(f"Invalid pet element. Valid elements: {valid}")

        pets_cog = self.bot.get_cog("Pets")
        if pets_cog is None:
            return False, _("Pet system is not available right now.")

        async with self.bot.pool.acquire() as conn:
            scroll = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id,
                'pet_element_scroll',
            )
            if not scroll or scroll['quantity'] < 1:
                return False, _("You don't have any Pet Element Scrolls.")

            pet = await conn.fetchrow(
                """
                SELECT id, name, default_name, level, element, skill_points, learned_skills
                FROM monster_pets
                WHERE id = $1 AND user_id = $2;
                """,
                pet_id,
                ctx.author.id,
            )
            if not pet:
                return False, _("Pet not found or doesn't belong to you.")

            canonical_god_name = self._canonical_god_pet_name(
                pet.get("default_name") or pet.get("name")
            )
            if canonical_god_name:
                return False, _(
                    "Pet Element Scroll cannot be used on god pets like {name}."
                ).format(name=canonical_god_name)

            current_element = self._normalize_pet_element(str(pet.get("element") or ""))
            if current_element == desired_element:
                return False, _("That pet already has this element.")

            reset_data = self._calculate_pet_skill_reset(pets_cog, pet)

            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE monster_pets
                    SET element = $1,
                        learned_skills = '[]'::jsonb,
                        skill_tree_progress = '{}'::jsonb,
                        skill_points = $2
                    WHERE id = $3;
                    """,
                    desired_element,
                    reset_data["rebuilt_skill_points"],
                    pet_id,
                )
                await conn.execute(
                    'UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;',
                    scroll['id'],
                )

        source_element = current_element or str(pet.get("element") or "Unknown")
        success_message = _(
            f"🔄 **Pet Element Scroll consumed!**\n\n"
            f"**{pet['name']}** (ID: `{pet['id']}`) changed from **{source_element}** to **{desired_element}**.\n"
            f"Learned pet skills were wiped and **+{reset_data['refunded_delta']} SP** was refunded."
            f" New total: **{reset_data['rebuilt_skill_points']} SP**."
        )
        if reset_data["unknown_count"] > 0:
            success_message += _(
                f"\nRecovered around **{reset_data['unknown_count']}** legacy/unknown skill entries while rebuilding SP."
            )

        return True, success_message

    @user_cooldown(2764800)  # 32 days cooldown
    @has_char()
    @commands.command(hidden=True, brief=_("Redeem dragon coins based on your tier"))
    @locale_doc
    async def redeemdc(self, ctx):
        _(
            """Redeem dragon coins based on your tier level.
            
            **Tier Rewards:**
            • Tier 1: 350 <:dragoncoin:1398714322372395008>
            • Tier 2: 800 <:dragoncoin:1398714322372395008>
            • Tier 3: 1600 <:dragoncoin:1398714322372395008>
            • Tier 4: 3500 <:dragoncoin:1398714322372395008>
            """
        )
        
        # Get user's tier and current dragon coins
        async with self.bot.pool.acquire() as conn:
            profile = await conn.fetchrow(
                'SELECT tier, dragoncoins FROM profile WHERE "user" = $1;',
                ctx.author.id
            )
            
            if not profile:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You don't have a character profile."))
            
            tier = profile['tier'] or 0
            current_dragoncoins = profile['dragoncoins'] or 0
        
        # Define tier rewards
        tier_rewards = {
            1: 350,
            2: 800,
            3: 1600,
            4: 3500
        }
        
        if tier not in tier_rewards:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You need to be at least Tier 1 to redeem dragon coins."))
        
        coins_to_add = tier_rewards[tier]
        new_total = current_dragoncoins + coins_to_add
        
        # Update dragon coins in database
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET dragoncoins = $1 WHERE "user" = $2;',
                new_total, ctx.author.id
            )
        
        # Create success embed
        embed = discord.Embed(
            title=_("🎉 Dragon Coins Redeemed!"),
            description=_(
                "You have successfully redeemed your tier rewards!\n\n"
                "**Tier {tier} Reward:** +{coins} <:dragoncoin:1398714322372395008>\n"
                "**Previous Balance:** {previous} <:dragoncoin:1398714322372395008>\n"
                "**New Balance:** {new} <:dragoncoin:1398714322372395008>"
            ).format(
                tier=tier,
                coins=coins_to_add,
                previous=current_dragoncoins,
                new=new_total
            ),
            colour=discord.Colour.gold(),
            timestamp=datetime.datetime.utcnow()
        )
        
        embed.set_footer(text=_("Use {prefix}dragoncoinshop to view the shop").format(prefix=ctx.clean_prefix))
        
        await ctx.send(embed=embed)

    @has_char()
    @commands.command(hidden=True, brief=_("Show tier rewards information"))
    @locale_doc
    async def tierrewards(self, ctx):
        _(
            """Show information about tier rewards and dragon coin redemption.
            
            **Tier Rewards:**
            • Tier 1: 300 <:dragoncoin:1398714322372395008>
            • Tier 2: 700 <:dragoncoin:1398714322372395008>
            • Tier 3: 1300 <:dragoncoin:1398714322372395008>
            • Tier 4: 3000 <:dragoncoin:1398714322372395008>
            """
        )
        
        # Get user's current tier
        async with self.bot.pool.acquire() as conn:
            tier = await conn.fetchval(
                'SELECT tier FROM profile WHERE "user" = $1;',
                ctx.author.id
            )
        
        tier = tier or 0
        
        embed = discord.Embed(
            title=_("🏆 Tier Rewards Information"),
            description=_(
                "Redeem dragon coins based on your tier level!\n\n"
                "**Available Rewards:**\n"
                "• **Tier 1:** 300 <:dragoncoin:1398714322372395008>\n"
                "• **Tier 2:** 700 <:dragoncoin:1398714322372395008>\n"
                "• **Tier 3:** 1300 <:dragoncoin:1398714322372395008>\n"
                "• **Tier 4:** 3000 <:dragoncoin:1398714322372395008>\n\n"
                "**Your Current Tier:** {tier}\n"
                "**Command:** `{prefix}redeemcoins`\n"
                "**Cooldown:** 32 days"
            ).format(tier=tier, prefix=ctx.clean_prefix),
            colour=discord.Colour.gold(),
            timestamp=datetime.datetime.utcnow()
        )
        
        embed.set_footer(text=_("Use {prefix}redeemcoins to claim your rewards").format(prefix=ctx.clean_prefix))
        embed.set_thumbnail(url=f"{self.bot.BASE_URL}/business.png")
        
        await ctx.send(embed=embed)

    async def open_materials_crate(self, ctx, return_details: bool = False):
        """
        Function to handle materials crate opening.
        Called by the open command in crates cog.
        """
        # Check if user has materials crates
        async with self.bot.pool.acquire() as conn:         
            # Get amuletcrafting cog to access resource generation
            amulet_cog = self.bot.get_cog('AmuletCrafting')
            if not amulet_cog:
                if return_details:
                    return False, "AmuletCrafting system not available.", []
                return False, "AmuletCrafting system not available."
            
            # Generate 3-10 random materials
            import random
            material_count = random.randint(3, 10)
            
            # Get random materials using the amuletcrafting system
            materials_gained = []
            for _ in range(material_count):
                resource = amulet_cog.get_random_resource()
                if resource:
                    # Give the material to the user
                    await amulet_cog.give_crafting_resource(ctx.author.id, resource, 1)
                    materials_gained.append(resource)
            
        material_count = len(materials_gained)
        materials_display = [resource.replace('_', ' ').title() for resource in materials_gained]
        
        success_message = (
            f"<:c_mats:1398983405516882002> **Materials Crate opened!**\n\n"
            f"You found **{material_count}** crafting materials:\n"
            f"• {', '.join(materials_display)}"
        )

        if return_details:
            return True, success_message, materials_gained
        return True, success_message

    def _normalize_weapon_element(self, raw_element: str):
        if not raw_element:
            return None
        normalized = str(raw_element).strip().lower()
        aliases = {
            "corruption": "Corrupted",
            "corrupted": "Corrupted",
            "light": "Light",
            "dark": "Dark",
            "fire": "Fire",
            "water": "Water",
            "electric": "Electric",
            "electricity": "Electric",
            "nature": "Nature",
            "wind": "Wind",
            "earth": "Earth",
        }
        candidate = aliases.get(normalized)
        if not candidate:
            return None
        return candidate if candidate in self.WEAPON_ELEMENTS else None

    async def consume_weapon_element_scroll(self, ctx, item_id: int, new_element: str):
        """
        Function to handle weapon element scroll consumption.
        Called by the consume command in profile cog.
        """
        desired_element = self._normalize_weapon_element(new_element)
        if not desired_element:
            valid = ", ".join(self.WEAPON_ELEMENTS)
            return False, _(f"Invalid element. Valid elements: {valid}")

        async with self.bot.pool.acquire() as conn:
            scroll = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                ctx.author.id,
                'weapon_element_scroll'
            )
            if not scroll or scroll['quantity'] < 1:
                return False, _("You don't have any Weapon Element Scrolls.")

            weapon = await conn.fetchrow(
                'SELECT id, name, type, element FROM allitems WHERE id = $1 AND owner = $2;',
                item_id,
                ctx.author.id
            )
            if not weapon:
                return False, _("Weapon not found or doesn't belong to you.")
            if str(weapon["type"]).lower() == "shield":
                return False, _("That item is a shield. Weapon Element Scroll can only be used on weapons.")

            current_element = (weapon["element"] or "Unknown").capitalize()
            if current_element == desired_element:
                return False, _("That weapon already has this element.")

            async with conn.transaction():
                await conn.execute(
                    'UPDATE user_consumables SET quantity = quantity - 1 WHERE id = $1;',
                    scroll['id']
                )
                await conn.execute(
                    'UPDATE allitems SET element = $1 WHERE id = $2;',
                    desired_element,
                    item_id
                )

        success_message = _(
            f"📜 **Weapon Element Scroll consumed!**\n\n"
            f"**{weapon['name']}** (ID: `{weapon['id']}`) changed from **{current_element}** to **{desired_element}**."
        )
        return True, success_message


async def setup(bot):
    await bot.add_cog(PremiumShop(bot)) 
