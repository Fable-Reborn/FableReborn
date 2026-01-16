import asyncio
import os
import random
import discord
from discord.ext import commands
from discord.ui import View, Button
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from io import BytesIO
import traceback
from fable.utils.i18n import _, locale_doc, use_current_gettext
from datetime import datetime

from fable.systems.shard_communication import user_on_cooldown as user_cooldown
from fable.utils.checks import is_gm, has_char  # Import is_gm from utils.checks
from fable.utils.i18n import locale_doc

# Directions
N, S, W, E = ("n", "s", "w", "e")

def get_hp_display(current_hp, max_hp=100):
    """Returns the HP display as 'current_hp/max_hp'."""
    return f"{current_hp}/{max_hp}"

class Cell:
    def __init__(self, x, y, walls, cog):
        self.x = x
        self.y = y
        self.walls = set(walls)
        self.cog = cog  # For access to probabilities, etc.
        self.trap = random.randint(1, 10) == 1  # 10% chance to be a trap
        if not self.trap:
            self.enemy = self.generate_enemy()  # Might be None
        else:
            self.enemy = None
        self.treasure = False
        self.ladder = False  # Marks a ladder cell for an early exit

    def is_full(self):
        return len(self.walls) == 4

    def _wall_to(self, other):
        assert abs(self.x - other.x) + abs(self.y - other.y) == 1, f"{self}, {other}"
        if other.y < self.y:
            return N
        elif other.y > self.y:
            return S
        elif other.x < self.x:
            return W
        elif other.x > self.x:
            return E
        else:
            raise ValueError("Invalid cell positions for wall removal.")

    def connect(self, other):
        other.walls.remove(other._wall_to(self))
        self.walls.remove(self._wall_to(other))

    def generate_enemy(self):
        if random.random() < self.cog.get_enemy_chance():
            enemy_type = random.choice(['Goblin', 'Skeleton', 'Orc'])
            return Enemy(enemy_type)
        return None

class Enemy:
    def __init__(self, enemy_type):
        self.type = enemy_type
        if enemy_type == 'Goblin':
            self.hp = 30
            self.max_hp = 30
            self.attack = 7
            self.defense = 5
        elif enemy_type == 'Skeleton':
            self.hp = 50
            self.max_hp = 50
            self.attack = 10
            self.defense = 6
        elif enemy_type == 'Orc':
            self.hp = 70
            self.max_hp = 70
            self.attack = 11
            self.defense = 3

    def is_defeated(self):
        return self.hp <= 0

class Maze:
    def __init__(self, width=20, height=10, cog=None):
        self.width = width
        self.height = height
        self.cog = cog
        self.cells = [Cell(x, y, [N, S, E, W], cog) for y in range(height) for x in range(width)]

    def __getitem__(self, index):
        x, y = index
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.cells[x + y * self.width]
        return None

    def neighbors(self, cell):
        x, y = cell.x, cell.y
        potential = [(x, y-1), (x, y+1), (x-1, y), (x+1, y)]
        return [self[new_x, new_y] for new_x, new_y in potential if self[new_x, new_y]]

    def randomize(self):
        cell_stack = []
        cell = random.choice(self.cells)
        n_visited = 1
        total = len(self.cells)
        while n_visited < total:
            neighbors = [c for c in self.neighbors(cell) if c.is_full()]
            if neighbors:
                neighbor = random.choice(neighbors)
                cell.connect(neighbor)
                cell_stack.append(cell)
                cell = neighbor
                n_visited += 1
            elif cell_stack:
                cell = cell_stack.pop()

    @staticmethod
    def generate(width=20, height=10, treasures=5, cog=None):
        maze = Maze(width, height, cog)
        maze.randomize()
        # Mark treasures.
        treasure_cells = random.sample(maze.cells[1:], treasures)
        for cell in treasure_cells:
            cell.treasure = True
        # Candidate cells exclude start (0,0) and exit (width-1, height-1)
        possible_cells = [cell for cell in maze.cells if not (cell.x == 0 and cell.y == 0)
                          and not (cell.x == maze.width - 1 and cell.y == maze.height - 1)]
        random.shuffle(possible_cells)
        if possible_cells:
            possible_cells[0].ladder = True
        # Ensure exit cell never has a ladder.
        exit_cell = maze[maze.width - 1, maze.height - 1]
        exit_cell.ladder = False
        return maze

