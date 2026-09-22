import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import tkinterdnd2
    _HAS_DND = True
except ImportError:
    _HAS_DND = False

import asr
from license import (
    TRIAL_MAX,
    check_auth,
    check_trial_or_registered,
    current_registration,
    increment_trial,
    is_registered,
    machine_code,
    save_registration,
    trial_count,
    verify_license,
)

_BASE_CLASS = tkinterdnd2.TkinterDnD.Tk if _HAS_DND else tk.Tk

_BG = "#f5f6fa"
_CARD = "#ffffff"
_ACCENT = "#4a6cf7"
_ACCENT_HOVER = "#3a5ce5"
_ACCENT_LIGHT = "#eef1fd"
_TEXT = "#2d3436"
_TEXT_SEC = "#636e72"
_TEXT_MUTED = "#b2bec3"
_BORDER = "#dfe6e9"
_SUCCESS = "#00b894"
_WARNING = "#fdcb6e"
_DANGER = "#e17055"
_DROP_BG = "#f0f3ff"
_DROP_BORDER = "#4a6cf7"
_LANG_MAP = {"自动识别": "auto", "中文": "zh", "英文": "en", "日文": "ja", "韩文": "ko", "粤语": "yue"}
_LANG_DISPLAY = list(_LANG_MAP.keys())
_SHADOW = "#e0e3eb"


class _Style:
    @staticmethod
    def apply(root):
        s = ttk.Style(root)
        s.theme_use("clam")
        s.configure(".", background=_BG, foreground=_TEXT, font=("PingFang SC", 10),
                     borderwidth=0, relief="flat")
        s.configure("TFrame", background=_BG)
        s.configure("Card.TFrame", background=_CARD)
        s.configure("TLabel", background=_BG, foreground=_TEXT)
        s.configure("Card.TLabel", background=_CARD, foreground=_TEXT)
        s.configure("Muted.TLabel", background=_BG, foreground=_TEXT_MUTED)
        s.configure("Sec.TLabel", background=_BG, foreground=_TEXT_SEC)
        s.configure("Title.TLabel", background=_CARD, foreground=_TEXT, font=("PingFang SC", 13, "bold"))
        s.configure("Heading.TLabel", background=_BG, foreground=_TEXT, font=("PingFang SC", 11, "bold"))
        s.configure("Success.TLabel", foreground=_SUCCESS)
        s.configure("Warning.TLabel", foreground=_WARNING)
        s.configure("Danger.TLabel", foreground=_DANGER)
        s.configure("TButton", background=_ACCENT, foreground="#ffffff",
                     font=("PingFang SC", 10, "bold"), padding=(20, 8),
                     borderwidth=0, relief="flat", focuscolor="none",
                     anchor="center")
        s.map("TButton",
              background=[("active", _ACCENT_HOVER), ("pressed", "#2f4cd3"), ("disabled", _BORDER)],
              foreground=[("disabled", _TEXT_MUTED)])
        s.configure("Outline.TButton", background=_CARD, foreground=_ACCENT,
                     font=("PingFang SC", 10), padding=(20, 8),
                     borderwidth=1, relief="solid",
                     focuscolor="none", anchor="center")
        s.map("Outline.TButton",
              background=[("active", _ACCENT_LIGHT), ("pressed", "#dce3fd")],
              bordercolor=[("!disabled", _ACCENT), ("disabled", _BORDER)])
        s.configure("TCheckbutton", background=_BG, foreground=_TEXT, font=("PingFang SC", 10),
                     focuscolor="none")
        s.configure("TCombobox", font=("PingFang SC", 10),
                     fieldbackground=_CARD, background=_CARD,
                     foreground=_TEXT, selectbackground=_ACCENT_LIGHT,
                     selectforeground=_ACCENT,
                     borderwidth=1, relief="solid",
                     arrowcolor=_ACCENT, arrowsize=12,
                     padding=(10, 6))
        s.map("TCombobox",
              fieldbackground=[("readonly", _CARD), ("focus", _CARD)],
              bordercolor=[("focus", _ACCENT), ("!focus", _BORDER)],
              selectbackground=[("readonly", _ACCENT_LIGHT)],
              selectforeground=[("readonly", _ACCENT)])
        s.configure("TCombobox.Listbox", background=_CARD, foreground=_TEXT,
                     font=("PingFang SC", 10), selectbackground=_ACCENT_LIGHT,
                     selectforeground=_ACCENT, borderwidth=0, relief="flat")
        s.configure("TLabelframe", background=_CARD, foreground=_TEXT, font=("PingFang SC", 10, "bold"))
        s.configure("TLabelframe.Label", background=_CARD, foreground=_TEXT, font=("PingFang SC", 10, "bold"))
        s.configure("TScrollbar", troughcolor=_BG, background=_BORDER, thickness=6,
                     borderwidth=0, relief="flat", arrowsize=10)
        s.map("TScrollbar", background=[("active", _TEXT_MUTED)])


