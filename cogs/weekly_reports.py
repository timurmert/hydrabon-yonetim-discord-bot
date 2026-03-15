import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import datetime
import pytz
import random
import io
from database import get_db

class WeeklyReports(commands.Cog):
    # Puanlama sabitleri
    MSG_WEIGHT = 1.0
    VOICE_WEIGHT = 4.0
    BUMP_WEIGHT = 10.0
    MESSAGES_PER_HOUR = 30
    EFFICIENCY_FLOOR = 0.7
    EFFICIENCY_BONUS = 0.6

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

    def calculate_staff_score(self, msg_count, online_hours, voice_hours, bump_count):
        """Yetkili performans puanını hesaplar (verimlilik bazlı)"""
        base = (msg_count * self.MSG_WEIGHT) + (voice_hours * self.VOICE_WEIGHT) + (bump_count * self.BUMP_WEIGHT)
        active_hours = voice_hours + (msg_count / self.MESSAGES_PER_HOUR)
        efficiency = active_hours / max(online_hours, 1)
        multiplier = self.EFFICIENCY_FLOOR + self.EFFICIENCY_BONUS * min(efficiency, 1.0)
        return round(base * multiplier, 1)

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
    
    async def safe_send(self, channel, content=None, embed=None, file=None, max_retries=3):
        """Güvenli mesaj gönderme fonksiyonu - 503 hatalarını önler"""
        if not channel:
            return None

        for attempt in range(max_retries):
            try:
                kwargs = {}
                if content:
                    kwargs['content'] = content
                if embed:
                    kwargs['embed'] = embed
                if file:
                    kwargs['file'] = file
                if not kwargs:
                    return None
                return await channel.send(**kwargs)
                    
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
    
    async def create_report_image(self, guild, start_date, end_date):
        """Haftalık rapor dashboard görselini oluşturur ve BytesIO olarak döndürür"""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.ticker as ticker
            import matplotlib.font_manager as fm
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as e:
            print(f"Rapor görseli için gerekli kütüphaneler yüklü değil: {e}")
            return None

        try:
            db = await get_db()
            turkey_tz = self.turkey_tz
            start_turkey = start_date.astimezone(turkey_tz)
            end_turkey = end_date.astimezone(turkey_tz)

            # ===== VERİ TOPLAMA =====
            member_stats = await db.get_member_stats_by_period(guild.id, start_date, end_date)

            try:
                registration_stats = await db.get_registration_stats(start_date, end_date)
            except Exception:
                registration_stats = {'total_registrations': 0, 'daily_average': 0}

            bump_stats = await db.get_bump_stats_by_period(guild.id, 'weekly')
            total_bumps = sum(b['bump_count'] for b in bump_stats) if bump_stats else 0

            try:
                channel_stats = await db.get_channel_stats_by_period(guild.id, start_date, end_date)
            except Exception:
                channel_stats = {}

            presence_snaps = await db.get_presence_snapshots(guild.id, start_date, end_date)
            daily_avgs = self._compute_daily_averages(presence_snaps, turkey_tz)
            presence_avgs = self._compute_presence_averages(presence_snaps, turkey_tz)

            try:
                mod_actions = await self.get_moderation_actions(guild, start_date, end_date)
            except Exception:
                mod_actions = {'kicks': [], 'bans': [], 'total': 0}

            # Kanal verilerini işle
            total_messages = 0
            sohbet_daily = []
            eglence_daily = []
            top_channels = []

            if channel_stats:
                if 'sohbet' in channel_stats:
                    total_messages += channel_stats['sohbet'].get('total_messages', 0)
                    sohbet_daily = channel_stats['sohbet'].get('daily_breakdown', [])
                    top_channels.extend(channel_stats['sohbet'].get('channels', []))
                if 'eglence' in channel_stats:
                    total_messages += channel_stats['eglence'].get('total_messages', 0)
                    eglence_daily = channel_stats['eglence'].get('daily_breakdown', [])
                    top_channels.extend(channel_stats['eglence'].get('channels', []))

            top_channels.sort(key=lambda x: x.get('total_messages', 0), reverse=True)
            top_channels = top_channels[:6]

            # ===== RENK PALETİ =====
            BG = (13, 17, 23)
            CARD_BG = (22, 27, 34)
            CARD_BORDER = (48, 54, 61)
            ACCENT = (43, 130, 255)
            ACCENT_HEX = '#2b82ff'
            GREEN = (63, 185, 80)
            GREEN_HEX = '#3fb950'
            RED = (248, 81, 73)
            RED_HEX = '#f85149'
            AMBER = (210, 153, 34)
            AMBER_HEX = '#d29922'
            PURPLE = (137, 87, 229)
            PURPLE_HEX = '#8957e5'
            CYAN = (56, 211, 159)
            CYAN_HEX = '#38d39f'
            TEXT_PRIMARY = (230, 237, 243)
            TEXT_SECONDARY = (139, 148, 158)
            TEXT_SEC_HEX = '#8b949e'
            BORDER_HEX = '#30363d'

            # ===== FONT YÜKLEME =====
            def load_font(size, bold=False):
                if bold:
                    paths = [
                        "C:/Windows/Fonts/segoeuib.ttf",
                        "C:/Windows/Fonts/arialbd.ttf",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                    ]
                else:
                    paths = [
                        "C:/Windows/Fonts/segoeui.ttf",
                        "C:/Windows/Fonts/arial.ttf",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                    ]
                for p in paths:
                    try:
                        return ImageFont.truetype(p, size)
                    except (OSError, IOError):
                        continue
                return ImageFont.load_default()

            font_title = load_font(38, bold=True)
            font_subtitle = load_font(20)
            font_section = load_font(22, bold=True)
            font_kpi_num = load_font(44, bold=True)
            font_kpi_label = load_font(14, bold=True)
            font_kpi_sub = load_font(13)
            font_regular = load_font(16)
            font_footer = load_font(14)
            font_mini_val = load_font(24, bold=True)

            # Matplotlib font ayarı
            available_fonts = {f.name for f in fm.fontManager.ttflist}
            if 'Segoe UI' in available_fonts:
                plt.rcParams['font.family'] = 'Segoe UI'
            elif 'DejaVu Sans' in available_fonts:
                plt.rcParams['font.family'] = 'DejaVu Sans'

            # ===== CANVAS =====
            WIDTH = 1400
            HEIGHT = 1500
            PADDING = 40
            CW = WIDTH - 2 * PADDING

            img = Image.new('RGBA', (WIDTH, HEIGHT), BG)
            draw = ImageDraw.Draw(img)

            # ===== YARDIMCI FONKSİYONLAR =====
            def rounded_rect(x, y, w, h, r=12, fill=CARD_BG, outline=CARD_BORDER):
                draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=fill, outline=outline, width=1)

            def center_text(text, x, y, w, font, fill=TEXT_PRIMARY):
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                draw.text((x + (w - tw) / 2, y), text, font=font, fill=fill)

            def make_chart_image(fig, target_w, target_h):
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=150, transparent=True, bbox_inches='tight', pad_inches=0.3)
                buf.seek(0)
                plt.close(fig)
                chart = Image.open(buf).convert('RGBA')
                chart = chart.resize((target_w, target_h), Image.LANCZOS)
                return chart

            y = PADDING

            # ===== 1. HEADER =====
            center_text("HAFTALIK SUNUCU RAPORU", PADDING, y, CW, font_title, ACCENT)
            y += 50

            date_str = f"{start_turkey.strftime('%d.%m.%Y %H:%M')}  —  {end_turkey.strftime('%d.%m.%Y %H:%M')}"
            center_text(date_str, PADDING, y, CW, font_subtitle, TEXT_SECONDARY)
            y += 30

            draw.line([(PADDING, y + 5), (WIDTH - PADDING, y + 5)], fill=ACCENT, width=2)
            y += 20

            # ===== 2. KPI CARDS =====
            card_gap = 20
            card_w = (CW - 3 * card_gap) // 4
            card_h = 110

            net = member_stats['net_change']
            kpis = [
                ('NET \u00dcYE', f"{'+' if net > 0 else ''}{net}",
                 GREEN if net >= 0 else RED,
                 f"Giri\u015f: {member_stats['joins']}  \u00c7\u0131k\u0131\u015f: {member_stats['leaves']}"),
                ('TOPLAM MESAJ', f"{total_messages:,}", ACCENT,
                 f"Mevcut \u00dcye: {guild.member_count:,}"),
                ('TOPLAM BUMP', f"{total_bumps:,}", PURPLE,
                 f"G\u00fcnl\u00fck Ort: {total_bumps / 7:.1f}"),
                ('KAYIT', f"{registration_stats.get('total_registrations', 0):,}", AMBER,
                 f"G\u00fcnl\u00fck Ort: {registration_stats.get('daily_average', 0)}"),
            ]

            for i, (label, value, color, sub) in enumerate(kpis):
                cx = PADDING + i * (card_w + card_gap)
                rounded_rect(cx, y, card_w, card_h)
                center_text(value, cx, y + 12, card_w, font_kpi_num, color)
                center_text(label, cx, y + 65, card_w, font_kpi_label, TEXT_SECONDARY)
                center_text(sub, cx, y + 88, card_w, font_kpi_sub, TEXT_SECONDARY)

            y += card_h + 25

            # ===== 3. G\u00dcNL\u00dcK MESAJ AKT\u0130V\u0130TES\u0130 =====
            draw.text((PADDING, y), "G\u00dcNL\u00dcK MESAJ AKT\u0130V\u0130TES\u0130", font=font_section, fill=TEXT_PRIMARY)
            y += 35

            chart_h_msg = 260
            day_labels_tr = ['Pzt', 'Sal', '\u00c7ar', 'Per', 'Cum', 'Cmt', 'Paz']

            all_dates_dict = {}
            for d in sohbet_daily:
                dk = d['date']
                all_dates_dict.setdefault(dk, {'sohbet': 0, 'eglence': 0})
                all_dates_dict[dk]['sohbet'] = d['message_count']
            for d in eglence_daily:
                dk = d['date']
                all_dates_dict.setdefault(dk, {'sohbet': 0, 'eglence': 0})
                all_dates_dict[dk]['eglence'] = d['message_count']

            sorted_dates = sorted(all_dates_dict.keys())

            if sorted_dates:
                s_vals = [all_dates_dict[d]['sohbet'] for d in sorted_dates]
                e_vals = [all_dates_dict[d]['eglence'] for d in sorted_dates]

                labels = []
                for d in sorted_dates:
                    dt = datetime.datetime.strptime(d, '%Y-%m-%d')
                    labels.append(f"{dt.strftime('%d.%m')}\n{day_labels_tr[dt.weekday()]}")

                fig, ax = plt.subplots(figsize=(13, 3.5))
                fig.patch.set_alpha(0)
                ax.set_facecolor('none')

                x_pos = range(len(sorted_dates))
                bw = 0.35

                ax.bar([i - bw / 2 for i in x_pos], s_vals, bw,
                       label='Sohbet', color=ACCENT_HEX, alpha=0.85, edgecolor='none', zorder=3)
                ax.bar([i + bw / 2 for i in x_pos], e_vals, bw,
                       label='E\u011flence', color=PURPLE_HEX, alpha=0.85, edgecolor='none', zorder=3)

                max_val = max(max(s_vals, default=0), max(e_vals, default=0))
                offset = max(max_val * 0.03, 1)
                for i, v in enumerate(s_vals):
                    if v > 0:
                        ax.text(i - bw / 2, v + offset, f'{v:,}',
                                ha='center', va='bottom', fontsize=8, color='white', fontweight='bold')
                for i, v in enumerate(e_vals):
                    if v > 0:
                        ax.text(i + bw / 2, v + offset, f'{v:,}',
                                ha='center', va='bottom', fontsize=8, color='white', fontweight='bold')

                ax.set_xticks(list(x_pos))
                ax.set_xticklabels(labels, fontsize=9, color=TEXT_SEC_HEX)
                ax.tick_params(axis='y', colors=TEXT_SEC_HEX, labelsize=8)
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.spines['left'].set_color(BORDER_HEX)
                ax.spines['bottom'].set_color(BORDER_HEX)
                ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'{int(x):,}'))
                ax.legend(fontsize=9, loc='upper right', framealpha=0.3, labelcolor='white',
                          facecolor='#161b22', edgecolor=BORDER_HEX)
                ax.grid(axis='y', alpha=0.1, color=TEXT_SEC_HEX)
                if max_val > 0:
                    ax.set_ylim(0, max_val * 1.2)

                plt.tight_layout()
                chart_img = make_chart_image(fig, CW, chart_h_msg)
                img.paste(chart_img, (PADDING, y), chart_img)
            else:
                rounded_rect(PADDING, y, CW, chart_h_msg)
                center_text("Bu hafta mesaj verisi bulunamad\u0131", PADDING, y + chart_h_msg // 2 - 10, CW, font_regular, TEXT_SECONDARY)

            y += chart_h_msg + 25

            # ===== 4. IKI SUTUNLU BOLUM =====
            col_gap = 20
            col_w = (CW - col_gap) // 2
            chart_h_col = 240

            draw.text((PADDING, y), "AKT\u0130F \u00dcYE ORTALAMALARI", font=font_section, fill=TEXT_PRIMARY)
            draw.text((PADDING + col_w + col_gap, y), "SAATL\u0130K AKT\u0130V\u0130TE", font=font_section, fill=TEXT_PRIMARY)
            y += 32

            # Sol: Gunluk aktif uye ortalamalari
            if daily_avgs['samples'] > 0:
                d_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                d_labels = ['Pzt', 'Sal', '\u00c7ar', 'Per', 'Cum', 'Cmt', 'Paz']
                avg_vals = [daily_avgs[d] or 0 for d in d_names]

                fig, ax = plt.subplots(figsize=(6.5, 3.2))
                fig.patch.set_alpha(0)
                ax.set_facecolor('none')

                colors_daily = [CYAN_HEX] * 5 + [ACCENT_HEX] * 2
                ax.bar(range(7), avg_vals, color=colors_daily, alpha=0.85, edgecolor='none', zorder=3)

                max_avg = max(avg_vals) if avg_vals else 1
                for i, v in enumerate(avg_vals):
                    if v > 0:
                        ax.text(i, v + max(max_avg * 0.03, 0.5), f'{v:.0f}',
                                ha='center', va='bottom', fontsize=9, color='white', fontweight='bold')

                ax.set_xticks(range(7))
                ax.set_xticklabels(d_labels, fontsize=9, color=TEXT_SEC_HEX)
                ax.tick_params(axis='y', colors=TEXT_SEC_HEX, labelsize=8)
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.spines['left'].set_color(BORDER_HEX)
                ax.spines['bottom'].set_color(BORDER_HEX)
                ax.grid(axis='y', alpha=0.1, color=TEXT_SEC_HEX)
                if max_avg > 0:
                    ax.set_ylim(0, max_avg * 1.25)

                plt.tight_layout()
                left_chart = make_chart_image(fig, col_w, chart_h_col)
                img.paste(left_chart, (PADDING, y), left_chart)
            else:
                rounded_rect(PADDING, y, col_w, chart_h_col)
                center_text("Veri yok", PADDING, y + chart_h_col // 2 - 10, col_w, font_regular, TEXT_SECONDARY)

            # Sag: Saatlik aktivite dagilimi
            if presence_avgs['samples'] > 0:
                r = presence_avgs['ranges']
                range_labels = ['00:00 - 06:00', '06:00 - 12:00', '12:00 - 18:00', '18:00 - 00:00']
                range_keys = ['00-06', '06-12', '12-18', '18-00']
                range_vals = [r[k] or 0 for k in range_keys]
                range_colors = ['#6366f1', '#f59e0b', '#22c55e', '#8b5cf6']

                fig, ax = plt.subplots(figsize=(6.5, 3.2))
                fig.patch.set_alpha(0)
                ax.set_facecolor('none')

                ax.barh(range(4), range_vals, color=range_colors, alpha=0.85, edgecolor='none', zorder=3)

                max_range = max(range_vals) if range_vals else 1
                for i, v in enumerate(range_vals):
                    if v > 0:
                        ax.text(v + max(max_range * 0.02, 0.3), i, f'{v:.1f}',
                                ha='left', va='center', fontsize=9, color='white', fontweight='bold')

                ax.set_yticks(range(4))
                ax.set_yticklabels(range_labels, fontsize=9, color=TEXT_SEC_HEX)
                ax.tick_params(axis='x', colors=TEXT_SEC_HEX, labelsize=8)
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.spines['left'].set_color(BORDER_HEX)
                ax.spines['bottom'].set_color(BORDER_HEX)
                ax.grid(axis='x', alpha=0.1, color=TEXT_SEC_HEX)
                ax.invert_yaxis()
                if max_range > 0:
                    ax.set_xlim(0, max_range * 1.25)

                plt.tight_layout()
                right_chart = make_chart_image(fig, col_w, chart_h_col)
                img.paste(right_chart, (PADDING + col_w + col_gap, y), right_chart)
            else:
                rx = PADDING + col_w + col_gap
                rounded_rect(rx, y, col_w, chart_h_col)
                center_text("Veri yok", rx, y + chart_h_col // 2 - 10, col_w, font_regular, TEXT_SECONDARY)

            y += chart_h_col + 25

            # ===== 5. EN AKTIF KANALLAR =====
            draw.text((PADDING, y), "EN AKTIF KANALLAR", font=font_section, fill=TEXT_PRIMARY)
            y += 32

            chart_h_ch = 220

            if top_channels:
                ch_names = [f"#{c['channel_name'][:25]}" for c in top_channels]
                ch_vals = [c['total_messages'] for c in top_channels]
                ch_colors = [ACCENT_HEX, PURPLE_HEX, CYAN_HEX, GREEN_HEX, AMBER_HEX, RED_HEX]

                fig, ax = plt.subplots(figsize=(13, 3))
                fig.patch.set_alpha(0)
                ax.set_facecolor('none')

                n = len(ch_names)
                ax.barh(range(n), ch_vals, color=ch_colors[:n], alpha=0.85, edgecolor='none', zorder=3)

                max_ch = max(ch_vals) if ch_vals else 1
                for i, v in enumerate(ch_vals):
                    if v > 0:
                        ax.text(v + max(max_ch * 0.02, 1), i, f'{v:,}',
                                ha='left', va='center', fontsize=10, color='white', fontweight='bold')

                ax.set_yticks(range(n))
                ax.set_yticklabels(ch_names, fontsize=10, color=TEXT_SEC_HEX)
                ax.tick_params(axis='x', colors=TEXT_SEC_HEX, labelsize=8)
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.spines['left'].set_color(BORDER_HEX)
                ax.spines['bottom'].set_color(BORDER_HEX)
                ax.grid(axis='x', alpha=0.1, color=TEXT_SEC_HEX)
                ax.invert_yaxis()
                if max_ch > 0:
                    ax.set_xlim(0, max_ch * 1.3)
                ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'{int(x):,}'))

                plt.tight_layout()
                ch_chart = make_chart_image(fig, CW, chart_h_ch)
                img.paste(ch_chart, (PADDING, y), ch_chart)
            else:
                rounded_rect(PADDING, y, CW, chart_h_ch)
                center_text("Bu hafta aktif kanal bulunamad\u0131", PADDING, y + chart_h_ch // 2 - 10, CW, font_regular, TEXT_SECONDARY)

            y += chart_h_ch + 25

            # ===== 6. OZET BILGILER =====
            draw.text((PADDING, y), "\u00d6ZET B\u0130LG\u0130LER", font=font_section, fill=TEXT_PRIMARY)
            y += 32

            mini_gap = 15
            mini_cols = 3
            mini_w = (CW - (mini_cols - 1) * mini_gap) // mini_cols
            mini_h = 65

            online_members = len([m for m in guild.members if m.status != discord.Status.offline])

            TAG_ROLE_ID = 1467145841830789367
            tag_role = guild.get_role(TAG_ROLE_ID)
            tag_count = len(tag_role.members) if tag_role else 0

            mini_cards = [
                ('ONLINE \u00dcYE', f"{online_members}/{guild.member_count}", ACCENT),
                ('MET\u0130N KANALI', str(len(guild.text_channels)), CYAN),
                ('SES KANALI', str(len(guild.voice_channels)), GREEN),
                ('ROL SAYISI', str(len(guild.roles)), PURPLE),
                ('TAG SAH\u0130PLER\u0130', f"{tag_count} ki\u015fi", AMBER),
                ('MODERASYON', f"{mod_actions['total']} i\u015flem", RED),
            ]

            for i, (label, value, color) in enumerate(mini_cards):
                col = i % mini_cols
                row = i // mini_cols
                mx = PADDING + col * (mini_w + mini_gap)
                my = y + row * (mini_h + mini_gap)

                rounded_rect(mx, my, mini_w, mini_h)
                center_text(value, mx, my + 10, mini_w, font_mini_val, color)
                center_text(label, mx, my + 42, mini_w, font_kpi_label, TEXT_SECONDARY)

            rows_count = (len(mini_cards) + mini_cols - 1) // mini_cols
            y += rows_count * (mini_h + mini_gap) + 15

            # ===== FOOTER =====
            draw.line([(PADDING, y), (WIDTH - PADDING, y)], fill=CARD_BORDER, width=1)
            y += 15

            center_text(f"{guild.name}  \u2022  Haftal\u0131k Rapor Sistemi", PADDING, y, CW, font_footer, TEXT_SECONDARY)

            # ===== EXPORT =====
            output = io.BytesIO()
            img.save(output, format='PNG', optimize=True)
            output.seek(0)

            return output

        except Exception as e:
            print(f"Rapor gorseli olusturma hatasi: {e}")
            import traceback
            traceback.print_exc()
            return None

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
            
            # Raporu oluştur ve gönder (2 embed döndürür)
            embeds = await self.create_weekly_report_embed(guild, start_date, end_date)

            # 1. Embed - Genel İstatistikler
            await self.safe_send(
                report_channel,
                content="📊 **HAFTALIK SUNUCU RAPORU** 📊",
                embed=embeds[0]
            )

            # 2. Embed - Yetkili Kadro & Özet
            if len(embeds) > 1:
                await self.safe_send(
                    report_channel,
                    embed=embeds[1]
                )

            # 3. Görsel raporu oluştur ve gönder
            try:
                report_image = await self.create_report_image(guild, start_date, end_date)
                if report_image:
                    file = discord.File(report_image, filename="haftalik_rapor.png")
                    await self.safe_send(report_channel, file=file)
            except Exception as e:
                print(f"Rapor görseli oluşturma/gönderme hatası: {e}")

            # Rapor gönderildikten sonra eski verileri temizle
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
                # Her yetkilinin en son rol atamasını koru
                await cursor.execute('''
                DELETE FROM staff_changes
                WHERE created_at < ?
                AND id NOT IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) as rn
                        FROM staff_changes
                        WHERE action IN ('added', 'promoted', 'demoted')
                    ) WHERE rn = 1
                )
                ''', (cleanup_cutoff.isoformat(),))

                # Eski staff_message_stats kayıtlarını temizle (28 gün öncesi)
                try:
                    cutoff_date_str = cleanup_cutoff.date().isoformat()
                    await cursor.execute('''
                    DELETE FROM staff_message_stats WHERE message_date < ?
                    ''', (cutoff_date_str,))
                except Exception:
                    pass

                # Eski channel_message_stats kayıtlarını temizle (28 gün öncesi)
                try:
                    cutoff_date_str = cleanup_cutoff.date().isoformat()
                    await cursor.execute('''
                    DELETE FROM channel_message_stats WHERE message_date < ?
                    ''', (cutoff_date_str,))
                    print(f"Haftalık rapor - Eski kanal mesaj istatistikleri temizlendi")
                except Exception as e:
                    print(f"Kanal mesaj istatistikleri temizliği hatası: {e}")

                # Eski presence snapshot'larını temizle (14 gün öncesi)
                await cursor.execute('''
                DELETE FROM presence_snapshots WHERE snapshot_time < ?
                ''', (presence_cutoff.isoformat(),))
                
                # Eski staff online session'larını da temizle (2 hafta öncesi)
                staff_online_cutoff = report_start_date - datetime.timedelta(days=14)
                deleted_sessions = await db.cleanup_old_staff_online_sessions(14)
                if deleted_sessions > 0:
                    print(f"Haftalık rapor - {deleted_sessions} eski online session silindi")
                
                # Eski voice activity session'larını temizle (2 hafta öncesi)
                deleted_voice_sessions = await db.cleanup_old_voice_sessions(14)
                if deleted_voice_sessions > 0:
                    print(f"Haftalık rapor - {deleted_voice_sessions} eski voice session silindi")
                
                # Eski özel oda loglarını temizle (28 gün öncesi)
                await cursor.execute('''
                DELETE FROM private_room_logs WHERE created_at < ?
                ''', (cleanup_cutoff.isoformat(),))
                
                await db.connection.commit()
                
                                    # Cleanup completed
                
        except Exception as e:
            print(f"Otomatik temizlik hatası: {e}")
    
    async def create_weekly_report_embed(self, guild, start_date, end_date):
        """Haftalık rapor embed'lerini oluşturur (2 embed döndürür)"""
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
                            'text': f"👢 **Atma** • {action_time} - <@{kick['user_id']}>\n└ Yetkili: <@{kick['moderator_id']}> • Sebep: {reason}"
                        })
                    
                    # Ban işlemleri
                    for ban in moderation_actions['bans']:
                        action_time = ban['action_time'].astimezone(self.turkey_tz).strftime('%d.%m %H:%M')
                        reason = ban['reason'] or "Sebep belirtilmedi"
                        if len(reason) > 50:
                            reason = reason[:47] + "..."
                        all_actions.append({
                            'time': ban['action_time'],
                            'text': f"🔨 **Yasaklama** • {action_time} - <@{ban['user_id']}>\n└ Yetkili: <@{ban['moderator_id']}> • Sebep: {reason}"
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
            
            # === KANAL İSTATİSTİKLERİ - SOHBET KANALLARI ===
            try:
                channel_stats = await db.get_channel_stats_by_period(guild.id, start_date, end_date)
                
                # Sohbet kanalları
                if channel_stats and 'sohbet' in channel_stats:
                    sohbet = channel_stats['sohbet']
                    lines = []
                    
                    # Genel istatistikler
                    total_msg = sohbet['total_messages']
                    active_ch = sohbet['active_channels']
                    avg_users = sohbet['avg_unique_users_per_day']
                    
                    lines.append(f"**📊 Genel Özet**")
                    lines.append(f"• Toplam Mesaj: **{total_msg:,}**")
                    lines.append(f"• Aktif Kanal: **{active_ch}**")
                    lines.append(f"• Günlük Ort. Aktif Kullanıcı: **{avg_users:.1f}**")
                    
                    # En aktif kanallar (top 5)
                    if sohbet['channels']:
                        lines.append(f"\n**🔥 En Aktif Kanallar**")
                        for i, ch in enumerate(sohbet['channels'][:5], 1):
                            ch_name = ch['channel_name']
                            ch_msg = ch['total_messages']
                            percentage = (ch_msg / total_msg * 100) if total_msg > 0 else 0
                            
                            # Emoji'ler
                            if i == 1:
                                emoji = "🥇"
                            elif i == 2:
                                emoji = "🥈"
                            elif i == 3:
                                emoji = "🥉"
                            else:
                                emoji = "▪️"
                            
                            lines.append(f"{emoji} #{ch_name}: **{ch_msg:,}** mesaj ({percentage:.1f}%)")
                    
                    # Günlük dağılım (grafiksel)
                    if sohbet.get('daily_breakdown'):
                        lines.append(f"\n**📅 Günlük Dağılım**")
                        
                        # Türkçe gün isimleri
                        daily_data = sohbet['daily_breakdown']
                        max_daily = max([d['message_count'] for d in daily_data]) if daily_data else 1
                        
                        for day_data in daily_data:
                            date_obj = datetime.datetime.strptime(day_data['date'], '%Y-%m-%d')
                            date_turkey = date_obj.replace(tzinfo=pytz.UTC).astimezone(self.turkey_tz)
                            day_name = date_turkey.strftime('%d.%m (%a)')
                            
                            msg_count = day_data['message_count']
                            bar_length = int((msg_count / max_daily) * 10) if max_daily > 0 else 0
                            bar = "█" * bar_length + "░" * (10 - bar_length)
                            
                            lines.append(f"`{day_name}` {bar} **{msg_count:,}**")
                    
                    embed.add_field(
                        name="💬 Sohbet Kanalları",
                        value="\n".join(lines)[:1024],
                        inline=False
                    )
                else:
                    # Sohbet kanallarında veri yok
                    embed.add_field(
                        name="💬 Sohbet Kanalları",
                        value="Bu hafta sohbet kanallarında aktivite tespit edilmedi.",
                        inline=False
                    )
                    
            except Exception as e:
                print(f"Sohbet kanalı istatistikleri eklenirken hata: {e}")
                embed.add_field(
                    name="💬 Sohbet Kanalları",
                    value=f"Bilgiler alınamadı: {e}",
                    inline=False
                )
            
            # === KANAL İSTATİSTİKLERİ - EĞLENCE KANALLARI ===
            try:
                channel_stats = await db.get_channel_stats_by_period(guild.id, start_date, end_date)
                
                # Eğlence kanalları
                if channel_stats and 'eglence' in channel_stats:
                    eglence = channel_stats['eglence']
                    lines = []
                    
                    # Genel istatistikler
                    total_msg = eglence['total_messages']
                    active_ch = eglence['active_channels']
                    avg_users = eglence['avg_unique_users_per_day']
                    
                    lines.append(f"**📊 Genel Özet**")
                    lines.append(f"• Toplam Mesaj: **{total_msg:,}**")
                    lines.append(f"• Aktif Kanal: **{active_ch}**")
                    lines.append(f"• Günlük Ort. Aktif Kullanıcı: **{avg_users:.1f}**")
                    
                    # En aktif kanallar (top 5)
                    if eglence['channels']:
                        lines.append(f"\n**🔥 En Aktif Kanallar**")
                        for i, ch in enumerate(eglence['channels'][:5], 1):
                            ch_name = ch['channel_name']
                            ch_msg = ch['total_messages']
                            percentage = (ch_msg / total_msg * 100) if total_msg > 0 else 0
                            
                            # Emoji'ler
                            if i == 1:
                                emoji = "🥇"
                            elif i == 2:
                                emoji = "🥈"
                            elif i == 3:
                                emoji = "🥉"
                            else:
                                emoji = "▪️"
                            
                            lines.append(f"{emoji} #{ch_name}: **{ch_msg:,}** mesaj ({percentage:.1f}%)")
                    
                    # Günlük dağılım (grafiksel)
                    if eglence.get('daily_breakdown'):
                        lines.append(f"\n**📅 Günlük Dağılım**")
                        
                        daily_data = eglence['daily_breakdown']
                        max_daily = max([d['message_count'] for d in daily_data]) if daily_data else 1
                        
                        for day_data in daily_data:
                            date_obj = datetime.datetime.strptime(day_data['date'], '%Y-%m-%d')
                            date_turkey = date_obj.replace(tzinfo=pytz.UTC).astimezone(self.turkey_tz)
                            day_name = date_turkey.strftime('%d.%m (%a)')
                            
                            msg_count = day_data['message_count']
                            bar_length = int((msg_count / max_daily) * 10) if max_daily > 0 else 0
                            bar = "█" * bar_length + "░" * (10 - bar_length)
                            
                            lines.append(f"`{day_name}` {bar} **{msg_count:,}**")
                    
                    embed.add_field(
                        name="🎮 Eğlence Kanalları",
                        value="\n".join(lines)[:1024],
                        inline=False
                    )
                else:
                    # Eğlence kanallarında veri yok
                    embed.add_field(
                        name="🎮 Eğlence Kanalları",
                        value="Bu hafta eğlence kanallarında aktivite tespit edilmedi.",
                        inline=False
                    )
                    
            except Exception as e:
                print(f"Eğlence kanalı istatistikleri eklenirken hata: {e}")
                embed.add_field(
                    name="🎮 Eğlence Kanalları",
                    value=f"Bilgiler alınamadı: {e}",
                    inline=False
                )
            
            # Footer ve thumbnail (1. embed)
            embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
            embed.set_footer(
                text=f"{guild.name} • Haftalık Rapor Sistemi (1/2)",
                icon_url=guild.icon.url if guild.icon else None
            )

            # ============================================================
            # 2. EMBED - Yetkili Kadro & Özet Bilgiler
            # ============================================================
            embed2 = discord.Embed(
                title="📊 Haftalık Sunucu Raporu — Yetkili Kadro & Özet",
                color=0x2b82ff,
                timestamp=datetime.datetime.now(self.turkey_tz)
            )

            # === AKTİF YETKİLİ KADRO (Mesaj İstatistikleri, Çevrim İçi Saatleri ve Bump Sayıları) ===
            try:
                # Sadece KURUCU ve YK BAŞKANI hariç tutulacak (tüm diğer yetkililer dahil)
                excluded_role_ids = {
                    1029089723110674463,  # KURUCU
                    1459975838853238897,  # KURUCU YARDIMCISI
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

                # Yetkili rol atama tarihlerini al
                staff_role_dates = await db.get_staff_current_role_dates(guild.id)

                # Veritabanından tüm yetkili mesaj verilerini al
                message_stats = await db.get_top_staff_message_stats(guild.id, start_date, end_date, limit=100)

                # Yetkili çevrim içi saatleri verilerini al
                staff_online_stats = await db.get_staff_online_stats(guild.id, start_date, end_date)

                # Ses kanalı aktivite verilerini al
                voice_activity_stats = await db.get_voice_activity_stats(guild.id, start_date, end_date)

                # Bump istatistiklerini al (haftalık için özel sorgu)
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

                # Ses kanalı saatlerini dictionary'ye çevir
                voice_stats_dict = {stat['user_id']: stat for stat in voice_activity_stats}

                # Yetkili rol hiyerarşisi (yüksekten düşüğe) ve kısa adları
                role_hierarchy = [
                    (1029089731314720798, "YK Üyesi"),
                    (1412843482980290711, "YK Adayı"),
                    (1163918130192580608, "Admin"),
                    (1460021463607152703, "K.Mod"),
                    (1163918107501412493, "Mod"),
                    (1200919832393154680, "Asistan"),
                    (1163918714081644554, "Stajyer"),
                ]

                def get_highest_staff_role(member):
                    """Üyenin en yüksek yetkili rolünü döndürür"""
                    user_role_ids = {r.id for r in member.roles}
                    for role_id, role_name in role_hierarchy:
                        if role_id in user_role_ids:
                            return role_name
                    return "Yetkili"

                def format_role_duration(member_id):
                    """Rol süresini okunabilir formata çevirir"""
                    role_data = staff_role_dates.get(member_id)
                    if not role_data or not role_data['assigned_at']:
                        return None
                    try:
                        assigned_at = datetime.datetime.fromisoformat(role_data['assigned_at'])
                        if assigned_at.tzinfo is None:
                            assigned_at = assigned_at.replace(tzinfo=pytz.UTC)
                        now = datetime.datetime.now(pytz.UTC)
                        delta = now - assigned_at
                        return f"{delta.days} gün"
                    except Exception:
                        return None

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

                    # Ses kanalı saatlerini al (yoksa 0)
                    voice_data = voice_stats_dict.get(member.id, {
                        'total_hours': 0,
                        'total_minutes': 0
                    })

                    # Bump sayısını al (yoksa 0)
                    bump_count = bump_user_stats.get(member.id, 0)

                    # Rol bilgisi ve süre
                    role_name = get_highest_staff_role(member)
                    role_duration = format_role_duration(member.id)
                    role_info = f"{role_name} ({role_duration})" if role_duration else role_name

                    score = self.calculate_staff_score(msg_count, online_data['total_hours'], voice_data['total_hours'], bump_count)
                    results.append((member, msg_count, online_data['total_hours'], online_data['daily_average'], bump_count, voice_data['total_hours'], score, role_info))

                # Puana göre sırala (yüksekten düşüğe)
                results.sort(key=lambda x: x[6], reverse=True)

                if results:
                    all_lines = []
                    for i, (member, msg_count, online_hours, daily_avg, bump_count, voice_hours, score, role_info) in enumerate(results, 1):
                        all_lines.append(f"**{i}.** {member.mention} `{role_info}` • **{score:.0f}** puan | {msg_count} mesaj • {online_hours:.1f}h online • {voice_hours:.1f}h ses • {bump_count} bump")

                    # Satırları 1024 karakter limitine göre field'lara böl
                    chunks = []
                    current_chunk = []
                    current_length = 0

                    for line in all_lines:
                        line_length = len(line) + 1  # +1 for \n
                        if current_length + line_length > 1024 and current_chunk:
                            chunks.append("\n".join(current_chunk))
                            current_chunk = [line]
                            current_length = len(line)
                        else:
                            current_chunk.append(line)
                            current_length += line_length

                    if current_chunk:
                        chunks.append("\n".join(current_chunk))

                    # İlk chunk ana başlıkla, diğerleri devam başlığıyla
                    for idx, chunk in enumerate(chunks):
                        if idx == 0:
                            field_name = f"👥 Aktif Yetkili Kadro ({len(results)} kişi)"
                        else:
                            field_name = f"👥 Yetkili Kadro (devam {idx + 1}/{len(chunks)})"

                        embed2.add_field(
                            name=field_name,
                            value=chunk,
                            inline=False
                        )
                else:
                    embed2.add_field(
                        name="👥 Aktif Yetkili Kadro",
                        value="Bu hafta yetkili kadrosunda aktivite bulunamadı.",
                        inline=False
                    )
            except Exception as e:
                embed2.add_field(
                    name="👥 Aktif Yetkili Kadro",
                    value=f"Bilgiler alınamadı: {e}",
                    inline=False
                )

            # === YETKİLİ DAĞILIMI ===
            try:
                yetkili_rolleri = [
                    ("YK Üyeleri", 1029089731314720798),
                    ("YK Adayları", 1412843482980290711),
                    ("Admin", 1163918130192580608),
                    ("Kıdemli Moderatör", 1460021463607152703),
                    ("Moderatör", 1163918107501412493),
                    ("Asistan", 1200919832393154680),
                    ("Stajyer", 1163918714081644554),
                ]

                dist_lines = []
                toplam_yetkili = 0
                for rol_adi, rol_id in yetkili_rolleri:
                    role = guild.get_role(rol_id)
                    count = len(role.members) if role else 0
                    toplam_yetkili += count
                    dist_lines.append(f"**{rol_adi}:** {count} kişi")

                dist_lines.append(f"\n**Toplam Yetkili:** {toplam_yetkili} kişi")

                embed2.add_field(
                    name="🛡️ Yetkili Dağılımı",
                    value="\n".join(dist_lines),
                    inline=True
                )
            except Exception as e:
                print(f"Yetkili dağılımı eklenirken hata: {e}")

            # === SUNUCU BİLGİLERİ ===
            online_members = len([m for m in guild.members if m.status != discord.Status.offline])

            # Tag sahiplerini say (HRN tag rolü)
            TAG_ROLE_ID = 1467145841830789367
            tag_role = guild.get_role(TAG_ROLE_ID)
            tag_count = len(tag_role.members) if tag_role else 0

            embed2.add_field(
                name="ℹ️ Genel Bilgiler",
                value=f"**Online Üye:** {online_members}/{guild.member_count}\n"
                      f"**Metin Kanalı:** {len(guild.text_channels)}\n"
                      f"**Ses Kanalı:** {len(guild.voice_channels)}\n"
                      f"**Rol Sayısı:** {len(guild.roles)}\n"
                      f"**Tag Sahipleri:** {tag_count} kişi",
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

                embed2.add_field(
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
                embed2.add_field(
                    name="🕐 Saatlik Aktif Üye Ortalamaları",
                    value="\n".join(lines),
                    inline=True
                )

            # Footer ve thumbnail (2. embed)
            embed2.set_thumbnail(url=guild.icon.url if guild.icon else None)
            embed2.set_footer(
                text=f"{guild.name} • Haftalık Rapor Sistemi (2/2)",
                icon_url=guild.icon.url if guild.icon else None
            )

            return [embed, embed2]

        except Exception as e:
            print(f"Rapor embed oluşturma hatası: {e}")
            # Hata durumunda basit embed döndür
            return [discord.Embed(
                title="❌ Rapor Hatası",
                description="Haftalık rapor oluşturulurken bir hata oluştu.",
                color=discord.Color.red()
            )]


async def setup(bot):
    cog = WeeklyReports(bot)
    await bot.add_cog(cog)
    # Command grupları __init__ metodunda ekleniyor