class AdventureState:
    def __init__(self, user_id, maze, attack, defense, total_treasures):
        self.user_id = user_id
        self.maze = maze
        self.attack = attack
        self.defense = defense
        self.position = (0, 0)
        self.hp = 100
        self.max_hp = 100
        self.treasures_found = 0
        self.total_treasures = total_treasures
        self.special_treasure_found = False
        self.is_active = True
        self.in_combat = False
        self.message = None  # The maze embed message
        self.turn = 1
        self.uploaded_files = []
        self.gold = 0
        self.inventory = []
        self.current_enemy = None
        self.defense_buff = 0  # Temporary defense buff for one turn
        self.ladder_prompt_shown = False  # Prevent repeated prompts

    def get_turn_filename(self):
        filename = f"maze_{self.user_id}_{self.turn}_{random.randint(1000,99999)}.png"
        self.uploaded_files.append(filename)
        self.turn += 1
        if self.turn > 999:
            self.turn = 1
        return filename

# NEW: Ladder confirmation view (for non-exit cells)
class LadderConfirmView(discord.ui.View):
    def __init__(self, cog, state):
        super().__init__(timeout=30)
        self.cog = cog
        self.state = state
        self.message = None
        self.original_message = None
        self.original_view = None

    @discord.ui.button(label="Exit Now", style=discord.ButtonStyle.success, custom_id="ladder_exit_yes")
    async def ladder_exit_yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await self.cog.handle_ladder_exit(interaction, self.state)
            self.stop()
        except Exception as e:
            await self.cog.report_error(e, interaction)

    @discord.ui.button(label="Keep Going", style=discord.ButtonStyle.secondary, custom_id="ladder_exit_no")
    async def ladder_exit_no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            for child in self.original_view.children:
                child.disabled = False
            embed, file = await self.cog.create_maze_embed(self.state)
            await self.original_message.edit(
                content="You have decided to continue your adventure.",
                embed=embed,
                view=self.original_view,
                attachments=[file]
            )
            await interaction.response.edit_message(content="Continuing your adventure!", view=None)
            self.state.ladder_prompt_shown = False
            self.stop()
        except Exception as e:
            await self.cog.report_error(e, interaction)

    async def on_timeout(self):
        try:
            for child in self.original_view.children:
                child.disabled = False
            embed, file = await self.cog.create_maze_embed(self.state)
            await self.original_message.edit(
                content="(Ladder decision timed out. Continuing your adventure.)",
                embed=embed,
                view=self.original_view,
                attachments=[file]
            )
            self.state.ladder_prompt_shown = False
            if self.message:
                await self.message.delete()
        except Exception as e:
            print(f"Error in ladder confirm timeout: {e}")

# NEW: Exit confirmation view at the exit cell.
class ConfirmExitView(discord.ui.View):
    def __init__(self, cog, state):
        super().__init__(timeout=30)
        self.cog = cog
        self.state = state
        self.message = None
        self.original_message = None
        self.original_view = None

    @discord.ui.button(label="Exit Now", style=discord.ButtonStyle.success, custom_id="exit_yes")
    async def exit_yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await self.cog.handle_exit(interaction, self.state)
            self.stop()
        except Exception as e:
            await self.cog.report_error(e, interaction)

    @discord.ui.button(label="Keep Exploring", style=discord.ButtonStyle.secondary, custom_id="exit_no")
    async def exit_no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            for child in self.original_view.children:
                child.disabled = False
            embed, file = await self.cog.create_maze_embed(self.state)
            await self.original_message.edit(
                content="You chose to keep exploring the maze.",
                embed=embed,
                view=self.original_view,
                attachments=[file]
            )
            await interaction.response.edit_message(content="Continuing your adventure!", view=None)
            self.stop()
        except Exception as e:
            await self.cog.report_error(e, interaction)

    async def on_timeout(self):
        try:
            for child in self.original_view.children:
                child.disabled = False
            embed, file = await self.cog.create_maze_embed(self.state)
            await self.original_message.edit(
                content="(Exit decision timed out. Continuing your adventure.)",
                embed=embed,
                view=self.original_view,
                attachments=[file]
            )
            if self.message:
                await self.message.delete()
        except Exception as e:
            print(f"Error in exit confirm timeout: {e}")

