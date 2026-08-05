# -*- coding: utf-8 -*-
"""
行空板 OS - 相机功能
- 实时预览 USB / 板载摄像头画面
- 拍照保存到 photos/ 目录
- 开发机无摄像头时降级显示占位提示，不崩溃
"""

import os
import time
import tkinter as tk
from tkinter import ttk

import theme
from theme import (
    BG, SURFACE, SURFACE2, ACCENT, ACCENT2, DANGER, TEXT, MUTED, ON_ACCENT,
    FONT_TITLE, FONT_NORMAL, FONT_SMALL, BOARD, BOARD_W, BOARD_H,
    apply_board_window, setup_board_button,
)

# 照片保存目录
_PHOTO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos")


class CameraApp:
    """相机预览与拍照。"""

    def __init__(self, master):
        self.master = master
        self.win = tk.Toplevel(master)
        self.win.title("相机")
        self.win.configure(bg=BG)

        if BOARD:
            apply_board_window(self.win)
        else:
            self.win.geometry("420x560")
            self.win.resizable(False, False)

        setup_board_button(self.win)

        self.cap = None
        self.cv2 = None
        self.running = False
        self.panel = None
        self._last_photo = None

        self._build_ui()
        self._init_camera()

    # ---------------- 初始化 ----------------
    def _init_camera(self):
        """尝试打开摄像头。失败则降级提示。"""
        try:
            import cv2
            from PIL import Image, ImageTk
            self.cv2 = cv2
            self._ImageTk = ImageTk
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                raise RuntimeError("摄像头打不开（设备不存在或无权限）")
            self.running = True
            self.status.config(text="就绪")
            self._update()
        except Exception as e:
            self.running = False
            self.status.config(text="⚠ 无摄像头 (开发机)", fg=DANGER)
            # 占位画面
            try:
                self.panel.config(text="[ 无摄像头 ]\n连接 USB 摄像头后重试",
                                  fg=MUTED, font=FONT_NORMAL,
                                  justify=tk.CENTER)
            except Exception:
                pass
            print(f"[camera] 初始化失败：{e}")

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = theme.board_padding()
        # 顶栏
        bar = tk.Frame(self.win, bg=SURFACE)
        bar.pack(fill=tk.X)
        tk.Label(bar, text="相机", bg=SURFACE, fg=ACCENT,
                 font=FONT_TITLE).pack(side=tk.LEFT, padx=pad, pady=6)
        ttk.Button(bar, text="返回", command=self._quit,
                   style="UH.TButton").pack(side=tk.RIGHT, padx=pad, pady=4)

        # 预览区
        self.panel = tk.Label(self.win, bg="black")
        self.panel.pack(fill=tk.BOTH, expand=True, padx=pad, pady=4)

        # 底栏
        bot = tk.Frame(self.win, bg=BG)
        bot.pack(fill=tk.X, pady=4)
        ttk.Button(bot, text="拍照", command=self._capture,
                   style="UH.TButton", width=10).pack(side=tk.LEFT, padx=4)
        ttk.Button(bot, text="查看", command=self._view_last,
                   style="UH.TButton", width=8).pack(side=tk.LEFT, padx=2)
        self.status = tk.Label(bot, text="初始化…", bg=BG, fg=MUTED,
                               font=FONT_SMALL)
        self.status.pack(side=tk.RIGHT, padx=4)

        self._style()

    def _update(self):
        """预览循环：每 30ms 抓取一帧并显示。"""
        if not self.running or self.cap is None:
            return
        try:
            ret, frame = self.cap.read()
            if ret:
                h, w = frame.shape[:2]
                target_w = BOARD_W if BOARD else 380
                scale = target_w / float(w)
                dim = (target_w, int(h * scale))
                frame = self.cv2.resize(frame, dim,
                                        interpolation=self.cv2.INTER_AREA)
                frame = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
                from PIL import Image
                img = Image.fromarray(frame)
                imgtk = self._ImageTk.PhotoImage(image=img)
                self.panel.imgtk = imgtk
                self.panel.configure(image=imgtk, text="")
        except Exception as e:
            print(f"[camera] 预览异常：{e}")
        if self.running:
            self.win.after(30, self._update)

    def _capture(self):
        """拍照并保存当前帧（BGR 原图，非预览缩放图）。"""
        if self.cap is None or not self.cap.isOpened():
            self.status.config(text="⚠ 无摄像头", fg=DANGER)
            return
        try:
            ret, frame = self.cap.read()
            if not ret:
                self.status.config(text="⚠ 抓取失败", fg=DANGER)
                return
            os.makedirs(_PHOTO_DIR, exist_ok=True)
            fn = os.path.join(_PHOTO_DIR, f"photo_{int(time.time())}.jpg")
            self.cv2.imwrite(fn, frame)
            self._last_photo = fn
            self.status.config(text=f"已保存 {os.path.basename(fn)}", fg=ACCENT)
        except Exception as e:
            self.status.config(text="保存失败", fg=DANGER)
            print(f"[camera] 保存失败：{e}")

    def _view_last(self):
        """用图片查看器打开最近一张照片。"""
        if not self._last_photo or not os.path.exists(self._last_photo):
            self.status.config(text="暂无照片", fg=MUTED)
            return
        try:
            import imageviewer
            imageviewer.ImageViewer(self.win, self._last_photo)
        except Exception as e:
            print(f"[camera] 打开照片失败：{e}")

    def _quit(self):
        self.running = False
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
        self.win.destroy()

    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass
        pp = (2, 2) if BOARD else 6
        s.configure("UH.TButton", background=ACCENT, foreground=ON_ACCENT,
                    font=FONT_NORMAL, borderwidth=0, padding=pp, width=8)
        s.map("UH.TButton", background=[("active", ACCENT2)])
