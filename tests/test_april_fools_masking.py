import unittest
from types import SimpleNamespace

from utils.april_fools import (
    APRIL_FOOLS_GREG_FLAG,
    GREG_DISPLAY_NAME,
    GREG_HIDDEN_PET_EFFECTS,
    GREG_PET_IMAGE_URL,
    GregMaskedName,
    get_greg_hidden_pet_effects,
    get_pet_display_name,
    get_pet_display_url,
    mask_runtime_name,
)


class TestAprilFoolsMasking(unittest.TestCase):
    def test_mask_runtime_name_keeps_actual_name_for_logic(self):
        bot = SimpleNamespace(april_fools_flags={APRIL_FOOLS_GREG_FLAG: True})

        masked_name = mask_runtime_name(bot, "Fear Incarnate")

        self.assertIsInstance(masked_name, GregMaskedName)
        self.assertEqual(GREG_DISPLAY_NAME, str(masked_name))
        self.assertTrue("Fear Incarnate" in masked_name)
        self.assertEqual("Fear Incarnate", masked_name.actual_name)

    def test_mask_runtime_name_keeps_unique_hashes(self):
        bot = SimpleNamespace(april_fools_flags={APRIL_FOOLS_GREG_FLAG: True})

        names = {
            mask_runtime_name(bot, "Fear Incarnate"),
            mask_runtime_name(bot, "Chaos Elemental"),
        }

        self.assertEqual(2, len(names))

    def test_pet_display_helpers_switch_to_greg_assets(self):
        bot = SimpleNamespace(april_fools_flags={APRIL_FOOLS_GREG_FLAG: True})

        self.assertEqual(GREG_DISPLAY_NAME, get_pet_display_name(bot, "Ancient Drake"))
        self.assertEqual(GREG_PET_IMAGE_URL, get_pet_display_url(bot, "https://example.com/pet.png"))

    def test_pet_display_helpers_leave_values_alone_when_disabled(self):
        bot = SimpleNamespace(april_fools_flags={APRIL_FOOLS_GREG_FLAG: False})

        self.assertEqual("Ancient Drake", get_pet_display_name(bot, "Ancient Drake"))
        self.assertEqual("https://example.com/pet.png", get_pet_display_url(bot, "https://example.com/pet.png"))

    def test_greg_hidden_pet_effects_only_exist_when_enabled(self):
        enabled_bot = SimpleNamespace(april_fools_flags={APRIL_FOOLS_GREG_FLAG: True})
        disabled_bot = SimpleNamespace(april_fools_flags={APRIL_FOOLS_GREG_FLAG: False})

        self.assertEqual({}, get_greg_hidden_pet_effects(disabled_bot))
        self.assertEqual(set(GREG_HIDDEN_PET_EFFECTS), set(get_greg_hidden_pet_effects(enabled_bot)))

    def test_greg_hidden_pet_effects_are_copied(self):
        bot = SimpleNamespace(april_fools_flags={APRIL_FOOLS_GREG_FLAG: True})

        greg_effects = get_greg_hidden_pet_effects(bot)
        greg_effects["gregplicate"]["chance"] = 99

        self.assertEqual(12, GREG_HIDDEN_PET_EFFECTS["gregplicate"]["chance"])


if __name__ == "__main__":
    unittest.main()
