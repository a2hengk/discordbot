import discord

from core.bot import LunasBot
from core.config import load_config


def main() -> None:
    discord.utils.setup_logging()
    config = load_config()
    bot = LunasBot(config)
    bot.run(config.token, log_handler=None)  # Logging ist oben schon eingerichtet


if __name__ == "__main__":
    main()
