# battles/utils.py

def create_hp_bar(current_hp, max_hp, length=20):
    """Create a visual HP bar"""
    ratio = current_hp / max_hp if max_hp > 0 else 0
    ratio = max(0, min(1, ratio))  # Ensure ratio is between 0 and 1
    filled_length = int(length * ratio)
    bar = '█' * filled_length + '░' * (length - filled_length)
    return bar

def format_hp(hp, decimal_places=1):
    """Format HP value with specified decimal places"""
    return f"{hp:.{decimal_places}f}"

def is_valid_battle_type(battle_type):
    """Check if a battle type is valid"""
    valid_types = ["pvp", "pve", "raid", "tower", "team"]
    return battle_type.lower() in valid_types

def parse_battle_options(options_string):
    """Parse options string into a dictionary"""
    options = {}
    if not options_string:
        return options
    
    parts = options_string.split()
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            
            # Convert boolean strings
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            # Convert numeric strings
            elif value.isdigit():
                value = int(value)
            elif value.replace(".", "", 1).isdigit():
                value = float(value)
                
            options[key] = value
    
    return options