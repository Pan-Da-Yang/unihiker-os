# -*- coding: utf-8 -*-
"""
行空板 OS - 视频播放器
基于 OpenCV(cv2) 逐帧读取 + tkinter Canvas 显示。
功能：播放 / 暂停 / 停止、进度条拖动定位、帧率同步、画面自适应。
注意：本播放器只渲染视频画面，不输出声音。
"""
import os
import time
import tkinter as tk
from tkinter import ttk, messagebox

import theme
from theme import (
    BG, SURFACE, SURFACE2, ACCENT, ACCENT2, TEXT, MUTED,
    FONT_NORMAL, FONT_SMALL, BOARD, apply_board_window, setup_board_button,
)

try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False


class VideoPlayer(tk.Toplevel):
    def __init__(self, master, path):
        super().__init__(master)
        self.title("行空视频播放器")
        self.configure(bg=BG)
        self.geometry(f"{theme.BOARD_W if BOARD else theme.WIN_W}x"
                      f"{theme.BOARD_H if BOARD else theme.WIN_H}")
        apply_board_window(self)
        self.master = master

        self.path = os.path.abspath(path)
        self.cap = None
        self.playing = False
        self._job = None          # after 任务 id，用于取消播放循环
        self.current_frame = 0
        self.total_frames = 0
        self.fps = 25.0
        self._photo = None
        self._seeking = False

        self._build_ui()
        setup_board_button(self)

        if not (CV2_OK and PIL_OK):
            self.status.config(text="缺少 OpenCV / Pillow，无法播放（请先安装依赖）")
            for b in (self.btn_play, self.btn_stop):
                b.configure(state=tk.DISABLED)
            return

        try:
            # 行空板等 ARM 小板上，FFmpeg 多线程解码极易触发
            # libavcodec/pthread_frame.c 断言崩溃；强制单线程可显著降低概率。
            cv2.setNumThreads(1)
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "threads|1"
            self.cap = cv2.VideoCapture(self.path, cv2.CAP_FFMPEG)
        except Exception as e:
            self.status.config(text=f"无法打开视频：{e}")
            return
        if not self.cap.isOpened():
            self.status.config(text="无法打开视频文件（格式/解码器不支持）")
            return
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.slider.configure(to=max(1, self.total_frames - 1))
        self._draw_current_frame()

    # ---------------- UI ----------------
    def _build_ui(self):
        self.canvas = tk.Canvas(self, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        ctrl = tk.Frame(self, bg=SURFACE)
        ctrl.pack(fill=tk.X)

        px = 2 if BOARD else 6
        py = 4 if BOARD else 8

        # 第一行：返回 + 播放控制（小屏优先保证返回可见）
        row1 = tk.Frame(ctrl, bg=SURFACE)
        row1.pack(fill=tk.X)
        ttk.Button(row1, text="返回", command=self._on_close,
                   style="UH.Danger.TButton").pack(side=tk.LEFT, padx=px, pady=py)
        self.btn_play = ttk.Button(row1, text="播放", command=self._toggle,
                                   style="UH.TButton")
        self.btn_play.pack(side=tk.LEFT, padx=px, pady=py)
        self.btn_stop = ttk.Button(row1, text="停止", command=self._stop,
                                   style="UH.TButton")
        self.btn_stop.pack(side=tk.LEFT, padx=px, pady=py)
        self.time_lbl = tk.Label(row1, text="00:00 / 00:00", bg=SURFACE,
                                 fg=TEXT, font=FONT_SMALL)
        self.time_lbl.pack(side=tk.LEFT, padx=4)

        # 第二行：进度条
        row2 = tk.Frame(ctrl, bg=SURFACE)
        row2.pack(fill=tk.X)
        self.slider = ttk.Scale(row2, from_=0, to=100, orient=tk.HORIZONTAL,
                                command=self._on_seek, style="UH.Horizontal.TScale")
        self.slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=px, pady=py)
        self.slider.bind("<ButtonPress-1>", self._seek_start)
        self.slider.bind("<ButtonRelease-1>", self._seek_release)

        self.status = tk.Label(self, text=os.path.basename(self.path),
                               bg=SURFACE2, fg=MUTED, font=FONT_SMALL,
                               anchor=tk.W)
        self.status.pack(fill=tk.X, padx=4, pady=2)

        self.bind("<space>", lambda e: self._toggle())
        self.bind("<Escape>", lambda e: self._on_close())
        self.canvas.bind("<Configure>", lambda e: self._draw_current_frame())

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
        s.configure("UH.Horizontal.TScale", background=SURFACE2,
                    troughcolor=SURFACE2, borderwidth=0)
        s.configure("Horizontal.TScale", background=SURFACE2)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- 播放控制 ----------------
    def _toggle(self):
        if not self.cap or not self.cap.isOpened():
            return
        if self.playing:
            self._pause()
        else:
            self._play()

    def _play(self):
        if self.current_frame >= self.total_frames - 1:
            self.current_frame = 0
            if self.cap:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.playing = True
        self.btn_play.configure(text="暂停")
        self._tick()

    def _pause(self):
        self.playing = False
        self.btn_play.configure(text="播放")
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _stop(self):
        self._pause()
        self.current_frame = 0
        if self.cap:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self._draw_current_frame()
        self._update_time()

    def _tick(self):
        """主线程逐帧读取并渲染（替代后台线程，避免 cv2.VideoCapture
        并发访问导致 libavcodec/pthread_frame 断言崩溃）。"""
        if not self.playing or not self.cap or not self.cap.isOpened():
            return
        if self._seeking:
            # 拖动进度条时暂停读取，避免与 seek 操作冲突
            self._job = self.after(20, self._tick)
            return
        t0 = time.time()
        ret, frame = self.cap.read()
        if not ret:
            self.playing = False
            self.btn_play.configure(text="播放")
            return
        self.current_frame += 1
        self._render(frame)
        self._update_progress()
        elapsed = time.time() - t0
        delay_ms = max(1, int(1000.0 / self.fps - elapsed * 1000))
        self._job = self.after(delay_ms, self._tick)

    def _render(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        cw = self.canvas.winfo_width() or theme.WIN_W
        ch = self.canvas.winfo_height() or theme.WIN_H
        scale = min(cw / img.width, ch / img.height)
        if scale > 0 and scale != 1:
            img = img.resize((max(1, int(img.width * scale)),
                              max(1, int(img.height * scale))), Image.LANCZOS)
        try:
            self._photo = ImageTk.PhotoImage(img)
        except Exception as e:
            self.status.config(text=f"画面显示失败：{e}")
            return
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo,
                                 anchor=tk.CENTER)

    def _draw_current_frame(self):
        if not (CV2_OK and PIL_OK and self.cap and self.cap.isOpened()):
            return
        was_open = self.cap.isOpened()
        pos = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
        ret, frame = self.cap.read()
        if ret:
            self._render(frame)
        if was_open:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, pos)

    def _update_progress(self):
        if self._seeking:
            return
        self.slider.set(self.current_frame)
        self._update_time()

    def _update_time(self):
        cur = self.current_frame / self.fps if self.fps else 0
        tot = self.total_frames / self.fps if self.fps else 0
        self.time_lbl.config(text=f"{self._fmt(cur)} / {self._fmt(tot)}")

    @staticmethod
    def _fmt(sec):
        sec = int(sec)
        m, s = divmod(sec, 60)
        return f"{m:02d}:{s:02d}"

    # ---------------- 进度条拖动 ----------------
    def _seek_start(self, _):
        self._seeking = True
        self._pause()          # seek 前先取消播放循环，避免并发读写 cap

    def _seek_release(self, _):
        val = int(self.slider.get())
        self.current_frame = val
        if self.cap:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, val)
        self._draw_current_frame()
        self._update_time()
        self._seeking = False
        # seek 后不自动播放，用户按播放键继续，最安全

    def _on_seek(self, _):
        pass

    def _on_close(self):
        self._pause()
        if self.cap:
            self.cap.release()
        self.destroy()

    def destroy(self):
        self._pause()
        try:
            if self.cap:
                self.cap.release()
        except Exception:
            pass
        super().destroy()


if __name__ == "__main__":
    import sys
    root = tk.Tk()
    root.withdraw()
    start = sys.argv[1] if len(sys.argv) > 1 else None
    if not start or not os.path.isfile(start):
        messagebox.showerror("用法", "python videoplayer.py <视频文件路径>")
    else:
        VideoPlayer(root, start)
        root.mainloop()
