"""PRPG cosmetics: local artwork, portable fonts and deterministic card chrome."""

from dataclasses import dataclass, replace
from functools import lru_cache
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


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

    @property
    def classic(self):
        return self.key == "classic"

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
    )
}

for _key, _rarity, _motif in (
    ("classic", "Original", "diamond"), ("dragon", "Epic", "claw"),
    ("evil", "Epic", "claw"), ("chaos", "Epic", "rift"),
    ("good", "Rare", "sun"), ("forest", "Uncommon", "leaf"), ("frost", "Epic", "star"),
):
    THEMES[_key] = replace(THEMES[_key], rarity=_rarity, motif=_motif)

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
    edition = list(THEMES).index(theme.key)
    draw.text((64, 465), f"{theme.collection.upper()}  /  {theme.rarity.upper()}  /  CHRONICLE {edition:02d}",
              font=theme_font(18, "heading"), fill=theme.muted)
    draw.line((64, 510, 1596, 510), fill=theme.secondary, width=1)
    draw_ornament(draw, 830, 510, 12, theme)
    if theme.finish == "prismatic":
        _add_prismatic_finish(result, theme)
    return result
