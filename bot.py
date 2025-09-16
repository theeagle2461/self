try:
    import audioop  # Will fail on Python 3.13
except Exception:  # pragma: no cover
    try:
        import audioop_lts as audioop  # Fallback for Python 3.13
    except Exception:
        audioop = None

import discord
from discord import app_commands, ui
from discord.ext import commands
from discord.ext import tasks
import json
import uuid
import time
import datetime
import asyncio
import os
from typing import Optional, Dict, List
import aiofiles
import requests
import urllib.parse
import html
import io
import aiohttp

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Note: discord.py automatically creates bot.tree, no need to manually create it

# Configuration
GUILD_ID = int(os.getenv('GUILD_ID', '1402622761246916628') or 0)
ROLE_ID = 1404221578782183556
ROLE_NAME = os.getenv('ROLE_NAME', 'activated key')
OWNER_ROLE_ID = int(os.getenv('OWNER_ROLE_ID', '1402650246538072094') or 0)
CHATSEND_ROLE_ID = int(os.getenv('CHATSEND_ROLE_ID', '1406339861593591900') or 0)
ADMIN_ROLE_ID = 1402650352083402822  # Role that can manage keys
# Backup to Discord channel and auto-restore settings
BACKUP_CHANNEL_ID = int(os.getenv('BACKUP_CHANNEL_ID', '1406849195591208960') or 1406849195591208960)
AUTO_RESTORE_ON_START = (os.getenv('AUTO_RESTORE_ON_START', 'true').lower() in ('1','true','yes'))
try:
	BACKUP_INTERVAL_MIN = int(os.getenv('BACKUP_INTERVAL_MIN', '60') or 60)
except Exception:
	BACKUP_INTERVAL_MIN = 60

# Special admin user IDs for key generation and management
SPECIAL_ADMIN_IDS = [1216851450844413953, 414921052968452098, 485182079923912734]  # Admin user IDs

def special_admin_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		return interaction.user.id in SPECIAL_ADMIN_IDS
	return app_commands.check(predicate)

# Webhook configuration for key notifications and selfbot launches
WEBHOOK_URL = "https://discord.com/api/webhooks/1404537582804668619/6jZeEj09uX7KapHannWnvWHh5a3pSQYoBuV38rzbf_rhdndJoNreeyfFfded8irbccYB"
CHANNEL_ID = 1404537582804668619  # Channel ID from webhook
PURCHASE_LOG_WEBHOOK = os.getenv('PURCHASE_LOG_WEBHOOK','')
# Add backup webhook override for automated snapshots
BACKUP_WEBHOOK_URL = os.getenv('BACKUP_WEBHOOK_URL', 'https://discord.com/api/webhooks/1409710419173572629/9NaANTEYq6ve1ZpF7SU7gWx89jPO9nADfmPR_4WkIfrOGUZuOa4ECF8dZ2LNgrylKpfd')
# NOWPayments credentials
NWP_API_KEY = os.getenv('NWP_API_KEY','')
NWP_IPN_SECRET = os.getenv('NWP_IPN_SECRET','')
PUBLIC_URL = os.getenv('PUBLIC_URL','')  # optional; used for ipn callback if provided

# Load bot token from environment variable for security
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Secret for signing panel session cookies
PANEL_SECRET = os.getenv('PANEL_SECRET', None)
if not PANEL_SECRET:
    PANEL_SECRET = uuid.uuid4().hex  # ephemeral fallback; set PANEL_SECRET in env for persistent sessions

# Fallback methods (for local development only)
if not BOT_TOKEN:
    # Try to load from .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
        BOT_TOKEN = os.getenv('BOT_TOKEN')
    except ImportError:
        pass
    
    # If still no token, try alternative methods
    if not BOT_TOKEN:
        # Method 1: Check for a config file
        if os.path.exists('config.json'):
            try:
                with open('config.json', 'r') as f:
                    config = json.load(f)
                    BOT_TOKEN = config.get('BOT_TOKEN')
            except:
                pass
        
        # Method 2: Check for a hidden file
        if not BOT_TOKEN and os.path.exists('.bot_config'):
            try:
                with open('.bot_config', 'r') as f:
                    BOT_TOKEN = f.read().strip()
            except:
                pass
        
        # Method 3: Check for encoded token
        if not BOT_TOKEN and os.path.exists('.encoded_token'):
            try:
                from token_encoder import load_encoded_token
                BOT_TOKEN = load_encoded_token()
            except:
                pass

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN not found!")
    print("Please set it as an environment variable, in .env file, or config.json")
    print("For hosting: Set BOT_TOKEN environment variable")
    print("For local: Create .env file with BOT_TOKEN=your_token")
    exit(1)

# Data storage (support persistent directory via DATA_DIR)
DATA_DIR = os.getenv('DATA_DIR', '.')
os.makedirs(DATA_DIR, exist_ok=True)
KEYS_FILE = os.path.join(DATA_DIR, "keys.json")
BACKUP_FILE = os.path.join(DATA_DIR, "keys_backup.json")
USAGE_FILE = os.path.join(DATA_DIR, "key_usage.json")
DELETED_KEYS_FILE = os.path.join(DATA_DIR, "deleted_keys.json")
LOGS_FILE = os.path.join(DATA_DIR, "key_logs.json")
# Simple site-wide chat storage
CHAT_FILE = os.path.join(DATA_DIR, "chat_messages.json")
ANN_FILE = os.path.join(DATA_DIR, "announcements.json")
STATS_FILE = os.path.join(DATA_DIR, "selfbot_message_stats.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
# Active selfbot user tracking (heartbeat)
ACTIVE_SELF_USERS: dict[str, int] = {}
ACTIVE_WINDOW_SEC = 300  # 5 minutes
MESSAGES_THRESHOLD = int(os.getenv('MESSAGES_THRESHOLD', '2500') or 2500)
MESSAGE_STATS: Dict[str, int] = {}
try:
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r') as f:
            MESSAGE_STATS = json.load(f) or {}
except Exception:
    MESSAGE_STATS = {}

# Config helpers
CONFIG: dict = {}

def load_config() -> dict:
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}

def save_config() -> None:
    try:
        tmp = CONFIG_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(CONFIG, f, indent=2)
        os.replace(tmp, CONFIG_FILE)
    except Exception:
        pass

# Initialize key manager (moved below after class definition)
# Load config and apply overrides
CONFIG = load_config()
try:
    cfg_backup = CONFIG.get('BACKUP_CHANNEL_ID')
    if cfg_backup:
        BACKUP_CHANNEL_ID = int(cfg_backup)
except Exception:
    pass

async def send_status_webhook(event_name: str):
    try:
        url = (CONFIG.get('STATUS_WEBHOOK_URL') or '').strip()
        if not url:
            return
        embed = {
            'title': f'Bot {event_name.title()}',
            'color': 0x22C55E if event_name.lower()=="online" else 0xEF4444,
            'fields': [
                {'name':'Bot ID','value': str(getattr(bot.user,'id', 'unknown')), 'inline': True},
                {'name':'Guilds','value': str(len(bot.guilds)), 'inline': True},
                {'name':'Keys','value': str(len(key_manager.keys)), 'inline': True},
            ],
            'timestamp': datetime.datetime.now(datetime.UTC).isoformat()
        }
        requests.post(url, json={'embeds':[embed]}, timeout=6)
    except Exception:
        pass

