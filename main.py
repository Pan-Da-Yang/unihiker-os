# -*- coding: utf-8 -*-
"""
行空板 OS - 桌面启动器（全家桶入口）
启动后进入一个极简桌面：3×3 九宫格图标网格（预留扩展位）+ 底部任务栏（时钟）。
点击图标打开对应 App，各 App 之间自动联动：
  · 文件管理器双击图片 -> 图片查看器
  · 文件管理器双击视频 -> 视频播放器

运行：
  python main.py            # 行空板 240x320 触摸屏模式（去边框、无 emoji）
  python main.py --full     # 全屏（保留窗口装饰）
  python main.py --window   # 开发机窗口模式（较大窗口，便于调试）
"""
import os
import sys
import time
import math
import json
import threading
import platform
import tkinter as tk
from tkinter import ttk, messagebox

import theme

# 默认按行空板 240x320 运行；--window 切换到开发机大窗口模式
# 必须先设置板子模式，再导入各 App（这样它们才能读到压缩后的字体/尺寸常量）
_WINDOW = "--window" in sys.argv
_BOARD = not _WINDOW
if _BOARD:
    theme.set_board_mode(True)

from theme import (
    BG, SURFACE, SURFACE2, HOVER, ACCENT, ACCENT2, DANGER, TEXT, MUTED, ON_ACCENT,
    FONT_TITLE, FONT_NORMAL, FONT_SMALL, BOARD, BOARD_W, BOARD_H,
    apply_board_window, spawn_window,
)

import filemanager
import imageviewer
import videoplayer
import gamecenter
import pincontrol
import composer
import player
# 机械臂控制为本地可选模块：本地有 armcontrol.py 则显示入口，
# 远程仓库（GitHub）通过 .gitignore 排除该文件，导入失败时自动隐藏，不崩溃。
try:
    import armcontrol
except ImportError:
    armcontrol = None
import camera
from qq.ui import QQApp
from qq.net import QQClient


