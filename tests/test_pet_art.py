import datetime
import unittest

from utils import pet_art


class TestPetArt(unittest.TestCase):
    def test_species_key_matches_the_library(self):
        # Same answers as Server/CrownFallServer/src/pets.js speciesKey.
        self.assertEqual(pet_art.species_key("Ilisrei's Whelp"), "ilisrei_s_whelp")
        self.assertEqual(pet_art.species_key("  Pavorinex  "), "pavorinex")
        self.assertEqual(pet_art.species_key("Élan Wyrm-Hound"), "elan_wyrm_hound")
        self.assertEqual(pet_art.species_key("<>"), "pet")
        self.assertEqual(len(pet_art.species_key("x" * 200)), 64)

    def test_library_pets_are_keyed_by_their_current_form(self):
        whelp = {"id": 1, "name": "Pip", "default_name": "Ilisrei's Whelp", "library_chapter": 0}
        self.assertEqual(pet_art.species_of(whelp), "Ilisrei's Whelp")
        self.assertEqual(pet_art.species_of({**whelp, "library_chapter": 4}), "Ilisrei's Drake")
        self.assertEqual(pet_art.species_of({**whelp, "library_chapter": 8}), "Ilisrei's Wyrm")

    def test_other_pets_use_their_species_not_their_nickname(self):
        pet = {"id": 7, "name": "Sir Fluff", "default_name": "Pavorinex", "element": "Fire", "url": "https://x/p.png"}
        details = pet_art.pet_details(pet)
        self.assertEqual(details["species"], "Pavorinex")
        self.assertEqual(details["species_key"], "pavorinex")
        self.assertEqual(details["pet_name"], "Sir Fluff")
        self.assertEqual(details["portrait"], "https://x/p.png")
        self.assertEqual(pet_art.species_of({"id": 8, "name": "Odd", "default_name": None}), "Odd")

    def test_species_is_cut_where_the_library_cuts_it(self):
        long_name = "Splice " + "a" * 80
        self.assertEqual(pet_art.species_of({"default_name": long_name}), long_name[:50])

    def test_cooldown_is_four_weeks_from_the_request(self):
        asked = datetime.datetime(2026, 11, 1, tzinfo=datetime.timezone.utc)
        self.assertEqual(pet_art.next_request_at(asked), datetime.datetime(2026, 11, 29, tzinfo=datetime.timezone.utc))
        self.assertIsNone(pet_art.next_request_at(None))

    def test_drawn_keys_reads_pet_sprites_json(self):
        self.assertEqual(pet_art.drawn_keys({"version": 1, "sprites": {"codexwyrm": {}, "pavorinex": {}}}),
                         {"codexwyrm", "pavorinex"})
        self.assertEqual(pet_art.drawn_keys(None), set())
        self.assertEqual(pet_art.drawn_keys({"sprites": []}), set())

    def test_batch_file_matches_the_hub_tools(self):
        rows = [{"id": 3, "species_key": "pavorinex", "species": "Pavorinex", "element": "Fire", "portrait": "https://x/p.png"}]
        made = datetime.datetime(2026, 11, 2, 10, 30, 5, 123, tzinfo=datetime.timezone.utc)
        data = pet_art.batch_file(rows, "2026-W45", made)
        self.assertEqual(data["batch"], "2026-W45")
        self.assertEqual(data["instructions"], "reports/Pets-Sprite-ArtPrompt.md")
        self.assertEqual(data["species"], [{"key": "pavorinex", "name": "Pavorinex", "element": "Fire", "owners": 1,
                                            "portrait": "https://x/p.png", "request": 3}])


    def test_sprite_entry_and_url(self):
        listing = {"sprites": {"codexwyrm": {"file": "codexwyrm", "frame": [48, 48]}, "odd": {"frame": [48, 48]}}}
        self.assertEqual(pet_art.sprite_entry(listing, "codexwyrm"), {"file": "codexwyrm", "frame": [48, 48]})
        self.assertIsNone(pet_art.sprite_entry(listing, "odd"))
        self.assertIsNone(pet_art.sprite_entry(listing, "missing"))
        self.assertIsNone(pet_art.sprite_entry(None, "codexwyrm"))
        self.assertEqual(pet_art.sheet_url("codexwyrm"), "https://game.fablereborn.xyz/games/hub/img/pets/codexwyrm.png")

    def test_sheet_preview_shows_every_frame_beside_the_portrait(self):
        import io
        from PIL import Image
        sheet = Image.new("RGBA", (144, 192))
        sheet.paste((200, 60, 60, 255), (16, 16, 32, 44))
        png = io.BytesIO()
        sheet.save(png, "PNG")
        portrait = io.BytesIO()
        Image.new("RGB", (400, 400), (20, 120, 200)).save(portrait, "JPEG")
        out = Image.open(io.BytesIO(pet_art.sheet_preview(png.getvalue(), (48, 48), portrait.getvalue(), "Pavorinex (pavorinex)")))
        self.assertEqual(out.format, "PNG")
        self.assertEqual(out.height, 12 * 2 + 18 + 192 * 3)
        self.assertEqual(out.width, 12 * 3 + 144 * 3 + 400 * 576 // 400)
        self.assertEqual(out.convert("RGB").getpixel((12 + 20 * 3, 12 + 18 + 20 * 3)), (200, 60, 60))
        alone = Image.open(io.BytesIO(pet_art.sheet_preview(png.getvalue(), (48, 48), b"not an image")))
        self.assertEqual(alone.size, (12 * 2 + 144 * 3, 12 * 2 + 192 * 3))


if __name__ == "__main__":
    unittest.main()
