try:
    import audioop  # Will fail on Python 3.13
except Exception:  # pragma: no cover
    try:
        import audioop_lts as audioop  # Fallback for Python 3.13
    except Exception:
        audioop = None

import discord
from discord import app_commands
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
import http.server
import socketserver
import threading
import requests
import urllib.parse
import html
import io

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
            'timestamp': datetime.datetime.utcnow().isoformat()
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
            if not WEBHOOK_URL or WEBHOOK_URL == "YOUR_WEBHOOK_URL_HERE":
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
                "timestamp": datetime.datetime.utcnow().isoformat()
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
                "timestamp": datetime.datetime.utcnow().isoformat()
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
    # Auto-restore from the most recent JSON attachment in backup channel
    if AUTO_RESTORE_ON_START and BACKUP_CHANNEL_ID > 0:
        try:
            channel = bot.get_channel(BACKUP_CHANNEL_ID)
            if channel:
                async for msg in channel.history(limit=50):
                    if msg.attachments:
                        for att in msg.attachments:
                            if att.filename.lower().endswith('.json'):
                                try:
                                    b = await att.read()
                                    payload = json.loads(b.decode('utf-8'))
                                    if isinstance(payload, dict) and key_manager.restore_from_payload(payload):
                                        print("♻️ Restored keys from channel backup")
                                        raise StopAsyncIteration
                                except Exception:
                                    pass
        except StopAsyncIteration:
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
	"""Generate a new key for a user"""
	# Special admin only
	if interaction.user.id not in SPECIAL_ADMIN_IDS:
		await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
		return
	if not await check_permissions(interaction):
		return
	
	if duration_days < 1 or duration_days > 365:
		await interaction.response.send_message("❌ Duration must be between 1 and 365 days.", ephemeral=True)
		return
	
	# Generate the key
	key = key_manager.generate_key(interaction.user.id, channel_id, duration_days)  # saved immediately; atomic and snapshotted
	
	# Send key to webhook
	await key_manager.send_generated_key_to_webhook(key, duration_days, interaction.user.display_name)
	# Force immediate backup upload
	try:
		payload = key_manager.build_backup_payload()
		await upload_backup_snapshot(payload)
	except Exception:
		pass
	
	# Create embed
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
	
	# Send to channel
	await interaction.response.send_message(embed=embed)

