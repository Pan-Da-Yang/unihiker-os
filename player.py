# -*- coding: utf-8 -*-
"""
行空板 OS - 音乐播放器（曲库播放）
  · 内置多首经典旋律（小星星 / 欢乐颂 / 生日歌 / 两只老虎 / 玛丽有只小羊羔）。
  · 通过 P0 扬声器发声（与「编曲」共用 hwio.tone：板子走蜂鸣器重定向到 P0，
    你接了外接扬声器，音量更大；开发机用 pygame 回退合成）。
  · 播放 / 暂停 / 上一首 / 下一首 / 进度 / 调速，配色跟随 theme。
  · 与「编曲」区分：本 App 是“播放”预设曲目；编曲是“创作”。
"""
import tkinter as tk
from tkinter import ttk

import theme
from theme import (
    BG, SURFACE, SURFACE2, HOVER, ACCENT, ACCENT2, DANGER, TEXT, MUTED,
    ON_ACCENT, FONT_NORMAL, FONT_SMALL, BOARD, apply_board_window,
)
import hwio
import composer

# 音名 -> 频率(Hz)
_FREQ = {
    "C4": 262, "D4": 294, "E4": 330, "F4": 349, "G4": 392, "A4": 440, "B4": 494,
    "C5": 523, "D5": 587, "E5": 659, "F5": 698, "G5": 784, "A5": 880, "B5": 988,
    "C6": 1047,
    "R": 0,  # 休止符
}

# 曲库：(标题, [(音名, 拍数), ...])
_SONGS = [
    ("小星星", [
        ("C4", 1), ("C4", 1), ("G4", 1), ("G4", 1), ("A4", 1), ("A4", 1), ("G4", 2),
        ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 1), ("D4", 1), ("C4", 2),
        ("G4", 1), ("G4", 1), ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 2),
        ("G4", 1), ("G4", 1), ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 2),
        ("C4", 1), ("C4", 1), ("G4", 1), ("G4", 1), ("A4", 1), ("A4", 1), ("G4", 2),
        ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 1), ("D4", 1), ("C4", 2),
    ]),
    ("欢乐颂", [
        ("E4", 1), ("E4", 1), ("F4", 1), ("G4", 1),
        ("G4", 1), ("F4", 1), ("E4", 1), ("D4", 1),
        ("C4", 1), ("C4", 1), ("D4", 1), ("E4", 1),
        ("E4", 1.5), ("D4", 0.5), ("D4", 2),
        ("E4", 1), ("E4", 1), ("F4", 1), ("G4", 1),
        ("G4", 1), ("F4", 1), ("E4", 1), ("D4", 1),
        ("C4", 1), ("C4", 1), ("D4", 1), ("E4", 1),
        ("D4", 1.5), ("C4", 0.5), ("C4", 2),
    ]),
    ("生日歌", [
        ("C4", 0.75), ("C4", 0.25), ("D4", 1), ("C4", 1), ("F4", 2), ("E4", 2),
        ("C4", 0.75), ("C4", 0.25), ("D4", 1), ("C4", 1), ("G4", 2), ("F4", 2),
        ("C4", 0.75), ("C4", 0.25), ("C5", 1), ("A4", 1), ("F4", 1), ("E4", 1), ("D4", 2),
        ("B4", 0.75), ("B4", 0.25), ("A4", 1), ("F4", 1), ("G4", 2), ("F4", 2),
    ]),
    ("两只老虎", [
        ("C4", 1), ("D4", 1), ("E4", 1), ("C4", 1),
        ("C4", 1), ("D4", 1), ("E4", 1), ("C4", 1),
        ("E4", 1), ("F4", 1), ("G4", 2),
        ("E4", 1), ("F4", 1), ("G4", 2),
        ("G4", 0.75), ("A4", 0.25), ("G4", 0.75), ("A4", 0.25), ("C5", 2),
        ("G4", 0.75), ("A4", 0.25), ("G4", 0.75), ("A4", 0.25), ("C5", 2),
        ("C5", 1), ("G4", 1), ("C4", 2),
        ("C5", 1), ("G4", 1), ("C4", 2),
    ]),
    ("玛丽有只小羊羔", [
        ("E4", 1), ("D4", 1), ("C4", 1), ("D4", 1),
        ("E4", 1), ("E4", 1), ("E4", 2),
        ("D4", 1), ("D4", 1), ("D4", 2),
        ("E4", 1), ("G4", 1), ("G4", 2),
        ("E4", 1), ("D4", 1), ("C4", 1), ("D4", 1),
        ("E4", 1), ("E4", 1), ("E4", 1), ("E4", 1),
        ("D4", 1), ("D4", 1), ("E4", 1), ("D4", 1),
        ("C4", 4),
    ]),
]


