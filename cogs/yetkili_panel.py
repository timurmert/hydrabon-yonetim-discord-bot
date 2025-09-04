import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from discord.ui import Button, View, Select, Modal, TextInput
from database import get_db
import datetime
from typing import List, Dict, Optional
from cogs.bump_tracker import BumpLogView
import psutil
import os
import platform
import pytz

# Yetkili rolleri
YETKILI_ROLLERI = {
    "STAJYER": 1163918714081644554,
    "ASİSTAN": 1200919832393154680,
    "MODERATÖR": 1163918107501412493,
    "ADMİN": 1163918130192580608,
    "YÖNETİM KURULU ÜYELERİ": 1029089731314720798,
    "YÖNETİM KURULU BAŞKANI": 1029089727061692522,
    "KURUCU": 1029089723110674463
}

# Yetkili rolleri hiyerarşisi (en düşükten en yükseğe)
YETKILI_HIYERARSI = [
    1163918714081644554,  # STAJYER
    1200919832393154680,  # ASİSTAN
    1163918107501412493,  # MODERATÖR
    1163918130192580608,  # ADMİN
    1029089731314720798,  # YÖNETİM KURULU ÜYELERİ
    1029089727061692522,  # YÖNETİM KURULU BAŞKANI
    1029089723110674463   # KURUCU
]

# "Yetkili İşlemleri" bölümüne erişebilecek üst yönetim rolleri
MANAGEMENT_ALLOWED_ROLE_IDS = [
    YETKILI_ROLLERI["YÖNETİM KURULU ÜYELERİ"],
    YETKILI_ROLLERI["YÖNETİM KURULU BAŞKANI"],
    YETKILI_ROLLERI["KURUCU"],
]

def user_has_management_permission(user: discord.Member) -> bool:
    return any(role.id in MANAGEMENT_ALLOWED_ROLE_IDS for role in user.roles)

# Komutlar için dekoratör
def guild_only():
    """Bu dekoratör, komutun yalnızca sunucu içinde çalışabilmesini sağlar."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message("Bu komut yalnızca sunucu içinde kullanılabilir.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

class YetkiliIslemleriView(discord.ui.View):
    def __init__(self, cog, user, yetkili_rol_id):
        super().__init__(timeout=600)  # 10 dakika timeout
        self.cog = cog
        self.user = user
        self.yetkili_rol_id = yetkili_rol_id
        self.message = None
    
    async def on_timeout(self):
        """Timeout olduğunda butonları devre dışı bırakma"""
        for item in self.children:
            item.disabled = True
        
        if self.message:
            await self.message.edit(view=self)
    
    @discord.ui.button(label="Yetki Yükselt", style=discord.ButtonStyle.green, emoji="⬆️", row=0)
    async def yetki_yukselt_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Yetki yükseltme butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Kullanıcı seçme ve sebep belirtme modalını göster
        await interaction.response.send_modal(YetkiYukseltModal(self.cog, self.user, self.yetkili_rol_id))
    
    @discord.ui.button(label="Yetki Düşür", style=discord.ButtonStyle.danger, emoji="⬇️", row=0)
    async def yetki_dusur_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Yetki düşürme butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Kullanıcı seçme ve sebep belirtme modalını göster
        await interaction.response.send_modal(YetkiDusurModal(self.cog, self.user, self.yetkili_rol_id))

    @discord.ui.button(label="Yetkili Ekle", style=discord.ButtonStyle.blurple, emoji="➕", row=1)
    async def yetkili_ekle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Sebep ve kullanıcı ID girerek yetkili ekleme"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)

        await interaction.response.send_modal(YetkiliEkleModal(self.cog, self.user))

    @discord.ui.button(label="Yetkili Çıkart", style=discord.ButtonStyle.blurple, emoji="➖", row=1)
    async def yetkili_cikart_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Sebep ve kullanıcı ID girerek yetkiliyi tamamen çıkartma"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)

        await interaction.response.send_modal(YetkiliCikartModal(self.cog, self.user))
    
    @discord.ui.button(label="Geri Dön", style=discord.ButtonStyle.danger, emoji="◀️", row=1)
    async def geri_don_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Geri dön butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Ana menüye dön - edit_message ile
        embed = discord.Embed(
            title="🛡️ HydRaboN Yetkili Paneli",
            description=(
                "Hoş geldiniz! Bu panel üzerinden yetkili işlemlerini gerçekleştirebilirsiniz.\n\n"
                "Lütfen yapmak istediğiniz işlemi aşağıdaki butonlardan seçin."
            ),
            color=0x3498db
        )
        
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        view = YetkiliPanelView(self.cog, self.user)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

class YetkiliPanelView(discord.ui.View):
    def __init__(self, cog, user):
        super().__init__(timeout=600)  # 10 dakika timeout
        self.cog = cog
        self.user = user
        self.message = None
        
        # Kullanıcının yetkili olup olmadığını kontrol et
        self.yetkili_rol_id = None
        for rol_id in YETKILI_HIYERARSI:
            rol = discord.Object(id=rol_id)
            if any(r.id == rol_id for r in user.roles):
                self.yetkili_rol_id = rol_id
                break
    
    async def on_timeout(self):
        """Timeout olduğunda butonları devre dışı bırakma"""
        for item in self.children:
            item.disabled = True
        
        if self.message:
            await self.message.edit(view=self)
    
    @discord.ui.button(label="Yetkili İşlemleri", style=discord.ButtonStyle.blurple, emoji="🛡️", row=0)
    async def yetkili_islemleri_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Yetkili işlemleri butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Yönetim izin kontrolü: YK Üyeleri, YK Başkanı ve Kurucu dışındaki herkes engellenir
        if not user_has_management_permission(interaction.user):
            embed = discord.Embed(
                title="⚠️ Yetersiz Yetki",
                description=(
                    "Bu işlem için yetkiniz yetersiz."
                ),
                color=discord.Color.red()
            )
            return await interaction.response.edit_message(embed=embed, view=self)

        # Yetkili işlemleri alt menüsünü göster
        view = YetkiliIslemleriView(self.cog, self.user, self.yetkili_rol_id)
        embed = discord.Embed(
            title="🛡️ Yetkili İşlemleri",
            description="Yetkili işlemleri menüsüne hoş geldiniz. Lütfen yapmak istediğiniz işlemi seçin.",
            color=0x3498db
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="Başvurular", style=discord.ButtonStyle.blurple, emoji="📝", row=0)
    async def basvurular_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Başvurular butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Başvurular alt menüsünü göster
        view = BasvurularView(self.cog, self.user)
        embed = discord.Embed(
            title="📝 Başvurular",
            description="Başvurular menüsüne hoş geldiniz. Lütfen yapmak istediğiniz işlemi seçin.",
            color=0x3498db
        )
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()
    
    @discord.ui.button(label="Yetkili Duyuru", style=discord.ButtonStyle.blurple, emoji="📢", row=0)
    async def yetkili_duyuru_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Yetkili duyuru butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Yönetici yetkisi kontrolü
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="⚠️ Yetersiz Yetki",
                description="Bu özelliği kullanabilmek için Administrator yetkisine sahip olmanız gerekiyor.",
                color=discord.Color.red()
            )
            return await interaction.response.edit_message(embed=embed, view=self)
        
        # Yetkili duyuru alt menüsünü göster
        view = YetkiliDuyuruView(self.cog, self.user)
        embed = discord.Embed(
            title="📢 Yetkili Duyuru",
            description="Yetkili duyuru menüsüne hoş geldiniz. Lütfen yapmak istediğiniz işlemi seçin.",
            color=0x3498db
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="İstatistikler", style=discord.ButtonStyle.blurple, emoji="📊", row=0)
    async def istatistikler_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """İstatistikler butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # İstatistikleri getir
        await self.cog.show_stats(interaction)
    
    @discord.ui.button(label="Bump Logları", style=discord.ButtonStyle.blurple, emoji="📈", row=1)
    async def bump_log_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bump logları butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Moderatör veya daha üstü rol kontrolü
        moderator_index = YETKILI_HIYERARSI.index(YETKILI_ROLLERI["MODERATÖR"])
        user_index = -1
        for i, rol_id in enumerate(YETKILI_HIYERARSI):
            if any(r.id == rol_id for r in interaction.user.roles):
                user_index = i
        
        if user_index < moderator_index:  # Kullanıcı en az Moderatör değilse
            embed = discord.Embed(
                title="⚠️ Yetersiz Yetki",
                description="Bu özelliği kullanabilmek için en az Moderatör yetkisine sahip olmanız gerekiyor.",
                color=discord.Color.red()
            )
            return await interaction.response.edit_message(embed=embed, view=self)
        
        # BumpTracker cog'unu al
        bump_tracker = interaction.client.get_cog("BumpTracker")
        
        if bump_tracker is None:
            embed = discord.Embed(
                title="⚠️ Hata",
                description="Bump Tracker modülü bulunamadı veya yüklenmemiş!",
                color=discord.Color.red()
            )
            return await interaction.response.edit_message(embed=embed, view=self)
        
        # Bump istatistikleri embedini oluştur
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
        embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        # Bump log view'ını oluştur
        view = BumpLogView(bump_tracker, interaction.user)
        
        # Mevcut mesajı güncelle
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()
    
    @discord.ui.button(label="Otomatik Mesajlar", style=discord.ButtonStyle.blurple, emoji="⏱️", row=1)
    async def otomatik_mesajlar_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Otomatik mesajlar butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Moderatör veya daha üstü rol kontrolü
        moderator_index = YETKILI_HIYERARSI.index(YETKILI_ROLLERI["MODERATÖR"])
        user_index = -1
        for i, rol_id in enumerate(YETKILI_HIYERARSI):
            if any(r.id == rol_id for r in interaction.user.roles):
                user_index = i
        
        if user_index < moderator_index:  # Kullanıcı en az Moderatör değilse
            embed = discord.Embed(
                title="⚠️ Yetersiz Yetki",
                description="Bu özelliği kullanabilmek için en az Moderatör yetkisine sahip olmanız gerekiyor.",
                color=discord.Color.red()
            )
            return await interaction.response.edit_message(embed=embed, view=self)
        
        # Otomatik mesajlar alt menüsünü göster
        view = OtomatikMesajlarView(self.cog, interaction.user) # interaction.user kullanılmalı
        embed = discord.Embed(
            title="⏱️ Otomatik Mesajlar",
            description="Otomatik mesajlar menüsüne hoş geldiniz. Bu menüden belirli kanallara belirli zamanlarda otomatik mesaj gönderme ayarlarını yapabilirsiniz.",
            color=0x3498db
        )
        await interaction.response.edit_message(embed=embed, view=view)
        edited_message = await interaction.original_response()
        view.message = edited_message # Eklendi: View'in kendi mesajını bilmesi için
    
    @discord.ui.button(label="Sistem Durumu", style=discord.ButtonStyle.blurple, emoji="💻", row=1)
    async def sistem_durumu_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Sistem durumu butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Admin yetkisi kontrolü
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="⚠️ Yetersiz Yetki",
                description="Bu özelliği kullanabilmek için Administrator yetkisine sahip olmanız gerekiyor.",
                color=discord.Color.red()
            )
            return await interaction.response.edit_message(embed=embed, view=self)
        
        # Sistem durumu view'ını göster
        view = SistemDurumuView(self.cog, self.user)
        await view.show_system_status(interaction)

    @discord.ui.button(label="Kullanıcı Notları", style=discord.ButtonStyle.blurple, emoji="📝", row=2)
    async def kullanici_notlari_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Kullanıcı notları panelini açar"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Admin yetkisi kontrolü
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="⚠️ Yetersiz Yetki",
                description="Bu özelliği kullanabilmek için Administrator yetkisine sahip olmanız gerekiyor.",
                color=discord.Color.red()
            )
            return await interaction.response.edit_message(embed=embed, view=self)
        
        # Kullanıcı notları view'ını göster
        view = KullaniciNotlariView(self.cog, self.user)
        await view.show_notes_panel(interaction)

    @discord.ui.button(label="Ana Menü", style=discord.ButtonStyle.green, emoji="🏠", row=2)
    async def ana_menu_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ana menüye dönüş butonu"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Ana menüye dön - edit_message ile
        embed = discord.Embed(
            title="🛡️ HydRaboN Yetkili Paneli",
            description=(
                "Hoş geldiniz! Bu panel üzerinden yetkili işlemlerini gerçekleştirebilirsiniz.\n\n"
                "Lütfen yapmak istediğiniz işlemi aşağıdaki butonlardan seçin."
            ),
            color=0x3498db
        )
        
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        view = YetkiliPanelView(self, interaction.user)
        
        if interaction.response.is_done():
            # İlk mesaj gönderilmiş, düzenleme yapalım
            await interaction.edit_original_response(embed=embed, view=view)
            message = await interaction.original_response()
        else:
            # İlk mesaj henüz gönderilmemiş
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            message = await interaction.original_response()
        
        view.message = message
    
    async def show_stats(self, interaction: discord.Interaction):
        """Sunucu istatistiklerini gösterir"""
        guild = interaction.guild
        
        # Temel istatistikleri hesapla
        total_members = guild.member_count
        online_members = len([m for m in guild.members if m.status != discord.Status.offline and not m.bot])
        total_channels = len(guild.channels)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        category_channels = len(guild.categories)
        total_roles = len(guild.roles)
        
        # Yetkili sayısını hesapla
        yetkili_sayisi = 0
        for rol_id in YETKILI_ROLLERI.values():
            rol = guild.get_role(rol_id)
            if rol:
                yetkili_sayisi += len(rol.members)
        
        # Sunucu yaşını hesapla
        tz = pytz.timezone('Europe/Istanbul')
        created_days = (datetime.datetime.now(tz) - guild.created_at.astimezone(tz)).days
        
        # Embed oluştur
        embed = discord.Embed(
            title="📊 Sunucu İstatistikleri",
            description=f"**{guild.name}** sunucusunun güncel istatistikleri",
            color=0x3498db
        )
        
        # Genel bilgiler
        embed.add_field(
            name="👥 Üye İstatistikleri",
            value=(
                f"**Toplam Üye:** {total_members}\n"
                f"**Çevrimiçi Üye:** {online_members}\n"
                f"**Yetkili Sayısı:** {yetkili_sayisi}"
            ),
            inline=True
        )
        
        # Kanal istatistikleri
        embed.add_field(
            name="💬 Kanal İstatistikleri", 
            value=(
                f"**Toplam Kanal:** {total_channels}\n"
                f"**Metin Kanalı:** {text_channels}\n"
                f"**Ses Kanalı:** {voice_channels}\n"
                f"**Kategori:** {category_channels}"
            ),
            inline=True
        )
        
        # Genel sunucu bilgileri
        embed.add_field(
            name="ℹ️ Sunucu Bilgileri",
            value=(
                f"**Kuruluş Tarihi:** {guild.created_at.strftime('%d/%m/%Y')}\n"
                f"**Sunucu Yaşı:** {created_days} gün\n"
                f"**Rol Sayısı:** {total_roles}"
            ),
            inline=False
        )
        
        # Veritabanından başvuru istatistiklerini getir
        try:
            db = await get_db()
            stats = await db.get_application_stats()
            
            # Başvuru istatistikleri
            status_counts = stats.get('status_counts', {})
            approved = status_counts.get('approved', 0)
            rejected = status_counts.get('rejected', 0)
            pending = status_counts.get('pending', 0)
            cancelled = status_counts.get('cancelled', 0)
            
            embed.add_field(
                name="📝 Başvuru İstatistikleri",
                value=(
                    f"**Toplam Başvuru:** {stats['total']}\n"
                    f"**Son 7 Gün:** {stats['recent']}\n"
                    f"**Bekleyen:** {pending}\n"
                    f"**Onaylanan:** {approved}\n"
                    f"**Reddedilen:** {rejected}\n"
                    f"**İptal Edilen:** {cancelled}"
                ),
                inline=False
            )
        except Exception as e:
            embed.add_field(
                name="📝 Başvuru İstatistikleri",
                value=f"Başvuru istatistikleri alınamadı: {str(e)}",
                inline=False
            )
        
        # Otomatik Mesaj İstatistikleri
        try:
            db = await get_db()
            messages = await db.get_all_scheduled_messages()
            
            active_count = len([m for m in messages if m['active']])
            total_sent = sum(m['sent_count'] for m in messages)
            
            embed.add_field(
                name="⏱️ Otomatik Mesaj İstatistikleri",
                value=(
                    f"**Toplam Mesaj:** {len(messages)}\n"
                    f"**Aktif Mesaj:** {active_count}\n"
                    f"**Toplam Gönderim:** {total_sent}"
                ),
                inline=False
            )
        except Exception as e:
            embed.add_field(
                name="⏱️ Otomatik Mesaj İstatistikleri",
                value=f"Otomatik mesaj istatistikleri alınamadı: {str(e)}",
                inline=False
            )
        
        # Veritabanı Boyut İstatistikleri
        try:
            db = await get_db()
            size_info = await db.get_database_size_info()
            
            embed.add_field(
                name="💾 Veritabanı İstatistikleri",
                value=(
                    f"**Bump Kayıtları:** {size_info['bump_logs_count']:,}\n"
                    f"**Başvuru Kayıtları:** {size_info['applications_count']:,}\n"
                    f"**Spam Kayıtları:** {size_info['spam_logs_count']:,}\n"
                    f"**Üye Giriş/Çıkış:** {size_info['member_logs_count']:,}\n"
                    f"**Tahmini Boyut:** {size_info['estimated_size_human']}\n"
                    f"**Bump Boyutu:** {size_info['estimated_bump_size_mb']} MB"
                ),
                inline=False
            )
        except Exception as e:
            embed.add_field(
                name="💾 Veritabanı İstatistikleri",
                value=f"Veritabanı boyut bilgileri alınamadı: {str(e)}",
                inline=False
            )
        
        # Thumbnail ve footer
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(text=f"{guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        # Geri dönüş butonu içeren view
        view = YetkiliPanelView(self, interaction.user)
        
        # Eğer interaction zaten yanıtlandıysa edit_message kullan
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)
        
        view.message = await interaction.original_response()