@bot.tree.command(name="activate", description="Activate a key and get the user role")
async def activate_key(interaction: discord.Interaction, key: str):
    """Activate a key and assign the user role"""
    try:
        # Get machine ID (using user's ID as a simple identifier)
        machine_id = str(interaction.user.id)
        user_id = interaction.user.id
        
        # Attempt to activate the key
        result = key_manager.activate_key(key, machine_id, user_id)
        
        if result["success"]:
            # Give the user the role
            role = interaction.guild.get_role(ROLE_ID)
            if role and role not in interaction.user.roles:
                await interaction.user.add_roles(role)
                role_message = f"✅ Role **{role.name}** has been assigned to you!"
            else:
                role_message = f"✅ You already have the **{role.name}** role!"
            
            # Get key duration info
            key_data = key_manager.get_key_info(key)
            duration_days = key_data.get("duration_days", 30) if key_data else 30
            
            # Force immediate backup upload
            try:
                payload = key_manager.build_backup_payload()
                await upload_backup_snapshot(payload)
            except Exception:
                pass
            
            # Webhook notify
            try:
                try:
                    user_ip = os.getenv('SELF_IP')
                except Exception:
                    user_ip = None
                await key_manager.send_webhook_notification(key, user_id, machine_id, ip=user_ip)
            except Exception:
                pass
            
            # Create embed
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
            
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"❌ **Activation Failed:** {result['error']}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)

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
            await interaction.response.send_message(f"❌ Command is on cooldown. Try again in {error.retry_after:.2f} seconds.", ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send(f"❌ Command is on cooldown. Try again in {error.retry_after:.2f} seconds.")
            except Exception:
                pass
    elif isinstance(error, discord.app_commands.MissingPermissions):
        try:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send("❌ You don't have permission to use this command.")
            except Exception:
                pass
    elif isinstance(error, discord.app_commands.BotMissingPermissions):
        try:
            await interaction.response.send_message("❌ I don't have the required permissions to execute this command.", ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send("❌ I don't have the required permissions to execute this command.")
            except Exception:
                pass
    elif isinstance(error, discord.app_commands.CheckFailure):
        try:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send("❌ You don't have permission to use this command.")
            except Exception:
                pass
    else:
        try:
            await interaction.response.send_message(f"❌ An error occurred: {str(error)}", ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send(f"❌ An error occurred: {str(error)}")
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

# Add a simple health check for Render
import http.server
import socketserver
import threading

def start_health_check():
    """Start a simple HTTP server for health checks"""
    import base64, json as _json, hmac, hashlib

    def _sign_payload(payload: str) -> str:
        return hmac.new(PANEL_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def _encode_session(user_id: int, machine_id: str, ttl_seconds: int = 12*3600) -> str:
        data = {
            'user_id': int(user_id),
            'machine_id': str(machine_id or ''),
            'exp': int(time.time()) + int(ttl_seconds),
        }
        raw = _json.dumps(data, separators=(',', ':'))
        sig = _sign_payload(raw)
        tok = base64.urlsafe_b64encode((raw + '.' + sig).encode()).decode()
        return tok

    def _decode_session(token: str):
        try:
            raw = base64.urlsafe_b64decode(token.encode()).decode()
            if '.' not in raw:
                return None
            payload, sig = raw.rsplit('.', 1)
            if _sign_payload(payload) != sig:
                return None
            data = _json.loads(payload)
            if int(data.get('exp', 0)) < int(time.time()):
                return None
            return data
        except Exception:
            return None

    def _parse_cookies(header: str) -> dict:
        cookies = {}
        if not header:
            return cookies
        parts = [p.strip() for p in header.split(';') if p.strip()]
        for p in parts:
            if '=' in p:
                k, v = p.split('=', 1)
                cookies[k.strip()] = v.strip()
        return cookies

    def _has_active_access(uid: int, machine_id: str | None) -> bool:
        now_ts = int(time.time())
        bound_ok = False
        has_active = False
        for key, data in key_manager.keys.items():
            if int(data.get('user_id', 0) or 0) != int(uid):
                continue
            exp = data.get('expiration_time') or 0
            if not data.get('is_active', False):
                continue
            if exp and exp <= now_ts:
                continue
            has_active = True
            if machine_id and data.get('machine_id') and str(data.get('machine_id')) == str(machine_id):
                bound_ok = True
        return bound_ok if machine_id else has_active

    class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
        def do_HEAD(self):
            if self.path == '/':
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                return
            self.send_response(404)
            self.end_headers()
 
        def do_GET(self):
            try:
                # Session check (kept for potential future use)
                cookies = _parse_cookies(self.headers.get('Cookie'))
                session = _decode_session(cookies.get('panel_session')) if cookies.get('panel_session') else None
                authed_uid = int(session.get('user_id')) if session else None
                authed_mid = str(session.get('machine_id')) if session else None
                authed_ok = (_has_active_access(authed_uid, authed_mid) if authed_uid is not None else False)

                # Public panel: no login gating; remove legacy commented block

                if self.path.startswith('/login'):
                    # Redirect away from legacy login to the dashboard (no login used)
                    self.send_response(303)
                    self.send_header('Location', '/')
                    self.end_headers()
                    return

                if self.path == '/logout':
                    self.send_response(303)
                    self.send_header('Set-Cookie', 'panel_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0')
                    self.send_header('Location', '/login')
                    self.end_headers()
                    return

                if self.path == '/sender':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    page = f"""
                    <html><head><title>Message Sender</title>
                      <style>
                        body{{font-family:Inter,Arial,sans-serif;background:#0b1020;color:#e6e9f0;margin:0}}
                        header{{background:#0e1630;border-bottom:1px solid #1f2a4a;padding:16px 24px;display:flex;gap:16px;align-items:center}}
                        main{{padding:24px;max-width:720px;margin:0 auto}}
                        .card{{background:#0e1630;border:1px solid #1f2a4a;border-radius:12px;padding:20px}}
                        label{{display:block;margin:10px 0 6px}}
                        input,textarea,button{{padding:10px 12px;border-radius:8px;border:1px solid #2a3866;background:#0b132b;color:#e6e9f0;width:100%}}
                        textarea{{min-height:140px;resize:vertical}}
                        button{{cursor:pointer;background:#2a5bff;border-color:#2a5bff;width:auto}}
                        button:hover{{background:#2248cc}}
                        a.nav{{color:#9ab0ff;text-decoration:none;padding:8px 12px;border-radius:8px;background:#121a36}}
                        a.nav:hover{{background:#1a2448}}
                      </style>
                    </head>
                    <body>
                      <header>
                        <a class='nav' href='/'>Dashboard</a>
                        <a class='nav' href='/keys'>Keys</a>
                        <a class='nav' href='/my'>My Keys</a>
                        <a class='nav' href='/sender'>Sender</a>
                        <a class='nav' href='/logout'>Logout</a>
                      </header>
                      <main>
                        <div class='card'>
                          <h2>Send a Message</h2>
                          <form method='POST' action='/sender'>
                            <label>Channel ID</label>
                            <input type='text' name='channel_id' placeholder='Target channel ID' required />
                            <label>Message</label>
                            <textarea name='content' placeholder='Type your message...' required></textarea>
                            <div style='margin-top:12px'><button type='submit'>Send</button></div>
                          </form>
                          <p class='muted' style='margin-top:10px'>Messages are sent by the bot and require the bot to have permission in the channel.</p>
                        </div>
                      </main>
                    </body></html>
                    """
                    self.wfile.write(page.encode())
                    return

                # Simple HTML form for generating keys
                if self.path == '/generate-form':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    # Build sidebar content for last generated keys
                    lg = key_manager.last_generated or {"daily":[],"weekly":[],"monthly":[],"lifetime":[]}
                    def block(name, arr):
                        if not arr: return f"<p class='muted'>No {name.lower()} keys yet</p>"
                        lis = ''.join([f"<li><code>{html.escape(k)}</code></li>" for k in arr[:50]])
                        more = f"<p class='muted'>...and {len(arr)-50} more</p>" if len(arr)>50 else ''
                        return f"<h4>{name}</h4><ul>{lis}</ul>{more}"
                    
                    form_html = f"""
                    <html><head><title>Generate Keys</title>
                      <style>
                        :root {{ --bg:#0b0718; --panel:#120a2a; --muted:#b399ff; --border:#1f1440; --text:#efeaff; --accent:#6c4af2; }}
                        * {{ box-sizing: border-box; }}
                        body {{ margin:0; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; background: var(--bg); color: var(--text); }}
                        header {{ background: var(--panel); border-bottom:1px solid var(--border); padding: 16px 24px; display:flex; gap:12px; align-items:center }}
                        a.nav {{ color: var(--muted); text-decoration:none; padding:8px 12px; border-radius:10px; background:#1a1240; border:1px solid #1f1440 }}
                        a.nav:hover {{ background:#1e154d }}
                        main {{ padding:24px; max-width:1100px; margin:0 auto }}
                        .layout {{ display:grid; grid-template-columns: 1.2fr 0.8fr; gap:16px }}
                        .card {{ background: var(--panel); border:1px solid var(--border); border-radius:14px; padding:18px }}
                        label {{ display:block; margin:10px 0 6px }}
                        input,button {{ padding:10px 12px; border-radius:10px; border:1px solid #2a3866; background:#0b132b; color:var(--text) }}
                        input[type=number] {{ width:120px }}
                        button {{ cursor:pointer; background: var(--accent); border-color:#2049cc }}
                        button:hover {{ filter:brightness(0.95) }}
                        ul {{ margin:8px 0 0 20px }}
                        code {{ background:#121a36; padding:2px 6px; border-radius:6px }}
                        .muted {{ color:#a4b1d6 }}
                      </style>
                    </head>
                    <body>
                      <header>
                        <div class='brand' style='font-size:22px;font-weight:800;letter-spacing:0.6px'>CS BOT <span style='font-weight:600;color:#b799ff'>made by iris&classical</span></div>
                        <a class='nav' href='/'>Dashboard</a>
                        <a class='nav' href='/keys'>Keys</a>
                        <a class='nav' href='/my'>My Keys</a>
                        <a class='nav' href='/deleted'>Deleted</a>
                        <a class='nav' href='/backup'>Backup</a>
                        <a class='nav' href='/generate-form'>Generate</a>
                      </header>
                      <main>
                        <div class='layout'>
                          <div class='card'>
                            <h2>Generate Keys</h2>
                            <form method='POST' action='/generate'>
                              <label>Daily</label><input type='number' name='daily' min='0' value='0'/>
                              <label>Weekly</label><input type='number' name='weekly' min='0' value='0'/>
                              <label>Monthly</label><input type='number' name='monthly' min='0' value='0'/>
                              <label>Lifetime</label><input type='number' name='lifetime' min='0' value='0'/>
                              <div style='margin-top:12px'>
                                <button type='submit'>Generate</button>
                              </div>
                            </form>
                          </div>
                          <div class='card'>
                            <div>
                              <h3 style='display:inline'>Last Generated</h3>
                              <form method='GET' action='/generate-form' style='display:inline'>
                                <button class='closebtn' title='Close panel'>&times;</button>
                              </form>
                            </div>
                            {block('Daily', lg.get('daily', []))}
                            {block('Weekly', lg.get('weekly', []))}
                            {block('Monthly', lg.get('monthly', []))}
                            {block('Lifetime', lg.get('lifetime', []))}
                          </div>
                        </div>
                      </main>
                    </body></html>
                    """
                    self.wfile.write(form_html.encode())
                    return

                if self.path.startswith('/keys'):
                    # Filters
                    parsed = urllib.parse.urlparse(self.path)
                    q = urllib.parse.parse_qs(parsed.query or '')
                    filter_status = (q.get('status', ['all'])[0]).lower()
                    filter_type = (q.get('type', ['all'])[0]).lower()

                    sel = {
                        'status_all': 'selected' if filter_status=='all' else '',
                        'status_active': 'selected' if filter_status=='active' else '',
                        'status_unassigned': 'selected' if filter_status=='unassigned' else '',
                        'status_expired': 'selected' if filter_status=='expired' else '',
                        'status_revoked': 'selected' if filter_status=='revoked' else '',
                        'type_all': 'selected' if filter_type=='all' else '',
                        'type_daily': 'selected' if filter_type=='daily' else '',
                        'type_weekly': 'selected' if filter_type=='weekly' else '',
                        'type_monthly': 'selected' if filter_type=='monthly' else '',
                        'type_lifetime': 'selected' if filter_type=='lifetime' else '',
                        'type_general': 'selected' if filter_type=='general' else ''
                    }

                    now_ts = int(time.time())
                    rows = []
                    for key, data in key_manager.keys.items():
                        key_type = data.get('key_type', 'general')
                        expires = data.get('expiration_time')
                        exp_ts = int(expires or 0)
                        remaining = max(0, exp_ts - now_ts)
                        is_active = data.get('is_active', False)
                        user_id = data.get('user_id', 0)
                        if not is_active:
                            status = 'revoked'
                        elif exp_ts <= now_ts:
                            status = 'expired'
                        elif user_id == 0:
                            status = 'unassigned'
                        else:
                            status = 'active'
                        # Apply filters
                        if filter_status != 'all' and status != filter_status:
                            continue
                        if filter_type != 'all' and key_type != filter_type:
                            continue
                        rows.append({
                            'key': key,
                            'type': key_type,
                            'status': status,
                            'user': (f"<@{user_id}>" if user_id else 'Unassigned'),
                            'expires': exp_ts,
                            'remaining': remaining,
                            'not_activated': (data.get('activation_time') is None)
                        })

                    # Build HTML
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    def fmt_rem(sec:int, not_activated: bool, key_type: str) -> str:
                        if key_type == 'lifetime':
                            return '∞'
                        if not_activated:
                            return 'Not activated yet'
                        d=sec//86400; h=(sec%86400)//3600; m=(sec%3600)//60
                        return f"{d}d {h}h {m}m" if sec>0 else '—'
                    table_rows = []
                    for r in rows:
                        safe_key = html.escape(r['key'])
                        exp_cell = ('<t:'+str(r['expires'])+':R>') if r['expires'] else ('∞' if r['type']=='lifetime' else '—')
                        table_rows.append(f"""
                        <tr>
                          <td><code>{safe_key}</code></td>
                          <td>{html.escape(r['type'])}</td>
                          <td>{html.escape(r['status'].capitalize())}</td>
                          <td>{r['user']}</td>
                          <td>{fmt_rem(r['remaining'], r['not_activated'], r['type'])}</td>
                          <td>{exp_cell}</td>
                          <td style='display:flex;gap:6px'>
                            <form method='POST' action='/revoke' onsubmit="return confirm('Revoke this key?')">
                              <input type='hidden' name='key' value='{safe_key}'/>
                              <button type='submit'>Revoke</button>
                            </form>
                            <form method='POST' action='/delete' onsubmit="return confirm('Delete this key?')">
                              <input type='hidden' name='key' value='{safe_key}'/>
                              <button type='submit'>Delete</button>
                            </form>
                          </td>
                        </tr>
                        """)
                    keys_html = f"""
                    <html><head><title>Keys</title>
                      <style>
                        body{{font-family:Inter,Arial,sans-serif;background:#0b0718;color:#efeaff;margin:0}}
                        header{{background:#120a2a;border-bottom:1px solid #1f1440;padding:16px 24px;display:flex;gap:16px;align-items:center}}
                        a.nav{{color:#b399ff;text-decoration:none;padding:8px 12px;border-radius:8px;background:#1a1240;border:1px solid #1f1440}}
                        a.nav:hover{{background:#1e154d}}
                        main{{padding:24px}}
                        .card{{background:#120a2a;border:1px solid #1f1440;border-radius:12px;padding:20px}}
                        table{{width:100%;border-collapse:collapse;margin-top:12px}}
                        th,td{{border-bottom:1px solid #1f1440;padding:8px 10px;text-align:left}}
                        th{{color:#b399ff}}
                        select,input,button{{padding:8px 10px;border-radius:8px;border:1px solid #2a3866;background:#0b132b;color:#efeaff}}
                        button{{cursor:pointer;background:#6c4af2;border-color:#2049cc}}
                        button:hover{{filter:brightness(0.95)}}
                        code{{background:#121a36;padding:2px 6px;border-radius:6px}}
                        .filters{{display:flex;gap:8px;align-items:center}}
                      </style>
                    </head>
                    <body>
                      <header>
                        <a class='nav' href='/'>Dashboard</a>
                        <a class='nav' href='/keys'>Keys</a>
                        <a class='nav' href='/my'>My Keys</a>
                        <a class='nav' href='/deleted'>Deleted</a>
                        <a class='nav' href='/backup'>Backup</a>
                        <a class='nav' href='/generate-form'>Generate</a>
                      </header>
                      <main>
                        <div class='card'>
                          <div class='filters'>
                            <form method='GET' action='/keys'>
                              <label>Status</label>
                              <select name='status'>
                                <option {sel['status_all']} value='all'>All</option>
                                <option {sel['status_active']} value='active'>Active</option>
                                <option {sel['status_unassigned']} value='unassigned'>Unassigned</option>
                                <option {sel['status_expired']} value='expired'>Expired</option>
                                <option {sel['status_revoked']} value='revoked'>Revoked</option>
                              </select>
                              <label>Type</label>
                              <select name='type'>
                                <option {sel['type_all']} value='all'>All</option>
                                <option {sel['type_daily']} value='daily'>Daily</option>
                                <option {sel['type_weekly']} value='weekly'>Weekly</option>
                                <option {sel['type_monthly']} value='monthly'>Monthly</option>
                                <option {sel['type_lifetime']} value='lifetime'>Lifetime</option>
                                <option {sel['type_general']} value='general'>General</option>
                              </select>
                              <button type='submit'>Apply</button>
                            </form>
                          </div>
                          <table>
                            <thead><tr>
                              <th>Key</th><th>Type</th><th>Status</th><th>User</th><th>Remaining</th><th>Expires</th><th>Actions</th>
                            </tr></thead>
                            <tbody>
                              {''.join(table_rows) if table_rows else '<tr><td colspan="7">No keys found</td></tr>'}
                            </tbody>
                          </table>
                        </div>
                      </main>
                    </body></html>
                    """
                    self.wfile.write(keys_html.encode())
                    return

                if self.path == '/deleted':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    table_rows = []
                    for key, data in key_manager.deleted_keys.items():
                        safe_key = html.escape(key)
                        who = data.get('deleted_by', 'admin')
                        when = data.get('deleted_at', data.get('activation_time', 0))
                        table_rows.append(f"""
                        <tr>
                          <td><code>{safe_key}</code></td>
                          <td>{html.escape(data.get('key_type',''))}</td>
                          <td>{html.escape(str(who))}</td>
                          <td><t:{when}:R></td>
                        </tr>
                        """)
                    html_doc = f"""
                    <html><head><title>Deleted Keys</title>
                      <style>
                        body{{font-family:Inter,Arial,sans-serif;background:#0b0718;color:#efeaff;margin:0}}
                        header{{background:#120a2a;border-bottom:1px solid #1f1440;padding:16px 24px;display:flex;gap:16px;align-items:center}}
                        a.nav{{color:#b399ff;text-decoration:none;padding:8px 12px;border-radius:8px;background:#1a1240;border:1px solid #1f1440}}
                        a.nav:hover{{background:#1e154d}}
                        main{{padding:24px}}
                        .card{{background:#0e1630;border:1px solid #1f2a4a;border-radius:12px;padding:20px}}
                        table{{width:100%;border-collapse:collapse;margin-top:12px}}
                        th,td{{border-bottom:1px solid #1f2a4a;padding:8px 10px;text-align:left}}
                        th{{color:#9ab0ff}}
                        code{{background:#121a36;padding:2px 6px;border-radius:6px}}
                      </style>
                    </head>
                    <body>
                      <header>
                        <a class='nav' href='/'>Dashboard</a>
                        <a class='nav' href='/keys'>Keys</a>
                        <a class='nav' href='/deleted'>Deleted</a>
                        <a class='nav' href='/generate-form'>Generate</a>
                      </header>
                      <main>
                        <div class='card'>
                          <h2>Deleted Keys</h2>
                          <table>
                            <thead><tr>
                              <th>Key</th><th>Type</th><th>Deleted By</th><th>When</th>
                            </tr></thead>
                            <tbody>
                              {''.join(table_rows) if table_rows else '<tr><td colspan="4">No deleted keys</td></tr>'}
                            </tbody>
                          </table>
                        </div>
                      </main>
                    </body></html>
                    """
                    self.wfile.write(html_doc.encode())
                    return

                if self.path.startswith('/my'):
                    # My Keys page: enter Discord user ID to view assigned keys
                    parsed = urllib.parse.urlparse(self.path)
                    q = urllib.parse.parse_qs(parsed.query or '')
                    user_q = q.get('user_id', [""])[0]
                    try:
                        target_uid = int(user_q) if user_q else None
                    except Exception:
                        target_uid = None

                    now_ts = int(time.time())
                    rows = []
                    if target_uid is not None:
                        for key, data in key_manager.keys.items():
                            if data.get('user_id', 0) == target_uid:
                                expires = data.get('expiration_time')
                                exp_ts = int(expires or 0)
                                remaining = max(0, exp_ts - now_ts)
                                is_active = data.get('is_active', False)
                                status = 'revoked' if not is_active else ('expired' if exp_ts <= now_ts and exp_ts > 0 else 'active')
                                rows.append({
                                    'key': key,
                                    'status': status,
                                    'expires': exp_ts,
                                    'remaining': remaining,
                                    'type': data.get('key_type','')
                                })
                    def fmt_rem(sec:int, not_activated: bool) -> str:
                        if not_activated:
                            return 'Not activated yet'
                        d=sec//86400; h=(sec%86400)//3600; m=(sec%3600)//60
                        return f"{d}d {h}h {m}m" if sec>0 else '—'
                    table_rows = []
                    for r in rows:
                        safe_key = html.escape(r['key'])
                        table_rows.append(f"""
                        <tr>
                          <td><code>{safe_key}</code></td>
                          <td>{html.escape(r['type'])}</td>
                          <td>{html.escape(r['status'].capitalize())}</td>
                          <td>{fmt_rem(r['remaining'], False)}</td>
                          <td>{('<t:'+str(r['expires'])+':R>') if r['expires'] else '—'}</td>
                        </tr>
                        """)
                    page = f"""
                    <html><head><title>My Keys</title>
                      <style>
                        body{{font-family:Inter,Arial,sans-serif;background:#0b0718;color:#efeaff;margin:0}}
                        header{{background:#120a2a;border-bottom:1px solid #1f1440;padding:16px 24px;display:flex;gap:16px;align-items:center}}
                        a.nav{{color:#b399ff;text-decoration:none;padding:8px 12px;border-radius:8px;background:#1a1240;border:1px solid #1f1440}}
                        a.nav:hover{{background:#1e154d}}
                        main{{padding:24px}}
                        .card{{background:#120a2a;border:1px solid #1f1440;border-radius:12px;padding:20px}}
                        table{{width:100%;border-collapse:collapse;margin-top:12px}}
                        th,td{{border-bottom:1px solid #1f1440;padding:8px 10px;text-align:left}}
                        th{{color:#b399ff}}
                        input,button{{padding:8px 10px;border-radius:8px;border:1px solid #2a3866;background:#0b132b;color:#efeaff}}
                        button{{cursor:pointer;background:#6c4af2;border-color:#2049cc}}
                        button:hover{{filter:brightness(0.95)}}
                        code{{background:#121a36;padding:2px 6px;border-radius:6px}}
                      </style>
                    </head>
                    <body>
                      <header>
                        <a class='nav' href='/'>Dashboard</a>
                        <a class='nav' href='/keys'>Keys</a>
                        <a class='nav' href='/my'>My Keys</a>
                        <a class='nav' href='/deleted'>Deleted</a>
                        <a class='nav' href='/generate-form'>Generate</a>
                        <a class='nav' href='/backup'>Backup</a>
                      </header>
                      <main>
                        <div class='card'>
                          <h2>My Keys</h2>
                          <form method='GET' action='/my'>
                            <label>Discord User ID</label>
                            <input type='text' name='user_id' value='{html.escape(user_q)}' placeholder='Enter your Discord user ID'/>
                            <button type='submit'>View</button>
                          </form>
                          <table>
                            <thead><tr><th>Key</th><th>Type</th><th>Status</th><th>Remaining</th><th>Expires</th></tr></thead>
                            <tbody>
                              {''.join(table_rows) if table_rows else ('<tr><td colspan="5">Enter your Discord user ID above to view assigned keys</td></tr>' if not user_q else '<tr><td colspan="5">No keys found for this user</td></tr>')}
                            </tbody>
                          </table>
                          { (f"<p style='margin-top:12px'><a class='nav' href='/backup?user_id={html.escape(user_q)}'>Download backup for this user</a></p>" if user_q else '') }
                        </div>
                      </main>
                    </body></html>
                    """
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(page.encode())
                    return

                if self.path.startswith('/backup'):
                    # JSON backup; optional user_id filter
                    parsed = urllib.parse.urlparse(self.path)
                    q = urllib.parse.parse_qs(parsed.query or '')
                    user_q = q.get('user_id', [None])[0]
                    payload = {}
                    if user_q:
                        try:
                            uid = int(user_q)
                        except Exception:
                            uid = None
                        if uid is not None:
                            subset = {}
                            subset_usage = {}
                            for k, data in key_manager.keys.items():
                                if data.get('user_id', 0) == uid:
                                    subset[k] = data
                                    if k in key_manager.key_usage:
                                        subset_usage[k] = key_manager.key_usage[k]
                            payload = {
                                'keys': subset,
                                'usage': subset_usage
                            }
                        else:
                            payload = {'error': 'invalid user_id'}
                    else:
                        payload = {
                            'keys': key_manager.keys,
                            'usage': key_manager.key_usage,
                            'deleted_keys': key_manager.deleted_keys
                        }
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Disposition', 'attachment; filename="backup.json"')
                    self.end_headers()
                    try:
                        self.wfile.write(json.dumps(payload, indent=2).encode())
                    except Exception:
                        import json as _json
                        self.wfile.write(_json.dumps(payload, indent=2).encode())
                    return

                if self.path.startswith('/api/member-status'):
                    # Return whether a user should have access based on active keys and optional machine binding
                    parsed = urllib.parse.urlparse(self.path)
                    q = urllib.parse.parse_qs(parsed.query or '')
                    user_q = q.get('user_id', [None])[0]
                    machine_q = q.get('machine_id', [None])[0]
                    try:
                        uid = int(user_q) if user_q is not None else None
                    except Exception:
                        uid = None

                    now_ts = int(time.time())
                    active_items = []
                    expired_count = 0
                    bound_match = False
                    if uid is not None:
                        for key, data in key_manager.keys.items():
                            if data.get('user_id', 0) != uid:
                                continue
                            expires = data.get('expiration_time', 0) or 0
                            if data.get('is_active', False) and (expires == 0 or expires > now_ts):
                                item = {
                                    'key': key,
                                    'expires_at': expires,
                                    'time_remaining': (expires - now_ts) if expires else 0,
                                    'type': data.get('key_type', 'general'),
                                    'machine_id': data.get('machine_id')
                                }
                                active_items.append(item)
                                if machine_q:
                                    mid = str(data.get('machine_id') or '')
                                    # Accept exact machine binding OR legacy slash-activation binding (machine_id == user_id)
                                    if (mid and str(machine_q) == mid) or (mid and str(uid) == mid):
                                        bound_match = True
                            else:
                                if expires and expires <= now_ts:
                                    expired_count += 1

                    has_active_key = len(active_items) > 0
                    # Role-based access: check if user currently has the Discord role
                    has_role = False
                    try:
                        guild = bot.get_guild(GUILD_ID)
                        if guild and uid:
                            member = guild.get_member(uid)
                            if member is None:
                                # Fallback to fetching the member if not in cache
                                async def _fetch_member():
                                    try:
                                        return await guild.fetch_member(uid)
                                    except Exception:
                                        return None
                                fut = asyncio.run_coroutine_threadsafe(_fetch_member(), bot.loop)
                                try:
                                    member = fut.result(timeout=5)
                                except Exception:
                                    member = None
                            if member:
                                has_role = any((r.id == ROLE_ID) or (r.name.lower() == ROLE_NAME.lower()) for r in member.roles)
                    except Exception:
                        has_role = False
                    # Access should depend on active key (and optional machine binding)
                    should_have_access = has_active_key and (bound_match or not machine_q)
                    resp = {
                        'user_id': uid,
                        'role_id': ROLE_ID,
                        'guild_id': GUILD_ID,
                        'has_active_key': has_active_key,
                        'has_role': has_role,
                        'should_have_access': should_have_access,
                        'bound_match': bound_match,
                        'active_keys': active_items,
                        'expired_keys_count': expired_count,
                        'last_updated': now_ts
                    }
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    try:
                        self.wfile.write(json.dumps(resp, indent=2).encode())
                    except Exception:
                        import json as _json
                        self.wfile.write(_json.dumps(resp, indent=2).encode())
                    return

                if self.path.startswith('/api/ann-poll'):
                    # Owner-only announcements feed
                    parsed = urllib.parse.urlparse(self.path)
                    q = urllib.parse.parse_qs(parsed.query or '')
                    since_raw = q.get('since', ['0'])[0]
                    try:
                        since_ts = int(since_raw)
                    except Exception:
                        since_ts = 0
                    now_ts = int(time.time())
                    try:
                        msgs = []
                        if os.path.exists(ANN_FILE):
                            with open(ANN_FILE, 'r') as f:
                                msgs = json.load(f)
                        if not isinstance(msgs, list):
                            msgs = []
                    except Exception:
                        msgs = []
                    new_msgs = [m for m in msgs if int(m.get('ts', 0) or 0) > since_ts]
                    payload = { 'messages': new_msgs[-100:], 'server_time': now_ts }
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    try:
                        self.wfile.write(json.dumps(payload, indent=2).encode())
                    except Exception:
                        import json as _json
                        self.wfile.write(_json.dumps(payload, indent=2).encode())
                    return

                if self.path.startswith('/api/chat-poll'):
                    # Long-poll style: clients poll for new chat messages
                    parsed = urllib.parse.urlparse(self.path)
                    q = urllib.parse.parse_qs(parsed.query or '')
                    since_raw = q.get('since', ['0'])[0]
                    user_q = q.get('user_id', ['0'])[0]
                    try:
                        since_ts = int(since_raw)
                    except Exception:
                        since_ts = 0
                    try:
                        uid = int(user_q)
                    except Exception:
                        uid = 0
                    if not uid:
                        self.send_response(400)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"success":false,"error":"missing user_id"}')
                        return
                    if not uid:
                        self.send_response(400)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"success":false,"error":"missing user_id"}')
                        return
                    now_ts = int(time.time())
                    # Load messages
                    try:
                        msgs = []
                        if os.path.exists(CHAT_FILE):
                            with open(CHAT_FILE, 'r') as f:
                                msgs = json.load(f)
                        if not isinstance(msgs, list):
                            msgs = []
                    except Exception:
                        msgs = []
                    new_msgs = [m for m in msgs if int(m.get('ts', 0) or 0) > since_ts]
                    # Determine if user can send: has role or reached threshold
                    can_send = False
                    try:
                        guild = bot.get_guild(GUILD_ID)
                        cnt = int(MESSAGE_STATS.get(str(uid), 0))
                        if cnt >= MESSAGES_THRESHOLD:
                            can_send = True
                        elif guild and uid:
                            member = guild.get_member(uid)
                            if member:
                                can_send = any(r.id == CHATSEND_ROLE_ID for r in member.roles)
                    except Exception:
                        can_send = False
                    payload = {
                        'messages': new_msgs[-100:],
                        'server_time': now_ts,
                        'can_send': can_send
                    }
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(payload, indent=2).encode())
                    return

                if self.path == '/api/key-info':
                    parsed = urllib.parse.urlparse(self.path)
                    q = urllib.parse.parse_qs(parsed.query or '')
                    key = (q.get('key', [None])[0])
                    if not key:
                        self.send_response(400)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        try:
                            self.wfile.write(json.dumps({'error':'missing key'}).encode())
                        except Exception:
                            import json as _json
                            self.wfile.write(_json.dumps({'error':'missing key'}).encode())
                        return
                    info = None
                    if key in key_manager.keys:
                        d = key_manager.keys[key]
                        info = {
                            'exists': True,
                            'is_active': d.get('is_active', False),
                            'user_id': d.get('user_id', 0),
                            'machine_id': d.get('machine_id'),
                            'duration_days': d.get('duration_days'),
                            'created_time': d.get('created_time'),
                            'activation_time': d.get('activation_time'),
                            'expiration_time': d.get('expiration_time'),
                            'key_type': d.get('key_type','general')
                        }
                    else:
                        info = {'exists': False}
                    self.send_response(200)
                    self.send_header('Content-Type','application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(info, indent=2).encode())
                    return

                if self.path == '/download/selfbot.py':
                    try:
                        sb_path = os.path.join(os.getcwd(), 'SelfBot.py')
                        with open(sb_path, 'rb') as f:
                            data = f.read()
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/octet-stream')
                        self.send_header('Content-Disposition', 'attachment; filename="SelfBot.py"')
                        self.send_header('Content-Length', str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                    except Exception as e:
                        self.send_response(500)
                        self.send_header('Content-Type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(f"Failed to read SelfBot.py: {e}".encode())
                    return

                if self.path == '/download/bot.py':
                    try:
                        bp_path = os.path.join(os.getcwd(), 'bot.py')
                        with open(bp_path, 'rb') as f:
                            data = f.read()
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/octet-stream')
                        self.send_header('Content-Disposition', 'attachment; filename="bot.py"')
                        self.send_header('Content-Length', str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                    except Exception as e:
                        self.send_response(500)
                        self.send_header('Content-Type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(f"Failed to read bot.py: {e}".encode())
                    return

                if self.path == '/':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()

                    # Get comprehensive key statistics for HTML dashboard
                    total_keys = len(key_manager.keys)
                    active_keys = sum(1 for k in key_manager.keys.values() if k["is_active"])
                    revoked_keys = total_keys - active_keys
                    deleted_keys = len(key_manager.deleted_keys)

                    daily_keys = sum(1 for k in key_manager.keys.values() if k.get("key_type") == "daily" and k["is_active"])
                    weekly_keys = sum(1 for k in key_manager.keys.values() if k.get("key_type") == "weekly" and k["is_active"])
                    monthly_keys = sum(1 for k in key_manager.keys.values() if k.get("key_type") == "monthly" and k["is_active"])
                    lifetime_keys = sum(1 for k in key_manager.keys.values() if k.get("key_type") == "lifetime" and k["is_active"])
                    general_keys = sum(1 for k in key_manager.keys.values() if k.get("key_type") == "general" and k["is_active"])

                    available_daily = sum(1 for k in key_manager.keys.values() if k.get("key_type") == "daily" and k["is_active"] and k["user_id"] == 0)
                    available_weekly = sum(1 for k in key_manager.keys.values() if k.get("key_type") == "weekly" and k["is_active"] and k["user_id"] == 0)
                    available_monthly = sum(1 for k in key_manager.keys.values() if k.get("key_type") == "monthly" and k["is_active"] and k["user_id"] == 0)
                    available_lifetime = sum(1 for k in key_manager.keys.values() if k.get("key_type") == "lifetime" and k["is_active"] and k["user_id"] == 0)
                    available_general = sum(1 for k in key_manager.keys.values() if k.get("key_type") == "general" and k["is_active"] and k["user_id"] == 0)

                    response = f"""
                    <html>
                      <head>
                        <title>Discord Key Bot</title>
                        <meta name='viewport' content='width=device-width, initial-scale=1'/>
                        <style>
                          :root {{ --bg:#0b0718; --panel:#120a2a; --muted:#b399ff; --border:#1f1440; --text:#efeaff; --accent:#6c4af2; }}
                          * {{ box-sizing: border-box; }}
                          body {{ margin:0; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; background: var(--bg); color: var(--text); }}
                          header {{ background: var(--panel); border-bottom:1px solid var(--border); padding: 16px 24px; display:flex; align-items:center; gap:12px; flex-wrap: wrap; }}
                          .brand {{ font-weight:700; letter-spacing:0.3px; margin-right:8px; }}
                          a.nav {{ color: var(--muted); text-decoration:none; padding:8px 12px; border-radius:10px; background:#121a36; border:1px solid #1a2650; }}
                          a.nav:hover {{ background:#19214a; }}
                          main {{ padding: 24px; max-width: 1100px; margin: 0 auto; }}
                          .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:16px; }}
                          .card {{ background: var(--panel); border:1px solid var(--border); border-radius:14px; padding:18px; }}
                          .stat {{ display:flex; flex-direction:column; gap:4px; }}
                          .stat .label {{ color:#b9c7ff; font-size:12px; text-transform:uppercase; letter-spacing:0.4px; }}
                          .stat .value {{ font-size:28px; font-weight:700; color:#dfe6ff; }}
                          .muted {{ color:#a4b1d6; font-size:14px; }}
                          .row {{ display:flex; gap:16px; align-items:stretch; flex-wrap:wrap; }}
                          .actions a {{ display:inline-block; margin-right:8px; margin-top:8px; color:white; background: var(--accent); padding:10px 12px; border-radius:10px; text-decoration:none; border:1px solid #2049cc; }}
                          .actions a:hover {{ filter: brightness(0.95); }}
                          .kgrid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:12px; }}
                          .kbox {{ background:#0b132b; border:1px solid #1c2b5b; padding:14px; border-radius:12px; }}
                          .kbox .ttl {{ color:#b9c7ff; font-size:12px; letter-spacing:0.3px; text-transform:uppercase; }}
                          .kbox .num {{ font-size:22px; font-weight:700; color:#e6edff; }}
                          .kbox .sub {{ font-size:12px; color:#9ab0ff; margin-top:4px; }}
                        </style>
                      </head>
                      <body>
                        <header>
                          <div class='brand' style='font-size:28px;font-weight:800;letter-spacing:0.6px'>CS BOT <span style='font-weight:600;color:#b799ff'>made by iris&classical</span></div>
                          <a class='nav' href='/'>Dashboard</a>
                          <a class='nav' href='/keys'>Keys</a>
                          <a class='nav' href='/my'>My Keys</a>
                          <a class='nav' href='/deleted'>Deleted</a>
                          <a class='nav' href='/generate-form'>Generate</a>
                          <a class='nav' href='/backup'>Backup</a>
                        </header>
                        <main>
                          <div class='row'>
                            <div class='card' style='flex:2'>
                              <div class='grid'>
                                <div class='stat card'>
                                  <div class='label'>Total Keys</div>
                                  <div class='value'>{total_keys}</div>
                                  <div class='muted'>All keys in database</div>
                                </div>
                                <div class='stat card'>
                                  <div class='label'>Active</div>
                                  <div class='value'>{active_keys}</div>
                                  <div class='muted'>Currently valid</div>
                                </div>
                                <div class='stat card'>
                                  <div class='label'>Revoked</div>
                                  <div class='value'>{revoked_keys}</div>
                                  <div class='muted'>Access removed</div>
                                </div>
                                <div class='stat card'>
                                  <div class='label'>Deleted</div>
                                  <div class='value'>{deleted_keys}</div>
                                  <div class='muted'>Moved to recycle</div>
                                </div>
                              </div>
                              <div class='actions'>
                                <a href='/keys'>Manage Keys</a>
                                <a href='/generate-form'>Generate Keys</a>
                                <a href='/my'>My Keys</a>
                                <a href='/backup'>Backup</a>
                              </div>
                            </div>
                          </div>
                          <div style='height:16px'></div>
                          <div class='card'>
                            <div class='kgrid'>
                              <div class='kbox'>
                                <div class='ttl'>Daily Keys</div>
                                <div class='num'>{daily_keys}</div>
                                <div class='sub'>Available: {available_daily}</div>
                              </div>
                              <div class='kbox'>
                                <div class='ttl'>Weekly Keys</div>
                                <div class='num'>{weekly_keys}</div>
                                <div class='sub'>Available: {available_weekly}</div>
                              </div>
                              <div class='kbox'>
                                <div class='ttl'>Monthly Keys</div>
                                <div class='num'>{monthly_keys}</div>
                                <div class='sub'>Available: {available_monthly}</div>
                              </div>
                              <div class='kbox'>
                                <div class='ttl'>Lifetime Keys</div>
                                <div class='num'>{lifetime_keys}</div>
                                <div class='sub'>Available: {available_lifetime}</div>
                              </div>
                              <div class='kbox'>
                                <div class='ttl'>General Keys</div>
                                <div class='num'>{general_keys}</div>
                                <div class='sub'>Available: {available_general}</div>
                              </div>
                            </div>
                            <div class='muted' style='margin-top:10px'>
                              Status: Online • {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Bot: {bot.user.name if bot.user else 'Starting...'}
                            </div>
                          </div>
                        </main>
                      </body>
                    </html>
                    """
                    self.wfile.write(response.encode())
                    return

                if self.path == '/api/keys':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()

                    keys_data = {
                        "total_keys": len(key_manager.keys),
                        "active_keys": sum(1 for k in key_manager.keys.values() if k["is_active"]),
                        "revoked_keys": sum(1 for k in key_manager.keys.values() if not k["is_active"]),
                        "deleted_keys": len(key_manager.deleted_keys),
                        "keys_by_type": {
                            "daily": sum(1 for k in key_manager.keys.values() if k.get("key_type") == "daily" and k["is_active"]),
                            "weekly": sum(1 for k in key_manager.keys.values() if k.get("key_type") == "weekly" and k["is_active"]),
                            "monthly": sum(1 for k in key_manager.keys.values() if k.get("key_type") == "monthly" and k["is_active"]),
                            "lifetime": sum(1 for k in key_manager.keys.values() if k.get("key_type") == "lifetime" and k["is_active"]),
                            "general": sum(1 for k in key_manager.keys.values() if k.get("key_type") == "general" and k["is_active"])
                        },
                        "available_keys": {
                            "daily": sum(1 for k in key_manager.keys.values() if k.get("key_type") == "daily" and k["is_active"] and k["user_id"] == 0),
                            "weekly": sum(1 for k in key_manager.keys.values() if k.get("key_type") == "weekly" and k["is_active"] and k["user_id"] == 0),
                            "monthly": sum(1 for k in key_manager.keys.values() if k.get("key_type") == "monthly" and k["is_active"] and k["user_id"] == 0),
                            "lifetime": sum(1 for k in key_manager.keys.values() if k.get("key_type") == "lifetime" and k["is_active"] and k["user_id"] == 0),
                            "general": sum(1 for k in key_manager.keys.values() if k.get("key_type") == "general" and k["is_active"] and k["user_id"] == 0)
                        },
                        "last_updated": int(time.time())
                    }
                    try:
                        self.wfile.write(json.dumps(keys_data, indent=2).encode())
                    except Exception:
                        import json as _json
                        self.wfile.write(_json.dumps(keys_data, indent=2).encode())
                    return

                # Direct download endpoints
                if self.path.lower() in ('/download/selfbot.py', '/download/selfbot'):
                    try:
                        file_path = os.path.join('.', 'Selfbot.py')
                        if not os.path.exists(file_path):
                            self.send_response(404)
                            self.end_headers()
                            self.wfile.write(b'Not found')
                            return
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/octet-stream')
                        self.send_header('Content-Disposition', 'attachment; filename="Selfbot.py"')
                        self.end_headers()
                        with open(file_path, 'rb') as f:
                            self.wfile.write(f.read())
                        return
                    except Exception as e:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(str(e).encode())
                        return
                if self.path.lower() in ('/download/bot.py', '/download/bot'):
                    try:
                        file_path = os.path.join('.', 'bot.py')
                        if not os.path.exists(file_path):
                            self.send_response(404)
                            self.end_headers()
                            self.wfile.write(b'Not found')
                            return
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/octet-stream')
                        self.send_header('Content-Disposition', 'attachment; filename="bot.py"')
                        self.end_headers()
                        with open(file_path, 'rb') as f:
                            self.wfile.write(f.read())
                        return
                    except Exception as e:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(str(e).encode())
                        return

                # Redirect unknown routes to dashboard instead of 404
                self.send_response(303)
                self.send_header('Location', '/')
                self.end_headers()
            except Exception as e:
                try:
                    self.send_response(500)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(f"Internal Server Error: {e}".encode())
                except Exception:
                    pass

        def do_POST(self):
            try:
                if self.path == '/generate':
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length).decode()
                    data = urllib.parse.parse_qs(body)
                    def to_int(name):
                        try:
                            return max(0, int(data.get(name, ['0'])[0]))
                        except Exception:
                            return 0
                    daily = to_int('daily')
                    weekly = to_int('weekly')
                    monthly = to_int('monthly')
                    lifetime = to_int('lifetime')

                    result = key_manager.generate_bulk_keys(daily, weekly, monthly, lifetime)
                    key_manager.last_generated = result

                    self.send_response(303)
                    self.send_header('Location','/generate-form')
                    self.end_headers()
                    return

                if self.path in ('/revoke','/delete'):
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length).decode()
                    data = urllib.parse.parse_qs(body)
                    key = (data.get('key',[None])[0])
                    if not key:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b'Missing key')
                        return
                    ok = False
                    if self.path == '/revoke':
                        ok = key_manager.revoke_key(key)
                    else:
                        ok = key_manager.delete_key(key)
                    self.send_response(303)
                    self.send_header('Location','/keys')
                    self.end_headers()
                    return

                if self.path == '/api/activate':
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length).decode()
                    data = urllib.parse.parse_qs(body)
                    key = (data.get('key', [None])[0])
                    user_id_str = (data.get('user_id', [None])[0])
                    machine = (data.get('machine_id', [''])[0])
                    try:
                        user_id_val = int(user_id_str) if user_id_str is not None else None
                    except Exception:
                        user_id_val = None
                    resp = {}
                    status_code = 200
                    if not key or not user_id_val or not machine:
                        resp = {'success': False, 'error': 'missing key, user_id, or machine_id'}
                        status_code = 400
                    else:
                        try:
                            result = key_manager.activate_key(key, str(machine), int(user_id_val))
                            resp = result
                            if not result.get('success'):
                                status_code = 400
                                print(f"/api/activate failure for key={key}: {result}")
                            else:
                                # Grant role immediately upon successful activation
                                try:
                                    guild = bot.get_guild(GUILD_ID)
                                    role = guild.get_role(ROLE_ID) if guild else None
                                    if not role and guild:
                                        import discord as _discord
                                        role = _discord.utils.find(lambda r: r.name.lower() == ROLE_NAME.lower(), guild.roles)
                                    if guild and role and user_id_val:
                                        async def _add_role():
                                            member = guild.get_member(int(user_id_val))
                                            if member:
                                                await member.add_roles(role, reason="Key activated via API")
                                        asyncio.run_coroutine_threadsafe(_add_role(), bot.loop)
                                except Exception:
                                    pass
                        except Exception as e:
                            resp = {'success': False, 'error': str(e)}
                            status_code = 500
                            print(f"/api/activate exception: {e}")
                    self.send_response(status_code)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    try:
                        self.wfile.write(json.dumps(resp, indent=2).encode())
                    except Exception:
                        import json as _json
                        self.wfile.write(_json.dumps(resp, indent=2).encode())
                    return

                if self.path == '/api/rebind':
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length).decode()
                    data = urllib.parse.parse_qs(body)
                    key = (data.get('key', [None])[0])
                    user_id_str = (data.get('user_id', [None])[0])
                    new_machine = (data.get('machine_id', [''])[0])
                    try:
                        user_id_val = int(user_id_str) if user_id_str is not None else None
                    except Exception:
                        user_id_val = None
                    resp = {}
                    status_code = 200
                    if not key or not user_id_val or not new_machine:
                        resp = {'success': False, 'error': 'missing key, user_id, or machine_id'}
                        status_code = 400
                    else:
                        try:
                            result = key_manager.rebind_key(key, int(user_id_val), str(new_machine))
                            resp = result
                            if not result.get('success'):
                                status_code = 400
                        except Exception as e:
                            resp = {'success': False, 'error': str(e)}
                            status_code = 500
                    self.send_response(status_code)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    try:
                        self.wfile.write(json.dumps(resp, indent=2).encode())
                    except Exception:
                        import json as _json
                        self.wfile.write(_json.dumps(resp, indent=2).encode())
                    return

                if self.path == '/sender':
                    # Auth check via cookie
                    cookies = _parse_cookies(self.headers.get('Cookie'))
                    session = _decode_session(cookies.get('panel_session')) if cookies.get('panel_session') else None
                    authed_uid = int(session.get('user_id')) if session else None
                    authed_mid = str(session.get('machine_id')) if session else None
                    if not authed_uid or not _has_active_access(authed_uid, authed_mid):
                        self.send_response(303)
                        self.send_header('Location', '/login')
                        self.end_headers()
                        return
                    # Parse form
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length).decode()
                    data = urllib.parse.parse_qs(body)
                    chan_str = (data.get('channel_id', [''])[0]).strip()
                    content = (data.get('content', [''])[0]).strip()
                    ok = False
                    err = None
                    try:
                        cid = int(chan_str)
                        ch = bot.get_channel(cid)
                        if ch is None:
                            err = 'Bot cannot see this channel'
                        elif not content:
                            err = 'Empty message'
                        else:
                            fut = asyncio.run_coroutine_threadsafe(ch.send(content), bot.loop)
                            fut.result(timeout=5)
                            ok = True
                    except Exception as e:
                        err = str(e)
                    # Redirect back with a flash-like message in query
                    self.send_response(303)
                    if ok:
                        self.send_header('Location', '/sender')
                    else:
                        msg = urllib.parse.quote(err or 'Failed')
                        self.send_header('Location', f'/sender?err={msg}')
                    self.end_headers()
                    return

                if self.path == '/api/ann-post':
                    # Only members with OWNER_ROLE_ID can post announcements
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length).decode()
                    data = urllib.parse.parse_qs(body)
                    content = (data.get('content', [''])[0] or '').strip()
                    user_q = (data.get('user_id', [''])[0] or '').strip()
                    if not content:
                        self.send_response(400)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"success":false,"error":"empty content"}')
                        return
                    try:
                        uid = int(user_q)
                    except Exception:
                        uid = 0
                    allowed = False
                    try:
                        guild = bot.get_guild(GUILD_ID)
                        if guild and uid:
                            member = guild.get_member(uid)
                            if member is None:
                                async def _fetch_member():
                                    try:
                                        return await guild.fetch_member(uid)
                                    except Exception:
                                        return None
                                fut = asyncio.run_coroutine_threadsafe(_fetch_member(), bot.loop)
                                try:
                                    member = fut.result(timeout=5)
                                except Exception:
                                    member = None
                            if member:
                                allowed = any((r.id == OWNER_ROLE_ID) or (r.id == ADMIN_ROLE_ID) for r in member.roles)
                    except Exception:
                        allowed = False
                    if not allowed:
                        self.send_response(403)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        reason = {'success': False, 'error': 'forbidden', 'reason': 'not_owner'}
                        try:
                            self.wfile.write(json.dumps(reason).encode())
                        except Exception:
                            import json as _json
                            self.wfile.write(_json.dumps(reason).encode())
                        return
                    # Append announcement
                    try:
                        msgs = []
                        if os.path.exists(ANN_FILE):
                            with open(ANN_FILE, 'r') as f:
                                msgs = json.load(f)
                        if not isinstance(msgs, list):
                            msgs = []
                        ts = int(time.time())
                        # Resolve username and avatar for announcer
                        username = str(uid)
                        avatar_url = ""
                        try:
                            async def _fetch_user():
                                try:
                                    return await bot.fetch_user(uid)
                                except Exception:
                                    return None
                            fut = asyncio.run_coroutine_threadsafe(_fetch_user(), bot.loop)
                            user = fut.result(timeout=5)
                            if user:
                                username = f"{user.name}#{user.discriminator}"
                                try:
                                    avatar_url = str(user.display_avatar.url)
                                except Exception:
                                    avatar_url = ""
                        except Exception:
                            pass
                        msgs.append({'ts': ts, 'content': content, 'user_id': uid, 'username': username, 'avatar_url': avatar_url})
                        msgs = msgs[-200:]
                        tmp = ANN_FILE + '.tmp'
                        with open(tmp, 'w') as f:
                            json.dump(msgs, f, indent=2)
                        os.replace(tmp, ANN_FILE)
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'success': True, 'ts': ts}).encode())
                        return
                    except Exception as e:
                        self.send_response(500)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
                        return

                if self.path == '/api/chat-post':
                    # Only members with ADMIN_CHAT_ROLE_ID (or ADMIN_ROLE_ID) can post broadcast messages
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length).decode()
                    data = urllib.parse.parse_qs(body)
                    content = (data.get('content', [''])[0] or '').strip()
                    user_q = (data.get('user_id', [''])[0] or '').strip()
                    if not content:
                        self.send_response(400)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"success":false,"error":"empty content"}')
                        return
                    try:
                        uid = int(user_q)
                    except Exception:
                        uid = 0
                    allowed = False
                    try:
                        guild = bot.get_guild(GUILD_ID)
                        cnt = int(MESSAGE_STATS.get(str(uid), 0))
                        if cnt >= MESSAGES_THRESHOLD:
                            allowed = True
                        if not allowed and guild and uid:
                            member = guild.get_member(uid)
                            if member is None:
                                async def _fetch_member():
                                    try:
                                        return await guild.fetch_member(uid)
                                    except Exception:
                                        return None
                                fut = asyncio.run_coroutine_threadsafe(_fetch_member(), bot.loop)
                                try:
                                    member = fut.result(timeout=5)
                                except Exception:
                                    member = None
                            if member:
                                allowed = any((r.id == CHATSEND_ROLE_ID) or (r.id == ADMIN_ROLE_ID) for r in member.roles)
                        # Auto-grant role if threshold met and missing role
                        if guild and uid and allowed and cnt >= MESSAGES_THRESHOLD and CHATSEND_ROLE_ID:
                            try:
                                member = guild.get_member(uid)
                                role = guild.get_role(CHATSEND_ROLE_ID)
                                if member and role and role not in member.roles:
                                    async def _add_role():
                                        try:
                                            await member.add_roles(role, reason="Reached message threshold")
                                        except Exception:
                                            pass
                                    asyncio.run_coroutine_threadsafe(_add_role(), bot.loop)
                            except Exception:
                                pass
                    except Exception:
                        allowed = False
                    if not allowed:
                        self.send_response(403)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        reason = {'success': False, 'error': 'forbidden', 'reason': 'role_or_threshold'}
                        try:
                            self.wfile.write(json.dumps(reason).encode())
                        except Exception:
                            import json as _json
                            self.wfile.write(_json.dumps(reason).encode())
                        return
                    # Append message
                    try:
                        msgs = []
                        if os.path.exists(CHAT_FILE):
                            with open(CHAT_FILE, 'r') as f:
                                msgs = json.load(f)
                        if not isinstance(msgs, list):
                            msgs = []
                        ts = int(time.time())
                        # Resolve username and avatar URL for the posting user
                        username = str(uid)
                        avatar_url = ""
                        try:
                            async def _fetch_user():
                                try:
                                    return await bot.fetch_user(uid)
                                except Exception:
                                    return None
                            fut = asyncio.run_coroutine_threadsafe(_fetch_user(), bot.loop)
                            user = fut.result(timeout=5)
                            if user:
                                username = f"{user.name}#{user.discriminator}"
                                try:
                                    avatar_url = str(user.display_avatar.url)
                                except Exception:
                                    avatar_url = ""
                        except Exception:
                            pass
                        msgs.append({'ts': ts, 'from': 'admin', 'user_id': uid, 'username': username, 'avatar_url': avatar_url, 'content': content})
                        msgs = msgs[-200:]
                        tmp = CHAT_FILE + '.tmp'
                        with open(tmp, 'w') as f:
                            json.dump(msgs, f, indent=2)
                        os.replace(tmp, CHAT_FILE)
                        # Mirror to webhook (best-effort)
                        try:
                            if CHAT_MIRROR_WEBHOOK:
                                payload = {
                                    'content': f"[{username}] {content}"
                                }
                                requests.post(CHAT_MIRROR_WEBHOOK, json=payload, timeout=5)
                        except Exception:
                            pass
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'success': True, 'ts': ts}).encode())
                        return
                    except Exception as e:
                        self.send_response(500)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
                        return

                if self.path == '/api/stat-incr':
                    try:
                        content_length = int(self.headers.get('Content-Length', 0))
                        body = self.rfile.read(content_length).decode()
                        data = urllib.parse.parse_qs(body)
                        uid = (data.get('user_id', [''])[0] or '').strip()
                        if not uid:
                            self.send_response(400)
                            self.send_header('Content-Type', 'application/json')
                            self.end_headers()
                            self.wfile.write(b'{"success":false,"error":"missing user_id"}')
                            return
                        # Increment and persist
                        try:
                            MESSAGE_STATS[uid] = int(MESSAGE_STATS.get(uid, 0)) + 1
                            tmp = STATS_FILE + '.tmp'
                            with open(tmp, 'w') as f:
                                json.dump(MESSAGE_STATS, f, indent=2)
                            os.replace(tmp, STATS_FILE)
                        except Exception as e:
                            self.send_response(500)
                            self.send_header('Content-Type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
                            return
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"success":true}')
                        return
                    except Exception as e:
                        self.send_response(500)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
                        return
                
                # Selfbot heartbeat: mark user active with timestamp
                if self.path == '/api/selfbot-heartbeat':
                    try:
                        content_length = int(self.headers.get('Content-Length', 0))
                        body = self.rfile.read(content_length).decode()
                        data = urllib.parse.parse_qs(body)
                        uid = (data.get('user_id', [''])[0] or '').strip()
                        if not uid:
                            self.send_response(400)
                            self.send_header('Content-Type', 'application/json')
                            self.end_headers()
                            self.wfile.write(b'{"success":false,"error":"missing user_id"}')
                            return
                        ACTIVE_SELF_USERS[uid] = int(time.time())
                        # Trim old entries
                        now_ts = int(time.time())
                        to_del = [k for k, ts in ACTIVE_SELF_USERS.items() if (now_ts - int(ts)) > ACTIVE_WINDOW_SEC]
                        for k in to_del:
                            del ACTIVE_SELF_USERS[k]
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'success': True}).encode())
                        return
                    except Exception as e:
                        self.send_response(500)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
                        return
                
                # Active users count
                if self.path == '/api/active-users':
                    try:
                        now_ts = int(time.time())
                        count = 0
                        for ts in list(ACTIVE_SELF_USERS.values()):
                            if (now_ts - int(ts)) <= ACTIVE_WINDOW_SEC:
                                count += 1
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'active_users': count}).encode())
                        return
                    except Exception as e:
                        self.send_response(500)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
                        return

                # Redirect unknown routes to dashboard instead of 404
                self.send_response(303)
                self.send_header('Location', '/')
                self.end_headers()
            except Exception as e:
                try:
                    self.send_response(500)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(f"Internal Server Error: {e}".encode())
                except Exception:
                    pass
    
    try:
        # Use Render's PORT environment variable or default to 8080
        port = int(os.getenv('PORT', 8080))
        from http.server import ThreadingHTTPServer
        server = ThreadingHTTPServer(("", port), HealthCheckHandler)
        print(f"🌐 Health check server started on port {port}")
        # Start aiohttp app for webhooks
        async def _run_aiohttp():
            app = web.Application()
            app.router.add_post('/webhook/coinbase-commerce', coinbase_webhook)
            app.router.add_post('/webhook/nowpayments', nowpayments_webhook)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', port+1)
            await site.start()
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.create_task(_run_aiohttp())
        server.serve_forever()
    except Exception as e:
        print(f"❌ Health check server failed: {e}")

