import discord
import datetime
import pytz
from discord.ext import commands
from typing import Optional, Union
import asyncio
import re
import random

class ServerLogs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.role_position_updates = {}  # Guild ID: {timestamp: [(role, old_pos, new_pos)]}
        self.position_update_delay = 2  # 2 saniye bekle
        self.log_channel = None
        self.target_guild_id = 1029088146752815138  # İzlenmeyecek sunucu ID'si
        self.alert_channel_id = 1362825644550914263  # Uyarı gönderilecek kanal ID'si
        
        # Yetkili rol ID'leri
        self.yetkili_rolleri = {
            "STAJYER": 1163918714081644554,
            "ASİSTAN": 1200919832393154680,
            "MODERATÖR": 1163918107501412493,
            "ADMİN": 1163918130192580608,
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

    async def safe_send(self, channel, content=None, embed=None, max_retries=3):
        """Güvenli mesaj gönderme fonksiyonu - Retry sistemi ile"""
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
        if message.author.bot:
            return  # Bot mesajlarını loglama
            
        if not message.guild:
            return  # Özel mesajları loglama
            
        # Embed oluştur
        embed = discord.Embed(
            title="Mesaj Silindi",
            description=f"**Kanal:** {message.channel.mention}\n"
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
            description=f"**Kanal:** {before.channel.mention}\n"
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
                              f"**Kanal:** {after.channel.mention} ({after.channel.name})"
        
        elif before.channel is not None and after.channel is None:
            # Ses kanalından ayrılma
            embed.title = "Ses Kanalından Ayrıldı"
            embed.description = f"**Kullanıcı:** {member.mention} ({member.name})\n" \
                              f"**Kanal:** {before.channel.mention} ({before.channel.name})"
        
        elif before.channel != after.channel:
            # Ses kanalı değiştirme
            embed.title = "Ses Kanalı Değiştirildi"
            embed.description = f"**Kullanıcı:** {member.mention} ({member.name})\n" \
                              f"**Önceki Kanal:** {before.channel.mention} ({before.channel.name})\n" \
                              f"**Yeni Kanal:** {after.channel.mention} ({after.channel.name})"
        
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
                
                await self.send_log_embed(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        """Yeni oluşturulan kanalları loglar"""
        # Audit log'dan kimin oluşturduğunu bul
        executor = await self.get_audit_log_executor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        executor_info = await self.format_executor_info(executor)
        
        embed = discord.Embed(
            title="Kanal Oluşturuldu",
            description=f"**Kanal:** {channel.mention} ({channel.name})\n"
                        f"**Kanal ID:** {channel.id}\n"
                        f"**Kanal Türü:** {str(channel.type).replace('_', ' ').title()}\n"
                        f"{executor_info}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        # Kategori bilgisi
        if hasattr(channel, 'category') and channel.category:
            embed.add_field(name="Kategori", value=channel.category.name, inline=False)
        
        await self.send_log_embed(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Silinen kanalları loglar"""
        # Audit log'dan kimin sildiğini bul
        executor = await self.get_audit_log_executor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        executor_info = await self.format_executor_info(executor)
        
        embed = discord.Embed(
            title="Kanal Silindi",
            description=f"**Kanal:** #{channel.name}\n"
                        f"**Kanal ID:** {channel.id}\n"
                        f"**Kanal Türü:** {str(channel.type).replace('_', ' ').title()}\n"
                        f"{executor_info}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        # Kategori bilgisi
        if hasattr(channel, 'category') and channel.category:
            embed.add_field(name="Kategori", value=channel.category.name, inline=False)
        
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
                description=f"**Kanal:** {after.mention} ({after.name})\n"
                            f"**Kanal ID:** {after.id}\n"
                            f"{executor_info}",
                color=discord.Color.gold(),
                timestamp=datetime.datetime.now(self.turkey_tz)
            )
            
            # Değişiklikleri ekle
            embed.add_field(name="Değişiklikler", value="\n".join(changes), inline=False)
            
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
            
        # 3. Aktivite değişikliği kontrolü (sadece aktivite değişirse kontrol et)
        if before.activities == after.activities:
            return
            
        # 4. Aktivite varlığı kontrolü
        if not after.activities:
            return
            
        # 5. Yetkili kontrolü (sadece gerektiğinde)
        user_role_ids = {role.id for role in after.roles}  # Set kullanarak hızlandır
        
        # Intersection kullanarak hızlı kontrol (cached set kullan)
        if not user_role_ids.intersection(self.yetkili_role_ids):
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
                # Diğer Discord hataları, sessizce geç
                pass

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
                title="⚠️ Yetkili Şüpheli Link Uyarısı",
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