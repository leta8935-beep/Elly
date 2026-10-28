import time
import io
import discord
from discord.ext import commands
from discord import app_commands
from utils.render import render_template

def fmt(n: int) -> str: return f"{n:,}".replace(",", " ")

# ─── Модалки и кнопки управления (без изменений) ───
class OrgEditModal(discord.ui.Modal, title="Настройки организации"):
    name = discord.ui.TextInput(label="Название", max_length=50)
    logo_url = discord.ui.TextInput(label="Ссылка на логотип", max_length=300)

    def __init__(self, bot, org_id: int, current_name: str, current_logo: str):
        super().__init__()
        self.bot = bot
        self.org_id = org_id
        self.name.default = current_name
        self.logo_url.default = current_logo

    async def on_submit(self, interaction: discord.Interaction):
        async with self.bot.db.pool.acquire() as c:
            await c.execute("UPDATE organizations SET name=$1, logo_url=$2 WHERE org_id=$3", self.name.value, self.logo_url.value, self.org_id)
        await interaction.response.send_message("✅ Данные обновлены! Нажмите `/org` снова.", ephemeral=True)

class AdminBalanceModal(discord.ui.Modal):
    amount = discord.ui.TextInput(label="Сумма", placeholder="1000 или -1000", max_length=12)
    def __init__(self, bot, org_id: int, action: str):
        super().__init__(title="Добавить в бюджет" if action == "add" else "Убрать из бюджета")
        self.bot = bot
        self.org_id = org_id
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            if amt <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message("Введите положительное число.", ephemeral=True)
        
        org = await self.bot.db.get_organization(self.org_id)
        if self.action == "add": await self.bot.db.add_to_org_balance(self.org_id, amt)
        else: await self.bot.db.update_organization(self.org_id, balance=max(0, org["balance"] - amt))
        
        await interaction.response.send_message(f"✅ Бюджет обновлён. Текущий: **{fmt(org['balance'] + (amt if self.action == 'add' else -amt))}** RUB", ephemeral=True)

