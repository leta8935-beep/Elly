import discord
from discord import app_commands

def is_staff():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild: return False
        if interaction.user.id == interaction.guild.owner_id: return True
        if interaction.user.guild_permissions.administrator: return True
        settings = await interaction.client.db.get_guild_settings(interaction.guild.id)
        if settings and settings["manager_id"] == interaction.user.id: return True
        raise app_commands.CheckFailure("Нет прав.")
    return app_commands.check(predicate)