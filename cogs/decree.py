# cogs/decree.py
import io
import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import is_staff

class DecreeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="signature", description="Установить подпись для указов")
    @app_commands.describe(url="Ссылка на изображение подписи (PNG/JPG)")
    async def signature_set(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.set_user_signature(interaction.user.id, url)
        await interaction.followup.send("✅ Подпись успешно сохранена.", ephemeral=True)

    @app_commands.command(name="decree", description="Создать официальный указ")
    @app_commands.describe(
        act_type="Тип акта (например, УКАЗ, РАСПОРЯЖЕНИЕ)",
        number="Номер акта",
        title="Заголовок (о чём указ)",
        content="Содержание указа (абзацы разделяйте пустой строкой)"
    )
    @is_staff()
    async def decree_create(
        self,
        interaction: discord.Interaction,
        act_type: str,
        number: str,
        title: str,
        content: str
    ):
        await interaction.response.defer(thinking=True)

        guild = interaction.guild
        if not guild:
            return await interaction.followup.send("Команда доступна только на сервере.")

        # 1. Получаем настройки государства из БД
        settings = await self.bot.db.get_guild_settings(guild.id)
        state_name = settings["state_name"] if settings else "ГОСУДАРСТВО"

        # 2. Сохраняем указ в БД
        await self.bot.db.create_decree(
            guild_id=guild.id,
            act_type=act_type.upper(),
            number=number,
            title=title,
            content=content,
            initiator_id=interaction.user.id
        )

        # 3. Разбиваем контент на части для Discord
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        chunks = []
        current = ""
        for p in paragraphs:
            if len(current) + len(p) + 2 > 3800:  # запас под лимит 4096
                chunks.append(current)
                current = p
            else:
                current += ("\n\n" if current else "") + p
        if current:
            chunks.append(current)

        # 4. Отправляем embed-сообщения
        embeds_to_send = []
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"{act_type.upper()} №{number}" if i == 0 else f"{act_type.upper()} №{number} (продолжение)",
                description=chunk,
                color=0x1A2B4C if i == 0 else 0xFFFFFF  # первый тёмно-синий, остальные белые
            )
            embeds_to_send.append(embed)

        for i in range(0, len(embeds_to_send), 10):
            await interaction.followup.send(embeds=embeds_to_send[i:i+10])

        # 5. Подготовка данных для PDF
        rp_name = await self.bot.db.get_user_rp_name(interaction.user.id) or interaction.user.display_name
        signature = await self.bot.db.get_user_signature(interaction.user.id)

        safe_content = "".join(
            f"<p>{discord.utils.escape_html(p)}</p>" for p in paragraphs
        )

        # 6. Рендерим PDF
        from cogs.export import render_pdf
        try:
            pdf_bytes = await render_pdf(
                template_name="decree.html",
                context={
                    "state_name": state_name,
                    "act_type": act_type.upper(),
                    "number": number,
                    "title": title,
                    "content": safe_content,
                    "signature": signature,
                    "fallback_name": rp_name,
                    "rp_name": rp_name,
                    "initiator_name": interaction.user.display_name,
                }
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ Ошибка при создании PDF: {e}")

        # 7. Отправляем PDF отдельным сообщением
        file = discord.File(io.BytesIO(pdf_bytes), filename=f"{act_type}_{number}.pdf")
        await interaction.followup.send(
            content=f"**Инициатор:** {interaction.user.mention}",
            file=file
        )

async def setup(bot):
    await bot.add_cog(DecreeCog(bot))