class _ProgressIndicator(tk.Canvas):
    """自绘进度条：圆角细线 + 脉冲动画。"""

    def __init__(self, master, **kw):
        super().__init__(master, height=3, bg=_BG, highlightthickness=0, **kw)
        self._pos = 0
        self._running = False
        self._bar_w = 80
        self.bind("<Configure>", self._draw)

    def start(self, interval=30):
        self._running = True
        self._tick()

    def stop(self):
        self._running = False
        self.delete("all")

    def _tick(self):
        if not self._running:
            return
        self._pos = (self._pos + 3) % (self.winfo_width() + self._bar_w)
        self._draw()
        self.after(30, self._tick)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        if w < 2:
            return
        self.create_rectangle(0, 0, w, 3, fill=_BORDER, outline="")
        x = self._pos - self._bar_w
        x1 = max(0, x)
        x2 = min(w, x + self._bar_w)
        if x2 > x1:
            self.create_rectangle(x1, 0, x2, 3, fill=_ACCENT, outline="")


class LicenseDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("软件注册")
        self.configure(bg=_BG)
        self.resizable(False, False)
        self.grab_set()
        self._ok = False
        self._build_ui()
        self._refresh_status()
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        main = ttk.Frame(self, style="Card.TFrame", padding=24)
        main.pack(fill="both", expand=True, padx=16, pady=16)

        ttk.Label(main, text="软件注册", style="Title.TLabel").pack(anchor="w", pady=(0, 16))

        ttk.Label(main, text="本机机器码", style="Heading.TLabel", background=_CARD).pack(anchor="w")
        self._lb_code = ttk.Label(
            main, text="", font=("Menlo", 11), foreground=_TEXT_SEC,
            wraplength=420, justify="left", background=_CARD,
        )
        self._lb_code.pack(anchor="w", pady=(2, 6))

        btn_copy = ttk.Button(main, text="复制机器码", command=self._copy_code, width=14, style="Outline.TButton")
        btn_copy.pack(anchor="w", pady=(0, 16))

        ttk.Label(main, text="注册码", style="Heading.TLabel", background=_CARD).pack(anchor="w")
        self._ed_code = ttk.Entry(main, width=50, font=("Menlo", 10))
        self._ed_code.pack(anchor="w", pady=(2, 6), fill="x")

        self._lb_status = ttk.Label(main, text="", wraplength=420, justify="left", background=_CARD)
        self._lb_status.pack(anchor="w", pady=(0, 16))

        ops = ttk.Frame(main, style="Card.TFrame")
        ops.pack(anchor="e")
        ttk.Button(ops, text="注册", command=self._do_register, width=10).pack(side="left", padx=(0, 8))
        ttk.Button(ops, text="关闭", command=self._on_close, width=10, style="Outline.TButton").pack(side="left")

    def _refresh_status(self):
        try:
            self._lb_code.config(text=machine_code())
        except RuntimeError as e:
            self._lb_code.config(text=str(e))
        reg = current_registration()
        if reg:
            self._lb_status.config(text="✓ 已注册（永久授权）", foreground=_SUCCESS)
        else:
            used = trial_count()
            remaining = TRIAL_MAX - used
            if remaining > 0:
                self._lb_status.config(
                    text=f"未注册。还剩 {remaining} 次免费试用机会。\n试用结束后需注册才能继续使用。",
                    foreground=_WARNING,
                )
            else:
                self._lb_status.config(
                    text="试用次数已用完。请将本机机器码发给卖方换取注册码。",
                    foreground=_DANGER,
                )

    def _copy_code(self):
        self.clipboard_clear()
        self.clipboard_append(self._lb_code.cget("text"))
        self._lb_status.config(text="机器码已复制到剪贴板。", foreground=_ACCENT)

    def _do_register(self):
        code = self._ed_code.get().strip()
        if not code:
            self._lb_status.config(text="请输入注册码。", foreground=_DANGER)
            return
        ok, msg, info = verify_license(code)
        if not ok:
            self._lb_status.config(text=msg, foreground=_DANGER)
            return
        if info.get("machine") and info["machine"] != self._lb_code.cget("text"):
            self._lb_status.config(text="该注册码不属于本机（机器码不匹配）。", foreground=_DANGER)
            return
        if save_registration(code):
            self._lb_status.config(text="✓ 注册成功（永久授权）。", foreground=_SUCCESS)
            self._ok = True
            self.after(700, self._on_close)
        else:
            self._lb_status.config(text="注册码写入失败，请检查权限后重试。", foreground=_DANGER)

    def _on_close(self):
        self.grab_release()
        self.destroy()

    def show(self) -> bool:
        self.wait_window()
        return self._ok


