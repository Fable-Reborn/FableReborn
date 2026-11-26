import datetime
import types
import unittest

import discord

from cogs.gm_events import announce, draft as draftlib
from cogs.gm_events.announce import build_announcement

ENDS = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)


def embeds_text(embeds):
    parts = []
    for e in embeds:
        parts += [e.title or "", e.description or ""]
        for f in e.fields:
            parts += [f.name, f.value]
        if e.footer and e.footer.text:
            parts.append(e.footer.text)
    return "\n".join(parts)


def fields(embed):
    return {f.name: f.value for f in embed.fields}


class AnnouncementTests(unittest.TestCase):
    def test_classic(self):
        content, (main, howto) = build_announcement(
            "classic", name="Dragon Egg", title="Big", message="Rare!", gm_name="Gm", prefix="!",
            role_mention="<@&5>",
        )
        self.assertEqual(content, "<@&5>")
        self.assertEqual(main.title, "Big")
        self.assertEqual(main.description, "Rare!")
        self.assertIn("12 hours", fields(main)["Ends"])
        self.assertIn("!bid <amount>", howto.description)
        self.assertIn("can't outbid yourself", howto.description)
        self.assertIn("12 hours", howto.description)
        self.assertEqual(main.footer.text, "Hosted by Gm")

    def test_silent(self):
        _c, (main, howto) = build_announcement(
            "silent", name="Sword", gm_name="Gm", prefix="$", ends_at=ENDS, min_bid=1500
        )
        f = fields(main)
        self.assertEqual(f["Minimum bid"], "$1,500")
        self.assertIn(f"<t:{int(ENDS.timestamp())}:R>", f["Ends"])
        self.assertIn("minimum $1,500", howto.description)
        self.assertIn("can't lower or withdraw", howto.description)
        self.assertIn("$silentbid <amount>", howto.description)
        self.assertIn("reached that amount first", howto.description)
        self.assertEqual(main.title, "🔒 Silent Auction: Sword")

    def test_raffle(self):
        _c, (main, howto) = build_announcement(
            "raffle", name="Crate", gm_name="Gm", prefix="$", ends_at=None, ticket_price=250,
            max_per_user=5, commitment="ab" * 32,
        )
        f = fields(main)
        self.assertEqual(f["Ticket price"], "$250")
        self.assertEqual(f["Max per player"], "5")
        self.assertEqual(f["Ends"], "When a GM draws")
        self.assertIn("ab" * 32, f["Fairness commitment"])
        self.assertIn("$raffle buy <amount>", howto.description)
        self.assertIn("$250", howto.description)
        self.assertIn("max 5 per player", howto.description)
        self.assertIn("when a GM draws", howto.description)
        self.assertIn("isn't refunded unless the raffle is cancelled", howto.description)

    def test_raffle_without_cap_and_ticket_counter(self):
        _c, (main, howto) = build_announcement(
            "raffle", name="X", gm_name="G", ticket_price=1, commitment="c", tickets=7, entrants=3
        )
        self.assertEqual(fields(main)["Max per player"], "No limit")
        self.assertIn("7 tickets, 3 players", fields(main)["Tickets sold"])
        self.assertIn("no limit per player", howto.description)

    def test_ping_only_changes_content(self):
        kw = dict(name="X", gm_name="G", ends_at=ENDS, min_bid=5, title="T", message="M")
        on = build_announcement("silent", role_mention="<@&1>", **kw)
        off = build_announcement("silent", role_mention=None, **kw)
        self.assertEqual(on[0], "<@&1>")
        self.assertIsNone(off[0])
        self.assertEqual([e.to_dict() for e in on[1]], [e.to_dict() for e in off[1]])

    def test_everyone_stays_text_and_mentions_are_restricted(self):
        _c, (main, _h) = build_announcement(
            "classic", name="@everyone item", message="hi @everyone <@&99> <@123>", gm_name="G"
        )
        self.assertIn("@everyone", main.description)
        role = types.SimpleNamespace(id=7)
        on = announce.allowed_mentions_for(role, True)
        self.assertFalse(on.everyone)
        self.assertFalse(on.users)
        self.assertEqual(on.roles, [role])
        off = announce.allowed_mentions_for(role, False)
        self.assertIs(off.roles, False)
        self.assertIs(announce.allowed_mentions_for(None, True).roles, False)

    def test_blank_announcement_uses_default_line(self):
        for kind, kw in (("classic", {}), ("silent", {"min_bid": 1, "ends_at": ENDS}),
                         ("raffle", {"ticket_price": 1, "commitment": "c"})):
            _c, (main, _h) = build_announcement(kind, name="X", title="  ", message="  ", gm_name="G", **kw)
            self.assertEqual(main.description, announce.default_message(kind))
            self.assertEqual(main.title, announce.default_title(kind, "X"))

    def test_maximum_length_input_stays_within_discord_limits(self):
        long = "x" * 5000
        for kind, kw in (("classic", {}), ("silent", {"min_bid": 10**15, "ends_at": ENDS}),
                         ("raffle", {"ticket_price": 10**12, "max_per_user": 1000,
                                     "commitment": "f" * 64, "tickets": 10**6, "entrants": 10**5})):
            _c, embeds = build_announcement(
                kind, name=long, title=long, message=long, gm_name=long, **kw
            )
            self.assertLessEqual(sum(len(e) for e in embeds), 6000, kind)
            for e in embeds:
                self.assertLessEqual(len(e.title), 256)
                self.assertLessEqual(len(e.description), 4096)
                for f in e.fields:
                    self.assertLessEqual(len(f.value), 1024)
                    self.assertLessEqual(len(f.name), 256)
            self.assertLessEqual(len(embeds[0].footer.text), 2048)

    def test_gm_text_is_not_translated_or_formatted(self):
        _c, (main, _h) = build_announcement(
            "classic", name="{item}", message="{0} {x} %s", gm_name="G"
        )
        self.assertEqual(main.description, "{0} {x} %s")
        self.assertEqual(fields(main)["Item"], "{item}")


