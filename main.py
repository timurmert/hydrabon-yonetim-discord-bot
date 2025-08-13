import os
import discord
import datetime
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from database import get_db

# .env dosyasından token yükleme
load_dotenv()
TOKEN = os.getenv('TOKEN')

# Bot yapılandırması
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

# Yetkili başvuru formundaki soru sayısı
FORM_QUESTION_COUNT = 5

# Kalıcı butonlar için View sınıfı
class PersistentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        style=discord.ButtonStyle.green,  # Daha modern yeşil buton
        label="Başvur",
        custom_id="staff_apply_button",
        emoji="📝"  # Başvuru için kalem emoji
    )
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Buton işlemi yetkili_alim cog'unda yapılacak
        pass

bot = commands.Bot(command_prefix="!", intents=intents)

# Bot hazır olduğunda çalışacak fonksiyon
@bot.event
async def on_ready():
    print(f"🤖 Bot başlatılıyor...")
    print(f"📊 Bot Adı: {bot.user.name} (ID: {bot.user.id})")
    print(f"🌐 Sunucu Sayısı: {len(bot.guilds)}")
    print(f"👥 Toplam Kullanıcı: {len(bot.users)}")
    
    # Bot başlangıç zamanını kaydet (uptime için)
    if not hasattr(bot, 'start_time'):
        bot.start_time = datetime.datetime.now()
    
    # Veritabanı bağlantısını kur
    print("💾 Veritabanı bağlantısı kuruluyor...")
    await get_db()
    print("✅ Veritabanı bağlantısı başarılı!")
    
    # Kalıcı görünümleri ekleme
    print("🔄 Kalıcı görünümler ekleniyor...")
    bot.add_view(PersistentView())
    print("✅ Kalıcı görünümler eklendi!")
    
    # Slash komutlarını global olarak senkronize et
    try:
        print("⚙️ Slash komutları senkronize ediliyor...")
        # Önce tüm komutları senkronize et
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} global komut senkronize edildi!")
        
        await bot.change_presence(activity=discord.Streaming(name="Kaplanları", url="https://www.twitch.tv/mrpresidentnotsjanymore"))
        print("🎮 Bot durumu ayarlandı!")
        
        # Tüm sunucularda komutları senkronize et
        print("🌐 Sunucu komutları senkronize ediliyor...")
        for guild in bot.guilds:
            try:
                await bot.tree.sync(guild=guild)
                print(f"✅ {guild.name} sunucusu senkronize edildi!")
            except Exception as e:
                print(f"❌ {guild.name} sunucusu için komut senkronizasyonu başarısız: {e}")
    except Exception as e:
        print(f"❌ Komut senkronizasyonu hatası: {e}")
    
    print("🚀 Bot tamamen hazır ve çalışıyor!")

# Bot kapatıldığında çalışacak fonksiyon
@bot.event
async def on_close():
    print("🔄 Bot kapatılıyor...")
    # Veritabanı bağlantısını kapat
    print("💾 Veritabanı bağlantısı kapatılıyor...")
    from database import db
    await db.close()
    print("✅ Veritabanı bağlantısı kapatıldı!")
    print("👋 Bot başarıyla kapatıldı!")

# Yönetici gruplandırması oluşturma
admin_group = app_commands.Group(name="admin", description="Yönetici komutları", 
                               default_permissions=discord.Permissions(administrator=True))
bot.tree.add_command(admin_group)

# Manuel olarak slash komutlarını senkronize etme komutu (slash komutuna dönüştürüldü)
@admin_group.command(name="sync", description="Slash komutlarını senkronize eder")
@app_commands.default_permissions(administrator=True)
async def sync_command(interaction: discord.Interaction):
    """Slash komutlarını senkronize eder"""
    # Kullanıcı ID kontrolü
    if interaction.user.id != 315888596437696522:
        await interaction.response.send_message("Bu komutu kullanma yetkiniz bulunmamaktadır.", ephemeral=True)
        return
        
    try:
        # Global komutları senkronize et
        await bot.tree.sync()
        
        # Sunucu özelinde senkronize et
        await bot.tree.sync(guild=interaction.guild)
        
        await interaction.response.send_message("Slash komutları başarıyla senkronize edildi! `/yetkilialim-kur` komutunu şimdi kullanabilirsiniz.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Komut senkronizasyonu sırasında hata oluştu: {e}", ephemeral=True)

