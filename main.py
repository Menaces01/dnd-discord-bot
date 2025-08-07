import discord
import openai
import os
import json
import random
from dotenv import load_dotenv

"""
This Discord bot acts as a Dungeons & Dragons (D&D) assistant using OpenAI's
ChatGPT API. It supports immersive storytelling, dice rolling, simple
character management with persistence, and a basic turn‑based combat system.

Commands:
  !dnd <text>         – Ask the Dungeon Master (ChatGPT) to narrate or
                         adjudicate an action.
  !roll NdM           – Roll N dice with M sides (e.g. !roll 2d20).
  !createchar <name>  – Create a new character with the given name.
  !sheet              – View your character's sheet (name, class, inventory).
  !setclass <class>   – Set your character's class.
  !additem <item>     – Add an item to your inventory.
  !startcombat        – Begin a combat encounter, shuffling turn order.
  !endturn            – End the current character's turn, advancing to next.
  !endcombat          – End the encounter and clear combat state.

Persistent state for characters and combats is stored in JSON files
(`character_data.json` and `combat_data.json` respectively) in the working
directory. If those files exist at startup, they will be loaded so that
character sheets and ongoing combats persist across restarts.
"""

load_dotenv()  # Load environment variables from a .env file (if present)

# Grab the OpenAI and Discord tokens from environment variables.  These must
# be defined in the host environment (e.g. a .env file or Render variables).
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

# Paths to our JSON persistence files.
CHARACTER_FILE = "character_data.json"
COMBAT_FILE = "combat_data.json"

# In‑memory stores for characters and combat encounters.  These will be
# loaded from disk at startup and written back on changes.
characters = {}
combat_state = {}


def load_data() -> None:
    """Load character and combat data from JSON files if they exist."""
    global characters, combat_state
    # Load characters
    if os.path.isfile(CHARACTER_FILE):
        try:
            with open(CHARACTER_FILE, "r", encoding="utf-8") as f:
                characters = json.load(f)
        except Exception as e:
            print(f"Error loading {CHARACTER_FILE}: {e}")
            characters = {}
    # Load combat state
    if os.path.isfile(COMBAT_FILE):
        try:
            with open(COMBAT_FILE, "r", encoding="utf-8") as f:
                combat_state = json.load(f)
        except Exception as e:
            print(f"Error loading {COMBAT_FILE}: {e}")
            combat_state = {}


def save_characters() -> None:
    """Persist the character dictionary to disk."""
    try:
        with open(CHARACTER_FILE, "w", encoding="utf-8") as f:
            json.dump(characters, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving characters: {e}")


def save_combat() -> None:
    """Persist the combat state to disk."""
    try:
        with open(COMBAT_FILE, "w", encoding="utf-8") as f:
            json.dump(combat_state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving combat state: {e}")


def parse_dice_expression(expr: str) -> list[int]:
    """Parse an expression like '2d20' and roll the dice.

    Returns a list of individual dice results.  Raises ValueError on bad
    formatting.
    """
    try:
        parts = expr.lower().split("d")
        if len(parts) != 2:
            raise ValueError("Dice expression must be in NdM format.")
        n, m = int(parts[0]), int(parts[1])
        if n <= 0 or m <= 0:
            raise ValueError("Number of dice and sides must be positive.")
        return [random.randint(1, m) for _ in range(n)]
    except Exception as e:
        raise ValueError(str(e)) from e


intents = discord.Intents.default()
intents.message_content = True  # Required to read message content

client = discord.Client(intents=intents)

# System message sets the tone for ChatGPT Dungeon Master responses.
SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "You are a Dungeon Master (DM) in a fantasy world. "
        "You narrate vividly, describe environments, and adjudicate actions. "
        "Maintain a fun, immersive tone and encourage roleplay."
    ),
}


@client.event
async def on_ready() -> None:
    print(f"Logged in as {client.user}")
    load_data()  # Load persisted state at startup


