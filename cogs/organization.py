# cogs/organization.py
import io
import discord
from discord.ext import commands
from discord import app_commands
from utils.render import render_template


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


# ══════════════════════════════════════════════════════════════════════
#   МОДАЛКИ
# ══════════════════════════════════════════════════════════════════════
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
            await c.execute(
                "UPDATE organizations SET name=$1, logo_url=$2 WHERE org_id=$3",
                self.name.value,
                self.logo_url.value,
                self.org_id,
            )
        await interaction.response.send_message(
            "✅ Данные обновлены! Нажмите `/org` снова.", ephemeral=True
        )


class DepositModal(discord.ui.Modal, title="Добавить в бюджет"):
    amount = discord.ui.TextInput(label="Сумма", placeholder="1000", max_length=12)

    def __init__(self, bot, org_id: int, parent_view: "BudgetManageView"):
        super().__init__()
        self.bot = bot
        self.org_id = org_id
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message("Введите число.", ephemeral=True)
        if amt <= 0:
            return await interaction.response.send_message(
                "Сумма должна быть больше 0.", ephemeral=True
            )
        user = await self.bot.db.get_user(interaction.user.id)
        if user["wallet"] < amt:
            return await interaction.response.send_message(
                "Недостаточно средств на кошельке.", ephemeral=True
            )
        await self.bot.db.update_wallet(interaction.user.id, -amt)
        await self.bot.db.add_to_org_balance(self.org_id, amt)
        await interaction.response.defer()
        await self.parent_view.refresh(interaction)


class WithdrawModal(discord.ui.Modal, title="Забрать из бюджета"):
    amount = discord.ui.TextInput(label="Сумма", placeholder="1000", max_length=12)

    def __init__(self, bot, org_id: int, parent_view: "BudgetManageView"):
        super().__init__()
        self.bot = bot
        self.org_id = org_id
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message("Введите число.", ephemeral=True)
        if amt <= 0:
            return await interaction.response.send_message(
                "Сумма должна быть больше 0.", ephemeral=True
            )
        org = await self.bot.db.get_organization(self.org_id)
        if not org:
            return await interaction.response.send_message(
                "Организация не найдена.", ephemeral=True
            )
        if org["balance"] < amt:
            return await interaction.response.send_message(
                f"В бюджете недостаточно средств (баланс: {fmt(org['balance'])}).",
                ephemeral=True,
            )
        await self.bot.db.add_to_org_balance(self.org_id, -amt)
        await self.bot.db.update_wallet(interaction.user.id, amt)
        await interaction.response.defer()
        await self.parent_view.refresh(interaction)


class HireModal(discord.ui.Modal, title="Нанять сотрудника"):
    user_id = discord.ui.TextInput(
        label="Discord ID или @упоминание",
        placeholder="123456789012345678",
        max_length=50,
    )
    rank = discord.ui.TextInput(
        label="Должность", placeholder="Менеджер", max_length=30, default="Сотрудник"
    )

    def __init__(self, bot, org_id: int):
        super().__init__()
        self.bot = bot
        self.org_id = org_id

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = (
            self.user_id.value.replace("<@", "").replace("!", "").replace(">", "").strip()
        )
        try:
            uid = int(raw_id)
        except ValueError:
            return await interaction.response.send_message(
                "Ошибка: неверный ID.", ephemeral=True
            )
        await self.bot.db.add_org_member(self.org_id, uid, self.rank.value)
        await interaction.response.send_message(
            f"✅ <@{uid}> принят на должность **{self.rank.value}**!", ephemeral=True
        )


class OrgPayModal(discord.ui.Modal, title="Перевод в бюджет"):
    amount = discord.ui.TextInput(label="Сумма", placeholder="1000", max_length=12)

    def __init__(self, bot, org_id):
        super().__init__()
        self.bot = bot
        self.org_id = org_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message("Введите число.", ephemeral=True)
        user = await self.bot.db.get_user(interaction.user.id)
        if user["wallet"] < amt:
            return await interaction.response.send_message(
                "Недостаточно средств.", ephemeral=True
            )
        await self.bot.db.update_wallet(interaction.user.id, -amt)
        await self.bot.db.add_to_org_balance(self.org_id, amt)
        org = await self.bot.db.get_organization(self.org_id)
        await interaction.response.send_message(
            f"✅ Переведено **{fmt(amt)}** RUB в бюджет **{org['name']}**.",
            ephemeral=True,
        )


