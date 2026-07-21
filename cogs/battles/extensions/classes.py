# battles/extensions/classes.py
from decimal import Decimal

from ..core.numbers import to_decimal
from classes.warrior import WARRIOR_EVOLUTION_LEVELS

class ClassBuffExtension:
    """Extension for class-based buffs"""
    
    # Classes with death-cheating abilities
    death_cheat_classes = {
        "Deathshroud": 10,
        "Soul Warden": 15,
        "Reaper": 20,
        "Phantom Scythe": 25,
        "Soul Snatcher": 30,
        "Deathbringer": 35,
        "Grim Reaper": 40,
    }
    
    # Classes with lifesteal abilities
    lifesteal_classes = {
        "Little Helper": 5,
        "Gift Gatherer": 7,
        "Holiday Aide": 10,
        "Joyful Jester": 12,
        "Yuletide Guardian": 15,
        "Festive Enforcer": 18,
        "Festive Champion": 20,
    }

    reaper_evolution_levels = {
        "Deathshroud": 1,
        "Soul Warden": 2,
        "Reaper": 3,
        "Phantom Scythe": 4,
        "Soul Snatcher": 5,
        "Deathbringer": 6,
        "Grim Reaper": 7,
    }

    santa_evolution_levels = {
        "Little Helper": 1,
        "Gift Gatherer": 2,
        "Holiday Aide": 3,
        "Joyful Jester": 4,
        "Yuletide Guardian": 5,
        "Festive Enforcer": 6,
        "Festive Champion": 7,
    }
    
    # Mage evolution levels for fireball spell
    mage_evolution_levels = {
        "Juggler": 1,
        "Witcher": 2,
        "Enchanter": 3,
        "Mage": 4,
        "Warlock": 5,
        "Dark Caster": 6,
        "White Sorcerer": 7,
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

    warrior_evolution_levels = WARRIOR_EVOLUTION_LEVELS

    # Paladin evolution levels for faith-based smites
    paladin_evolution_levels = {
        "Squire": 1,
        "Foot Knight": 2,
        "Crusader": 3,
        "Templar": 4,
        "Justicar": 5,
        "Divine Champion": 6,
        "Archpaladin": 7,
    }

    # Raider evolution levels for raid marks
    raider_evolution_levels = {
        "Adventurer": 1,
        "Swordsman": 2,
        "Fighter": 3,
        "Swashbuckler": 4,
        "Dragonslayer": 5,
        "Raider": 6,
        "Eternal Hero": 7,
    }

    # Ritualist evolution levels for doom sigils
    ritualist_evolution_levels = {
        "Priest": 1,
        "Mysticist": 2,
        "Doomsayer": 3,
        "Seer": 4,
        "Oracle": 5,
        "Prophet": 6,
        "Ritualist": 7,
    }

    # Paragon evolution levels for adaptive mastery
    paragon_evolution_levels = {
        "Novice": 1,
        "Proficient": 2,
        "Artisan": 3,
        "Master": 4,
        "Champion": 5,
        "Vindicator": 6,
        "Paragon": 7,
    }

    # Bard evolution levels for party songs
    bard_evolution_levels = {
        "Busker": 1,
        "Minstrel": 2,
        "Skald": 3,
        "Troubadour": 4,
        "Songweaver": 5,
        "Virtuoso": 6,
        "Maestro": 7,
    }

    # Beastmaster evolution levels for pet-bond scaling
    beastmaster_evolution_levels = {
        "Wrangler": 1,
        "Beast Kin": 2,
        "Packmate": 3,
        "Wildcaller": 4,
        "Alphabond": 5,
        "Feralheart": 6,
        "Beastlord": 7,
    }
    
    # Mage fireball damage multipliers
    evolution_damage_multiplier = {
        1: 1.10,  # 110%
        2: 1.20,  # 120%
        3: 1.30,  # 130%
        4: 1.50,  # 150%
        5: 1.75,  # 175%
        6: 2.00,  # 200%
        7: 2.10,  # 210%
    }

    # Mage arcane shield gain per successful non-fireball hit
    mage_arcane_shield_gain = {
        1: 0.035,  # 3.5%
        2: 0.040,  # 4.0%
        3: 0.045,  # 4.5%
        4: 0.050,  # 5.0%
        5: 0.055,  # 5.5%
        6: 0.060,  # 6.0%
        7: 0.065,  # 6.5%
    }

    # Soft cap for passive arcane shielding
    mage_arcane_shield_cap = {
        1: 0.15,  # 15%
        2: 0.17,  # 17%
        3: 0.19,  # 19%
        4: 0.21,  # 21%
        5: 0.23,  # 23%
        6: 0.25,  # 25%
        7: 0.26,  # 26%
    }

    # Paladin smite bonus damage based on attack stat
    paladin_smite_damage_multiplier = {
        1: 0.20,  # 20%
        2: 0.25,  # 25%
        3: 0.30,  # 30%
        4: 0.35,  # 35%
        5: 0.40,  # 40%
        6: 0.45,  # 45%
        7: 0.50,  # 50%
    }

    # Paladin holy shield granted when Divine Smite triggers
    paladin_holy_shield_gain = {
        1: 0.04,  # 4%
        2: 0.05,  # 5%
        3: 0.06,  # 6%
        4: 0.07,  # 7%
        5: 0.08,  # 8%
        6: 0.09,  # 9%
        7: 0.10,  # 10%
    }

    # Soft cap for paladin holy shielding
    paladin_holy_shield_cap = {
        1: 0.12,  # 12%
        2: 0.14,  # 14%
        3: 0.16,  # 16%
        4: 0.18,  # 18%
        5: 0.20,  # 20%
        6: 0.22,  # 22%
        7: 0.24,  # 24%
    }

    # Raider bonus damage from consuming raid marks
    raider_mark_damage_multiplier = {
        1: 0.15,  # 15%
        2: 0.18,  # 18%
        3: 0.21,  # 21%
        4: 0.24,  # 24%
        5: 0.27,  # 27%
        6: 0.30,  # 30%
        7: 0.35,  # 35%
    }

    # Raider bonus scaling from target max HP
    raider_mark_max_hp_ratio = {
        1: 0.010,  # 1.0%
        2: 0.012,  # 1.2%
        3: 0.014,  # 1.4%
        4: 0.016,  # 1.6%
        5: 0.018,  # 1.8%
        6: 0.020,  # 2.0%
        7: 0.025,  # 2.5%
    }

    # Paragon bonus damage when adapting to armored targets
    paragon_break_damage_multiplier = {
        1: 0.08,  # 8%
        2: 0.10,  # 10%
        3: 0.12,  # 12%
        4: 0.14,  # 14%
        5: 0.16,  # 16%
        6: 0.18,  # 18%
        7: 0.20,  # 20%
    }

    # Paragon shield gain when adapting defensively
    paragon_guard_shield_gain = {
        1: 0.020,  # 2.0%
        2: 0.025,  # 2.5%
        3: 0.030,  # 3.0%
        4: 0.035,  # 3.5%
        5: 0.040,  # 4.0%
        6: 0.045,  # 4.5%
        7: 0.050,  # 5.0%
    }

    # Paragon balanced strike damage when no extreme matchup is detected
    paragon_balanced_damage_multiplier = {
        1: 0.04,  # 4%
        2: 0.05,  # 5%
        3: 0.06,  # 6%
        4: 0.07,  # 7%
        5: 0.08,  # 8%
        6: 0.09,  # 9%
        7: 0.10,  # 10%
    }

    # Paragon balanced shield gain when no extreme matchup is detected
    paragon_balanced_shield_gain = {
        1: 0.010,  # 1.0%
        2: 0.012,  # 1.2%
        3: 0.014,  # 1.4%
        4: 0.016,  # 1.6%
        5: 0.018,  # 1.8%
        6: 0.020,  # 2.0%
        7: 0.025,  # 2.5%
    }

    # Soft cap for paragon adaptive barriers
    paragon_shield_cap = {
        1: 0.12,  # 12%
        2: 0.14,  # 14%
        3: 0.16,  # 16%
        4: 0.18,  # 18%
        5: 0.20,  # 20%
        6: 0.22,  # 22%
        7: 0.25,  # 25%
    }

    # Ritualist burst damage when doom sigils align
    ritualist_doom_burst_multiplier = {
        1: 0.12,  # 12%
        2: 0.15,  # 15%
        3: 0.18,  # 18%
        4: 0.21,  # 21%
        5: 0.24,  # 24%
        6: 0.27,  # 27%
        7: 0.30,  # 30%
    }

    # Ritualist follow-up doom damage on subsequent hits
    ritualist_doom_echo_multiplier = {
        1: 0.06,  # 6%
        2: 0.07,  # 7%
        3: 0.08,  # 8%
        4: 0.09,  # 9%
        5: 0.10,  # 10%
        6: 0.11,  # 11%
        7: 0.12,  # 12%
    }

    # Ritualist favor ward gained after finishing a doomed enemy
    ritualist_favor_shield_gain = {
        1: 0.04,  # 4%
        2: 0.05,  # 5%
        3: 0.06,  # 6%
        4: 0.07,  # 7%
        5: 0.08,  # 8%
        6: 0.09,  # 9%
        7: 0.10,  # 10%
    }

    # Soft cap for ritualist favor ward
    ritualist_favor_shield_cap = {
        1: 0.12,  # 12%
        2: 0.14,  # 14%
        3: 0.16,  # 16%
        4: 0.18,  # 18%
        5: 0.20,  # 20%
        6: 0.22,  # 22%
        7: 0.24,  # 24%
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
            "warrior_evolution": None,
            "tank_evolution": None,
            "paladin_evolution": None,
            "raider_evolution": None,
            "ritualist_evolution": None,
            "paragon_evolution": None,
            "ranger_evolution": None,
            "bard_evolution": None,
            "beastmaster_evolution": None,
            "reaper_evolution": None,
            "santa_evolution": None,
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

            if class_name in self.reaper_evolution_levels:
                level = self.reaper_evolution_levels[class_name]
                if buffs["reaper_evolution"] is None or level > buffs["reaper_evolution"]:
                    buffs["reaper_evolution"] = level

            if class_name in self.santa_evolution_levels:
                level = self.santa_evolution_levels[class_name]
                if buffs["santa_evolution"] is None or level > buffs["santa_evolution"]:
                    buffs["santa_evolution"] = level
            
            # Mage evolution
            if class_name in self.mage_evolution_levels:
                level = self.mage_evolution_levels[class_name]
                if buffs["mage_evolution"] is None or level > buffs["mage_evolution"]:
                    buffs["mage_evolution"] = level

            if class_name in self.warrior_evolution_levels:
                level = self.warrior_evolution_levels[class_name]
                if buffs["warrior_evolution"] is None or level > buffs["warrior_evolution"]:
                    buffs["warrior_evolution"] = level
            
            # Tank evolution
            if class_name in self.tank_evolution_levels:
                level = self.tank_evolution_levels[class_name]
                if buffs["tank_evolution"] is None or level > buffs["tank_evolution"]:
                    buffs["tank_evolution"] = level

            # Paladin evolution
            if class_name in self.paladin_evolution_levels:
                level = self.paladin_evolution_levels[class_name]
                if buffs["paladin_evolution"] is None or level > buffs["paladin_evolution"]:
                    buffs["paladin_evolution"] = level

            # Raider evolution
            if class_name in self.raider_evolution_levels:
                level = self.raider_evolution_levels[class_name]
                if buffs["raider_evolution"] is None or level > buffs["raider_evolution"]:
                    buffs["raider_evolution"] = level

            # Ritualist evolution
            if class_name in self.ritualist_evolution_levels:
                level = self.ritualist_evolution_levels[class_name]
                if buffs["ritualist_evolution"] is None or level > buffs["ritualist_evolution"]:
                    buffs["ritualist_evolution"] = level

            # Paragon evolution
            if class_name in self.paragon_evolution_levels:
                level = self.paragon_evolution_levels[class_name]
                if buffs["paragon_evolution"] is None or level > buffs["paragon_evolution"]:
                    buffs["paragon_evolution"] = level
                    
            # Ranger evolution
            if class_name in self.ranger_egg_bonuses:
                level = list(self.ranger_egg_bonuses.keys()).index(class_name) + 1
                if buffs["ranger_evolution"] is None or level > buffs["ranger_evolution"]:
                    buffs["ranger_evolution"] = level

            # Bard evolution
            if class_name in self.bard_evolution_levels:
                level = self.bard_evolution_levels[class_name]
                if buffs["bard_evolution"] is None or level > buffs["bard_evolution"]:
                    buffs["bard_evolution"] = level

            # Beastmaster evolution
            if class_name in self.beastmaster_evolution_levels:
                level = self.beastmaster_evolution_levels[class_name]
                if buffs["beastmaster_evolution"] is None or level > buffs["beastmaster_evolution"]:
                    buffs["beastmaster_evolution"] = level

        return buffs

    def apply_tank_buffs(self, total_health, tank_evolution, has_shield):
        """Apply tank class buffs to health and calculate reflection"""
        total_health = to_decimal(total_health)
        tank_evolution = to_decimal(tank_evolution)
        damage_reflection = Decimal("0")

        if tank_evolution and has_shield:
            # Health bonus: +4% per evolution level
            health_multiplier = Decimal("1") + (Decimal("0.04") * tank_evolution)
            total_health *= health_multiplier
            damage_reflection = Decimal("0.03") * tank_evolution
        elif tank_evolution:
            # Smaller health bonus without shield
            health_multiplier = Decimal("1") + (Decimal("0.01") * tank_evolution)
            total_health *= health_multiplier

        return total_health, damage_reflection
