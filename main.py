import os
import discord
import traceback
from discord.ext import commands
from dotenv import load_dotenv
from database import Database

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

COGS = [
    "cogs.economy", 
    "cogs.organization", 
    "cogs.admin", 
    "cogs.settings",
    "cogs.registration"
]

class Elly(commands.Bot):
    def __init__(self):
        # Включаем интенты (важно для чтения сообщений)
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.db = Database(DATABASE_URL)
        self.temp_reg_data = {}

    async def setup_hook(self):
        print("🔄 Запуск setup_hook...", flush=True)
        try:
            print("⏳ Подключение к базе данных...", flush=True)
            await self.db.connect()
            print("✅ База данных подключена.", flush=True)
        except Exception as e:
            print(f"❌ ОШИБКА БАЗЫ ДАННЫХ: {e}", flush=True)
            raise e # Останавливаем запуск, если база не работает

        for cog in COGS:
            try:
                await self.load_extension(cog)
                print(f"✅ Загружен {cog}", flush=True)
            except Exception as e:
                print(f"❌ Ошибка при загрузке {cog}: {e}", flush=True)
                traceback.print_exc()
        
        print("⏳ Синхронизация команд...", flush=True)
        await self.tree.sync()
        print("✅ Бот запущен, команды синхронизированы!", flush=True)

if __name__ == "__main__":
    if not TOKEN or not DATABASE_URL:
        raise RuntimeError("Заполни DISCORD_TOKEN и DATABASE_URL")
    bot = Elly()
    bot.run(TOKEN)