class RerenderTests(unittest.TestCase):
    """A later edit (e.g. the raffle ticket counter) must keep the GM's announcement."""

    def make(self):
        from cogs.gm_events import GMEvents

        fake = types.SimpleNamespace(
            _gm_name=lambda uid: "Gm",
            bot=types.SimpleNamespace(config=types.SimpleNamespace(bot=types.SimpleNamespace(global_prefix="$"))),
        )
        return GMEvents, fake

    def test_raffle_row_keeps_announcement_and_title(self):
        GMEvents, fake = self.make()
        row = {
            "prize": "Crate", "announcement": "Special crate for the community!",
            "announcement_title": "Crate Night", "created_by": 1, "ends_at": None,
            "ticket_price": 100, "max_per_user": 3, "seed_commitment": "ab" * 32,
        }
        embeds = GMEvents._row_embeds(fake, "raffle", row, tickets=12, entrants=4)
        self.assertEqual(embeds[0].title, "Crate Night")
        self.assertEqual(embeds[0].description, "Special crate for the community!")
        self.assertIn("12 tickets, 4 players", fields(embeds[0])["Tickets sold"])
        self.assertEqual(len(embeds), 2)

    def test_silent_row_without_announcement_uses_defaults(self):
        GMEvents, fake = self.make()
        row = {
            "item": "Sword", "announcement": None, "announcement_title": None, "created_by": 1,
            "ends_at": ENDS, "min_bid": 10,
        }
        embeds = GMEvents._row_embeds(fake, "silent", row)
        self.assertEqual(embeds[0].description, announce.default_message("silent"))


class DraftTests(unittest.TestCase):
    def test_classic_needs_only_a_name(self):
        errors, parsed = draftlib.validate(draftlib.Draft(kind="classic", name=" Egg "))
        self.assertEqual(errors, [])
        self.assertEqual(parsed.name, "Egg")
        self.assertIsNone(parsed.duration)
        self.assertTrue(draftlib.validate(draftlib.Draft(kind="classic"))[0])

    def test_silent_validation(self):
        good = draftlib.Draft(kind="silent", name="X", min_bid="1,000", duration="1d12h")
        errors, parsed = draftlib.validate(good)
        self.assertEqual(errors, [])
        self.assertEqual((parsed.min_bid, parsed.duration), (1000, datetime.timedelta(hours=36)))
        for field, value in (("min_bid", "abc"), ("min_bid", "0"), ("duration", "1m"),
                             ("duration", "15d"), ("duration", ""), ("name", "")):
            bad = draftlib.Draft(**{**good.__dict__, field: value})
            errors, parsed = draftlib.validate(bad)
            self.assertTrue(errors, (field, value))
            self.assertIsNone(parsed)

    def test_raffle_validation(self):
        base = draftlib.Draft(kind="raffle", name="P", ticket_price="1k", duration="manual")
        errors, parsed = draftlib.validate(base)
        self.assertEqual(errors, [])
        self.assertEqual((parsed.ticket_price, parsed.max_per_user, parsed.duration), (1000, None, None))
        capped = draftlib.Draft(**{**base.__dict__, "max_per_user": "25", "duration": "3d"})
        parsed = draftlib.validate(capped)[1]
        self.assertEqual((parsed.max_per_user, parsed.duration), (25, datetime.timedelta(days=3)))
        for field, value in (("max_per_user", "0"), ("max_per_user", "1001"), ("max_per_user", "x"),
                             ("ticket_price", ""), ("ticket_price", str(10**13)), ("duration", ""),
                             ("duration", "1m")):
            errors, parsed = draftlib.validate(draftlib.Draft(**{**base.__dict__, field: value}))
            self.assertTrue(errors, (field, value))
            self.assertIsNone(parsed)

    def test_text_limits(self):
        d = draftlib.Draft(kind="classic", name="X", title="t" * 101, message="m" * 1501)
        self.assertEqual(len(draftlib.validate(d)[0]), 2)

    def test_switch_keeps_shared_and_clears_type_fields(self):
        d = draftlib.Draft(kind="silent", name="Sword", min_bid="5", duration="1h",
                           title="T", message="M", ping=False)
        r = draftlib.switch_kind(d, "raffle")
        self.assertEqual((r.kind, r.name, r.title, r.message, r.ping), ("raffle", "Sword", "T", "M", False))
        self.assertEqual((r.min_bid, r.duration, r.ticket_price, r.max_per_user), ("", "", "", ""))
        self.assertEqual(d.min_bid, "5")  # original untouched

    def test_invalid_input_is_kept_raw(self):
        d = draftlib.Draft(kind="silent", name="X", min_bid="oops", duration="1h")
        draftlib.validate(d)
        self.assertEqual(d.min_bid, "oops")


class BuilderImportTests(unittest.TestCase):
    def test_builder_module_and_command_registered(self):
        from cogs.gm_events import GMEvents, builder

        self.assertTrue(hasattr(builder, "BuilderView"))
        command = GMEvents.gmauctionbuilder
        self.assertEqual(command.name, "gmauctionbuilder")
        self.assertEqual(set(command.aliases), {"gmab", "auctionbuilder"})


if __name__ == "__main__":
    unittest.main()