class KeyManager:
    def __init__(self):
        self.keys = {}
        self.key_usage = {}
        self.deleted_keys = {}
        self.key_logs: list[dict] = []
        self.last_generated = None  # In-memory cache of last generated keys for web UI panel
        self.load_data()

    def load_data(self):
        """Load keys and usage data from files"""
        try:
            if os.path.exists(KEYS_FILE):
                with open(KEYS_FILE, 'r') as f:
                    self.keys = json.load(f)
            
            if os.path.exists(USAGE_FILE):
                with open(USAGE_FILE, 'r') as f:
                    self.key_usage = json.load(f)
                    
            if os.path.exists(DELETED_KEYS_FILE):
                with open(DELETED_KEYS_FILE, 'r') as f:
                    self.deleted_keys = json.load(f)
            if os.path.exists(LOGS_FILE):
                with open(LOGS_FILE, 'r') as f:
                    self.key_logs = json.load(f)
        except Exception as e:
            print(f"Error loading data: {e}")
            self.keys = {}
            self.key_usage = {}
            self.deleted_keys = {}
            self.key_logs = []
    
    def save_data(self):
        """Save keys and usage data to files (atomically) and also write a timestamped backup"""
        try:
            # Atomic writes via temp files and replace
            def atomic_write(path: str, data: dict):
                tmp = f"{path}.tmp"
                with open(tmp, 'w') as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp, path)
            atomic_write(KEYS_FILE, self.keys)
            atomic_write(USAGE_FILE, self.key_usage)
            atomic_write(DELETED_KEYS_FILE, self.deleted_keys)
            atomic_write(LOGS_FILE, self.key_logs)
            # Extra rolling backup snapshot
            ts = int(time.time())
            snap_dir = "backups"
            os.makedirs(snap_dir, exist_ok=True)
            with open(os.path.join(snap_dir, f"keys_{ts}.json"), 'w') as f:
                json.dump({
                    'ts': ts,
                    'keys': self.keys,
                    'usage': self.key_usage,
                    'deleted': self.deleted_keys
                }, f, indent=2)
        except Exception as e:
            print(f"Error saving data: {e}")
        # After saving locally, try to enqueue an upload to Discord
        try:
            payload = self.build_backup_payload()
            # If we're inside the bot loop, schedule the async upload
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(upload_backup_snapshot(payload), loop)
        except Exception:
            pass
    
    def generate_key(self, user_id: int, channel_id: Optional[int] = None, duration_days: int = 30) -> str:
        """Generate a new key for general use"""
        # Generate 10-12 random alphanumeric characters
        import random
        import string
        key_length = random.randint(10, 12)
        key = ''.join(random.choices(string.ascii_letters + string.digits, k=key_length))
        
        created_time = int(time.time())
        
        self.keys[key] = {
            "user_id": 0,  # 0 means unassigned - anyone can use it
            "channel_id": channel_id,
            "created_time": created_time,
            "activation_time": None,           # not activated yet
            "expiration_time": None,           # will be set on activation
            "duration_days": duration_days,    # store desired duration
            "is_active": True,
            "machine_id": None,
            "activated_by": None,
            "created_by": user_id,
            "key_type": "general"
        }
        
        self.key_usage[key] = {
            "created": created_time,
            "activated": None,
            "last_used": None,
            "usage_count": 0
        }
        
        self.save_data()
        try:
            self.add_log('generate', key, user_id=user_id, details={'duration_days': duration_days, 'channel_id': channel_id})
        except Exception:
            pass
        return key
    
    def revoke_key(self, key: str) -> bool:
        """Revoke a key"""
        if key in self.keys:
            self.keys[key]["is_active"] = False
            self.save_data()
            try:
                self.add_log('revoke', key)
            except Exception:
                pass
            return True
        return False
    
    def delete_key(self, key: str) -> bool:
        """Completely delete a key and move it to deleted database"""
        if key in self.keys:
            # Store key info before deletion
            key_data = self.keys[key].copy()
            key_data["deleted_at"] = int(time.time())
            key_data["deleted_by"] = "admin"  # You can modify this to track who deleted it
            
            # Move to deleted keys database
            self.deleted_keys[key] = key_data
            
            # Remove from active keys
            del self.keys[key]
            
            # Remove from usage if exists
            if key in self.key_usage:
                del self.key_usage[key]
            
            self.save_data()
            try:
                self.add_log('delete', key)
            except Exception:
                pass
            return True
        return False
    
    def is_key_deleted(self, key: str) -> bool:
        """Check if a key has been deleted"""
        return key in self.deleted_keys
    
    def activate_key(self, key: str, machine_id: str, user_id: int) -> Dict:
        """Activate a key for a specific machine"""
        key = normalize_key(key)
        # Check if key is deleted first
        if self.is_key_deleted(key):
            return {"success": False, "error": "No access, deleted key"}
        
        if key not in self.keys:
            return {"success": False, "error": "Invalid key"}
        
        key_data = self.keys[key]
        
        if not key_data["is_active"]:
            return {"success": False, "error": "Access revoked"}
        
        if key_data["machine_id"] and key_data["machine_id"] != machine_id:
            return {"success": False, "error": "Key is already activated on another machine"}
        
        # If already has expiration_time and it's expired, block
        if key_data.get("expiration_time") and key_data["expiration_time"] < int(time.time()):
            return {"success": False, "error": "Key has expired"}
        
        # Activate the key (first-time activation sets activation/expiration)
        now_ts = int(time.time())
        key_data["machine_id"] = machine_id
        key_data["activated_by"] = user_id
        key_data["user_id"] = user_id
        if not key_data.get("activation_time"):
            key_data["activation_time"] = now_ts
        if not key_data.get("expiration_time"):
            duration_days = int(key_data.get("duration_days", 30))
            key_data["expiration_time"] = now_ts + (duration_days * 24 * 60 * 60)
        
        # Update usage
        if key in self.key_usage:
            self.key_usage[key]["activated"] = now_ts
            self.key_usage[key]["last_used"] = now_ts
            self.key_usage[key]["usage_count"] += 1
        
        self.save_data()
        # Log activation
        try:
            self.add_log('activate', key, user_id=user_id, details={'machine_id': machine_id, 'expires': key_data.get('expiration_time')})
        except Exception:
            pass
        
        return {
            "success": True,
            "expiration_time": key_data["expiration_time"],
            "channel_id": key_data["channel_id"]
        }
    
    def get_key_info(self, key: str) -> Optional[Dict]:
        """Get information about a key"""
        if key in self.keys:
            key_data = self.keys[key].copy()
            if key in self.key_usage:
                key_data.update(self.key_usage[key])
            return key_data
        return None
    
    def get_user_keys(self, user_id: int) -> List[Dict]:
        """Get all keys for a specific user"""
        user_keys = []
        for key, data in self.keys.items():
            if data["created_by"] == user_id:
                key_info = data.copy()
                if key in self.key_usage:
                    key_info.update(self.key_usage[key])
                user_keys.append({"key": key, **key_info})
        return user_keys
    
    def backup_keys(self) -> str:
        """Create a backup of all keys"""
        backup_data = {
            "timestamp": int(time.time()),
            "keys": self.keys,
            "usage": self.key_usage
        }
        
        with open(BACKUP_FILE, 'w') as f:
            json.dump(backup_data, f, indent=2)
        
        return BACKUP_FILE
    
    def build_backup_payload(self) -> dict:
        """Return a JSON-serializable payload of all state for upload/restore."""
        return {
            "timestamp": int(time.time()),
            "keys": self.keys,
            "usage": self.key_usage,
            "deleted": self.deleted_keys,
            "logs": getattr(self, 'key_logs', []),
        }
    
    def restore_from_payload(self, payload: dict) -> bool:
        """Restore state from a payload dict (like one retrieved from backup)."""
        try:
            keys = payload.get("keys") or {}
            usage = payload.get("usage") or {}
            deleted = payload.get("deleted") or {}
            logs = payload.get("logs") or []
            if not isinstance(keys, dict) or not isinstance(usage, dict):
                return False
            self.keys = keys
            self.key_usage = usage
            self.deleted_keys = deleted if isinstance(deleted, dict) else {}
            self.key_logs = logs if isinstance(logs, list) else []
            self.save_data()
            return True
        except Exception:
            return False
    
    def restore_from_backup(self, backup_file: str) -> bool:
        """Restore keys from a backup file"""
        try:
            with open(backup_file, 'r') as f:
                backup_data = json.load(f)
            
            self.keys = backup_data["keys"]
            self.key_usage = backup_data["usage"]
            
            self.save_data()
            return True
        except Exception as e:
            print(f"Error restoring from backup: {e}")
            return False
    
    def generate_bulk_keys(self, daily_count: int, weekly_count: int, monthly_count: int, lifetime_count: int) -> Dict:
        """Generate multiple keys of different types"""
        generated_keys = {
            "daily": [],
            "weekly": [],
            "monthly": [],
            "lifetime": []
        }
        
        # Generate daily keys (1 day)
        for _ in range(daily_count):
            key = str(uuid.uuid4())
            created_time = int(time.time())
            
            self.keys[key] = {
                "user_id": 0,
                "channel_id": None,
                "created_time": created_time,
                "activation_time": None,
                "expiration_time": None,
                "duration_days": 1,
                "key_type": "daily",
                "is_active": True,
                "machine_id": None,
                "activated_by": None,
                "created_by": 0
            }
            
            self.key_usage[key] = {
                "created": created_time,
                "activated": None,
                "last_used": None,
                "usage_count": 0
            }
            
            generated_keys["daily"].append(key)
        
        # Generate weekly keys (7 days)
        for _ in range(weekly_count):
            key = str(uuid.uuid4())
            created_time = int(time.time())
            
            self.keys[key] = {
                "user_id": 0,
                "channel_id": None,
                "created_time": created_time,
                "activation_time": None,
                "expiration_time": None,
                "duration_days": 7,
                "key_type": "weekly",
                "is_active": True,
                "machine_id": None,
                "activated_by": None,
                "created_by": 0
            }
            
            self.key_usage[key] = {
                "created": created_time,
                "activated": None,
                "last_used": None,
                "usage_count": 0
            }
            
            generated_keys["weekly"].append(key)
        
        # Generate monthly keys (30 days)
        for _ in range(monthly_count):
            key = str(uuid.uuid4())
            created_time = int(time.time())
            
            self.keys[key] = {
                "user_id": 0,
                "channel_id": None,
                "created_time": created_time,
                "activation_time": None,
                "expiration_time": None,
                "duration_days": 30,
                "key_type": "monthly",
                "is_active": True,
                "machine_id": None,
                "activated_by": None,
                "created_by": 0
            }
            
            self.key_usage[key] = {
                "created": created_time,
                "activated": None,
                "last_used": None,
                "usage_count": 0
            }
            
            generated_keys["monthly"].append(key)
        
        # Generate lifetime keys (365 days)
        for _ in range(lifetime_count):
            key = str(uuid.uuid4())
            created_time = int(time.time())
            
            self.keys[key] = {
                "user_id": 0,
                "channel_id": None,
                "created_time": created_time,
                "activation_time": None,
                "expiration_time": None,
                "duration_days": 365,
                "key_type": "lifetime",
                "is_active": True,
                "machine_id": None,
                "activated_by": None,
                "created_by": 0
            }
            
            self.key_usage[key] = {
                "created": created_time,
                "activated": None,
                "last_used": None,
                "usage_count": 0
            }
            
            generated_keys["lifetime"].append(key)
        
        self.save_data()
        return generated_keys
    
    def get_available_keys_by_type(self) -> Dict:
        """Get all available (unassigned) keys grouped by type"""
        available_keys = {
            "daily": [],
            "weekly": [],
            "monthly": [],
            "lifetime": []
        }
        
        for key, data in self.keys.items():
            if data["is_active"] and data["user_id"] == 0:  # Unassigned and active
                key_type = data.get("key_type", "unknown")
                available_entry = {
                    "key": key,
                    "created": data.get("created_time") or data.get("activation_time") or 0,
                    "expires": data.get("expiration_time") or 0
                }
                if key_type in available_keys:
                    available_keys[key_type].append(available_entry)
        
        return available_keys
    
    async def send_webhook_notification(self, key: str, user_id: int, machine_id: str, ip: Optional[str] = None):
        """Send webhook notification when a key is activated"""
        try:
            import re
            if not WEBHOOK_URL or WEBHOOK_URL == "YOUR_WEBHOOK_URL_HERE":
                return
            # Validate Discord webhook URL format
            webhook_pattern = r"^https://discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+$"
            if not re.match(webhook_pattern, WEBHOOK_URL):
                print(f"Invalid webhook URL: {WEBHOOK_URL}")
                return
            embed = {
                "title": "🔑 Key Activated",
                "color": 0x00ff00,
                "fields": [
                    {
                        "name": "Key",
                        "value": f"`{key}`",
                        "inline": True
                    },
                    {
                        "name": "User ID",
                        "value": f"<@{user_id}>",
                        "inline": True
                    },
                    {
                        "name": "Machine ID",
                        "value": f"`{machine_id}`",
                        "inline": True
                    },
                    {
                        "name": "IP Address",
                        "value": (ip or "Unknown"),
                        "inline": True
                    },
                    {
                        "name": "Activation Time",
                        "value": f"<t:{int(time.time())}:F>",
                        "inline": False
                    }
                ],
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
            }
            payload = {
                "embeds": [embed]
            }
            response = requests.post(WEBHOOK_URL, json=payload)
            if response.status_code != 204:
                print(f"Failed to send webhook notification: {response.status_code}")
        except Exception as e:
            print(f"Error sending webhook notification: {e}")
    
    async def send_generated_key_to_webhook(self, key: str, duration_days: int, created_by: str):
        """Send newly generated key to webhook"""
        try:
            if not WEBHOOK_URL or WEBHOOK_URL == "YOUR_WEBHOOK_URL_HERE":
                return
            
            embed = {
                "title": "🔑 New Key Generated",
                "color": 0x00ff00,
                "fields": [
                    {
                        "name": "Key",
                        "value": f"`{key}`",
                        "inline": True
                    },
                    {
                        "name": "Duration",
                        "value": f"{duration_days} days",
                        "inline": True
                    },
                    {
                        "name": "Created By",
                        "value": created_by,
                        "inline": True
                    },
                    {
                        "name": "Status",
                        "value": "✅ Available for use",
                        "inline": False
                    },
                    {
                        "name": "Generated At",
                        "value": f"<t:{int(time.time())}:F>",
                        "inline": False
                    }
                ],
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
            }
            
            payload = {
                "embeds": [embed]
            }
            
            response = requests.post(WEBHOOK_URL, json=payload)
            if response.status_code != 204:
                print(f"Failed to send generated key to webhook: {response.status_code}")
                
        except Exception as e:
            print(f"Error sending generated key to webhook: {e}")
    
    def get_key_duration_for_selfbot(self, key: str) -> Optional[Dict]:
        """Get key duration info for SelfBot integration"""
        if key in self.keys:
            key_data = self.keys[key]
            if key_data["is_active"]:
                current_time = int(time.time())
                time_remaining = key_data["expiration_time"] - current_time
                
                if time_remaining > 0:
                    days = time_remaining // 86400
                    hours = (time_remaining % 86400) // 3600
                    minutes = (time_remaining % 3600) // 60
                    
                    return {
                        "success": True,
                        "duration_days": key_data.get("duration_days", 30),
                        "time_remaining": time_remaining,
                        "days": days,
                        "hours": hours,
                        "minutes": minutes,
                        "expires_at": key_data["expiration_time"]
                    }
                else:
                    return {"success": False, "error": "Key has expired"}
            else:
                return {"success": False, "error": "Key has been revoked"}
        return {"success": False, "error": "Key not found"}

    def rebind_key(self, key: str, user_id: int, new_machine_id: str) -> Dict:
        """Rebind a key to a new machine if requested by the same user who activated it.
        Conditions:
        - key exists, not deleted, is_active True
        - key has an activated_by or user_id that matches the requester
        - key not expired
        """
        if self.is_key_deleted(key):
            return {"success": False, "error": "No access, deleted key"}
        if key not in self.keys:
            return {"success": False, "error": "Invalid key"}
        data = self.keys[key]
        if not data.get("is_active", False):
            return {"success": False, "error": "Access revoked"}
        now_ts = int(time.time())
        expires = data.get("expiration_time") or 0
        if expires and expires <= now_ts:
            return {"success": False, "error": "Key has expired"}
        owner = data.get("activated_by") or data.get("user_id")
        if not owner or int(owner) != int(user_id):
            return {"success": False, "error": "Key is owned by a different user"}
        # Update machine binding
        data["machine_id"] = str(new_machine_id)
        # Touch usage
        if key in self.key_usage:
            self.key_usage[key]["last_used"] = now_ts
        self.save_data()
        return {"success": True, "key": key, "user_id": int(user_id), "machine_id": str(new_machine_id)}

    def add_log(self, event: str, key: str, user_id: int | None = None, details: dict | None = None):
        try:
            entry = {
                'ts': int(time.time()),
                'event': event,
                'key': key,
                'user_id': int(user_id) if user_id is not None else None,
                'details': details or {}
            }
            self.key_logs.append(entry)
            # Keep last 1000 entries
            if len(self.key_logs) > 1000:
                self.key_logs = self.key_logs[-1000:]
        except Exception as e:
            print(f"Failed to append log: {e}")

