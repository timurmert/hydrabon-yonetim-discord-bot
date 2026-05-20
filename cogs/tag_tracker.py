import discord
import logging
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)


class TagTracker(commands.Cog):
    """HRN tag takibi yapan cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hydrabon_guild_id = 1029088146752815138
        self.tag_role_id = 1467145841830789367
        self.periodic_sync.start()

    def cog_unload(self):
        self.periodic_sync.cancel()

    def _primary_guild_id(self, user: discord.User | discord.Member) -> int | None:
        pg = getattr(user, 'primary_guild', None)
        return getattr(pg, 'id', None) if pg is not None else None

    async def _fetch_member(self, guild: discord.Guild, user_id: int) -> discord.Member | None:
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except (discord.NotFound, discord.HTTPException):
                return None
        return member

    async def _sync_member_role(
        self,
        member: discord.Member,
        role: discord.Role,
        has_tag: bool,
    ) -> None:
        if has_tag and role not in member.roles:
            try:
                await member.add_roles(role, reason="HRN tag'ı aldı")
                logger.info("TagTracker: %s kullanıcısına HRN tag rolü verildi.", member)
            except discord.Forbidden:
                logger.warning("TagTracker: %s için rol verme yetkisi yok.", member)
            except discord.HTTPException as e:
                logger.error("TagTracker: Rol verme hatası (%s): %s", member, e)
        elif not has_tag and role in member.roles:
            try:
                await member.remove_roles(role, reason="HRN tag'ını bıraktı veya değiştirdi")
                logger.info("TagTracker: %s kullanıcısından HRN tag rolü alındı.", member)
            except discord.Forbidden:
                logger.warning("TagTracker: %s için rol alma yetkisi yok.", member)
            except discord.HTTPException as e:
                logger.error("TagTracker: Rol alma hatası (%s): %s", member, e)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        """Kullanıcının tag bilgisi değiştiğinde tetiklenir."""
        before_pg_id = self._primary_guild_id(before)
        after_pg_id = self._primary_guild_id(after)

        if before_pg_id == after_pg_id:
            return

        guild = self.bot.get_guild(self.hydrabon_guild_id)
        if guild is None:
            return

        role = guild.get_role(self.tag_role_id)
        if role is None:
            logger.warning("TagTracker: Rol bulunamadı (ID: %s)", self.tag_role_id)
            return

        member = await self._fetch_member(guild, after.id)
        if member is None:
            return

        has_tag = after_pg_id == self.hydrabon_guild_id
        await self._sync_member_role(member, role, has_tag)

    @tasks.loop(minutes=30)
    async def periodic_sync(self):
        """Her 30 dakikada bir tüm üyelerin tag durumunu kontrol eder."""
        guild = self.bot.get_guild(self.hydrabon_guild_id)
        if guild is None:
            return

        role = guild.get_role(self.tag_role_id)
        if role is None:
            return

        for member in guild.members:
            if member.bot:
                continue
            has_tag = self._primary_guild_id(member) == self.hydrabon_guild_id
            await self._sync_member_role(member, role, has_tag)

    @periodic_sync.before_loop
    async def before_periodic_sync(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(TagTracker(bot))