@client.event
async def on_message(message: discord.Message) -> None:
    # Ignore messages from ourselves
    if message.author == client.user:
        return

    content = message.content.strip()
    # D&D chat with ChatGPT
    if content.startswith("!dnd"):
        prompt = content[4:].strip()
        if not prompt:
            await message.channel.send("Please provide an action or query after !dnd.")
            return
        messages = [SYSTEM_PROMPT, {"role": "user", "content": prompt}]
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=messages,
                max_tokens=500,
                temperature=0.9,
            )
            reply = response.choices[0].message.content.strip()
            await message.channel.send(reply)
        except Exception as e:
            await message.channel.send(f"⚠️ Error contacting OpenAI: {e}")
        return

    # Dice roller: !roll NdM
    if content.startswith("!roll"):
        expr = content[5:].strip()
        try:
            rolls = parse_dice_expression(expr)
            total = sum(rolls)
            roll_details = "+".join(str(r) for r in rolls)
            await message.channel.send(f"🎲 You rolled: {roll_details} = {total}")
        except ValueError as e:
            await message.channel.send(f"⚠️ {e}")
        return

    # Character creation: !createchar Name
    if content.startswith("!createchar"):
        name = content[len("!createchar"):].strip()
        if not name:
            await message.channel.send("Please provide a name for your character.")
            return
        user_id = str(message.author.id)
        characters[user_id] = {
            "name": name,
            "class": "",
            "items": [],
        }
        save_characters()
        await message.channel.send(f"Character '{name}' created!")
        return

    # Character sheet: !sheet
    if content.startswith("!sheet"):
        user_id = str(message.author.id)
        char = characters.get(user_id)
        if not char:
            await message.channel.send("You don't have a character yet. Use !createchar <name> to create one.")
            return
        name = char.get("name", "Unnamed")
        char_class = char.get("class", "Unassigned") or "Unassigned"
        items = char.get("items", [])
        item_list = ", ".join(items) if items else "No items"
        await message.channel.send(
            f"📜 **{name}** (Class: {char_class})\nInventory: {item_list}"
        )
        return

    # Set class: !setclass Class Name
    if content.startswith("!setclass"):
        class_name = content[len("!setclass"):].strip()
        user_id = str(message.author.id)
        char = characters.get(user_id)
        if not char:
            await message.channel.send("Create a character first using !createchar.")
            return
        if not class_name:
            await message.channel.send("Please specify a class.")
            return
        char["class"] = class_name
        save_characters()
        await message.channel.send(f"Class set to {class_name} for {char['name']}.")
        return

    # Add item: !additem Item Name
    if content.startswith("!additem"):
        item_name = content[len("!additem"):].strip()
        user_id = str(message.author.id)
        char = characters.get(user_id)
        if not char:
            await message.channel.send("Create a character first using !createchar.")
            return
        if not item_name:
            await message.channel.send("Please specify an item to add.")
            return
        char.setdefault("items", []).append(item_name)
        save_characters()
        await message.channel.send(f"Added {item_name} to {char['name']}'s inventory.")
        return

    # Combat commands
    # Start combat: !startcombat
    if content.startswith("!startcombat"):
        if combat_state.get("ongoing"):
            await message.channel.send("Combat is already in progress.")
            return
        # Build a turn order from all existing characters
        turn_order = [c["name"] for c in characters.values()]
        if not turn_order:
            await message.channel.send("No characters exist to start combat.")
            return
        random.shuffle(turn_order)
        combat_state["ongoing"] = True
        combat_state["turn_order"] = turn_order
        combat_state["current_index"] = 0
        save_combat()
        await message.channel.send(
            "⚔️ Combat begins! Turn order: " + ", ".join(turn_order) + f"\nIt is now {turn_order[0]}'s turn."
        )
        return

    # End turn: !endturn
    if content.startswith("!endturn"):
        if not combat_state.get("ongoing"):
            await message.channel.send("No combat is currently in progress.")
            return
        turn_order = combat_state.get("turn_order", [])
        idx = combat_state.get("current_index", 0)
        idx = (idx + 1) % len(turn_order) if turn_order else 0
        combat_state["current_index"] = idx
        save_combat()
        await message.channel.send(f"It is now {turn_order[idx]}'s turn.")
        return

    # End combat: !endcombat
    if content.startswith("!endcombat"):
        if not combat_state.get("ongoing"):
            await message.channel.send("No combat is currently in progress.")
            return
        combat_state.clear()
        save_combat()
        await message.channel.send("🛑 Combat has ended.")
        return


# Entrypoint for running the bot.  We only call client.run if DISCORD_TOKEN
# is set.  When running locally, ensure you have a .env file or environment
# variables defined.
if __name__ == "__main__":
    if not DISCORD_TOKEN or not OPENAI_API_KEY:
        raise RuntimeError(
            "Missing DISCORD_TOKEN or OPENAI_API_KEY environment variables."
        )
    client.run(DISCORD_TOKEN)