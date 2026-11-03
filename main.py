"""Downmax - Professional Video & MP3 Downloader
Developer: TKsadhan  |  Contact: sadhanpatar@gmail.com
"""
import io
import os
import queue
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from app_info import APP_NAME, CONTACT, DEVELOPER, TAGLINE, VERSION
from downloader import (AUDIO_BITRATES, VIDEO_QUALITIES, DownloadEngine,
                        DownloadOptions, fetch_info, format_duration)

ACCENT = "#6366f1"
ACCENT_HOVER = "#4f46e5"


def resource(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / rel


def open_folder(path: str):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class DownmaxApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title(f"{APP_NAME} - {TAGLINE}")
        self.geometry("780x820")
        self.minsize(720, 760)
        self._set_icon()

        self.q = queue.Queue()
        self.engine = DownloadEngine(
            on_progress=lambda p, t: self.q.put(("progress", p, t)),
            on_log=lambda m: self.q.put(("log", m)),
        )
        self.busy = False
        self.cookies_path = None
        self.out_dir = str(Path.home() / "Downloads" / "Downmax")
        self._thumb_img = None

        self._build_ui()
        self.after(100, self._poll)

    # ---------------------------------------------------------------- UI
    def _set_icon(self):
        ico = resource("assets/icon.ico")
        png = resource("assets/logo.png")
        try:
            if sys.platform.startswith("win"):
                self.iconbitmap(str(ico))
            else:
                import tkinter as tk
                self._icon_ref = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._icon_ref)
        except Exception:
            pass

    def _card(self, parent):
        return ctk.CTkFrame(parent, corner_radius=14, fg_color=("#e2e8f0", "#1e293b"))

    def _build_ui(self):
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=20, pady=16)

        # header
        head = ctk.CTkFrame(root, fg_color="transparent")
        head.pack(fill="x")
        logo = ctk.CTkImage(Image.open(resource("assets/logo.png")), size=(56, 56))
        ctk.CTkLabel(head, image=logo, text="").pack(side="left")
        tbox = ctk.CTkFrame(head, fg_color="transparent")
        tbox.pack(side="left", padx=12)
        ctk.CTkLabel(tbox, text=APP_NAME, font=ctk.CTkFont(size=28, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(tbox, text=TAGLINE, text_color="gray60").pack(anchor="w")
        ctk.CTkButton(head, text="About", width=70, fg_color="transparent", border_width=1,
                      command=self._about).pack(side="right")

        # URL card
        c1 = self._card(root)
        c1.pack(fill="x", pady=(14, 8))
        ctk.CTkLabel(c1, text="Video link  (YouTube, Facebook, Instagram, or any website)",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(12, 4))
        row = ctk.CTkFrame(c1, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 12))
        self.url_var = ctk.StringVar()
        self.url_entry = ctk.CTkEntry(row, textvariable=self.url_var, height=40,
                                      placeholder_text="Paste link here…")
        self.url_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Paste", width=70, height=40, command=self._paste).pack(side="left", padx=(8, 0))
        self.fetch_btn = ctk.CTkButton(row, text="Check", width=80, height=40,
                                       fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._fetch)
        self.fetch_btn.pack(side="left", padx=(8, 0))

        # info card
        self.info_card = self._card(root)
        self.info_card.pack(fill="x", pady=8)
        self.thumb_lbl = ctk.CTkLabel(self.info_card, text="", width=160, height=90)
        self.thumb_lbl.pack(side="left", padx=12, pady=12)
        ib = ctk.CTkFrame(self.info_card, fg_color="transparent")
        ib.pack(side="left", fill="both", expand=True, pady=12)
        self.title_lbl = ctk.CTkLabel(ib, text="No video selected yet", anchor="w", justify="left",
                                      wraplength=480, font=ctk.CTkFont(size=15, weight="bold"))
        self.title_lbl.pack(anchor="w")
        self.meta_lbl = ctk.CTkLabel(ib, text="Paste a link and press Check (optional).",
                                     text_color="gray60", anchor="w", justify="left", wraplength=480)
        self.meta_lbl.pack(anchor="w", pady=(4, 0))

        # options card
        c2 = self._card(root)
        c2.pack(fill="x", pady=8)
        r1 = ctk.CTkFrame(c2, fg_color="transparent")
        r1.pack(fill="x", padx=14, pady=(12, 6))
        self.mode_var = ctk.StringVar(value="Video (MP4)")
        ctk.CTkSegmentedButton(r1, values=["Video (MP4)", "Audio (MP3)"], variable=self.mode_var,
                               command=self._mode_changed, selected_color=ACCENT,
                               selected_hover_color=ACCENT_HOVER).pack(side="left")
        self.quality_var = ctk.StringVar(value="Best available")
        self.quality_menu = ctk.CTkOptionMenu(r1, variable=self.quality_var, width=180,
                                              values=list(VIDEO_QUALITIES.keys()))
        self.quality_menu.pack(side="left", padx=12)
        self.playlist_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(r1, text="Download full playlist", variable=self.playlist_var).pack(side="left", padx=8)

        r2 = ctk.CTkFrame(c2, fg_color="transparent")
        r2.pack(fill="x", padx=14, pady=6)
        ctk.CTkLabel(r2, text="Save to:", width=70, anchor="w").pack(side="left")
        self.dir_lbl = ctk.CTkLabel(r2, text=self.out_dir, anchor="w", text_color="gray70")
        self.dir_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r2, text="Change", width=80, command=self._pick_dir).pack(side="right")

        r3 = ctk.CTkFrame(c2, fg_color="transparent")
        r3.pack(fill="x", padx=14, pady=(6, 12))
        ctk.CTkLabel(r3, text="Cookies:", width=70, anchor="w").pack(side="left")
        self.cookie_lbl = ctk.CTkLabel(r3, text="None (needed only for private / login-only videos)",
                                       anchor="w", text_color="gray60")
        self.cookie_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r3, text="Clear", width=60, fg_color="transparent", border_width=1,
                      command=self._clear_cookies).pack(side="right", padx=(6, 0))
        ctk.CTkButton(r3, text="Select", width=80, command=self._pick_cookies).pack(side="right")

        # actions
        act = ctk.CTkFrame(root, fg_color="transparent")
        act.pack(fill="x", pady=(8, 4))
        self.dl_btn = ctk.CTkButton(act, text="⬇  Download", height=46, fg_color=ACCENT,
                                    hover_color=ACCENT_HOVER, font=ctk.CTkFont(size=16, weight="bold"),
                                    command=self._start)
        self.dl_btn.pack(side="left", fill="x", expand=True)
        self.cancel_btn = ctk.CTkButton(act, text="Cancel", height=46, width=100, fg_color="#dc2626",
                                        hover_color="#b91c1c", state="disabled", command=self._cancel)
        self.cancel_btn.pack(side="left", padx=(8, 0))
        self.open_btn = ctk.CTkButton(act, text="Open folder", height=46, width=110, fg_color="transparent",
                                      border_width=1, command=lambda: open_folder(self.out_dir))
        self.open_btn.pack(side="left", padx=(8, 0))

        self.progress = ctk.CTkProgressBar(root, height=12, progress_color=ACCENT)
        self.progress.set(0)
        self.progress.pack(fill="x", pady=(8, 2))
        self.status_lbl = ctk.CTkLabel(root, text="Ready", anchor="w", text_color="gray70")
        self.status_lbl.pack(fill="x")

        self.log = ctk.CTkTextbox(root, height=110, font=ctk.CTkFont(family="Consolas", size=11))
        self.log.pack(fill="both", expand=True, pady=(6, 6))
        self.log.configure(state="disabled")

        ctk.CTkLabel(
            root, text="Download only content you own or have permission to save. "
                       "You are responsible for following each platform's terms and local copyright law.",
            text_color="gray50", font=ctk.CTkFont(size=10), wraplength=720).pack()
        foot = ctk.CTkFrame(root, fg_color="transparent")
        foot.pack(pady=(4, 0))
        ctk.CTkLabel(foot, text=f"v{VERSION}  •  Developed by {DEVELOPER}  •  ",
                     text_color="gray60", font=ctk.CTkFont(size=11)).pack(side="left")
        mail = ctk.CTkLabel(foot, text=CONTACT, text_color="#60a5fa", cursor="hand2",
                            font=ctk.CTkFont(size=11, underline=True))
        mail.pack(side="left")
        mail.bind("<Button-1>", lambda e: webbrowser.open(f"mailto:{CONTACT}"))

    # ------------------------------------------------------------ helpers
    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text.strip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _paste(self):
        try:
            self.url_var.set(self.clipboard_get().strip())
        except Exception:
            pass

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.out_dir)
        if d:
            self.out_dir = d
            self.dir_lbl.configure(text=d)

    def _pick_cookies(self):
        f = filedialog.askopenfilename(title="Select cookies.txt (Netscape format)",
                                       filetypes=[("Cookies", "*.txt"), ("All files", "*.*")])
        if f:
            self.cookies_path = f
            self.cookie_lbl.configure(text=f, text_color="gray70")

    def _clear_cookies(self):
        self.cookies_path = None
        self.cookie_lbl.configure(text="None (needed only for private / login-only videos)",
                                  text_color="gray60")

    def _mode_changed(self, value):
        if value.startswith("Audio"):
            vals = [f"{b} kbps" for b in AUDIO_BITRATES]
            self.quality_menu.configure(values=vals)
            self.quality_var.set("192 kbps")
        else:
            self.quality_menu.configure(values=list(VIDEO_QUALITIES.keys()))
            self.quality_var.set("Best available")

    def _set_busy(self, busy: bool):
        self.busy = busy
        self.dl_btn.configure(state="disabled" if busy else "normal")
        self.fetch_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")

    def _about(self):
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME} v{VERSION}\n{TAGLINE}\n\nDeveloper: {DEVELOPER}\nContact: {CONTACT}\n\n"
            "Powered by yt-dlp and FFmpeg.")

    # --------------------------------------------------------------- fetch
    def _fetch(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning(APP_NAME, "Please paste a link first.")
            return
        self.title_lbl.configure(text="Checking link…")
        self.meta_lbl.configure(text="")
        self.fetch_btn.configure(state="disabled")

        def work():
            try:
                info = fetch_info(url, self.cookies_path)
                thumb = None
                if info.get("thumbnail"):
                    try:
                        req = urllib.request.Request(info["thumbnail"], headers={"User-Agent": "Mozilla/5.0"})
                        data = urllib.request.urlopen(req, timeout=15).read()
                        thumb = Image.open(io.BytesIO(data)).convert("RGB")
                    except Exception:
                        thumb = None
                self.q.put(("info", info, thumb))
            except Exception as e:
                self.q.put(("info_err", str(e)))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ download
    def _start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning(APP_NAME, "Please paste a link first.")
            return
        mode = "mp3" if self.mode_var.get().startswith("Audio") else "video"
        q = self.quality_var.get()
        opts = DownloadOptions(
            url=url, out_dir=self.out_dir, mode=mode,
            quality=q if mode == "video" else "Best available",
            audio_bitrate=q.split()[0] if mode == "mp3" else "192",
            playlist=self.playlist_var.get(), cookies_file=self.cookies_path)
        self._set_busy(True)
        self.progress.set(0)
        self.status_lbl.configure(text="Starting…")
        self._log(f"Starting: {url}")

        def work():
            try:
                result = self.engine.run(opts)
                self.q.put(("finished", result, None))
            except Exception as e:
                self.q.put(("finished", "error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _cancel(self):
        self.engine.cancel()
        self.status_lbl.configure(text="Cancelling…")

    # --------------------------------------------------------- queue poll
    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    self.progress.set(min(max(msg[1], 0), 1))
                    self.status_lbl.configure(text=msg[2])
                elif kind == "log":
                    self._log(msg[1])
                elif kind == "info":
                    info, thumb = msg[1], msg[2]
                    self.fetch_btn.configure(state="normal")
                    self.title_lbl.configure(text=info["title"])
                    meta = [info["uploader"], format_duration(info["duration"])]
                    if info["is_playlist"]:
                        meta.append(f"Playlist • {info['count']} items")
                    self.meta_lbl.configure(text="  •  ".join(m for m in meta if m and m != "--"))
                    if thumb:
                        thumb.thumbnail((160, 90))
                        self._thumb_img = ctk.CTkImage(thumb, size=thumb.size)
                        self.thumb_lbl.configure(image=self._thumb_img, text="")
                    else:
                        self._thumb_img = None
                        self.thumb_lbl.configure(image=None, text="No preview")
                    if info["is_playlist"]:
                        self.playlist_var.set(True)
                elif kind == "info_err":
                    self.fetch_btn.configure(state="normal")
                    self.title_lbl.configure(text="Could not read this link")
                    self.meta_lbl.configure(text="You can still try pressing Download.")
                    self._log(msg[1])
                elif kind == "finished":
                    self._set_busy(False)
                    result, err = msg[1], msg[2]
                    if result == "done":
                        self.progress.set(1)
                        self.status_lbl.configure(text="✅ Download complete")
                        self._log(f"Saved in: {self.out_dir}")
                    elif result == "cancelled":
                        self.progress.set(0)
                        self.status_lbl.configure(text="Cancelled")
                    else:
                        self.progress.set(0)
                        self.status_lbl.configure(text="❌ Failed")
                        self._log(err)
                        messagebox.showerror(APP_NAME, err[:900])
        except queue.Empty:
            pass
        self.after(100, self._poll)


if __name__ == "__main__":
    DownmaxApp().mainloop()
