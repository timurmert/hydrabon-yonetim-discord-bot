import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import datetime
from datetime import timezone
from database import get_db
import pytz
turkey_tz = pytz.timezone('Europe/Istanbul')

# Rol ID'leri
ADMIN_ROLE_ID = 1163918130192580608
KURUCU_ROLE_ID = 1029089723110674463
YK_ADAYLARI_ROLE_ID = 1412843482980290711

# Kanal ID'leri (setup komutundan sonra güncellenmeli)
YK_BASVURU_CHANNEL_ID = 1480642892249698394  # 💫┃yk-başvuru kanalı - setup sonrası güncellenecek
YK_BASVURULAR_CHANNEL_ID = 1487920398690680883  # 💫┃yk-başvurular kanalı - setup sonrası güncellenecek
YK_CATEGORY_ID = 1029089771525521520  # YK başvuru kategorisi - setup sonrası güncellenecek

# Form soruları
YK_QUESTIONS = [
    "HydRaboN bünyesinde Discord, Ar-Ge, Medya veya açılabilecek yeni alanların hangilerinde aktif sorumluluk almak istersin? Kendini en faydalı göreceğin alan(lar)ı kısaca belirt.",
    "Yönetim Kurulu'na neden katılmak istiyorsun? Bu rolde neyi değiştirmek, geliştirmek veya güçlendirmek istiyorsun?",
    "Mazeret, yoğunluk veya aktif olamayacağın bir durum olduğunda bunu mümkün olan en kısa sürede yönetime bildirebilir misin?",
    "HydRaboN sence önümüzdeki dönemde hangi alanda daha fazla gelişmeli veya ne gibi yenilikler yapmalı? Bu gelişim için senin fikrin ne olurdu?",
    "WhatsApp gruplarındaki ve Discord yönetim kanallarındaki bilgi akışını düzenli olarak takip edip, olaylara ve gündeme hızlı reaksiyon gösterebilir misin?",
    "Yetkili kadrosunda bulunan ekip arkadaşlarına yol gösterme, destek olma ve motive etme konusunda sorumluluk alabilir misin?",
    "Yeni yetkililerin ekibe kazandırılması, mevcut yetkililerin ise ekip içinde daha bağlı, sıcak ve desteklenmiş hissetmesi için aktif rol alabilir misin?",
    "Yönetim Kurulu içerisinde yetki ve imkânların artmasıyla birlikte sorumluluğun da ciddi şekilde artacağının farkında olup, bunun için gerekli olan zamanı ayırıp bu sorumluluğu üstleneceğini kabul ediyor musun?",
    "Sana doğrudan görev verilmediği zamanlarda da inisiyatif alarak HydRaboN'a katkı sağlayacak yeni fikirler, çalışmalar veya geliştirmeler üretmeye istekli misin?",
    "Planlı ya da ani gelişen toplantılara, geçerli bir mazeretin olmadığı sürece katılım sağlayacağını; aksi durumun yönetim sorumluluğunun yerine getirilmemesi olarak değerlendirilebileceğini kabul ediyor musun?",
    "Yönetim Kurulu içerisinde paylaşılan bilgiler, yaşanan iç meseleler, ekip içinde alınan kararlar ve yapılan planlamaların kesinlikle Yönetim Kurulu dışına çıkarılmaması gerektiğinin; aksi durumda sürecin sunucudan yasaklanmaya kadar uzanabilecek ciddi yaptırımlar doğurabileceğinin farkında olup, bu kurala bağlı kalacağını kabul ve taahhüt ediyor musun?"
]

# Sabitler
FORM_QUESTION_COUNT = len(YK_QUESTIONS)
MIN_ADMIN_DAYS = 14

