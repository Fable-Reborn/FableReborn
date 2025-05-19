# battles/extensions/classes.py

class ClassBuffExtension:
    """Extension for class-based buffs"""
    
    # Classes with death-cheating abilities
    death_cheat_classes = {
        "Deathshroud": 20,
        "Soul Warden": 30,
        "Reaper": 40,
        "Phantom Scythe": 50,
        "Soul Snatcher": 60,
        "Deathbringer": 70,
        "Grim Reaper": 80,
    }
    
    # Classes with lifesteal abilities
    lifesteal_classes = {
        "Little Helper": 7,
        "Gift Gatherer": 14,
        "Holiday Aide": 21,
        "Joyful Jester": 28,
        "Yuletide Guardian": 35,
        "Festive Enforcer": 40,
        "Festive Champion": 60,
    }
    
    # Mage evolution levels for fireball spell
    mage_evolution_levels = {
        "Witcher": 1,
        "Enchanter": 2,
        "Mage": 3,
        "Warlock": 4,
        "Dark Caster": 5,
        "White Sorcerer": 6,
    }
    
    # Tank evolution levels for shield abilities
    tank_evolution_levels = {
        "Protector": 1,
        "Guardian": 2,
        "Bulwark": 3,
        "Defender": 4,
        "Vanguard": 5,
        "Fortress": 6,
        "Titan": 7,
    }
    
    # Mage fireball damage multipliers
    evolution_damage_multiplier = {
        1: 1.10,  # 110%
        2: 1.20,  # 120%
        3: 1.30,  # 130%
        4: 1.50,  # 150%
        5: 1.75,  # 175%
        6: 2.00,  # 200%
    }
    
    # Tank health multipliers
    evolution_health_multiplier = {
        1: 1.05,  # 105%
        2: 1.10,  # 110%
        3: 1.15,  # 115%
        4: 1.20,  # 120%
        5: 1.25,  # 125%
        6: 1.30,  # 130%
        7: 1.35,  # 135%
    }
    
    # Tank damage reflection multipliers
    evolution_reflection_multiplier = {
        1: 0.03,  # 3%
        2: 0.06,  # 6%
        3: 0.09,  # 9%
        4: 0.12,  # 12%
        5: 0.15,  # 15%
        6: 0.18,  # 18%
        7: 0.21,  # 21%
    }
    
    # Ranger classes for egg bonuses
    ranger_egg_bonuses = {
        "Caretaker": 0.02,  # +2%
        "Tamer": 0.04,      # +4%
        "Trainer": 0.06,    # +6%
        "Bowman": 0.08,     # +8%
        "Hunter": 0.10,     # +10%
        "Warden": 0.13,     # +13%
        "Ranger": 0.15,     # +15%
    }
    
    async def get_class_buffs(self, classes):
        """Get buffs for a user based on their classes"""
        # Buffs to return
        buffs = {
            "death_cheat_chance": 0,
            "lifesteal_percent": 0,
            "mage_evolution": None,
            "tank_evolution": None,
            "ranger_evolution": None,
        }
        
        if not classes:
            return buffs
            
        # Ensure classes is a list
        if not isinstance(classes, list):
            classes = [classes]
        
        # Calculate buffs based on classes
        for class_name in classes:
            # Death cheat chance
            if class_name in self.death_cheat_classes:
                buffs["death_cheat_chance"] = max(buffs["death_cheat_chance"], self.death_cheat_classes[class_name])
            
            # Lifesteal
            if class_name in self.lifesteal_classes:
                buffs["lifesteal_percent"] = max(buffs["lifesteal_percent"], self.lifesteal_classes[class_name])
            
            # Mage evolution
            if class_name in self.mage_evolution_levels:
                level = self.mage_evolution_levels[class_name]
                if buffs["mage_evolution"] is None or level > buffs["mage_evolution"]:
                    buffs["mage_evolution"] = level
            
            # Tank evolution
            if class_name in self.tank_evolution_levels:
                level = self.tank_evolution_levels[class_name]
                if buffs["tank_evolution"] is None or level > buffs["tank_evolution"]:
                    buffs["tank_evolution"] = level
                    
            # Ranger evolution
            if class_name in self.ranger_egg_bonuses:
                level = list(self.ranger_egg_bonuses.keys()).index(class_name) + 1
                if buffs["ranger_evolution"] is None or level > buffs["ranger_evolution"]:
                    buffs["ranger_evolution"] = level
        
        return buffs
        
    def apply_tank_buffs(self, total_health, tank_evolution, has_shield):
        """Apply tank class buffs to health and calculate reflection"""
        damage_reflection = 0.0
        
        if tank_evolution and has_shield:
            # Health bonus: +4% per evolution level
            health_multiplier = 1 + (0.04 * tank_evolution)
            total_health *= health_multiplier
            damage_reflection = 0.03 * tank_evolution
        elif tank_evolution:
            # Smaller health bonus without shield
            health_multiplier = 1 + (0.01 * tank_evolution)
            total_health *= health_multiplier
            
        return total_health, damage_reflection