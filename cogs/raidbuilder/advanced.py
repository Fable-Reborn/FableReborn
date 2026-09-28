"""Form/select authoring and Discord adapter for the encounter engine."""

import asyncio
import copy

import discord

from discord.ui import Button, Select, View

from utils.joins import JoinView

from .engine import (
    EFFECTS,
    NODE_KINDS,
    OPERATORS,
    TARGETS,
    TRIGGERS,
    EncounterEngine,
    default_node,
    default_rule,
    validate_encounter,
)
from .storage import registry_edit
from .mechanics import upgrade_encounter
from .runtime_ui import RoleAssignmentView, BattleDecisionView


def _options(values):
    return [(str(key), str(label)) for key, label in values]


class OptionSelect(Select):
    def __init__(self, editor, field, page=0):
        self.editor = editor
        self.builder_view = editor.builder_view
        self.edit_revision = editor.edit_revision
        self.field_key = field["key"]
        self.page = page
        values = field["options"]
        options = [
            discord.SelectOption(
                label=label[:100], value=key, default=key == str(field["value"])
            )
            for key, label in values[page : page + 23]
        ]
        if page:
            options.append(
                discord.SelectOption(label="Previous choices", value="__previous__")
            )
        if page + 23 < len(values):
            options.append(discord.SelectOption(label="More choices", value="__next__"))
        super().__init__(placeholder=field["label"][:100], options=options)

    @registry_edit
    async def callback(self, interaction):
        value = self.values[0]
        payload = self.editor.payload()
        field = next(f for f in payload["option_fields"] if f["key"] == self.field_key)
        if value in {"__previous__", "__next__"}:
            self.editor.pages[self.field_key] = max(
                0, self.page + (23 if value == "__next__" else -23)
            )
        else:
            if value not in {key for key, _ in field["options"]}:
                raise ValueError("That option no longer exists.")
            field["set"](value)
            await self.builder_view.cog._save_registry()
        self.editor.edit_revision = self.builder_view.cog.registry_revision
        self.editor.rebuild()
        await interaction.response.edit_message(
            content="Settings save automatically. Use Details for text and numbers.",
            view=self.editor,
        )
        await self.builder_view.refresh_message()


class AdvancedOptionsView(View):
    def __init__(self, panel):
        super().__init__(timeout=600)
        self.builder_view = panel
        self.definition_id = panel.selected_definition_id
        self.page_key = panel.current_page_key
        self.item_key = panel.current_item_key
        self.edit_revision = panel.cog.registry_revision
        self.pages = {}
        self.rebuild()

    def payload(self):
        definition = self.builder_view.cog._get_definition(self.definition_id)
        self.builder_view.cog._assert_owned(
            definition, self.builder_view.author.id, draft=True
        )
        return self.builder_view.cog._advanced_page_payload(
            definition, self.page_key, self.item_key
        )

    def rebuild(self):
        self.clear_items()
        for field in self.payload().get("option_fields", []):
            self.add_item(OptionSelect(self, field, self.pages.get(field["key"], 0)))
        button = Button(label="Details", style=discord.ButtonStyle.primary)
        button.callback = self.details
        self.add_item(button)

    @registry_edit
    async def details(self, interaction):
        from . import RaidBuilderFormModal

        payload = self.payload()
        modal = RaidBuilderFormModal(
            self.builder_view,
            title=payload["form_title"],
            fields=payload["form_fields"],
            submit_handler=payload["submit_handler"],
        )
        modal.definition_id, modal.page_key, modal.item_key = (
            self.definition_id,
            self.page_key,
            self.item_key,
        )
        await interaction.response.send_modal(modal)


class DecisionView(View):
    def __init__(self, options, eligible, timeout):
        super().__init__(timeout=timeout)
        self.eligible = set(eligible)
        self.decisions = {}
        selector = Select(
            placeholder="Choose your action",
            options=[
                discord.SelectOption(label=label[:100], value=key)
                for key, label in options
            ],
        )
        selector.callback = self.choose
        self.add_item(selector)
        self.selector = selector

    async def choose(self, interaction):
        key = str(interaction.user.id)
        if key not in self.eligible:
            return await interaction.response.send_message(
                "Only surviving participants can choose.", ephemeral=True
            )
        self.decisions[key] = self.selector.values[0]
        await interaction.response.send_message("Choice recorded.", ephemeral=True)
        if len(self.decisions) == len(self.eligible):
            self.stop()