class App(_BASE_CLASS):
    def __init__(self):
        super().__init__()
        self.title("音频转文字")
        self.configure(bg=_BG)
        self.resizable(False, False)
        self._result_queue = queue.Queue()
        _Style.apply(self)
        self._build_ui()
        if _HAS_DND:
            self._setup_dnd()
        self._center_window()
        self._poll_queue()

    def _build_menu(self):
        menubar = tk.Menu(self, bg=_CARD, fg=_TEXT, activebackground=_ACCENT, activeforeground="#fff",
                          font=("PingFang SC", 10))
        help_menu = tk.Menu(menubar, tearoff=0, bg=_CARD, fg=_TEXT,
                            activebackground=_ACCENT, activeforeground="#fff",
                            font=("PingFang SC", 10))
        help_menu.add_command(label="注册授权...", command=self._show_license)
        help_menu.add_separator()
        help_menu.add_command(label="关于", command=self._show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.config(menu=menubar)

    def _center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        self._build_menu()

        self.file_var = tk.StringVar()

        self._build_drop_zone()
        self._build_options()
        self._build_actions()
        self._build_result_area()

        self.file_var.trace_add("write", self._on_file_var_change)

    def _build_drop_zone(self):
        outer = tk.Frame(self, bg=_BG, padx=16, pady=12)
        outer.pack(fill="x")

        shadow = tk.Frame(outer, bg=_SHADOW, padx=2, pady=2)
        shadow.pack(fill="x")

        self._drop_frame = tk.Frame(shadow, bg=_DROP_BG, highlightbackground=_DROP_BORDER,
                                     highlightthickness=2, cursor="hand2")
        self._drop_frame.pack(fill="x")

        inner = tk.Frame(self._drop_frame, bg=_DROP_BG, padx=20, pady=16)
        inner.pack(fill="x")

        self._drop_icon = tk.Label(
            inner, text="🎵", font=("", 24), fg=_ACCENT, bg=_DROP_BG,
        )
        self._drop_icon.pack(side="left", padx=(0, 16))

        text_col = tk.Frame(inner, bg=_DROP_BG)
        text_col.pack(side="left", fill="y", expand=True)

        self._drop_label = tk.Label(
            text_col,
            text="拖拽音频文件到此处，或点击选择",
            fg=_TEXT_SEC, bg=_DROP_BG,
            font=("PingFang SC", 12),
            anchor="w",
        )
        self._drop_label.pack(anchor="w")

        self._drop_hint = tk.Label(
            text_col,
            text="支持 WAV / MP3 / M4A 格式",
            fg=_TEXT_MUTED, bg=_DROP_BG,
            font=("PingFang SC", 9),
            anchor="w",
        )
        self._drop_hint.pack(anchor="w")

        self._file_label = tk.Label(
            text_col,
            text="", fg=_ACCENT, bg=_DROP_BG,
            font=("PingFang SC", 11, "bold"), anchor="w",
        )

        for w in (self._drop_frame, inner, self._drop_icon, self._drop_label, self._drop_hint):
            w.bind("<Button-1>", lambda e: self._pick_file())
            w.bind("<Enter>", self._on_drop_enter)
            w.bind("<Leave>", self._on_drop_leave)

    def _build_options(self):
        bar = tk.Frame(self, bg=_CARD, padx=20, pady=10)
        bar.pack(fill="x", padx=16, pady=(12, 0))

        tk.Label(bar, text="语言", bg=_CARD, fg=_TEXT_SEC,
                 font=("PingFang SC", 9)).pack(side="left", padx=(0, 4))
        self.lang_var = tk.StringVar(value="自动识别")
        self.lang_combo = ttk.Combobox(
            bar, textvariable=self.lang_var,
            values=_LANG_DISPLAY,
            state="readonly", width=8,
        )
        self.lang_combo.pack(side="left", padx=(0, 24))

        self.diarize_var = tk.BooleanVar(value=False)
        self._diarize_cb = tk.Checkbutton(
            bar, text="区分说话人", variable=self.diarize_var,
            command=self._on_diarize_change,
            bg=_CARD, fg=_TEXT, selectcolor=_CARD,
            activebackground=_CARD, activeforeground=_ACCENT,
            font=("PingFang SC", 10), cursor="hand2",
        )
        self._diarize_cb.pack(side="left", padx=(0, 8))

        self.num_speakers_var = tk.StringVar(value="自动")
        tk.Label(bar, text="人数", bg=_CARD, fg=_TEXT_SEC,
                 font=("PingFang SC", 9)).pack(side="left", padx=(0, 4))
        self.num_speakers_combo = ttk.Combobox(
            bar, textvariable=self.num_speakers_var,
            values=["自动", "2", "3", "4", "5"],
            state="readonly", width=4,
        )
        self.num_speakers_combo.pack(side="left")
        self.num_speakers_combo.config(state="disabled")

    def _build_actions(self):
        frame = ttk.Frame(self, padding=(16, 12))
        frame.pack(fill="x")

        self.run_btn = ttk.Button(frame, text="▶  开始识别", command=self._run)
        self.run_btn.pack(side="left")

        ttk.Button(frame, text="复制结果", command=self._copy_result, style="Outline.TButton").pack(side="left", padx=(8, 0))

        self._status_label = ttk.Label(frame, text="", style="Muted.TLabel", font=("PingFang SC", 9))
        self._status_label.pack(side="right")

        self.progress = _ProgressIndicator(self)
        self.progress.pack(fill="x", padx=16)

    def _build_result_area(self):
        card = ttk.Frame(self, style="Card.TFrame", padding=16)
        card.pack(fill="both", expand=True, padx=16, pady=(12, 16))

        ttk.Label(card, text="识别结果", style="Title.TLabel").pack(anchor="w", pady=(0, 8))

        text_frame = tk.Frame(card, bg=_BORDER, padx=1, pady=1)
        text_frame.pack(fill="both", expand=True)

        self.result_text = tk.Text(
            text_frame, height=12, width=60, wrap="word",
            bg=_CARD, fg=_TEXT, font=("PingFang SC", 11),
            relief="flat", padx=12, pady=8,
            insertbackground=_ACCENT, selectbackground=_ACCENT_LIGHT,
        )
        scrollbar = ttk.Scrollbar(text_frame, command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=scrollbar.set)
        self.result_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _setup_dnd(self):
        self._drop_frame.drop_target_register("DND_Files")
        self._drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        self._drop_frame.dnd_bind("<<DndEnter>>", self._on_dnd_enter)
        self._drop_frame.dnd_bind("<<DndLeave>>", self._on_dnd_leave)
        self._drop_label.drop_target_register("DND_Files")
        self._drop_label.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop_enter(self, event=None):
        self._drop_frame.config(highlightbackground=_ACCENT, bg=_DROP_HOVER)
        for w in (self._drop_icon, self._drop_label, self._drop_hint, self._file_label):
            w.config(bg=_DROP_HOVER)

    def _on_drop_leave(self, event=None):
        self._drop_frame.config(highlightbackground=_DROP_BORDER, bg=_DROP_BG)
        for w in (self._drop_icon, self._drop_label, self._drop_hint, self._file_label):
            w.config(bg=_DROP_BG)

    def _on_dnd_enter(self, event):
        self._on_drop_enter()

    def _on_dnd_leave(self, event):
        self._on_drop_leave()

    def _on_drop(self, event):
        self._on_drop_leave()
        path = event.data.strip().strip('"').strip("'")
        if path:
            self.file_var.set(path)

    def _on_file_var_change(self, *args):
        path = self.file_var.get().strip()
        if path:
            self._drop_label.pack_forget()
            self._drop_hint.pack_forget()
            self._drop_icon.config(text="📄")
            self._file_label.config(text=os.path.basename(path))
            self._file_label.pack(anchor="w")
        else:
            self._file_label.pack_forget()
            self._drop_icon.config(text="🎵")
            self._drop_label.pack(anchor="w")
            self._drop_hint.pack(anchor="w")

    def _on_diarize_change(self):
        if self.diarize_var.get():
            self.num_speakers_combo.config(state="readonly")
        else:
            self.num_speakers_combo.config(state="disabled")

    def _check_license(self) -> bool:
        ok, msg = check_trial_or_registered()
        if not ok:
            messagebox.showinfo(
                "授权提示",
                msg or "试用次数已用完，请注册后继续使用。\n"
                "请将机器码发送给卖方获取注册码。",
            )
            dlg = LicenseDialog(self)
            dlg.show()
            return is_registered()
        if is_registered():
            return True
        if not check_auth():
            messagebox.showwarning("授权校验", "授权验证异常，请重新注册。")
            return False
        used = trial_count()
        remaining = increment_trial()
        messagebox.showinfo(
            "免费试用",
            f"您正在使用免费试用模式（第 {used + 1}/{TRIAL_MAX} 次）。\n"
            f"剩余 {remaining} 次试用机会。\n"
            "试用结束后需注册才能继续使用。",
        )
        return True

    def _show_license(self):
        dlg = LicenseDialog(self)
        dlg.show()

    def _show_about(self):
        reg = current_registration()
        if reg:
            status = "✓ 已注册（永久授权）"
        else:
            used = trial_count()
            remaining = TRIAL_MAX - used
            if remaining > 0:
                status = f"未注册 · 剩余 {remaining} 次试用"
            else:
                status = "试用已用完，请注册"
        messagebox.showinfo(
            "关于",
            f"音频转文字\n\n"
            f"识别模型：SenseVoice\n"
            f"支持语言：中文 / 英文 / 日文 / 韩文 / 粤语\n\n"
            f"授权状态：{status}",
        )

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="选择音频文件",
            filetypes=[
                ("音频文件", "*.wav *.mp3 *.m4a"),
                ("WAV", "*.wav"),
                ("MP3", "*.mp3"),
                ("M4A", "*.m4a"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.file_var.set(path)

    def _set_ui_busy(self, busy):
        state = "disabled" if busy else "normal"
        self.run_btn.config(state=state)
        if busy:
            self.progress.start()
            self._status_label.config(text="识别中...", foreground=_ACCENT)
        else:
            self.progress.stop()
            self._status_label.config(text="")

    def _poll_queue(self):
        try:
            while True:
                msg_type, msg_data = self._result_queue.get_nowait()
                if msg_type == "result":
                    self._show_result(msg_data)
                elif msg_type == "error":
                    self._show_error(msg_data)
                elif msg_type == "log":
                    self.result_text.insert("end", msg_data + "\n")
                    self.result_text.see("end")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _run(self):
        if not self._check_license():
            return
        audio_path = self.file_var.get().strip().strip('"').strip("'")
        if not audio_path:
            messagebox.showwarning("提示", "请先选择音频文件")
            return
        if not os.path.exists(audio_path):
            messagebox.showerror("错误", f"文件不存在:\n{audio_path}")
            return

        model = "sensevoice"
        language = _LANG_MAP.get(self.lang_var.get(), "auto")
        use_vad = False
        use_diarize = self.diarize_var.get()
        num_speakers_str = self.num_speakers_var.get()

        self._set_ui_busy(True)
        self.result_text.delete("1.0", "end")
        self.result_text.insert("end", "识别中...\n")

        q = self._result_queue

        def worker():
            temp_wav = None
            try:
                q.put(("log", f"[调试] 开始处理: {audio_path}"))
                q.put(("log", f"[调试] 模型: {model}, 语言: {language}, VAD: {use_vad}, 区分说话人: {use_diarize}"))

                q.put(("log", "[调试] 步骤1: 转换音频格式..."))
                wav_path = asr.convert_to_wav(audio_path)
                if wav_path != audio_path:
                    temp_wav = wav_path
                    q.put(("log", f"[调试] 已转换为WAV: {wav_path}"))
                else:
                    q.put(("log", "[调试] 已是WAV格式，无需转换"))

                if use_diarize:
                    q.put(("log", "[调试] 步骤2: 说话人区分 + 语音识别..."))
                    num_clusters = -1
                    if num_speakers_str != "自动":
                        num_clusters = int(num_speakers_str)
                    text = asr.transcribe_with_diarization(
                        wav_path,
                        model=model,
                        language=language,
                        num_threads=4,
                        num_clusters=num_clusters,
                    )
                else:
                    q.put(("log", "[调试] 步骤2: 加载模型并识别..."))
                    text = asr.transcribe_file(
                        wav_path,
                        model=model,
                        language=language,
                        use_vad=use_vad,
                        num_threads=4,
                    )
                q.put(("log", f"[调试] 识别完成，结果长度: {len(text)}"))

                if temp_wav and os.path.exists(temp_wav):
                    os.remove(temp_wav)
                    q.put(("log", "[调试] 临时文件已清理"))

                q.put(("result", text))
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                print(tb)
                q.put(("error", f"{e}\n\n详细错误:\n{tb}"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, text):
        self._set_ui_busy(False)
        self.result_text.delete("1.0", "end")
        if text:
            self.result_text.insert("end", text)
        else:
            self.result_text.insert("end", "(识别完成，但未检测到语音内容)")

    def _show_error(self, msg):
        self._set_ui_busy(False)
        self.result_text.delete("1.0", "end")
        self.result_text.insert("end", f"识别失败:\n{msg}")

    def _copy_result(self):
        text = self.result_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("提示", "已复制到剪贴板")


if __name__ == "__main__":
    app = App()
    app.mainloop()