class MusicPlayer(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("音乐")
        self.configure(bg=BG)
        apply_board_window(self)
        self.master = master

        self.hw = hwio.ensure_hw()
        self.songs = _SONGS
        self.idx = 0
        self.cur = 0
        self.playing = False
        self.beat_ms = 400  # 每拍毫秒（≈150 BPM）
        self._after_id = None

        self._build_ui()
        self._bind_board_key()
        if not self.hw:
            self.hw_lbl.config(text="无硬件(静音)")
        self._update_title()
        self._progress()

    # ============ UI ============
    def _build_ui(self):
        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill=tk.X)
        px = 2 if BOARD else 4
        ttk.Button(bar, text="返回", command=self._on_close,
                   style="UH.Danger.TButton").pack(side=tk.LEFT, padx=px, pady=4)
        tk.Label(bar, text="音乐", bg=SURFACE, fg=TEXT,
                 font=FONT_NORMAL).pack(side=tk.LEFT, padx=2)
        self.hw_lbl = tk.Label(bar, text="P0 扬声器", bg=SURFACE, fg=ACCENT2,
                               font=FONT_SMALL, anchor=tk.E)
        self.hw_lbl.pack(side=tk.RIGHT, padx=4)

        # 曲库列表
        lib = tk.Frame(self, bg=BG)
        lib.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        tk.Label(lib, text="曲库", bg=BG, fg=MUTED,
                 font=FONT_SMALL, anchor=tk.W).pack(fill=tk.X)
        self.lst = tk.Listbox(lib, bg=SURFACE, fg=TEXT,
                               selectbackground=ACCENT, selectforeground=ON_ACCENT,
                               font=FONT_NORMAL, relief=tk.FLAT,
                               highlightthickness=0,
                               height=6 if BOARD else 12)
        self.lst.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        sb = ttk.Scrollbar(lib, orient=tk.VERTICAL, command=self.lst.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.lst.config(yscrollcommand=sb.set)
        for title, _ in self.songs:
            self.lst.insert(tk.END, title)
        self.lst.bind("<<ListboxSelect>>", self._on_list_select)

        # 当前歌曲 + 进度
        info = tk.Frame(self, bg=BG)
        info.pack(fill=tk.X, pady=2)
        self.cur_lbl = tk.Label(info, text="", bg=BG, fg=TEXT,
                                font=FONT_NORMAL, anchor=tk.W)
        self.cur_lbl.pack(fill=tk.X, padx=4)
        self.bar = ttk.Progressbar(info, orient=tk.HORIZONTAL,
                                   mode="determinate", length=100)
        self.bar.pack(fill=tk.X, padx=4, pady=2)

        # 控制栏
        ctl = tk.Frame(self, bg=BG)
        ctl.pack(fill=tk.X, pady=2)
        ttk.Button(ctl, text="⏮", width=3, command=self._prev,
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2,
                                                expand=True, fill=tk.X)
        self.play_btn = ttk.Button(ctl, text="▶", width=3, command=self._toggle,
                                   style="UH.TButton")
        self.play_btn.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ttk.Button(ctl, text="⏭", width=3, command=self._next,
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2,
                                                expand=True, fill=tk.X)

        # 速度 + 编曲入口
        spd = tk.Frame(self, bg=BG)
        spd.pack(fill=tk.X, pady=2)
        ttk.Button(spd, text="慢", width=4, command=lambda: self._bpm(-40),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2,
                                                expand=True, fill=tk.X)
        self.bpm_lbl = tk.Label(spd, text="150 BPM", bg=BG, fg=MUTED,
                                font=FONT_SMALL)
        self.bpm_lbl.pack(side=tk.LEFT, padx=2)
        ttk.Button(spd, text="快", width=4, command=lambda: self._bpm(40),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2,
                                                expand=True, fill=tk.X)
        ttk.Button(self, text="去编曲 →", command=self._open_composer,
                   style="UH.Num.TButton").pack(fill=tk.X, padx=4, pady=(2, 4))

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._style()

    # ============ 播放控制 ============
    def _advance(self):
        if not self.playing or not self.winfo_exists():
            return
        song = self.songs[self.idx][1]
        if self.cur >= len(song):
            self._next(auto=True)
            return
        note, beats = song[self.cur]
        dur = max(80, int(beats * self.beat_ms))
        freq = _FREQ.get(note, 0)
        if freq > 0:
            hwio.tone(freq, dur)
        self.cur += 1
        self._progress()
        self._after_id = self.after(dur, self._advance)

    def _toggle(self):
        if self.playing:
            self._pause()
            return
        song = self.songs[self.idx][1]
        if self.cur >= len(song):
            self.cur = 0
        self.playing = True
        self._update_play_btn()
        self._advance()

    def _pause(self):
        self.playing = False
        hwio.tone_stop()
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self._update_play_btn()

    def _next(self, auto=False):
        hwio.tone_stop()
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self.idx = (self.idx + 1) % len(self.songs)
        self.cur = 0
        self._update_title()
        self._progress()
        if auto or self.playing:
            self.playing = True
            self._update_play_btn()
            self._advance()

    def _prev(self):
        hwio.tone_stop()
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self.idx = (self.idx - 1) % len(self.songs)
        self.cur = 0
        self._update_title()
        self._progress()
        if self.playing:
            self._advance()

    def _select(self, i):
        hwio.tone_stop()
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self.idx = i
        self.cur = 0
        self._update_title()
        self._progress()
        self.playing = True
        self._update_play_btn()
        self._advance()

    def _on_list_select(self, ev):
        sel = self.lst.curselection()
        if not sel:
            return
        i = sel[0]
        if i != self.idx:
            self._select(i)

    def _bpm(self, d):
        self.beat_ms = max(200, min(800, self.beat_ms - d))
        bpm = round(60000 / self.beat_ms)
        self.bpm_lbl.config(text="%d BPM" % bpm)

    def _update_title(self):
        self.cur_lbl.config(text="%s  (%d/%d)" % (
            self.songs[self.idx][0], self.idx + 1, len(self.songs)))
        self.lst.selection_clear(0, tk.END)
        self.lst.selection_set(self.idx)
        self.lst.see(self.idx)

    def _update_play_btn(self):
        self.play_btn.config(text="⏸" if self.playing else "▶")

    def _progress(self):
        song = self.songs[self.idx][1]
        total = max(1, len(song))
        self.bar.config(maximum=total, value=self.cur)

    def _open_composer(self):
        try:
            composer.Composer(self)
        except Exception:
            pass

    # ============ 关闭 / 板载键 ============
    def _on_close(self):
        self.playing = False
        hwio.tone_stop()
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        try:
            self.destroy()
        except Exception:
            pass

    def _bind_board_key(self):
        if not self.hw:
            return
        hwio.bind_a(self._on_a)

    def _on_a(self, pin):
        try:
            if self.winfo_exists():
                self.after(0, self._on_close)
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
    MusicPlayer(root)
    root.mainloop()
