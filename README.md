# HydRaboN Yetkili Alım Bot

Discord sunucunuz için gelişmiş yetkili alım sistemi. Bu bot, sunucunuzda yetkili olmak isteyen kullanıcıların başvuru yapmalarını sağlar ve başvuruları yönetmenize yardımcı olur.

## Özellikler

- Özel yetkili alım kategorisi ve kanalları oluşturma
- Başvuru butonu ile kolay erişim
- Her başvuran için özel başvuru kanalı oluşturma
- Form sistemi ile detaylı bilgi toplama
- Başvuruları yöneticilerin görebileceği özel bir kanalda toplama
- Başvuruları onaylama veya reddetme butonları
- Onaylanan başvurulara otomatik rol atama
- Başvuru sonucunu kullanıcıya özel mesaj ile bildirme

## Kurulum

1. Python 3.8 veya daha yüksek bir sürümü yükleyin.
2. Bu depoyu bilgisayarınıza indirin.
3. Gerekli paketleri yüklemek için aşağıdaki komutu çalıştırın:
   ```
   pip install -r requirements.txt
   ```
4. `.env` dosyasını düzenleyerek Discord bot tokenınızı girin:
   ```
   TOKEN=BURAYA_DISCORD_BOT_TOKENINIZI_YAZIN
   ```
5. **ÖNEMLİ:** [Discord Developer Portal](https://discord.com/developers/applications)'dan botunuzu seçin ve "Bot" sekmesinde aşağıdaki intent'leri etkinleştirin:
   - Presence Intent
   - Server Members Intent 
   - Message Content Intent
6. Bot'u başlatmak için aşağıdaki komutu çalıştırın:
   ```
   python main.py
   ```

## Bot'u Discord Sunucunuza Ekleme

1. [Discord Developer Portal](https://discord.com/developers/applications)'a gidin ve yeni bir uygulama oluşturun.
2. "Bot" sekmesine giderek bir bot oluşturun.
3. Bot'un yetkilerini ayarlayın (aşağıdaki izinler önerilir):
   - `Manage Channels`
   - `Manage Roles`
   - `Send Messages`
   - `Embed Links`
   - `Read Message History`
   - `Add Reactions`
   - `Use Slash Commands`
   - `applications.commands` scope (OAuth2 URL oluştururken)
4. "OAuth2" sekmesinden bir davet bağlantısı oluşturun ve bot'u sunucunuza ekleyin. Scope olarak **bot** ve **applications.commands** seçeneklerini işaretlediğinizden emin olun.

## Kullanım

1. Bot'u sunucunuza ekledikten sonra:
   - Bot otomatik olarak sunucunuzdaki slash komutlarını senkronize etmeye çalışacaktır
   - Eğer "Bilinmeyen Entegrasyon" hatası alırsanız, `!sync` komutunu kullanarak slash komutlarını manuel olarak senkronize edebilirsiniz
   
2. Yetkili alım sistemini kurmak için slash komutu kullanın:
   ```
   /yetkilialim-kur
   ```

3. Bot otomatik olarak aşağıdaki kanalları oluşturacaktır:
   - `Yetkili Alım` kategorisi
   - `yetkili-alım` kanalı (başvuru butonu içerecek)
   - `başvurular` kanalı (sadece yöneticilerin görebileceği)
4. Kullanıcılar `yetkili-alım` kanalındaki "Başvur" butonuna tıklayarak başvuru formunu doldurmaya başlayabilir.
5. Kullanıcı başvuruyu tamamladığında, başvuru bilgileri `başvurular` kanalında gösterilir ve yöneticiler başvuruyu onaylama veya reddetme seçeneğine sahip olur.

## Sorun Giderme

- **"Başvur" butonuna bastığımda "etkileşim başarısız oldu" hatası alıyorum**: Bu sorunu çözmek için bot'u yeniden başlatın. Bot başlatıldıktan sonra zaten var olan butonlar istemcilere kayıtlı olacak ve düzgün çalışacaktır. Alternatif olarak, `/yetkilialim-kur` komutunu yeniden çalıştırarak butonları güncelleyebilirsiniz.

- **"/yetkilialim-kur" komutunda "Bilinmeyen Entegrasyon" hatası alıyorum**: Discord API'de slash komutlarının düzgün kayıtlı olmadığını gösterir. Aşağıdaki çözümleri deneyin:
  1. Botu yeniden başlatın
  2. `!sync` komutunu kullanarak komutları manuel olarak senkronize edin
  3. Bot davet bağlantısını oluştururken `applications.commands` iznini eklediğinizden emin olun
  4. Botun bot token'ı aktif ve doğru olduğundan emin olun

- **Butonlar çalışmıyor**: [Discord Developer Portal](https://discord.com/developers/applications)'dan "Bot" sekmesinde "Privileged Gateway Intents" bölümündeki tüm intent'lerin (özellikle "Message Content Intent") açık olduğundan emin olun.

## Diğer Komutlar

Bot ayrıca şu komutları sunar (sadece yöneticiler kullanabilir):

- `!sync` - Slash komutlarını günceller ve senkronize eder
- `!load yetkili_alim` - Yetkili alım modülünü yükler
- `!unload yetkili_alim` - Yetkili alım modülünü devre dışı bırakır
- `!reload yetkili_alim` - Yetkili alım modülünü yeniden yükler

## Notlar

- Bot'un düzgün çalışabilmesi için "Sunucu Üyelerini Görüntüle" ve "Mesaj İçeriğini Görüntüle" intent'lerinin Discord Developer Portal'da etkinleştirilmiş olması gerekir.
- Başvuru formu soruları `cogs/yetkili_alim.py` dosyasından özelleştirilebilir. 