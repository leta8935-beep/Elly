import os
import discord
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
    "cogs.registration",
    "cogs.welcome" # <-- Добавили приветствия
]

class Elly(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True # <-- Обязательно для on_member_join
        super().__init__(command_prefix="!", intents=intents)
        self.db = Database(DATABASE_URL)
        self.temp_reg_data = {}

    async def setup_hook(self):
        await self.db.connect()
        print("База данных подключена.")
        for cog in COGS:
            try:
                await self.load_extension(cog)
                print(f"✅ Загружен {cog}")
            except Exception as e:
                print(f"❌ Ошибка при загрузке {cog}: {e}")
        
        await self.tree.sync()
        print("Бот запущен, команды синхронизированы!")

if __name__ == "__main__":
    if not TOKEN or not DATABASE_URL:
        raise RuntimeError("Заполни DISCORD_TOKEN и DATABASE_URL")
    bot = Elly()
    bot.run(TOKEN)