# Error handling
@bot.event
async def on_error(event, *args, **kwargs):
    print(f"❌ Error in {event}: {args}")


# Run the bot
if __name__ == "__main__":
    print("🚀 Starting Discord Bot...")
    print("=" * 40)
    
    # Start health check server in a separate thread
    health_thread = threading.Thread(target=start_health_check, daemon=True)
    health_thread.start()
    print("✅ Health check server started")

    async def start_with_backoff():
        delay_seconds = 60
        max_delay = 900
        while True:
            try:
                print("🔗 Connecting to Discord...")
                await bot.start(BOT_TOKEN)
            except Exception as e:
                # If Discord is rate-limiting or network issue, back off and retry
                msg = str(e)
                if "429" in msg or "Too Many Requests" in msg:
                    print(f"⚠️ 429/Rate limited. Retrying in {delay_seconds}s...")
                else:
                    print(f"⚠️ Startup error: {e}. Retrying in {delay_seconds}s...")
                await asyncio.sleep(delay_seconds)
                delay_seconds = min(delay_seconds * 2, max_delay)
            else:
                break

    try:
        asyncio.run(start_with_backoff())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        exit(1)

async def purge_global_commands():
    try:
        app_id = (bot.user.id if bot.user else None)
        if app_id:
            await bot.http.bulk_upsert_global_commands(app_id, [])
            print("🧹 Purged all global application commands")
    except Exception as e:
        print(f"⚠️ Failed to purge global commands: {e}")

