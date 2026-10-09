"""Kleine Chat-Persönlichkeit: Begrüßungen und Antworten bei @Mention/Reply."""

from __future__ import annotations

import json
import random
import re

import discord
from discord.ext import commands

from core.bot import LunasBot
from core.config import CONVO_FILE

_PUNCT = re.compile(r"[!?.,:;~]+")


def normalize(text: str) -> str:
    return _PUNCT.sub("", text.lower()).strip()


def matches(text: str, triggers: list[str]) -> bool:
    """Ganze Wörter/Phrasen statt Substring – sonst triggert 'gut' auch in 'gute nacht'."""
    return any(re.search(rf"(?<!\w){re.escape(t)}(?!\w)", text) for t in triggers)


class Chat(commands.Cog):
    def __init__(self, bot: LunasBot):
        self.bot = bot
        convo = json.loads(CONVO_FILE.read_text(encoding="utf-8"))
        self.greetings: list[dict] = convo["greetings"]
        self.intents: list[dict] = convo["intents"]

    async def _is_reply_to_bot(self, message: discord.Message) -> bool:
        ref = message.reference
        if ref is None or ref.message_id is None:
            return False
        target = ref.resolved
        if not isinstance(target, discord.Message):
            try:
                target = await message.channel.fetch_message(ref.message_id)
            except discord.HTTPException:
                return False
        return target.author == self.bot.user

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        text = normalize(message.content)

        # Begrüßungen: nur wenn die ganze Nachricht genau so lautet
        for greeting in self.greetings:
            if text in greeting["triggers"]:
                await message.channel.send(greeting["response"].format(mention=message.author.mention))
                return

        mentioned = self.bot.user in message.mentions
        if not (mentioned or await self._is_reply_to_bot(message)):
            return

        for intent in self.intents:
            if matches(text, intent["triggers"]):
                await message.reply(random.choice(intent["responses"]), mention_author=False)
                return


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(Chat(bot))