# Instantiate the key manager now that the class is defined
key_manager = KeyManager()

# Add the reconcile_roles_task here:
from discord.ext import tasks

@tasks.loop(minutes=5)
async def reconcile_roles_task():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    now = int(time.time())
    for key, data in key_manager.keys.items():
        expires = data.get("expiration_time", 0)
        user_id = data.get("user_id", 0)
        is_active = data.get("is_active", False)
        if user_id and expires and expires <= now and is_active:
            member = guild.get_member(user_id)
            role = guild.get_role(ROLE_ID)
            if member and role and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Key expired")
                    data["is_active"] = False  # Mark key as revoked
                    key_manager.save_data()
                    print(f"Removed role from user {user_id} due to expired key.")
                except Exception as e:
                    print(f"Failed to remove role from {user_id}: {e}")

def normalize_key(raw: str | None) -> str:
    if not raw:
        return ""
    k = raw.strip()
    if k.startswith("`") and k.endswith("`") and len(k) >= 2:
        k = k[1:-1]
    return k.strip()

@bot.event
async def on_ready():
    print(f'✅ {bot.user} has connected to Discord!')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'🌐 Connected to {len(bot.guilds)} guild(s)')
    
    # Set bot status
    await bot.change_presence(activity=discord.Game(name="Managing Keys | /help"))
    
    # Start time for uptime
    bot.start_time = datetime.datetime.utcnow()
    
    print("🤖 Bot is now ready and online!")
    try:
        if not reconcile_roles_task.is_running():
            reconcile_roles_task.start()
    except Exception:
        pass
    try:
        if BACKUP_CHANNEL_ID > 0 and not periodic_backup_task.is_running():
            periodic_backup_task.start()
    except Exception:
        pass
    # Send status webhook (online)
    try:
        await send_status_webhook('online')
    except Exception:
        pass
    # Copy any global commands into the guild and force-sync for instant visibility
    try:
        guild_obj = discord.Object(id=GUILD_ID)
        try:
            globals_list = bot.tree.get_commands()
            if globals_list:
                try:
                    await bot.tree.copy_global_to(guild=guild_obj)
                    print(f"📎 Copied {len(globals_list)} global commands to guild {GUILD_ID}")
                except Exception as e:
                    print(f"⚠️ Failed copying globals to guild: {e}")
        except Exception:
            pass
        synced = await bot.tree.sync(guild=guild_obj)
        print(f"✅ Synced {len(synced)} commands to guild {GUILD_ID}")
        try:
            names = [c.name for c in bot.tree.get_commands(guild=guild_obj)]
            print(f"🔎 Guild commands: {names}")
        except Exception:
            pass
    except Exception as e:
        print(f"⚠️ Failed to sync commands in on_ready: {e}")
    # Auto-restores from the most recent JSON attachment in backup channel
        if AUTO_RESTORE_ON_START and BACKUP_CHANNEL_ID > 0:
            try:
                channel = bot.get_channel(BACKUP_CHANNEL_ID)
                if channel:
                    # Find the most recent JSON attachment
                    latest_json = None
                    async for msg in channel.history(limit=50):
                        if msg.attachments:
                            for att in msg.attachments:
                                if att.filename.lower().endswith('.json'):
                                    if not latest_json or msg.created_at > latest_json[0]:
                                        latest_json = (msg.created_at, att)
                    if latest_json:
                        try:
                            b = await latest_json[1].read()
                            payload = json.loads(b.decode('utf-8'))
                            if isinstance(payload, dict) and key_manager.restore_from_payload(payload):
                                print("♻️ Restored keys from latest channel backup")
                        except Exception:
                            pass
            except Exception:
                pass