@bot.tree.command(name="keylogs", description="Show recent key logs (last 15)")
async def keylogs(interaction: discord.Interaction):
    if not await check_permissions(interaction):
        return
    logs = list(reversed(key_manager.key_logs[-15:]))
    if not logs:
        await interaction.response.send_message("📭 No logs yet.", ephemeral=True)
        return
    lines = []
    for e in logs:
        when = f"<t:{e.get('ts',0)}:R>"
        event = e.get('event','?')
        key = e.get('key','')
        uid = e.get('user_id')
        lines.append(f"{when} — {event.upper()} — `{key}` — {('<@'+str(uid)+'>') if uid else ''}")
    embed = discord.Embed(title="📝 Recent Key Logs", description="\n".join(lines), color=0x8b5cf6)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tasks.loop(seconds=60)
async def reconcile_roles_task():
    """Grant or remove the access role based on key validity."""
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            return
        role = guild.get_role(ROLE_ID)
        if not role:
            try:
                import discord as _discord
                role = _discord.utils.find(lambda r: r.name.lower() == ROLE_NAME.lower(), guild.roles)
            except Exception:
                role = None
        if not role:
            return
        now = int(time.time())
        # Build set of user_ids present in keys
        user_ids: set[int] = set()
        for _, data in key_manager.keys.items():
            uid = data.get('user_id')
            if uid:
                try:
                    user_ids.add(int(uid))
                except Exception:
                    pass
        for uid in user_ids:
            # Determine if user has at least one active (not expired and not revoked) key
            has_active = False
            for _, data in key_manager.keys.items():
                if int(data.get('user_id', 0)) != uid:
                    continue
                if not data.get('is_active', False):
                    continue
                exp = int(data.get('expiration_time') or 0)
                if exp == 0 or exp > now:
                    has_active = True
                    break
            member = guild.get_member(uid)
            if not member:
                continue
            try:
                if has_active and role not in member.roles:
                    await member.add_roles(role, reason="Key active")
                elif (not has_active) and role in member.roles:
                    await member.remove_roles(role, reason="Key expired or revoked")
            except Exception:
                pass
    except Exception:
        pass

