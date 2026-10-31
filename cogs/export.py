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
    """Конвертирует текст сообщения в HTML."""
    text = escape(message.content or "")

    # Упоминания пользователей
    def resolve_user(m):
        uid = int(m.group(1))
        member = message.guild.get_member(uid) if message.guild else None
        name = member.display_name if member else f"user#{uid}"
        return f'<span class="mention">@{escape(name)}</span>'
    text = re.sub(r"&lt;@!?(\d+)&gt;", resolve_user, text)

    # Упоминания каналов
    def resolve_channel(m):
        cid = int(m.group(1))
        ch = message.guild.get_channel(cid) if message.guild else None
        name = ch.name if ch else f"channel#{cid}"
        return f'<span class="mention">#{escape(name)}</span>'
    text = re.sub(r"&lt;#(\d+)&gt;", resolve_channel, text)

    # Упоминания ролей
    def resolve_role(m):
        rid = int(m.group(1))
        role = message.guild.get_role(rid) if message.guild else None
        name = role.name if role else f"role#{rid}"
        return f'<span class="mention">@{escape(name)}</span>'
    text = re.sub(r"&lt;@&amp;(\d+)&gt;", resolve_role, text)

    # Кастомные эмодзи
    text = re.sub(
        r"&lt;(a?):([a-zA-Z0-9_]+):(\d+)&gt;",
        lambda m: (
            f'<img class="emoji" src="https://cdn.discordapp.com/emojis/'
            f'{m.group(3)}.{"gif" if m.group(1) == "a" else "png"}" '
            f'alt="{escape(m.group(2))}">'
        ),
        text,
    )

    # Код-блоки
    text = re.sub(
        r"```(?:\w+)?\n?(.+?)```",
        r'<pre class="code-block"><code>\1</code></pre>',
        text, flags=re.DOTALL,
    )
    # Инлайн-код
    text = re.sub(r"`([^`]+)`", r'<span class="code">\1</span>', text)
    # Жирный
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Курсив
    text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", text)
    # Подчёркнутый
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text)
    # Зачёркнутый
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    # Ссылки
    text = re.sub(r"(https?://[^\s<]+)", r'<a class="link" href="\1">\1</a>', text)

    return text


def process_attachments(message: discord.Message) -> str:
    if not message.attachments:
        return ""
    parts = []
    for att in message.attachments:
        if att.content_type and att.content_type.startswith("image/"):
            parts.append(
                f'<div class="attachment"><img src="{escape(att.url)}" '
                f'alt="attachment" loading="lazy"></div>'
            )
        else:
            parts.append(
                f'<div class="attachment">📎 <a class="link" href="{escape(att.url)}">'
                f'{escape(att.filename)}</a></div>'
            )
    return "".join(parts)


def process_embed(embed: discord.Embed) -> str:
    color = f"#{embed.color.value:06x}" if embed.color else "#4e5058"
    parts = [f'<div class="embed" style="border-left-color: {color};">']
    if embed.author and embed.author.name:
        parts.append(f'<div class="embed-author">{escape(embed.author.name)}</div>')
    if embed.title:
        parts.append(f'<div class="embed-title">{escape(embed.title)}</div>')
    if embed.description:
        parts.append(
            f'<div class="embed-desc">'
            f'{escape(embed.description).replace(chr(10), "<br>")}</div>'
        )
    for field in embed.fields:
        parts.append(
            f'<div class="embed-field">'
            f'<div class="embed-field-name">{escape(field.name)}</div>'
            f'<div class="embed-field-value">'
            f'{escape(field.value).replace(chr(10), "<br>")}</div></div>'
        )
    if embed.image and embed.image.url:
        parts.append(f'<img class="embed-image" src="{escape(embed.image.url)}" alt="">')
    if embed.thumbnail and embed.thumbnail.url:
        parts.append(f'<img class="embed-thumb" src="{escape(embed.thumbnail.url)}" alt="">')
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
        # Кастомные эмодзи в реакциях
        if r.custom_emoji:
            emoji = (
                f'<img class="emoji" src="{r.custom_emoji.url}" '
                f'alt="{escape(r.custom_emoji.name)}">'
            )
        parts.append(f'<span class="reaction">{emoji} {r.count}</span>')
    return f'<div class="reactions">{" ".join(parts)}</div>'


