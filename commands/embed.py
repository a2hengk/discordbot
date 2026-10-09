import discord
from discord.ext import commands

class EmbedCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(
        name="embed",
        description="Sendet einen Text oder ein Bild als Embed."
    )
    async def embed(
        self,
        interaction: discord.Interaction,
        text: str = None,
        image: discord.Attachment = None
    ):
        # Embed erstellen
        embed = discord.Embed(
            description=text if text else None,
            color=discord.Color.blue()
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )

        # Falls ein Bild hochgeladen wurde
        if image:
            if image.content_type and image.content_type.startswith("image"):
                embed.set_image(url=image.url)

        # Embed senden
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(EmbedCommand(bot))
