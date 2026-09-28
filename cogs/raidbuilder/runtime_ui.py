"""Participant role selection and private, role-aware battle choices."""

import discord
from discord.ui import View, Select, Button


class RoleAssignmentView(View):
    def __init__(self, roles, eligible, timeout):
        super().__init__(timeout=timeout)
        self.roles = {r["id"]: r for r in roles}
        self.eligible = set(map(str, eligible))
        self.choices = {}
        self.selector = Select(placeholder="Choose your role", options=[
            discord.SelectOption(label=r["label"], value=r["id"],
                description=f"Team: {r['team']} • Slots: {r.get('slots') or 'unlimited'}") for r in roles])
        self.selector.callback = self.choose
        self.add_item(self.selector)

    async def choose(self, interaction):
        user = str(interaction.user.id)
        if self.is_finished() or user not in self.eligible:
            return await interaction.response.send_message("Role selection is closed or you are not a participant.", ephemeral=True)
        key = self.selector.values[0]
        role = self.roles[key]
        occupied = sum(value == key for who, value in self.choices.items() if who != user)
        if role.get("slots", 0) and occupied >= role["slots"]:
            return await interaction.response.send_message("That role is full. Choose another role.", ephemeral=True)
        self.choices[user] = key
        await interaction.response.send_message(f"You chose {role['label']}.", ephemeral=True)
        if len(self.choices) == len(self.eligible):
            self.stop()


class PlayerActionView(View):
    def __init__(self, parent, user_id):
        super().__init__(timeout=parent.timeout)
        self.parent = parent
        self.user_id = str(user_id)
        engine = parent.engine
        options = engine.prompt(self.user_id)
        self.action = options[0][0]
        self.target = None
        action_select = Select(placeholder="Choose your action", options=[discord.SelectOption(label=label, value=key) for key, label in options])
        action_select.callback = self.select_action
        self.add_item(action_select)
        self.action_select = action_select
        targets = engine.enemy_options()
        if targets:
            self.target = targets[0][0]
            self.target_select = Select(placeholder="Enemy target (for targeted actions)", options=[discord.SelectOption(label=label, value=key) for key, label in targets])
            self.target_select.callback = self.select_target
            self.add_item(self.target_select)
        button = Button(label="Confirm action", style=discord.ButtonStyle.success)
        button.callback = self.confirm
        self.add_item(button)

    async def interaction_check(self, interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This action picker belongs to another player.", ephemeral=True)
            return False
        return True

    async def select_action(self, interaction):
        self.action = self.action_select.values[0]
        await interaction.response.defer()

    async def select_target(self, interaction):
        self.target = self.target_select.values[0]
        await interaction.response.defer()

    async def confirm(self, interaction):
        if str(interaction.user.id) != self.user_id or self.parent.is_finished() or self.user_id not in self.parent.engine.alive:
            return await interaction.response.send_message("This decision window has closed.", ephemeral=True)
        allowed = {key for key, _ in self.parent.engine.prompt(self.user_id)}
        if self.action not in allowed:
            return await interaction.response.send_message("That action is not available to your role.", ephemeral=True)
        self.parent.decisions[self.user_id] = {"action": self.action, "target": self.target}
        await interaction.response.edit_message(content="Action confirmed.", view=None)
        self.stop()
        if len(self.parent.decisions) == len(self.parent.engine.alive):
            self.parent.stop()


class BattleDecisionView(View):
    def __init__(self, engine, timeout):
        super().__init__(timeout=timeout)
        self.engine = engine
        self.decisions = {}
        button = Button(label="Choose action / target", style=discord.ButtonStyle.primary)
        button.callback = self.choose
        self.add_item(button)

    async def choose(self, interaction):
        user = str(interaction.user.id)
        if self.is_finished() or user not in self.engine.alive:
            return await interaction.response.send_message("Only surviving participants may act during this decision window.", ephemeral=True)
        player = self.engine.players[user]
        role = self.engine.roles[player.role]["label"]
        await interaction.response.send_message(f"{role} • HP {player.hp}/{player.max_hp} • Shield {player.shield}",
            view=PlayerActionView(self, user), ephemeral=True)