# ══════════════════════════════════════════════════════════════════════
#   УПРАВЛЕНИЕ БЮДЖЕТОМ
# ══════════════════════════════════════════════════════════════════════
class BudgetManageView(discord.ui.View):
    def __init__(self, bot, org_id: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.org_id = org_id

    async def _build_embed(self) -> discord.Embed:
        org = await self.bot.db.get_organization(self.org_id)
        return discord.Embed(
            title="💰 Управление бюджетом",
            description=(
                f"**Организация:** {org['name']}\n"
                f"**Текущий баланс:** {fmt(org['balance'])} RUB"
            ),
            color=0x8B5CF6,
        )

    async def refresh(self, interaction: discord.Interaction):
        embed = await self._build_embed()
        await interaction.edit_original_response(
            content=None,
            embed=embed,
            attachments=[],
            view=BudgetManageView(self.bot, self.org_id),
        )

    @discord.ui.button(label="Добавить", style=discord.ButtonStyle.success, emoji="➕")
    async def add_btn(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(DepositModal(self.bot, self.org_id, self))

    @discord.ui.button(label="Забрать", style=discord.ButtonStyle.danger, emoji="➖")
    async def withdraw_btn(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(WithdrawModal(self.bot, self.org_id, self))

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def back_btn(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.defer()
        org = await self.bot.db.get_organization(self.org_id)
        await render_org_card(i, self.bot, org, edit=True)


# ══════════════════════════════════════════════════════════════════════
#   УПРАВЛЕНИЕ СОТРУДНИКАМИ
# ══════════════════════════════════════════════════════════════════════
class StaffManageView(discord.ui.View):
    def __init__(self, bot, org_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.org_id = org_id

    @discord.ui.button(label="Нанять", style=discord.ButtonStyle.success, emoji="➕")
    async def hire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(HireModal(self.bot, self.org_id))

    @discord.ui.button(label="Список", style=discord.ButtonStyle.secondary, emoji="📋")
    async def list_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        members = await self.bot.db.get_org_members(self.org_id)
        if not members:
            return await interaction.response.send_message(
                "В организации нет сотрудников.", ephemeral=True
            )
        text = "\n".join([f"• <@{m['user_id']}> — {m['rank']}" for m in members])
        await interaction.response.send_message(f"**Сотрудники:**\n{text}", ephemeral=True)


# ══════════════════════════════════════════════════════════════════════
#   ОСНОВНЫЕ КНОПКИ КАРТОЧКИ
# ══════════════════════════════════════════════════════════════════════
class OrgActions(discord.ui.View):
    def __init__(self, bot, org_id: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.org_id = org_id

    @discord.ui.button(label="Бюджет", style=discord.ButtonStyle.primary, emoji="💰")
    async def budget_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await BudgetManageView(self.bot, self.org_id)._build_embed()
        await interaction.edit_original_response(
            content=None,
            embed=embed,
            attachments=[],
            view=BudgetManageView(self.bot, self.org_id),
        )

    @discord.ui.button(label="Настройки", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def edit_org(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or (
            org["owner_id"] != interaction.user.id
            and not interaction.user.guild_permissions.administrator
        ):
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        await interaction.response.send_modal(
            OrgEditModal(self.bot, self.org_id, org["name"], org["logo_url"])
        )

    @discord.ui.button(label="Сотрудники", style=discord.ButtonStyle.secondary, emoji="👥")
    async def staff_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or (
            org["owner_id"] != interaction.user.id
            and not interaction.user.guild_permissions.administrator
        ):
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        await interaction.response.send_message(
            "Управление сотрудниками:",
            view=StaffManageView(self.bot, self.org_id),
            ephemeral=True,
        )


# ══════════════════════════════════════════════════════════════════════
#   РЕНДЕР КАРТОЧКИ
# ══════════════════════════════════════════════════════════════════════
async def build_org_data(bot, org) -> dict:
    owner_user = bot.get_user(org["owner_id"])
    owner_name = owner_user.display_name if owner_user else f"ID: {org['owner_id']}"
    owner_nick = owner_user.name if owner_user else ""
    try:
        founded = org["created_at"].strftime("%Y") if org["created_at"] else "2024"
    except Exception:
        founded = "2024"
    return {
        "name": org["name"],
        "org_type": org["org_type"] or "Бизнес",
        "sphere": org["sphere"] or "Не указана",
        "logo_url": org["logo_url"] or "",
        "balance": fmt(org["balance"]),
        "owner_name": owner_name,
        "owner_nick": owner_nick,
        "founded": founded,
    }


async def render_org_card(interaction: discord.Interaction, bot, org, edit: bool = True):
    data = await build_org_data(bot, org)
    view = OrgActions(bot, org["org_id"])
    try:
        png = await render_template("organization.html", data)
        file = discord.File(fp=io.BytesIO(png), filename="org.png")
        if edit:
            await interaction.edit_original_response(
                content=None, embed=None, attachments=[file], view=view
            )
        else:
            await interaction.followup.send(file=file, view=view, ephemeral=True)
    except Exception as e:
        print(f"❌ ОШИБКА РЕНДЕРА: {e}")
        embed = discord.Embed(
            title=f"🏢 {org['name']}",
            description=f"*{org['sphere']}*",
            color=0x8B5CF6,
        )
        embed.add_field(name="Владелец", value=f"<@{org['owner_id']}>", inline=True)
        embed.add_field(name="Тип", value=org["org_type"], inline=True)
        embed.add_field(name="Бюджет", value=f"{fmt(org['balance'])} RUB", inline=True)
        if edit:
            await interaction.edit_original_response(
                content=None, embed=embed, attachments=[], view=view
            )
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════
#   ВЫБОР ОРГАНИЗАЦИИ (редактирует текущее сообщение!)
# ══════════════════════════════════════════════════════════════════════
class OrgSelectMenu(discord.ui.Select):
    def __init__(self, orgs: list, bot, is_admin_view: bool):
        options = []
        for o in orgs:
            desc = (
                f"Владелец: <@{o['owner_id']}>"
                if is_admin_view
                else f"{o['org_type']}"
            )
            options.append(
                discord.SelectOption(
                    label=o["name"], value=str(o["org_id"]), description=desc
                )
            )
        super().__init__(placeholder="Выберите организацию...", options=options)
        self.bot = bot
        self.is_admin_view = is_admin_view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        org_id = int(self.values[0])
        org = await self.bot.db.get_organization(org_id)
        await render_org_card(interaction, self.bot, org, edit=True)


class OrgSelectView(discord.ui.View):
    def __init__(self, bot, user, is_admin: bool, view_all: bool, orgs: list):
        super().__init__(timeout=180)
        self.bot = bot
        self.user = user
        self.is_admin = is_admin
        self.view_all = view_all
        if orgs:
            self.add_item(OrgSelectMenu(orgs, self.bot, self.is_admin or self.view_all))
        if self.is_admin:
            btn_label = "🏢 Мои организации" if self.view_all else "🌐 Все организации"
            btn_style = (
                discord.ButtonStyle.secondary
                if self.view_all
                else discord.ButtonStyle.primary
            )
            btn = discord.ui.Button(label=btn_label, style=btn_style, row=1)
            btn.callback = self.toggle_view
            self.add_item(btn)

    async def toggle_view(self, interaction: discord.Interaction):
        self.view_all = not self.view_all
        if self.view_all:
            orgs = await self.bot.db.get_all_organizations()
        else:
            orgs = await self.bot.db.get_user_organizations(self.user.id)
        new_view = OrgSelectView(
            self.bot, self.user, self.is_admin, self.view_all, orgs
        )
        await interaction.response.edit_message(view=new_view)


# ══════════════════════════════════════════════════════════════════════
#   COG
# ══════════════════════════════════════════════════════════════════════
class Organization(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="org", description="Меню управления организациями")
    async def org(self, i: discord.Interaction):
        is_admin = (
            i.user.guild_permissions.administrator or i.user.id == i.guild.owner_id
        )
        orgs = await self.bot.db.get_user_organizations(i.user.id)
        if not orgs and not is_admin:
            return await i.response.send_message(
                "У вас нет организаций. Подайте заявку!", ephemeral=True
            )

        await i.response.defer(ephemeral=True)

        if len(orgs) == 1 and not is_admin:
            await render_org_card(i, self.bot, orgs[0], edit=False)
        else:
            view = OrgSelectView(self.bot, i.user, is_admin, view_all=False, orgs=orgs)
            await i.followup.send("Выберите организацию:", view=view, ephemeral=True)

    @app_commands.command(
        name="orgpay", description="Перевести деньги в бюджет своей организации"
    )
    async def orgpay(self, i: discord.Interaction):
        orgs = await self.bot.db.get_user_organizations(i.user.id)
        if not orgs:
            return await i.response.send_message("У вас нет организаций.", ephemeral=True)

        class OrgPaySelect(discord.ui.Select):
            def __init__(self, orgs, bot):
                options = [
                    discord.SelectOption(label=o["name"], value=str(o["org_id"]))
                    for o in orgs
                ]
                super().__init__(placeholder="Выберите организацию...", options=options)
                self.bot = bot

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.send_modal(
                    OrgPayModal(self.bot, int(self.values[0]))
                )

        view = discord.ui.View()
        view.add_item(OrgPaySelect(orgs, self.bot))
        await i.response.send_message(
            "В какую организацию перевести средства?", view=view, ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Organization(bot))