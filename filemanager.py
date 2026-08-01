# -*- coding: utf-8 -*-
"""
行空板 OS - 文件管理器
功能：目录浏览、返回/上级、文件列表（名称/大小/修改时间）、
      双击进入文件夹、按扩展名联动打开图片查看器/视频播放器、删除（带确认）。
"""
import os
import sys
import time
import shlex
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import theme
from theme import (
    BG, SURFACE, SURFACE2, HOVER, ACCENT, ACCENT2, DANGER,
    TEXT, MUTED, ON_ACCENT, COLOR_FOLDER, COLOR_IMAGE, COLOR_VIDEO, COLOR_FILE, COLOR_PY, COLOR_TEXT, COLOR_SHELL,
    FONT_NORMAL, FONT_SMALL, is_image, is_video, is_python, is_shell, is_text, BOARD, apply_board_window,
    setup_board_button, spawn_window,
)
from softkeyboard import SoftKeyboard


def human_size(n: int) -> str:
    units = ["B", "K", "M", "G", "T"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024.0
        i += 1
    if i == 0:
        return f"{int(f)}B"
    return f"{f:.1f}{units[i]}"


class FileManager(tk.Toplevel):
    def __init__(self, master, start_dir=None, on_open_image=None, on_open_video=None):
        super().__init__(master)
        self.title("行空文件管理器")
        self.configure(bg=BG)
        apply_board_window(self)
        self.geometry(f"{theme.BOARD_W if BOARD else theme.WIN_W}x{theme.BOARD_H if BOARD else theme.WIN_H}")
        self.master = master

        self.on_open_image = on_open_image
        self.on_open_video = on_open_video

        self.current_dir = os.path.abspath(start_dir or os.getcwd())
        self._kbd = None
        self._build_ui()
        self._refresh()
        setup_board_button(self)

    # ---------------- UI ----------------
    def _build_ui(self):
        px = 2 if BOARD else 4
        py = 4 if BOARD else 6

        # 顶部第一行：返回桌面 / 上级 / 回用户主目录
        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="返回", command=lambda: self.destroy(),
                   style="UH.Danger.TButton").pack(side=tk.LEFT, padx=px, pady=py)
        ttk.Button(bar, text="上级", command=self._up,
                   style="UH.TButton").pack(side=tk.LEFT, padx=px, pady=py)
        ttk.Button(bar, text="主页", command=self._home,
                   style="UH.TButton").pack(side=tk.RIGHT, padx=px, pady=py)

        # 第二行：路径输入 + GO（小屏也能手动跳转）
        pathbar = tk.Frame(self, bg=SURFACE)
        pathbar.pack(fill=tk.X)
        self.path_var = tk.StringVar(value=self.current_dir)
        self.path_entry = tk.Entry(pathbar, textvariable=self.path_var,
                                   bg=SURFACE2, fg=TEXT, font=FONT_SMALL,
                                   relief=tk.FLAT, insertbackground=TEXT)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True,
                             padx=px, pady=py)
        # 点击路径框弹出自制软键盘（仅触摸，避免焦点回弹循环）
        self.path_entry.bind("<Button-1>", self._open_keyboard)
        ttk.Button(pathbar, text="GO", command=self._goto,
                   style="UH.TButton").pack(side=tk.LEFT, padx=px, pady=py)
        if not BOARD:
            ttk.Button(pathbar, text="其他", command=self._browse,
                       style="UH.TButton").pack(side=tk.LEFT, padx=px, pady=py)

        # 列表区 + 右侧滚动条
        list_frame = tk.Frame(self, bg=BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

        cols = ("name", "size", "mtime")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings",
                                 selectmode="browse")
        self.tree.heading("name", text="名称", anchor=tk.W)
        self.tree.heading("size", text="大小", anchor=tk.W)
        self.tree.heading("mtime", text="时间", anchor=tk.W)
        if BOARD:
            # 240 宽小屏只显示名称列，给滚动条留空间；stretch 打开边界可拖动
            self.tree.column("name", width=190, anchor=tk.W, stretch=True, minwidth=40)
            self.tree.column("size", width=0, stretch=False, minwidth=0)
            self.tree.column("mtime", width=0, stretch=False, minwidth=0)
            self.tree["displaycolumns"] = ("name",)
        else:
            self.tree.column("name", width=360, anchor=tk.W, stretch=True, minwidth=80)
            self.tree.column("size", width=110, anchor=tk.E, stretch=False)
            self.tree.column("mtime", width=170, anchor=tk.W, stretch=False)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 使用 tk.Scrollbar：板子上比 ttk 滚动条更粗、更显眼、触控更好抓
        self.vscroll = tk.Scrollbar(
            list_frame, orient=tk.VERTICAL,
            command=self.tree.yview,
            width=18 if BOARD else 20,
            troughcolor=BG,
            bg=ACCENT,
            activebackground=ACCENT2,
            highlightthickness=0,
            bd=0,
            relief=tk.FLAT,
        )
        self.vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=self.vscroll.set)

        self.tree.tag_configure("folder", foreground=COLOR_FOLDER)
        self.tree.tag_configure("image", foreground=COLOR_IMAGE)
        self.tree.tag_configure("video", foreground=COLOR_VIDEO)
        self.tree.tag_configure("py", foreground=COLOR_PY)
        self.tree.tag_configure("text", foreground=COLOR_TEXT)
        self.tree.tag_configure("shell", foreground=COLOR_SHELL)
        self.tree.tag_configure("file", foreground=COLOR_FILE)

        self.tree.bind("<Double-1>", self._on_double)
        self.tree.bind("<Return>", self._on_double)
        self.tree.bind("<KeyPress-a>", lambda e: self.destroy())
        self.tree.bind("<KeyPress-A>", lambda e: self.destroy())

        # 快捷键：A / a 返回桌面
        self.bind("<KeyPress-a>", lambda e: self.destroy())
        self.bind("<KeyPress-A>", lambda e: self.destroy())
        self.focus_set()

        # 底部操作栏
        foot = tk.Frame(self, bg=SURFACE)
        foot.pack(fill=tk.X)
        ttk.Button(foot, text="删除", command=self._delete,
                   style="UH.Danger.TButton").pack(side=tk.RIGHT,
                                                    padx=px, pady=py)
        ttk.Button(foot, text="运行", command=self._run_selected,
                   style="UH.Run.TButton").pack(side=tk.RIGHT, padx=px, pady=py)
        ttk.Button(foot, text="打开", command=self._open_selected,
                   style="UH.TButton").pack(side=tk.RIGHT, padx=px, pady=py)
        self.status = tk.Label(foot, text="就绪", bg=SURFACE, fg=MUTED,
                               font=FONT_SMALL, anchor=tk.W)
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        self._style()

    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("UH.TButton", background=ACCENT, foreground=theme.ON_ACCENT,
                    font=FONT_NORMAL, borderwidth=0,
                    padding=(2, 2) if BOARD else 6)
        s.map("UH.TButton", background=[("active", ACCENT2)])
        s.configure("UH.Danger.TButton", background=DANGER, foreground="#fff",
                    font=FONT_NORMAL, borderwidth=0,
                    padding=(2, 2) if BOARD else 6)
        s.map("UH.Danger.TButton", background=[("active", "#c9184a")])
        s.configure("UH.Run.TButton", background=COLOR_IMAGE, foreground="#06231d",
                    font=FONT_NORMAL, borderwidth=0,
                    padding=(2, 2) if BOARD else 6)
        s.map("UH.Run.TButton", background=[("active", ACCENT2)])
        s.configure("Treeview", background=SURFACE, foreground=TEXT,
                    fieldbackground=SURFACE, font=FONT_NORMAL,
                    rowheight=22 if BOARD else 28, borderwidth=0)
        s.configure("Treeview.Heading", background=SURFACE2, foreground=TEXT,
                    font=FONT_NORMAL, borderwidth=0, anchor=tk.W)
        s.map("Treeview",
              background=[("selected", HOVER)],
              foreground=[("selected", TEXT)])
        # 列表滚动条是 tk.Scrollbar，直接传颜色参数，不用 ttk 样式

    # ---------------- 逻辑 ----------------
    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.path_var.set(self.current_dir)
        try:
            entries = sorted(
                os.listdir(self.current_dir),
                key=lambda n: (not os.path.isdir(os.path.join(self.current_dir, n)),
                               n.lower()),
            )
        except PermissionError:
            messagebox.showerror("错误", "没有权限访问该目录")
            return

        for name in entries:
            full = os.path.join(self.current_dir, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            if os.path.isdir(full):
                tag, size = "folder", "[目录]"
            elif is_image(name):
                tag, size = "image", human_size(st.st_size)
            elif is_video(name):
                tag, size = "video", human_size(st.st_size)
            elif is_python(name):
                tag, size = "py", human_size(st.st_size)
            elif is_shell(name):
                tag, size = "shell", human_size(st.st_size)
            elif is_text(name):
                tag, size = "text", human_size(st.st_size)
            else:
                tag, size = "file", human_size(st.st_size)
            mtime = time.strftime("%m-%d %H:%M", time.localtime(st.st_mtime))
            self.tree.insert("", tk.END, values=(name, size, mtime),
                             tags=(tag,))

        self.status.config(text=f"{len(entries)} 项 · {self.current_dir}")

    def _selected_path(self):
        sel = self.tree.selection()
        if not sel:
            return None
        name = self.tree.item(sel[0], "values")[0]
        return os.path.join(self.current_dir, name)

    def _on_double(self, _=None):
        self._open_selected()

    def _open_selected(self):
        path = self._selected_path()
        if not path:
            return
        if os.path.isdir(path):
            self.current_dir = path
            self._refresh()
            return
        self._confirm_open(path)

    def _run_selected(self):
        path = self._selected_path()
        if not path:
            return
        if os.path.isdir(path):
            return
        name = os.path.basename(path)
        if not is_python(name) and not is_shell(name):
            messagebox.showinfo("提示",
                                "只有 .py / .sh 文件可以一键运行。\n"
                                "其他类型请用「打开」按钮。")
            return
        # .py / .sh 都走统一的打开确认窗口（默认动作=运行）
        self._confirm_open(path, focus="run")

    def _confirm_open(self, path, focus=None):
        """双击/打开时弹出统一确认窗口，按类型给出可执行动作。"""
        name = os.path.basename(path)
        actions = []
        if is_python(name):
            desc = "Python 程序：运行会打开终端/窗口；也可在此编辑源码。"
            actions = [
                ("运行", lambda: self._run_py(path)),
                ("编辑", lambda: self._edit_text(path)),
            ]
        elif is_shell(name):
            desc = "Shell 脚本：可用原生控制台（系统终端）或自制控制台运行，" \
                   "也可在此编辑源码。"
            actions = [
                ("原生控制台", lambda: self._run_sh_native(path)),
                ("自制控制台", lambda: self._run_sh_console(path)),
                ("编辑", lambda: self._edit_text(path)),
            ]
        elif is_image(name):
            desc = "将用图片查看器打开。"
            actions = [("查看", lambda: self._launch_image(path))]
        elif is_video(name):
            desc = "将用视频播放器播放。"
            actions = [("播放", lambda: self._launch_video(path))]
        elif is_text(name):
            desc = "将用文本编辑器打开。"
            actions = [("编辑", lambda: self._edit_text(path))]
        else:
            desc = "暂不支持预览该类型。"
            actions = []
        OpenConfirm(self, path, actions, desc, focus=focus)

    def _run_py(self, path):
        name = os.path.basename(path)
        if messagebox.askyesno("运行 Python 程序",
                               f"确定运行：\n{name}\n\n"
                               "将在后台启动子进程，可随时停止。"):
            RunWindow(self.master, path)
            self.status.config(text=f"已启动：{name}")

    def _run_sh_console(self, path):
        """用自制控制台（tk 窗口）运行 shell 脚本。"""
        from shconsole import RunShWindow
        RunShWindow(self.master, path)
        self.status.config(text=f"自制控制台：{os.path.basename(path)}")

    # 原生控制台：启动系统终端模拟器运行脚本。
    # 不同终端的「执行命令」参数不同，按候选顺序挑一个可用的。
    _TERMINAL_FLAGS = [
        ("lxterminal", ["-e"]),
        ("x-terminal-emulator", ["-e"]),
        ("gnome-terminal", ["--"]),
        ("konsole", ["-e"]),
        ("xfce4-terminal", ["-x"]),
        ("terminator", ["-x"]),
        ("tilix", ["-e"]),
        ("xterm", ["-e"]),
    ]

    def _find_terminal(self):
        """返回 (终端可执行路径, 执行命令的参数列表) 或 None。"""
        if sys.platform.startswith("win"):
            p = shutil.which("wt.exe") or shutil.which("wt")
            if p:
                return (p, ["-p", "Command Prompt", "/k", "bash", "-c"])
            return ("cmd.exe", ["/c", "start", "", "bash", "-c"])
        for cmd, flag in self._TERMINAL_FLAGS:
            p = shutil.which(cmd)
            if p:
                return (p, flag)
        return None

    def _run_sh_native(self, path):
        """用原生控制台（系统终端）运行 shell 脚本。"""
        name = os.path.basename(path)
        term = self._find_terminal()
        if not term:
            messagebox.showwarning("原生控制台不可用",
                                   "未检测到系统终端模拟器，无法启动原生控制台。\n"
                                   "请改用「自制控制台」运行此脚本。")
            return
        exe, flag = term
        # 脚本结束后保持窗口，方便查看输出；read 等待用户回车关闭
        inner = "bash %s; echo; echo '=== 已结束，按回车关闭 ==='; read" \
                % shlex.quote(path)
        argv = [exe] + list(flag) + ["bash", "-c", inner]
        try:
            subprocess.Popen(argv)
            self.status.config(text=f"已在原生控制台启动：{name}")
        except Exception as e:
            messagebox.showerror("启动失败", str(e))

    def _edit_text(self, path):
        from texteditor import TextEditor
        TextEditor(self.master, path)
        self.status.config(text=f"编辑：{os.path.basename(path)}")

    def _launch_image(self, path):
        # 用 spawn_window：打开图片查看器时隐藏文件管理器，关闭后自动恢复。
        # 行空板无窗口管理器，必须保证同一时刻只有唯一可交互窗口。
        if self.on_open_image:
            spawn_window(self, self.on_open_image, path)
        else:
            from imageviewer import ImageViewer
            spawn_window(self, ImageViewer, self.master, path)

    def _launch_video(self, path):
        if self.on_open_video:
            spawn_window(self, self.on_open_video, path)
        else:
            from videoplayer import VideoPlayer
            spawn_window(self, VideoPlayer, self.master, path)

    def _up(self):
        parent = os.path.dirname(self.current_dir)
        if parent and parent != self.current_dir:
            self.current_dir = parent
            self._refresh()

    def _home(self):
        self.current_dir = os.path.expanduser("~")
        self._refresh()

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.current_dir)
        if d:
            self.current_dir = d
            self._refresh()

    def _goto(self):
        p = self.path_var.get().strip()
        if os.path.isdir(p):
            self.current_dir = os.path.abspath(p)
            self._refresh()
        else:
            messagebox.showerror("错误", "目录不存在")

    def _open_keyboard(self, _=None):
        """点击路径输入框弹出自制软键盘输入法。"""
        if self._kbd and self._kbd.winfo_exists():
            self._kbd.lift()
            return
        self._kbd = SoftKeyboard(self, self.path_entry)

    def _delete(self):
        path = self._selected_path()
        if not path:
            return
        name = os.path.basename(path)
        if not messagebox.askyesno("确认删除", f"确定删除：\n{name} ?"):
            return
        try:
            if os.path.isdir(path):
                import shutil
                shutil.rmtree(path)
            else:
                os.remove(path)
            self._refresh()
            self.status.config(text=f"已删除：{name}")
        except Exception as e:
            messagebox.showerror("删除失败", str(e))


