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
        
        # Presence snapshot görevini başlat (15 dakikada bir)
        self.presence_snapshot_task.start()
    
    def cog_unload(self):
        """Cog kaldırıldığında task'ı durdur"""
        self.weekly_report_task.cancel()
        try:
            self.presence_snapshot_task.cancel()
        except Exception:
            pass
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
    
    @tasks.loop(time=datetime.time(hour=9, tzinfo=datetime.timezone.utc))
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

    @tasks.loop(seconds=900)
    async def presence_snapshot_task(self):
        """15 dakikada bir online kullanıcı sayısını kaydeder"""
        try:
            guild = self.bot.get_guild(self.GUILD_ID)
            if not guild:
                return
            # Çevrimiçi üyeler (botlar dahil)
            online_members = len([m for m in guild.members if m.status != discord.Status.offline])
            total_members = guild.member_count or len(guild.members)
            db = await get_db()
            await db.add_presence_snapshot(guild.id, online_members, total_members)
        except Exception as e:
            print(f"Presence snapshot hatası: {e}")

    @presence_snapshot_task.before_loop
    async def before_presence_snapshot_task(self):
        await self.bot.wait_until_ready()

    def _compute_daily_averages(self, snapshots, turkey_tz):
        """Günlük ortalamalar hesaplar (Pazartesi-Pazar)"""
        if not snapshots:
            return {
                'monday': None, 'tuesday': None, 'wednesday': None, 'thursday': None,
                'friday': None, 'saturday': None, 'sunday': None,
                'samples': 0
            }
        
        # Günlere göre grupla
        daily_buckets = {
            0: [],  # Pazartesi
            1: [],  # Salı
            2: [],  # Çarşamba
            3: [],  # Perşembe
            4: [],  # Cuma
            5: [],  # Cumartesi
            6: []   # Pazar
        }
        
        for snap in snapshots:
            try:
                # snapshot_time string olabilir; ISO formatlı
                snap_time = snap['snapshot_time']
                dt = datetime.datetime.fromisoformat(snap_time.replace('Z', '+00:00')) if isinstance(snap_time, str) else snap_time
                dt_tr = dt.astimezone(turkey_tz)
                weekday = dt_tr.weekday()  # 0=Pazartesi, 6=Pazar
                val = int(snap['online_count'])
                daily_buckets[weekday].append(val)
            except Exception:
                continue
        
        def avg(lst):
            return (sum(lst) / len(lst)) if lst else None
        
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        daily_averages = {}
        total_samples = 0
        
        for i, day_name in enumerate(day_names):
            daily_averages[day_name] = avg(daily_buckets[i])
            total_samples += len(daily_buckets[i])
        
        daily_averages['samples'] = total_samples
        return daily_averages

    def _compute_presence_averages(self, snapshots, turkey_tz):
        """6 saatlik dilimler, gündüz/gece ve genel ortalamaları hesaplar"""
        if not snapshots:
            return {
                'ranges': {
                    '00-06': None, '06-12': None, '12-18': None, '18-00': None
                },
                'day': None,
                'night': None,
                'overall': None,
                'samples': 0
            }

        buckets = {
            '00-06': [],
            '06-12': [],
            '12-18': [],
            '18-00': []
        }
        day_values = []  # 06-18
        night_values = []  # 18-06
        all_values = []

        for snap in snapshots:
            try:
                # snapshot_time string olabilir; ISO formatlı
                snap_time = snap['snapshot_time']
                dt = datetime.datetime.fromisoformat(snap_time.replace('Z', '+00:00')) if isinstance(snap_time, str) else snap_time
                dt_tr = dt.astimezone(turkey_tz)
                hour = dt_tr.hour
                val = int(snap['online_count'])
                all_values.append(val)

                if 0 <= hour < 6:
                    buckets['00-06'].append(val)
                    night_values.append(val)
                elif 6 <= hour < 12:
                    buckets['06-12'].append(val)
                    day_values.append(val)
                elif 12 <= hour < 18:
                    buckets['12-18'].append(val)
                    day_values.append(val)
                else:  # 18-24
                    buckets['18-00'].append(val)
                    night_values.append(val)
            except Exception:
                continue

        def avg(lst):
            return (sum(lst) / len(lst)) if lst else None

        ranges_avg = {k: avg(v) for k, v in buckets.items()}
        return {
            'ranges': ranges_avg,
            'day': avg(day_values),
            'night': avg(night_values),
            'overall': avg(all_values),
            'samples': len(all_values)
        }
    
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
    
    async def get_moderation_actions(self, guild, start_date, end_date):
        """Belirtilen tarih aralığında gerçekleşen kick/ban işlemlerini audit log'dan alır"""
        moderation_data = {
            'kicks': [],
            'bans': [],
            'total': 0
        }
        
        try:
            # Audit log'dan kick ve ban işlemlerini al
            async for entry in guild.audit_logs(
                after=start_date,
                before=end_date,
                action=discord.AuditLogAction.kick,
                limit=100
            ):
                kick_data = {
                    'user_id': entry.target.id if entry.target else 0,
                    'username': str(entry.target) if entry.target else "Bilinmeyen Kullanıcı",
                    'moderator_id': entry.user.id if entry.user else 0,
                    'moderator_name': str(entry.user) if entry.user else "Bilinmeyen Moderatör",
                    'reason': entry.reason,
                    'action_time': entry.created_at
                }
                moderation_data['kicks'].append(kick_data)
            
            async for entry in guild.audit_logs(
                after=start_date,
                before=end_date,
                action=discord.AuditLogAction.ban,
                limit=100
            ):
                ban_data = {
                    'user_id': entry.target.id if entry.target else 0,
                    'username': str(entry.target) if entry.target else "Bilinmeyen Kullanıcı",
                    'moderator_id': entry.user.id if entry.user else 0,
                    'moderator_name': str(entry.user) if entry.user else "Bilinmeyen Moderatör",
                    'reason': entry.reason,
                    'action_time': entry.created_at
                }
                moderation_data['bans'].append(ban_data)
            
            moderation_data['total'] = len(moderation_data['kicks']) + len(moderation_data['bans'])
            
        except discord.Forbidden:
            # Audit log izni yok
            pass
        except Exception as e:
            print(f"Moderation actions alınırken hata: {e}")
        
        return moderation_data
    
    async def cleanup_old_data_after_report(self, report_start_date):
        """Haftalık rapor gönderildikten sonra eski verileri temizler"""
        try:
            db = await get_db()
            
            # Bu rapordan 4 hafta önceki verileri sil (28 gün)
            cleanup_cutoff = report_start_date - datetime.timedelta(days=28)
            # Presence snapshot'ları için 2 haftadan eski olanları sil (14 gün)
            presence_cutoff = report_start_date - datetime.timedelta(days=14)
            
            async with db.connection.cursor() as cursor:
                # Eski member loglarını temizle
                await cursor.execute('''
                DELETE FROM member_logs WHERE timestamp < ?
                ''', (cleanup_cutoff.isoformat(),))
                
                # Eski bump loglarını temizle (60 gün öncesi)
                bump_cutoff = report_start_date - datetime.timedelta(days=30)
                await cursor.execute('''
                DELETE FROM bump_logs WHERE bump_time < ?
                ''', (bump_cutoff.isoformat(),))
                
                # Eski spam loglarını temizle (30 gün öncesi)  
                spam_cutoff = report_start_date - datetime.timedelta(days=14)
                await cursor.execute('''
                DELETE FROM spam_logs WHERE spam_time < ?
                ''', (spam_cutoff.isoformat(),))

                # Eski staff_changes kayıtlarını temizle (28 gün öncesi)
                await cursor.execute('''
                DELETE FROM staff_changes WHERE created_at < ?
                ''', (cleanup_cutoff.isoformat(),))

                # Eski staff_message_stats kayıtlarını temizle (28 gün öncesi)
                try:
                    cutoff_date_str = cleanup_cutoff.date().isoformat()
                    await cursor.execute('''
                    DELETE FROM staff_message_stats WHERE message_date < ?
                    ''', (cutoff_date_str,))
                except Exception:
                    pass

                # Eski presence snapshot'larını temizle (14 gün öncesi)
                await cursor.execute('''
                DELETE FROM presence_snapshots WHERE snapshot_time < ?
                ''', (presence_cutoff.isoformat(),))
                
                # Eski staff online session'larını da temizle (2 hafta öncesi)
                staff_online_cutoff = report_start_date - datetime.timedelta(days=14)
                deleted_sessions = await db.cleanup_old_staff_online_sessions(14)
                if deleted_sessions > 0:
                    print(f"Haftalık rapor - {deleted_sessions} eski online session silindi")
                
                # Eski özel oda loglarını temizle (28 gün öncesi)
                await cursor.execute('''
                DELETE FROM private_room_logs WHERE created_at < ?
                ''', (cleanup_cutoff.isoformat(),))
                
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
                timestamp=datetime.datetime.now(self.turkey_tz)
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
            
            # === KAYIT SİSTEMİ İSTATİSTİKLERİ ===
            try:
                registration_stats = await db.get_registration_stats(start_date, end_date)
                
                if registration_stats['total_registrations'] > 0:
                    reg_value = f"**Toplam Kayıt:** {registration_stats['total_registrations']} kişi\n"
                    reg_value += f"**Günlük Ortalama:** {registration_stats['daily_average']} kayıt"
                    
                    # En aktif saatleri ekle (varsa)
                    if registration_stats.get('top_hours'):
                        reg_value += "\n\n**🕐 En Aktif Saatler:**"
                        for hour_data in registration_stats['top_hours'][:3]:
                            hour = hour_data['hour']
                            count = hour_data['count']
                            reg_value += f"\n• {hour:02d}:00-{hour+1:02d}:00 → {count} kayıt"
                    
                    embed.add_field(
                        name="📝 Kayıt Sistemi",
                        value=reg_value,
                        inline=True
                    )
                else:
                    # Kayıt yoksa bile alan ekle (düzen bozulmasın)
                    if 'error' not in registration_stats:
                        embed.add_field(
                            name="📝 Kayıt Sistemi",
                            value="Bu hafta kayıt aktivitesi tespit edilmedi.",
                            inline=True
                        )
            except Exception as e:
                # Hata durumunda sessiz geç (rapor bozulmasın)
                print(f"Kayıt istatistikleri eklenirken hata: {e}")
            
            # === ÖZEL ODA İSTATİSTİKLERİ ===
            try:
                private_room_stats = await db.get_private_room_stats(guild.id, start_date, end_date)
                
                if private_room_stats['total_rooms'] > 0:
                    daily_avg = private_room_stats['total_rooms'] / 7
                    
                    # Toplam süreyi saat ve dakika olarak formatla
                    total_hours = int(private_room_stats['total_hours'])
                    total_minutes = int(private_room_stats['total_minutes'] % 60)
                    avg_minutes = private_room_stats['average_minutes']
                    
                    value_text = f"**Toplam Açılan Oda:** {private_room_stats['total_rooms']}\n"
                    value_text += f"**Günlük Ortalama:** {daily_avg:.1f} oda\n"
                    value_text += f"**Toplam Aktif Süre:** {total_hours}s {total_minutes}dk\n"
                    value_text += f"**Oda Başına Ortalama:** {avg_minutes:.0f} dk"
                    
                    embed.add_field(
                        name="🎙️ Özel Oda Sistemi",
                        value=value_text,
                        inline=True
                    )
                else:
                    embed.add_field(
                        name="🎙️ Özel Oda Sistemi",
                        value="Bu hafta özel oda açılmadı.",
                        inline=True
                    )
            except Exception as e:
                print(f"Özel oda istatistikleri eklenirken hata: {e}")
            
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
            
            # === YETKİLİ KADRO DEĞİŞİKLİKLERİ ===
            try:
                staff_stats = await db.get_staff_change_stats(guild.id, start_date, end_date)
                staff_changes = await db.get_staff_changes_by_period(guild.id, start_date, end_date)
                total_events = sum(staff_stats.values())
                if total_events > 0:
                    lines = []
                    # Özet
                    lines.append(f"Toplam: {total_events} işlem")
                    lines.append(f"• Yeni Gelen: {staff_stats.get('added', 0)}")
                    lines.append(f"• Yükselen: {staff_stats.get('promoted', 0)}")
                    lines.append(f"• Düşen: {staff_stats.get('demoted', 0)}")
                    lines.append(f"• Görevden Alınan: {staff_stats.get('removed', 0)}")
                    # Detaylı liste (maks 10 satır)
                    if staff_changes:
                        turkey_tz = self.turkey_tz
                        detail_lines = []
                        action_map = {
                            'added': '➕ Eklendi',
                            'removed': '➖ Çıkartıldı',
                            'promoted': '⬆️ Yükseltildi',
                            'demoted': '⬇️ Düşürüldü'
                        }
                        for ch in staff_changes[:10]:
                            user_disp = f"<@{ch['user_id']}>"
                            role_from = ch['old_role_name'] or (f"<@&{ch['old_role_id']}>" if ch['old_role_id'] else '-')
                            role_to = ch['new_role_name'] or (f"<@&{ch['new_role_id']}>" if ch['new_role_id'] else '-')
                            reason = ch['reason'] or '-'
                            detail_lines.append(
                                f"{user_disp}\n"
                                f"└ {role_from} → {role_to}\n"
                                f"└ Sebep: {reason}"
                            )
                        lines.append("\n".join(detail_lines))
                    embed.add_field(
                        name="🛡️ Yetkili Kadro Değişiklikleri",
                        value="\n".join(lines)[:1024],
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="🛡️ Yetkili Kadro Değişiklikleri",
                        value="Bu hafta yetkili kadrosunda değişiklik yok.",
                        inline=False
                    )
            except Exception as e:
                embed.add_field(
                    name="🛡️ Yetkili Kadro Değişiklikleri",
                    value=f"Bilgiler alınamadı: {e}",
                    inline=False
                )
            
            # === MODERATION İŞLEMLERİ (Kick/Ban) ===
            try:
                moderation_actions = await self.get_moderation_actions(guild, start_date, end_date)
                if moderation_actions['total'] > 0:
                    lines = []
                    # Özet istatistikleri
                    lines.append(f"**Toplam İşlem:** {moderation_actions['total']}")
                    if moderation_actions['kicks']:
                        lines.append(f"• 👢 **Atma (Kick):** {len(moderation_actions['kicks'])} kişi")
                    if moderation_actions['bans']:
                        lines.append(f"• 🔨 **Yasaklama (Ban):** {len(moderation_actions['bans'])} kişi")
                    
                    # Detaylı liste (maksimum 8 kişi)
                    all_actions = []
                    
                    # Kick işlemleri
                    for kick in moderation_actions['kicks']:
                        action_time = kick['action_time'].astimezone(self.turkey_tz).strftime('%d.%m %H:%M')
                        reason = kick['reason'] or "Sebep belirtilmedi"
                        if len(reason) > 50:
                            reason = reason[:47] + "..."
                        all_actions.append({
                            'time': kick['action_time'],
                            'text': f"👢 **Atma** • {action_time} - <@{kick['user_id']}>\n└ Sebep: {reason}"
                        })
                    
                    # Ban işlemleri
                    for ban in moderation_actions['bans']:
                        action_time = ban['action_time'].astimezone(self.turkey_tz).strftime('%d.%m %H:%M')
                        reason = ban['reason'] or "Sebep belirtilmedi"
                        if len(reason) > 50:
                            reason = reason[:47] + "..."
                        all_actions.append({
                            'time': ban['action_time'],
                            'text': f"🔨 **Yasaklama** • {action_time} - <@{ban['user_id']}>\n└ Sebep: {reason}"
                        })
                    
                    # Zamana göre sırala (en yeni önce)
                    all_actions.sort(key=lambda x: x['time'], reverse=True)
                    
                    # İlk 8 tanesini göster
                    if all_actions:
                        lines.append("")  # Boş satır
                        for action in all_actions[:8]:
                            lines.append(action['text'])
                        
                        if len(all_actions) > 8:
                            lines.append(f"\n*...ve {len(all_actions) - 8} işlem daha*")
                    
                    embed.add_field(
                        name="⚖️ Moderation İşlemleri",
                        value="\n".join(lines)[:1024],
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="⚖️ Moderation İşlemleri",
                        value="Bu hafta kick/ban işlemi gerçekleştirilmedi.",
                        inline=False
                    )
            except Exception as e:
                embed.add_field(
                    name="⚖️ Moderation İşlemleri",
                    value=f"Bilgiler alınamadı: {e}",
                    inline=False
                )
            
            # === AKTİF YETKİLİ KADRO (Mesaj İstatistikleri, Çevrim İçi Saatleri ve Bump Sayıları) ===
            try:
                # Sadece KURUCU ve YK BAŞKANI hariç tutulacak (tüm diğer yetkililer dahil)
                excluded_role_ids = {
                    1029089723110674463,  # KURUCU
                    1029089727061692522,  # YK BAŞKANI
                }
                
                # Dahil edilecek yetkili rol ID'leri (YETKİLİ_HİYERARSİ'den çek)
                try:
                    from cogs.yetkili_panel import YETKILI_HIYERARSI
                    included_role_ids = set(YETKILI_HIYERARSI)
                except Exception:
                    # Fallback: Manuel rol ID'leri
                    included_role_ids = {
                        1163918714081644554,  # STAJYER
                        1200919832393154680,  # ASİSTAN
                        1163918107501412493,  # MODERATÖR
                        1460021463607152703,  # KIDEMLİ MODERATÖR
                        1163918130192580608,  # ADMİN
                        1412843482980290711,  # YÖNETİM KURULU ADAYLARI
                        1029089731314720798,  # YÖNETİM KURULU ÜYELERİ
                    }
                
                # Veritabanından tüm yetkili mesaj verilerini al
                message_stats = await db.get_top_staff_message_stats(guild.id, start_date, end_date, limit=100)
                
                # Yetkili çevrim içi saatleri verilerini al
                staff_online_stats = await db.get_staff_online_stats(guild.id, start_date, end_date)
                
                # Bump istatistiklerini al (haftalık için özel sorgu)
                # start_date ve end_date arasındaki bump verilerini al
                bump_user_stats = {}
                async with db.connection.cursor() as cursor:
                    await cursor.execute('''
                    SELECT user_id, COUNT(*) as bump_count
                    FROM bump_logs
                    WHERE guild_id = ? AND bump_time >= ? AND bump_time < ?
                    GROUP BY user_id
                    ''', (guild.id, start_date.isoformat(), end_date.isoformat()))
                    
                    rows = await cursor.fetchall()
                    for row in rows:
                        bump_user_stats[row[0]] = row[1]
                
                def is_included_staff(member):
                    user_role_ids = {r.id for r in member.roles}
                    return any(rid in user_role_ids for rid in included_role_ids)
                
                def is_excluded(member):
                    user_role_ids = {r.id for r in member.roles}
                    return any(rid in user_role_ids for rid in excluded_role_ids)
                
                # Mesaj istatistiklerini dictionary'ye çevir
                message_stats_dict = {stat['user_id']: stat['total_messages'] for stat in message_stats}
                
                # Online saatleri dictionary'ye çevir
                online_stats_dict = {stat['user_id']: stat for stat in staff_online_stats}
                
                # Tüm yetkililer için results listesi oluştur
                results = []
                
                # Sunucudaki tüm üyeleri kontrol et
                for member in guild.members:
                    if not is_included_staff(member):
                        continue
                    if is_excluded(member):
                        continue
                    
                    # Mesaj sayısını al (yoksa 0)
                    msg_count = message_stats_dict.get(member.id, 0)
                    
                    # Online istatistiklerini al
                    online_data = online_stats_dict.get(member.id, {
                        'total_hours': 0,
                        'daily_average': 0
                    })
                    
                    # Bump sayısını al (yoksa 0)
                    bump_count = bump_user_stats.get(member.id, 0)
                    
                    results.append((member, msg_count, online_data['total_hours'], online_data['daily_average'], bump_count))
                
                # Sırala (mesaj sayısına göre, sonra online saatlere göre, sonra bump sayısına göre)
                results.sort(key=lambda x: (x[1], x[2], x[4]), reverse=True)
                
                if results:
                    lines = []
                    for i, (member, msg_count, online_hours, daily_avg, bump_count) in enumerate(results, 1):
                        lines.append(f"**{i}.** {member.mention} - {msg_count} mesaj • {online_hours:.1f}h online • {bump_count} bump")
                    
                    # Çok uzunsa bölümlere ayır
                    if len(lines) > 20:
                        # İlk 20'yi göster, kalanları say
                        first_20 = lines[:20]
                        remaining_count = len(lines) - 20
                        first_20.append(f"\n*...ve {remaining_count} yetkili daha*")
                        lines = first_20
                    
                    embed.add_field(
                        name=f"👥 Aktif Yetkili Kadro - Mesaj, Online & Bump ({len(results)} kişi)",
                        value="\n".join(lines),
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="👥 Aktif Yetkili Kadro - Mesaj, Online & Bump",
                        value="Bu hafta yetkili kadrosunda aktivite bulunamadı.",
                        inline=False
                    )
            except Exception as e:
                embed.add_field(
                    name="👥 Aktif Yetkili Kadro - Mesaj, Online & Bump",
                    value=f"Bilgiler alınamadı: {e}",
                    inline=False
                )
            
            # Son Aktiviteler bölümü kaldırıldı
            
            # === SUNUCU BİLGİLERİ ===
            online_members = len([m for m in guild.members if m.status != discord.Status.offline])
            
            embed.add_field(
                name="ℹ️ Genel Bilgiler",
                value=f"**Online Üye:** {online_members}/{guild.member_count}\n"
                      f"**Metin Kanalı:** {len(guild.text_channels)}\n"
                      f"**Ses Kanalı:** {len(guild.voice_channels)}\n"
                      f"**Rol Sayısı:** {len(guild.roles)}",
                inline=True
            )

            # === AKTİF KULLANICI ORTALAMALARI ===
            presence_snaps = await db.get_presence_snapshots(guild.id, start_date, end_date)
            
            # Günlük ortalamalar
            daily_stats = self._compute_daily_averages(presence_snaps, turkey_tz)
            if daily_stats['samples'] > 0:
                def fmt(v):
                    return f"{v:.1f}" if v is not None else "-"
                
                # Türkçe gün isimleri
                day_names_tr = {
                    'monday': 'Pazartesi',
                    'tuesday': 'Salı', 
                    'wednesday': 'Çarşamba',
                    'thursday': 'Perşembe',
                    'friday': 'Cuma',
                    'saturday': 'Cumartesi',
                    'sunday': 'Pazar'
                }
                
                daily_lines = []
                for day_en, day_tr in day_names_tr.items():
                    avg_val = daily_stats[day_en]
                    daily_lines.append(f"**{day_tr}:** {fmt(avg_val)}")
                
                embed.add_field(
                    name="📅 Günlük Aktif Üye Ortalamaları",
                    value="\n".join(daily_lines),
                    inline=True
                )
            
            # Saatlik ortalamalar
            presence_stats = self._compute_presence_averages(presence_snaps, turkey_tz)
            if presence_stats['samples'] > 0:
                r = presence_stats['ranges']
                def fmt(v):
                    return f"{v:.1f}" if v is not None else "-"
                lines = [
                    f"**00-06:** {fmt(r['00-06'])}",
                    f"**06-12:** {fmt(r['06-12'])}",
                    f"**12-18:** {fmt(r['12-18'])}",
                    f"**18-00:** {fmt(r['18-00'])}",
                    f"**Gündüz (06-18):** {fmt(presence_stats['day'])}",
                    f"**Gece (18-06):** {fmt(presence_stats['night'])}",
                    f"**Genel Ortalama:** {fmt(presence_stats['overall'])}",
                ]
                embed.add_field(
                    name="🕐 Saatlik Aktif Üye Ortalamaları",
                    value="\n".join(lines),
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