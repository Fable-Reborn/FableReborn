"""PRPG cosmetics: local artwork, portable fonts and deterministic card chrome."""

import colorsys
from dataclasses import dataclass, replace
from functools import lru_cache
import math
from pathlib import Path
import random
import re

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps


ASSET_ROOT = Path(__file__).resolve().parents[2] / "assets" / "profile_themes"


@dataclass(frozen=True)
class ProfileTheme:
    key: str
    name: str
    epithet: str
    description: str
    accent: str
    secondary: str
    background: str
    panel: str
    text: str
    muted: str
    emoji: str
    collection: str = "Origins"
    rarity: str = "Rare"
    motif: str = "diamond"
    title_lines: tuple[str, ...] = ()
    finish: str = "standard"
    event: str = ""
    unlock_flag: str = ""
    layout: str = "standard"

    @property
    def card_size(self):
        if self.classic:
            return (1660, 940)
        if self.rarity == "Fable":
            return FABLE_SIZE
        return TRANSCENDENT_SIZE if self.rarity == "Transcendent" else (1660, 1460)

    @property
    def classic(self):
        return self.key == "classic"

    @property
    def is_event(self):
        return bool(self.event)

    @property
    def palette(self):
        return {
            "panel": self.panel,
            "panel_inner": self.background,
            "border": self.accent,
            "border_dim": self.secondary,
            "text": self.text,
            "muted": self.muted,
            "bar_bg": self.background,
        }