# Modül yükleme komutu (slash komutuna dönüştürüldü)
@admin_group.command(name="load", description="Belirtilen modülü yükler")
@app_commands.default_permissions(administrator=True)
async def load_cmd(interaction: discord.Interaction, extension: str):
    # Kullanıcı ID kontrolü
    if interaction.user.id != 315888596437696522:
        await interaction.response.send_message("Bu komutu kullanma yetkiniz bulunmamaktadır.", ephemeral=True)
        return
        
    try:
        await bot.load_extension(f"cogs.{extension}")
        await interaction.response.send_message(f"`{extension}` modülü yüklendi.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"`{extension}` modülü yüklenirken hata oluştu: {e}", ephemeral=True)

# Modül kaldırma komutu (slash komutuna dönüştürüldü)
@admin_group.command(name="unload", description="Belirtilen modülü kaldırır")
@app_commands.default_permissions(administrator=True)
async def unload_cmd(interaction: discord.Interaction, extension: str):
    # Kullanıcı ID kontrolü
    if interaction.user.id != 315888596437696522:
        await interaction.response.send_message("Bu komutu kullanma yetkiniz bulunmamaktadır.", ephemeral=True)
        return
        
    try:
        await bot.unload_extension(f"cogs.{extension}")
        await interaction.response.send_message(f"`{extension}` modülü kaldırıldı.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"`{extension}` modülü kaldırılırken hata oluştu: {e}", ephemeral=True)

# Modül yeniden yükleme komutu (slash komutuna dönüştürüldü)
@admin_group.command(name="reload", description="Belirtilen modülü yeniden yükler")
@app_commands.default_permissions(administrator=True)
async def reload_cmd(interaction: discord.Interaction, extension: str):
    # Kullanıcı ID kontrolü
    if interaction.user.id != 315888596437696522:
        await interaction.response.send_message("Bu komutu kullanma yetkiniz bulunmamaktadır.", ephemeral=True)
        return
        
    try:
        await bot.reload_extension(f"cogs.{extension}")
        await interaction.response.send_message(f"`{extension}` modülü yeniden yüklendi.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"`{extension}` modülü yeniden yüklenirken hata oluştu: {e}", ephemeral=True)

# Cogs klasöründeki tüm modülleri yükleme
async def load_extensions():
    """Cog'ları yükleme fonksiyonu"""
    print("📦 Modüller yükleniyor...")
    
    extensions = [
        'cogs.yetkili_alim',
        'cogs.yetkili_panel',  # Yeni eklenen modül
        'cogs.server_logs',    # Sunucu log sistemi
        'cogs.extra_features', # Ekstra özellikler sistemi
        'cogs.bump_tracker',   # Bump takip sistemi
        'cogs.weekly_reports', # Haftalık rapor sistemi
        'cogs.user_notes'      # Kullanıcı notları sistemi
    ]
    
    successful_loads = 0
    total_extensions = len(extensions)
    
    for extension in extensions:
        try:
            await bot.load_extension(extension)
            print(f"✅ {extension}")
            successful_loads += 1
        except Exception as e:
            print(f'❌ {extension} modülü yüklenirken hata oluştu: {e}')
    
    print(f"📊 Modül Yükleme Sonucu: {successful_loads}/{total_extensions} başarılı")

# Yetkili alım sistemini kurma komutu
@admin_group.command(name="yetkilialim-kur", description="Yetkili alım sistemini kurar")
@app_commands.default_permissions(administrator=True)
async def setup_staff_application(interaction: discord.Interaction):
    # Kullanıcı ID kontrolü
    if interaction.user.id != 315888596437696522:
        await interaction.response.send_message("Bu komutu kullanma yetkiniz bulunmamaktadır.", ephemeral=True)
        return
        
    guild = interaction.guild
    
    # Yetkili Alım kategorisi oluşturma
    category_name = "YETKİLİ ALIM"
    existing_category = discord.utils.get(guild.categories, name=category_name)
    
    if existing_category:
        category = existing_category
        await interaction.response.send_message(f"`{category_name}` kategorisi zaten mevcut, onu kullanıyorum.", ephemeral=True)
    else:
        category = await guild.create_category(category_name)
        await interaction.response.send_message(f"`{category_name}` kategorisi oluşturuldu.", ephemeral=True)
    
    # Yetkili alım kanalı oluşturma
    application_channel_name = "yetkili-alım"
    existing_channel = discord.utils.get(guild.text_channels, name=application_channel_name)
    
    if existing_channel:
        application_channel = existing_channel
        await interaction.followup.send(f"`{application_channel_name}` kanalı zaten mevcut, onu kullanıyorum.", ephemeral=True)
    else:
        application_channel = await guild.create_text_channel(application_channel_name, category=category)
        await interaction.followup.send(f"`{application_channel_name}` kanalı oluşturuldu.", ephemeral=True)
    
    # Başvurular kanalı oluşturma (sadece yöneticilerin görebileceği)
    submissions_channel_name = "başvurular"
    existing_submissions = discord.utils.get(guild.text_channels, name=submissions_channel_name)
    
    if existing_submissions:
        submissions_channel = existing_submissions
        await interaction.followup.send(f"`{submissions_channel_name}` kanalı zaten mevcut, onu kullanıyorum.", ephemeral=True)
    else:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        
        # Yönetici rolü için izinleri ayarlama
        admin_roles = [role for role in guild.roles if role.permissions.administrator]
        for role in admin_roles:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        submissions_channel = await guild.create_text_channel(submissions_channel_name, category=category, overwrites=overwrites)
        await interaction.followup.send(f"`{submissions_channel_name}` kanalı oluşturuldu ve izinleri ayarlandı.", ephemeral=True)
    
    # Yetkili panel log kanalı oluşturma (sadece yöneticilerin görebileceği)
    log_channel_name = "yetkili-panel-log"
    existing_log = discord.utils.get(guild.text_channels, name=log_channel_name)
    
    if existing_log:
        log_channel = existing_log
        await interaction.followup.send(f"`{log_channel_name}` kanalı zaten mevcut, onu kullanıyorum.", ephemeral=True)
    else:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        
        # Yönetici rolü için izinleri ayarlama
        admin_roles = [role for role in guild.roles if role.permissions.administrator]
        for role in admin_roles:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        log_channel = await guild.create_text_channel(log_channel_name, category=category, overwrites=overwrites)
        await interaction.followup.send(f"`{log_channel_name}` kanalı oluşturuldu ve izinleri ayarlandı.", ephemeral=True)
    
    # Yetkili alım kanalına şık başvuru embed'i gönderme
    embed = discord.Embed(
        title="🌟 Yetkili Alım Başvurusu 🌟",
        description=(
            "### 📢 HydRaboN'da Yetkili Olmak İster Misiniz?\n\n"
            "• Ekibimize katılarak sizler de birçok ayrıcalıktan yararlanabilirsiniz.\n"
            "• Yetkili ekibimizin bir parçası olmak için aşağıdaki **Başvur** butonuna tıklayın ve başvuru formunu doldurun.\n\n"
            f"📋 **Başvuru Süreci:**\n"
            f"• Form toplam **{FORM_QUESTION_COUNT}** sorudan oluşmaktadır.\n"
            f"• Tüm sorulara dürüst ve detaylı cevaplar vermeniz önemlidir.\n"
            f"• Başvurunuz yetkililer tarafından incelenecek ve size geri dönüş yapılacaktır.\n\n"
            f"✨ **İyi Şanslar!** ✨"
        ),
        color=0x2b82ff  # Mavi renk tonu (daha canlı)
    )
    
    # Embed'e görsel ekleme
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
        
    # Zaman damgası ve footer ekleme
    embed.set_footer(text=f"{guild.name} • Yetkili Alım Sistemi", icon_url=guild.icon.url if guild.icon else None)
    embed.timestamp = discord.utils.utcnow()
    
    # Kalıcı buton görünümü
    view = PersistentView()
    
    await application_channel.send(embed=embed, view=view)
    await interaction.followup.send("Başvuru butonu yetkili alım kanalına gönderildi.", ephemeral=True)
    
    # Yükleme tamamlandı mesajı
    kurulum_tamamlandi_embed = discord.Embed(
        title="🛡️ HydRaboN Yetkili Sistemi Kurulumu Tamamlandı",
        description=(
            "Yetkili alım ve panel sistemi başarıyla kuruldu!\n\n"
            "Kullanabileceğiniz komutlar:\n"
            "• `/yetkili-panel` - Yetkili işlemleri için panel açar\n"
            "• `/admin yetkili-istatistik` - Yetkili başvuru istatistiklerini gösterir\n"
            "• `/admin basvuru-ara` - Kullanıcının başvurusunu görüntüler\n\n"
            "Yetkili panel ile yapabileceğiniz işlemler:\n"
            "• Yetkili işlemleri (yükseltme, düşürme)\n"
            "• Başvuru sorgulama\n"
            "• Yetkili duyuruları gönderme (admin yetkisi gerektirir)\n"
            "• Sunucu/başvuru istatistiklerini görüntüleme"
        ),
        color=0x2b82ff
    )
    
    if guild.icon:
        kurulum_tamamlandi_embed.set_thumbnail(url=guild.icon.url)
    
    await interaction.followup.send(embed=kurulum_tamamlandi_embed, ephemeral=True)

# Sunucu log kanalı kurma komutu
@admin_group.command(name="sunuculog-kur", description="Sunucu log kanalını kurar")
@app_commands.default_permissions(administrator=True)
async def setup_server_logs(interaction: discord.Interaction):
    """Sunucu log kanalı kurulum komutu"""
    # Kullanıcı ID kontrolü
    if interaction.user.id != 315888596437696522:
        await interaction.response.send_message("Bu komutu kullanma yetkiniz bulunmamaktadır.", ephemeral=True)
        return
        
    try:
        # ServerLogs cog'unu al
        server_logs_cog = bot.get_cog("ServerLogs")
        
        if server_logs_cog is None:
            return await interaction.response.send_message(
                "❌ ServerLogs modülü bulunamadı veya yüklenmemiş!", 
                ephemeral=True
            )
        
        # logkanal-kur komutunu çalıştır
        await server_logs_cog.setup_log_channel(interaction)
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Log kanalı kurulumu sırasında bir hata oluştu: {e}", 
            ephemeral=True
        )

# Spam istatistikleri komut
@admin_group.command(name="spam-istatistik", description="Spam koruma sistemi istatistiklerini gösterir")
@app_commands.default_permissions(administrator=True)
async def spam_stats_cmd(interaction: discord.Interaction, gun: int = 30):
    """Spam koruma istatistiklerini görüntüler"""
    # Kullanıcı ID kontrolü
    if interaction.user.id != 315888596437696522:
        await interaction.response.send_message("Bu komutu kullanma yetkiniz bulunmamaktadır.", ephemeral=True)
        return
        
    try:
        from database import get_db
        db = await get_db()
        
        # Spam istatistiklerini al
        stats = await db.get_spam_stats(interaction.guild.id, gun)
        
        # Embed oluştur
        embed = discord.Embed(
            title="📊 Spam Koruma İstatistikleri",
            description=f"**Son {gun} gün içerisindeki spam verileri**",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # Ana istatistikler
        embed.add_field(
            name="📈 Genel İstatistikler",
            value=f"**Toplam Spam Olayı:** {stats['total_spam']}\n"
                  f"**Spam Yapan Kullanıcı:** {stats['spam_users']}\n"
                  f"**Analiz Süresi:** {stats['period_days']} gün",
            inline=False
        )
        
        # En çok spam yapan kullanıcılar
        if stats['top_spammers']:
            top_spammers_text = []
            for i, spammer in enumerate(stats['top_spammers'][:5], 1):
                user = interaction.guild.get_member(spammer['user_id'])
                user_mention = user.mention if user else f"Bilinmeyen Kullanıcı ({spammer['user_id']})"
                top_spammers_text.append(f"**{i}.** {user_mention} - {spammer['spam_count']} spam")
            
            embed.add_field(
                name="🏆 En Çok Spam Yapan Kullanıcılar (Top 5)",
                value="\n".join(top_spammers_text),
                inline=False
            )
        else:
            embed.add_field(
                name="🏆 En Çok Spam Yapan Kullanıcılar",
                value="Son dönemde spam tespit edilmedi. 🎉",
                inline=False
            )
        
        # Sistem bilgileri
        extra_features_cog = bot.get_cog("ExtraFeatures")
        if extra_features_cog:
            # Cache performans bilgileri
            total_messages_in_cache = sum(len(user_data['messages']) for user_data in extra_features_cog.user_message_cache.values())
            
            embed.add_field(
                name="⚙️ Sistem Ayarları",
                value=f"**Spam Mesaj Limiti:** {extra_features_cog.SPAM_MESSAGE_LIMIT} aynı mesaj\n"
                      f"**Zaman Penceresi:** {extra_features_cog.SPAM_TIME_WINDOW} saniye\n"
                      f"**Timeout Süresi:** {extra_features_cog.SPAM_TIMEOUT_DURATION} gün",
                inline=False
            )
            
            embed.add_field(
                name="📊 Cache Performansı",
                value=f"**Aktif Kullanıcı:** {len(extra_features_cog.user_message_cache)}/{extra_features_cog.MAX_CACHE_USERS}\n"
                      f"**Toplam Mesaj Cache:** {total_messages_in_cache}\n"
                      f"**Kullanıcı Başına Limit:** {extra_features_cog.MAX_MESSAGES_PER_USER}\n"
                      f"**Cache Temizlik Aralığı:** {extra_features_cog.CACHE_CLEANUP_INTERVAL}s\n"
                      f"**İnaktif Timeout:** {extra_features_cog.INACTIVE_USER_TIMEOUT}s",
                inline=False
            )
        
        embed.set_footer(
            text=f"{interaction.guild.name} • Spam Koruma Sistemi",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Spam istatistikleri alınırken hata oluştu: {e}", 
            ephemeral=True
        )

# Veritabanı temizlik komutu
@admin_group.command(name="veritabani-temizle", description="Eski spam, bump ve member loglarını temizler")
@app_commands.default_permissions(administrator=True)
async def cleanup_database_cmd(interaction: discord.Interaction, spam_gun: int = 90, bump_gun: int = 365, member_gun: int = 90):
    """Veritabanı temizlik komutu"""
    # Kullanıcı ID kontrolü
    if interaction.user.id != 315888596437696522:
        await interaction.response.send_message("Bu komutu kullanma yetkiniz bulunmamaktadır.", ephemeral=True)
        return
        
    try:
        await interaction.response.send_message("🧹 Veritabanı temizliği başlatılıyor...", ephemeral=True)
        
        from database import get_db
        db = await get_db()
        
        # Temizlik işlemini başlat
        results = await db.cleanup_all_old_logs(spam_days=spam_gun, bump_days=bump_gun, member_days=member_gun)
        
        # Sonuç embed'i oluştur
        embed = discord.Embed(
            title="🧹 Veritabanı Temizliği Tamamlandı",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="📊 Temizlik Sonuçları",
            value=f"**Silinen Spam Kaydı:** {results['spam_logs_deleted']}\n"
                  f"**Silinen Bump Kaydı:** {results['bump_logs_deleted']}\n"
                  f"**Silinen Member Kaydı:** {results['member_logs_deleted']}\n"
                  f"**Toplam Silinen:** {results['total_deleted']}",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Temizlik Ayarları",
            value=f"**Spam Log Limit:** {spam_gun} gün\n"
                  f"**Bump Log Limit:** {bump_gun} gün\n"
                  f"**Member Log Limit:** {member_gun} gün",
            inline=False
        )
        
        # Boyut bilgilerini al
        size_info = await db.get_database_size_info()
        embed.add_field(
            name="💾 Veritabanı Durumu",
            value=f"**Spam Kayıt:** {size_info['spam_logs_count']}\n"
                  f"**Bump Kayıt:** {size_info['bump_logs_count']}\n"
                  f"**Member Kayıt:** {size_info['member_logs_count']}\n"
                  f"**Başvuru Kayıt:** {size_info['applications_count']}\n"
                  f"**Tahmini Boyut:** {size_info['estimated_size_human']}",
            inline=False
        )
        
        embed.set_footer(
            text=f"{interaction.guild.name} • Veritabanı Yönetimi",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Veritabanı temizliği sırasında hata oluştu: {e}", 
            ephemeral=True
        )

# Haftalık rapor komutları weekly_reports.py'de tanımlanmıştır

# Bot'u çalıştırma
async def main():
    print("=" * 50)
    print("🌟 HydRaboN Discord Bot Başlatılıyor...")
    print(f"⏰ Başlangıç Zamanı: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    print("=" * 50)
    
    async with bot:
        await load_extensions()
        print("🔗 Discord'a bağlanılıyor...")
        await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 