class OpenConfirm(tk.Toplevel):
    """打开任意文件前的统一确认窗口：显示文件名/类型，按类型给出动作按钮。"""

    def __init__(self, master, path, actions, desc, focus=None):
        super().__init__(master)
        self.title("打开确认")
        self.configure(bg=BG)
        apply_board_window(self)
        self.geometry(f"{theme.BOARD_W if BOARD else theme.WIN_W}x"
                      f"{theme.BOARD_H if BOARD else theme.WIN_H}")
        self.master = master
        name = os.path.basename(path)
        px = 2 if BOARD else 4
        py = 4 if BOARD else 6

        # 顶部信息
        info = tk.Frame(self, bg=SURFACE)
        info.pack(fill=tk.X, padx=4, pady=4)
        tk.Label(info, text="打开确认", bg=SURFACE, fg=ACCENT,
                 font=FONT_NORMAL).pack(anchor=tk.W)
        tk.Label(info, text=name, bg=SURFACE, fg=TEXT, font=FONT_NORMAL,
                 wraplength=210 if BOARD else 600, anchor=tk.W
                 ).pack(anchor=tk.W, pady=(3, 0))
        tk.Label(info, text=desc, bg=SURFACE, fg=MUTED, font=FONT_SMALL,
                 wraplength=210 if BOARD else 600, anchor=tk.W
                 ).pack(anchor=tk.W, pady=(2, 0))

        # 动作按钮区
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        for label, cb in actions:
            tk.Button(body, text=label,
                      command=lambda c=cb: self._do(c),
                      bg=ACCENT, fg=ON_ACCENT, font=FONT_NORMAL,
                      activebackground=ACCENT2, relief=tk.FLAT, bd=0,
                      highlightthickness=0
                      ).pack(fill=tk.X, padx=px, pady=py)
        # 取消
        tk.Button(body, text="取消", command=lambda: self.destroy(),
                  bg=SURFACE2, fg=TEXT, font=FONT_NORMAL,
                  activebackground=HOVER, relief=tk.FLAT, bd=0,
                  highlightthickness=0
                  ).pack(fill=tk.X, padx=px, pady=py)

        setup_board_button(self)
        self.focus_set()

    def _do(self, cb):
        self.destroy()
        try:
            cb()
        except Exception as e:
            messagebox.showerror("打开失败", str(e))


