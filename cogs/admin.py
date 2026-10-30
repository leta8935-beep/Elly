# cogs/admin.py
import discord
from discord.ext import commands
from discord import app_commands
from utils.checks import is_staff
from utils.logger import send_log


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


# ─── Модалки бюджета ───
class AdminOrgModal(discord.ui.Modal):
    amount = discord.ui.TextInput(label="Сумма", placeholder="1000", max_length=12)

    def __init__(self, bot, org_id: int, action: str):
        super().__init__(title="Управление бюджетом организации")
        self.bot = bot
        self.org_id = org_id
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message(
                "Введите число.", ephemeral=True
            )

        org = await self.bot.db.get_organization(self.org_id)
        if not org:
            return await interaction.response.send_message(
                "Организация не найдена.", ephemeral=True
            )

        if self.action == "add":
            await self.bot.db.add_to_org_balance(self.org_id, amt)
            msg = f"✅ Добавлено {fmt(amt)} в бюджет."
        elif self.action == "remove":
            await self.bot.db.add_to_org_balance(self.org_id, -amt)
            msg = f"✅ Убрано {fmt(amt)} из бюджета."
        else:
            await self.bot.db.update_organization(self.org_id, balance=amt)
            msg = f"✅ Бюджет изменён на {fmt(amt)}."

        await interaction.response.send_message(msg, ephemeral=True)

        log_embed = discord.Embed(
            title="💰 Изменение бюджета организации",
            color=0xEB459E,
            description=(
                f"**Администратор:** {interaction.user.mention}\n"
                f"**Организация:** {org['name']} (`{org['org_id']}`)\n"
                f"**Действие:** {self.action}\n"
                f"**Сумма:** {fmt(amt)}"
            ),
        )
        await send_log(self.bot, interaction.guild_id, log_embed)


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
        options = [
            discord.SelectOption(
                label=o["name"],
                value=str(o["org_id"]),
                description=f"Владелец: {o['owner_id']}",
            )
            for o in orgs
        ]
        super().__init__(placeholder="Выберите организацию...", options=options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        org_id = int(self.values[0])
        await interaction.response.send_message(
            "Выберите действие с бюджетом:",
            view=AdminOrgActionView(self.bot, org_id),
            ephemeral=True,
        )


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, bot, org_id, org_name):
        super().__init__(timeout=60)
        self.bot = bot
        self.org_id = org_id
        self.org_name = org_name

    @discord.ui.button(label="Да, удалить", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.bot.db.delete_organization(self.org_id)
        await interaction.response.edit_message(
            content=f"🗑️ Организация **{self.org_name}** успешно удалена.", view=None
        )
        log_embed = discord.Embed(
            title="🗑️ Удаление организации",
            color=0xEB459E,
            description=(
                f"**Администратор:** {interaction.user.mention}\n"
                f"**Организация:** {self.org_name} (`{self.org_id}`)"
            ),
        )
        await send_log(self.bot, interaction.guild_id, log_embed)

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Удаление отменено.", view=None)


class DeleteOrgSelect(discord.ui.Select):
    def __init__(self, bot, orgs):
        options = [
            discord.SelectOption(label=o["name"], value=str(o["org_id"]))
            for o in orgs
        ]
        super().__init__(placeholder="Выберите организацию для удаления...", options=options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        org_id = int(self.values[0])
        org_name = next(
            (o.label for o in self.options if o.value == self.values[0]), "Неизвестно"
        )
        await interaction.response.edit_message(
            content=f"⚠️ Вы уверены, что хотите удалить **{org_name}**?",
            view=ConfirmDeleteView(self.bot, org_id, org_name),
        )


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ✅ /addmon — бывшая economy_admin
    @app_commands.command(
        name="addmon", description="[STAFF] Управление балансом игроков"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="➕ Добавить", value="add"),
            app_commands.Choice(name="➖ Убрать", value="remove"),
            app_commands.Choice(name="🔄 Обновить", value="update"),
        ]
    )
    @is_staff()
    async def addmon(
        self,
        i: discord.Interaction,
        action: app_commands.Choice[str],
        member: discord.Member,
        amount: int,
    ):
        if amount < 0:
            return await i.response.send_message("❌ Сумма > 0.", ephemeral=True)

        await self.bot.db.get_user(member.id)

        if action.value == "add":
            await self.bot.db.update_wallet(member.id, amount)
        elif action.value == "remove":
            await self.bot.db.update_wallet(member.id, -amount)
        else:
            await self.bot.db.set_wallet(member.id, amount)

        u = await self.bot.db.get_user(member.id)
        embed = discord.Embed(
            title="💰 Баланс изменён",
            color=0xEB459E,
            description=f"**Игрок:** {member.mention}\n**Новый баланс:** {fmt(u['wallet'])}",
        )
        await i.response.send_message(embed=embed, ephemeral=True)

        log_embed = discord.Embed(
            title="💳 Изменение баланса игрока",
            color=0xEB459E,
            description=(
                f"**Администратор:** {i.user.mention}\n"
                f"**Игрок:** {member.mention} (`{member.id}`)\n"
                f"**Действие:** {action.name}\n"
                f"**Сумма:** {fmt(amount)}\n"
                f"**Новый баланс:** {fmt(u['wallet'])}"
            ),
        )
        await send_log(self.bot, i.guild_id, log_embed)

    # ✅ /addmonorg — бывшая admin_org
    @app_commands.command(
        name="addmonorg", description="[STAFF] Управление бюджетами организаций"
    )
    @is_staff()
    async def addmonorg(self, i: discord.Interaction):
        orgs = await self.bot.db.get_all_organizations()
        if not orgs:
            return await i.response.send_message(
                "На сервере нет организаций.", ephemeral=True
            )
        view = discord.ui.View()
        view.add_item(AdminOrgSelect(self.bot, orgs))
        await i.response.send_message(
            "Выберите организацию для управления бюджетом:", view=view, ephemeral=True
        )

    @app_commands.command(name="delete_org", description="[STAFF] Удалить организацию")
    @is_staff()
    async def delete_org(self, i: discord.Interaction):
        orgs = await self.bot.db.get_all_organizations()
        if not orgs:
            return await i.response.send_message(
                "На сервере нет организаций.", ephemeral=True
            )
        view = discord.ui.View()
        view.add_item(DeleteOrgSelect(self.bot, orgs))
        await i.response.send_message(
            "Выберите организацию, которую хотите удалить:", view=view, ephemeral=True
        )

    @app_commands.command(
        name="create_org", description="[STAFF] Создать организацию для игрока"
    )
    @is_staff()
    async def create_org(
        self,
        i: discord.Interaction,
        member: discord.Member,
        name: str,
        org_type: str = "Бизнес",
        initial_balance: int = 0,
    ):
        await self.bot.db.create_organization(
            member.id, name, org_type, "Не указана", "", initial_balance
        )
        await i.response.send_message(
            f"✅ Организация **{name}** создана для {member.mention} "
            f"с бюджетом {fmt(initial_balance)}!",
            ephemeral=True,
        )
        log_embed = discord.Embed(
            title="🏢 Создание организации",
            color=0xEB459E,
            description=(
                f"**Администратор:** {i.user.mention}\n"
                f"**Владелец:** {member.mention} (`{member.id}`)\n"
                f"**Название:** {name}\n"
                f"**Стартовый бюджет:** {fmt(initial_balance)}"
            ),
        )
        await send_log(self.bot, i.guild_id, log_embed)

    @app_commands.command(name="purge", description="[STAFF] Очистить сообщения")
    @is_staff()
    async def purge(self, i: discord.Interaction, amount: int):
        if not (1 <= amount <= 100):
            return await i.response.send_message("1..100", ephemeral=True)
        await i.response.defer(ephemeral=True)
        deleted = await i.channel.purge(limit=amount)
        await i.followup.send(f"🧹 Удалено {len(deleted)} сообщений.", ephemeral=True)

    async def cog_app_command_error(self, i, error):
        if isinstance(error, app_commands.CheckFailure):
            await i.response.send_message(f"⛔ {error}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))