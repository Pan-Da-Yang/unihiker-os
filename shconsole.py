# -*- coding: utf-8 -*-
"""
行空板 OS - 自制控制台（运行 .sh / .bash 脚本）

在 tkinter 窗口内运行 shell 脚本：
  · 类 Unix（行空板/开发机 Linux/Mac）：通过伪终端(pty)运行，
    能驱动交互式脚本（含 read / 菜单选择），并实时回显输出。
  · Windows：无 pty，退化为管道(pipe)模式，仅实时显示输出、不可交互输入。
  · 顶部「停止」可终止进程；底部输入框可向脚本发送一行（pty 模式）；
    输入框右侧「键盘」按钮可弹出软键盘输入法（触摸屏输入命令/参数）。
  · 适配 240x320 小屏：去边框铺满，粗滚动条，A 键返回桌面。
"""
import os
import re
import sys
import time
import queue
import struct
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

import theme
from softkeyboard import SoftKeyboard
from theme import (
    BG, SURFACE, SURFACE2, HOVER, ACCENT, ACCENT2, DANGER, TEXT, MUTED, ON_ACCENT,
    FONT_NORMAL, FONT_SMALL, BOARD, apply_board_window, setup_board_button,
)

try:
    import pty
    import select
    import fcntl
    import termios
    _HAVE_PTY = not sys.platform.startswith("win")
except Exception:
    _HAVE_PTY = False

# 去掉 ANSI 转义（颜色/光标码），避免在文本框里显示乱码
_ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]")
# 等宽字体，更像一个真实控制台
_MONO = ("DejaVu Sans Mono", "Courier New", "Consolas", "monospace")


def _strip_ansi(b: bytes) -> bytes:
    return _ANSI_RE.sub(b"", b)