class YKBasvuru(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_applications = {}

    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        """Buton etkileşimlerini dinleyen metod"""
        if not interaction.type == discord.InteractionType.component:
            return

        custom_id = interaction.data.get('custom_id', '')

        if custom_id == 'yk_apply_button':
            await self.handle_yk_application_button(interaction)
        elif custom_id.startswith('yk_approve_'):
            # Sadece KURUCU rolü kontrolü
            if not any(role.id == KURUCU_ROLE_ID for role in interaction.user.roles):
                return await interaction.response.send_message(
                    "Bu işlemi gerçekleştirmek için gerekli yetkiye sahip değilsiniz. Bu işlem yalnızca **Kurucu** rolüne sahip kişiler tarafından yapılabilir.",
                    ephemeral=True
                )

            user_id = int(custom_id.split('_')[2])
            user = interaction.guild.get_member(user_id)

            if not user:
                return await interaction.response.send_message(
                    "Kullanıcı sunucuda bulunamadı.",
                    ephemeral=True
                )

            # Başvuru durumu kontrolü
            try:
                db = await get_db()
                application = await db.get_yk_application_by_user_id(user_id)

                if application and application['status'] != 'pending':
                    status_text = "onaylanmış" if application['status'] == "approved" else "reddedilmiş"
                    return await interaction.response.send_message(
                        f"Bu başvuru zaten {status_text}. Başvuru ID: {application['id']}",
                        ephemeral=True
                    )
            except Exception as e:
                print(f"YK başvuru durumu kontrolü hatası: {e}")

            await interaction.response.send_modal(YKApprovalModal(user))

        elif custom_id.startswith('yk_reject_'):
            # Sadece KURUCU rolü kontrolü
            if not any(role.id == KURUCU_ROLE_ID for role in interaction.user.roles):
                return await interaction.response.send_message(
                    "Bu işlemi gerçekleştirmek için gerekli yetkiye sahip değilsiniz. Bu işlem yalnızca **Kurucu** rolüne sahip kişiler tarafından yapılabilir.",
                    ephemeral=True
                )

            user_id = int(custom_id.split('_')[2])
            user = interaction.guild.get_member(user_id)

            if not user:
                return await interaction.response.send_message(
                    "Kullanıcı sunucuda bulunamadı.",
                    ephemeral=True
                )

            # Başvuru durumu kontrolü
            try:
                db = await get_db()
                application = await db.get_yk_application_by_user_id(user_id)

                if application and application['status'] != 'pending':
                    status_text = "onaylanmış" if application['status'] == "approved" else "reddedilmiş"
                    return await interaction.response.send_message(
                        f"Bu başvuru zaten {status_text}. Başvuru ID: {application['id']}",
                        ephemeral=True
                    )
            except Exception as e:
                print(f"YK başvuru durumu kontrolü hatası: {e}")

            await interaction.response.send_modal(YKRejectionModal(user))

    async def handle_yk_application_button(self, interaction):
        """YK başvuru butonuna tıklandığında çalışan fonksiyon"""

        # 1. Aktif başvuru kontrolü
        if interaction.user.id in self.active_applications:
            return await interaction.response.send_message(
                "Zaten aktif bir YK başvuru sürecindesiniz. Lütfen önce onu tamamlayın.",
                ephemeral=True
            )

        # 2. Admin rolü kontrolü
        if not any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles):
            return await interaction.response.send_message(
                "❌ Bu başvuruyu yapabilmek için **Admin** rolüne sahip olmanız gerekmektedir.",
                ephemeral=True
            )

        # 3. 14 gün süre kontrolü
        try:
            db = await get_db()
            role_dates = await db.get_staff_current_role_dates(interaction.guild.id)
            user_data = role_dates.get(interaction.user.id)

            if not user_data:
                return await interaction.response.send_message(
                    "❌ Admin rolünüze ait süre bilgisi veritabanında bulunamadı. Lütfen bir yetkiliye başvurun.",
                    ephemeral=True
                )

            assigned_at = datetime.datetime.fromisoformat(user_data['assigned_at'])
            if assigned_at.tzinfo is None:
                assigned_at = assigned_at.replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            days_held = (now - assigned_at).days

            if days_held < MIN_ADMIN_DAYS:
                remaining = MIN_ADMIN_DAYS - days_held
                return await interaction.response.send_message(
                    f"❌ Yönetim Kurulu'na başvurabilmek için Admin rolünde en az **{MIN_ADMIN_DAYS} gün** görev yapmış olmanız gerekmektedir.\n"
                    f"📅 Mevcut süreniz: **{days_held} gün**\n"
                    f"⏳ Kalan süre: **{remaining} gün**",
                    ephemeral=True
                )
        except Exception as e:
            print(f"YK süre kontrolü hatası: {e}")
            return await interaction.response.send_message(
                "❌ Süre kontrolü sırasında bir hata oluştu. Lütfen daha sonra tekrar deneyin.",
                ephemeral=True
            )

        # 4. Bekleyen başvuru kontrolü
        try:
            application = await db.get_yk_application_by_user_id(interaction.user.id)
            if application and application['status'] == 'pending':
                return await interaction.response.send_message(
                    "❌ Zaten beklemede olan bir YK başvurunuz bulunmaktadır. Lütfen mevcut başvurunuzun sonuçlanmasını bekleyin.",
                    ephemeral=True
                )
        except Exception as e:
            print(f"YK bekleyen başvuru kontrolü hatası: {e}")

        # 5. Tüm kontrollerden geçti - başvuru başlat
        await interaction.response.send_message(
            "Yönetim Kurulu başvuru formunu doldurmak üzeresiniz. Lütfen sorulara özenle cevap verin.\n"
            "İptal etmek için herhangi bir aşamada `iptal` yazabilirsiniz.",
            ephemeral=True
        )

        self.active_applications[interaction.user.id] = {
            "step": 0,
            "answers": {},
            "channel": interaction.channel,
            "guild": interaction.guild,
        }

        # Özel başvuru kanalı oluştur
        category = interaction.guild.get_channel(YK_CATEGORY_ID) if YK_CATEGORY_ID else None

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel_name = f"yk-başvuru-{interaction.user.name}"
        channel_name = ''.join(c for c in channel_name if c.isalnum() or c == '-').lower()
        channel_name = channel_name[:32]

        try:
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"{interaction.user.name}'in Yönetim Kurulu başvurusu"
            )

            self.active_applications[interaction.user.id]["private_channel"] = channel

            # Hoş geldin mesajı
            embed = discord.Embed(
                title="💫 Yönetim Kurulu Başvuru Formu",
                description=(
                    f"### Merhaba {interaction.user.mention}! \n\n"
                    f"Yönetim Kurulu başvuru sürecine hoş geldiniz. Sizi daha iyi tanımak ve "
                    f"Yönetim Kurulu'na ne katabileceğinizi görmek için aşağıdaki soruları cevaplamanızı rica ediyoruz.\n\n"
                    f"📋 **Başvuru Bilgileri:**\n"
                    f"• Toplam **{FORM_QUESTION_COUNT}** soru cevaplamanız gerekiyor\n"
                    f"• Her soruya detaylı ve dürüst bir şekilde cevap verin\n"
                    f"• Başvurunuzu iptal etmek için herhangi bir aşamada `iptal` yazabilirsiniz\n"
                    f"• Bir soru için 10 dakika içinde cevap vermezseniz başvurunuz iptal edilir\n\n"
                    f"İlk sorunuz birkaç saniye içinde gönderilecek..."
                ),
                color=0xFFD700
            )

            if interaction.guild.icon:
                embed.set_thumbnail(url=interaction.guild.icon.url)

            embed.set_footer(text=f"{interaction.guild.name} • YK Başvuru Sistemi", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            embed.timestamp = datetime.datetime.now(turkey_tz)

            await channel.send(embed=embed)

            await interaction.followup.send(
                f"YK başvuru kanalınız oluşturuldu: {channel.mention}\n"
                "Lütfen soruları cevaplamak için o kanala geçiş yapın.",
                ephemeral=True
            )

            await self.start_yk_application_form(interaction.user)

        except Exception as e:
            if interaction.user.id in self.active_applications:
                del self.active_applications[interaction.user.id]
            await interaction.followup.send(
                f"Başvuru kanalı oluşturulurken bir hata meydana geldi: {str(e)}",
                ephemeral=True
            )

    async def start_yk_application_form(self, user):
        """YK başvuru formunu başlatan ve soruları soran fonksiyon"""

        app_data = self.active_applications.get(user.id)
        if not app_data:
            return

        channel = app_data["private_channel"]

        for i, question in enumerate(YK_QUESTIONS):
            app_data["step"] = i + 1

            # Soruyu gönder
            embed = discord.Embed(
                title=f"Soru {i+1}/{len(YK_QUESTIONS)}",
                description=question,
                color=0xFFD700
            )

            # İlerleme çubuğu
            progress = int((i + 1) / len(YK_QUESTIONS) * 10)
            progress_bar = "▰" * progress + "▱" * (10 - progress)
            embed.add_field(name=f"İlerleme: {progress_bar} ({i+1}/{len(YK_QUESTIONS)})", value="", inline=False)

            await channel.send(embed=embed)

            # Kullanıcı cevabını bekle
            try:
                def check(m):
                    return m.author.id == user.id and m.channel.id == channel.id

                message = await self.bot.wait_for("message", check=check, timeout=600)

                # İptal kontrolü
                if message.content.lower() == "iptal":
                    reason_embed = discord.Embed(
                        title="ℹ️ İptal Nedeni",
                        description="Başvurunuzu neden iptal etmek istediğinizi kısaca belirtebilir misiniz?\n\n*Cevaplamak istemiyorsanız, 'belirtmek istemiyorum' yazabilirsiniz.*",
                        color=discord.Color.gold()
                    )
                    await channel.send(embed=reason_embed)

                    try:
                        reason_msg = await self.bot.wait_for("message", check=check, timeout=120)
                        cancel_reason = reason_msg.content
                    except asyncio.TimeoutError:
                        cancel_reason = "Kullanıcı iptal nedeni belirtmedi (zaman aşımı)"

                    cancel_embed = discord.Embed(
                        title="❌ YK Başvurusu İptal Edildi",
                        description="Başvurunuz isteğiniz üzerine iptal edildi. Bu kanal 10 saniye içinde silinecek.",
                        color=discord.Color.red()
                    )
                    await channel.send(embed=cancel_embed)

                    await self.send_cancelled_yk_application(user, app_data, i+1, question, cancel_reason)

                    await asyncio.sleep(10)
                    await channel.delete()
                    if user.id in self.active_applications:
                        del self.active_applications[user.id]
                    return

                # Cevabı kaydet
                app_data["answers"][question] = message.content
                await message.add_reaction("🧡")

            except asyncio.TimeoutError:
                timeout_embed = discord.Embed(
                    title="⏰ Zaman Aşımı",
                    description="Uzun süre yanıt vermediğiniz için YK başvurunuz iptal edildi. Bu kanal 10 saniye içinde silinecek.",
                    color=discord.Color.red()
                )
                await channel.send(embed=timeout_embed)

                await self.send_cancelled_yk_application(user, app_data, i+1, question, "Kullanıcı uzun süre yanıt vermedi (zaman aşımı)")
                await self.send_timeout_dm(user, i+1, len(YK_QUESTIONS))

                await asyncio.sleep(10)
                await channel.delete()
                if user.id in self.active_applications:
                    del self.active_applications[user.id]
                return

        # Başvuru tamamlandı
        await self.complete_yk_application(user)

    async def complete_yk_application(self, user):
        """Başvuruyu tamamlayan ve sonuçları Kurucu'ya gönderen fonksiyon"""
        app_data = self.active_applications.get(user.id)
        if not app_data:
            return

        channel = app_data["private_channel"]
        guild = app_data["guild"]

        # Tamamlama mesajı
        completion_embed = discord.Embed(
            title="🎉 YK Başvurunuz Tamamlandı!",
            description=(
                "Tebrikler! Yönetim Kurulu başvurunuz başarıyla alındı.\n\n"
                "📋 **Sonraki Adımlar:**\n"
                "• Başvurunuz Kurucu tarafından incelenecek\n"
                "• Sonuç hakkında size özel mesaj ile bilgilendirme yapılacak\n"
                "• Dolayısıyla DM kutunuzun açık olduğundan emin olunuz\n"
                "• Bu kanal 60 saniye içinde otomatik olarak silinecektir\n\n"
                "Gösterdiğiniz ilgi için teşekkür ederiz!"
            ),
            color=discord.Color.green()
        )

        if guild.icon:
            completion_embed.set_thumbnail(url=guild.icon.url)

        completion_embed.set_footer(text=f"{guild.name} • YK Başvuru Sistemi", icon_url=guild.icon.url if guild.icon else None)
        completion_embed.timestamp = datetime.datetime.now(turkey_tz)

        await channel.send(embed=completion_embed)

        # Veritabanına kaydet
        db = await get_db()
        application_id = await db.save_yk_application(
            user_id=user.id,
            username=user.name,
            answers=app_data["answers"]
        )

        # Admin süresi hesapla
        admin_days = "Bilinmiyor"
        try:
            role_dates = await db.get_staff_current_role_dates(guild.id)
            user_data = role_dates.get(user.id)
            if user_data:
                assigned_at = datetime.datetime.fromisoformat(user_data['assigned_at'])
                if assigned_at.tzinfo is None:
                    assigned_at = assigned_at.replace(tzinfo=datetime.timezone.utc)
                now = datetime.datetime.now(datetime.timezone.utc)
                admin_days = f"{(now - assigned_at).days} gün"
        except Exception:
            pass

        # Kullanıcı notlarını kontrol et
        user_notes = []
        try:
            notes = await db.get_user_notes(user.id, guild.id, limit=5)
            if notes:
                user_notes = notes
        except Exception as e:
            print(f"Kullanıcı notları alınırken hata: {e}")

        # Embed 1: Kullanıcı bilgileri + Soru 1-6
        embed1 = discord.Embed(
            title="💫 Yönetim Kurulu Başvurusu",
            description=f"{user.mention} ({user.name}) tarafından gönderildi.",
            color=0xFFD700,
            timestamp=datetime.datetime.now()
        )

        embed1.set_thumbnail(url=user.display_avatar.url)

        embed1.add_field(name="👤 Kullanıcı Bilgileri", value="", inline=False)
        embed1.add_field(name="ID", value=user.id, inline=True)
        embed1.add_field(name="Katılma Tarihi", value=user.joined_at.strftime("%d/%m/%Y"), inline=True)
        embed1.add_field(name="Admin Süresi", value=admin_days, inline=True)

        # Roller
        if len(user.roles) > 1:
            roles = [role.mention for role in user.roles if role.name != "@everyone"]
            if roles:
                embed1.add_field(name="🏷️ Roller", value=" ".join(roles), inline=False)

        embed1.add_field(name="📝 Form Cevapları (1-6)", value="", inline=False)

        questions_list = list(app_data["answers"].items())
        for i, (question, answer) in enumerate(questions_list[:6]):
            embed1.add_field(name=f"Soru {i+1}", value=f"**{question}**\n{answer[:1024]}", inline=False)

        # Embed 2: Soru 7-11 + Sistem bilgileri
        embed2 = discord.Embed(
            title="💫 Yönetim Kurulu Başvurusu (devam)",
            color=0xFFD700,
            timestamp=datetime.datetime.now()
        )

        embed2.add_field(name="📝 Form Cevapları (7-11)", value="", inline=False)

        for i, (question, answer) in enumerate(questions_list[6:], start=6):
            embed2.add_field(name=f"Soru {i+1}", value=f"**{question}**\n{answer[:1024]}", inline=False)

        embed2.add_field(name="📊 Sistem Bilgisi", value=f"Başvuru ID: `{application_id}`", inline=False)

        # Kullanıcı notları (varsa)
        if user_notes:
            notes_text = []
            for i, note in enumerate(user_notes, 1):
                created_date = datetime.datetime.fromisoformat(note['created_at']).replace(tzinfo=datetime.timezone.utc)
                created_date_tr = created_date.astimezone(turkey_tz).strftime('%d.%m.%Y')
                content_preview = note['note_content'][:80] + "..." if len(note['note_content']) > 80 else note['note_content']
                notes_text.append(f"**#{note['id']}** - {created_date_tr}\n└ {content_preview}\n└ Ekleyen: {note['created_by_username']}")

            notes_field_value = "\n\n".join(notes_text)
            if len(notes_field_value) > 1024:
                notes_field_value = notes_field_value[:1000] + f"\n\n*...ve daha fazla not var*"

            embed2.add_field(
                name="⚠️ KULLANICI HAKKINDA NOTLAR ⚠️",
                value=notes_field_value,
                inline=False
            )

        # Başvurular kanalına gönder
        submissions_channel = guild.get_channel(YK_BASVURULAR_CHANNEL_ID) if YK_BASVURULAR_CHANNEL_ID else None
        if submissions_channel:
            # Onay/Ret butonları
            view = discord.ui.View(timeout=None)
            approve_button = discord.ui.Button(
                style=discord.ButtonStyle.green,
                label="Onayla",
                custom_id=f"yk_approve_{user.id}",
                emoji="✅"
            )
            reject_button = discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="Reddet",
                custom_id=f"yk_reject_{user.id}",
                emoji="❌"
            )
            view.add_item(approve_button)
            view.add_item(reject_button)

            # İlk embed'i buton olmadan gönder
            await submissions_channel.send(embed=embed1)
            # İkinci embed'i butonlarla gönder
            await submissions_channel.send(embed=embed2, view=view)

        # Kanal temizleme
        await asyncio.sleep(60)
        if channel:
            try:
                await channel.delete()
            except:
                pass

        if user.id in self.active_applications:
            del self.active_applications[user.id]

    async def send_cancelled_yk_application(self, user, app_data, current_step, current_question, cancel_reason):
        """İptal edilen YK başvurusunu yetkililere gönderen fonksiyon"""
        guild = app_data["guild"]

        embed = discord.Embed(
            title="⛔ İptal Edilen YK Başvurusu",
            description=f"{user.mention} ({user.name}) tarafından iptal edildi.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now()
        )

        embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(name="👤 Kullanıcı Bilgileri", value="", inline=False)
        embed.add_field(name="ID", value=user.id, inline=True)
        embed.add_field(name="Katılma Tarihi", value=user.joined_at.strftime("%d/%m/%Y"), inline=True)
        embed.add_field(name="Hesap Oluşturma", value=user.created_at.strftime("%d/%m/%Y"), inline=True)

        if len(user.roles) > 1:
            roles = [role.mention for role in user.roles if role.name != "@everyone"]
            if roles:
                embed.add_field(name="🏷️ Roller", value=" ".join(roles), inline=False)

        embed.add_field(
            name="📝 İptal Bilgisi",
            value=f"Kullanıcı **Soru {current_step}**'de başvurusunu iptal etti.\nSoru: **{current_question[:200]}**",
            inline=False
        )

        embed.add_field(
            name="❓ İptal Nedeni",
            value=cancel_reason,
            inline=False
        )

        if app_data["answers"]:
            embed.add_field(name="📋 Cevaplanan Sorular", value="", inline=False)
            for i, (question, answer) in enumerate(app_data["answers"].items()):
                embed.add_field(name=f"Soru {i+1}", value=f"**{question[:200]}**\n{answer[:1024]}", inline=False)

        # İptal edilen başvuruyu veritabanına kaydet
        try:
            db = await get_db()
            application_id = await db.save_yk_application(
                user_id=user.id,
                username=user.name,
                answers=app_data["answers"]
            )

            await db.update_yk_application_status(
                application_id=application_id,
                status='cancelled',
                reviewer_id=user.id,
                review_message=f"Kullanıcı başvuruyu iptal etti. Sebep: {cancel_reason}"
            )
        except Exception as e:
            print(f"İptal edilen YK başvurusunu veritabanına kaydetme hatası: {e}")

        submissions_channel = guild.get_channel(YK_BASVURULAR_CHANNEL_ID) if YK_BASVURULAR_CHANNEL_ID else None
        if submissions_channel:
            await submissions_channel.send(embed=embed)

    async def send_timeout_dm(self, user, current_step, total_questions):
        """Zaman aşımına uğrayan kullanıcıya DM gönderen fonksiyon"""
        try:
            timeout_dm_embed = discord.Embed(
                title="⏰ YK Başvuru Zaman Aşımı",
                description=(
                    f"👋 Merhaba {user.mention},\n\n"
                    f"🚨 Yönetim Kurulu başvurunuz 10 dakika boyunca yanıt alamadığımız için zaman aşımına uğradı.\n"
                    f"📝 Dilediğiniz zaman tekrar başvuru yapabilirsiniz.\n\n"
                    f"🧡 İyi günler dileriz!"
                ),
                color=discord.Color.orange()
            )

            if user.guild and user.guild.icon:
                timeout_dm_embed.set_thumbnail(url=user.guild.icon.url)
                timeout_dm_embed.set_footer(
                    text=f"{user.guild.name} • YK Başvuru Sistemi",
                    icon_url=user.guild.icon.url
                )
            else:
                timeout_dm_embed.set_footer(text="YK Başvuru Sistemi")

            timeout_dm_embed.timestamp = datetime.datetime.now(turkey_tz)

            await user.send(embed=timeout_dm_embed)

        except Exception as e:
            print(f"YK zaman aşımı DM gönderme hatası ({user.name}): {e}")


