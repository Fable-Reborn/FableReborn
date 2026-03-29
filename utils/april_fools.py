from __future__ import annotations


APRIL_FOOLS_GREG_FLAG = "greg_mode"
GREG_DISPLAY_NAME = "Greg"
GREG_PET_IMAGE_URL = (
    "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/"
    "295173706496475136_greg_profile_pic2023-640w-removebg-preview-removebg-preview_1.png"
)
GREG_HIDDEN_PET_EFFECTS = {
    "gregplicate": {
        "chance": 12,
        "clone_damage": 0.45,
        "type": "duplicate_attack",
    },
    "greg_stare": {
        "chance": 18,
        "turn_delay": 1,
        "accuracy_reduction": 0.18,
        "duration": 2,
        "type": "enemy_debuff",
    },
    "coffee_break": {
        "heal_percent": 0.03,
        "type": "owner_heal_on_attack",
    },
}


class GregMaskedName(str):
    """Render as Greg while preserving the underlying name for lookups and checks."""

    __slots__ = ("actual_name",)

    def __new__(cls, actual_name: object, display_name: str = GREG_DISPLAY_NAME):
        display_text = str(display_name or GREG_DISPLAY_NAME)
        obj = super().__new__(cls, display_text)
        obj.actual_name = "" if actual_name is None else str(actual_name)
        return obj

    def __contains__(self, item: object) -> bool:
        return str(item) in self.actual_name

    def __eq__(self, other: object) -> bool:
        if isinstance(other, GregMaskedName):
            return self.actual_name == other.actual_name
        return self.actual_name == str(other)

    def __hash__(self) -> int:
        return hash(self.actual_name)

    def __reduce__(self):
        return (self.__class__, (self.actual_name, str(self)))


def _get_flag_map(bot) -> dict:
    return getattr(bot, "april_fools_flags", {}) or {}


def is_greg_mode_enabled(bot) -> bool:
    return bool(_get_flag_map(bot).get(APRIL_FOOLS_GREG_FLAG, False))


def extract_actual_name(name: object) -> str:
    if isinstance(name, GregMaskedName):
        return name.actual_name
    return "" if name is None else str(name)


def mask_runtime_name(bot, actual_name: object):
    actual_text = extract_actual_name(actual_name)
    if not is_greg_mode_enabled(bot):
        return actual_text
    return GregMaskedName(actual_text)


def get_pet_display_name(bot, actual_name: object) -> str:
    if is_greg_mode_enabled(bot):
        return GREG_DISPLAY_NAME
    return extract_actual_name(actual_name)


def get_pet_display_url(bot, actual_url: object) -> str:
    if is_greg_mode_enabled(bot):
        return GREG_PET_IMAGE_URL
    return "" if actual_url is None else str(actual_url)


def get_greg_hidden_pet_effects(bot) -> dict:
    if not is_greg_mode_enabled(bot):
        return {}
    return {
        effect_name: dict(effect_data)
        for effect_name, effect_data in GREG_HIDDEN_PET_EFFECTS.items()
    }


def mask_pet_record_for_display(bot, pet):
    if pet is None:
        return None

    masked_pet = dict(pet)
    if is_greg_mode_enabled(bot):
        masked_pet["name"] = GREG_DISPLAY_NAME
        masked_pet["url"] = GREG_PET_IMAGE_URL
    return masked_pet
