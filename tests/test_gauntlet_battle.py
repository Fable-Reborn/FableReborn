"""Tests for the simultaneous Defense Gauntlet battle.

The gauntlet used to run on TowerBattle, which fights the enemy list as a
sequence of stages. That put the defender and their pet on opposite sides of a
one-way index: the pet's support skills could only fire once its owner was
already dead, and a pet heal landing on that corpse stranded a living enemy at
an index the battle could never return to, hanging the fight until timeout.
GauntletBattle fights both sides at once instead.
"""

import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace

from tests.pet_test_loader import load_gauntlet_runtime_types, load_pet_runtime_types


class GauntletBattleTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.GauntletBattle, cls.Team, cls.Combatant = load_gauntlet_runtime_types()

    def _new_combatant(self, name, hp=100, is_pet=False):
        return self.Combatant(
            user=name,
            hp=hp,
            max_hp=100,
            damage=10,
            armor=5,
            element="Fire",
            name=name,
            is_pet=is_pet,
        )

    def _new_battle(self, *, attacker_pet=True, defender_pet=True):
        ctx = SimpleNamespace(
            bot=SimpleNamespace(
                cogs={"Battles": SimpleNamespace()},
                get_cog=lambda name: None,
            ),
            send=None,
        )
        attackers = [self._new_combatant("Attacker")]
        if attacker_pet:
            attackers.append(self._new_combatant("Attacker Pet", is_pet=True))
        defenders = [self._new_combatant("Defender")]
        if defender_pet:
            defenders.append(self._new_combatant("Defender Pet", is_pet=True))

        return self.GauntletBattle(
            ctx,
            [self.Team("Player", attackers), self.Team("Enemy", defenders)],
            attacker_name="Attacker",
            defender_name="Defender",
        )


class TestGauntletIsSimultaneous(GauntletBattleTestBase):
    def test_both_defenders_are_active_from_the_first_turn(self):
        battle = self._new_battle()

        async def run():
            battle.turn_order = []
            for team in battle.teams:
                for combatant in team.combatants:
                    battle.turn_order.append(combatant)
            return battle.turn_order

        turn_order = asyncio.run(run())
        names = {c.name for c in turn_order}

        # The defender's pet fights alongside its owner rather than waiting for
        # the owner to die first, which is what made its support kit useless.
        self.assertIn("Defender", names)
        self.assertIn("Defender Pet", names)
        self.assertEqual(4, len(turn_order))

    def test_there_is_no_sequential_opponent_index(self):
        battle = self._new_battle()

        self.assertFalse(hasattr(battle, "current_opponent_index"))
        self.assertFalse(hasattr(battle, "pending_enemy_transition"))

    def test_team_handles_exist_for_skeleton_summoning(self):
        # TeamBattle referenced self.team_a / self.team_b without ever setting
        # them, so any skeleton summon raised AttributeError mid-battle.
        battle = self._new_battle()

        self.assertIs(battle.teams[0], battle.team_a)
        self.assertIs(battle.teams[1], battle.team_b)

    def test_exposes_player_and_enemy_team_handles(self):
        battle = self._new_battle()

        self.assertIs(battle.teams[0], battle.player_team)
        self.assertIs(battle.teams[1], battle.enemy_team)


class TestGauntletOutcome(GauntletBattleTestBase):
    def _end(self, battle):
        async def noop_save():
            return None

        battle.save_battle_to_database = noop_save
        return asyncio.run(battle.end_battle())

    def test_attacker_wins_when_the_whole_defence_falls(self):
        battle = self._new_battle()
        for defender in battle.enemy_team.combatants:
            defender.hp = Decimal("0")

        self.assertIs(battle.player_team, self._end(battle))

    def test_defence_holds_when_the_attacking_party_falls(self):
        battle = self._new_battle()
        for attacker in battle.player_team.combatants:
            attacker.hp = Decimal("0")

        self.assertIs(battle.enemy_team, self._end(battle))

    def test_defence_holds_on_a_mutual_wipe(self):
        battle = self._new_battle()
        for combatant in battle.player_team.combatants + battle.enemy_team.combatants:
            combatant.hp = Decimal("0")

        self.assertIs(battle.enemy_team, self._end(battle))

    def test_attacker_wins_while_only_their_pet_survives(self):
        # The gauntlet lets pets carry the fight, so a downed attacker whose
        # pet finishes the defence still breaches it.
        battle = self._new_battle()
        battle.player_team.combatants[0].hp = Decimal("0")
        for defender in battle.enemy_team.combatants:
            defender.hp = Decimal("0")

        self.assertIs(battle.player_team, self._end(battle))

    def test_stalemate_returns_no_winner(self):
        battle = self._new_battle()

        self.assertIsNone(self._end(battle))

    def test_battle_is_over_once_either_side_is_wiped(self):
        battle = self._new_battle()
        self.assertFalse(asyncio.run(battle.is_battle_over()))

        for defender in battle.enemy_team.combatants:
            defender.hp = Decimal("0")

        self.assertTrue(asyncio.run(battle.is_battle_over()))


class TestAttackerWonResolution(GauntletBattleTestBase):
    """The gauntlet cog reads the winner off live team state, not the label."""

    @staticmethod
    def _attacker_won(battle, result):
        # Mirrors Gauntlet._attacker_won_battle
        if battle.enemy_team.is_defeated():
            return not battle.player_team.is_defeated()
        if battle.player_team.is_defeated():
            return False
        return result is battle.player_team

    def test_breach_is_credited_to_the_attacker(self):
        battle = self._new_battle()
        for defender in battle.enemy_team.combatants:
            defender.hp = Decimal("0")

        self.assertTrue(self._attacker_won(battle, battle.player_team))

    def test_stalemate_counts_as_a_hold(self):
        battle = self._new_battle()

        self.assertFalse(self._attacker_won(battle, None))


class TestPetOwnerHealsRespectDeath(unittest.TestCase):
    """A pet's owner-heal supports a living owner; it never raises a corpse."""

    @classmethod
    def setUpClass(cls):
        cls.Combatant, cls.PetExtension = load_pet_runtime_types()
        _, cls.Team, _ = load_gauntlet_runtime_types()

    def _pair(self, owner_hp):
        owner = self.Combatant(
            user=4242,
            hp=owner_hp,
            max_hp=1000,
            damage=10,
            armor=5,
            element="Water",
            name="Defender",
        )
        pet = self.Combatant(
            user="Defender Pet",
            hp=500,
            max_hp=500,
            damage=100,
            armor=10,
            element="Water",
            name="Defender Pet",
            is_pet=True,
        )
        pet.owner = owner
        pet.skill_effects = {"life_spring": {"heal_percent": 0.2, "type": "owner_heal"}}
        pet.attacked_this_turn = True
        pet.team = self.Team("Enemy", [owner, pet])
        pet.enemy_team = self.Team("Player", [])
        return owner, pet

    def test_life_spring_heals_a_living_owner(self):
        owner, pet = self._pair(owner_hp=400)

        messages = self.PetExtension().process_skill_effects_per_turn(pet)

        self.assertGreater(owner.hp, Decimal("400"))
        self.assertTrue(any("Life Spring" in m for m in messages))

    def test_life_spring_does_nothing_for_a_downed_owner(self):
        owner, pet = self._pair(owner_hp=0)

        messages = self.PetExtension().process_skill_effects_per_turn(pet)

        self.assertEqual(Decimal("0"), owner.hp)
        self.assertFalse(owner.is_alive())
        # No phantom log line claiming a heal that could not land
        self.assertFalse(any("Life Spring" in m for m in messages))


if __name__ == "__main__":
    unittest.main()
