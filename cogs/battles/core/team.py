# battles/core/team.py

class Team:
    """Represents a group of combatants fighting together"""
    
    def __init__(self, name, combatants=None):
        self.name = name
        self.combatants = combatants or []
    
    def add_combatant(self, combatant):
        """Add a combatant to the team"""
        self.combatants.append(combatant)
        return self
    
    def is_defeated(self):
        """Check if all team members are defeated"""
        return all(not c.is_alive() for c in self.combatants)
    
    def get_alive_combatants(self):
        """Get all living combatants on the team"""
        return [c for c in self.combatants if c.is_alive()]
    
    def __str__(self):
        """String representation of the team"""
        return f"Team {self.name}: {', '.join(str(c) for c in self.combatants)}"
        
    def get_members_mentions(self):
        """Get mentions of all team members who are discord users"""
        mentions = []
        for combatant in self.combatants:
            if hasattr(combatant.user, "mention"):
                mentions.append(combatant.user.mention)
            else:
                mentions.append(combatant.name)
        return mentions