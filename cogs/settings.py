import discord
from discord.ext import commands
from discord import app_commands
from utils.checks import is_staff

STATE_TRANSLATIONS = {
    "РОССИЯ": "RUSSIAN FEDERATION", "РОССИЙСКАЯ ФЕДЕРАЦИЯ": "RUSSIAN FEDERATION",
    "ГЕРМАНИЯ": "GERMANY", "США": "UNITED STATES OF AMERICA", "ФРАНЦИЯ": "FRANCE",
    "ВЕЛИКОБРИТАНИЯ": "UNITED KINGDOM", "ИТАЛИЯ": "ITALY", "ЯПОНИЯ": "JAPAN",
    "КИТАЙ": "CHINA", "УКРАИНА": "UKRAINE", "КАЗАХСТАН": "KAZAKHSTAN",
}

# ─── 1. Модалка Государства (с валютой) ───
class StateModal(discord.ui.Modal, title="Настройка государства"):
    ru = discord.ui.TextInput(label="Название (Рус.)", placeholder="РОССИЙСКАЯ ФЕДЕРАЦИЯ", max_length=50)
    code = discord.ui.TextInput(label="Код (3 буквы)", placeholder="RUS", max_length=3, min_length=3)
    en = discord.ui.TextInput(label="Название (Англ., опционально)", required=False, max_length=50)
    currency = discord.ui.TextInput(label="Валюта", placeholder="RUB или ₽", max_length=10, default="RUB")

    def __init__(self, bot, guild_id):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        ru_name = self.ru.value.strip().upper()
        code = self.code.value.strip().upper()
        en_name = self.en.value.strip().upper() or STATE_TRANSLATIONS.get(ru_name, "UNKNOWN")
        
        await self.bot.db.set_guild_setting(self.guild_id, "state_name", ru_name)
        await self.bot.db.set_guild_setting(self.guild_id, "state_code", code)
        await self.bot.db.set_guild_setting(self.guild_id, "state_name_en", en_name)
        await self.bot.db.set_guild_setting(self.guild_id, "currency", self.currency.value.strip())
        
        await interaction.response.send_message(f"✅ Государство: **{ru_name} / {en_name} ({code})**\nВалюта: **{self.currency.value.strip()}**", ephemeral=True)

# ─── 2. Модалка Менеджера ───
class ManagerModal(discord.ui.Modal, title="Назначить менеджера"):
    user_id = discord.ui.TextInput(label="Discord ID пользователя", placeholder="123456789012345678")

    def __init__(self, bot, guild_id):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id.value.replace("<@", "").replace("!", "").replace(">", ""))
            await self.bot.db.set_guild_setting(self.guild_id, "manager_id", uid)
            await interaction.response.send_message(f"✅ <@{uid}> теперь менеджер бота.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Ошибка: неверный ID.", ephemeral=True)

# ─── 3. Выбор каналов (Универсальный) ───
class ChannelSelect(discord.ui.Select):
    def __init__(self, bot, guild_id, channels, setting_name, label):
        options = [discord.SelectOption(label=f"#{ch.name}", value=str(ch.id)) for ch in channels[:25]]
        super().__init__(placeholder=f"Выберите {label}...", options=options)
        self.bot = bot
        self.guild_id = guild_id
        self.setting_name = setting_name

    async def callback(self, interaction: discord.Interaction):
        await self.bot.db.set_guild_setting(self.guild_id, self.setting_name, int(self.values[0]))
        await interaction.response.send_message(f"✅ {self.setting_name} установлен: <#{self.values[0]}>", ephemeral=True)

# ─── 4. Модалка Ролей ───
class RolesModal(discord.ui.Modal, title="Настройка ролей"):
    citizen = discord.ui.TextInput(label="ID ролей граждан (через запятую)", required=False)
    curator = discord.ui.TextInput(label="ID Куратора", required=False)
    mod = discord.ui.TextInput(label="ID Модератора", required=False)
    admin = discord.ui.TextInput(label="ID Администратора", required=False)
    pr = discord.ui.TextInput(label="ID Пиар-менеджера", required=False)

    def __init__(self, bot, guild_id):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        if self.citizen.value: await self.bot.db.set_guild_setting(self.guild_id, "start_roles", self.citizen.value.replace(" ", ""))
        for field, col in [(self.curator, "curator_role"), (self.mod, "mod_role"), (self.admin, "admin_role"), (self.pr, "pr_role")]:
            if field.value: await self.bot.db.set_guild_setting(self.guild_id, col, int(field.value))
        await interaction.response.send_message("✅ Роли сохранены!", ephemeral=True)

