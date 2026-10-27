import asyncio
import logging
import discord
from discord.ext import commands

from database import db
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("zebot")

COGS = [
    "cogs.economy",
    "cogs.profile",
    "cogs.jobs",
    "cogs.shop",
    "cogs.market",
    "cogs.parties",
    "cogs.elections",
    "cogs.organizations",
    "cogs.tuppers",
    "cogs.purge",
    "cogs.registration",
    "cogs.settings",
    "cogs.admin",
    "cogs.welcome",
]


class ZeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.db = db
        self.temp_reg_data = {}

    async def setup_hook(self):
        await self.db.connect()

        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info("✅ Загружен %s", cog)
            except Exception:
                log.exception("❌ Ошибка загрузки %s", cog)

        from utils.command_groups import game, profile, admin

        for group in (game, profile, admin):
            try:
                self.tree.add_command(group)
            except Exception:
                log.exception("❌ Не удалось добавить группу %s", group.name)

        # --- Синхронизация ---
        guild_id = getattr(config, "GUILD_ID", None)
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            try:
                # 1. Очищаем старые команды в гильдии
                self.tree.clear_commands(guild=guild)
                # 2. Копируем глобальные команды в гильдию (чтобы они там появились)
                self.tree.copy_global_to(guild=guild)
                # 3. Синхронизируем гильдию (применяется мгновенно)
                synced = await self.tree.sync(guild=guild)
                log.info("🔁 Синхронизировано для гильдии %s: %s команд", guild_id, len(synced))
            except Exception:
                log.exception("❌ Ошибка синхронизации гильдии")

        # Глобальная синхронизация (может занять до 1 часа)
        try:
            synced = await self.tree.sync()
            log.info("🌍 Глобально синхронизировано: %s команд", len(synced))
        except Exception:
            log.exception("❌ Ошибка глобальной синхронизации")

    async def on_ready(self):
        log.info("🤖 Бот запущен как %s (%s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="за экономикой государства",
            )
        )

    async def close(self):
        try:
            from utils import election_image, organization_image
            await election_image.shutdown()
            await organization_image.shutdown()
        except Exception:
            pass
        await self.db.close()
        await super().close()


async def main():
    if not config.TOKEN or not config.DATABASE_URL:
        raise RuntimeError("Заполни DISCORD_TOKEN и DATABASE_URL в .env")
    bot = ZeBot()
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Бот остановлен")
