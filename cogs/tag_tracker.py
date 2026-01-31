"""
Tag Tracker Cog
Discord kullanıcılarının clan tag'lerini takip eder ve ilgili rolü verir/alır.
"""

import asyncio
import time
from collections import deque
from typing import Optional

import aiohttp
import discord
from discord.ext import commands, tasks


class TagTracker(commands.Cog):
    """
    Kullanıcıların Discord profilindeki clan tag'ini takip eder.
    Tag eşleşen kullanıcılara otomatik olarak rol verir,
    tag eşleşmeyen veya bırakan kullanıcılardan rolü alır.
    """

    # =========================
    # AYARLAR
    # =========================
    GUILD_ID = 1029088146752815138  # HydRaboN sunucu ID'si
    TAG_ROLE_ID = 1467145841830789367  # Tag rolü ID'si
    TARGET_TAG = "HRN"  # Hedef clan tag'i

    # Online üyeler: her 10 saniyede bir kontrol
    HOT_INTERVAL = 10  # saniye
    HOT_COOLDOWN = 10  # bir kullanıcı en fazla 10 sn'de 1 kontrol

    # Offline üyeler: tüm offline seti ~30 dakikada bir tamamlanacak şekilde round-robin
    OFFLINE_FULL_SCAN_SECONDS = 30 * 60  # 30 dakika
    OFFLINE_TICK = 30  # her 30 sn'de bir offline batch işle

    # HTTP istekleri için düşük concurrency (rate-limit'e saygılı)
    WORKERS = 3

    API_VERSION = "10"
    BASE = f"https://discord.com/api/v{API_VERSION}"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None

        self.guild: Optional[discord.Guild] = None
        self.tag_role: Optional[discord.Role] = None

        # Presence takip
        self.online_ids: set[int] = set()

        # Offline round-robin kuyruğu
        self.offline_queue: deque[int] = deque()

        # Kontrol throttling
        self.last_checked: dict[int, float] = {}

        # İş kuyruğu + in-flight dedupe
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self.in_flight: set[int] = set()

        self._tasks: list[asyncio.Task] = []
        self._initialized = False

    async def cog_load(self):
        """Cog yüklendiğinde çalışır"""
        # Bot token'ını al
        import os
        from dotenv import load_dotenv
        load_dotenv()
        token = os.getenv('TOKEN')
        
        self.session = aiohttp.ClientSession(
            headers={"Authorization": f"Bot {token}"}
        )

    async def cog_unload(self):
        """Cog kaldırıldığında çalışır"""
        # Tüm task'ları iptal et
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        
        # HTTP session'ı kapat
        if self.session:
            await self.session.close()
            self.session = None
        
        self._initialized = False

    # -------------------------
    # Rate-limit safe GET
    # -------------------------
    async def discord_get_json(self, url: str):
        """Discord API'den JSON veri çeker, rate-limit'e uyumlu"""
        if self.session is None:
            return None
            
        try:
            while True:
                async with self.session.get(url) as resp:
                    if resp.status == 429:
                        data = await resp.json()
                        retry_after = float(data.get("retry_after", 1.0))
                        await asyncio.sleep(retry_after)
                        continue

                    if resp.status != 200:
                        return None

                    data = await resp.json()

                    # Header tabanlı yumuşak fren
                    rem = resp.headers.get("X-RateLimit-Remaining")
                    reset_after = resp.headers.get("X-RateLimit-Reset-After")
                    try:
                        if rem is not None and reset_after is not None and float(rem) <= 0:
                            await asyncio.sleep(float(reset_after))
                    except ValueError:
                        pass

                    return data
        except Exception as e:
            print(f"[TagTracker] API isteği hatası: {e}")
            return None

    # -------------------------
    # Presence: online set güncelle
    # -------------------------
    def _status_is_online(self, status: discord.Status) -> bool:
        """Kullanıcının online olup olmadığını kontrol eder"""
        return status in (discord.Status.online, discord.Status.idle, discord.Status.dnd)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """Presence güncellemelerini dinler"""
        if not self._initialized:
            return
            
        if after.bot:
            return
            
        if after.guild.id != self.GUILD_ID:
            return
            
        if self._status_is_online(after.status):
            self.online_ids.add(after.id)
        else:
            self.online_ids.discard(after.id)
            # offline'a düştüyse offline queue'ya ekle
            self.offline_queue.append(after.id)

    # -------------------------
    # Kullanıcıyı kuyruğa "safe" ekle
    # -------------------------
    async def enqueue_if_due(self, user_id: int, cooldown: float):
        """Kullanıcıyı kontrol kuyruğuna ekler (cooldown kontrolü ile)"""
        now = time.time()
        last = self.last_checked.get(user_id, 0)
        if now - last < cooldown:
            return
        if user_id in self.in_flight:
            return

        self.in_flight.add(user_id)
        await self.queue.put(user_id)

    # -------------------------
    # Worker: tek kullanıcı kontrol + rol ver/al
    # -------------------------
    async def worker(self, wid: int):
        """Kullanıcıların tag'lerini kontrol eden worker"""
        if self.guild is None or self.tag_role is None:
            return

        while True:
            try:
                user_id = await self.queue.get()
                try:
                    member = self.guild.get_member(user_id)
                    if member is None or member.bot:
                        continue

                    user_json = await self.discord_get_json(f"{self.BASE}/users/{user_id}")
                    if not user_json:
                        continue

                    clan = user_json.get("clan") or {}
                    has_tag = (clan.get("tag") == self.TARGET_TAG)

                    if has_tag and self.tag_role not in member.roles:
                        try:
                            await member.add_roles(self.tag_role, reason="Clan tag eşleşti")
                        except discord.Forbidden:
                            print(f"[TagTracker] Rol verme yetkisi yok: {member.id}")
                        except Exception as e:
                            print(f"[TagTracker] Rol verme hatası ({member.id}): {e}")
                    elif (not has_tag) and (self.tag_role in member.roles):
                        try:
                            await member.remove_roles(self.tag_role, reason="Clan tag eşleşmedi")
                        except discord.Forbidden:
                            print(f"[TagTracker] Rol alma yetkisi yok: {member.id}")
                        except Exception as e:
                            print(f"[TagTracker] Rol alma hatası ({member.id}): {e}")

                    self.last_checked[user_id] = time.time()

                except Exception as e:
                    print(f"[TagTracker Worker {wid}] Hata: {e}")
                finally:
                    self.in_flight.discard(user_id)
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[TagTracker Worker {wid}] Kritik hata: {e}")

    # -------------------------
    # Online döngü (HOT)
    # -------------------------
    async def hot_loop(self):
        """Online kullanıcıları sık sık kontrol eden döngü"""
        while True:
            try:
                # snapshot al (set iterasyonu sırasında değişmesin)
                ids = list(self.online_ids)

                for uid in ids:
                    await self.enqueue_if_due(uid, cooldown=self.HOT_COOLDOWN)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[TagTracker] Hot loop hatası: {e}")

            await asyncio.sleep(self.HOT_INTERVAL)

    # -------------------------
    # Offline döngü (COLD, round-robin)
    # -------------------------
    async def cold_loop(self):
        """Offline kullanıcıları periyodik olarak kontrol eden döngü"""
        while True:
            try:
                if not self.offline_queue:
                    await asyncio.sleep(self.OFFLINE_TICK)
                    continue

                # "30 dakikada hepsini bitir" hedefi
                offline_ids_unique = list(dict.fromkeys(self.offline_queue))
                offline_count = len(offline_ids_unique)
                ticks = max(1, int(self.OFFLINE_FULL_SCAN_SECONDS / self.OFFLINE_TICK))
                batch = max(1, (offline_count + ticks - 1) // ticks)

                # batch kadar popla, online olanı skip et
                for _ in range(batch):
                    if not self.offline_queue:
                        break
                    uid = self.offline_queue.popleft()
                    if uid in self.online_ids:
                        continue
                    await self.enqueue_if_due(uid, cooldown=self.OFFLINE_TICK)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[TagTracker] Cold loop hatası: {e}")

            await asyncio.sleep(self.OFFLINE_TICK)

    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda tag tracker'ı başlat"""
        if self._initialized:
            return

        self.guild = self.bot.get_guild(self.GUILD_ID)
        if not self.guild:
            print(f"[TagTracker] Hata: Guild bulunamadı (ID: {self.GUILD_ID})")
            return

        self.tag_role = self.guild.get_role(self.TAG_ROLE_ID)
        if not self.tag_role:
            print(f"[TagTracker] Hata: Rol bulunamadı (ID: {self.TAG_ROLE_ID})")
            return

        # Üyeleri çek ve online/offline kuyruklarını kur
        try:
            async for m in self.guild.fetch_members(limit=None):
                if m.bot:
                    continue
                if self._status_is_online(m.status):
                    self.online_ids.add(m.id)
                else:
                    self.offline_queue.append(m.id)
        except Exception as e:
            print(f"[TagTracker] Üye çekme hatası: {e}")
            return

        # Worker'ları başlat
        for i in range(self.WORKERS):
            task = asyncio.create_task(self.worker(i))
            self._tasks.append(task)

        # Loop'ları başlat
        self._tasks.append(asyncio.create_task(self.hot_loop()))
        self._tasks.append(asyncio.create_task(self.cold_loop()))

        self._initialized = True


async def setup(bot: commands.Bot):
    """Cog'u bot'a ekler"""
    await bot.add_cog(TagTracker(bot))