class YKApprovalModal(discord.ui.Modal, title="YK Başvurusu Onayı"):
    """YK başvurusunu onaylama modalı"""

    def __init__(self, user):
        super().__init__()
        self.user = user

        self.message = discord.ui.TextInput(
            label="Kullanıcıya Gönderilecek Mesaj",
            placeholder="YK başvurunuz onaylandı! Yönetim Kurulu'na hoş geldiniz!",
            required=True,
            style=discord.TextStyle.paragraph
        )

        self.add_item(self.message)

    async def on_submit(self, interaction):
        try:
            await interaction.response.defer(ephemeral=True)

            db = await get_db()
            application = await db.get_yk_application_by_user_id(self.user.id)

            if not application:
                return await interaction.followup.send(
                    "Kullanıcının veritabanında kayıtlı bir YK başvurusu bulunamadı.",
                    ephemeral=True
                )

            if application['status'] != 'pending':
                status_text = "onaylanmış" if application['status'] == "approved" else "reddedilmiş"
                return await interaction.followup.send(
                    f"Bu başvuru zaten {status_text}. Başvuru ID: {application['id']}",
                    ephemeral=True
                )

            # YK ADAYLARI rolü ata
            yk_adaylari_role = interaction.guild.get_role(YK_ADAYLARI_ROLE_ID)
            if yk_adaylari_role:
                await self.user.add_roles(yk_adaylari_role)

            # staff_changes'a kayıt (promoted olarak)
            try:
                admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
                await db.add_staff_change(
                    guild_id=interaction.guild.id,
                    user_id=self.user.id,
                    username=self.user.name,
                    action='promoted',
                    old_role_id=ADMIN_ROLE_ID,
                    old_role_name=admin_role.name if admin_role else "Admin",
                    new_role_id=YK_ADAYLARI_ROLE_ID,
                    new_role_name=yk_adaylari_role.name if yk_adaylari_role else "Yönetim Kurulu Adayları",
                    reason=f"YK başvurusu onaylandı (Başvuru ID: {application['id']})",
                    actor_id=interaction.user.id,
                    actor_username=interaction.user.name
                )
            except Exception as e:
                print(f"YK staff_changes kayıt hatası: {e}")

            # Veritabanını güncelle
            await db.update_yk_application_status(
                application_id=application['id'],
                status='approved',
                reviewer_id=interaction.user.id,
                review_message=self.message.value
            )

            # DM gönder
            dm_sent = False
            try:
                dm_embed = discord.Embed(
                    title="💫 Yönetim Kurulu Başvurunuz Onaylandı!",
                    description=(
                        f"Merhaba {self.user.mention},\n\n"
                        f"Yönetim Kurulu başvurunuz değerlendirildi ve **onaylandı**! 🎉\n\n"
                        f"Yönetim Kurulu Adayı olarak aramıza hoş geldiniz."
                    ),
                    color=discord.Color.green()
                )

                dm_embed.add_field(name="📝 Mesaj", value=self.message.value, inline=False)
                dm_embed.add_field(name="📊 Başvuru Bilgisi", value=f"Başvuru ID: `{application['id']}`", inline=False)
                dm_embed.set_footer(text=f"{interaction.guild.name} • YK Başvuru Sistemi",
                                    icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

                await self.user.send(embed=dm_embed)
                dm_sent = True
            except Exception as e:
                print(f"YK onay DM gönderme hatası: {e}")

            # Butonları devre dışı bırak
            try:
                submissions_channel = interaction.guild.get_channel(YK_BASVURULAR_CHANNEL_ID) if YK_BASVURULAR_CHANNEL_ID else None
                if submissions_channel:
                    async for msg in submissions_channel.history(limit=100):
                        if msg.embeds and f"{self.user.id}" in msg.content + str([e.to_dict() for e in msg.embeds]):
                            if msg.components:
                                disabled_view = discord.ui.View()
                                for row in msg.components:
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

                                if disabled_view.children:
                                    try:
                                        await msg.edit(view=disabled_view)
                                        break
                                    except Exception as edit_error:
                                        print(f"YK buton devre dışı bırakma hatası: {edit_error}")
            except Exception as btn_error:
                print(f"YK buton devre dışı bırakma işlemi hatası: {btn_error}")

            # Log mesajı
            if YK_BASVURULAR_CHANNEL_ID:
                log_channel = interaction.guild.get_channel(YK_BASVURULAR_CHANNEL_ID)
                if log_channel:
                    log_embed = discord.Embed(
                        title="✅ YK Başvurusu Onaylandı",
                        description=f"{self.user.mention} kullanıcısının YK başvurusu {interaction.user.mention} tarafından onaylandı.",
                        color=discord.Color.green(),
                        timestamp=datetime.datetime.now()
                    )
                    log_embed.add_field(name="🏅 Atanan Rol", value=yk_adaylari_role.mention if yk_adaylari_role else "YK Adayları", inline=False)
                    log_embed.add_field(name="📝 Mesaj", value=self.message.value, inline=False)
                    log_embed.add_field(name="📨 DM Durumu", value="Gönderildi ✅" if dm_sent else "Gönderilemedi ❌", inline=False)
                    log_embed.add_field(name="📊 Başvuru Bilgisi", value=f"Başvuru ID: `{application['id']}`", inline=False)

                    await log_channel.send(embed=log_embed)

            # Onay bildirimi
            dm_status = "ve kullanıcıya bildirim gönderildi" if dm_sent else "ancak kullanıcıya DM gönderilemedi"
            await interaction.followup.send(
                f"✅ {self.user.mention} kullanıcısının YK başvurusu onaylandı {dm_status}.\n"
                f"🏅 Atanan Rol: YK Adayları\n"
                f"📊 Başvuru ID: `{application['id']}`",
                ephemeral=True
            )

        except Exception as e:
            error_msg = f"YK başvurusunu onaylama sırasında bir hata oluştu: {str(e)}"
            print(error_msg)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(error_msg, ephemeral=True)
                else:
                    await interaction.followup.send(error_msg, ephemeral=True)
            except Exception as follow_error:
                print(f"Hata mesajı gönderme hatası: {follow_error}")

    async def on_error(self, interaction, error):
        print(f"YK onay modal hatası: {error}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Bir hata oluştu: {str(error)}", ephemeral=True)
            else:
                await interaction.followup.send(f"Bir hata oluştu: {str(error)}", ephemeral=True)
        except Exception as e:
            print(f"Hata mesajı gönderme hatası: {e}")


class YKRejectionModal(discord.ui.Modal, title="YK Başvurusu Reddi"):
    """YK başvurusunu reddetme modalı"""

    def __init__(self, user):
        super().__init__()
        self.user = user

        self.reason = discord.ui.TextInput(
            label="Red Sebebi",
            placeholder="YK başvurunuz maalesef kabul edilmedi çünkü...",
            required=True,
            style=discord.TextStyle.paragraph
        )

        self.add_item(self.reason)

    async def on_submit(self, interaction):
        try:
            await interaction.response.defer(ephemeral=True)

            db = await get_db()
            application = await db.get_yk_application_by_user_id(self.user.id)

            if not application:
                return await interaction.followup.send(
                    "Kullanıcının veritabanında kayıtlı bir YK başvurusu bulunamadı.",
                    ephemeral=True
                )

            if application['status'] != 'pending':
                status_text = "onaylanmış" if application['status'] == "approved" else "reddedilmiş"
                return await interaction.followup.send(
                    f"Bu başvuru zaten {status_text}. Başvuru ID: {application['id']}",
                    ephemeral=True
                )

            # DM gönder
            dm_sent = False
            try:
                dm_embed = discord.Embed(
                    title="❌ Yönetim Kurulu Başvurunuz Reddedildi",
                    description=(
                        f"Merhaba {self.user.mention},\n\n"
                        f"Yönetim Kurulu başvurunuz değerlendirildi ancak aşağıdaki gerekçe ile reddedildi. "
                        f"İleride tekrar başvurabilirsiniz."
                    ),
                    color=discord.Color.red()
                )

                dm_embed.add_field(name="📝 Red Sebebi", value=self.reason.value, inline=False)
                dm_embed.add_field(name="📊 Başvuru Bilgisi", value=f"Başvuru ID: `{application['id']}`", inline=False)
                dm_embed.set_footer(text=f"{interaction.guild.name} • YK Başvuru Sistemi",
                                    icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

                await self.user.send(embed=dm_embed)
                dm_sent = True
            except Exception as e:
                print(f"YK red DM gönderme hatası: {e}")

            # Veritabanını güncelle
            await db.update_yk_application_status(
                application_id=application['id'],
                status='rejected',
                reviewer_id=interaction.user.id,
                review_message=self.reason.value
            )

            # Butonları devre dışı bırak
            try:
                submissions_channel = interaction.guild.get_channel(YK_BASVURULAR_CHANNEL_ID) if YK_BASVURULAR_CHANNEL_ID else None
                if submissions_channel:
                    async for msg in submissions_channel.history(limit=100):
                        if msg.embeds and f"{self.user.id}" in msg.content + str([e.to_dict() for e in msg.embeds]):
                            if msg.components:
                                disabled_view = discord.ui.View()
                                for row in msg.components:
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

                                if disabled_view.children:
                                    try:
                                        await msg.edit(view=disabled_view)
                                        break
                                    except Exception as edit_error:
                                        print(f"YK buton devre dışı bırakma hatası: {edit_error}")
            except Exception as btn_error:
                print(f"YK buton devre dışı bırakma işlemi hatası: {btn_error}")

            # Log mesajı
            if YK_BASVURULAR_CHANNEL_ID:
                log_channel = interaction.guild.get_channel(YK_BASVURULAR_CHANNEL_ID)
                if log_channel:
                    log_embed = discord.Embed(
                        title="❌ YK Başvurusu Reddedildi",
                        description=f"{self.user.mention} kullanıcısının YK başvurusu {interaction.user.mention} tarafından reddedildi.",
                        color=discord.Color.red(),
                        timestamp=datetime.datetime.now()
                    )

                    log_embed.add_field(name="📝 Red Sebebi", value=self.reason.value, inline=False)
                    log_embed.add_field(name="📨 DM Durumu", value="Gönderildi ✅" if dm_sent else "Gönderilemedi ❌", inline=False)
                    log_embed.add_field(name="📊 Başvuru Bilgisi", value=f"Başvuru ID: `{application['id']}`", inline=False)

                    await log_channel.send(embed=log_embed)

            # Red bildirimi
            dm_status = "ve kullanıcıya bildirim gönderildi" if dm_sent else "ancak kullanıcıya DM gönderilemedi"
            await interaction.followup.send(
                f"✅ {self.user.mention} kullanıcısının YK başvurusu reddedildi {dm_status}.\n📊 Başvuru ID: `{application['id']}`",
                ephemeral=True
            )

        except Exception as e:
            error_msg = f"YK başvurusunu reddetme sırasında bir hata oluştu: {str(e)}"
            print(error_msg)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(error_msg, ephemeral=True)
                else:
                    await interaction.followup.send(error_msg, ephemeral=True)
            except Exception as follow_error:
                print(f"Hata mesajı gönderme hatası: {follow_error}")

    async def on_error(self, interaction, error):
        print(f"YK red modal hatası: {error}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Bir hata oluştu: {str(error)}", ephemeral=True)
            else:
                await interaction.followup.send(f"Bir hata oluştu: {str(error)}", ephemeral=True)
        except Exception as e:
            print(f"Hata mesajı gönderme hatası: {e}")


async def setup(bot):
    """Cog'u bot'a yükleme fonksiyonu"""
    await bot.add_cog(YKBasvuru(bot))
