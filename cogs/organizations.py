import io
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path

from storage import storage
from database import db
from utils import organization_image


CAT_LABEL = {
    "ministry": "Министерство",
    "organization": "Организация",
    "company": "Компания",
    "other": "Другое",
}
TYPE_LABEL = {"government": "Государственная", "private": "Частная"}
ROLE_LABEL = {"leader": "👑 Лидер", "officer": "🛡️ Офицер", "member": "👤 Участник"}


def _format_created_at(value) -> str:
    """Безопасно форматирует дату создания в ДД.ММ.ГГГГ."""
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%d.%m.%Y")
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            return ""
    return ""


# ============================================================
# МОДАЛЬНОЕ ОКНО СОЗДАНИЯ
# ============================================================
class CreateOrgModal(discord.ui.Modal, title="Создание организации"):
    name = discord.ui.TextInput(
        label="Название", max_length=60, required=True,
        placeholder="Например: Министерство Обороны",
    )
    short = discord.ui.TextInput(
        label="Короткое название", max_length=12, required=False,
        placeholder="МО",
    )
    description = discord.ui.TextInput(
        label="Описание", style=discord.TextStyle.paragraph,
        max_length=400, required=False, default="—",
    )
    motto = discord.ui.TextInput(
        label="Девиз", max_length=100, required=False,
        placeholder="Например: Служим Отечеству",
    )
    color = discord.ui.TextInput(
        label="HEX-цвет", max_length=7, required=False, default="#1e3a8a",
    )

    def __init__(self, bot, leader: discord.Member, type_: str, category: str):
        super().__init__()
        self.bot = bot
        self.leader = leader
        self.type_ = type_
        self.category = category

    async def on_submit(self, interaction: discord.Interaction):
        color = (self.color.value or "#1e3a8a").strip()
        if not color.startswith("#") or len(color) not in (4, 7):
            color = "#1e3a8a"

        if await db.get_org(self.name.value.strip()):
            return await interaction.response.send_message(
                "❌ Организация с таким названием уже есть.",
                ephemeral=True,
            )

        oid = await db.create_org(
            name=self.name.value.strip(),
            leader_id=self.leader.id,
            type_=self.type_,
            category=self.category,
            description=self.description.value.strip() or "—",
            motto=(self.motto.value or "—").strip() or "—",
            color=color,
            short_name=(self.short.value or "").strip() or None,
            created_by=interaction.user.id,
        )
        embed = discord.Embed(
            title="✅ Организация создана",
            description=(
                f"**{self.name.value}** (#{oid})\n"
                f"Тип: {TYPE_LABEL[self.type_]}\n"
                f"Категория: {CAT_LABEL[self.category]}\n"
                f"Лидер: {self.leader.mention}"
            ),
            color=discord.Color.from_str(color),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        try:
            await self.leader.send(
                f"👑 Вас назначили лидером организации **{self.name.value}**!\n"
                f"Используйте `/org panel` для управления."
            )
        except Exception:
            pass


# ============================================================
# МОДАЛЬНОЕ ОКНО РЕДАКТИРОВАНИЯ
# ============================================================
class EditOrgModal(discord.ui.Modal, title="Изменение организации"):
    name = discord.ui.TextInput(label="Название", max_length=60, required=False)
    short = discord.ui.TextInput(label="Короткое название", max_length=12, required=False)
    description = discord.ui.TextInput(
        label="Описание", style=discord.TextStyle.paragraph,
        max_length=400, required=False,
    )
    motto = discord.ui.TextInput(label="Девиз", max_length=100, required=False)
    color = discord.ui.TextInput(label="HEX-цвет", max_length=7, required=False)

    def __init__(self, org):
        super().__init__()
        self.org = org
        self.name.default = org["name"]
        self.short.default = org["short_name"] or ""
        self.description.default = org["description"] or "—"
        self.motto.default = org["motto"] or "—"
        self.color.default = org["color"] or "#1e3a8a"

    async def on_submit(self, interaction: discord.Interaction):
        fields = {}
        if self.name.value and self.name.value.strip() != self.org["name"]:
            fields["name"] = self.name.value.strip()
        if self.short.value is not None:
            fields["short_name"] = self.short.value.strip() or None
        if self.description.value is not None:
            fields["description"] = self.description.value.strip() or "—"
        if self.motto.value is not None:
            fields["motto"] = self.motto.value.strip() or "—"
        color = (self.color.value or "").strip()
        if color.startswith("#") and len(color) in (4, 7):
            fields["color"] = color
        if fields:
            await db.update_org(self.org["org_id"], **fields)
        await interaction.response.send_message(
            "✅ Организация обновлена.",
            ephemeral=True,
        )


# ============================================================
# МОДАЛЬНОЕ ОКНО ЗАЯВКИ
# ============================================================
class ApplyModal(discord.ui.Modal, title="Заявка на вступление"):
    message = discord.ui.TextInput(
        label="Сопроводительное сообщение",
        style=discord.TextStyle.paragraph,
        max_length=400,
        required=True,
        placeholder="Почему вы хотите вступить? Чем можете быть полезны?",
    )

    def __init__(self, bot, org):
        super().__init__()
        self.bot = bot
        self.org = org

    async def on_submit(self, interaction: discord.Interaction):
        if await db.get_user_org(interaction.user.id):
            return await interaction.response.send_message(
                "❌ Вы уже состоите в организации.",
                ephemeral=True,
            )
        await db.create_org_request(
            self.org["org_id"],
            interaction.user.id,
            self.message.value,
        )
        await interaction.response.send_message(
            "✅ Заявка отправлена. Ожидайте решения лидера.",
            ephemeral=True,
        )
        leader = interaction.guild.get_member(self.org["leader_id"])
        if leader:
            try:
                await leader.send(
                    f"📨 Новая заявка в **{self.org['name']}** от "
                    f"{interaction.user.mention}.\n"
                    f"Проверить: `/org panel`"
                )
            except Exception:
                pass


# ============================================================
# ПАНЕЛЬ УПРАВЛЕНИЯ — View с кнопками
# ============================================================
class OrgPanelView(discord.ui.View):
    def __init__(self, bot, org, is_leader: bool):
        super().__init__(timeout=300)
        self.bot = bot
        self.org = org
        self.is_leader = is_leader
        if not is_leader:
            self.remove_item(self.requests_btn)
            self.remove_item(self.manage_btn)
            self.remove_item(self.edit_btn)
            self.remove_item(self.budget_btn)

    async def _check_leader(self, interaction: discord.Interaction) -> bool:
        org = await db.get_org(self.org["org_id"])
        if not (
            interaction.user.id == org["leader_id"]
            or interaction.user.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                "❌ Только лидер.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Участники", style=discord.ButtonStyle.primary, row=0)
    async def members_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = await db.get_org_members(self.org["org_id"])
        lines = []
        for m in rows:
            user = interaction.guild.get_member(m["user_id"])
            name = user.mention if user else f"ID {m['user_id']}"
            role = ROLE_LABEL.get(m["role"], m["role"])
            sal = f" · {m['salary']:,}" if m["salary"] else ""
            lines.append(f"{role} — {name}{sal}")
        embed = discord.Embed(
            title=f"👥 Состав — {self.org['name']}",
            description="\n".join(lines) or "Пусто",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Заявки", style=discord.ButtonStyle.secondary, row=0)
    async def requests_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_leader(interaction):
            return
        # ... логика заявок ...
        await interaction.response.send_message(
            "Раздел заявок в разработке.",
            ephemeral=True,
        )

    @discord.ui.button(label="Управление", style=discord.ButtonStyle.secondary, row=1)
    async def manage_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_leader(interaction):
            return
        await interaction.response.send_message(
            "Раздел управления в разработке.",
            ephemeral=True,
        )

    @discord.ui.button(label="Редактировать", style=discord.ButtonStyle.secondary, row=1)
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_leader(interaction):
            return
        await interaction.response.send_modal(EditOrgModal(self.org))

    @discord.ui.button(label="Бюджет", style=discord.ButtonStyle.secondary, row=2)
    async def budget_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_leader(interaction):
            return
        await interaction.response.send_message(
            "Раздел бюджета в разработке.",
            ephemeral=True,
        )


# ============================================================
# ОСНОВНОЙ КОГ
# ============================================================
class Organizations(commands.Cog):
    """Организации, партии, выборы."""

    def __init__(self, bot):
        self.bot = bot

    # ... остальные команды кога ...


async def setup(bot):
    await bot.add_cog(Organizations(bot))