@tasks.loop(minutes=BACKUP_INTERVAL_MIN)
async def periodic_backup_task():
    """Periodically upload a JSON backup to the configured Discord channel."""
    if BACKUP_CHANNEL_ID <= 0 and not BACKUP_WEBHOOK_URL:
        return
    try:
        payload = key_manager.build_backup_payload()
        await upload_backup_snapshot(payload)
    except Exception:
        pass




@bot.tree.command(name="autobuy", description="Create a crypto invoice to buy a key")
async def autobuy(interaction: discord.Interaction, coin: str, key_type: str):
    """Create a NOWPayments invoice for the chosen coin and key type inside a ticket channel."""
    try:
        await interaction.response.defer(ephemeral=True)
        if not NWP_API_KEY or not NWP_IPN_SECRET:
            await interaction.followup.send("Payment processor not configured.")
            return
        coin = coin.upper()
        if coin not in ("BTC","LTC","ETH","USDC","USDT"):
            await interaction.followup.send("Unsupported coin. Choose BTC, LTC, ETH, USDC or USDT.")
            return
        key_type = key_type.lower()
        price_map = {"daily":3, "weekly":10, "monthly":20, "lifetime":50}
        if key_type not in price_map:
            await interaction.followup.send("Invalid key type. Choose daily, weekly, monthly or lifetime.")
            return
        amount = price_map[key_type]
        order_id = f"{interaction.user.id}:{interaction.channel.id}:{key_type}:${amount}"
        # Build invoice payload
        payload = {
            "price_amount": amount,
            "price_currency": "USD",
            "order_id": order_id,
            "order_description": f"{key_type} key for {interaction.user.id}",
            "pay_currency": coin,
            "is_fixed_rate": True,
        }
        if PUBLIC_URL:
            payload["ipn_callback_url"] = f"{PUBLIC_URL.rstrip('/')}/webhook/nowpayments"
        headers = {
            "x-api-key": NWP_API_KEY,
            "Content-Type": "application/json"
        }
        import requests as _req, json as _json
        try:
            r = _req.post("https://api.nowpayments.io/v1/invoice", headers=headers, data=_json.dumps(payload), timeout=15)
            if r.status_code not in (200,201):
                await interaction.followup.send(f"Failed to create invoice (HTTP {r.status_code}).")
                return
            inv = r.json()
        except Exception as e:
            await interaction.followup.send(f"Error creating invoice: {e}")
            return
        url = inv.get("invoice_url") or inv.get("pay_url") or inv.get("invoice_url")
        if not url:
            await interaction.followup.send("Invoice created but no URL returned.")
            return
        note = "autobuy confirmation times vary, defaulting from 3-6 minutes up to 20 minutes"
        em = discord.Embed(title="Autobuy", description=f"Pay with {coin} for a {key_type} key ($ {amount}).\n\n{note}", color=0x7d5fff)
        em.add_field(name="Checkout", value=f"[Open Invoice]({url})", inline=False)
        await interaction.followup.send(embed=em)
    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"Error: {e}")
        else:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)

