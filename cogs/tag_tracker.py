import discord
from discord.ext import commands


class TagTracker(commands.Cog):
    """HRN tag takibi yapan cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hydrabon_guild_id = 1029088146752815138  # HydRaboN sunucu ID'si
        self.tag_role_id = 1467145841830789367  # Verilecek rol ID'si

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        """Kullanıcının tag bilgisi değiştiğinde tetiklenir."""

        # primary_guild değişikliğini kontrol et
        before_guild = getattr(before, 'primary_guild', None)
        after_guild = getattr(after, 'primary_guild', None)
        
        # Eğer değişiklik yoksa işlem yapma
        if before_guild == after_guild:
            return
        
        # HydRaboN sunucusunu al
        guild = self.bot.get_guild(self.hydrabon_guild_id)
        if guild is None:
            return
        
        # Rolü al
        role = guild.get_role(self.tag_role_id)
        if role is None:
            return
        
        # Kullanıcıyı sunucuda bul (member olarak)
        member = guild.get_member(after.id)
        if member is None:
            return
        
        # After durumunu kontrol et
        after_guild_id = getattr(after_guild, 'id', None) if after_guild else None
        
        # Eğer HydRaboN tag'ı varsa (guild id eşleşiyor ve tag HRN)
        if after_guild_id == self.hydrabon_guild_id:
            # Rol yoksa ekle
            if role not in member.roles:
                try:
                    await member.add_roles(role, reason="HRN tag'ı aldı")
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass
        else:
            # Tag yok, farklı sunucunun tag'ı var veya tag değişmiş - rolü al
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason="HRN tag'ını bıraktı veya değiştirdi")
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(TagTracker(bot))
