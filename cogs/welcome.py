import discord
import io
import random
from pathlib import Path
from discord.ext import commands
from utils.render import render_template

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await self.bot.db.get_guild_settings(member.guild.id)
        if not settings or not settings["welcome_channel_id"]:
            return

        channel = member.guild.get_channel(int(settings["welcome_channel_id"]))
        if not channel:
            return

        # 1. Ищем картинку локально на компьютере
        bg_num = random.randint(1, 10)
        assets_dir = Path(__file__).parent.parent / "assets" / "welcome_bg"
        extensions = [".png", ".jpg", ".jpeg", ".webp"]
        bg_path = None

        for ext in extensions:
            check_path = assets_dir / f"{bg_num}{ext}"
            if check_path.exists():
                bg_path = check_path
                break
        
        bg_url = bg_path.as_uri() if bg_path else ""

        # 2. Данные для HTML
        data = {
            "bg_url": bg_url,
            "avatar_url": member.display_avatar.url,
            "username": member.name,
            "server_name": member.guild.name,
            "member_count": member.guild.member_count
        }

        # 3. Рендер картинки
        try:
            png = await render_template("welcome.html", data)
            file = discord.File(fp=io.BytesIO(png), filename="welcome.png")
        except Exception as e:
            print(f"❌ Ошибка рендера приветствия: {e}")
            file = None

        # 4. Форматируем время захода в обычный текст (например, "28.10.2026 20:45")
        join_time = member.joined_at.strftime("%d.%m.%Y %H:%M") if member.joined_at else "Неизвестно"

        # 5. Эмбед
        server_logo = member.guild.icon.url if member.guild.icon else "https://i.imgur.com/vHq5K9u.png"
        
        embed = discord.Embed(
            color=886333,
            title=f"Добро пожаловать, {member.name}!",
            description=f"[{member.name}](https://discord.com/users/{member.id}), добро пожаловать на наш сервер! Чувствуй себя здесь хорошо. Администрация и добрые игроки помогут тебе у нас освоиться. Нам было бы приятно знать, откуда ты узнал о нашем проекте. Ознакомься с правилами и информацией о сервере. **Приятного тебе прибывания!**"
        )
        embed.set_author(name=f"{member.name} ({member.id}) пришёл к нам!", icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=server_logo)
        
        if file:
            embed.set_image(url="attachment://welcome.png")

        # 6. НОВЫЙ ФУТЕР: убрали "Время захода", поставили дефис
        embed.set_footer(text=f"С уважением, администрация проекта {member.guild.name}! - {join_time}")

        # 7. Отправляем. Пинг выносим в content, чтобы он работал как уведомление
        ping = member.mention
        
        if file:
            await channel.send(content=ping, embed=embed, file=file)
        else:
            await channel.send(content=ping, embed=embed)

async def setup(bot):
    await bot.add_cog(Welcome(bot))