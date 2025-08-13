import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import datetime
import pytz
import random
from database import get_db

class WeeklyReports(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.REPORT_CHANNEL_ID = 1400154619962851480  # YK rapor kanalı
        self.GUILD_ID = 1029088146752815138  # Ana sunucu ID'si
        self.turkey_tz = pytz.timezone('Europe/Istanbul')  # UTC+3
        
        # Rapor komut grubunu oluştur
        self.rapor_group = app_commands.Group(name="rapor", description="Haftalık rapor yönetim komutları")
        
        # Komutları gruba ekle
        self.setup_commands()
        
        # Rapor komut grubunu bot'a ekle
        self.bot.tree.add_command(self.rapor_group)
        
        # Haftalık rapor görevini başlat
        self.weekly_report_task.start()
    
    def cog_unload(self):
        """Cog kaldırıldığında task'ı durdur"""
        self.weekly_report_task.cancel()
        # Rapor komut grubunu bot'tan kaldır
        self.bot.tree.remove_command(self.rapor_group.name)
    
    def setup_commands(self):
        """Rapor komutlarını gruba ekler"""
        
        @self.rapor_group.command(name="test", description="Test raporu oluşturur")
        @app_commands.default_permissions(administrator=True)
        async def test_weekly_report(interaction: discord.Interaction):
            """Manuel test raporu oluşturur (sadece admin)"""
            if interaction.user.id != 315888596437696522:
                await interaction.response.send_message("Bu komutu kullanma yetkiniz bulunmamaktadır.", ephemeral=True)
                return
                
            try:
                await interaction.response.send_message("🔄 Test raporu oluşturuluyor...", ephemeral=True)
                await self.generate_weekly_report()
                await interaction.followup.send("✅ Test raporu gönderildi!", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Test raporu hatası: {e}", ephemeral=True)
        
        @self.rapor_group.command(name="sonraki", description="Sonraki haftalık raporun ne zaman gönderileceğini gösterir")
        @app_commands.default_permissions(administrator=True)
        async def next_report_time(interaction: discord.Interaction):
            """Sonraki haftalık raporun ne zaman gönderileceğini gösterir"""
            try:
                # Şimdiki zaman (Türkiye saati)
                now_turkey = datetime.datetime.now(self.turkey_tz)
                
                # Bir sonraki Pazar'ı bul
                days_until_sunday = (6 - now_turkey.weekday()) % 7
                if days_until_sunday == 0:  # Bugün Pazar ise
                    if now_turkey.hour < 12:  # Henüz saat 12 olmamışsa
                        next_sunday = now_turkey.replace(hour=12, minute=0, second=0, microsecond=0)
                    else:  # Saat 12'yi geçmişse, bir sonraki Pazar
                        next_sunday = now_turkey + datetime.timedelta(days=7)
                        next_sunday = next_sunday.replace(hour=12, minute=0, second=0, microsecond=0)
                else:
                    next_sunday = now_turkey + datetime.timedelta(days=days_until_sunday)
                    next_sunday = next_sunday.replace(hour=12, minute=0, second=0, microsecond=0)
                
                # Kalan süreyi hesapla
                remaining = next_sunday - now_turkey
                days = remaining.days
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                embed = discord.Embed(
                    title="📊 Sonraki Haftalık Rapor",
                    description=f"**Tarih:** {next_sunday.strftime('%d.%m.%Y Pazar')}\n"
                               f"**Saat:** 12:00 (UTC+3)\n"
                               f"**Kalan Süre:** {days} gün, {hours} saat, {minutes} dakika",
                    color=0x2b82ff
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            except Exception as e:
                await interaction.response.send_message(f"❌ Hata: {e}", ephemeral=True)
        
        @self.rapor_group.command(name="temizle", description="Eski member loglarını temizler")
        @app_commands.describe(days="Kaç günden eski loglar silinsin (varsayılan: 90)")
        @app_commands.default_permissions(administrator=True)
        async def cleanup_old_member_logs(interaction: discord.Interaction, days: int = 90):
            """Eski member loglarını temizler (varsayılan: 90 gün)"""
            if interaction.user.id != 315888596437696522:
                await interaction.response.send_message("Bu komutu kullanma yetkiniz bulunmamaktadır.", ephemeral=True)
                return
                
            try:
                await interaction.response.send_message(f"🧹 {days} günden eski member logları temizleniyor...", ephemeral=True)
                
                db = await get_db()
                
                # Eski logları temizle
                cutoff_date = datetime.datetime.now(pytz.UTC) - datetime.timedelta(days=days)
                
                async with db.connection.cursor() as cursor:
                    # Silinecek kayıt sayısını say
                    await cursor.execute('''
                    SELECT COUNT(*) FROM member_logs WHERE timestamp < ?
                    ''', (cutoff_date.isoformat(),))
                    
                    count_to_delete = (await cursor.fetchone())[0]
                    
                    if count_to_delete > 0:
                        # Eski kayıtları sil
                        await cursor.execute('''
                        DELETE FROM member_logs WHERE timestamp < ?
                        ''', (cutoff_date.isoformat(),))
                        
                        await db.connection.commit()
                        
                        embed = discord.Embed(
                            title="🧹 Temizlik Tamamlandı",
                            description=f"**Silinen Kayıt:** {count_to_delete:,}\n"
                                       f"**Tarih Limiti:** {days} gün\n"
                                       f"**Kesim Tarihi:** {cutoff_date.strftime('%d.%m.%Y %H:%M')}",
                            color=0x00ff00
                        )
                    else:
                        embed = discord.Embed(
                            title="ℹ️ Temizlik Sonucu",
                            description=f"{days} günden eski kayıt bulunamadı.",
                            color=0x2b82ff
                        )
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    
            except Exception as e:
                await interaction.followup.send(f"❌ Temizlik hatası: {e}", ephemeral=True)
    
    async def safe_send(self, channel, content=None, embed=None, max_retries=3):
        """Güvenli mesaj gönderme fonksiyonu - 503 hatalarını önler"""
        if not channel:
            return None
            
        for attempt in range(max_retries):
            try:
                if content and embed:
                    return await channel.send(content=content, embed=embed)
                elif content:
                    return await channel.send(content=content)
                elif embed:
                    return await channel.send(embed=embed)
                else:
                    return None
                    
            except discord.Forbidden:
                return None
                
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    retry_after = getattr(e, 'retry_after', None) or (2 ** attempt)
                    await asyncio.sleep(min(retry_after + random.uniform(0.1, 0.5), 60))
                    continue
                    
                elif e.status in [503, 502, 500]:  # Server errors
                    if attempt < max_retries - 1:
                        delay = min((2 ** attempt) + random.uniform(0.1, 1.0), 30)
                        await asyncio.sleep(delay)
                        continue
                    else:
                        print(f"Haftalık rapor gönderme hatası (503/502/500): {e}")
                        return None
                        
                elif e.status == 400:  # Bad request
                    print(f"Haftalık rapor gönderme hatası (400): {e}")
                    return None
                    
                else:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1 + random.uniform(0.1, 0.5))
                        continue
                    else:
                        print(f"Haftalık rapor gönderme HTTP hatası: {e}")
                        return None
                        
            except (asyncio.TimeoutError, OSError) as e:
                if attempt < max_retries - 1:
                    delay = min((2 ** attempt) + random.uniform(0.5, 1.5), 20)
                    await asyncio.sleep(delay)
                    continue
                else:
                    print(f"Haftalık rapor gönderme bağlantı hatası: {e}")
                    return None
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 + random.uniform(0.1, 1.0))
                    continue
                else:
                    print(f"Haftalık rapor gönderme beklenmeyen hata: {e}")
                    return None
        
        return None
    
    @tasks.loop(time=datetime.time(hour=12, tzinfo=pytz.timezone('Europe/Istanbul')))
    async def weekly_report_task(self):
        """Haftalık rapor görevi - Her Pazar 12:00'da çalışır (Optimize edilmiş)"""
        try:
            # Şimdiki zaman (Türkiye saati)
            now_turkey = datetime.datetime.now(self.turkey_tz)
            
            # Sadece Pazar günü çalıştır
            if now_turkey.weekday() == 6:  # Pazar = 6
                await self.generate_weekly_report()
                # Weekly report sent
            else:
                # Weekly report skipped (not Sunday)
                pass
                
        except Exception as e:
            print(f"❌ Haftalık rapor görevi hatası: {e}")
    
    @weekly_report_task.before_loop
    async def before_weekly_report_task(self):
        """Task başlamadan önce bot'un hazır olmasını bekle"""
        await self.bot.wait_until_ready()
    
    async def generate_weekly_report(self):
        """Haftalık raporu oluşturur ve gönderir"""
        try:
            guild = self.bot.get_guild(self.GUILD_ID)
            if not guild:
                # Guild not found error
                return
                
            report_channel = guild.get_channel(self.REPORT_CHANNEL_ID)
            if not report_channel:
                # Report channel not found error
                return
            
            # Geçen haftanın tarih aralığını hesapla (Pazar 12:00 - Pazar 12:00)
            now_turkey = datetime.datetime.now(self.turkey_tz)
            
            # Bu haftanın Pazar 12:00'ı
            current_sunday = now_turkey.replace(hour=12, minute=0, second=0, microsecond=0)
            
            # Geçen haftanın Pazar 12:00'ı
            last_sunday = current_sunday - datetime.timedelta(days=7)
            
            # UTC'ye çevir (veritabanında UTC olarak saklıyoruz)
            start_date = last_sunday.astimezone(pytz.UTC)
            end_date = current_sunday.astimezone(pytz.UTC)
            
            # Raporu oluştur ve gönder
            embed = await self.create_weekly_report_embed(guild, start_date, end_date)
            
            # Fire-and-forget: Haftalık rapor background'da gönderilir
            asyncio.create_task(self.safe_send(
                report_channel,
                content="📊 **HAFTALIK SUNUCU RAPORU** 📊",
                embed=embed
            ))
            
            # Rapor task'ı başlatıldıktan sonra eski verileri temizle
            await self.cleanup_old_data_after_report(start_date)
            
            # Weekly report sent successfully
            
        except Exception as e:
            print(f"Haftalık rapor oluşturma hatası: {e}")
    
    async def cleanup_old_data_after_report(self, report_start_date):
        """Haftalık rapor gönderildikten sonra eski verileri temizler"""
        try:
            db = await get_db()
            
            # Bu rapordan 4 hafta önceki verileri sil (28 gün)
            cleanup_cutoff = report_start_date - datetime.timedelta(days=28)
            
            async with db.connection.cursor() as cursor:
                # Eski member loglarını temizle
                await cursor.execute('''
                DELETE FROM member_logs WHERE timestamp < ?
                ''', (cleanup_cutoff.isoformat(),))
                
                member_deleted = cursor.rowcount
                
                # Eski bump loglarını temizle (60 gün öncesi)
                bump_cutoff = report_start_date - datetime.timedelta(days=60)
                await cursor.execute('''
                DELETE FROM bump_logs WHERE bump_time < ?
                ''', (bump_cutoff.isoformat(),))
                
                bump_deleted = cursor.rowcount
                
                # Eski spam loglarını temizle (30 gün öncesi)  
                spam_cutoff = report_start_date - datetime.timedelta(days=30)
                await cursor.execute('''
                DELETE FROM spam_logs WHERE spam_time < ?
                ''', (spam_cutoff.isoformat(),))
                
                spam_deleted = cursor.rowcount
                
                await db.connection.commit()
                
                                    # Cleanup completed
                
        except Exception as e:
            print(f"Otomatik temizlik hatası: {e}")
    
    async def create_weekly_report_embed(self, guild, start_date, end_date):
        """Haftalık rapor embed'ini oluşturur"""
        try:
            db = await get_db()
            
            # Rapor başlığı ve tarihleri
            turkey_tz = pytz.timezone('Europe/Istanbul')
            start_turkey = start_date.astimezone(turkey_tz)
            end_turkey = end_date.astimezone(turkey_tz)
            
            embed = discord.Embed(
                title="📊 Haftalık Sunucu Raporu",
                description=f"**📅 Rapor Dönemi**\n"
                           f"{start_turkey.strftime('%d.%m.%Y %H:%M')} - {end_turkey.strftime('%d.%m.%Y %H:%M')}",
                color=0x2b82ff,
                timestamp=datetime.datetime.now()
            )
            
            # === ÜYE İSTATİSTİKLERİ ===
            member_stats = await db.get_member_stats_by_period(guild.id, start_date, end_date)
            
            # Net değişim emoji ve renk
            if member_stats['net_change'] > 0:
                change_emoji = "📈"
                change_text = f"+{member_stats['net_change']}"
            elif member_stats['net_change'] < 0:
                change_emoji = "📉"
                change_text = str(member_stats['net_change'])
            else:
                change_emoji = "➖"
                change_text = "0"
            
            embed.add_field(
                name="👥 Üye Hareketleri",
                value=f"**Giriş:** {member_stats['joins']} kişi\n"
                      f"**Çıkış:** {member_stats['leaves']} kişi\n"
                      f"**Net Değişim:** {change_emoji} {change_text}\n"
                      f"**Mevcut Üye:** {guild.member_count} kişi",
                inline=True
            )
            
            # === BUMP İSTATİSTİKLERİ ===
            # Bump verilerini al (son 7 gün)
            bump_stats = await db.get_bump_stats_by_period(guild.id, 'weekly')
            
            if bump_stats:
                # Top 5 bumper
                top_bumpers = []
                for i, bumper in enumerate(bump_stats[:5], 1):
                    user = guild.get_member(bumper['user_id'])
                    username = user.mention if user else bumper['username']
                    top_bumpers.append(f"**{i}.** {username} - {bumper['bump_count']} bump")
                
                total_bumps = sum(bumper['bump_count'] for bumper in bump_stats)
                total_bumpers = len(bump_stats)
                
                embed.add_field(
                    name="📈 Bump İstatistikleri",
                    value=f"**Toplam Bump:** {total_bumps}\n"
                          f"**Aktif Bumper:** {total_bumpers} kişi\n"
                          f"**Günlük Ortalama:** {total_bumps/7:.1f} bump",
                    inline=True
                )
                
                if top_bumpers:
                    embed.add_field(
                        name="🏆 Top 5 Bumper",
                        value="\n".join(top_bumpers),
                        inline=False
                    )
            else:
                embed.add_field(
                    name="📈 Bump İstatistikleri",
                    value="Bu hafta bump aktivitesi tespit edilmedi.",
                    inline=True
                )
            
            # === SON AKTİVİTELER ===
            activities = []
            
            # Son girişler
            if member_stats['recent_joins']:
                activities.append("**📥 Son Girişler:**")
                for join in member_stats['recent_joins'][:3]:
                    join_time = datetime.datetime.fromisoformat(join['timestamp'].replace('Z', '+00:00'))
                    join_turkey = join_time.astimezone(turkey_tz)
                    activities.append(f"• {join['username']} - {join_turkey.strftime('%d.%m %H:%M')}")
            
            # Son çıkışlar
            if member_stats['recent_leaves']:
                activities.append("\n**📤 Son Çıkışlar:**")
                for leave in member_stats['recent_leaves'][:3]:
                    leave_time = datetime.datetime.fromisoformat(leave['timestamp'].replace('Z', '+00:00'))
                    leave_turkey = leave_time.astimezone(turkey_tz)
                    activities.append(f"• {leave['username']} - {leave_turkey.strftime('%d.%m %H:%M')}")
            
            if activities:
                embed.add_field(
                    name="🔄 Son Aktiviteler",
                    value="\n".join(activities),
                    inline=False
                )
            
            # === SUNUCU BİLGİLERİ ===
            online_members = len([m for m in guild.members if m.status != discord.Status.offline and not m.bot])
            
            embed.add_field(
                name="ℹ️ Genel Bilgiler",
                value=f"**Online Üye:** {online_members}/{guild.member_count}\n"
                      f"**Metin Kanalı:** {len(guild.text_channels)}\n"
                      f"**Ses Kanalı:** {len(guild.voice_channels)}\n"
                      f"**Rol Sayısı:** {len(guild.roles)}",
                inline=True
            )
            
            # === RAPOR BİLGİLERİ ===
            embed.add_field(
                name="📋 Rapor Bilgileri",
                value=f"**Oluşturma:** {datetime.datetime.now(turkey_tz).strftime('%d.%m.%Y %H:%M')}\n"
                      f"**Sistem:** HydRaboN Bot v2.0\n"
                      f"**Durum:** Otomatik Rapor",
                inline=True
            )
            
            # Footer ve thumbnail
            embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
            embed.set_footer(
                text=f"{guild.name} • Haftalık Rapor Sistemi",
                icon_url=guild.icon.url if guild.icon else None
            )
            
            return embed
            
        except Exception as e:
            print(f"Rapor embed oluşturma hatası: {e}")
            # Hata durumunda basit embed döndür
            return discord.Embed(
                title="❌ Rapor Hatası",
                description="Haftalık rapor oluşturulurken bir hata oluştu.",
                color=discord.Color.red()
            )


async def setup(bot):
    cog = WeeklyReports(bot)
    await bot.add_cog(cog)
    # Command grupları __init__ metodunda ekleniyor