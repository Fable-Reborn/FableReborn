"""Shared elemental matchup rules used by combat systems."""


SUPER_EFFECTIVE_MODIFIER = 0.50
WEAK_MODIFIER = -0.30

# Three balanced cycles. Every combat element has exactly one strength and one
# weakness; Unknown is a neutral fallback rather than a combat element.
ELEMENT_STRENGTHS = {
    "Light": "Corrupted",
    "Corrupted": "Dark",
    "Dark": "Light",
    "Fire": "Nature",
    "Nature": "Water",
    "Water": "Fire",
    "Earth": "Electric",
    "Electric": "Wind",
    "Wind": "Earth",
    "Unknown": None,
}


def normalize_element(element):
    if not element:
        return "Unknown"
    return str(element).strip().capitalize()


def is_element_strong_against(attacker_element, defender_element):
    attacker_element = normalize_element(attacker_element)
    defender_element = normalize_element(defender_element)
    return ELEMENT_STRENGTHS.get(attacker_element) == defender_element


def calculate_element_modifier(attacker_element, defender_element):
    attacker_element = normalize_element(attacker_element)
    defender_element = normalize_element(defender_element)

    if ELEMENT_STRENGTHS.get(attacker_element) == defender_element:
        return SUPER_EFFECTIVE_MODIFIER
    if ELEMENT_STRENGTHS.get(defender_element) == attacker_element:
        return WEAK_MODIFIER
    return 0.0
