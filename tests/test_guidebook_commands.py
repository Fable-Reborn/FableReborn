import asyncio
import sys
import types
import unittest


def _load_help():
    try:
        from cogs.help import GuidebookView, Help
        return GuidebookView, Help
    except ModuleNotFoundError:
        for name in list(sys.modules):
            if name == "cogs.help" or name.startswith("cogs.help."):
                del sys.modules[name]
        asyncpg = types.ModuleType("asyncpg")

        class UniqueViolationError(Exception):
            pass

        asyncpg.UniqueViolationError = UniqueViolationError
        sys.modules.setdefault("asyncpg", asyncpg)
        bot = types.ModuleType("classes.bot")

        class Bot:
            pass

        bot.Bot = Bot
        sys.modules.setdefault("classes.bot", bot)
        pytz = types.ModuleType("pytz")
        pytz.utc = None
        sys.modules.setdefault("pytz", pytz)
        from cogs.help import GuidebookView, Help
        return GuidebookView, Help


GuidebookView, Help = _load_help()


class FakeCommand:
    def __init__(self, brief="", doc="", help_text=""):
        self.brief = brief
        self.help = help_text

        async def callback():
            return None

        callback.__doc__ = doc or None
        self.callback = callback


class FakeContext:
    clean_prefix = "$"


class TestGuidebookCommands(unittest.TestCase):
    def test_one_liner_uses_the_docstring_when_the_brief_is_missing(self):
        command = FakeCommand(
            brief="",
            doc="Feed a pet so it does not starve.\n\n`<pet>` - the pet to feed",
        )
        line = Help._command_one_liner(command)
        self.assertEqual(line, "Feed a pet so it does not starve.")
        self.assertNotIn("No brief description", line)

    def test_one_liner_ignores_a_placeholder_brief(self):
        command = FakeCommand(brief="No brief description.", doc="Show your profile.")
        self.assertEqual(Help._command_one_liner(command), "Show your profile.")

    def test_help_text_keeps_the_real_docs_and_fills_in_the_prefix(self):
        command = FakeCommand(doc="Open it with `{prefix}pets`.")
        text = Help._command_help_text(command, "$")
        self.assertEqual(text, "Open it with `$pets`.")

    def test_categories_use_the_live_cog_names(self):
        help_cog = Help(None)
        mapping = help_cog._command_category_map()
        economy = mapping["Economy & Social"]["cogs"]
        events = mapping["Events & Special Systems"]["cogs"]
        games = mapping["Games & Side Modes"]["cogs"]
        combat = mapping["Combat & Challenges"]["cogs"]
        stories = mapping["Stories & Extra Systems"]["cogs"]

        self.assertIn("Scheduling", economy)
        self.assertNotIn("Scheduler", economy)
        self.assertIn("Christmas", events)
        self.assertNotIn("Wintersday", events)
        self.assertIn("Slots", games)
        self.assertNotIn("DragonSlots", games)
        self.assertIn("CardsAgainstHumanity", games)
        self.assertIn("Lottery", games)
        self.assertIn("Shotgunroulette", games)
        self.assertIn("SlayTheSpire", combat)
        self.assertIn("Fables", stories)
        self.assertIn("Companions", stories)

    def test_uncategorized_commands_land_in_additional(self):
        help_cog = Help(None)
        categories = help_cog._build_command_categories(
            {
                "Scheduling": [{"qualified": "schedule", "one_liner": "Plan something"}],
                "Fables": [{"qualified": "fables", "one_liner": "Open the library"}],
                "MysteryCog": [{"qualified": "mystery", "one_liner": "Does something else"}],
            },
            ["Scheduling", "Fables", "MysteryCog"],
        )
        by_label = {category["label"]: [entry["qualified"] for entry in category["commands"]] for category in categories}
        self.assertEqual(by_label["Economy & Social"], ["schedule"])
        self.assertEqual(by_label["Stories & Extra Systems"], ["fables"])
        self.assertEqual(by_label["Additional"], ["mystery"])

    def _sections(self):
        sections = []
        for index in range(25):
            sections.append(
                {
                    "label": f"Topic {index}",
                    "summary": f"Summary {index}",
                    "emoji": "📖",
                    "pages": [{"title": "Page", "description": "Hello", "fields": []}],
                }
            )
        commands = [
            {
                "qualified": f"cmd{index}",
                "usage": f"$cmd{index}",
                "one_liner": f"Does thing {index}",
                "help_text": f"Full help for cmd{index}.",
                "aliases": ["c"],
            }
            for index in range(30)
        ]
        sections.append(
            {
                "label": "Commands",
                "summary": "Pick a category, then a command.",
                "emoji": "📚",
                "kind": "commands",
                "categories": [
                    {
                        "label": "Starter & Progression",
                        "description": "Start here",
                        "commands": commands,
                    }
                ],
                "pages": [{"title": "How", "description": "Use the menus", "fields": []}],
            }
        )
        return sections

    def test_command_browser_and_second_dropdown_page(self):
        async def scenario():
            view = GuidebookView(ctx=FakeContext(), sections=self._sections(), color=0)
            self.assertEqual(view.prev_page_button.label, "Prev Page")
            self.assertIsNone(view.command_select)

            view.section_index = 25
            view._sync_controls()
            embed = view._build_embed()

            self.assertEqual(view.prev_page_button.label, "Prev commands")
            self.assertEqual(view.next_page_button.label, "Next commands")
            self.assertEqual(view.prev_index_button.label, "Previous sections")
            self.assertEqual(view.next_index_button.label, "More sections")
            self.assertIsNotNone(view.category_select)
            self.assertEqual(len(view.command_select.options), 25)
            self.assertEqual(embed.title, "📚 cmd0")
            self.assertIn("Full help for cmd0.", embed.description)
            selected = [option for option in view.section_select.options if option.default]
            self.assertEqual([option.value for option in selected], ["25"])

            view.command_chunk = 1
            view.command_index = 25
            view._sync_controls()
            embed = view._build_embed()
            self.assertEqual(view.command_select.options[0].label, "cmd25")
            self.assertEqual(embed.title, "📚 cmd25")
            self.assertTrue(view.command_select.options[0].default)

            view.section_index = 0
            view._sync_controls()
            self.assertEqual(view.prev_page_button.label, "Prev Page")
            self.assertIsNone(view.command_select)
            self.assertIsNone(view.category_select)
            view.stop()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
