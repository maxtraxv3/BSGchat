"""tkinter GUI for the Asciline E2E encrypted chat client.

Layout:
  Top-left:  Server IP / .onion address + room
  Below:     Connected users list
  Right:     Chat messages (scrollable) + text input at bottom
  Toolbar:   Mic / Camera / Screen / Viewer / Send Image toggle buttons
  Viewer:    Separate popup window with video + audio
"""

from __future__ import annotations

import asyncio
import base64
import io
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from client.main import ChatClient

POLL_MS = 50  # queue poll interval (20 Hz)

BG = "#1e1e1e"
BG_PANEL = "#252526"
FG = "#d4d4d4"
FG_DIM = "#808080"
FG_SYS = "#569cd6"
FG_STATUS = "#6a9955"
FG_USER = "#dcdcaa"
FG_IMG = "#ce9178"


class ViewerWindow:
    """Separate popup window for video display + system audio capture/playback."""

    def __init__(self, gui: ChatGUI) -> None:
        self.gui = gui
        self.client = gui.client
        self._audio_running = False
        self._audio_thread: threading.Thread | None = None

        self.win = tk.Toplevel(gui.root)
        self.win.title("Asciline Viewer")
        self.win.geometry("720x480")
        self.win.configure(bg=BG)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        self.lbl_video = tk.Label(self.win, bg=BG)
        self.lbl_video.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        bottom = tk.Frame(self.win, bg=BG_PANEL)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        self.lbl_meta = tk.Label(bottom, text="waiting for frames...", bg=BG_PANEL, fg=FG_DIM,
                                 font=("monospace", 9), anchor="w", padx=6, pady=3)
        self.lbl_meta.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_audio = tk.Button(bottom, text="Audio Off", command=self._toggle_audio,
                                   bg=BG_PANEL, fg=FG, activebackground="#333",
                                   relief=tk.FLAT, padx=8, font=("monospace", 9))
        self.btn_audio.pack(side=tk.RIGHT, padx=6)

        self._start_audio_capture()

    def push_jpeg(self, jpeg_bytes: bytes, source: str) -> None:
        try:
            from PIL import Image, ImageTk
            img = Image.open(io.BytesIO(jpeg_bytes))
            max_w = max(self.win.winfo_width() - 20, 320)
            ratio = max_w / img.width
            img = img.resize((max_w, int(img.height * ratio)), Image.NEAREST)
            photo = ImageTk.PhotoImage(img)
            self.lbl_video.configure(image=photo)
            self.lbl_video._photo = photo  # prevent GC
            self.lbl_meta.configure(text=f"{source}  {img.width}x{img.height}")
        except Exception:
            pass

    # ---- audio capture + playback ----

    def _start_audio_capture(self) -> None:
        if self._audio_running:
            return
        self._audio_running = True
        self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self._audio_thread.start()

    def _audio_loop(self) -> None:
        if sys.platform == "win32":
            self._audio_loop_windows()
        else:
            self._audio_loop_linux()

    def _audio_loop_windows(self) -> None:
        import sounddevice as sd
        try:
            wasapi_settings = None
            try:
                if hasattr(sd, "WasapiSettings"):
                    wasapi_settings = sd.WasapiSettings(loopback=True)
            except Exception:
                pass

            RATE = 8000
            CHUNK_SAMPLES = 640
            default_out = sd.default.device[1]
            dev_info = sd.query_devices(default_out)
            dev_name = dev_info.get("name", "")
            print(f"[viewer-audio] WASAPI loopback: {dev_name}", file=sys.stderr, flush=True)

            play_queue: queue.Queue = queue.Queue(maxlen=20)

            def capture_cb(indata, frames, time_info, status):
                if self._audio_running:
                    play_queue.put(bytes(indata))

            def playback_cb(outdata, frames, time_info, status):
                try:
                    data = play_queue.get_nowait()
                    outdata[:len(data)] = data
                except queue.Empty:
                    outdata[:] = b"\x00" * len(outdata)

            kwargs = {}
            if wasapi_settings is not None:
                kwargs["extra_settings"] = wasapi_settings

            with sd.InputStream(device=default_out, channels=1, samplerate=RATE,
                                dtype="int16", blocksize=CHUNK_SAMPLES,
                                callback=capture_cb, **kwargs), \
                 sd.OutputStream(channels=1, samplerate=RATE, dtype="int16",
                                 blocksize=CHUNK_SAMPLES, callback=playback_cb):
                while self._audio_running:
                    sd.sleep(100)
        except Exception as exc:
            print(f"[viewer-audio] WASAPI error: {exc}", file=sys.stderr, flush=True)
            self._audio_running = False
            self.gui.root.after(0, lambda: self.btn_audio.configure(text="Audio N/A"))

    def _audio_loop_linux(self) -> None:
        import subprocess
        try:
            result = subprocess.run(["pactl", "info"], capture_output=True, text=True, timeout=5)
            sink_name = None
            for line in result.stdout.splitlines():
                if line.startswith("Default Sink:"):
                    sink_name = line.split(":", 1)[1].strip()
                    break
            if not sink_name:
                print("[viewer-audio] no default sink", file=sys.stderr, flush=True)
                self._audio_running = False
                return

            monitor_source = sink_name + ".monitor"
            result = subprocess.run(["pactl", "list", "sources", "short"],
                                    capture_output=True, text=True, timeout=5)
            if monitor_source not in result.stdout:
                print(f"[viewer-audio] monitor '{monitor_source}' not found", file=sys.stderr, flush=True)
                self._audio_running = False
                return

            RATE = 8000
            CHUNK_SAMPLES = 640
            chunk_bytes = CHUNK_SAMPLES * 2

            print(f"[viewer-audio] capturing {monitor_source}", file=sys.stderr, flush=True)

            proc = subprocess.Popen(
                ["pw-record", "--target", monitor_source, "--format", "s16",
                 "--rate", str(RATE), "--channels", "1", "-a", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )

            import sounddevice as sd
            play_queue: queue.Queue = queue.Queue(maxlen=20)

            def playback_cb(outdata, frames, time_info, status):
                try:
                    data = play_queue.get_nowait()
                    outdata[:len(data)//2] = data
                except queue.Empty:
                    pass

            with sd.OutputStream(channels=1, samplerate=RATE, dtype="int16",
                                blocksize=CHUNK_SAMPLES, callback=playback_cb):
                while self._audio_running:
                    raw = proc.stdout.read(chunk_bytes)
                    if not raw or len(raw) < chunk_bytes:
                        break
                    play_queue.put(raw)

            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception as exc:
            print(f"[viewer-audio] error: {exc}", file=sys.stderr, flush=True)
            self._audio_running = False

    def _toggle_audio(self) -> None:
        if self._audio_running:
            self._audio_running = False
            self.btn_audio.configure(text="Audio Off")
        else:
            self._audio_running = True
            self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
            self._audio_thread.start()
            self.btn_audio.configure(text="Audio On")

    def _on_close(self) -> None:
        self._audio_running = False
        self.gui._viewer_window = None
        self.gui._viewer_active = False
        self.gui.root.after(0, lambda: self.gui.btn_viewer.configure(text="Viewer"))
        self.win.destroy()


class ChatGUI:
    def __init__(self, client: ChatClient) -> None:
        self.client = client
        self.client._gui_queue = queue.Queue()
        self.client._gui_mode = True

        self.root = tk.Tk()
        self.root.title("Asciline Chat")
        self.root.geometry("960x640")
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._voice_var = tk.BooleanVar(value=False)
        self._video_var = tk.BooleanVar(value=False)
        self._screen_var = tk.BooleanVar(value=False)
        self._viewer_active = False
        self._viewer_window: ViewerWindow | None = None

        self._build_toolbar()
        self._build_main()

    # ------------------------------------------------------------------ build
    def _build_toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=BG_PANEL, pady=4)
        bar.pack(side=tk.TOP, fill=tk.X)

        btn_style = dict(bg=BG_PANEL, fg=FG, activebackground="#333", activeforeground=FG,
                         relief=tk.FLAT, padx=8, pady=2, font=("monospace", 10))

        self.btn_voice = tk.Checkbutton(bar, text="Mic", variable=self._voice_var,
                                        command=self._toggle_voice, **btn_style)
        self.btn_voice.pack(side=tk.LEFT, padx=4)

        self.btn_video = tk.Checkbutton(bar, text="Camera", variable=self._video_var,
                                        command=self._toggle_video, **btn_style)
        self.btn_video.pack(side=tk.LEFT, padx=4)

        self.btn_screen = tk.Checkbutton(bar, text="Screen", variable=self._screen_var,
                                         command=self._toggle_screen, **btn_style)
        self.btn_screen.pack(side=tk.LEFT, padx=4)

        tk.Frame(bar, width=2, bg=FG_DIM).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)

        self.btn_viewer = tk.Button(bar, text="Viewer", command=self._toggle_viewer, **btn_style)
        self.btn_viewer.pack(side=tk.LEFT, padx=4)

        self.btn_send_img = tk.Button(bar, text="Send Image", command=self._send_image_dialog, **btn_style)
        self.btn_send_img.pack(side=tk.LEFT, padx=4)

        self.btn_send_file = tk.Button(bar, text="Send File", command=self._send_file_dialog, **btn_style)
        self.btn_send_file.pack(side=tk.LEFT, padx=4)

    def _build_main(self) -> None:
        main = tk.Frame(self.root, bg=BG)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # ---- left panel ----
        left = tk.Frame(main, bg=BG_PANEL, width=200)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(2, 0), pady=2)
        left.pack_propagate(False)

        # server
        sf = tk.LabelFrame(left, text=" Server ", bg=BG_PANEL, fg=FG_DIM,
                           font=("monospace", 9), padx=6, pady=3)
        sf.pack(fill=tk.X, padx=4, pady=(4, 2))
        self.lbl_server = tk.Label(sf, text=f"{self.client.host}:{self.client.port}",
                                   bg=BG_PANEL, fg=FG, anchor="w", font=("monospace", 11, "bold"))
        self.lbl_server.pack(fill=tk.X)

        # room
        rf = tk.LabelFrame(left, text=" Room ", bg=BG_PANEL, fg=FG_DIM,
                           font=("monospace", 9), padx=6, pady=3)
        rf.pack(fill=tk.X, padx=4, pady=2)
        self.lbl_room = tk.Label(rf, text=self.client.room,
                                 bg=BG_PANEL, fg=FG, anchor="w", font=("monospace", 11))
        self.lbl_room.pack(fill=tk.X)

        # peers
        pf = tk.LabelFrame(left, text=" Peers ", bg=BG_PANEL, fg=FG_DIM,
                           font=("monospace", 9), padx=6, pady=3)
        pf.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        peer_inner = tk.Frame(pf, bg=BG_PANEL)
        peer_inner.pack(fill=tk.BOTH, expand=True)
        self.peer_scroll = tk.Scrollbar(peer_inner)
        self.peer_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.peer_listbox = tk.Listbox(peer_inner, yscrollcommand=self.peer_scroll.set,
                                       activestyle="none", font=("monospace", 10),
                                       bg=BG_PANEL, fg=FG, selectbackground="#264f78",
                                       selectforeground=FG, relief=tk.FLAT,
                                       highlightthickness=0, bd=0)
        self.peer_listbox.pack(fill=tk.BOTH, expand=True)
        self.peer_scroll.configure(command=self.peer_listbox.yview)

        # status
        stf = tk.LabelFrame(left, text=" Status ", bg=BG_PANEL, fg=FG_DIM,
                            font=("monospace", 9), padx=6, pady=3)
        stf.pack(fill=tk.X, padx=4, pady=(2, 4))
        self.lbl_status = tk.Label(stf, text="Connecting...", bg=BG_PANEL, fg=FG_STATUS,
                                   anchor="w", wraplength=180, justify="left",
                                   font=("monospace", 9))
        self.lbl_status.pack(fill=tk.X)

        # ---- right panel ----
        right = tk.Frame(main, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)

        # chat text area
        chat_wrap = tk.Frame(right, bg=BG)
        chat_wrap.pack(fill=tk.BOTH, expand=True)

        self.txt_chat = tk.Text(chat_wrap, state=tk.DISABLED, wrap=tk.WORD,
                                bg=BG, fg=FG, insertbackground=FG,
                                font=("monospace", 10), relief=tk.FLAT,
                                padx=8, pady=8, bd=0, highlightthickness=0)
        chat_scroll = tk.Scrollbar(chat_wrap, command=self.txt_chat.yview, bg=BG_PANEL)
        chat_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_chat.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.txt_chat.configure(yscrollcommand=chat_scroll.set)

        self.txt_chat.tag_configure("sys", foreground=FG_SYS)
        self.txt_chat.tag_configure("status", foreground=FG_STATUS)
        self.txt_chat.tag_configure("chat_user", foreground=FG_USER, font=("monospace", 10, "bold"))
        self.txt_chat.tag_configure("chat_text", foreground=FG)
        self.txt_chat.tag_configure("img_info", foreground=FG_IMG)

        # input bar
        inp = tk.Frame(right, bg=BG)
        inp.pack(fill=tk.X, side=tk.BOTTOM, pady=(4, 0))

        self.entry_input = tk.Entry(inp, font=("monospace", 11), bg="#3c3c3c", fg=FG,
                                    insertbackground=FG, relief=tk.FLAT,
                                    highlightthickness=1, highlightcolor="#555",
                                    highlightbackground="#555")
        self.entry_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.entry_input.bind("<Return>", self._on_entry_return)

        self.btn_send = tk.Button(inp, text="Send", command=self._on_send,
                                  bg="#0e639c", fg=FG, activebackground="#1177bb",
                                  relief=tk.FLAT, padx=14, pady=4, font=("monospace", 10, "bold"))
        self.btn_send.pack(side=tk.RIGHT)

    # ------------------------------------------------------------ polling
    def _poll_queue(self) -> None:
        try:
            for _ in range(200):  # drain up to 200 messages per tick
                method, args, kwargs = self.client._gui_queue.get_nowait()
                handler = getattr(self, method, None)
                if handler:
                    handler(*args, **kwargs)
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._poll_queue)

    # -------------------------------------------------------- chat display
    def _append_chat(self, text: str, tag: str = "chat_text") -> None:
        self.txt_chat.configure(state=tk.NORMAL)
        self.txt_chat.insert(tk.END, text + "\n", tag)
        self.txt_chat.see(tk.END)
        self.txt_chat.configure(state=tk.DISABLED)

    def ui(self, msg: str) -> None:
        self._append_chat(msg)

    def ui_status(self, msg: str) -> None:
        self._append_chat(f"* {msg}", "status")

    def ui_sys(self, msg: str) -> None:
        self._append_chat(f"* {msg}", "sys")
        # sync media toggle states
        low = msg.lower()
        if "voice on" in low or "voice listen" in low:
            self._voice_var.set(True)
        elif "voice off" in low:
            self._voice_var.set(False)
        if "camera on" in low:
            self._video_var.set(True)
        elif "camera off" in low:
            self._video_var.set(False)
        if "screen on" in low:
            self._screen_var.set(True)
        elif "screen off" in low:
            self._screen_var.set(False)
        # refresh peers on join/leave
        if "joined" in low or "left" in low or "sharing" in low:
            self._refresh_peers()
        # update status label
        if "connected to" in msg:
            self.lbl_status.configure(text=msg)

    def ui_chat(self, who: str, text: str) -> None:
        self.txt_chat.configure(state=tk.NORMAL)
        self.txt_chat.insert(tk.END, f"<{who}> ", "chat_user")
        self.txt_chat.insert(tk.END, f"{text}\n", "chat_text")
        self.txt_chat.see(tk.END)
        self.txt_chat.configure(state=tk.DISABLED)

    def ui_video_frame(self, text: str, label: str = "ASCIILINE") -> None:
        self._append_chat(f"── {label} ──", "status")

    def ui_image(self, image_id: str, webp_bytes: bytes, sender: str, name: str, width: int, height: int) -> None:
        try:
            from PIL import Image, ImageTk
            img = Image.open(io.BytesIO(webp_bytes))
            # Scale to fit chat width (~600px)
            max_w = 580
            if img.width > max_w:
                ratio = max_w / img.width
                img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)

            # Create a frame in the chat area for the image
            self.txt_chat.configure(state=tk.NORMAL)
            # Sender label
            self.txt_chat.insert(tk.END, f"\n<{sender}> ", "chat_user")
            self.txt_chat.insert(tk.END, f"sent image {name} ({width}x{height})\n", "chat_text")
            # Insert the image via a window tag
            img_frame = tk.Frame(self.txt_chat, bg=BG)
            lbl = tk.Label(img_frame, image=photo, bg=BG)
            lbl._photo = photo  # prevent GC
            lbl.pack()
            # Download button
            saved_path = self.client._received_images.get(image_id, (None, None, None))[0] if image_id in self.client._received_images else None
            btn = tk.Button(img_frame, text=f"Download ({name})", bg="#0e639c", fg=FG,
                            activebackground="#1177bb", relief=tk.FLAT, padx=8, pady=2,
                            font=("monospace", 9),
                            command=lambda p=image_id: self._download_image(p))
            btn.pack(pady=(2, 4))
            self.txt_chat.window_create(tk.END, window=img_frame)
            self.txt_chat.insert(tk.END, "\n")
            self.txt_chat.see(tk.END)
            self.txt_chat.configure(state=tk.DISABLED)
        except Exception:
            self._append_chat(f"* image preview failed", "status")

    def _download_image(self, image_id: str) -> None:
        if image_id not in self.client._received_images:
            self.ui_status(f"image {image_id} not found")
            return
        meta, webp_bytes, _ = self.client._received_images[image_id]
        path = filedialog.asksaveasfilename(
            title="Save Image",
            initialfile=f"{meta.name}",
            defaultextension=".webp",
            filetypes=[("WebP", "*.webp"), ("PNG", "*.png"), ("JPEG", "*.jpg"), ("All", "*.*")]
        )
        if path:
            if path.lower().endswith((".png", ".jpg", ".jpeg")):
                from PIL import Image
                img = Image.open(io.BytesIO(webp_bytes))
                img.save(path)
            else:
                from pathlib import Path
                Path(path).write_bytes(webp_bytes)
            self.ui_status(f"saved → {path}")

    def ui_video_jpeg(self, jpeg_bytes: bytes, source: str) -> None:
        if self._viewer_window is not None:
            self._viewer_window.push_jpeg(jpeg_bytes, source)

    def ui_file(self, file_id: str, file_bytes: bytes, sender: str, name: str, mime_type: str, size: int) -> None:
        self.txt_chat.configure(state=tk.NORMAL)
        self.txt_chat.insert(tk.END, f"\n<{sender}> ", "chat_user")
        size_kb = size / 1024
        self.txt_chat.insert(tk.END, f"sent file {name} ({mime_type}, {size_kb:.1f} KB)\n", "chat_text")
        file_frame = tk.Frame(self.txt_chat, bg=BG)
        lbl = tk.Label(file_frame, text=f"  {name}  {mime_type}  {size_kb:.1f} KB",
                       bg=BG, fg=FG, font=("monospace", 10), anchor="w")
        lbl.pack(side=tk.LEFT, padx=4)
        btn = tk.Button(file_frame, text="Save", bg="#0e639c", fg=FG,
                        activebackground="#1177bb", relief=tk.FLAT, padx=8, pady=2,
                        font=("monospace", 9),
                        command=lambda p=file_id: self._download_file(p))
        btn.pack(side=tk.LEFT, padx=4)
        self.txt_chat.window_create(tk.END, window=file_frame)
        self.txt_chat.insert(tk.END, "\n")
        self.txt_chat.see(tk.END)
        self.txt_chat.configure(state=tk.DISABLED)

    def _download_file(self, file_id: str) -> None:
        if file_id not in self.client._received_files:
            self.ui_status(f"file {file_id} not found")
            return
        meta, file_bytes = self.client._received_files[file_id]
        path = filedialog.asksaveasfilename(
            title="Save File",
            initialfile=meta.name,
            defaultextension="",
            filetypes=[("All", "*.*")]
        )
        if path:
            from pathlib import Path
            Path(path).write_bytes(file_bytes)
            self.ui_status(f"saved → {path}")

    # ----------------------------------------------------------- peers
    def _refresh_peers(self) -> None:
        self.peer_listbox.delete(0, tk.END)
        for uid in self.client.peer_identity:
            name = self.client.peer_display.get(uid, uid)
            e2e = "E2E" if uid in self.client.sessions else "pending"
            voice = " mic" if self.client.voice_active_peers.get(uid) else ""
            media = ""
            self.peer_listbox.insert(tk.END, f"{name}  {e2e}{voice}{media}")

    # ----------------------------------------------------------- input
    def _on_entry_return(self, _event: Any = None) -> None:
        self._on_send()

    def _on_send(self) -> None:
        text = self.entry_input.get().strip()
        if not text:
            return
        self.entry_input.delete(0, tk.END)
        if text.startswith("/"):
            asyncio.run_coroutine_threadsafe(
                self.client._command(text), self.client.loop
            )
        else:
            asyncio.run_coroutine_threadsafe(
                self.client.send_chat(text), self.client.loop
            )

    # ------------------------------------------------------- media toggles
    def _toggle_voice(self) -> None:
        if self.client.loop is None:
            return
        if self._voice_var.get():
            self.client.loop.call_soon_threadsafe(self.client.start_voice)
        else:
            self.client.loop.call_soon_threadsafe(self.client.stop_voice)

    def _toggle_video(self) -> None:
        if self.client.loop is None:
            return
        if self._video_var.get():
            self.client.loop.call_soon_threadsafe(self.client.start_video)
        else:
            self.client.loop.call_soon_threadsafe(self.client.stop_video)

    def _toggle_screen(self) -> None:
        if self.client.loop is None:
            return
        if self._screen_var.get():
            self.client.loop.call_soon_threadsafe(self.client.start_screen)
        else:
            self.client.loop.call_soon_threadsafe(self.client.stop_screen)

    def _toggle_viewer(self) -> None:
        if self._viewer_active and self._viewer_window is not None:
            self._viewer_window._on_close()
        else:
            self._viewer_window = ViewerWindow(self)
            self._viewer_active = True
            self.btn_viewer.configure(text="Viewer *")

    # ------------------------------------------------------ send image
    def _send_image_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Send Image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.gif *.bmp"), ("All", "*.*")]
        )
        if path:
            asyncio.run_coroutine_threadsafe(
                self.client.send_image(path), self.client.loop
            )

    def _send_file_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Send File",
            filetypes=[("All", "*.*")]
        )
        if path:
            asyncio.run_coroutine_threadsafe(
                self.client.send_file(path), self.client.loop
            )

    # -------------------------------------------------------- lifecycle
    def _start_asyncio_thread(self) -> None:
        def _loop() -> None:
            self.client.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.client.loop)
            try:
                self.client.loop.run_until_complete(self.client.run())
            except Exception:
                pass

        self._async_thread = threading.Thread(target=_loop, daemon=True, name="asciline-async")
        self._async_thread.start()

    def run(self) -> None:
        self._start_asyncio_thread()
        self._poll_queue()
        self.root.mainloop()

    def _on_close(self) -> None:
        if self.client.loop:
            self.client._stop.set()
        self.root.after(300, self.root.destroy)
