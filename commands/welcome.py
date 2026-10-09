import discord
from discord.ext import commands
import os
import json

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.welcome_channel_id = 0  # Standardwert

        if os.path.exists("config.json"):
            with open("config.json") as f:
                config = json.load(f)
                self.welcome_channel_id = int(config.get("welcome_channel_id", 0))

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not self.welcome_channel_id:
            print("Kein Welcome-Channel in config.json gesetzt.")
            return

        channel = self.bot.get_channel(self.welcome_channel_id)
        if not channel:
            print(f"Kanal mit ID {self.welcome_channel_id} nicht gefunden.")
            return

        embed = discord.Embed(
            title="Willkommen auf dem Server!",
            description=f"Hallo {member.mention}, wir freuen uns, dich hier zu haben!",
            color=discord.Color.green()
        )

        image_path = "images/join.gif"
        if os.path.isfile(image_path):
            with open(image_path, 'rb') as f:
                picture = discord.File(f, filename="image.gif")
                embed.set_image(url="attachment://image.gif")
                await channel.send(embed=embed, file=picture)
        else:
            await channel.send(embed=embed)  # trotzdem Embed senden

async def setup(bot):
    await bot.add_cog(Welcome(bot))