class RunShWindow(tk.Toplevel):
    """自制控制台：运行 shell 脚本，实时输出，可输入、可停止。"""

    def __init__(self, master, path):
        super().__init__(master)
        self.path = os.path.abspath(path)
        self.master = master
        self.proc = None
        self._master = None          # pty 主端 fd（交互输入用）
        self._use_pty = False
        self._t0 = time.time()
        self._q = queue.Queue()      # 后台线程 -> 主线程的唯一通道（线程安全）
        self.title("自制控制台: " + os.path.basename(path))
        self.configure(bg=BG)
        apply_board_window(self)
        self.geometry(f"{theme.BOARD_W if BOARD else theme.WIN_W}x"
                      f"{theme.BOARD_H if BOARD else theme.WIN_H}")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start()
        self._poll()                 # 主线程轮询队列，避免跨线程操作 Tk

    # ---------------- UI ----------------
    def _build(self):
        px = 2 if BOARD else 4
        py = 3 if BOARD else 6

        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill=tk.X)
        self.stop_btn = ttk.Button(bar, text="停止", command=self._stop,
                                   style="UH.Danger.TButton")
        self.stop_btn.pack(side=tk.LEFT, padx=px, pady=py)
        ttk.Button(bar, text="返回", command=self._on_close,
                   style="UH.TButton").pack(side=tk.RIGHT, padx=px, pady=py)
        self.status = tk.Label(bar, text="启动中...", bg=SURFACE, fg=MUTED,
                               font=FONT_SMALL, anchor=tk.W)
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        # 输出区：文本框 + 粗滚动条（小屏好抓）
        out_frame = tk.Frame(self, bg=BG)
        out_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.txt = tk.Text(out_frame, bg=SURFACE2, fg=TEXT,
                           font=(_MONO[0], 9 if BOARD else 11),
                           relief=tk.FLAT, state=tk.DISABLED, wrap=tk.WORD,
                           insertbackground=TEXT, width=1, height=1)
        self.txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vscroll = tk.Scrollbar(out_frame, orient=tk.VERTICAL,
                                    command=self.txt.yview,
                                    width=16 if BOARD else 18,
                                    troughcolor=BG, bg=ACCENT,
                                    activebackground=ACCENT2,
                                    highlightthickness=0, bd=0, relief=tk.FLAT)
        self.vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt.configure(yscrollcommand=self.vscroll.set)

        # 底部输入行（pty 模式可用，管道模式禁用）
        foot = tk.Frame(self, bg=SURFACE)
        foot.pack(fill=tk.X)
        self.input_var = tk.StringVar()
        self.entry = tk.Entry(foot, textvariable=self.input_var,
                              bg=SURFACE2, fg=TEXT, font=(_MONO[0], 9 if BOARD else 11),
                              relief=tk.FLAT, insertbackground=TEXT)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True,
                        padx=px, pady=py)
        self.entry.bind("<Return>", self._send_input)
        self.kbd_btn = ttk.Button(foot, text="键盘", command=self._open_keyboard,
                                  style="UH.TButton")
        self.send_btn = ttk.Button(foot, text="发送", command=self._send_input,
                                   style="UH.TButton")
        self.send_btn.pack(side=tk.RIGHT, padx=px, pady=py)
        self.kbd_btn.pack(side=tk.RIGHT, padx=px, pady=py)

        self._style()

    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("UH.TButton", background=ACCENT, foreground=ON_ACCENT,
                    font=FONT_NORMAL, borderwidth=0,
                    padding=(2, 2) if BOARD else 6)
        s.map("UH.TButton", background=[("active", ACCENT2)])
        s.configure("UH.Danger.TButton", background=DANGER, foreground="#fff",
                    font=FONT_NORMAL, borderwidth=0,
                    padding=(2, 2) if BOARD else 6)
        s.map("UH.Danger.TButton", background=[("active", "#c9184a")])

    # ---------------- 运行 ----------------
    def _start(self):
        cwd = os.path.dirname(self.path)
        self._append(f"$ bash {os.path.basename(self.path)}\n"
                     f"  工作目录: {cwd}\n\n")
        if _HAVE_PTY:
            self._start_pty(cwd)
        else:
            self._start_pipe(cwd)

    def _start_pty(self, cwd):
        try:
            master, slave = pty.openpty()
            # 设定伪终端窗口大小，让脚本里的行换行更合理
            try:
                winsize = struct.pack("HHHH", 40, 100, 0, 0)
                fcntl.ioctl(slave, termios.TIOCSWINSZ, winsize)
            except Exception:
                pass
            self._master = master
            self._use_pty = True
            self.proc = subprocess.Popen(
                ["bash", self.path],
                cwd=cwd,
                stdin=slave, stdout=slave, stderr=slave,
                env=os.environ.copy(), close_fds=True,
            )
            os.close(slave)
        except Exception as e:
            self._append(f"[无法启动] {e}\n")
            self.status.config(text="启动失败")
            self.stop_btn.configure(state=tk.DISABLED)
            self.entry.configure(state=tk.DISABLED)
            self.send_btn.configure(state=tk.DISABLED)
            self.kbd_btn.configure(state=tk.DISABLED)
            return
        self._t0 = time.time()
        threading.Thread(target=self._pump_pty, args=(master,),
                         daemon=True).start()

    def _start_pipe(self, cwd):
        self._use_pty = False
        # 管道模式不支持交互输入
        self.entry.configure(state=tk.DISABLED)
        self.send_btn.configure(state=tk.DISABLED)
        self.kbd_btn.configure(state=tk.DISABLED)
        try:
            self.proc = subprocess.Popen(
                ["bash", self.path],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, bufsize=1, errors="replace",
            )
        except Exception as e:
            self._append(f"[无法启动] {e}\n")
            self.status.config(text="启动失败")
            self.stop_btn.configure(state=tk.DISABLED)
            return
        self._t0 = time.time()
        threading.Thread(target=self._pump_pipe, args=(self.proc,),
                         daemon=True).start()

    def _pump_pty(self, master):
        try:
            while True:
                try:
                    r, _, _ = select.select([master], [], [], 0.2)
                except Exception:
                    break
                if r:
                    try:
                        data = os.read(master, 4096)
                    except OSError:
                        break
                    if not data:
                        break
                    self._q.put(("out", data))
        except Exception:
            pass
        rc = self.proc.wait() if self.proc else -1
        dt = time.time() - self._t0
        self._q.put(("done", (rc, dt)))

    def _pump_pipe(self, proc):
        try:
            for line in proc.stdout:
                self._q.put(("out", line))
        except Exception:
            pass
        try:
            rc = proc.wait()
        except Exception:
            rc = -1
        dt = time.time() - self._t0
        self._q.put(("done", (rc, dt)))

    def _poll(self):
        """主线程轮询输出队列，把所有 Tk 操作留在主线程执行（线程安全）。"""
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "out":
                    if isinstance(payload, (bytes, bytearray)):
                        self._append_bytes(payload)
                    else:
                        self._append(payload)
                elif kind == "done":
                    self._finish(*payload)
                    return  # 进程结束，停止轮询
        except queue.Empty:
            pass
        self.after(80, self._poll)

    # ---------------- 输出 ----------------
    def _append(self, text):
        self.txt.configure(state=tk.NORMAL)
        self.txt.insert(tk.END, text)
        self.txt.see(tk.END)
        self.txt.configure(state=tk.DISABLED)

    def _append_bytes(self, data):
        clean = _strip_ansi(data)
        try:
            text = clean.decode("utf-8", "replace")
        except Exception:
            text = clean.decode("latin-1", "replace")
        self._append(text)

    def _finish(self, rc, dt):
        self._append(f"\n[进程结束] 退出码={rc}  用时={dt:.1f}s\n")
        self.status.config(text=f"结束 退出码 {rc}")
        self.stop_btn.configure(state=tk.DISABLED)

    # ---------------- 输入 / 停止 ----------------
    def _send_input(self, _=None):
        if not self._use_pty or self._master is None:
            return
        line = self.input_var.get()
        self.input_var.set("")
        try:
            os.write(self._master, (line + "\n").encode("utf-8", "replace"))
        except Exception:
            pass

    def _open_keyboard(self):
        """打开软键盘输入法，把命令/参数输进底部输入框（触摸屏用）。"""
        if not self.entry.winfo_exists():
            return
        if str(self.entry.cget("state")) == tk.DISABLED:
            return
        try:
            SoftKeyboard(self, self.entry)
        except Exception:
            pass

    def _stop(self):
        if self.proc and self.proc.poll() is None:
            self._append("\n[用户停止...]\n")
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.after(1500, self._force_kill)

    def _force_kill(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass

    def _on_close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    import tempfile
    root = tk.Tk()
    root.withdraw()
    # 冒烟测试：写一个回显脚本并打开自制控制台
    tf = tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False)
    tf.write("echo 'hello from 自制控制台'\nread -p '输入点什么: ' x\n"
             "echo \"你输入了: $x\"\n")
    tf.close()
    RunShWindow(root, tf.name)
    root.mainloop()
