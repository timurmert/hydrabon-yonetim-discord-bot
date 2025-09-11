import discord
from discord.ext import commands, tasks
import psutil
import datetime
import pytz


class SystemMonitor(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Sabitler / Ayarlar
        self.ALERT_CHANNEL_ID = 1362825668965957845  # yk-sohbet
        self.turkey_tz = pytz.timezone('Europe/Istanbul')

        # Eşik değerler
        self.CPU_THRESHOLD = 85.0  # %
        self.RAM_THRESHOLD = 80.0  # %
        self.DISK_THRESHOLD = 90.0  # % (en dolu bölüm)

        # Kontrol aralığı ve uyarı soğuma süresi
        self.CHECK_INTERVAL_SECONDS = 120  # saniye
        self.ALERT_COOLDOWN_SECONDS = 1800  # saniye (30 dk)
        self.REQUIRED_CONSECUTIVE_BREACHES = 2  # ardışık ihlal sayısı (gürültüyü azaltır)

        # Durum takibi
        self._last_alert_times = {"cpu": None, "ram": None, "disk": None}
        self._consecutive_breach_counts = {"cpu": 0, "ram": 0, "disk": 0}

        # Görevi başlat
        self.system_check_task.start()

    def cog_unload(self):
        self.system_check_task.cancel()

    def _now(self) -> datetime.datetime:
        return datetime.datetime.now(self.turkey_tz)

    def _should_alert(self, metric_key: str) -> bool:
        last = self._last_alert_times.get(metric_key)
        if last is None:
            return True
        return (self._now() - last).total_seconds() >= self.ALERT_COOLDOWN_SECONDS

    def _mark_alert(self, metric_key: str) -> None:
        self._last_alert_times[metric_key] = self._now()
        self._consecutive_breach_counts[metric_key] = 0

    def _get_disk_usage_percent(self) -> float:
        max_percent = 0.0
        try:
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    if usage.percent > max_percent:
                        max_percent = float(usage.percent)
                except Exception:
                    # Erişim hataları veya desteklenmeyen bölümler göz ardı edilir
                    continue
        except Exception:
            pass

        if max_percent <= 0.0:
            # Genel kök kullanımına geri dönüş (platforma göre çalışır)
            try:
                usage = psutil.disk_usage('/')
                max_percent = float(usage.percent)
            except Exception:
                max_percent = 0.0

        return max_percent

    @tasks.loop(seconds=60)
    async def system_check_task(self):
        # Kanala erişim
        channel = self.bot.get_channel(self.ALERT_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(self.ALERT_CHANNEL_ID)
            except Exception:
                return

        # Anlık ölçümler
        try:
            cpu_percent = float(psutil.cpu_percent(interval=0.0))
        except Exception:
            cpu_percent = 0.0

        try:
            ram_percent = float(psutil.virtual_memory().percent)
        except Exception:
            ram_percent = 0.0

        try:
            disk_percent = self._get_disk_usage_percent()
        except Exception:
            disk_percent = 0.0

        # İhlal kontrolü (ardışık N ölçüm şartı + cooldown)
        triggered_keys = []

        if cpu_percent >= self.CPU_THRESHOLD:
            self._consecutive_breach_counts["cpu"] += 1
            if self._consecutive_breach_counts["cpu"] >= self.REQUIRED_CONSECUTIVE_BREACHES and self._should_alert("cpu"):
                triggered_keys.append("cpu")
        else:
            self._consecutive_breach_counts["cpu"] = 0

        if ram_percent >= self.RAM_THRESHOLD:
            self._consecutive_breach_counts["ram"] += 1
            if self._consecutive_breach_counts["ram"] >= self.REQUIRED_CONSECUTIVE_BREACHES and self._should_alert("ram"):
                triggered_keys.append("ram")
        else:
            self._consecutive_breach_counts["ram"] = 0

        if disk_percent >= self.DISK_THRESHOLD:
            self._consecutive_breach_counts["disk"] += 1
            if self._consecutive_breach_counts["disk"] >= self.REQUIRED_CONSECUTIVE_BREACHES and self._should_alert("disk"):
                triggered_keys.append("disk")
        else:
            self._consecutive_breach_counts["disk"] = 0

        if not triggered_keys:
            return

        # Uyarı gönder
        embed = discord.Embed(
            title="⚠️ Sistem Kaynak Uyarısı",
            description="Sunucu kaynak kullanım eşikleri aşıldı.",
            color=discord.Color.orange(),
            timestamp=self._now()
        )

        embed.add_field(name="CPU Kullanımı", value=f"{cpu_percent:.1f}% (eşik {self.CPU_THRESHOLD:.0f}%)", inline=True)
        embed.add_field(name="RAM Kullanımı", value=f"{ram_percent:.1f}% (eşik {self.RAM_THRESHOLD:.0f}%)", inline=True)
        embed.add_field(name="Disk Kullanımı", value=f"{disk_percent:.1f}% (eşik {self.DISK_THRESHOLD:.0f}%)", inline=True)

        try:
            await channel.send(embed=embed)
            for key in triggered_keys:
                self._mark_alert(key)
        except Exception:
            # Mesaj gönderilemezse sessizce geç
            pass

    @system_check_task.before_loop
    async def before_system_check_task(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(SystemMonitor(bot))