THEMES = {
    t.key: t for t in (
        ProfileTheme("classic", "Original Chronicle", "Your story begins here.",
                     "The original parchment-and-bronze profile card.",
                     "#c69c5a", "#846236", "#27180e", "#4a311e", "#f7e7c4", "#d6ba8c", "📜"),
        ProfileTheme("dragon", "Ashen Sovereign", "FROM ASH, AN EMPIRE.",
                     "An obsidian wyrm, molten gold and a citadel forged in fire.",
                     "#f6bb68", "#8c5935", "#120e0c", "#251b15", "#fff1db", "#d3bda4", "🐉"),
        ProfileTheme("evil", "The Hollow Crown", "LET THE LIGHT KNEEL.",
                     "A blood eclipse, a skeletal throne and blackened steel.",
                     "#f48591", "#83414c", "#100b10", "#25141d", "#fbe8ec", "#c9aab7", "💀"),
        ProfileTheme("chaos", "Violet Rupture", "REALITY IS A SUGGESTION.",
                     "Shattered dimensions, amethyst lightning and an eldritch eye.",
                     "#d0a1ff", "#7950ac", "#110d20", "#211733", "#f5eaff", "#c8b3e4", "🌀"),
        ProfileTheme("good", "Dawnward", "THE DAWN STANDS WITH YOU.",
                     "A winged celestial guardian in pearl, sun gold and azure.",
                     "#f2d58b", "#827454", "#101c2a", "#1c2c3c", "#fff8e7", "#bfceda", "☀️"),
        ProfileTheme("forest", "Verdant Oath", "THE OLD WORLD REMEMBERS.",
                     "A sacred antlered spirit beneath an emerald forest cathedral.",
                     "#ade0a5", "#4e8266", "#0b1916", "#142d25", "#edf7df", "#b0cebb", "🌿"),
        ProfileTheme("frost", "Winterveil", "EVEN ETERNITY CAN FREEZE.",
                     "An ice-crowned sovereign, silver spires and midnight auroras.",
                     "#afe7ff", "#4e7d9e", "#0b1421", "#17283a", "#edf9ff", "#b5ccdf", "❄️"),
        ProfileTheme("elysia", "Elysia's Mercy", "KINDNESS IS DIVINE POWER.",
                     "The healing goddess, a sacred white stag and sunlit lilies.",
                     "#f4d892", "#598f8a", "#0d2227", "#19383c", "#fff8e8", "#bbdcd5", "🌸", "Divine", "Divine", "sun"),
        ProfileTheme("sepulchure", "Sepulchure's Requiem", "EVERY ENDING ANSWERS TO HIM.",
                     "A death lord commands his spectral legion beneath a blood eclipse.",
                     "#df9096", "#755660", "#160d13", "#29151e", "#fbeaec", "#c9b0b9", "☠️", "Divine", "Divine", "claw"),
        ProfileTheme("drakath", "Drakath's Paradox", "THE FUTURE HAS BEEN UNWRITTEN.",
                     "The chaos god unfolds crystalline wings over shattered timelines.",
                     "#cba5ff", "#7468b7", "#140e28", "#291b42", "#f4edff", "#c8bce5", "🔮", "Divine", "Divine", "rift"),
        ProfileTheme("moonbunny", "Moonpetal Burrow", "SMALL PAWS. INFINITE WONDER.",
                     "Moon rabbits and a sleepy baby dragon share a porcelain teacup.",
                     "#f4bad7", "#a27394", "#271b2e", "#3b2a42", "#fff0f7", "#d8bfd4", "🐇", "Companions", "Uncommon", "petal"),
        ProfileTheme("slime", "Slime Royalty", "ALL HAIL THE LITTLE BLOB.",
                     "A crowned jelly king rules a tiny kingdom of strawberries and dew.",
                     "#bbefa2", "#62947f", "#112721", "#1c3d31", "#f1ffe6", "#bcdcc9", "👑", "Companions", "Uncommon", "bubble"),
        ProfileTheme("frogzard", "Frogzard Festival", "ONE MORE SONG BEFORE THE QUEST.",
                     "Leaf-cloaked frog-lizards dance around a firefly-lit mushroom stage.",
                     "#e6d583", "#558e7a", "#102620", "#1c3b31", "#f6f5dc", "#bfd3b5", "🐸", "Companions", "Rare", "leaf"),
        ProfileTheme("chickencow", "Cloudmilk Meadow", "A LITTLE MOO. A LITTLE MAGIC.",
                     "Fluffy winged Chickencows nap among buttercups and peach clouds.",
                     "#f8d499", "#a48a7a", "#2a252c", "#40353b", "#fff7e9", "#e1cfc1", "🐮", "Companions", "Uncommon", "petal"),
        ProfileTheme("mushroom", "Mosslight Hollow", "HOME IS WHERE THE LANTERN GLOWS.",
                     "A tiny mushroom sprite and a cottage-carrying snail wander home.",
                     "#fac59c", "#8e9574", "#20261e", "#343e2e", "#fff1db", "#d6d2b4", "🍄", "Companions", "Uncommon", "leaf"),
        ProfileTheme("leviathan", "Abyssal Monarch", "THE DEEP DOES NOT BOW.",
                     "A luminous leviathan coils around a cathedral swallowed by the sea.",
                     "#87e4f0", "#396f8b", "#081c2a", "#103344", "#e4faff", "#a6cddc", "🐙", "Mythic", "Legendary", "wave"),
        ProfileTheme("phoenix", "Cindersong", "EVERY ASH REMEMBERS ITS FIRE.",
                     "A phoenix of scarlet and white-gold rises through a storm of ash roses.",
                     "#ffc191", "#a36160", "#251218", "#3d2029", "#fff0e4", "#ddbab2", "🔥", "Mythic", "Legendary", "sun"),
        ProfileTheme("storm", "Stormbreaker", "THUNDER KNOWS YOUR NAME.",
                     "An armored thunder wolf roars above a shattered mountain.",
                     "#a7d5ff", "#596eae", "#0c172b", "#182944", "#eef5ff", "#b5c7e2", "⚡", "Mythic", "Epic", "rift"),
        ProfileTheme("eclipse", "Eclipse Devourer", "EVEN THE SUN CAN FALL.",
                     "An obsidian cosmic dragon coils around the last light of a dying sun.",
                     "#efd494", "#8e774d", "#111115", "#242125", "#fff5df", "#d3c8af", "🌑", "Mythic", "Mythic", "sun"),
        ProfileTheme("bloodmoon", "Bloodmoon Hunt", "THE NIGHT HAS TEETH.",
                     "A silver-black dire werewolf claims a ruined tower under a crimson moon.",
                     "#f299a8", "#8c536a", "#170f1b", "#2c1c2c", "#ffecf2", "#cbb7ca", "🐺", "Mythic", "Legendary", "claw"),
        ProfileTheme("astral", "Starfall Archive", "SOME STORIES CARRY WORLDS.",
                     "A celestial whale carries an illuminated library through a sea of stars.",
                     "#bbc8ff", "#6276b3", "#10172d", "#1e2a45", "#f0f2ff", "#bfc9e6", "🐋", "Mythic", "Legendary", "star"),
        ProfileTheme("kitsune", "Foxfire Masquerade", "NINE TAILS. A THOUSAND SECRETS.",
                     "An ivory fox spirit drifts through shrine lanterns and teal foxfire.",
                     "#f4bdaf", "#967178", "#201923", "#342b35", "#fff2e8", "#d7c3c6", "🦊", "Wonders", "Epic", "petal"),
        ProfileTheme("mimic", "The Gilded Maw", "FORTUNE FAVOURS THE HUNGRY.",
                     "An extravagantly jeweled treasure chest with a very toothy secret.",
                     "#edca7d", "#96734b", "#211a16", "#372a20", "#fff1d3", "#d4c1a0", "💰", "Wonders", "Epic", "gear"),
        ProfileTheme("lotus", "Lotus Dream", "LET THE WORLD DRIFT BY.",
                     "Celestial koi and luminous lotus flowers float through a jade dream.",
                     "#f3bed0", "#6e9a98", "#15272c", "#253d42", "#fff1f2", "#bed4d1", "🪷", "Wonders", "Rare", "wave"),
        ProfileTheme("clockwork", "Clockwork Seraph", "ETERNITY, BEAUTIFULLY ENGINEERED.",
                     "A six-winged mechanical owl presides over a brass cosmic observatory.",
                     "#eecb89", "#718d88", "#152228", "#29373b", "#fff2d9", "#c9ccc1", "⚙️", "Wonders", "Epic", "gear"),
        ProfileTheme("darkelf", "Nightglass Court", "BEAUTY SHARP ENOUGH TO CUT.",
                     "A silver-haired dark elf empress reigns over an obsidian underworld.",
                     "#d4acfa", "#826298", "#1b1226", "#2e203d", "#f5eaff", "#d0bbdf", "🕷️", "Elven", "Epic", "rift"),
        ProfileTheme("woodelf", "Heartwood Covenant", "OUR ROOTS OUTLAST KINGDOMS.",
                     "A wood elf guardian and spirit fox watch over a living tree sanctuary.",
                     "#cfdfa0", "#798b55", "#182519", "#2b3b27", "#f4f8df", "#c9d3b1", "🏹", "Elven", "Rare", "leaf"),
        ProfileTheme("highelf", "Starglass Dominion", "WE WERE HERE BEFORE THE STARS.",
                     "A high elf archmage summons starlight above sapphire crystal towers.",
                     "#c7dbff", "#6985ae", "#142134", "#25374c", "#f1f7ff", "#c0d0e5", "✨", "Elven", "Epic", "star"),
        ProfileTheme("elysia_ascendant", "Elysia Ascendant", "THE LIGHT REMEMBERS ITS QUEEN.",
                     "Black-haired Elysia commands the dawn from her golden phoenix throne.",
                     "#f6d68d", "#977452", "#231b20", "#382a2b", "#fff5df", "#d9c5b0", "🌞", "Divine", "Exalted", "sun"),
        ProfileTheme("sepulchure_unbound", "Sepulchure Unbound", "ALL KINGDOMS END IN DOOM.",
                     "Crimson DoomKnight armor, a skull-hilted blade and a kingdom of red lightning.",
                     "#ff9c91", "#9b5159", "#1b0e13", "#331921", "#fff0e8", "#d8b5b6", "🗡️", "Divine", "Exalted", "claw"),
        ProfileTheme("drakath_incarnate", "Drakath Incarnate", "CHAOS HAS OPENED ITS EYES.",
                     "Orange eyes burn beneath black hair as the horn-armored god tears reality apart.",
                     "#d1a4ff", "#8055ad", "#170d29", "#2b1944", "#f6ebff", "#cfb7e4", "👁️", "Divine", "Exalted", "rift"),
        ProfileTheme("lanternwake", "Lanternwake", "EVERY LIGHT IS SOMEONE COMING HOME.",
                     "A red panda lantern keeper guides a procession beneath a city suspended from an ancient bell.",
                     "#ffc78c", "#92735d", "#101c22", "#1e3036", "#fff1df", "#c8c8ba", "🏮", "Companions", "Uncommon", "lantern"),
        ProfileTheme("glasswing", "Glasswing Reverie", "A THOUSAND GARDENS. ONE HEARTBEAT.",
                     "A palace-sized moon moth shelters living gardens inside its crystalline wings.",
                     "#bceacb", "#678f81", "#101e1c", "#20332e", "#effaf0", "#b8d2c2", "🦋", "Wonders", "Uncommon", "wing"),
        ProfileTheme("porcelain", "Porcelain Tempest", "WHAT BREAKS BECOMES GOLD.",
                     "An ivory and cobalt kirin races the black tide, its porcelain fractures blazing with gold.",
                     "#e8d3a2", "#6c91a3", "#101c2c", "#20324a", "#f3f5ed", "#b9ccdc", "🌊", "Wonders", "Uncommon", "wave"),
        ProfileTheme("firstflame", "Crown of the First Flame", "BEFORE THE DAWN, THERE WAS A KING.",
                     "An obsidian lion sovereign wears the first sun as a crown above a shattered temple.",
                     "#ffd28c", "#986b49", "#1c1314", "#302024", "#fff3dd", "#d9c1aa", "🦁", "Mythic", "Legendary", "crown",
                     title_lines=("Crown of the", "First Flame")),
        ProfileTheme("unwritten", "The World Unwritten", "EVEN ETERNITY CAN BE ERASED.",
                     "An ivory archivist turns the final page, folding kingdoms into an ocean of ink.",
                     "#ede1c2", "#928374", "#14171c", "#252a31", "#faf5e7", "#c8c8c4", "📖", "Mythic", "Mythic", "quill"),
        ProfileTheme("laststar", "Cathedral of the Last Star", "ONE LIGHT. AFTER EVERYTHING.",
                     "A sentinel of black opal holds the last star within six wings of cathedral vaults.",
                     "#c6dcff", "#797cad", "#111421", "#23283d", "#f4f5ff", "#c0c8e0", "💠", "Mythic", "Mythic", "spire",
                     title_lines=("Cathedral of", "the Last Star")),
        ProfileTheme("tynfdarius", "Emperor of the Caldera", "THE MOUNTAIN HAS A MASTER.",
                     "Avatar Tynfdarius lifts a fortress from the caldera, bronze armor crowned in living flame.",
                     "#ffd291", "#a46c50", "#211016", "#371f25", "#fff1df", "#dcc0ad", "🌋", "Bestiary", "Epic", "sun",
                     title_lines=("Emperor of", "the Caldera")),
        ProfileTheme("mechaknight", "The Iron Apocalypse", "THE LAST CHARGE NEVER ENDS.",
                     "Mech-a-Knight shatters an iron causeway beneath acid-green reactors and a scarlet axe.",
                     "#d1edac", "#718975", "#111d1b", "#22332f", "#f1f6e8", "#bfcdbb", "⚙️", "Bestiary", "Epic", "gear",
                     title_lines=("The Iron", "Apocalypse")),
        ProfileTheme("umbracrown", "Garden of the Petrified", "EVERY KING RETURNS TO STONE.",
                     "The six-legged Umbracrown Basilisk reigns over moonlit kings and gardens turned to marble.",
                     "#d8d1ee", "#8787aa", "#171927", "#292d42", "#f5f1ff", "#c9c8dc", "🐍", "Bestiary", "Legendary", "crown",
                     title_lines=("Garden of", "the Petrified")),
        ProfileTheme("deimos", "Chains of the Dread King", "EVEN THE ABYSS HAS A PRISONER.",
                     "Deimos tears a prison cathedral apart, chains trailing from his wings through blue ghostfire.",
                     "#afd9ff", "#617fad", "#101827", "#202c42", "#eef6ff", "#b8cbe4", "⛓️", "Bestiary", "Legendary", "claw",
                     title_lines=("Chains of", "the Dread King")),
        ProfileTheme("voiddragon", "Sovereign of the Rift", "EVERY WORLD IS JUST A DOOR.",
                     "The Void Dragon coils around an inverted silver kingdom, cyan ribbons flowing through its halo.",
                     "#acefe5", "#8d78a9", "#1a1427", "#30233f", "#f1f9f8", "#c6bed8", "🌀", "Bestiary", "Legendary", "rift",
                     title_lines=("Sovereign of", "the Rift")),
        ProfileTheme("nullstar", "Hunger Beyond Heaven", "THE STARS WERE ONLY THE BEGINNING.",
                     "Nullstar Behemoth devours a planetary ring through the singularity burning in its carapace.",
                     "#d7b7ff", "#8d68b1", "#1a1128", "#302040", "#f8efff", "#d0bcdf", "💠", "Bestiary", "Mythic", "rift",
                     title_lines=("Hunger Beyond", "Heaven")),
        ProfileTheme("boneglass", "Boneglass Requiem", "DEATH STILL KNOWS THE MELODY.",
                     "A skeletal maestro conducts spectral ravens through a drowned opera house of bone and glass.",
                     "#cbebd8", "#7d9b8b", "#101f1d", "#223630", "#f4f5e9", "#c2d1c5", "💀", "Wonders", "Epic", "quill"),
        ProfileTheme("drownedpearl", "Pearl of the Drowned", "AN OCEAN CANNOT BURY A KINGDOM.",
                     "An abyssal nautilus carries an entire drowned kingdom inside its mother-of-pearl shell.",
                     "#f1d0d4", "#ac8599", "#14222c", "#253845", "#fff2ef", "#ccd2da", "🐚", "Wonders", "Legendary", "wave",
                     title_lines=("Pearl of", "the Drowned")),
        ProfileTheme("worldheart", "Anvil of Creation", "EVERY WORLD BEGINS WITH A SPARK.",
                     "A masked titan forges a living world inside a crystal sword above an obsidian mountain anvil.",
                     "#edcf9b", "#788dab", "#131c2b", "#263449", "#fff5e3", "#c7cedc", "⚒️", "Mythic", "Mythic", "gear"),
        ProfileTheme("sandreign", "Empire in the Hourglass", "NOTHING IS LOST. ONLY TURNED.",
                     "A lapis-crowned sphinx holds a glass empire that falls as golden sand and rises anew.",
                     "#edce8c", "#9d8864", "#18242a", "#2b383e", "#fff2d9", "#d2cbb5", "⌛", "Wonders", "Epic", "diamond",
                     title_lines=("Empire in", "the Hourglass")),
        ProfileTheme("emberkettle", "The Last Warm Hearth", "EVERY QUEST DESERVES A WARM RETURN.",
                     "A badger innkeeper tends a copper kettle whose steam shelters a tiny flame dragon.",
                     "#f1cf9b", "#8f987a", "#182623", "#2b3b31", "#fff2df", "#cdd3be", "🫖", "Wonders", "Common", "lantern",
                     title_lines=("The Last", "Warm Hearth")),
        ProfileTheme("mossback", "Mossback Caravan", "HOME GOES WHERE THE ROAD GROWS.",
                     "A giant tortoise carries a bustling lantern-lit market village above a misty forest gorge.",
                     "#d3e5ac", "#879c74", "#192a24", "#2d4032", "#f5f7e4", "#c6d6bc", "🐢", "Companions", "Common", "leaf"),
        ProfileTheme("brassbeak", "Brassbeak Post", "NO MOUNTAIN CAN KEEP A LETTER.",
                     "A barn owl courier sorts moonlit parcels inside a magnificent cliffside post office.",
                     "#ead5a5", "#8594aa", "#1c2532", "#303e50", "#faf4e6", "#cbd1dd", "🦉", "Companions", "Common", "quill"),
        ProfileTheme("moonharvest", "Moonberry Harvest", "SOME STARS GROW CLOSE TO HOME.",
                     "A capybara herbalist gathers translucent moonberries beneath a silver orchard.",
                     "#e6c4ec", "#9484ab", "#241b31", "#3a2d49", "#fcf0fc", "#d5c4df", "🫐", "Companions", "Common", "petal"),
        ProfileTheme("stormheron", "Heron of the Thunder Marsh", "STILLNESS HOLDS THE STORM.",
                     "A silver-feathered heron carries a fork of lightning above a flooded bell sanctuary.",
                     "#c4e4ee", "#7e9aab", "#16272f", "#293d46", "#eff9f7", "#c1d5dc", "🪶", "Wonders", "Uncommon", "quill",
                     title_lines=("Heron of the", "Thunder Marsh")),
        ProfileTheme("velvetprowl", "Velvet Prowler", "THE NIGHT HAS A SOFTER FOOTSTEP.",
                     "A constellation-furred lynx with golden claw guards prowls above a rainlit city.",
                     "#e6bdd8", "#aa7e9f", "#281c30", "#402b46", "#fff1fb", "#ddc3d8", "🐈‍⬛", "Companions", "Uncommon", "claw"),
        ProfileTheme("emberbloom", "Emberbloom Sanctuary", "EVEN FIRE CAN LEARN TO REST.",
                     "A ruby-glass salamander sleeps around a glowing lotus in a subterranean crystal garden.",
                     "#f6c4b0", "#ad8883", "#29202b", "#44303b", "#fff0e6", "#ddc4c7", "🌺", "Companions", "Uncommon", "petal"),
        ProfileTheme("tideweaver", "The Tideweaver", "WE SAIL ON WHAT WE DARE TO DREAM.",
                     "An octopus artisan weaves moonlight into a silver sail alive with tiny luminous fish.",
                     "#d3dce9", "#8e8fa9", "#1d2933", "#303e4c", "#f5f6fc", "#c6d2dd", "🐙", "Wonders", "Uncommon", "wave"),
        ProfileTheme("amberreliquary", "The Amber Reliquary", "A FOREST REMEMBERS THROUGH GOLD.",
                     "A giant stag beetle preserves a prehistoric forest inside its translucent amber carapace.",
                     "#eddaa0", "#90956a", "#252b1d", "#3b432c", "#fff8df", "#d8d5b8", "🪲", "Wonders", "Rare", "leaf",
                     title_lines=("The Amber", "Reliquary")),
        ProfileTheme("frostgardener", "The Frost Gardener", "WINTER IS ANOTHER WAY TO BLOOM.",
                     "An ermine sorceress grows a rose of cloud-filled ice around one golden ember.",
                     "#d9e6fc", "#9c9cbc", "#20283c", "#343f57", "#f6f6ff", "#cdd4e9", "❄️", "Companions", "Rare", "petal",
                     title_lines=("The Frost", "Gardener")),
        ProfileTheme("leviathanswake", "The Leviathan's Wake", "CARRY THE LIGHT THROUGH ANY STORM.",
                     "An ancient white whale carries a towering lighthouse fortress through the midnight sea.",
                     "#e8d8aa", "#8598a8", "#172632", "#2b3b4c", "#f8f5e9", "#c8d1db", "🐋", "Mythic", "Epic", "wave",
                     title_lines=("The Leviathan's", "Wake")),
        ProfileTheme("gravebloom", "Where Titans Sleep", "THE WORLD STILL GROWS AROUND US.",
                     "A mountain-sized stone knight blooms with peonies, waterfalls and a bridge made from its sword.",
                     "#efc9d9", "#a790a6", "#292335", "#42354b", "#fff1f6", "#dfcbd8", "🌸", "Mythic", "Epic", "petal",
                     title_lines=("Where Titans", "Sleep")),
        ProfileTheme("allworlds", "Covenant of All Worlds", "EVERY STORY. EVERY STAR. TOGETHER.",
                     "A celestial peacock shelters seven living worlds within a fan of opal, platinum and dimensional glass.",
                     "#f3dfb2", "#8d96ad", "#111a2b", "#263148", "#faf5ea", "#c7d2e5", "🦚", "Mythic", "Mythic", "covenant",
                     title_lines=("Covenant of", "All Worlds"), finish="prismatic"),
        ProfileTheme("cloverpony", "Cloverhoof Meadow", "THE ROAD IS BETTER WITH A FRIEND.",
                     "A chestnut pony rests among lanterns and wildflowers.",
                     "#d9bd8f", "#82765b", "#232922", "#393b2f", "#f3ede6", "#b5ada3",
                     "🐴", "Journeys", "Common", "leaf",
                     title_lines=("Cloverhoof", "Meadow"), finish="standard"),
        ProfileTheme("breadandembers", "Bread and Embers", "A WARM LOAF BEFORE THE LONG ROAD.",
                     "A stone oven glows in a dwarven roadside bakery.",
                     "#e5b987", "#886c51", "#241917", "#3b2c24", "#f3ede6", "#b9aca0",
                     "🍞", "Journeys", "Common", "lantern",
                     title_lines=("Bread and", "Embers"), finish="standard"),
        ProfileTheme("silverhook", "Silverhook Landing", "THE QUIET HOURS HAVE THEIR TREASURES.",
                     "An otter angler waits beside a jade mountain river.",
                     "#a5d6d0", "#60817f", "#152527", "#263a3b", "#f3ede6", "#a6b4b6",
                     "🎣", "Journeys", "Common", "wave",
                     title_lines=("Silverhook", "Landing"), finish="standard"),
        ProfileTheme("coalwhisker", "Coalwhisker Mine", "SMALL PAWS. BRIGHT FORTUNES.",
                     "A mole miner uncovers a vein of honey quartz.",
                     "#e8c77e", "#887554", "#201d26", "#383131", "#f3ede6", "#bab09e",
                     "⛏️", "Journeys", "Common", "diamond",
                     title_lines=("Coalwhisker", "Mine"), finish="standard"),
        ProfileTheme("patchworkcamp", "Patchwork Camp", "REST HERE. THE WORLD CAN WAIT.",
                     "Adventurers share a quiet fire under the stars.",
                     "#d7b191", "#7e6d61", "#1e232d", "#343439", "#f3ede6", "#b5a9a3",
                     "🏕️", "Journeys", "Common", "flame",
                     title_lines=("Patchwork", "Camp"), finish="standard"),
        ProfileTheme("thimbleguard", "The Thimble Guard", "COURAGE IS NEVER MEASURED IN INCHES.",
                     "A mouse knight guards a rain-soaked garden gate.",
                     "#c9c4a0", "#787964", "#202724", "#343a33", "#f3ede6", "#b1afa8",
                     "🐭", "Journeys", "Common", "crown",
                     title_lines=("The Thimble", "Guard"), finish="standard"),
        ProfileTheme("jadeapothecary", "The Jade Apothecary", "EVERY WOUND HAS A WILDER ANSWER.",
                     "An elven herbalist distils moonlight into glass.",
                     "#a7d4ab", "#60826a", "#142a23", "#263e33", "#f3ede6", "#a6b4ab",
                     "⚗️", "Journeys", "Uncommon", "leaf",
                     title_lines=("The Jade", "Apothecary"), finish="standard"),
        ProfileTheme("silkroadwyrm", "The Silkroad Wyrm", "FORTUNE FOLLOWS THE LONGEST SHADOW.",
                     "A jewel-scaled serpent escorts a desert caravan.",
                     "#edc397", "#8f7261", "#2a1b26", "#412f34", "#f3ede6", "#bbafa5",
                     "🐫", "Journeys", "Uncommon", "scale",
                     title_lines=("The Silkroad", "Wyrm"), finish="standard"),
        ProfileTheme("bellkeeper", "The Bellkeeper", "SOME SOULS STILL KNOW THE WAY HOME.",
                     "A bronze stag rings a forgotten forest bell.",
                     "#c9c6a3", "#777a6a", "#1e282c", "#333b3a", "#f3ede6", "#b1b0a9",
                     "🔔", "Journeys", "Uncommon", "lantern",
                     title_lines=("The", "Bellkeeper"), finish="standard"),
        ProfileTheme("inkfin", "Inkfin Atelier", "THE SEA SIGNS ITS NAME IN GOLD.",
                     "An octopus calligrapher paints living constellations.",
                     "#bea8df", "#74648d", "#231b35", "#362c49", "#f3ede6", "#ada7bb",
                     "🖋️", "Journeys", "Uncommon", "star",
                     title_lines=("Inkfin", "Atelier"), finish="standard"),
        ProfileTheme("gildedrook", "The Gilded Rook", "THE NEXT MOVE BELONGS TO YOU.",
                     "A raven watches a living ivory chess kingdom.",
                     "#ddd0a2", "#847d69", "#23232b", "#393839", "#f3ede6", "#b7b3a8",
                     "♟️", "Journeys", "Uncommon", "crown",
                     title_lines=("The Gilded", "Rook"), finish="standard"),
        ProfileTheme("auroraferry", "Aurora Ferry", "EVEN THE NIGHT NEEDS A WAY ACROSS.",
                     "A lantern skiff sails a river beneath the northern lights.",
                     "#a6d9d9", "#608389", "#142532", "#263b46", "#f3ede6", "#a6b5b9",
                     "⛵", "Journeys", "Uncommon", "wave",
                     title_lines=("Aurora", "Ferry"), finish="standard"),
        ProfileTheme("rubyforge", "The Ruby Forge", "TEMPERED IN THE HEART OF THE MOUNTAIN.",
                     "A master smith draws a crimson blade from crystal fire.",
                     "#e6aa98", "#8c645f", "#2b1822", "#412a30", "#f3ede6", "#b9a7a5",
                     "🔨", "Relics", "Rare", "flame",
                     title_lines=("The Ruby", "Forge"), finish="standard"),
        ProfileTheme("opalunicorn", "The Opal Unicorn", "PURITY IS A POWER ALL ITS OWN.",
                     "An opal unicorn steps across a moonlit mirror lake.",
                     "#cbd5ed", "#778097", "#1d2339", "#32384f", "#f3ede6", "#b1b4bf",
                     "🦄", "Relics", "Rare", "star",
                     title_lines=("The Opal", "Unicorn"), finish="standard"),
        ProfileTheme("amethystbastion", "Amethyst Bastion", "HOLD FAST WHERE THE SKY BREAKS.",
                     "A crystal sentinel keeps watch over a violet fortress.",
                     "#c7aeed", "#776793", "#211b32", "#352d48", "#f3ede6", "#b0a8bf",
                     "🏰", "Relics", "Rare", "diamond",
                     title_lines=("Amethyst", "Bastion"), finish="standard"),
        ProfileTheme("honeycrown", "Court of Honey", "A THOUSAND WINGS. ONE GOLDEN VOW.",
                     "A bee empress rules a palace of translucent amber.",
                     "#ecd19c", "#8e7e5d", "#292419", "#403929", "#f3ede6", "#bbb3a7",
                     "🐝", "Relics", "Rare", "crown",
                     title_lines=("Court of", "Honey"), finish="standard"),
        ProfileTheme("duskmoth", "Duskmoth Reliquary", "THE LIGHT YOU LOST STILL LIVES HERE.",
                     "A giant velvet moth shelters a fragile lantern city.",
                     "#d8b2ce", "#846a83", "#2a1d32", "#3f2f45", "#f3ede6", "#b5aab6",
                     "🕯️", "Relics", "Rare", "wing",
                     title_lines=("Duskmoth", "Reliquary"), finish="standard"),
        ProfileTheme("thundercolossus", "The Thunder Colossus", "LET THE MOUNTAINS HEAR YOUR FOOTSTEPS.",
                     "A storm titan crosses a broken mountain range.",
                     "#b3d2ef", "#698098", "#18273a", "#2b3c50", "#f3ede6", "#aab3bf",
                     "🌩️", "Relics", "Epic", "bolt",
                     title_lines=("The Thunder", "Colossus"), finish="standard"),
        ProfileTheme("sableopera", "The Sable Opera", "THE LAST NOTE OUTLIVES THE KINGDOM.",
                     "A masked spectre conducts an orchestra of black swans.",
                     "#dac1dd", "#84718a", "#271b30", "#3c2f45", "#f3ede6", "#b6aeba",
                     "🎭", "Relics", "Epic", "crown",
                     title_lines=("The Sable", "Opera"), finish="standard"),
        ProfileTheme("coralcitadel", "The Coral Citadel", "BENEATH THE WAVES, AN EMPIRE WAKES.",
                     "A lionfish knight guards a radiant coral throne.",
                     "#edbea8", "#877672", "#182937", "#323b45", "#f3ede6", "#bbadaa",
                     "🐠", "Relics", "Epic", "scale",
                     title_lines=("The Coral", "Citadel"), finish="standard"),
        ProfileTheme("dawnpegasus", "Wings of the First Dawn", "THE SKY WAS ONLY THE BEGINNING.",
                     "A golden-winged Pegasus soars above a sea of clouds.",
                     "#edcfa6", "#8a7f72", "#1e2939", "#373d46", "#f3ede6", "#bbb2aa",
                     "🌄", "Relics", "Epic", "wing",
                     title_lines=("Wings of the", "First Dawn"), finish="standard"),
        ProfileTheme("seraphimvault", "The Seraphim Vault", "WHAT HEAVEN HID, YOU HAVE FOUND.",
                     "A six-winged guardian opens an impossible golden vault.",
                     "#f0d8a7", "#8e7f6e", "#231e30", "#3c343e", "#f3ede6", "#bcb5aa",
                     "🗝️", "Eternities", "Legendary", "wing",
                     title_lines=("The Seraphim", "Vault"), finish="standard"),
        ProfileTheme("winterregent", "The Winter Regent", "THE WORLD HOLDS ITS BREATH.",
                     "A crowned polar sovereign rules a palace of frozen light.",
                     "#badde6", "#6c8693", "#172839", "#2b3e4e", "#f3ede6", "#acb7bd",
                     "🧊", "Eternities", "Legendary", "crown",
                     title_lines=("The Winter", "Regent"), finish="standard"),
        ProfileTheme("gravepony", "The Graveborn Foal", "EVEN DEATH COULD NOT BREAK YOUR SPIRIT.",
                     "An undead demon pony trots through a thornbound necropolis.",
                     "#dfa5c7", "#87627f", "#271a30", "#3d2b42", "#f3ede6", "#b7a6b3",
                     "🥀", "Eternities", "Legendary", "flame",
                     title_lines=("The Graveborn", "Foal"), finish="standard"),
        ProfileTheme("opalodyssey", "The Opal Odyssey", "NO HORIZON CAN HOLD YOU.",
                     "A skyship sails through the ribs of a fallen moon.",
                     "#d5c3e7", "#7e7694", "#20233a", "#36364f", "#f3ede6", "#b4afbd",
                     "🌙", "Eternities", "Legendary", "star",
                     title_lines=("The Opal", "Odyssey"), finish="standard"),
        ProfileTheme("dreamsovereign", "Sovereign of Dreams", "ALL THAT COULD BE BOWS BEFORE YOU.",
                     "A sleeping cosmic sovereign dreams entire living worlds.",
                     "#e7c5e5", "#897392", "#231a38", "#3b2f4d", "#f3ede6", "#baafbc",
                     "🪐", "Eternities", "Mythic", "covenant",
                     title_lines=("Sovereign of", "Dreams"), finish="prismatic"),
        ProfileTheme("eternityloom", "The Eternity Loom", "EVERY DESTINY RETURNS TO YOUR HANDS.",
                     "An ancient weaver spins galaxies into living silk.",
                     "#e5d1ad", "#867d71", "#1f2231", "#373740", "#f3ede6", "#b9b3ac",
                     "🧵", "Eternities", "Mythic", "covenant",
                     title_lines=("The Eternity", "Loom"), finish="prismatic"),
        ProfileTheme("sunweaver", "Genesis of the Sun", "THE FIRST DAWN STILL BURNS WITHIN YOU.",
                     "An ivory solar regent stands within an unfolding lotus palace of newborn suns.",
                     "#f8dfa8", "#a58f73", "#131e2e", "#293649", "#fff6e5", "#d5d4d3", "🌅", "Transcendent", "Transcendent", "covenant",
                     title_lines=("Genesis of", "the Sun"), finish="prismatic", layout="altar"),
        ProfileTheme("nightpalace", "The Velvet Singularity", "ETERNITY PAUSES WHEN YOU PASS.",
                     "An obsidian panther holds court above a dead star and an inverted platinum city.",
                     "#e1cceb", "#95839f", "#1b1427", "#30263e", "#fff0fa", "#d0c1dc", "🌌", "Transcendent", "Transcendent", "crown",
                     title_lines=("The Velvet", "Singularity"), finish="prismatic", layout="observatory"),
        ProfileTheme("worldtreeheart", "The Worldtree's Heart", "ALL LIFE REMEMBERS YOUR NAME.",
                     "A mahogany dryad queen shelters an entire living kingdom inside an emerald seed.",
                     "#e3e2b3", "#8aa493", "#132724", "#283d35", "#f6f6e3", "#cbd8c5", "🌳", "Transcendent", "Transcendent", "leaf",
                     title_lines=("The Worldtree's", "Heart"), finish="prismatic", layout="sanctum"),
        # Fables: story editions from The Tiamat Sacrament, drawn by render_fable.
        ProfileTheme("sacrament", "The Tiamat Sacrament", "THE ONLY HOPE TOOK WING.",
                     "Az'uar, Kelburn and Xandra above the waterfall kingdom.",
                     "#9ccfff", "#4d6f9c", "#08111f", "#132339", "#eef6ff", "#a8bdd8", "🐉", "Fables", "Fable", "wave",
                     title_lines=("The Tiamat", "Sacrament"), finish="prismatic", layout="sacrament"),
        ProfileTheme("gyle", "The Penitent Blade", "SOME DEBTS ARE PAID IN STEEL.",
                     "Gyle stands sword-down in the Nether Garrison at dawn.",
                     "#f09a86", "#7d4a42", "#120e0c", "#2a201b", "#faf1e6", "#cdb9a6", "⚔️", "Fables", "Fable", "claw",
                     title_lines=("The Penitent", "Blade"), finish="prismatic", layout="garrison"),
        ProfileTheme("ryjin", "Ry'jin's Dominion", "EVERY DRAGON'S BREATH IS MINE.",
                     "The Tyrant of Ildria and Az'golath in the breath laboratories.",
                     "#c6f06a", "#5c7a30", "#070b07", "#151d12", "#f1f8e4", "#adbd98", "🧪", "Fables", "Fable", "rift",
                     title_lines=("Ry'jin's", "Dominion"), finish="prismatic", layout="dominion"),
        ProfileTheme("tiamat", "Tiamat's Grace", "FROM HER SOUL, THE FIRST WINGS.",
                     "The goddess of creation and a guardian dragon above her sacred pool.",
                     "#d5b5f5", "#82709e", "#110f20", "#262139", "#faf3ff", "#c5b9d9", "💜", "Fables", "Fable", "wave",
                     title_lines=("Tiamat's", "Grace"), finish="prismatic", layout="creation"),
        # The Library's own edition: only readers who came in its Founding Week ever own it.
        ProfileTheme("founding", "The Founding Reader", "THE FIRST TO WALK THE LIBRARY.",
                     "Candlelight on the Fables Library's doors in its very first week.",
                     "#ead08e", "#6f8296", "#0a0e18", "#161d2b", "#fbf5e6", "#b9c2cf", "📖", "Fables", "Fable", "quill",
                     title_lines=("The Founding", "Reader"), finish="prismatic", layout="library"),
    )
}

for _key, _rarity, _motif in (
    ("classic", "Original", "diamond"), ("dragon", "Epic", "claw"),
    ("evil", "Epic", "claw"), ("chaos", "Epic", "rift"),
    ("good", "Rare", "sun"), ("forest", "Uncommon", "leaf"), ("frost", "Epic", "star"),
):
    THEMES[_key] = replace(THEMES[_key], rarity=_rarity, motif=_motif)

MOTIFS = ("diamond", "star", "rift", "sun", "gear", "claw", "leaf", "wave", "petal",
          "bubble", "lantern", "wing", "crown", "quill", "spire")