class StaffManageView(discord.ui.View):
    def __init__(self, bot, org_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.org_id = org_id

    @discord.ui.button(label="Нанять сотрудника", style=discord.ButtonStyle.success, emoji="➕")
    async def hire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(HireModal(self.bot, self.org_id))

    @discord.ui.button(label="Список сотрудников", style=discord.ButtonStyle.secondary, emoji="📋")
    async def list_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        members = await self.bot.db.get_org_members(self.org_id)
        if not members: return await interaction.response.send_message("В организации нет сотрудников.", ephemeral=True)
        text = "\n".join([f"• <@{m['user_id']}> — {m['rank']}" for m in members])
        await interaction.response.send_message(f"**Сотрудники:**\n{text}", ephemeral=True)

class HireModal(discord.ui.Modal, title="Нанять сотрудника"):
    user_id = discord.ui.TextInput(label="Discord ID или @упоминание", placeholder="123456789012345678", max_length=50)
    rank = discord.ui.TextInput(label="Должность", placeholder="Менеджер", max_length=30, default="Сотрудник")

    def __init__(self, bot, org_id: int):
        super().__init__()
        self.bot = bot
        self.org_id = org_id

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.user_id.value.replace("<@", "").replace("!", "").replace(">", "").strip()
        try: uid = int(raw_id)
        except ValueError: return await interaction.response.send_message("Ошибка: неверный ID.", ephemeral=True)
        await self.bot.db.add_org_member(self.org_id, uid, self.rank.value)
        await interaction.response.send_message(f"✅ <@{uid}> принят на должность **{self.rank.value}**!", ephemeral=True)

class OrgActions(discord.ui.View):
    def __init__(self, bot, org_id: int, is_admin_view: bool = False):
        super().__init__(timeout=120)
        self.bot = bot
        self.org_id = org_id
        if is_admin_view:
            delete_btn = discord.ui.Button(label="Удалить", style=discord.ButtonStyle.danger, emoji="🗑️", row=2)
            delete_btn.callback = self.delete_org
            self.add_item(delete_btn)

    async def delete_org(self, interaction: discord.Interaction):
        org = await self.bot.db.get_organization(self.org_id)
        await self.bot.db.delete_organization(self.org_id)
        await interaction.response.edit_message(content=f"🗑️ Организация **{org['name']}** удалена.", embed=None, view=None)

    @discord.ui.button(label="Собрать прибыль", style=discord.ButtonStyle.success, emoji="💰")
    async def collect(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or (org["owner_id"] != interaction.user.id and not interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("Это не ваша организация.", ephemeral=True)
        now = time.time()
        hours = (now - org["last_collect"]) / 3600
        if hours < 1: return await interaction.response.send_message(f"Прибыль через {int((1-hours)*60)} мин.", ephemeral=True)
        accumulated = min(int(hours * (org["level"] * 500)), (org["level"] * 500) * 24)
        await self.bot.db.update_wallet(org["owner_id"], accumulated)
        await self.bot.db.update_organization(self.org_id, last_collect=now)
        await interaction.response.send_message(f"Собрано **{fmt(accumulated)}** RUB!", ephemeral=True)

    @discord.ui.button(label="Пополнить бюджет", style=discord.ButtonStyle.primary, emoji="🏦")
    async def deposit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DepositModal(self.bot, self.org_id))

    @discord.ui.button(label="Улучшить", style=discord.ButtonStyle.secondary, emoji="📈")
    async def upgrade(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or (org["owner_id"] != interaction.user.id and not interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("Это не ваша организация.", ephemeral=True)
        cost = org["level"] * 10000
        user = await self.bot.db.get_user(org["owner_id"])
        if user["wallet"] < cost: return await interaction.response.send_message(f"Нужно **{fmt(cost)}** RUB на кошельке.", ephemeral=True)
        await self.bot.db.update_wallet(org["owner_id"], -cost)
        await self.bot.db.update_organization(self.org_id, level=org["level"]+1)
        await interaction.response.send_message(f"Организация улучшена до **LVL {org['level']+1}**!", ephemeral=True)

    @discord.ui.button(label="Настройки", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def edit_org(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or (org["owner_id"] != interaction.user.id and not interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        await interaction.response.send_modal(OrgEditModal(self.bot, self.org_id, org["name"], org["logo_url"]))

    @discord.ui.button(label="Сотрудники", style=discord.ButtonStyle.secondary, emoji="👥", row=1)
    async def staff_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or (org["owner_id"] != interaction.user.id and not interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        await interaction.response.send_message("Управление сотрудниками:", view=StaffManageView(self.bot, self.org_id), ephemeral=True)

    @discord.ui.button(label="Бюджет (Админ)", style=discord.ButtonStyle.danger, emoji="🛠️", row=2)
    async def admin_balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Только для админов.", ephemeral=True)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Пополнить", style=discord.ButtonStyle.success, custom_id="add"))
        view.add_item(discord.ui.Button(label="Списать", style=discord.ButtonStyle.danger, custom_id="remove"))
        async def callback(inter: discord.Interaction):
            await inter.response.send_modal(AdminBalanceModal(self.bot, self.org_id, inter.data["custom_id"]))
        for child in view.children: child.callback = callback
        await interaction.response.send_message("Действие с бюджетом:", view=view, ephemeral=True)

class DepositModal(discord.ui.Modal, title="Пополнение бюджета"):
    amount = discord.ui.TextInput(label="Сумма", placeholder="1000", max_length=12)
    def __init__(self, bot, org_id: int):
        super().__init__()
        self.bot = bot
        self.org_id = org_id
    async def on_submit(self, interaction: discord.Interaction):
        try: amt = int(self.amount.value)
        except ValueError: return await interaction.response.send_message("Введите число.", ephemeral=True)
        user = await self.bot.db.get_user(interaction.user.id)
        if user["wallet"] < amt: return await interaction.response.send_message("Мало денег.", ephemeral=True)
        await self.bot.db.update_wallet(interaction.user.id, -amt)
        await self.bot.db.add_to_org_balance(self.org_id, amt)
        await interaction.response.send_message(f"Бюджет пополнен на **{fmt(amt)}** RUB.", ephemeral=True)

# ─── НОВОЕ МЕНЮ ВЫБОРА ───
class OrgSelectMenu(discord.ui.Select):
    def __init__(self, orgs: list, bot, is_admin_view: bool):
        options = []
        for o in orgs:
            desc = f"Владелец: <@{o['owner_id']}>" if is_admin_view else f"{o['org_type']} • LVL {o['level']}"
            options.append(discord.SelectOption(label=o['name'], value=str(o['org_id']), description=desc))
        
        super().__init__(placeholder="Выберите организацию...", options=options)
        self.bot = bot
        self.is_admin_view = is_admin_view

    async def callback(self, interaction: discord.Interaction):
        org_id = int(self.values[0])
        await interaction.response.defer()
        org = await self.bot.db.get_organization(org_id)
        now = time.time()
        accumulated = min(int(((now - org["last_collect"]) / 3600) * (org["level"] * 500)), (org["level"] * 500) * 24)
        
        data = {
            "name": org["name"], "org_type": org["org_type"], "sphere": org["sphere"],
            "logo_url": org["logo_url"], "income": org["level"] * 500, "acc": accumulated,
            "balance": org["balance"], "level": org["level"], "owner": f"ID: {org['owner_id']}"
        }
        png = await render_template("organization.html", data)
        file = discord.File(fp=io.BytesIO(png), filename="org.png")
        
        view = OrgActions(self.bot, org_id, is_admin_view=self.is_admin_view)
        await interaction.followup.send(file=file, view=view, ephemeral=True)


class OrgSelectView(discord.ui.View):
    def __init__(self, bot, user, is_admin: bool, view_all: bool, orgs: list):
        super().__init__(timeout=180)
        self.bot = bot
        self.user = user
        self.is_admin = is_admin
        self.view_all = view_all
        
        if orgs:
            self.add_item(OrgSelectMenu(orgs, self.bot, self.is_admin or self.view_all))

        # Если это админ, добавляем кнопку переключения
        if self.is_admin:
            btn_label = "👤 Мои организации" if self.view_all else "🌐 Все организации"
            btn_style = discord.ButtonStyle.secondary if self.view_all else discord.ButtonStyle.primary
            btn = discord.ui.Button(label=btn_label, style=btn_style, row=1)
            btn.callback = self.toggle_view
            self.add_item(btn)

    async def toggle_view(self, interaction: discord.Interaction):
        self.view_all = not self.view_all
        if self.view_all:
            orgs = await self.bot.db.get_all_organizations()
        else:
            orgs = await self.bot.db.get_user_organizations(self.user.id)
        
        # Пересоздаем View с новыми данными
        new_view = OrgSelectView(self.bot, self.user, self.is_admin, self.view_all, orgs)
        await interaction.response.edit_message(view=new_view)


# ─── КОМАНДА /org ───
class Organization(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="org", description="Меню управления организациями")
    async def org(self, i: discord.Interaction):
        is_admin = i.user.guild_permissions.administrator or i.user.id == i.guild.owner_id
        orgs = await self.bot.db.get_user_organizations(i.user.id)
        
        if not orgs and not is_admin:
            return await i.response.send_message("У вас нет организаций. Подайте заявку через панель!", ephemeral=True)

        # Если у обычного игрока только одна организация, сразу открываем её
        if len(orgs) == 1 and not is_admin:
            org = orgs[0]
            await i.response.defer(ephemeral=True)
            now = time.time()
            accumulated = min(int(((now - org["last_collect"]) / 3600) * (org["level"] * 500)), (org["level"] * 500) * 24)
            data = {
                "name": org["name"], "org_type": org["org_type"], "sphere": org["sphere"], "logo_url": org["logo_url"],
                "income": org["level"] * 500, "acc": accumulated, "balance": org["balance"], "level": org["level"], "owner": f"ID: {org['owner_id']}"
            }
            png = await render_template("organization.html", data)
            file = discord.File(fp=io.BytesIO(png), filename="org.png")
            await i.followup.send(file=file, view=OrgActions(self.bot, org["org_id"], is_admin_view=False), ephemeral=True)
        else:
            # Если это админ или у игрока несколько орг, показываем меню
            view = OrgSelectView(self.bot, i.user, is_admin, view_all=False, orgs=orgs)
            await i.response.send_message("Выберите организацию:", view=view, ephemeral=True)

async def setup(bot): await bot.add_cog(Organization(bot))