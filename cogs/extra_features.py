# Otorol sistemi, Özel oda sistemi, Chat kontrol sistemi (Link, harf)

import re
import discord
import datetime
import random
import os
import tempfile
import asyncio
from discord.ext import commands
from discord import app_commands
from typing import Optional, Union
from database import get_db
from .yetkili_panel import YETKILI_ROLLERI
import pytz

# Dosyanın varlığını kontrol et ve yoksa oluştur
karaliste_path = 'karaliste.txt'

class ExtraFeatures(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.turkey_tz = pytz.timezone('Europe/Istanbul')
        # Temel değişkenler
        self.yasakli_harfler = ['ي', 'و', 'هـ','ن','م','ل','ك','ق','ف','غ','ع','ظ','ط','ض','ص','ش','س','ز','ر','ذ','د','خ','ح','ج','ث','ت','ب','ا','ء','ؤ','ئ','آ','ة','ى','آ','إ','أ','آ']
        self.START_VOICE_CHANNEL_ID = 1173008264225619988
        self.created_channels = []  # Oluşturulan kanalları takip etmek için liste
        self.channel_owners = {}  # Kanal ID'sini ve sahibinin ID'sini tutan sözlük
        self.GUILD_ID = 1029088146752815138
        self.LOG_CHANNEL_ID = 1362825644550914263  # Yetkili sohbet kanalı ID'si
        self.KURUCU_ROLE_ID = 1029089723110674463  # Kurucu rolü ID'si
        self.KURUCU_ID = 315888596437696522  # Kurucu ID'si
        self.WELCOME_CHANNEL_ID = 1406431661872124026  # Hoş geldin kanalı ID'si
        
        # İzin verilen yetkili roller
        self.EXEMPT_ROLES = {
            YETKILI_ROLLERI["YÖNETİM KURULU ÜYELERİ"],
            YETKILI_ROLLERI["YÖNETİM KURULU BAŞKANI"],
            YETKILI_ROLLERI["KURUCU"]
        }
        
        self.discord_invite_pattern = re.compile(r'discord(?:\.gg|app\.com\/invite|\.com\/invite)\/([a-zA-Z0-9]+)')
        
        # Link pattern (http veya https ile başlayan URL'ler)
        self.link_pattern = re.compile(r'https?://[^\s]+', re.IGNORECASE)
        
        # Karalisteyi yükle
        self.karaliste = self.load_karaliste()
        
        # Spam koruma sistemi için cache
        self.user_message_cache = {}  # {user_id: [{'content': str, 'timestamp': datetime, 'channel_id': int, 'message_id': int}, ...]}
        self.SPAM_MESSAGE_LIMIT = 3  # Kaç aynı mesaj spam sayılır
        self.SPAM_TIME_WINDOW = 60  # Saniye cinsinden zaman penceresi (60 saniye)
        self.SPAM_TIMEOUT_DURATION = 7  # Gün cinsinden timeout süresi
        
        # Cache optimizasyon ayarları
        self.MAX_CACHE_USERS = 500  # Maksimum cache'de tutulacak kullanıcı sayısı
        self.CACHE_CLEANUP_INTERVAL = 300  # Cache temizliği için saniye (5 dakika)
        self.MAX_MESSAGES_PER_USER = 10  # Kullanıcı başına maksimum tutulacak mesaj
        self.INACTIVE_USER_TIMEOUT = 600  # İnaktif kullanıcı timeout (10 dakika)
        
        # Temizlik için son çalıştırma zamanı
        self.last_cache_cleanup = datetime.datetime.now(self.turkey_tz)
        
        # Üst düzey yetkili etiketleme ihlalleri cache'i
        self.mention_violations = {}  # {user_id: {'count': int, 'last_violation': datetime, 'violations': [timestamps]}}
        self.MENTION_VIOLATION_WINDOW = 24 * 60 * 60  # 24 saat (saniye cinsinden)
        self.MENTION_TIMEOUT_LEVELS = [5, 30, 120, 360, 720, 1440]  # Dakika cinsinden kademeli timeout süreleri (5min, 30min, 2h, 6h, 12h, 24h)
        self.MAX_VIOLATION_RECORDS = 20  # Kullanıcı başına maksimum ihlal kaydı
        
    def load_karaliste(self):
        """Karaliste dosyasını yükler"""
        try:
            with open('karaliste.txt', 'r', encoding='ISO-8859-9') as file:
                return [line.strip() for line in file.readlines() if line.strip()]
        except Exception as e:
            print(f"Karaliste yüklenirken hata oluştu: {e}")
            return []
    
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            # Extra Features module loaded
            pass
        except Exception as e:
            print(f"Durum ayarlanırken hata oluştu: {e}")
    
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
                        print(f"Güvenli mesaj gönderme hatası (503/502/500): {e}")
                        return None
                        
                elif e.status == 400:  # Bad request
                    print(f"Güvenli mesaj gönderme hatası (400): {e}")
                    return None
                    
                else:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1 + random.uniform(0.1, 0.5))
                        continue
                    else:
                        print(f"Güvenli mesaj gönderme HTTP hatası: {e}")
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
    async def on_member_join(self, member):
        """Yeni bir üye sunucuya katıldığında çalışır"""
        try:
            # Bot'ları hariç tut (sadece veritabanı kaydı için)
            if not member.bot:
                # Veritabanına giriş kaydı ekle
                db = await get_db()
                await db.add_member_log(
                    user_id=member.id,
                    username=str(member),
                    discriminator=member.discriminator,
                    guild_id=member.guild.id,
                    action='join',
                    account_created=member.created_at
                )
            
            # Kullanıcı notu kontrolü (sadece gerçek kullanıcılar için)
            if not member.bot:
                await self.check_user_notes_on_join(member)
                    
        except Exception as e:
            print(f"Member join işlemi hatası: {e}")
    
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Üye sunucudan ayrıldığında çalışır"""
        try:
            # Bot'ları hariç tut
            if not member.bot:
                # Veritabanına çıkış kaydı ekle
                db = await get_db()
                await db.add_member_log(
                    user_id=member.id,
                    username=str(member),
                    discriminator=member.discriminator,
                    guild_id=member.guild.id,
                    action='leave',
                    account_created=member.created_at
                )
                
                # Yetkili rolü kontrolü - ayrılan üye yetkili miydi?
                await self.check_staff_leave(member, db)
                    
        except Exception as e:
            print(f"Member remove işlemi hatası: {e}")

    async def check_staff_leave(self, member, db):
        """Yetkili rolüne sahip bir üye sunucudan ayrıldığında otomatik not ekler ve log atar"""
        try:
            YETKILI_PANEL_LOG_CHANNEL_ID = 1365954141880455238
            
            # Üyenin sahip olduğu yetkili rollerini tespit et
            sahip_roller = []
            for rol_adi, rol_id in YETKILI_ROLLERI.items():
                if any(r.id == rol_id for r in member.roles):
                    sahip_roller.append(rol_adi)
            
            # Yetkili rolü yoksa işlem yapma
            if not sahip_roller:
                return
            
            # Roller listesini formatla
            roller_str = ", ".join(sahip_roller)
            en_yuksek_rol = sahip_roller[-1] if sahip_roller else sahip_roller[0]
            
            # Zaman bilgisi
            turkey_tz = pytz.timezone('Europe/Istanbul')
            simdi = datetime.datetime.now(turkey_tz)
            tarih_str = simdi.strftime("%d.%m.%Y %H:%M")
            
            # Katılma tarihi bilgisi
            katilma_bilgisi = ""
            if member.joined_at:
                katilma_gun = (simdi - member.joined_at.astimezone(turkey_tz)).days
                katilma_bilgisi = f" | Sunucuda {katilma_gun} gün bulundu"
            
            # Otomatik kullanıcı notu ekle
            not_icerigi = (
                f"⚠️ Bu kullanıcı yetkili ({roller_str}) iken sunucudan ayrıldı. "
                f"[{tarih_str}]{katilma_bilgisi}"
            )
            
            note_id = await db.add_user_note(
                user_id=member.id,
                username=member.name,
                discriminator=member.discriminator or "0",
                note_content=not_icerigi,
                created_by=self.bot.user.id,
                created_by_username="Sistem (Otomatik)",
                guild_id=member.guild.id
            )
            
            # Yetkili panel log kanalına bildirim gönder
            log_channel = self.bot.get_channel(YETKILI_PANEL_LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="⚠️ Yetkili Ayrılış Tespiti",
                    description=(
                        f"Yetkili rolüne sahip bir kullanıcı sunucudan ayrıldı. "
                        f"Kullanıcıya otomatik not eklendi."
                    ),
                    color=discord.Color.dark_orange(),
                    timestamp=simdi
                )
                embed.add_field(
                    name="👤 Kullanıcı",
                    value=f"**{member.name}** ({member.mention})\n`ID: {member.id}`",
                    inline=True
                )
                embed.add_field(
                    name="🛡️ Yetkili Rolleri",
                    value=roller_str,
                    inline=True
                )
                if member.joined_at:
                    embed.add_field(
                        name="📅 Katılma Tarihi",
                        value=f"{discord.utils.format_dt(member.joined_at, style='R')} ({katilma_gun} gün)",
                        inline=True
                    )
                embed.add_field(
                    name="📝 Eklenen Not",
                    value=f"```{not_icerigi}```",
                    inline=False
                )
                embed.add_field(
                    name="🔖 Not ID",
                    value=f"`#{note_id}`",
                    inline=True
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"Kullanıcı ID: {member.id} • Otomatik Not Sistemi")
                
                await log_channel.send(embed=embed)
            
            print(f"[Yetkili Ayrılış] {member.name} ({member.id}) - Roller: {roller_str} - Not #{note_id} eklendi")
            
        except Exception as e:
            print(f"Yetkili ayrılış kontrolü hatası: {e}")
    
    async def check_user_notes_on_join(self, member):
        """Yeni katılan üye için not kontrolü yapar ve uyarı gönderir"""
        try:
            from database import get_db
            db = await get_db()
            
            # Kullanıcının notlarını kontrol et
            notes = await db.get_user_notes(member.id, member.guild.id, limit=10)
            
            if notes:
                # Yetkili sohbet kanalını al
                yetkili_channel = self.bot.get_channel(self.LOG_CHANNEL_ID)
                if not yetkili_channel:
                    return
                
                # Uyarı embed'i oluştur
                embed = discord.Embed(
                    title="⚠️ NOTLU KULLANICI GİRİŞİ",
                    description=f"**Kullanıcı:** {member.mention} ({member.display_name})\n"
                               f"**Kullanıcı ID:** `{member.id}`\n"
                               f"**Hesap Oluşturma:** {discord.utils.format_dt(member.created_at, style='R')}\n"
                               f"**Toplam Not Sayısı:** {len(notes)}",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(self.turkey_tz)
                )
                
                # İlk 3 notu göster
                for i, note in enumerate(notes[:3], 1):
                    created_date = datetime.datetime.fromisoformat(note['created_at']).strftime('%d.%m.%Y %H:%M')
                    note_content = note['note_content']
                    if len(note_content) > 200:
                        note_content = note_content[:200] + "..."
                    
                    embed.add_field(
                        name=f"📝 Not #{note['id']} - {created_date}",
                        value=f"**İçerik:** {note_content}\n"
                              f"**Ekleyen:** {note['created_by_username']}",
                        inline=False
                    )
                
                # Eğer 3'ten fazla not varsa bilgi ekle
                if len(notes) > 3:
                    embed.add_field(
                        name="ℹ️ Ek Bilgi",
                        value=f"Bu kullanıcı hakkında **{len(notes) - 3} adet daha not** bulunmaktadır.\n"
                              f"Tüm notları görmek için `/yetkili-panel` → `Kullanıcı Notları` → `👤 Kullanıcıya Göre Filtrele` kullanın.",
                        inline=False
                    )
                
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(
                    text=f"Kontrol: Otomatik Not Sistemi",
                    icon_url=member.guild.icon.url if member.guild.icon else None
                )
                
                # Uyarı mesajını gönder (everyone kullanmadan)
                await self.safe_send(
                    yetkili_channel,
                    content="🚨 **DİKKAT** 🚨\nNotlu bir kullanıcı sunucuya katıldı!",
                    embed=embed
                )
                
        except Exception as e:
            print(f"Kullanıcı not kontrolü hatası: {e}")
    
    async def check_discord_invite(self, message_content, guild):
        """Discord davet linklerini kontrol eder"""
        # Discord davet linkini ara
        match = self.discord_invite_pattern.search(message_content)
        if not match:
            return True  # Discord davet linki değil
            
        invite_code = match.group(1)
        
        # discord.gg/hydrabon'u hariç tut
        if invite_code.lower() == 'hydrabon':
            return True
            
        # Sunucudaki mevcut davetleri kontrol et
        try:
            invites = await guild.invites()
            for invite in invites:
                if invite.code == invite_code:
                    return True  # Bu sunucunun daveti
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"Davet kontrolü sırasında hata: {e}")
            
        return False  # Yasak Discord daveti

    @commands.Cog.listener()
    async def on_message(self, message):
        """Mesaj gönderildiğinde çalışır"""
        # Mesaj bot tarafından gönderilmişse işleme alma
        if message.author.bot:
            return

        # Yetkili kullanıcıları kontrol et (üst yönetim tamamen muaf)
        if any(role.id in self.EXEMPT_ROLES for role in message.author.roles):
            return
            
        # Kurucu rolü/kurucu kullanıcı etiketleme kontrolü (sadece yetkili olmayanlar için)
        try:
            # Kullanıcının herhangi bir yetkili rolü var mı? (STAJYER'den KURUCU'ya kadar)
            is_yetkili = any(r.id in YETKILI_ROLLERI.values() for r in message.author.roles)

            # Sadece yetkili ROLÜ OLMAYAN kullanıcılar kurucuyu etiketleyemez
            if not is_yetkili:
                # Sadece mesaj içeriğinde direkt kurucu etiketlemesi var mı kontrol et
                # Mesaj yanıtları (reply) bu kontrolden muaf tutulur
                kurucu_role_etiketi = False
                kurucu_kullanici_etiketi = False
                
                # Spesifik kurucu ID'si kontrolü
                kurucu_etiketi_pattern = f"<@!?{self.KURUCU_ID}>"
                
                if kurucu_etiketi_pattern in message.content or f"<@{self.KURUCU_ID}>" in message.content:
                    kurucu_kullanici_etiketi = True
                
                # Kurucu rolü etiketlendi mi? (sadece mesaj içeriğinde)
                kurucu_role = message.guild.get_role(self.KURUCU_ROLE_ID) if message.guild else None
                if kurucu_role and f"<@&{self.KURUCU_ROLE_ID}>" in message.content:
                    kurucu_role_etiketi = True

                if kurucu_role_etiketi or kurucu_kullanici_etiketi:
                        try:
                            await message.delete()
                        except discord.Forbidden:
                            pass
                        except Exception:
                            pass

                        # Kullanıcıya yönlendirici kısa uyarı
                        try:
                            ticket_channel = message.guild.get_channel(1364306040727933017) if message.guild else None
                            ticket_mention = ticket_channel.mention if ticket_channel else "<#1364306040727933017>"
                            await message.channel.send(f"{message.author.mention} kurucumuzu etiketlemek yerine, lütfen {ticket_mention} kanalını kullanın.")
                        except Exception:
                            pass

                        # Log kanalına bilgi
                        try:
                            log_channel = self.bot.get_channel(self.LOG_CHANNEL_ID)
                            if log_channel:
                                embed = discord.Embed(
                                    title="🚫 Kurucu Etiketleme Mesajı Silindi",
                                    description=(
                                        f"**Kullanıcı:** {message.author.mention} ({message.author.id})\n"
                                        f"**Kanal:** {message.channel.mention}\n"
                                        f"**İçerik:** ```{message.content[:1000]}```"
                                    ),
                                    color=discord.Color.red(),
                                    timestamp=datetime.datetime.now(self.turkey_tz)
                                )
                                embed.set_thumbnail(url=message.author.display_avatar.url)
                                embed.set_footer(text=f"{message.guild.name} • Kurucu Etiket Koruma")
                                asyncio.create_task(self.safe_send(log_channel, embed=embed))
                        except Exception:
                            pass

                        return
        except Exception:
            pass

        # Üst düzey yetkili etiketleme kontrolü
        await self.check_high_level_mentions(message)
            
        # Spam koruma sistemi
        await self.check_spam_protection(message)

        # Discord davet linki denetimi (mesaj içeriği veya thread ismi)
        has_invite_in_content = self.discord_invite_pattern.search(message.content)
        has_invite_in_thread_name = False
        
        # Thread isminde davet linki kontrolü
        if isinstance(message.channel, discord.Thread):
            has_invite_in_thread_name = self.discord_invite_pattern.search(message.channel.name)
        
        if has_invite_in_content or has_invite_in_thread_name:
            # İçerikteki veya thread ismindeki daveti kontrol et
            check_text = message.content if has_invite_in_content else message.channel.name
            is_allowed = await self.check_discord_invite(check_text, message.guild)
            
            if not is_allowed:
                try:
                    # Thread kontrolü - Eğer mesaj thread'in başlangıç mesajıysa veya thread isminde davet varsa thread'i sil
                    thread_deleted = False
                    if isinstance(message.channel, discord.Thread):
                        # Thread'in başlangıç mesajı mı kontrol et veya thread isminde davet var mı
                        if message.id == message.channel.id or has_invite_in_thread_name:
                            try:
                                await message.channel.delete()
                                thread_deleted = True
                            except discord.Forbidden:
                                pass
                            except Exception as e:
                                print(f"Alt başlık silme hatası: {e}")
                    
                    # Mesajı sil (thread silinmediyse)
                    if not thread_deleted:
                        await message.delete()
                    
                    # 1 haftalık timeout uygula (7 gün = 604800 saniye)
                    timeout_duration = datetime.timedelta(days=7)
                    await message.author.timeout(timeout_duration, reason="Başka Discord davet linki paylaşımı")
                    
                    # Log kanalına uyarı mesajı gönder
                    log_channel = self.bot.get_channel(self.LOG_CHANNEL_ID)
                    if log_channel:
                        embed = discord.Embed(
                            title="⚠️ Başka Discord Davet Linki Paylaşımı",
                            color=discord.Color.red(),
                            timestamp=datetime.datetime.now(self.turkey_tz)
                        )
                        embed.add_field(name="Kullanıcı", value=f"{message.author.mention} ({message.author.id})", inline=False)
                        embed.add_field(name="Kanal", value=f"{message.channel.mention if not thread_deleted else f'#{message.channel.name} (Alt başlık Silindi)'}", inline=False)
                        embed.add_field(name="Mesaj İçeriği", value=f"```{message.content[:1000]}```", inline=False)
                        
                        action_text = "Mesaj silindi ve kullanıcıya 7 günlük timeout uygulandı"
                        if thread_deleted:
                            action_text = "Alt başlık ve mesaj silindi, kullanıcıya 7 günlük timeout uygulandı"
                        elif has_invite_in_thread_name:
                            action_text += " (Alt başlık isminde davet linki tespit edildi)"
                            
                        embed.add_field(name="İşlem", value=action_text, inline=False)
                        embed.set_footer(text=f"Kullanıcı ID: {message.author.id}")
                        
                        # Fire-and-forget: Krıitik uyarı background'da gönderilir
                        asyncio.create_task(self.safe_send(log_channel, content="**KRİTİK UYARI** ||@everyone||", embed=embed))
                    
                    return
                    
                except discord.Forbidden:
                    pass
                except Exception as e:
                    print(f"Discord davet linki işlemi sırasında hata: {e}")

        # Link denetimi - Mesajın içinde link var mı kontrol et
        if self.link_pattern.search(message.content):
            # Hoş geldin kanalında link kontrolü
            if message.channel.id == self.WELCOME_CHANNEL_ID:
                await message.delete()
                msg = await message.channel.send(f'{message.author.mention}, medya içeriklerini <#1406432595679383572> kanalına atmanız gerekmektedir.')
                await msg.delete(delay=4)
                return

        # Arapça karakter denetimi
        for harf in message.content:
            if harf in self.yasakli_harfler:
                await message.delete()
                msg = await message.channel.send(f'{message.author.mention} bu sunucuda ar*pça konuşamazsın!')
                await msg.delete(delay=4)
                break
    
    async def check_spam_protection(self, message):
        """Spam koruma kontrolü yapar - Optimize edilmiş versiyon"""
        if not message.guild:
            return  # DM mesajlarını kontrol etme
            
        # Belirli kategori içindeki kanalları hariç tut
        EXCLUDED_CATEGORY_ID = 1036080439942713365
        if message.channel.category and message.channel.category.id == EXCLUDED_CATEGORY_ID:
            return
            
        user_id = message.author.id
        current_time = datetime.datetime.now(self.turkey_tz)
        message_content = message.content.strip()
        
        # Boş mesajları kontrol etme
        if not message_content:
            return
            
        # Periyodik cache temizliği
        await self.periodic_cache_cleanup(current_time)
        
        # Cache boyut kontrolü - Çok büyükse en eski kullanıcıları temizle
        await self.manage_cache_size()
        
        # Kullanıcının mesaj geçmişini al veya oluştur
        if user_id not in self.user_message_cache:
            self.user_message_cache[user_id] = {'last_activity': current_time, 'messages': []}
            
        user_data = self.user_message_cache[user_id]
        user_data['last_activity'] = current_time  # Son aktivite zamanını güncelle
        user_messages = user_data['messages']
        
        # Eski mesajları temizle (zaman penceresi dışındaki)
        cutoff_time = current_time - datetime.timedelta(seconds=self.SPAM_TIME_WINDOW)
        user_messages[:] = [msg for msg in user_messages if msg['timestamp'] > cutoff_time]
        
        # Kullanıcı başına mesaj limiti kontrolü
        if len(user_messages) >= self.MAX_MESSAGES_PER_USER:
            user_messages.pop(0)  # En eski mesajı çıkar
        
        # Yeni mesajı ekle (message objesi yerine sadece gerekli bilgiler)
        new_message = {
            'content': message_content,
            'timestamp': current_time,
            'channel_id': message.channel.id,
            'message_id': message.id
        }
        user_messages.append(new_message)
        
        # Aynı mesajın tekrar sayısını kontrol et (sadece aynı kanalda)
        same_message_count = 0
        same_messages = []
        
        for msg in user_messages:
            if msg['content'] == message_content and msg['channel_id'] == message.channel.id:
                same_message_count += 1
                same_messages.append(msg)
        
        # Spam tespit edildi mi? (Sadece ilk spam tespitinde işlem yap)
        if same_message_count == self.SPAM_MESSAGE_LIMIT:
            await self.handle_spam_detected(message, same_messages, message_content)
    
    async def periodic_cache_cleanup(self, current_time):
        """Periyodik cache temizliği yapar"""
        # Son temizlikten beri yeterli zaman geçti mi?
        if (current_time - self.last_cache_cleanup).total_seconds() < self.CACHE_CLEANUP_INTERVAL:
            return
            
        self.last_cache_cleanup = current_time
        inactive_threshold = current_time - datetime.timedelta(seconds=self.INACTIVE_USER_TIMEOUT)
        
        # İnaktif kullanıcıları bul ve sil (spam cache)
        inactive_users = []
        for user_id, user_data in self.user_message_cache.items():
            if user_data['last_activity'] < inactive_threshold:
                inactive_users.append(user_id)
        
        # İnaktif kullanıcıları cache'den çıkar
        for user_id in inactive_users:
            del self.user_message_cache[user_id]
        
        # Etiketleme ihlalleri cache temizliği (optimize edilmiş)
        mention_cutoff_time = current_time - datetime.timedelta(seconds=self.MENTION_VIOLATION_WINDOW)
        expired_mention_users = []
        
        for user_id, user_data in self.mention_violations.items():
            violations = user_data['violations']
            # Eski ihlalleri temizle (optimize edilmiş)
            violations[:] = [timestamp for timestamp in violations if timestamp > mention_cutoff_time]
            
            # Kullanıcı verilerini güncelle
            user_data['count'] = len(violations)
            
            # Eğer hiç ihlal kalmadıysa kullanıcıyı listeden çıkar
            if not violations:
                expired_mention_users.append(user_id)
        
        # Boş kayıtları sil (toplu silme - performans iyileştirmesi)
        for user_id in expired_mention_users:
            del self.mention_violations[user_id]
    
    async def manage_cache_size(self):
        """Cache boyutunu yönetir - Optimize edilmiş versiyon"""
        # Spam cache boyut kontrolü
        if len(self.user_message_cache) > self.MAX_CACHE_USERS:
            # Son aktiviteye göre sırala ve en eskisini çıkar
            users_by_activity = sorted(
                self.user_message_cache.items(), 
                key=lambda x: x[1]['last_activity']
            )
            
            # En eski %20'yi çıkar
            users_to_remove = len(self.user_message_cache) - int(self.MAX_CACHE_USERS * 0.8)
            
            for i in range(users_to_remove):
                user_id, _ = users_by_activity[i]
                del self.user_message_cache[user_id]
        
        # Etiketleme ihlalleri cache boyut kontrolü
        max_mention_cache_size = 200  # Maksimum etiketleme cache kullanıcı sayısı
        if len(self.mention_violations) > max_mention_cache_size:
            # Son ihlale göre sırala ve en eskisini çıkar
            users_by_last_violation = sorted(
                self.mention_violations.items(),
                key=lambda x: x[1]['last_violation']
            )
            
            # En eski %30'unu çıkar
            users_to_remove = len(self.mention_violations) - int(max_mention_cache_size * 0.7)
            
            for i in range(users_to_remove):
                user_id, _ = users_by_last_violation[i]
                del self.mention_violations[user_id]
    
    async def handle_spam_detected(self, original_message, spam_messages, message_content):
        """Spam tespit edildiğinde çalışır - Optimize edilmiş versiyon"""
        user = original_message.author
        guild = original_message.guild
        channel = original_message.channel
        
        try:
            # Spam mesajlarını sil (Batch silme için optimize)
            deleted_count = 0
            messages_to_delete = []
            
            # Önce mevcut mesajları bul
            for msg_data in spam_messages:
                try:
                    if msg_data['message_id'] == original_message.id:
                        # Ana mesajı direkt sil
                        messages_to_delete.append(original_message)
                    else:
                        # Diğer mesajları ID ile getir
                        try:
                            msg = await channel.fetch_message(msg_data['message_id'])
                            messages_to_delete.append(msg)
                        except discord.NotFound:
                            pass  # Mesaj zaten silinmiş
                except Exception as e:
                    print(f"Mesaj getirme hatası: {e}")
            
            # Mesajları sil (bulk delete varsa kullan, yoksa tek tek)
            if len(messages_to_delete) > 1:
                try:
                    # Bulk delete (2-100 arası mesaj için Discord'un özelliği)
                    await channel.delete_messages(messages_to_delete)
                    deleted_count = len(messages_to_delete)
                except discord.Forbidden:
                    # Bulk delete izni yoksa tek tek sil
                    for msg in messages_to_delete:
                        try:
                            await msg.delete()
                            deleted_count += 1
                        except:
                            pass
                except discord.HTTPException:
                    # Bulk delete başarısızsa tek tek sil
                    for msg in messages_to_delete:
                        try:
                            await msg.delete()
                            deleted_count += 1
                        except:
                            pass
            elif len(messages_to_delete) == 1:
                try:
                    await messages_to_delete[0].delete()
                    deleted_count = 1
                except:
                    pass
            
            # Kullanıcıya timeout uygula (7 gün)
            timeout_applied = False
            try:
                timeout_duration = datetime.timedelta(days=self.SPAM_TIMEOUT_DURATION)
                await user.timeout(timeout_duration, reason=f"Spam: Aynı mesajın {len(spam_messages)} kez atılması")
                timeout_applied = True
            except discord.Forbidden:
                pass
            except Exception as e:
                print(f"Timeout uygulama hatası: {e}")
            
            # Kullanıcının cache'ini temizle
            if user.id in self.user_message_cache:
                del self.user_message_cache[user.id]
            
            # Veritabanına log kaydet (asenkron olarak)
            asyncio.create_task(self.log_spam_async(user, guild, channel, message_content, timeout_applied, deleted_count))
            
            # Log kanalına bildirim gönder (asenkron olarak)
            asyncio.create_task(self.send_spam_alert(user, guild, channel, message_content, deleted_count, timeout_applied))
            
        except Exception as e:
            print(f"Spam işleme genel hatası: {e}")
    
    async def log_spam_async(self, user, guild, channel, message_content, timeout_applied, deleted_count):
        """Spam logunu asenkron olarak kaydeder"""
        try:
            from database import get_db
            db = await get_db()
            await db.add_spam_log(
                user_id=user.id,
                username=str(user),
                guild_id=guild.id,
                channel_id=channel.id,
                message_content=message_content,
                timeout_applied=timeout_applied,
                messages_deleted=deleted_count
            )
        except Exception as e:
            print(f"Spam log kaydetme hatası: {e}")
    
    async def send_spam_alert(self, user, guild, channel, message_content, deleted_count, timeout_applied):
        """Spam uyarısını log kanalına gönderir"""
        try:
            log_channel = self.bot.get_channel(self.LOG_CHANNEL_ID)
            if not log_channel:
                return
                
            # Embed oluştur
            embed = discord.Embed(
                title="🚨 SPAM TESPİT EDİLDİ",
                description=f"**Kullanıcı:** {user.mention} ({user.name})\n"
                           f"**Kanal:** {channel.mention}\n"
                           f"**Kullanıcı ID:** {user.id}",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(self.turkey_tz)
            )
            
            # Mesaj içeriğini ekle (uzunsa kısalt)
            content_preview = message_content
            if len(content_preview) > 1000:
                content_preview = content_preview[:997] + "..."
            
            embed.add_field(
                name="📝 Spam Mesaj İçeriği",
                value=f"```{content_preview}```",
                inline=False
            )
            
            embed.add_field(
                name="📊 İşlem Detayları",
                value=f"**Silinen Mesaj Sayısı:** {deleted_count}\n"
                      f"**Timeout Uygulandı:** {'✅ Evet' if timeout_applied else '❌ Hayır'}\n"
                      f"**Timeout Süresi:** {self.SPAM_TIMEOUT_DURATION} gün",
                inline=False
            )
            
            embed.add_field(
                name="👤 Kullanıcı Bilgileri",
                value=f"**Katılma Tarihi:** {user.joined_at.strftime('%d/%m/%Y %H:%M') if user.joined_at else 'Bilinmiyor'}\n"
                      f"**Hesap Oluşturma:** {user.created_at.strftime('%d/%m/%Y %H:%M')}\n"
                      f"**Rol Sayısı:** {len(user.roles) - 1}",
                inline=False
            )
            
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(
                text=f"{guild.name} • Spam Koruma Sistemi",
                icon_url=guild.icon.url if guild.icon else None
            )
            
            # Fire-and-forget: Spam uyarısı background'da gönderilir
            asyncio.create_task(self.safe_send(
                log_channel,
                content="🚨 **KRİTİK UYARI - SPAM TESPİT EDİLDİ** 🚨",
                embed=embed
            ))
            
        except Exception as e:
            print(f"Spam uyarısı gönderme hatası: {e}")
    
    async def check_high_level_mentions(self, message):
        """Üst düzey yetkili etiketlemelerini kontrol eder ve kademeli timeout uygular"""
        try:
            # Mesaj içeriğinde ID bazlı etiketleme var mı kontrol et (regex ile)
            mention_pattern = re.compile(r'<@!?(\d+)>')
            mention_matches = mention_pattern.findall(message.content)
            
            if not mention_matches:
                return
            
            # Üst düzey roller (optimize edilmiş set kullanımı)
            high_level_roles = {
                YETKILI_ROLLERI["YÖNETİM KURULU ÜYELERİ"],
                YETKILI_ROLLERI["YÖNETİM KURULU BAŞKANI"],
                YETKILI_ROLLERI["KURUCU"]
            }
            
            # Etiketlenen ID'leri member objesine çevir ve üst düzey yetkili kontrol et
            mentioned_high_level_users = []
            for user_id_str in mention_matches:
                try:
                    user_id = int(user_id_str)
                    mentioned_user = message.guild.get_member(user_id)
                    
                    if mentioned_user and isinstance(mentioned_user, discord.Member):
                        user_role_ids = {role.id for role in mentioned_user.roles}
                        if high_level_roles & user_role_ids:  # Set intersection (daha hızlı)
                            mentioned_high_level_users.append(mentioned_user)
                except (ValueError, AttributeError):
                    continue  # Geçersiz ID'leri atla
            
            # Üst düzey yetkili etiketlenmişse
            if mentioned_high_level_users:
                # Mesaj yazarının yetkili olup olmadığını kontrol et (optimize edilmiş)
                author_role_ids = {role.id for role in message.author.roles}
                yetkili_role_set = set(YETKILI_ROLLERI.values())
                is_author_authorized = bool(yetkili_role_set & author_role_ids)  # Set intersection
                
                # Yazar yetkili değilse ihlal kontrol et ve gerekirse mesaj gönder
                if not is_author_authorized:
                    # Kullanıcının önceki ihlallerini kontrol et ve timeout uygula
                    timeout_duration = await self.process_mention_violation(message.author, mentioned_high_level_users)
                    
                    # Mesaj gönder (-1 = ilk ihlal/mesaj yok, 0 = sadece uyarı, >0 = uyarı + timeout)
                    if timeout_duration >= 0:
                        # Ticket kanalını mention et
                        ticket_channel = message.guild.get_channel(1364306040727933017)
                        ticket_mention = ticket_channel.mention if ticket_channel else "<#1364306040727933017>"
                        
                        # Kısa ve doğal mesajlar
                        if timeout_duration == 0:
                            # 2. ihlal: Sadece uyarı mesajı (doğal format)
                            response_text = (
                                f"⚠️ {message.author.mention} Üst Yönetim'den birisini tekrar etiketlediniz. "
                                f"Bir sorununuz varsa {ticket_mention} kanalını kullanın. "
                                f"**Bir sonraki etiketlemede timeout uygulanacaktır.**"
                            )
                        else:
                            # 3+ ihlal: Timeout mesajı (doğal format)
                            if timeout_duration < 60:
                                time_text = f"{timeout_duration} dakika"
                            elif timeout_duration < 1440:
                                time_text = f"{timeout_duration // 60} saat"
                            else:
                                time_text = f"{timeout_duration // 1440} gün"
                                
                            response_text = (
                                f"🚨 {message.author.mention} Üst Yönetim'den birisini tekrar etiketlediğiniz için "
                                f"**{time_text} timeout** uygulandı. "
                                f"Acil durumlarınız için {ticket_mention} kanalını kullanın."
                            )
                        
                        # Kısa ve öz yanıt gönder
                        await message.reply(response_text, mention_author=False)
                    
        except Exception as e:
            pass
    
    async def process_mention_violation(self, user, mentioned_users):
        """Etiketleme ihlalini işler ve kademeli timeout uygular - Optimize edilmiş"""
        try:
            current_time = datetime.datetime.now(self.turkey_tz)
            user_id = user.id
            
            # Kullanıcının ihlal kaydını al veya oluştur
            if user_id not in self.mention_violations:
                self.mention_violations[user_id] = {
                    'count': 0,
                    'last_violation': current_time,
                    'violations': []
                }
            
            user_data = self.mention_violations[user_id]
            violations = user_data['violations']
            
            # 24 saat öncesindeki ihlalleri temizle (optimize edilmiş)
            cutoff_time = current_time - datetime.timedelta(seconds=self.MENTION_VIOLATION_WINDOW)
            violations[:] = [timestamp for timestamp in violations if timestamp > cutoff_time]
            
            # Mevcut aktif ihlal sayısını belirle
            violation_count = len(violations)
            
            # Yeni ihlali kaydet (sadece timestamp - memory optimize)
            violations.append(current_time)
            
            # Cache boyut kontrolü (memory optimize)
            if len(violations) > self.MAX_VIOLATION_RECORDS:
                violations[:] = violations[-self.MAX_VIOLATION_RECORDS:]
            
            # Kullanıcı verilerini güncelle
            user_data['count'] = len(violations)
            user_data['last_violation'] = current_time
            
            # Toplam ihlal sayısını hesapla (yeni ihlal dahil)
            total_violation_count = len(violations)
            
            # Timeout süresini belirle (1. ihlal = hiçbir şey, 2. ihlal = sadece uyarı, 3+ ihlal = timeout)
            timeout_duration = 0
            
            if total_violation_count == 2:
                # 2. ihlal: Sadece uyarı mesajı, timeout yok
                timeout_duration = 0
            elif total_violation_count > 2:
                # 3+ ihlal: Timeout uygula (3. ihlal = index 0, 4. ihlal = index 1, vs.)
                level_index = min(total_violation_count - 3, len(self.MENTION_TIMEOUT_LEVELS) - 1)
                timeout_duration = self.MENTION_TIMEOUT_LEVELS[level_index]
                
                # Timeout uygula
                try:
                    timeout_timedelta = datetime.timedelta(minutes=timeout_duration)
                    await user.timeout(timeout_timedelta, reason=f"Üst düzey yetkili tekrar etiketleme ({total_violation_count}. ihlal)")
                except discord.Forbidden:
                    pass
                except Exception as e:
                    print(f"Timeout uygulama hatası: {e}")
            
            # Log kaydı için bilgileri kaydet (2+ ihlalde)
            if total_violation_count > 1:
                asyncio.create_task(self.log_mention_violation(user, mentioned_users, total_violation_count, timeout_duration))
            
            # Dönüş değerleri: -1 = mesaj yok, 0 = sadece uyarı, >0 = uyarı + timeout
            if total_violation_count == 1:
                return -1  # İlk ihlal: hiçbir mesaj gönderme
            elif total_violation_count == 2:
                return 0   # İkinci ihlal: sadece uyarı mesajı
            else:
                return timeout_duration  # 3+ ihlal: uyarı + timeout
            
        except Exception as e:
            print(f"Etiketleme ihlali işleme hatası: {e}")
            return 0
    
    async def log_mention_violation(self, user, mentioned_users, violation_count, timeout_duration):
        """Etiketleme ihlalini log kanalına kaydeder"""
        try:
            log_channel = self.bot.get_channel(self.LOG_CHANNEL_ID)
            if not log_channel:
                return
                
            # Embed oluştur
            embed = discord.Embed(
                title="🚨 ÜST DÜZEY YETKİLİ ETİKETLEME İHLALİ",
                description=f"**Kullanıcı:** {user.mention} ({user.name})\n"
                           f"**Kullanıcı ID:** {user.id}\n"
                           f"**İhlal Sayısı:** {violation_count}\n"
                           f"**Uygulanan Timeout:** {timeout_duration} dakika",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(self.turkey_tz)
            )
            
            embed.add_field(
                name="📝 Etiketlenen Üst Düzey Yetkililer",
                value=", ".join([user.mention for user in mentioned_users]),
                inline=False
            )
            
            embed.add_field(
                name="⏱️ Timeout Detayları",
                value=f"**Süre:** {timeout_duration} dakika\n"
                      f"**Sebep:** Üst düzey yetkili tekrar etiketleme\n"
                      f"**24 saat içindeki toplam ihlal:** {violation_count}",
                inline=False
            )
            
            embed.add_field(
                name="👤 Kullanıcı Bilgileri",
                value=f"**Katılma Tarihi:** {user.joined_at.strftime('%d/%m/%Y %H:%M') if user.joined_at else 'Bilinmiyor'}\n"
                      f"**Hesap Oluşturma:** {user.created_at.strftime('%d/%m/%Y %H:%M')}\n"
                      f"**Rol Sayısı:** {len(user.roles) - 1}",
                inline=False
            )
            
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(
                text=f"{user.guild.name} • Yetkili Etiketleme Koruma Sistemi",
                icon_url=user.guild.icon.url if user.guild.icon else None
            )
            
            # Fire-and-forget: İhlal uyarısı background'da gönderilir
            asyncio.create_task(self.safe_send(
                log_channel,
                content="🚨 **YETKİLİ ETİKETLEME İHLALİ** 🚨",
                embed=embed
            ))
            
        except Exception as e:
            print(f"Etiketleme ihlali log kaydetme hatası: {e}")
    
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Kanal silindiğinde çalışır — koruma sistemi"""
        guild = channel.guild

        # Muaf kategori kontrolü — bu kategorideki kanallar silinebilir
        EXEMPT_CATEGORY_ID = 1067552184423694466
        if channel.category_id == EXEMPT_CATEGORY_ID:
            return

        # Denetim kaydını kontrol edip kanalı kimin sildiğini bul
        deleter = None
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
                deleter = entry.user
                break
        except discord.Forbidden:
            return

        if not deleter:
            return

        # Bot hesaplarına dokunma
        if deleter.bot:
            return

        # KURUCU rolüne sahip kişiler muaf
        member = guild.get_member(deleter.id)
        if not member:
            return

        if any(role.id == self.KURUCU_ROLE_ID for role in member.roles):
            return

        # Kanal türü belirleme
        channel_type_text = "Metin Kanalı"
        if isinstance(channel, discord.VoiceChannel):
            channel_type_text = "Ses Kanalı"
        elif isinstance(channel, discord.CategoryChannel):
            channel_type_text = "Kategori"
        elif isinstance(channel, discord.StageChannel):
            channel_type_text = "Sahne Kanalı"
        elif isinstance(channel, discord.ForumChannel):
            channel_type_text = "Forum Kanalı"

        # 1. Öncelik: Tüm rolleri kaldır
        removed_roles = []
        for role in member.roles[1:]:  # @everyone hariç
            try:
                await member.remove_roles(role, reason="Kanal silme koruması — tüm roller kaldırıldı")
                removed_roles.append(role.name)
            except discord.Forbidden:
                pass
            except discord.HTTPException as e:
                print(f"Kanal silme koruması — {role.name} rolünü kaldırırken hata: {e}")

        # 2. 7 gün zaman aşımı uygula
        timeout_applied = False
        try:
            await member.timeout(datetime.timedelta(days=7), reason="Kanal silme koruması — 7 gün zaman aşımı")
            timeout_applied = True
        except discord.Forbidden:
            print(f"Kanal silme koruması — {member.name} kullanıcısına timeout uygulanamadı (yetki yetersiz)")
        except discord.HTTPException as e:
            print(f"Kanal silme koruması — timeout hatası: {e}")

        # 3. yk-sohbet kanalına bilgi gönder
        YK_SOHBET_CHANNEL_ID = 1362825668965957845
        log_channel = guild.get_channel(YK_SOHBET_CHANNEL_ID)
        if log_channel:
            now = datetime.datetime.now(pytz.timezone('Europe/Istanbul'))

            embed = discord.Embed(
                title="🚨 Kanal Silme Koruması Tetiklendi",
                description=f"Bir kullanıcı izinsiz kanal sildi. Otomatik yaptırımlar uygulandı.",
                color=discord.Color.red(),
                timestamp=now
            )
            embed.add_field(name="👤 Kullanıcı", value=f"{member.mention} (`{member.name}` — ID: {member.id})", inline=False)
            embed.add_field(name="📺 Silinen Kanal", value=f"**{channel.name}** (ID: {channel.id})", inline=True)
            embed.add_field(name="📁 Kanal Türü", value=channel_type_text, inline=True)
            if channel.category:
                embed.add_field(name="📂 Kategori", value=channel.category.name, inline=True)
            embed.add_field(name="🕐 Saat", value=now.strftime("%d.%m.%Y %H:%M:%S"), inline=False)

            # Uygulanan yaptırımlar
            yaptirimlar = []
            if removed_roles:
                yaptirimlar.append(f"✅ **{len(removed_roles)}** rol kaldırıldı")
            else:
                yaptirimlar.append("❌ Rol kaldırılamadı")
            if timeout_applied:
                yaptirimlar.append("✅ 7 gün zaman aşımı uygulandı")
            else:
                yaptirimlar.append("❌ Zaman aşımı uygulanamadı")

            embed.add_field(name="⚡ Uygulanan Yaptırımlar", value="\n".join(yaptirimlar), inline=False)

            if removed_roles:
                roles_text = ", ".join(removed_roles)
                if len(roles_text) > 1024:
                    roles_text = roles_text[:1000] + "..."
                embed.add_field(name="🏷️ Kaldırılan Roller", value=roles_text, inline=False)

            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"{guild.name} • Kanal Silme Koruması", icon_url=guild.icon.url if guild.icon else None)

            await log_channel.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        """Rol silindiğinde çalışır"""
        # Denetim kaydını kontrol edip rolü kimin sildiğini bul
        try:
            async for entry in role.guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
                deleter = entry.user
                break
        except discord.Forbidden:
            pass
            return
        
        if deleter and any(role.id in self.EXEMPT_ROLES for role in deleter.roles):
            return

        if deleter:
            # Eğer rolü silen kişi bir bot değilse
            if not deleter.bot:
                # Kullanıcının tüm rollerini kaldır
                for user_role in deleter.roles[1:]:  # @everyone rolünü dışarıda bırak
                    try:
                        await deleter.remove_roles(user_role, reason="Rol silme nedeniyle roller kaldırıldı")
                    except discord.Forbidden:
                        pass
                    except discord.HTTPException as e:
                        print(f"{user_role.name} rolünü kaldırırken bir hata oluştu: {e}")

                # Admin'e durumu bildir
                admin_user = self.bot.get_user(315888596437696522)
                if admin_user:
                    await admin_user.send(f"{deleter.mention} adlı kullanıcı '{role.name}' adlı bir rolü sildi ve tüm rolleri kaldırıldı.")
    
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Üye güncellendiğinde çalışır"""
        # Eğer kullanıcının rollerinde bir değişiklik olduysa
        if before.roles != after.roles:
            try:
                # Denetim kayıtlarını kontrol edip rolü kimin değiştirdiğini bul
                async for entry in after.guild.audit_logs(action=discord.AuditLogAction.member_role_update, limit=1):
                    updater = entry.user
                    break
            except discord.Forbidden:
                pass
                return
            
            if updater and any(role.id in self.EXEMPT_ROLES for role in updater.roles):
                return

            # Rolü değiştiren kişiyle güncellenen kişi aynı değilse
            if updater and updater != after:
                # ÜYE rolüne sahip kullanıcılar bu işlemden muaf tutulur
                uye_role_id = 1029089740022095973  # ÜYE rol ID'si
                if any(role.id == uye_role_id for role in updater.roles):
                    return
                
                # Eğer rolü değiştiren kişi bir bot değilse
                if not updater.bot:
                    # YK-sohbet kanalına bildirim gönder
                    yk_sohbet_channel = after.guild.get_channel(1362825668965957845)
                    yk_role = after.guild.get_role(1029089731314720798)
                    
                    if yk_sohbet_channel and yk_role:
                        try:
                            # Eklenen ve kaldırılan rolleri tespit et
                            added_roles = [role for role in after.roles if role not in before.roles]
                            removed_roles = [role for role in before.roles if role not in after.roles]
                            
                            # Embed oluştur
                            embed = discord.Embed(
                                title="⚠️ Yetkisiz Rol Değişikliği Tespit Edildi",
                                description=f"**İşlemi Yapan:** {updater.mention} ({updater.name})\n"
                                           f"**Etkilenen Kullanıcı:** {after.mention} ({after.name})",
                                color=discord.Color.red(),
                                timestamp=datetime.datetime.now(self.turkey_tz)
                            )
                            
                            # Eklenen roller varsa
                            if added_roles:
                                roles_text = ", ".join([role.mention for role in added_roles])
                                embed.add_field(name="➕ Eklenen Roller", value=roles_text, inline=False)
                            
                            # Kaldırılan roller varsa
                            if removed_roles:
                                roles_text = ", ".join([role.mention for role in removed_roles])
                                embed.add_field(name="➖ Kaldırılan Roller", value=roles_text, inline=False)
                            
                            # Kullanıcı bilgileri
                            embed.add_field(
                                name="👤 İşlemi Yapan Kullanıcı Bilgileri",
                                value=f"**ID:** {updater.id}\n"
                                      f"**Katılma Tarihi:** {updater.joined_at.strftime('%d/%m/%Y') if updater.joined_at else 'Bilinmiyor'}\n"
                                      f"**Hesap Oluşturma:** {updater.created_at.strftime('%d/%m/%Y')}",
                                inline=True
                            )
                            
                            embed.add_field(
                                name="👥 Etkilenen Kullanıcı Bilgileri", 
                                value=f"**ID:** {after.id}\n"
                                      f"**Katılma Tarihi:** {after.joined_at.strftime('%d/%m/%Y') if after.joined_at else 'Bilinmiyor'}\n"
                                      f"**Hesap Oluşturma:** {after.created_at.strftime('%d/%m/%Y')}",
                                inline=True
                            )
                            
                            embed.set_thumbnail(url=updater.display_avatar.url)
                            embed.set_footer(
                                text=f"{after.guild.name} • Güvenlik Sistemi",
                                icon_url=after.guild.icon.url if after.guild.icon else None
                            )
                            
                            # YK rolünü etiketleyerek mesaj gönder
                            await yk_sohbet_channel.send(
                                content=f"🚨 {yk_role.mention} **DİKKAT!** Yetkisiz rol değişikliği tespit edildi!",
                                embed=embed
                            )
                            
                        except Exception as e:
                            print(f"YK-sohbet kanalına bildirim gönderme hatası: {e}")
                    else:
                        print("YK-sohbet kanalı veya YK rolü bulunamadı!")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Ses kanalı hareketlerini takip eder ve özel kanallar oluşturur"""
        # Kullanıcı START_VOICE_CHANNEL_ID kanalına katıldıysa
        if after.channel and after.channel.id == self.START_VOICE_CHANNEL_ID:
            # Kullanıcı adıyla yeni bir kanal oluştur
            guild = member.guild
            category = after.channel.category
            
            try:
                # Kanal için izinleri oluştur - Artık tüm kullanıcılar için aynı sistem
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(connect=True)  # Herkes için açık başlat
                }
                
                # Kayıtsız Üye rolü için kanal görüntüleme ve bağlanma izni kapat
                kayitsiz_role = guild.get_role(1428496119213588521)
                if kayitsiz_role:
                    overwrites[kayitsiz_role] = discord.PermissionOverwrite(view_channel=False, connect=False)
                
                # Kanal sahibi her zaman girebilir
                overwrites[member] = discord.PermissionOverwrite(connect=True)
                
                # Kullanıcı adını kullanarak yeni kanal oluştur
                new_channel = await guild.create_voice_channel(
                    name=f"{member.display_name}",
                    category=category,
                    bitrate=64000,  # 64 kbps kalite
                    user_limit=0,  # Sınırsız kullanıcı
                    overwrites=overwrites
                )
                
                # Kanalı oluşturulan kanallar listesine ekle
                self.created_channels.append(new_channel.id)
                
                # Kanal sahibini kaydet
                self.channel_owners[new_channel.id] = member.id
                
                # Kullanıcıyı yeni kanala taşı
                await member.move_to(new_channel)
                
                # Özel oda oluşturma kaydını veritabanına ekle
                try:
                    db = await get_db()
                    await db.add_private_room_log(
                        guild_id=guild.id,
                        user_id=member.id,
                        username=str(member),
                        channel_id=new_channel.id,
                        channel_name=new_channel.name
                    )
                except Exception as e:
                    print(f"Özel oda log kaydedilirken hata: {e}")
                
            except discord.HTTPException as e:
                print(f"Kanal oluşturulurken hata: {e}")
        
        # Kullanıcı çıkış yaptığında, kanal boş kaldıysa ve bizim oluşturduğumuz bir kanalsa sil
        if before.channel and before.channel.id in self.created_channels:
            # Kanalda kimse kalmadıysa ve bot'un oluşturduğu bir kanalsa sil
            if len(before.channel.members) == 0:
                try:
                    channel_id = before.channel.id
                    await before.channel.delete()
                    
                    # Özel oda silinme zamanını veritabanına kaydet
                    try:
                        db = await get_db()
                        await db.update_private_room_deleted(channel_id)
                    except Exception as e:
                        print(f"Özel oda silinme zamanı güncellenirken hata: {e}")
                    
                    # Listelerden kaldır
                    self.created_channels.remove(channel_id)
                    if channel_id in self.channel_owners:
                        del self.channel_owners[channel_id]
                except discord.HTTPException as e:
                    print(f"Kanal silinirken hata: {e}")

    # Özel ses kanalı yönetim komutları
    @app_commands.command(name="limit", description="Özel odanın üye limitini ayarlar")
    @app_commands.describe(limit="Oda limiti ayarlar")
    async def limit(self, interaction: discord.Interaction, limit: int):
        # Kullanıcı bir ses kanalında mı kontrol et
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Bu komutu kullanmak için bir ses kanalında olmalısınız.", ephemeral=True)
            
        voice_channel = interaction.user.voice.channel

        # Kullanıcı kanal sahibi mi kontrol et
        if voice_channel.id in self.channel_owners and self.channel_owners[voice_channel.id] == interaction.user.id:
            await voice_channel.edit(user_limit=limit)
            await interaction.response.send_message(f"Oda limiti {limit} olarak ayarlandı.", ephemeral=True)
        else:
            await interaction.response.send_message("Bu işlemi yapmak için oda sahibi olmanız gerekmektedir.", ephemeral=True)



    @app_commands.command(name="isim", description="Özel odanın ismini değiştirir")
    @app_commands.describe(name="Yeni oda ismi")
    async def isim(self, interaction: discord.Interaction, name: str):
        # Kullanıcı bir ses kanalında mı kontrol et
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Bu komutu kullanmak için bir ses kanalında olmalısınız.", ephemeral=True)
            
        voice_channel = interaction.user.voice.channel

        # Kullanıcı kanal sahibi mi kontrol et
        if voice_channel.id in self.channel_owners and self.channel_owners[voice_channel.id] == interaction.user.id:
            # İsim doğrulaması
            if "hydrabon" in name.lower():
                await interaction.response.send_message("Oda ismi güvenlik önlemleri gereği HydRaboN içeremez.", ephemeral=True)
                return
            elif any(kara_kelime.lower() in name.lower() for kara_kelime in self.karaliste):
                await interaction.response.send_message("Uygunsuz kelime içeren bir oda ismi giremezsiniz.", ephemeral=True)
                return
            else:
                await voice_channel.edit(name=name)
                await interaction.response.send_message(f"Oda ismi {name} olarak ayarlandı.", ephemeral=True)
        else:
            await interaction.response.send_message("Bu işlemi yapmak için oda sahibi olmanız gerekmektedir.", ephemeral=True)

    @app_commands.command(name="sahiplik-aktar", description="Özel oda sahipliğini başka bir kullanıcıya aktarır")
    @app_commands.describe(kullanici="Yeni oda sahibi olacak kullanıcı")
    async def sahiplik_aktar(self, interaction: discord.Interaction, kullanici: discord.Member):
        # Kullanıcı bir ses kanalında mı kontrol et
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Bu komutu kullanmak için bir ses kanalında olmalısınız.", ephemeral=True)
            
        voice_channel = interaction.user.voice.channel

        # Kullanıcı kanal sahibi mi kontrol et
        if voice_channel.id in self.channel_owners and self.channel_owners[voice_channel.id] == interaction.user.id:
            # Sahipliği aktar
            self.channel_owners[voice_channel.id] = kullanici.id
            await voice_channel.edit(name=f"{kullanici.display_name}")
            await interaction.response.send_message(f"Oda sahipliği {kullanici} adlı kullanıcıya aktarıldı.", ephemeral=True)
        else:
            await interaction.response.send_message("Bu işlemi yapmak için oda sahibi olmanız gerekmektedir.", ephemeral=True)

    @app_commands.command(name="izin-ver", description="Belirlenen kullanıcıya özel odaya bağlanma izni verir")
    @app_commands.describe(kullanici="Odaya erişim izni verilecek kullanıcı")
    async def izin_ver(self, interaction: discord.Interaction, kullanici: discord.Member):
        # Kullanıcı bir ses kanalında mı kontrol et
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Bu komutu kullanmak için bir ses kanalında olmalısınız.", ephemeral=True)
            
        voice_channel = interaction.user.voice.channel

        # Kullanıcı kanal sahibi mi kontrol et
        if voice_channel.id in self.channel_owners and self.channel_owners[voice_channel.id] == interaction.user.id:
            # Kullanıcıya kanal izni ver
            await voice_channel.set_permissions(kullanici, connect=True)
            await interaction.response.send_message(f"{kullanici} adlı kullanıcıya odaya erişim izni verildi.", ephemeral=True)
        else:
            await interaction.response.send_message("Bu işlemi yapmak için oda sahibi olmanız gerekmektedir.", ephemeral=True)

    @app_commands.command(name="izin-sil", description="Belirlenen kullanıcının özel odaya bağlanma iznini kaldırır")
    @app_commands.describe(kullanici="Odaya erişim izni silinecek kullanıcı")
    async def izin_sil(self, interaction: discord.Interaction, kullanici: discord.Member):
        # Kullanıcı bir ses kanalında mı kontrol et
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Bu komutu kullanmak için bir ses kanalında olmalısınız.", ephemeral=True)
            
        voice_channel = interaction.user.voice.channel

        # Kullanıcı kanal sahibi mi kontrol et
        if voice_channel.id in self.channel_owners and self.channel_owners[voice_channel.id] == interaction.user.id:
            # Kullanıcıdan kanal iznini kaldır
            await voice_channel.set_permissions(kullanici, connect=False)
            await interaction.response.send_message(f"{kullanici} adlı kullanıcıdan odaya erişim izni silindi.", ephemeral=True)
        else:
            await interaction.response.send_message("Bu işlemi yapmak için oda sahibi olmanız gerekmektedir.", ephemeral=True)

    @app_commands.command(name="kilitle", description="Özel odayı kilitler")
    async def kilitle(self, interaction: discord.Interaction):
        # Kullanıcı bir ses kanalında mı kontrol et
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Bu komutu kullanmak için bir ses kanalında olmalısınız.", ephemeral=True)
            
        voice_channel = interaction.user.voice.channel
        guild = interaction.guild

        # Kullanıcı kanal sahibi mi kontrol et
        if voice_channel.id in self.channel_owners and self.channel_owners[voice_channel.id] == interaction.user.id:
            # @everyone rolü için "Bağlan" iznini kaldır
            overwrites = voice_channel.overwrites
            everyone_role = guild.default_role  # @everyone rolünü elde et
            overwrites[everyone_role] = discord.PermissionOverwrite(connect=False)

            # Kanal sahibi her zaman bağlanabilir
            overwrites[interaction.user] = discord.PermissionOverwrite(connect=True)
            await voice_channel.edit(overwrites=overwrites)

            await interaction.response.send_message("Oda kilitlendi.", ephemeral=True)
        else:
            await interaction.response.send_message("Bu işlemi yapmak için oda sahibi olmanız gerekmektedir.", ephemeral=True)

    @app_commands.command(name="kilit-ac", description="Özel odanın kilidini açar")
    async def kilit_ac(self, interaction: discord.Interaction):
        # Kullanıcı bir ses kanalında mı kontrol et
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Bu komutu kullanmak için bir ses kanalında olmalısınız.", ephemeral=True)
            
        voice_channel = interaction.user.voice.channel
        guild = interaction.guild

        # Kullanıcı kanal sahibi mi kontrol et
        if voice_channel.id in self.channel_owners and self.channel_owners[voice_channel.id] == interaction.user.id:
            # @everyone rolü için "Bağlan" iznini geri ver
            overwrites = voice_channel.overwrites
            everyone_role = guild.default_role  # @everyone rolünü elde et
            overwrites[everyone_role] = discord.PermissionOverwrite(connect=True)

            await voice_channel.edit(overwrites=overwrites)
            await interaction.response.send_message("Oda kilidi açıldı.", ephemeral=True)
        else:
            await interaction.response.send_message("Bu işlemi yapmak için oda sahibi olmanız gerekmektedir.", ephemeral=True)

    @app_commands.command(name="sil", description="Belirtilen sayıda mesajı siler (Sadece yetkili kullanıcılar)")
    @app_commands.describe(miktar="Silinecek mesaj sayısı (1-100 arası)")
    async def sil(self, interaction: discord.Interaction, miktar: int):
        # Yetkili kontrolü
        if not any(role.id in self.EXEMPT_ROLES for role in interaction.user.roles):
            return await interaction.response.send_message("Bu komutu kullanmak için yetkiniz yok!", ephemeral=True)
        
        # 100'den fazla mesaj silme girişimi kontrolü
        if miktar > 100:
            # YK-sohbet kanalına uyarı gönder
            yk_sohbet_channel = interaction.guild.get_channel(1362825668965957845)
            yk_role = interaction.guild.get_role(1029089731314720798)
            
            if yk_sohbet_channel and yk_role:
                try:
                    # Uyarı embed'i oluştur
                    embed = discord.Embed(
                        title="🚨 Yüksek Mesaj Silme Girişimi Tespit Edildi",
                        description=f"**İşlemi Yapmaya Çalışan:** {interaction.user.mention} ({interaction.user.name})\n"
                                   f"**Kanal:** {interaction.channel.mention}\n"
                                   f"**İstenen Miktar:** {miktar:,} mesaj",
                        color=discord.Color.red(),
                        timestamp=datetime.datetime.now(self.turkey_tz)
                    )
                    
                    embed.add_field(
                        name="⚠️ Güvenlik Bilgisi",
                        value="100'den fazla mesaj silme girişimi tespit edildi ve engelendi.\n"
                              "Bu işlem güvenlik protokolleri gereği engellenmektedir.",
                        inline=False
                    )
                    
                    embed.add_field(
                        name="👤 Kullanıcı Bilgileri",
                        value=f"**ID:** {interaction.user.id}\n"
                              f"**Katılma Tarihi:** {interaction.user.joined_at.strftime('%d/%m/%Y %H:%M') if interaction.user.joined_at else 'Bilinmiyor'}\n"
                              f"**Hesap Oluşturma:** {interaction.user.created_at.strftime('%d/%m/%Y %H:%M')}",
                        inline=False
                    )
                    
                    embed.set_thumbnail(url=interaction.user.display_avatar.url)
                    embed.set_footer(
                        text=f"{interaction.guild.name} • Güvenlik Sistemi",
                        icon_url=interaction.guild.icon.url if interaction.guild.icon else None
                    )
                    
                    # YK rolünü etiketleyerek mesaj gönder
                    await yk_sohbet_channel.send(
                        content=f"🚨 {yk_role.mention} **DİKKAT!** Yüksek sayıda mesaj silme girişimi tespit edildi!",
                        embed=embed
                    )
                    
                except Exception as e:
                    print(f"YK-sohbet kanalına yüksek mesaj silme uyarısı gönderme hatası: {e}")
            
            # Kullanıcıya hata mesajı
            return await interaction.response.send_message(
                f"❌ **Hata:** En fazla 100 mesaj silebilirsiniz. İstediğiniz miktar: {miktar:,}",
                ephemeral=True
            )
        
        # Geçersiz miktar kontrolü
        if miktar < 1:
            return await interaction.response.send_message("❌ **Hata:** En az 1 mesaj silmelisiniz.", ephemeral=True)
        
        # İşlem bilgisi
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Mesajları topla (silmeden önce log için)
            messages_to_delete = []
            deleted_messages_info = []
            
            async for message in interaction.channel.history(limit=miktar):
                messages_to_delete.append(message)
                # Mesaj bilgilerini sakla
                deleted_messages_info.append({
                    'author': message.author,
                    'content': message.content,
                    'created_at': message.created_at,
                    'id': message.id
                })
            
            # Mesajları sil
            deleted_count = len(messages_to_delete)
            await interaction.channel.delete_messages(messages_to_delete)
            
            # Sunucu-log kanalına bilgi gönder
            sunucu_log_channel = interaction.guild.get_channel(1365956201539571835)
            if sunucu_log_channel:
                try:
                    # UTC+3 (Türkiye saati) hesapla
                    turkish_time = datetime.datetime.now(self.turkey_tz)
                    
                    # Log embed'i oluştur
                    log_embed = discord.Embed(
                        title="🗑️ Toplu Mesaj Silme İşlemi",
                        description=f"**İşlemi Yapan:** {interaction.user.mention} ({interaction.user.name})\n"
                                   f"**Kanal:** {interaction.channel.mention}\n"
                                   f"**Silinen Mesaj Sayısı:** {deleted_count:,} mesaj",
                        color=discord.Color.orange(),
                        timestamp=turkish_time
                    )
                    
                    # Silinen mesajların detaylarını dosya olarak hazırla
                    file_content = None
                    if deleted_messages_info:
                        # Dosya içeriğini hazırla
                        file_lines = []
                        file_lines.append("=" * 60)
                        file_lines.append(f"SİLİNEN MESAJLAR RAPORU")
                        file_lines.append("=" * 60)
                        file_lines.append(f"İşlem Yapan: {interaction.user.name} ({interaction.user.id})")
                        file_lines.append(f"Kanal: #{interaction.channel.name} ({interaction.channel.id})")
                        # UTC+3 (Türkiye saati) hesapla
                        turkish_time = datetime.datetime.now(self.turkey_tz)
                        file_lines.append(f"Tarih: {turkish_time.strftime('%d/%m/%Y %H:%M:%S')} UTC+3")
                        file_lines.append(f"Toplam Silinen Mesaj: {len(deleted_messages_info)}")
                        file_lines.append("=" * 60)
                        file_lines.append("")
                        
                        for i, msg_info in enumerate(deleted_messages_info, 1):
                            # Mesaj zamanını UTC+3'e çevir
                            msg_created = msg_info['created_at']
                            if msg_created.tzinfo is None:
                                msg_created = msg_created.replace(tzinfo=datetime.timezone.utc)
                            msg_turkish_time = msg_created.astimezone(self.turkey_tz)
                            file_lines.append(f"[{i:03d}] {msg_turkish_time.strftime('%d/%m/%Y %H:%M:%S')}")
                            file_lines.append(f"Yazar: {msg_info['author'].name} ({msg_info['author'].id})")
                            file_lines.append(f"Mesaj ID: {msg_info['id']}")
                            
                            content = msg_info['content']
                            if content:
                                # Çok uzun mesajları kırp
                                if len(content) > 2000:
                                    content = content[:1997] + "..."
                                file_lines.append(f"İçerik: {content}")
                            else:
                                file_lines.append("İçerik: [Mesaj içeriği yok - Resim/Video/Embed olabilir]")
                            
                            file_lines.append("-" * 40)
                            file_lines.append("")
                        
                        # Dosya içeriğini string olarak birleştir
                        file_content = "\n".join(file_lines)
                        
                        # Embed'e sadece özet bilgi ekle
                        summary_text = f"Toplam {len(deleted_messages_info)} mesaj silindi.\n"
                        summary_text += "Detaylı rapor yukarıdaki dosyada bulunmaktadır."
                        
                        log_embed.add_field(
                            name="📝 Silinen Mesajlar",
                            value=summary_text,
                            inline=False
                        )
                    
                    log_embed.add_field(
                        name="👤 İşlem Yapan Bilgileri",
                        value=f"**ID:** {interaction.user.id}\n"
                              f"**İşlem Zamanı:** {discord.utils.format_dt(turkish_time, style='F')}",
                        inline=False
                    )
                    
                    log_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                    log_embed.set_footer(
                        text=f"{interaction.guild.name} • Sunucu Log Sistemi",
                        icon_url=interaction.guild.icon.url if interaction.guild.icon else None
                    )
                    
                    # Dosya varsa dosya ile birlikte gönder
                    if file_content:
                        # Geçici dosya oluştur
                        temp_file_path = None
                        try:
                            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as temp_file:
                                temp_file.write(file_content)
                                temp_file_path = temp_file.name
                            
                            # Dosya adını oluştur (UTC+3 ile)
                            timestamp = turkish_time.strftime('%Y%m%d_%H%M%S')
                            filename = f"silinen_mesajlar_{timestamp}.txt"
                            
                            # Embed + dosyayı birlikte gönder
                            await sunucu_log_channel.send(
                                embed=log_embed,
                                file=discord.File(temp_file_path, filename=filename)
                            )
                        finally:
                            # Geçici dosyayı temizle
                            if temp_file_path and os.path.exists(temp_file_path):
                                try:
                                    os.unlink(temp_file_path)
                                except Exception:
                                    pass
                    else:
                        # Dosya yoksa sadece embed gönder
                        # Fire-and-forget: Sunucu log background'da gönderilir
                        asyncio.create_task(self.safe_send(sunucu_log_channel, embed=log_embed))
                    
                except Exception as e:
                    print(f"Sunucu-log kanalına mesaj silme bilgisi gönderme hatası: {e}")
            
            # Kullanıcıya başarı mesajı
            await interaction.followup.send(
                f"✅ **Başarılı:** {deleted_count:,} mesaj başarıyla silindi.",
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ **Hata:** Mesajları silmek için gerekli izinlere sahip değilim.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ **Hata:** Mesaj silme işlemi sırasında bir sorun oluştu: {str(e)}",
                ephemeral=True
            )
        except Exception as e:
            print(f"Mesaj silme komutu hatası: {e}")
            await interaction.followup.send(
                "❌ **Hata:** Beklenmeyen bir hata oluştu.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(ExtraFeatures(bot))
