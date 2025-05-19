# battles/extensions/elements.py

# Debug storage
class DebugInfo:
    logs = []
    
    @classmethod
    def log(cls, message):
        cls.logs.append(f"{len(cls.logs) + 1}. {message}")
        # Keep only the last 100 messages
        cls.logs = cls.logs[-100:]

class ElementExtension:
    """Extension for element-based effects"""
    
    # Element strength relationships
    element_strengths = {
        "Light": "Corrupted",
        "Dark": "Light",
        "Corrupted": "Dark",
        "Nature": "Electric",
        "Electric": "Water",
        "Water": "Fire",
        "Fire": "Nature",
        "Wind": "Electric",
        "Unknown": None
    }
    
    # Element to emoji mapping
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
        "Unknown": "❓"
    }
    
    async def get_player_element(self, ctx, user_id):
        """Get a user's primary element"""
        try:
            async with ctx.bot.pool.acquire() as conn:
                highest_items = await conn.fetch(
                    "SELECT ai.element FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN"
                    " inventory i ON (ai.id=i.item) WHERE i.equipped IS TRUE AND p.user=$1"
                    " ORDER BY GREATEST(ai.damage, ai.armor) DESC;",
                    user_id,
                )
                highest_element = highest_items[0]["element"].capitalize() if highest_items and highest_items[0]["element"] else "Unknown"
                return highest_element
        except Exception:
            return "Unknown"
    
    def _log_debug(self, message):
        """Helper method to store debug information"""
        DebugInfo.log(message)
    
    def calculate_damage_modifier(self, ctx_or_attacker_element, attacker_element=None, defender_element=None):
        """Calculate damage modifier based on element relationships
        
        Can be called as:
        - calculate_damage_modifier(attacker_element, defender_element)
        - calculate_damage_modifier(ctx, attacker_element, defender_element)
        """
        import random
        
        # Handle both calling conventions
        if attacker_element is None and defender_element is None:
            # Called with (attacker_element, defender_element)
            attacker_element = ctx_or_attacker_element
            defender_element = attacker_element
        else:
            # Called with (ctx, attacker_element, defender_element)
            attacker_element = attacker_element
            defender_element = defender_element
        
        # Test log to verify this method is being called
        self._log_debug(f"calculate_damage_modifier called with: {attacker_element} vs {defender_element}")
        
        # Ensure elements are properly capitalized to match the dictionary keys
        attacker_element = str(attacker_element).capitalize() if attacker_element else "Unknown"
        defender_element = str(defender_element).capitalize() if defender_element else "Unknown"
        
        # Debug logging
        self._log_debug(f"Element check - Attacker: {attacker_element} ({type(attacker_element)}), "
                      f"Defender: {defender_element} ({type(defender_element)})")
        self._log_debug(f"Attacker element type: {type(attacker_element)}")
        self._log_debug(f"Element strengths: {self.element_strengths}")
        self._log_debug(f"Attacker in strengths: {attacker_element in self.element_strengths}")
        if attacker_element in self.element_strengths:
            self._log_debug(f"Attacker's strength: {self.element_strengths[attacker_element]}")
        
        if attacker_element in self.element_strengths and self.element_strengths[attacker_element] == defender_element:
            mod = round(random.uniform(0.1, 0.3), 2)
            self._log_debug(f"Element bonus: +{mod*100}%")
            return mod
        elif defender_element in self.element_strengths and self.element_strengths[defender_element] == attacker_element:
            mod = round(random.uniform(-0.3, -0.1), 2)
            self._log_debug(f"Element penalty: {mod*100}%")
            return mod
        self._log_debug("No element modifier")
        return 0.0
    
    def get_element_emoji(self, element):
        """Get emoji for a given element"""
        return self.element_to_emoji.get(element, "❓")
    
    @classmethod
    def get_debug_info(cls):
        """Get all debug logs"""
        return "\n".join(DebugInfo.logs[-20:])  # Return last 20 messages

    @classmethod
    async def debug_cmd(cls, ctx):
        """Command to show debug logs"""
        logs = cls.get_debug_info()
        if not logs:
            return await ctx.send("No debug logs available yet.")
        
        # Split into chunks of 2000 characters for Discord
        for i in range(0, len(logs), 1900):
            chunk = logs[i:i+1900]
            await ctx.send(f"```\n{chunk}\n```")