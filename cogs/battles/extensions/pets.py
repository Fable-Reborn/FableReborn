# battles/extensions/pets.py
from ..core.combatant import Combatant
from decimal import Decimal

class PetExtension:
    """Extension for pet integration in battles"""
    
    async def get_pet_combatant(self, ctx, user, include_element=True):
        """Create a combatant object for a player's pet if they have one equipped"""
        if not user:
            return None
            
        async with ctx.bot.pool.acquire() as conn:
            # Check if user has an equipped pet
            pet = await conn.fetchrow(
                "SELECT * FROM monster_pets WHERE user_id = $1 AND equipped = TRUE;",
                user.id
            )
            
            if not pet:
                return None
                
            # Get pet's element
            pet_element = pet["element"].capitalize() if pet["element"] and include_element else "Unknown"
            
            # Get owner's stats
            owner_stats = await conn.fetchrow(
                "SELECT * FROM profile WHERE \"user\" = $1;",
                user.id
            )
                
            # Get owner's luck if available, or use default
            owner_luck = owner_stats["luck"] if owner_stats and "luck" in owner_stats else 0.6
            # Convert owner_luck to float to avoid decimal/float type mismatch
            owner_luck = float(owner_luck)
            
            # Apply the same luck calculation formula as the main character
            # Copy from the battle factory logic
            pet_luck = 20 if owner_luck <= 0.3 else ((owner_luck - 0.3) / (1.5 - 0.3)) * 80 + 20
            pet_luck = round(pet_luck, 2)
            pet_luck = min(pet_luck, 100.0)  # Cap at 100% like owner
            
            # Create pet combatant
            return Combatant(
                user=user,  # Reference to owner
                hp=float(pet["hp"]),
                max_hp=float(pet["hp"]),
                armor=float(pet["defense"]),
                damage=float(pet["attack"]),
                luck=pet_luck,  # Use owner's luck instead of fixed value
                element=pet_element,
                is_pet=True,
                owner=user,
                name=pet["name"],  # Changed from pet_name to name to ensure pet has correct name
                pet_id=pet["id"]
            )
    
    def apply_pet_bonuses(self, pet_combatant, owner_combatant):
        """Apply any special bonuses between pet and owner"""
        # Currently no extra bonuses, but can be added here
        return