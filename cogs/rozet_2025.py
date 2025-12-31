# 2025 Rozet Dağıtım Sistemi - Yılbaşı Özel

import discord
import datetime
import pytz
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button

# Türkiye saat dilimi
turkey_tz = pytz.timezone('Europe/Istanbul')

# Rozet rolü ID'si
ROZET_2025_ROLE_ID = 1455895059001118842

class Rozet2025View(discord.ui.View):
    """Kalıcı buton görünümü - Bot yeniden başlatılsa bile çalışır"""
    
    def __init__(self):
        super().__init__(timeout=None)  # Timeout yok = kalıcı
    
    @discord.ui.button(
        style=discord.ButtonStyle.green,
        label="🎊 2025 Rozetini Al",
        custom_id="rozet_2025_claim_button",  # Kalıcılık için önemli
        emoji="🎁"
    )
    async def claim_rozet_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Rozet alma butonu"""
        try:
            # Rozet rolünü al
            rozet_role = interaction.guild.get_role(ROZET_2025_ROLE_ID)
            
            if not rozet_role:
                await interaction.response.send_message(
                    "❌ **Hata:** Rozet rolü bulunamadı! Lütfen yöneticilere bildirin.",
                    ephemeral=True
                )
                return
            
            # Kullanıcının zaten rozeti var mı kontrol et
            if rozet_role in interaction.user.roles:
                # Zaten rozeti var
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="✨ Harika!",
                        description=(
                            f"🎉 **Zaten HydRaboN 2025 Rozetine sahipsin!**\n\n"
                            f"2025'i birlikte geride bıraktığımız için mutluyuz.\n\n"
                            f"🎊 **2026'da seni bekleyen ayrıcalıklar için hazır ol!**"
                        ),
                        color=discord.Color.gold(),
                        timestamp=datetime.datetime.now(turkey_tz)
                    ),
                    ephemeral=True
                )
                return
            
            # Rozeti kullanıcıya ver
            await interaction.user.add_roles(rozet_role, reason="2025 Rozeti - Yılbaşı Özel")
            
            # Başarı mesajı
            success_embed = discord.Embed(
                title="🎊 Tebrikler!",
                description=(
                    f"🎁 **2025 Rozeti başarıyla hesabına eklendi!**\n\n"
                    f"🌟 Artık özel {rozet_role.mention} rozeti senin!\n"
                    f"Bu rozet, 2025 yılını bizimle beraber geçirdiğin için verilen özel bir roldür.\n\n"
                    f"✨ **2026'da bu rozetle birlikte seni bekleyen sürprizler olacak!**\n"
                    f"🎉 **Yeni yılın kutlu olsun!** 🎉"
                ),
                color=discord.Color.green(),
                timestamp=datetime.datetime.now(turkey_tz)
            )
            success_embed.set_footer(
                text=f"HydRaboN • 2025 Rozet Sistemi",
                icon_url=interaction.guild.icon.url if interaction.guild.icon else None
            )
            success_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
            await interaction.response.send_message(
                embed=success_embed,
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ **Hata:** Bu rolü verme yetkim yok! Lütfen yöneticilere bildirin.",
                ephemeral=True
            )
        except Exception as e:
            print(f"2025 Rozet verme hatası: {e}")
            await interaction.response.send_message(
                "❌ **Hata:** Rozet verilirken bir sorun oluştu. Lütfen yöneticilere bildirin.",
                ephemeral=True
            )


class Rozet2025(commands.Cog):
    """2025 Yılbaşı Rozet Sistemi"""
    
    def __init__(self, bot):
        self.bot = bot
        self.turkey_tz = turkey_tz
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda kalıcı görünümü ekle"""
        try:
            # Kalıcı görünümü bot'a ekle
            self.bot.add_view(Rozet2025View())
            print("✅ 2025 Rozet sistemi kalıcı görünümü eklendi!")
        except Exception as e:
            print(f"❌ 2025 Rozet sistemi kalıcı görünüm hatası: {e}")
    
    @app_commands.command(
        name="rozet-2025-kur",
        description="2025 Yılbaşı Rozet dağıtım sistemini kurar (Sadece yönetici)"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_rozet_2025(self, interaction: discord.Interaction):
        """2025 Rozet sistemini kurar ve embed mesajı gönderir"""
        
        # Sadece belirli kullanıcı kullanabilir
        if interaction.user.id != 315888596437696522:
            await interaction.response.send_message(
                "❌ Bu komutu kullanma yetkiniz bulunmamaktadır.",
                ephemeral=True
            )
            return
        
        try:
            # Rozet rolünü kontrol et
            rozet_role = interaction.guild.get_role(ROZET_2025_ROLE_ID)
            
            if not rozet_role:
                await interaction.response.send_message(
                    f"❌ **Hata:** `{ROZET_2025_ROLE_ID}` ID'li rol bulunamadı!\n"
                    f"Lütfen önce bu rolü oluşturun veya rol ID'sini kontrol edin.",
                    ephemeral=True
                )
                return
            
            # Ana embed mesajını oluştur
            main_embed = discord.Embed(
                title="🎊 HydRaboN 2025 Rozeti 🎊",
                description=(
                    "## 🌟 2025 Yılını Birlikte Tamamladık!\n\n"
                    "**HydRaboN** ailesinin değerli üyesi,\n\n"
                    "2025 yılını bizimle geçirdiğin için çok teşekkür ederiz! "
                    "Bu özel günde, sana **HydRaboN 2025 Rozeti**'ni sunuyoruz. 🎁\n\n"
                    "### ✨ Bu Rozet Nedir?\n"
                    f"• {rozet_role.mention} bir daha alınamayacak özel bir roldür.\n"
                    "• 2025'i bizimle geçiren herkese özel bir hediyedir.\n\n"
                    "### 🎯 Gelecekte Neler Olabilir?\n"
                    "Bu rozet sadece bir başlangıç! İlerleyen zamanlarda bu rozete sahip olan kullanıcılar için:\n\n"
                    "• Özel etkinliklere erken erişim\n"
                    "• Sunucu içi özel ayrıcalıklar\n"
                    "• Ve daha fazlası gibi sürprizler seni bekliyor!\n\n"
                    "### 🎁 Nasıl Alınır?\n"
                    "Aşağıdaki **🎊 2025 Rozetini Al** butonuna tıklamanız yeterli!\n"
                    "Bot otomatik olarak rolü size verecektir.\n\n"
                    "**🎉 Mutlu Yıllar! 🎉**"
                ),
                color=0xFFD700  # Altın sarısı
            )
            
            # Sunucu ikonunu ekle
            if interaction.guild.icon:
                main_embed.set_thumbnail(url=interaction.guild.icon.url)
            
            # Footer ekle
            main_embed.set_footer(
                text=f"{interaction.guild.name} • Yılbaşı Özel 2025 ➜ 2026",
                icon_url=interaction.guild.icon.url if interaction.guild.icon else None
            )
            main_embed.timestamp = datetime.datetime.now(turkey_tz)
            
            # Görsel banner (isteğe bağlı - URL'yi değiştirebilirsiniz)
            # main_embed.set_image(url="https://example.com/2025-banner.png")
            
            # Kalıcı buton görünümünü oluştur
            view = Rozet2025View()
            
            # Mesajı gönder
            await interaction.channel.send(embed=main_embed, view=view)
            
            # Başarı bildirimi
            await interaction.response.send_message(
                "✅ **Başarılı!** 2025 Rozet dağıtım mesajı gönderildi!\n\n"
                f"🎊 **Rozet Rolü:** {rozet_role.mention}\n"
                f"📍 **Kanal:** {interaction.channel.mention}\n\n"
                f"Kullanıcılar artık butona tıklayarak rozet alabilirler. "
                f"Bot yeniden başlatılsa bile buton çalışmaya devam edecektir.",
                ephemeral=True
            )
            
        except Exception as e:
            print(f"2025 Rozet kurulum hatası: {e}")
            await interaction.response.send_message(
                f"❌ **Hata:** Rozet sistemi kurulurken bir sorun oluştu: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(
        name="rozet-2025-istatistik",
        description="2025 Rozeti istatistiklerini gösterir (Sadece yönetici)"
    )
    @app_commands.default_permissions(administrator=True)
    async def rozet_2025_stats(self, interaction: discord.Interaction):
        """2025 Rozet istatistiklerini gösterir"""
        
        # Sadece belirli kullanıcı kullanabilir
        if interaction.user.id != 315888596437696522:
            await interaction.response.send_message(
                "❌ Bu komutu kullanma yetkiniz bulunmamaktadır.",
                ephemeral=True
            )
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Rozet rolünü al
            rozet_role = interaction.guild.get_role(ROZET_2025_ROLE_ID)
            
            if not rozet_role:
                await interaction.followup.send(
                    f"❌ **Hata:** `{ROZET_2025_ROLE_ID}` ID'li rol bulunamadı!",
                    ephemeral=True
                )
                return
            
            # İstatistikleri hesapla
            total_members = len([m for m in interaction.guild.members if not m.bot])
            members_with_rozet = len(rozet_role.members)
            percentage = (members_with_rozet / total_members * 100) if total_members > 0 else 0
            
            # İstatistik embed'i
            stats_embed = discord.Embed(
                title="📊 2025 Rozet İstatistikleri",
                description=f"**{interaction.guild.name}** sunucusundaki 2025 Rozet dağılımı",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(turkey_tz)
            )
            
            stats_embed.add_field(
                name="🎁 Rozet Bilgileri",
                value=(
                    f"**Rozet Rolü:** {rozet_role.mention}\n"
                    f"**Rol ID:** `{ROZET_2025_ROLE_ID}`\n"
                    f"**Rol Rengi:** {rozet_role.color}"
                ),
                inline=False
            )
            
            stats_embed.add_field(
                name="📈 Dağıtım İstatistikleri",
                value=(
                    f"**Rozete Sahip Üye:** `{members_with_rozet:,}` kişi\n"
                    f"**Toplam Üye:** `{total_members:,}` kişi\n"
                    f"**Dağıtım Oranı:** `{percentage:.2f}%`"
                ),
                inline=False
            )
            
            # İlk 10 rozet sahibini göster (örnek)
            if rozet_role.members:
                first_10 = rozet_role.members[:10]
                members_text = "\n".join([f"• {member.mention}" for member in first_10])
                
                if len(rozet_role.members) > 10:
                    members_text += f"\n... ve {len(rozet_role.members) - 10} kişi daha"
                
                stats_embed.add_field(
                    name="👥 Rozete Sahip Üyeler (İlk 10)",
                    value=members_text,
                    inline=False
                )
            else:
                stats_embed.add_field(
                    name="👥 Rozete Sahip Üyeler",
                    value="Henüz kimse rozet almamış.",
                    inline=False
                )
            
            stats_embed.set_footer(
                text=f"{interaction.guild.name} • Rozet İstatistik Sistemi",
                icon_url=interaction.guild.icon.url if interaction.guild.icon else None
            )
            
            await interaction.followup.send(embed=stats_embed, ephemeral=True)
            
        except Exception as e:
            print(f"2025 Rozet istatistik hatası: {e}")
            await interaction.followup.send(
                f"❌ **Hata:** İstatistikler alınırken bir sorun oluştu: {str(e)}",
                ephemeral=True
            )


async def setup(bot):
    """Cog'u bot'a ekle"""
    await bot.add_cog(Rozet2025(bot))

