# cogs/decree.py
import io
import html
import discord
from discord import app_commands
from discord.ext import commands


class DecreeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="signature", description="Установить подпись для указов")
    @app_commands.describe(
        url="Ссылка на изображение подписи (PNG/JPG)",
        user="[АДМИН] Установить подпись другому игроку"
    )
    async def signature_set(self, interaction: discord.Interaction, url: str, user: discord.User = None):
        # Если указан другой пользователь, проверяем, что вызывающий — администратор
        if user and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ Только администраторы могут устанавливать подписи другим игрокам.",
                ephemeral=True
            )
        
        target_user = user or interaction.user
        await self.bot.db.set_user_signature(target_user.id, url)
        await interaction.response.send_message(
            f"✅ Подпись для {target_user.mention} успешно сохранена.",
            ephemeral=True
        )

    @app_commands.command(name="decree", description="Создать и опубликовать официальный указ")
    @app_commands.describe(
        act_type="Тип акта (например, УКАЗ, РАСПОРЯЖЕНИЕ)",
        number="Номер акта",
        title="Заголовок (о чём указ)",
        city="Город издания указа",
        position="Должность лица, подписывающего указ",
        content="Содержание указа (если не используете файл)",
        file="Загрузите .txt файл с текстом (заменяет параметр content)"
    )
    # Никаких проверок прав — команду может использовать любой участник
    async def decree_create(
        self,
        interaction: discord.Interaction,
        act_type: str,
        number: str,
        title: str,
        city: str,
        position: str,
        content: str = None,
        file: discord.Attachment = None
    ):
        await interaction.response.defer(thinking=True)

        guild = interaction.guild
        if not guild:
            return await interaction.followup.send("Команда доступна только на сервере.")

        if file:
            if not file.filename.endswith('.txt'):
                return await interaction.followup.send("❌ Поддерживаются только текстовые файлы (.txt).")
            try:
                file_bytes = await file.read()
                content = file_bytes.decode('utf-8')
            except Exception as e:
                return await interaction.followup.send(f"❌ Ошибка чтения файла: {e}")
        elif not content:
            return await interaction.followup.send("❌ Укажите текст указа или прикрепите .txt файл.")

        settings = await self.bot.db.get_guild_settings(guild.id)
        state_name = settings["state_name"] if settings else "ГОСУДАРСТВО"

        await self.bot.db.create_decree(
            guild_id=guild.id,
            act_type=act_type.upper(),
            number=number,
            title=title,
            content=content,
            initiator_id=interaction.user.id
        )

        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        chunks = []
        current = ""
        for p in paragraphs:
            if len(current) + len(p) + 2 > 3800:
                chunks.append(current)
                current = p
            else:
                current += ("\n\n" if current else "") + p
        if current:
            chunks.append(current)

        embeds_to_send = []
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"{act_type.upper()} №{number}" if i == 0 else f"{act_type.upper()} №{number} (продолжение)",
                description=chunk,
                color=0x1A2B4C if i == 0 else 0xF8F9FA
            )
            
            if i == 0:
                embed.set_author(name=state_name)
                embed.add_field(name="🏙 Город", value=city, inline=True)
                embed.add_field(name="👤 Должность", value=position, inline=True)
            
            if i == len(chunks) - 1:
                embed.set_footer(
                    text=f"Инициатор: {interaction.user.display_name}", 
                    icon_url=interaction.user.display_avatar.url
                )

            embeds_to_send.append(embed)

        for i in range(0, len(embeds_to_send), 10):
            await interaction.followup.send(embeds=embeds_to_send[i:i+10])

        rp_name = await self.bot.db.get_user_rp_name(interaction.user.id) or interaction.user.display_name
        signature = await self.bot.db.get_user_signature(interaction.user.id)
        safe_content = "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)

        try:
            from cogs.export import render_html, html_to_image

            html_doc = await render_html(
                template_name="decree.html",
                context={
                    "state_name": state_name,
                    "act_type": act_type.upper(),
                    "number": number,
                    "title": title,
                    "city": city,
                    "content": safe_content,
                    "signature": signature,
                    "fallback_name": rp_name,
                    "rp_name": rp_name,
                    "position": position,
                    "initiator_name": interaction.user.display_name,
                }
            )
            png_bytes = await html_to_image(html_doc)
        except ModuleNotFoundError as e:
            return await interaction.followup.send(f"⚠️ Ошибка зависимостей: `{e.name}`.")
        except Exception as e:
            return await interaction.followup.send(f"⚠️ Ошибка генерации изображения: `{e}`.")

        if not png_bytes:
            return await interaction.followup.send("⚠️ Не удалось сгенерировать изображение указа.")

        image_file = discord.File(io.BytesIO(png_bytes), filename=f"{act_type}_{number}.png")
        await interaction.followup.send(file=image_file)


async def setup(bot):
    await bot.add_cog(DecreeCog(bot))