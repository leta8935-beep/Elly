import discord
from discord.ext import commands
from discord import app_commands
from urllib.parse import urlparse

def fmt(n: int) -> str: return f"{n:,}".replace(",", " ")

def is_valid_url(url):
    """Проверяет, является ли строка валидной ссылкой (http/https)."""
    if not url or not isinstance(url, str):
        return False
    try:
        result = urlparse(url.strip())
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Показать ваш кошелёк")
    async def balance(self, i: discord.Interaction, member: discord.Member = None):
        is_admin = i.user.guild_permissions.administrator or i.user.id == i.guild.owner_id
        if member and member.id != i.user.id and not is_admin:
            return await i.response.send_message("🚫 Только персонал может смотреть чужие кошельки.", ephemeral=True)

        target = member or i.user
        u = await self.bot.db.get_user(target.id)
        p = await self.bot.db.get_passport(target.id)
        settings = await self.bot.db.get_guild_settings(i.guild.id)
        
        currency = settings["currency"] if settings and settings["currency"] else "RUB"

        embed = discord.Embed(
            color=1685058,
            title="💰 » Финансовый отчёт",
            description=f"**- [ 👤 ] Участник :** *{target.mention};*\n**- [ 🧾 ] Баланс :** *{fmt(u['wallet'])} {currency}.*"
        )
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
        
        # --- ЛОГИКА ФУТЕРА (ЕСЛИ НЕТ ПАСПОРТА) ---
        if p:
            full_name = f"{p['surname']} {p['name']}"
            photo = p.get("photo_url", "")
            
            if is_valid_url(photo):
                embed.set_footer(text=full_name, icon_url=photo.strip())
            else:
                embed.set_footer(text=full_name)
        else:
            # Если нет паспорта, просто пишем текст, без иконки
            embed.set_footer(text="Нету персонажа")

        await i.response.send_message(embed=embed, ephemeral=(target.id == i.user.id))

    @app_commands.command(name="pay", description="Перевести средства (без налога)")
    async def pay(self, i: discord.Interaction, member: discord.Member, amount: int):
        if member.bot or member.id == i.user.id or amount <= 0:
            return await i.response.send_message("❌ Некорректная операция.", ephemeral=True)

        sender = await self.bot.db.get_user(i.user.id)
        if sender["wallet"] < amount:
            return await i.response.send_message("❌ Недостаточно средств.", ephemeral=True)

        await self.bot.db.get_user(member.id)
        
        # Перевод без налога
        await self.bot.db.update_wallet(i.user.id, -amount)
        await self.bot.db.update_wallet(member.id, amount)
        await self.bot.db.log(i.user.id, member.id, amount, "pay")

        settings = await self.bot.db.get_guild_settings(i.guild.id)
        currency = settings["currency"] if settings and settings["currency"] else "RUB"

        embed = discord.Embed(title="✅ Перевод выполнен", color=0x57F287)
        embed.description = f"**{i.user.mention}** перевел **{fmt(amount)} {currency}** для {member.mention}"
        await i.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Economy(bot))