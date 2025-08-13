import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from database import get_db
import datetime
import pytz
from typing import Optional

class UserNotes(commands.Cog):
    """Kullanıcı notları yönetim sistemi"""
    
    def __init__(self, bot):
        self.bot = bot
        self.turkey_tz = pytz.timezone('Europe/Istanbul')
    
    @app_commands.command(name="not", description="Kullanıcı not yönetimi")
    @app_commands.describe(
        işlem="Yapılacak işlem",
        kullanıcı="Not alınacak/görüntülenecek kullanıcı", 
        not_içeriği="Eklenecek not içeriği",
        not_id="Düzenlenecek/silinecek not ID'si"
    )
    @app_commands.choices(işlem=[
        app_commands.Choice(name="Ekle", value="ekle"),
        app_commands.Choice(name="Görüntüle", value="gör"),
        app_commands.Choice(name="Düzenle", value="düzenle"),
        app_commands.Choice(name="Sil", value="sil")
    ])
    @app_commands.default_permissions(administrator=True)
    async def not_command(
        self, 
        interaction: discord.Interaction, 
        işlem: app_commands.Choice[str],
        kullanıcı: Optional[discord.User] = None,
        not_içeriği: Optional[str] = None,
        not_id: Optional[int] = None
    ):
        """Ana not yönetimi komutu"""
        
        # Administrator kontrolü
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Bu komutu kullanmak için Administrator yetkisine sahip olmalısınız!", 
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            if işlem.value == "ekle":
                await self._add_note(interaction, kullanıcı, not_içeriği)
            elif işlem.value == "gör":
                await self._view_notes(interaction, kullanıcı)
            elif işlem.value == "düzenle":
                await self._edit_note(interaction, not_id, not_içeriği)
            elif işlem.value == "sil":
                await self._delete_note(interaction, not_id)
                
        except Exception as e:
            await interaction.followup.send(
                f"❌ Bir hata oluştu: {str(e)}", 
                ephemeral=True
            )
    
    async def _add_note(self, interaction: discord.Interaction, user: discord.User, content: str):
        """Kullanıcı hakkında not ekler"""
        if not user or not content:
            await interaction.followup.send(
                "❌ Not eklemek için kullanıcı ve not içeriği belirtmelisiniz!\n"
                "**Kullanım:** `/not ekle kullanıcı:@kullanıcı not_içeriği:Buraya not yazın`",
                ephemeral=True
            )
            return
        
        if len(content) > 1500:
            await interaction.followup.send(
                "❌ Not içeriği 1500 karakterden uzun olamaz!",
                ephemeral=True
            )
            return
        
        db = await get_db()
        
        # Kullanıcı bilgilerini al
        username = user.global_name or user.name
        discriminator = user.discriminator if user.discriminator != "0" else None
        
        # Notu ekle
        note_id = await db.add_user_note(
            user_id=user.id,
            username=username,
            discriminator=discriminator,
            note_content=content,
            created_by=interaction.user.id,
            created_by_username=interaction.user.global_name or interaction.user.name,
            guild_id=interaction.guild.id
        )
        
        # Başarı mesajı
        embed = discord.Embed(
            title="✅ Not Başarıyla Eklendi",
            description=f"**Kullanıcı:** {user.mention} (`{user.id}`)\n"
                       f"**Not ID:** `{note_id}`\n"
                       f"**İçerik:** {content[:100]}{'...' if len(content) > 100 else ''}",
            color=0x00ff00,
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        embed.set_footer(text=f"Not ekleyen: {interaction.user.name}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def _view_notes(self, interaction: discord.Interaction, user: discord.User):
        """Kullanıcının notlarını görüntüler"""
        if not user:
            await interaction.followup.send(
                "❌ Notlarını görüntülemek için kullanıcı belirtmelisiniz!\n"
                "**Kullanım:** `/not gör kullanıcı:@kullanıcı`",
                ephemeral=True
            )
            return
        
        db = await get_db()
        notes = await db.get_user_notes(user.id, interaction.guild.id, limit=10)
        
        if not notes:
            await interaction.followup.send(
                f"📝 **{user.mention}** kullanıcısı hakkında henüz not bulunmuyor.",
                ephemeral=True
            )
            return
        
        # Embed oluştur
        embed = discord.Embed(
            title=f"📝 {user.global_name or user.name} - Kullanıcı Notları",
            description=f"**Kullanıcı:** {user.mention} (`{user.id}`)\n"
                       f"**Toplam Not Sayısı:** {len(notes)}",
            color=0x3498db,
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        # Notları ekle (en fazla 5 tane)
        for i, note in enumerate(notes[:5], 1):
            created_date = datetime.datetime.fromisoformat(note['created_at']).strftime('%d.%m.%Y %H:%M')
            note_content = note['note_content']
            if len(note_content) > 200:
                note_content = note_content[:200] + "..."
            
            embed.add_field(
                name=f"Not #{note['id']} - {created_date}",
                value=f"**İçerik:** {note_content}\n"
                      f"**Ekleyen:** {note['created_by_username']}",
                inline=False
            )
        
        if len(notes) > 5:
            embed.add_field(
                name="ℹ️ Bilgi",
                value=f"Sadece son 5 not gösteriliyor. Tüm notları görmek için yetkili paneli kullanın.",
                inline=False
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def _edit_note(self, interaction: discord.Interaction, note_id: int, new_content: str):
        """Mevcut notu düzenler"""
        if not note_id or not new_content:
            await interaction.followup.send(
                "❌ Not düzenlemek için not ID'si ve yeni içerik belirtmelisiniz!\n"
                "**Kullanım:** `/not düzenle not_id:123 not_içeriği:Yeni not içeriği`",
                ephemeral=True
            )
            return
        
        if len(new_content) > 1500:
            await interaction.followup.send(
                "❌ Not içeriği 1500 karakterden uzun olamaz!",
                ephemeral=True
            )
            return
        
        db = await get_db()
        
        # Önce notu kontrol et
        note = await db.get_note_by_id(note_id, interaction.guild.id)
        if not note:
            await interaction.followup.send(
                f"❌ `{note_id}` ID'li not bulunamadı!",
                ephemeral=True
            )
            return
        
        # Notu güncelle
        success = await db.update_user_note(note_id, new_content, interaction.guild.id)
        
        if success:
            embed = discord.Embed(
                title="✅ Not Başarıyla Güncellendi",
                description=f"**Not ID:** `{note_id}`\n"
                           f"**Kullanıcı:** <@{note['user_id']}> (`{note['user_id']}`)\n"
                           f"**Eski İçerik:** {note['note_content'][:100]}{'...' if len(note['note_content']) > 100 else ''}\n"
                           f"**Yeni İçerik:** {new_content[:100]}{'...' if len(new_content) > 100 else ''}",
                color=0x00ff00,
                timestamp=datetime.datetime.now(self.turkey_tz)
            )
            embed.set_footer(text=f"Düzenleyen: {interaction.user.name}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ Not güncellenirken bir hata oluştu!",
                ephemeral=True
            )
    
    async def _delete_note(self, interaction: discord.Interaction, note_id: int):
        """Notu siler"""
        if not note_id:
            await interaction.followup.send(
                "❌ Not silmek için not ID'si belirtmelisiniz!\n"
                "**Kullanım:** `/not sil not_id:123`",
                ephemeral=True
            )
            return
        
        db = await get_db()
        
        # Önce notu kontrol et
        note = await db.get_note_by_id(note_id, interaction.guild.id)
        if not note:
            await interaction.followup.send(
                f"❌ `{note_id}` ID'li not bulunamadı!",
                ephemeral=True
            )
            return
        
        # Onay için buton ekle
        view = DeleteConfirmView(note, interaction.user)
        
        embed = discord.Embed(
            title="⚠️ Not Silme Onayı",
            description=f"**Not ID:** `{note_id}`\n"
                       f"**Kullanıcı:** <@{note['user_id']}> (`{note['user_id']}`)\n"
                       f"**İçerik:** {note['note_content'][:200]}{'...' if len(note['note_content']) > 200 else ''}\n"
                       f"**Ekleyen:** {note['created_by_username']}\n"
                       f"**Tarih:** {datetime.datetime.fromisoformat(note['created_at']).strftime('%d.%m.%Y %H:%M')}\n\n"
                       f"Bu notu silmek istediğinizden emin misiniz?",
            color=0xff6b6b,
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class DeleteConfirmView(discord.ui.View):
    """Not silme onay view'ı"""
    
    def __init__(self, note, user):
        super().__init__(timeout=60)
        self.note = note
        self.user = user
    
    @discord.ui.button(label="🗑️ Sil", style=discord.ButtonStyle.danger)
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message(
                "❌ Bu işlemi sadece komutu kullanan kişi yapabilir!",
                ephemeral=True
            )
            return
        
        db = await get_db()
        success = await db.delete_user_note(self.note['id'], interaction.guild.id)
        
        if success:
            embed = discord.Embed(
                title="✅ Not Başarıyla Silindi",
                description=f"**Not ID:** `{self.note['id']}`\n"
                           f"**Kullanıcı:** <@{self.note['user_id']}> (`{self.note['user_id']}`)\n"
                           f"**Silinen İçerik:** {self.note['note_content'][:100]}{'...' if len(self.note['note_content']) > 100 else ''}",
                color=0x00ff00,
                timestamp=datetime.datetime.now(self.turkey_tz)
            )
            embed.set_footer(text=f"Silen: {interaction.user.name}")
            
            # Butonları devre dışı bırak
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message(
                "❌ Not silinirken bir hata oluştu!",
                ephemeral=True
            )
    
    @discord.ui.button(label="❌ İptal", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message(
                "❌ Bu işlemi sadece komutu kullanan kişi yapabilir!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="❌ İşlem İptal Edildi",
            description="Not silme işlemi iptal edildi.",
            color=0x95a5a6,
            timestamp=datetime.datetime.now(self.turkey_tz)
        )
        
        # Butonları devre dışı bırak
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def on_timeout(self):
        # Timeout olduğunda butonları devre dışı bırak
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

async def setup(bot):
    await bot.add_cog(UserNotes(bot))