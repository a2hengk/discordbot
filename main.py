import discord
from discord.ext import commands
import os
import json
import random

# Lade den Token aus der config.json

with open("config.json") as f:
    config = json.load(f)

TOKEN = config["discord_token"]


# Setze die Intents für den Bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


# Synchronisiert alle Commands nach dem Laden
@bot.event
async def on_ready():
    print(f"Bot ist online als {bot.user} (ID: {bot.user.id})")
    synced = await bot.tree.sync()  # Synchronisiert einmal alle Commands
    print(f"Slash-Commands synchronisiert: {len(synced)} Commands")

    # Setze eine Rich Presence Aktivität
    
    activity = discord.Activity(
        type=discord.ActivityType.watching, 
        name="The angel next door spoils me rotten",
        details="top 1 romance anime",
        state="watching: (2/2)",
    )
    await bot.change_presence(activity=activity)


async def load_commands():
    for filename in os.listdir("./commands"):
        if filename.endswith(".py"):
            await bot.load_extension(f"commands.{filename[:-3]}")
    for filename in os.listdir("./commands/miniGames"):
        if filename.endswith(".py"):
            await bot.load_extension(f"commands.miniGames.{filename[:-3]}")

# Lade Konversationen aus convo.json
with open("convo.json", "r", encoding="utf-8") as f:
    convo = json.load(f)


@bot.event
async def setup_hook():
    await load_commands()

# Helferfunktion, um zu prüfen, ob eine Phrase in einer Nachricht enthalten ist
def contains_phrase(msg, phrases):
    return any(phrase in msg for phrase in phrases)


@bot.event
async def on_message(message):
    # Ignoriere eigene Nachrichten
    if message.author == bot.user:
        return
    # Kleinbuchstaben für bessere Erkennung
    msg = message.content.lower()

    if "guten morgen" == msg or "good morning" == msg or "gumo" == msg:
        await message.channel.send(f"Guten Morgen, {message.author.mention}! ☀️")
    elif "gute nacht" == msg or "good night" == msg or "guna" == msg:
        await message.channel.send(f"Gute Nacht, {message.author.mention}! 🌙")
    elif "Mahlzeit" == msg or "Mahlzeit!" == msg:
        await message.channel.send(f"Mahlzeit! {message.author.mention}, lass es dir schmecken! 🍽️")
    elif "Ja" == msg or "ya" == msg:
        await message.channel.send(f"Nichts hihi <3")

    # Mention prüfen
    is_mention = bot.user in message.mentions

    # Reply prüfen
    is_reply = False
    if message.reference:
        reply_msg = await message.channel.fetch_message(message.reference.message_id)
        if reply_msg.author == bot.user:
            is_reply = True

    if not (is_mention or is_reply):
        return  # Nur reagieren, wenn Mention oder Reply

    if contains_phrase(msg, convo["wie_gehts_phrases"]):
        response = random.choice(convo["wie_gehts_responses"])
        await message.channel.send(response)

    elif contains_phrase(msg, convo["user_wie_gehts_responses_happy"]):
        response = random.choice(convo["bot_was_machst_du_phrases_happy"])
        await message.channel.send(response)

    elif contains_phrase(msg, convo["user_wie_gehts_responses_sad"]):
        response = random.choice(convo["bot_was_machst_du_phrases_sad"])
        await message.channel.send(response)

    elif contains_phrase(msg, convo["user_was_machst_du_phrases"]):
        response = random.choice(convo["bot_was_machst_du_responses"])
        await message.channel.send(response)

    elif contains_phrase(msg, convo["user_erzaele_mir_ein_witz_phrases"]):
        response = random.choice(convo["bot_erzaele_mir_ein_witz_responses"])
        await message.channel.send(response)

    await bot.process_commands(message)


bot.run(TOKEN)