class ConfirmQuitView(discord.ui.View):
    def __init__(self, cog, state):
        super().__init__(timeout=30)
        self.cog = cog
        self.state = state
        self.message = None
        self.original_message = None
        self.original_view = None

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger, custom_id="confirm_quit_yes")
    async def confirm_quit_yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.cog.handle_quit(interaction, self.state)
            self.stop()
        except Exception as e:
            await self.cog.report_error(e, interaction)

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary, custom_id="confirm_quit_no")
    async def confirm_quit_no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            for child in self.original_view.children:
                child.disabled = False
            embed, file = await self.cog.create_maze_embed(self.state)
            await self.original_message.edit(
                content=None,
                embed=embed,
                view=self.original_view,
                attachments=[file]
            )
            await interaction.response.edit_message(content="Quit cancelled - you can continue your adventure!", view=None)
            self.stop()
        except Exception as e:
            await self.cog.report_error(e, interaction)

    async def on_timeout(self):
        try:
            for child in self.original_view.children:
                child.disabled = False
            embed, file = await self.cog.create_maze_embed(self.state)
            await self.original_message.edit(
                content=None,
                embed=embed,
                view=self.original_view,
                attachments=[file]
            )
            if self.message:
                await self.message.delete()
        except Exception as e:
            print(f"Error in timeout handler: {e}")

class AdventureView(discord.ui.View):
    def __init__(self, cog, state):
        super().__init__(timeout=None)
        self.cog = cog
        self.state = state

        # Enable or disable buttons based on combat state.
        if state.in_combat:
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.custom_id.startswith("move_"):
                    child.disabled = True
                elif isinstance(child, discord.ui.Button) and child.custom_id.startswith("action_"):
                    child.disabled = False
        else:
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.custom_id.startswith("move_"):
                    child.disabled = False
                elif isinstance(child, discord.ui.Button) and child.custom_id.startswith("action_"):
                    child.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.state.user_id:
            await interaction.response.send_message("This adventure isn't for you!", ephemeral=True)
            return False
        return True

    # Movement Buttons – North, East, South, West.
    @discord.ui.button(label="North", style=discord.ButtonStyle.primary, emoji="⬆️", custom_id="move_north")
    async def move_north_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.safe_handle_move(interaction, self.state, "north")

    @discord.ui.button(label="East", style=discord.ButtonStyle.primary, emoji="➡️", custom_id="move_east")
    async def move_east_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.safe_handle_move(interaction, self.state, "east")

    @discord.ui.button(label="South", style=discord.ButtonStyle.primary, emoji="⬇️", custom_id="move_south")
    async def move_south_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.safe_handle_move(interaction, self.state, "south")

    @discord.ui.button(label="West", style=discord.ButtonStyle.primary, emoji="⬅️", custom_id="move_west")
    async def move_west_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.safe_handle_move(interaction, self.state, "west")

    # Action Buttons.
    @discord.ui.button(label="⚔️ Attack", style=discord.ButtonStyle.secondary, custom_id="action_attack")
    async def action_attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.safe_handle_action(interaction, self.state, "attack")

    @discord.ui.button(label="🛡️ Defend", style=discord.ButtonStyle.secondary, custom_id="action_defend")
    async def action_defend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.safe_handle_action(interaction, self.state, "defend")

    @discord.ui.button(label="❤️ Heal", style=discord.ButtonStyle.secondary, custom_id="action_heal")
    async def action_heal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.safe_handle_action(interaction, self.state, "heal")

    @discord.ui.button(label="🏳️ Quit", style=discord.ButtonStyle.danger, custom_id="quit_adventure")
    async def quit_adventure_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            for child in self.children:
                child.disabled = True
            confirm_view = ConfirmQuitView(self.cog, self.state)
            embed, file = await self.cog.create_maze_embed(self.state)
            await interaction.message.edit(
                content="⚠️ Are you sure you want to quit the adventure?",
                embed=embed,
                view=self,
                attachments=[file]
            )
            confirm_message = await interaction.followup.send(
                "Click Yes to confirm quitting, or No to continue playing.",
                view=confirm_view,
                ephemeral=True
            )
            confirm_view.message = confirm_message
            confirm_view.original_message = interaction.message
            confirm_view.original_view = self
        except Exception as e:
            await self.cog.report_error(e, interaction)

class TestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_adventures = {}  # user_id: AdventureState
        self.error_recipient_id = 0  # Replace with your error recipient's ID

        # Create a directory for maze images if it doesn't exist.
        self.image_dir = "maze_images"
        os.makedirs(self.image_dir, exist_ok=True)

        # Load assets and font.
        self.assets = self.load_assets()
        self.font = self.load_font()

        # Manual night time toggle: None = system time, True = night, False = day.
        self.manual_night_time = None

    def load_assets(self):
        assets = {}
        asset_paths = {
            "floor": "assets/images/ui/floor.png",
            "player": "assets/images/ui/player.png",
            "treasure": "assets/images/ui/treasure.png",
            "trap": "assets/images/ui/trap.png",
            "exit": "assets/images/ui/exit.png",
            "enemy": "assets/images/enemies/enemy.png",
            "enemy_goblin": "assets/images/enemies/enemy_goblin.png",
            "enemy_skeleton": "assets/images/enemies/enemy_skeleton.png",
            "enemy_orc": "assets/images/enemies/enemy_orc.png",
            "battle_image": "assets/images/battle/battle_image.png",
        }
        for name, path in asset_paths.items():
            if os.path.exists(path):
                assets[name] = Image.open(path).convert("RGBA")
            else:
                print(f"Asset '{name}' not found at '{path}'.")
        return assets

    def load_font(self):
        font_path = os.path.join("assets", "fonts", "pixel_font.ttf")
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size=24)
        else:
            return ImageFont.load_default()

    @has_char()
    @user_cooldown(7200)
    @commands.command(aliases=["aa"], brief="Embark on an active adventure.")
    @locale_doc
    async def activeadventure(self, ctx):
        _(
            """Active adventures will put you into a randomly generated maze.
You begin at the top left and must reach the exit at the bottom right.
Use the arrow buttons to navigate.
• Each cell may have traps, enemies, or treasure.
• There’s a 10% chance for a trap (causing 1/10 to 1/8 of your HP in damage) and, if not, a 10% chance for an enemy.
• Each maze has 5 treasure chests.
In battle you can attack (⚔️), defend (🛡️) or heal (❤️).
Defending grants a temporary buff and a chance to counterattack!
A hidden ladder lets you exit early (with partial rewards).
When you reach the exit, you will be asked to confirm if you want to exit.
(This command has a 30-minute cooldown)"""
        )



        if not self.is_night_time():
            tres = 5
            maze = Maze.generate(width=12, height=12, treasures=tres, cog=self)
        else:
            tres = random.randint(5, 9)
            maze = Maze.generate(width=15, height=15, treasures=tres, cog=self)
        attack, defense = await self.get_damage_armor_for(ctx.author)
        state = AdventureState(ctx.author.id, maze, attack, defense, total_treasures=tres)
        self.active_adventures[ctx.author.id] = state

        try:
            embed, file = await self.create_maze_embed(state)
            view = AdventureView(self, state)
            message = await ctx.send(
                "🌀 You have entered the labyrinth! Use the buttons below to navigate.",
                embed=embed,
                view=view,
                file=file
            )
            state.message = message
            view.message = message
        except Exception as e:
            await self.report_error(e, ctx)

    @is_gm()
    @commands.command(aliases=["aaanight"], brief="Toggle night time manually.")
    async def toggle_night_time(self, ctx, mode: str = None):
        channel_id = 1311869497497354281  # Replace with your channel ID
        if channel_id != ctx.channel.id:
            return
        if mode is None:
            if self.manual_night_time is None:
                self.manual_night_time = True
                await ctx.send("🌙 Night time is now manually set to ON.")
            else:
                self.manual_night_time = None
                await ctx.send("🌞 Night time is now set to AUTO (system time).")
        else:
            mode = mode.lower()
            if mode == "on":
                self.manual_night_time = True
                await ctx.send("🌙 Night time is now manually set to ON.")
            elif mode == "off":
                self.manual_night_time = False
                await ctx.send("🌞 Night time is now manually set to OFF.")
            elif mode == "auto":
                self.manual_night_time = None
                await ctx.send("🌞 Night time is now set to AUTO (system time).")
            else:
                await ctx.send("Invalid mode. Usage: aaanight [on|off|auto]")

    def is_night_time(self):
        if self.manual_night_time is not None:
            return self.manual_night_time
        current_hour = datetime.now().hour
        return current_hour >= 18 or current_hour < 6

    def get_treasure_gold_range(self):
        if self.is_night_time():
            return (15000, 25000)
        else:
            return (10000, 15000)

    def get_exit_gold_range(self):
        if self.is_night_time():
            return (50000, 70000)
        else:
            return (30000, 50000)

    def get_enemy_chance(self):
        if self.is_night_time():
            return 0.10
        else:
            return 0.05

    async def create_maze_embed(self, state: AdventureState):
        if state.in_combat:
            image_buffer = self.generate_battle_image(state)
            embed = discord.Embed(
                title="⚔️ Battle! ⚔️",
                description=f"You are battling a {state.current_enemy.type}!",
                color=discord.Color.red()
            )
            embed.add_field(
                name="❤️ Your HP",
                value=f"{get_hp_display(state.hp, state.max_hp)}",
                inline=True
            )
            embed.add_field(
                name=f"👾 {state.current_enemy.type}'s HP",
                value=f"{get_hp_display(state.current_enemy.hp, state.current_enemy.max_hp)}",
                inline=True
            )
        else:
            maze = state.maze
            image_buffer = self.generate_maze_image(maze, state.position, state)
            embed = discord.Embed(
                title="🌀 Maze Adventure 🌀",
                description="Navigate through the maze to find the exit!",
                color=discord.Color.dark_gray()
            )
            embed.add_field(
                name="❤️ HP",
                value=f"{get_hp_display(state.hp, state.max_hp)}",
                inline=True
            )
            embed.add_field(
                name="💰 Gold",
                value=f"{state.gold}",
                inline=False
            )
            embed.add_field(
                name="💎 Treasures",
                value=f"{state.treasures_found}/{state.total_treasures}",
                inline=False
            )
        embed.set_footer(text="Use the buttons below to interact.")
        filename = state.get_turn_filename()
        filepath = os.path.join(self.image_dir, filename)
        with open(filepath, 'wb') as f:
            image_buffer.seek(0)
            f.write(image_buffer.getvalue())
        file = discord.File(filepath, filename=filename)
        embed.set_image(url=f"attachment://{filename}")
        return embed, file

    def generate_battle_image(self, state: AdventureState):
        battle_bg = self.assets.get('battle_image')
        if not battle_bg:
            battle_bg = Image.new('RGBA', (800, 600), (0, 0, 0, 255))
        else:
            battle_bg = battle_bg.copy()
        img = battle_bg.copy()
        draw = ImageDraw.Draw(img)
        bar_width = 300
        bar_height = 20
        player_bar_x = 50
        player_bar_y = 50
        enemy_bar_x = img.width - bar_width - 50
        enemy_bar_y = 50
        self.draw_pixel_hp_bar(
            draw, player_bar_x, player_bar_y, bar_width, bar_height,
            state.hp, state.max_hp, fill_color=(0, 255, 0)
        )
        self.draw_pixel_hp_bar(
            draw, enemy_bar_x, enemy_bar_y, bar_width, bar_height,
            state.current_enemy.hp, state.current_enemy.max_hp, fill_color=(255, 0, 0)
        )
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    def draw_pixel_hp_bar(self, draw, x, y, width, height, current_hp, max_hp, fill_color):
        border_color = (255, 255, 255)
        draw.rectangle((x, y, x + width, y + height), outline=border_color, width=2)
        draw.rectangle((x + 1, y + 1, x + width - 1, y + height - 1), fill=(50, 50, 50))
        hp_ratio = current_hp / max_hp
        hp_fill_width = int((width - 2) * hp_ratio)
        for i in range(hp_fill_width):
            line_color = (
                int(fill_color[0] * (1 - i / hp_fill_width)),
                int(fill_color[1] * (i / hp_fill_width)),
                fill_color[2]
            )
            draw.line([(x + 1 + i, y + 1), (x + 1 + i, y + height - 2)], fill=line_color)
        hp_text = f"{current_hp}/{max_hp}"
        font = self.font
        bbox = draw.textbbox((0, 0), hp_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = x + (width - text_width) / 2
        text_y = y + (height - text_height) / 2 - 1
        draw.text((text_x, text_y), hp_text, fill=(255, 255, 255), font=font)

    def generate_maze_image(self, maze: Maze, player_pos, state: AdventureState):
        cell_size = 40
        wall_thickness = 4
        width_px = maze.width * cell_size
        height_px = maze.height * cell_size
        img = Image.new("RGBA", (width_px, height_px), (20, 20, 20, 255))
        draw = ImageDraw.Draw(img)
        px, py = player_pos
        floor_tile = self.assets.get('floor')
        for cell in maze.cells:
            x = cell.x
            y = cell.y
            cell_x = x * cell_size
            cell_y = y * cell_size
            if floor_tile:
                img.paste(floor_tile, (cell_x, cell_y))
            else:
                draw.rectangle([(cell_x, cell_y), (cell_x + cell_size, cell_y + cell_size)], fill=(50, 50, 50))
        wall_color = (200, 200, 200)
        for cell in maze.cells:
            x = cell.x
            y = cell.y
            cell_x = x * cell_size
            cell_y = y * cell_size
            if N in cell.walls:
                draw.line([(cell_x, cell_y), (cell_x + cell_size, cell_y)], fill=wall_color, width=wall_thickness)
            if S in cell.walls:
                draw.line([(cell_x, cell_y + cell_size), (cell_x + cell_size, cell_y + cell_size)], fill=wall_color, width=wall_thickness)
            if W in cell.walls:
                draw.line([(cell_x, cell_y), (cell_x, cell_y + cell_size)], fill=wall_color, width=wall_thickness)
            if E in cell.walls:
                draw.line([(cell_x + cell_size, cell_y), (cell_x + cell_size, cell_y + cell_size)], fill=wall_color, width=wall_thickness)
        exit_tile = self.assets.get('exit')
        if exit_tile:
            ex, ey = (maze.width - 1) * cell_size, (maze.height - 1) * cell_size
            img.paste(exit_tile, (ex, ey), exit_tile)
        for cell in maze.cells:
            x = cell.x
            y = cell.y
            cell_x = x * cell_size
            cell_y = y * cell_size
            if cell.trap and not state.in_combat:
                trap_tile = self.assets.get('trap')
                if trap_tile:
                    trap_tile_resized = trap_tile.resize((20, 20))
                    img.paste(trap_tile_resized, (cell_x + 10, cell_y + 10), trap_tile_resized)
            if cell.treasure:
                treasure_tile = self.assets.get('treasure')
                if treasure_tile:
                    img.paste(treasure_tile, (cell_x, cell_y), treasure_tile)
            if cell.enemy:
                enemy_tile = self.assets.get(f'enemy_{cell.enemy.type.lower()}')
                if enemy_tile:
                    img.paste(enemy_tile, (cell_x, cell_y), enemy_tile)
        if self.is_night_time():
            gradient_radius = cell_size * 3
            mask = Image.new('L', (width_px, height_px), color=0)
            draw_mask = ImageDraw.Draw(mask)
            center_x = px * cell_size + cell_size // 2
            center_y = py * cell_size + cell_size // 2
            max_radius = int(gradient_radius)
            for r in range(max_radius, 0, -1):
                alpha = int(255 * ((max_radius - r) / max_radius))
                bbox = (center_x - r, center_y - r, center_x + r, center_y + r)
                draw_mask.ellipse(bbox, fill=alpha)
            darkness = Image.new('RGBA', (width_px, height_px), (0, 0, 0, 255))
            img = Image.composite(img, darkness, mask)
            glow = Image.new('RGBA', (width_px, height_px), (255, 140, 0, 0))
            glow_mask = mask.filter(ImageFilter.GaussianBlur(radius=10))
            glow.putalpha(glow_mask)
            img = Image.alpha_composite(img, glow)
        player_tile = self.assets.get('player')
        if player_tile:
            img.paste(player_tile, (px * cell_size, py * cell_size), player_tile)
        else:
            draw.ellipse(
                [(px * cell_size + 5, py * cell_size + 5), (px * cell_size + cell_size - 5, py * cell_size + cell_size - 5)],
                fill=(0, 0, 255, 255)
            )
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    async def get_damage_armor_for(self, user):
        # Placeholder: Replace with your own logic.
        attack = 15
        defense = 5
        return attack, defense

    async def safe_handle_move(self, interaction: discord.Interaction, state: AdventureState, direction: str):
        try:
            await self.handle_move(interaction, state, direction)
        except Exception as e:
            await self.report_error(e, interaction)

    async def safe_handle_action(self, interaction: discord.Interaction, state: AdventureState, action: str):
        try:
            await self.handle_action(interaction, state, action)
        except Exception as e:
            await self.report_error(e, interaction)

    async def safe_handle_quit(self, interaction: discord.Interaction, state: AdventureState):
        try:
            await self.handle_quit(interaction, state)
        except Exception as e:
            await self.report_error(e, interaction)

    async def handle_move(self, interaction: discord.Interaction, state: AdventureState, direction: str):
        x, y = state.position
        maze = state.maze
        current_cell = maze[x, y]
        dir_letter = direction[0].lower()
        if dir_letter not in 'nsew':
            return
        if state.in_combat:
            embed, file = await self.create_maze_embed(state)
            view = AdventureView(self, state)
            await interaction.response.edit_message(
                content="⚔️ You are in combat and cannot move!",
                embed=embed,
                view=view,
                attachments=[file]
            )
            return
        if dir_letter in current_cell.walls:
            embed, file = await self.create_maze_embed(state)
            view = AdventureView(self, state)
            await interaction.response.edit_message(
                content="⛔ You can't move in that direction; there's a wall!",
                embed=embed,
                view=view,
                attachments=[file]
            )
            return
        if dir_letter == 'n':
            y -= 1
        elif dir_letter == 's':
            y += 1
        elif dir_letter == 'e':
            x += 1
        elif dir_letter == 'w':
            x -= 1
        state.position = (x, y)
        current_cell = maze[x, y]

        # NEW: Check for ladder prompt (only if not on the exit)
        if current_cell.ladder and not state.ladder_prompt_shown and (x, y) != (maze.width - 1, maze.height - 1):
            state.ladder_prompt_shown = True
            # Disable all buttons on the current (AdventureView) so the player can’t do other actions.
            current_view = interaction.message.view  # This is the view currently attached to the maze message.
            for child in current_view.children:
                child.disabled = True
            # Update the message with the disabled view.
            await interaction.message.edit(view=current_view)

            # Create and remember the ladder confirm view.
            ladder_view = LadderConfirmView(self, state)
            # Pass along a reference to the currently disabled view
            ladder_view.original_view = current_view
            ladder_view.original_message = interaction.message
            await interaction.response.send_message(
                "You have discovered a mysterious ladder that can lead you out early (with partial rewards).\nDo you want to exit now?",
                view=ladder_view,
                ephemeral=True
            )
            return

        if (x, y) == (maze.width - 1, maze.height - 1):
            # Create a new instance of AdventureView and disable all buttons.
            disabled_view = AdventureView(self, state)
            for child in disabled_view.children:
                child.disabled = True
              # Update the original maze message with the disabled view.
            await interaction.message.edit(view=disabled_view)

              # Create the exit confirm view and pass the disabled view along.
            exit_view = ConfirmExitView(self, state)
            exit_view.original_view = disabled_view
            exit_view.original_message = interaction.message
            await interaction.response.send_message(
            "You have reached the exit. Do you want to exit now and claim your reward, or keep exploring?",
            view = exit_view,
            ephemeral = True
            )
            return

        event_messages = []
        if current_cell.trap:
            damage = random.randint(5, 15)
            state.hp -= damage
            event_messages.append(f"💥 You stepped on a trap and lost {damage} HP!")
            current_cell.trap = False
            if state.hp <= 0:
                event_messages.append("😵 You have been defeated by a trap!")
                # End the adventure immediately
                embed, file = await self.create_maze_embed(state)
                view = AdventureView(self, state)
                await interaction.response.edit_message(
                    content="\n".join(event_messages),
                    embed=embed,
                    view=view,
                    attachments=[file]
                )
                await self.end_adventure(
                    interaction,
                    state,
                    success=False,
                    message="😵 You have been defeated by a trap!"
                )
                return
        if current_cell.enemy:
            state.in_combat = True
            state.current_enemy = current_cell.enemy
            event_messages.append(f"🐲 You encountered a {current_cell.enemy.type}! Prepare for battle!")
        elif current_cell.treasure:
            state.treasures_found += 1
            gold_min, gold_max = self.get_treasure_gold_range()
            gold_found = random.randint(gold_min, gold_max)
            state.gold += gold_found
            current_cell.treasure = False
            event_messages.append(f"💰 You found a treasure and gained {gold_found} gold!")
        embed, file = await self.create_maze_embed(state)
        view = AdventureView(self, state)
        event_content = "\n".join(event_messages) if event_messages else "✅ You moved successfully."
        await interaction.response.edit_message(
            content=event_content,
            embed=embed,
            view=view,
            attachments=[file]
        )

    async def handle_action(self, interaction: discord.Interaction, state: AdventureState, action: str):
        enemy = state.current_enemy
        if not enemy:
            state.in_combat = False
            embed, file = await self.create_maze_embed(state)
            view = AdventureView(self, state)
            await interaction.response.edit_message(
                content="❗ There's no enemy here!",
                embed=embed,
                view=view,
                attachments=[file]
            )
            return
        message = ""
        if action == "attack":
            damage = max(0, state.attack - enemy.defense)
            enemy_damage = max(0, enemy.attack - state.defense)
            enemy.hp -= damage
            message += f"⚔️ You attacked the {enemy.type} and dealt {damage} damage!\n"
            if not enemy.is_defeated():
                state.hp -= enemy_damage
                message += f"🐲 The {enemy.type} retaliated and dealt {enemy_damage} damage!\n"
            else:
                message += f"🎉 You defeated the {enemy.type}!\n"
                cell = state.maze[state.position]
                cell.enemy = None
                state.current_enemy = None
                state.in_combat = False
        elif action == "defend":
            state.defense_buff = 5
            enemy_damage = max(0, enemy.attack - (state.defense + state.defense_buff))
            state.hp -= enemy_damage
            message += f"🛡️ You defended and your defense increased by 5 for this turn!\n"
            if random.random() < 0.3:
                counter_damage = max(0, (state.attack // 2) - enemy.defense)
                enemy.hp -= counter_damage
                message += f"🔄 You counterattacked for {counter_damage} damage!\n"
            else:
                message += f"🐲 The {enemy.type} attacked and dealt {enemy_damage} damage!\n"
            state.defense_buff = 0
        elif action == "heal":
            heal_amount = random.randint(3, 10)
            state.hp = min(state.max_hp, state.hp + heal_amount)
            enemy_damage = max(0, enemy.attack - state.defense)
            state.hp -= enemy_damage
            message += f"❤️ You healed for {heal_amount} HP!\n"
            message += f"🐲 The {enemy.type} attacked and dealt {enemy_damage} damage!\n"
        else:
            embed, file = await self.create_maze_embed(state)
            view = AdventureView(self, state)
            await interaction.response.edit_message(
                content="❓ Unknown action.",
                embed=embed,
                view=view,
                attachments=[file]
            )
            return
        if state.hp <= 0:
            message += "😵 You have been defeated by the enemy."
            await self.end_adventure(
                interaction,
                state,
                success=False,
                message=message
            )
            return
        if enemy.is_defeated():
            cell = state.maze[state.position]
            cell.enemy = None
            state.current_enemy = None
            state.in_combat = False
        embed, file = await self.create_maze_embed(state)
        view = AdventureView(self, state)
        await interaction.response.edit_message(
            content=message,
            embed=embed,
            view=view,
            attachments=[file]
        )

    async def handle_quit(self, interaction: discord.Interaction, state: AdventureState):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            await self.end_adventure(
                interaction=interaction,
                state=state,
                success=False,
                message="🏳️ You have quit the adventure."
            )
            try:
                if state.message:
                    await state.message.delete()
            except Exception as e:
                print(f"Error deleting maze message on quit: {e}")
        except Exception as e:
            await self.report_error(e, interaction)

    async def handle_ladder_exit(self, interaction: discord.Interaction, state: AdventureState):
        try:
            message = "🏁 You have chosen to exit early via the ladder. Your current rewards have been secured."
            await self.end_adventure(interaction, state, success=True, message=message)
        except Exception as e:
            await self.report_error(e, interaction)

    async def handle_exit(self, interaction: discord.Interaction, state: AdventureState):
        try:
            # Processing for the exit prompt
            gold_min, gold_max = self.get_exit_gold_range()
            exit_reward = random.randint(gold_min, gold_max)
            state.gold += exit_reward
            await self.end_adventure(interaction, state, success=True, message="🎉 You have reached the exit and claimed your reward!")
        except Exception as e:
            await self.report_error(e, interaction)

    async def end_adventure(self, interaction: discord.Interaction, state: AdventureState, success: bool, message: str):
        try:
            await self.delete_uploaded_images(state)
            if state.user_id in self.active_adventures:
                del self.active_adventures[state.user_id]
            embed = discord.Embed(
                title="🌀 Adventure Ended 🌀",
                description=message,
                color=discord.Color.green() if success else discord.Color.red()
            )
            if success:
                embed.add_field(name="🎁 Reward", value=f"You have been rewarded with {state.gold} gold!", inline=False)
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        state.gold,
                        interaction.user.id,
                    )
            try:
                if state.message and not interaction.response.is_done():
                    await interaction.response.edit_message(
                        embed=embed,
                        view=None,
                        content=None,
                        attachments=[]
                    )
                elif state.message:
                    await interaction.message.edit(
                        embed=embed,
                        view=None,
                        content=None,
                        attachments=[]
                    )
            except (discord.NotFound, discord.HTTPException, AttributeError):
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                    else:
                        await interaction.followup.send(embed=embed, ephemeral=True)
                except Exception as e:
                    print(f"Failed to send end message: {e}")
        except Exception as e:
            print(f"Error in end_adventure: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("⚠️ An error occurred while ending the adventure. Administrators have been notified.", ephemeral=True)
                else:
                    await interaction.followup.send("⚠️ An error occurred while ending the adventure. Administrators have been notified.", ephemeral=True)
            except Exception as e:
                print(f"Failed to send error message: {e}")

    async def delete_uploaded_images(self, state: AdventureState):
        for filename in state.uploaded_files:
            try:
                filepath = os.path.join(self.image_dir, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                print(f"Failed to delete {filename}: {e}")

    async def report_error(self, exception: Exception, context):
        error_recipient = self.bot.get_user(self.error_recipient_id)
        if not error_recipient:
            print(f"Error recipient with ID {self.error_recipient_id} not found.")
            return

    @commands.Cog.listener()
    async def on_ready(self):
        print("TestCog is ready.")

async def setup(bot):
    await bot.add_cog(TestCog(bot))
