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


class LicenseDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("软件注册")
        self.resizable(False, False)
        self.grab_set()
        self._ok = False
        self._build_ui()
        self._refresh_status()
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        pad = dict(padx=10, pady=4)
        main = ttk.Frame(self, padding=15)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="本机机器码：", font=("", 10, "bold")).pack(anchor="w")
        self._lb_code = ttk.Label(
            main, text="", font=("Menlo", 11), foreground="#333",
            wraplength=420, justify="left",
        )
        self._lb_code.pack(anchor="w", pady=(0, 4))

        btn_copy = ttk.Button(main, text="复制机器码", command=self._copy_code, width=14)
        btn_copy.pack(anchor="w", pady=(0, 10))

        ttk.Label(main, text="注册码：", font=("", 10, "bold")).pack(anchor="w")
        self._ed_code = ttk.Entry(main, width=55, font=("Menlo", 10))
        self._ed_code.pack(anchor="w", pady=(0, 4))

        self._lb_status = ttk.Label(main, text="", wraplength=420, justify="left")
        self._lb_status.pack(anchor="w", pady=(0, 10))

        ops = ttk.Frame(main)
        ops.pack(anchor="e")
        ttk.Button(ops, text="注册", command=self._do_register, width=10).pack(side="left", padx=4)
        ttk.Button(ops, text="关闭", command=self._on_close, width=10).pack(side="left", padx=4)

    def _refresh_status(self):
        try:
            self._lb_code.config(text=machine_code())
        except RuntimeError as e:
            self._lb_code.config(text=str(e))
        reg = current_registration()
        if reg:
            self._lb_status.config(text="✓ 已注册（永久授权）", foreground="#2e7d32")
        else:
            used = trial_count()
            remaining = TRIAL_MAX - used
            if remaining > 0:
                self._lb_status.config(
                    text=f"未注册。还剩 {remaining} 次免费试用机会。\n试用结束后需注册才能继续使用。",
                    foreground="#e65100",
                )
            else:
                self._lb_status.config(
                    text="试用次数已用完。请将本机机器码发给卖方换取注册码。",
                    foreground="#c00000",
                )

    def _copy_code(self):
        self.clipboard_clear()
        self.clipboard_append(self._lb_code.cget("text"))
        self._lb_status.config(text="机器码已复制到剪贴板。", foreground="#1565c0")

    def _do_register(self):
        code = self._ed_code.get().strip()
        if not code:
            self._lb_status.config(text="请输入注册码。", foreground="#c00000")
            return
        ok, msg, info = verify_license(code)
        if not ok:
            self._lb_status.config(text=msg, foreground="#c00000")
            return
        if info.get("machine") and info["machine"] != self._lb_code.cget("text"):
            self._lb_status.config(text="该注册码不属于本机（机器码不匹配）。", foreground="#c00000")
            return
        if save_registration(code):
            self._lb_status.config(text="✓ 注册成功（永久授权）。", foreground="#2e7d32")
            self._ok = True
            self.after(700, self._on_close)
        else:
            self._lb_status.config(text="注册码写入失败，请检查权限后重试。", foreground="#c00000")

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
        self.resizable(False, False)
        self._result_queue = queue.Queue()
        self._build_ui()
        if _HAS_DND:
            self._setup_dnd()
        self._center_window()
        self._poll_queue()

    def _build_menu(self):
        menubar = tk.Menu(self)

        help_menu = tk.Menu(menubar, tearoff=0)
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

        pad = dict(padx=8, pady=4)

        self.file_var = tk.StringVar()

        self._drop_frame = tk.Frame(
            self, bg="#e8e8e8", relief="groove", bd=2,
            width=460, height=80,
        )
        self._drop_frame.pack(fill="x", padx=10, pady=(10, 0))
        self._drop_frame.pack_propagate(False)

        self._drop_label = tk.Label(
            self._drop_frame,
            text="拖拽音频文件到此处\n或点击选择文件",
            fg="#999999", bg="#e8e8e8",
            font=("", 13),
        )
        self._drop_label.pack(expand=True)

        self._file_label = tk.Label(
            self._drop_frame,
            text="", fg="#333333", bg="#e8e8e8",
            font=("", 10), anchor="w",
        )

        self._drop_label.bind("<Button-1>", lambda e: self._pick_file())
        self._drop_frame.bind("<Button-1>", lambda e: self._pick_file())

        self.file_var.trace_add("write", self._on_file_var_change)

        frame_top = ttk.Frame(self, padding=10)
        frame_top.pack(fill="x")

        ttk.Label(frame_top, text="语言:").grid(row=0, column=0, sticky="e")
        self.lang_var = tk.StringVar(value="auto")
        self.lang_combo = ttk.Combobox(
            frame_top, textvariable=self.lang_var,
            values=["auto", "zh", "en", "ja", "ko", "yue"], state="readonly", width=20,
        )
        self.lang_combo.grid(row=0, column=1, sticky="w", **pad)
        self.lang_combo.bind("<<ComboboxSelected>>", lambda e: None)

        self.diarize_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame_top, text="区分说话人 (对话模式)", variable=self.diarize_var,
            command=self._on_diarize_change,
        ).grid(row=1, column=1, sticky="w", **pad)

        self.num_speakers_var = tk.StringVar(value="自动")
        speaker_frame = ttk.Frame(frame_top)
        speaker_frame.grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(speaker_frame, text="说话人数量:").pack(side="left")
        self.num_speakers_combo = ttk.Combobox(
            speaker_frame, textvariable=self.num_speakers_var,
            values=["自动", "2", "3", "4", "5"], state="readonly", width=5,
        )
        self.num_speakers_combo.pack(side="left", padx=4)
        self.num_speakers_combo.config(state="disabled")

        btn_frame = ttk.Frame(frame_top)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=10)
        self.run_btn = ttk.Button(btn_frame, text="开始识别", command=self._run)
        self.run_btn.pack(side="left", padx=10)
        ttk.Button(btn_frame, text="复制结果", command=self._copy_result).pack(side="left", padx=10)

        self.progress = ttk.Progressbar(self, mode="indeterminate", length=400)
        self.progress.pack(fill="x", padx=10)

        result_frame = ttk.LabelFrame(self, text="识别结果", padding=10)
        result_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.result_text = tk.Text(result_frame, height=12, width=60, wrap="word")
        scrollbar = ttk.Scrollbar(result_frame, command=self.result_text.yview)
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

    def _on_dnd_enter(self, event):
        self._drop_frame.config(bg="#d0e8ff")
        self._drop_label.config(bg="#d0e8ff")
        self._file_label.config(bg="#d0e8ff")

    def _on_dnd_leave(self, event):
        bg = "#e8e8e8"
        self._drop_frame.config(bg=bg)
        self._drop_label.config(bg=bg)
        self._file_label.config(bg=bg)

    def _on_drop(self, event):
        self._on_dnd_leave(event)
        path = event.data.strip().strip('"').strip("'")
        if path:
            self.file_var.set(path)

    def _on_file_var_change(self, *args):
        path = self.file_var.get().strip()
        if path:
            self._drop_label.pack_forget()
            self._file_label.config(text=os.path.basename(path))
            self._file_label.pack(expand=True)
        else:
            self._file_label.pack_forget()
            self._drop_label.pack(expand=True)

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
                ("音频文件", "*.wav *.mp3 *.flac *.ogg *.m4a"),
                ("WAV", "*.wav"),
                ("MP3", "*.mp3"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.file_var.set(path)

    def _set_ui_busy(self, busy):
        state = "disabled" if busy else "normal"
        self.run_btn.config(state=state)
        if busy:
            self.progress.start(10)
        else:
            self.progress.stop()

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
        language = self.lang_var.get()
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