class RunWindow(tk.Toplevel):
    """一键运行 Python 程序的输出窗口：后台启动子进程，实时显示输出，可停止。"""

    def __init__(self, master, path):
        super().__init__(master)
        self.path = path
        self.proc = None
        self.title("运行: " + os.path.basename(path))
        self.configure(bg=BG)
        apply_board_window(self)
        self.geometry(f"{theme.BOARD_W if BOARD else theme.WIN_W}x{theme.BOARD_H if BOARD else theme.WIN_H}")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start()

    def _build(self):
        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill=tk.X)
        px = 2 if BOARD else 4
        py = 4 if BOARD else 6
        self.stop_btn = ttk.Button(bar, text="停止", command=self._stop,
                                   style="UH.Danger.TButton")
        self.stop_btn.pack(side=tk.LEFT, padx=px, pady=py)
        ttk.Button(bar, text="返回", command=self._on_close,
                   style="UH.TButton").pack(side=tk.RIGHT, padx=px, pady=py)
        self.status = tk.Label(bar, text="运行中...", bg=SURFACE, fg=MUTED,
                               font=FONT_SMALL, anchor=tk.W)
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        self.txt = tk.Text(self, bg=SURFACE2, fg=TEXT, font=FONT_SMALL,
                           relief=tk.FLAT, state=tk.DISABLED, wrap=tk.WORD)
        self.txt.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def _append(self, text):
        self.txt.configure(state=tk.NORMAL)
        self.txt.insert(tk.END, text)
        self.txt.see(tk.END)
        self.txt.configure(state=tk.DISABLED)

    def _start(self):
        cwd = os.path.dirname(self.path)
        self._append(f"$ {sys.executable} {os.path.basename(self.path)}\n"
                     f"  工作目录: {cwd}\n\n")
        try:
            self.proc = subprocess.Popen(
                [sys.executable, self.path],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                errors="replace",
            )
        except Exception as e:
            self._append(f"[无法启动] {e}\n")
            self.status.config(text="启动失败")
            self.stop_btn.configure(state=tk.DISABLED)
            return
        self._t0 = time.time()
        threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()

    def _pump(self, proc):
        try:
            for line in proc.stdout:
                self.after(0, self._append, line)
        except Exception:
            pass
        try:
            rc = proc.wait()
        except Exception:
            rc = -1
        dt = time.time() - self._t0
        self.after(0, self._finish, rc, dt)

    def _finish(self, rc, dt):
        self._append(f"\n[进程结束] 退出码={rc}  用时={dt:.1f}s\n")
        self.status.config(text=f"结束 退出码 {rc}")
        self.stop_btn.configure(state=tk.DISABLED)

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
    root = tk.Tk()
    root.withdraw()
    FileManager(root)
    root.mainloop()