@app_commands.guilds(discord.Object(id=GUILD_ID))
@bot.tree.command(name="sbautobuy", description="Create a crypto invoice (backup command)")
async def sbautobuy(interaction: discord.Interaction, coin: str, key_type: str):
    await autobuy.callback(interaction, coin, key_type)

@app_commands.guilds(discord.Object(id=GUILD_ID))
@bot.tree.command(name="listcommands", description="List registered application commands (debug)")
async def listcommands(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
        cmds = bot.tree.get_commands(guild=discord.Object(id=GUILD_ID))
        names = [c.name for c in cmds]
        await interaction.followup.send("\n".join(names) or "(no commands)")
    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"Error: {e}")
        else:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)

async def nowpayments_webhook(request: web.Request):
    try:
        secret = NWP_IPN_SECRET or ''
        body_txt = await request.text()
        sig = request.headers.get('x-nowpayments-sig','')
        import hmac, hashlib
        expected = hmac.new(secret.encode(), body_txt.encode() if isinstance(body_txt, str) else body_txt, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return web.Response(status=400, text='bad sig')
        data = json.loads(body_txt)
        status = str(data.get('payment_status','')).lower()
        order_id = str(data.get('order_id',''))
        # order_id format: user:channel:key:amount
        parts = order_id.split(':') if order_id else []
        user_id = parts[0] if len(parts) > 0 else None
        ticket_channel_id = parts[1] if len(parts) > 1 else None
        key_type = parts[2] if len(parts) > 2 else ''
        amount = parts[3] if len(parts) > 3 else ''
        # Log pending/confirmed
        try:
            if PURCHASE_LOG_WEBHOOK:
                color = 0xF59E0B if ('pending' in status or 'waiting' in status or 'confirming' in status) else 0x22C55E if ('finished' in status or 'confirmed' in status) else 0x64748B
                embed = {
                    'title': 'Autobuy (NOWPayments)',
                    'description': status,
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
        # On finished/confirmed
        if user_id and key_type and (('finished' in status) or ('confirmed' in status)):
            try:
                durations = {'daily':1, 'weekly':7, 'monthly':30, 'lifetime':365}
                duration_days = durations.get(key_type, 30)
                key = key_manager.generate_key(int(user_id), None, duration_days)
                guild = bot.get_guild(GUILD_ID)
                if guild and ticket_channel_id:
                    try:
                        chan = guild.get_channel(int(ticket_channel_id))
                        if chan:
                            member = guild.get_member(int(user_id))
                            if member:
                                try:
                                    await chan.set_permissions(member, read_messages=True, send_messages=True)
                                except Exception:
                                    pass
                            await chan.send(f"<@{user_id}> Your {key_type} key: `{key}`")
                    except Exception:
                        pass
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

@bot.tree.command(name="setstatuswebhook", description="Set the webhook URL to receive bot online/offline status")
async def set_status_webhook_cmd(interaction: discord.Interaction, webhook_url: str):
    try:
        CONFIG['STATUS_WEBHOOK_URL'] = webhook_url.strip()
        save_config()
        await interaction.response.send_message("✅ Status webhook set.", ephemeral=True)
        # Send a test online ping
        try:
            await send_status_webhook('online')
        except Exception:
            pass
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to set webhook: {e}", ephemeral=True)

@bot.tree.command(name="backupchannel", description="Set the channel to auto-backup keys and auto-restore on deploy")
async def set_backup_channel_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        global BACKUP_CHANNEL_ID
        BACKUP_CHANNEL_ID = int(channel.id)
        CONFIG['BACKUP_CHANNEL_ID'] = BACKUP_CHANNEL_ID
        save_config()
        await interaction.response.send_message(f"✅ Backup channel set to {channel.mention}.", ephemeral=True)
        # Ensure backup loop is running
        try:
            if not periodic_backup_task.is_running():
                periodic_backup_task.start()
        except Exception:
            pass
        # Optional immediate backup
        try:
            payload = key_manager.build_backup_payload()
            data = json.dumps(payload, indent=2).encode()
            file = discord.File(io.BytesIO(data), filename=f"backup_{int(time.time())}.json")
            await channel.send(content="Manual backup after setting channel", file=file)
        except Exception:
            pass
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to set backup channel: {e}", ephemeral=True)

# ---------------------- TEXT COMMAND FALLBACKS ----------------------
    try:
        # Only allow in the configured guild
        if not ctx.guild or ctx.guild.id != GUILD_ID:
            return
        # Load stats
        stats: dict[str, int] = {}
        try:
            if os.path.exists(STATS_FILE):
                async with aiofiles.open(STATS_FILE, 'r') as f:
                    raw = await f.read()
                import json as _json
                stats = _json.loads(raw) or {}
            else:
                stats = MESSAGE_STATS
        except Exception:
            stats = MESSAGE_STATS
        top = sorted(stats.items(), key=lambda kv: kv[1], reverse=True)[:10]
        if not top:
            await ctx.reply("No stats yet.")
            return
        em = discord.Embed(title="Selfbot Leaderboard", color=0x5a3e99)
        desc_lines = []
        rank = 1
        for uid, cnt in top:
            try:
                user = await bot.fetch_user(int(uid))
                name = f"{user.name}#{user.discriminator}" if user else uid
            except Exception:
                name = uid
            desc_lines.append(f"**{rank}.** {name} — {cnt}")
            rank += 1
        em.description = "\n".join(desc_lines)
        await ctx.reply(embed=em)
    except Exception as e:
        await ctx.reply(f"Error: {e}")

@bot.command(name="autobuy")
async def autobuy_text(ctx: commands.Context, coin: str = None, key_type: str = None):
    try:
        if not ctx.guild or ctx.guild.id != GUILD_ID:
            return
        if not coin or not key_type:
            await ctx.reply("Usage: !autobuy <BTC|LTC|ETH|USDC|USDT> <daily|weekly|monthly|lifetime>")
            return
        if not NWP_API_KEY or not NWP_IPN_SECRET:
            await ctx.reply("Payment processor not configured.")
            return
        coin = coin.upper()
        if coin not in ("BTC","LTC","ETH","USDC","USDT"):
            await ctx.reply("Unsupported coin. Choose BTC, LTC, ETH, USDC or USDT.")
            return
        key_type = key_type.lower()
        price_map = {"daily":3, "weekly":10, "monthly":20, "lifetime":50}
        if key_type not in price_map:
            await ctx.reply("Invalid key type. Choose daily, weekly, monthly or lifetime.")
            return
        amount = price_map[key_type]
        order_id = f"{ctx.author.id}:{ctx.channel.id}:{key_type}:${amount}"
        payload = {
            "price_amount": amount,
            "price_currency": "USD",
            "order_id": order_id,
            "order_description": f"{key_type} key for {ctx.author.id}",
            "pay_currency": coin,
            "is_fixed_rate": True,
        }
        if PUBLIC_URL:
            payload["ipn_callback_url"] = f"{PUBLIC_URL.rstrip('/')}/webhook/nowpayments"
        headers = {"x-api-key": NWP_API_KEY, "Content-Type": "application/json"}
        import requests as _req, json as _json
        try:
            r = _req.post("https://api.nowpayments.io/v1/invoice", headers=headers, data=_json.dumps(payload), timeout=15)
            if r.status_code not in (200,201):
                await ctx.reply(f"Failed to create invoice (HTTP {r.status_code}).")
                return
            inv = r.json()
        except Exception as e:
            await ctx.reply(f"Error creating invoice: {e}")
            return
        url = inv.get("invoice_url") or inv.get("pay_url") or inv.get("invoice_url")
        if not url:
            await ctx.reply("Invoice created but no URL returned.")
            return
        note = "autobuy confirmation times vary, defaulting from 3-6 minutes up to 20 minutes"
        em = discord.Embed(title="Autobuy", description=f"Pay with {coin} for a {key_type} key ($ {amount}).\n\n{note}", color=0x7d5fff)
        em.add_field(name="Checkout", value=f"[Open Invoice]({url})", inline=False)
        await ctx.reply(embed=em)
    except Exception as e:
        await ctx.reply(f"Error: {e}")

        return

async def upload_backup_snapshot(payload: dict) -> None:
    """Upload a JSON snapshot to the configured Discord backup channel and webhook."""
    # Send to channel as file attachment, if configured
    try:
        if BACKUP_CHANNEL_ID > 0:
            channel = bot.get_channel(BACKUP_CHANNEL_ID)
            if channel:
                data = json.dumps(payload, indent=2).encode()
                file = discord.File(io.BytesIO(data), filename=f"backup_{int(time.time())}.json")
                await channel.send(content="Backup snapshot", file=file)
    except Exception:
        pass
    # Send to webhook as JSON payload, if provided
    try:
        url = (BACKUP_WEBHOOK_URL or '').strip()
        if url:
            data = json.dumps(payload, indent=2).encode()
            files = {"file": (f"backup_{int(time.time())}.json", io.BytesIO(data), "application/json")}
            requests.post(url, files=files, timeout=15)
    except Exception:
        pass

@app_commands.guilds(discord.Object(id=GUILD_ID))
@bot.tree.command(name="swapkey", description="Swap a key from one user to another (Special Admin Only)")
async def swap_key(interaction: discord.Interaction, from_user: discord.Member, to_user: discord.Member, key: str):
	# Special admin only
	if interaction.user.id not in SPECIAL_ADMIN_IDS:
		await interaction.response.send_message("❌ **Access Denied:** Only special admins can use this command.", ephemeral=True)
		return
	if not await check_permissions(interaction):
		return
	try:
		k = key.strip()
		info = key_manager.get_key_info(k)
		if not info:
			await interaction.response.send_message("❌ Key not found.", ephemeral=True)
			return
		if int(info.get('user_id', 0) or 0) != int(from_user.id):
			await interaction.response.send_message("❌ This key is not owned by the from_user.", ephemeral=True)
			return
		if not info.get('is_active', False):
			await interaction.response.send_message("❌ Key is not active.", ephemeral=True)
			return
		now = int(time.time())
		exp = int(info.get('expiration_time') or 0)
		if exp and exp <= now:
			await interaction.response.send_message("❌ Key is expired.", ephemeral=True)
			return
		# Transfer ownership and reset binding so new user can activate/bind
		key_manager.keys[k]['user_id'] = int(to_user.id)
		key_manager.keys[k]['activated_by'] = int(to_user.id)
		key_manager.keys[k]['machine_id'] = None
		key_manager.keys[k]['activation_time'] = None
		# Persist and log
		key_manager.save_data()
		try:
			key_manager.add_log('swapkey', k, user_id=int(to_user.id), details={'from_user': int(from_user.id)})
		except Exception:
			pass
		# Upload immediate backup
		try:
			payload = key_manager.build_backup_payload()
			await upload_backup_snapshot(payload)
		except Exception:
			pass
		# Adjust roles: remove from old user, add to new user
		try:
			guild = interaction.guild
			role = guild.get_role(ROLE_ID) if guild else None
			if guild and role:
				oldm = guild.get_member(int(from_user.id))
				newm = guild.get_member(int(to_user.id))
				if oldm and role in oldm.roles:
					await oldm.remove_roles(role, reason="Key swapped to another user")
				if newm and role not in newm.roles:
					await newm.add_roles(role, reason="Key received via swap")
		except Exception:
			pass
		# Report remaining time
		rem = 0
		try:
			exp = int(info.get('expiration_time') or 0)
			rem = max(0, exp - int(time.time()))
		except Exception:
			rem = 0
		d = rem // 86400; h = (rem % 86400)//3600; m = (rem % 3600)//60
		await interaction.response.send_message(f"✅ Swapped key `{k}` to {to_user.mention}. Remaining: {d}d {h}h {m}m. The new user must activate to bind a machine.")
	except Exception as e:
		await interaction.response.send_message(f"❌ Swap failed: {e}", ephemeral=True)



