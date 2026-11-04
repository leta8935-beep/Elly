# cogs/export.py
import io
import re
from datetime import datetime
from html import escape
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import is_staff

# ─── Цвета ───
AVATAR_GRADIENTS = [
    ("#5865f2", "#eb459e"), ("#f0b232", "#f23f43"),
    ("#23a55a", "#06b6d4"), ("#8b5cf6", "#00a8fc"),
    ("#f97316", "#eb459e"), ("#10b981", "#3b82f6"),
    ("#eab308", "#ef4444"), ("#8b5cf6", "#ec4899"),
    ("#06b6d4", "#8b5cf6"), ("#10b981", "#f59e0b"),
]
USERNAME_COLORS = [
    "#c9cdfb", "#f0b232", "#a3e2c0", "#f4b8b8", "#b8d4f4",
    "#d4b8f4", "#f4d4b8", "#b8f4d4", "#f4b8d4", "#d4f4b8",
]

def get_avatar_gradient(user_id: int) -> str:
    c = AVATAR_GRADIENTS[user_id % len(AVATAR_GRADIENTS)]
    return f"linear-gradient(135deg, {c[0]}, {c[1]})"

def get_username_color(user_id: int) -> str:
    return USERNAME_COLORS[user_id % len(USERNAME_COLORS)]

# ─── Форматирование ───
def fmt_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")

def fmt_date(dt: datetime) -> str:
    months = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    return f"{dt.day} {months[dt.month - 1]} {dt.year} г."

