from discord import app_commands

# Shared command groups. Keeping them in one module lets different cogs
# contribute commands without creating dozens of top-level slash commands.
game = app_commands.Group(name="game", description="Игра: деньги, работа, магазин и рынок")
profile = app_commands.Group(name="profile", description="Профиль, паспорт и рейтинг")
admin = app_commands.Group(name="admin", description="Настройка и управление сервером")