def message_html(message: discord.Message, is_first: bool) -> str:
    author = message.author
    uid = author.id
    uname = escape(author.display_name)
    color = get_username_color(uid)
    gradient = get_avatar_gradient(uid)
    initial = escape((author.display_name or "?")[0].upper())

    # Avatar
    if author.display_avatar:
        avatar_html = (
            f'<div class="avatar"><img src="{escape(author.display_avatar.url)}" '
            f'alt="avatar"></div>'
        )
    else:
        avatar_html = f'<div class="avatar" style="background: {gradient};">{initial}</div>'

    # Reply
    reply_html = ""
    if message.reference and isinstance(message.reference.resolved, discord.Message):
        ref = message.reference.resolved
        ref_author = escape(ref.author.display_name)
        ref_text = escape((ref.content or "*вложение*")[:120])
        reply_html = (
            f'<div class="reply"><span class="r-author">{ref_author}</span> '
            f'<span>{ref_text}</span></div>'
        )

    # Содержимое
    body = process_content(message)
    body += process_attachments(message)
    for emb in message.embeds:
        body += process_embed(emb)
    body += process_reactions(message)

    if not body.strip():
        body = '<div class="text"><em style="color:#4e5058">пустое сообщение</em></div>'
    else:
        body = f'<div class="text">{body}</div>'

    bot_tag = '<span class="bot-tag">bot</span>' if author.bot else ""

    if is_first:
        return f'''
  <div class="message first">
    {avatar_html}
    <div class="content">
      {reply_html}
      <div class="header">
        <span class="username" style="color:{color}">{uname}</span>
        {bot_tag}
        <span class="timestamp">{fmt_time(message.created_at)}</span>
      </div>
      {body}
    </div>
  </div>'''
    return f'''
  <div class="message grouped">
    <span class="hover-time">{fmt_time(message.created_at)}</span>
    <div class="content">
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
        # Разделитель даты
        d = msg.created_at.date()
        if prev_date != d:
            chunks.append(f'<div class="divider">{fmt_date(msg.created_at)}</div>')
            prev_date = d
            prev = None

        # Группировка (тот же автор + <5 мин + не reply)
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
            await page.wait_for_timeout(2000)  # подождать картинки
            pdf = await page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "10mm", "bottom": "10mm",
                        "left": "10mm", "right": "10mm"},
                scale=0.8,
            )
            await browser.close()
            return pdf
    except Exception as e:
        print(f"❌ PDF error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════
#   COG
# ══════════════════════════════════════════════════════════════════════
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
                "❌ Можно экспортировать только текстовые каналы.", ephemeral=True
            )

        await i.response.defer(ephemeral=True)

        # ─── Загрузка ───
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
                        content=f"📥 Загружено {len(messages)} сообщений..."
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

        # ─── HTML ───
        await i.edit_original_response(
            content=f"📄 Генерирую HTML ({len(messages)} сообщений)..."
        )
        html = build_html(messages, target.name)
        html_bytes = html.encode("utf-8")
        stamp = i.created_at.strftime("%Y%m%d_%H%M")
        html_file = discord.File(
            io.BytesIO(html_bytes),
            filename=f"chat_{target.name}_{stamp}.html",
        )

        # ─── PDF ───
        await i.edit_original_response(content="📄 Генерирую PDF (может занять время)...")
        pdf_bytes = await html_to_pdf(html)
        pdf_file = None
        if pdf_bytes:
            pdf_file = discord.File(
                io.BytesIO(pdf_bytes),
                filename=f"chat_{target.name}_{stamp}.pdf",
            )

        # ─── Отправка в ЛС ───
        try:
            dm = await i.user.create_dm()
            await dm.send(
                f"📦 **Экспорт канала #{target.name}**\n"
                f"Сообщений: **{len(messages)}**",
                file=html_file,
            )
            if pdf_file:
                await dm.send("📄 PDF-версия:", file=pdf_file)
            else:
                await dm.send(
                    "⚠️ PDF не сгенерирован (playwright недоступен). "
                    "Используйте HTML-версию."
                )

            await i.edit_original_response(
                content=f"✅ Экспорт отправлен в ЛС ({len(messages)} сообщений)."
            )
        except discord.Forbidden:
            await i.edit_original_response(
                content="❌ Не могу отправить в ЛС — включите личные сообщения."
            )
        except discord.HTTPException as e:
            await i.edit_original_response(
                content=f"❌ Ошибка отправки: файл слишком большой? `{e}`"
            )


async def setup(bot):
    await bot.add_cog(ChatExport(bot))