class Launcher:
    def __init__(self, root, fullscreen=False, board=False):
        self.root = root
        self.board = board
        root.title("行空 OS")
        root.configure(bg=BG)

        if board:
            apply_board_window(root)
        elif fullscreen:
            root.attributes("-fullscreen", True)
        else:
            root.geometry(f"{theme.WIN_W}x{theme.WIN_H}")

        self.apps = []
        self._build_desktop()
        self._build_taskbar()
        self._tick()

    # ---------------- 桌面 ----------------
    def _build_desktop(self):
        # 顶部标题栏
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill=tk.X, pady=(10 if self.board else 18, 4))
        tk.Label(top, text="行空 OS", bg=BG, fg=ACCENT,
                 font=FONT_TITLE).pack(side=tk.LEFT,
                                        padx=(10 if self.board else 20, 4))
        if not self.board:
            tk.Label(top, text="软件全家桶 v1.0", bg=BG, fg=MUTED,
                     font=FONT_SMALL).pack(side=tk.LEFT, padx=2)

        # 右上角设置按钮（齿轮）—— 直接用 Canvas 当按钮并绑定点击，
        # 避免“Button 里塞 Canvas”时点击落在 Canvas 上、按钮 command 收不到事件而点不开。
        gw, gh = (26, 26) if self.board else (28, 28)
        set_btn = tk.Canvas(top, width=gw, height=gh, bg=ACCENT,
                            highlightthickness=0, cursor="hand2")
        set_btn.pack(side=tk.RIGHT,
                     padx=(4, 6 if self.board else 16), pady=2)
        self._draw_gear(set_btn, ON_ACCENT, gw, gh)
        set_btn.bind("<Button-1>", lambda e: self._open_settings())
        set_btn.bind("<Enter>", lambda e: set_btn.config(bg=ACCENT2))
        set_btn.bind("<Leave>", lambda e: set_btn.config(bg=ACCENT))

        # 3×3 九宫格，居中；用空位占位把网格补齐到 9 格，
        # 后续新增 App 只要往 self._icons 里追加即可自动填满。
        self.grid = tk.Frame(self.root, bg=BG)
        self.grid.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._icons = [
            ("folder", "文件管理", ACCENT, self._open_filemanager),
            ("image", "图片查看", ACCENT2, self._spawn_image),
            ("video", "视频播放", DANGER, self._spawn_video),
            ("game", "游戏中心", "#9b5de5", self._spawn_games),
            ("pin", "引脚控制", "#2ec4b6", self._spawn_pins),
            ("music", "音乐", ACCENT2, self._spawn_music),
            ("qq", "QQ", ACCENT, self._spawn_qq),
        ]
        # 机械臂为本地可选模块，仅当 armcontrol 可导入时才加入九宫格
        if armcontrol is not None:
            self._icons.append(("arm", "机械臂", "#e76f51", self._spawn_arm))
        self._icons.append(("camera", "相机", "#06d6a0", self._spawn_camera))
        cols, rows = 3, 3
        for idx in range(cols * rows):
            item = self._icons[idx] if idx < len(self._icons) else None
            self._make_icon(self.grid, item, idx, cols)

    def _cell_geom(self):
        """返回 (cell_w, cell_h, icon_w, icon_h, pad)，板子/开发机两套尺寸。"""
        if self.board:
            # 240x320：3 行须压缩高度才能塞下九宫格
            return 72, 76, 32, 30, 2
        return 200, 120, 64, 54, 10

    def _make_icon(self, parent, item, idx, cols=3):
        if item is None:
            self._make_empty_slot(parent, idx, cols)
            return
        kind, label, color, cmd = item
        row, col = divmod(idx, cols)
        cell_w, cell_h, icon_w, icon_h, pad = self._cell_geom()

        cell = tk.Frame(parent, bg=BG, width=cell_w, height=cell_h)
        cell.grid(row=row, column=col, padx=pad, pady=pad)
        cell.pack_propagate(False)
        cell.grid_propagate(False)

        cvs = tk.Canvas(cell, width=icon_w, height=icon_h, bg=BG,
                        highlightthickness=0)
        cvs.pack(pady=(6, 2))
        self._draw_icon(cvs, kind, color, icon_w, icon_h)

        btn = tk.Button(cell, text=label, command=cmd, bg=SURFACE,
                        fg=color, font=FONT_NORMAL, relief=tk.FLAT,
                        activebackground=SURFACE2, cursor="hand2",
                        width=8 if self.board else 10)
        btn.pack()

        # 让网格居中
        parent.grid_rowconfigure(row, weight=1)
        parent.grid_columnconfigure(col, weight=1)

    def _make_empty_slot(self, parent, idx, cols):
        """九宫格里尚未启用的空位，用浅色 '+' 表示可扩展。"""
        row, col = divmod(idx, cols)
        cell_w, cell_h, _iw, _ih, pad = self._cell_geom()
        cell = tk.Frame(parent, bg=BG, width=cell_w, height=cell_h)
        cell.grid(row=row, column=col, padx=pad, pady=pad)
        cell.pack_propagate(False)
        cell.grid_propagate(False)

        cvs = tk.Canvas(cell, width=26, height=26, bg=BG,
                        highlightthickness=0)
        cvs.pack(expand=True)
        cvs.create_line(13, 5, 13, 21, fill=MUTED, width=2)
        cvs.create_line(5, 13, 21, 13, fill=MUTED, width=2)

        parent.grid_rowconfigure(row, weight=1)
        parent.grid_columnconfigure(col, weight=1)

    def _draw_icon(self, cvs, kind, color, w, h):
        pad = 4
        if kind == "folder":
            cvs.create_rectangle(pad, pad + 6, w - pad, h - pad,
                                 outline=color, width=2)
            cvs.create_line(pad + 4, pad + 6, pad + 18, pad + 6,
                            fill=color, width=2)
            cvs.create_line(pad + 4, pad + 6, pad + 4, pad,
                            fill=color, width=2)
            cvs.create_line(pad + 18, pad + 6, pad + 18, pad,
                            fill=color, width=2)
            cvs.create_line(pad + 4, pad, pad + 18, pad,
                            fill=color, width=2)
        elif kind == "image":
            cvs.create_rectangle(pad, pad, w - pad, h - pad,
                                 outline=color, width=2)
            cvs.create_polygon(
                pad + 6, h - pad - 4,
                w // 2, pad + 10,
                w - pad - 6, h - pad - 4,
                outline=color, fill="", width=2
            )
            cvs.create_oval(w - pad - 14, pad + 6, w - pad - 4, pad + 16,
                            outline=color, width=2)
        elif kind == "video":
            cvs.create_rectangle(pad, pad, w - pad, h - pad,
                                 outline=color, width=2)
            cvs.create_polygon(
                w // 2 - 7, h // 2 - 9,
                w // 2 - 7, h // 2 + 9,
                w // 2 + 10, h // 2,
                outline=color, fill=color, width=2
            )
        elif kind == "settings":
            # 齿轮
            cx, cy = w // 2, h // 2
            r = min(cx, cy) - pad - 4
            cvs.create_arc(cx - r, cy - r, cx + r, cy + r,
                           start=0, extent=360, outline=color, width=2,
                           style="arc")
            cr = r * 0.45
            cvs.create_arc(cx - cr, cy - cr, cx + cr, cy + cr,
                           start=0, extent=360, outline=color, width=2,
                           style="arc")
            for a in range(0, 360, 45):
                rad = math.radians(a)
                x1 = cx + math.cos(rad) * r
                y1 = cy + math.sin(rad) * r
                x2 = cx + math.cos(rad) * (r + 5)
                y2 = cy + math.sin(rad) * (r + 5)
                cvs.create_line(x1, y1, x2, y2, fill=color, width=2)
        elif kind == "game":
            # 游戏手柄
            cx = w // 2
            cy = h // 2
            bw, bh = w - pad * 2 - 6, h - pad * 2 - 8
            cvs.create_rectangle(pad, cy - bh // 2, w - pad - 6, cy + bh // 2,
                                 outline=color, width=2)
            # 左摇杆
            cvs.create_oval(pad + 6, cy - 4, pad + 14, cy + 4,
                            outline=color, width=2)
            # 右按键
            cvs.create_oval(w - pad - 18, cy - 6, w - pad - 10, cy + 2,
                            outline=color, width=2)
            cvs.create_oval(w - pad - 10, cy + 2, w - pad - 2, cy + 10,
                            outline=color, width=2)
        elif kind == "pin":
            # 芯片：中间方块 + 四边引脚
            cx, cy = w // 2, h // 2
            bw, bh = w - pad * 2 - 16, h - pad * 2 - 16
            cvs.create_rectangle(cx - bw // 2, cy - bh // 2,
                                 cx + bw // 2, cy + bh // 2,
                                 outline=color, width=2)
            for i in range(3):
                off = (i - 1) * (bw // 3)
                cvs.create_line(cx + off, cy - bh // 2,
                                cx + off, cy - bh // 2 - 5,
                                fill=color, width=2)
                cvs.create_line(cx + off, cy + bh // 2,
                                cx + off, cy + bh // 2 + 5,
                                fill=color, width=2)
                cvs.create_line(cx - bw // 2, cy + off,
                                cx - bw // 2 - 5, cy + off,
                                fill=color, width=2)
                cvs.create_line(cx + bw // 2, cy + off,
                                cx + bw // 2 + 5, cy + off,
                                fill=color, width=2)
        elif kind == "music":
            # 音符：符头 + 符干 + 八分音符旗
            cx = w // 2 - 2
            cy = h // 2 + 6
            r = 5
            cvs.create_oval(cx - r, cy - r, cx + r, cy + r,
                            outline=color, width=2)
            cvs.create_line(cx + r, cy, cx + r, cy - 18,
                            fill=color, width=2)
            cvs.create_line(cx + r, cy - 18, cx + r + 8, cy - 14,
                            fill=color, width=2)
            # 第二个符头（八度）
            cvs.create_oval(cx - r + 12, cy - r - 8, cx + r + 12, cy - 8,
                            outline=color, width=2)
            cvs.create_line(cx + r + 12, cy - 8, cx + r + 12, cy - 26,
                            fill=color, width=2)
        elif kind == "qq":
            # QQ 企鹅风格：圆头 + 身体 + 围巾（简化线条版）
            cx = w // 2
            cy = h // 2 + 1
            # 头
            hr = 8
            cvs.create_oval(cx - hr, cy - hr - 4, cx + hr, cy + hr - 4,
                            outline=color, width=2)
            # 身体（下方椭圆）
            cvs.create_oval(cx - 6, cy - 1, cx + 6, cy + 11,
                            outline=color, width=2)
            # 围巾
            cvs.create_line(cx - 7, cy + 2, cx + 7, cy + 2,
                            fill=color, width=2)
            # 眼睛两点
            cvs.create_oval(cx - 3, cy - 6, cx - 1, cy - 4, fill=color, outline="")
            cvs.create_oval(cx + 1, cy - 6, cx + 3, cy - 4, fill=color, outline="")
            # 嘴巴（小三角）
            cvs.create_polygon(cx - 2, cy - 2, cx + 2, cy - 2, cx, cy,
                               outline=color, fill="", width=1)
        elif kind == "arm":
            # 机械臂：底座 + 两段连杆 + 夹爪
            bx = w // 2
            by = h - pad - 2
            # 底座椭圆
            cvs.create_oval(bx - 10, by - 5, bx + 10, by + 2,
                            outline=color, width=1)
            # 大臂
            cvs.create_line(bx, by - 3, bx - 4, pad + 10,
                            fill=color, width=2, capstyle=tk.ROUND)
            # 小臂
            cvs.create_line(bx - 4, pad + 10, bx + 6, pad + 2,
                            fill=color, width=2, capstyle=tk.ROUND)
            # 夹爪两指
            cvs.create_line(bx + 6, pad + 2, bx + 3, pad - 1,
                            fill=color, width=1)
            cvs.create_line(bx + 6, pad + 2, bx + 9, pad - 1,
                            fill=color, width=1)
            # 关节点
            for jx, jy in [(bx, by - 3), (bx - 4, pad + 10), (bx + 6, pad + 2)]:
                cvs.create_oval(jx - 2, jy - 2, jx + 2, jy + 2,
                                fill=color, outline="")
        elif kind == "camera":
            # 相机：机身 + 镜头圈 + 闪光点
            bw, bh = w - pad * 2 - 8, h - pad * 2 - 14
            cvs.create_rectangle(pad, pad + 4, pad + bw, pad + 4 + bh,
                                 outline=color, width=2)
            # 顶部取景器凸起
            cvs.create_rectangle(pad + 6, pad - 2, pad + 16, pad + 4,
                                 outline=color, width=2)
            # 镜头
            cx, cy = pad + bw // 2, pad + 4 + bh // 2
            lr = min(bw, bh) // 3
            cvs.create_oval(cx - lr, cy - lr, cx + lr, cy + lr,
                            outline=color, width=2)
            cvs.create_oval(cx - lr + 3, cy - lr + 3, cx + lr - 3, cy + lr - 3,
                            outline=color, width=1)
            # 闪光灯
            cvs.create_oval(pad + bw - 6, pad + 8, pad + bw - 2, pad + 12,
                            outline=color, width=1)

    def _draw_gear(self, cvs, color, w, h):
        cx, cy = w // 2, h // 2
        r = min(cx, cy) - 2
        cvs.create_arc(cx - r, cy - r, cx + r, cy + r,
                       start=0, extent=360, outline=color, width=2,
                       style="arc")
        cr = r * 0.5
        cvs.create_arc(cx - cr, cy - cr, cx + cr, cy + cr,
                       start=0, extent=360, outline=color, width=2,
                       style="arc")
        for a in range(0, 360, 60):
            rad = math.radians(a)
            cvs.create_line(cx + math.cos(rad) * r, cy + math.sin(rad) * r,
                            cx + math.cos(rad) * (r + 2),
                            cy + math.sin(rad) * (r + 2),
                            fill=color, width=2)

    # ---------------- 任务栏 ----------------
    def _build_taskbar(self):
        bar = tk.Frame(self.root, bg=SURFACE2, height=28 if self.board else 34)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.clock = tk.Label(bar, text="", bg=SURFACE2, fg=TEXT,
                              font=FONT_NORMAL, anchor=tk.E)
        self.clock.pack(side=tk.RIGHT, padx=8 if self.board else 16)
        hint = "点击启动" if self.board else "点击图标启动应用"
        tk.Label(bar, text=hint, bg=SURFACE2, fg=MUTED,
                 font=FONT_SMALL, anchor=tk.W).pack(side=tk.LEFT,
                                                     padx=8 if self.board else 16)

    def _tick(self):
        self.clock.config(text=time.strftime("%H:%M:%S"))
        self.root.after(1000, self._tick)

    # ---------------- 启动 App ----------------
    def _track(self, win):
        self.apps.append(win)

    def _open_filemanager(self):
        try:
            win = filemanager.FileManager(
                self.root,
                on_open_image=self._open_image_viewer,
                on_open_video=self._open_video_player,
            )
            self._track(win)
            return win
        except Exception as e:
            messagebox.showerror("打开失败", f"文件管理器：{e}")
            return None

    # 桌面图标：用 spawn_window 打开子 App，自动隐藏桌面、关闭时恢复桌面。
    # （行空板无窗口管理器，必须保证同一时刻只有唯一可交互窗口，否则
    #  会出现“新窗口开在底层 / 焦点错乱 / 点哪儿都没反应”）
    def _spawn_image(self):
        spawn_window(self.root, self._open_image_viewer, None)

    def _spawn_video(self):
        spawn_window(self.root, self._open_video_player, None)

    def _spawn_games(self):
        spawn_window(self.root, self._open_gamecenter, None)

    def _spawn_pins(self):
        spawn_window(self.root, self._open_pincontrol, None)

    def _spawn_music(self):
        spawn_window(self.root, self._open_music, None)

    def _open_music(self):
        return player.MusicPlayer(self.root)

    def _spawn_composer(self):
        spawn_window(self.root, self._open_composer, None)

    def _spawn_qq(self):
        spawn_window(self.root, self._open_qq, None)

    def _spawn_arm(self):
        if armcontrol is None:
            return
        spawn_window(self.root, self._open_armcontrol, None)

    def _spawn_camera(self):
        spawn_window(self.root, self._open_camera, None)

    def _open_image_viewer(self, path=None):
        try:
            if path is None:
                if BOARD:
                    # 板子无原生文件对话框（240x320 屏不可用），直接进文件管理器挑图
                    return self._open_filemanager()
                from tkinter import filedialog
                path = filedialog.askopenfilename(
                    title="选择图片",
                    filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.bmp *.webp")])
                if not path:
                    return None
            win = imageviewer.ImageViewer(self.root, path)
            self._track(win)
            return win
        except Exception as e:
            messagebox.showerror("打开失败", f"图片查看器：{e}")
            return None

    def _open_video_player(self, path=None):
        try:
            if path is None:
                if BOARD:
                    return self._open_filemanager()
                from tkinter import filedialog
                path = filedialog.askopenfilename(
                    title="选择视频",
                    filetypes=[("视频", "*.mp4 *.avi *.mkv *.mov *.webm *.flv")])
                if not path:
                    return None
            win = videoplayer.VideoPlayer(self.root, path)
            self._track(win)
            return win
        except Exception as e:
            messagebox.showerror("打开失败", f"视频播放器：{e}")
            return None

    def _open_gamecenter(self, path=None):
        try:
            win = gamecenter.GameCenter(self.root)
            self._track(win)
            return win
        except Exception as e:
            messagebox.showerror("打开失败", f"游戏中心：{e}")
            return None

    def _open_settings(self):
        SettingsWindow(self.root)

    def _open_pincontrol(self, path=None):
        try:
            win = pincontrol.PinControl(self.root)
            self._track(win)
            return win
        except Exception as e:
            messagebox.showerror("打开失败", f"引脚控制：{e}")
            return None

    def _open_composer(self, path=None):
        try:
            win = composer.Composer(self.root)
            self._track(win)
            return win
        except Exception as e:
            messagebox.showerror("打开失败", f"编曲：{e}")
            return None

    def _open_qq(self, path=None):
        try:
            top = tk.Toplevel(self.root)
            top.title("QQ - 行空板")
            # QQ 界面专为 240x320 设计，两种模式都固定此尺寸
            if BOARD:
                apply_board_window(top)
            else:
                top.geometry("240x320")
            top.configure(bg="#ffffff")

            # ---- 复用 qq_unihiker 的客户端与连接逻辑 ----
            cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "qq", "config.json")
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}
            DEFAULT_SERVER = "win1q4t1r.xyz"
            PORT = 8888
            _saved_ip = cfg.get("server_ip")
            _LOCALHOST_SET = ("127.0.0.1", "localhost", "::1")
            _is_not_windows = platform.system().lower() != "windows"
            if _is_not_windows and (not _saved_ip or _saved_ip in _LOCALHOST_SET):
                server_ip = DEFAULT_SERVER
            else:
                server_ip = _saved_ip or DEFAULT_SERVER
            port = cfg.get("port", PORT)

            client = QQClient(server_ip or "127.0.0.1", port,
                              lambda m: top.after(0, app.on_net, m))
            app = QQApp(top, client)
            app.fields["serverip"] = server_ip

            # 连接逻辑（对齐 qq_unihiker/main.py）
            def try_connect():
                raw = (app.fields.get("serverip", "") or "").strip() or "127.0.0.1"
                ip = raw
                if ":" in raw:
                    parts = raw.rsplit(":", 1)
                    ip = parts[0].strip()
                    try:
                        p = int(parts[1].strip())
                        client.port = p
                    except (ValueError, IndexError):
                        ip = raw
                client.host = ip
                try:
                    client.connect(timeout=8)
                    cfg["server_ip"] = raw
                    cfg["port"] = client.port
                    try:
                        with open(cfg_path, "w", encoding="utf-8") as f:
                            json.dump(cfg, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    top.after(0, app._on_connected)
                except Exception as e:
                    err = str(e)
                    top.after(0, lambda h=ip, p=client.port, e=err:
                               app._on_conn_fail(h, p, e))

            app.on_retry = lambda: threading.Thread(
                target=try_connect, daemon=True).start()
            threading.Thread(target=try_connect, daemon=True).start()

            # 关闭窗口时一并关闭网络客户端
            orig_destroy = top.destroy
            def _my_destroy():
                try:
                    client.close()
                except Exception:
                    pass
                orig_destroy()
            top.destroy = _my_destroy

            self._track(top)
            return top
        except Exception as e:
            messagebox.showerror("打开失败", f"QQ：{e}")
            return None

    def _open_armcontrol(self, path=None):
        if armcontrol is None:
            return None
        try:
            win = armcontrol.ArmControl(self.root)
            self._track(win)
            return win
        except Exception as e:
            messagebox.showerror("打开失败", f"机械臂控制：{e}")
            return None

    def _open_camera(self, path=None):
        try:
            win = camera.CameraApp(self.root)
            self._track(win)
            return win
        except Exception as e:
            messagebox.showerror("打开失败", f"相机：{e}")
            return None

    def _exit(self):
        self.root.destroy()


class SettingsWindow(tk.Toplevel):
    """设置面板：切换亮/暗主题、退出程序。"""

    def __init__(self, master):
        super().__init__(master)
        self.title("设置")
        self.configure(bg=BG)
        apply_board_window(self)
        self.geometry("240x320")
        self.master = master
        self._build()
        self._style()

    def _build(self):
        # 顶部栏
        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill=tk.X)
        tk.Label(bar, text="设置", bg=SURFACE, fg=TEXT,
                 font=FONT_TITLE).pack(side=tk.LEFT, padx=10, pady=6)
        ttk.Button(bar, text="返回", command=lambda: self.destroy(),
                   style="UH.TButton").pack(side=tk.RIGHT, padx=4, pady=4)

        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        tk.Label(body, text="外观主题", bg=BG, fg=MUTED,
                 font=FONT_SMALL).pack(anchor=tk.W, pady=(2, 4))
        self.btn_light = ttk.Button(body, text="亮色",
                                    command=lambda: self._choose("light"),
                                    style="UH.TButton")
        self.btn_light.pack(fill=tk.X, pady=3)
        self.btn_dark = ttk.Button(body, text="暗色",
                                   command=lambda: self._choose("dark"),
                                   style="UH.TButton")
        self.btn_dark.pack(fill=tk.X, pady=3)
        self._mark(theme.get_theme())

        ttk.Separator(body).pack(fill=tk.X, pady=10)

        tk.Label(body, text="音量", bg=BG, fg=MUTED,
                 font=FONT_SMALL).pack(anchor=tk.W, pady=(2, 4))
        vol_row = tk.Frame(body, bg=BG)
        vol_row.pack(fill=tk.X)
        self.vol_lbl = tk.Label(vol_row, text=f"{theme.get_volume()}%",
                                bg=BG, fg=TEXT, font=FONT_SMALL)
        self.vol_lbl.pack(side=tk.RIGHT, padx=4)
        self.vol = ttk.Scale(vol_row, from_=0, to=100,
                             orient=tk.HORIZONTAL, value=theme.get_volume(),
                             command=self._on_vol, style="UH.Horizontal.TScale")
        self.vol.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        ttk.Separator(body).pack(fill=tk.X, pady=10)

        tk.Label(body, text="系统", bg=BG, fg=MUTED,
                 font=FONT_SMALL).pack(anchor=tk.W, pady=(2, 4))
        ttk.Button(body, text="退出程序", command=self._exit,
                   style="UH.Danger.TButton").pack(fill=tk.X, pady=3)

    def _mark(self, cur):
        try:
            if cur == "light":
                self.btn_light.configure(text="亮色  ✓")
                self.btn_dark.configure(text="暗色")
            else:
                self.btn_dark.configure(text="暗色  ✓")
                self.btn_light.configure(text="亮色")
        except Exception:
            pass

    def _on_vol(self, v):
        iv = int(float(v))
        theme.set_volume(iv)
        self.vol_lbl.config(text=f"{iv}%")
        # 若当前有音频在播放（同进程 pygame.mixer），实时生效
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.set_volume(iv / 100.0)
        except Exception:
            pass

    def _choose(self, name):
        theme.set_theme(name)
        self._mark(name)
        # 重启进程，让桌面与所有组件按新主题重建
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def _exit(self):
        try:
            self.master.destroy()
        finally:
            os._exit(0)

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
        s.configure("UH.Danger.TButton", background=DANGER, foreground="#ffffff",
                    font=FONT_NORMAL, borderwidth=0,
                    padding=(2, 2) if BOARD else 6)
        s.map("UH.Danger.TButton", background=[("active", "#b00020")])
        s.configure("UH.Horizontal.TScale", background=SURFACE2,
                    troughcolor=SURFACE2, borderwidth=0)


def main():
    root = tk.Tk()
    Launcher(root, fullscreen="--full" in sys.argv, board=_BOARD)
    root.mainloop()


if __name__ == "__main__":
    main()
