import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Select
import aiosqlite
import datetime
import asyncio
from typing import List, Dict, Optional
import json
from database import get_db
import pytz

class BumpLogView(discord.ui.View):
    def __init__(self, cog, user):
        super().__init__(timeout=600)
        self.cog = cog
        self.user = user
        self.message = None
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        
        if self.message:
            await self.message.edit(view=self)
    
    @discord.ui.button(label="Günlük İstatistikler", style=discord.ButtonStyle.primary, emoji="📊", row=0)
    async def daily_stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        await self.cog.show_stats(interaction, "daily")
    
    @discord.ui.button(label="Haftalık İstatistikler", style=discord.ButtonStyle.primary, emoji="📈", row=0)
    async def weekly_stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        await self.cog.show_stats(interaction, "weekly")
    
    @discord.ui.button(label="2 Haftalık İstatistikler", style=discord.ButtonStyle.primary, emoji="📉", row=1)
    async def biweekly_stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        await self.cog.show_stats(interaction, "biweekly")
    
    @discord.ui.button(label="Aylık İstatistikler", style=discord.ButtonStyle.primary, emoji="📆", row=1)
    async def monthly_stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        await self.cog.show_stats(interaction, "monthly")

class BumpTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        self.DISBOARD_BOT_ID = 302050872383242240
        self.BUMP_CHANNEL_ID = 1366027014154223719
        self.YETKILI_ROLLERI = [
            1163918714081644554,  # STAJYER
            1200919832393154680,  # ASİSTAN
            1163918107501412493,  # MODERATÖR
            1163918130192580608,  # ADMİN
            1029089731314720798,  # YÖNETİM KURULU ÜYELERİ
            1029089727061692522,  # YÖNETİM KURULU BAŞKANI
            1029089723110674463   # KURUCU
        ]
        self.turkey_tz = pytz.timezone('Europe/Istanbul')
    
    async def cog_load(self):
        self.db = await get_db()
        await self.create_tables()
    
    async def create_tables(self):
        # Tablolar artık database.py'da oluşturuluyor
        pass
    
    def is_staff(self, member):
        for role in member.roles:
            if role.id in self.YETKILI_ROLLERI:
                return True
        return False
    
    async def check_last_message_is_disboard(self, channel):
        async for message in channel.history(limit=1):
            return message.author.id == self.DISBOARD_BOT_ID
        return False
    
    async def get_bump_count(self, user_id, guild_id):
        """Kullanıcının toplam bump sayısını getirir"""
        async with self.db.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT total_bumps FROM bump_users
            WHERE user_id = ? AND guild_id = ?
            ''', (user_id, guild_id))
            
            row = await cursor.fetchone()
            
            if row:
                return row[0]
            return 0
    
    async def get_last_bump_time(self, user_id, guild_id):
        """Kullanıcının son bump zamanını getirir"""
        async with self.db.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT last_bump FROM bump_users
            WHERE user_id = ? AND guild_id = ?
            ''', (user_id, guild_id))
            
            row = await cursor.fetchone()
            
            if row and row[0]:
                return datetime.datetime.fromisoformat(row[0])
            return None
    
    async def add_bump(self, user_id, username, guild_id):
        """Yeni bump kaydı ekler ve toplam sayıyı döndürür"""
        try:
            bump_id, total_bumps = await self.db.add_bump_log(user_id, username, guild_id)
            return total_bumps
        except Exception as e:
            print(f"Veritabanı hatası (add_bump): {e}")
            raise
    
    @app_commands.command(
        name="bump", 
        description="Yetkili bump sayınızı günceller"
    )
    async def bump_command(self, interaction: discord.Interaction):
        if interaction.channel_id != self.BUMP_CHANNEL_ID:
            return await interaction.response.send_message(
                "Bu komutu sadece bump kanalında kullanabilirsiniz!",
                ephemeral=True
            )
        
        if not self.is_staff(interaction.user):
            return await interaction.response.send_message(
                "Bu komutu sadece yetkililer kullanabilir!",
                ephemeral=True
            )
        
        channel = interaction.channel
        is_disboard_last = await self.check_last_message_is_disboard(channel)
        
        if not is_disboard_last:
            return await interaction.response.send_message(
                "Bu komutu kullanabilmek için son mesajın DISBOARD botuna ait olması gerekiyor!",
                ephemeral=True
            )
        
        try:
            await interaction.response.defer()
            
            user = interaction.user
            guild_id = interaction.guild_id
            bump_count = await self.add_bump(user.id, user.display_name, guild_id)
            
            embed = discord.Embed(
                title="🚀 Bump Sayınız Güncellendi!",
                description=f"{user.mention} yeni bir bump gerçekleştirdi!",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Toplam Bump Sayısı",
                value=f"**{bump_count}** kez bump yapmış!",
                inline=False
            )
            
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(self.turkey_tz).strftime('%d.%m.%Y %H:%M')}")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Bump kaydetme hatası: {e}")
            await interaction.followup.send("Bump işlemi sırasında bir hata oluştu. Lütfen daha sonra tekrar deneyin.", ephemeral=True)
    
    @app_commands.command(
        name="bump-log", 
        description="Yetkililerin bump komutunu kullanma istatistiklerini gösterir"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def bump_log(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📊 Bump İstatistikleri",
            description=(
                "Yetkililerin bump komutunu kullanma istatistiklerini görüntülemek için "
                "aşağıdaki butonlardan birini seçebilirsiniz.\n\n"
                "**Günlük**: Son 24 saat içindeki bump istatistikleri\n"
                "**Haftalık**: Son 7 gün içindeki bump istatistikleri\n"
                "**2 Haftalık**: Son 14 gün içindeki bump istatistikleri\n"
                "**Aylık**: Son 30 gün içindeki bump istatistikleri"
            ),
            color=discord.Color.blue()
        )
        
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(self.turkey_tz).strftime('%d.%m.%Y %H:%M')}")
        
        view = BumpLogView(self, interaction.user)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()
    
    async def get_bump_stats(self, guild_id: int, period: str):
        """Belirtilen döneme göre bump istatistiklerini getirir"""
        try:
            stats = await self.db.get_bump_stats_by_period(guild_id, period)
            return stats
        except Exception as e:
            print(f"İstatistik alma hatası: {e}")
            return []
    
    async def show_stats(self, interaction: discord.Interaction, period: str):
        """İstatistikleri güzel bir embed ile gösterir"""
        stats = await self.get_bump_stats(interaction.guild.id, period)
        
        # Başlık metinleri
        period_titles = {
            "daily": "Günlük Bump İstatistikleri",
            "weekly": "Haftalık Bump İstatistikleri (Son 7 Gün)",
            "biweekly": "2 Haftalık Bump İstatistikleri (Son 14 Gün)",
            "monthly": "Aylık Bump İstatistikleri (Son 30 Gün)"
        }
        
        title = period_titles.get(period, "Bump İstatistikleri")
        
        # Zaman aralığı açıklaması
        period_descriptions = {
            "daily": "Bugün gerçekleştirilen bump sayıları",
            "weekly": "Son 7 gün içinde gerçekleştirilen bump sayıları",
            "biweekly": "Son 14 gün içinde gerçekleştirilen bump sayıları",
            "monthly": "Son 30 gün içinde gerçekleştirilen bump sayıları"
        }
        
        description = period_descriptions.get(period, "Yetkililerin bump komutunu kullanma sayıları")
        
        embed = discord.Embed(
            title=f"📊 {title}",
            description=f"{description}\n\n{'─' * 40}",
            color=discord.Color.blue()
        )
        
        if not stats:
            embed.add_field(
                name="📭 Sonuç Bulunamadı", 
                value="Bu zaman aralığında herhangi bir bump komutu kullanılmamış.\nBump yapmak için `/bump` komutunu kullanabilirsiniz.", 
                inline=False
            )
        else:
            # İstatistikleri göster (maksimum 20 kişi)
            stats_text = ""
            for i, stat in enumerate(stats[:20], 1):
                user = interaction.guild.get_member(stat['user_id'])
                user_name = user.display_name if user else stat['username']
                
                # Medal emojileri
                if i == 1:
                    medal = "🥇"
                elif i == 2:
                    medal = "🥈"
                elif i == 3:
                    medal = "🥉"
                else:
                    medal = f"**{i}.**"
                
                stats_text += f"{medal} {user_name}: **{stat['bump_count']}** bump\n"
            
            embed.add_field(
                name="🏆 Bump Sıralaması",
                value=stats_text,
                inline=False
            )
            
            # Eğer 20'den fazla kişi varsa belirt
            if len(stats) > 20:
                embed.add_field(
                    name="ℹ️ Bilgi",
                    value=f"Toplam **{len(stats)}** kişi bump yapmış, ilk 20 kişi gösteriliyor.",
                    inline=False
                )
        
        # Toplam istatistikleri
        total_bumps = sum(stat['bump_count'] for stat in stats)
        active_users = len(stats)
        
        if total_bumps > 0:
            avg_bumps = round(total_bumps / active_users, 1) if active_users > 0 else 0
            
            embed.add_field(
                name="📈 Özet İstatistikler",
                value=(
                    f"**Toplam Bump:** {total_bumps}\n"
                    f"**Aktif Kullanıcı:** {active_users}\n"
                    f"**Ortalama Bump:** {avg_bumps} bump/kişi"
                ),
                inline=True
            )
        
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(
            text=f"{interaction.guild.name} • {datetime.datetime.now(self.turkey_tz).strftime('%d.%m.%Y %H:%M')}",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        
        await interaction.response.edit_message(embed=embed)

async def setup(bot):
    await bot.add_cog(BumpTracker(bot)) 