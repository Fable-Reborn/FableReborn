"""The companion roster: who can be unlocked and how they are shown.

Each companion's art lives in assets/companions/<key>/ as portrait.png and
silhouette.png (the blacked-out art shown while locked). `focus` is the point,
as fractions of the portrait's width and height, that the diagonal tiles crop
around (usually the face). Lore comes from Tiamat Sacrament.
"""

from dataclasses import dataclass

GOOD = "good"
EVIL = "evil"


@dataclass(frozen=True)
class Companion:
    key: str
    name: str
    title: str
    alignment: str
    description: str
    hint: str
    accent: tuple
    focus: tuple = (0.5, 0.22)
    zoom: float = 0.42


COMPANIONS = (
    Companion(
        key="azuar",
        name="Az'uar",
        title="Whelp of Ilisrei",
        alignment=GOOD,
        description=(
            "The last hatchling of the dragon Ilisrei, who refused the order to shatter her eggs. "
            "Raised in hiding beside the scholar Xandra, Az'uar grows from whelp to wyrm through "
            "the Tiamat Sacrament, carrying his mother's fury against the empire that slew her."
        ),
        hint="A heartbeat stirs within an egg that should have been shattered.",
        accent=(74, 140, 246),
        focus=(0.74, 0.4),
        zoom=0.4,
    ),
    Companion(
        key="ryjin",
        name="Ry'jin",
        title="Tyrant of Ildria",
        alignment=EVIL,
        description=(
            "The usurper who slew King Khytiel and his entire royal guard to seize Ildria. "
            "Ry'jin splices dragon DNA into his own flesh, stealing the breath of earth, air, "
            "water and fire, and reads the minds of those who would betray him."
        ),
        hint="The throne of Ildria casts a long and hollow shadow.",
        accent=(150, 132, 214),
        focus=(0.5, 0.2),
    ),
    Companion(
        key="gyle",
        name="Gyle",
        title="Ry'jin's Blade",
        alignment=EVIL,
        description=(
            "Ry'jin's strongest operative and the knight whose blade felled Ilisrei. "
            "Gyle leads the raids from the Nether Garrison, breathes a stolen Inferno Breath "
            "and hunts the last of the dragons, sworn to see them driven to extinction."
        ),
        hint="Steel that remembers the taste of dragonfire.",
        accent=(214, 52, 58),
        focus=(0.5, 0.2),
    ),
    Companion(
        key="xandra",
        name="Xandra",
        title="Scholar of Draslin",
        alignment=GOOD,
        description=(
            "A scholar of Draslin and Az'uar's steadfast ally, Xandra hides a royal name: "
            "Princess Alexandra, King Khytiel's surviving heir. She stands against Ry'jin's "
            "tyranny, choosing the people she can protect and the family she has found "
            "over the safety of a crown."
        ),
        hint="Among forbidden books, a lost heir keeps hope alive.",
        accent=(214, 116, 150),
        focus=(0.52, 0.19),
    ),
)

BY_KEY = {companion.key: companion for companion in COMPANIONS}


def find(name):
    """A companion by key or display name, ignoring case and apostrophes."""
    wanted = (name or "").lower().replace("'", "").strip()
    for companion in COMPANIONS:
        if wanted in (companion.key, companion.name.lower().replace("'", "")):
            return companion
    return None
