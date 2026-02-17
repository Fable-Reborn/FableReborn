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

    @staticmethod
    def _normalize_element(element):
        if not element:
            return "Unknown"
        return str(element).strip().capitalize()

    @staticmethod
    def _record_value(record, key, default=None):
        try:
            if isinstance(record, dict):
                return record.get(key, default)
            return record[key]
        except Exception:
            return default

    def _first_known_element(self, *elements):
        normalized = [self._normalize_element(element) for element in elements]
        for element in normalized:
            if element != "Unknown":
                return element
        return normalized[0] if normalized else "Unknown"

    def resolve_player_combat_elements(self, equipped_items):
        items = []
        for raw_item in equipped_items or []:
            item_type = str(self._record_value(raw_item, "type", "") or "").strip()
            damage = int(self._record_value(raw_item, "damage", 0) or 0)
            armor = int(self._record_value(raw_item, "armor", 0) or 0)
            element = self._normalize_element(self._record_value(raw_item, "element", "Unknown"))
            items.append(
                {
                    "type": item_type,
                    "damage": damage,
                    "armor": armor,
                    "element": element,
                }
            )

        shields = sorted(
            [item for item in items if item["type"].lower() == "shield"],
            key=lambda item: (item["armor"], item["damage"]),
            reverse=True,
        )
        weapons = sorted(
            [item for item in items if item["type"].lower() != "shield"],
            key=lambda item: (item["damage"], item["armor"]),
            reverse=True,
        )

        has_shield = bool(shields)
        primary_weapon = weapons[0] if weapons else None
        secondary_weapon = weapons[1] if len(weapons) > 1 else None
        best_shield = shields[0] if shields else None

        primary_weapon_element = (
            self._normalize_element(primary_weapon["element"]) if primary_weapon else "Unknown"
        )
        secondary_weapon_element = (
            self._normalize_element(secondary_weapon["element"]) if secondary_weapon else "Unknown"
        )
        shield_element = (
            self._normalize_element(best_shield["element"]) if best_shield else "Unknown"
        )

        dual_attack_elements = None
        if (
            primary_weapon
            and secondary_weapon
            and primary_weapon["damage"] == secondary_weapon["damage"]
            and primary_weapon_element != "Unknown"
            and secondary_weapon_element != "Unknown"
            and primary_weapon_element != secondary_weapon_element
        ):
            dual_attack_elements = [primary_weapon_element, secondary_weapon_element]

        attack_element = self._first_known_element(
            primary_weapon_element,
            secondary_weapon_element,
            shield_element,
            "Unknown",
        )

        defense_element = self._first_known_element(
            shield_element,
            secondary_weapon_element,
            attack_element,
            "Unknown",
        )

        return {
            "attack_element": attack_element,
            "defense_element": defense_element,
            "dual_attack_elements": dual_attack_elements,
            "has_shield": has_shield,
        }

    async def get_player_combat_elements(self, ctx, user_id):
        try:
            async with ctx.bot.pool.acquire() as conn:
                equipped_items = await conn.fetch(
                    "SELECT ai.type, ai.damage, ai.armor, ai.element FROM profile p "
                    "JOIN allitems ai ON (p.user=ai.owner) JOIN inventory i ON (ai.id=i.item) "
                    "WHERE i.equipped IS TRUE AND p.user=$1;",
                    user_id,
                )
            return self.resolve_player_combat_elements(equipped_items)
        except Exception:
            return {
                "attack_element": "Unknown",
                "defense_element": "Unknown",
                "dual_attack_elements": None,
                "has_shield": False,
            }
    
    async def get_player_element(self, ctx, user_id):
        """Get a user's primary element"""
        element_data = await self.get_player_combat_elements(ctx, user_id)
        return element_data.get("attack_element", "Unknown")
    
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
        if defender_element is None:
            if attacker_element is None:
                attacker_element = ctx_or_attacker_element
                defender_element = "Unknown"
            else:
                defender_element = attacker_element
                attacker_element = ctx_or_attacker_element
        
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
