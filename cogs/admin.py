import discord
from discord.ext import commands
from discord import app_commands
from utils.checks import is_staff

def fmt(n: int) -> str: return f"{n:,}".replace(",", " ")

class AdminOrgModal(discord.ui.Modal):
    amount = discord.ui.TextInput(label="Сумма", placeholder="1000", max_length=12)

    def __init__(self, bot, org_id: int, action: str):
        super().__init__(title="Управление бюджетом организации")
        self.bot = bot
        self.org_id = org_id
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        try: amt = int(self.amount.value)
        except ValueError: return await interaction.response.send_message("Введите число.", ephemeral=True)
        
        org = await self.bot.db.get_organization(self.org_id)
        if self.action == "add":
            await self.bot.db.add_to_org_balance(self.org_id, amt)
            await interaction.response.send_message(f"✅ Добавлено {fmt(amt)} в бюджет.", ephemeral=True)
        elif self.action == "remove":
            await self.bot.db.update_organization(self.org_id, balance=max(0, org["balance"] - amt))
            await interaction.response.send_message(f"✅ Убрано {fmt(amt)} из бюджета.", ephemeral=True)
        elif self.action == "set":
            await self.bot.db.update_organization(self.org_id, balance=amt)
            await interaction.response.send_message(f"✅ Бюджет изменен на {fmt(amt)}.", ephemeral=True)


class AdminOrgActionView(discord.ui.View):
    def __init__(self, bot, org_id):
        super().__init__(timeout=120)
        self.bot = bot
        self.org_id = org_id

    @discord.ui.button(label="Добавить", style=discord.ButtonStyle.success)
    async def add(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(AdminOrgModal(self.bot, self.org_id, "add"))

    @discord.ui.button(label="Убрать", style=discord.ButtonStyle.danger)
    async def remove(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(AdminOrgModal(self.bot, self.org_id, "remove"))

    @discord.ui.button(label="Установить", style=discord.ButtonStyle.primary)
    async def set_b(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(AdminOrgModal(self.bot, self.org_id, "set"))

class AdminOrgSelect(discord.ui.Select):
    def __init__(self, bot, orgs):
        options = [discord.SelectOption(label=o['name'], value=str(o['org_id']), description=f"Владелец: {o['owner_id']}") for o in orgs]
        super().__init__(placeholder="Выберите организацию...", options=options)
        self.bot = bot
    async def callback(self, interaction: discord.Interaction):
        org_id = int(self.values[0])
        await interaction.response.send_message("Выберите действие с бюджетом:", view=AdminOrgActionView(self.bot, org_id), ephemeral=True)

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="admin", description="[STAFF] Управление балансом игроков")
    @app_commands.choices(action=[
        app_commands.Choice(name="➕ Добавить", value="add"),
        app_commands.Choice(name="➖ Убрать", value="remove"),
        app_commands.Choice(name="🔄 Обновить", value="update"),
    ])
    @is_staff()
    async def admin(self, i: discord.Interaction, action: app_commands.Choice[str], member: discord.Member, amount: int):
        if amount < 0: return await i.response.send_message("❌ Сумма > 0.", ephemeral=True)
        await self.bot.db.get_user(member.id)
        
        if action.value == "add": await self.bot.db.update_wallet(member.id, amount)
        elif action.value == "remove": await self.bot.db.update_wallet(member.id, -amount)
        else: await self.bot.db.set_wallet(member.id, amount)
        
        u = await self.bot.db.get_user(member.id)
        embed = discord.Embed(title="Баланс изменен", color=0xEB459E, description=f"**Игрок:** {member.mention}\n**Новый баланс:** {fmt(u['wallet'])} 💰")
        await i.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="admin_org", description="[STAFF] Управление бюджетами организаций")
    @is_staff()
    async def admin_org(self, i: discord.Interaction):
        orgs = await self.bot.db.get_all_organizations()
        if not orgs:
            return await i.response.send_message("На сервере нет организаций.", ephemeral=True)
        
        view = discord.ui.View()
        view.add_item(AdminOrgSelect(self.bot, orgs))
        await i.response.send_message("Выберите организацию для управления бюджетом:", view=view, ephemeral=True)

    @app_commands.command(name="create_org", description="[STAFF] Создать организацию для игрока")
    @is_staff()
    async def create_org(self, i: discord.Interaction, member: discord.Member, name: str, org_type: str = "Бизнес"):
        await self.bot.db.create_organization(member.id, name, org_type, "Не указана", "")
        await i.response.send_message(f"✅ Организация **{name}** создана для {member.mention}!", ephemeral=True)

    @app_commands.command(name="purge", description="[STAFF] Очистить сообщения")
    @is_staff()
    async def purge(self, i: discord.Interaction, amount: int):
        if not (1 <= amount <= 100):
            return await i.response.send_message("1..100", ephemeral=True)
        await i.response.defer(ephemeral=True)
        deleted = await i.channel.purge(limit=amount)
        await i.followup.send(f"🧹 Удалено {len(deleted)} сообщений.", ephemeral=True)

    async def cog_app_command_error(self, i, error):
        if isinstance(error, app_commands.CheckFailure): await i.response.send_message(f"🚫 {error}", ephemeral=True)

async def setup(bot): 
    await bot.add_cog(Admin(bot))