class BasvurularView(discord.ui.View):
    def __init__(self, cog, user):
        super().__init__(timeout=600)  # 10 dakika timeout
        self.cog = cog
        self.user = user
        self.message = None
    
    async def on_timeout(self):
        """Timeout olduğunda butonları devre dışı bırakma"""
        for item in self.children:
            item.disabled = True
        
        if self.message:
            await self.message.edit(view=self)
    
    @discord.ui.button(label="Başvuru Ara", style=discord.ButtonStyle.blurple, emoji="🔍", row=0)
    async def basvuru_ara_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Başvuru arama butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Başvuru arama modalını göster
        await interaction.response.send_modal(BasvuruAraModal(self.cog, self.user))
    
    @discord.ui.button(label="Son Başvuruları Göster", style=discord.ButtonStyle.blurple, emoji="📋", row=0)
    async def son_basvurular_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Son başvuruları gösterme butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Son başvuruları getir
        try:
            db = await get_db()
            applications = await db.get_all_applications()
            
            if not applications:
                embed = discord.Embed(
                    title="📋 Başvurular",
                    description="Henüz hiç başvuru bulunmuyor.",
                    color=0x3498db
                )
                return await interaction.response.edit_message(embed=embed, view=self)
            
            # Maksimum 10 başvuruyu listele
            applications = applications[:10]
            
            # Özet embed oluştur
            embed = discord.Embed(
                title="📋 Son Başvurular",
                description=f"Sistemde kayıtlı son {len(applications)} başvurunun özeti",
                color=0x3498db
            )
            
            # Her başvuru için özet bilgi
            for app in applications:
                user_id = app['user_id']
                member = interaction.guild.get_member(user_id)
                
                status_emojis = {
                    "pending": "⏳",
                    "approved": "✅",
                    "rejected": "❌",
                    "cancelled": "⛔"
                }
                
                status_emoji = status_emojis.get(app['status'], "❓")
                
                username = member.name if member else app['username']
                user_mention = member.mention if member else f"<@{user_id}>"
                
                embed.add_field(
                    name=f"{status_emoji} Başvuru #{app['id']}",
                    value=(
                        f"**Kullanıcı:** {user_mention}\n"
                        f"**Tarih:** {app['application_date'].split('T')[0]}\n"
                        f"**ID:** `{app['id']}`"
                    ),
                    inline=True
                )
            
            # Thumbnail ve footer
            embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
            embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
            
            # Mevcut view'a ek bir buton ekleyemiyoruz, yeni bir view oluşturalım
            view = BasvurularListeView(self.cog, self.user)
            
            await interaction.response.edit_message(embed=embed, view=view)
            view.message = await interaction.original_response()
            
        except Exception as e:
            await interaction.response.send_message(f"Başvuruları getirirken bir hata oluştu: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="Geri Dön", style=discord.ButtonStyle.danger, emoji="◀️", row=1)
    async def geri_don_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Geri dön butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Ana menüye dön - edit_message ile
        embed = discord.Embed(
            title="🛡️ HydRaboN Yetkili Paneli",
            description=(
                "Hoş geldiniz! Bu panel üzerinden yetkili işlemlerini gerçekleştirebilirsiniz.\n\n"
                "Lütfen yapmak istediğiniz işlemi aşağıdaki butonlardan seçin."
            ),
            color=0x3498db
        )
        
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        view = YetkiliPanelView(self.cog, self.user)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

class BasvurularListeView(discord.ui.View):
    def __init__(self, cog, user):
        super().__init__(timeout=600)  # 10 dakika timeout
        self.cog = cog
        self.user = user
        self.message = None
    
    async def on_timeout(self):
        """Timeout olduğunda butonları devre dışı bırakma"""
        for item in self.children:
            item.disabled = True
        
        if self.message:
            await self.message.edit(view=self)
    
    @discord.ui.button(label="Geri Dön", style=discord.ButtonStyle.danger, emoji="◀️", row=0)
    async def geri_don_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Geri dön butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Başvurular menüsüne dön
        view = BasvurularView(self.cog, self.user)
        embed = discord.Embed(
            title="📝 Başvurular",
            description="Başvurular menüsüne hoş geldiniz. Lütfen yapmak istediğiniz işlemi seçin.",
            color=0x3498db
        )
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

class BasvuruAraModal(discord.ui.Modal, title="Başvuru Arama"):
    def __init__(self, cog, user):
        super().__init__()
        self.cog = cog
        self.user = user
        
        self.basvuru_id = discord.ui.TextInput(
            label="Başvuru ID veya Kullanıcı ID",
            placeholder="Aramak istediğiniz başvurunun ID'sini veya kullanıcı ID'sini girin",
            required=True
        )
        self.add_item(self.basvuru_id)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Form gönderildiğinde"""
        try:
            id_value = self.basvuru_id.value
            db = await get_db()
            
            # Başvuru ID'si mi kullanıcı ID'si mi kontrol et
            try:
                id_int = int(id_value)
                
                # Önce başvuru ID'sine göre ara
                application = None
                try:
                    # Burada başvuru ID'sine göre arama yapacak bir metod olmadığı için
                    # tüm başvuruları getirip filtreliyoruz
                    all_apps = await db.get_all_applications()
                    for app in all_apps:
                        if app['id'] == id_int:
                            application = app
                            break
                except:
                    pass
                
                # Bulunamadıysa kullanıcı ID'sine göre ara
                if not application:
                    application = await db.get_application_by_user_id(id_int)
            except ValueError:
                # ID numerik değilse
                await interaction.response.send_message("Geçersiz ID formatı. Lütfen geçerli bir ID girin.", ephemeral=True)
                return
            
            if not application:
                await interaction.response.send_message(f"Belirtilen ID'ye sahip bir başvuru bulunamadı: {id_value}", ephemeral=True)
                return
            
            # Başvuru detaylarını göster
            await self.show_application_details(interaction, application)
            
        except Exception as e:
            await interaction.response.send_message(f"Başvuru aranırken bir hata oluştu: {str(e)}", ephemeral=True)
    
    async def show_application_details(self, interaction, application):
        """Başvuru detaylarını gösteren embed ve butonları oluşturur"""
        guild = interaction.guild
        
        # Kullanıcı bilgilerini getir
        user_id = application['user_id']
        member = guild.get_member(user_id)
        
        # Başvuru detaylarını içeren embed oluştur
        embed = discord.Embed(
            title=f"📝 Başvuru #{application['id']}",
            description=f"**Başvuru Tarihi:** {application['application_date'].split('T')[0]}",
            color=0x3498db
        )
        
        # Kullanıcı bilgileri
        embed.add_field(
            name="👤 Kullanıcı Bilgileri",
            value=(
                f"**ID:** {user_id}\n"
                f"**Kullanıcı:** {member.mention if member else application['username']}"
            ),
            inline=False
        )
        
        # Durum bilgisi
        status_emoji = {
            "pending": "⏳ Beklemede",
            "approved": "✅ Onaylandı",
            "rejected": "❌ Reddedildi",
            "cancelled": "⛔ İptal Edildi"
        }
        
        embed.add_field(
            name="📊 Durum",
            value=status_emoji.get(application['status'], "Bilinmiyor"),
            inline=False
        )
        
        # Cevapları ekle
        embed.add_field(name="📋 Form Cevapları", value="", inline=False)
        
        for i, (question, answer) in enumerate(application['answers'].items()):
            embed.add_field(name=f"Soru {i+1}", value=f"**{question}**\n{answer[:1024]}", inline=False)
        
        # İnceleme bilgisi (eğer varsa)
        if application['reviewer_id']:
            reviewer = guild.get_member(application['reviewer_id'])
            reviewer_mention = reviewer.mention if reviewer else f"ID: {application['reviewer_id']}"
            
            embed.add_field(
                name="🔍 İnceleme Bilgileri",
                value=(
                    f"**İnceleyen:** {reviewer_mention}\n"
                    f"**İnceleme Tarihi:** {application['review_date']}\n"
                    f"**Mesaj:** {application['review_message']}"
                ),
                inline=False
            )
        
        # Atanan rol bilgisi (eğer onaylandıysa)
        if application['status'] == 'approved' and application['assigned_role_id']:
            role = guild.get_role(application['assigned_role_id'])
            role_mention = role.mention if role else application['assigned_role_name']
            
            embed.add_field(
                name="🏅 Atanan Rol",
                value=role_mention,
                inline=False
            )
        
        # Thumbnail
        if member and member.avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        
        # Footer
        embed.set_footer(text=f"{guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        # Geri dönüş butonu
        view = BasvuruDetayView(self.cog, self.user)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class BasvuruDetayView(discord.ui.View):
    def __init__(self, cog, user):
        super().__init__(timeout=600)  # 10 dakika timeout
        self.cog = cog
        self.user = user
    
    @discord.ui.button(label="Başvurular Menüsüne Dön", style=discord.ButtonStyle.danger, emoji="◀️", row=0)
    async def geri_don_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Geri dön butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Başvurular menüsünü göster
        view = BasvurularView(self.cog, self.user)
        embed = discord.Embed(
            title="📝 Başvurular",
            description="Başvurular menüsüne hoş geldiniz. Lütfen yapmak istediğiniz işlemi seçin.",
            color=0x3498db
        )
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()
    
    @discord.ui.button(label="Ana Menüye Dön", style=discord.ButtonStyle.green, emoji="🏠", row=0)
    async def ana_menu_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ana menüye dönüş butonu"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Ana menüye dön - edit_message ile
        embed = discord.Embed(
            title="🛡️ HydRaboN Yetkili Paneli",
            description=(
                "Hoş geldiniz! Bu panel üzerinden yetkili işlemlerini gerçekleştirebilirsiniz.\n\n"
                "Lütfen yapmak istediğiniz işlemi aşağıdaki butonlardan seçin."
            ),
            color=0x3498db
        )
        
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        view = YetkiliPanelView(self.cog, self.user)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()
    
class YetkiliDuyuruView(discord.ui.View):
    def __init__(self, cog, user):
        super().__init__(timeout=600)  # 10 dakika timeout
        self.cog = cog
        self.user = user
        self.message = None
    
    async def on_timeout(self):
        """Timeout olduğunda butonları devre dışı bırakma"""
        for item in self.children:
            item.disabled = True
        
        if self.message:
            await self.message.edit(view=self)
    
    @discord.ui.button(label="Duyuru Oluştur", style=discord.ButtonStyle.blurple, emoji="📢", row=0)
    async def duyuru_olustur_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Duyuru oluşturma butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Yönetici yetkisi kontrolü
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "Bu işlemi gerçekleştirmek için Administrator yetkisine sahip olmanız gerekiyor.",
                ephemeral=True
            )
        
        # Duyuru oluşturma modalını göster
        await interaction.response.send_modal(YetkiliDuyuruModal(self.cog, self.user))
    
    @discord.ui.button(label="Geri Dön", style=discord.ButtonStyle.danger, emoji="◀️", row=1)
    async def geri_don_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Geri dön butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Ana menüye dön - edit_message ile
        embed = discord.Embed(
            title="🛡️ HydRaboN Yetkili Paneli",
            description=(
                "Hoş geldiniz! Bu panel üzerinden yetkili işlemlerini gerçekleştirebilirsiniz.\n\n"
                "Lütfen yapmak istediğiniz işlemi aşağıdaki butonlardan seçin."
            ),
            color=0x3498db
        )
        
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        view = YetkiliPanelView(self.cog, self.user)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

class YetkiliDuyuruModal(discord.ui.Modal, title="Yetkili Duyurusu Oluştur"):
    def __init__(self, cog, user):
        super().__init__()
        self.cog = cog
        self.user = user
        
        self.duyuru_basligi = discord.ui.TextInput(
            label="Duyuru Başlığı",
            placeholder="Duyuru için kısa bir başlık girin",
            required=True,
            max_length=100
        )
        self.add_item(self.duyuru_basligi)
        
        self.duyuru_metni = discord.ui.TextInput(
            label="Duyuru Metni",
            placeholder="Duyuru içeriğini detaylı olarak girin",
            required=True,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.duyuru_metni)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Form gönderildiğinde"""
        # Hedef rolleri seçme viewi göster
        view = YetkiliDuyuruRolSecView(
            self.cog, 
            self.user, 
            self.duyuru_basligi.value, 
            self.duyuru_metni.value
        )
        
        embed = discord.Embed(
            title="📢 Yetkili Duyurusu - Hedef Roller",
            description=(
                "Duyurunun gönderileceği yetkili rollerini seçin.\n\n"
                "**Duyuru Başlığı:** " + self.duyuru_basligi.value
            ),
            color=0x3498db
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()

class YetkiliDuyuruRolSecView(discord.ui.View):
    def __init__(self, cog, user, baslik, metin):
        super().__init__(timeout=300)  # 5 dakika timeout
        self.cog = cog
        self.user = user
        self.baslik = baslik
        self.metin = metin
        self.message = None
        self.secilen_roller = []
        
        # Rol seçim menüsünü ekle
        self.add_item(YetkiliRolSecimMenu(self))
    
    async def on_timeout(self):
        """Timeout olduğunda butonları devre dışı bırakma"""
        for item in self.children:
            item.disabled = True
        
        if self.message:
            await self.message.edit(view=self)
    
    @discord.ui.button(label="Duyuruyu Gönder", style=discord.ButtonStyle.green, emoji="✅", row=1)
    async def duyuru_gonder_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Duyuruyu gönderme butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Yönetici yetkisi kontrolü
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "Bu işlemi gerçekleştirmek için Administrator yetkisine sahip olmanız gerekiyor.",
                ephemeral=True
            )
        
        # Rol seçilip seçilmediğini kontrol et
        if not self.secilen_roller:
            return await interaction.response.send_message(
                "Lütfen duyuruyu göndermek için en az bir yetkili rolü seçin.",
                ephemeral=True
            )
        
        # Çift tıklamayı engelle: Butonu devre dışı bırak ve görünümü güncelle
        button.disabled = True
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            await interaction.edit_original_response(view=self)
        except Exception as e:
            try:
                await interaction.followup.send(f"Duyuru gönderim sırasında hata: {str(e)}", ephemeral=True)
            except Exception:
                pass
            return

        # Duyurunun gönderileceği üyeleri topla
        guild = interaction.guild
        hedef_uyeler = set()
        rol_isimleri = []
        
        for rol_id in self.secilen_roller:
            rol = guild.get_role(rol_id)
            if rol:
                rol_isimleri.append(rol.name)
                for uye in rol.members:
                    hedef_uyeler.add(uye)
        
        # İşlem başlıyor bilgisi (daha önce defer edildi, tekrar etmeye gerek yok)
        
        # Duyuru mesajını oluştur
        embed = discord.Embed(
            title=f"📢 {self.baslik}",
            description=self.metin,
            color=0x3498db,
            timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
        )
        
        embed.set_author(
            name=f"{interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )
        
        embed.set_footer(
            text=f"{interaction.guild.name} • Yetkili Duyurusu",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        
        # Duyuruyu DM olarak gönder
        basarili = 0
        basarisiz = 0
        
        for uye in hedef_uyeler:
            try:
                await uye.send(embed=embed)
                basarili += 1
            except:
                basarisiz += 1
        
        # İşlem sonucu
        sonuc_embed = discord.Embed(
            title="📢 Duyuru Gönderim Sonucu",
            description=(
                f"**{basarili}** kişiye duyuru başarıyla gönderildi.\n"
                f"**{basarisiz}** kişiye duyuru gönderilemedi (DM kapalı olabilir).\n\n"
                f"**Hedef Roller:** {', '.join(rol_isimleri)}"
            ),
            color=0x3498db
        )
        
        # Log kanalına mesaj gönder
        log_kanali = discord.utils.get(guild.text_channels, name="yetkili-panel-log")
        if log_kanali:
            log_embed = discord.Embed(
                title="📢 Yetkili Duyurusu Gönderildi",
                description=(
                    f"**Gönderen:** {interaction.user.mention} ({interaction.user.id})\n"
                    f"**Başlık:** {self.baslik}\n"
                    f"**Hedef Roller:** {', '.join(rol_isimleri)}\n"
                    f"**Gönderim Durumu:** {basarili} başarılı, {basarisiz} başarısız"
                ),
                color=0x3498db,
                timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
            )
            
            log_embed.add_field(
                name="Duyuru İçeriği",
                value=self.metin[:1024],
                inline=False
            )
            
            await log_kanali.send(embed=log_embed)
        
        # Ana menüye dönüş için view
        view = YetkiliPanelView(self.cog, self.user)
        
        await interaction.followup.send(embed=sonuc_embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="İptal", style=discord.ButtonStyle.danger, emoji="❌", row=1)
    async def iptal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """İptal butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Ana menüye dön - edit_message ile
        embed = discord.Embed(
            title="🛡️ HydRaboN Yetkili Paneli",
            description=(
                "Hoş geldiniz! Bu panel üzerinden yetkili işlemlerini gerçekleştirebilirsiniz.\n\n"
                "Lütfen yapmak istediğiniz işlemi aşağıdaki butonlardan seçin."
            ),
            color=0x3498db
        )
        
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        view = YetkiliPanelView(self.cog, self.user)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

class YetkiliRolSecimMenu(discord.ui.Select):
    def __init__(self, ana_view):
        self.ana_view = ana_view
        self.secili_roller = []
        
        options = []
        for rol_adi, rol_id in YETKILI_ROLLERI.items():
            options.append(
                discord.SelectOption(
                    label=rol_adi,
                    value=str(rol_id),
                    description=f"ID: {rol_id}"
                )
            )
        
        super().__init__(
            placeholder="Duyuru için yetkili rolleri seçin...",
            min_values=1,
            max_values=len(options),
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Roller seçildiğinde"""
        if interaction.user.id != self.ana_view.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Seçilen rolleri kaydet
        self.ana_view.secilen_roller = [int(value) for value in self.values]
        
        # Seçilen rollerin isimlerini al
        guild = interaction.guild
        rol_isimleri = []
        
        for rol_id in self.ana_view.secilen_roller:
            rol = guild.get_role(rol_id)
            if rol:
                rol_isimleri.append(rol.name)
        
        # Seçim bilgisini güncelle
        embed = discord.Embed(
            title="📢 Yetkili Duyurusu - Hedef Roller",
            description=(
                "Duyurunun gönderileceği yetkili rollerini seçin.\n\n"
                "**Duyuru Başlığı:** " + self.ana_view.baslik + "\n\n"
                "**Seçilen Roller:** " + ", ".join(rol_isimleri)
            ),
            color=0x3498db
        )
        
        await interaction.response.edit_message(embed=embed, view=self.ana_view)

class YetkiYukseltModal(discord.ui.Modal, title="Yetki Yükseltme İşlemi"):
    def __init__(self, cog, user, yetkili_rol_id):
        super().__init__()
        self.cog = cog
        self.user = user
        self.yetkili_rol_id = yetkili_rol_id
        
        self.kullanici_id = discord.ui.TextInput(
            label="Kullanıcı ID",
            placeholder="Yetkisini yükseltmek istediğiniz kullanıcının ID'sini girin",
            required=True,
            min_length=17,
            max_length=20
        )
        self.add_item(self.kullanici_id)
        
        self.sebep = discord.ui.TextInput(
            label="Yükseltme Sebebi",
            placeholder="Yetki yükseltme sebebini belirtin",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.add_item(self.sebep)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Form gönderildiğinde"""
        try:
            # ID'nin sayısal olup olmadığını kontrol et
            kullanici_id = int(self.kullanici_id.value)
            
            # İşlem başlıyor bilgisi
            await interaction.response.defer(ephemeral=True)
            
            # Yetki yükseltme işlemini başlat
            await self.cog.yetki_yukselt(
                interaction,
                kullanici_id,
                self.sebep.value,
                self.yetkili_rol_id
            )
            
        except ValueError:
            await interaction.response.send_message("Geçersiz kullanıcı ID'si. Lütfen sayısal bir ID girin.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"İşlem sırasında bir hata oluştu: {str(e)}", ephemeral=True)

class YetkiDusurModal(discord.ui.Modal, title="Yetki Düşürme İşlemi"):
    def __init__(self, cog, user, yetkili_rol_id):
        super().__init__()
        self.cog = cog
        self.user = user
        self.yetkili_rol_id = yetkili_rol_id
        
        self.kullanici_id = discord.ui.TextInput(
            label="Kullanıcı ID",
            placeholder="Yetkisini düşürmek istediğiniz kullanıcının ID'sini girin",
            required=True,
            min_length=17,
            max_length=20
        )
        self.add_item(self.kullanici_id)
        
        self.sebep = discord.ui.TextInput(
            label="Düşürme Sebebi",
            placeholder="Yetki düşürme sebebini belirtin",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.add_item(self.sebep)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Form gönderildiğinde"""
        try:
            # ID'nin sayısal olup olmadığını kontrol et
            kullanici_id = int(self.kullanici_id.value)
            
            # İşlem başlıyor bilgisi
            await interaction.response.defer(ephemeral=True)
            
            # Yetki düşürme işlemini başlat
            await self.cog.yetki_dusur(
                interaction,
                kullanici_id,
                self.sebep.value,
                self.yetkili_rol_id
            )
            
        except ValueError:
            await interaction.response.send_message("Geçersiz kullanıcı ID'si. Lütfen sayısal bir ID girin.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"İşlem sırasında bir hata oluştu: {str(e)}", ephemeral=True)

class YetkiliEkleModal(discord.ui.Modal, title="Yetkili Ekle"):
    def __init__(self, cog, user):
        super().__init__()
        self.cog = cog
        self.user = user

    user_id_input = discord.ui.TextInput(
        label="Kullanıcı ID",
        placeholder="Yetkili yapılacak kullanıcının ID'si",
        min_length=15,
        max_length=25,
        required=True
    )

    reason_input = discord.ui.TextInput(
        label="Sebep",
        placeholder="Yetkili ekleme sebebi",
        min_length=2,
        max_length=200,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Yönetim izni kontrolü
        if not user_has_management_permission(interaction.user):
            return await interaction.response.send_message("Bu işlem için yetkiniz yok.", ephemeral=True)
        try:
            hedef_id = int(self.user_id_input.value)
        except ValueError:
            return await interaction.response.send_message("Kullanıcı ID geçerli bir sayı olmalıdır.", ephemeral=True)
        # Rol seçimi için view aç
        view = YetkiliEkleRolSecimView(self.cog, interaction.user, hedef_id, self.reason_input.value)
        embed = discord.Embed(
            title="Rol Seçimi",
            description="Lütfen verilecek yetkiyi aşağıdaki menüden seçin.",
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class YetkiliCikartModal(discord.ui.Modal, title="Yetkili Çıkart"):
    def __init__(self, cog, user):
        super().__init__()
        self.cog = cog
        self.user = user

    user_id_input = discord.ui.TextInput(
        label="Kullanıcı ID",
        placeholder="Yetkili rol(ler)i kaldırılacak kullanıcının ID'si",
        min_length=15,
        max_length=25,
        required=True
    )

    reason_input = discord.ui.TextInput(
        label="Sebep",
        placeholder="Yetkili çıkartma sebebi",
        min_length=2,
        max_length=200,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Yönetim izni kontrolü
        if not user_has_management_permission(interaction.user):
            return await interaction.response.send_message("Bu işlem için yetkiniz yok.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            hedef_id = int(self.user_id_input.value)
        except ValueError:
            return await interaction.followup.send("Kullanıcı ID geçerli bir sayı olmalıdır.", ephemeral=True)
        await self.cog.yetkili_cikart(interaction, hedef_id, self.reason_input.value)

class YetkiliEkleRolSecimMenu(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = []
        # STAJYER'den ADMİN'e kadar seçim sunalım; YK rollerini manuel atamayalım
        selectable_roles = [
            ("STAJYER", YETKILI_ROLLERI["STAJYER"]),
            ("ASİSTAN", YETKILI_ROLLERI["ASİSTAN"]),
            ("MODERATÖR", YETKILI_ROLLERI["MODERATÖR"]),
            ("ADMİN", YETKILI_ROLLERI["ADMİN"]),
        ]
        for name, rid in selectable_roles:
            options.append(discord.SelectOption(label=name, value=str(rid)))
        super().__init__(
            placeholder="Verilecek yetkiyi seçin...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.requester.id:
            return await interaction.response.send_message("Bu seçim size ait değil!", ephemeral=True)
        try:
            role_id = int(self.values[0])
        except ValueError:
            return await interaction.response.send_message("Geçersiz rol seçimi.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self.parent_view.on_role_selected(interaction, role_id)

class YetkiliEkleRolSecimView(discord.ui.View):
    def __init__(self, cog, requester: discord.Member, hedef_kullanici_id: int, reason: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.requester = requester
        self.hedef_kullanici_id = hedef_kullanici_id
        self.reason = reason
        self.add_item(YetkiliEkleRolSecimMenu(self))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    async def on_role_selected(self, interaction: discord.Interaction, role_id: int):
        await self.cog.yetkili_ekle(interaction, self.hedef_kullanici_id, self.reason, role_id)

# Otomatik Mesajlar için sınıflar
class OtomatikMesajlarView(discord.ui.View):
    def __init__(self, cog, user):
        super().__init__(timeout=600)  # 10 dakika timeout
        self.cog = cog
        self.user = user
        self.message = None
    
    async def on_timeout(self):
        """Timeout olduğunda butonları devre dışı bırakma"""
        for item in self.children:
            item.disabled = True
        
        if self.message:
            await self.message.edit(view=self)
    
    @discord.ui.button(label="Mesaj Ekle", style=discord.ButtonStyle.green, emoji="➕", row=0)
    async def mesaj_ekle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Yeni mesaj ekleme butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Yeni mesaj ekleme modalını göster
        await interaction.response.send_modal(OtomatikMesajEkleModal(self.cog, self.user))
        
    @discord.ui.button(label="Mesajları Listele", style=discord.ButtonStyle.blurple, emoji="📋", row=0)
    async def mesajlari_listele_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mesajları listeleme butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Mesajları listele
        await self.cog.list_scheduled_messages(interaction)
    
    @discord.ui.button(label="Mesaj Görüntüle", style=discord.ButtonStyle.blurple, emoji="🔍", row=0)
    async def mesaj_goruntule_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mesaj görüntüleme butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Görüntülenecek mesaj ID'sini soran modalı göster
        await interaction.response.send_modal(MesajGoruntuleModal(self.cog, self.user))
    
    @discord.ui.button(label="Mesaj Sil", style=discord.ButtonStyle.red, emoji="🗑️", row=1)
    async def mesaj_sil_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mesaj silme butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Silinecek mesaj ID'sini soran modalı göster
        await interaction.response.send_modal(OtomatikMesajSecModal(self.cog, self.user, "delete"))
    
    @discord.ui.button(label="Geri Dön", style=discord.ButtonStyle.danger, emoji="◀️", row=1)
    async def geri_don_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Geri dön butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Ana menüye dön - edit_message ile
        embed = discord.Embed(
            title="🛡️ HydRaboN Yetkili Paneli",
            description=(
                "Hoş geldiniz! Bu panel üzerinden yetkili işlemlerini gerçekleştirebilirsiniz.\n\n"
                "Lütfen yapmak istediğiniz işlemi aşağıdaki butonlardan seçin."
            ),
            color=0x3498db
        )
        
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        view = YetkiliPanelView(self.cog, self.user)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

class OtomatikMesajEkleModal(discord.ui.Modal, title="Otomatik Mesaj Ekle"):
    def __init__(self, cog, user):
        super().__init__(timeout=None) # Timeout'u None yaparak veya artırarak modalin daha uzun süre açık kalmasını sağlayabilirsiniz.
        self.cog = cog
        self.user = user
        
        self.mesaj_icerik = discord.ui.TextInput(
            label="Mesaj İçeriği",
            placeholder="Otomatik olarak gönderilecek mesajın içeriğini girin...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000
        )
        self.add_item(self.mesaj_icerik)
        
        self.tekrar_sayisi = discord.ui.TextInput(
            label="Tekrar Sayısı (0: Sonsuz, 1-100)",
            placeholder="Mesajın kaç kez gönderileceğini belirtin (0-100)",
            default="1",
            required=True,
            max_length=3
        )
        self.add_item(self.tekrar_sayisi)
        
        self.gun_input = discord.ui.TextInput(
            label="Gün Aralığı (Boş bırakılabilir)",
            placeholder="Örn: 7 (7 günde bir)",
            required=False, # Artık zorunlu değil
            max_length=3,
            default="0"
        )
        self.add_item(self.gun_input)

        self.saat_input = discord.ui.TextInput(
            label="Saat Aralığı (Boş bırakılabilir)",
            placeholder="Örn: 12 (12 saatte bir)",
            required=False, # Artık zorunlu değil
            max_length=3,
            default="0"
        )
        self.add_item(self.saat_input)

        self.dakika_input = discord.ui.TextInput(
            label="Dakika Aralığı (Boş bırakılabilir)",
            placeholder="Örn: 30 (30 dakikada bir)",
            required=False, # Artık zorunlu değil
            max_length=3,
            default="0"
        )
        self.add_item(self.dakika_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Form gönderildiğinde"""
        try:
            tekrar_sayisi = int(self.tekrar_sayisi.value)
            if not (0 <= tekrar_sayisi <= 100): # 0 sonsuz anlamına gelecek
                return await interaction.response.send_message("Tekrar sayısı 0-100 arasında olmalıdır.", ephemeral=True)
            
            gun_str = self.gun_input.value.strip()
            saat_str = self.saat_input.value.strip()
            dakika_str = self.dakika_input.value.strip()

            gun = int(gun_str) if gun_str else 0
            saat = int(saat_str) if saat_str else 0
            dakika = int(dakika_str) if dakika_str else 0

            if gun < 0 or saat < 0 or dakika < 0:
                return await interaction.response.send_message("Gün, saat ve dakika negatif olamaz.", ephemeral=True)
            
            if saat >= 24:
                 return await interaction.response.send_message("Saat 0-23 arasında olmalıdır.", ephemeral=True)
            if dakika >= 60:
                 return await interaction.response.send_message("Dakika 0-59 arasında olmalıdır.", ephemeral=True)

            if gun == 0 and saat == 0 and dakika == 0:
                return await interaction.response.send_message("En az bir zaman aralığı (gün, saat veya dakika) belirtmelisiniz.", ephemeral=True)

            schedule_data = {"days": gun, "hours": saat, "minutes": dakika}
            
            # Kanal seçim menüsünü göster
            view = KanalSecimView(
                self.cog,
                self.user,
                self.mesaj_icerik.value,
                tekrar_sayisi,
                schedule_data # zaman_araligi yerine schedule_data
            )
            await interaction.response.send_message(
                "Mesajın gönderileceği kanalı seçin:",
                view=view,
                ephemeral=True
            )
            view.message = await interaction.original_response()
            
        except ValueError:
            await interaction.response.send_message("Lütfen gün, saat, dakika ve tekrar sayısı için geçerli sayısal değerler girin.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Bir hata oluştu: {e}", ephemeral=True)

class KanalSecimView(discord.ui.View):
    def __init__(self, cog, user, mesaj_icerik, tekrar_sayisi, schedule_data): # zaman_araligi -> schedule_data
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.mesaj_icerik = mesaj_icerik
        self.tekrar_sayisi = tekrar_sayisi
        self.schedule_data = schedule_data # Değişti
        self.message = None 
        
        self.add_item(KanalSecimMenu(self))
    
    async def on_timeout(self):
        """Timeout olduğunda butonları devre dışı bırakma"""
        for item in self.children:
            item.disabled = True
        
        message = getattr(self, "message", None)
        if message:
            await message.edit(view=self)

class KanalSecimMenu(discord.ui.Select):
    def __init__(self, ana_view):
        self.ana_view = ana_view
        
        # Görünür tüm metin kanallarını al
        text_channels = []
        guild = self.ana_view.user.guild
        for channel in guild.text_channels:
            # Kullanıcının mesaj gönderebileceği kanallar
            member_permissions = channel.permissions_for(self.ana_view.user)
            if member_permissions.send_messages and member_permissions.view_channel:
                text_channels.append(channel)
        
        # En fazla 25 kanal gösterebiliriz (Discord limiti)
        text_channels = text_channels[:25]
        
        options = [
            discord.SelectOption(
                label=f"#{channel.name}",
                value=str(channel.id),
                description=f"ID: {channel.id}"
            ) for channel in text_channels
        ]
        
        super().__init__(
            placeholder="Mesajın gönderileceği kanalı seçin...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Kanal seçildiğinde"""
        if interaction.user.id != self.ana_view.user.id:
            return await interaction.response.send_message("Bu seçim size ait değil!", ephemeral=True)
            
        kanal_id = int(self.values[0])
        kanal = interaction.guild.get_channel(kanal_id)
        
        if not kanal:
            return await interaction.response.send_message("Seçilen kanal bulunamadı.", ephemeral=True)
        
        # Zamanlamayı oluştur
        schedule_type = "interval_custom" # Değişti
        # schedule_data zaten ana_view'de doğru formatta
        
        try:
            db = await get_db()
            mesaj_id = await db.add_scheduled_message(
                channel_id=kanal_id,
                channel_name=kanal.name,
                message_content=self.ana_view.mesaj_icerik,
                created_by=interaction.user.id,
                schedule_type=schedule_type, 
                schedule_data=self.ana_view.schedule_data, # Değişti
                repeat_count=self.ana_view.tekrar_sayisi,
                # embed_data=None # Gerekirse eklenecek
            )
            
            # Kullanıcıya bildirim gönder
            embed = discord.Embed(
                title="✅ Otomatik Mesaj Eklendi",
                description=f"Otomatik mesaj başarıyla eklendi.\n\n**Mesaj ID:** `{mesaj_id}`",
                color=discord.Color.green()
            )
            
            zaman_araligi_str = []
            if self.ana_view.schedule_data.get("days",0) > 0:
                zaman_araligi_str.append(f"{self.ana_view.schedule_data['days']} gün")
            if self.ana_view.schedule_data.get("hours",0) > 0:
                zaman_araligi_str.append(f"{self.ana_view.schedule_data['hours']} saat")
            if self.ana_view.schedule_data.get("minutes",0) > 0:
                zaman_araligi_str.append(f"{self.ana_view.schedule_data['minutes']} dakika")
            
            embed.add_field(
                name="Mesaj Ayarları",
                value=(
                    f"**Kanal:** <#{kanal_id}>\n"
                    f"**Zaman Aralığı:** {', '.join(zaman_araligi_str) if zaman_araligi_str else 'Belirtilmedi'}\n"
                    f"**Tekrar Sayısı:** {'Sonsuz' if self.ana_view.tekrar_sayisi == 0 else self.ana_view.tekrar_sayisi}"
                ),
                inline=False
            )
            
            # Log kanalına da bildirim gönder
            log_channel = discord.utils.get(interaction.guild.text_channels, name="yetkili-panel-log")
            if log_channel:
                log_embed = discord.Embed(
                    title="⏱️ Otomatik Mesaj Eklendi",
                    description=f"**{interaction.user.name}** tarafından yeni bir otomatik mesaj eklendi.",
                    color=0x3498db,
                    timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
                )
                
                log_embed.add_field(
                    name="Mesaj Bilgileri",
                    value=(
                        f"**Mesaj ID:** `{mesaj_id}`\n"
                        f"**Kanal:** <#{kanal_id}>\n"
                        f"**Zaman Aralığı:** {', '.join(zaman_araligi_str) if zaman_araligi_str else 'Belirtilmedi'}\n"
                        f"**Tekrar Sayısı:** {'Sonsuz' if self.ana_view.tekrar_sayisi == 0 else self.ana_view.tekrar_sayisi}"
                    ),
                    inline=False
                )
                
                log_embed.add_field(
                    name="Mesaj İçeriği",
                    value=self.ana_view.mesaj_icerik[:1000] + ("..." if len(self.ana_view.mesaj_icerik) > 1000 else ""),
                    inline=False
                )
                
                log_embed.set_footer(text=f"Kullanıcı ID: {interaction.user.id}")
                await log_channel.send(embed=log_embed)
            
            # Ana menüye dönüş butonu
            view = OtomatikMesajlarView(self.ana_view.cog, self.ana_view.user)
            await interaction.response.edit_message(embed=embed, view=view)
            
        except Exception as e:
            await interaction.response.edit_message(
                content=f"Otomatik mesaj eklenirken bir hata oluştu: {str(e)}",
                view=None
            )

class OtomatikMesajSecModal(discord.ui.Modal):
    def __init__(self, cog, user, action_type):
        self.action_type = action_type
        title = "Mesaj Düzenle" if action_type == "edit" else "Mesaj Sil"
        super().__init__(title=title)
        
        self.cog = cog
        self.user = user
        
        self.mesaj_id = discord.ui.TextInput(
            label="Mesaj ID",
            placeholder="Düzenlemek/silmek istediğiniz mesajın ID'sini girin",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.mesaj_id)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Form gönderildiğinde"""
        try:
            mesaj_id = int(self.mesaj_id.value)
            
            # Mesajın var olup olmadığını kontrol et
            db = await get_db()
            mesaj = await db.get_scheduled_message(mesaj_id)
            
            if not mesaj:
                return await interaction.response.send_message(
                    f"ID'si {mesaj_id} olan bir otomatik mesaj bulunamadı.",
                    ephemeral=True
                )
            
            # Kullanıcı sadece kendi oluşturduğu mesajları düzenleyebilir
            # Admin ve üstü roller herhangi bir mesajı düzenleyebilir
            is_admin = interaction.user.guild_permissions.administrator
            is_owner = mesaj['created_by'] == interaction.user.id
            
            if not is_admin and not is_owner:
                return await interaction.response.send_message(
                    "Bu mesajı düzenlemek için yetkiniz yok. Sadece kendi oluşturduğunuz mesajları düzenleyebilirsiniz.",
                    ephemeral=True
                )
            
            if self.action_type == "edit":
                # Mesaj düzenleme modalını göster
                await interaction.response.send_modal(OtomatikMesajDuzenleModal(self.cog, self.user, mesaj))
            else:  # action_type == "delete"
                # Mesajı sil
                deleted = await db.delete_scheduled_message(mesaj_id)
                
                if deleted:
                    embed = discord.Embed(
                        title="✅ Otomatik Mesaj Silindi",
                        description=f"ID'si `{mesaj_id}` olan otomatik mesaj başarıyla silindi.",
                        color=discord.Color.green()
                    )
                    
                    # Log kanalına bildirim gönder
                    log_channel = discord.utils.get(interaction.guild.text_channels, name="yetkili-panel-log")
                    if log_channel:
                        log_embed = discord.Embed(
                            title="🗑️ Otomatik Mesaj Silindi",
                            description=f"**{interaction.user.name}** tarafından bir otomatik mesaj silindi.",
                            color=discord.Color.red(),
                            timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
                        )
                        
                        log_embed.add_field(
                            name="Mesaj Bilgileri",
                            value=(
                                f"**Mesaj ID:** `{mesaj_id}`\n"
                                f"**Kanal:** <#{mesaj['channel_id']}>\n"
                                f"**Oluşturan:** <@{mesaj['created_by']}>"
                            ),
                            inline=False
                        )
                        
                        log_embed.set_footer(text=f"Silen Kullanıcı ID: {interaction.user.id}")
                        await log_channel.send(embed=log_embed)
                    
                    # Ana menüye dönüş butonu
                    view = OtomatikMesajlarView(self.cog, self.user)
                    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                else:
                    await interaction.response.send_message(
                        f"Mesaj silinirken bir hata oluştu.",
                        ephemeral=True
                    )
                
        except ValueError:
            await interaction.response.send_message("Lütfen geçerli bir mesaj ID'si girin.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Bir hata oluştu: {str(e)}", ephemeral=True)

class OtomatikMesajDuzenleModal(discord.ui.Modal, title="Otomatik Mesaj Düzenle"):
    def __init__(self, cog, user, mesaj):
        super().__init__(timeout=None) # Timeout'u None yaparak veya artırarak modalin daha uzun süre açık kalmasını sağlayabilirsiniz.
        self.cog = cog
        self.user = user
        self.mesaj = mesaj
        
        self.mesaj_icerik = discord.ui.TextInput(
            label="Mesaj İçeriği",
            placeholder="Otomatik olarak gönderilecek mesajın içeriğini girin...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
            default=mesaj['message_content']
        )
        self.add_item(self.mesaj_icerik)
        
        self.tekrar_sayisi = discord.ui.TextInput(
            label="Tekrar Sayısı (0: Sonsuz, 1-100)",
            placeholder="Mesajın kaç kez gönderileceğini belirtin (0-100)",
            default=str(mesaj['repeat_count']),
            style=discord.TextStyle.short,
            required=True,
            max_length=3
        )
        self.add_item(self.tekrar_sayisi)
        
        current_schedule = mesaj.get('schedule_data', {})
        current_days = str(current_schedule.get('days', 0))
        current_hours = str(current_schedule.get('hours', 0))
        current_minutes = str(current_schedule.get('minutes', 0))
        
        self.gun_input = discord.ui.TextInput(
            label="Gün Aralığı (Boş bırakılabilir)",
            placeholder="Örn: 7 (7 günde bir)",
            required=False,
            max_length=3,
            default=current_days
        )
        self.add_item(self.gun_input)

        self.saat_input = discord.ui.TextInput(
            label="Saat Aralığı (Boş bırakılabilir)",
            placeholder="Örn: 12 (12 saatte bir)",
            required=False,
            max_length=3,
            default=current_hours
        )
        self.add_item(self.saat_input)

        self.dakika_input = discord.ui.TextInput(
            label="Dakika Aralığı (Boş bırakılabilir)",
            placeholder="Örn: 30 (30 dakikada bir)",
            required=False,
            max_length=3,
            default=current_minutes
        )
        self.add_item(self.dakika_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Form gönderildiğinde"""
        try:
            tekrar_sayisi = int(self.tekrar_sayisi.value)
            if not (0 <= tekrar_sayisi <= 100):
                return await interaction.response.send_message("Tekrar sayısı 0-100 arasında olmalıdır.", ephemeral=True)
            
            gun_str = self.gun_input.value.strip()
            saat_str = self.saat_input.value.strip()
            dakika_str = self.dakika_input.value.strip()

            gun = int(gun_str) if gun_str else 0
            saat = int(saat_str) if saat_str else 0
            dakika = int(dakika_str) if dakika_str else 0

            if gun < 0 or saat < 0 or dakika < 0:
                return await interaction.response.send_message("Gün, saat ve dakika negatif olamaz.", ephemeral=True)
            
            if saat >= 24:
                 return await interaction.response.send_message("Saat 0-23 arasında olmalıdır.", ephemeral=True)
            if dakika >= 60:
                 return await interaction.response.send_message("Dakika 0-59 arasında olmalıdır.", ephemeral=True)

            if gun == 0 and saat == 0 and dakika == 0:
                return await interaction.response.send_message("En az bir zaman aralığı (gün, saat veya dakika) belirtmelisiniz.", ephemeral=True)

            schedule_data = {"days": gun, "hours": saat, "minutes": dakika}
            
            try:
                db = await get_db()
                updated = await db.update_scheduled_message(
                    message_id=self.mesaj['id'],
                    message_content=self.mesaj_icerik.value,
                    schedule_data=schedule_data,
                    repeat_count=tekrar_sayisi,
                    # schedule_type gerekirse güncellenebilir, şimdilik veritabanı fonksiyonu bunu almıyor varsayalım
                )
                
                if updated:
                    embed = discord.Embed(
                        title="✅ Otomatik Mesaj Güncellendi",
                        description=f"ID'si `{self.mesaj['id']}` olan otomatik mesaj başarıyla güncellendi.",
                        color=discord.Color.green()
                    )
                    
                    zaman_araligi_str = []
                    if schedule_data.get("days",0) > 0:
                        zaman_araligi_str.append(f"{schedule_data['days']} gün")
                    if schedule_data.get("hours",0) > 0:
                        zaman_araligi_str.append(f"{schedule_data['hours']} saat")
                    if schedule_data.get("minutes",0) > 0:
                        zaman_araligi_str.append(f"{schedule_data['minutes']} dakika")

                    embed.add_field(
                        name="Yeni Mesaj Ayarları",
                        value=(
                            f"**Kanal:** <#{self.mesaj['channel_id']}>\n"
                            f"**Zaman Aralığı:** {', '.join(zaman_araligi_str) if zaman_araligi_str else 'Belirtilmedi'}\n"
                            f"**Tekrar Sayısı:** {'Sonsuz' if tekrar_sayisi == 0 else tekrar_sayisi}"
                        ),
                        inline=False
                    )
                    
                    embed.add_field(
                        name="Mesaj İçeriği",
                        value=self.mesaj_icerik.value[:1000] + ("..." if len(self.mesaj_icerik.value) > 1000 else ""),
                        inline=False
                    )
                    
                    # Log kanalına bildirim gönder
                    log_channel = discord.utils.get(interaction.guild.text_channels, name="yetkili-panel-log")
                    if log_channel:
                        log_embed = discord.Embed(
                            title="✏️ Otomatik Mesaj Güncellendi",
                            description=f"**{interaction.user.name}** tarafından bir otomatik mesaj güncellendi.",
                            color=0x3498db,
                            timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
                        )
                        
                        log_embed.add_field(
                            name="Mesaj Bilgileri",
                            value=(
                                f"**Mesaj ID:** `{self.mesaj['id']}`\n"
                                f"**Kanal:** <#{self.mesaj['channel_id']}>\n"
                                f"**Oluşturan:** <@{self.mesaj['created_by']}>\n"
                                f"**Yeni Zaman Aralığı:** {', '.join(zaman_araligi_str) if zaman_araligi_str else 'Belirtilmedi'}\n"
                                f"**Yeni Tekrar Sayısı:** {'Sonsuz' if tekrar_sayisi == 0 else tekrar_sayisi}"
                            ),
                            inline=False
                        )
                        
                        log_embed.add_field(
                            name="Yeni Mesaj İçeriği",
                            value=self.mesaj_icerik.value[:1000] + ("..." if len(self.mesaj_icerik.value) > 1000 else ""),
                            inline=False
                        )
                        
                        log_embed.set_footer(text=f"Düzenleyen Kullanıcı ID: {interaction.user.id}")
                        await log_channel.send(embed=log_embed)
                    
                    # Ana menüye dönüş butonu
                    view = OtomatikMesajlarView(self.cog, self.user)
                    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                else:
                    await interaction.response.send_message(
                        f"Mesaj güncellenirken bir hata oluştu. Mesaj bulunamadı veya güncellenemedi.",
                        ephemeral=True
                    )
            except Exception as e:
                await interaction.response.send_message(
                    f"Mesaj güncellenirken bir hata oluştu: {str(e)}",
                    ephemeral=True
                )
                
        except ValueError:
            await interaction.response.send_message("Lütfen sayısal değerler girin.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Bir hata oluştu: {str(e)}", ephemeral=True)

# Mesaj görüntüleme için modal
class MesajGoruntuleModal(discord.ui.Modal, title="Mesaj Görüntüle"):
    def __init__(self, cog, user):
        super().__init__()
        self.cog = cog
        self.user = user
        
        self.mesaj_id = discord.ui.TextInput(
            label="Mesaj ID",
            placeholder="Görüntülemek istediğiniz mesajın ID'sini girin",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.mesaj_id)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Form gönderildiğinde"""
        try:
            mesaj_id = int(self.mesaj_id.value)
            
            # Mesajın var olup olmadığını kontrol et
            try:
                db = await get_db()
                mesaj = await db.get_scheduled_message(mesaj_id)
                
                if not mesaj:
                    return await interaction.response.send_message(
                        f"ID'si {mesaj_id} olan bir otomatik mesaj bulunamadı.",
                        ephemeral=True
                    )
                
                # Mesaj detaylarını gösterecek embed oluştur
                embed = discord.Embed(
                    title=f"📝 Otomatik Mesaj #{mesaj_id}",
                    description="Otomatik mesaj detayları",
                    color=0x3498db
                )
                
                # Mesaj bilgileri
                status_emoji = "✅" if mesaj['active'] else "❌"
                
                schedule_data = mesaj.get('schedule_data', {})
                zaman_bilgisi_parts = []
                if schedule_data.get("days", 0) > 0:
                    zaman_bilgisi_parts.append(f"{schedule_data['days']} gün")
                if schedule_data.get("hours", 0) > 0:
                    zaman_bilgisi_parts.append(f"{schedule_data['hours']} saat")
                if schedule_data.get("minutes", 0) > 0:
                    zaman_bilgisi_parts.append(f"{schedule_data['minutes']} dakika")
                zaman_bilgisi = ", ".join(zaman_bilgisi_parts) + " aralıkla" if zaman_bilgisi_parts else "Belirtilmemiş aralıkla"
                
                son_gonderim_str = "Henüz gönderilmedi"
                if mesaj['last_sent']:
                    try:
                        son_gonderim_dt_utc = datetime.datetime.fromisoformat(mesaj['last_sent'].replace("Z", "+00:00")).replace(tzinfo=datetime.timezone.utc)
                        son_gonderim_dt_tr = son_gonderim_dt_utc + datetime.timedelta(hours=3)
                        son_gonderim_str = son_gonderim_dt_tr.strftime('%d.%m.%Y %H:%M')
                    except ValueError:
                        son_gonderim_str = f"{mesaj['last_sent']} (Format Hatalı)"
                
                olusturulma_str = "Bilinmiyor"
                if mesaj['created_at']:
                    try:
                        olusturulma_dt_utc = datetime.datetime.fromisoformat(mesaj['created_at'].replace("Z", "+00:00")).replace(tzinfo=datetime.timezone.utc)
                        olusturulma_dt_tr = olusturulma_dt_utc + datetime.timedelta(hours=3)
                        olusturulma_str = olusturulma_dt_tr.strftime('%d.%m.%Y %H:%M')
                    except ValueError:
                        olusturulma_str = f"{mesaj['created_at']} (Format Hatalı)"
                
                tekrar_str = f"{'Sonsuz' if mesaj['repeat_count'] == 0 else mesaj['repeat_count']} kez"
                
                embed.add_field(
                    name="⚙️ Mesaj Ayarları",
                    value=(
                        f"**Durum:** {status_emoji} {'Aktif' if mesaj['active'] else 'Pasif'}\n"
                        f"**Oluşturan:** <@{mesaj['created_by']}>\n"
                        f"**Kanal:** <#{mesaj['channel_id']}> (#{mesaj['channel_name']})\n"
                        f"**Oluşturulma:** {olusturulma_str}\n"
                        f"**Zamanlama:** {zaman_bilgisi}\n"
                        f"**Gönderim:** {mesaj['sent_count']}/{mesaj['repeat_count']} kez\n"
                        f"**Son Gönderim:** {son_gonderim_str}"
                    ),
                    inline=False
                )
                
                # Mesaj içeriği
                embed.add_field(
                    name="📄 Mesaj İçeriği",
                    value=mesaj['message_content'][:1024] + ("..." if len(mesaj['message_content']) > 1024 else ""),
                    inline=False
                )
                
                # Embed bilgisi varsa
                if mesaj.get('embed_data'):
                    embed.add_field(
                        name="🖼️ Embed Bilgisi",
                        value="Bu mesaj ile birlikte bir embed gönderilecek.",
                        inline=False
                    )
                
                # Kontrol butonları
                view = MesajDetayView(self.cog, self.user, mesaj)
                
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                view.message = await interaction.original_response()
            
            except Exception as e:
                await interaction.response.send_message(
                    f"Mesaj bilgileri alınırken bir hata oluştu: {str(e)}",
                    ephemeral=True
                )
                
        except ValueError:
            await interaction.response.send_message("Lütfen geçerli bir mesaj ID'si girin.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Bir hata oluştu: {str(e)}", ephemeral=True)

# Mesaj detay görünümü
class MesajDetayView(discord.ui.View):
    def __init__(self, cog, user, mesaj):
        super().__init__(timeout=300)  # 5 dakika timeout
        self.cog = cog
        self.user = user
        self.mesaj = mesaj
        self.message = None # Orijinal mesajı saklamak için
    
    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.NotFound: # Mesaj silinmiş olabilir
                pass
            except discord.HTTPException as e: # Diğer olası hatalar
                print(f"MesajDetayView on_timeout edit error: {e}")
                pass
    
    @discord.ui.button(label="Düzenle", style=discord.ButtonStyle.blurple, emoji="✏️", row=0)
    async def duzenle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Düzenleme butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Kullanıcı sadece kendi oluşturduğu mesajları düzenleyebilir
        # Admin ve üstü roller herhangi bir mesajı düzenleyebilir
        is_admin = interaction.user.guild_permissions.administrator
        is_owner = self.mesaj['created_by'] == interaction.user.id
        
        if not is_admin and not is_owner:
            return await interaction.response.send_message(
                "Bu mesajı düzenlemek için yetkiniz yok. Sadece kendi oluşturduğunuz mesajları düzenleyebilirsiniz.",
                ephemeral=True
            )
        
        # Mesaj düzenleme modalını göster
        await interaction.response.send_modal(OtomatikMesajDuzenleModal(self.cog, self.user, self.mesaj))
    

    
    @discord.ui.button(label="Geri Dön", style=discord.ButtonStyle.secondary, emoji="◀️", row=1)
    async def geri_don_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Geri dön butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Otomatik mesajlar menüsüne dön
        view = OtomatikMesajlarView(self.cog, self.user)
        embed = discord.Embed(
            title="⏱️ Otomatik Mesajlar",
            description="Otomatik mesajlar menüsüne hoş geldiniz. Bu menüden belirli kanallara belirli zamanlarda otomatik mesaj gönderme ayarlarını yapabilirsiniz.",
            color=0x3498db
        )
        await interaction.response.edit_message(embed=embed, view=view)

# Mesaj silme onay görünümü
class MesajSilOnayView(discord.ui.View):
    def __init__(self, cog, user, mesaj):
        super().__init__(timeout=60)  # 1 dakika timeout
        self.cog = cog
        self.user = user
        self.mesaj = mesaj
        self.message = None # Orijinal mesajı saklamak için
    
    async def on_timeout(self):
        # if self.message: # Bu kontrol kaldırıldı, ephemeral mesajlar için message düzenlenemeyebilir.
        for item in self.children:
            item.disabled = True
        # Ephemeral mesajlar için, view'ı içeren mesajı editlemek her zaman mümkün olmayabilir.
        # Özellikle followup mesajı ise. Butonları disable etmek genellikle yeterlidir.
        # Eğer orijinal mesajı (view'ı ilk gönderen) düzenlemek gerekiyorsa, o mesajın referansı doğru tutulmalı.
        # MesajSilOnayView'da followup.send kullanıldığı için, bu view'a ait mesaj ephemeral bir followup mesajıdır.
        # Bu mesajı editlemeye çalışmak yerine sadece butonları disable etmek daha güvenli.
        # Eğer ana mesajı (MesajDetayView'ı içeren) editlemek gerekirse, o view'ın on_timeout'u bunu yapmalı.
        if self.message: # Yeniden eklendi, ancak dikkatli kullanılmalı.
            try:
                # Bu satır muhtemelen hata verecektir çünkü self.message MesajSilOnayView için yanlış ayarlanmış olabilir
                # veya ephemeral followup mesajı düzenlenemeyebilir.
                # await self.message.edit(view=self) 
                # Şimdilik sadece loglayalım ve butonların disable olmasını umalım.
                print(f"MesajSilOnayView timed out. Buttons disabled. Associated message: {self.message}")
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                print(f"MesajSilOnayView on_timeout edit error: {e}")
                pass
    
    @discord.ui.button(label="Evet, Sil", style=discord.ButtonStyle.danger, emoji="✓", row=0)
    async def onayla_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Onay butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # İşlem başlıyor bilgisi
        await interaction.response.defer(ephemeral=True)
        
        # Mesajı sil
        db = await get_db()
        deleted = await db.delete_scheduled_message(self.mesaj['id'])
        
        if deleted:
            embed = discord.Embed(
                title="✅ Otomatik Mesaj Silindi",
                description=f"ID'si `{self.mesaj['id']}` olan otomatik mesaj başarıyla silindi.",
                color=discord.Color.green()
            )
            
            # Log kanalına bildirim gönder
            log_channel = discord.utils.get(interaction.guild.text_channels, name="yetkili-panel-log")
            if log_channel:
                log_embed = discord.Embed(
                    title="🗑️ Otomatik Mesaj Silindi",
                    description=f"**{interaction.user.name}** tarafından bir otomatik mesaj silindi.",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
                )
                
                log_embed.add_field(
                    name="Mesaj Bilgileri",
                    value=(
                        f"**Mesaj ID:** `{self.mesaj['id']}`\n"
                        f"**Kanal:** <#{self.mesaj['channel_id']}>\n"
                        f"**Oluşturan:** <@{self.mesaj['created_by']}>"
                    ),
                    inline=False
                )
                
                log_embed.set_footer(text=f"Silen Kullanıcı ID: {interaction.user.id}")
                await log_channel.send(embed=log_embed)
            
            # Ana menüye dönüş butonu
            view = OtomatikMesajlarView(self.cog, self.user)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(
                content=f"Mesaj silinirken bir hata oluştu.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Hayır, İptal", style=discord.ButtonStyle.secondary, emoji="✗", row=0)
    async def iptal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """İptal butonuna tıklandığında"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # İşlem başlıyor bilgisi
        await interaction.response.defer(ephemeral=True)
        
        # Silme işlemini iptal et
        await interaction.followup.send(
            content="Mesaj silme işlemi iptal edildi.",
            ephemeral=True
        )


class KullaniciNotlariView(discord.ui.View):
    """Kullanıcı notları yönetim view'ı"""
    
    def __init__(self, cog, user):
        super().__init__(timeout=600)
        self.cog = cog
        self.user = user
        self.current_page = 0
        self.notes_per_page = 5
        
    async def show_notes_panel(self, interaction: discord.Interaction):
        """Ana notlar panelini gösterir"""
        embed = await self.create_notes_overview_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def create_notes_overview_embed(self, guild):
        """Notlar genel bakış embed'ini oluşturur"""
        db = await get_db()
        stats = await db.get_notes_stats(guild.id)
        recent_notes = await db.get_all_user_notes(guild.id, limit=self.notes_per_page, offset=0)
        
        embed = discord.Embed(
            title="📝 Kullanıcı Notları Paneli",
            description="Sunucudaki kullanıcı notlarını yönetebilirsiniz.",
            color=0x3498db,
            timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
        )
        
        # İstatistikler
        embed.add_field(
            name="📊 Not İstatistikleri",
            value=f"**Toplam Not Sayısı:** {stats['total_notes']:,}\n"
                  f"**Notlu Kullanıcı Sayısı:** {stats['unique_users']:,}\n"
                  f"**En Aktif Admin:** {stats['top_admin']} ({stats['top_admin_count']} not)\n"
                  f"**Bu Hafta Eklenen:** {stats['weekly_notes']:,}",
            inline=False
        )
        
        # Son eklenen notlar
        if recent_notes:
            notes_text = ""
            for note in recent_notes:
                created_date = datetime.datetime.fromisoformat(note['created_at']).strftime('%d.%m %H:%M')
                content_preview = note['note_content'][:80] + "..." if len(note['note_content']) > 80 else note['note_content']
                notes_text += f"**#{note['id']}** - <@{note['user_id']}> ({note['username']})\n"
                notes_text += f"└ {content_preview}\n"
                notes_text += f"└ *{note['created_by_username']} - {created_date}*\n\n"
            
            embed.add_field(
                name="📋 Son Eklenen Notlar",
                value=notes_text if notes_text else "Henüz not bulunmuyor.",
                inline=False
            )
        
        embed.set_footer(text=f"Sayfa {self.current_page + 1} • Kullanım: Aşağıdaki butonları kullanın")
        return embed
    
    @discord.ui.button(label="🔍 Not Ara", style=discord.ButtonStyle.blurple, emoji="🔍", row=0)
    async def search_notes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Not arama modalını açar"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        modal = SearchNotesModal(self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="👤 Kullanıcıya Göre Filtrele", style=discord.ButtonStyle.blurple, emoji="👤", row=0)
    async def filter_user_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Kullanıcıya göre filtreleme modalını açar"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        modal = FilterUserModal(self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📊 Detaylı İstatistikler", style=discord.ButtonStyle.secondary, emoji="📊", row=1)
    async def detailed_stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Detaylı istatistikleri gösterir"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        await self.show_detailed_stats(interaction)
    
    @discord.ui.button(label="⬅️ Önceki", style=discord.ButtonStyle.secondary, emoji="⬅️", row=1)
    async def previous_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Önceki sayfaya gider"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        if self.current_page > 0:
            self.current_page -= 1
            embed = await self.create_notes_overview_embed(interaction.guild)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Bu ilk sayfa!", ephemeral=True)
    
    @discord.ui.button(label="➡️ Sonraki", style=discord.ButtonStyle.secondary, emoji="➡️", row=1)
    async def next_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Sonraki sayfaya gider"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        db = await get_db()
        total_notes = await db.get_total_notes_count(interaction.guild.id)
        max_pages = (total_notes + self.notes_per_page - 1) // self.notes_per_page
        
        if self.current_page < max_pages - 1:
            self.current_page += 1
            embed = await self.create_notes_overview_embed(interaction.guild)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Bu son sayfa!", ephemeral=True)
    
    @discord.ui.button(label="◀️ Geri Dön", style=discord.ButtonStyle.danger, emoji="◀️", row=2)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ana panele dön"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Ana panele dön
        main_view = YetkiliPanelView(self.cog, self.user)
        embed = discord.Embed(
            title="🛡️ HydRaboN Yetkili Paneli",
            description=(
                "Hoş geldiniz! Bu panel üzerinden yetkili işlemlerini gerçekleştirebilirsiniz.\n\n"
                "Lütfen yapmak istediğiniz işlemi aşağıdaki butonlardan seçin."
            ),
            color=0x00ff00,
            timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
        )
        embed.set_footer(text=f"Kullanıcı: {self.user.name}")
        await interaction.response.edit_message(embed=embed, view=main_view)
    
    async def show_detailed_stats(self, interaction: discord.Interaction):
        """Detaylı istatistikleri gösterir"""
        db = await get_db()
        stats = await db.get_notes_stats(interaction.guild.id)
        
        # En fazla notu olan kullanıcıları al
        async with db.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT username, COUNT(*) as note_count 
            FROM user_notes 
            WHERE guild_id = ? 
            GROUP BY user_id, username 
            ORDER BY note_count DESC 
            LIMIT 5
            ''', (interaction.guild.id,))
            
            top_users = []
            for row in await cursor.fetchall():
                top_users.append(f"**{row[0]}:** {row[1]} not")
        
        # En aktif admin'leri al
        async with db.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT created_by_username, COUNT(*) as note_count 
            FROM user_notes 
            WHERE guild_id = ? 
            GROUP BY created_by_username 
            ORDER BY note_count DESC 
            LIMIT 5
            ''', (interaction.guild.id,))
            
            top_admins = []
            for row in await cursor.fetchall():
                top_admins.append(f"**{row[0]}:** {row[1]} not")
        
        embed = discord.Embed(
            title="📊 Detaylı Not İstatistikleri",
            color=0x2ecc71,
            timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
        )
        
        embed.add_field(
            name="📈 Genel İstatistikler",
            value=f"**Toplam Not:** {stats['total_notes']:,}\n"
                  f"**Notlu Kullanıcı:** {stats['unique_users']:,}\n"
                  f"**Bu Hafta:** {stats['weekly_notes']:,}",
            inline=True
        )
        
        embed.add_field(
            name="👥 En Fazla Notu Olan Kullanıcılar",
            value="\n".join(top_users[:5]) if top_users else "Veri bulunamadı",
            inline=True
        )
        
        embed.add_field(
            name="👑 En Aktif Admin'ler",
            value="\n".join(top_admins[:5]) if top_admins else "Veri bulunamadı",
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class SearchNotesModal(discord.ui.Modal, title="Not Arama"):
    """Not arama modal'ı"""
    
    def __init__(self, notes_view):
        super().__init__()
        self.notes_view = notes_view
        
    search_term = discord.ui.TextInput(
        label="Arama Terimi",
        placeholder="Kullanıcı adı veya not içeriği...",
        max_length=100,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        db = await get_db()
        notes = await db.search_user_notes(self.search_term.value, interaction.guild.id, limit=10)
        
        if not notes:
            await interaction.response.send_message(
                f"🔍 `{self.search_term.value}` için sonuç bulunamadı.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"🔍 Arama Sonuçları: '{self.search_term.value}'",
            description=f"**Bulunan Not Sayısı:** {len(notes)}",
            color=0x3498db,
            timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
        )
        
        for note in notes[:5]:  # İlk 5 sonucu göster
            created_date = datetime.datetime.fromisoformat(note['created_at']).strftime('%d.%m.%Y %H:%M')
            content_preview = note['note_content'][:150] + "..." if len(note['note_content']) > 150 else note['note_content']
            
            embed.add_field(
                name=f"Not #{note['id']} - {note['username']}",
                value=f"**İçerik:** {content_preview}\n"
                      f"**Ekleyen:** {note['created_by_username']}\n"
                      f"**Tarih:** {created_date}",
                inline=False
            )
        
        if len(notes) > 5:
            embed.set_footer(text=f"+ {len(notes) - 5} adet daha sonuç bulundu")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class FilterUserModal(discord.ui.Modal, title="Kullanıcıya Göre Filtrele"):
    """Kullanıcıya göre filtreleme modal'ı"""
    
    def __init__(self, notes_view):
        super().__init__()
        self.notes_view = notes_view
        
    user_input = discord.ui.TextInput(
        label="Kullanıcı ID veya Kullanıcı Adı",
        placeholder="123456789012345678 veya kullanıcı_adı",
        max_length=100,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.user_input.value.strip()
        
        # ID olarak denemeyi dene
        user_id = None
        if user_input.isdigit():
            user_id = int(user_input)
        else:
            # Kullanıcı adına göre ara
            db = await get_db()
            async with db.connection.cursor() as cursor:
                await cursor.execute('''
                SELECT DISTINCT user_id FROM user_notes 
                WHERE guild_id = ? AND username LIKE ?
                ''', (interaction.guild.id, f"%{user_input}%"))
                
                results = await cursor.fetchall()
                if results:
                    user_id = results[0][0]  # İlk sonucu al
        
        if not user_id:
            await interaction.response.send_message(
                f"❌ `{user_input}` kullanıcısı bulunamadı.",
                ephemeral=True
            )
            return
        
        # Kullanıcının notlarını getir
        db = await get_db()
        notes = await db.get_user_notes(user_id, interaction.guild.id, limit=10)
        
        if not notes:
            await interaction.response.send_message(
                f"📝 Bu kullanıcı hakkında not bulunamadı.",
                ephemeral=True
            )
            return
        
        # Kullanıcı bilgisini al
        user = interaction.guild.get_member(user_id)
        display_name = user.display_name if user else notes[0]['username']
        
        embed = discord.Embed(
            title=f"📝 {display_name} - Kullanıcı Notları",
            description=f"**Kullanıcı ID:** `{user_id}`\n**Toplam Not:** {len(notes)}",
            color=0x3498db,
            timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
        )
        
        for note in notes[:5]:  # İlk 5 notu göster
            created_date = datetime.datetime.fromisoformat(note['created_at']).strftime('%d.%m.%Y %H:%M')
            content_preview = note['note_content'][:200] + "..." if len(note['note_content']) > 200 else note['note_content']
            
            embed.add_field(
                name=f"Not #{note['id']} - {created_date}",
                value=f"**İçerik:** {content_preview}\n"
                      f"**Ekleyen:** {note['created_by_username']}",
                inline=False
            )
        
        if len(notes) > 5:
            embed.set_footer(text=f"+ {len(notes) - 5} adet daha not bulunuyor")
            
        if user:
            embed.set_thumbnail(url=user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class YetkiliPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Otomatik mesaj gönderme işlemini başlat
        self.message_check_task = None
    
    async def cog_load(self):
        """Cog yüklendiğinde çalışan metod"""
        # Otomatik mesaj kontrol görevini başlat
        self.message_check_task = self.bot.loop.create_task(self.check_scheduled_messages())
    
    async def cog_unload(self):
        """Cog kaldırıldığında çalışan metod"""
        # Otomatik mesaj kontrol görevini iptal et
        if self.message_check_task:
            self.message_check_task.cancel()
    
    @app_commands.command(
        name="yetkili-panel", 
        description="Yetkili işlemlerini yapabileceğiniz paneli açar"
    )
    @guild_only()
    async def yetkili_panel(self, interaction: discord.Interaction):
        """Yetkili panelini açar"""
        # Kullanıcının yetkili rollerine sahip olup olmadığını kontrol et
        yetkili_mi = False
        for rol_id in YETKILI_ROLLERI.values():
            if any(r.id == rol_id for r in interaction.user.roles):
                yetkili_mi = True
                break
                
        if not yetkili_mi:
            return await interaction.response.send_message(
                "Bu komutu kullanabilmek için yetkili rolüne sahip olmanız gerekiyor!", 
                ephemeral=True
            )
        
        await self.show_main_panel(interaction)
    
    async def list_scheduled_messages(self, interaction: discord.Interaction):
        """Tüm zamanlanmış mesajları listeler ve mevcut mesajı günceller."""
        # Defer immediately to prevent interaction timeout before slow operations
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        # else: if already responded, this interaction might be stale.
        # For a button click, it shouldn't be done yet.

        try:
            # Check if interaction.message (the message with the button) is available
            if not interaction.message:
                print("Hata: list_scheduled_messages içinde interaction.message None geldi after defer.")
                # We have deferred, so use followup to send a message
                await interaction.followup.send("Bir hata oluştu: Orijinal mesaj referansı bulunamadı.", ephemeral=True)
                return

            db = await get_db()
            messages = await db.get_all_scheduled_messages()

            if not messages:
                embed = discord.Embed(
                    title="📋 Zamanlanmış Mesajlar",
                    description="Şu anda tanımlanmış bir otomatik mesaj bulunmuyor.",
                    color=0x3498db
                )
            else:
                embed = discord.Embed(
                    title="📋 Zamanlanmış Mesajlar",
                    description=f"Toplam **{len(messages)}** adet zamanlanmış mesaj bulundu:",
                    color=0x3498db
                )
                for msg in messages:
                    status_emoji = "✅" if msg.get('active', False) else "❌"
                    schedule_data = msg.get('schedule_data', {})
                    zaman_bilgisi_parts = []
                    if schedule_data.get("days", 0) > 0:
                        zaman_bilgisi_parts.append(f"{schedule_data['days']} gün")
                    if schedule_data.get("hours", 0) > 0:
                        zaman_bilgisi_parts.append(f"{schedule_data['hours']} saat")
                    if schedule_data.get("minutes", 0) > 0:
                        zaman_bilgisi_parts.append(f"{schedule_data['minutes']} dakika")
                    zaman_bilgisi = ", ".join(zaman_bilgisi_parts) + " aralıkla" if zaman_bilgisi_parts else "Belirtilmemiş"

                    last_sent_str_display = "Henüz gönderilmedi"
                    if msg['last_sent']:
                        try:
                            last_sent_dt_utc = datetime.datetime.fromisoformat(msg['last_sent'].replace('Z', '+00:00')).replace(tzinfo=datetime.timezone.utc)
                            last_sent_dt_tr = last_sent_dt_utc + datetime.timedelta(hours=3)
                            last_sent_str_display = f"Son: {last_sent_dt_tr.strftime('%d.%m.%Y %H:%M')} (UTC+3)"
                        except ValueError:
                            last_sent_str_display = f"Son: {msg['last_sent']} (Format Hatalı)"
                    
                    repeat_count_val = msg.get('repeat_count', 1)
                    tekrar_str = f"{'Sonsuz' if repeat_count_val == 0 else repeat_count_val} kez"

                    embed.add_field(
                        name=f"{status_emoji} Mesaj #{msg['id']}",
                        value=(
                            f"**Kanal:** <#{msg['channel_id']}>\n"
                            f"**Durum:** {'Aktif' if msg.get('active', False) else 'Pasif'}\n"
                            f"**Gönderim:** {msg.get('sent_count',0)}/{tekrar_str}\n"
                            f"**Zamanlama:** {zaman_bilgisi}\n"
                            f"**{last_sent_str_display}**"
                        ),
                        inline=True
                    )
                embed.set_footer(text="Mesaj içeriğini görmek, düzenlemek veya silmek için ilgili butonları kullanın.")
            
            new_view = OtomatikMesajlarView(self, interaction.user)
            
            # Edit the original message using the deferred interaction
            await interaction.edit_original_response(embed=embed, view=new_view)
            
            # Get the message object after editing and assign it to the view
            # This is useful for the view's on_timeout or other internal logic
            edited_message = await interaction.original_response()
            new_view.message = edited_message

            # The defer was moved to the beginning, so this is no longer needed here.
            # if not interaction.response.is_done():
            #    await interaction.response.defer(ephemeral=True)
            
        except discord.NotFound as e: # Specifically catch NotFound (10008 Unknown Message)
            print(f"NotFound error in list_scheduled_messages (likely from edit_original_response): {e.code} - {e.text}")
            error_embed = discord.Embed(
                title="❌ Hata",
                description=f"Mesaj güncellenemedi. Orijinal mesaj bulunamadı veya zaman aşımına uğramış olabilir (Hata Kodu: {e.code}).",
                color=discord.Color.red()
            )
            try:
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            except discord.HTTPException as he:
                print(f"Failed to send followup after NotFound: {he}")
        except Exception as e:
            print(f"Error in list_scheduled_messages: {e}")
            error_embed = discord.Embed(
                title="❌ Hata",
                description=f"Zamanlanmış mesajlar listelenirken bir hata oluştu: {str(e)}",
                color=discord.Color.red()
            )
            # Since we deferred, we must use followup.send for error messages
            try:
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            except discord.HTTPException as he:
                 print(f"Failed to send followup for generic error: {he}")
    
    async def check_scheduled_messages(self):
        await self.bot.wait_until_ready()
        # Scheduled message checker started
        while not self.bot.is_closed():
            try:
                db = await get_db()
                active_messages = await db.get_all_scheduled_messages(active_only=True)
                
                for message_data in active_messages:
                    if await self.should_send_message(message_data):
                        await self.send_scheduled_message(message_data)
                
            except Exception as e:
                print(f"Error in check_scheduled_messages loop: {str(e)}")
            
            await asyncio.sleep(60) # Her dakika kontrol et
    
    async def should_send_message(self, message_data: dict) -> bool:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)

            # Tekrar sayısı kontrolü (0 sonsuz demek)
            if message_data.get('repeat_count', 1) != 0 and message_data.get('sent_count', 0) >= message_data.get('repeat_count', 1):
                # print(f"Message ID {message_data['id']} reached repeat count. Deactivating.")
                # db = await get_db()
                # await db.update_scheduled_message(message_id=message_data['id'], active=False)
                # Bu kontrol send_scheduled_message içinde yapılıyor, burada sadece gönderim zamanını kontrol etmeliyiz.
                return False # Gönderim hakkı dolmuşsa gönderme.

            if not message_data['last_sent']:
                # İlk gönderimse, oluşturulma zamanından bu yana en az bir interval geçmiş mi diye bakılabilir
                # veya direkt gönderilebilir. Şimdilik ilk gönderimi uygun sayalım.
                # print(f"Message ID {message_data['id']} is new, eligible for sending.")
                return True

            last_sent_dt = datetime.datetime.fromisoformat(message_data['last_sent'].replace('Z', '+00:00')).replace(tzinfo=datetime.timezone.utc)
            
            schedule = message_data.get('schedule_data', {})
            interval_days = schedule.get('days', 0)
            interval_hours = schedule.get('hours', 0)
            interval_minutes = schedule.get('minutes', 0)

            if interval_days == 0 and interval_hours == 0 and interval_minutes == 0:
                # print(f"Message ID {message_data['id']} has no valid interval. Skipping.")
                return False # Geçersiz aralık

            # Bir sonraki gönderim zamanını hesapla
            # timedelta saniye bazlı çalıştığı için toplam saniyeyi hesaplayıp eklemek daha doğru olabilir
            # ya da dateutil.relativedelta gibi bir kütüphane kullanılabilir daha karmaşık aralıklar için.
            # Şimdilik basit timedelta ile devam edelim.
            
            # Eğer aralıklar çok büyükse (örn. aylar), timedelta limitasyonları olabilir.
            # Bu bot için gün/saat/dakika yeterli olacaktır.
            next_send_time = last_sent_dt + datetime.timedelta(
                days=interval_days, 
                hours=interval_hours, 
                minutes=interval_minutes
            )
            
            # print(f"Message ID {message_data['id']}: Now: {now_utc}, Last Sent: {last_sent_dt}, Next Send: {next_send_time}")
            return now_utc >= next_send_time

        except Exception as e:
            print(f"Error in should_send_message for message ID {message_data.get('id')}: {e}")
            return False
    
    async def send_scheduled_message(self, message_data: dict):
        try:
            channel = self.bot.get_channel(message_data['channel_id'])
            if not channel:
                print(f"Scheduled message channel ID {message_data['channel_id']} not found for message ID {message_data['id']}. Deactivating.")
                db = await get_db()
                await db.update_scheduled_message(message_id=message_data['id'], active=False)
                return

            content = message_data.get('message_content')
            embed_to_send = None
            raw_embed_data = message_data.get('embed_data')

            if raw_embed_data: # Bu artık dict olmalı
                try:
                    # Embed.from_dict() kullanmak daha güvenli
                    # Temel alanların varlığını kontrol edelim (title veya description en azından olmalı)
                    if 'title' in raw_embed_data or 'description' in raw_embed_data:
                         embed_to_send = discord.Embed.from_dict(raw_embed_data)
                    else:
                        print(f"Embed data for message ID {message_data['id']} is present but lacks title/description. Not sending embed.")
                except Exception as e:
                    print(f"Error creating embed from dict for message ID {message_data['id']}: {e}. Data: {raw_embed_data}")
            
            # Eğer content None ise ve embed de oluşturulamadıysa boş mesaj göndermemek için kontrol
            if not content and not embed_to_send:
                print(f"Message ID {message_data['id']} has no content and no valid embed. Deactivating.")
                db = await get_db()
                await db.update_scheduled_message(message_id=message_data['id'], active=False)
                return

            # Önceki mesajı silme işlemi
            previous_message_id = message_data.get('last_message_id')
            if previous_message_id:
                try:
                    # Önceki mesajı bul ve sil
                    try:
                        previous_message = await channel.fetch_message(int(previous_message_id))
                        await previous_message.delete()
                    except discord.NotFound:
                        print(f"Previous message ID {previous_message_id} not found for deletion")
                    except discord.Forbidden:
                        print(f"No permission to delete previous message ID {previous_message_id}")
                    except Exception as e:
                        print(f"Error deleting previous message ID {previous_message_id}: {e}")
                except Exception as e:
                    print(f"Error handling previous message deletion: {e}")

            # Yeni mesajı gönder
            new_message = await channel.send(content=content if content else None, embed=embed_to_send)

            # Veritabanını güncelle - son mesaj ID'sini ve sent_count'u artır
            db = await get_db()
            await db.update_message_sent(
                message_id=message_data['id'], 
                last_message_id=str(new_message.id)
            )

        except discord.Forbidden:
            print(f"Forbidden (no permission) to send message ID {message_data['id']} to channel {message_data.get('channel_id')}. Deactivating.")
            db = await get_db()
            await db.update_scheduled_message(message_id=message_data['id'], active=False)
        except discord.HTTPException as e:
            print(f"HTTPException while sending message ID {message_data['id']}: {e}. Status: {e.status}, Code: {e.code}, Text: {e.text}")
            # 40005: Request body is too large. Embed veya mesaj içeriği çok uzun olabilir.
            # 50001: Missing Access (Botun kanala erişimi yok)
            # 50013: Missing Permissions (Botun kanalda mesaj gönderme izni yok)
            # 10003: Unknown Channel (Kanal silinmiş olabilir)
            if e.code == 10003 or e.status == 404: # Unknown channel or generic not found
                 print(f"Deactivating message ID {message_data['id']} due to channel not found (HTTP {e.status}).")
                 db = await get_db()
                 await db.update_scheduled_message(message_id=message_data['id'], active=False)
            # Diğer HTTP hatalarında mesajı pasif yapmayabiliriz, belki geçici bir sorundur.
        except Exception as e:
            print(f"Generic error sending/updating scheduled message ID {message_data['id']}: {e}")

    async def show_main_panel(self, interaction: discord.Interaction):
        """Ana yetkili panelini gösterir"""
        embed = discord.Embed(
            title="🛡️ HydRaboN Yetkili Paneli",
            description=(
                "Hoş geldiniz! Bu panel üzerinden yetkili işlemlerini gerçekleştirebilirsiniz.\n\n"
                "Lütfen yapmak istediğiniz işlemi aşağıdaki butonlardan seçin."
            ),
            color=0x3498db
        )
        
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        view = YetkiliPanelView(self, interaction.user)
        
        if interaction.response.is_done():
            # İlk mesaj gönderilmiş, düzenleme yapalım
            await interaction.edit_original_response(embed=embed, view=view)
            message = await interaction.original_response()
        else:
            # İlk mesaj henüz gönderilmemiş
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            message = await interaction.original_response()
        
        view.message = message
    
    async def show_stats(self, interaction: discord.Interaction):
        """Sunucu istatistiklerini gösterir"""
        guild = interaction.guild
        
        # Temel istatistikleri hesapla
        total_members = guild.member_count
        online_members = len([m for m in guild.members if m.status != discord.Status.offline])
        total_channels = len(guild.channels)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        category_channels = len(guild.categories)
        total_roles = len(guild.roles)
        
        # Yetkili sayısını hesapla
        yetkili_sayisi = 0
        for rol_id in YETKILI_ROLLERI.values():
            rol = guild.get_role(rol_id)
            if rol:
                yetkili_sayisi += len(rol.members)
        
        # Sunucu yaşını hesapla
        created_days = (datetime.datetime.now(pytz.timezone('Europe/Istanbul')) - guild.created_at.astimezone(pytz.timezone('Europe/Istanbul'))).days
        
        # Embed oluştur
        embed = discord.Embed(
            title="📊 Sunucu İstatistikleri",
            description=f"**{guild.name}** sunucusunun güncel istatistikleri",
            color=0x3498db
        )
        
        # Genel bilgiler
        embed.add_field(
            name="👥 Üye İstatistikleri",
            value=(
                f"**Toplam Üye:** {total_members}\n"
                f"**Çevrimiçi Üye:** {online_members}\n"
                f"**Yetkili Sayısı:** {yetkili_sayisi}"
            ),
            inline=True
        )
        
        # Kanal istatistikleri
        embed.add_field(
            name="💬 Kanal İstatistikleri", 
            value=(
                f"**Toplam Kanal:** {total_channels}\n"
                f"**Metin Kanalı:** {text_channels}\n"
                f"**Ses Kanalı:** {voice_channels}\n"
                f"**Kategori:** {category_channels}"
            ),
            inline=True
        )
        
        # Genel sunucu bilgileri
        embed.add_field(
            name="ℹ️ Sunucu Bilgileri",
            value=(
                f"**Kuruluş Tarihi:** {guild.created_at.strftime('%d/%m/%Y')}\n"
                f"**Sunucu Yaşı:** {created_days} gün\n"
                f"**Rol Sayısı:** {total_roles}"
            ),
            inline=False
        )
        
        # Veritabanından başvuru istatistiklerini getir
        try:
            db = await get_db()
            stats = await db.get_application_stats()
            
            # Başvuru istatistikleri
            status_counts = stats.get('status_counts', {})
            approved = status_counts.get('approved', 0)
            rejected = status_counts.get('rejected', 0)
            pending = status_counts.get('pending', 0)
            cancelled = status_counts.get('cancelled', 0)
            
            embed.add_field(
                name="📝 Başvuru İstatistikleri",
                value=(
                    f"**Toplam Başvuru:** {stats['total']}\n"
                    f"**Son 7 Gün:** {stats['recent']}\n"
                    f"**Bekleyen:** {pending}\n"
                    f"**Onaylanan:** {approved}\n"
                    f"**Reddedilen:** {rejected}\n"
                    f"**İptal Edilen:** {cancelled}"
                ),
                inline=False
            )
        except Exception as e:
            embed.add_field(
                name="📝 Başvuru İstatistikleri",
                value=f"Başvuru istatistikleri alınamadı: {str(e)}",
                inline=False
            )
        
        # Otomatik Mesaj İstatistikleri
        try:
            db = await get_db()
            messages = await db.get_all_scheduled_messages()
            
            active_count = len([m for m in messages if m['active']])
            total_sent = sum(m['sent_count'] for m in messages)
            
            embed.add_field(
                name="⏱️ Otomatik Mesaj İstatistikleri",
                value=(
                    f"**Toplam Mesaj:** {len(messages)}\n"
                    f"**Aktif Mesaj:** {active_count}\n"
                    f"**Toplam Gönderim:** {total_sent}"
                ),
                inline=False
            )
        except Exception as e:
            embed.add_field(
                name="⏱️ Otomatik Mesaj İstatistikleri",
                value=f"Otomatik mesaj istatistikleri alınamadı: {str(e)}",
                inline=False
            )
        
        # Veritabanı Boyut İstatistikleri
        try:
            db = await get_db()
            size_info = await db.get_database_size_info()
            
            embed.add_field(
                name="💾 Veritabanı İstatistikleri",
                value=(
                    f"**Bump Kayıtları:** {size_info['bump_logs_count']:,}\n"
                    f"**Başvuru Kayıtları:** {size_info['applications_count']:,}\n"
                    f"**Spam Kayıtları:** {size_info['spam_logs_count']:,}\n"
                    f"**Üye Giriş/Çıkış:** {size_info['member_logs_count']:,}\n"
                    f"**Tahmini Boyut:** {size_info['estimated_size_human']}\n"
                    f"**Bump Boyutu:** {size_info['estimated_bump_size_mb']} MB"
                ),
                inline=False
            )
        except Exception as e:
            embed.add_field(
                name="💾 Veritabanı İstatistikleri",
                value=f"Veritabanı boyut bilgileri alınamadı: {str(e)}",
                inline=False
            )
        
        # Thumbnail ve footer
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(text=f"{guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        # Geri dönüş butonu içeren view
        view = YetkiliPanelView(self, interaction.user)
        
        # Eğer interaction zaten yanıtlandıysa edit_message kullan
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)
        
        view.message = await interaction.original_response()

    # Yetki yükseltme işlemi
    async def yetki_yukselt(self, interaction, hedef_kullanici_id, sebep, yetkili_rol_id):
        """Belirtilen kullanıcının yetkisini bir seviye yükseltir"""
        guild = interaction.guild
        yetkili = interaction.user
        
        try:
            # Hedef kullanıcıyı bul
            hedef_uye = await guild.fetch_member(hedef_kullanici_id)
            if not hedef_uye:
                return await interaction.followup.send(
                    "Belirtilen ID'ye sahip bir kullanıcı bulunamadı.", 
                    ephemeral=True
                )
            
            # Hedef kullanıcının yetkili olup olmadığını kontrol et
            hedef_yetkili_rol_id = None
            for rol_id in YETKILI_HIYERARSI:
                if any(r.id == rol_id for r in hedef_uye.roles):
                    hedef_yetkili_rol_id = rol_id
                    break
            
            if not hedef_yetkili_rol_id:
                return await interaction.followup.send(
                    f"{hedef_uye.mention} bir yetkili değil. Yetki yükseltme işlemi sadece yetkililere uygulanabilir.",
                    ephemeral=True
                )
            
            # Yetkili hiyerarşisinde kullanıcının ve hedefin konumlarını belirle
            yetkili_index = YETKILI_HIYERARSI.index(yetkili_rol_id)
            hedef_index = YETKILI_HIYERARSI.index(hedef_yetkili_rol_id)
            
            # Yetki kontrolü - kendi seviyesindeki ya da üstündeki birine işlem yapılamaz
            if hedef_index >= yetkili_index:
                return await interaction.followup.send(
                    f"Yetkinize eşit veya daha yüksek seviyedeki yetkililerin yetkilerini değiştiremezsiniz.",
                    ephemeral=True
                )
            
            # Kendisinden bir alt seviyeden daha alt seviyeye atama yapabilir mi kontrolü
            if hedef_index < yetkili_index - 1:
                yeni_index = hedef_index + 1
            else:
                # Bir alt seviyedekini ancak kendi seviyesine kadar getirebilir
                yeni_index = min(hedef_index + 1, yetkili_index)
            
            # Yeni rol bilgilerini al
            eski_rol = guild.get_role(YETKILI_HIYERARSI[hedef_index])
            yeni_rol = guild.get_role(YETKILI_HIYERARSI[yeni_index])
            
            # Eski rol ismini bul
            eski_rol_ismi = "Bilinmeyen Rol"
            yeni_rol_ismi = "Bilinmeyen Rol"
            for isim, rol_id in YETKILI_ROLLERI.items():
                if rol_id == eski_rol.id:
                    eski_rol_ismi = isim
                if rol_id == yeni_rol.id:
                    yeni_rol_ismi = isim
            
            # Rol değişikliğini yap
            await hedef_uye.remove_roles(eski_rol, reason=f"Yetki Yükseltme: {sebep}")
            await hedef_uye.add_roles(yeni_rol, reason=f"Yetki Yükseltme: {sebep}")
            # DB log: promoted
            try:
                db = await get_db()
                await db.add_staff_change(
                    guild_id=guild.id,
                    user_id=hedef_uye.id,
                    username=hedef_uye.name,
                    action='promoted',
                    actor_id=yetkili.id,
                    actor_username=yetkili.name,
                    old_role_id=eski_rol.id,
                    old_role_name=eski_rol_ismi,
                    new_role_id=yeni_rol.id,
                    new_role_name=yeni_rol_ismi,
                    reason=sebep
                )
            except Exception:
                pass
            
            # Başarılı işlem bildirimi
            embed = discord.Embed(
                title="✅ Yetki Yükseltme Başarılı",
                description=f"{hedef_uye.mention} kullanıcısının yetkisi başarıyla yükseltildi.",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
            )
            
            embed.add_field(
                name="Yetki Bilgileri",
                value=(
                    f"**Eski Yetki:** {eski_rol.mention} ({eski_rol_ismi})\n"
                    f"**Yeni Yetki:** {yeni_rol.mention} ({yeni_rol_ismi})"
                ),
                inline=False
            )
            
            embed.add_field(
                name="İşlem Detayları",
                value=(
                    f"**Yetkiyi Yükselten:** {yetkili.mention}\n"
                    f"**Sebep:** {sebep}"
                ),
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Log kanalına bildirim gönder
            log_kanali = discord.utils.get(guild.text_channels, name="yetkili-panel-log")
            if log_kanali:
                log_embed = discord.Embed(
                    title="🔼 Yetki Yükseltme",
                    description=f"{hedef_uye.mention} kullanıcısının yetkisi yükseltildi.",
                    color=discord.Color.gold(),
                    timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
                )
                
                log_embed.add_field(
                    name="Yetki Bilgileri", 
                    value=(
                        f"**Eski Yetki:** {eski_rol.mention} ({eski_rol_ismi})\n"
                        f"**Yeni Yetki:** {yeni_rol.mention} ({yeni_rol_ismi})"
                    ), 
                    inline=False
                )
                
                log_embed.add_field(
                    name="İşlem Detayları",
                    value=(
                        f"**Yetkiyi Yükselten:** {yetkili.mention} ({yetkili.id})\n"
                        f"**Yükseltilen Kullanıcı:** {hedef_uye.mention} ({hedef_uye.id})\n"
                        f"**Sebep:** {sebep}"
                    ),
                    inline=False
                )
                
                log_embed.set_thumbnail(url=hedef_uye.display_avatar.url)
                log_embed.set_footer(text=f"İşlem Zamanı: {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
                
                await log_kanali.send(embed=log_embed)
            
        except Exception as e:
            await interaction.followup.send(
                f"Yetki yükseltme işlemi sırasında bir hata oluştu: {str(e)}",
                ephemeral=True
            )
            
    # Yetki düşürme işlemi
    async def yetki_dusur(self, interaction, hedef_kullanici_id, sebep, yetkili_rol_id):
        """Belirtilen kullanıcının yetkisini bir seviye düşürür"""
        guild = interaction.guild
        yetkili = interaction.user
        
        try:
            # Hedef kullanıcıyı bul
            hedef_uye = await guild.fetch_member(hedef_kullanici_id)
            if not hedef_uye:
                return await interaction.followup.send(
                    "Belirtilen ID'ye sahip bir kullanıcı bulunamadı.", 
                    ephemeral=True
                )
            
            # Hedef kullanıcının yetkili olup olmadığını kontrol et
            hedef_yetkili_rol_id = None
            for rol_id in YETKILI_HIYERARSI:
                if any(r.id == rol_id for r in hedef_uye.roles):
                    hedef_yetkili_rol_id = rol_id
                    break
            
            if not hedef_yetkili_rol_id:
                return await interaction.followup.send(
                    f"{hedef_uye.mention} bir yetkili değil. Yetki düşürme işlemi sadece yetkililere uygulanabilir.",
                    ephemeral=True
                )
            
            # Yetkili hiyerarşisinde kullanıcının ve hedefin konumlarını belirle
            yetkili_index = YETKILI_HIYERARSI.index(yetkili_rol_id)
            hedef_index = YETKILI_HIYERARSI.index(hedef_yetkili_rol_id)
            
            # Yetki kontrolü - kendi seviyesindeki ya da üstündeki birine işlem yapılamaz
            if hedef_index >= yetkili_index:
                return await interaction.followup.send(
                    f"Yetkinize eşit veya daha yüksek seviyedeki yetkililerin yetkilerini değiştiremezsiniz.",
                    ephemeral=True
                )
            
            # En düşük yetkiden daha aşağı düşüremez
            if hedef_index == 0:
                return await interaction.followup.send(
                    f"{hedef_uye.mention} zaten en düşük yetkili seviyesinde. Daha fazla düşürülemez.",
                    ephemeral=True
                )
            
            # Yeni rol bilgilerini al
            eski_rol = guild.get_role(YETKILI_HIYERARSI[hedef_index])
            yeni_rol = guild.get_role(YETKILI_HIYERARSI[hedef_index - 1])
            
            # Rol isimlerini bul
            eski_rol_ismi = "Bilinmeyen Rol"
            yeni_rol_ismi = "Bilinmeyen Rol"
            for isim, rol_id in YETKILI_ROLLERI.items():
                if rol_id == eski_rol.id:
                    eski_rol_ismi = isim
                if rol_id == yeni_rol.id:
                    yeni_rol_ismi = isim
            
            # Rol değişikliğini yap
            await hedef_uye.remove_roles(eski_rol, reason=f"Yetki Düşürme: {sebep}")
            await hedef_uye.add_roles(yeni_rol, reason=f"Yetki Düşürme: {sebep}")
            # DB log: demoted
            try:
                db = await get_db()
                await db.add_staff_change(
                    guild_id=guild.id,
                    user_id=hedef_uye.id,
                    username=hedef_uye.name,
                    action='demoted',
                    actor_id=yetkili.id,
                    actor_username=yetkili.name,
                    old_role_id=eski_rol.id,
                    old_role_name=eski_rol_ismi,
                    new_role_id=yeni_rol.id,
                    new_role_name=yeni_rol_ismi,
                    reason=sebep
                )
            except Exception:
                pass
            
            # Başarılı işlem bildirimi
            embed = discord.Embed(
                title="✅ Yetki Düşürme Başarılı",
                description=f"{hedef_uye.mention} kullanıcısının yetkisi başarıyla düşürüldü.",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
            )
            
            embed.add_field(
                name="Yetki Bilgileri",
                value=(
                    f"**Eski Yetki:** {eski_rol.mention} ({eski_rol_ismi})\n"
                    f"**Yeni Yetki:** {yeni_rol.mention} ({yeni_rol_ismi})"
                ),
                inline=False
            )
            
            embed.add_field(
                name="İşlem Detayları",
                value=(
                    f"**Yetkiyi Düşüren:** {yetkili.mention}\n"
                    f"**Sebep:** {sebep}"
                ),
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Log kanalına bildirim gönder
            log_kanali = discord.utils.get(guild.text_channels, name="yetkili-panel-log")
            if log_kanali:
                log_embed = discord.Embed(
                    title="🔽 Yetki Düşürme",
                    description=f"{hedef_uye.mention} kullanıcısının yetkisi düşürüldü.",
                    color=discord.Color.orange(),
                    timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
                )
                
                log_embed.add_field(
                    name="Yetki Bilgileri", 
                    value=(
                        f"**Eski Yetki:** {eski_rol.mention} ({eski_rol_ismi})\n"
                        f"**Yeni Yetki:** {yeni_rol.mention} ({yeni_rol_ismi})"
                    ), 
                    inline=False
                )
                
                log_embed.add_field(
                    name="İşlem Detayları",
                    value=(
                        f"**Yetkiyi Düşüren:** {yetkili.mention} ({yetkili.id})\n"
                        f"**Düşürülen Kullanıcı:** {hedef_uye.mention} ({hedef_uye.id})\n"
                        f"**Sebep:** {sebep}"
                    ),
                    inline=False
                )
                
                log_embed.set_thumbnail(url=hedef_uye.display_avatar.url)
                log_embed.set_footer(text=f"İşlem Zamanı: {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
                
                await log_kanali.send(embed=log_embed)
            
        except Exception as e:
            await interaction.followup.send(
                f"Yetki düşürme işlemi sırasında bir hata oluştu: {str(e)}",
                ephemeral=True
            )

    # Yönetim onaylı başvurusuz yetkili ekleme (ilk yetki: STAJYER)
    async def yetkili_ekle(self, interaction, hedef_kullanici_id: int, sebep: str, verilecek_rol_id: int):
        guild = interaction.guild
        ekleyen = interaction.user
        try:
            hedef_uye = await guild.fetch_member(hedef_kullanici_id)
            if not hedef_uye:
                return await interaction.followup.send("Belirtilen ID'ye sahip kullanıcı bulunamadı.", ephemeral=True)

            # Zaten yetkili mi?
            if any(r.id in YETKILI_HIYERARSI for r in hedef_uye.roles):
                return await interaction.followup.send("Bu kullanıcı zaten yetkili.", ephemeral=True)

            # Verilecek rol kontrolü
            if verilecek_rol_id not in YETKILI_HIYERARSI:
                return await interaction.followup.send("Verilecek rol, yetkili hiyerarşisinde bulunmuyor.", ephemeral=True)
            verilecek_rol = guild.get_role(verilecek_rol_id)
            if not verilecek_rol:
                return await interaction.followup.send("Verilecek rol sunucuda bulunamadı.", ephemeral=True)

            await hedef_uye.add_roles(verilecek_rol, reason=f"Yetkili Ekleme: {sebep}")
            # DB log: added
            try:
                db = await get_db()
                await db.add_staff_change(
                    guild_id=guild.id,
                    user_id=hedef_uye.id,
                    username=hedef_uye.name,
                    action='added',
                    actor_id=ekleyen.id,
                    actor_username=ekleyen.name,
                    old_role_id=None,
                    old_role_name=None,
                    new_role_id=verilecek_rol.id,
                    new_role_name=verilecek_rol.name,
                    reason=sebep
                )
            except Exception:
                pass

            # ÜYE rolünü kaldır (ID: 1029089740022095973)
            uye_rol = guild.get_role(1029089740022095973)
            if uye_rol and uye_rol in hedef_uye.roles:
                await hedef_uye.remove_roles(
                    uye_rol,
                    reason=f"Yetkili rolü verildiği için ÜYE rolü kaldırıldı - {ekleyen.name} tarafından"
                )

            embed = discord.Embed(
                title="✅ Yetkili Eklendi",
                description=f"{hedef_uye.mention} kullanıcısına {verilecek_rol.mention} yetkisi verildi.",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
            )
            embed.add_field(name="Sebep", value=sebep or "Belirtilmedi", inline=False)
            embed.add_field(name="İşlemi Yapan", value=f"{ekleyen.mention} ({ekleyen.id})", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

            log_kanali = discord.utils.get(guild.text_channels, name="yetkili-panel-log")
            if log_kanali:
                log_embed = discord.Embed(
                    title="🆕 Yetkili Ekleme",
                    description=f"{hedef_uye.mention} yetkili yapıldı ({verilecek_rol.mention}).",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
                )
                log_embed.add_field(name="Sebep", value=sebep or "Belirtilmedi", inline=False)
                log_embed.add_field(name="İşlemi Yapan", value=f"{ekleyen.mention} ({ekleyen.id})", inline=False)
                await log_kanali.send(embed=log_embed)

        except Exception as e:
            await interaction.followup.send(f"Yetkili ekleme sırasında hata: {str(e)}", ephemeral=True)

    # Yönetim onaylı başvurusuz yetkili çıkartma (tüm yetkili rolleri kaldır)
    async def yetkili_cikart(self, interaction, hedef_kullanici_id: int, sebep: str):
        guild = interaction.guild
        cikarani = interaction.user
        try:
            hedef_uye = await guild.fetch_member(hedef_kullanici_id)
            if not hedef_uye:
                return await interaction.followup.send("Belirtilen ID'ye sahip kullanıcı bulunamadı.", ephemeral=True)

            yetkili_roller = [guild.get_role(rid) for rid in YETKILI_HIYERARSI]
            mevcut_yetkili_roller = [r for r in hedef_uye.roles if r in yetkili_roller]
            if not mevcut_yetkili_roller:
                return await interaction.followup.send("Kullanıcının üzerinde yetkili rolü yok.", ephemeral=True)

            await hedef_uye.remove_roles(*mevcut_yetkili_roller, reason=f"Yetkili Çıkartma: {sebep}")
            # DB log: removed (en yüksek mevcut yetkili rolünü eski olarak kaydet)
            try:
                top_role = None
                for rid in reversed(YETKILI_HIYERARSI):
                    r = guild.get_role(rid)
                    if r in mevcut_yetkili_roller:
                        top_role = r
                        break
                db = await get_db()
                await db.add_staff_change(
                    guild_id=guild.id,
                    user_id=hedef_uye.id,
                    username=hedef_uye.name,
                    action='removed',
                    actor_id=cikarani.id,
                    actor_username=cikarani.name,
                    old_role_id=top_role.id if top_role else None,
                    old_role_name=top_role.name if top_role else None,
                    new_role_id=None,
                    new_role_name=None,
                    reason=sebep
                )
            except Exception:
                pass
            # Üye rolünü ekle
            uye_rol_id = 1029089740022095973
            uye_rol = guild.get_role(uye_rol_id)
            if uye_rol and uye_rol not in hedef_uye.roles:
                await hedef_uye.add_roles(uye_rol, reason=f"Yetkili Çıkartma Sonrası Üye Rolü Eklendi: {sebep}")

            embed = discord.Embed(
                title="✅ Yetkili Çıkartıldı",
                description=f"{hedef_uye.mention} kullanıcısının tüm yetkili rolleri kaldırıldı ve Üye rolü verildi.",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
            )
            embed.add_field(name="Sebep", value=sebep or "Belirtilmedi", inline=False)
            embed.add_field(name="İşlemi Yapan", value=f"{cikarani.mention} ({cikarani.id})", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

            log_kanali = discord.utils.get(guild.text_channels, name="yetkili-panel-log")
            if log_kanali:
                log_embed = discord.Embed(
                    title="🗑️ Yetkili Çıkartma",
                    description=f"{hedef_uye.mention} kullanıcısının yetkileri kaldırıldı.",
                    color=discord.Color.dark_red(),
                    timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
                )
                log_embed.add_field(name="Sebep", value=sebep or "Belirtilmedi", inline=False)
                log_embed.add_field(name="İşlemi Yapan", value=f"{cikarani.mention} ({cikarani.id})", inline=False)
                await log_kanali.send(embed=log_embed)

        except Exception as e:
            await interaction.followup.send(f"Yetkili çıkartma sırasında hata: {str(e)}", ephemeral=True)

class DatabaseCleanupModal(discord.ui.Modal, title="Veritabanı Temizlik"):
    def __init__(self, cog, user):
        super().__init__()
        self.cog = cog
        self.user = user
    
    days_input = discord.ui.TextInput(
        label="Kaç Günden Eski Kayıtları Sil?",
        placeholder="365 (1 yıl önerilir)",
        default="365",
        min_length=1,
        max_length=4,
        required=True
    )
    
    confirm_input = discord.ui.TextInput(
        label="Onay için 'EVET' yazın",
        placeholder="EVET",
        min_length=1,
        max_length=10,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Modal gönderildiğinde"""
        # Onay kontrolü
        if self.confirm_input.value.upper() != "EVET":
            return await interaction.response.send_message(
                "❌ İşlem iptal edildi. Onay metni hatalı.",
                ephemeral=True
            )
        
        # Gün sayısını kontrol et
        try:
            days = int(self.days_input.value)
            if days < 30 or days > 3650:  # 30 gün ile 10 yıl arası
                return await interaction.response.send_message(
                    "❌ Gün sayısı 30 ile 3650 arasında olmalıdır.",
                    ephemeral=True
                )
        except ValueError:
            return await interaction.response.send_message(
                "❌ Geçersiz gün sayısı. Sadece sayı giriniz.",
                ephemeral=True
            )
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Temizlik işlemini başlat
            db = await get_db()
            
            # Önce mevcut boyut bilgisini al
            size_info_before = await db.get_database_size_info()
            
            # Temizlik yap
            deleted_count = await db.cleanup_old_bump_logs(days)
            
            # Sonraki boyut bilgisini al
            size_info_after = await db.get_database_size_info()
            
            # Sonuç raporu
            embed = discord.Embed(
                title="🧹 Veritabanı Temizlik Raporu",
                description="Eski bump kayıtları başarıyla temizlendi.",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
            )
            
            embed.add_field(
                name="📊 Temizlik Detayları",
                value=(
                    f"**Silinen Kayıt:** {deleted_count:,} bump\n"
                    f"**Temizlik Süresi:** {days} günden eski\n"
                    f"**Kalan Kayıt:** {size_info_after['bump_logs_count']:,} bump"
                ),
                inline=False
            )
            
            embed.add_field(
                name="💾 Boyut Karşılaştırması",
                value=(
                    f"**Önceki Boyut:** {size_info_before['estimated_size_human']}\n"
                    f"**Sonraki Boyut:** {size_info_after['estimated_size_human']}\n"
                    f"**Tasarruf:** ~{size_info_before['estimated_bump_size_mb'] - size_info_after['estimated_bump_size_mb']:.2f} MB"
                ),
                inline=False
            )
            
            if deleted_count == 0:
                embed.add_field(
                    name="ℹ️ Bilgi",
                    value=f"Belirtilen tarihten ({days} gün) daha eski kayıt bulunamadı.",
                    inline=False
                )
            
            embed.set_footer(
                text=f"İşlemi Gerçekleştiren: {interaction.user.display_name}",
                icon_url=interaction.user.display_avatar.url
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Temizlik işlemi sırasında hata oluştu: {str(e)}",
                ephemeral=True
            )
    
    async def on_error(self, interaction: discord.Interaction, error):
        """Hata durumunda"""
        await interaction.response.send_message(
            "❌ Modal işlemi sırasında bir hata oluştu.",
            ephemeral=True
        )

class SistemDurumuView(discord.ui.View):
    def __init__(self, cog, user):
        super().__init__(timeout=600)  # 10 dakika timeout
        self.cog = cog
        self.user = user
        self.message = None
        self.bot_start_time = getattr(cog.bot, 'start_time', datetime.datetime.now(pytz.timezone('Europe/Istanbul')))
    
    async def on_timeout(self):
        """Timeout olduğunda butonları devre dışı bırakma"""
        for item in self.children:
            item.disabled = True
        
        if self.message:
            await self.message.edit(view=self)
    
    async def show_system_status(self, interaction: discord.Interaction):
        """Sistem durumunu gösterir"""
        try:
            # Sistem bilgilerini topla
            embed = await self.create_system_embed(interaction.guild)
            
            await interaction.response.edit_message(embed=embed, view=self)
            self.message = await interaction.original_response()
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Hata",
                description=f"Sistem durumu bilgileri alınırken hata oluştu: {e}",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=self)
    
    async def create_system_embed(self, guild):
        """Sistem durumu embed'ini oluşturur"""
        embed = discord.Embed(
            title="💻 Sistem Durumu",
            description="Bot ve sunucu sistem durumu bilgileri",
            color=0x00ff00,
            timestamp=datetime.datetime.now(pytz.timezone('Europe/Istanbul'))
        )
        
        # === SİSTEM KAYNAKLARI ===
        # CPU kullanımı
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # RAM kullanımı
        memory = psutil.virtual_memory()
        memory_used = memory.used / (1024**3)  # GB
        memory_total = memory.total / (1024**3)  # GB
        memory_percent = memory.percent
        
        # Disk kullanımı
        disk = psutil.disk_usage('/')
        disk_used = disk.used / (1024**3)  # GB
        disk_total = disk.total / (1024**3)  # GB
        disk_percent = (disk.used / disk.total) * 100
        
        embed.add_field(
            name="🖥️ Sistem Kaynakları",
            value=f"**CPU Kullanımı:** {cpu_percent}% ({cpu_count} çekirdek)\n"
                  f"**RAM Kullanımı:** {memory_used:.1f}GB / {memory_total:.1f}GB ({memory_percent}%)\n"
                  f"**Disk Kullanımı:** {disk_used:.1f}GB / {disk_total:.1f}GB ({disk_percent:.1f}%)",
            inline=False
        )
        
        # === BOT DURUMU ===
        # Bot uptime
        uptime_delta = datetime.datetime.now(pytz.timezone('Europe/Istanbul')) - self.bot_start_time
        uptime_str = str(uptime_delta).split('.')[0]  # Milisaniyeleri çıkar
        
        # Bot process bilgileri
        process = psutil.Process()
        bot_memory = process.memory_info().rss / (1024**2)  # MB
        bot_cpu = process.cpu_percent()
        
        embed.add_field(
            name="🤖 Bot Durumu",
            value=f"**Uptime:** {uptime_str}\n"
                  f"**Bot RAM:** {bot_memory:.1f} MB\n"
                  f"**Bot CPU:** {bot_cpu}%\n"
                  f"**Python:** {platform.python_version()}\n"
                  f"**discord.py:** {discord.__version__}",
            inline=False
        )
        
        # === VERİTABANI BİLGİLERİ ===
        try:
            db = await get_db()
            size_info = await db.get_database_size_info()
            
            embed.add_field(
                name="💾 Veritabanı Durumu",
                value=f"**Spam Kayıtları:** {size_info['spam_logs_count']:,}\n"
                      f"**Bump Kayıtları:** {size_info['bump_logs_count']:,}\n"
                      f"**Başvuru Kayıtları:** {size_info['applications_count']:,}\n"
                      f"**Üye Giriş/Çıkış:** {size_info['member_logs_count']:,}\n"
                      f"**Kullanıcı Notları:** {size_info['user_notes_count']:,}\n"
                      f"**Zamanlanmış Mesajlar:** {size_info['scheduled_messages_count']:,}\n"
                      f"**Toplam Boyut:** {size_info['estimated_size_human']}",
                inline=False
            )
        except Exception as e:
            embed.add_field(
                name="💾 Veritabanı Durumu",
                value=f"❌ Veritabanı bilgileri alınamadı: {e}",
                inline=False
            )
        
        # === CACHE BİLGİLERİ ===
        try:
            extra_features_cog = self.cog.bot.get_cog("ExtraFeatures")
            if extra_features_cog:
                total_cache_messages = sum(len(user_data['messages']) for user_data in extra_features_cog.user_message_cache.values())
                
                embed.add_field(
                    name="🗄️ Cache Durumu",
                    value=f"**Spam Cache Kullanıcıları:** {len(extra_features_cog.user_message_cache):,}\n"
                          f"**Toplam Cache Mesajları:** {total_cache_messages:,}\n"
                          f"**Cache Limiti:** {extra_features_cog.MAX_CACHE_USERS:,}\n"
                          f"**Cache Kullanım Oranı:** {(len(extra_features_cog.user_message_cache) / extra_features_cog.MAX_CACHE_USERS * 100):.1f}%",
                    inline=False
                )
            else:
                embed.add_field(
                    name="🗄️ Cache Durumu",
                    value="❌ ExtraFeatures modülü bulunamadı",
                    inline=False
                )
        except Exception as e:
            embed.add_field(
                name="🗄️ Cache Durumu",
                value=f"❌ Cache bilgileri alınamadı: {e}",
                inline=False
            )
        
        # === HAFTALIK RAPOR SİSTEMİ ===
        try:
            weekly_reports_cog = self.cog.bot.get_cog("WeeklyReports")
            if weekly_reports_cog:
                # Sonraki rapor zamanını hesapla
                turkey_tz = pytz.timezone('Europe/Istanbul')
                now_turkey = datetime.datetime.now(turkey_tz)
                
                # Bir sonraki Pazar 12:00'ı hesapla
                days_until_sunday = (6 - now_turkey.weekday()) % 7
                if days_until_sunday == 0 and now_turkey.hour >= 12:
                    days_until_sunday = 7
                
                next_sunday = now_turkey + datetime.timedelta(days=days_until_sunday)
                next_sunday = next_sunday.replace(hour=12, minute=0, second=0, microsecond=0)
                
                # Kalan süreyi hesapla
                time_until = next_sunday - now_turkey
                days = time_until.days
                hours = time_until.seconds // 3600
                
                embed.add_field(
                    name="📊 Haftalık Rapor Sistemi",
                    value=f"**Durum:** ✅ Aktif\n"
                          f"**Sonraki Rapor:** {next_sunday.strftime('%d.%m.%Y %H:%M')}\n"
                          f"**Kalan Süre:** {days} gün, {hours} saat\n"
                          f"**Rapor Kanalı:** <#{weekly_reports_cog.REPORT_CHANNEL_ID}>",
                    inline=False
                )
            else:
                embed.add_field(
                    name="📊 Haftalık Rapor Sistemi",
                    value="❌ WeeklyReports modülü bulunamadı",
                    inline=False
                )
        except Exception as e:
            embed.add_field(
                name="📊 Haftalık Rapor Sistemi",
                value=f"❌ Rapor sistemi bilgileri alınamadı: {e}",
                inline=False
            )
        
        # === SUNUCU BİLGİLERİ ===
        online_members = len([m for m in guild.members if m.status != discord.Status.offline and not m.bot])
        
        embed.add_field(
            name="🏠 Sunucu Bilgileri",
            value=f"**Toplam Üye:** {guild.member_count:,}\n"
                  f"**Online Üye:** {online_members:,}\n"
                  f"**Metin Kanalları:** {len(guild.text_channels):,}\n"
                  f"**Ses Kanalları:** {len(guild.voice_channels):,}\n"
                  f"**Roller:** {len(guild.roles):,}",
            inline=False
        )
        
        # Sistem durumuna göre renk belirleme
        if cpu_percent > 80 or memory_percent > 80:
            embed.color = discord.Color.red()  # Kritik
        elif cpu_percent > 60 or memory_percent > 60:
            embed.color = discord.Color.orange()  # Uyarı
        else:
            embed.color = discord.Color.green()  # Normal
        
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(
            text=f"{guild.name} • Son Güncelleme",
            icon_url=guild.icon.url if guild.icon else None
        )
        
        return embed
    
    @discord.ui.button(label="🔄 Yenile", style=discord.ButtonStyle.green, emoji="🔄", row=0)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Sistem durumunu yenile"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        try:
            embed = await self.create_system_embed(interaction.guild)
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            await interaction.response.send_message(f"❌ Yenileme hatası: {e}", ephemeral=True)
    
    @discord.ui.button(label="🧹 Cache Temizle", style=discord.ButtonStyle.secondary, emoji="🧹", row=0)
    async def clear_cache_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cache'i temizle"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        try:
            extra_features_cog = self.cog.bot.get_cog("ExtraFeatures")
            if extra_features_cog:
                old_cache_size = len(extra_features_cog.user_message_cache)
                extra_features_cog.user_message_cache.clear()
                
                embed = discord.Embed(
                    title="✅ Cache Temizlendi",
                    description=f"**Temizlenen Kullanıcı:** {old_cache_size:,}\n"
                               f"**Yeni Durum:** 0 kullanıcı",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("❌ ExtraFeatures modülü bulunamadı!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Cache temizleme hatası: {e}", ephemeral=True)
    
    @discord.ui.button(label="◀️ Geri Dön", style=discord.ButtonStyle.danger, emoji="◀️", row=1)
    async def geri_don_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ana menüye dön"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Bu panel size ait değil!", ephemeral=True)
        
        # Ana menüye dön
        embed = discord.Embed(
            title="🛡️ HydRaboN Yetkili Paneli",
            description=(
                "Hoş geldiniz! Bu panel üzerinden yetkili işlemlerini gerçekleştirebilirsiniz.\n\n"
                "Lütfen yapmak istediğiniz işlemi aşağıdaki butonlardan seçin."
            ),
            color=0x3498db
        )
        
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{interaction.guild.name} • {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')}")
        
        view = YetkiliPanelView(self.cog, self.user)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(YetkiliPanel(bot)) 