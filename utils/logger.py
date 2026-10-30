# utils/logger.py
import discord


async def send_log(bot, guild_id: int, embed: discord.Embed):
    """Отправляет лог-эмбед в канал, настроенный в /setup."""
    if not guild_id:
        return
    settings = await bot.db.get_guild_settings(guild_id)
    if not settings:
        return
    try:
        log_channel_id = settings["log_channel_id"]
    except (KeyError, TypeError, IndexError):
        return
    if not log_channel_id:
        return
    channel = bot.get_channel(log_channel_id)
    if channel is None:
        return
    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass