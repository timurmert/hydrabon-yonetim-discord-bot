import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import datetime
from database import get_db
import pytz
turkey_tz = pytz.timezone('Europe/Istanbul')

# Ana dosyada tanımlanan değeri burada da tanımlayarak senkronize ediyoruz
FORM_QUESTION_COUNT = 5

# Başvuruların gönderileceği kanal ID'si
BASVURU_CHANNEL_ID = 1365954139607269436
YETKILI_ALIM_CATEGORY_ID = 1365954135190409226

class YetkiliAlim(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Formlar için kullanıcıların durumlarını takip etme
        self.active_applications = {}
    
    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        """Buton etkileşimlerini dinleyen ve ilgili fonksiyonu çağıran metod"""
        if not interaction.type == discord.InteractionType.component:
            return
        
        custom_id = interaction.data.get('custom_id', '')
        
        if custom_id == 'staff_apply_button':
            await self.handle_application_button(interaction)
        elif custom_id.startswith('approve_'):
            # Yetkili rolü kontrolü
            allowed_role_ids = [1029089723110674463, 1029089727061692522, 1029089731314720798, 1412843482980290711]  # KURUCU, YÖNETİM KURULU BAŞKANI, YÖNETİM KURULU ÜYELERİ, YÖNETİM KURULU ADAYLARI
            user_has_permission = interaction.user.guild_permissions.administrator or any(role.id in allowed_role_ids for role in interaction.user.roles)
            
            if not user_has_permission:
                return await interaction.response.send_message(
                    "Bu işlemi gerçekleştirmek için gerekli yetkiye sahip değilsiniz. Bu işlem için KURUCU, YÖNETİM KURULU BAŞKANI, YÖNETİM KURULU ÜYELERİ veya YÖNETİM KURULU ADAYLARI rollerine sahip olmanız gerekiyor.", 
                    ephemeral=True
                )
            
            user_id = int(custom_id.split('_')[1])
            user = interaction.guild.get_member(user_id)
            
            if not user:
                return await interaction.response.send_message(
                    "Kullanıcı sunucuda bulunamadı.", 
                    ephemeral=True
                )
            
            # Veritabanından başvuru bilgisini kontrol et - onaylanmış veya reddedilmiş mi
            try:
                db = await get_db()
                application = await db.get_application_by_user_id(user_id)
                
                if application and application['status'] != 'pending':
                    # Başvuru zaten işlenmiş
                    status_text = "onaylanmış" if application['status'] == "approved" else "reddedilmiş"
                    return await interaction.response.send_message(
                        f"Bu başvuru zaten {status_text}. Başvuru ID: {application['id']}", 
                        ephemeral=True
                    )
            except Exception as e:
                print(f"Başvuru durumu kontrolü hatası: {e}")
            
            # Modal üzerinden yetkili rolü ve mesaj girişi
            await interaction.response.send_modal(StaffApprovalModal(user))
            
        elif custom_id.startswith('reject_'):
            # Yetkili rolü kontrolü
            allowed_role_ids = [1029089723110674463, 1029089727061692522, 1029089731314720798, 1412843482980290711]  # KURUCU, YÖNETİM KURULU BAŞKANI, YÖNETİM KURULU ÜYELERİ, YÖNETİM KURULU ADAYLARI
            user_has_permission = interaction.user.guild_permissions.administrator or any(role.id in allowed_role_ids for role in interaction.user.roles)
            
            if not user_has_permission:
                return await interaction.response.send_message(
                    "Bu işlemi gerçekleştirmek için gerekli yetkiye sahip değilsiniz. Bu işlem için KURUCU, YÖNETİM KURULU BAŞKANI, YÖNETİM KURULU ÜYELERİ veya YÖNETİM KURULU ADAYLARI rollerine sahip olmanız gerekiyor.", 
                    ephemeral=True
                )
            
            user_id = int(custom_id.split('_')[1])
            user = interaction.guild.get_member(user_id)
            
            if not user:
                return await interaction.response.send_message(
                    "Kullanıcı sunucuda bulunamadı.", 
                    ephemeral=True
                )
            
            # Veritabanından başvuru bilgisini kontrol et - onaylanmış veya reddedilmiş mi
            try:
                db = await get_db()
                application = await db.get_application_by_user_id(user_id)
                
                if application and application['status'] != 'pending':
                    # Başvuru zaten işlenmiş
                    status_text = "onaylanmış" if application['status'] == "approved" else "reddedilmiş"
                    return await interaction.response.send_message(
                        f"Bu başvuru zaten {status_text}. Başvuru ID: {application['id']}", 
                        ephemeral=True
                    )
            except Exception as e:
                print(f"Başvuru durumu kontrolü hatası: {e}")
            
            # Modal üzerinden ret sebebi girişi
            await interaction.response.send_modal(StaffRejectionModal(user))
    
    async def handle_application_button(self, interaction):
        """Yetkili başvuru butonuna tıklandığında çalışan fonksiyon"""
        
        # Kullanıcının zaten başvuru sürecinde olup olmadığını kontrol etme
        if interaction.user.id in self.active_applications:
            return await interaction.response.send_message(
                "Zaten aktif bir başvuru sürecindesiniz. Lütfen önce onu tamamlayın.", 
                ephemeral=True
            )
        
        await interaction.response.send_message(
            "Yetkili başvuru formunu doldurmak üzeresiniz. Lütfen sorulara özenle cevap verin.\n"
            "İptal etmek için herhangi bir aşamada `iptal` yazabilirsiniz.", 
            ephemeral=True
        )
        
        # Başvuru durumunu aktif olarak işaretleme
        self.active_applications[interaction.user.id] = {
            "step": 0,
            "answers": {},
            "channel": interaction.channel,
            "guild": interaction.guild,
        }
        
        # Kullanıcıya özel başvuru kanalı oluşturma
        # Bu kanal yetkili alım kategorisinde ve sadece başvuran kişi görebilecek
        category = interaction.guild.get_channel(YETKILI_ALIM_CATEGORY_ID)
        if not category:
            return await interaction.followup.send(
                "Yetkili Alım kategorisi bulunamadı. Lütfen bir yetkiliyle iletişime geçin.", 
                ephemeral=True
            )
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        channel_name = f"başvuru-{interaction.user.name}"
        # Discord kanalları için güvenli bir isim oluşturma
        channel_name = ''.join(c for c in channel_name if c.isalnum() or c == '-').lower()
        channel_name = channel_name[:32]  # Discord kanal ismi uzunluk limiti
        
        try:
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"{interaction.user.name}'in yetkili başvurusu"
            )
            
            self.active_applications[interaction.user.id]["private_channel"] = channel
            
            # Başvuru kanalına hoş geldin mesajı - daha şık bir embed ile
            embed = discord.Embed(
                title="📝 Yetkili Başvuru Formu",
                description=(
                    f"### Merhaba {interaction.user.mention}! \n\n"
                    f"Yetkili başvuru sürecine hoş geldiniz. Sizi daha iyi tanımak ve sunucumuza ne katabileceğinizi "
                    f"görmek için aşağıdaki soruları cevaplamanızı rica ediyoruz.\n\n"
                    f"📋 **Başvuru Bilgileri:**\n"
                    f"• Toplam **{FORM_QUESTION_COUNT}** soru cevaplamanız gerekiyor\n"
                    f"• Her soruya detaylı ve dürüst bir şekilde cevap verin\n"
                    f"• Başvurunuzu iptal etmek için herhangi bir aşamada `iptal` yazabilirsiniz\n"
                    f"• Bir soru için 10 dakika içinde cevap vermezseniz başvurunuz iptal edilir\n\n"
                    f"İlk sorunuz birkaç saniye içinde gönderilecek..."
                ),
                color=0x2b82ff
            )
            
            if interaction.guild.icon:
                embed.set_thumbnail(url=interaction.guild.icon.url)
            
            embed.set_footer(text=f"{interaction.guild.name} • Yetkili Alım Sistemi", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            embed.timestamp = datetime.datetime.now(turkey_tz)
            
            await channel.send(embed=embed)
            
            # Kullanıcıya yönlendirme
            await interaction.followup.send(
                f"Başvuru kanalınız oluşturuldu: {channel.mention}\n"
                "Lütfen soruları cevaplamak için o kanala geçiş yapın.", 
                ephemeral=True
            )
            
            # Formu başlatma
            await self.start_application_form(interaction.user)
            
        except Exception as e:
            if interaction.user.id in self.active_applications:
                del self.active_applications[interaction.user.id]
            await interaction.followup.send(
                f"Başvuru kanalı oluşturulurken bir hata meydana geldi: {str(e)}", 
                ephemeral=True
            )
    
    async def start_application_form(self, user):
        """Başvuru formunu başlatan ve soruları soran fonksiyon"""
        
        # Form soruları
        questions = [
            "Adınız ve yaşınız nedir?",
            "Discord'da günde kaç saat aktif olabilirsiniz?",
            "Discord sunucularında yetkililik deneyiminiz var mı? Varsa ne kadar süre?",
            "Sunucumuzda yetkili olmak isteme sebebiniz nedir?",
            "Sizce iyi bir Discord yetkilisinin sahip olması gereken özellikler nelerdir?"
        ]
        
        # Senkronizasyon kontrolü
        if len(questions) != FORM_QUESTION_COUNT:
            print(f"UYARI: Tanımlanan soru sayısı ({FORM_QUESTION_COUNT}) ile gerçek soru sayısı ({len(questions)}) uyuşmuyor!")
        
        app_data = self.active_applications.get(user.id)
        if not app_data:
            return
        
        channel = app_data["private_channel"]
        
        # Her soru için döngü
        for i, question in enumerate(questions):
            app_data["step"] = i + 1
            
            # Soruyu gönder - daha şık embed ile
            embed = discord.Embed(
                title=f"Soru {i+1}/{len(questions)}",
                description=question,
                color=0x2b82ff
            )
            
            # İlerleme çubuğu ekle (emoji ile gösterim)
            progress = int((i + 1) / len(questions) * 10)
            progress_bar = "▰" * progress + "▱" * (10 - progress)
            embed.add_field(name=f"İlerleme: {progress_bar} ({i+1}/{len(questions)})", value="", inline=False)
            
            await channel.send(embed=embed)
            
            # Kullanıcı cevabını bekle
            try:
                def check(m):
                    return m.author.id == user.id and m.channel.id == channel.id
                
                message = await self.bot.wait_for("message", check=check, timeout=600)  # 10 dakika timeout
                
                # İptal kontrolü
                if message.content.lower() == "iptal":
                    # İptal nedeni sormak için embed
                    reason_embed = discord.Embed(
                        title="ℹ️ İptal Nedeni",
                        description="Başvurunuzu neden iptal etmek istediğinizi kısaca belirtebilir misiniz?\n\n*Cevaplamak istemiyorsanız, 'belirtmek istemiyorum' yazabilirsiniz.*",
                        color=discord.Color.gold()
                    )
                    await channel.send(embed=reason_embed)
                    
                    # İptal nedeni cevabını bekle
                    try:
                        reason_msg = await self.bot.wait_for("message", check=check, timeout=120)  # 2 dakika timeout
                        cancel_reason = reason_msg.content
                    except asyncio.TimeoutError:
                        cancel_reason = "Kullanıcı iptal nedeni belirtmedi (zaman aşımı)"
                    
                    # İptal onay mesajı
                    cancel_embed = discord.Embed(
                        title="❌ Başvuru İptal Edildi",
                        description="Başvurunuz isteğiniz üzerine iptal edildi. Bu kanal 10 saniye içinde silinecek.",
                        color=discord.Color.red()
                    )
                    await channel.send(embed=cancel_embed)
                    
                    # İptal edilen başvuruyu başvurular kanalına gönder
                    await self.send_cancelled_application(user, app_data, i+1, question, cancel_reason)
                    
                    await asyncio.sleep(10)
                    await channel.delete()
                    if user.id in self.active_applications:
                        del self.active_applications[user.id]
                    return
                
                # Cevabı kaydetme
                app_data["answers"][question] = message.content
                
                # Cevap sonrası onay mesajı
                if i < len(questions) - 1:  # Son soru değilse
                    await message.add_reaction("🧡")
                else:
                    await message.add_reaction("🧡")
                
            except asyncio.TimeoutError:
                timeout_embed = discord.Embed(
                    title="⏰ Zaman Aşımı",
                    description="Uzun süre yanıt vermediğiniz için başvurunuz iptal edildi. Bu kanal 10 saniye içinde silinecek.",
                    color=discord.Color.red()
                )
                await channel.send(embed=timeout_embed)
                
                # Zaman aşımına uğrayan başvuruyu başvurular kanalına gönder
                await self.send_cancelled_application(user, app_data, i+1, question, "Kullanıcı uzun süre yanıt vermedi (zaman aşımı)")
                
                # Kullanıcıya DM ile zaman aşımı bildirimi gönder
                await self.send_timeout_dm(user, i+1, len(questions))
                
                await asyncio.sleep(10)
                await channel.delete()
                if user.id in self.active_applications:
                    del self.active_applications[user.id]
                return
        
        # Başvuru tamamlandığında özet gönderme
        await self.complete_application(user)
    
    async def complete_application(self, user):
        """Başvuruyu tamamlayan ve sonuçları yetkililere gönderen fonksiyon"""
        app_data = self.active_applications.get(user.id)
        if not app_data:
            return
        
        channel = app_data["private_channel"]
        guild = app_data["guild"]
        
        # Kullanıcıya tamamlama mesajı - daha şık embed ile
        completion_embed = discord.Embed(
            title="🎉 Başvurunuz Tamamlandı!",
            description=(
                "Tebrikler! Yetkili başvurunuz başarıyla alındı.\n\n"
                "📋 **Sonraki Adımlar:**\n"
                "• Başvurunuz yetkililerimiz tarafından incelenecek\n"
                "• Sonuç hakkında size özel mesaj ile bilgilendirme yapılacak\n"
                "• Dolayısıyla DM kutunuzun açık olduğundan emin olunuz\n"
                "• Bu kanal 60 saniye içinde otomatik olarak silinecektir\n\n"
                "Gösterdiğiniz ilgi için teşekkür ederiz!"
            ),
            color=discord.Color.green()
        )
        
        if guild.icon:
            completion_embed.set_thumbnail(url=guild.icon.url)
            
        completion_embed.set_footer(text=f"{guild.name} • Yetkili Alım Sistemi", icon_url=guild.icon.url if guild.icon else None)
        completion_embed.timestamp = datetime.datetime.now(turkey_tz)
        
        await channel.send(embed=completion_embed)
        
        # Veritabanına başvuruyu kaydet
        db = await get_db()
        application_id = await db.save_staff_application(
            user_id=user.id,
            username=user.name,
            answers=app_data["answers"]
        )
        
        # Kullanıcı notlarını kontrol et
        user_notes = []
        try:
            notes = await db.get_user_notes(user.id, guild.id, limit=5)
            if notes:
                user_notes = notes
        except Exception as e:
            print(f"Kullanıcı notları alınırken hata: {e}")
        
        # Başvuru özetini oluşturma - daha şık bir başvuru özeti
        embed = discord.Embed(
            title="📑 Yetkili Başvurusu",
            description=f"{user.mention} ({user.name}) tarafından gönderildi.",
            color=0x2b82ff,
            timestamp=datetime.datetime.now()
        )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Kullanıcı bilgileri bölümü
        embed.add_field(name="👤 Kullanıcı Bilgileri", value="", inline=False)
        embed.add_field(name="ID", value=user.id, inline=True)
        embed.add_field(name="Katılma Tarihi", value=user.joined_at.strftime("%d/%m/%Y"), inline=True)
        embed.add_field(name="Hesap Oluşturma", value=user.created_at.strftime("%d/%m/%Y"), inline=True)
        
        # Roller bölümü (varsa)
        if len(user.roles) > 1:  # @everyone hariç rol varsa
            roles = [role.mention for role in user.roles if role.name != "@everyone"]
            if roles:
                embed.add_field(name="🏷️ Roller", value=" ".join(roles), inline=False)
        
        # Form cevapları bölümü
        embed.add_field(name="📝 Form Cevapları", value="", inline=False)
        
        # Cevapları ekle
        for i, (question, answer) in enumerate(app_data["answers"].items()):
            embed.add_field(name=f"Soru {i+1}", value=f"**{question}**\n{answer[:1024]}", inline=False)
        
        # Veritabanı ID'sini ekle (yöneticilerin referans için kullanması için)
        embed.add_field(name="📊 Sistem Bilgisi", value=f"Başvuru ID: `{application_id}`", inline=False)
        
        # Kullanıcı notları bölümü (varsa) - formun en altında göze çarpacak şekilde
        if user_notes:
            notes_text = []
            for i, note in enumerate(user_notes, 1):
                created_date = datetime.datetime.fromisoformat(note['created_at']).replace(tzinfo=datetime.timezone.utc)
                created_date_tr = created_date.astimezone(turkey_tz).strftime('%d.%m.%Y')
                content_preview = note['note_content'][:80] + "..." if len(note['note_content']) > 80 else note['note_content']
                notes_text.append(f"**#{note['id']}** - {created_date_tr}\n└ {content_preview}\n└ Ekleyen: {note['created_by_username']}")
            
            notes_field_value = "\n\n".join(notes_text)
            # Eğer çok uzunsa kısalt
            if len(notes_field_value) > 1024:
                notes_field_value = notes_field_value[:1000] + f"\n\n*...ve {len(user_notes) - 2} not daha var*"
            
            embed.add_field(
                name="⚠️ KULLANICI HAKKINDA NOTLAR ⚠️",
                value=notes_field_value,
                inline=False
            )
        
        # Başvurular kanalına gönderme (ID ile alınıyor)
        submissions_channel = guild.get_channel(BASVURU_CHANNEL_ID)
        if submissions_channel:
            # Onay/Ret butonları
            view = discord.ui.View(timeout=None)
            approve_button = discord.ui.Button(
                style=discord.ButtonStyle.green, 
                label="Onayla", 
                custom_id=f"approve_{user.id}",
                emoji="✅"
            )
            reject_button = discord.ui.Button(
                style=discord.ButtonStyle.danger, 
                label="Reddet", 
                custom_id=f"reject_{user.id}",
                emoji="❌"
            )
            view.add_item(approve_button)
            view.add_item(reject_button)
            
            # Mesajı gönder ve referansını sakla
            message = await submissions_channel.send(embed=embed, view=view)
            
            # Mesaj ID'sini veritabanına kaydet (opsiyonel olarak yapılabilir)
            try:
                # İleriki bir iyileştirme olarak veritabanına mesaj ID'si de eklenebilir
                pass
            except Exception as e:
                print(f"Mesaj ID kaydetme hatası: {e}")
        
        # Kullanıcı durumunu temizleme
        await asyncio.sleep(60)
        if channel:
            try:
                await channel.delete()
            except:
                pass
        
        if user.id in self.active_applications:
            del self.active_applications[user.id]

    async def send_cancelled_application(self, user, app_data, current_step, current_question, cancel_reason):
        """İptal edilen başvuruları yetkililere gönderen fonksiyon"""
        guild = app_data["guild"]
        
        # Başvuru özetini oluşturma
        embed = discord.Embed(
            title="⛔ İptal Edilen Yetkili Başvurusu",
            description=f"{user.mention} ({user.name}) tarafından iptal edildi.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now()
        )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Kullanıcı bilgileri bölümü
        embed.add_field(name="👤 Kullanıcı Bilgileri", value="", inline=False)
        embed.add_field(name="ID", value=user.id, inline=True)
        embed.add_field(name="Katılma Tarihi", value=user.joined_at.strftime("%d/%m/%Y"), inline=True)
        embed.add_field(name="Hesap Oluşturma", value=user.created_at.strftime("%d/%m/%Y"), inline=True)
        
        # Roller bölümü (varsa)
        if len(user.roles) > 1:  # @everyone hariç rol varsa
            roles = [role.mention for role in user.roles if role.name != "@everyone"]
            if roles:
                embed.add_field(name="🏷️ Roller", value=" ".join(roles), inline=False)
        
        # İptal bilgisi
        embed.add_field(
            name="📝 İptal Bilgisi",
            value=f"Kullanıcı **Soru {current_step}**'de başvurusunu iptal etti.\nSoru: **{current_question}**",
            inline=False
        )
        
        # İptal nedeni
        embed.add_field(
            name="❓ İptal Nedeni",
            value=cancel_reason,
            inline=False
        )
        
        # Cevaplanan soruları ekle (eğer varsa)
        if app_data["answers"]:
            embed.add_field(name="📋 Cevaplanan Sorular", value="", inline=False)
            for i, (question, answer) in enumerate(app_data["answers"].items()):
                embed.add_field(name=f"Soru {i+1}", value=f"**{question}**\n{answer[:1024]}", inline=False)
        
        # İptal edileni veritabanına kaydet (iptal durumu olarak)
        try:
            db = await get_db()
            # Önce başvuruyu (varsa cevaplarla) kaydet.
            # save_staff_application'ın status'u default olarak 'pending' ayarladığını varsayıyoruz.
            application_id = await db.save_staff_application(
                user_id=user.id,
                username=user.name,
                answers=app_data["answers"] # app_data["answers"] başvuru başında {} olabilir.
            )
            
            # Kaydedilen başvurunun durumunu 'cancelled' olarak güncelle.
            # reviewer_id olarak işlemi yapan bot/sistem veya iptal eden kullanıcı olabilir.
            # Şimdilik iptal eden kullanıcıyı (user.id) reviewer_id olarak atayalım.
            await db.update_application_status(
                application_id=application_id,
                status='cancelled',
                reviewer_id=user.id, 
                review_message=f"Kullanıcı başvuruyu iptal etti. Sebep: {cancel_reason}"
            )
        except Exception as e:
            print(f"İptal edilen başvuruyu veritabanına kaydetme/güncelleme hatası: {e}")
        
        # Başvurular kanalına gönderme (ID ile alınıyor)
        submissions_channel = guild.get_channel(BASVURU_CHANNEL_ID)
        if submissions_channel:
            await submissions_channel.send(embed=embed)

    async def send_timeout_dm(self, user, current_step, total_questions):
        """Zaman aşımına uğrayan kullanıcıya DM gönderen fonksiyon"""
        try:
            # Zaman aşımı bilgilendirme embed'i
            timeout_dm_embed = discord.Embed(
                title="⏰ Yetkili Başvuru Zaman Aşımı",
                description=(
                    f"👋 Merhaba {user.mention},\n\n"
                    f"🚨 Yetkili başvurunuz 10 dakika boyunca yanıt alamadığımız için zaman aşımına uğradı.\n"
                    f"📝 Dilediğiniz zaman tekrar başvuru yapabilirsiniz.\n\n"
                    f"🧡 İyi günler dileriz!"
                ),
                color=discord.Color.orange()
            )
            
            if user.guild and user.guild.icon:
                timeout_dm_embed.set_thumbnail(url=user.guild.icon.url)
                timeout_dm_embed.set_footer(
                    text=f"{user.guild.name} • Yetkili Alım Sistemi", 
                    icon_url=user.guild.icon.url
                )
            else:
                timeout_dm_embed.set_footer(text="Yetkili Alım Sistemi")
            
            timeout_dm_embed.timestamp = datetime.datetime.now(turkey_tz)
            
            await user.send(embed=timeout_dm_embed)
            
        except Exception as e:
            print(f"Zaman aşımı DM gönderme hatası ({user.name}): {e}")

class StaffApprovalModal(discord.ui.Modal, title="Yetkili Başvurusu Onayı"):
    """Yetkili başvurusunu onaylama modalı"""
    
    def __init__(self, user):
        super().__init__()
        self.user = user
        
        self.message = discord.ui.TextInput(
            label="Kullanıcıya Gönderilecek Mesaj",
            placeholder="Yetkili başvurunuz onaylandı! Aramıza hoşgeldiniz!",
            required=True,
            style=discord.TextStyle.paragraph
        )
        
        self.add_item(self.message)
    
    async def on_submit(self, interaction):
        try:
            # İşlem gecikmesi oluşabilir, kullanıcıya bildir
            await interaction.response.defer(ephemeral=True)
            
            # Veritabanından başvuru bilgisini al
            db = await get_db()
            application = await db.get_application_by_user_id(self.user.id)
            
            if not application:
                return await interaction.followup.send(
                    "Kullanıcının veritabanında kayıtlı bir başvurusu bulunamadı.", 
                    ephemeral=True
                )
                
            # Başvuru durumunu kontrol et
            if application['status'] != 'pending':
                status_text = "onaylanmış" if application['status'] == "approved" else "reddedilmiş"
                return await interaction.followup.send(
                    f"Bu başvuru zaten {status_text}. Başvuru ID: {application['id']}", 
                    ephemeral=True
                )
            
            # Rol seçimi için dropdown menü oluşturma
            view = RoleSelectionView(self.user, self.message.value, interaction, application['id'])
            
            # Görünüm için embed hazırlama
            embed = discord.Embed(
                title="🔍 Yetkili Rolü Seçin",
                description=f"{self.user.mention} kullanıcısına verilecek yetkili rolünü seçin.\n\n**Başvuru ID:** `{application['id']}`",
                color=discord.Color.blue()
            )
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
        except Exception as e:
            print(f"Yetkili onay modal hatası: {e}")
            # followup kullanabilir miyiz kontrol et
            try:
                await interaction.followup.send(f"Bir hata oluştu: {str(e)}", ephemeral=True)
            except:
                # Zaten yanıt verilmiş olabilir
                pass
    
    async def on_error(self, interaction, error):
        print(f"Modal hatası: {error}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"Bir hata oluştu: {str(error)}", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"Bir hata oluştu: {str(error)}", 
                    ephemeral=True
                )
        except Exception as e:
            print(f"Hata mesajı gönderme hatası: {e}")

class RoleSelectionView(discord.ui.View):
    """Yetkili rolü seçim menüsü"""
    
    def __init__(self, user, message, original_interaction, application_id):
        super().__init__(timeout=300)  # 5 dakika timeout
        self.user = user
        self.message = message
        self.original_interaction = original_interaction
        self.application_id = application_id
        self.add_item(RoleSelectMenu(self.user, self.message, self.original_interaction, self.application_id))
    
    async def on_timeout(self):
        # Timeout durumunda view'ı devre dışı bırak
        for item in self.children:
            item.disabled = True

class RoleSelectMenu(discord.ui.Select):
    """Rol seçim menüsü"""
    
    def __init__(self, user, message, original_interaction, application_id):
        self.user = user
        self.message = message
        self.original_interaction = original_interaction
        self.application_id = application_id
        self.is_processed = False  # İşlem durumu kontrolü
        
        # Rolleri yükle
        options = self.load_roles()
        
        # Üst sınıfı başlat
        super().__init__(
            placeholder="Verilecek rolü seçin...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    def load_roles(self):
        """Menüye sunucudaki rolleri yükleme"""
        # Yeni bir options listesi oluştur
        options = []
        
        # İstenen rol ID'leri
        allowed_role_ids = [
            1163918714081644554,  # STAJYER
            1200919832393154680,  # ASİSTAN
            1163918107501412493,  # MODERATÖR
            1460021463607152703,  # KIDEMLİ MODERATÖR
            1163918130192580608  # ADMİN
        ]
        
        # Eğer context mevcut değilse, henüz roller yüklenemez
        if not self.original_interaction or not self.original_interaction.guild:
            options.append(discord.SelectOption(label="Roller yüklenemedi", value="error"))
            return options
            
        # Sunucudaki rollerden sadece izin verilenleri al
        for role_id in allowed_role_ids:
            role = self.original_interaction.guild.get_role(role_id)
            if role:
                options.append(discord.SelectOption(
                label=role.name,
                value=str(role.id),
                description=f"ID: {role.id}" if len(f"ID: {role.id}") <= 100 else f"ID: {role.id}"[:97] + "..."
            ))
        
        # Eğer hiç rol bulunamadıysa
        if not options:
            options.append(discord.SelectOption(label="Uygun yetkili rolü bulunamadı", value="none"))
        
        return options
    
    async def callback(self, interaction):
        try:
            # İşlenmiş mi kontrol et
            if self.is_processed:
                return await interaction.response.send_message("Bu işlem zaten tamamlandı.", ephemeral=True)
            
            # Seçilen rolü al
            selected_role_id = int(self.values[0])
            role = interaction.guild.get_role(selected_role_id)
            
            if not role:
                return await interaction.response.send_message("Seçilen rol bulunamadı.", ephemeral=True)
            
            # İşlem bildirimi
            await interaction.response.defer(ephemeral=True)
            
            # İşleniyor olarak işaretle
            self.is_processed = True
            
            # Kullanıcıya rolü ver
            await self.user.add_roles(role, reason=f"Yetkili başvurusu onaylandı - {interaction.user.name} tarafından")
            
            # ÜYE rolünü kaldır (ID: 1029089740022095973)
            uye_role = interaction.guild.get_role(1029089740022095973)
            if uye_role and uye_role in self.user.roles:
                await self.user.remove_roles(uye_role, reason=f"Yetkili rolü verildiği için ÜYE rolü kaldırıldı - {interaction.user.name} tarafından")

            # DB log: added via application approval
            try:
                db = await get_db()
                await db.add_staff_change(
                    guild_id=interaction.guild.id,
                    user_id=self.user.id,
                    username=self.user.name,
                    action='added',
                    actor_id=interaction.user.id,
                    actor_username=interaction.user.name,
                    old_role_id=None,
                    old_role_name=None,
                    new_role_id=role.id,
                    new_role_name=role.name,
                    reason=f"Başvuru onayı (ID: {self.application_id})"
                )
            except Exception as _:
                pass
            
            # Yetkili-sohbet kanalına hoş geldin mesajı gönder
            yetkili_sohbet_channel = interaction.guild.get_channel(1362825644550914263)
            if yetkili_sohbet_channel:
                try:
                    # Hoş geldin embed'i oluştur
                    welcome_embed = discord.Embed(
                        title="🎉 Aramıza Hoş Geldin!",
                        description=f"🎊 **{self.user.mention}** artık yetkili kadromuzun bir parçası!\n\n"
                                   f"🏅 **Başlangıç Rolü:** {role.mention}\n"
                                   f"📝 **Onaylayan Yetkili:** {interaction.user.mention}\n\n"
                                   f"Görevlerinde başarılar dileriz! 💪",
                        color=discord.Color.green(),
                        timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
                    )
                    
                    welcome_embed.set_thumbnail(url=self.user.display_avatar.url)
                    welcome_embed.set_footer(
                        text=f"{interaction.guild.name} • Yetkili Alım Sistemi", 
                        icon_url=interaction.guild.icon.url if interaction.guild.icon else None
                    )
                    
                    # Hoş geldin mesajını gönder
                    await yetkili_sohbet_channel.send(
                        content=f"🎉 {self.user.mention} aramıza katıldı! Herkes hoş geldin desin! 🎊",
                        embed=welcome_embed
                    )
                    
                except Exception as e:
                    print(f"Yetkili-sohbet kanalına hoş geldin mesajı gönderme hatası: {e}")
            else:
                print("Yetkili-sohbet kanalı bulunamadı!")
            
            # DM üzerinden bilgilendir
            dm_sent = False
            try:
                embed = discord.Embed(
                    title="🎉 Yetkili Başvurunuz Onaylandı!",
                    description=self.message,
                    color=discord.Color.green()
                )
                
                embed.add_field(name="🏅 Verilen Rol", value=role.name, inline=False)
                embed.add_field(name="📊 Başvuru Bilgisi", value=f"Başvuru ID: `{self.application_id}`", inline=False)
                embed.set_footer(text=f"{interaction.guild.name} • Yetkili Alım Sistemi", 
                                icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                
                await self.user.send(embed=embed)
                dm_sent = True
            except Exception as e:
                print(f"DM gönderme hatası: {e}")
                # DM hatası bildirilecek
            
            # Veritabanında başvuruyu güncelle
            try:
                db = await get_db()
                await db.update_application_status(
                    application_id=self.application_id,
                    status='approved',
                    reviewer_id=interaction.user.id,
                    review_message=self.message,
                    assigned_role_id=role.id,
                    assigned_role_name=role.name
                )
                
                # Başvuru butonlarını devre dışı bırak
                try:
                    # Sunucudaki tüm başvuru mesajlarını kontrol et (ID ile alınıyor)
                    log_channel = interaction.guild.get_channel(BASVURU_CHANNEL_ID)
                    if log_channel:
                        async for message in log_channel.history(limit=100):
                            # Mesaj içeriğinde kullanıcı ID'si var mı kontrol et
                            if message.embeds and f"{self.user.id}" in message.content + str([e.to_dict() for e in message.embeds]):
                                # Mesajın butonları varsa devre dışı bırak
                                if message.components:
                                    # Yeni bir view ile butonları devre dışı bırak
                                    disabled_view = discord.ui.View()
                                    # Mevcut butonları kopyala ve devre dışı bırak
                                    for row in message.components:
                                        for component in row.children:
                                            if isinstance(component, discord.Button):
                                                disabled_button = discord.ui.Button(
                                                    style=component.style,
                                                    label=component.label,
                                                    custom_id=component.custom_id,
                                                    emoji=component.emoji,
                                                    disabled=True
                                                )
                                                disabled_view.add_item(disabled_button)
                                    
                                    # Güncelleme yapılabilirse
                                    if disabled_view.children:
                                        try:
                                            await message.edit(view=disabled_view)
                                            break
                                        except Exception as edit_error:
                                            print(f"Buton devre dışı bırakma hatası: {edit_error}")
                except Exception as btn_error:
                    print(f"Buton devre dışı bırakma işlemi hatası: {btn_error}")
                
            except Exception as e:
                print(f"Başvuru onaylama veritabanı hatası: {e}")
            
            # Log kanalına bilgi gönder (başvurular - ID ile alınıyor)
            log_channel = interaction.guild.get_channel(BASVURU_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="✅ Yetkili Başvurusu Onaylandı",
                    description=f"{self.user.mention} kullanıcısının yetkili başvurusu {interaction.user.mention} tarafından onaylandı.",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.now()
                )
                embed.add_field(name="🏅 Verilen Rol", value=role.mention, inline=False)
                embed.add_field(name="📝 Mesaj", value=self.message, inline=False)
                embed.add_field(name="📊 Başvuru Bilgisi", value=f"Başvuru ID: `{self.application_id}`", inline=False)
                await log_channel.send(embed=embed)

            # YK log kanalına detaylı bilgi gönder (yetkili-panel-log)
            try:
                yk_log_channel = interaction.guild.get_channel(1365954141880455238)
                if yk_log_channel is None:
                    try:
                        yk_log_channel = await interaction.client.fetch_channel(1365954141880455238)
                    except Exception:
                        yk_log_channel = None
                if yk_log_channel:
                    # Kullanıcının sunucuya katılım tarihi
                    joined_at_tr = None
                    try:
                        if self.user.joined_at:
                            joined_at_tr = self.user.joined_at.astimezone(turkey_tz).strftime('%d.%m.%Y %H:%M')
                    except Exception:
                        joined_at_tr = None

                    detay_embed = discord.Embed(
                        title="🛡️ Yetkili Alımı Onayı (YK Log)",
                        description=(
                            f"Yeni yetkili ataması yapıldı.\n"
                            f"Kullanıcı: {self.user.mention} ({self.user.id})"
                        ),
                        color=discord.Color.blurple(),
                        timestamp=datetime.datetime.now(turkey_tz)
                    )
                    detay_embed.add_field(name="🏅 Verilen Rol", value=f"{role.mention} ({role.id})", inline=False)
                    detay_embed.add_field(name="✅ Onaylayan", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
                    # Mesaj alanı 1024 sınırına uysun diye kırp
                    msg_value = self.message if len(self.message) <= 1024 else (self.message[:1021] + "...")
                    detay_embed.add_field(name="📝 Kullanıcıya Gönderilen Mesaj", value=msg_value or "-", inline=False)
                    detay_embed.add_field(name="📊 Başvuru ID", value=f"`{self.application_id}`", inline=True)
                    detay_embed.add_field(name="🕒 Onay Zamanı", value=datetime.datetime.now(turkey_tz).strftime('%d.%m.%Y %H:%M'), inline=True)
                    if joined_at_tr:
                        detay_embed.add_field(name="👋 Sunucuya Katılım", value=joined_at_tr, inline=True)
                    detay_embed.set_thumbnail(url=self.user.display_avatar.url)
                    await yk_log_channel.send(embed=detay_embed)
            except Exception as e:
                print(f"YK log gönderim hatası: {e}")
            
            # Menüyü devre dışı bırak ve bildirimi güncelle
            for child in self.view.children:
                child.disabled = True
            
            # DM durumuna göre mesaj
            dm_status = "" if dm_sent else "\n⚠️ Kullanıcıya DM gönderilemedi."
            
            # View'ı güncelle
            await interaction.followup.send(
                f"✅ {self.user.mention} kullanıcısına {role.mention} rolü verildi ve kullanıcı bilgilendirildi.{dm_status}\n📊 Başvuru ID: `{self.application_id}`", 
                ephemeral=True
            )
            
            # Tüm görünümü devre dışı bırak
            self.view.stop()
            
        except Exception as e:
            error_msg = f"Rol verme sırasında bir hata oluştu: {str(e)}"
            print(error_msg)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(error_msg, ephemeral=True)
                else:
                    await interaction.followup.send(error_msg, ephemeral=True)
            except Exception as follow_error:
                print(f"Hata mesajı gönderme hatası: {follow_error}")

class StaffRejectionModal(discord.ui.Modal, title="Yetkili Başvurusu Reddi"):
    """Yetkili başvurusunu reddetme modalı"""
    
    def __init__(self, user):
        super().__init__()
        self.user = user
        
        self.reason = discord.ui.TextInput(
            label="Red Sebebi",
            placeholder="Başvurunuz maalesef kabul edilmedi çünkü...",
            required=True,
            style=discord.TextStyle.paragraph
        )
        
        self.add_item(self.reason)
    
    async def on_submit(self, interaction):
        try:
            # İşlem bilgisi
            await interaction.response.defer(ephemeral=True)
            
            # Veritabanından başvuru bilgisini al
            db = await get_db()
            application = await db.get_application_by_user_id(self.user.id)
            
            if not application:
                return await interaction.followup.send(
                    "Kullanıcının veritabanında kayıtlı bir başvurusu bulunamadı.", 
                    ephemeral=True
                )
                
            # Başvuru durumunu kontrol et
            if application['status'] != 'pending':
                status_text = "onaylanmış" if application['status'] == "approved" else "reddedilmiş"
                return await interaction.followup.send(
                    f"Bu başvuru zaten {status_text}. Başvuru ID: {application['id']}", 
                    ephemeral=True
                )
            
            # DM üzerinden bilgilendir
            embed = discord.Embed(
                title="❌ Yetkili Başvurunuz Reddedildi",
                description=f"Merhaba {self.user.mention},\n\n"
                           f"Yetkili başvurunuz değerlendirildi ancak aşağıdaki gerekçe ile reddedildi. "
                           f"İleride tekrar başvurabilirsiniz.",
                color=discord.Color.red()
            )
            
            embed.add_field(name="📝 Red Sebebi", value=self.reason.value, inline=False)
            embed.add_field(name="📊 Başvuru Bilgisi", value=f"Başvuru ID: `{application['id']}`", inline=False)
            embed.set_footer(text=f"{interaction.guild.name} • Yetkili Alım Sistemi", 
                             icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            
            dm_sent = False
            try:
                await self.user.send(embed=embed)
                dm_sent = True
            except Exception as e:
                print(f"DM gönderme hatası: {e}")
            
            # Veritabanında başvuruyu güncelle
            try:
                await db.update_application_status(
                    application_id=application['id'],
                    status='rejected',
                    reviewer_id=interaction.user.id,
                    review_message=self.reason.value
                )
                
                # Başvuru butonlarını devre dışı bırak
                try:
                    # Sunucudaki tüm başvuru mesajlarını kontrol et (ID ile alınıyor)
                    log_channel = interaction.guild.get_channel(BASVURU_CHANNEL_ID)
                    if log_channel:
                        async for message in log_channel.history(limit=100):
                            # Mesaj içeriğinde kullanıcı ID'si var mı kontrol et
                            if message.embeds and f"{self.user.id}" in message.content + str([e.to_dict() for e in message.embeds]):
                                # Mesajın butonları varsa devre dışı bırak
                                if message.components:
                                    # Yeni bir view ile butonları devre dışı bırak
                                    disabled_view = discord.ui.View()
                                    # Mevcut butonları kopyala ve devre dışı bırak
                                    for row in message.components:
                                        for component in row.children:
                                            if isinstance(component, discord.Button):
                                                disabled_button = discord.ui.Button(
                                                    style=component.style,
                                                    label=component.label,
                                                    custom_id=component.custom_id,
                                                    emoji=component.emoji,
                                                    disabled=True
                                                )
                                                disabled_view.add_item(disabled_button)
                                    
                                    # Güncelleme yapılabilirse
                                    if disabled_view.children:
                                        try:
                                            await message.edit(view=disabled_view)
                                            break
                                        except Exception as edit_error:
                                            print(f"Buton devre dışı bırakma hatası: {edit_error}")
                except Exception as btn_error:
                    print(f"Buton devre dışı bırakma işlemi hatası: {btn_error}")
                
            except Exception as e:
                print(f"Başvuru reddetme veritabanı hatası: {e}")
            
            # Log kanalına bilgi gönder (ID ile alınıyor)
            log_channel = interaction.guild.get_channel(BASVURU_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="❌ Yetkili Başvurusu Reddedildi",
                    description=f"{self.user.mention} kullanıcısının yetkili başvurusu {interaction.user.mention} tarafından reddedildi.",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now()
                )
                
                embed.add_field(name="📝 Red Sebebi", value=self.reason.value, inline=False)
                embed.add_field(name="📨 DM Durumu", value="Gönderildi ✅" if dm_sent else "Gönderilemedi ❌", inline=False)
                embed.add_field(name="📊 Başvuru Bilgisi", value=f"Başvuru ID: `{application['id']}`", inline=False)
                
                await log_channel.send(embed=embed)
            
            # Kullanıcıya bildirim
            dm_status = "ve kullanıcıya bildirim gönderildi" if dm_sent else "ancak kullanıcıya DM gönderilemedi"
            await interaction.followup.send(
                f"✅ {self.user.mention} kullanıcısının başvurusu reddedildi {dm_status}.\n📊 Başvuru ID: `{application['id']}`", 
                ephemeral=True
            )
            
        except Exception as e:
            error_msg = f"Başvuruyu reddetme sırasında bir hata oluştu: {str(e)}"
            print(error_msg)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(error_msg, ephemeral=True)
                else:
                    await interaction.followup.send(error_msg, ephemeral=True)
            except Exception as follow_error:
                print(f"Hata mesajı gönderme hatası: {follow_error}")
    
    async def on_error(self, interaction, error):
        print(f"Modal hatası: {error}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"Bir hata oluştu: {str(error)}", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"Bir hata oluştu: {str(error)}", 
                    ephemeral=True
                )
        except Exception as e:
            print(f"Hata mesajı gönderme hatası: {e}")

async def setup(bot):
    """Cog'u bot'a yükleme fonksiyonu"""
    await bot.add_cog(YetkiliAlim(bot))