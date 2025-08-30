Import os
Import io
Import json
Import time
Import uuid
Import hmac
Import hashlib
Import asyncio
Import datetime
Import requests
Import aiofiles
 from typing import Optional, Dict, List
 
 Import discord
 from discord import app_commands
 from discord.ext import commands, tasks
 
 # --------- ENV / CONFIG ---------
 BOT_TOKEN = os.getenv("BOT_TOKEN", ")
 if not BOT_TOKEN:
 print("BOT_TOKEN missing")
 raise SystemExit(1)
 
 GUILD_ID = int(os.getenv("GUILD_ID", "0"))
 ROLE_ID = int(os.getenv("ROLE_ID", "0") or 0)
 ROLE_NAME = os.getenv("ROLE_NAME", "activated key")
 OWNER_ROLE_ID = int(os.getenv("OWNER_ROLE_ID", "0") or 0)
 
 BACKUP_CHANNEL_ID = int(os.getenv("BACKUP_CHANNEL_ID", "0") or 0)
 BACKUP_WEBHOOK_URL = os.getenv("BACKUP_WEBHOOK_URL", ")
 AUTO_RESTORE_ON_START = os.getenv("AUTO_RESTORE_ON_START", "true").lower() in ("1", "true", "yes")
 BACKUP_INTERVAL_MIN = int(os.getenv("BACKUP_INTERVAL_MIN", "60") or 60)
 
 AUTOBUY_CHANNEL_ID = int(os.getenv("AUTOBUY_CHANNEL_ID", "0") or 0)
 NWP_API_KEY = os.getenv("NWP_API_KEY", ")
 NWP_IPN_SECRET = os.getenv("NWP_IPN_SECRET", ")
 
 PURCHASE_LOG_WEBHOOK = os.getenv("PURCHASE_LOG_WEBHOOK", ")
 IP_TRACK_WEBHOOK = os.getenv("IP_TRACK_WEBHOOK", ")
 
 DATA_DIR = os.getenv("DATA_DIR", ".")
 os.makedirs (DATA_DIR, exist_ok=True)
 KEYS_FILE = os.path.join(DATA_DIR, "keys.json")
 USAGE_FILE = os.path.join(DATA_DIR, "key_usage.json")
 DELETED_KEYS_FILE = os.path.join (DATA_DIR, "deleted_keys.json")
 LOGS_FILE = os.path.join(DATA_DIR, "key_logs.json")
 STATS_FILE = os.path.join(DATA_DIR, "selfbot_message_stats.json")
 
 MESSAGE_STATS: Dict[str, int] = {}
 try:
 if os.path.exists (STATS_FILE):
 with open(STATS_FILE, "r") as f:
 MESSAGE_STATS = json.load(f) or {}
 Except Exception:
 MESSAGE_STATS = {}
 
 intents = discord.Intents.default()
 intents.guilds = True
 intents.members = True
 intents.message_content = True
 bot = commands.Bot(command_prefix=None, intents=intents, help_command=None)
 
 # --------- HELPERS ---------
 def now_ts() -> int:
 return inttime.time()
 
 def normalize_key(raw: Optional[str]) -> str:
 if not raw:
 return ""
 k = raw.strip()
 if k.startswith("`") and k.endswith("`") and len(k) >= 2:
 k = k[1:-1]
 return k.strip()
 
 def atomic_json_write(path: str, data):
 tmp = f"{path}.tmp"
 with open(tmp, "w") as f:
 json.dump(data, f, indent=2)
 os.replace (tmp, path)
 
 async def safe_followup(inter: discord.Interaction, content=None, embedded=None, ephemeral=True):
 try:
 if inter.response.is_done():
 await inter.followup.send(content=content, embedded=embed, ephemeral=ephemeral)
 else:
 await inter.response.send_message(content=content, embedded=embed, ephemeral=ephemeral)
 Except Exception:
 pass
 
 def pay_currency_map(code: str) -> str:
 code = (code or "").lower()
 return {
 "usdc": "usdcpoly",
 "usdt": "usdttrc20",
 "btc": "btc",
 "eth": "eth",
 "ltc": "ltc",
 "sol": "sol",
 }.get(code, code)
 
 # -------- KEY MANAGER ---------
 class KeyManager:
 def __init__(self):
 self.keys: dict = {}
 self.key_usage: dict = {}
 self.deleted_keys: dict = {}
 self.key_logs: list[dict] = []
 self.load()
 
 def load(self):
 try:
 if os.path.exists (KEYS_FILE):
 with open(KEYS_FILE, "r") as f:
 self.keys = json.load(f) or {}
 if os.path.exists (USAGE_FILE):
 with open(USAGE_FILE, "r") as f:
 self.key_usage = json.load(f) or {}
 if os.path.exists (DELETED_KEYS_FILE):
 with open (DELETED_KEYS_FILE, "r") as f:
 self.deleted_keys = json.load(f) or {}
 if os.path.exists (LOGS_FILE):
 with open(LOGS_FILE, "r") as f:
 self.key_logs = json.load(f) or []
 Except Exception as e:
 print("load error:", e)
 self.keys, self.key_usage, self.deleted_keys, self.key_logs = {}, {}, {}, []
 
 def save(self):
 try:
 atomic_json_write(KEYS_FILE, self.keys)
 atomic_json_write(USAGE_FILE, self.key_usage)
 atomic_json_write(DELETED_KEYS_FILE, self.deleted_keys)
 atomic_json_write(LOGS_FILE, self.key_logs)
 Except Exception as e:
 print("save error:", e)
 
 def add_log(self, event: str, key: str, user_id: Optional[int] = None, details: Optional[dict] = None):
 try:
 self.key_logs.append({"ts": now_ts(), "event": event, "key": key, "user_id": user_id, "details": details or {}})
 if len(self.key_logs) > 1000:
 self.key_logs = self.key_logs[-1000:]
 Except Exception:
 pass
 
 def build_backup_payload(self) -> dict:
 return {"timestamp": now_ts(), "keys": self.keys, "usage": self.key_usage, "deleted": self.deleted_keys, "logs": self.key_logs}
 
 def generate(self, created_by: int, channel_id: Optional[int], duration_days: int) -> str:
 key = str(uuid.uuid4())
 self.keys[key] = {
 "user_id": 0, "channel_id": channel_id, "created_time": now_ts(),
 "activation_time": None, "expiration_time": None, "duration_days": int(duration_days),
 "key_type": "general", "is_active": True, "machine_id": None, "activated_by": None, "created_by": int(created_by)
 }
 self.key_usage[key] = {"created": now_ts(), "activated": None, "last_used": None, "usage_count": 0}
 self.add_log("generate", key, created_by, {"duration_days": duration_days, "channel_id": channel_id})
 self.save()
 Return key
 
 def generate_bulk(self, daily: int, weekly: int, monthly: int, lifetime: int) -> dict:
 def add(count: int, days: int, label: str):
 for _ in range(count):
 k = str(uuid.uuid4())
 self.keys[k] = {
 "user_id": 0, "channel_id": None, "created_time": now_ts(), "activation_time": None,
 "expiration_time": None, "duration_days": days, "key_type": label, "is_active": True,
 "machine_id": None, "activated_by": None, "created_by": 0
 }
 self.key_usage[k] = {"created": now_ts(), "activated": None, "last_used": None, "usage_count": 0}
 out[label].append(k)
 out = {"daily": [], "weekly": [], "monthly": [], "lifetime": []}
 add(daily, 1, "daily")
 add (weekly, 7, "weekly")
 add (monthly, 30, "monthly")
 add (lifetime, 365, "lifetime")
 self.add_log("generate_bulk", "-", None, {"counts": {k: len(v) for k, v in out.items()}})
		self.save()
 Return out
 
 def activate(self, key: str, machine_id: str, user_id: int) -> dict:
 key = normalize_key(key)
 If key not in self.keys:
 return {"success": False, "error": "Invalid key"}
 d = self.keys[key]
 If not d.get("is_active", False):
 return {"success": False, "error": "Access revoked"}
 if d.get("machine_id") and d["machine_id"] ! = machine_id:
 return {"success": False, "error": "Key is already activated on another machine"}
 if d.get("expiration_time") and d["expiration_time"] < now_ts():
 return {"success": False, "error": "Key has expired"}
 d["machine_id"] = machine_id
 d["activated_by"] = int(user_id)
 d["user_id"] = int(user_id)
 if not d.get("activation_time"):
 d["activation_time"] = now_ts()
 if not d.get("expiration_time"):
 d["expiration_time"] = now_ts() + int(d.get("duration_days", 30)) * 86400
 if key in self.key_usage:
 self.key_usage[key]["activated"] = now_ts()
 self.key_usage[key]["last_used"] = now_ts()
 self.key_usage[key]["usage_count"] = int(self.key_usage[key].get("usage_count", 0)) + 1
 self.add_log("activate", key, user_id, {"machine_id": machine_id, "expires": d["expiration_time"]})
 self.save()
 return {"success": True, "expiration_time": d["expiration_time"], "channel_id": d.get("channel_id")}
 
 def revoke(self, key: str) -> bool:
 if key in self.keys:
 self.keys[key]["is_active"] = False
 self.add_log("revoke", key)
 self.save()
 Return True
 Return False
 
 def unrevoke(self, key: str) -> bool:
 if key in self.keys:
 self.keys[key]["is_active"] = True
 self.add_log("unrevoke", key)
 self.save()
 Return True
 Return False
 
 def delete(self, key: str) -> bool:
 if key in self.keys:
 rep = self.keys[key].copy()
 rep["deleted_at"] = now_ts()
 self.deleted_keys[key] = rep
 del self.keys[key]
 if key in self.key_usage:
 del self.key_usage[key]
 self.add_log("delete", key)
 self.save()
 Return True
 Return False
 
 def info(self, key: str) -> Optional[dict]:
 if key in self.keys:
 data = self.keys[key].copy()
 if key in self.key_usage:
 data.update(self.key_usage[key])
 Return data
 Return None
 
 def user_keys(self, user_id: int) -> dict:
 out = {}
 for k, d in self.keys.items():
 if int(d.get("created_by", 0)) == int(user_id):
 info = d.copy()
 if k in self.key_usage:
 info.update(self.key_usage[k])
 out[k] = info
 Return out
 
 def available_by_type(self) -> dict:
 out = {"daily": [], "weekly": [], "monthly": [], "lifetime": []}
 for k, d in self.keys.items():
 if d.get("is_active") and int(d.get("user_id", 0)) == 0:
 item = {"key": k, "created": d.get("created_time") or 0, "expires": d.get("expiration_time") or 0}
 lbl = d.get("key_type", "general")
 if lbl in out:
 out[lbl].append(item)
 Return out
 
 key_manager = KeyManager()
 
 # --------- PERMS ----------
 def admin_role_only():
 async def predicate(inter: discord.Interaction) -> bool:
 try:
 if not inter.guild or inter.guild.id! = GUILD_ID:
 Return False
 member = inter.user if isinstance(inter.user, discord.Member) else inter.guild.get_member(inter.user.id)
 return bool (member and any (getattr(r, "id", 0) == OWNER_ROLE_ID for r in getattr (member, "roles", [])))
 Except Exception:
 Return False
 return app_commands.check (predicate)
 
 # --------- BACKUPS ----------
 async def upload_backup(payload: dict):
 try:
 if BACKUP_CHANNEL_ID > 0:
 ch = bot.get_channel (BACKUP_CHANNEL_ID)
 if ch:
 b = json.dumps(payload, indent=2).encode()
 await ch.send(file=discord.File(io.BytesIO(b), filename=f"backup_{now_ts()}.json")
 Except Exception:
 pass
 try:
 if BACKUP_WEBHOOK_URL:
 b = json.dumps(payload, indent=2).encode()
 requests.post(BACKUP_WEBHOOK_URL, files={"file": (f"backup_{now_ts()}.json", io.BytesIO(b), "application/json")}, timeout=10)
 Except Exception:
 pass
 
 @tasks.loop(minutes=BACKUP_INTERVAL_MIN)
 async def periodic_backup_task():
 try:
 await upload_backup(key_manager.build_backup_payload()
 Except Exception:
 pass
 
 # --------- READY ----------
 @bot.event
 async def on_ready():
 print(f"✅ {bot.user} online")
 try:
 gobj = discord.Object(id=GUILD_ID)
 await bot.tree.sync (guild=gobj)
 print ("guild commands synced")
 Except Exception as e:
 print("sync error:", e)
 try:
 if BACKUP_CHANNEL_ID and not periodic_backup_task.is_running():
 periodic_backup_task.start()
 Except Exception:
 pass
 if AUTO_RESTORE_ON_START and BACKUP_CHANNEL_ID:
 try:
 ch = bot.get_channel (BACKUP_CHANNEL_ID)
 if ch:
 async for m in ch.history(limit=50):
 for att in m.attachments:
 If att.filename.lower().endswith(".json"):
 try:
 data = await att.read()
 pl = json.loads (data.decode ("utf-8"))
 If isinstance(pl, dict):
 key_manager.keys = pl.get("keys") or {}
 key_manager.key_usage = pl.get("usage") or {}
 key_manager.deleted_keys = pl.get("deleted") or {}
 key_manager.key_logs = pl.get("logs") or []
 key_manager.save()
 print ("snail ️ restored from channel backup")
 raise StopAsyncIteration
 Except Exception:
 pass
 except StopAsyncIteration:
 pass
 Except Exception:
 pass
 
 # --------- ERROR ----------
 @bot.tree.error
 async def on_app_command_error(inter: discord.Interaction, error: discord.app_commands.AppCommandError):
 try:
 if not inter.response.is_done():
 try: await inter.response.defer (ephemeral=True)
 Except Exception: pass
 await inter.followup.send(f"❌ {error.__class__.__name__}", ephemeral=True)
 Except Exception:
 pass
 
 # -------- SLASH: KEYS ----------
 @app_commands.guilds(discord.Object(id=GUILD_ID))
 @bot.tree.command(name="activate_key", description="Activate key and get role")
 async def activate_key(inter: discord.Interaction, key: str):
 try:
 await inter.response.defer (ephemeral=True)
 res = key_manager.activate(key, str(inter.user.id), int(inter.user.id))
 If not res.get("success"):
			await inter.followup.send(f"❌ {res.get('error')}", ephemeral=True); return
 try:
 role = inter.build.get_role(ROLE_ID) or discord.utils.find(lambda r: r.name.lower()==ROLE_NAME.lower(), inter.build.roles)
 If role and role not in inter.user.roles:
 await inter.user.add_roles(role, reason="Key activated")
 Except Exception:
 pass
 try:
 await upload_backup(key_manager.build_backup_payload())
 Except Exception:
 pass
 em = discord.Embed(title="🔑 Activated", color=0x22C55E)
 em.add_field(name="Expires", value=f"<t:{res['expiration_time']}:R>")
 await inter.followup.send(embed=em, ephemeral=True)
 Except Exception as e:
 await inter.followup.send(f"❌ Error: {e}", ephemeral=True)
 
 @app_commands.guilds(discord.Object(id=GUILD_ID))
 @admin_role_only()
 @bot.tree.command(name="revoke_key", description="Revoke a key")
 async def revoke_key(inter: discord.Interaction, key: str):
 try:
 await inter.response.defer (ephemeral=True)
 ok = key_manager.revoke(key)
 if ok:
			try: await upload_backup(key_manager.build_backup_payload())
 except: pass
 await inter.followup.send (f" ️ Key `{key}` revoked.", ephemeral=True)
 else:
 await inter.followup.send("❌ Not found.", ephemeral=True)
 Except Exception as e:
 await inter.followup.send(f"❌ Error: {e}", ephemeral=True)
 
 @app_commands.guilds(discord.Object(id=GUILD_ID))
 @admin_role_only()
 @bot.tree.command(name="unrevoke_key", description="Re-enable a revoked key")
 async def unrevoke_key(inter: discord.Interaction, key: str):
 try:
 await inter.response.defer (ephemeral=True)
 ok = key_manager.unrevoke(key)
 if ok:
 try: await upload_backup(key_manager.build_backup_payload())
 except: pass
 await inter.followup.send(f"✅ Key `{key}` enabled.", ephemeral=True)
 else:
 await inter.followup.send("❌ Not found.", ephemeral=True)
 Except Exception as e:
 await inter.followup.send(f"❌ Error: {e}", ephemeral=True)
 
 @app_commands.guilds(discord.Object(id=GUILD_ID))
 @admin_role_only()
 @bot.tree.command(name="delete_key", description="Delete key permanently")
 async def delete_key(inter: discord.Interaction, key: str):
 try:
 await inter.response.defer (ephemeral=True)
 ok = key_manager.delete(key)
 if ok:
 try: await upload_backup(key_manager.build_backup_payload())
 except: pass
 await inter.followup.send (f" ️ Key `{key}` deleted.", ephemeral=True)
 else:
 await inter.followup.send("❌ Not found.", ephemeral=True)
 Except Exception as e:
 await inter.followup.send(f"❌ Error: {e}", ephemeral=True)
 
 @app_commands.guilds(discord.Object(id=GUILD_ID))
 @admin_role_only()
 @bot.tree.command(name="generate_bulk_keys", description="Generate daily/weekly/monthly/lifetime")
 async def generate_bulk_keys(inter: discord.Interaction, daily: int, weekly: int, monthly: int, lifetime: int):
 try:
 await inter.response.defer (ephemeral=True)
 If any (x<0 for x in (daily, weekly, monthly, lifetime)):
 await inter.followup.send("❌ Counts must be ≥ 0", ephemeral=True); Return
 if daily==weekly==monthly==lifetime==0:
 await inter.followup.send("❌ Provide at least one > 0", ephemeral=True); return
 Out = key_manager.generate_bulk (daily, weekly, monthly, lifetime)
 try: await upload_backup(key_manager.build_backup_payload())
 except: pass
 em = discord.Embed(title="🔑 Generated", color=0x22C55E)
 for k in ("daily", "weekly", "monthly", "lifetime"):
 em.add_field(name=k.title(), value=str(len(out.get(k, []))), inline=True)
 await inter.followup.send(embed=em, ephemeral=True)
 Except Exception as e:
 await inter.followup.send(f"❌ Error: {e}", ephemeral=True)
 
 @app_commands.guilds(discord.Object(id=GUILD_ID))
 @admin_role_only()
 @bot.tree.command(name="view_available_keys", description="View unassigned keys by type")
 async def view_available_keys(inter: discord.Interaction):
 try:
 await inter.response.defer (ephemeral=True)
 avail = key_manager.available_by_type()
 Def block(items):
 If not items: return ["None"]
 lines, out, cur = [f"`{i['key']}` — Expires {(f'<t:{i['expires']}:R>' if i['expires'] else '—')}" for I in items], [], "
 for ln in lines:
 if len(cur)+len(ln)+1>1024:
 If cur: out.append(cur)
 cur = ln
 else:
 cur = f"{cur}\n{ln}" if cur else ln
 If cur: out.append(cur)
 Return out
 em = discord.Embed(title="🔑 Available Keys", color=0x2d6cdf, description="Unassigned keys")
 for name in ("daily", "weekly", "monthly", "lifetime"):
 items = avail.get(name, [])
 for I, chunk in enumerate (block (items), 1):
 sfx = f" (part {i})" if i>1 else ""
 em.add_field(name=f"{name.title()} ({len(items)}){sfx}", value=chunk, inline=False)
 await inter.followup.send(embed=em, ephemeral=True)
 Except Exception as e:
 await inter.followup.send(f"❌ Error: {e}", ephemeral=True)
 
 @app_commands.guilds(discord.Object(id=GUILD_ID))
 @bot.tree.command(name="bot_status", description="Bot stats")
 async def bot_status(inter: discord.Interaction):
 try:
 total = len(key_manager.keys)
 active = sum (1 for d in key_manager.keys.values() if d.get("is_active"))
 deleted = len(key_manager.deleted_keys)
 usage = sum(int(u.get("usage_count",0)) for u in key_manager.key_usage.values())
 em = discord.Embed(title="📊 Status", color=0x2d6cdf)
 em.add_field(name="Total", value=str(total), inline=True)
 em.add_field(name="Active", value=str(active), inline=True)
 em.add_field(name="Deleted", value=str(deleted), inline=True)
 em.add_field(name="Usage", value=str(usage), inline=True)
 await safe_followup(inter, embedded=em, ephemeral=True)
 Except Exception as e:
 await safe_followup(inter, f"❌ Error: {e}", ephemeral=True)
 
 # --------- LEADERBOARD ---------
 @app_commands.guilds(discord.Object(id=GUILD_ID))
 @bot.tree.command(name="leaderboard", description="Top 10 users by selfbot messages")
 async def leaderboard (inter: discord.Interaction):
 try:
 await inter.response.defer (ephemeral=False)
 stats = {}
 try:
 if os.path.exists (STATS_FILE):
 async with aiofiles.open(STATS_FILE, "r") as f:
 raw = await f.read()
 stats = json.loads(raw) or {}
 else:
 stats = MESSAGE_STATS.copy()
 Except Exception:
 stats = MESSAGE_STATS.copy()
 for uid, cnt in MESSAGE_STATS.items():
 stats[uid] = max(stats.get(uid,0), cnt)
 top = sorted(stats.items(), key=lambda kv: kv[1], reverse=True)[:10]
 if not top:
 await inter.followup.send("📊 No data yet."); return
 em = discord.Embed(title="🏆 Selfbot Leaderboard", color=0xffd700)
 Medals = ["🥇","🥈","🥉","4️towel","5️towel","6️towel","7️towel","8️towel","9️towel", "🔟"]
 em.description = ""
 for i, (uid, c) in enumerate(top):
 try:
 u = await bot.fetch_user(int(uid))
 name = f"{u.name}#{u.discriminator}" if u else uid
 Except Exception:
 name = uid
 em.description += f"{medals[i]} {name} — {c:,}\n"
 await inter.followup.send(embed=em)
 Except Exception as e:
 try: await inter.followup.send(f"❌ Error: {e}")
 except: await inter.response.send_message(f"❌ Error: {e}", ephemeral=True)
 
 # --------- AUTOBUY ----------
async def create_invoice(price: int, coin_code: str, order_id: str, desc: str) -> Optional[dict]:
 try:
 h = {"x-api-key": NWP_API_KEY, "Content-Type": "application/json"}
 d = {"price_amount": price, "price_currency":"USD", "pay_currency": coin_code, "order_id": order_id, "order_description": desc}
 r = requests.post("https://api.nowpayments.io/v1/invoice", headers=h, json=d, timeout=15)
 if r.status_code in (200,201):
 return r.json()
 Except Exception as e:
 print("invoice error:", e)
 Return None
 
 @app_commands.guilds(discord.Object(id=GUILD_ID))
 @bot.tree.command(name="autobuy", description="Buy a key with USDC/USDT/BTC/ETH/LTC/SOL")
 async def autobuy (inter: discord.Interaction):
 try:
 if AUTOBUY_CHANNEL_ID and inter.channel.id! = AUTOBUY_CHANNEL_ID:
 await inter.response.send_message(f"❌ Use this in <#{AUTOBUY_CHANNEL_ID}>,.ephemeral=True); return
 If not (NWP_API_KEY and NWP_IPN_SECRET):
 await inter.response.send_message("❌ Payment not configured.") ephemeral=True); return
 
 Class KeyType (discord.ui.Select):
 def __init__(self):
 super().__init__(placeholder="Choose key duration...", options=[
 discord.SelectOption(label="1 Day - $3", value="daily"),
 discord.SelectOption(label="1 Week - $10", value="weekly"),
 discord.SelectOption(label="1 Month - $15", value="monthly"),
 discord.SelectOption(label="Lifetime - $30", value="lifetime"),
 ])
 async def callback(self, itx: discord.Interaction):
 await itx.response.edit_message(content=f"Selected: {self.values[0].title()}.  Now choose crypto...", view=CryptoView(self.values[0])
 
 class CryptoView (discord.ui.View):
 def __init__(self, key_type: str):
 super().__init__(timeout=300)
 self.key_type = key_type
 self.add_item(CryptoSelect(key_type))
 
 class CryptoSelect (discord.ui.Select):
 def __init__(self, key_type: str):
 self.key_type = key_type
 super().__init__(placeholder="Choose crypto...", options=[
 discord.SelectOptionlabel="USDC", value="USDC"
 discord.SelectOption(label="USDT", value="USDT"),
 discord.SelectOption(label="BTC", value="BTC"),
 discord.SelectOption(label="ETH", value="ETH"),
 discord.SelectOption(label="LTC", value="LTC"),
 discord.SelectOption(label="SOL", value="SOL"),
 ])
 async def callback(self, itx: discord.Interaction):
 pm = {"daily":3, "weekly":10, "monthly":15, "lifetime":30}
 kt = self.key_type
 coin = self.values[0]
 await itx.response.defer()
 order_id = f"{inter.user.id}:{inter.channel.id}:{kt}:{pm[kt]}:{now_ts()}"
 inv = await create_invoice(pm[kt], pay_currency_map(coin), order_id, f"{kt} key for {inter.user.id}")
 if not inv:
 await itx.followup.send("❌ Failed to create invoice.", ephemeral=True); return
 url = inv.get("invoice_url") or inv.get("pay_url")
 em = discord.Embed(title="💳 Pay Invoice", description=f"Key: {kt.title()} — ${pm[kt]}\nCrypto: {coin}\n\n[Open Invoice]({url})", color=0x22C55E)
				await itx.followup.send(embed=em, ephemeral=True)
 
 view = discord.ui.View (timeout=300)
 view.add_item(KeyType())
 em = discord.Embed(title="🛒 AutoBuy", description="Select a key duration to begin.", color=0x5a3e99)
 await inter.response.send_message(embed=em, view=view, ephemeral=True)
 Except Exception as e:
 await inter.response.send_message(f"❌ Error: {e}", ephemeral=True)
 
 # -------- NOWPAYMENTS IPN ---------
 from aiohttp import web
 
 async def nowpayments_ipn(request: web.Request):
 try:
 raw = await request.read()
 sig = request.headers.get("x-nowpayments-sig","")
 If not (sig and NWP_IPN_SECRET):
 return web.Response(status=400, text="bad sig")
 exp = hmac.new(NWP_IPN_SECRET.encode("utf-8"), raw, hashlib.sha512).hexdigest()
 If not hmac.compare_digest(exp, sig):
 return web.Response(status=400, text="bad sig")
 data = json.loads (raw.decode ("utf-8"))
 status = str(data.get("payment_status","")).lower()
 order_id = str(data.get("order_id",""))
		parts = order_id.split(":")
 user_id = int(parts[0]) if len(parts)>0 and parts[0].isdigit() else None
 channel_id = int(parts[1]) if len(parts)>1 and parts[1].isdigit() else None
 key_type = parts[2] if len(parts)>2 else ""
 amount = parts[3] if len(parts)>3 else ""
 
 try:
 if PURCHASE_LOG_WEBHOOK:
 color = 0xF59E0B if "pending" in status or "waiting" in status else 0x22C55E if "finished" in status or "confirmed" in status else 0x64748B
 requests.post(PURCHASE_LOG_WEBHOOK, json={"embeds":[
 {"title": "Autobuy (NOWPayments)", "description":status, "color":color,
 "fields":[{"name": "User ID", "value":str(user_id), "inline":True},
 {"name": "Key", "value":key_type, "inline":True},
 {"name": "Amount", "value":str(amount), "inline":True}]}
 ]}, timeout=8
 Except Exception:
 pass
 
 If user_id and key_type and (("finished" in status) or ("confirmed" in status)):
 durs = {"daily":1, "weekly":7, "monthly":30, "lifetime":365}
 k = key_manager.generate(user_id, None, durs.get(key_type, 30))
 try:
 u = await bot.fetch_user(user_id)
 if u:
 em = discord.Embed(title="🎉 Payment Confirmed", description=f"Your {key_type} key:\n`{k}`", color=0x22C55E)
 await u.send(embed=em)
 Except Exception:
 pass
 try:
 await upload_backup(key_manager.build_backup_payload())
 Except Exception:
 pass
 try:
 if channel_id:
 ch = bot.get_channel(channel_id)
 if ch:
 await ch.send(f"<@{user_id}> Your {key_type} key: `{k}`")
 Except Exception:
 pass
 return web.Response(text="ok")
 Except Exception as e:
 return web.Response(status=500, text=str(e))
 
 async def start_ipn():
 app = web.Application()
 app.router.add_post("/webhook/nowpayments", nowpayments_ipn)
 runner = web.AppRunner(app)
 await runner.setup()
 port = int(os.getenv("PORT", "8080")) + 1
 site = web.TCPSite (runner, "0.0.0.0", port)
 await site.start()
 
 # -------- DOWNLOAD ENDPOINT ----------
 import http.server, socketserver, threading
 
 class DownloadHandler (http.server.SimpleHTTPRequestHandler):
 def do_GET(self):
 If self.path.lower() in ("/download/bot.py", "/download/bot"):
 try:
 with open("bot.py", "rb") as f:
 data = f.read()
 self.send_response(200)
 self.send_header("Content-Type", "application/octet-stream")
 self.send_header("Content-Disposition", 'attachment; filename="bot.py"')
 self.send_header("Content-Length", str(len(data))
 self.end_headers()
 self.wfile.write(data)
 Except Exception as e:
 self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode()
 Return
 return super().do_GET()
 
 def start_download_server():
 port = int (os.getenv("PORT", "8080"))
 def _run():
 with socketserver.TCPServer(("", port), DownloadHandler) as httpd:
 print(f"🌐 Download server on {port} (GET /download/bot.py)")
 httpd.serve_forever()
 t = threading.Thread(target=_run, daemon=True)
 t.start()
 
 # --------- MAIN ---------
 async def main():
 start_download_server()
 await start_ipn()
 await bot.start (BOT_TOKEN)
 
 if __name__ == "__main__":
 try:
 asyncio.run (main())
 except KeyboardInterrupt:

 print("Stopped")