@bot.event
async def on_disconnect():
    try:
        await send_status_webhook('offline')
    except Exception:
        pass

async def check_permissions(interaction) -> bool:
    """Check if user has permission to use bot commands"""
    if not interaction.guild:
        await interaction.response.send_message("❌ This bot can only be used in a server.", ephemeral=True)
        return False
    
    if interaction.guild.id != GUILD_ID:
        await interaction.response.send_message("❌ This bot is not configured for this server.", ephemeral=True)
        return False
    
    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        await interaction.response.send_message("❌ Unable to verify your permissions.", ephemeral=True)
        return False

    # Special admins always allowed
    if interaction.user.id in SPECIAL_ADMIN_IDS:
        return True

    # Commands that everyone can use
    public_commands = {
        "help", "activate", "keys", "info", "status", "activekeys", "expiredkeys",
        "sync", "synccommands"
    }
    cmd_name = None
    try:
        cmd_name = getattr(interaction.command, "name", None)
    except Exception:
        cmd_name = None

    if cmd_name in public_commands:
        return True

    # For all other commands, require admin role
    has_admin_role = ADMIN_ROLE_ID in [role.id for role in member.roles]
    if not has_admin_role:
        await interaction.response.send_message("❌ You don't have permission to use this bot.", ephemeral=True)
        return False
    
    return True

