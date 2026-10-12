"""Boot rule for cogs/game_master/__init__.py when this event ships.

Not imported. The live loader still restores every event_settings row,
including Halloween, into memory on startup.

At the end of _init_event_settings, after bot.event_flags is assigned,
force Halloween off in memory only. Do not write the database. A restart
must not turn the event back on. A GM turns it on afterward with
$gmevent halloween on, which is the existing command and still saves the row.

    self.event_flags["halloween"] = False
    self.bot.event_flags = self.event_flags

That one flag is the whole event. Bones, the spooky shop, Hollow Manor, and
the adventure flavor all read it. Loading the cogs in config.toml only
registers the commands. It does not enable the event.
"""
