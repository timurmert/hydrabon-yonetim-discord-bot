import discord
import datetime
import pytz
from discord.ext import commands
from typing import Optional, Union
import asyncio
import re
import random
from database import get_db

class ServerLogs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.role_position_updates = {}  # Guild ID: {timestamp: [(role, old_pos, new_pos)]}
        self.position_update_delay = 2  # 2 saniye bekle
        self.log_channel = None
        self.target_guild_id = 1029088146752815138  # İzlenmeyecek sunucu ID'si (Davet korumasında HydRaboN hariç tutmak için)
        self.alert_channel_id = 1362825644550914263  # Uyarı gönderilecek kanal ID'si (Yetkili sohbet)
        # Log kategorileri (mesaj silme cezaları bu kategorilerde tetiklenir)
        self.log_category_ids = {1217523779471937547, 1281779525658742784}
        # YK sohbet kanal ID'si (uyarı buraya gidecek)
        self.yk_sohbet_channel_id = 1362825668965957845
        
        # Yetkili rol ID'leri
        self.yetkili_rolleri = {
            "STAJYER": 1163918714081644554,
            "ASİSTAN": 1200919832393154680,
            "MODERATÖR": 1163918107501412493,
            "ADMİN": 1163918130192580608,
            "YÖNETİM KURULU ADAYLARI": 1412843482980290711,
            "YÖNETİM KURULU ÜYELERİ": 1029089731314720798,
            "YÖNETİM KURULU BAŞKANI": 1029089727061692522,
            "KURUCU": 1029089723110674463
        }
        
        # Performans için compiled regex pattern
        self.invite_pattern = re.compile(
            r'(?:https?://)?(?:www\.)?(?:discord\.gg/|discordapp\.com/invite/|discord\.com/invite/)([a-zA-Z0-9]+)', 
            re.IGNORECASE
        )
        
        # Yetkili rol ID'lerini set olarak cache'le
        self.yetkili_role_ids = set(self.yetkili_rolleri.values())
        
        # YK rol ID'si
        self.yk_role_id = 1029089731314720798  # YÖNETİM KURULU ÜYELERİ
        self.turkey_tz = pytz.timezone('Europe/Istanbul')
        
        # Online session tracking için cache
        self.staff_online_cache = {}  # user_id: {'status': str, 'last_update': datetime}
        
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda aktif online yetkilileri tespit et"""
        await self._initialize_staff_online_sessions()
        
    async def _initialize_staff_online_sessions(self):
        """Bot başladığında mevcut online yetkilileri tespit eder"""
        try:
            await asyncio.sleep(3)  # Bot tamamen hazır olana kadar bekle
            
            for guild in self.bot.guilds:
                db = await get_db()
                
                # Önce tüm aktif session'ları sonlandır (bot restart)
                await db.end_all_staff_sessions(guild.id)
                
                # Şu anda online olan yetkilileri tespit et
                online_statuses = {discord.Status.online, discord.Status.idle, discord.Status.dnd}
                
                for member in guild.members:
                    if member.bot:
                        continue
                        
                    user_role_ids = {role.id for role in member.roles}
                    is_staff = bool(user_role_ids.intersection(self.yetkili_role_ids))
                    
                    if is_staff and member.status in online_statuses:
                        status_str = str(member.status)
                        await db.start_staff_online_session(guild.id, member.id, member.display_name, status_str)
                        self.staff_online_cache[member.id] = {
                            'status': status_str,
                            'last_update': datetime.datetime.now(self.turkey_tz)
                        }
                        
        except Exception as e:
            print(f"Staff online session initialization hatası: {e}")
        
    async def _handle_staff_status_change(self, after, before):
        """Yetkili durum değişikliklerini handle eder ve session tracking yapar"""
        try:
            # Status değişikliği kontrol et
            if before.status == after.status:
                return
            
            user_id = after.id
            guild_id = after.guild.id
            username = after.display_name
            
            # Online statuslar: online, idle, dnd
            online_statuses = {discord.Status.online, discord.Status.idle, discord.Status.dnd}
            
            was_online = before.status in online_statuses
            is_online = after.status in online_statuses
            
            db = await get_db()
            
            # Online'dan offline'a geçiş
            if was_online and not is_online:
                await db.end_staff_online_session(guild_id, user_id)
                # Cache'den kaldır
                if user_id in self.staff_online_cache:
                    del self.staff_online_cache[user_id]
            
            # Offline'dan online'a geçiş
            elif not was_online and is_online:
                status_str = str(after.status)
                await db.start_staff_online_session(guild_id, user_id, username, status_str)
                # Cache'e ekle
                self.staff_online_cache[user_id] = {
                    'status': status_str,
                    'last_update': datetime.datetime.now(self.turkey_tz)
                }
            
            # Online içinde durum değişikliği (online -> idle, idle -> dnd vs.)
            elif was_online and is_online and before.status != after.status:
                # Mevcut session'ı sonlandır ve yenisini başlat
                await db.end_staff_online_session(guild_id, user_id)
                status_str = str(after.status)
                await db.start_staff_online_session(guild_id, user_id, username, status_str)
                # Cache'i güncelle
                self.staff_online_cache[user_id] = {
                    'status': status_str,
                    'last_update': datetime.datetime.now(self.turkey_tz)
                }
                
        except Exception as e:
            # Silent fail - performansı etkilemeyecek şekilde
            print(f"Staff status tracking hatası: {e}")
            pass

    async def get_log_channel(self, guild):
        """Sunucudaki log kanalını bulur ve döndürür"""
        if self.log_channel is not None:
            return self.log_channel
            
        # Kanal adına göre log kanalını bul
        log_channel = discord.utils.get(guild.channels, name="sunucu-log")
        
        # Eğer kanal yoksa, None döndür
        self.log_channel = log_channel
        return log_channel

    async def send_log_embed(self, guild, embed):
        """Log kanalına embed mesaj gönderir - Non-blocking güvenli sistem"""
        channel = await self.get_log_channel(guild)
        if channel is None:
            return
        
        # Fire-and-forget: Diğer işlemleri bloklamaz
        asyncio.create_task(self.safe_send(channel, embed=embed))

    async def safe_send(self, channel, content=None, embed=None, allowed_mentions=None, max_retries=3):
        """Güvenli mesaj gönderme fonksiyonu - Retry sistemi ile"""
        if not channel:
            return None
            
        for attempt in range(max_retries):
            try:
                if content and embed:
                    return await channel.send(content=content, embed=embed, allowed_mentions=allowed_mentions)
                elif content:
                    return await channel.send(content=content, allowed_mentions=allowed_mentions)
                elif embed:
                    return await channel.send(embed=embed, allowed_mentions=allowed_mentions)
                else:
                    return None
                    
            except discord.Forbidden:
                # Bot yetkisi yok, tekrar deneme
                return None
                
            except discord.HTTPException as e:
                # Rate limiting ve API hatalarını yakala
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
                        print(f"Güvenli mesaj gönderme hatası (son deneme): {e}")
                        return None
                        
                elif e.status == 400:  # Bad request
                    print(f"Güvenli mesaj gönderme hatası (kötü istek): {e}")
                    return None
                    
                else:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1 + random.uniform(0.1, 0.5))
                        continue
                    else:
                        print(f"Güvenli mesaj gönderme hatası: {e}")
                        return None
                        
            except (asyncio.TimeoutError, OSError) as e:
                if attempt < max_retries - 1:
                    delay = min((2 ** attempt) + random.uniform(0.5, 1.5), 20)
                    await asyncio.sleep(delay)
                    continue
                else:
                    print(f"Güvenli mesaj gönderme bağlantı hatası: {e}")
                    return None
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 + random.uniform(0.1, 1.0))
                    continue
                else:
                    print(f"Güvenli mesaj gönderme beklenmeyen hata: {e}")
                    return None
        
        return None

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Silinen mesajları loglar"""
        if message.author.bot and not message.channel.category_id in self.log_category_ids:
            return  # Bot mesajlarını loglama
            
        if not message.guild:
            return  # Özel mesajları loglama
            
        # Embed oluştur
        embed = discord.Embed(
            title="Mesaj Silindi",
            description=f"**Kanal:** {message.channel.mention} #{message.channel.name} ({message.channel.id})\n"
                        f"**Yazar:** {message.author.mention} ({message.author.name})\n"
                        f"**Mesaj ID:** {message.id}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        # Mesaj içeriği
        if message.content:
            # Uzun mesajları kısalt
            content = message.content
            if len(content) > 1024:
                content = content[:1021] + "..."
                
            embed.add_field(name="İçerik", value=content, inline=False)
        
        # İşlemi yapanı belirlemeye çalış (audit log)
        executor_user = None
        try:
            executor_user = await self.get_audit_log_executor(message.guild, discord.AuditLogAction.message_delete, message.author.id)
        except Exception:
            executor_user = None
        if executor_user:
            embed.add_field(name="İşlemi Yapan", value=f"{executor_user.mention} ({executor_user.id})", inline=False)
        else:
            # Eğer silme işlemini yapan belirlenemezse, mesajın yazarını silen kişi olarak ata
            embed.add_field(name="İşlemi Yapan", value=f"{message.author.mention} ({message.author.id})", inline=False)
        
        # Eklentileri göster
        if message.attachments:
            files = []
            for i, attachment in enumerate(message.attachments):
                files.append(f"[{attachment.filename}]({attachment.url})")
                if i >= 9:  # En fazla 10 eklenti göster
                    files.append(f"... ve {len(message.attachments) - 10} daha fazla")
                    break
                    
            embed.add_field(name="Eklentiler", value="\n".join(files), inline=False)
        
        # Footer bilgisi
        embed.set_footer(text=f"Kullanıcı ID: {message.author.id}")
        
        # Kullanıcı avatarı
        embed.set_thumbnail(url=message.author.display_avatar.url)
        
        await self.send_log_embed(message.guild, embed)

        # Eğer silinen mesaj belirlenen log kategorilerinden birinde ise, silen kişiyi tespit edip işlem yap
        try:
            category_id = getattr(message.channel, 'category_id', None)
        except Exception:
            category_id = None

        if category_id and category_id in self.log_category_ids:
            deleter_member = None
            is_kurucu = False
            try:
                # Audit log'tan mesajı silen moderatörü bul (kanal ve hedef kullanıcı eşleşmeli)
                async for entry in message.guild.audit_logs(action=discord.AuditLogAction.message_delete, limit=6):
                    # Hedef kullanıcı (mesaj sahibi) eşleşmesi (opsiyonel ama doğruluk için)
                    if getattr(entry, 'target', None) and hasattr(entry.target, 'id'):
                        if entry.target.id != message.author.id:
                            continue
                    # Kanal eşleşmesi
                    extra = getattr(entry, 'extra', None)
                    if extra and getattr(extra, 'channel', None):
                        if extra.channel.id != message.channel.id:
                            continue
                    # Zaman penceresi (son 30 sn)
                    time_diff = (datetime.datetime.now(datetime.timezone.utc) - entry.created_at).total_seconds()
                    if time_diff > 30:
                        continue
                    # Silen kullanıcıyı üye olarak al
                    if entry.user:
                        deleter_member = entry.user if isinstance(entry.user, discord.Member) else message.guild.get_member(entry.user.id)
                    break
            except (discord.Forbidden, discord.HTTPException):
                deleter_member = None

            # Rollerini kaldır (kurucu hariç), bot ve None durumlarını atla
            if deleter_member and not deleter_member.bot:
                kurucu_role_id = self.yetkili_rolleri.get("KURUCU")
                is_kurucu = any(role.id == kurucu_role_id for role in deleter_member.roles) if kurucu_role_id else False
                if not is_kurucu:
                    roles_to_remove = [
                        role for role in deleter_member.roles
                        if role != message.guild.default_role and (not kurucu_role_id or role.id != kurucu_role_id)
                    ]
                    if roles_to_remove:
                        # Rolleri pozisyonuna göre sırala (en yüksekten en düşüğe)
                        roles_to_remove.sort(key=lambda r: r.position, reverse=True)
                        
                        # Rolleri tek tek kaldır
                        for role in roles_to_remove:
                            try:
                                await deleter_member.remove_roles(role, reason="Log kategorisinde mesaj silme tespit edildi")
                                # Kısa bir bekleme süresi ekle (rate limiting önleme)
                                await asyncio.sleep(0.5)
                            except (discord.Forbidden, discord.HTTPException):
                                # Hata durumunda devam et, diğer rolleri kaldırmaya çalış
                                continue

            # YK-sohbet kanalına @everyone ile uyarı gönder
            warn_channel = self.bot.get_channel(self.yk_sohbet_channel_id) or message.guild.get_channel(self.yk_sohbet_channel_id)
            if not is_kurucu and warn_channel:
                warn_text = "@everyone DİKKAT: Log kategorilerinden birinde mesaj silme tespit edildi."
                if deleter_member:
                    warn_text += f" İşlemi yapan: {deleter_member.mention} ({deleter_member.id})."
                else:
                    # Eğer silen kişi belirlenemezse, mesaj yazarını göster
                    warn_text += f" İşlemi yapan: {message.author.mention} ({message.author.id})."

                # Silinen mesajın özet embed'i (özellikle log embed'leri için)
                deleted_summary = discord.Embed(
                    title="Silinen Log Mesajı",
                    description=f"**Kanal:** {message.channel.mention} #{message.channel.name} ({message.channel.id})\n"
                                f"**Mesaj ID:** {message.id}",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(self.turkey_tz)
                )

                # Metin içeriği varsa ekle
                if message.content:
                    text_content = message.content
                    if len(text_content) > 1000:
                        text_content = text_content[:997] + "..."
                    deleted_summary.add_field(name="Metin İçeriği", value=f"```{text_content}```", inline=False)

                # Embed içeriği varsa ilk embed üzerinden özetle
                if message.embeds:
                    orig = message.embeds[0]
                    orig_title = getattr(orig, 'title', None)
                    orig_desc = getattr(orig, 'description', None)

                    if orig_title:
                        if len(orig_title) > 1024:
                            orig_title = orig_title[:1021] + "..."
                        deleted_summary.add_field(name="Log Başlık", value=orig_title, inline=False)

                    if orig_desc:
                        if len(orig_desc) > 1024:
                            orig_desc = orig_desc[:1021] + "..."
                        deleted_summary.add_field(name="Log Açıklama", value=orig_desc, inline=False)

                    # Embed alanlarından ilk 5 tanesini ekle
                    try:
                        fields = getattr(orig, 'fields', []) or []
                        for idx, fld in enumerate(fields[:5]):
                            fname = getattr(fld, 'name', f"Alan {idx+1}") or f"Alan {idx+1}"
                            fval = getattr(fld, 'value', "") or ""
                            if len(fname) > 256:
                                fname = fname[:253] + "..."
                            if len(fval) > 1024:
                                fval = fval[:1021] + "..."
                            deleted_summary.add_field(name=fname, value=fval, inline=False)
                        if len(fields) > 5:
                            deleted_summary.add_field(name="Not", value=f"Toplam {len(fields)} alan vardı, ilk 5'i gösterildi.", inline=False)
                    except Exception:
                        pass

                    # Çoklu embed bilgisi
                    if len(message.embeds) > 1:
                        deleted_summary.add_field(name="Not", value=f"Bu mesajda {len(message.embeds)} embed vardı, ilki özetlendi.", inline=False)

                deleted_summary.set_footer(text=f"Silinen mesajı özetler")

                await self.safe_send(
                    warn_channel,
                    content=warn_text,
                    embed=deleted_summary,
                    allowed_mentions=discord.AllowedMentions(everyone=True)
                )

    @commands.Cog.listener()
    async def on_message(self, message):
        """Yetkili mesaj sayımlarını toplar (Kurucu, YK Başkanı hariç - YK Üyeleri ve Adayları dahil)."""
        try:
            if message.author.bot or not message.guild:
                return
            # Yetkili mi?
            user_role_ids = {role.id for role in message.author.roles}
            if not user_role_ids & set(self.yetkili_rolleri.values()):
                return
            # Sadece en üst yönetim hariç: Kurucu, YK Başkanı (YK Üyeleri ve Adayları dahil)
            excluded = {
                self.yetkili_rolleri.get("KURUCU"),
                self.yetkili_rolleri.get("YÖNETİM KURULU BAŞKANI"),
            }
            if any(rid in user_role_ids for rid in excluded if rid):
                return
            # Sayaç artır
            db = await get_db()
            created_iso = message.created_at.replace(tzinfo=datetime.timezone.utc).isoformat() if message.created_at else datetime.datetime.now(datetime.timezone.utc).isoformat()
            await db.increment_staff_message(message.guild.id, message.author.id, message.author.name, created_iso)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        """Düzenlenen mesajları loglar"""
        if before.author.bot:
            return  # Bot mesajlarını loglama
            
        if not before.guild:
            return  # Özel mesajları loglama
            
        # İçerik değişmediyse (sadece embed yüklendi vs.) loglama
        if before.content == after.content:
            return
            
        # Embed oluştur
        embed = discord.Embed(
            title="Mesaj Düzenlendi",
            description=f"**Kanal:** {before.channel.mention} #{before.channel.name} ({before.channel.id})\n"
                        f"**Yazar:** {before.author.mention} ({before.author.name})\n"
                        f"**Mesaj ID:** {before.id}\n"
                        f"**Bağlantı:** [Mesaja Git]({after.jump_url})",
            color=discord.Color.gold(),
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        # Eski ve yeni içerik
        if before.content:
            content = before.content
            if len(content) > 1024:
                content = content[:1021] + "..."
            embed.add_field(name="Eski İçerik", value=content, inline=False)
            
        if after.content:
            content = after.content
            if len(content) > 1024:
                content = content[:1021] + "..."
            embed.add_field(name="Yeni İçerik", value=content, inline=False)
        
        # İşlemi yapan (mesaj sahibi kendi düzenledi)
        embed.add_field(name="İşlemi Yapan", value=f"{before.author.mention} ({before.author.name})", inline=False)
        
        # Footer bilgisi
        embed.set_footer(text=f"Kullanıcı ID: {before.author.id}")
        
        # Kullanıcı avatarı
        embed.set_thumbnail(url=before.author.display_avatar.url)
        
        await self.send_log_embed(before.guild, embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Ses kanalı hareketlerini loglar"""
        if member.bot:
            return  # Bot hareketlerini loglama
            
        # Embed oluştur
        embed = discord.Embed(
            description=f"**Kullanıcı:** {member.mention} ({member.name})",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        # Kullanıcı avatarı
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # Footer bilgisi
        embed.set_footer(text=f"Kullanıcı ID: {member.id}")
        
        # Ses kanalı bağlantı durumları
        if before.channel is None and after.channel is not None:
            # Ses kanalına katılma
            embed.title = "Ses Kanalına Katıldı"
            embed.description = f"**Kullanıcı:** {member.mention} ({member.name})\n" \
                              f"**Kanal:** {after.channel.mention} #{after.channel.name} ({after.channel.id})"
        
        elif before.channel is not None and after.channel is None:
            # Ses kanalından ayrılma
            embed.title = "Ses Kanalından Ayrıldı"
            embed.description = f"**Kullanıcı:** {member.mention} ({member.name})\n" \
                              f"**Kanal:** {before.channel.mention} #{before.channel.name} ({before.channel.id})"
        
        elif before.channel != after.channel:
            # Ses kanalı değiştirme
            embed.title = "Ses Kanalı Değiştirildi"
            embed.description = f"**Kullanıcı:** {member.mention} ({member.name})\n" \
                              f"**Önceki Kanal:** {before.channel.mention} #{before.channel.name} ({before.channel.id})\n" \
                              f"**Yeni Kanal:** {after.channel.mention} #{after.channel.name} ({after.channel.id})"
        
        # Ses durumu değişiklikleri
        if before.self_mute != after.self_mute:
            if after.self_mute:
                state = "Mikrofon Kapatıldı"
            else:
                state = "Mikrofon Açıldı"
                
            embed.add_field(name="Ses Durumu", value=state, inline=True)
            
        if before.self_deaf != after.self_deaf:
            if after.self_deaf:
                state = "Kulaklık Kapatıldı"
            else:
                state = "Kulaklık Açıldı"
                
            embed.add_field(name="Kulaklık Durumu", value=state, inline=True)
            
        if before.self_stream != after.self_stream:
            if after.self_stream:
                state = "Yayın Başlatıldı"
            else:
                state = "Yayın Sonlandırıldı"
                
            embed.add_field(name="Yayın Durumu", value=state, inline=True)
            
        if before.self_video != after.self_video:
            if after.self_video:
                state = "Kamera Açıldı"
            else:
                state = "Kamera Kapatıldı"
                
            embed.add_field(name="Kamera Durumu", value=state, inline=True)
            
        # Eğer bir değişiklik yoksa gönderme
        if embed.title:
            # İşlemi yapan (kullanıcının kendisi)
            embed.add_field(name="İşlemi Yapan", value=f"{member.mention} ({member.name})", inline=False)
            await self.send_log_embed(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Sunucuya katılan üyeleri loglar"""
        # Hesap yaşını hesapla
        created_at = member.created_at
        created_ago = (datetime.datetime.now(self.turkey_tz) - created_at.astimezone(self.turkey_tz)).days
        
        # Embed oluştur
        embed = discord.Embed(
            title="Üye Katıldı",
            description=f"**Kullanıcı:** {member.mention} ({member.name})\n"
                        f"**ID:** {member.id}\n"
                        f"**Hesap Oluşturulma:** {discord.utils.format_dt(created_at, style='R')} ({created_ago} gün önce)",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        # Kullanıcı avatarı
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # İşlemi yapan (kullanıcının kendisi)
        embed.add_field(name="İşlemi Yapan", value=f"{member.mention} ({member.name})", inline=False)
        
        await self.send_log_embed(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Sunucudan ayrılan üyeleri loglar"""
        # Katılma bilgisini al
        joined_at = member.joined_at
        if joined_at:
            joined_ago = (datetime.datetime.now(self.turkey_tz) - joined_at.astimezone(self.turkey_tz)).days
            joined_text = f"{discord.utils.format_dt(joined_at, style='R')} ({joined_ago} gün önce)"
        else:
            joined_text = "Bilinmiyor"
        
        # Embed oluştur
        embed = discord.Embed(
            title="Üye Ayrıldı",
            description=f"**Kullanıcı:** {member.mention} ({member.name})\n"
                        f"**ID:** {member.id}\n"
                        f"**Katılma Tarihi:** {joined_text}\n"
                        f"**Rol Sayısı:** {len(member.roles) - 1}",  # @everyone rolünü çıkart
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        # Kullanıcının rollerini listele (eğer varsa)
        if len(member.roles) > 1:  # @everyone dışında rol varsa
            roles = [role.mention for role in reversed(member.roles) if role.name != "@everyone"]
            roles_str = ", ".join(roles)
            
            if len(roles_str) > 1024:
                roles_str = roles_str[:1021] + "..."
                
            embed.add_field(name="Roller", value=roles_str, inline=False)
        
        # Kullanıcı avatarı
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # İşlemi yapan (kullanıcının kendisi)
        embed.add_field(name="İşlemi Yapan", value=f"{member.mention} ({member.name})", inline=False)
        
        await self.send_log_embed(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Üye güncellemelerini loglar (Nickname, rol değişiklikleri)"""
        if before.display_name != after.display_name:
            # Kullanıcı adı değişikliği
            embed = discord.Embed(
                title="Kullanıcı Adı Değiştirildi",
                description=f"**Kullanıcı:** {after.mention} ({after.name})",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(self.turkey_tz)
            )
            
            embed.add_field(name="Eski İsim", value=before.display_name, inline=True)
            embed.add_field(name="Yeni İsim", value=after.display_name, inline=True)
            
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.set_footer(text=f"Kullanıcı ID: {after.id}")
            
            # İşlemi yapanı belirlemeye çalış (audit log; bulunamazsa kullanıcı kendi değişikliği olabilir)
            executor_user = None
            try:
                executor_user = await self.get_audit_log_executor(after.guild, discord.AuditLogAction.member_update, after.id)
            except Exception:
                executor_user = None
            if executor_user:
                embed.add_field(name="İşlemi Yapan", value=f"{executor_user.mention} ({executor_user.name})", inline=False)
            else:
                # Kullanıcı kendisi yapmış olabilir, yine de standartlaştırma için Belirlenemedi yaz
                embed.add_field(name="İşlemi Yapan", value="Belirlenemedi", inline=False)
            
            await self.send_log_embed(after.guild, embed)
            
        # Rol değişiklikleri
        if before.roles != after.roles:
            # Eklenen/çıkarılan rolleri bul
            added_roles = [role for role in after.roles if role not in before.roles]
            removed_roles = [role for role in before.roles if role not in after.roles]
            
            if added_roles:
                # Audit log'dan kimin eklediğini bul
                executor = await self.get_audit_log_executor(after.guild, discord.AuditLogAction.member_role_update, after.id)
                executor_info = await self.format_executor_info(executor)
                
                # Rol ekleme
                embed = discord.Embed(
                    title="Kullanıcıya Rol Eklendi",
                    description=f"**Kullanıcı:** {after.mention} ({after.name})\n"
                                f"{executor_info}",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.now(self.turkey_tz)
                )
                
                roles_text = ", ".join([role.mention for role in added_roles])
                embed.add_field(name="Eklenen Roller", value=roles_text, inline=False)
                
                embed.set_thumbnail(url=after.display_avatar.url)
                embed.set_footer(text=f"Kullanıcı ID: {after.id}")
                
                if executor:
                    embed.add_field(name="İşlemi Yapan", value=f"{executor.mention} ({executor.name})", inline=False)
                else:
                    embed.add_field(name="İşlemi Yapan", value="Belirlenemedi", inline=False)
                
                await self.send_log_embed(after.guild, embed)
                
            if removed_roles:
                # Audit log'dan kimin kaldırdığını bul
                executor = await self.get_audit_log_executor(after.guild, discord.AuditLogAction.member_role_update, after.id)
                executor_info = await self.format_executor_info(executor)
                
                # Rol çıkarma
                embed = discord.Embed(
                    title="Kullanıcıdan Rol Kaldırıldı",
                    description=f"**Kullanıcı:** {after.mention} ({after.name})\n"
                                f"{executor_info}",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(self.turkey_tz)
                )
                
                roles_text = ", ".join([role.mention for role in removed_roles])
                embed.add_field(name="Kaldırılan Roller", value=roles_text, inline=False)
                
                embed.set_thumbnail(url=after.display_avatar.url)
                embed.set_footer(text=f"Kullanıcı ID: {after.id}")
                
                if executor:
                    embed.add_field(name="İşlemi Yapan", value=f"{executor.mention} ({executor.name})", inline=False)
                else:
                    embed.add_field(name="İşlemi Yapan", value="Belirlenemedi", inline=False)
                
                await self.send_log_embed(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        """Yeni oluşturulan kanalları loglar"""
        # Audit log'dan kimin oluşturduğunu bul
        executor = await self.get_audit_log_executor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        executor_info = await self.format_executor_info(executor)
        
        embed = discord.Embed(
            title="Kanal Oluşturuldu",
            description=f"**Kanal:** {channel.mention} #{channel.name} ({channel.id})\n"
                        f"**Kanal Türü:** {str(channel.type).replace('_', ' ').title()}\n"
                        f"{executor_info}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        # Kategori bilgisi
        if hasattr(channel, 'category') and channel.category:
            embed.add_field(name="Kategori", value=channel.category.name, inline=False)
        
        if executor:
            embed.add_field(name="İşlemi Yapan", value=f"{executor.mention} ({executor.name})", inline=False)
        else:
            embed.add_field(name="İşlemi Yapan", value="Belirlenemedi", inline=False)
        await self.send_log_embed(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Silinen kanalları loglar"""
        # Audit log'dan kimin sildiğini bul
        executor = await self.get_audit_log_executor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        executor_info = await self.format_executor_info(executor)
        
        embed = discord.Embed(
            title="Kanal Silindi",
            description=f"**Kanal:** #{channel.name} ({channel.id})\n"
                        f"**Kanal Türü:** {str(channel.type).replace('_', ' ').title()}\n"
                        f"{executor_info}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        # Kategori bilgisi
        if hasattr(channel, 'category') and channel.category:
            embed.add_field(name="Kategori", value=channel.category.name, inline=False)
        
        if executor:
            embed.add_field(name="İşlemi Yapan", value=f"{executor.mention} ({executor.name})", inline=False)
        else:
            embed.add_field(name="İşlemi Yapan", value="Belirlenemedi", inline=False)
        await self.send_log_embed(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        """Güncellenen kanalları loglar"""
        changes = []
        
        # İsim değişikliği
        if before.name != after.name:
            changes.append(f"**İsim:** {before.name} → {after.name}")
        
        # Konu değişikliği (metin kanalları için)
        if hasattr(before, 'topic') and hasattr(after, 'topic') and before.topic != after.topic:
            before_topic = before.topic or "Yok"
            after_topic = after.topic or "Yok"
            
            if len(before_topic) > 300:
                before_topic = before_topic[:297] + "..."
            if len(after_topic) > 300:
                after_topic = after_topic[:297] + "..."
                
            changes.append(f"**Konu:** {before_topic} → {after_topic}")
        
        # Kategori değişikliği
        if hasattr(before, 'category') and hasattr(after, 'category') and before.category != after.category:
            before_category = before.category.name if before.category else "Yok"
            after_category = after.category.name if after.category else "Yok"
            changes.append(f"**Kategori:** {before_category} → {after_category}")
        
        # Yavaş mod değişikliği
        if hasattr(before, 'slowmode_delay') and hasattr(after, 'slowmode_delay') and before.slowmode_delay != after.slowmode_delay:
            before_delay = f"{before.slowmode_delay} saniye" if before.slowmode_delay else "Kapalı"
            after_delay = f"{after.slowmode_delay} saniye" if after.slowmode_delay else "Kapalı"
            changes.append(f"**Yavaş Mod:** {before_delay} → {after_delay}")
        
        # NSFW değişikliği
        if hasattr(before, 'nsfw') and hasattr(after, 'nsfw') and before.nsfw != after.nsfw:
            changes.append(f"**NSFW:** {'Açık' if before.nsfw else 'Kapalı'} → {'Açık' if after.nsfw else 'Kapalı'}")
        
        if changes:
            # Audit log'dan kimin güncellediğini bul
            executor = await self.get_audit_log_executor(after.guild, discord.AuditLogAction.channel_update, after.id)
            executor_info = await self.format_executor_info(executor)
            
            embed = discord.Embed(
                title="Kanal Güncellendi",
                description=f"**Kanal:** {after.mention} #{after.name} ({after.id})\n"
                            f"{executor_info}",
                color=discord.Color.gold(),
                timestamp=datetime.datetime.now(self.turkey_tz)
            )
            
            # Değişiklikleri ekle
            embed.add_field(name="Değişiklikler", value="\n".join(changes), inline=False)
            
            if executor:
                embed.add_field(name="İşlemi Yapan", value=f"{executor.mention} ({executor.name})", inline=False)
            else:
                embed.add_field(name="İşlemi Yapan", value="Belirlenemedi", inline=False)
            await self.send_log_embed(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        """Yeni oluşturulan rolleri loglar"""
        # Audit log'dan kimin oluşturduğunu bul
        executor = await self.get_audit_log_executor(role.guild, discord.AuditLogAction.role_create, role.id)
        executor_info = await self.format_executor_info(executor)
        
        embed = discord.Embed(
            title="Rol Oluşturuldu",
            description=f"**Rol:** {role.mention} ({role.name})\n"
                        f"**Rol ID:** {role.id}\n"
                        f"{executor_info}",
            color=role.color,
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        # Rol özellikleri
        permissions = []
        if role.permissions.administrator:
            permissions.append("Yönetici")
        if role.permissions.ban_members:
            permissions.append("Üye Yasaklama")
        if role.permissions.kick_members:
            permissions.append("Üye Atma")
        if role.permissions.manage_channels:
            permissions.append("Kanalları Yönetme")
        if role.permissions.manage_guild:
            permissions.append("Sunucuyu Yönetme")
        if role.permissions.manage_messages:
            permissions.append("Mesajları Yönetme")
        if role.permissions.manage_roles:
            permissions.append("Rolleri Yönetme")
        if role.permissions.mention_everyone:
            permissions.append("@everyone Etiketleme")
        
        if permissions:
            embed.add_field(name="Önemli Yetkiler", value=", ".join(permissions), inline=False)
        
        if executor:
            embed.add_field(name="İşlemi Yapan", value=f"{executor.mention} ({executor.name})", inline=False)
        else:
            embed.add_field(name="İşlemi Yapan", value="Belirlenemedi", inline=False)
        await self.send_log_embed(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        """Silinen rolleri loglar"""
        # Audit log'dan kimin sildiğini bul
        executor = await self.get_audit_log_executor(role.guild, discord.AuditLogAction.role_delete, role.id)
        executor_info = await self.format_executor_info(executor)
        
        embed = discord.Embed(
            title="Rol Silindi",
            description=f"**Rol:** {role.name}\n"
                        f"**Rol ID:** {role.id}\n"
                        f"**Renk:** {role.color}\n"
                        f"**Pozisyon:** {role.position}\n"
                        f"{executor_info}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        if executor:
            embed.add_field(name="İşlemi Yapan", value=f"{executor.mention} ({executor.name})", inline=False)
        else:
            embed.add_field(name="İşlemi Yapan", value="Belirlenemedi", inline=False)
        await self.send_log_embed(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        """Güncellenen rolleri loglar"""
        changes = []
        
        # İsim değişikliği
        if before.name != after.name:
            changes.append(f"**İsim:** {before.name} → {after.name}")
        
        # Renk değişikliği
        if before.color != after.color:
            changes.append(f"**Renk:** {before.color} → {after.color}")
        
        # Ayrı gösterme değişikliği
        if before.hoist != after.hoist:
            changes.append(f"**Ayrı Göster:** {'Evet' if before.hoist else 'Hayır'} → {'Evet' if after.hoist else 'Hayır'}")
        
        # Bahsedilebilirlik değişikliği
        if before.mentionable != after.mentionable:
            changes.append(f"**Bahsedilebilir:** {'Evet' if before.mentionable else 'Hayır'} → {'Evet' if after.mentionable else 'Hayır'}")
        
        # Pozisyon değişikliği - toplu güncelleme sistemi
        if before.position != after.position:
            await self.handle_role_position_change(before, after)
            # Pozisyon değişikliğini normal değişikliklerden ayır
            # changes.append(f"**Pozisyon:** {before.position} → {after.position}")
        
        # İzin değişiklikleri
        permission_changes = []
        
        for perm, value in after.permissions:
            before_value = getattr(before.permissions, perm)
            if before_value != value:
                # İzin adını düzgün formata getir
                perm_name = perm.replace('_', ' ').title()
                permission_changes.append(f"**{perm_name}:** {'✅' if before_value else '❌'} → {'✅' if value else '❌'}")
        
        if changes or permission_changes:
            # Audit log'dan kimin güncellediğini bul
            executor = await self.get_audit_log_executor(after.guild, discord.AuditLogAction.role_update, after.id)
            executor_info = await self.format_executor_info(executor)
            
            embed = discord.Embed(
                title="Rol Güncellendi",
                description=f"**Rol:** {after.mention} ({after.name})\n"
                            f"**Rol ID:** {after.id}\n"
                            f"{executor_info}",
                color=after.color,
                timestamp=datetime.datetime.now(self.turkey_tz)
            )
            
            # Genel değişiklikleri ekle
            if changes:
                embed.add_field(name="Genel Değişiklikler", value="\n".join(changes), inline=False)
            
            # İzin değişikliklerini ekle (eğer varsa)
            if permission_changes:
                # İzin değişiklikleri çok uzunsa kısalt
                perm_text = "\n".join(permission_changes)
                if len(perm_text) > 1024:
                    perm_text = perm_text[:1021] + "..."
                    
                embed.add_field(name="İzin Değişiklikleri", value=perm_text, inline=False)
            
            if executor:
                embed.add_field(name="İşlemi Yapan", value=f"{executor.mention} ({executor.name})", inline=False)
            else:
                embed.add_field(name="İşlemi Yapan", value="Belirlenemedi", inline=False)
            await self.send_log_embed(after.guild, embed)
    
    async def handle_role_position_change(self, before, after):
        """Rol pozisyon değişikliklerini toplu olarak işler"""
        guild_id = after.guild.id
        current_time = datetime.datetime.now(self.turkey_tz)
        
        # Guild için dictionary oluştur
        if guild_id not in self.role_position_updates:
            self.role_position_updates[guild_id] = {}
        
        # Mevcut toplu güncelleme var mı kontrol et
        active_update = None
        for timestamp, data in self.role_position_updates[guild_id].items():
            # Son 2 saniye içindeki güncellemeleri kontrol et
            if (current_time - timestamp).total_seconds() < self.position_update_delay:
                active_update = timestamp
                break
        
        if active_update:
            # Mevcut güncellemeye ekle
            self.role_position_updates[guild_id][active_update]["changes"].append((after, before.position, after.position))
        else:
            # Yeni toplu güncelleme başlat
            self.role_position_updates[guild_id][current_time] = {
                "changes": [(after, before.position, after.position)],
                "guild": after.guild
            }
            # 2 saniye sonra gönder
            asyncio.create_task(self.send_role_position_update(guild_id, current_time))
    
    async def send_role_position_update(self, guild_id, timestamp):
        """Toplu rol pozisyon güncellemesini gönderir"""
        await asyncio.sleep(self.position_update_delay)
        
        if guild_id not in self.role_position_updates or timestamp not in self.role_position_updates[guild_id]:
            return
        
        update_data = self.role_position_updates[guild_id][timestamp]
        changes = update_data["changes"]
        guild = update_data["guild"]
        
        # Güncelleme verilerini temizle
        del self.role_position_updates[guild_id][timestamp]
        if not self.role_position_updates[guild_id]:
            del self.role_position_updates[guild_id]
        
        if not changes:
            return
        
        # Audit log'dan kimin yaptığını bul
        executor = await self.get_audit_log_executor(guild, discord.AuditLogAction.role_update)
        executor_info = await self.format_executor_info(executor)
        
        # Tek rol değişikliği ise normal log
        if len(changes) == 1:
            role, old_pos, new_pos = changes[0]
            embed = discord.Embed(
                title="Rol Pozisyonu Değiştirildi",
                description=f"**Rol:** {role.mention} ({role.name})\n"
                            f"**Rol ID:** {role.id}\n"
                            f"{executor_info}",
                color=role.color,
                timestamp=datetime.datetime.now(self.turkey_tz)
            )
            embed.add_field(name="Pozisyon Değişikliği", value=f"**Pozisyon:** {old_pos} → {new_pos}", inline=False)
        else:
            # Çoklu rol değişikliği - toplu log
            embed = discord.Embed(
                title="Çoklu Rol Pozisyonu Değişikliği",
                description=f"**{len(changes)}** rolün pozisyonu değiştirildi:\n"
                            f"{executor_info}",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(self.turkey_tz)
            )
            
            change_text = []
            for role, old_pos, new_pos in changes:
                change_text.append(f"**{role.name}:** {old_pos} → {new_pos}")
            
            # Çok uzunsa kısalt
            full_text = "\n".join(change_text)
            if len(full_text) > 1024:
                # İlk 20 değişikliği göster
                visible_changes = change_text[:20]
                remaining = len(changes) - 20
                full_text = "\n".join(visible_changes)
                if remaining > 0:
                    full_text += f"\n\n*...ve {remaining} rol daha*"
            
            embed.add_field(name="Pozisyon Değişiklikleri", value=full_text, inline=False)
        
        if executor:
            embed.add_field(name="İşlemi Yapan", value=f"{executor.mention} ({executor.name})", inline=False)
        else:
            embed.add_field(name="İşlemi Yapan", value="Belirlenemedi", inline=False)
        await self.send_log_embed(guild, embed)
    
    async def get_audit_log_executor(self, guild, action_type, target_id=None, limit=5):
        """Audit log'dan işlemi yapan kişiyi bulur"""
        try:
            async for entry in guild.audit_logs(action=action_type, limit=limit):
                # Hedef ID kontrolü (varsa)
                if target_id and hasattr(entry, 'target') and entry.target:
                    if hasattr(entry.target, 'id') and entry.target.id != target_id:
                        continue
                
                # Son 30 saniye içindeki işlemler
                time_diff = (datetime.datetime.now(datetime.timezone.utc) - entry.created_at).total_seconds()
                if time_diff <= 30:
                    return entry.user
            return None
        except (discord.Forbidden, discord.HTTPException):
            return None
    
    async def format_executor_info(self, executor):
        """Executor bilgisini formatlar"""
        if executor:
            return f"**İşlemi Yapan:** {executor.mention} ({executor.name})"
        return "**İşlemi Yapan:** *Belirlenemedi*"

    @commands.hybrid_command(name="logkanal-kur", description="Sunucu için log kanalı oluşturur")
    @commands.has_permissions(administrator=True)
    async def setup_log_channel(self, interaction):
        """Sunucu için log kanalı oluşturur"""
        # Kanal zaten var mı kontrol et
        existing_channel = discord.utils.get(interaction.guild.channels, name="sunucu-log")
        
        if existing_channel:
            await interaction.response.send_message("⚠️ 'sunucu-log' kanalı zaten mevcut!")
            self.log_channel = existing_channel
            return
        
        # Yeni log kanalı oluştur
        try:
            # Overwrites ile sadece yöneticilerin görebileceği bir kanal oluştur
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True)
            }
            
            # Yöneticiler için izin ekle
            for role in interaction.guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True)
            
            # Kanalı oluştur
            log_channel = await interaction.guild.create_text_channel(
                name="sunucu-log",
                overwrites=overwrites,
                topic="HydRaboN Sunucu Log Kanalı - Sunucu içi olaylar burada loglanır",
                reason="HydRaboN Log Sistemi tarafından oluşturuldu"
            )
            
            self.log_channel = log_channel
            
            # Başarı mesajı
            embed = discord.Embed(
                title="✅ Log Kanalı Kuruldu",
                description=f"Sunucu logları artık {log_channel.mention} kanalına gönderilecek.",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(embed=embed)
            
            # İlk log mesajını gönder
            welcome_embed = discord.Embed(
                title="🔍 Log Sistemi Aktif",
                description="HydRaboN Log Sistemi bu kanala sunucu içi olayları loglamaya başladı.",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )
            
            welcome_embed.add_field(
                name="İzlenen Olaylar",
                value="• Mesaj Silme/Düzenleme\n"
                      "• Ses Kanalı Hareketleri\n"
                      "• Üye Giriş/Çıkış\n"
                      "• Üye Güncellemeleri\n"
                      "• Kanal Oluşturma/Silme/Düzenleme\n"
                      "• Rol Oluşturma/Silme/Düzenleme",
                inline=False
            )
            
            # Fire-and-forget: Setup sonrası background'da gönderilir
            asyncio.create_task(self.safe_send(log_channel, embed=welcome_embed))
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot'un kanal oluşturma izni yok!")
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Kanal oluşturulurken bir hata oluştu: {e}")

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        """Yetkili kadrosundaki üyelerin Discord durum değişikliklerini izler"""
        # Performans optimizasyonları
        
        # 1. Bot kontrolü (en hızlı kontrol)
        if after.bot:
            return
            
        # 2. Sunucu kontrolü
        if not after.guild:
            return
        
        # 3. Yetkili kontrolü (sadece gerektiğinde)
        user_role_ids = {role.id for role in after.roles}  # Set kullanarak hızlandır
        
        # Intersection kullanarak hızlı kontrol (cached set kullan)
        is_staff = bool(user_role_ids.intersection(self.yetkili_role_ids))
        
        if is_staff:
            # Online session tracking
            await self._handle_staff_status_change(after, before)
        
        # 4. Orijinal davet linki kontrolü (sadece aktivite değişirse)
        if before.activities == after.activities:
            return
            
        # 5. Aktivite varlığı kontrolü
        if not after.activities:
            return
            
        # 6. Yetkili değilse davet kontrolü yapmaya gerek yok
        if not is_staff:
            return
        
        # Tüm aktivite metinlerini birleştir (daha verimli)
        all_activity_text = ""
        for activity in after.activities:
            if hasattr(activity, 'name') and activity.name:
                all_activity_text += activity.name + " "
            if hasattr(activity, 'details') and activity.details:
                all_activity_text += activity.details + " "
            if hasattr(activity, 'state') and activity.state:
                all_activity_text += activity.state + " "
            if hasattr(activity, 'url') and activity.url:
                all_activity_text += activity.url + " "
        
        # Eğer davet linki yoksa erken çık (cached pattern kullan)
        if not self.invite_pattern.search(all_activity_text):
            return
            
        # Discord davet linklerini bul (cached pattern kullan)
        matches = self.invite_pattern.findall(all_activity_text)
        
        if not matches:
            return
            
        # Her davet kodu için kontrol et
        for invite_code in matches:
            try:
                # Davet linkini çözümle
                invite = await self.bot.fetch_invite(invite_code)
                
                # Eğer davet linki bizim hedef sunucumuza ait değilse uyar
                if invite.guild and invite.guild.id != self.target_guild_id:
                    await self.send_invite_alert(after, invite, all_activity_text)
                    break  # İlk bulduğunda dur (spam önleme)
                    
            except discord.NotFound:
                # Geçersiz davet linki, ama yine de uyar
                await self.send_invalid_invite_alert(after, invite_code, all_activity_text)
                break  # İlk bulduğunda dur
            except discord.HTTPException:
                print(f"Davet linki uyarısı gönderme hatası: {e}")

    async def send_invite_alert(self, member, invite, activity_text):
        """Yetkili kadrosundaki üyenin başka sunucu davet linki koyması durumunda uyarı gönderir"""
        try:
            alert_channel = self.bot.get_channel(self.alert_channel_id)
            if not alert_channel:
                return
                
            # YK rolünü al (direkt ID ile)
            yk_role = member.guild.get_role(self.yk_role_id)
            
            # Embed oluştur
            embed = discord.Embed(
                title="⚠️ Yetkili Davet Linki Uyarısı",
                description=f"**Yetkili Üye:** {member.mention} ({member.name})\n"
                           f"**Başka Sunucu Davet Linki Tespit Edildi!**",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(self.turkey_tz)
            )
            
            embed.add_field(
                name="Davet Edilen Sunucu",
                value=f"**Sunucu:** {invite.guild.name}\n"
                      f"**Sunucu ID:** {invite.guild.id}\n"
                      f"**Davet Kodu:** {invite.code}",
                inline=False
            )
            
            embed.add_field(
                name="Aktivite Metni",
                value=f"```{activity_text[:1000]}```",
                inline=False
            )
            
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Kullanıcı ID: {member.id}")
            
            # Mesaj içeriği
            content = f"{member.mention}"
            if yk_role:
                content += f" {yk_role.mention}"
                
            content += f"\n\n🚨 **DİKKAT:** Yetkili kadrosundaki {member.mention} kullanıcısının Discord durumunda başka bir sunucuya ait davet linki tespit edildi!"
            
            # Fire-and-forget: Alert mesajları background'da gönderilir
            asyncio.create_task(self.safe_send(alert_channel, content=content, embed=embed))
            
        except Exception as e:
            print(f"Davet linki uyarısı gönderme hatası: {e}")

    async def send_invalid_invite_alert(self, member, invite_code, activity_text):
        """Geçersiz davet linki tespit edildiğinde uyarı gönderir"""
        try:
            alert_channel = self.bot.get_channel(self.alert_channel_id)
            if not alert_channel:
                return
                
            # YK rolünü al (direkt ID ile)
            yk_role = member.guild.get_role(self.yk_role_id)
            
            # Embed oluştur
            embed = discord.Embed(
                title="⚠️ Yetkili Geçersiz/Şüpheli Link Uyarısı",
                description=f"**Yetkili Üye:** {member.mention} ({member.name})\n"
                           f"**Geçersiz/Şüpheli Davet Linki Tespit Edildi!**",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now(self.turkey_tz)
            )
            
            embed.add_field(
                name="Tespit Edilen Davet Kodu",
                value=f"```{invite_code}```",
                inline=False
            )
            
            embed.add_field(
                name="Aktivite Metni",
                value=f"```{activity_text[:1000]}```",
                inline=False
            )
            
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Kullanıcı ID: {member.id}")
            
            # Mesaj içeriği
            content = f"{member.mention}"
            if yk_role:
                content += f" {yk_role.mention}"
                
            content += f"\n\n🚨 **DİKKAT:** Yetkili kadrosundaki {member.mention} kullanıcısının Discord durumunda şüpheli/geçersiz davet linki tespit edildi!"
            
            # Fire-and-forget: Alert mesajları background'da gönderilir
            asyncio.create_task(self.safe_send(alert_channel, content=content, embed=embed))
            
        except Exception as e:
            print(f"Geçersiz davet linki uyarısı gönderme hatası: {e}")

async def setup(bot):
    await bot.add_cog(ServerLogs(bot)) 