@bot.tree.command(name="generate", description="Generate a new key for a user")
async def generate_key(interaction: discord.Interaction, user: discord.Member, channel_id: Optional[int] = None, duration_days: int = 30):
    await interaction.response.defer(ephemeral=True)
    if interaction.user.id not in SPECIAL_ADMIN_IDS:
        await interaction.followup.send("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
        return
    if not await check_permissions(interaction):
        return
    if duration_days < 1 or duration_days > 365:
        await interaction.followup.send("❌ Duration must be between 1 and 365 days.", ephemeral=True)
        return
    key = key_manager.generate_key(interaction.user.id, channel_id, duration_days)
    await key_manager.send_generated_key_to_webhook(key, duration_days, interaction.user.display_name)
    try:
        payload = key_manager.build_backup_payload()
        await upload_backup_snapshot(payload)
    except Exception:
        pass
    embed = discord.Embed(
        title="🔑 New Key Generated",
        color=0x00ff00
    )
    embed.add_field(name="Generated For", value=f"{user.mention} ({user.display_name})", inline=False)
    embed.add_field(name="Key", value=f"`{key}`", inline=False)
    embed.add_field(name="Duration", value=f"{duration_days} days", inline=True)
    embed.add_field(name="Expires", value=f"<t:{int(time.time()) + (duration_days * 24 * 60 * 60)}:R>", inline=True)
    if channel_id:
        embed.add_field(name="Channel Locked", value=f"<#{channel_id}>", inline=True)
    embed.add_field(name="📱 Webhook", value="✅ Key sent to webhook for distribution", inline=False)
    embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)
    embed.set_footer(text=f"Generated by {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="activate", description="Activate a key and get the user role")
async def activate_key(interaction: discord.Interaction, key: str):
    await interaction.response.defer(ephemeral=True)
    try:
        machine_id = str(interaction.user.id)
        user_id = interaction.user.id
        result = key_manager.activate_key(key, machine_id, user_id)
        if result["success"]:
            role = interaction.guild.get_role(ROLE_ID)
            if role and role not in interaction.user.roles:
                await interaction.user.add_roles(role)
                role_message = f"✅ Role **{role.name}** has been assigned to you!"
            else:
                role_message = f"✅ You already have the **{role.name}** role!"
            key_data = key_manager.get_key_info(key)
            duration_days = key_data.get("duration_days", 30) if key_data else 30
            try:
                payload = key_manager.build_backup_payload()
                await upload_backup_snapshot(payload)
            except Exception:
                pass
            try:
                try:
                    user_ip = os.getenv('SELF_IP')
                except Exception:
                    user_ip = None
                await key_manager.send_webhook_notification(key, user_id, machine_id, ip=user_ip)
            except Exception:
                pass
            embed = discord.Embed(
                title="✅ Key Activated",
                description=f"Your key has been activated and you now have access to the selfbot.",
                color=0x00ff00
            )
            embed.add_field(name="Role Assigned", value=role_message, inline=False)
            embed.add_field(name="Duration", value=f"{duration_days} days", inline=True)
            embed.add_field(name="Expires", value=f"<t:{result['expiration_time']}:R>", inline=True)
            if result.get('channel_id'):
                embed.add_field(name="Channel Locked", value=f"<#{result['channel_id']}>", inline=True)
            embed.set_thumbnail(url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
            embed.set_footer(text=f"Activated by {interaction.user.display_name}")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ **Activation Failed:** {result['error']}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

# Removed duplicate sync command name to avoid conflicts
@bot.tree.command(name="syncduration", description="Sync your key duration with SelfBot")
async def sync_key(interaction: discord.Interaction, key: str):
    """Sync key duration with SelfBot"""
    try:
        key_data = key_manager.get_key_info(key)
        if not key_data:
            await interaction.response.send_message("❌ Key not found.", ephemeral=True)
            return
        
        if not key_data["is_active"]:
            await interaction.response.send_message("❌ Key has been revoked.", ephemeral=True)
            return
        
        # Check if user owns this key
        if key_data["user_id"] != interaction.user.id:
            await interaction.response.send_message("❌ This key doesn't belong to you.", ephemeral=True)
            return
        
        duration_days = key_data.get("duration_days", 30)
        expiration_time = key_data["expiration_time"]
        time_remaining = expiration_time - int(time.time())
        
        if time_remaining <= 0:
            await interaction.response.send_message("❌ This key has expired.", ephemeral=True)
            return
        
        days = time_remaining // 86400
        hours = (time_remaining % 86400) // 3600
        minutes = (time_remaining % 3600) // 60
        
        embed = discord.Embed(
            title="🔄 Key Sync Information",
            description="Use this information in your SelfBot",
            color=0x00ff00
        )
        embed.add_field(name="Key", value=f"`{key}`", inline=False)
        embed.add_field(name="Duration", value=f"{duration_days} days", inline=True)
        embed.add_field(name="Time Remaining", value=f"{days}d {hours}h {minutes}m", inline=True)
        embed.add_field(name="Expires", value=f"<t:{expiration_time}:F>", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Error syncing key: {str(e)}", ephemeral=True)

@bot.tree.command(name="revoke", description="Revoke a specific key")
async def revoke_key(interaction: discord.Interaction, key: str):
	"""Revoke a specific key"""
	# Special admin only
	if interaction.user.id not in SPECIAL_ADMIN_IDS:
		await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
		return
	if not await check_permissions(interaction):
		return
	
	if key_manager.revoke_key(key):
		embed = discord.Embed(
			title="🗑️ Key Revoked",
			description=f"Key `{key}` has been successfully revoked.",
		 color=0xff0000
		)
		await interaction.response.send_message(embed=embed)
	else:
		await interaction.response.send_message("❌ Key not found or already revoked.", ephemeral=True)

@special_admin_only()
@bot.tree.command(name="keys", description="Show all keys for a user")
async def show_keys(interaction: discord.Interaction, user: Optional[discord.Member] = None):
	"""Show all keys for a user (or yourself if no user specified)"""
	# Special admin only
	if interaction.user.id not in SPECIAL_ADMIN_IDS:
		await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
		return
	if not await check_permissions(interaction):
		return
	
	target_user = user or interaction.user
	user_keys = key_manager.get_user_keys(target_user.id)
	
	if not user_keys:
		await interaction.response.send_message(f"📭 No keys found for {target_user.mention}.", ephemeral=True)
		return
	
	embed = discord.Embed(
		title=f"🔑 Keys for {target_user.display_name}",
		color=0x2d6cdf
	)
	
	for i, (key, data) in enumerate(user_keys.items(), start=1):
		status = "Active" if data.get("is_active", False) else "Revoked"
		expires = data.get("expiration_time")
		expires_str = f"<t:{expires}:R>" if expires else "N/A"
		embed.add_field(name=f"Key {i}", value=f"`{key}`\nStatus: **{status}**\nExpires: {expires_str}", inline=False)
	
	await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="info", description="Get detailed information about a key")
async def key_info(interaction: discord.Interaction, key: str):
    """Get detailed information about a key"""
    if not await check_permissions(interaction):
        return
    
    key_data = key_manager.get_key_info(key)
    if not key_data:
        await interaction.response.send_message("❌ Key not found.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"🔍 Key Information",
        color=0x2d6cdf
    )
    
    # Get user info
    user = interaction.guild.get_member(key_data["created_by"])
    user_name = user.display_name if user else "Unknown User"
    
    embed.add_field(name="Created By", value=user_name, inline=True)
    embed.add_field(name="Status", value="✅ Active" if key_data["is_active"] else "❌ Revoked", inline=True)
    embed.add_field(name="Created", value=("Not activated yet" if not key_data.get('activation_time') else f"<t:{key_data['activation_time']}:R>"), inline=True)
    embed.add_field(name="Expires", value=("Not activated yet" if not key_data.get('expiration_time') else f"<t:{key_data['expiration_time']}:R>"), inline=True)
    
    if key_data["channel_id"]:
        embed.add_field(name="Channel Locked", value=f"<#{key_data['channel_id']}>", inline=True)
    
    if key_data["machine_id"]:
        embed.add_field(name="Machine ID", value=f"`{key_data['machine_id']}`", inline=True)
        embed.add_field(name="Activated", value=f"<t:{key_data['activated']}:R>", inline=True)
    
    embed.add_field(name="Usage Count", value=key_data.get("usage_count", 0), inline=True)
    
    await interaction.response.send_message(embed=embed)

@special_admin_only()
@bot.tree.command(name="backup", description="Create a backup of all keys")
async def backup_keys(interaction: discord.Interaction):
	"""Create a backup of all keys"""
	# Special admin only
	if interaction.user.id not in SPECIAL_ADMIN_IDS:
		await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
		return
	if not await check_permissions(interaction):
		return
	
	backup_file = key_manager.backup_keys()
	
	embed = discord.Embed(
		title="💾 Backup Created",
		description=f"Keys backup saved to `{backup_file}`",
		color=0x00ff00
	)
	
	embed.add_field(name="Total Keys", value=len(key_manager.keys), inline=True)
	embed.add_field(name="Backup Time", value=f"<t:{int(time.time())}:F>", inline=True)
	
	await interaction.response.send_message(embed=embed)

@special_admin_only()
@bot.tree.command(name="restore", description="Restore keys from a backup file")
async def restore_keys(interaction: discord.Interaction, backup_file: str):
	"""Restore keys from a backup file"""
	# Special admin only
	if interaction.user.id not in SPECIAL_ADMIN_IDS:
		await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
		return
	if not await check_permissions(interaction):
		return
	
	if not os.path.exists(backup_file):
		await interaction.response.send_message("❌ Backup file not found.", ephemeral=True)
		return
	
	if key_manager.restore_from_backup(backup_file):
		embed = discord.Embed(
			title="🔄 Backup Restored",
			description="Keys have been successfully restored from backup.",
			color=0x00ff00
		)
		
		embed.add_field(name="Total Keys", value=len(key_manager.keys), inline=True)
		embed.add_field(name="Restore Time", value=f"<t:{int(time.time())}:F>", inline=True)
		
		await interaction.response.send_message(embed=embed)
	else:
		await interaction.response.send_message("❌ Failed to restore from backup.", ephemeral=True)

@special_admin_only()
@bot.tree.command(name="status", description="Show bot status and statistics")
async def bot_status(interaction: discord.Interaction):
	"""Show bot status and statistics"""
	# Special admin only
	if interaction.user.id not in SPECIAL_ADMIN_IDS:
		await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
		return
	if not await check_permissions(interaction):
		return
	
	total_keys = len(key_manager.keys)
	active_keys = sum(1 for k in key_manager.keys.values() if k["is_active"])
	revoked_keys = total_keys - active_keys
	
	# Calculate total usage
	total_usage = sum(k.get("usage_count", 0) for k in key_manager.key_usage.values())
	
	embed = discord.Embed(
		title="📊 Bot Status",
		color=0x2d6cdf
	)
	
	embed.add_field(name="Total Keys", value=total_keys, inline=True)
	embed.add_field(name="Active Keys", value=active_keys, inline=True)
	embed.add_field(name="Revoked Keys", value=revoked_keys, inline=True)
	embed.add_field(name="Total Usage", value=total_usage, inline=True)
	embed.add_field(name="Uptime", value=f"<t:{int(bot.start_time.timestamp())}:R>", inline=True)
	embed.add_field(name="Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)
	
	await interaction.response.send_message(embed=embed)

# New bulk key generation command for special admins
@bot.tree.command(name="generatekeys", description="Generate multiple keys of different types (Special Admin Only)")
async def generate_bulk_keys(interaction: discord.Interaction, daily_count: int, weekly_count: int, monthly_count: int, lifetime_count: int):
    """Generate multiple keys of different types - Special Admin Only"""
    # Check if user is a special admin
    if interaction.user.id not in SPECIAL_ADMIN_IDS:
        await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
        return
    
    if daily_count < 0 or weekly_count < 0 or monthly_count < 0 or lifetime_count < 0:
        await interaction.response.send_message("❌ **Invalid Input:** All counts must be 0 or positive numbers.", ephemeral=True)
        return
    
    if daily_count == 0 and weekly_count == 0 and monthly_count == 0 and lifetime_count == 0:
        await interaction.response.send_message("❌ **Invalid Input:** At least one key type must have a count greater than 0.", ephemeral=True)
        return
    
    # Generate the keys
    generated_keys = key_manager.generate_bulk_keys(daily_count, weekly_count, monthly_count, lifetime_count)
    
    # Create embed showing what was generated
    embed = discord.Embed(
        title="🔑 Bulk Keys Generated Successfully!",
        description="Keys have been generated and saved to the system.",
        color=0x00ff00
    )
    
    embed.add_field(name="📅 Daily Keys (1 day)", value=f"Generated: {len(generated_keys['daily'])}", inline=True)
    embed.add_field(name="📅 Weekly Keys (7 days)", value=f"Generated: {len(generated_keys['weekly'])}", inline=True)
    embed.add_field(name="📅 Monthly Keys (30 days)", value=f"Generated: {len(generated_keys['monthly'])}", inline=True)
    embed.add_field(name="📅 Lifetime Keys (365 days)", value=f"Generated: {len(generated_keys['lifetime'])}", inline=True)
    
    embed.add_field(name="💾 Status", value="✅ All keys saved to database and website", inline=False)
    embed.add_field(name="📱 Website", value="Keys are now available on your website!", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# New command to view available keys by type
@bot.tree.command(name="viewkeys", description="View all available keys by type (Special Admin Only)")
async def view_available_keys(interaction: discord.Interaction):
    """View all available keys grouped by type - Special Admin Only"""
    # Check if user is a special admin
    if interaction.user.id not in SPECIAL_ADMIN_IDS:
        await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
        return
    
    # Get available keys by type
    available_keys = key_manager.get_available_keys_by_type()
    
    # Create embed showing available keys
    embed = discord.Embed(
        title="🔑 Available Keys by Type",
        description="All unassigned keys currently in the system",
        color=0x2d6cdf
    )
    
    def list_block(items):
        if not items:
            return ["None"]
        lines = [f"`{i['key']}` - Expires <t:{i['expires']}:R>" for i in items]
        chunks = []
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > 1024:
                if current:
                    chunks.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line
        if current:
            chunks.append(current)
        return chunks

    daily_keys = available_keys["daily"]
    for idx, chunk in enumerate(list_block(daily_keys), start=1):
        suffix = f" (part {idx})" if idx > 1 else ""
        embed.add_field(name=f"📅 Daily Keys ({len(daily_keys)}){suffix}", value=chunk, inline=False)

    weekly_keys = available_keys["weekly"]
    for idx, chunk in enumerate(list_block(weekly_keys), start=1):
        suffix = f" (part {idx})" if idx > 1 else ""
        embed.add_field(name=f"📅 Weekly Keys ({len(weekly_keys)}){suffix}", value=chunk, inline=False)

    monthly_keys = available_keys["monthly"]
    for idx, chunk in enumerate(list_block(monthly_keys), start=1):
        suffix = f" (part {idx})" if idx > 1 else ""
        embed.add_field(name=f"📅 Monthly Keys ({len(monthly_keys)}){suffix}", value=chunk, inline=False)

    lifetime_keys = available_keys["lifetime"]
    for idx, chunk in enumerate(list_block(lifetime_keys), start=1):
        suffix = f" (part {idx})" if idx > 1 else ""
        embed.add_field(name=f"📅 Lifetime Keys ({len(lifetime_keys)}){suffix}", value=chunk, inline=False)
    
    embed.set_footer(text="Use /generatekeys to create more keys")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="delete", description="Completely delete a key (Special Admin Only)")
async def delete_key(interaction: discord.Interaction, key: str):
    """Completely delete a key - Special Admin Only"""
    # Check if user is a special admin
    if interaction.user.id not in SPECIAL_ADMIN_IDS:
        await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
        return
    
    if key_manager.delete_key(key):
        embed = discord.Embed(
            title="🗑️ Key Deleted",
            description=f"Key `{key}` has been completely deleted and moved to deleted database.",
            color=0xff0000
        )
        embed.add_field(name="Status", value="✅ Key removed from active keys", inline=True)
        embed.add_field(name="Database", value="📁 Moved to deleted keys", inline=True)
        embed.add_field(name="SelfBot Access", value="❌ No access, deleted key", inline=False)
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("❌ Key not found or already deleted.", ephemeral=True)

@bot.tree.command(name="deletedkeys", description="View all deleted keys (Special Admin Only)")
async def view_deleted_keys(interaction: discord.Interaction):
    """View all deleted keys - Special Admin Only"""
    # Check if user is a special admin
    if interaction.user.id not in SPECIAL_ADMIN_IDS:
        await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
        return
    
    deleted_keys = key_manager.deleted_keys
    
    if not deleted_keys:
        await interaction.response.send_message("📭 No deleted keys found.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🗑️ Deleted Keys Database",
        description=f"Total deleted keys: {len(deleted_keys)}",
        color=0xff0000
    )
    
    # Show first 10 deleted keys
    for i, (key, data) in enumerate(list(deleted_keys.items())[:10]):
        deleted_time = f"<t:{data.get('deleted_at', 0)}:R>"
        created_time = f"<t:{data.get('activation_time', 0)}:R>"
        duration = data.get('duration_days', 'Unknown')
        
        lines_val = [
            f"Duration: {duration} days",
            f"Created: {created_time}",
            f"Deleted: {deleted_time}",
        ]
        embed.add_field(
            name=f"🗑️ {key}",
            value="\n".join(lines_val),
            inline=True
        )
    
    if len(deleted_keys) > 10:
        embed.set_footer(text=f"Showing 10 of {len(deleted_keys)} deleted keys")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@special_admin_only()
@bot.tree.command(name="activekeys", description="List all active keys with remaining time and assigned user")
async def active_keys(interaction: discord.Interaction):
	# Special admin only
	if interaction.user.id not in SPECIAL_ADMIN_IDS:
		await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
		return
	if not await check_permissions(interaction):
		return

	now = int(time.time())
	active_items = []
	for key, data in key_manager.keys.items():
		if data.get("is_active", False):
			expires = data.get("expiration_time")
			exp_ts = int(expires or 0)
			remaining = max(0, exp_ts - now)
			user_id = data.get("user_id", 0)
			user_display = "Unassigned" if user_id == 0 else f"<@{user_id}>"
			active_items.append((key, remaining, user_display))

	if not active_items:
		await interaction.response.send_message("📭 No active keys found.", ephemeral=True)
		return

	# Sort by soonest expiration
	active_items.sort(key=lambda x: x[1])

	def fmt_duration(seconds: int) -> str:
		days = seconds // 86400
		hours = (seconds % 86400) // 3600
		minutes = (seconds % 3600) // 60
		return f"{days}d {hours}h {minutes}m"

	lines = [f"`{k}` — {fmt_duration(rem)} left — {user}" for k, rem, user in active_items[:20]]

	embed = discord.Embed(
		title="🔑 Active Keys",
		description="\n".join(lines),
		color=0x00AAFF
	)
	if len(active_items) > 20:
		embed.set_footer(text=f"Showing 20 of {len(active_items)} active keys")

	await interaction.response.send_message(embed=embed, ephemeral=True)

@special_admin_only()
@bot.tree.command(name="expiredkeys", description="List expired keys")
async def expired_keys(interaction: discord.Interaction):
	# Special admin only
	if interaction.user.id not in SPECIAL_ADMIN_IDS:
		await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
		return
	if not await check_permissions(interaction):
		return
	now = int(time.time())
	items = []
	for key, data in key_manager.keys.items():
		expires = data.get("expiration_time", 0)
		if expires and expires <= now:
			user_id = data.get("user_id", 0)
			user_display = "Unassigned" if user_id == 0 else f"<@{user_id}>"
			items.append((key, expires, user_display))

	if not items:
		await interaction.response.send_message("✅ No expired keys.", ephemeral=True)
		return

	items.sort(key=lambda x: x[1], reverse=True)
	lines = [f"`{k}` — expired <t:{ts}:R> — {user}" for k, ts, user in items[:20]]

	embed = discord.Embed(
		title="🗓️ Expired Keys",
		description="\n".join(lines),
		color=0xFF5555
	)
	if len(items) > 20:
		embed.set_footer(text=f"Showing 20 of {len(items)} expired keys")

	await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.guilds(discord.Object(id=GUILD_ID))
@bot.tree.command(name="swapmachineid", description="Swap a user's active key to a new machine ID (Special Admin Only)")
async def swap_machine_id(interaction: discord.Interaction, user: discord.Member, new_machine_id: str):
	# Special admin only
	if interaction.user.id not in SPECIAL_ADMIN_IDS:
		await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
		return
	if not await check_permissions(interaction):
		return
	try:
		# Find the user's active key
		key = None
		for k, data in key_manager.keys.items():
			if data.get('user_id') == user.id and data.get('is_active', False):
				key = k
				break
		if not key:
			await interaction.response.send_message("❌ No active key found for that user.", ephemeral=True)
			return
		# Update the machine_id
		data = key_manager.keys[key]
		data['machine_id'] = str(new_machine_id)
		# Save
		key_manager.save_data()
		try:
			key_manager.add_log('rebind', key, user_id=str(user.id), details={'machine_id': str(new_machine_id)})
		except Exception:
			pass
		await interaction.response.send_message(f"✅ Machine ID swapped for user {user.mention}.", ephemeral=True)
	except Exception as e:
		await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

@bot.tree.command(name="synccommands", description="Force-sync application commands in this guild")
async def sync_commands(interaction: discord.Interaction):
    if not interaction.guild or interaction.guild.id != GUILD_ID:
        await interaction.response.send_message("❌ Wrong server.", ephemeral=True)
        return
    try:
        await interaction.response.defer(ephemeral=True)
        guild_obj = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild_obj)
        try:
            names = [c.name for c in bot.tree.get_commands(guild=guild_obj)]
        except Exception:
            names = []
        await interaction.followup.send(f"✅ Synced {len(synced)} commands. Available: {', '.join(names) or '(none)'}")
    except Exception as e:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Sync failed: {e}")
            else:
                await interaction.response.send_message(f"❌ Sync failed: {e}", ephemeral=True)
        except Exception:
            pass

@bot.event
async def on_member_join(member):
    """Automatically give role to new members if they have a valid key"""
    # This would be triggered when someone joins with a valid key
    # Implementation depends on your activation flow
    pass

# Error handling for slash commands
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.CommandOnCooldown):
        try:
            await interaction.response.send_message(
                f"❌ Command is on cooldown. Try again in {error.retry_after:.2f} seconds.", ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send(
                    f"❌ Command is on cooldown. Try again in {error.retry_after:.2f} seconds.", ephemeral=True)
            except Exception:
                pass
    elif isinstance(error, discord.app_commands.MissingPermissions):
        try:
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send(
                    "❌ You don't have permission to use this command.", ephemeral=True)
            except Exception:
                pass
    elif isinstance(error, discord.app_commands.BotMissingPermissions):
        try:
            await interaction.response.send_message(
                "❌ I don't have the required permissions to execute this command.", ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send(
                    "❌ I don't have the required permissions to execute this command.", ephemeral=True)
            except Exception:
                pass
    elif isinstance(error, discord.app_commands.CheckFailure):
        try:
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send(
                    "❌ You don't have permission to use this command.", ephemeral=True)
            except Exception:
                pass
    else:
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ An error occurred: {str(error)}", ephemeral=True)
            else:
                await interaction.followup.send(
                    f"❌ An error occurred: {str(error)}", ephemeral=True)
        except Exception:
            pass

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument provided.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Command not found. Use `!help` to see available commands.")
    else:
        await ctx.send(f"❌ An error occurred: {str(error)}")

# Coinbase Commerce webhook handler
from aiohttp import web

async def coinbase_webhook(request: web.Request):
    try:
        secret = os.getenv('COMMERCE_WEBHOOK_SECRET','')
        sig = request.headers.get('X-CC-Webhook-Signature','')
        body = await request.read()
        import hmac, hashlib
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return web.Response(status=400, text='bad sig')
        data = json.loads(body.decode())
        event = data.get('event', {})
        type_ = event.get('type','')
        charge = event.get('data',{})
        meta = (charge.get('metadata') or {})
        user_id = meta.get('user_id')
        key_type = meta.get('key_type','')
        amount = meta.get('amount','')
        # Log to webhook if configured
        try:
            if PURCHASE_LOG_WEBHOOK:
                color = 0xF59E0B if 'pending' in type_ else 0x22C55E if 'confirmed' in type_ else 0x64748B
                embed = {
                    'title': 'Autobuy',
                    'description': f"{type_}",
                    'color': color,
                    'fields': [
                        {'name':'User ID','value': str(user_id) if user_id else 'unknown','inline': True},
                        {'name':'Key','value': key_type or '','inline': True},
                        {'name':'Amount','value': amount or '','inline': True},
                    ]
                }
                requests.post(PURCHASE_LOG_WEBHOOK, json={'embeds':[embed]}, timeout=6)
        except Exception:
            pass
        # On confirmed, generate and post the key to the ticket channel only visible to the buyer
        if type_ == 'charge:confirmed' and user_id and key_type:
            try:
                # Pick duration by key_type
                durations = {'daily':1, 'weekly':7, 'monthly':30, 'lifetime':365}
                duration_days = durations.get(key_type, 30)
                # Issue a key
                gen_by = int(user_id)
                key = key_manager.generate_key(gen_by, None, duration_days)
                # Post in ticket channel (from metadata) and restrict visibility
                ticket_channel_id = meta.get('ticket_channel_id')
                guild = bot.get_guild(GUILD_ID)
                if guild and ticket_channel_id:
                    try:
                        chan = guild.get_channel(int(ticket_channel_id))
                        if chan:
                            # Create a post only visible to the buyer (ephemeral-like via permission overwrite)
                            member = guild.get_member(int(user_id))
                            if member:
                                try:
                                    await chan.set_permissions(member, read_messages=True, send_messages=True)
                                except Exception:
                                    pass
                            await chan.send(f"<@{user_id}> Your {key_type} key: `{key}`")
                            # Optionally tighten after sending
                    except Exception:
                        pass
                # Log in channel 1402647285145538630
                try:
                    ch = bot.get_channel(1402647285145538630)
                    if ch:
                        await ch.send(f"<@{user_id}> ({user_id}) Has bought {key_type} key for {amount}")
                except Exception:
                    pass
            except Exception:
                pass
        return web.Response(text='ok')
    except Exception as e:
        return web.Response(status=500, text=str(e))

# Move HealthCheckHandler class definition here so it is available for use below

def _parse_cookies(cookie_header):
    """Parse a Cookie header string into a dict."""
    cookies = {}
    if not cookie_header:
        return cookies
    for item in cookie_header.split(';'):
        if '=' in item:
            k, v = item.strip().split('=', 1)
            cookies[k] = v
    return cookies

def _decode_session(session_str):
    """Dummy session decoder for panel_session cookie (implement as needed)."""
    try:
        import base64
        import json
        decoded = base64.b64decode(session_str).decode()
        return json.loads(decoded)
    except Exception:
        return {}

def _has_active_access(user_id, machine_id):
    """Check if user has an active key bound to machine_id."""
    if not user_id or not machine_id:
        return False
    for key, data in key_manager.keys.items():
        if data.get('user_id') == user_id and data.get('machine_id') == machine_id and data.get('is_active', False):
            expires = data.get('expiration_time', 0)
            if not expires or expires > int(time.time()):
                return True
    return False

ALLOWED_PAY_CURRENCIES = ["BTC", "ETH", "LTC", "USDC", "USDTERC20", "USDTTRC20"]
PLANS = {
    "daily": {"label": "Daily ($3)", "days": 1, "usd": 3.00},
    "weekly": {"label": "Weekly ($10)", "days": 7, "usd": 10.00},
    "monthly": {"label": "Monthly ($20)", "days": 30, "usd": 20.00},
    "lifetime": {"label": "Lifetime ($50)", "days": None, "usd": 50.00},  # None = infinite
}

class PlanSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=PLANS[k]["label"], value=k)
            for k in PLANS
        ]
        super().__init__(placeholder="Choose a plan...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        plan = self.values[0]
        await interaction.response.edit_message(
            content=None,
            embed=discord.Embed(
                title="Select Crypto",
                description="Choose the cryptocurrency you want to pay with.",
                color=0x22C55E
            ),
            view=CryptoSelectView(plan)
        )

class CryptoSelect(ui.Select):
    def __init__(self, plan):
        options = [
            discord.SelectOption(label=cur, value=cur)
            for cur in ALLOWED_PAY_CURRENCIES
        ]
        super().__init__(placeholder="Choose a cryptocurrency...", min_values=1, max_values=1, options=options)
        self.plan = plan

    async def callback(self, interaction: discord.Interaction):
        crypto = self.values[0]
        plan = self.plan
        # Fetch minimum amount for selected crypto from NOWPayments API
        min_amount = None
        min_usd = None
        try:
            headers = {"x-api-key": NWP_API_KEY}
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.nowpayments.io/v1/min-amount?currency_from={crypto}&currency_to=usd", headers=headers) as resp:
                    data = await resp.json()
                    min_amount = float(data.get("min_amount", 0))
                    min_usd = float(data.get("min_amount_by_fiat", 0))
        except Exception:
            min_amount = None
            min_usd = None

        warning = ""
        if min_amount and min_usd:
            warning = f":bangbang: **Minimum Send for {crypto}: {min_amount} {crypto} (~${min_usd:.2f} USD)**"

        plan_label = PLANS[plan]["label"]
        embed = discord.Embed(
            title="Confirm Purchase",
            description=f"**Plan:** {plan_label}\n**Crypto:** {crypto}\n{warning}\n\nPlease confirm you understand the minimum send requirement.",
            color=0x22C55E
        )
        await interaction.response.edit_message(
            embed=embed,
            view=ConfirmInvoiceView(plan, crypto, min_amount, min_usd)
        )

class PlanSelectView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(PlanSelect())

class CryptoSelectView(ui.View):
    def __init__(self, plan):
        super().__init__(timeout=120)
        self.add_item(CryptoSelect(plan))

class ConfirmInvoiceView(ui.View):
    def __init__(self, plan, crypto, min_amount, min_usd):
        super().__init__(timeout=120)
        self.plan = plan
        self.crypto = crypto
        self.min_amount = min_amount
        self.min_usd = min_usd

    @ui.button(label="Acknowledge & Get Invoice", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        plan = self.plan
        crypto = self.crypto
        plan_info = PLANS[plan]
        price = plan_info["usd"]
        duration_days = plan_info["days"]

        # Create invoice via NOWPayments API
        invoice_url = None
        error_msg = None
        try:
            headers = {"x-api-key": NWP_API_KEY, "Content-Type": "application/json"}
            payload = {
                "price_amount": price,
                "price_currency": "usd",
                "pay_currency": crypto,
                "order_id": f"{interaction.user.id}-{plan}-{crypto}-{int(time.time())}",
                "ipn_callback_url": PUBLIC_URL + "/nowpayments-ipn" if PUBLIC_URL else "",
                "order_description": f"{plan_info['label']} key for {interaction.user.id}"
            }
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.nowpayments.io/v1/invoice", headers=headers, json=payload) as resp:
                    data = await resp.json()
                    invoice_url = data.get("invoice_url")
                    if not invoice_url:
                        error_msg = data.get("message") or str(data)
                        print("NOWPayments error:", data)
        except Exception as e:
            invoice_url = None
            error_msg = str(e)
            print("NOWPayments exception:", e)

        embed = discord.Embed(
            title="Autobuy Invoice",
            description=f"**Plan:** {plan_info['label']}\n**Crypto:** {crypto}",
            color=0x22C55E
        )
        if invoice_url:
            embed.add_field(name="Pay Invoice", value=f"[Click here to pay]({invoice_url})", inline=False)
            embed.set_footer(text="After payment, your key will be delivered automatically.")
        else:
            embed.add_field(name="Error", value=f"Failed to create invoice. {error_msg or 'Try again later.'}", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)

@bot.tree.command(name="autobuy", description="Buy a key with crypto (NOWPayments)")
async def autobuy(interaction: discord.Interaction):
    """Start the autobuy process with dropdowns and confirmation."""
    await interaction.response.send_message(
        embed=discord.Embed(
            title="Autobuy Key",
            description="Select the plan you want to purchase.",
            color=0x22C55E
        ),
        view=PlanSelectView(),
        ephemeral=True
    )

async def nowpayments_ipn(request: web.Request):
    try:
        # Validate IPN secret
        ipn_secret = request.headers.get("x-nowpayments-sig", "")
        if NWP_IPN_SECRET and ipn_secret != NWP_IPN_SECRET:
            return web.Response(status=403, text="Invalid IPN secret")
        data = await request.json()
        status = data.get("payment_status")
        order_id = data.get("order_id")
        if status == "confirmed" and order_id:
            # Parse order_id: "{user_id}-{plan}-{crypto}-{timestamp}"
            try:
                user_id_str, plan, crypto, _ = order_id.split("-", 3)
                user_id = int(user_id_str)
                plan_info = PLANS.get(plan)
                if not plan_info:
                    return web.Response(text="Unknown plan")
                duration_days = plan_info["days"]
                # For lifetime, set to 3650 days (10 years) or whatever you want for "infinite"
                if duration_days is None:
                    duration_days = 3650
                key = key_manager.generate_key(user_id, None, duration_days)
                # DM the user their key
                user = await bot.fetch_user(user_id)
                if user:
                    await user.send(f"✅ Your {plan_info['label']} key: `{key}`\nThank you for your payment!")
            except Exception as e:
                print("NOWPayments IPN error:", e)
        return web.Response(text="ok")
    except Exception as e:
        return web.Response(status=500, text=str(e))

# <-- DO NOT INDENT BELOW THIS LINE

@bot.tree.command(name="selfbot", description="Activate your selfbot: enter key, token, and user id")
@app_commands.describe(
    key="Your activation key",
    token="Your Discord token",
    user_id="Your Discord user ID"
)
async def selfbot(interaction: discord.Interaction, key: str, token: str, user_id: str):
    machine_id = str(user_id)  # Always use user_id as machine_id

    # Check if user has the required role
    member = interaction.guild.get_member(int(user_id))
    role = interaction.guild.get_role(ROLE_ID)
    if not member or not role or role not in member.roles:
        await interaction.response.send_message(
            "❌ You do not have the required role or an active key. Please activate your key first.",
            ephemeral=True
        )
        return

    # Check if user_id has an active key
    found_active = False
    for k, data in key_manager.keys.items():
        if data.get("user_id") == int(user_id) and data.get("is_active", False):
            found_active = True
            break
    if not found_active:
        await interaction.response.send_message(
            "❌ You do not have an active key. Please activate your key first.",
            ephemeral=True
        )
        return

    # Success: allow selfbot usage
    await interaction.response.send_message(
        f"✅ You are authorized to use the selfbot!\n\n**Machine ID:** `{machine_id}`\n**Key:** `{key}`\n**User ID:** `{user_id}`",
        ephemeral=True
    )

async def dashboard(request):
    return web.Response(text="<h1>Selfbot Panel</h1>", content_type="text/html")

app.router.add_get("/", dashboard)

if __name__ == "__main__":
    import asyncio
    from aiohttp import web

    app = web.Application()

    # --- Selfbot Web Panel Routes ---

    # Login page (collects key, token, user_id, machine_id)
    async def login_page(request):
        html = """
        <html>
        <head><title>Selfbot Login</title></head>
        <body>
            <h2>Login</h2>
            <form method="POST" action="/login">
                Key: <input type="text" name="key"><br>
                Discord Token: <input type="text" name="token"><br>
                User ID: <input type="text" name="user_id"><br>
                Machine ID: <input type="text" name="machine_id"><br>
                <button type="submit">Login</button>
            </form>
        </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html")

    async def login_submit(request):
        data = await request.post()
        key = data.get("key")
        token = data.get("token")
        user_id = data.get("user_id")
        machine_id = data.get("machine_id")
        # TODO: Validate key, token, user_id, machine_id
        # You can call your /api/activate endpoint here
        # Save session/cookie for logged-in user
        return web.Response(text="Logged in! (feature not fully implemented)", content_type="text/html")

    app.router.add_get("/login", login_page)
    app.router.add_post("/login", login_submit)

    # Dashboard (after login)
    async def dashboard(request):
        html = """
        <html>
        <head><title>Selfbot Dashboard</title></head>
        <body>
            <h2>Welcome to the Selfbot Panel</h2>
            <ul>
                <li><a href="/chat">Send Message</a></li>
                <li><a href="/tokens">Manage Tokens</a></li>
                <li><a href="/settings">Settings</a></li>
                <li><a href="/logs">Logs</a></li>
                <li><a href="/community">Community Chat</a></li>
            </ul>
        </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html")
    app.router.add_get("/", dashboard)

    # Example: Message sender page
    async def chat_page(request):
        html = """
        <html>
        <head><title>Send Message</title></head>
        <body>
            <h2>Send Message</h2>
            <form method="POST" action="/chat">
                Channel ID: <input type="text" name="channel_id"><br>
                Message: <textarea name="message"></textarea><br>
                <button type="submit">Send</button>
            </form>
        </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html")

    async def chat_send(request):
        data = await request.post()
        channel_id = data.get("channel_id")
        message = data.get("message")
        # TODO: Use Discord API with user's token to send message
        return web.Response(text=f"Sent message to {channel_id}: {message}", content_type="text/html")

    app.router.add_get("/chat", chat_page)
    app.router.add_post("/chat", chat_send)

    # --- API route for selfbot access check ---
    async def member_status(request):
        user_id = request.query.get("user_id")
        machine_id = request.query.get("machine_id")
        has_access = False
        has_role = False
        try:
            # Check if user has an active key bound to machine_id
            has_access = _has_active_access(int(user_id), str(machine_id))
            # Check if user has the required role
            guild = bot.get_guild(GUILD_ID)
            member = guild.get_member(int(user_id)) if guild else None
            role = guild.get_role(ROLE_ID) if guild else None
            has_role = member and role and role in member.roles
        except Exception:
            pass
        return web.json_response({
            "should_have_access": has_access,
            "has_role": has_role
        })

    app.router.add_get("/api/member-status", member_status)

    # --- Existing routes ---
    app.router.add_post("/nowpayments-ipn", nowpayments_ipn)

    runner = web.AppRunner(app)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    loop.run_until_complete(site.start())

    # Start the Discord bot
    bot.run(BOT_TOKEN)