# -*- coding: utf-8 -*-
"""
行空板 OS - 编曲（步进音序器）
  · 8 个音符（C 大调五声音阶，低→高）× 8 步 的网格，点格子开关音。
  · ▶播放 / ⏹停止 / 清除 / 示例 / 速度(60–240 BPM)。
  · 板子走 P0 蜂鸣器发声（单声道，每步取该列最高音）；开发机用 pygame 回退。
  · 无硬件时仅可视化，不崩溃。
"""
import tkinter as tk
from tkinter import ttk, messagebox

import theme
from theme import (
    BG, SURFACE, SURFACE2, HOVER, ACCENT, ACCENT2, DANGER, TEXT, MUTED,
    ON_ACCENT, FONT_NORMAL, FONT_SMALL, BOARD, apply_board_window,
)
import hwio

# 8 个音符（音名, 频率Hz），低→高
_NOTES = [
    ("E5", 659), ("D5", 587), ("C5", 523), ("A4", 440),
    ("G4", 392), ("E4", 330), ("D4", 294), ("C4", 262),
]
_STEPS = 8


class Composer(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("编曲")
        self.configure(bg=BG)
        apply_board_window(self)
        self.master = master

        self.hw = hwio.ensure_hw()
        self.cells = [[False] * _STEPS for _ in range(len(_NOTES))]
        self.bpm = 120
        self.playing = False
        self._step = 0
        self._play_id = None
        self._after_ids = set()

        # 网格画布尺寸（板子压缩，开发机大一些便于编辑）
        if BOARD:
            self.cw, self.ch = 228, 196
        else:
            self.cw, self.ch = 380, 300

        self._build_ui()
        self._bind_board_key()
        if not self.hw:
            self.hw_lbl.config(text="无硬件(静音)")
        self._draw()

    # ============ UI ============
    def _build_ui(self):
        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill=tk.X)
        px = 2 if BOARD else 4
        ttk.Button(bar, text="返回", command=lambda: self.destroy(),
                   style="UH.Danger.TButton").pack(side=tk.LEFT, padx=px, pady=4)
        tk.Label(bar, text="编曲", bg=SURFACE, fg=TEXT,
                 font=FONT_NORMAL).pack(side=tk.LEFT, padx=2)
        self.bpm_lbl = tk.Label(bar, text="120 BPM", bg=SURFACE, fg=ACCENT2,
                                font=FONT_SMALL, anchor=tk.E)
        self.bpm_lbl.pack(side=tk.RIGHT, padx=4)
        self.hw_lbl = tk.Label(bar, text="", bg=SURFACE, fg=MUTED,
                               font=FONT_SMALL, anchor=tk.E)
        self.hw_lbl.pack(side=tk.RIGHT, padx=2)

        # 网格画布
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0,
                                width=self.cw, height=self.ch)
        self.canvas.pack(pady=(4, 2))
        self.canvas.bind("<Button-1>", self._on_tap)

        # 控制栏
        ctl = tk.Frame(self, bg=BG)
        ctl.pack(fill=tk.X, pady=2)
        ttk.Button(ctl, text="▶", width=3, command=self._play,
                   style="UH.TButton").pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ttk.Button(ctl, text="⏹", width=3, command=self._stop,
                   style="UH.Danger.TButton").pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ttk.Button(ctl, text="清除", width=4, command=self._clear,
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ttk.Button(ctl, text="示例", width=4, command=self._demo,
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)

        # 速度栏
        spd = tk.Frame(self, bg=BG)
        spd.pack(fill=tk.X, pady=2)
        ttk.Button(spd, text="慢", width=4, command=lambda: self._bpm(-20),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        tk.Label(spd, text="速度", bg=BG, fg=MUTED,
                 font=FONT_SMALL).pack(side=tk.LEFT, padx=2)
        ttk.Button(spd, text="快", width=4, command=lambda: self._bpm(20),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)

        self._style()

    # ============ 绘制网格 ============
    def _draw(self, highlight_col=None):
        cw, ch = self.cw, self.ch
        n = len(_NOTES)
        cell_w = cw // _STEPS
        cell_h = ch // n
        self.canvas.delete("all")
        # 音符色：低→高 由蓝紫渐变到橙红
        import colorsys
        for r in range(n):
            _, freq = _NOTES[r]
            # 用音高做色相
            hue = 0.62 - (r / max(1, n - 1)) * 0.6  # 0.62(蓝)→0.02(红)
            rgb = colorsys.hsv_to_rgb(hue, 0.55, 0.95)
            col = "#%02x%02x%02x" % tuple(int(255 * c) for c in rgb)
            for c in range(_STEPS):
                x0, y0 = c * cell_w, r * cell_h
                x1, y1 = x0 + cell_w, y0 + cell_h
                if self.cells[r][c]:
                    self.canvas.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1,
                                                  fill=col, outline="")
                else:
                    self.canvas.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1,
                                                  fill=SURFACE2, outline="")
        # 网格线
        for c in range(_STEPS + 1):
            self.canvas.create_line(c * cell_w, 0, c * cell_w, ch,
                                    fill=MUTED, width=1)
        for r in range(n + 1):
            self.canvas.create_line(0, r * cell_h, cw, r * cell_h,
                                    fill=MUTED, width=1)
        # 当前播放列高亮
        if highlight_col is not None:
            x0 = highlight_col * cell_w
            self.canvas.create_rectangle(x0, 0, x0 + cell_w, ch,
                                         outline=ACCENT2, width=2)

    def _on_tap(self, ev):
        if self.playing:
            return
        n = len(_NOTES)
        cell_w = self.cw // _STEPS
        cell_h = self.ch // n
        c = ev.x // cell_w
        r = ev.y // cell_h
        if 0 <= r < n and 0 <= c < _STEPS:
            self.cells[r][c] = not self.cells[r][c]
            self._draw()

    # ============ 播放控制 ============
    def _step_ms(self):
        return max(80, 60000 // self.bpm)

    def _play(self):
        if self.playing:
            return
        self.playing = True
        self._step = 0
        self._tick()

    def _tick(self):
        if not self.playing or not self.winfo_exists():
            return
        col = self._step
        self._draw(highlight_col=col)
        # 单声道：取该列最高音（最靠上）
        freq = None
        for r in range(len(_NOTES) - 1, -1, -1):
            if self.cells[r][col]:
                freq = _NOTES[r][1]
                break
        if freq is not None:
            hwio.tone(freq)
            aid = self.after(self._step_ms() - 20, hwio.tone_stop)
            self._after_ids.add(aid)
        self._step = (col + 1) % _STEPS
        self._play_id = self.after(self._step_ms(), self._tick)

    def _stop(self):
        self.playing = False
        hwio.tone_stop()
        if self._play_id is not None:
            try:
                self.after_cancel(self._play_id)
            except Exception:
                pass
            self._play_id = None
        self._draw()

    def _clear(self):
        self._stop()
        self.cells = [[False] * _STEPS for _ in range(len(_NOTES))]
        self._draw()

    def _demo(self):
        """载入一段示例旋律（小星星前两句简化：C C G G A A G），方便上手。"""
        self._stop()
        self.cells = [[False] * _STEPS for _ in range(len(_NOTES))]
        # 行索引：0=E5 1=D5 2=C5 3=A4 4=G4 5=E4 6=D4 7=C4
        # 1 1 5 5 6 6 5 -（C C G G A A G）
        seq = [(7, 0), (7, 1), (4, 2), (4, 3), (5, 4), (5, 5), (6, 6)]
        for r, c in seq:
            self.cells[r][c] = True
        self._draw()

    def _bpm(self, d):
        self.bpm = max(60, min(240, self.bpm + d))
        self.bpm_lbl.config(text="%d BPM" % self.bpm)

    # ============ 板载 A 键停止 ============
    def _bind_board_key(self):
        if not self.hw:
            return
        hwio.bind_a(self._on_a)

    def _on_a(self, pin):
        try:
            if self.winfo_exists():
                self.after(0, self._stop)
                self.after(0, lambda: self.destroy())
        except Exception:
            pass

    # ============ 样式 ============
    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("UH.TButton", background=ACCENT, foreground=ON_ACCENT,
                    font=FONT_NORMAL, borderwidth=0, width=4,
                    padding=(2, 2) if BOARD else 6)
        s.map("UH.TButton", background=[("active", ACCENT2)])
        s.configure("UH.Danger.TButton", background=DANGER, foreground="#ffffff",
                    font=FONT_NORMAL, borderwidth=0, width=4,
                    padding=(2, 2) if BOARD else 6)
        s.map("UH.Danger.TButton", background=[("active", "#b00020")])
        s.configure("UH.Num.TButton", background=SURFACE2, foreground=TEXT,
                    font=FONT_SMALL, borderwidth=0, width=4,
                    padding=(2, 2) if BOARD else 6)
        s.map("UH.Num.TButton", background=[("active", HOVER)])


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    Composer(root)
    root.mainloop()