# ─── 5. Основное меню настроек ───
class SetupView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(label="Государство и Валюта", style=discord.ButtonStyle.primary, emoji="🌍")
    async def state_btn(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(StateModal(self.bot, self.guild_id))

    @discord.ui.button(label="Канал проверки", style=discord.ButtonStyle.secondary, emoji="📢")
    async def review_channel_btn(self, i: discord.Interaction, b: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(ChannelSelect(self.bot, self.guild_id, i.guild.text_channels, "review_channel_id", "канал проверки"))
        await i.response.send_message("Выберите канал проверки анкет:", view=view, ephemeral=True)

    @discord.ui.button(label="Канал приветствий", style=discord.ButtonStyle.secondary, emoji="👋")
    async def welcome_channel_btn(self, i: discord.Interaction, b: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(ChannelSelect(self.bot, self.guild_id, i.guild.text_channels, "welcome_channel_id", "канал приветствий"))
        await i.response.send_message("Выберите канал для приветствий:", view=view, ephemeral=True)

    @discord.ui.button(label="Роли", style=discord.ButtonStyle.secondary, emoji="🎭")
    async def roles_btn(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(RolesModal(self.bot, self.guild_id))

    @discord.ui.button(label="Менеджер", style=discord.ButtonStyle.secondary, emoji="👑", row=1)
    async def manager_btn(self, i: discord.Interaction, b: discord.ui.Button):
        if i.user.id != i.guild.owner_id:
            return await i.response.send_message("Только владелец сервера может назначать менеджера.", ephemeral=True)
        await i.response.send_modal(ManagerModal(self.bot, self.guild_id))

    @discord.ui.button(label="Закрыть", style=discord.ButtonStyle.danger, emoji="✖️", row=1)
    async def close_btn(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.edit_message(content="Настройка завершена.", view=None)

class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="[STAFF] Настройка сервера")
    @is_staff()
    async def setup_cmd(self, i: discord.Interaction):
        s = await self.bot.db.get_guild_settings(i.guild.id)
        ru = s["state_name"] if s and s["state_name"] else "Не задано"
        code = s["state_code"] if s and s["state_code"] else "Не задано"
        curr = s["currency"] if s and s["currency"] else "RUB"
        ch_review = f"<#{s['review_channel_id']}>" if s and s["review_channel_id"] else "Не задано"
        ch_welcome = f"<#{s['welcome_channel_id']}>" if s and s["welcome_channel_id"] else "Не задано"
        
        embed = discord.Embed(title="⚙️ Настройка сервера", color=0x5865F2)
        embed.description = "Нажмите на кнопку, чтобы изменить параметр."
        embed.add_field(name="🌍 Государство", value=f"{ru} ({code})", inline=True)
        embed.add_field(name="💵 Валюта", value=curr, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="📢 Канал проверки", value=ch_review, inline=True)
        embed.add_field(name="👋 Канал приветствий", value=ch_welcome, inline=True)
        
        await i.response.send_message(embed=embed, view=SetupView(self.bot, i.guild.id), ephemeral=True)

    @app_commands.command(name="idtext", description="[STAFF] Отправить панель")
    @is_staff()
    @app_commands.choices(message_type=[
        app_commands.Choice(name="Регистрация", value="registration"),
        app_commands.Choice(name="Набор в Стафф", value="staff_registration"),
        app_commands.Choice(name="Заявка на Организацию", value="org_registration")
    ])
    async def idtext(self, i: discord.Interaction, channel: discord.TextChannel, message_type: app_commands.Choice[str], text: str = "Нажмите кнопку ниже.", image_url: str = None):
        embed = discord.Embed(title="📋 Заявка", description=text, color=discord.Color.blue())
        if image_url: embed.set_image(url=image_url)

        from cogs.registration import RegistrationView, StaffRegistrationView, OrgRegistrationView
        if message_type.value == "registration":
            embed.title = "📋 Регистрация Гражданина"
            view = RegistrationView()
        elif message_type.value == "staff_registration":
            embed.title = "👑 Набор в Администрацию"
            view = StaffRegistrationView()
        else:
            embed.title = "🏢 Открытие Организации"
            view = OrgRegistrationView()
        
        await channel.send(embed=embed, view=view)
        await i.response.send_message("✅ Отправлено!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Settings(bot))