class AdvancedBuilderMixin:
    def _advanced_page_specs(self):
        return [
            {"key": key, "label": label, "description": description}
            for key, label, description in (
                (
                    "overview",
                    "Overview",
                    "Name, description, health and join/decision timers",
                ),
                ("flow", "Flow", "Starting step, pacing and encounter limits"),
                ("canvas", "Visual Canvas", "Drag-and-drop editing: teams, roles, enemies, statuses and AND/OR rules"),
                (
                    "steps",
                    "Steps",
                    "Scenes, battles, trials, checks, votes and endings",
                ),
                ("links", "Step Links", "Success, failure and timeout destinations"),
                (
                    "battle",
                    "Battle / Trial",
                    "Boss stats, round limits and trial chance",
                ),
                ("check", "Step Condition", "Conditions for branching check steps"),
                ("resources", "Resources", "Named shared meters with bounds"),
                (
                    "actions",
                    "Player Actions",
                    "Combine effects, targets and resource costs",
                ),
                ("choices", "Choices", "Labels and destinations for player votes"),
                ("rules", "Rules: When / If", "Triggers, conditions and repeat limits"),
                ("effects", "Rules: Do", "Effects, targets and amounts"),
                (
                    "rewards",
                    "Rewards",
                    "Victory rewards using the normal raid reward system",
                ),
                (
                    "simulate",
                    "Validate / Simulate",
                    "Test with simulated players before publishing",
                ),
            )
        ]

    def _advanced_item_options(self, definition, page):
        spec = definition["config"]["encounter"]
        if page in {"steps", "links", "battle", "check"}:
            items = spec["nodes"]
        elif page in {"resources", "actions"}:
            items = spec[page]
        elif page in {"rules", "effects", "choices"}:
            collection = "choices" if page == "choices" else "rules"
            result = []
            for node in spec["nodes"]:
                if page == "choices" and node["kind"] != "choice":
                    continue
                entries = node.get(collection, [])
                for entry in entries:
                    result.append(
                        {
                            "key": node["id"] + "|" + entry["id"],
                            "label": f"{node['title']}: {entry.get('label', entry['id'])}",
                            "description": collection.title(),
                        }
                    )
                if not entries:
                    result.append(
                        {
                            "key": node["id"] + "|",
                            "label": node["title"] + " (empty)",
                            "description": "Use Structure > Add to create an entry",
                        }
                    )
            return result
        else:
            return []
        return [
            {
                "key": item["id"],
                "label": item.get("label", item.get("title", item["id"])),
                "description": item["id"],
            }
            for item in items
        ]

    def _advanced_collection(self, definition, page, item_key):
        spec = definition["config"]["encounter"]
        if page in {"steps", "resources", "actions"}:
            return spec["nodes" if page == "steps" else page], item_key, None
        if page in {"rules", "effects", "choices"} and item_key and "|" in item_key:
            node_id, entry_id = item_key.split("|", 1)
            node = next(n for n in spec["nodes"] if n["id"] == node_id)
            return node["choices" if page == "choices" else "rules"], entry_id, node
        return None, None, None

    def _advanced_structure_state(self, definition, page, item_key):
        items, key, _ = self._advanced_collection(definition, page, item_key)
        if items is None:
            return {
                "supported": False,
                "reason": "Use Steps, Resources, Actions, Choices or Rules.",
            }
        index = next((i for i, item in enumerate(items) if item["id"] == key), 0)
        return {
            "supported": True,
            "entity_label": page,
            "selected_label": key or "empty",
            "position": index + 1 if items else 0,
            "total": len(items),
            "can_delete": bool(items),
            "can_move_up": index > 0,
            "can_move_down": index + 1 < len(items),
        }

    async def _advanced_structure_action(
        self, definition, page, item_key, action, *, delta=0
    ):
        items, key, node = self._advanced_collection(definition, page, item_key)
        if items is None:
            raise ValueError("Choose a collection page first.")
        index = next((i for i, item in enumerate(items) if item["id"] == key), 0)
        if action in {"add", "duplicate"}:
            maximum = 100 if page in {"steps", "rules", "effects"} else 25
            if len(items) >= maximum:
                raise ValueError(f"This collection supports up to {maximum} entries.")
            key = self._unique_builder_key(
                {i["id"] for i in items},
                {"effects": "rule", "rules": "rule"}.get(page, page.rstrip("s")),
            )
            if action == "duplicate" and items:
                entry = copy.deepcopy(items[index])
                entry["id"] = key
            elif page == "steps":
                entry = default_node(key)
            elif page == "resources":
                entry = {
                    "id": key,
                    "label": key.title(),
                    "initial": 0,
                    "min": 0,
                    "max": 100,
                }
            elif page == "actions":
                entry = {
                    "id": key,
                    "label": key.title(),
                    "effect": "boss_damage",
                    "target": "self",
                    "amount": 10,
                    "resource": "",
                    "cost_resource": "",
                    "cost": 0,
                }
            elif page == "choices":
                entry = {"id": key, "label": key.title(), "next": "victory"}
            else:
                entry = default_rule(key)
            items.insert(index + 1 if items else 0, entry)
        elif action == "delete":
            if not items:
                raise ValueError("This collection is empty.")
            # Drafts may temporarily contain broken links; publication validates them.
            items.pop(index)
            key = items[min(index, len(items) - 1)]["id"] if items else ""
        elif action == "move":
            if not items:
                raise ValueError("This collection is empty.")
            target = max(0, min(len(items) - 1, index + delta))
            items.insert(target, items.pop(index))
        await self._save_registry()
        return (
            page,
            (node["id"] + "|" + (key or "")) if node else key,
            "Structure saved. Validate before publishing.",
        )

    def _advanced_page_payload(self, definition, page, item_key):
        config, spec = definition["config"], definition["config"]["encounter"]
        if page == "canvas":
            return {"title": "Advanced Raid Canvas", "description": "Press Edit to download your visual editor. Arrange steps, add roles and teams, define statuses and enemies, and build nested AND/OR conditions without code. Save the file, then upload it with `raidmode import " + definition["id"] + "`.", "fields": [], "form_fields": [], "submit_handler": None}
        fields, option_fields = [], []
        description = "Use Edit for details and selectors; Structure adds, copies and removes entries. Drafts autosave."
        target = spec

        def field(key, label, default, parser=str):
            fields.append(
                {
                    "key": key,
                    "label": label,
                    "default": str(default),
                    "parser": parser,
                    "style": (
                        discord.TextStyle.paragraph
                        if key in {"text", "description"}
                        else discord.TextStyle.short
                    ),
                }
            )

        def number(key, label, default, low=0, high=1_000_000):
            field(
                key,
                label,
                default,
                lambda value: self._parse_int(
                    value, label, min_value=low, max_value=high
                ),
            )

        def option(key, label, values, obj=None):
            obj = target if obj is None else obj
            option_fields.append(
                {
                    "key": key,
                    "label": label,
                    "value": obj.get(key, ""),
                    "options": _options(values),
                    "set": lambda value, obj=obj, key=key: obj.__setitem__(key, value),
                }
            )

        node_options = [(n["id"], n["title"]) for n in spec["nodes"]]
        resource_options = [("", "None")] + [
            (r["id"], r["label"]) for r in spec["resources"]
        ]
        subjects = [
            (key, label)
            for key, label in (
                ("round", "Round"),
                ("alive", "Living players"),
                ("boss_hp", "Boss HP"),
                ("boss_hp_percent", "Boss HP %"),
            )
        ] + resource_options[1:]
        if page == "overview":
            field("name", "Raid name", definition["name"])
            field("description", "Description", definition["description"])
            number("player_hp", "Starting player health", spec["player_hp"], 1)
            number(
                "join_timeout", "Join window (seconds)", config["join_timeout"], 30, 900
            )
            number(
                "decision_timeout",
                "Decision window (seconds)",
                config["decision_timeout"],
                10,
                180,
            )
        elif page == "flow":
            option("start", "Starting step", node_options)
            number("max_steps", "Maximum engine steps", spec["max_steps"], 1, 1000)
            number("step_delay", "Scene delay (seconds)", config["step_delay"], 1, 30)
        elif page in {"steps", "links", "battle", "check"}:
            target = next((n for n in spec["nodes"] if n["id"] == item_key), None)
            if target:
                if page == "steps":
                    option("kind", "Step type", [(k, k.title()) for k in NODE_KINDS])
                    option(
                        "outcome",
                        "Ending outcome",
                        [("victory", "Victory"), ("defeat", "Defeat")],
                    )
                    field("title", "Title", target["title"])
                    field("text", "Narration", target["text"])
                elif page == "links":
                    option("next", "Success / next step", node_options)
                    option("failure", "Failure / tie / timeout", node_options)
                    field("text", "Narration", target["text"])
                elif page == "battle":
                    number("boss_hp", "Boss health", target["boss_hp"], 1)
                    number(
                        "boss_damage", "Boss damage per round", target["boss_damage"]
                    )
                    number(
                        "max_rounds",
                        "Maximum battle rounds",
                        target["max_rounds"],
                        1,
                        100,
                    )
                    number(
                        "chance", "Trial success chance (%)", target["chance"], 0, 100
                    )
                else:
                    option("subject", "Condition subject", subjects)
                    option("operator", "Comparison", [(k, k) for k in OPERATORS])
                    number("value", "Compared value", target["value"], -1_000_000)
        elif page in {"resources", "actions", "rules", "effects", "choices"}:
            items, key, node = self._advanced_collection(definition, page, item_key)
            target = next((i for i in (items or []) if i["id"] == key), None)
            if target:
                if page == "resources":
                    field("label", "Resource name", target["label"])
                    for key in ("initial", "min", "max"):
                        number(key, key.title(), target[key], -1_000_000)
                elif page == "choices":
                    option("next", "Choice destination", node_options)
                    field("label", "Choice label", target["label"])
                elif page == "rules":
                    option(
                        "trigger",
                        "WHEN",
                        [(k, k.replace("_", " ").title()) for k in TRIGGERS],
                    )
                    option("subject", "IF subject", subjects)
                    option("operator", "Comparison", [(k, k) for k in OPERATORS])
                    number("value", "Compared value", target["value"], -1_000_000)
                    number("limit", "Maximum firings per raid", target["limit"], 1, 100)
                    field("text", "Announcement text", target["text"])
                else:
                    option(
                        "effect",
                        "DO effect",
                        [
                            (k, k.replace("_", " ").title())
                            for k in EFFECTS
                            if page != "actions" or k != "transition"
                        ],
                    )
                    targets = [(k, k.replace("_", " ").title()) for k in TARGETS]
                    targets += [("team:" + t["id"], "Team: " + t["label"]) for t in spec.get("teams", [])]
                    targets += [("role:" + r["id"], "Role: " + r["label"]) for r in spec.get("roles", [])]
                    option("target", "Target", targets)
                    if target.get("effect") in {"apply_status", "remove_status"}:
                        option("status", "Status", [("", "Choose a status in Canvas")] + [(s["id"], s["label"]) for s in spec.get("statuses", [])])
                    else:
                        option("resource", "Resource to change", resource_options)
                    if page == "actions":
                        option("cost_resource", "Resource to spend", resource_options)
                        field("label", "Action label", target["label"])
                        number("cost", "Resource cost", target["cost"])
                    else:
                        option("destination", "Transition destination", node_options)
                    number(
                        "amount",
                        "Effect amount",
                        target["amount"],
                        -1_000_000 if target["effect"] == "resource" else 0,
                    )
                    field("text", "Announcement text", target.get("text", ""))
        elif page == "rewards":
            return self._reward_page_payload(
                definition,
                description="Paid only on victory; simulations award nothing.",
                bonus_label="Survivor",
                dragon_coin_label="Survivor",
                crate_recipient_label="survivor",
                submit_message="Updated advanced raid rewards.",
            )
        elif page == "simulate":
            description = "Runs the same engine with simulated players and a repeatable random seed. No real players or rewards."
            number("players", "Simulated player count", 5, 1, 100)
            number("seed", "Random seed", 42, 0, 1_000_000)

        if page in {"check", "rules"} and target and target.get("condition") is not None:
            description += " This entry uses a compound condition. Edit its AND/OR tree in Visual Canvas."
            fields = [f for f in fields if f["key"] != "value"]
            option_fields = [f for f in option_fields if f["key"] not in {"subject", "operator"}]

        async def submit(values):
            # Parse all inputs before mutating, so rejected forms cannot partially save.
            parsed = {f["key"]: f["parser"](values[f["key"]]) for f in fields}
            if page == "simulate":
                engine = EncounterEngine(
                    spec, range(parsed["players"]), seed=parsed["seed"]
                )
                frames = engine.simulate()
                trace = "\n".join(
                    f"{f.title}: {'; '.join(f.events[:2]) or f.text[:80]}"
                    for f in frames[-8:]
                )
                return f"Simulation: **{engine.outcome}**, {engine.steps} steps, {len(engine.alive)} survivors.\n{trace}"[
                    :1900
                ]
            if page == "overview":
                if (
                    not parsed["name"].strip()
                    or len(parsed["name"]) > 100
                    or len(parsed["description"]) > 3500
                ):
                    raise ValueError(
                        "Use a name of 1-100 characters and a description of at most 3500."
                    )
                definition.update(
                    name=parsed["name"], description=parsed["description"]
                )
                spec["player_hp"] = parsed["player_hp"]
                config.update(
                    join_timeout=parsed["join_timeout"],
                    decision_timeout=parsed["decision_timeout"],
                )
                config["announce"].update(
                    title=parsed["name"], description=parsed["description"]
                )
            elif page == "flow":
                spec["max_steps"] = parsed["max_steps"]
                config["step_delay"] = parsed["step_delay"]
            elif target is None:
                raise ValueError("Add an entry with Structure first.")
            else:
                if "label" in parsed and not 1 <= len(parsed["label"].strip()) <= 100:
                    raise ValueError("Labels must contain 1-100 characters.")
                if "title" in parsed and not 1 <= len(parsed["title"].strip()) <= 256:
                    raise ValueError("Titles must contain 1-256 characters.")
                if len(parsed.get("text", "")) > 3500:
                    raise ValueError("Narration must fit 3500 characters.")
                target.update(parsed)
            await self._save_registry()
            return "Advanced draft saved."

        summary = [
            {"name": f["label"], "value": str(f["default"])[:500] or "None"}
            for f in fields
        ]
        summary += [
            {
                "name": f["label"],
                "value": next(
                    (label for key, label in f["options"] if key == str(f["value"])),
                    "Choose an option",
                ),
            }
            for f in option_fields
        ]
        if target is None:
            description = "This collection is empty. Choose Structure > Add. For choices, first create a step with type Choice."
        return {
            "title": (definition["name"] + " • Advanced • " + page.title())[:256],
            "description": description,
            "fields": summary,
            "form_fields": fields,
            "option_fields": option_fields,
            "form_title": "Advanced: " + page.title(),
            "submit_handler": submit if fields else None,
        }

    async def _run_encounter_definition(self, ctx, definition):
        config = definition["config"]
        validate_encounter(config["encounter"])
        join = JoinView(
            Button(label="Join", style=discord.ButtonStyle.primary),
            message="You joined the encounter.",
            timeout=config["join_timeout"],
        )
        message = await ctx.send(
            embed=discord.Embed(
                title=definition["name"], description=definition["description"]
            ),
            view=join,
        )
        await join.wait()
        await message.edit(view=None)
        users = await self._filter_eligible_users(
            list(join.joined), config.get("eligibility", {}).get("god")
        )
        if not users:
            await ctx.send("No eligible players joined this encounter.")
            return
        spec = upgrade_encounter(config["encounter"])
        role_choices = {}
        if len(spec["roles"]) > 1:
            roles = RoleAssignmentView(spec["roles"], [u.id for u in users], config["decision_timeout"])
            role_message = await ctx.send("Choose your raid role. Players who do not choose receive the unlimited fallback role.", view=roles)
            await roles.wait()
            await role_message.edit(view=None)
            role_choices = roles.choices
        engine = EncounterEngine(spec, [u.id for u in sorted(users, key=lambda u: u.id)], role_choices=role_choices)
        while engine.outcome is None:
            options = engine.prompt()
            decisions = {}
            if options:
                view = (BattleDecisionView(engine, config["decision_timeout"])
                    if engine.nodes[engine.node_id]["kind"] == "battle"
                    else DecisionView(options, engine.alive, config["decision_timeout"]))
                node = engine.nodes[engine.node_id]
                prompt = await ctx.send(
                    embed=discord.Embed(title=node["title"], description=node["text"]),
                    view=view,
                )
                await view.wait()
                await prompt.edit(view=None)
                decisions = view.decisions
            frame = engine.advance(decisions)
            details = "\n".join(frame.events)
            embed = discord.Embed(
                title=frame.title, description=(frame.text + "\n\n" + details)[:4000]
            )
            embed.set_footer(
                text=f"Survivors: {len(engine.alive)} • Step {engine.steps} • {frame.outcome or 'In progress'}"
            )
            await ctx.send(embed=embed)
            if engine.outcome is None:
                await asyncio.sleep(config["step_delay"])
        if engine.outcome == "victory":
            survivors = [u for u in users if str(u.id) in engine.alive]
            await self._award_definition_rewards(
                ctx,
                config.get("rewards", {}),
                participant_users=users,
                bonus_users=survivors,
                crate_users=survivors,
                participant_label="participant",
                bonus_label="survivor",
            )
