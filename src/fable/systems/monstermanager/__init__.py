import discord
from discord.ext import commands
import random
import asyncio

from fable.utils.checks import is_gm


class MonsterManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Your provided JSON data
        # Define the monsters per level
        self.monsters = {
            1: [
                {"name": "Sneevil", "hp": 100, "attack": 95, "defense": 100, "element": "Earth",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Sneevil-removebg-preview.png"},
                {"name": "Slime", "hp": 120, "attack": 100, "defense": 105, "element": "Water",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_slime.png"},
                {"name": "Frogzard", "hp": 120, "attack": 90, "defense": 95, "element": "Nature",
                 "url": "https://static.wikia.nocookie.net/aqwikia/images/d/d6/Frogzard.png"},
                {"name": "Rat", "hp": 90, "attack": 100, "defense": 90, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Rat-removebg-preview.png"},
                {"name": "Bat", "hp": 150, "attack": 95, "defense": 85, "element": "Wind",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Bat-removebg-preview.png"},
                {"name": "Skeleton", "hp": 190, "attack": 105, "defense": 100, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Skelly-removebg-preview.png"},
                {"name": "Imp", "hp": 180, "attack": 95, "defense": 85, "element": "Fire",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_zZquzlh-removebg-preview.png"},
                {"name": "Pixie", "hp": 100, "attack": 90, "defense": 80, "element": "Light",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_pixie-removebg-preview.png"},
                {"name": "Zombie", "hp": 170, "attack": 100, "defense": 95, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_zombie-removebg-preview.png"},
                {"name": "Spiderling", "hp": 220, "attack": 95, "defense": 90, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_spider-removebg-preview.png"},
                {"name": "Spiderling", "hp": 220, "attack": 95, "defense": 90, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_spider-removebg-preview.png"},
                {"name": "Moglin", "hp": 200, "attack": 90, "defense": 85, "element": "Light",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Moglin.png"},
                {"name": "Red Ant", "hp": 140, "attack": 105, "defense": 100, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_redant-removebg-preview.png"},
                {"name": "Chickencow", "hp": 300, "attack": 150, "defense": 90, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChickenCow-removebg-preview.png"},
                {"name": "Tog", "hp": 380, "attack": 105, "defense": 95, "element": "Earth",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Tog-removebg-preview.png"},
                {"name": "Lemurphant", "hp": 340, "attack": 95, "defense": 80, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Lemurphant-removebg-preview.png"},
                {"name": "Fire Imp", "hp": 200, "attack": 100, "defense": 90, "element": "Fire",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_zZquzlh-removebg-preview.png"},
                {"name": "Zardman", "hp": 300, "attack": 95, "defense": 100, "element": "Earth",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Zardman-removebg-preview.png"},
                {"name": "Wind Elemental", "hp": 165, "attack": 90, "defense": 85, "element": "Wind",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_WindElemental-removebg-preview.png"},
                {"name": "Dark Wolf", "hp": 200, "attack": 100, "defense": 90, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_DarkWolf-removebg-preview.png"},
                {"name": "Treeant", "hp": 205, "attack": 105, "defense": 95, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Treeant-removebg-preview.png"},
            ],
            2: [
                {"name": "Cyclops Warlord", "hp": 230, "attack": 160, "defense": 155, "element": "Earth",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_CR-removebg-preview.png"},
                {"name": "Fishman Soldier", "hp": 200, "attack": 165, "defense": 160, "element": "Water",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Fisherman-removebg-preview.png"},
                {"name": "Fire Elemental", "hp": 215, "attack": 150, "defense": 145, "element": "Fire",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_fire_elemental-removebg-preview.png"},
                {"name": "Vampire Bat", "hp": 200, "attack": 170, "defense": 160, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_viO2oSJ-removebg-preview.png"},
                {"name": "Blood Eagle", "hp": 195, "attack": 165, "defense": 150, "element": "Wind",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_BloodEagle-removebg-preview.png"},
                {"name": "Earth Elemental", "hp": 190, "attack": 175, "defense": 160, "element": "Earth",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Earth_Elemental-removebg-preview.png"},
                {"name": "Fire Mage", "hp": 200, "attack": 160, "defense": 140, "element": "Fire",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_FireMage-removebg-preview.png"},
                {"name": "Dready Bear", "hp": 230, "attack": 155, "defense": 150, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_dreddy-removebg-preview.png"},
                {"name": "Undead Soldier", "hp": 280, "attack": 160, "defense": 155, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_UndeadSoldier-removebg-preview.png"},
                {"name": "Skeleton Warrior", "hp": 330, "attack": 155, "defense": 150, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_SkeelyWarrior-removebg-preview.png"},
                {"name": "Giant Spider", "hp": 350, "attack": 160, "defense": 145, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_DreadSpider-removebg-preview.png"},
                {"name": "Castle spider", "hp": 310, "attack": 170, "defense": 160, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Castle-removebg-preview.png"},
                {"name": "ConRot", "hp": 210, "attack": 165, "defense": 155, "element": "Water",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ConRot-removebg-preview.png"},
                {"name": "Horc Warrior", "hp": 270, "attack": 175, "defense": 170, "element": "Earth",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_HorcWarrior-removebg-preview.png"},
                {"name": "Shadow Hound", "hp": 300, "attack": 160, "defense": 150, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Hound-removebg-preview.png"},
                {"name": "Fire Sprite", "hp": 290, "attack": 165, "defense": 155, "element": "Fire",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_FireSprite-removebg-preview.png"},
                {"name": "Rock Elemental", "hp": 300, "attack": 160, "defense": 165, "element": "Earth",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Earth_Elemental-removebg-preview.png"},
                {"name": "Shadow Serpent", "hp": 335, "attack": 155, "defense": 150, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ShadowSerpant-removebg-preview.png"},
                {"name": "Dark Elemental", "hp": 340, "attack": 165, "defense": 155, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_DarkEle-Photoroom.png"},
                {"name": "Forest Guardian", "hp": 500, "attack": 250, "defense": 250, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ForestGuardian-removebg-preview.png"},
            ],
            3: [
                {"name": "Mana Golem", "hp": 200, "attack": 220, "defense": 210, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_managolum-removebg-preview.png"},
                {"name": "Karok the Fallen", "hp": 180, "attack": 215, "defense": 205, "element": "Ice",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_VIMs8un-removebg-preview.png"},
                {"name": "Water Draconian", "hp": 220, "attack": 225, "defense": 200, "element": "Water",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_waterdrag-removebg-preview.png"},
                {"name": "Shadow Creeper", "hp": 190, "attack": 220, "defense": 205, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_shadowcreep-removebg-preview.png"},
                {"name": "Wind Djinn", "hp": 210, "attack": 225, "defense": 215, "element": "Wind",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_djinn-removebg-preview.png"},
                {"name": "Autunm Fox", "hp": 205, "attack": 230, "defense": 220, "element": "Earth",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Autumn_Fox-removebg-preview.png"},
                {"name": "Dark Draconian", "hp": 195, "attack": 220, "defense": 200, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_darkdom-removebg-preview.png"},
                {"name": "Light Elemental", "hp": 185, "attack": 215, "defense": 210, "element": "Light",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_LightELemental-removebg-preview.png"},
                {"name": "Undead Giant", "hp": 230, "attack": 220, "defense": 210, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_UndGiant-removebg-preview.png"},
                {"name": "Chaos Spider", "hp": 215, "attack": 215, "defense": 205, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChaosSpider-removebg-preview.png"},
                {"name": "Seed Spitter", "hp": 225, "attack": 220, "defense": 200, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_SeedSpitter-removebg-preview.png"},
                {"name": "Beach Werewolf", "hp": 240, "attack": 230, "defense": 220, "element": "Water",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_BeachWerewold-removebg-preview.png"},
                {"name": "Boss Dummy", "hp": 220, "attack": 225, "defense": 210, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_BossDummy-removebg-preview.png"},
                {"name": "Rock", "hp": 235, "attack": 225, "defense": 215, "element": "Earth",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Rock-removebg-preview.png"},
                {"name": "Shadow Serpent", "hp": 200, "attack": 220, "defense": 205, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ShadoeSerpant-removebg-preview.png"},
                {"name": "Flame Elemental", "hp": 210, "attack": 225, "defense": 210, "element": "Fire",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_FireElemental-removebg-preview.png"},
                {"name": "Bear", "hp": 225, "attack": 215, "defense": 220, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732611726453.png"},
                {"name": "Chair", "hp": 215, "attack": 210, "defense": 215, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_chair-removebg-preview.png"},
                {"name": "Chaos Serpant", "hp": 230, "attack": 220, "defense": 205, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChaosSerp-removebg-preview.png"},
                {"name": "Gorillaphant", "hp": 240, "attack": 225, "defense": 210, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_gorillaserpant-removebg-preview.png"},
            ],
            4: [
                {"name": "Hydra Head", "hp": 300, "attack": 280, "defense": 270, "element": "Water",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_hydra.png"},
                {"name": "Blessed Deer", "hp": 280, "attack": 275, "defense": 265, "element": "Light",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_BlessedDeer-removebg-preview.png"},
                {"name": "Chaos Sphinx", "hp": 320, "attack": 290, "defense": 275, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChaopsSpinx.png"},
                {"name": "Inferno Dracolion", "hp": 290, "attack": 285, "defense": 270, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732614284328.png"},
                {"name": "Wind Cyclone", "hp": 310, "attack": 290, "defense": 280, "element": "Wind",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_WindElemental-removebg-preview.png"},
                {"name": "Mr Cuddles", "hp": 305, "attack": 295, "defense": 285, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_mrcuddles-removebg-preview.png"},
                {"name": "Infernal Fiend", "hp": 295, "attack": 285, "defense": 270, "element": "Fire",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732614284328.png"},
                {"name": "Dark Mukai", "hp": 285, "attack": 275, "defense": 265, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732614826889.png"},
                {"name": "Undead Berserker", "hp": 330, "attack": 285, "defense": 275, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732614863579.png"},
                {"name": "Chaos Warrior", "hp": 315, "attack": 280, "defense": 270, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChaosWarrior-removebg-preview.png"},
                {"name": "Dire Wolf", "hp": 325, "attack": 285, "defense": 275, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_DireWolf-removebg-preview.png"},
                {"name": "Skye Warrior", "hp": 340, "attack": 295, "defense": 285, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_SkyeWarrior-removebg-preview.png"},
                {"name": "Death On Wings", "hp": 320, "attack": 290, "defense": 275, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_DeathonWings-removebg-preview.png"},
                {"name": "Chaorruption", "hp": 335, "attack": 295, "defense": 285, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Chaorruption-removebg-preview.png"},
                {"name": "Shadow Beast", "hp": 300, "attack": 285, "defense": 270, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ShadowBeast-removebg-preview.png"},
                {"name": "Hootbear", "hp": 310, "attack": 290, "defense": 275, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_HootBear-removebg-preview.png"},
                {"name": "Anxiety", "hp": 325, "attack": 280, "defense": 290, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_anxiety-removebg-preview.png"},
                {"name": "Twilly", "hp": 315, "attack": 275, "defense": 285, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Twilly-removebg-preview.png"},
                {"name": "Black Cat", "hp": 330, "attack": 285, "defense": 270, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_QJsLMnk-removebg-preview.png"},
                {"name": "Forest Guardian", "hp": 340, "attack": 290, "defense": 275, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ForestGuardian-removebg-preview.png"},
            ],
            5: [
                {"name": "Chaos Dragon", "hp": 400, "attack": 380, "defense": 370, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChaosDragon-removebg-preview.png"},
                {"name": "Wooden Door", "hp": 380, "attack": 375, "defense": 365, "element": "Earth",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_WoodenDoor-removebg-preview.png"},
                {"name": "Garvodeus", "hp": 420, "attack": 390, "defense": 375, "element": "Water",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Garvodeus-removebg-preview.png"},
                {"name": "Shadow Lich", "hp": 390, "attack": 385, "defense": 370, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ShadowLich-removebg-preview.png"},
                {"name": "Zorbak", "hp": 410, "attack": 390, "defense": 380, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Zorbak-removebg-preview.png"},
                {"name": "Dwakel Rocketman", "hp": 405, "attack": 395, "defense": 385, "element": "Electric",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_DwarkalRock-removebg-preview.png"},
                {"name": "Kathool", "hp": 395, "attack": 385, "defense": 370, "element": "Water",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Kathool-removebg-preview.png"},
                {"name": "Celestial Hound", "hp": 385, "attack": 375, "defense": 365, "element": "Light",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_CelestialHound-removebg-preview.png"},
                {"name": "Undead Raxgore", "hp": 430, "attack": 385, "defense": 375, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Raxfore-removebg-preview_1.png"},
                {"name": "Droognax", "hp": 415, "attack": 380, "defense": 370, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Droognax-removebg-preview.png"},
                {"name": "Corrupted Boar", "hp": 425, "attack": 385, "defense": 375, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Corrupted_Bear-removebg-preview.png"},
                {"name": "Fressa", "hp": 440, "attack": 395, "defense": 385, "element": "Water",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Fressa-removebg-preview.png"},
                {"name": "Grimskull", "hp": 420, "attack": 390, "defense": 375, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Grimskull-removebg-preview.png"},
                {"name": "Chaotic Chicken", "hp": 435, "attack": 385, "defense": 380, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChaoticChicken-removebg-preview.png"},
                {"name": "Baelgar", "hp": 400, "attack": 385, "defense": 370, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Baelgar-removebg-preview.png"},
                {"name": "Blood Dragon", "hp": 410, "attack": 390, "defense": 375, "element": "Fire",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_BloodDragon-removebg-preview.png"},
                {"name": "Avatar of Desolich", "hp": 425, "attack": 380, "defense": 390, "element": "Fire",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732696555786.png"},
                {"name": "Piggy Drake", "hp": 415, "attack": 375, "defense": 385, "element": "Wind",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732696596976.png"},
                {"name": "Chaos Alteon", "hp": 430, "attack": 385, "defense": 370, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Chaos_Alteon-removebg-preview.png"},
                {"name": "Argo", "hp": 440, "attack": 380, "defense": 375, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Argo-removebg-preview.png"},
            ],
            6: [
                {"name": "Ultra Cuddles", "hp": 500, "attack": 470, "defense": 460, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ultracuddles-removebg-preview.png"},
                {"name": "General Pollution", "hp": 480, "attack": 465, "defense": 455, "element": "Earth",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_genpol-removebg-preview.png"},
                {"name": "Manslayer Fiend", "hp": 520, "attack": 475, "defense": 460, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_manlsayer-removebg-preview.png"},
                {"name": "The Hushed", "hp": 490, "attack": 470, "defense": 455, "element": "Light",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_hushed-removebg-preview.png"},
                {"name": "The Jailer", "hp": 510, "attack": 475, "defense": 465, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_jailer-removebg-preview.png"},
                {"name": "Thriller", "hp": 505, "attack": 480, "defense": 470, "element": "Electric",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Thriller-removebg-preview.png"},
                {"name": "Dire Razorclaw", "hp": 495, "attack": 470, "defense": 455, "element": "Fire",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_file.png"},
                {"name": "Dollageddon", "hp": 485, "attack": 465, "defense": 455, "element": "Light",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Dollageddon-removebg-preview.png"},
                {"name": "Gold Werewolf", "hp": 530, "attack": 475, "defense": 460, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Gold_Werewolf-removebg-preview.png"},
                {"name": "FlameMane", "hp": 515, "attack": 470, "defense": 455, "element": "Fire",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_FlameMane-removebg-preview.png"},
                {"name": "Specimen 66", "hp": 525, "attack": 475, "defense": 460, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Specimen_66-removebg-preview.png"},
                {"name": "Frank", "hp": 540, "attack": 480, "defense": 470, "element": "Electric",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Frank-removebg-preview.png"},
                {"name": "French Horned ToadDragon", "hp": 520, "attack": 475, "defense": 460, "element": "Water",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_file__1_-removebg-preview.png"},
                {"name": "Mog Zard", "hp": 535, "attack": 475, "defense": 465, "element": "Earth",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_MogZard-removebg-preview.png"},
                {"name": "Mo-Zard", "hp": 500, "attack": 470, "defense": 455, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_file__2_-removebg-preview.png"},
                {"name": "Nulgath", "hp": 510, "attack": 475, "defense": 460, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Nulgath-removebg-preview.png"},
                {"name": "Proto Champion", "hp": 525, "attack": 465, "defense": 475, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_file_3.png"},
                {"name": "Trash Can", "hp": 515, "attack": 460, "defense": 470, "element": "Light",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_TrashCan-removebg-preview.png"},
                {"name": "Turdragon", "hp": 530, "attack": 475, "defense": 460, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Turagon-removebg-preview.png"},
                {"name": "Unending Avatar", "hp": 540, "attack": 470, "defense": 455, "element": "Nature",
                 "url": " https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_file_4.png"},
            ],
            7: [
                {"name": "Astral Dragon", "hp": 600, "attack": 570, "defense": 560, "element": "Light",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_AstralDragon.png"},
                {"name": "Eise Horror", "hp": 580, "attack": 565, "defense": 555, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Elise_Horror-removebg-preview.png"},
                {"name": "Asbane", "hp": 620, "attack": 575, "defense": 560, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Adbane.png"},
                {"name": "Apephyryx", "hp": 590, "attack": 570, "defense": 555, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Apephryx-removebg-preview.png"},
                {"name": "Enchantress", "hp": 610, "attack": 575, "defense": 565, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Enchantress-removebg-preview.png"},
                {"name": "Queen of Monsters", "hp": 605, "attack": 580, "defense": 570, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_QueenOfMonsters-removebg-preview.png"},
                {"name": "Krykan", "hp": 595, "attack": 570, "defense": 555, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove_background_project.png"},
                {"name": "Painadin Overlord", "hp": 585, "attack": 565, "defense": 555, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Painadin_Overlord-removebg-preview.png"},
                {"name": "EL-Blender", "hp": 630, "attack": 575, "defense": 560, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_EbilBlender-removebg-preview.png"},
                {"name": "Key of Sholemoh", "hp": 615, "attack": 570, "defense": 555, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Key_of_Sholemoh-removebg-preview.png"},
                {"name": "Specimen 30", "hp": 625, "attack": 575, "defense": 560, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Specimen_30.png"},
                {"name": "Pinky", "hp": 640, "attack": 580, "defense": 570, "element": "Electric",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Pinky-removebg-preview.png"},
                {"name": "Monster Cake", "hp": 620, "attack": 575, "defense": 560, "element": "Nature",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Monster_Cake-removebg-preview.png"},
                {"name": "Angyler Fish", "hp": 635, "attack": 575, "defense": 565, "element": "Water",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Angyler_Fish-removebg-preview.png"},
                {"name": "Big Bad Ancient.. Goose?", "hp": 600, "attack": 570, "defense": 555, "element": "Light",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_BigBadAncientGoose-removebg-preview.png"},
                {"name": "Barlot Field", "hp": 610, "attack": 575, "defense": 560, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Barlot_Fiend-removebg-preview.png"},
                {"name": "Barghest", "hp": 625, "attack": 565, "defense": 575, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Barghest-removebg-preview.png"},
                {"name": "Yuzil", "hp": 615, "attack": 560, "defense": 570, "element": "Dark",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Yuzil.png"},
                {"name": "Azkorath", "hp": 630, "attack": 575, "defense": 560, "element": "Corrupted",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Azkorath-removebg-preview.png"},
                {"name": "Boto", "hp": 640, "attack": 570, "defense": 555, "element": "Water",
                 "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Boto.png"},
            ]
        }

    def distribute_iv_points(self, total_points):
        """Distribute IV points randomly across attack, defense, and hp."""
        attack_incr = random.randint(0, total_points)
        defense_incr = random.randint(0, total_points - attack_incr)
        hp_incr = total_points - attack_incr - defense_incr
        return attack_incr, defense_incr, hp_incr

    @commands.command(name='runmonsterpatch')
    @is_gm()
    async def update_monsters(self, ctx):
        """
        Updates adult monsters in the database based on the provided JSON data.
        """
        await ctx.send("Starting the monster update process...")

        try:
            async with self.bot.pool.acquire() as connection:
                # Fetch all adult monsters
                records = await connection.fetch("""
                    SELECT id, default_name, attack, defense, hp, "IV"
                    FROM monster_pets
                    WHERE growth_stage = 'adult'
                """)

                updated_count = 0
                skipped_count = 0
                not_found_monsters = []

                for record in records:
                    monster_id = record['id']
                    name = record['default_name']
                    current_attack = record['attack']
                    current_defense = record['defense']
                    current_hp = record['hp']
                    iv = record['IV']

                    # Search for the monster in the JSON data (case-insensitive)
                    monster_data = None
                    for level, monster_list in self.monsters.items():
                        for monster in monster_list:
                            if monster['name'].strip().lower() == name.strip().lower():
                                monster_data = monster
                                break
                        if monster_data:
                            break

                    if not monster_data:
                        not_found_monsters.append(name)
                        skipped_count += 1
                        continue  # Skip to the next monster

                    # Update attack, defense, and hp based on JSON
                    json_attack = monster_data['attack']
                    json_defense = monster_data['defense']
                    json_hp = monster_data['hp']

                    updated_attack = json_attack
                    updated_defense = json_defense
                    updated_hp = json_hp

                    # Handle IV
                    doubled_iv = iv * 2

                    # Distribute IV points randomly
                    attack_incr, defense_incr, hp_incr = self.distribute_iv_points(doubled_iv)

                    updated_attack += attack_incr
                    updated_defense += defense_incr
                    updated_hp += hp_incr

                    # Update the monster in the database
                    await connection.execute("""
                        UPDATE monster_pets
                        SET attack = $1,
                            defense = $2,
                            hp = $3
                        WHERE id = $4
                    """, updated_attack, updated_defense, updated_hp, monster_id)

                    updated_count += 1

                # Prepare the response message
                response = f"✅ **Monster Update Completed!**\n" \
                           f"**Total Monsters Processed:** {len(records)}\n" \
                           f"**Monsters Updated:** {updated_count}\n" \
                           f"**Monsters Skipped (Not Found in JSON):** {skipped_count}"

                if not_found_monsters:
                    response += "\n**Monsters Not Found in JSON:**\n" + "\n".join(f"- {m}" for m in not_found_monsters)

                await ctx.send(response)

        except Exception as e:
            await ctx.send(f"❌ An error occurred during the update process: {e}")
            raise  # Re-raise the exception for debugging purposes

async def setup(bot):
    await bot.add_cog(MonsterManager(bot))