def process_content(message: discord.Message) -> str:
    text = escape(message.content or "")

    def resolve_user(m):
        uid = int(m.group(1))
        member = message.guild.get_member(uid) if message.guild else None
        name = member.display_name if member else f"user#{uid}"
        return f'@{escape(name)}'

    text = re.sub(r"<@!?(\d+)>", resolve_user, text)

    def resolve_channel(m):
        cid = int(m.group(1))
        ch = message.guild.get_channel(cid) if message.guild else None
        name = ch.name if ch else f"channel#{cid}"
        return f'#{escape(name)}'

    text = re.sub(r"<#(\d+)>", resolve_channel, text)

    def resolve_role(m):
        rid = int(m.group(1))
        role = message.guild.get_role(rid) if message.guild else None
        name = role.name if role else f"role#{rid}"
        return f'@{escape(name)}'

    text = re.sub(r"<@&(\d+)>", resolve_role, text)
    text = re.sub(r"<(a?):([a-zA-Z0-9_]+):(\d+)>", lambda m: "[Image 0]", text)
    text = re.sub(r"```(?:\w+)?\n?(.+?)```", r"<pre>\1</pre>", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', text)
    return text

def process_attachments(message: discord.Message) -> str:
    if not message.attachments:
        return ""
    parts = []
    for att in message.attachments:
        if att.content_type and att.content_type.startswith("image/"):
            parts.append(f'<div class="attachment-image"><img src="{att.url}" /></div>')
        else:
            parts.append(f'<div class="attachment-file">📎 <a href="{att.url}">{escape(att.filename)}</a></div>')
    return "".join(parts)

def process_embed(embed: discord.Embed) -> str:
    color = f"#{embed.color.value:06x}" if embed.color else "#4e5058"
    parts = [f'<div class="embed" style="border-left: 4px solid {color};">']
    if embed.author and embed.author.name:
        parts.append(f'<div class="embed-author">{escape(embed.author.name)}</div>')
    if embed.title:
        parts.append(f'<div class="embed-title">{escape(embed.title)}</div>')
    if embed.description:
        parts.append(f'<div class="embed-description">{escape(embed.description).replace(chr(10), "<br>")}</div>')
    for field in embed.fields:
        parts.append(f'<div class="embed-field"><div class="embed-field-name">{escape(field.name)}</div><div class="embed-field-value">{escape(field.value).replace(chr(10), "<br>")}</div></div>')
    if embed.image and embed.image.url:
        parts.append(f'<img class="embed-image" src="{embed.image.url}" />')
    if embed.thumbnail and embed.thumbnail.url:
        parts.append(f'<img class="embed-thumbnail" src="{embed.thumbnail.url}" />')
    if embed.footer and embed.footer.text:
        parts.append(f'<div class="embed-footer">{escape(embed.footer.text)}</div>')
    parts.append("</div>")
    return "".join(parts)

def process_reactions(message: discord.Message) -> str:
    if not message.reactions:
        return ""
    parts = []
    for r in message.reactions:
        emoji = str(r.emoji)
        if r.custom_emoji:
            emoji = f'<img class="reaction-emoji" src="{r.emoji.url}" />'
        parts.append(f'{emoji} {r.count}')
    return f'<div class="reactions">{" ".join(parts)}</div>'

def message_html(message: discord.Message, is_first: bool) -> str:
    author = message.author
    uid = author.id
    uname = escape(author.display_name)
    color = get_username_color(uid)
    gradient = get_avatar_gradient(uid)
    initial = escape((author.display_name or "?")[0].upper())

    if author.display_avatar:
        avatar_html = f'<img class="avatar" src="{author.display_avatar.url}" />'
    else:
        avatar_html = f'<div class="avatar" style="background: {gradient};">{initial}</div>'

    reply_html = ""
    if message.reference and isinstance(message.reference.resolved, discord.Message):
        ref = message.reference.resolved
        ref_author = escape(ref.author.display_name)
        ref_text = escape((ref.content or "*вложение*")[:120])
        reply_html = f'<div class="reply"><span class="reply-author">{ref_author}</span> {ref_text}</div>'

    body = process_content(message)
    body += process_attachments(message)
    for emb in message.embeds:
        body += process_embed(emb)
    body += process_reactions(message)

    if not body.strip():
        body = '<div class="empty-message">пустое сообщение</div>'
    else:
        body = f'<div class="message-content">{body}</div>'

    bot_tag = '<span class="bot-tag">bot</span>' if author.bot else ""

    if is_first:
        return f'''
        <div class="message first">
            {avatar_html}
            <div class="message-body">
                {reply_html}
                <div class="message-header">
                    <span class="username" style="color: {color};">{uname}</span>
                    {bot_tag}
                    <span class="timestamp">{fmt_time(message.created_at)}</span>
                </div>
                {body}
            </div>
        </div>'''
    else:
        return f'''
        <div class="message">
            <div class="message-body">
                <div class="message-header">
                    <span class="timestamp">{fmt_time(message.created_at)}</span>
                </div>
                {body}
            </div>
        </div>'''

def build_html(messages: list, channel_name: str) -> str:
    template_path = Path(__file__).parent.parent / "templates" / "chat_export.html"
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    chunks = []
    prev = None
    prev_date = None

    for msg in messages:
        d = msg.created_at.date()
        if prev_date != d:
            chunks.append(f'<div class="date-separator">{fmt_date(msg.created_at)}</div>')
            prev_date = d
            prev = None

        is_grouped = (
            prev is not None
            and prev.author.id == msg.author.id
            and (msg.created_at - prev.created_at).total_seconds() < 300
            and not msg.reference
            and not prev.reference
        )
        chunks.append(message_html(msg, is_first=not is_grouped))
        prev = msg

    html = template.replace("%%CHANNEL_NAME%%", escape(channel_name))
    html = html.replace("%%MESSAGES%%", "\n".join(chunks))
    return html

async def html_to_pdf(html: str) -> bytes | None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ playwright не установлен — PDF пропущен")
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content(html, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            pdf = await page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
                scale=0.8,
            )
            await browser.close()
            return pdf
    except Exception as e:
        print(f"❌ PDF error: {e}")
        return None

async def html_to_image(html: str) -> bytes | None:
    """Рендерит HTML в PNG-изображение, вырезая только блок .a4-page."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ playwright не установлен — изображение пропущено")
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            # Устанавливаем вьюпорт под размер А4 (при 96 DPI это ~794x1123)
            # device_scale_factor=2 делает картинку в 2 раза четче
            page = await browser.new_page(viewport={"width": 800, "height": 1150}, device_scale_factor=2)
            await page.set_content(html, wait_until="networkidle")
            
            # Ждем загрузку шрифтов
            await page.wait_for_timeout(1000)
            
            # Ищем наш лист А4 и делаем скриншот ТОЛЬКО его
            element = await page.query_selector('.a4-page')
            if element:
                png = await element.screenshot(type="png")
            else:
                # Если класс не найден, делаем обычный скриншот (запасной вариант)
                png = await page.screenshot(full_page=True, type="png")
                
            await browser.close()
            return png
    except Exception as e:
        print(f"❌ Screenshot error: {e}")
        return None

async def render_html(template_name: str, context: dict) -> str:
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template(template_name)
    return template.render(**context)

class ChatExport(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="export",
        description="[STAFF] Экспортировать чат в HTML и PDF (в ЛС)",
    )
    @app_commands.describe(
        channel="Канал для экспорта (по умолчанию — текущий)",
        limit="Ограничить количество сообщений (0 = все)",
    )
    @is_staff()
    async def export_cmd(
        self,
        i: discord.Interaction,
        channel: discord.TextChannel = None,
        limit: int = 0,
    ):
        target = channel or i.channel
        if not isinstance(target, discord.TextChannel):
            return await i.response.send_message(
                "❌ Можно экспортировать только текстовые каналы.",
                ephemeral=True
            )
        await i.response.defer(ephemeral=True)

        messages = []
        try:
            async for msg in target.history(
                limit=limit or None,
                oldest_first=True,
                before=i.created_at,
            ):
                messages.append(msg)
                if len(messages) % 500 == 0:
                    await i.edit_original_response(
                        content=f"Загружено {len(messages)} сообщений..."
                    )
        except discord.Forbidden:
            return await i.edit_original_response(
                content="❌ Нет доступа к истории этого канала."
            )
        except Exception as e:
            return await i.edit_original_response(
                content=f"❌ Ошибка загрузки: `{e}`"
            )

        if not messages:
            return await i.edit_original_response(content="❌ Канал пуст.")

        await i.edit_original_response(
            content=f"Генерирую HTML ({len(messages)} сообщений)..."
        )
        html = build_html(messages, target.name)
        html_bytes = html.encode("utf-8")
        stamp = i.created_at.strftime("%Y%m%d_%H%M")
        html_file = discord.File(
            io.BytesIO(html_bytes),
            filename=f"chat_{target.name}_{stamp}.html",
        )

        pdf_bytes = await html_to_pdf(html)
        pdf_file = None
        if pdf_bytes:
            pdf_file = discord.File(
                io.BytesIO(pdf_bytes),
                filename=f"chat_{target.name}_{stamp}.pdf",
            )

        try:
            dm = await i.user.create_dm()
            await dm.send(
                f"**Экспорт канала #{target.name}**\n"
                f"Сообщений: **{len(messages)}**",
                file=html_file,
            )
            if pdf_file:
                await dm.send(file=pdf_file)
            await i.edit_original_response(
                content="✅ Экспорт отправлен вам в личные сообщения."
            )
        except discord.Forbidden:
            await i.edit_original_response(
                content="❌ Не удалось отправить в ЛС. Откройте личные сообщения."
            )

async def setup(bot):
    await bot.add_cog(ChatExport(bot))