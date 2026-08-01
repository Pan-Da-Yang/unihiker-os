# -*- coding: utf-8 -*-
"""
行空板 OS - 图片查看器
功能：打开图片、自适应缩放、上一张/下一张、放大缩小、旋转、适应窗口。
可从文件夹批量浏览（由文件管理器传入同目录图片列表）。
"""
import os
import tkinter as tk
from tkinter import ttk, messagebox

import theme
from theme import (
    BG, SURFACE, SURFACE2, ACCENT, ACCENT2, TEXT, MUTED,
    FONT_NORMAL, FONT_SMALL, is_image, BOARD, apply_board_window,
    setup_board_button,
)

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False


class ImageViewer(tk.Toplevel):
    def __init__(self, master, path, image_list=None, index=0):
        super().__init__(master)
        self.title("行空图片查看器")
        self.configure(bg=BG)
        self.geometry(f"{theme.BOARD_W if BOARD else theme.WIN_W}x"
                      f"{theme.BOARD_H if BOARD else theme.WIN_H}")
        apply_board_window(self)
        self.master = master

        self.dir_path = os.path.dirname(os.path.abspath(path))
        if image_list is None:
            self.images = sorted(
                f for f in os.listdir(self.dir_path) if is_image(f)
            )
            self.index = self.images.index(os.path.basename(path)) \
                if os.path.basename(path) in self.images else 0
        else:
            self.images = [os.path.basename(p) for p in image_list]
            self.index = index
            self.dir_path = os.path.dirname(os.path.abspath(image_list[index])) \
                if image_list else self.dir_path

        self.zoom = 1.0
        self.angle = 0
        self._pil = None
        self._photo = None

        self._build_ui()
        setup_board_button(self)
        self._show()
        self.canvas.bind("<Configure>", lambda e: self._show())

    def _build_ui(self):
        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill=tk.X)

        px = 2 if BOARD else 4
        py = 4 if BOARD else 6
        # 第一行：返回 + 切图（最重要的三个，保证小屏不溢出）
        row1 = tk.Frame(bar, bg=SURFACE)
        row1.pack(fill=tk.X)
        ttk.Button(row1, text="返回", command=lambda: self.destroy(),
                   style="UH.Danger.TButton").pack(side=tk.LEFT, padx=px, pady=py)
        ttk.Button(row1, text="上一", command=self._prev,
                   style="UH.TButton").pack(side=tk.LEFT, padx=px, pady=py)
        ttk.Button(row1, text="下一", command=self._next,
                   style="UH.TButton").pack(side=tk.LEFT, padx=px, pady=py)

        # 第二行：缩放旋转（小屏可折行，不会被挤掉返回）
        row2 = tk.Frame(bar, bg=SURFACE)
        row2.pack(fill=tk.X)
        ttk.Button(row2, text="放大", command=lambda: self._zoom(1.2),
                   style="UH.TButton").pack(side=tk.LEFT, padx=px, pady=py)
        ttk.Button(row2, text="缩小", command=lambda: self._zoom(1/1.2),
                   style="UH.TButton").pack(side=tk.LEFT, padx=px, pady=py)
        ttk.Button(row2, text="旋转", command=self._rotate,
                   style="UH.TButton").pack(side=tk.LEFT, padx=px, pady=py)
        ttk.Button(row2, text="适应", command=self._fit,
                   style="UH.TButton").pack(side=tk.LEFT, padx=px, pady=py)

        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.status = tk.Label(self, text="", bg=SURFACE, fg=MUTED,
                               font=FONT_SMALL, anchor=tk.W)
        self.status.pack(fill=tk.X, padx=4, pady=2)

        # 键盘快捷键
        self.bind("<Left>", lambda e: self._prev())
        self.bind("<Right>", lambda e: self._next())
        self.bind("<plus>", lambda e: self._zoom(1.2))
        self.bind("<minus>", lambda e: self._zoom(1/1.2))
        self.bind("<r>", lambda e: self._rotate())
        self.bind("<Escape>", lambda e: self.destroy())

        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("UH.TButton", background=ACCENT, foreground=theme.ON_ACCENT,
                    font=FONT_NORMAL, borderwidth=0,
                    padding=(2, 2) if BOARD else 6)
        s.map("UH.TButton", background=[("active", ACCENT2)])
        s.configure("UH.Danger.TButton", background="#ef476f", foreground="#fff",
                    font=FONT_NORMAL, borderwidth=0,
                    padding=(2, 2) if BOARD else 6)
        s.map("UH.Danger.TButton", background=[("active", "#c9184a")])

    # ---------------- 显示 ----------------
    def _show(self):
        if not PIL_OK:
            self.status.config(text="未安装 Pillow，无法显示图片")
            return
        if not self.images:
            self.status.config(text="该目录没有可显示的图片")
            return
        name = self.images[self.index]
        full = os.path.join(self.dir_path, name)
        try:
            img = Image.open(full).convert("RGB")
        except Exception as e:
            messagebox.showerror("打开失败", f"{name}\n{e}")
            return
        if self.angle:
            img = img.rotate(self.angle, expand=True)
        self._pil = img
        self._draw()

    def _draw(self):
        img = self._pil
        if img is None:
            return
        cw = self.canvas.winfo_width() or theme.WIN_W
        ch = self.canvas.winfo_height() or theme.WIN_H
        base = min(cw / img.width, ch / img.height)
        scale = base * self.zoom
        new_w = max(1, int(img.width * scale))
        new_h = max(1, int(img.height * scale))
        disp = img.resize((new_w, new_h), Image.LANCZOS)
        try:
            self._photo = ImageTk.PhotoImage(disp)
        except Exception as e:
            self.status.config(text=f"图像显示失败：{e}")
            return
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo,
                                 anchor=tk.CENTER)
        total = len(self.images)
        short = self.images[self.index]
        if len(short) > 16:
            short = short[:13] + "..."
        self.status.config(
            text=f"{self.index + 1}/{total} · {short} · {self.zoom:.0%}")

    # ---------------- 控制 ----------------
    def _prev(self):
        if not self.images:
            return
        self.index = (self.index - 1) % len(self.images)
        self._show()

    def _next(self):
        if not self.images:
            return
        self.index = (self.index + 1) % len(self.images)
        self._show()

    def _zoom(self, factor):
        self.zoom = max(0.1, min(8.0, self.zoom * factor))
        self._draw()

    def _rotate(self):
        self.angle = (self.angle + 90) % 360
        self._show()

    def _fit(self):
        self.zoom = 1.0
        self._draw()


if __name__ == "__main__":
    import sys
    root = tk.Tk()
    root.withdraw()
    start = sys.argv[1] if len(sys.argv) > 1 else __file__
    if not os.path.isfile(start):
        start = os.getcwd()
    ImageViewer(root, start)
    root.mainloop()