def _mix(color, target, amount):
    """Blend two #rrggbb colours; amount=0 keeps color, amount=1 returns target."""
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(target[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


def event_theme(key, name, *, accent, event, epithet="", description="", emoji="🎉",
                motif="star", title_lines=(), secondary=None, background=None,
                panel=None, text=None, muted=None, profile_flag=None):
    """Build an event-only theme. Only key, name, accent and event are required;
    the rest of the palette is derived from the accent colour.

    profile_flag names a BOOLEAN column on the profile table. Players whose
    column is true claim the theme automatically the next time their themes sync.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,31}", key):
        raise ValueError(f"Event theme key {key!r} must be 2-32 lowercase letters, digits or _, starting with a letter.")
    colours = dict(accent=accent, secondary=secondary, background=background, panel=panel, text=text, muted=muted)
    for field, value in colours.items():
        if value is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError(f"Event theme {key!r}: {field} must look like '#f2a65a', got {value!r}.")
    if motif not in MOTIFS:
        raise ValueError(f"Event theme {key!r}: motif must be one of {', '.join(MOTIFS)}.")
    if not name or len(name) > 60:
        raise ValueError(f"Event theme {key!r}: name must be 1-60 characters.")
    if not event:
        raise ValueError(f"Event theme {key!r}: event must name the event it belongs to.")
    if profile_flag is not None and not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", profile_flag):
        raise ValueError(f"Event theme {key!r}: profile_flag must be a lowercase profile column name, got {profile_flag!r}.")
    accent = accent.lower()
    return ProfileTheme(
        key, name,
        epithet or event.upper(),
        description or f"A limited cosmetic from {event}.",
        accent,
        secondary or _mix(accent, "#000000", .45),
        background or _mix(accent, "#0c0e14", .9),
        panel or _mix(accent, "#0c0e14", .82),
        text or _mix(accent, "#ffffff", .85),
        muted or _mix(accent, "#c4c4c4", .55),
        emoji, "Events", "Event", motif, tuple(title_lines), event=event,
        unlock_flag=profile_flag or "",
    )


# ===========================================================================
#  EVENT THEMES  —  GM / admin section
# ===========================================================================
# Event themes never drop from gameplay and are never auto-claimed. Players only
# get them when a GM awards them (or an event cog calls grant_event_theme).
#
# To add one:
#   1. Copy the example below into EVENT_THEMES and fill it in. Only key, name,
#      accent and event are required; every other colour is derived from accent.
#   2. Optional artwork: save it as assets/profile_themes/<key>.png (any size;
#      it is cropped to 1660x554). Without art the banner is a plain colour.
#   3. Reload the Profile cog. A typo raises a clear error and the old version
#      stays loaded.
#   4. In Discord:  $gmeventtheme list
#                   $gmeventtheme preview <key>        (renders it on your card)
#                   $gmeventtheme give @player1 @player2 <key>
#
# Unlock from the database instead of by hand: add profile_flag="column_name".
# Everyone whose profile.column_name is true gets the theme the next time they
# open $prpg or $prpg themes. The column is created (BOOLEAN, default false) on
# cog load if it does not exist yet. Your event code then only has to run:
#   UPDATE profile SET column_name = true WHERE "user" = $1;
#
# Never delete or rename an event theme once awarded: owners would lose it
# (their card falls back to classic). Leave old events in the list.
#
# Optional fields: epithet="SHOUTED TAGLINE.", description="One sentence.",
#   emoji="🎃", motif="lantern", title_lines=("Two-line", "Banner Title"),
#   secondary/background/panel/text/muted="#rrggbb" to override derived colours.
# Motifs: diamond star rift sun gear claw leaf wave petal bubble lantern wing
#   crown quill spire
#
# Example:
#   event_theme(
#       "harvest2026", "Harvest Moon Festival",
#       accent="#f2a65a", event="Harvest Festival 2026",
#       epithet="THE FIELDS REMEMBER EVERY HAND.",
#       description="Lanterns and a copper moon over the autumn fair.",
#       emoji="🎃", motif="lantern",
#   ),

EVENT_THEMES = (
    # Add event themes here ↓
    event_theme(
        "hallowmanor", "The Last Lantern",
        accent="#ff7a1a",
        event="Halloween 2026",
        emoji="🎃",
        motif="lantern",
        title_lines=("The Last", "Lantern"),
        epithet="ONE WINDOW STILL BURNS.",
        description="A house on the hill keeps a single orange window lit against the Halloween dark.",
    ),
    event_theme(
        "headlesshorseman", "Hollow Rider",
        accent="#f28c28",
        event="Halloween 2026",
        emoji="🎃",
        motif="claw",
        title_lines=("HOLLOW", "RIDER"),
        epithet="THE ROAD CLAIMS EVERY SOUL.",
        description="SEASONAL / RARE / CHRONICLE 50",
    ),

    event_theme(
        "ghostship", "Wraithwake",
        accent="#7bdac6",
        event="Halloween 2026",
        emoji="👻",
        motif="wave",
        title_lines=("WRAITHWAKE",),
        epithet="THE DEAD STILL TAKE THEIR TEA.",
        description="SEASONAL / RARE / CHRONICLE 51",
    ),

    event_theme(
        "dancingskeletons", "Bonecourt Revel",
        accent="#b58cff",
        event="Halloween 2026",
        emoji="💀",
        motif="crown",
        title_lines=("BONECOURT", "REVEL"),
        epithet="THE MUSIC OUTLIVED THE GUESTS.",
        description="SEASONAL / RARE / CHRONICLE 52",
    ),

    # Database-flag example: everyone who unlocked the Halloween class
    # (profile.spookyclass = true, set by cogs/halloween) gets this theme.
    # Remove the # from the six lines below to switch it on.
    # event_theme(
    #     "spooky_season", "Spooky Season",
    #     accent="#ff7a1a", event="Halloween",
    #     epithet="SOMETHING IS KNOCKING.", emoji="🎃", motif="lantern",
    #     profile_flag="spookyclass",
    # ),
)

for _theme in EVENT_THEMES:
    if _theme.key in THEMES:
        raise ValueError(f"Event theme key {_theme.key!r} is already used by {THEMES[_theme.key].name!r}.")
    THEMES[_theme.key] = _theme

ALIASES = {
    "normal": "classic", "plain": "classic", "default": "classic", "reset": "classic",
    "fire": "dragon", "sinister": "evil", "dark": "evil", "purple": "chaos",
    "light": "good", "angel": "good", "nature": "forest", "ice": "frost",
    "bunny": "moonbunny", "cow": "chickencow", "sea": "leviathan", "wolf": "bloodmoon",
    "dark elf": "darkelf", "wood elf": "woodelf", "high elf": "highelf",
    "dark_elf": "darkelf", "wood_elf": "woodelf", "high_elf": "highelf",
    "avatar tynfdarius": "tynfdarius", "mech-a-knight": "mechaknight",
    "umbracrown basilisk": "umbracrown", "void dragon": "voiddragon",
    "nullstar behemoth": "nullstar",
    "tiamat sacrament": "sacrament", "azuar": "sacrament", "az'uar": "sacrament",
    "goddess of creation": "tiamat", "tiamats grace": "tiamat",
    "kelburn": "sacrament", "xandra": "sacrament", "heroes": "sacrament",
    "penitent": "gyle", "penance": "gyle", "nether garrison": "gyle",
    "ry'jin": "ryjin", "ryjins dominion": "ryjin", "dominion": "ryjin", "tyrant": "ryjin",
    "az'golath": "ryjin", "azgolath": "ryjin",
    "founding reader": "founding", "founder": "founding", "library": "founding",
    # The Halloween manor docs and announcement call it hollowmanor / The Last Lantern.
    "hollowmanor": "hallowmanor", "the last lantern": "hallowmanor", "last lantern": "hallowmanor",
    **{theme.name.lower(): theme.key for theme in THEMES.values()},
}

COLLECTIONS = tuple(dict.fromkeys(theme.collection for theme in THEMES.values()))


def resolve_theme(value):
    """Strict for user input; callers explicitly decide when to fall back."""
    key = str(value or "").strip().lower()
    return THEMES.get(ALIASES.get(key, key))


@lru_cache(maxsize=32)
def theme_font(size, role="body"):
    filename = {"title": "Cinzel.ttf", "heading": "Lato-Bold.ttf"}.get(role, "Lato-Regular.ttf")
    try:
        return ImageFont.truetype(str(ASSET_ROOT / "fonts" / filename), size)
    except OSError:
        return ImageFont.truetype(str(ASSET_ROOT.parents[1] / "EightBitDragon-anqx.ttf"), size)


@lru_cache(maxsize=6)
def _banner(key):
    """Cache only decoded source banners, never a user's composed card."""
    with Image.open(ASSET_ROOT / f"{key}.png") as source:
        return ImageOps.fit(source.convert("RGB"), (1660, 554), method=Image.Resampling.LANCZOS)


def theme_background(theme, size):
    canvas = Image.new("RGBA", size, theme.background)
    draw = ImageDraw.Draw(canvas)
    width, height = size
    # Engraved diagonals and a double metal rim; all decoration stays in the gutters.
    for x in range(-height, width, 70):
        draw.line((x, 0, x + height, height), fill=theme.panel, width=1)
    draw.rounded_rectangle((24, 24, width - 24, height - 24), 24,
                           fill=theme.background, outline=theme.secondary, width=2)
    draw.rounded_rectangle((35, 35, width - 35, height - 35), 19,
                           outline=theme.panel, width=2)
    for x in (24, width - 24):
        for y in (24, height - 24):
            draw_ornament(draw, x, y, 13, theme)
    return canvas


def draw_ornament(draw, x, y, radius, theme):
    """Small engraved emblems, used on frames and panels; never over live text."""
    r, ink = radius, theme.accent
    motif = theme.motif
    if motif == "covenant":
        draw.ellipse((x-r*.45, y-r*.45, x+r*.45, y+r*.45), outline="#f6edda", width=2)
        for i in range(8):
            a = i * math.tau / 8
            cx, cy = x+math.cos(a)*r*.8, y+math.sin(a)*r*.8
            tip = r*.2
            draw.polygon([(cx, cy-tip), (cx+tip*.6, cy), (cx, cy+tip), (cx-tip*.6, cy)],
                         fill=ink if i % 2 else "#bcdde6")
        draw.ellipse((x-2, y-2, x+2, y+2), fill="#fff5df")
    elif motif == "lantern":
        draw.line((x, y-r, x, y-r*.6), fill=ink, width=2)
        draw.ellipse((x-r*.55, y-r*.6, x+r*.55, y+r*.55), outline=ink, width=2)
        draw.line((x, y-r*.5, x, y+r*.5), fill=ink, width=1)
        draw.line((x-r*.35, y-r*.6, x+r*.35, y-r*.6), fill=ink, width=2)
        draw.line((x, y+r*.55, x, y+r), fill=ink, width=2)
    elif motif == "wing":
        for sign in (-1, 1):
            draw.polygon([(x, y), (x+sign*r, y-r*.75),
                          (x+sign*r*.7, y+r*.3), (x+sign*r*.2, y+r*.7)], outline=ink)
            draw.line((x, y-r*.5, x+sign*r*.25, y-r), fill=ink, width=1)
        draw.line((x, y-r*.4, x, y+r*.65), fill=ink, width=2)
    elif motif == "crown":
        draw.line([(x-r*.75, y+r*.5), (x-r, y-r*.5), (x-r*.3, y),
                   (x, y-r), (x+r*.3, y), (x+r, y-r*.5),
                   (x+r*.75, y+r*.5), (x-r*.75, y+r*.5)], fill=ink, width=2)
        draw.line((x-r*.6, y+r*.8, x+r*.6, y+r*.8), fill=ink, width=1)
    elif motif == "quill":
        draw.line((x-r*.8, y+r, x+r*.65, y-r*.8), fill=ink, width=2)
        draw.polygon([(x-r*.35, y+r*.2), (x-r*.25, y-r*.6),
                      (x+r*.75, y-r), (x+r*.65, y-r*.05)], outline=ink)
    elif motif == "spire":
        draw.line([(x-r*.75, y+r*.7), (x-r*.75, y-r*.1), (x, y-r),
                   (x+r*.75, y-r*.1), (x+r*.75, y+r*.7)], fill=ink, width=2)
        draw.line((x, y-r*.6, x, y+r*.9), fill=ink, width=1)
        draw.ellipse((x-r*.2, y-r*.15, x+r*.2, y+r*.25), fill=ink)
    elif motif in {"sun", "gear"}:
        count = 12 if motif == "sun" else 8
        draw.ellipse((x-r*.55, y-r*.55, x+r*.55, y+r*.55), outline=ink, width=2)
        for i in range(count):
            a = i * math.tau / count
            draw.line((x+math.cos(a)*r*.75, y+math.sin(a)*r*.75,
                       x+math.cos(a)*r, y+math.sin(a)*r), fill=ink, width=2 if motif == "sun" else 4)
    elif motif in {"star", "rift", "diamond"}:
        tips = 4 if motif != "rift" else 3
        points = []
        for i in range(tips * 2):
            a = i * math.pi / tips - math.pi / 2
            length = r if i % 2 == 0 else r * .32
            points.append((x+math.cos(a)*length, y+math.sin(a)*length))
        draw.polygon(points, fill=ink)
        if motif == "rift":
            draw.arc((x-r, y-r, x+r, y+r), 30, 230, fill=ink, width=1)
    elif motif == "claw":
        for offset in (-7, 0, 7):
            draw.polygon([(x+offset-4, y+r), (x+offset+4, y-r), (x+offset+1, y+r*.3)], fill=ink)
    elif motif == "leaf":
        draw.line((x-r*.7, y+r*.7, x+r*.7, y-r*.7), fill=ink, width=2)
        draw.arc((x-r, y-r*.8, x+r*.7, y+r), 180, 300, fill=ink, width=2)
        draw.arc((x-r*.7, y-r, x+r, y+r*.8), 0, 120, fill=ink, width=2)
    elif motif == "wave":
        for offset in (-6, 0, 6):
            draw.line([(x-r+i*r/10, y+offset+math.sin(i*math.pi/10)*3) for i in range(21)], fill=ink, width=2)
    elif motif == "petal":
        for i in range(5):
            a = i * math.tau / 5
            cx, cy = x+math.cos(a)*r*.55, y+math.sin(a)*r*.55
            draw.ellipse((cx-r*.32, cy-r*.32, cx+r*.32, cy+r*.32), outline=ink, width=2)
        draw.ellipse((x-2, y-2, x+2, y+2), fill=ink)
    elif motif == "flame":
        draw.polygon([(x, y-r), (x+r*.3, y-r*.1), (x+r*.7, y-r*.4),
                      (x+r*.7, y+r*.5), (x, y+r), (x-r*.7, y+r*.5),
                      (x-r*.7, y), (x-r*.25, y+r*.1)], outline=ink, width=2)
    elif motif == "bolt":
        draw.polygon([(x+r*.3, y-r), (x-r*.7, y+r*.15), (x-r*.05, y+r*.15),
                      (x-r*.3, y+r), (x+r*.7, y-r*.15), (x+r*.05, y-r*.15)], outline=ink, width=2)
    elif motif == "scale":
        for dx, dy in ((-r*.45, -r*.35), (r*.45, -r*.35), (0, r*.35)):
            draw.arc((x+dx-r*.5, y+dy-r*.6, x+dx+r*.5, y+dy+r*.6), 0, 180, fill=ink, width=2)
    elif motif == "bubble":
        for dx, dy, size in ((-5, 3, 7), (6, -5, 5), (7, 9, 3)):
            draw.ellipse((x+dx-size, y+dy-size, x+dx+size, y+dy+size), outline=ink, width=2)


def _foil_color(position):
    """A deterministic pearl/gold/opal finish; no user-specific cache or randomness."""
    stops = ((168, 132, 81), (247, 220, 165), (255, 251, 231),
             (171, 213, 228), (201, 178, 219), (247, 220, 165), (168, 132, 81))
    index = (position % 1) * (len(stops) - 1)
    left = int(index)
    fraction = index - left
    return tuple(round(a + (b-a)*fraction) for a, b in zip(stops[left], stops[left+1]))


def _draw_foil_title(image, position, text, font):
    """Tint only title glyphs; the source artwork and dark outline stay intact."""
    x, y = position
    mask = Image.new("L", (math.ceil(font.getlength(text)) + 8, 110))
    ImageDraw.Draw(mask).text((4, 0), text, font=font, fill=255)
    foil = Image.new("RGB", mask.size)
    draw = ImageDraw.Draw(foil)
    for row in range(mask.height):
        draw.line((0, row, mask.width, row), fill=_foil_color(.1 + row / 150))
    image.paste(foil, (x-4, y), mask)


def _add_prismatic_finish(image, theme):
    """Covenant's jeweled rails and avatar halo occupy reserved decoration space."""
    draw = ImageDraw.Draw(image)
    width, height = image.size
    draw.rounded_rectangle((7, 7, width-8, height-8), radius=24, outline=theme.secondary, width=1)
    for y in range(32, height-32):
        color = _foil_color(y / height)
        for x in (14, width-15):
            draw.line((x, y, x+1, y), fill=color)
    for x in range(32, width-32):
        color = _foil_color(x / width)
        for y in (14, height-15):
            draw.line((x, y, x, y+1), fill=color)
    for x in (24, width-25):
        for y in (24, height-25):
            draw_ornament(draw, x, y, 18, theme)
    # A seven-gem collar beneath the painting, above all profile panels.
    draw.line((70, 533, width-70, 533), fill=theme.secondary, width=1)
    jewels = ("#b9eac6", "#d2edff", "#efb0a3", "#aae7e1", "#edccab", "#c6bdff", "#f6dfa6")
    for index, color in enumerate(jewels):
        x, y = 126 + index * (width-252) / 6, 533
        draw.polygon([(x, y-10), (x+16, y), (x, y+10), (x-16, y)],
                     fill=theme.background, outline=theme.accent, width=1)
        draw.polygon([(x, y-6), (x+6, y), (x, y+6), (x-6, y)], fill=color)
        draw.line((x-26, y-3, x-20, y), fill=color)
        draw.line((x+20, y, x+26, y-3), fill=color)
    # Avatar center is (221, 265) in the 940px stat card, shifted by the 520px banner.
    cx, cy = 221, 785
    for start in range(0, 360, 3):
        for radius in (124, 128):
            draw.arc((cx-radius, cy-radius, cx+radius, cy+radius), start, start+3,
                     fill=_foil_color(start / 360), width=2 if radius == 124 else 1)
    for i in range(12):
        angle = i * math.tau / 12
        x, y = cx+math.cos(angle)*128, cy+math.sin(angle)*128
        draw.polygon([(x, y-3), (x+3, y), (x, y+3), (x-3, y)], fill=_foil_color(i / 12))
    draw.rounded_rectangle((64, 416, 399, 449), radius=9,
                           fill=theme.background, outline=theme.accent, width=1)
    draw.text((82, 423), "P R I S M A T I C   C O V E N A N T",
              font=theme_font(15, "heading"), fill="#f4dfb6")


TRANSCENDENT_SIZE = (1800, 2400)
_SS = 2  # Filigree is drawn at twice the size and filtered down, so metal edges stay smooth.
_CREST = (900, 975)
# Glass panels: three stat plaques, armament/world/legacy, companion, quest footer.
_FOLIO_PANELS = ((130, 1352, 590, 1514), (670, 1352, 1130, 1514), (1210, 1352, 1670, 1514),
                 (72, 1556, 1100, 2284), (1140, 1556, 1728, 2284), (210, 2294, 1590, 2348))
_FOLIO_HEADERS = ((100, 1568, "I   /   ARMAMENT", 1070), (100, 1810, "II   /   WORLD & ALLEGIANCE", 1070),
                  (100, 2058, "III   /   LEGACY", 1070), (1180, 1568, "IV   /   SOUL COMPANION", 1700))

# Every edition is minted from its own metal, jewel and light. `foil` runs across the
# engraved frame; `ink` runs top-to-bottom through chrome lettering.
_EDITIONS = {
    "altar": dict(
        foil=((126, 84, 36), (214, 160, 80), (255, 234, 180), (255, 252, 238), (242, 200, 120), (170, 112, 50), (252, 222, 156)),
        ink=((255, 252, 238), (255, 232, 172), (238, 192, 110), (160, 108, 50), (246, 210, 136), (255, 246, 214)),
        glow=(255, 190, 100), jewel=((255, 196, 92), (255, 248, 220), (150, 84, 20))),
    "observatory": dict(
        foil=((86, 80, 108), (184, 176, 206), (246, 244, 255), (212, 186, 246), (255, 238, 252), (150, 138, 180), (230, 222, 248)),
        ink=((255, 255, 255), (236, 228, 252), (198, 182, 230), (116, 102, 150), (216, 198, 244), (248, 242, 255)),
        glow=(186, 150, 255), jewel=((176, 128, 255), (246, 234, 255), (74, 44, 130))),
    "sanctum": dict(
        foil=((66, 92, 56), (168, 172, 92), (246, 232, 168), (255, 250, 226), (170, 220, 164), (206, 164, 90), (240, 222, 156)),
        ink=((255, 254, 236), (242, 236, 178), (206, 194, 112), (104, 122, 62), (214, 228, 160), (248, 250, 222)),
        glow=(160, 236, 140), jewel=((72, 208, 140), (230, 255, 222), (18, 90, 60))),
}


def _edition(theme):
    return _EDITIONS.get(theme.layout, _EDITIONS["altar"])


def _edition_number(theme):
    keys = [t.key for t in THEMES.values() if t.rarity == "Transcendent"]
    return keys.index(theme.key) + 1 if theme.key in keys else 1, max(1, len(keys))


def _roman(number):
    out = ""
    for value, glyph in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while number >= value:
            out, number = out + glyph, number - value
    return out


def _rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _lerp(stops, t):
    t = max(0.0, min(1.0, t))
    index = t * (len(stops) - 1)
    left = min(int(index), len(stops) - 2)
    fraction = index - left
    return tuple(round(a + (b-a)*fraction) for a, b in zip(stops[left], stops[left+1]))


@lru_cache(maxsize=1)
def _radial():
    n = 96
    c = (n - 1) / 2
    image = Image.new("L", (n, n))
    image.putdata([round(255 * max(0.0, 1 - math.hypot(x-c, y-c)/c) ** 2.2) for y in range(n) for x in range(n)])
    return image


@lru_cache(maxsize=4)
def _disc_mask(diameter):
    big = Image.new("L", (diameter*4, diameter*4))
    ImageDraw.Draw(big).ellipse((0, 0, diameter*4 - 1, diameter*4 - 1), fill=255)
    return big.resize((diameter, diameter), Image.Resampling.LANCZOS)


def _light(canvas, box, color, strength=1.0):
    """Screen a soft elliptical light onto the canvas. Light only ever brightens."""
    x1, y1, x2, y2 = (round(v) for v in box)
    size = (max(1, x2-x1), max(1, y2-y1))
    mask = _radial().resize(size, Image.Resampling.BICUBIC)
    if strength != 1:
        mask = mask.point(lambda v: min(255, round(v*strength)))
    light = Image.composite(Image.new("RGB", size, color), Image.new("RGB", size), mask)
    canvas.paste(ImageChops.screen(canvas.crop((x1, y1, x2, y2)), light), (x1, y1))


def _screen(canvas, mask, color, strength=1.0):
    if strength != 1:
        mask = mask.point(lambda v: min(255, round(v*strength)))
    layer = Image.composite(Image.new("RGB", canvas.size, color), Image.new("RGB", canvas.size), mask)
    return ImageChops.screen(canvas, layer)


def _foil_sheet(stops, size):
    """A diagonal metallic sweep with a gentle ripple, like light moving over foil."""
    sw, sh = size[0] // 10, size[1] // 10
    ring = stops + stops[:1]
    small = Image.new("RGB", (sw, sh))
    small.putdata([_lerp(ring, (x/sw*1.1 + y/sh*1.7 + .06*math.sin(x/sw*11 + y/sh*5)) % 1)
                   for y in range(sh) for x in range(sw)])
    return small.resize(size, Image.Resampling.BICUBIC)


def _holo_sheet(size):
    """Low-saturation iridescence laid over the whole folio like a collector foil."""
    sw, sh = 60, 80
    small = Image.new("RGB", (sw, sh))
    small.putdata([tuple(round(c*255) for c in colorsys.hsv_to_rgb((x/sw*.7 + y/sh*1.3) % 1, .42, 1))
                   for y in range(sh) for x in range(sw)])
    return small.resize(size, Image.Resampling.BICUBIC)


def _foil_text(canvas, x, y, value, font, ink, glow=None, strength=.75, center=False):
    """Chrome lettering: soft drop shadow, coloured bloom, then a vertical metal gradient."""
    value = str(value)
    if not value:
        return
    if center:
        x -= font.getlength(value) / 2
    x, y = round(x), round(y)
    _, top, right, bottom = font.getbbox(value)
    pad = max(8, font.size // 3)
    mask = Image.new("L", (right + pad*2, bottom + pad*2))
    ImageDraw.Draw(mask).text((pad, pad), value, font=font, fill=255)
    ox, oy = x - pad, y - pad
    box = (ox, oy, ox + mask.width, oy + mask.height)
    region = canvas.crop(box)
    shadow = mask.filter(ImageFilter.GaussianBlur(max(1.5, font.size/14)))
    drop = max(1, font.size // 26)
    region.paste((4, 5, 9), (0, drop, mask.width, mask.height + drop), shadow)
    if glow:
        bloom = mask.filter(ImageFilter.GaussianBlur(max(2, font.size/5)))
        bloom = bloom.point(lambda v: min(255, round(v*strength)))
        region = ImageChops.screen(region, Image.composite(Image.new("RGB", mask.size, glow), Image.new("RGB", mask.size), bloom))
    span = max(1, bottom - top)
    strip = Image.new("RGB", (1, mask.height))
    strip.putdata([_lerp(ink, (row - pad - top) / span) for row in range(mask.height)])
    region.paste(strip.resize(mask.size, Image.Resampling.NEAREST), (0, 0), mask)
    canvas.paste(region, (ox, oy))


def _glint(canvas, x, y, size, color):
    """A four-point star of light with a soft core."""
    n = int(size * 2) + 6
    c = n // 2
    mask = Image.new("L", (n, n))
    d = ImageDraw.Draw(mask)
    for i in range(c):
        value = round(255 * (1 - i/c) ** 2.4)
        thick = 1 if i > c * .25 else 2
        for dx, dy in ((i, 0), (-i, 0), (0, i), (0, -i)):
            d.line((c+dx - (thick-1)*(dy != 0), c+dy - (thick-1)*(dx != 0),
                    c+dx + (thick-1)*(dy != 0), c+dy + (thick-1)*(dx != 0)), fill=value)
        if i < c * .4:
            diag = round(150 * (1 - i/(c*.4)) ** 2)
            for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                d.point((c + sx*i*.72, c + sy*i*.72), fill=diag)
    core = _radial().resize((max(2, int(size*.7)),) * 2, Image.Resampling.BICUBIC)
    mask.paste(ImageChops.lighter(mask.crop((c - core.width//2, c - core.height//2, c - core.width//2 + core.width,
                                             c - core.height//2 + core.height)), core), (c - core.width//2, c - core.height//2))
    mask = mask.filter(ImageFilter.GaussianBlur(.7))
    light = Image.composite(Image.new("RGB", mask.size, color), Image.new("RGB", mask.size), mask)
    box = (round(x) - c, round(y) - c, round(x) - c + n, round(y) - c + n)
    canvas.paste(ImageChops.screen(canvas.crop(box), light), box[:2])


class _Pen:
    """Draws in 1x folio coordinates onto a supersampled mask."""

    def __init__(self, draw, scale=_SS):
        self.d, self.s = draw, scale

    def _w(self, width):
        return max(1, round(width * self.s))

    def line(self, points, width=1.0, fill=255):
        self.d.line([(x*self.s, y*self.s) for x, y in points], fill=fill, width=self._w(width), joint="curve")

    def poly(self, points, fill=255):
        self.d.polygon([(x*self.s, y*self.s) for x, y in points], fill=fill)

    def ring(self, x, y, r, width=1.0, fill=255):
        s = self.s
        self.d.ellipse(((x-r)*s, (y-r)*s, (x+r)*s, (y+r)*s), outline=fill, width=self._w(width))

    def disc(self, x, y, r, fill=255):
        s = self.s
        self.d.ellipse(((x-r)*s, (y-r)*s, (x+r)*s, (y+r)*s), fill=fill)

    def rrect(self, box, radius, width=1.0, fill=255):
        self.d.rounded_rectangle([v*self.s for v in box], radius=radius*self.s, outline=fill, width=self._w(width))

    def diamond(self, x, y, r, width=1.0, fill=255, stretch=1.0):
        self.line([(x, y-r), (x+r*stretch, y), (x, y+r), (x-r*stretch, y), (x, y-r)], width, fill)

    def leaf(self, x, y, angle, length, breadth, fill=255):
        ux, uy = math.cos(angle), math.sin(angle)
        points = []
        for i in range(13):
            t = i / 12
            half = math.sin(t * math.pi) * breadth / 2
            points.append((x + ux*length*t - uy*half, y + uy*length*t + ux*half))
        for i in range(11, 0, -1):
            t = i / 12
            half = math.sin(t * math.pi) * breadth / 2
            points.append((x + ux*length*t + uy*half, y + uy*length*t - ux*half))
        self.poly(points, fill)


def _steps(start, stop, count):
    return [start + (stop-start) * i / count for i in range(count + 1)]


def _chamfer(box, cut):
    x1, y1, x2, y2 = box
    return [(x1+cut, y1), (x2-cut, y1), (x2, y1+cut), (x2, y2-cut), (x2-cut, y2),
            (x1+cut, y2), (x1, y2-cut), (x1, y1+cut), (x1+cut, y1)]


def _draw_folio_frame(pen, layout, w, h, gems):
    pen.rrect((12, 12, w-12, h-12), 26, 3)
    pen.rrect((22, 22, w-22, h-22), 20, 1)
    pen.rrect((30, 30, w-30, h-30), 14, 1.6)
    for cx, cy, sx, sy in ((30, 30, 1, 1), (w-30, 30, -1, 1), (30, h-30, 1, -1), (w-30, h-30, -1, -1)):
        def p(u, v, cx=cx, cy=cy, sx=sx, sy=sy):
            return (cx + sx*u, cy + sy*v)
        for radius, width in ((64, 2.2), (78, 1)):
            pen.line([p(radius*math.cos(t), radius*math.sin(t)) for t in _steps(0, math.pi/2, 28)], width)
        for flip in (False, True):
            def q(u, v, flip=flip, p=p):
                return p(v, u) if flip else p(u, v)
            pen.line([q(80, 9), q(330, 9)], 1.3)
            pen.line([q(80, 15), q(210, 15)], .8)
            for centre, size in ((110, 12), (158, 8)):
                pen.line([q(centre + size*(1 - t/13)*math.cos(t), 24 + size*(1 - t/13)*math.sin(t))
                          for t in _steps(0, 13, 70)], 1.2)
            (ax, ay), (bx, by) = q(0, 0), q(1, 0)
            pen.leaf(*q(236, 15), math.atan2(by - ay, bx - ax), 34, 8)
        jewel = p(40, 40)
        pen.diamond(*jewel, 17, 1.6)
        gems.append((*jewel, 11))
        if layout == "altar":
            for i in range(16):
                a = i * math.tau / 16
                inner, outer = 21, 30 if i % 2 else 36
                pen.line([(jewel[0] + math.cos(a)*inner, jewel[1] + math.sin(a)*inner),
                          (jewel[0] + math.cos(a)*outer, jewel[1] + math.sin(a)*outer)], 1.2 if i % 2 else 2)
        elif layout == "observatory":
            pen.line([(jewel[0] + 27*math.cos(t), jewel[1] + 27*math.sin(t)) for t in _steps(.5, 5.2, 40)], 1.6)
            for a in (math.pi/4, 3*math.pi/4, 5*math.pi/4, 7*math.pi/4):
                pen.disc(jewel[0] + math.cos(a)*33, jewel[1] + math.sin(a)*33, 2.2)
        else:
            base = math.atan2(sy, sx)
            for offset in (-.55, 0, .55):
                pen.leaf(jewel[0] + math.cos(base+offset)*18, jewel[1] + math.sin(base+offset)*18,
                         base + offset, 26, 9)
    for x, sx in ((30, 1), (w-30, -1)):
        pen.diamond(x, 1200, 22, 1.6)
        pen.diamond(x, 1200, 30, 1)
        gems.append((x, 1200, 10))
        for start, stop in ((1060, 1166), (1234, 1340)):
            pen.line([(x + sx*8, start), (x + sx*8, stop)], 1.2)
    for y in (30, h-30):
        pen.diamond(900, y, 18, 1.6, stretch=1.6)
        gems.append((900, y, 9))
        for sign in (-1, 1):
            pen.line([(900 + sign*34, y), (900 + sign*150, y)], 3)
            pen.disc(900 + sign*160, y, 3.2)


def _draw_folio_crest(pen, layout, gems):
    cx, cy = _CREST
    pen.ring(cx, cy, 113, 3)
    pen.ring(cx, cy, 119, 1)
    pen.ring(cx, cy, 150, 1)
    pen.ring(cx, cy, 155, 2.4)
    for i in range(72):
        a = i * math.tau / 72
        pen.disc(cx + math.cos(a)*162, cy + math.sin(a)*162, 3.2 if i % 6 == 0 else 1.5)
    if layout == "altar":
        for i in range(0, 360, 5):
            a = math.radians(i)
            reach = abs(math.cos(a)) ** 3
            length = (34 if i % 30 == 0 else 18 if i % 15 == 0 else 9) * (.35 + 2.2*reach)
            half = math.radians(1.6 if i % 30 == 0 else .8)
            r0, r1 = 170, 170 + length
            pen.poly([(cx + math.cos(a-half)*r0, cy + math.sin(a-half)*r0), (cx + math.cos(a)*r1, cy + math.sin(a)*r1),
                      (cx + math.cos(a+half)*r0, cy + math.sin(a+half)*r0)], 255 if i % 15 == 0 else 190)
    elif layout == "observatory":
        pen.line(_orbit_halves(0)[0], 2.6)
        pen.line(_orbit_halves(1)[0], 1, 150)
        pen.line([(cx, cy-176), (cx+262, cy), (cx, cy+170), (cx-262, cy), (cx, cy-176)], 1, 200)
        for a in (-2.3, -.9):
            x, y = _orbit_point(0, a)
            pen.disc(x, y, 6)
    else:
        for sign in (-1, 1):
            start, stop = math.radians(90 - sign*22), math.radians(90 - sign*205)
            angles = _steps(start, stop, 48)
            pen.line([(cx + math.cos(a)*176, cy + math.sin(a)*176) for a in angles], 2)
            for k, a in enumerate(angles[2:-1:3]):
                x, y = cx + math.cos(a)*176, cy + math.sin(a)*176
                tangent = a - sign*math.pi/2
                length = 30 - k*.6
                pen.leaf(x, y, tangent - sign*.55, length, 11)
                pen.leaf(x, y, tangent + sign*.35, length*.85, 10)
        for a in (math.radians(-90), math.radians(90 + 205), math.radians(90 - 205)):
            x, y = cx + math.cos(a)*176, cy + math.sin(a)*176
            for i in range(5):
                b = i * math.tau / 5 - math.pi/2
                pen.leaf(x, y, b, 14, 8)
            gems.append((x, y, 4))
    if layout != "observatory":
        for sign in (-1, 1):
            pen.line([(cx + sign*244, cy), (cx + sign*318, cy)], 1.4)
            pen.diamond(cx + sign*326, cy, 7, 1.4)


def _orbit_point(index, t):
    cx, cy = _CREST
    rx, ry, tilt = ((292, 60, -.17), (252, 44, -.17))[index]
    x, y = rx*math.cos(t), ry*math.sin(t)
    return (cx + x*math.cos(tilt) - y*math.sin(tilt), cy + x*math.sin(tilt) + y*math.cos(tilt))


@lru_cache(maxsize=2)
def _orbit_halves(index):
    """Back (upper) and front (lower) halves of the accretion ring around the crest."""
    back = [_orbit_point(index, t) for t in _steps(math.pi, math.tau, 90)]
    front = [_orbit_point(index, t) for t in _steps(0, math.pi, 90)]
    return back, front


def _draw_folio_etching(draw, layout, rng, w, h):
    """Faint light-etched patterns in the dark field; painted with the edition glow."""
    cx, cy = _CREST
    if layout == "altar":
        for i in range(56):
            a0 = i * math.tau / 56
            a1 = a0 + math.tau / 112
            draw.polygon([(cx, cy), (cx + 2600*math.cos(a0), cy + 2600*math.sin(a0)),
                          (cx + 2600*math.cos(a1), cy + 2600*math.sin(a1))], fill=15)
        for r in range(250, 1700, 96):
            draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline=30, width=1)
    elif layout == "observatory":
        for _ in range(1300):
            x, y = rng.uniform(36, w-36), rng.uniform(600, h-36)
            b = rng.random() ** 3
            r = .6 + b * 1.7
            draw.ellipse((x-r, y-r, x+r, y+r), fill=round(80 + 175*b))
        for _ in range(8):
            x, y = rng.uniform(120, w-120), rng.uniform(1300, h-140)
            points = [(x, y)]
            for _ in range(rng.randint(3, 5)):
                x = min(w-60, max(60, x + rng.uniform(-150, 150)))
                y = min(h-60, max(1200, y + rng.uniform(-110, 110)))
                points.append((x, y))
            draw.line(points, fill=55, width=1)
            for px, py in points:
                draw.ellipse((px-2.4, py-2.4, px+2.4, py+2.4), fill=230)
        for rx, ry in ((760, 190), (1060, 280), (1400, 380)):
            points = []
            for t in _steps(0, math.tau, 240):
                x, y = rx*math.cos(t), ry*math.sin(t)
                points.append((cx + x*math.cos(-.17) - y*math.sin(-.17), cy + x*math.sin(-.17) + y*math.cos(-.17)))
            draw.line(points, fill=34, width=1)
    else:
        for x0, side in ((52, 1), (w-52, -1)):
            vine = [(x0 + side*9*math.sin(y/80), y) for y in range(880, h-70, 4)]
            draw.line(vine, fill=80, width=2)
            for k, y in enumerate(range(900, h-90, 58)):
                x = x0 + side*9*math.sin(y/80)
                a = -math.pi/2 + (.9 if k % 2 else -.9)
                leaf = []
                for i in range(13):
                    t = i / 12
                    half = math.sin(t*math.pi) * 5
                    leaf.append((x + math.cos(a)*28*t - math.sin(a)*half, y + math.sin(a)*28*t + math.cos(a)*half))
                for i in range(11, 0, -1):
                    t = i / 12
                    half = math.sin(t*math.pi) * 5
                    leaf.append((x + math.cos(a)*28*t + math.sin(a)*half, y + math.sin(a)*28*t - math.cos(a)*half))
                draw.polygon(leaf, fill=95)
        for r in range(230, 1500, 120):
            draw.arc((cx-r, cy-r*.62, cx+r, cy+r*.62), 200, 340, fill=26, width=1)


def _draw_guilloche(pen):
    """Banknote-style braided rosette behind the crest; faint enough to sit under text."""
    cx, cy = _CREST
    for base, amp, petals, strands in ((372, 20, 44, 7), (322, 12, 60, 5)):
        for j in range(strands):
            phase = j * math.tau / (petals * strands) * petals / 2
            points = []
            for t in _steps(0, math.tau, 900):
                r = base + amp * math.sin(petals*t + phase * petals)
                points.append((cx + r*math.cos(t), cy + r*.5*math.sin(t)))
            pen.line(points, .7, 48)


def _draw_ring_text(mask, top, bottom, role, centre, radius):
    """Engrave a coin legend: the top arc reads clockwise, the bottom arc left-to-right."""
    cx, cy = centre
    size, tracking = 16, 2.5
    while True:
        font = theme_font(size, role)
        spans = [sum(font.getlength(ch) + tracking for ch in value) / radius for value in (top, bottom)]
        if sum(spans) < math.radians(318) or size <= 11:
            break
        size -= 1
    for value, span, lower in ((top, spans[0], False), (bottom, spans[1], True)):
        # Angles run clockwise from twelve o'clock; the lower arc walks backwards.
        angle = (math.pi + span/2) if lower else -span/2
        for ch in value:
            step = (font.getlength(ch) + tracking) / radius
            middle = angle - step/2 if lower else angle + step/2
            angle = angle - step if lower else angle + step
            if not ch.strip():
                continue
            glyph = Image.new("L", (size*2, size*2))
            ImageDraw.Draw(glyph).text((size, size), ch, font=font, fill=255, anchor="mm")
            glyph = glyph.rotate(-math.degrees(middle - math.pi if lower else middle), resample=Image.Resampling.BICUBIC)
            x = round(cx + math.sin(middle)*radius - glyph.width/2)
            y = round(cy - math.cos(middle)*radius - glyph.height/2)
            mask.paste(255, (x, y, x + glyph.width, y + glyph.height), glyph)
    draw = ImageDraw.Draw(mask)
    for middle in ((spans[0]/2 + math.pi - spans[1]/2) / 2, -(spans[0]/2 + math.pi - spans[1]/2) / 2):
        x, y = cx + math.sin(middle)*radius, cy - math.cos(middle)*radius
        draw.polygon([(x, y-5), (x+5, y), (x, y+5), (x-5, y)], fill=255)


def _paint_gems(canvas, gems, jewel, foil):
    draw = ImageDraw.Draw(canvas)
    base, light, deep = jewel
    for x, y, r in gems:
        _light(canvas, (x - r*4, y - r*4, x + r*4, y + r*4), base, .9)
        draw.polygon([(x, y-r), (x+r, y), (x, y+r), (x-r, y)], fill=base)
        draw.polygon([(x, y-r), (x, y), (x-r, y)], fill=_lerp((base, light), .55))
        draw.polygon([(x, y), (x+r, y), (x, y+r)], fill=_lerp((base, deep), .5))
        draw.polygon([(x, y-r), (x+r, y), (x, y+r), (x-r, y)], outline=foil[3])
        draw.ellipse((x - r*.55 - 1.5, y - r*.55 - 1.5, x - r*.55 + 1.5, y - r*.55 + 1.5), fill=(255, 255, 255))


@lru_cache(maxsize=3)
def _poster_art(key, size):
    with Image.open(ASSET_ROOT / f"{key}.png") as source:
        return ImageOps.fit(source.convert("RGB"), size, method=Image.Resampling.LANCZOS)


@lru_cache(maxsize=3)
def _transcendent_base(key):
    """Everything that depends only on the edition, never on a player. Callers copy it."""
    theme = THEMES[key]
    ed = _edition(theme)
    w, h = TRANSCENDENT_SIZE
    cx, cy = _CREST
    bg = _rgb(theme.background)
    glow = ed["glow"]
    canvas = Image.new("RGB", (w, h), bg)
    try:
        art = _poster_art(key, (w, 900))
    except (OSError, ValueError):
        art = None

    if art is not None:
        # The painting's own colours, reflected and diffused down the folio.
        wash = art.crop((0, 380, w, 900)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        wash = wash.resize((18, 24), Image.Resampling.BOX).resize((w, h), Image.Resampling.BICUBIC)
        fade = Image.linear_gradient("L").resize((w, h)).point(lambda v: round(170 - v*.5))
        canvas = Image.composite(wash, canvas, fade)
        canvas = Image.blend(Image.new("RGB", (w, h), bg), canvas, .8)
    _light(canvas, (cx-760, cy-560, cx+760, cy+560), glow, .45)
    _light(canvas, (-400, 1500, 1000, 2800), glow, .14)
    _light(canvas, (800, 1400, 2200, 2700), glow, .14)

    etch = Image.new("L", (w, h))
    _draw_folio_etching(ImageDraw.Draw(etch), theme.layout, random.Random(key), w, h)
    if theme.layout == "sanctum":
        motes = Image.new("L", (w, h))
        md = ImageDraw.Draw(motes)
        rng = random.Random(key + "motes")
        for _ in range(95):
            x, y, r = rng.uniform(40, w-40), rng.uniform(700, h-40), rng.uniform(1.4, 4.2)
            md.ellipse((x-r, y-r, x+r, y+r), fill=255)
        etch = ImageChops.lighter(etch, motes.filter(ImageFilter.GaussianBlur(2.6)).point(lambda v: min(255, v*2)))
    canvas = _screen(canvas, etch, glow, .95)

    if art is not None:
        column = Image.new("L", (1, 900))
        column.putdata([255 if y < 520 else round(255 * max(0.0, 1 - (y-520)/380) ** 1.3) for y in range(900)])
        canvas.paste(art, (0, 0), column.resize((w, 900)))

    shade = Image.new("RGBA", (w, h))
    sd = ImageDraw.Draw(shade)
    for y in range(170):
        sd.line((0, y, w, y), fill=(3, 4, 8, round(190 * (1 - y/170) ** 1.6)))
    for y in range(700, h):
        sd.line((0, y, w, y), fill=(*bg, round(90 * min(1.0, (y-700) / 320))))
    # A soft scrim so the title block reads over the brightest waterlines.
    scrim = _radial().resize((1500, 330), Image.Resampling.BICUBIC).point(lambda v: min(185, round(v*1.5)))
    shade.alpha_composite(Image.merge("RGBA", (*Image.new("RGB", scrim.size, (3, 4, 8)).split(), scrim)), (150, 521))
    deep = _rgb(_mix(theme.background, "#000000", .5))
    for box in _FOLIO_PANELS:
        sd.polygon(_chamfer(box, 16), fill=(*deep, 165))
    # Edge-only vignette: the corners sink into shadow, the painting keeps its light.
    vignette = Image.new("L", (90, 120))
    vignette.putdata([round(150 * min(1.0, max(0.0, (math.hypot(x/44.5 - 1, y/59.5 - 1) - .78) / .6)) ** 1.5)
                      for y in range(120) for x in range(90)])
    shade = Image.alpha_composite(shade, Image.merge("RGBA", (*Image.new("RGB", (w, h), (2, 2, 6)).split(),
                                                             vignette.resize((w, h), Image.Resampling.BICUBIC))))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shade).convert("RGB")
    _light(canvas, (cx-240, cy-240, cx+240, cy+240), glow, .75)

    # Gilded linework: drawn into one mask, bloomed, then filled with the edition's foil.
    metal = Image.new("L", (w*_SS, h*_SS))
    pen = _Pen(ImageDraw.Draw(metal))
    gems = []
    _draw_folio_frame(pen, theme.layout, w, h, gems)
    _draw_guilloche(pen)
    _draw_folio_crest(pen, theme.layout, gems)
    for index, box in enumerate(_FOLIO_PANELS):
        pen.line(_chamfer(box, 16), 1.5, 235)
        x1, y1, x2, y2 = box
        pen.line(_chamfer((x1+7, y1+7, x2-7, y2-7), 11), .8, 110)
        for x, y in ((x1+16, y1), (x2-16, y1), (x1+16, y2), (x2-16, y2)):
            pen.diamond(x, y, 4, 1.2)
        if index < 3:
            pen.diamond((x1+x2)/2, y1, 7, 1.4)
            gems.append(((x1+x2)/2, y1, 4))
    header_font = theme_font(18, "heading")
    for x, y, value, end in _FOLIO_HEADERS:
        start = x + header_font.getlength(value) + 22
        pen.line([(start, y+11), (end - 14, y+11)], 1, 130)
        pen.diamond(end - 8, y+11, 4, 1, 200)
    for x in (100, 605):
        pen.line([(x, 1786), (x+460, 1786)], 1, 120)
    pen.line([(100, 2033), (1065, 2033)], 1, 120)
    for sign in (-1, 1):
        pen.line([(900 + sign*48, 1535), (900 + sign*760, 1535)], 1.2, 210)
        pen.line([(900 + sign*60, 1541), (900 + sign*380, 1541)], .7, 120)
    pen.diamond(900, 1535, 22, 1.6)
    pen.diamond(900, 1535, 30, 1, 180, stretch=1.5)
    gems.append((900, 1535, 11))
    metal = metal.reduce(_SS)

    number, total = _edition_number(theme)
    band = Image.new("L", (w, h))
    _draw_ring_text(band, f"TRANSCENDENT  ·  {theme.name.upper()}", f"EDITION {_roman(number)} OF {_roman(total)}",
                    "heading", _CREST, 134)
    metal = ImageChops.lighter(metal, band)

    canvas = _screen(canvas, metal.filter(ImageFilter.GaussianBlur(7)), glow, 1.3)
    canvas = _screen(canvas, metal.filter(ImageFilter.GaussianBlur(2)), glow, .6)
    canvas.paste(_foil_sheet(ed["foil"], (w, h)), (0, 0), metal)
    _paint_gems(canvas, gems, ed["jewel"], ed["foil"])

    # The iridescent sheen lives on the folio, never over the painting itself.
    sheen = Image.new("L", (1, h))
    sheen.putdata([round(56 * min(1.0, max(0.0, (y-560) / 320))) for y in range(h)])
    canvas.paste(ImageChops.overlay(canvas, _holo_sheet((w, h))), (0, 0), sheen.resize((w, h)))

    # Sparkles: the brightest points of the painting, plus the crest and frame jewels.
    if art is not None:
        grid = art.convert("L").resize((60, 30), Image.Resampling.BOX)
        cells = sorted(((grid.getpixel((x, y)), x, y) for y in range(2, 26) for x in range(2, 58)), reverse=True)
        chosen = []
        for value, x, y in cells:
            if value < 150 or len(chosen) == 7:
                break
            if all(abs(x-a) + abs(y-b) > 9 for a, b in chosen):
                chosen.append((x, y))
        for i, (x, y) in enumerate(chosen):
            _glint(canvas, x*30 + 15, y*30 + 15, 46 - i*3, glow)
    for x, y, size in ((cx, cy-156, 40), (cx-155, cy+20, 22), (cx+150, cy-50, 26), (42+28, 42+28, 30),
                       (w-70, h-70, 30), (900, 1535, 34), (w-70, 70, 22), (70, h-70, 22)):
        _glint(canvas, x, y, size, (255, 250, 236))

    ink = ed["ink"]
    _foil_text(canvas, 120, 80, "F A B L E   /   R E B O R N", theme_font(21, "heading"), ink, glow, .5)
    heading = "T R A N S C E N D E N T"
    font = theme_font(21, "heading")
    _foil_text(canvas, w - 120 - font.getlength(heading), 80, heading, font, ink, glow, .7)
    draw = ImageDraw.Draw(canvas)
    for i in range(7):
        x, y, r = w - 128 - i*24, 124, 5 + (i == 0)
        draw.polygon([(x, y-r), (x+r, y), (x, y+r), (x-r, y)], fill=_lerp(ink, .15 + i*.05), outline=ed["jewel"][0])

    title_font = theme_font(76, "title")
    size = 76
    while title_font.getlength(theme.name.upper()) > 1540 and size > 40:
        size -= 2
        title_font = theme_font(size, "title")
    tag = f"E D I T I O N   {' '.join(_roman(number))}   O F   {' '.join(_roman(total))}"
    tag_font = theme_font(17, "heading")
    _foil_text(canvas, w/2, 598, tag, tag_font, ink, glow, .6, center=True)
    half = tag_font.getlength(tag) / 2
    for sign in (-1, 1):
        x0 = w/2 + sign*(half + 24)
        draw.line((x0, 610, x0 + sign*180, 610), fill=ed["foil"][2], width=1)
        draw.polygon([(x0 + sign*188, 604), (x0 + sign*194, 610), (x0 + sign*188, 616), (x0 + sign*182, 610)], fill=ed["jewel"][0])
    _foil_text(canvas, w/2, 632, theme.name.upper(), title_font, ink, glow, 1.1, center=True)
    epithet_font = theme_font(22, "heading")
    _foil_text(canvas, w/2, 738, theme.epithet, epithet_font, ink, glow, .45, center=True)
    half = epithet_font.getlength(theme.epithet) / 2
    for sign in (-1, 1):
        x0 = w/2 + sign*(half + 30)
        draw.line((x0, 752, x0 + sign*240, 752), fill=ed["foil"][2], width=2)
        draw.line((x0 + sign*20, 759, x0 + sign*170, 759), fill=ed["foil"][1], width=1)
        draw.polygon([(x0 + sign*250, 744), (x0 + sign*260, 752), (x0 + sign*250, 760), (x0 + sign*240, 752)], fill=ed["jewel"][0])
    for x, y, value, _ in _FOLIO_HEADERS:
        _foil_text(canvas, x, y, value, header_font, ink, glow, .35)
    _foil_text(canvas, 236, 2311, "CURRENT QUEST", header_font, ink, glow, .35)
    return canvas


@lru_cache(maxsize=1)
def _orbit_front():
    """The near half of the accretion ring, laid over the portrait for depth."""
    w, h = TRANSCENDENT_SIZE
    cx, cy = _CREST
    box = (cx-320, cy-110, cx+320, cy+110)
    mask = Image.new("L", ((box[2]-box[0])*_SS, (box[3]-box[1])*_SS))
    pen = _Pen(ImageDraw.Draw(mask))
    for index, width, fill in ((0, 2.6, 255), (1, 1, 150)):
        pen.line([(x - box[0], y - box[1]) for x, y in _orbit_halves(index)[1]], width, fill)
    mask = mask.reduce(_SS)
    return box, mask


def render_transcendent(theme, data):
    """Draw a collector folio from resolved data, never cropped standard panels."""
    w, h = TRANSCENDENT_SIZE
    ed = _edition(theme)
    ink, glow = ed["ink"], ed["glow"]
    canvas = _transcendent_base(theme.key).copy()
    draw = ImageDraw.Draw(canvas)

    def fit(value, size, role, width):
        value = str(value or "")
        font = theme_font(size, role)
        if width:
            while font.getlength(value) > width and size > 17:
                size -= 1
                font = theme_font(size, role)
            if font.getlength(value) > width:
                while value and font.getlength(value+"…") > width:
                    value = value[:-1]
                value += "…"
        return value, font

    def text(x, y, value, size=24, color=None, width=None, role="body", center=False):
        value, font = fit(value, size, role, width)
        if center:
            x -= font.getlength(value)/2
        draw.text((round(x), y), value, font=font, fill=color or theme.text)

    def foil(x, y, value, size, width=None, role="title", center=False, strength=.8):
        value, font = fit(value, size, role, width)
        _foil_text(canvas, x, y, value, font, ink, glow, strength, center)

    def label(x, y, value):
        text(x, y, value, 18, theme.accent, role="heading")

    def bar(x, y, width, ratio, thick=8):
        ratio = max(0, min(1, ratio))
        x, y, width = round(x), round(y), round(width)
        top = y - thick//2
        draw.rounded_rectangle((x, top, x+width, top+thick), radius=thick//2,
                               fill=_mix(theme.background, "#000000", .4), outline=theme.panel)
        filled = round(width * ratio)
        if filled >= thick:
            strip = Image.new("RGB", (width, 1))
            strip.putdata([_lerp((ed["foil"][5], ed["foil"][1], ed["foil"][2], ed["foil"][3]), i/max(1, width-1)) for i in range(width)])
            strip = strip.resize((width, thick), Image.Resampling.NEAREST).crop((0, 0, filled, thick))
            mask = Image.new("L", (filled, thick))
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, filled-1, thick-1), radius=thick//2, fill=255)
            canvas.paste(strip, (x, top), mask)
            draw.line((x + thick//2, top+1, x + filled - thick//2, top+1), fill=ed["foil"][3], width=1)
            _light(canvas, (x+filled-22, y-22, x+filled+22, y+22), glow, .9)
            _light(canvas, (x+filled-7, y-7, x+filled+7, y+7), (255, 255, 255), .8)
        for i in range(1, 10):
            tx = x + width*i/10
            draw.line((tx, top+1, tx, top+thick-2), fill=_mix(theme.background, "#000000", .3), width=1)

    cx, cy = _CREST
    radius = 110
    avatar = ImageOps.fit(data["avatar"].convert("RGB"), (220, 220), method=Image.Resampling.LANCZOS)
    canvas.paste(avatar, (cx-radius, cy-radius), _disc_mask(220))
    if theme.layout == "observatory":
        box, mask = _orbit_front()
        region = canvas.crop(box)
        region = _screen(region, mask.filter(ImageFilter.GaussianBlur(6)), glow, 1.4)
        region.paste(_foil_sheet(ed["foil"], mask.size), (0, 0), mask)
        canvas.paste(region, box[:2])

    text(460, 918, "LEVEL", 18, theme.muted, role="heading", center=True)
    foil(460, 936, data["level"], 82, center=True, strength=1)
    text(460, 1044, f'{data["rarity"].upper()} HERO', 18, theme.muted, role="heading", center=True)
    text(1340, 918, "COMBAT POWER", 18, theme.muted, role="heading", center=True)
    foil(1340, 950, f'{data["power"]:,}', 64, 440, center=True, strength=1)
    text(1340, 1044, f'LUCK BLESSING  {data["luck"]:.2f}%', 18, theme.muted, center=True)
    foil(900, 1150, data["name"], 60, 1500, center=True, strength=.9)
    text(900, 1226, f'{data["race"]}  /  {data["classes"]}', 24, theme.muted, 1400, center=True)
    bar(580, 1284, 640, data["xp_progress"], 8)
    text(900, 1300, f'{data["xp_progress"]:.0%} TO LEVEL {data["level"]+1}   /   XP #{data["rank_xp"] or "-"}   /   WEALTH #{data["rank_money"] or "-"}',
         17, theme.muted, 1100, center=True)
    for x, name, value, cap in (
        (360, "VITALITY / HEALTH", data["health"], 20000),
        (900, "OFFENSE / ATTACK", data["attack"], 5000),
        (1440, "WARD / DEFENSE", data["defense"], 5000),
    ):
        text(x, 1370, name, 18, theme.accent, center=True, role="heading")
        foil(x, 1394, f"{value:,}", 64, 410, center=True, strength=.7)
        bar(x-190, 1486, 380, value/cap, 8)

    text(100, 1604, data["stance"], 30, theme.text, 980, "title")
    for i, item in enumerate(data["equipment"]):
        x = 100+i*505
        label(x, 1665, item["label"])
        text(x, 1696, item["name"], 29, theme.text, 460, "heading")
        text(x, 1740, item["detail"], 21, theme.muted, 460)
    ledger = dict(data["ledger"])
    for index, key in enumerate(("Money", "Guild", "God", "Amulet", "PvP Wins", "Marriage")):
        x, y = 100+(index % 3)*335, 1853+(index//3)*85
        label(x, y, key.upper())
        text(x, y+29, ledger[key], 24, theme.text, 305)
    text(100, 2090, "ASCENSION", 17, theme.muted)
    text(100, 2119, data["ascension"], 24, theme.text, 955)
    for i, badge in enumerate(data["badges"][:6]):
        text(100+(i % 2)*490, 2160+(i//2)*29, badge, 21, theme.muted, 455)
    if data["jury_title"]:
        text(100, 2250, data["jury_title"], 20, theme.accent, 950)

    pet = data["companion"]
    if pet:
        _light(canvas, (1251-120, 1691-120, 1251+120, 1691+120), glow, .7)
        pet_image = pet.get("image")
        if pet_image:
            portrait = ImageOps.fit(pet_image.convert("RGBA"), (142, 142), method=Image.Resampling.LANCZOS)
            pmask = ImageChops.multiply(_disc_mask(142), portrait.getchannel("A"))
            canvas.paste(portrait, (1180, 1620), pmask)
        else:
            draw_ornament(draw, 1251, 1691, 43, theme)
        for r, width, colour in ((76, 3, ed["foil"][2]), (81, 1, ed["foil"][1]), (88, 1, ed["foil"][5])):
            draw.ellipse((1251-r, 1691-r, 1251+r, 1691+r), outline=colour, width=width)
        for a in range(4):
            x, y = 1251 + math.cos(a*math.pi/2)*81, 1691 + math.sin(a*math.pi/2)*81
            draw.polygon([(x, y-6), (x+6, y), (x, y+6), (x-6, y)], fill=ed["jewel"][0], outline=ed["foil"][3])
        foil(1354, 1622, pet["name"], 34, 340, strength=.6)
        text(1354, 1675, f'Lv {pet["level"]} / {pet["element"]}', 21, theme.muted, 350)
        text(1354, 1710, pet["stage"], 21, theme.muted, 350)
        text(1180, 1792, f'BOND  {pet["bond"]}  /  IV {pet["iv"]}%', 20, theme.accent, 515)
        for i, (name, value) in enumerate((("Happiness", pet["happiness"]), ("Hunger", pet["hunger"]), ("Trust", pet["trust"]))):
            y = 1841+i*56
            text(1180, y, name.upper(), 17, theme.muted)
            text(1605, y, f"{value}%", 19, theme.text)
            bar(1180, y+33, 510, value/100, 6)
        for i, (name, value, cap) in enumerate((("HEALTH", pet["hp"], 30000), ("ATTACK", pet["attack"], 6000), ("DEFENSE", pet["defense"], 6000))):
            y = 2033+i*64
            label(1180, y, name)
            text(1520, y-5, f"{value:,}", 28, theme.text, 175)
            bar(1180, y+39, 510, value/cap, 7)
    else:
        # An empty jewelled setting, waiting for a companion.
        _light(canvas, (1435-170, 1720-170, 1435+170, 1720+170), glow, .7)
        for r, width, colour in ((58, 3, ed["foil"][2]), (64, 1, ed["foil"][1]), (72, 1, ed["foil"][5])):
            draw.ellipse((1435-r, 1720-r, 1435+r, 1720+r), outline=colour, width=width)
        base, light, deep = ed["jewel"]
        draw.polygon([(1435, 1684), (1463, 1720), (1435, 1756), (1407, 1720)], fill=base, outline=ed["foil"][3])
        draw.polygon([(1435, 1684), (1435, 1720), (1407, 1720)], fill=_lerp((base, light), .55))
        draw.polygon([(1435, 1720), (1463, 1720), (1435, 1756)], fill=_lerp((base, deep), .5))
        _glint(canvas, 1426, 1706, 26, (255, 255, 255))
        foil(1435, 1830, "A BOND YET TO BE", 28, 500, center=True, strength=.5)
        text(1435, 1880, "No pet equipped / Use $pets equip", 22, theme.muted, 500, center=True)

    text(430, 2307, data["mission"], 23, theme.text, 900)
    text(1370, 2314, f'ID {data["user_id"]}', 15, theme.muted, 200)
    if data.get("sprite") is not None:
        sprite = data["sprite"].convert("RGBA")
        canvas.paste(sprite, (100, 892), sprite)
        text(166, 1053, data["sprite_name"], 17, theme.muted, 210, center=True)
    return canvas


# ===========================================================================
#  FABLE FOLIOS  —  story editions from The Tiamat Sacrament
# ===========================================================================
# The Fable paintings are 3:1 panoramas, so this folio is a landscape card that
# keeps each one whole. Below the painting the scene is reflected (in a lake, on
# polished steel, in a toxic pool) under frosted glass, gilded in the edition's metal.

FABLE_SIZE = (2400, 1700)
_FABLE_ART = {"sacrament": "tiamat-sacrament-banner-v1.png",
              "gyle": "gyle-nether-garrison-v2.png",
              "ryjin": "ryjin-dominion-banner-v2.png",
              "tiamat": "tiamat.png",
              "founding": "founding-reader-v1.png"}
_FABLE_ART_H = 800
_MEDALLION = (300, 930)
_FABLE_PLAQUES = ((600, 1098, 1146, 1258), (1187, 1098, 1733, 1258), (1774, 1098, 2320, 1258))
_FABLE_LEDGER = (80, 1280, 1560, 1590)
_FABLE_BOND = (1600, 1280, 2320, 1590)
_FABLE_QUEST = (420, 1610, 1980, 1652)
_FABLE_HEADERS = ((110, 1298, "I   /   ARMAMENT", 548), (600, 1298, "II   /   ALLEGIANCE", 1038),
                  (1090, 1298, "III   /   LEGACY", 1530), (1630, 1298, "IV   /   SOUL COMPANION", 2290))
_FABLE_STATS = ("VITALITY  /  HEALTH", "OFFENSE  /  ATTACK", "WARD  /  DEFENSE")
# The goddess's edition is earned with all seven Soul Gems: the Seven crown her medallion in the
# order their statues stand in the Library's Tiamat Hall (Ilisrei, Knoas, Unoquil, Saphira at the
# summit, Xetoa, Tamanir, Kadelej), each in the colour of its gem on the Library's dragon door.
_SEVEN = ((255, 150, 60), (190, 120, 255), (90, 225, 255), (255, 205, 80), (80, 150, 255), (255, 80, 80), (90, 230, 120))
_ORB = (1518, 392)   # the light cupped in the goddess's hands, in folio coordinates


def _seven_points():
    cx, cy = _MEDALLION
    return [(cx + math.cos(a)*250, cy + math.sin(a)*250) for a in (-math.pi/2 + (i-3)*.33 for i in range(7))]


# `foil` runs over the engraved metal, `ink` top-to-bottom through chrome lettering.
_FABLES = {
    "creation": dict(
        chapter=4, kicker="TIAMAT   ·   GODDESS OF CREATION", legend="TIAMAT  ·  GODDESS OF CREATION",
        foil=((66, 48, 80), (164, 132, 184), (238, 215, 242), (255, 246, 228), (194, 162, 226), (184, 148, 102), (242, 218, 180)),
        ink=((255, 249, 255), (239, 222, 250), (202, 174, 232), (114, 86, 150), (220, 194, 242), (252, 241, 255)),
        glow=(190, 152, 230), jewel=((160, 104, 224), (242, 219, 255), (57, 30, 92)),
        lower="lake", tint=(172, 151, 202), haze=(202, 182, 224), sun=None, rays=None,
        motes=((230, 211, 245), (194, 172, 230))),
    "sacrament": dict(
        chapter=1, kicker="AZ'UAR   ·   KELBURN   ·   XANDRA", legend="THE TIAMAT SACRAMENT",
        foil=((84, 70, 46), (196, 162, 98), (255, 240, 204), (255, 255, 252), (168, 208, 255), (212, 176, 108), (250, 234, 186)),
        ink=((255, 255, 255), (232, 243, 255), (178, 210, 252), (70, 104, 176), (198, 224, 255), (250, 252, 255)),
        glow=(110, 186, 255), jewel=((46, 122, 255), (206, 236, 255), (10, 28, 104)),
        lower="lake", tint=(130, 178, 238), haze=(176, 214, 255), sun=(1440, 170), rays=(255, 226, 168),
        motes=((214, 240, 255), (120, 230, 255))),
    "garrison": dict(
        chapter=2, kicker="GYLE   ·   THE NETHER GARRISON", legend="GYLE  ·  THE PENITENT",
        foil=((52, 54, 62), (146, 150, 162), (232, 236, 244), (255, 255, 255), (178, 182, 194), (92, 94, 106), (210, 214, 224)),
        ink=((255, 255, 255), (236, 236, 242), (196, 198, 208), (96, 100, 112), (212, 214, 224), (252, 250, 250)),
        glow=(255, 104, 74), jewel=((214, 38, 48), (255, 196, 186), (86, 6, 14)),
        lower="steel", tint=(186, 146, 108), haze=(255, 222, 170), sun=(1400, 90), rays=(255, 214, 156),
        motes=((255, 226, 186), (255, 120, 54))),
    "dominion": dict(
        chapter=3, kicker="RY'JIN   ·   TYRANT OF ILDRIA", legend="RY'JIN  ·  TYRANT OF ILDRIA",
        foil=((28, 32, 24), (94, 108, 58), (208, 238, 118), (246, 255, 200), (148, 188, 68), (66, 76, 42), (198, 228, 108)),
        ink=((250, 255, 232), (226, 246, 160), (182, 222, 82), (68, 94, 30), (202, 236, 122), (244, 255, 216)),
        glow=(160, 255, 54), jewel=((140, 232, 36), (234, 255, 186), (36, 76, 8)),
        lower="pool", tint=(118, 196, 74), haze=(150, 255, 70), sun=None, rays=None,
        motes=((210, 255, 140), (150, 255, 60))),
    # The Fables Library: candle-gold over the emblem's moonlit silver, the Tiamat door's blue gem.
    "library": dict(
        chapter=0, kicker="THE FABLES LIBRARY   ·   FOUNDING WEEK", legend="FOUNDING READER",
        foil=((58, 62, 74), (150, 162, 180), (230, 236, 244), (255, 252, 240), (226, 196, 128), (120, 100, 60), (246, 226, 176)),
        ink=((255, 252, 244), (246, 234, 206), (226, 200, 140), (110, 92, 54), (236, 214, 164), (255, 250, 236)),
        glow=(240, 198, 120), jewel=((66, 128, 230), (214, 232, 255), (14, 32, 92)),
        lower="lake", tint=(150, 160, 190), haze=(226, 206, 168), sun=None, rays=None,
        motes=((255, 236, 200), (255, 208, 130))),
}


def _fable(theme):
    return _FABLES.get(theme.layout, _FABLES["sacrament"])


@lru_cache(maxsize=4)
def _fable_art(key):
    with Image.open(ASSET_ROOT / _FABLE_ART.get(key, f"{key}.png")) as source:
        return ImageOps.fit(source.convert("RGB"), (FABLE_SIZE[0], _FABLE_ART_H), method=Image.Resampling.LANCZOS)


def _ripple(image, seed):
    """Water: each row slides sideways, wider and slower the further it is from the shore."""
    pixels = np.asarray(image)
    h, w = pixels.shape[:2]
    rows = np.arange(h)
    depth = rows / max(1, h - 1)
    phase = random.Random(seed).uniform(0, math.tau)
    shift = ((3 + 30*depth) * np.sin(rows * .23 / (1 + depth*2.2) + phase)
             + (2 + 12*depth) * np.sin(rows * .051 + 1.7)).round().astype(int)
    cols = (np.arange(w)[None, :] - shift[:, None]) % w
    return Image.fromarray(pixels[rows[:, None], cols])


def _noise(size, cells, rng, blur=0):
    """Smooth value noise: a coarse random grid enlarged with bicubic filtering."""
    small = Image.new("L", cells)
    small.putdata([rng.randint(0, 255) for _ in range(cells[0] * cells[1])])
    image = small.resize(size, Image.Resampling.BICUBIC)
    return image.filter(ImageFilter.GaussianBlur(blur)) if blur else image


def _fable_lower(art, ed, w, h, bg):
    """The painting continues beneath its own edge: mirrored in water, or as open ground."""
    top = _FABLE_ART_H
    height = h - top
    mirror = art.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    field = Image.new("RGB", (w, height))
    field.paste(mirror, (0, 0))
    if height > mirror.height:
        field.paste(mirror.crop((0, mirror.height - 1, w, mirror.height)).resize((w, height - mirror.height)),
                    (0, mirror.height))
    if ed["lower"] == "steel":
        # Polished plate: the reflection smears downward like light on brushed metal.
        field = field.resize((w, height // 30), Image.Resampling.BOX).resize((w, height), Image.Resampling.BICUBIC)
        field = field.filter(ImageFilter.GaussianBlur(3))
    else:
        sharp = _ripple(field, ed["legend"])
        soft = _ripple(field.filter(ImageFilter.GaussianBlur(9)), ed["legend"])
        field = Image.composite(soft, sharp, Image.linear_gradient("L").resize((w, height)).point(lambda v: min(255, v*3)))
    field = ImageChops.multiply(field, Image.new("RGB", field.size, ed["tint"]))
    fade = Image.linear_gradient("L").resize((w, height)).point(lambda v: round(70 + v*.62))
    return top, Image.composite(Image.new("RGB", field.size, bg), field, fade)


def _rays(size, origin, rng, count=36):
    """A fan of soft light shafts falling from the painting's light source."""
    mask = Image.new("L", size)
    d = ImageDraw.Draw(mask)
    ox, oy = origin
    for _ in range(count):
        a = rng.uniform(math.radians(38), math.radians(152))
        spread = rng.uniform(.005, .022)
        d.polygon([(ox, oy), (ox + math.cos(a-spread)*3000, oy + math.sin(a-spread)*3000),
                   (ox + math.cos(a+spread)*3000, oy + math.sin(a+spread)*3000)], fill=rng.randint(16, 58))
    return mask.filter(ImageFilter.GaussianBlur(16))


def _motes(size, rng, count, area, radius, value=(120, 255), trail=0, rings=False):
    mask = Image.new("L", size)
    d = ImageDraw.Draw(mask)
    x1, y1, x2, y2 = area
    for _ in range(count):
        x, y = rng.uniform(x1, x2), rng.uniform(y1, y2)
        r, v = rng.uniform(*radius), rng.randint(*value)
        if rings:
            d.ellipse((x-r, y-r, x+r, y+r), outline=v, width=max(1, round(r/5)))
            d.ellipse((x-r*.55, y-r*.65, x-r*.25, y-r*.35), fill=v)
        else:
            d.ellipse((x-r, y-r, x+r, y+r), fill=v)
        if trail:
            # Rising sparks leave a fading streak beneath them.
            length = rng.uniform(trail*.4, trail)
            drift = rng.uniform(-.3, .3) * length
            for i in range(8):
                t0, t1 = i/8, (i+1)/8
                d.line((x + drift*t0, y + length*t0, x + drift*t1, y + length*t1),
                       fill=round(v*(1-t1)*.7), width=max(1, round(r*.9*(1-t0))))
    return mask


def _petals(size, rng, count, area):
    """Wisteria petals adrift: small tilted ovals, the nearer ones larger and dimmer."""
    mask = Image.new("L", size)
    d = ImageDraw.Draw(mask)
    x1, y1, x2, y2 = area
    for _ in range(count):
        x, y = rng.uniform(x1, x2), rng.uniform(y1, y2)
        near = rng.random() ** 2
        length, breadth = 5 + near*13, 2.2 + near*4.5
        a = rng.uniform(0, math.pi)
        ux, uy = math.cos(a), math.sin(a)
        points = [(x + ux*length*math.cos(t) - uy*breadth*math.sin(t), y + uy*length*math.cos(t) + ux*breadth*math.sin(t))
                  for t in _steps(0, math.tau, 18)]
        d.polygon(points, fill=round(230 - near*110))
    return mask


def _paint_seven(canvas, foil):
    """The seven Soul Gems, each in its own colour and light."""
    draw = ImageDraw.Draw(canvas)
    for (x, y), base in zip(_seven_points(), _SEVEN):
        _light(canvas, (x-70, y-70, x+70, y+70), base, .9)
        # The setting's ring in fixed pale gold: the foil sweep runs dark in places.
        draw.ellipse((x-24, y-24, x+24, y+24), outline=foil[2], width=2)
        light, deep = _lerp((base, (255, 255, 255)), .62), _lerp((base, (0, 0, 0)), .58)
        _paint_gems(canvas, [(x, y, 13)], (base, light, deep), foil)
        _glint(canvas, x - 4, y - 6, 15, (255, 255, 255))


def _spectrum_ring(canvas, centre, radius, width):
    """A halo of the Seven's colours, Saphira's gold at the summit."""
    cx, cy = centre
    step = 360 / 7
    box = (cx-radius, cy-radius, cx+radius, cy+radius)
    for i, colour in enumerate(_SEVEN):
        mid = -90 + (i - 3)*step
        mask = Image.new("L", canvas.size)
        ImageDraw.Draw(mask).arc(box, mid - step/2 + 2, mid + step/2 - 2, fill=255, width=width + 6)
        canvas = _screen(canvas, mask.filter(ImageFilter.GaussianBlur(9)), colour, 1.5)
        ImageDraw.Draw(canvas).arc(box, mid - step/2 + 2, mid + step/2 - 2, fill=_lerp((colour, (255, 255, 255)), .4), width=width)
    return canvas


def _frost(canvas, box, cut, deep, alpha):
    """Frosted glass: the scene behind is blurred and darkened, with a lit upper edge."""
    x1, y1, x2, y2 = box
    size = (x2-x1, y2-y1)
    region = canvas.crop(box).filter(ImageFilter.GaussianBlur(18))
    region = Image.blend(region, Image.new("RGB", size, deep), alpha)
    sheen = Image.linear_gradient("L").transpose(Image.Transpose.FLIP_TOP_BOTTOM).resize(size)
    sheen = sheen.point(lambda v: round(max(0, v-150) * .3))
    region = _screen(region, sheen, (255, 255, 255))
    mask = Image.new("L", size)
    ImageDraw.Draw(mask).polygon(_chamfer((0, 0, size[0]-1, size[1]-1), cut), fill=255)
    canvas.paste(region, box[:2], mask)


def _sword(pen, hilt, tip):
    (hx, hy), (tx, ty) = hilt, tip
    length = math.hypot(tx-hx, ty-hy)
    ux, uy = (tx-hx)/length, (ty-hy)/length

    def at(t, s):
        return (hx + ux*t - uy*s, hy + uy*t + ux*s)
    pen.disc(*at(-36, 0), 10)
    pen.line([at(-28, 0), at(0, 0)], 8)
    pen.line([at(0, -66), at(0, 66)], 7)
    for side in (-1, 1):
        pen.disc(*at(0, side*68), 6.5)
    pen.line([at(10, -14), at(length-50, -12), at(length, 0), at(length-50, 12), at(10, 14), at(10, -14)], 2.4)
    pen.line([at(24, 0), at(length-70, 0)], 1.2)


def _horn(pen, root, angle, length, width, bend):
    """A tapering horn that curls by `bend` radians from root to tip."""
    x, y = root
    spine = []
    for i in range(25):
        t = i / 24
        spine.append((x, y, angle + bend*t*t, width/2 * (1 - t) ** .85))
        a = angle + bend*t*t
        x, y = x + math.cos(a)*length/24, y + math.sin(a)*length/24
    left = [(px - math.sin(a)*half, py + math.cos(a)*half) for px, py, a, half in spine]
    right = [(px + math.sin(a)*half, py - math.cos(a)*half) for px, py, a, half in spine]
    pen.poly(left + right[::-1])


def _fable_medallion(pen, layout, gems, extra):
    """The portrait's setting. `extra` receives linework that must stay outside the rim."""
    cx, cy = _MEDALLION
    for r, width in ((128, 3), (134, 1), (172, 1), (178, 2.4)):
        pen.ring(cx, cy, r, width)
    if layout == "creation":
        # The sacred pool's ripples and a pearl halo, a sunburst of creation behind them, and
        # the seven Soul Gems set in a crown above (coloured later by _paint_seven).
        for r, width in ((190, 2), (204, 1), (216, 1.4)):
            pen.ring(cx, cy, r, width)
        for i in range(16):
            a = i * math.tau / 16
            x, y = cx + math.cos(a)*204, cy + math.sin(a)*204
            pen.disc(x, y, 3)
        for i in range(96):
            a = i * math.tau / 96
            reach = 78 if i % 8 == 0 else 48 if i % 4 == 0 else 26 if i % 2 == 0 else 13
            extra.line([(cx + math.cos(a)*226, cy + math.sin(a)*226),
                        (cx + math.cos(a)*(226 + reach), cy + math.sin(a)*(226 + reach))], 1.7 if i % 8 == 0 else .9)
        extra.ring(cx, cy, 250, 1)
        for x, y in _seven_points():
            extra.disc(x, y, 22, 0)
            extra.diamond(x, y, 19, 1.8)
        for a in (0, math.pi/2, math.pi):
            x, y = cx + math.cos(a)*216, cy + math.sin(a)*216
            pen.diamond(x, y, 14, 1.5)
            gems.append((x, y, 8))
    elif layout == "sacrament":
        # Az'uar's swept crown of horns, and a collar of overlapping scales.
        for side in (-1, 1):
            for k in range(5):
                a = -math.pi/2 + side*(.26 + k*.25)
                _horn(pen, (cx + math.cos(a)*176, cy + math.sin(a)*176), a + side*.15, 190 - k*30, 30 - k*4, side*(1.05 - k*.08))
        for i in range(44):
            a = i * math.tau / 44
            x, y = cx + math.cos(a)*190, cy + math.sin(a)*190
            pen.line([(x + math.cos(t)*13, y + math.sin(t)*13) for t in _steps(a - math.pi/2, a + math.pi/2, 12)], 1.6)
        for a in (math.pi*.25, math.pi*.75, math.pi*.5):
            gems.append((cx + math.cos(a)*204, cy + math.sin(a)*204, 9))
    elif layout == "garrison":
        # Two swords crossed point-down behind a riveted steel rim.
        for sign in (-1, 1):
            _sword(extra, (cx - sign*178, cy - 178), (cx + sign*172, cy + 172))
        pen.ring(cx, cy, 188, 3)
        pen.ring(cx, cy, 200, 1)
        for i in range(28):
            a = i * math.tau / 28
            pen.disc(cx + math.cos(a)*194, cy + math.sin(a)*194, 4.4 if i % 7 else 6.5)
        for a in (-math.pi/2, 0, math.pi):
            gems.append((cx + math.cos(a)*194, cy + math.sin(a)*194, 8))
    elif layout == "library":
        # The Fables emblem around the portrait: a pointed door-arch rising over it, and the
        # pages of an open book fanned out beneath, like the Library's sign.
        pen.ring(cx, cy, 190, 2)
        pen.ring(cx, cy, 200, 1)
        for side in (-1, 1):
            for spread, rise, width in ((206, 330, 2.6), (222, 352, 1.1)):
                # A lancet: each side is an arc whose centre sits across the doorway.
                radius = (spread*spread + rise*rise) / (2*spread)
                top = math.acos((radius - spread) / radius)
                extra.line([(cx + side*(spread - radius + radius*math.cos(t)), cy - radius*math.sin(t))
                            for t in _steps(0, top, 40)], width)
            for k in range(4):
                # Page edges, each a little lower and wider than the one above.
                reach, sag, lift = 214 + k*18, 196 + k*12, 118 + k*16
                extra.line([(cx + side*reach*t, cy + lift + (sag - lift)*(1 - t)**2) for t in _steps(0, 1, 30)],
                           2 if k == 0 else 1)
            gems.append((cx + side*214, cy + 118, 8))
        extra.diamond(cx, cy - 330, 14, 1.6)
        gems.append((cx, cy - 330, 8))
    else:
        # A spiked crown inside a summoning circle.
        for i in range(36):
            a = i * math.tau / 36
            reach, half = (52, .05) if i % 3 == 0 else (24, .035)
            pen.poly([(cx + math.cos(a-half)*180, cy + math.sin(a-half)*180),
                      (cx + math.cos(a)*(180+reach), cy + math.sin(a)*(180+reach)),
                      (cx + math.cos(a+half)*180, cy + math.sin(a+half)*180)])
        pen.ring(cx, cy, 252, 1.4)
        pen.ring(cx, cy, 262, .8)
        for flip in (0, math.pi):
            points = [(cx + math.cos(flip - math.pi/2 + i*math.tau/3)*262, cy + math.sin(flip - math.pi/2 + i*math.tau/3)*262)
                      for i in range(4)]
            extra.line(points, 1.4)
        for i in range(12):
            a = i * math.tau / 12 + math.pi/12
            x, y = cx + math.cos(a)*257, cy + math.sin(a)*257
            extra.ring(x, y, 7, 1.2)
            extra.line([(x - math.cos(a)*12, y - math.sin(a)*12), (x + math.cos(a)*12, y + math.sin(a)*12)], 1.2)
        for a in (-math.pi/2, math.pi/6, math.pi*5/6):
            gems.append((cx + math.cos(a)*262, cy + math.sin(a)*262, 9))


def _fable_frame(pen, layout, w, h, gems):
    pen.rrect((14, 14, w-14, h-14), 26, 3)
    pen.rrect((24, 24, w-24, h-24), 20, 1)
    pen.rrect((32, 32, w-32, h-32), 14, 1.6)
    corners = ((32, 32, 1, 1), (w-32, 32, -1, 1), (32, h-32, 1, -1), (w-32, h-32, -1, -1))
    for cx, cy, sx, sy in corners:
        def p(u, v, cx=cx, cy=cy, sx=sx, sy=sy):
            return (cx + sx*u, cy + sy*v)
        if layout in ("sacrament", "creation", "library"):
            for radius, width in ((62, 2.2), (76, 1)):
                pen.line([p(radius*math.cos(t), radius*math.sin(t)) for t in _steps(0, math.pi/2, 28)], width)
            for flip in (False, True):
                for i in range(14):
                    u = 96 + i*22
                    pts = [p(u + 10*math.cos(t), 12 + 10*math.sin(t)) if not flip else p(12 + 10*math.sin(t), u + 10*math.cos(t))
                           for t in _steps(0, math.pi, 10)]
                    pen.line(pts, 1.3 - i*.04)
            pen.line([p(110 + 16*(1 - t/14)*math.cos(t), 40 + 16*(1 - t/14)*math.sin(t)) for t in _steps(0, 14, 80)], 1.3)
            pen.line([p(40 + 16*(1 - t/14)*math.sin(t), 110 + 16*(1 - t/14)*math.cos(t)) for t in _steps(0, 14, 80)], 1.3)
        elif layout == "garrison":
            pen.line([p(0, 0), p(232, 0), p(214, 18), p(18, 18), p(18, 214), p(0, 232), p(0, 0)], 2.4)
            for i in range(5):
                pen.disc(*p(40 + i*42, 9), 3.6)
                pen.disc(*p(9, 40 + i*42), 3.6)
        else:
            # Barbed thorns along both edges, pointing away from the corner.
            for flip in (False, True):
                def q(u, v, flip=flip, p=p):
                    return p(v, u) if flip else p(u, v)
                pen.line([q(78, 10), q(330, 10)], 1.6)
                for k in range(5):
                    u, size = 92 + k*48, 26 - k*4
                    pen.poly([q(u, 10), q(u + size*1.3, 10), q(u + size*1.6, 10 + size*.9)])
            pen.line([p(62*math.cos(t), 62*math.sin(t)) for t in _steps(0, math.pi/2, 28)], 2.2)
        jewel = p(44, 44)
        pen.diamond(*jewel, 17, 1.6)
        gems.append((*jewel, 11))
        if layout == "creation":
            # A lotus opening from each corner jewel toward the heart of the folio.
            inward = math.atan2(sy, sx)
            # Small enough to stay clear of the corner lettering ("FABLE / REBORN" starts at x 112).
            for turn, length, breadth in ((0, 30, 11), (-.7, 23, 9), (.7, 23, 9), (-1.22, 15, 6), (1.22, 15, 6)):
                pen.leaf(*p(54, 54), inward + turn, length, breadth)
    if layout == "creation":
        # Strings of pearls along every edge, a larger pearl at each fourth bead.
        for y in (24, h-24):
            for i, x in enumerate(range(420, w-410, 19)):
                if abs(x - w/2) > 236:
                    pen.disc(x, y, 3.7 if i % 4 == 0 else 2.3)
        for x in (24, w-24):
            for i, y in enumerate(range(420, h-410, 19)):
                if abs(y - 850) > 52:
                    pen.disc(x, y, 3.7 if i % 4 == 0 else 2.3)
    if layout == "garrison":
        for y in (24, h-24):
            for x in range(260, w-250, 64):
                pen.disc(x, y, 2.6)
        for x in (24, w-24):
            for y in range(260, h-250, 64):
                pen.disc(x, y, 2.6)
    elif layout == "dominion":
        for y, sign in ((48, 1), (h-48, -1)):
            for offset in (0, 8):
                pen.line([(260, y + sign*offset), (w-260, y + sign*offset)], 1.2)
            for x in range(320, w-300, 150):
                pen.line([(x, y - 8*(sign < 0)), (x, y + 16 - 8*(sign < 0))], 5)
    for x in (32, w-32):
        pen.diamond(x, 850, 22, 1.6)
        pen.diamond(x, 850, 30, 1)
        gems.append((x, 850, 10))
    for y in (32, h-32):
        pen.diamond(w/2, y, 18, 1.6, stretch=1.6)
        gems.append((w/2, y, 9))
        for sign in (-1, 1):
            pen.line([(w/2 + sign*34, y), (w/2 + sign*190, y)], 3)
            pen.disc(w/2 + sign*200, y, 3.2)


def _fable_etching(draw, layout, rng, w, h):
    """Faint light-etched patterns in the lower field, painted with the edition glow."""
    cx, cy = _MEDALLION
    if layout == "creation":
        # Rings spreading over the pool, and the Flower of Life, the first shape of creation,
        # blooming from beneath the goddess and around the portrait.
        for k, r in enumerate(range(240, 2600, 110)):
            draw.ellipse((cx-r, 1090 - r*.2, cx+r, 1090 + r*.2), outline=max(10, 70 - k*3), width=1)
        for (fx, fy), r, ink in (((cx, cy), 118, 44), ((1520, 1010), 150, 34)):
            for i in range(-2, 3):
                for j in range(-2, 3):
                    if max(abs(i), abs(j), abs(i + j)) > 2:
                        continue
                    x, y = fx + r*(i + j/2), fy + r*j*math.sqrt(3)/2
                    draw.ellipse((x-r, y-r, x+r, y+r), outline=ink, width=1)
            for ring in (2, 3):
                draw.ellipse((fx - r*ring - 6*(ring-2), fy - r*ring - 6*(ring-2), fx + r*ring + 6*(ring-2), fy + r*ring + 6*(ring-2)),
                             outline=ink + 20, width=2 if ring == 3 else 1)
    elif layout == "sacrament":
        # Rings spreading over the lake from beneath the portrait, and water-magic spirals.
        for k, r in enumerate(range(240, 2600, 110)):
            draw.ellipse((cx-r, 1090 - r*.2, cx+r, 1090 + r*.2), outline=max(10, 70 - k*3), width=1)
        for turn in range(3):
            points = []
            for t in _steps(0, 4.2*math.pi, 300):
                r = 210 + 46*t
                points.append((cx + r*math.cos(t + turn*math.tau/3), cy + r*.42*math.sin(t + turn*math.tau/3)))
            draw.line(points, fill=46, width=2)
            for x, y in points[::14]:
                draw.ellipse((x-2.2, y-2.2, x+2.2, y+2.2), fill=150)
    elif layout == "library":
        # Candlelight rings on the polished floor, and the faint ruled lines of a page.
        for k, r in enumerate(range(240, 2600, 110)):
            draw.ellipse((cx-r, 1090 - r*.2, cx+r, 1090 + r*.2), outline=max(10, 60 - k*3), width=1)
        for y in range(860, h, 34):
            draw.line((0, y, w, y), fill=14, width=1)
        draw.line((640, 820, 640, h), fill=26, width=1)
    elif layout == "garrison":
        # Brushed steel: long faint strokes across the parade ground.
        for _ in range(900):
            x, y = rng.uniform(-200, w), rng.uniform(820, h)
            draw.line((x, y, x + rng.uniform(80, 520), y), fill=rng.randint(8, 30), width=1)
        for r in range(300, 1800, 140):
            draw.arc((cx-r, cy-r, cx+r, cy+r), 280, 360, fill=22, width=1)
    else:
        # The laboratory floor plates and an outer alchemical circle.
        for x in range(0, w, 120):
            draw.line((x, 820, x, h), fill=16, width=1)
        for y in range(820, h, 120):
            draw.line((0, y, w, y), fill=16, width=1)
            for x in range(0, w, 120):
                draw.ellipse((x-2, y-2, x+2, y+2), fill=60)
        for r in (330, 344, 470):
            draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline=40, width=1)
        for i in range(48):
            a = i * math.tau / 48
            draw.line((cx + math.cos(a)*330, cy + math.sin(a)*330, cx + math.cos(a)*(344 if i % 4 else 360),
                       cy + math.sin(a)*(344 if i % 4 else 360)), fill=70, width=1)


@lru_cache(maxsize=4)
def _fable_base(key):
    """Everything that depends only on the edition, never on a player. Callers copy it."""
    theme = THEMES[key]
    ed = _fable(theme)
    w, h = FABLE_SIZE
    cx, cy = _MEDALLION
    bg = _rgb(theme.background)
    glow, ink = ed["glow"], ed["ink"]
    rng = random.Random(key)
    canvas = Image.new("RGB", (w, h), bg)
    try:
        art = _fable_art(key)
    except (OSError, ValueError):
        art = None

    if art is not None:
        top, field = _fable_lower(art, ed, w, h, bg)
        canvas.paste(field, (0, top))
        # Bloom: the painting's highlights glow softly into their surroundings.
        # The goddess's painting is pale throughout, so only its very brightest light blooms.
        threshold = 205 if theme.layout == "creation" else 165
        lit = art.convert("L").point(lambda v: max(0, v - threshold) * 3).filter(ImageFilter.GaussianBlur(20))
        art = ImageChops.screen(art, Image.composite(art.filter(ImageFilter.GaussianBlur(22)), Image.new("RGB", art.size), lit))
        canvas.paste(art, (0, 0))
    _light(canvas, (cx-700, cy-520, cx+700, cy+520), glow, .35)

    # Mist where the painting meets its continuation.
    band = Image.new("L", (1, h))
    band.putdata([round(255 * max(0.0, 1 - abs(y - 805) / 120) ** 1.5) for y in range(h)])
    mist = ImageChops.multiply(band.resize((w, h)), _noise((w, h), (40, 14), rng, 6))
    canvas = _screen(canvas, mist, ed["haze"], .55)
    if ed["lower"] == "pool":
        vapour = ImageChops.multiply(Image.linear_gradient("L").resize((w, h)).point(lambda v: round(v*.8)),
                                     _noise((w, h), (26, 9), rng, 10))
        canvas = _screen(canvas, vapour, ed["haze"], .35)

    etch = Image.new("L", (w, h))
    _fable_etching(ImageDraw.Draw(etch), theme.layout, rng, w, h)
    lower = Image.new("L", (1, h))
    lower.putdata([0 if y < 780 else 255 for y in range(h)])
    canvas = _screen(canvas, ImageChops.multiply(etch, lower.resize((w, h))), glow, .9)

    if ed["sun"]:
        rays = _rays((w, h), ed["sun"], rng)
        canvas = _screen(canvas, rays, ed["rays"], .7)

    # Shade: a dark top edge, a scrim for the title, the lower field darkening toward the stats.
    # Each is its own mask and the darkest wins, so no layer can cut a hard edge into another.
    column = Image.new("L", (1, h))
    column.putdata([round(170 * max(0.0, 1 - y/150) ** 1.6) for y in range(h)])
    shade = column.resize((w, h))
    row = Image.new("L", (w, 1))
    row.putdata([round(150 * max(0.0, 1 - x/1250) ** 1.3) for x in range(w)])
    fall = Image.new("L", (1, h))
    fall.putdata([round(255 * min(1.0, max(0.0, (920 - y) / 220))) for y in range(h)])
    shade = ImageChops.lighter(shade, ImageChops.multiply(row.resize((w, h)), fall.resize((w, h))))
    for size, place, peak, gain in (((1900, 900), (-450, -120), 200, 1.4), ((1100, 760), (-250, 560), 150, 1.2)):
        blot = Image.new("L", (w, h))
        blot.paste(_radial().resize(size, Image.Resampling.BICUBIC).point(lambda v, peak=peak, gain=gain: min(peak, round(v*gain))), place)
        shade = ImageChops.lighter(shade, blot)
    vignette = Image.new("L", (120, 85))
    vignette.putdata([round(170 * min(1.0, max(0.0, (math.hypot(x/59.5 - 1, y/42 - 1) - .8) / .55)) ** 1.6)
                      for y in range(85) for x in range(120)])
    shade = ImageChops.lighter(shade, vignette.resize((w, h), Image.Resampling.BICUBIC))
    canvas = Image.composite(Image.new("RGB", (w, h), (3, 4, 8)), canvas, shade)

    # Atmosphere: depth-of-field bokeh, then fine motes or sparks in the light.
    near, spark = ed["motes"]
    bokeh = _motes((w, h), rng, 46, (60, 120, w-60, h-80), (10, 30), (30, 90)).filter(ImageFilter.GaussianBlur(7))
    canvas = _screen(canvas, bokeh, near, .8)
    if ed["lower"] == "steel":
        dust = _motes((w, h), rng, 260, (40, 60, w-40, h-40), (.8, 2.2), (60, 190))
        embers = _motes((w, h), rng, 70, (500, 300, w-60, h-80), (1.4, 3.4), (170, 255), trail=46)
        canvas = _screen(canvas, dust.filter(ImageFilter.GaussianBlur(.8)), near, .9)
        canvas = _screen(canvas, embers.filter(ImageFilter.GaussianBlur(5)), spark, .9)
        canvas = _screen(canvas, embers.filter(ImageFilter.GaussianBlur(.7)), (255, 210, 150), 1)
    elif ed["lower"] == "pool":
        spores = _motes((w, h), rng, 170, (40, 380, w-40, h-40), (1, 3), (120, 255), trail=30)
        bubbles = _motes((w, h), rng, 40, (60, 900, w-60, h-60), (4, 11), (110, 220), rings=True)
        canvas = _screen(canvas, spores.filter(ImageFilter.GaussianBlur(4)), spark, .8)
        canvas = _screen(canvas, ImageChops.lighter(spores, bubbles).filter(ImageFilter.GaussianBlur(.7)), near, .9)
    else:
        spray = _motes((w, h), rng, 240, (40, 640, w-40, h-40), (.8, 2.6), (90, 255))
        canvas = _screen(canvas, spray.filter(ImageFilter.GaussianBlur(3)), spark, .7)
        canvas = _screen(canvas, spray.filter(ImageFilter.GaussianBlur(.7)), near, 1)
        if theme.layout == "creation":
            # Her orb's radiance, and wisteria petals adrift across the whole folio.
            ox, oy = _ORB
            # Kept tight and soft: the orb glows, her skin stays as painted.
            _light(canvas, (ox-120, oy-120, ox+120, oy+120), (226, 196, 255), .45)
            petals = _petals((w, h), rng, 95, (40, 60, w-40, h-60))
            canvas = _screen(canvas, petals.filter(ImageFilter.GaussianBlur(7)), (206, 150, 255), .9)
            canvas = _screen(canvas, petals.filter(ImageFilter.GaussianBlur(.9)), (255, 232, 252), .85)
        streaks = Image.new("L", (w, h))
        sd = ImageDraw.Draw(streaks)
        lum = canvas.convert("L")
        for _ in range(1300):
            x, y = rng.uniform(0, w), rng.uniform(820, h-40)
            v = lum.getpixel((min(w-1, int(x)), int(y)))
            sd.line((x, y, x + rng.uniform(14, 90), y), fill=min(255, v * 2), width=1)
        canvas = _screen(canvas, streaks.filter(ImageFilter.GaussianBlur(.6)), (220, 240, 255), .5)

    deep = _rgb(_mix(theme.background, "#000000", .35))
    for box in (*_FABLE_PLAQUES, _FABLE_LEDGER, _FABLE_BOND, _FABLE_QUEST):
        _frost(canvas, box, 16 if box != _FABLE_QUEST else 10, deep, .62)
    _light(canvas, (cx-300, cy-300, cx+300, cy+300), glow, .7)

    # Gilded linework: one supersampled mask, bloomed, then filled with the edition's foil.
    metal = Image.new("L", (w*_SS, h*_SS))
    pen = _Pen(ImageDraw.Draw(metal))
    beyond = Image.new("L", (w*_SS, h*_SS))
    extra = _Pen(ImageDraw.Draw(beyond))
    gems = []
    _fable_frame(pen, theme.layout, w, h, gems)
    _fable_medallion(pen, theme.layout, gems, extra)
    extra.disc(cx, cy, 204, 0)
    metal = ImageChops.lighter(metal, beyond)
    for box in (*_FABLE_PLAQUES, _FABLE_LEDGER, _FABLE_BOND, _FABLE_QUEST):
        cut = 16 if box != _FABLE_QUEST else 10
        pen.line(_chamfer(box, cut), 1.5, 235)
        x1, y1, x2, y2 = box
        pen.line(_chamfer((x1+7, y1+7, x2-7, y2-7), cut-5), .8, 110)
        for x, y in ((x1+cut, y1), (x2-cut, y1), (x1+cut, y2), (x2-cut, y2)):
            pen.diamond(x, y, 4, 1.2)
        if box in _FABLE_PLAQUES:
            pen.diamond((x1+x2)/2, y1, 7, 1.4)
            gems.append(((x1+x2)/2, y1, 4))
    for x in (575, 1065):
        pen.line([(x, 1300), (x, 1570)], 1, 120)
    pen.line([(1965, 1330), (1965, 1570)], 1, 120)
    pen.line([(1985, 850), (1985, 1010)], 1, 150)
    header_font = theme_font(18, "heading")
    for x, y, value, end in _FABLE_HEADERS:
        start = x + header_font.getlength(value) + 18
        pen.line([(start, y+11), (end - 12, y+11)], 1, 130)
        pen.diamond(end - 6, y+11, 4, 1, 200)
    pen.line([(580, 1072), (1420, 1072)], 1.2, 200)
    pen.line([(1480, 1072), (2320, 1072)], 1.2, 200)
    pen.diamond(1450, 1072, 16, 1.6, stretch=1.5)
    gems.append((1450, 1072, 8))
    metal = metal.reduce(_SS)

    band = Image.new("L", (w, h))
    edition = ("SECRET FABLE" if theme.layout == "creation" else "FOUNDING EDITION" if theme.layout == "library"
               else f"FABLE {_roman(ed['chapter'])} OF III")
    _draw_ring_text(band, ed["legend"], edition, "heading", _MEDALLION, 153)
    metal = ImageChops.lighter(metal, band)

    canvas = _screen(canvas, metal.filter(ImageFilter.GaussianBlur(8)), glow, 1.4)
    canvas = _screen(canvas, metal.filter(ImageFilter.GaussianBlur(2)), glow, .6)
    canvas.paste(_foil_sheet(ed["foil"], (w, h)), (0, 0), metal)
    _paint_gems(canvas, gems, ed["jewel"], ed["foil"])
    if theme.layout == "creation":
        canvas = _spectrum_ring(canvas, _MEDALLION, 197, 3)
        _paint_seven(canvas, ed["foil"])

    # Iridescent sheen on the folio, never over the painting itself.
    sheen = Image.new("L", (1, h))
    sheen.putdata([round(40 * min(1.0, max(0.0, (y-820) / 260))) for y in range(h)])
    canvas.paste(ImageChops.overlay(canvas, _holo_sheet((w, h))), (0, 0), sheen.resize((w, h)))

    if art is not None and ed["lower"] == "lake":
        grid = _fable_art(key).convert("L").resize((80, 26), Image.Resampling.BOX)
        cells = sorted(((grid.getpixel((x, y)), x, y) for y in range(8, 24) for x in range(30, 78)), reverse=True)
        chosen = []
        for value, x, y in cells:
            if value < 150 or len(chosen) == 6:
                break
            if all(abs(x-a) + abs(y-b) > 8 for a, b in chosen):
                chosen.append((x, y))
        for i, (x, y) in enumerate(chosen):
            _glint(canvas, x*30 + 15, y*30.77 + 15, 40 - i*3, glow)
    for x, y, size in ((cx, cy-178, 38), (cx+178, cy, 22), (76, 76, 30), (w-76, h-76, 30),
                       (w-76, 76, 22), (76, h-76, 22), (1450, 1072, 30), (w/2, 32, 30)):
        _glint(canvas, x, y, size, (255, 250, 236))

    # The edition's own lettering.
    _foil_text(canvas, 112, 74, "F A B L E   /   R E B O R N", theme_font(22, "heading"), ink, glow, .5)
    label = {"creation": "S E C R E T   E D I T I O N", "library": "F O U N D I N G   E D I T I O N"}.get(
        theme.layout, "F A B L E   E D I T I O N")
    font = theme_font(22, "heading")
    _foil_text(canvas, w - 120 - font.getlength(label), 74, label, font, ink, glow, .7)
    draw = ImageDraw.Draw(canvas)
    base, light, deep_jewel = ed["jewel"]
    if theme.layout == "creation":
        # All seven Soul Gems, lit: the price of this edition.
        for i, colour in enumerate(_SEVEN):
            x, y, r = w - 128 - (6-i)*32, 128, 9
            _light(canvas, (x-34, y-34, x+34, y+34), colour, .9)
            draw.polygon([(x, y-r), (x+r, y), (x, y+r), (x-r, y)], fill=colour, outline=ed["foil"][3])
            draw.polygon([(x, y-r), (x, y), (x-r, y)], fill=_lerp((colour, (255, 255, 255)), .55))
    for i in range(3 if theme.layout not in ("creation", "library") else 0):
        x, y, r = w - 128 - (2-i)*34, 128, 9
        if i + 1 == ed["chapter"]:
            _light(canvas, (x-40, y-40, x+40, y+40), base, 1)
            draw.polygon([(x, y-r), (x+r, y), (x, y+r), (x-r, y)], fill=base, outline=ed["foil"][3])
            draw.polygon([(x, y-r), (x, y), (x-r, y)], fill=_lerp((base, light), .55))
        else:
            draw.polygon([(x, y-r+2), (x+r-2, y), (x, y+r-2), (x-r+2, y)], outline=ed["foil"][1])

    kicker_font = theme_font(19, "heading")
    draw.polygon([(112, 158), (120, 166), (112, 174), (104, 166)], fill=ed["jewel"][0])
    _foil_text(canvas, 136, 154, ed["kicker"], kicker_font, ink, glow, .45)
    title_font_size = 112
    lines = [line.upper() for line in theme.title_lines] or [theme.name.upper()]
    while max(theme_font(title_font_size, "title").getlength(line) for line in lines) > 1000 and title_font_size > 60:
        title_font_size -= 2
    title_font = theme_font(title_font_size, "title")
    y = 196
    for line in lines:
        _foil_text(canvas, 104, y, line, title_font, ink, glow, 1.15)
        y += round(title_font_size * 1.06)
    epithet_font = theme_font(25, "heading")
    _foil_text(canvas, 112, y + 22, theme.epithet, epithet_font, ink, glow, .5)
    rule = y + 78
    draw.line((112, rule, 112 + epithet_font.getlength(theme.epithet), rule), fill=ed["foil"][2], width=2)
    draw.line((112, rule + 7, 112 + epithet_font.getlength(theme.epithet)*.6, rule + 7), fill=ed["foil"][1], width=1)
    chip = ("S E C R E T   F A B L E" if theme.layout == "creation"
            else "T H E   L I B R A R Y ' S   F I R S T   W E E K" if theme.layout == "library"
            else f"F A B L E   {' '.join(_roman(ed['chapter']))}   O F   I I I")
    _foil_text(canvas, 112, rule + 26, chip, theme_font(17, "heading"), ink, glow, .55)

    for x, y, value, _ in _FABLE_HEADERS:
        _foil_text(canvas, x, y, value, header_font, ink, glow, .35)
    _foil_text(canvas, 450, 1621, "CURRENT QUEST", header_font, ink, glow, .35)
    for (x1, y1, x2, _), name in zip(_FABLE_PLAQUES, _FABLE_STATS):
        _foil_text(canvas, (x1+x2)/2, y1+18, name, header_font, ink, glow, .3, center=True)
    for x, value in ((1800, "LEVEL"), (2150, "COMBAT POWER")):
        _foil_text(canvas, x, 852, value, header_font, ink, glow, .3, center=True)
    return canvas


def render_fable(theme, data):
    """Draw a widescreen Fable folio from resolved data, never cropped standard panels."""
    ed = _fable(theme)
    ink, glow = ed["ink"], ed["glow"]
    canvas = _fable_base(theme.key).copy()
    draw = ImageDraw.Draw(canvas)

    def fit(value, size, role, width):
        value = str(value or "")
        font = theme_font(size, role)
        if width:
            while font.getlength(value) > width and size > 17:
                size -= 1
                font = theme_font(size, role)
            if font.getlength(value) > width:
                while value and font.getlength(value+"…") > width:
                    value = value[:-1]
                value += "…"
        return value, font

    def text(x, y, value, size=24, color=None, width=None, role="body", center=False, right=False):
        value, font = fit(value, size, role, width)
        if center:
            x -= font.getlength(value)/2
        elif right:
            x -= font.getlength(value)
        draw.text((round(x), y), value, font=font, fill=color or theme.text)

    def foil(x, y, value, size, width=None, role="title", center=False, strength=.8):
        value, font = fit(value, size, role, width)
        _foil_text(canvas, x, y, value, font, ink, glow, strength, center)

    def label(x, y, value):
        text(x, y, value, 17, theme.accent, role="heading")

    def bar(x, y, width, ratio, thick=8):
        ratio = max(0, min(1, ratio))
        x, y, width = round(x), round(y), round(width)
        top = y - thick//2
        draw.rounded_rectangle((x, top, x+width, top+thick), radius=thick//2,
                               fill=_mix(theme.background, "#000000", .4), outline=theme.panel)
        filled = round(width * ratio)
        if filled >= thick:
            strip = Image.new("RGB", (width, 1))
            strip.putdata([_lerp((ed["foil"][5], ed["foil"][1], ed["foil"][2], ed["foil"][3]), i/max(1, width-1)) for i in range(width)])
            strip = strip.resize((width, thick), Image.Resampling.NEAREST).crop((0, 0, filled, thick))
            mask = Image.new("L", (filled, thick))
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, filled-1, thick-1), radius=thick//2, fill=255)
            canvas.paste(strip, (x, top), mask)
            draw.line((x + thick//2, top+1, x + filled - thick//2, top+1), fill=ed["foil"][3], width=1)
            _light(canvas, (x+filled-24, y-24, x+filled+24, y+24), glow, .9)
            _light(canvas, (x+filled-7, y-7, x+filled+7, y+7), (255, 255, 255), .8)
        for i in range(1, 10):
            tx = x + width*i/10
            draw.line((tx, top+1, tx, top+thick-2), fill=_mix(theme.background, "#000000", .3), width=1)

    cx, cy = _MEDALLION
    avatar = ImageOps.fit(data["avatar"].convert("RGB"), (250, 250), method=Image.Resampling.LANCZOS)
    canvas.paste(avatar, (cx-125, cy-125), _disc_mask(250))

    sprite = data.get("sprite")
    name_width = 900 if sprite is None else 860
    foil(580, 846, data["name"], 76, name_width, strength=.95)
    text(584, 946, f'{data["race"]}  /  {data["classes"]}', 26, theme.muted, name_width)
    bar(584, 1000, 820 if sprite is None else 780, data["xp_progress"], 8)
    text(584, 1030, f'{data["xp_progress"]:.0%} TO LEVEL {data["level"]+1}   /   XP #{data["rank_xp"] or "-"}   /   WEALTH #{data["rank_money"] or "-"}',
         17, theme.muted, 820, role="heading")
    if sprite is not None:
        sprite = sprite.convert("RGBA")
        _light(canvas, (1490-70, 860-20, 1490+200, 860+190), glow, .5)
        canvas.paste(sprite, (1420 + (132 - sprite.width)//2, 852), sprite)
        text(1486, 1010, data["sprite_name"], 15, theme.muted, 200, center=True)

    foil(1800, 874, data["level"], 96, 300, center=True, strength=1)
    text(1800, 1000, f'{str(data["rarity"]).upper()} HERO', 17, theme.muted, 300, role="heading", center=True)
    foil(2150, 890, f'{data["power"]:,}', 72, 320, center=True, strength=1)
    text(2150, 1000, f'LUCK BLESSING  {data["luck"]:.2f}%', 17, theme.muted, 320, center=True)

    for (x1, y1, x2, y2), value, cap in zip(_FABLE_PLAQUES, (data["health"], data["attack"], data["defense"]),
                                            (20000, 5000, 5000)):
        mid = (x1 + x2) / 2
        foil(mid, y1 + 40, f"{value:,}", 58, 480, center=True, strength=.7)
        bar(x1 + 40, y2 - 22, x2 - x1 - 80, value/cap, 8)

    text(110, 1338, data["stance"], 28, theme.text, 440, "title")
    for i, item in enumerate(data["equipment"]):
        y = 1388 + i*102
        label(110, y, item["label"])
        text(110, y+24, item["name"], 26, theme.text, 440, "heading")
        text(110, y+60, item["detail"], 19, theme.muted, 440)
    ledger = dict(data["ledger"])
    for index, key in enumerate(("Money", "Guild", "God", "Amulet", "PvP Wins", "Marriage")):
        x, y = 600 + (index % 2)*235, 1340 + (index // 2)*80
        label(x, y, key.upper())
        text(x, y+26, ledger[key], 22, theme.text, 215)
    text(1090, 1340, "ASCENSION", 17, theme.muted, role="heading")
    text(1090, 1364, data["ascension"], 24, theme.text, 440)
    for i, badge in enumerate(data["badges"][:6]):
        text(1090 + (i % 2)*230, 1414 + (i//2)*30, badge, 19, theme.muted, 215)
    if data["jury_title"]:
        text(1090, 1520, data["jury_title"], 19, theme.accent, 440)

    pet = data["companion"]
    if pet:
        px, py = 1702, 1400
        _light(canvas, (px-120, py-120, px+120, py+120), glow, .7)
        pet_image = pet.get("image")
        if pet_image:
            portrait = ImageOps.fit(pet_image.convert("RGBA"), (120, 120), method=Image.Resampling.LANCZOS)
            canvas.paste(portrait, (px-60, py-60), ImageChops.multiply(_disc_mask(120), portrait.getchannel("A")))
        else:
            draw_ornament(draw, px, py, 36, theme)
        for r, width, colour in ((64, 3, ed["foil"][2]), (69, 1, ed["foil"][1]), (76, 1, ed["foil"][5])):
            draw.ellipse((px-r, py-r, px+r, py+r), outline=colour, width=width)
        for a in range(4):
            x, y = px + math.cos(a*math.pi/2)*69, py + math.sin(a*math.pi/2)*69
            draw.polygon([(x, y-6), (x+6, y), (x, y+6), (x-6, y)], fill=ed["jewel"][0], outline=ed["foil"][3])
        foil(1792, 1340, pet["name"], 30, 160, strength=.6)
        text(1792, 1386, f'Lv {pet["level"]} / {pet["element"]}', 19, theme.muted, 160)
        text(1792, 1414, pet["stage"], 19, theme.muted, 160)
        text(1630, 1494, f'BOND  {pet["bond"]}', 18, theme.accent, 320, role="heading")
        text(1630, 1526, f'IV  {pet["iv"]}%', 18, theme.muted, 320, role="heading")
        rows = (("HAPPINESS", pet["happiness"], 100, "%"), ("HUNGER", pet["hunger"], 100, "%"), ("TRUST", pet["trust"], 100, "%"),
                ("HEALTH", pet["hp"], 30000, ""), ("ATTACK", pet["attack"], 6000, ""), ("DEFENSE", pet["defense"], 6000, ""))
        for i, (name, value, cap, unit) in enumerate(rows):
            y = 1336 + i*40
            text(1990, y, name, 15, theme.muted, role="heading")
            text(2290, y-3, f"{value:,}{unit}", 19, theme.text, 150, right=True)
            bar(1990, y+27, 300, value/cap, 6)
    else:
        # An empty jewelled setting, waiting for a companion.
        px, py = 1960, 1410
        _light(canvas, (px-170, py-170, px+170, py+170), glow, .7)
        for r, width, colour in ((52, 3, ed["foil"][2]), (58, 1, ed["foil"][1]), (66, 1, ed["foil"][5])):
            draw.ellipse((px-r, py-r, px+r, py+r), outline=colour, width=width)
        base, light, deep = ed["jewel"]
        draw.polygon([(px, py-30), (px+26, py), (px, py+30), (px-26, py)], fill=base, outline=ed["foil"][3])
        draw.polygon([(px, py-30), (px, py), (px-26, py)], fill=_lerp((base, light), .55))
        draw.polygon([(px, py), (px+26, py), (px, py+30)], fill=_lerp((base, deep), .5))
        _glint(canvas, px-9, py-14, 26, (255, 255, 255))
        foil(px, 1494, "A BOND YET TO BE", 26, 600, center=True, strength=.5)
        text(px, 1540, "No pet equipped / Use $pets equip", 20, theme.muted, 600, center=True)

    text(640, 1620, data["mission"], 22, theme.text, 1040)
    text(1950, 1624, f'ID {data["user_id"]}', 15, theme.muted, 260, right=True)
    return canvas


def add_theme_banner(card, theme):
    """A full-width painted banner above the existing readable stat layout."""
    result = Image.new("RGB", (1660, 1460), theme.background)
    try:
        result.paste(_banner(theme.key), (0, 0))
    except (OSError, ValueError):
        # Missing optional artwork must never prevent someone viewing their stats.
        pass
    overlay = Image.new("RGBA", (1660, 554))
    shade = ImageDraw.Draw(overlay)
    for x in range(850):
        shade.line((x, 0, x, 554), fill=(4, 6, 12, int(125 * (1 - x / 850))))
    result.paste(overlay, (0, 0), overlay)
    overlay = Image.new("RGBA", (1660, 554))
    shade = ImageDraw.Draw(overlay)
    rgb = Image.new("RGB", (1, 1), theme.background).getpixel((0, 0))
    for y in range(414, 520):
        shade.line((0, y, 1660, y), fill=(*rgb, int(255 * (y - 414) / 105)))
    result.paste(overlay, (0, 0), overlay)
    result.paste(card.convert("RGB"), (0, 520))
    draw = ImageDraw.Draw(result)
    draw.text((64, 68), "F A B L E   /   R E B O R N", font=theme_font(22, "heading"), fill=theme.accent)
    draw.line((64, 118, 280, 118), fill=theme.accent, width=2)
    words = theme.name.upper().split()
    lines = [theme.name.upper()] if len(words) == 1 else [" ".join(words[:-1]), words[-1]]
    if theme.title_lines:
        lines = [line.upper() for line in theme.title_lines]
    y = 160
    for line in lines:
        size = 70
        while draw.textlength(line, font=theme_font(size, "title")) > 730 and size > 32:
            size -= 2
        draw.text((60, y), line, font=theme_font(size, "title"), fill="#fff7ea",
                  stroke_width=1, stroke_fill="#19202a")
        if theme.finish == "prismatic":
            _draw_foil_title(result, (60, y), line, theme_font(size, "title"))
        y += 90
    draw.text((64, y + 20), theme.epithet, font=theme_font(23, "heading"), fill=theme.accent)
    if theme.is_event:
        caption = f"EVENT EDITION  /  {theme.event.upper()}"
    else:
        edition = list(THEMES).index(theme.key)
        caption = f"{theme.collection.upper()}  /  {theme.rarity.upper()}  /  CHRONICLE {edition:02d}"
    draw.text((64, 465), caption, font=theme_font(18, "heading"), fill=theme.muted)
    draw.line((64, 510, 1596, 510), fill=theme.secondary, width=1)
    draw_ornament(draw, 830, 510, 12, theme)
    if theme.finish == "prismatic":
        _add_prismatic_finish(result, theme)
    return result
