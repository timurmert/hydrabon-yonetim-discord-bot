import aiosqlite
import json
import os
import asyncio
from datetime import datetime, timezone, timedelta

class Database:
    def __init__(self, db_path="hydrabon_bot.db"):
        self.db_path = db_path
        self.connection = None
        
    async def connect(self):
        """Veritabanına bağlanır ve tabloları oluşturur"""
        self.connection = await aiosqlite.connect(self.db_path)
        
        # Tablolara daha rahat erişim için row_factory ayarlanması
        self.connection.row_factory = aiosqlite.Row
        
        # Tabloların oluşturulması
        await self.create_tables()
        
        return self.connection
        
    async def close(self):
        """Veritabanı bağlantısını kapatır"""
        if self.connection:
            await self.connection.close()
            self.connection = None
            
    async def create_tables(self):
        """Gerekli veritabanı tablolarını oluşturur"""
        async with self.connection.cursor() as cursor:
            # Yetkili başvuruları tablosu
            await cursor.execute('''
            CREATE TABLE IF NOT EXISTS staff_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                application_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                answers TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                reviewer_id INTEGER,
                review_date TIMESTAMP,
                review_message TEXT,
                assigned_role_id INTEGER,
                assigned_role_name TEXT
            )
            ''')
            
            # Otomatik mesajlar tablosu
            await cursor.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                channel_name TEXT NOT NULL,
                message_content TEXT NOT NULL, 
                embed_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER NOT NULL,
                schedule_type TEXT NOT NULL,
                schedule_data TEXT NOT NULL,
                repeat_count INTEGER DEFAULT 1,
                sent_count INTEGER DEFAULT 0,
                active BOOLEAN DEFAULT 1,
                last_sent TIMESTAMP,
                last_message_id TEXT
            )
            ''')
            
            # Bump logları tablosu - her bump için ayrı kayıt
            await cursor.execute('''
            CREATE TABLE IF NOT EXISTS bump_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                bump_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Bump kullanıcıları özet tablosu - hızlı erişim için
            await cursor.execute('''
            CREATE TABLE IF NOT EXISTS bump_users (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                total_bumps INTEGER DEFAULT 0,
                last_bump TIMESTAMP,
                first_bump TIMESTAMP,
                PRIMARY KEY (user_id, guild_id)
            )
            ''')
            
            # Spam koruması tablosu
            await cursor.execute('''
            CREATE TABLE IF NOT EXISTS spam_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_content TEXT NOT NULL,
                spam_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                timeout_applied BOOLEAN DEFAULT 1,
                messages_deleted INTEGER DEFAULT 3
            )
            ''')
            
            # Performans için indeksler
            await cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_bump_logs_user_guild 
            ON bump_logs(user_id, guild_id)
            ''')
            
            await cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_bump_logs_time 
            ON bump_logs(bump_time)
            ''')
            
            await cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_bump_logs_guild_time 
            ON bump_logs(guild_id, bump_time)
            ''')
            
            await cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_bump_users_guild 
            ON bump_users(guild_id)
            ''')
            
            # Spam logs için indeksler
            await cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_spam_logs_user_guild 
            ON spam_logs(user_id, guild_id)
            ''')
            
            await cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_spam_logs_time 
            ON spam_logs(spam_time)
            ''')
            
            # Üye giriş/çıkış logları tablosu
            await cursor.execute('''
            CREATE TABLE IF NOT EXISTS member_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                discriminator TEXT,
                guild_id INTEGER NOT NULL,
                action TEXT NOT NULL,  -- 'join' veya 'leave'
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                account_created TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Member logs için indeksler
            await cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_member_logs_guild_time 
            ON member_logs(guild_id, timestamp)
            ''')
            
            await cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_member_logs_action_time 
            ON member_logs(action, timestamp)
            ''')
            
            # Presence snapshot'ları tablosu: periyodik online kullanıcı sayısı
            await cursor.execute('''
            CREATE TABLE IF NOT EXISTS presence_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                snapshot_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                online_count INTEGER NOT NULL,
                total_members INTEGER NOT NULL
            )
            ''')
            
            # Presence için indeksler
            await cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_presence_guild_time
            ON presence_snapshots(guild_id, snapshot_time)
            ''')
            
            # Kullanıcı notları tablosu
            await cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                discriminator TEXT,
                note_content TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_by_username TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                guild_id INTEGER NOT NULL
            )
            ''')
            
            # User notes için indeksler
            await cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_notes_user_id 
            ON user_notes(user_id)
            ''')
            
            await cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_notes_guild_created 
            ON user_notes(guild_id, created_at)
            ''')
            
            await cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_notes_created_by 
            ON user_notes(created_by, created_at)
            ''')
            
            # Migration: Eski bump verilerini yeni tablolara taşı
            await self.migrate_old_bump_data()
            
            # Eksik sütunu kontrol et ve ekle
            try:
                await cursor.execute("SELECT last_message_id FROM scheduled_messages LIMIT 1")
            except aiosqlite.OperationalError:
                # Sütun mevcut değilse ekle
                # Adding missing column
                await cursor.execute("ALTER TABLE scheduled_messages ADD COLUMN last_message_id TEXT")
            
            await self.connection.commit()
            
    async def migrate_old_bump_data(self):
        """Eski bump verilerini yeni tablo yapısına taşır"""
        async with self.connection.cursor() as cursor:
            # Eski bump_users tablosundaki verileri kontrol et
            try:
                await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bump_users'")
                table_exists = await cursor.fetchone()
                
                if table_exists:
                    # Eski bump_users tablosunda bump_count sütunu var mı kontrol et
                    await cursor.execute("PRAGMA table_info(bump_users)")
                    columns = await cursor.fetchall()
                    column_names = [column[1] for column in columns]
                    
                    # Eğer eski yapıda bump_count varsa yeni yapıya geç
                    if 'bump_count' in column_names and 'total_bumps' not in column_names:
                        # Migrating old bump data
                        
                        # Geçici tablo oluştur
                        await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS bump_users_new (
                            user_id INTEGER NOT NULL,
                            guild_id INTEGER NOT NULL,
                            username TEXT NOT NULL,
                            total_bumps INTEGER DEFAULT 0,
                            last_bump TIMESTAMP,
                            first_bump TIMESTAMP,
                            PRIMARY KEY (user_id, guild_id)
                        )
                        ''')
                        
                        # Eski verileri yeni tabloya taşı
                        await cursor.execute('''
                        INSERT OR REPLACE INTO bump_users_new 
                        (user_id, guild_id, username, total_bumps, last_bump, first_bump)
                        SELECT user_id, guild_id, username, bump_count, last_bump, last_bump
                        FROM bump_users
                        ''')
                        
                        # Eski tabloyu sil ve yenisini yeniden adlandır
                        await cursor.execute("DROP TABLE bump_users")
                        await cursor.execute("ALTER TABLE bump_users_new RENAME TO bump_users")
                        
                        # Migration completed
                        
            except Exception as e:
                print(f"Migration sırasında hata: {e}")
                pass
            
    async def save_staff_application(self, user_id, username, answers):
        """Yetkili başvurusunu veritabanına kaydeder
        
        Args:
            user_id (int): Başvuran kullanıcının Discord ID'si
            username (str): Başvuran kullanıcının kullanıcı adı
            answers (dict): Soru ve cevapların olduğu sözlük
            
        Returns:
            int: Kaydedilen başvurunun ID'si
        """
        # Cevapları JSON formatına dönüştürme
        answers_json = json.dumps(answers, ensure_ascii=False)
        
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            INSERT INTO staff_applications (user_id, username, answers, application_date)
            VALUES (?, ?, ?, ?)
            ''', (user_id, username, answers_json, datetime.now(timezone.utc).isoformat()))
            
            await self.connection.commit()
            return cursor.lastrowid
            
    async def update_application_status(self, application_id, status, reviewer_id=None, 
                                      review_message=None, assigned_role_id=None, assigned_role_name=None):
        """Yetkili başvurusunun durumunu günceller
        
        Args:
            application_id (int): Başvuru ID'si
            status (str): Başvuru durumu ('approved', 'rejected', 'pending')
            reviewer_id (int, optional): İnceleyenin Discord ID'si
            review_message (str, optional): İnceleyenin mesajı
            assigned_role_id (int, optional): Atanan rol ID'si 
            assigned_role_name (str, optional): Atanan rol adı
            
        Returns:
            bool: Güncelleme başarılı ise True, değilse False
        """
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute('''
                UPDATE staff_applications 
                SET status = ?, 
                    reviewer_id = ?,
                    review_date = ?,
                    review_message = ?,
                    assigned_role_id = ?,
                    assigned_role_name = ?
                WHERE id = ?
                ''', (status, reviewer_id, datetime.now(timezone.utc).isoformat(), review_message, 
                      assigned_role_id, assigned_role_name, application_id))
                
                await self.connection.commit()
                return True
        except Exception as e:
            print(f"Başvuru güncelleme hatası: {e}")
            return False
            
    async def get_application_by_user_id(self, user_id):
        """Kullanıcının en son başvurusunu getirir
        
        Args:
            user_id (int): Kullanıcının Discord ID'si
            
        Returns:
            dict: Başvuru bilgileri veya None
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT * FROM staff_applications
            WHERE user_id = ?
            ORDER BY application_date DESC
            LIMIT 1
            ''', (user_id,))
            
            row = await cursor.fetchone()
            
            if row:
                # Row nesnesi sözlüğe dönüştürülüyor
                application = dict(row)
                # JSON formatındaki cevapları Python sözlüğüne dönüştür
                application['answers'] = json.loads(application['answers'])
                return application
            
            return None
            
    async def get_all_applications(self, status=None):
        """Tüm başvuruları getirir
        
        Args:
            status (str, optional): Filtrelenecek durum ('approved', 'rejected', 'pending')
            
        Returns:
            list: Başvuru bilgilerinin listesi
        """
        async with self.connection.cursor() as cursor:
            if status:
                await cursor.execute('''
                SELECT * FROM staff_applications
                WHERE status = ?
                ORDER BY application_date DESC
                ''', (status,))
            else:
                await cursor.execute('''
                SELECT * FROM staff_applications
                ORDER BY application_date DESC
                ''')
            
            rows = await cursor.fetchall()
            
            applications = []
            for row in rows:
                application = dict(row)
                application['answers'] = json.loads(application['answers'])
                applications.append(application)
            
            return applications
            
    async def add_bump_log(self, user_id, username, guild_id):
        """Yeni bump kaydını veritabanına ekler ve özet tablosunu günceller
        
        Args:
            user_id (int): Kullanıcının Discord ID'si
            username (str): Kullanıcının adı
            guild_id (int): Sunucu ID'si
            
        Returns:
            tuple: (bump_id, total_bumps)
        """
        current_time = datetime.now(timezone.utc).isoformat()
        
        async with self.connection.cursor() as cursor:
            # Bump logu ekle
            await cursor.execute('''
            INSERT INTO bump_logs (user_id, username, guild_id, bump_time, created_at)
            VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, guild_id, current_time, current_time))
            
            bump_id = cursor.lastrowid
            
            # Özet tablosunu güncelle veya oluştur
            await cursor.execute('''
            INSERT INTO bump_users (user_id, guild_id, username, total_bumps, last_bump, first_bump)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET
                username = ?,
                total_bumps = total_bumps + 1,
                last_bump = ?
            ''', (user_id, guild_id, username, current_time, current_time, username, current_time))
            
            # Güncellenmiş toplam bump sayısını al
            await cursor.execute('''
            SELECT total_bumps FROM bump_users 
            WHERE user_id = ? AND guild_id = ?
            ''', (user_id, guild_id))
            
            result = await cursor.fetchone()
            total_bumps = result[0] if result else 1
            
            await self.connection.commit()
            return bump_id, total_bumps
            
    async def get_bump_stats_by_period(self, guild_id, period_type):
        """Belirtilen periyoda göre bump istatistiklerini getirir
        
        Args:
            guild_id (int): Sunucu ID'si
            period_type (str): 'daily', 'weekly', 'biweekly', 'monthly'
            
        Returns:
            list: Kullanıcı bazlı bump istatistikleri
        """
        # Tarih aralığını hesapla
        now = datetime.now(timezone.utc)
        
        if period_type == 'daily':
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period_type == 'weekly':
            start_time = now - timedelta(days=7)
        elif period_type == 'biweekly':
            start_time = now - timedelta(days=14)
        elif period_type == 'monthly':
            start_time = now - timedelta(days=30)
        else:
            raise ValueError("Geçersiz period_type. 'daily', 'weekly', 'biweekly', 'monthly' olmalı.")
        
        start_time_str = start_time.isoformat()
        
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT 
                user_id,
                username,
                COUNT(*) as bump_count,
                MIN(bump_time) as first_bump,
                MAX(bump_time) as last_bump
            FROM bump_logs 
            WHERE guild_id = ? AND bump_time >= ?
            GROUP BY user_id, username
            ORDER BY bump_count DESC, last_bump DESC
            ''', (guild_id, start_time_str))
            
            rows = await cursor.fetchall()
            
            stats = []
            for row in rows:
                stats.append({
                    'user_id': row[0],
                    'username': row[1],
                    'bump_count': row[2],
                    'first_bump': row[3],
                    'last_bump': row[4]
                })
            
            return stats
            
    async def get_user_bump_history(self, user_id, guild_id, limit=50):
        """Kullanıcının bump geçmişini getirir
        
        Args:
            user_id (int): Kullanıcının Discord ID'si
            guild_id (int): Sunucu ID'si
            limit (int): Maksimum kayıt sayısı
            
        Returns:
            list: Bump kayıtları
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT id, bump_time, created_at
            FROM bump_logs 
            WHERE user_id = ? AND guild_id = ?
            ORDER BY bump_time DESC
            LIMIT ?
            ''', (user_id, guild_id, limit))
            
            rows = await cursor.fetchall()
            
            history = []
            for row in rows:
                history.append({
                    'id': row[0],
                    'bump_time': row[1],
                    'created_at': row[2]
                })
            
            return history
            
    async def get_total_bump_stats(self, guild_id):
        """Sunucunun toplam bump istatistiklerini getirir
        
        Args:
            guild_id (int): Sunucu ID'si
            
        Returns:
            dict: Toplam istatistikler
        """
        async with self.connection.cursor() as cursor:
            # Toplam bump sayısı
            await cursor.execute('''
            SELECT COUNT(*) FROM bump_logs WHERE guild_id = ?
            ''', (guild_id,))
            total_bumps = (await cursor.fetchone())[0]
            
            # Aktif kullanıcı sayısı
            await cursor.execute('''
            SELECT COUNT(DISTINCT user_id) FROM bump_logs WHERE guild_id = ?
            ''', (guild_id,))
            active_users = (await cursor.fetchone())[0]
            
            # En son bump
            await cursor.execute('''
            SELECT bump_time, username FROM bump_logs 
            WHERE guild_id = ? 
            ORDER BY bump_time DESC 
            LIMIT 1
            ''', (guild_id,))
            latest_bump_row = await cursor.fetchone()
            
            # Bugünkü bump sayısı
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            await cursor.execute('''
            SELECT COUNT(*) FROM bump_logs 
            WHERE guild_id = ? AND bump_time >= ?
            ''', (guild_id, today.isoformat()))
            today_bumps = (await cursor.fetchone())[0]
            
            return {
                'total_bumps': total_bumps,
                'active_users': active_users,
                'latest_bump': {
                    'time': latest_bump_row[0] if latest_bump_row else None,
                    'username': latest_bump_row[1] if latest_bump_row else None
                },
                'today_bumps': today_bumps
            }

    async def get_application_stats(self):
        """Başvurular hakkında istatistikler döndürür
        
        Returns:
            dict: İstatistik bilgileri
        """
        async with self.connection.cursor() as cursor:
            # Toplam başvuru sayısı
            await cursor.execute('SELECT COUNT(*) as total FROM staff_applications')
            total = (await cursor.fetchone())['total']
            
            # Durumlara göre sayı
            await cursor.execute('SELECT status, COUNT(*) as count FROM staff_applications GROUP BY status')
            status_counts = {}
            for row in await cursor.fetchall():
                status_counts[row['status']] = row['count']
            
            # Son 7 gündeki başvuruların sayısı
            await cursor.execute('''
            SELECT COUNT(*) as recent FROM staff_applications 
            WHERE application_date >= datetime('now', '-7 days')
            ''')
            recent = (await cursor.fetchone())['recent']
            
            return {
                'total': total,
                'status_counts': status_counts,
                'recent': recent
            }
            
    # Otomatik mesajlar için yeni metodlar
    async def add_scheduled_message(self, channel_id, channel_name, message_content, created_by, 
                                  schedule_type, schedule_data, repeat_count=1, embed_data=None):
        """Yeni bir zamanlanmış mesaj ekler
        
        Args:
            channel_id (int): Mesajın gönderileceği kanal ID
            channel_name (str): Kanal adı
            message_content (str): Mesaj içeriği
            created_by (int): Oluşturan kullanıcının ID'si
            schedule_type (str): Zamanlama türü ('daily', 'weekly', 'interval_hours', 'specific_time')
            schedule_data (dict): Zamanlama ayarları içeren sözlük
            repeat_count (int): Tekrar sayısı (varsayılan: 1)
            embed_data (dict, optional): Embed verisi (varsa)
            
        Returns:
            int: Eklenen mesajın ID'si
        """
        # JSON formatlarını oluştur
        schedule_data_json = json.dumps(schedule_data, ensure_ascii=False)
        embed_json = json.dumps(embed_data, ensure_ascii=False) if embed_data else None
        
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            INSERT INTO scheduled_messages 
            (channel_id, channel_name, message_content, embed_json, created_by, 
             schedule_type, schedule_data, repeat_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (channel_id, channel_name, message_content, embed_json, created_by, 
                  schedule_type, schedule_data_json, repeat_count))
            
            await self.connection.commit()
            return cursor.lastrowid
            
    async def update_scheduled_message(self, message_id, channel_id=None, channel_name=None, 
                                      message_content=None, schedule_type=None, schedule_data=None, 
                                      repeat_count=None, active=None, embed_data=None):
        """Zamanlanmış mesajı günceller
        
        Args:
            message_id (int): Güncellenecek mesaj ID'si
            ...ve güncellenecek alanlar
            
        Returns:
            bool: Güncelleme başarılı ise True, değilse False
        """
        try:
            # Mevcut veriyi al
            async with self.connection.cursor() as cursor:
                await cursor.execute('SELECT * FROM scheduled_messages WHERE id = ?', (message_id,))
                current = await cursor.fetchone()
                
                if not current:
                    return False
                
                # Update değerlerini hazırla
                params = []
                sql_parts = []
                
                if channel_id is not None:
                    sql_parts.append('channel_id = ?')
                    params.append(channel_id)
                    
                if channel_name is not None:
                    sql_parts.append('channel_name = ?')
                    params.append(channel_name)
                    
                if message_content is not None:
                    sql_parts.append('message_content = ?')
                    params.append(message_content)
                    
                if schedule_type is not None:
                    sql_parts.append('schedule_type = ?')
                    params.append(schedule_type)
                    
                if schedule_data is not None:
                    sql_parts.append('schedule_data = ?')
                    params.append(json.dumps(schedule_data, ensure_ascii=False))
                    
                if repeat_count is not None:
                    sql_parts.append('repeat_count = ?')
                    params.append(repeat_count)
                    
                if active is not None:
                    sql_parts.append('active = ?')
                    params.append(1 if active else 0)
                    
                if embed_data is not None:
                    sql_parts.append('embed_json = ?')
                    params.append(json.dumps(embed_data, ensure_ascii=False))
                
                # SQL sorgusunu tamamla
                if not sql_parts:
                    return True  # Değişiklik yoksa başarılı kabul et
                
                sql = f"UPDATE scheduled_messages SET {', '.join(sql_parts)} WHERE id = ?"
                params.append(message_id)
                
                await cursor.execute(sql, params)
                await self.connection.commit()
                return True
                
        except Exception as e:
            print(f"Zamanlanmış mesaj güncelleme hatası: {e}")
            return False
            
    async def delete_scheduled_message(self, message_id):
        """Zamanlanmış mesajı siler
        
        Args:
            message_id (int): Silinecek mesaj ID'si
            
        Returns:
            bool: Silme başarılı ise True, değilse False
        """
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute('DELETE FROM scheduled_messages WHERE id = ?', (message_id,))
                await self.connection.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Zamanlanmış mesaj silme hatası: {e}")
            return False
            
    async def get_scheduled_message(self, message_id):
        """Belirli bir zamanlanmış mesajı ID'ye göre getirir"""
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT * FROM scheduled_messages WHERE id = ?", (message_id,))
            row = await cursor.fetchone()
            if row:
                message = dict(row)
                message['schedule_data'] = json.loads(message['schedule_data']) if message['schedule_data'] else {}
                if message['embed_json']:
                    message['embed_data'] = json.loads(message['embed_json'])
                else:
                    message['embed_data'] = None
                return message
            return None
            
    async def get_all_scheduled_messages(self, active_only=False):
        """Tüm zamanlanmış mesajları getirir"""
        query = "SELECT * FROM scheduled_messages"
        params = []
        if active_only:
            query += " WHERE active = ?"
            params.append(1)
        query += " ORDER BY created_at DESC"
        
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, params)
            rows = await cursor.fetchall()
            messages = []
            for row in rows:
                message = dict(row)
                message['schedule_data'] = json.loads(message['schedule_data']) if message['schedule_data'] else {}
                if message['embed_json']:
                    message['embed_data'] = json.loads(message['embed_json'])
                else:
                    message['embed_data'] = None
                messages.append(message)
            return messages
            
    async def update_message_sent(self, message_id, last_message_id=None):
        """Mesajın gönderildiğini işaretle
        
        Args:
            message_id (int): Mesaj ID'si
            last_message_id (str, optional): Son gönderilen Discord mesajının ID'si
            
        Returns:
            bool: Güncelleme başarılı ise True, değilse False
        """
        try:
            async with self.connection.cursor() as cursor:
                # Mevcut durumu kontrol et
                await cursor.execute('SELECT sent_count, repeat_count FROM scheduled_messages WHERE id = ?', (message_id,))
                result = await cursor.fetchone()
                
                if not result:
                    return False
                    
                sent_count = result['sent_count'] + 1
                repeat_count = result['repeat_count']
                
                # Maksimum tekrar sayısını aştıysa devre dışı bırak
                active = 1
                if repeat_count > 0 and sent_count >= repeat_count:
                    active = 0
                
                # Gönderim sayısını ve son mesaj ID'sini güncelle
                if last_message_id:
                    await cursor.execute('''
                    UPDATE scheduled_messages 
                    SET sent_count = ?, last_sent = ?, active = ?, last_message_id = ?
                    WHERE id = ?
                    ''', (sent_count, datetime.now(timezone.utc).isoformat(), active, last_message_id, message_id))
                else:
                    await cursor.execute('''
                    UPDATE scheduled_messages 
                    SET sent_count = ?, last_sent = ?, active = ?
                    WHERE id = ?
                    ''', (sent_count, datetime.now(timezone.utc).isoformat(), active, message_id))
                
                await self.connection.commit()
                return True
                
        except Exception as e:
            print(f"Zamanlanmış mesaj gönderim güncelleme hatası: {e}")
            return False

    async def cleanup_old_bump_logs(self, days_to_keep=365):
        """Eski bump loglarını temizler (varsayılan: 1 yıl)
        
        Args:
            days_to_keep (int): Kaç günlük veriyi tutacak (varsayılan 365 gün)
            
        Returns:
            int: Silinen kayıt sayısı
        """
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).isoformat()
        
        async with self.connection.cursor() as cursor:
            # Silinecek kayıt sayısını say
            await cursor.execute('''
            SELECT COUNT(*) FROM bump_logs WHERE bump_time < ?
            ''', (cutoff_date,))
            
            count_to_delete = (await cursor.fetchone())[0]
            
            if count_to_delete > 0:
                # Eski kayıtları sil
                await cursor.execute('''
                DELETE FROM bump_logs WHERE bump_time < ?
                ''', (cutoff_date,))
                
                await self.connection.commit()
                # Bump cleanup completed
            
            return count_to_delete
            
    async def cleanup_old_spam_logs(self, days_to_keep=90):
        """Eski spam loglarını temizler (varsayılan: 3 ay)
        
        Args:
            days_to_keep (int): Kaç günlük veriyi tutacak (varsayılan 90 gün)
            
        Returns:
            int: Silinen kayıt sayısı
        """
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).isoformat()
        
        async with self.connection.cursor() as cursor:
            # Silinecek kayıt sayısını say
            await cursor.execute('''
            SELECT COUNT(*) FROM spam_logs WHERE spam_time < ?
            ''', (cutoff_date,))
            
            count_to_delete = (await cursor.fetchone())[0]
            
            if count_to_delete > 0:
                # Eski spam kayıtlarını sil
                await cursor.execute('''
                DELETE FROM spam_logs WHERE spam_time < ?
                ''', (cutoff_date,))
                
                await self.connection.commit()
                # Spam cleanup completed
            
            return count_to_delete
            
    async def cleanup_all_old_logs(self, spam_days=90, bump_days=365, member_days=90):
        """Tüm eski logları temizler
        
        Args:
            spam_days (int): Spam logları için gün limiti
            bump_days (int): Bump logları için gün limiti
            member_days (int): Member logları için gün limiti
            
        Returns:
            dict: Temizlik sonuçları
        """
        spam_deleted = await self.cleanup_old_spam_logs(spam_days)
        bump_deleted = await self.cleanup_old_bump_logs(bump_days)
        member_deleted = await self.cleanup_old_member_logs(member_days)
        
        return {
            'spam_logs_deleted': spam_deleted,
            'bump_logs_deleted': bump_deleted,
            'member_logs_deleted': member_deleted,
            'total_deleted': spam_deleted + bump_deleted + member_deleted
        }

    async def cleanup_old_member_logs(self, days=90):
        """Eski member loglarını temizler"""
        try:
            from datetime import datetime, timedelta
            import pytz
            
            cutoff_date = datetime.now(pytz.UTC) - timedelta(days=days)
            
            async with self.connection.cursor() as cursor:
                # Silinecek kayıt sayısını al
                await cursor.execute('''
                SELECT COUNT(*) FROM member_logs WHERE timestamp < ?
                ''', (cutoff_date.isoformat(),))
                
                count_to_delete = (await cursor.fetchone())[0]
                
                if count_to_delete > 0:
                    # Eski kayıtları sil
                    await cursor.execute('''
                    DELETE FROM member_logs WHERE timestamp < ?
                    ''', (cutoff_date.isoformat(),))
                    
                    await self.connection.commit()
                
                return count_to_delete
                
        except Exception as e:
            print(f"Member logs temizlik hatası: {e}")
            return 0
            
    async def get_database_size_info(self):
        """Veritabanı boyut bilgilerini getirir
        
        Returns:
            dict: Boyut bilgileri
        """
        async with self.connection.cursor() as cursor:
            # Toplam bump logs sayısı
            await cursor.execute("SELECT COUNT(*) FROM bump_logs")
            total_bump_logs = (await cursor.fetchone())[0]
            
            # Toplam başvuru sayısı
            await cursor.execute("SELECT COUNT(*) FROM staff_applications")
            total_applications = (await cursor.fetchone())[0]
            
            # Toplam scheduled message sayısı
            await cursor.execute("SELECT COUNT(*) FROM scheduled_messages")
            total_scheduled = (await cursor.fetchone())[0]
            
            # Toplam spam logs sayısı
            await cursor.execute("SELECT COUNT(*) FROM spam_logs")
            total_spam_logs = (await cursor.fetchone())[0]
            
            # Toplam member logs sayısı
            await cursor.execute("SELECT COUNT(*) FROM member_logs")
            total_member_logs = (await cursor.fetchone())[0]
            
            # Toplam user notes sayısı
            await cursor.execute("SELECT COUNT(*) FROM user_notes")
            total_user_notes = (await cursor.fetchone())[0]
            
            # Tahmini boyutlar (byte cinsinden)
            estimated_bump_size = total_bump_logs * 104  # ~104 byte per bump
            estimated_app_size = total_applications * 2048  # ~2KB per application
            estimated_msg_size = total_scheduled * 512  # ~512 byte per scheduled message
            estimated_spam_size = total_spam_logs * 256  # ~256 byte per spam log
            estimated_member_size = total_member_logs * 128  # ~128 byte per member log
            estimated_notes_size = total_user_notes * 384  # ~384 byte per user note (ortalama not uzunluğu)
            
            total_estimated = estimated_bump_size + estimated_app_size + estimated_msg_size + estimated_spam_size + estimated_member_size + estimated_notes_size
            
            return {
                'bump_logs_count': total_bump_logs,
                'applications_count': total_applications,
                'scheduled_messages_count': total_scheduled,
                'spam_logs_count': total_spam_logs,
                'member_logs_count': total_member_logs,
                'user_notes_count': total_user_notes,
                'estimated_bump_size_mb': round(estimated_bump_size / (1024 * 1024), 2),
                'estimated_spam_size_mb': round(estimated_spam_size / (1024 * 1024), 2),
                'estimated_member_size_mb': round(estimated_member_size / (1024 * 1024), 2),
                'estimated_total_size_mb': round(total_estimated / (1024 * 1024), 2),
                'estimated_size_human': self._format_bytes(total_estimated)
            }
            
    def _format_bytes(self, bytes_size):
        """Byte boyutunu okunabilir formata çevirir"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"
        
    async def add_presence_snapshot(self, guild_id: int, online_count: int, total_members: int):
        """Anlık online kullanıcı sayısını snapshot olarak kaydeder"""
        current_time = datetime.now(timezone.utc).isoformat()
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            INSERT INTO presence_snapshots (guild_id, snapshot_time, online_count, total_members)
            VALUES (?, ?, ?, ?)
            ''', (guild_id, current_time, online_count, total_members))
            await self.connection.commit()
            return cursor.lastrowid

    async def get_presence_snapshots(self, guild_id: int, start_time: datetime, end_time: datetime):
        """Belirtilen tarih aralığındaki presence snapshot'larını döndürür"""
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT snapshot_time, online_count, total_members
            FROM presence_snapshots
            WHERE guild_id = ? AND snapshot_time >= ? AND snapshot_time < ?
            ORDER BY snapshot_time ASC
            ''', (guild_id, start_time.isoformat(), end_time.isoformat()))
            rows = await cursor.fetchall()
            snapshots = []
            for row in rows:
                snapshots.append({
                    'snapshot_time': row[0],
                    'online_count': row[1],
                    'total_members': row[2]
                })
            return snapshots

    async def add_spam_log(self, user_id, username, guild_id, channel_id, message_content, timeout_applied=True, messages_deleted=3):
        """Spam kaydını veritabanına ekler
        
        Args:
            user_id (int): Kullanıcının Discord ID'si
            username (str): Kullanıcının adı
            guild_id (int): Sunucu ID'si
            channel_id (int): Kanal ID'si
            message_content (str): Spam mesaj içeriği
            timeout_applied (bool): Timeout uygulanıp uygulanmadığı
            messages_deleted (int): Silinen mesaj sayısı
            
        Returns:
            int: Spam kaydının ID'si
        """
        current_time = datetime.now(timezone.utc).isoformat()
        
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            INSERT INTO spam_logs (user_id, username, guild_id, channel_id, message_content, spam_time, timeout_applied, messages_deleted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, guild_id, channel_id, message_content, current_time, timeout_applied, messages_deleted))
            
            await self.connection.commit()
            return cursor.lastrowid
            
    async def get_spam_stats(self, guild_id, period_days=30):
        """Belirtilen periyoda göre spam istatistiklerini getirir
        
        Args:
            guild_id (int): Sunucu ID'si
            period_days (int): Kaç günlük periyod (varsayılan 30)
            
        Returns:
            dict: Spam istatistikleri
        """
        start_time = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
        
        async with self.connection.cursor() as cursor:
            # Toplam spam kayıt sayısı
            await cursor.execute('''
            SELECT COUNT(*) FROM spam_logs 
            WHERE guild_id = ? AND spam_time >= ?
            ''', (guild_id, start_time))
            total_spam = (await cursor.fetchone())[0]
            
            # Spam yapan kullanıcı sayısı
            await cursor.execute('''
            SELECT COUNT(DISTINCT user_id) FROM spam_logs 
            WHERE guild_id = ? AND spam_time >= ?
            ''', (guild_id, start_time))
            spam_users = (await cursor.fetchone())[0]
            
            # En çok spam yapan kullanıcılar
            await cursor.execute('''
            SELECT user_id, username, COUNT(*) as spam_count
            FROM spam_logs 
            WHERE guild_id = ? AND spam_time >= ?
            GROUP BY user_id, username
            ORDER BY spam_count DESC
            LIMIT 10
            ''', (guild_id, start_time))
            
            top_spammers = []
            for row in await cursor.fetchall():
                top_spammers.append({
                    'user_id': row[0],
                    'username': row[1],
                    'spam_count': row[2]
                })
            
            return {
                'total_spam': total_spam,
                'spam_users': spam_users,
                'top_spammers': top_spammers,
                'period_days': period_days
            }
            
    async def add_member_log(self, user_id, username, discriminator, guild_id, action, account_created=None):
        """Üye giriş/çıkış logunu veritabanına ekler
        
        Args:
            user_id (int): Kullanıcının Discord ID'si
            username (str): Kullanıcının adı
            discriminator (str): Kullanıcının discriminator'ı
            guild_id (int): Sunucu ID'si
            action (str): 'join' veya 'leave'
            account_created (datetime, optional): Hesap oluşturma tarihi
            
        Returns:
            int: Log kaydının ID'si
        """
        current_time = datetime.now(timezone.utc).isoformat()
        account_created_str = account_created.isoformat() if account_created else None
        
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            INSERT INTO member_logs (user_id, username, discriminator, guild_id, action, timestamp, account_created, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, discriminator, guild_id, action, current_time, account_created_str, current_time))
            
            await self.connection.commit()
            return cursor.lastrowid
            
    async def get_member_stats_by_period(self, guild_id, start_date, end_date):
        """Belirtilen periyoda göre üye giriş/çıkış istatistiklerini getirir
        
        Args:
            guild_id (int): Sunucu ID'si
            start_date (datetime): Başlangıç tarihi
            end_date (datetime): Bitiş tarihi
            
        Returns:
            dict: Üye istatistikleri
        """
        start_time_str = start_date.isoformat()
        end_time_str = end_date.isoformat()
        
        async with self.connection.cursor() as cursor:
            # Giriş sayısı
            await cursor.execute('''
            SELECT COUNT(*) FROM member_logs 
            WHERE guild_id = ? AND action = 'join' AND timestamp >= ? AND timestamp < ?
            ''', (guild_id, start_time_str, end_time_str))
            joins = (await cursor.fetchone())[0]
            
            # Çıkış sayısı
            await cursor.execute('''
            SELECT COUNT(*) FROM member_logs 
            WHERE guild_id = ? AND action = 'leave' AND timestamp >= ? AND timestamp < ?
            ''', (guild_id, start_time_str, end_time_str))
            leaves = (await cursor.fetchone())[0]
            
            # Net değişim
            net_change = joins - leaves
            
            return {
                'joins': joins,
                'leaves': leaves,
                'net_change': net_change,
                # Son aktiviteler kaldırıldı
            }
    
    async def add_user_note(self, user_id, username, discriminator, note_content, created_by, created_by_username, guild_id):
        """Kullanıcı hakkında not ekler"""
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            INSERT INTO user_notes (user_id, username, discriminator, note_content, created_by, created_by_username, guild_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, discriminator, note_content, created_by, created_by_username, guild_id))
            
            note_id = cursor.lastrowid
            await self.connection.commit()
            return note_id
    
    async def get_user_notes(self, user_id, guild_id, limit=50, offset=0):
        """Belirli bir kullanıcının notlarını getirir"""
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT id, user_id, username, discriminator, note_content, created_by, created_by_username, 
                   created_at, updated_at
            FROM user_notes 
            WHERE user_id = ? AND guild_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            ''', (user_id, guild_id, limit, offset))
            
            notes = []
            for row in await cursor.fetchall():
                notes.append({
                    'id': row[0],
                    'user_id': row[1],
                    'username': row[2],
                    'discriminator': row[3],
                    'note_content': row[4],
                    'created_by': row[5],
                    'created_by_username': row[6],
                    'created_at': row[7],
                    'updated_at': row[8]
                })
            return notes
    
    async def get_user_notes_count(self, user_id, guild_id):
        """Belirli bir kullanıcının toplam not sayısını döndürür"""
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT COUNT(*) FROM user_notes WHERE user_id = ? AND guild_id = ?
            ''', (user_id, guild_id))
            return (await cursor.fetchone())[0]
    
    async def get_note_by_id(self, note_id, guild_id):
        """ID'ye göre belirli bir notu getirir"""
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT id, user_id, username, discriminator, note_content, created_by, created_by_username, 
                   created_at, updated_at
            FROM user_notes 
            WHERE id = ? AND guild_id = ?
            ''', (note_id, guild_id))
            
            row = await cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'user_id': row[1],
                    'username': row[2],
                    'discriminator': row[3],
                    'note_content': row[4],
                    'created_by': row[5],
                    'created_by_username': row[6],
                    'created_at': row[7],
                    'updated_at': row[8]
                }
            return None
    
    async def update_user_note(self, note_id, new_content, guild_id):
        """Mevcut bir notu günceller"""
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            UPDATE user_notes 
            SET note_content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND guild_id = ?
            ''', (new_content, note_id, guild_id))
            
            affected_rows = cursor.rowcount
            await self.connection.commit()
            return affected_rows > 0
    
    async def delete_user_note(self, note_id, guild_id):
        """Belirli bir notu siler"""
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            DELETE FROM user_notes WHERE id = ? AND guild_id = ?
            ''', (note_id, guild_id))
            
            affected_rows = cursor.rowcount
            await self.connection.commit()
            return affected_rows > 0
    
    async def search_user_notes(self, search_term, guild_id, limit=50, offset=0):
        """Kullanıcı adı veya not içeriğinde arama yapar"""
        async with self.connection.cursor() as cursor:
            search_pattern = f"%{search_term}%"
            await cursor.execute('''
            SELECT id, user_id, username, discriminator, note_content, created_by, created_by_username, 
                   created_at, updated_at
            FROM user_notes 
            WHERE guild_id = ? AND (username LIKE ? OR note_content LIKE ?)
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            ''', (guild_id, search_pattern, search_pattern, limit, offset))
            
            notes = []
            for row in await cursor.fetchall():
                notes.append({
                    'id': row[0],
                    'user_id': row[1],
                    'username': row[2],
                    'discriminator': row[3],
                    'note_content': row[4],
                    'created_by': row[5],
                    'created_by_username': row[6],
                    'created_at': row[7],
                    'updated_at': row[8]
                })
            return notes
    
    async def get_all_user_notes(self, guild_id, limit=50, offset=0):
        """Sunucudaki tüm notları getirir (yönetici paneli için)"""
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT id, user_id, username, discriminator, note_content, created_by, created_by_username, 
                   created_at, updated_at
            FROM user_notes 
            WHERE guild_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            ''', (guild_id, limit, offset))
            
            notes = []
            for row in await cursor.fetchall():
                notes.append({
                    'id': row[0],
                    'user_id': row[1],
                    'username': row[2],
                    'discriminator': row[3],
                    'note_content': row[4],
                    'created_by': row[5],
                    'created_by_username': row[6],
                    'created_at': row[7],
                    'updated_at': row[8]
                })
            return notes
    
    async def get_total_notes_count(self, guild_id):
        """Sunucudaki toplam not sayısını döndürür"""
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
            SELECT COUNT(*) FROM user_notes WHERE guild_id = ?
            ''', (guild_id,))
            return (await cursor.fetchone())[0]
    
    async def get_notes_stats(self, guild_id):
        """Not istatistiklerini döndürür"""
        async with self.connection.cursor() as cursor:
            # Toplam not sayısı
            await cursor.execute('SELECT COUNT(*) FROM user_notes WHERE guild_id = ?', (guild_id,))
            total_notes = (await cursor.fetchone())[0]
            
            # Notlu kullanıcı sayısı
            await cursor.execute('SELECT COUNT(DISTINCT user_id) FROM user_notes WHERE guild_id = ?', (guild_id,))
            unique_users = (await cursor.fetchone())[0]
            
            # En aktif not ekleyen admin
            await cursor.execute('''
            SELECT created_by_username, COUNT(*) as note_count 
            FROM user_notes WHERE guild_id = ?
            GROUP BY created_by_username 
            ORDER BY note_count DESC LIMIT 1
            ''', (guild_id,))
            
            top_admin_row = await cursor.fetchone()
            top_admin = top_admin_row[0] if top_admin_row else "Yok"
            top_admin_count = top_admin_row[1] if top_admin_row else 0
            
            # Bu hafta eklenen not sayısı
            from datetime import datetime, timedelta
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            await cursor.execute('''
            SELECT COUNT(*) FROM user_notes 
            WHERE guild_id = ? AND created_at >= ?
            ''', (guild_id, week_ago))
            weekly_notes = (await cursor.fetchone())[0]
            
            return {
                'total_notes': total_notes,
                'unique_users': unique_users,
                'top_admin': top_admin,
                'top_admin_count': top_admin_count,
                'weekly_notes': weekly_notes
            }





# Singleton pattern - tek bir veritabanı örneği
db = Database()

async def get_db():
    """Veritabanı bağlantısını döndürür, gerekirse yeni bağlantı kurar"""
    if db.connection is None:
        await db.connect()
    return db 