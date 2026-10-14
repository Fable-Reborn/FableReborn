"""Adventure flavor for cogs/adventure/__init__.py when this event ships.

Not imported. Do not replace ADVENTURE_EVENTS. The normal stories stay where
they are. This branch only runs while the Halloween flag is on.

Inside get_adventure_narrative, before the Shrek / tier lookup:

    events = []
    if self._is_event_enabled("halloween"):
        try:
            from cogs.halloweenmanor.adventure_flavor import HALLOWEEN_ADVENTURE_LINES
            events = list(HALLOWEEN_ADVENTURE_LINES)
        except Exception:
            events = []
    if not events:
        if adventure_name == "Shrek's Swamp":
            events = self.ADVENTURE_EVENTS["Shrek's Swamp"]
        else:
            tier = f"tier_{min(10, max(1, (adventure_level - 1) // 10 + 1))}"
            events = self.ADVENTURE_EVENTS[tier]

When the flag is off, or the flavor module cannot be imported, the method
uses the existing lists. Bones already follow the same flag in this file.
"""
