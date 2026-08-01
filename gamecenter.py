# -*- coding: utf-8 -*-
"""
行空板 OS - 游戏中心
替换原「音频浏览」功能。内置几十个纯 tkinter 小游戏，适配 240x320 触摸屏，
支持触摸点按 + 键盘（开发机调试）。所有游戏在单窗口模式（spawn_window）下
打开，点「返回」自动回到游戏中心列表。

运行：
  python main.py            # 行空板模式，桌面点「游戏中心」进入
  python gamecenter.py      # 单独调试游戏中心（开发机大窗口）
"""
import math
import random
import time
import tkinter as tk
from tkinter import ttk, messagebox

import theme
from theme import (
    BG, SURFACE, SURFACE2, ACCENT, ACCENT2, DANGER, TEXT, MUTED, ON_ACCENT,
    HOVER, FONT_NORMAL, FONT_SMALL, BOARD, apply_board_window, setup_board_button,
    spawn_window,
)

# 内容区域尺寸（留出顶部 30px 返回栏）。
# 注意：不能模块导入时缓存！main.py 会在运行中把 theme.BOARD 设成 True，
# 导入时缓存会得到 760x520 的开发机尺寸，导致真机 240x320 上所有绘制崩坏。
def _cw():
    return theme.BOARD_W if theme.BOARD else theme.WIN_W


def _ch():
    return (theme.BOARD_H if theme.BOARD else theme.WIN_H) - 30


# ===================== 游戏注册表 =====================
GAMES = []  # [(分类, 名称, 类)]


def _reg(cls):
    """装饰器：把游戏类登记到 GAMES 列表。"""
    GAMES.append((cls.GAME_CAT, cls.GAME_NAME, cls))
    return cls


# ===================== 游戏基类 =====================
class MiniGame(tk.Toplevel):
    GAME_NAME = "游戏"
    GAME_CAT = "其他"

    def __init__(self, master):
        super().__init__(master)
        self.title(self.GAME_NAME)
        self.configure(bg=BG)
        self._style()
        self.geometry(f"{_cw()}x{_ch() + 30}")
        apply_board_window(self)
        self.master = master
        self._alive = True
        self._after_ids = []

        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="返回", command=lambda: self.destroy(),
                   style="UH.Danger.TButton").pack(side=tk.LEFT, padx=2, pady=4)
        tk.Label(bar, text=self.GAME_NAME, bg=SURFACE, fg=TEXT,
                 font=FONT_NORMAL).pack(side=tk.LEFT, padx=6, pady=4)

        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill=tk.BOTH, expand=True)

        setup_board_button(self)
        try:
            self._build()
        except Exception as e:
            messagebox.showerror("启动失败", f"{self.GAME_NAME}：{e}")

    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass
        # 小屏用更小的字体和更紧的 padding，避免底部按钮行占太多高度
        btn_font = FONT_SMALL if BOARD else FONT_NORMAL
        s.configure("UH.TButton", background=ACCENT, foreground=ON_ACCENT,
                    font=btn_font, borderwidth=0,
                    padding=(2, 1) if BOARD else 6)
        s.map("UH.TButton", background=[("active", ACCENT2)])
        s.configure("UH.Danger.TButton", background=DANGER, foreground="#ffffff",
                    font=btn_font, borderwidth=0,
                    padding=(2, 1) if BOARD else 6)
        s.map("UH.Danger.TButton", background=[("active", "#b00020")])
        s.configure("UH.Num.TButton", background=SURFACE2, foreground=TEXT,
                    font=btn_font, borderwidth=0,
                    padding=(2, 1) if BOARD else 6)
        s.map("UH.Num.TButton", background=[("active", HOVER)])

    def _build(self):
        raise NotImplementedError

    def _make_canvas(self, w=None, h=None):
        if w is None:
            w = _cw()
        # 宽度设为满屏(避免水平方向也超出 body)，高度设为最小 1 交给
        # pack 的 expand 填充剩余空间。绝不能把高度设成 _ch()：那样 Canvas
        # 会占满 body，把底部按钮行(nav, 非 expand)用负余量挤成 0 高度，
        # 导致所有按钮整排消失。
        cv = tk.Canvas(self.body, width=w, height=1, bg=BG, highlightthickness=0)
        cv.pack(fill=tk.BOTH, expand=True)
        return cv

    def _num_pad(self, parent, cb, digits, extra=None):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill=tk.X)
        rowf = None
        seq = list(digits)
        if extra:
            seq = extra + seq
        for i, d in enumerate(seq):
            if i % 3 == 0:
                rowf = tk.Frame(f, bg=BG)
                rowf.pack(fill=tk.X)
            label = d if isinstance(d, str) else str(d)
            ttk.Button(rowf, text=label, style="UH.Num.TButton",
                       command=lambda x=d: cb(x)).pack(
                side=tk.LEFT, expand=True, fill=tk.X, padx=2, pady=2)
        return f

    def after(self, ms, func=None, *args):
        aid = super().after(ms, func, *args)
        if aid is not None:
            self._after_ids.append(aid)
        return aid

    def destroy(self):
        self._alive = False
        for aid in getattr(self, "_after_ids", []):
            try:
                self.after_cancel(aid)
            except Exception:
                pass
        try:
            super().destroy()
        except Exception:
            pass


# ===================== 游戏中心启动器 =====================
class GameCenter(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("游戏中心")
        self.configure(bg=BG)
        self._style()
        self.geometry(f"{_cw()}x{_ch() + 30}")
        apply_board_window(self)
        self.master = master
        self._after_ids = []
        self._build()
        setup_board_button(self)

    def after(self, ms, func=None, *args):
        aid = super().after(ms, func, *args)
        if aid is not None:
            self._after_ids.append(aid)
        return aid

    def destroy(self):
        for aid in getattr(self, "_after_ids", []):
            try:
                self.after_cancel(aid)
            except Exception:
                pass
        try:
            super().destroy()
        except Exception:
            pass

    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass
        btn_font = FONT_SMALL if BOARD else FONT_NORMAL
        s.configure("UH.TButton", background=ACCENT, foreground=ON_ACCENT,
                    font=btn_font, borderwidth=0,
                    padding=(2, 1) if BOARD else 6)
        s.map("UH.TButton", background=[("active", ACCENT2)])
        s.configure("UH.Danger.TButton", background=DANGER, foreground="#ffffff",
                    font=btn_font, borderwidth=0,
                    padding=(2, 1) if BOARD else 6)
        s.map("UH.Danger.TButton", background=[("active", "#b00020")])

    def _build(self):
        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="返回", command=lambda: self.destroy(),
                   style="UH.Danger.TButton").pack(side=tk.LEFT, padx=2, pady=4)
        tk.Label(bar, text="游戏中心", bg=SURFACE, fg=TEXT,
                 font=FONT_NORMAL).pack(side=tk.LEFT, padx=6, pady=4)

        self.cats = ["全部", "休闲", "棋盘", "街机", "反应"]
        catbar = tk.Frame(self, bg=BG)
        catbar.pack(fill=tk.X, pady=2)
        for c in self.cats:
            ttk.Button(catbar, text=c, style="UH.TButton",
                       command=lambda x=c: self._filter(x)).pack(
                side=tk.LEFT, padx=1, pady=2, expand=True, fill=tk.X)

        self.canvas = tk.Canvas(self, width=_cw(), height=1, bg=BG,
                                highlightthickness=0, yscrollincrement=18)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.win = self.canvas.create_window((0, 0), window=self.inner,
                                             anchor="nw")
        self.canvas.bind("<Configure>", self._on_cfg)
        self.inner.bind("<Configure>", self._on_inner)

        nav = tk.Frame(self, bg=SURFACE2)
        nav.pack(fill=tk.X)
        ttk.Button(nav, text="▲ 上滑", command=lambda: self._scroll(-3),
                   style="UH.TButton").pack(side=tk.LEFT, expand=True,
                                            fill=tk.X, padx=2)
        ttk.Button(nav, text="▼ 下滑", command=lambda: self._scroll(3),
                   style="UH.TButton").pack(side=tk.LEFT, expand=True,
                                            fill=tk.X, padx=2)
        self.bind("<Up>", lambda e: self._scroll(-3))
        self.bind("<Down>", lambda e: self._scroll(3))

        self._filter("全部")

    def _on_cfg(self, e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.itemconfig(self.win, width=e.width)

    def _on_inner(self, e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _scroll(self, d):
        # yscrollincrement=18，每次 3 个单位 = 54px，按钮高约 30px，一跳两个按钮
        self.canvas.yview_scroll(d, "units")

    def _filter(self, cat):
        for w in self.inner.winfo_children():
            w.destroy()
        items = [g for g in GAMES if cat == "全部" or g[0] == cat]
        for cat_, name, cls in items:
            ttk.Button(self.inner, text=name, style="UH.TButton",
                       command=lambda c=cls: spawn_window(
                           self, lambda: c(self))).pack(
                fill=tk.X, padx=8, pady=3)
        # 立即刷新滚动区域，真机上 Configure 事件不一定触发
        self.after(10, self._update_scroll)

    def _update_scroll(self):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.itemconfig(self.win, width=self.canvas.winfo_width())


# ===================== 休闲类 =====================
@_reg
class Game2048(MiniGame):
    GAME_NAME = "2048"
    GAME_CAT = "休闲"

    def _build(self):
        self.grid = [[0] * 4 for _ in range(4)]
        self.score = 0
        self.over = False
        self._add()
        self._add()
        self.cv = self._make_canvas()
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        for txt, d in [("←", "left"), ("↑", "up"), ("↓", "down"), ("→", "right")]:
            ttk.Button(nav, text=txt, style="UH.TButton",
                       command=lambda x=d: self._move(x)).pack(
                side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self.bind("<Left>", lambda e: self._move("left"))
        self.bind("<Right>", lambda e: self._move("right"))
        self.bind("<Up>", lambda e: self._move("up"))
        self.bind("<Down>", lambda e: self._move("down"))
        # 触摸屏滑动手势：在棋盘上按下并拖动，松开时按位移方向滑动
        self.cv.bind("<ButtonPress-1>", self._swipe_start)
        self.cv.bind("<ButtonRelease-1>", self._swipe_end)
        self._draw()

    def _add(self):
        empt = [(r, c) for r in range(4) for c in range(4)
                if self.grid[r][c] == 0]
        if empt:
            r, c = random.choice(empt)
            self.grid[r][c] = 2 if random.random() < 0.9 else 4

    def _slide(self, row):
        filled = [v for v in row if v]
        res, i = [], 0
        while i < len(filled):
            if i + 1 < len(filled) and filled[i] == filled[i + 1]:
                res.append(filled[i] * 2)
                self.score += filled[i] * 2
                i += 2
            else:
                res.append(filled[i])
                i += 1
        return res + [0] * (4 - len(res))

    def _move(self, d):
        if self.over:
            return
        g = self.grid
        if d in ("left", "right"):
            lines = [row[:] for row in g]
            if d == "right":
                lines = [row[::-1] for row in lines]
            new = [self._slide(r) for r in lines]
            if d == "right":
                new = [row[::-1] for row in new]
        else:
            t = [list(col) for col in zip(*g)]
            if d == "down":
                t = [row[::-1] for row in t]
            new = [self._slide(r) for r in t]
            if d == "down":
                new = [row[::-1] for row in new]
            new = [list(col) for col in zip(*new)]
        if new != g:
            self.grid = new
            self._add()
            if not self._can_move():
                self.over = True
        self._draw()

    def _swipe_start(self, e):
        self._sx, self._sy = e.x, e.y

    def _swipe_end(self, e):
        if self.over or not hasattr(self, "_sx"):
            return
        dx, dy = e.x - self._sx, e.y - self._sy
        # 位移小于阈值视为点按，不滑动
        if abs(dx) < 18 and abs(dy) < 18:
            return
        if abs(dx) > abs(dy):
            self._move("right" if dx > 0 else "left")
        else:
            self._move("down" if dy > 0 else "up")

    def _can_move(self):
        for r in range(4):
            for c in range(4):
                if self.grid[r][c] == 0:
                    return True
                if c < 3 and self.grid[r][c] == self.grid[r][c + 1]:
                    return True
                if r < 3 and self.grid[r][c] == self.grid[r + 1][c]:
                    return True
        return False

    def _col(self, v):
        m = {0: SURFACE, 2: "#eee4da", 4: "#ede0c8", 8: "#f2b179",
             16: "#f59563", 32: "#f67c5f", 64: "#f65e3b", 128: "#edcf72",
             256: "#edcc61", 512: "#edc850", 1024: "#edc53f",
             2048: "#edc22e"}
        return m.get(v, "#3c3a32")

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        pad = 4
        size = min(w, h) - pad * 2
        cell = size // 4
        ox = (w - size) // 2
        oy = (h - size) // 2 + 10
        for r in range(4):
            for c in range(4):
                x = ox + c * cell
                y = oy + r * cell
                v = self.grid[r][c]
                cv.create_rectangle(x + 1, y + 1, x + cell - 1, y + cell - 1,
                                    fill=self._col(v), outline=SURFACE2)
                if v:
                    fs = 14 if v < 1000 else 11
                    cv.create_text(x + cell / 2, y + cell / 2, text=str(v),
                                   fill=TEXT if v < 8 else "#ffffff",
                                   font=(FONT_NORMAL[0], fs, "bold"))
        cv.create_text(w / 2, 12, text=f"分数 {self.score}", fill=ACCENT,
                       font=FONT_SMALL)
        if self.over:
            cv.create_text(w / 2, h / 2, text="游戏结束",
                           fill=DANGER, font=(FONT_NORMAL[0], 20, "bold"))


@_reg
class GameDice(MiniGame):
    GAME_NAME = "掷骰子"
    GAME_CAT = "休闲"

    def _build(self):
        self.cv = self._make_canvas()
        self.val = 1
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        ttk.Button(nav, text="掷一次", style="UH.TButton",
                   command=self._roll).pack(side=tk.LEFT, expand=True,
                                            fill=tk.X, padx=2)
        ttk.Button(nav, text="掷两颗", style="UH.TButton",
                   command=lambda: self._roll(2)).pack(side=tk.LEFT, expand=True,
                                                       fill=tk.X, padx=2)
        self.dice = 1
        self._draw()

    def _roll(self, n=1):
        self.dice = n
        self.val = random.randint(1, 6)
        self.val2 = random.randint(1, 6) if n == 2 else 0
        self._draw()

    def _pip(self, cv, cx, cy, r, pips):
        for (dx, dy) in pips:
            cv.create_oval(cx + dx * r, cy + dy * r, cx + dx * r + r * 0.5,
                           cy + dy * r + r * 0.5, fill=TEXT, outline=TEXT)

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        layouts = {
            1: [(0, 0)],
            2: [(-1, -1), (1, 1)],
            3: [(-1, -1), (0, 0), (1, 1)],
            4: [(-1, -1), (1, -1), (-1, 1), (1, 1)],
            5: [(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)],
            6: [(-1, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (1, 1)],
        }
        if self.dice == 1:
            self._draw_die(cv, w / 2, h / 2, min(w, h) * 0.3, self.val, layouts)
        else:
            self._draw_die(cv, w / 3, h / 2, min(w, h) * 0.25, self.val, layouts)
            self._draw_die(cv, 2 * w / 3, h / 2, min(w, h) * 0.25,
                           self.val2, layouts)
            cv.create_text(w / 2, h - 16, text=f"合计 {self.val + self.val2}",
                           fill=ACCENT, font=FONT_NORMAL)

    def _draw_die(self, cv, cx, cy, s, v, layouts):
        cv.create_rectangle(cx - s, cy - s, cx + s, cy + s, fill=SURFACE2,
                            outline=TEXT, width=2)
        r = s * 0.42
        for (dx, dy) in layouts[v]:
            cv.create_oval(cx + dx * r - r * 0.18, cy + dy * r - r * 0.18,
                           cx + dx * r + r * 0.18, cy + dy * r + r * 0.18,
                           fill=TEXT, outline=TEXT)


@_reg
class GameSpin(MiniGame):
    GAME_NAME = "幸运转盘"
    GAME_CAT = "休闲"

    def _build(self):
        self.prizes = ["大奖", "再来", "5分", "谢谢", "10分", "好运", "1分", "红包"]
        self.cv = self._make_canvas()
        self.angle = 0
        self.spin = False
        ttk.Button(self.body, text="开始转动", style="UH.TButton",
                   command=self._go).pack(fill=tk.X, padx=8, pady=4)
        self._draw()

    def _go(self):
        if self.spin:
            return
        self.spin = True
        self._speed = 22
        self._steps = random.randint(70, 130)
        self.result_text = ""
        self._tick()

    def _tick(self):
        if not self.winfo_exists() or not self._alive:
            return
        self.angle = (self.angle + self._speed) % 360
        self._draw()
        self._steps -= 1
        if self._steps > 0:
            # 最后 30 步逐渐减速
            if self._steps < 30 and self._steps % 3 == 0:
                self._speed = max(1, self._speed - 1)
            self.after(30, self._tick)
        else:
            self.spin = False
            n = len(self.prizes)
            # 指针在正上方（270°），计算当前指向的扇区
            ptr = (270 - self.angle) % 360
            idx = int(ptr / 360 * n) % n
            self.result_text = f"结果：{self.prizes[idx]}"
            self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 60
        cx, cy = w / 2, h / 2 + 10
        r = min(w, h) * 0.38
        n = len(self.prizes)
        cols = [ACCENT, ACCENT2, DANGER, "#06d6a0", "#c77dff", "#ffd166",
                "#80ed99", "#fb8500"]
        for i in range(n):
            a0 = self.angle + i * 360 / n
            a1 = self.angle + (i + 1) * 360 / n
            cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=a0, extent=(a1 - a0),
                          fill=cols[i % len(cols)], outline=BG)
            mid = math.radians((a0 + a1) / 2)
            mx = cx + (r * 0.55) * math.cos(mid)
            my = cy + (r * 0.55) * math.sin(mid)
            cv.create_text(mx, my, text=self.prizes[i], fill=TEXT,
                           font=FONT_SMALL)
        cv.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill=SURFACE2,
                       outline=TEXT)
        cv.create_polygon(cx, cy - r - 8, cx - 8, cy - r + 6, cx + 8, cy - r + 6,
                          fill=DANGER, outline=DANGER)
        if self.result_text:
            cv.create_text(w / 2, 20, text=self.result_text,
                           fill=ACCENT, font=FONT_NORMAL)


@_reg
class GameRPS(MiniGame):
    GAME_NAME = "石头剪刀布"
    GAME_CAT = "休闲"

    def _build(self):
        self.cv = self._make_canvas()
        self.win = self.draw = self.lose = 0
        self.result = ""
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        for t, m in [("石头", "石头"), ("剪刀", "剪刀"), ("布", "布")]:
            ttk.Button(nav, text=t, style="UH.TButton",
                       command=lambda x=m: self._play(x)).pack(
                side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self._draw()

    def _play(self, you):
        cpu = random.choice(["石头", "剪刀", "布"])
        if you == cpu:
            self.draw += 1
            self.result = f"平局（电脑出{cpu}）"
        elif (you == "石头" and cpu == "剪刀") or \
             (you == "剪刀" and cpu == "布") or \
             (you == "布" and cpu == "石头"):
            self.win += 1
            self.result = f"你赢了（电脑出{cpu}）"
        else:
            self.lose += 1
            self.result = f"你输了（电脑出{cpu}）"
        self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        cv.create_text(w / 2, 20, text=self.result or "选一个出吧",
                       fill=ACCENT, font=FONT_NORMAL)
        cv.create_text(w / 2, h - 24,
                       text=f"胜 {self.win}  负 {self.lose}  平 {self.draw}",
                       fill=TEXT, font=FONT_SMALL)


@_reg
class GameMathQuiz(MiniGame):
    GAME_NAME = "速算挑战"
    GAME_CAT = "休闲"

    def _build(self):
        self.cv = self._make_canvas()
        self.score = 0
        self.q = 0
        self._next()
        self._draw()

    def _next(self):
        a = random.randint(2, 9)
        b = random.randint(2, 9)
        op = random.choice(["+", "-", "×"])
        if op == "+":
            self.ans = a + b
        elif op == "-":
            if a < b:
                a, b = b, a
            self.ans = a - b
        else:
            self.ans = a * b
        self.qtext = f"{a} {op} {b} = ?"
        opts = [self.ans]
        while len(opts) < 4:
            d = self.ans + random.randint(-5, 5)
            if d >= 0 and d not in opts:
                opts.append(d)
        random.shuffle(opts)
        self.opts = opts

    def _choose(self, v):
        if v == self.ans:
            self.score += 1
        else:
            self.score -= 1
        self.q += 1
        self._next()
        self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        cv.create_text(w / 2, 20, text=f"得分 {self.score}  第{self.q + 1}题",
                       fill=ACCENT, font=FONT_SMALL)
        cv.create_text(w / 2, h * 0.3, text=self.qtext, fill=TEXT,
                       font=(FONT_NORMAL[0], 22, "bold"))
        bw = w / 2 - 10
        bh = 36
        for i, v in enumerate(self.opts):
            x = 8 + (i % 2) * (bw + 4)
            y = h * 0.45 + (i // 2) * (bh + 6)
            cv.create_rectangle(x, y, x + bw, y + bh, fill=SURFACE2,
                                outline=ACCENT)
            cv.create_text(x + bw / 2, y + bh / 2, text=str(v), fill=TEXT,
                           font=FONT_NORMAL)
            cv.tag_bind(cv.create_rectangle(x, y, x + bw, y + bh,
                            fill="", outline=""),
                        "<Button-1>", lambda e, val=v: self._choose(val))


# ===================== 棋盘类 =====================
@_reg
class GameTicTac(MiniGame):
    GAME_NAME = "井字棋"
    GAME_CAT = "棋盘"

    def _build(self):
        self.board = [""] * 9
        self.over = False
        self.cv = self._make_canvas()
        self.cv.bind("<Button-1>", self._tap)
        self._draw()

    def _tap(self, e):
        if self.over:
            return
        w = _cw()
        h = _ch() - 40
        size = min(w, h) - 20
        cell = size // 3
        ox = (w - size) // 2
        oy = (h - size) // 2 + 10
        c = int((e.x - ox) // cell)
        r = int((e.y - oy) // cell)
        if 0 <= r < 3 and 0 <= c < 3:
            i = r * 3 + c
            if self.board[i] == "":
                self.board[i] = "X"
                if self._check("X"):
                    self.over = True
                elif "" not in self.board:
                    self.over = True
                else:
                    self._ai()
                self._draw()

    def _ai(self):
        empt = [i for i, v in enumerate(self.board) if v == ""]
        # 简单策略：先堵再随机
        for i in empt:
            b = self.board[:]
            b[i] = "O"
            if self._win_line(b, "O"):
                self.board[i] = "O"
                return
        for i in empt:
            b = self.board[:]
            b[i] = "X"
            if self._win_line(b, "X"):
                self.board[i] = "O"
                return
        self.board[random.choice(empt)] = "O"

    def _win_line(self, b, p):
        for i in range(3):
            if b[i * 3] == b[i * 3 + 1] == b[i * 3 + 2] == p:
                return True
            if b[i] == b[i + 3] == b[i + 6] == p:
                return True
        return b[0] == b[4] == b[8] == p or b[2] == b[4] == b[6] == p

    def _check(self, p):
        return self._win_line(self.board, p)

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        size = min(w, h) - 20
        cell = size // 3
        ox = (w - size) // 2
        oy = (h - size) // 2 + 10
        for i in range(1, 3):
            cv.create_line(ox + i * cell, oy, ox + i * cell, oy + size,
                           fill=MUTED)
            cv.create_line(ox, oy + i * cell, ox + size, oy + i * cell,
                           fill=MUTED)
        for i, v in enumerate(self.board):
            r, c = divmod(i, 3)
            x = ox + c * cell + cell / 2
            y = oy + r * cell + cell / 2
            if v == "X":
                cv.create_text(x, y, text="X", fill=ACCENT,
                               font=(FONT_NORMAL[0], 28, "bold"))
            elif v == "O":
                cv.create_text(x, y, text="O", fill=DANGER,
                               font=(FONT_NORMAL[0], 28, "bold"))
        msg = ""
        if self.over:
            if self._check("X"):
                msg = "你赢了！"
            elif self._check("O"):
                msg = "电脑赢了"
            else:
                msg = "平局"
        cv.create_text(w / 2, 16, text=msg or "你执 X，先手", fill=ACCENT,
                       font=FONT_SMALL)


@_reg
class GameConnect4(MiniGame):
    GAME_NAME = "四子棋"
    GAME_CAT = "棋盘"

    def _build(self):
        self.cols = 7
        self.rows = 6
        self.board = [[0] * self.cols for _ in range(self.rows)]
        self.over = False
        self.cv = self._make_canvas()
        self.cv.bind("<Button-1>", self._tap)
        self._draw()

    def _tap(self, e):
        if self.over:
            return
        w = _cw()
        cell = w / self.cols
        c = int(e.x // cell)
        if 0 <= c < self.cols:
            for r in range(self.rows - 1, -1, -1):
                if self.board[r][c] == 0:
                    self.board[r][c] = 1
                    if self._win(1):
                        self.over = True
                    else:
                        self._ai()
                        if self._win(2):
                            self.over = True
                        elif all(self.board[0][c] for c in range(self.cols)):
                            self.over = True
                    self._draw()
                    return

    def _ai(self):
        # 1) 能赢直接赢
        for c in range(self.cols):
            r = self._free(c)
            if r is None:
                continue
            self.board[r][c] = 2
            if self._win(2):
                return
            self.board[r][c] = 0
        # 2) 必须堵玩家
        for c in range(self.cols):
            r = self._free(c)
            if r is None:
                continue
            self.board[r][c] = 1
            if self._win(1):
                self.board[r][c] = 2
                return
            self.board[r][c] = 0
        # 3) 优先占中列，其次随机
        order = sorted(range(self.cols), key=lambda c: abs(c - self.cols // 2))
        for c in order:
            r = self._free(c)
            if r is not None:
                self.board[r][c] = 2
                return

    def _free(self, c):
        for r in range(self.rows - 1, -1, -1):
            if self.board[r][c] == 0:
                return r
        return None

    def _win(self, p):
        b = self.board
        for r in range(self.rows):
            for c in range(self.cols):
                if b[r][c] != p:
                    continue
                for dr, dc in [(0, 1), (1, 0), (1, 1), (1, -1)]:
                    ok = True
                    for k in range(4):
                        nr, nc = r + dr * k, c + dc * k
                        if not (0 <= nr < self.rows and 0 <= nc < self.cols) \
                                or b[nr][nc] != p:
                            ok = False
                            break
                    if ok:
                        return True
        return False

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        cell = w / self.cols
        size = cell * self.rows
        ox = 0
        oy = (h - size) // 2 + 10
        for r in range(self.rows):
            for c in range(self.cols):
                x = ox + c * cell + cell / 2
                y = oy + r * cell + cell / 2
                cv.create_oval(x - cell * 0.4, y - cell * 0.4, x + cell * 0.4,
                               y + cell * 0.4,
                               fill=SURFACE2 if self.board[r][c] == 0
                               else (ACCENT if self.board[r][c] == 1 else DANGER),
                               outline=MUTED)
        msg = ""
        if self.over:
            msg = "你赢了！" if self._win(1) else ("电脑赢了" if self._win(2)
                                                  else "平局")
        cv.create_text(w / 2, 16, text=msg or "点列落子（你=青）",
                       fill=ACCENT, font=FONT_SMALL)


@_reg
class GameMines(MiniGame):
    GAME_NAME = "扫雷"
    GAME_CAT = "棋盘"

    def _build(self):
        self.n = 8
        self.mines = 10
        self.board = [[0] * self.n for _ in range(self.n)]
        self.rev = [[False] * self.n for _ in range(self.n)]
        self.flag = [[False] * self.n for _ in range(self.n)]
        self.over = False
        self.started = False
        self.sel = None
        self.cv = self._make_canvas()
        self.cv.bind("<Button-1>", self._tap)
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        ttk.Button(nav, text="挖开", style="UH.TButton",
                   command=self._dig_sel).pack(side=tk.LEFT, expand=True,
                                               fill=tk.X, padx=2)
        ttk.Button(nav, text="插旗", style="UH.TButton",
                   command=self._flag_sel).pack(side=tk.LEFT, expand=True,
                                                fill=tk.X, padx=2)
        ttk.Button(nav, text="重开", style="UH.TButton",
                   command=self._reset).pack(side=tk.LEFT, expand=True,
                                             fill=tk.X, padx=2)
        self._draw()

    def _place(self, safe_r, safe_c):
        # 首次挖开时才布雷；保证 safe 格及其 8 邻域无雷，从而挖开一定是 0 并自动扩散
        spots = [(r, c) for r in range(self.n) for c in range(self.n)
                 if not (abs(r - safe_r) <= 1 and abs(c - safe_c) <= 1)]
        random.shuffle(spots)
        for (r, c) in spots[:self.mines]:
            self.board[r][c] = -1
        for r in range(self.n):
            for c in range(self.n):
                if self.board[r][c] == -1:
                    continue
                cnt = 0
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < self.n and 0 <= nc < self.n and \
                                self.board[nr][nc] == -1:
                            cnt += 1
                self.board[r][c] = cnt

    def _reset(self):
        self.rev = [[False] * self.n for _ in range(self.n)]
        self.flag = [[False] * self.n for _ in range(self.n)]
        self.over = False
        self.started = False
        self.sel = None
        self.board = [[0] * self.n for _ in range(self.n)]
        self._draw()

    def _tap(self, e):
        if self.over:
            return
        w = _cw()
        cell = w / self.n
        c = int(e.x // cell)
        r = int((e.y - getattr(self, "_my", 0)) // cell)
        if 0 <= r < self.n and 0 <= c < self.n:
            self.sel = (r, c)
            self._draw()

    def _dig_sel(self):
        if self.over or self.sel is None:
            return
        r, c = self.sel
        if self.flag[r][c]:
            return
        if not self.started:
            self.started = True
            self._place(r, c)
        self._reveal(r, c)
        if self.board[r][c] == -1:
            self.over = True
        self.sel = None
        self._draw()

    def _flag_sel(self):
        if self.over or self.sel is None:
            return
        r, c = self.sel
        if not self.rev[r][c]:
            self.flag[r][c] = not self.flag[r][c]
        self.sel = None
        self._draw()

    def _reveal(self, r, c):
        if not (0 <= r < self.n and 0 <= c < self.n) or self.rev[r][c]:
            return
        self.rev[r][c] = True
        if self.board[r][c] == 0:
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    self._reveal(r + dr, c + dc)

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        cell = w / self.n
        size = cell * self.n
        ox = 0
        oy = (h - size) // 2 + 6
        self._mx, self._my, self._mc = ox, oy, cell
        win = True
        for r in range(self.n):
            for c in range(self.n):
                x = ox + c * cell
                y = oy + r * cell
                if self.rev[r][c]:
                    v = self.board[r][c]
                    cv.create_rectangle(x + 1, y + 1, x + cell - 1, y + cell - 1,
                                        fill=SURFACE, outline=MUTED)
                    if v == -1:
                        cv.create_text(x + cell / 2, y + cell / 2, text="✸",
                                       fill=DANGER, font=FONT_NORMAL)
                    elif v > 0:
                        cols = ["", "#0077b6", "#00b4d8", "#06d6a0", "#fb8500",
                                "#ef476f", "#c77dff", "#ffd166", "#80ed99"]
                        cv.create_text(x + cell / 2, y + cell / 2, text=str(v),
                                       fill=cols[v], font=FONT_SMALL)
                else:
                    cv.create_rectangle(x + 1, y + 1, x + cell - 1, y + cell - 1,
                                        fill=SURFACE2, outline=MUTED)
                    if self.flag[r][c]:
                        cv.create_text(x + cell / 2, y + cell / 2, text="⚑",
                                       fill=DANGER, font=FONT_SMALL)
                    else:
                        win = False
                if self.sel == (r, c):
                    cv.create_rectangle(x + 1, y + 1, x + cell - 1,
                                        y + cell - 1, outline=ACCENT, width=2)
        if self.over:
            cv.create_text(w / 2, 16, text="踩雷了！点重开", fill=DANGER,
                           font=FONT_NORMAL)
        elif win and all(self.rev[r][c] or self.board[r][c] == -1
                         for r in range(self.n) for c in range(self.n)):
            cv.create_text(w / 2, 16, text="胜利！", fill=ACCENT,
                           font=FONT_NORMAL)
        else:
            seltxt = ""
            if self.sel:
                seltxt = f" 选中{self.sel[0] + 1},{self.sel[1] + 1}"
            cv.create_text(w / 2, 16, text="点格子选中，再按挖开/插旗" + seltxt,
                           fill=ACCENT, font=FONT_SMALL)


@_reg
class GameMemory(MiniGame):
    GAME_NAME = "记忆翻牌"
    GAME_CAT = "棋盘"

    def _build(self):
        self.n = 4
        syms = ["★", "●", "▲", "◆", "♥", "☀", "✿", "✦"]
        deck = syms * 2
        random.shuffle(deck)
        self.cards = deck
        self.rev = [False] * 16
        self.matched = [False] * 16
        self.first = None
        self.lock = False
        self.cv = self._make_canvas()
        self.cv.bind("<Button-1>", self._tap)
        self._draw()

    def _tap(self, e):
        if self.lock:
            return
        w = _cw()
        cell = w / self.n
        c = int(e.x // cell)
        r = int((e.y - getattr(self, "_my", 0)) // cell)
        if not (0 <= r < self.n and 0 <= c < self.n):
            return
        i = r * self.n + c
        if self.rev[i] or self.matched[i]:
            return
        self.rev[i] = True
        if self.first is None:
            self.first = i
        else:
            a, b = self.first, i
            self.first = None
            if self.cards[a] == self.cards[b]:
                self.matched[a] = self.matched[b] = True
            else:
                self.lock = True
                self.after(600, lambda: self._hide(a, b))
        self._draw()

    def _hide(self, a, b):
        if not self.winfo_exists():
            return
        self.rev[a] = self.rev[b] = False
        self.lock = False
        self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        cell = w / self.n
        size = cell * self.n
        ox = 0
        oy = (h - size) // 2 + 6
        done = sum(self.matched)
        for i in range(16):
            r, c = divmod(i, self.n)
            x = ox + c * cell
            y = oy + r * cell
            if self.matched[i]:
                cv.create_rectangle(x + 1, y + 1, x + cell - 1, y + cell - 1,
                                    fill=ACCENT, outline=BG)
                cv.create_text(x + cell / 2, y + cell / 2, text=self.cards[i],
                               fill=ON_ACCENT, font=(FONT_NORMAL[0], 16))
            elif self.rev[i]:
                cv.create_rectangle(x + 1, y + 1, x + cell - 1, y + cell - 1,
                                    fill=SURFACE2, outline=ACCENT)
                cv.create_text(x + cell / 2, y + cell / 2, text=self.cards[i],
                               fill=TEXT, font=(FONT_NORMAL[0], 16))
            else:
                cv.create_rectangle(x + 1, y + 1, x + cell - 1, y + cell - 1,
                                    fill=SURFACE, outline=MUTED)
        cv.create_text(w / 2, 16,
                       text=f"配对 {done // 2}/8" + ("  完成！" if done == 16
                                                     else ""),
                       fill=ACCENT, font=FONT_SMALL)


@_reg
class GameFifteen(MiniGame):
    GAME_NAME = "数字华容道"
    GAME_CAT = "棋盘"

    def _build(self):
        self.n = 3
        self.tiles = list(range(1, self.n * self.n)) + [0]
        self._shuffle()
        self.cv = self._make_canvas()
        self.cv.bind("<Button-1>", self._tap)
        self._draw()

    def _shuffle(self):
        for _ in range(100):
            z = self.tiles.index(0)
            r, c = divmod(z, self.n)
            opts = []
            if r > 0:
                opts.append(z - self.n)
            if r < self.n - 1:
                opts.append(z + self.n)
            if c > 0:
                opts.append(z - 1)
            if c < self.n - 1:
                opts.append(z + 1)
            t = random.choice(opts)
            self.tiles[z], self.tiles[t] = self.tiles[t], self.tiles[z]

    def _tap(self, e):
        w = _cw()
        cell = w / self.n
        c = int(e.x // cell)
        r = int((e.y - getattr(self, "_my", 0)) // cell)
        if not (0 <= r < self.n and 0 <= c < self.n):
            return
        i = r * self.n + c
        z = self.tiles.index(0)
        if abs(i - z) in (1, self.n) and (
                (i - z == 1 and z % self.n < self.n - 1) or
                (i - z == -1 and z % self.n > 0) or abs(i - z) == self.n):
            self.tiles[z], self.tiles[i] = self.tiles[i], self.tiles[z]
            self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        cell = w / self.n
        size = cell * self.n
        ox = 0
        oy = (h - size) // 2 + 6
        solved = self.tiles == list(range(1, self.n * self.n)) + [0]
        for i, v in enumerate(self.tiles):
            r, c = divmod(i, self.n)
            x = ox + c * cell
            y = oy + r * cell
            if v:
                cv.create_rectangle(x + 1, y + 1, x + cell - 1, y + cell - 1,
                                    fill=SURFACE2, outline=ACCENT)
                cv.create_text(x + cell / 2, y + cell / 2, text=str(v),
                               fill=TEXT, font=(FONT_NORMAL[0], 16))
        cv.create_text(w / 2, 16,
                       text="点数字滑动" + (" 完成！" if solved else ""),
                       fill=ACCENT, font=FONT_SMALL)


@_reg
class GameSokoban(MiniGame):
    GAME_NAME = "推箱子"
    GAME_CAT = "棋盘"

    def _build(self):
        self.rows = self.cols = 8
        self.boxes = 3
        self._gen()
        self.cv = self._make_canvas()
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        for t, d in [("↑", (0, -1)), ("↓", (0, 1)), ("←", (-1, 0)), ("→", (1, 0))]:
            ttk.Button(nav, text=t, style="UH.TButton",
                       command=lambda x=d: self._move(x)).pack(
                side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(nav, text="重开", style="UH.TButton",
                   command=self._reset).pack(side=tk.LEFT, expand=True,
                                             fill=tk.X, padx=2)
        self.bind("<Up>", lambda e: self._move((0, -1)))
        self.bind("<Down>", lambda e: self._move((0, 1)))
        self.bind("<Left>", lambda e: self._move((-1, 0)))
        self.bind("<Right>", lambda e: self._move((1, 0)))
        self._draw()

    def _gen(self):
        # 生成可解关卡：从解状态反向随机拉动箱子
        r, c = self.rows, self.cols
        self.map = [["#"] * c for _ in range(r)]
        for y in range(1, r - 1):
            for x in range(1, c - 1):
                self.map[y][x] = " "
        # 内部随机墙
        inner = [(y, x) for y in range(2, r - 2) for x in range(2, c - 2)]
        random.shuffle(inner)
        for y, x in inner[:5]:
            self.map[y][x] = "#"

        floors = set((y, x) for y in range(1, r - 1) for x in range(1, c - 1)
                     if self.map[y][x] == " ")
        targets = random.sample(sorted(floors), self.boxes)
        target_set = set(targets)
        # 箱子初始放在目标上
        boxes = set(targets)
        # 玩家放在某个目标旁边
        ty, tx = targets[0]
        adj = [(ty + dy, tx + dx) for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0))
               if (ty + dy, tx + dx) in floors]
        player = random.choice(adj)

        def is_floor(p):
            return p in floors and p not in boxes

        def render():
            m = [["#"] * c for _ in range(r)]
            for y in range(r):
                for x in range(c):
                    if (y, x) not in floors:
                        continue
                    p = (y, x)
                    on_target = p in target_set
                    has_box = p in boxes
                    is_player = p == player
                    if is_player and has_box:
                        # 不应当发生
                        m[y][x] = "+" if on_target else "@"
                    elif is_player:
                        m[y][x] = "+" if on_target else "@"
                    elif has_box:
                        m[y][x] = "*" if on_target else "$"
                    elif on_target:
                        m[y][x] = "."
                    else:
                        m[y][x] = " "
            return m

        # 反向拉动 30~50 次
        for _ in range(random.randint(30, 50)):
            moves = []
            for b in boxes:
                by, bx = b
                for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    # 反向拉：箱子从 b 退到 b - (dy,dx)，玩家站到 b
                    nby, nbx = by - dy, bx - dx
                    pny, pnx = by + dy, bx + dx
                    nb = (nby, nbx)
                    np_pos = (by, bx)
                    old_player_pos = (pny, pnx)
                    # 新箱子位置必须是地板，玩家新位置是原箱子位置（当前是箱子，反向时先空出），
                    # 玩家原来的位置要空出来给移动路径
                    if nb in floors and nb not in boxes and nb != player:
                        if old_player_pos in floors and old_player_pos not in boxes:
                            moves.append((b, nb, np_pos, old_player_pos))
            if not moves:
                break
            b, nb, np_pos, old_player_pos = random.choice(moves)
            boxes.remove(b)
            boxes.add(nb)
            player = np_pos

        self.map = render()

    def _reset(self):
        self._gen()
        self._draw()

    def _find_player(self):
        for r, row in enumerate(self.map):
            for c, v in enumerate(row):
                if v in ("@", "+"):
                    return c, r
        return None

    def _move(self, d):
        px, py = self._find_player()
        if px is None:
            return
        nx, ny = px + d[0], py + d[1]
        cur = self.map[ny][nx]
        if cur in (" ", "."):
            self.map[py][px] = "." if self.map[py][px] == "+" else " "
            self.map[ny][nx] = "+" if cur == "." else "@"
        elif cur in ("$", "*"):
            bx, by = nx + d[0], ny + d[1]
            if self.map[by][bx] in (" ", "."):
                self.map[py][px] = "." if self.map[py][px] == "+" else " "
                self.map[ny][nx] = "+" if cur == "*" else "@"
                self.map[by][bx] = "*" if self.map[by][bx] == "." else "$"
        self._draw()

    def _win(self):
        return not any("$" in row for row in self.map)

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        rows = len(self.map)
        cols = max(len(r) for r in self.map)
        cell = min(w / cols, (h - 30) / rows)
        ox = (w - cell * cols) / 2
        oy = 30
        for r, row in enumerate(self.map):
            for c, v in enumerate(row):
                x = ox + c * cell
                y = oy + r * cell
                if v == "#":
                    cv.create_rectangle(x, y, x + cell, y + cell, fill=SURFACE2,
                                        outline=MUTED)
                elif v in (" ", "@"):
                    fill = BG if v == " " else None
                    if fill:
                        cv.create_rectangle(x, y, x + cell, y + cell, fill=fill,
                                            outline=MUTED)
                    else:
                        cv.create_rectangle(x, y, x + cell, y + cell, fill=BG,
                                            outline=MUTED)
                    if v == "@":
                        cv.create_oval(x + cell * 0.25, y + cell * 0.25,
                                       x + cell * 0.75, y + cell * 0.75,
                                       fill=ACCENT2, outline=ACCENT2)
                elif v in (".", "+", "*"):
                    # 目标点用高亮底色 + 红色靶心，非常明显
                    cv.create_rectangle(x, y, x + cell, y + cell, fill="#ffe0b2",
                                        outline=ACCENT2, width=2)
                    cv.create_oval(x + cell * 0.35, y + cell * 0.35,
                                   x + cell * 0.65, y + cell * 0.65,
                                   fill=DANGER, outline=DANGER)
                    if v == "+":
                        cv.create_oval(x + cell * 0.25, y + cell * 0.25,
                                       x + cell * 0.75, y + cell * 0.75,
                                       fill=TEXT, outline=TEXT)
                    elif v == "*":
                        cv.create_oval(x + cell * 0.2, y + cell * 0.2,
                                       x + cell * 0.8, y + cell * 0.8,
                                       fill=ACCENT, outline=ACCENT)
                elif v == "$":
                    cv.create_rectangle(x, y, x + cell, y + cell, fill=BG,
                                        outline=MUTED)
                    cv.create_oval(x + cell * 0.2, y + cell * 0.2,
                                   x + cell * 0.8, y + cell * 0.8,
                                   fill=DANGER, outline=DANGER)
        cv.create_text(w / 2, 14,
                       text="把箱子推到目标点" + (" 完成！" if self._win()
                                                 else ""),
                       fill=ACCENT, font=FONT_SMALL)


@_reg
class GameSudoku(MiniGame):
    GAME_NAME = "四宫数独"
    GAME_CAT = "棋盘"

    def _build(self):
        self.n = 4
        self.solution = self._gen()
        self.board = [row[:] for row in self.solution]
        # 挖空
        empties = random.sample(range(16), 8)
        for i in empties:
            self.board[i // 4][i % 4] = 0
        self.sel = None
        self.cv = self._make_canvas()
        self.cv.bind("<Button-1>", self._tap)
        self._num_pad(self.body, self._fill, range(1, 5), extra=["清除"])
        self._draw()

    def _gen(self):
        grid = [[0] * 4 for _ in range(4)]
        nums = list(range(1, 5))

        def ok(r, c, v):
            for i in range(4):
                if grid[r][i] == v or grid[i][c] == v:
                    return False
            br, bc = (r // 2) * 2, (c // 2) * 2
            for i in range(2):
                for j in range(2):
                    if grid[br + i][bc + j] == v:
                        return False
            return True

        def fill(pos):
            if pos == 16:
                return True
            r, c = divmod(pos, 4)
            for v in random.sample(nums, 4):
                if ok(r, c, v):
                    grid[r][c] = v
                    if fill(pos + 1):
                        return True
                    grid[r][c] = 0
            return False

        fill(0)
        return grid

    def _tap(self, e):
        w = _cw()
        cell = w / self.n
        c = int(e.x // cell)
        r = int((e.y - getattr(self, "_sy", 0)) // cell)
        if 0 <= r < self.n and 0 <= c < self.n and self.board[r][c] == 0:
            self.sel = (r, c)
            self._draw()

    def _fill(self, v):
        if self.sel is None:
            return
        r, c = self.sel
        if v == "清除":
            self.board[r][c] = 0
        else:
            self.board[r][c] = v
        self.sel = None
        self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 80
        cell = w / self.n
        size = cell * self.n
        ox = 0
        oy = (h - size) // 2 + 6
        self._sx, self._sy, self._sc = ox, oy, cell
        solved = all(self.board[r][c] == self.solution[r][c]
                     for r in range(4) for c in range(4))
        for r in range(4):
            for c in range(4):
                x = ox + c * cell
                y = oy + r * cell
                fill = SURFACE if (r, c) == self.sel else BG
                cv.create_rectangle(x + 1, y + 1, x + cell - 1, y + cell - 1,
                                    fill=fill, outline=MUTED)
                if self.board[r][c]:
                    cv.create_text(x + cell / 2, y + cell / 2,
                                   text=str(self.board[r][c]), fill=TEXT,
                                   font=FONT_NORMAL)
            cv.create_line(ox, oy + (r + 1) * cell, ox + size,
                           oy + (r + 1) * cell, fill=ACCENT, width=2)
        for c in range(4):
            cv.create_line(ox + (c + 1) * cell, oy, ox + (c + 1) * cell,
                           oy + size, fill=ACCENT, width=2)
        cv.create_text(w / 2, 14,
                       text="点空格选数字" + (" 完成！" if solved else ""),
                       fill=ACCENT, font=FONT_SMALL)


@_reg
class GameMaze(MiniGame):
    GAME_NAME = "走迷宫"
    GAME_CAT = "棋盘"

    def _build(self):
        self.n = 11
        self._reset()

    def _reset(self):
        self.grid = self._gen()
        self.px, self.py = 1, 1
        if hasattr(self, "cv"):
            self._draw()
            return
        self.cv = self._make_canvas()
        self.cv.bind("<Button-1>", self._tap)
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        for t, d in [("↑", (0, -1)), ("↓", (0, 1)), ("←", (-1, 0)), ("→", (1, 0))]:
            ttk.Button(nav, text=t, style="UH.TButton",
                       command=lambda x=d: self._move(x)).pack(
                side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(nav, text="重开", style="UH.TButton",
                   command=self._reset).pack(side=tk.LEFT, expand=True,
                                             fill=tk.X, padx=2)
        self.bind("<Up>", lambda e: self._move((0, -1)))
        self.bind("<Down>", lambda e: self._move((0, 1)))
        self.bind("<Left>", lambda e: self._move((-1, 0)))
        self.bind("<Right>", lambda e: self._move((1, 0)))
        self._draw()

    def _gen(self):
        n = self.n
        g = [[1] * n for _ in range(n)]

        def carve(x, y):
            g[y][x] = 0
            for dx, dy in random.sample([(0, -2), (0, 2), (-2, 0), (2, 0)], 4):
                nx, ny = x + dx, y + dy
                if 0 <= nx < n and 0 <= ny < n and g[ny][nx] == 1:
                    g[(y + ny) // 2][(x + nx) // 2] = 0
                    carve(nx, ny)

        carve(1, 1)
        g[n - 2][n - 2] = 0
        return g

    def _move(self, d):
        nx, ny = self.px + d[0], self.py + d[1]
        if 0 <= nx < self.n and 0 <= ny < self.n and self.grid[ny][nx] == 0:
            self.px, self.py = nx, ny
            self._draw()

    def _tap(self, e):
        w = _cw()
        cell = getattr(self, "_mc", w / self.n)
        c = int((e.x - getattr(self, "_mx", 0)) // cell)
        r = int((e.y - getattr(self, "_my", 0)) // cell)
        if 0 <= r < self.n and 0 <= c < self.n and self.grid[r][c] == 0:
            # 点相邻可走格直接移动
            if abs(r - self.py) + abs(c - self.px) == 1:
                self.px, self.py = c, r
                self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        cell = min(w, h - 20) / self.n
        size = cell * self.n
        ox = (w - size) / 2
        oy = 20
        self._mx, self._my, self._mc = ox, oy, cell
        for r in range(self.n):
            for c in range(self.n):
                x = ox + c * cell
                y = oy + r * cell
                if self.grid[r][c] == 1:
                    cv.create_rectangle(x, y, x + cell, y + cell,
                                        fill=SURFACE2, outline=SURFACE2)
        # 终点
        cv.create_rectangle(ox + (self.n - 2) * cell, oy + (self.n - 2) * cell,
                            ox + (self.n - 1) * cell, oy + (self.n - 1) * cell,
                            fill=ACCENT, outline=ACCENT)
        # 玩家
        cv.create_oval(ox + self.px * cell + cell * 0.2,
                       oy + self.py * cell + cell * 0.2,
                       ox + self.px * cell + cell * 0.8,
                       oy + self.py * cell + cell * 0.8,
                       fill=DANGER, outline=DANGER)
        if self.px == self.n - 2 and self.py == self.n - 2:
            cv.create_text(w / 2, 14, text="到达终点，胜利！",
                           fill=ACCENT, font=FONT_NORMAL)
        else:
            cv.create_text(w / 2, 14, text="从起点走到右下角",
                           fill=ACCENT, font=FONT_SMALL)


@_reg
class GameHangman(MiniGame):
    GAME_NAME = "猜单词"
    GAME_CAT = "棋盘"

    WORDS = ["PYTHON", "TIGER", "APPLE", "ROBOT", "PLANET", "DRAGON",
             "GUITAR", "PENCIL", "WINDOW", "CASTLE", "GARDEN", "BOTTLE"]

    def _build(self):
        self.word = random.choice(self.WORDS)
        self.guessed = set()
        self.wrong = 0
        self.maxwrong = 6
        self.cv = self._make_canvas()
        self._build_keys()
        self._draw()

    def _build_keys(self):
        f = tk.Frame(self.body, bg=BG)
        f.pack(fill=tk.X)
        rowf = None
        for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            if i % 7 == 0:
                rowf = tk.Frame(f, bg=BG)
                rowf.pack(fill=tk.X)
            ttk.Button(rowf, text=ch, style="UH.Num.TButton",
                       command=lambda x=ch: self._guess(x)).pack(
                side=tk.LEFT, expand=True, fill=tk.X, padx=1, pady=1)

    def _guess(self, ch):
        if ch in self.guessed or self.wrong >= self.maxwrong:
            return
        self.guessed.add(ch)
        if ch not in self.word:
            self.wrong += 1
        self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 120
        display = " ".join(c if c in self.guessed else "_" for c in self.word)
        cv.create_text(w / 2, 20, text=display, fill=TEXT,
                       font=(FONT_NORMAL[0], 18, "bold"))
        # 小人
        base_y = h * 0.7
        cv.create_line(w * 0.3, base_y, w * 0.3, h * 0.2, fill=MUTED)
        cv.create_line(w * 0.3, h * 0.2, w * 0.5, h * 0.2, fill=MUTED)
        cv.create_line(w * 0.5, h * 0.2, w * 0.5, h * 0.28, fill=MUTED)
        parts = [
            lambda: cv.create_oval(w * 0.46, h * 0.28, w * 0.54, h * 0.36,
                                   outline=TEXT),
            lambda: cv.create_line(w * 0.5, h * 0.36, w * 0.5, h * 0.5,
                                   fill=TEXT),
            lambda: cv.create_line(w * 0.5, h * 0.4, w * 0.44, h * 0.46,
                                   fill=TEXT),
            lambda: cv.create_line(w * 0.5, h * 0.4, w * 0.56, h * 0.46,
                                   fill=TEXT),
            lambda: cv.create_line(w * 0.5, h * 0.5, w * 0.45, h * 0.6,
                                   fill=TEXT),
            lambda: cv.create_line(w * 0.5, h * 0.5, w * 0.55, h * 0.6,
                                   fill=TEXT),
        ]
        for i in range(self.wrong):
            parts[i]()
        won = all(c in self.guessed for c in self.word)
        if won:
            cv.create_text(w / 2, h * 0.85, text="猜对了！", fill=ACCENT,
                           font=FONT_NORMAL)
        elif self.wrong >= self.maxwrong:
            cv.create_text(w / 2, h * 0.85, text=f"答案是 {self.word}",
                           fill=DANGER, font=FONT_NORMAL)


# ===================== 街机类 =====================
@_reg
class GameSnake(MiniGame):
    GAME_NAME = "贪吃蛇"
    GAME_CAT = "街机"

    def _build(self):
        self.cols = 20
        self.rows = 20
        self.cell = min(_cw() // self.cols, (_ch() - 60) // self.rows)
        self.snake = [(10, 10)]
        self.dir = (1, 0)
        self.food = self._newfood()
        self.alive = True
        self.score = 0
        self.cv = self._make_canvas()
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        for t, d in [("←", (-1, 0)), ("↑", (0, -1)), ("↓", (0, 1)), ("→", (1, 0))]:
            ttk.Button(nav, text=t, style="UH.TButton",
                       command=lambda x=d: self._set(x)).pack(
                side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self.bind("<Left>", lambda e: self._set((-1, 0)))
        self.bind("<Right>", lambda e: self._set((1, 0)))
        self.bind("<Up>", lambda e: self._set((0, -1)))
        self.bind("<Down>", lambda e: self._set((0, 1)))
        self._loop()

    def _newfood(self):
        while True:
            p = (random.randint(0, self.cols - 1),
                 random.randint(0, self.rows - 1))
            if p not in self.snake:
                return p

    def _set(self, d):
        if (d[0] * -1, d[1] * -1) != self.dir:
            self.dir = d

    def _loop(self):
        if not self.winfo_exists():
            return
        if not self._alive:
            return
        if self.alive:
            h = self.snake[0]
            nx, ny = h[0] + self.dir[0], h[1] + self.dir[1]
            if nx < 0 or ny < 0 or nx >= self.cols or ny >= self.rows or \
                    (nx, ny) in self.snake:
                self.alive = False
            else:
                self.snake.insert(0, (nx, ny))
                if (nx, ny) == self.food:
                    self.score += 1
                    self.food = self._newfood()
                else:
                    self.snake.pop()
        self._draw()
        self.after(140, self._loop)

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 60
        ox = (w - self.cols * self.cell) / 2
        oy = 6
        for (x, y) in self.snake:
            cv.create_rectangle(ox + x * self.cell, oy + y * self.cell,
                                ox + x * self.cell + self.cell - 1,
                                oy + y * self.cell + self.cell - 1,
                                fill=ACCENT, outline=BG)
        fx, fy = self.food
        cv.create_rectangle(ox + fx * self.cell, oy + fy * self.cell,
                            ox + fx * self.cell + self.cell - 1,
                            oy + fy * self.cell + self.cell - 1,
                            fill=DANGER, outline=BG)
        cv.create_text(w / 2, h - 12,
                       text=f"长度 {self.score + 1}" + ("" if self.alive
                                                        else "  撞了！返回重玩"),
                       fill=ACCENT, font=FONT_SMALL)


@_reg
class GameTetris(MiniGame):
    GAME_NAME = "俄罗斯方块"
    GAME_CAT = "街机"

    SHAPES = {
        'I': [[1, 1, 1, 1]],
        'O': [[1, 1], [1, 1]],
        'T': [[0, 1, 0], [1, 1, 1]],
        'S': [[0, 1, 1], [1, 1, 0]],
        'Z': [[1, 1, 0], [0, 1, 1]],
        'J': [[1, 0, 0], [1, 1, 1]],
        'L': [[0, 0, 1], [1, 1, 1]],
    }
    COLORS = {'I': "#06d6a0", 'O': "#ffd166", 'T': "#c77dff", 'S': "#80ed99",
              'Z': "#ef476f", 'J': "#00b4d8", 'L': "#fb8500"}

    def _build(self):
        self.cols = 10
        self.rows = 18
        self.board = [[0] * self.cols for _ in range(self.rows)]
        self.score = 0
        self.alive = True
        self._new()
        self.cv = self._make_canvas()
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        for t, cmd in [("←", lambda: self._mv(-1)), ("→", lambda: self._mv(1)),
                       ("↓", self._down), ("↻", self._rot)]:
            ttk.Button(nav, text=t, style="UH.TButton", command=cmd).pack(
                side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self.bind("<Left>", lambda e: self._mv(-1))
        self.bind("<Right>", lambda e: self._mv(1))
        self.bind("<Down>", lambda e: self._down())
        self.bind("<Up>", lambda e: self._rot())
        # 在棋盘上滑动手势：上滑旋转，左右下滑移动/下落
        self.cv.bind("<ButtonPress-1>", self._swipe_start)
        self.cv.bind("<ButtonRelease-1>", self._swipe_end)
        self._loop()

    def _swipe_start(self, e):
        self._sx, self._sy = e.x, e.y

    def _swipe_end(self, e):
        if not self.alive or not hasattr(self, "_sx"):
            return
        dx, dy = e.x - self._sx, e.y - self._sy
        if abs(dx) < 18 and abs(dy) < 18:
            return
        if abs(dy) > abs(dx):
            if dy < 0:
                self._rot()
            else:
                self._down()
        else:
            self._mv(1 if dx > 0 else -1)

    def _new(self):
        self.shape = random.choice(list(self.SHAPES))
        self.mat = [row[:] for row in self.SHAPES[self.shape]]
        self.x = self.cols // 2 - 1
        self.y = 0
        if self._collide(self.x, self.y, self.mat):
            self.alive = False

    def _collide(self, x, y, mat):
        for r in range(len(mat)):
            for c in range(len(mat[0])):
                if mat[r][c]:
                    nx, ny = x + c, y + r
                    if nx < 0 or nx >= self.cols or ny >= self.rows:
                        return True
                    if ny >= 0 and self.board[ny][nx]:
                        return True
        return False

    def _merge(self):
        for r in range(len(self.mat)):
            for c in range(len(self.mat[0])):
                if self.mat[r][c]:
                    ny, nx = self.y + r, self.x + c
                    if 0 <= ny < self.rows and 0 <= nx < self.cols:
                        self.board[ny][nx] = self.shape

    def _clear(self):
        new = [row for row in self.board if any(row)]
        cleared = self.rows - len(new)
        self.score += cleared * cleared * 10
        self.board = [[0] * self.cols for _ in range(cleared)] + new

    def _step(self):
        if self._collide(self.x, self.y + 1, self.mat):
            self._merge()
            self._clear()
            self._new()
        else:
            self.y += 1

    def _mv(self, d):
        if self._collide(self.x + d, self.y, self.mat):
            return
        self.x += d
        self._draw()

    def _down(self):
        while not self._collide(self.x, self.y + 1, self.mat):
            self.y += 1
        self._step()
        self._draw()

    def _rot(self):
        nm = [list(r) for r in zip(*self.mat[::-1])]
        if not self._collide(self.x, self.y, nm):
            self.mat = nm
            self._draw()

    def _loop(self):
        if not self.winfo_exists():
            return
        if not self._alive:
            return
        if self.alive:
            self._step()
        self._draw()
        self.after(420, self._loop)

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 60
        cell = min(w // self.cols, (h - 20) // self.rows)
        ox = (w - self.cols * cell) / 2
        oy = 16
        for r in range(self.rows):
            for c in range(self.cols):
                if self.board[r][c]:
                    cv.create_rectangle(ox + c * cell, oy + r * cell,
                                        ox + c * cell + cell - 1,
                                        oy + r * cell + cell - 1,
                                        fill=self.COLORS[self.board[r][c]],
                                        outline=BG)
        for r in range(len(self.mat)):
            for c in range(len(self.mat[0])):
                if self.mat[r][c]:
                    cv.create_rectangle(ox + (self.x + c) * cell,
                                        oy + (self.y + r) * cell,
                                        ox + (self.x + c) * cell + cell - 1,
                                        oy + (self.y + r) * cell + cell - 1,
                                        fill=self.COLORS[self.shape],
                                        outline=BG)
        cv.create_text(w / 2, 8, text=f"分数 {self.score}" + ("" if self.alive
                                                              else "  GAME OVER"),
                       fill=ACCENT, font=FONT_SMALL)


@_reg
class GameBreakout(MiniGame):
    GAME_NAME = "打砖块"
    GAME_CAT = "街机"

    def _build(self):
        self.cv = self._make_canvas()
        w = _cw()
        h = _ch()
        self.W, self.H = w, h
        self.px = w / 2
        self.pw = 44
        self.bx = w / 2
        self.by = h - 60
        self.bvx = 3
        self.bvy = -3
        self.bricks = []
        for r in range(4):
            for c in range(6):
                self.bricks.append([c * (w / 6) + 4, 30 + r * 16,
                                     (c + 1) * (w / 6) - 4, 30 + r * 16 + 12])
        self.over = False
        self.win = False
        self.cv.bind("<Button-1>", self._aim)
        self.bind("<Left>", lambda e: self._move_p(-20))
        self.bind("<Right>", lambda e: self._move_p(20))
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        ttk.Button(nav, text="◀", style="UH.TButton",
                   command=lambda: self._move_p(-20)).pack(side=tk.LEFT,
                                                          expand=True, fill=tk.X)
        ttk.Button(nav, text="▶", style="UH.TButton",
                   command=lambda: self._move_p(20)).pack(side=tk.LEFT,
                                                          expand=True, fill=tk.X)
        self._loop()

    def _aim(self, e):
        self.px = e.x

    def _move_p(self, d):
        self.px = max(self.pw / 2, min(self.W - self.pw / 2, self.px + d))

    def _loop(self):
        if not self.winfo_exists():
            return
        if not self._alive or self.over or self.win:
            return
        self.bx += self.bvx
        self.by += self.bvy
        if self.bx < 4 or self.bx > self.W - 4:
            self.bvx *= -1
        if self.by < 4:
            self.bvy *= -1
        if self.by > self.H - 4:
            self.over = True
        # 挡板
        if self.by + 4 >= self.H - 50 and abs(self.bx - self.px) < self.pw / 2 \
                and self.bvy > 0:
            self.bvy *= -1
        # 砖块
        for b in self.bricks:
            if b and b[0] < self.bx < b[2] and b[1] < self.by < b[3]:
                self.bvy *= -1
                self.bricks[self.bricks.index(b)] = None
                break
        if all(not b for b in self.bricks):
            self.win = True
        self._draw()
        self.after(20, self._loop)

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        for b in self.bricks:
            if b:
                cv.create_rectangle(b[0], b[1], b[2], b[3], fill=ACCENT2,
                                    outline=BG)
        cv.create_rectangle(self.px - self.pw / 2, self.H - 50,
                            self.px + self.pw / 2, self.H - 44, fill=ACCENT,
                            outline=BG)
        cv.create_oval(self.bx - 4, self.by - 4, self.bx + 4, self.by + 4,
                       fill=DANGER, outline=DANGER)
        msg = "胜利！" if self.win else ("失败，返回重玩" if self.over else
                                         "点屏移动挡板")
        cv.create_text(self.W / 2, 14, text=msg, fill=ACCENT, font=FONT_SMALL)


@_reg
class GamePong(MiniGame):
    GAME_NAME = "弹球对战"
    GAME_CAT = "街机"

    def _build(self):
        self.cv = self._make_canvas()
        w = _cw()
        h = _ch()
        self.W, self.H = w, h
        self.px = w / 2
        self.pw = 44
        self.ay = 40
        self.ah = 8
        self.bx = w / 2
        self.by = h / 2
        self.bvx = 3
        self.bvy = 2
        self.score = 0
        self.over = False
        self.cv.bind("<Button-1>", self._aim)
        self.bind("<Left>", lambda e: self._move_p(-20))
        self.bind("<Right>", lambda e: self._move_p(20))
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        ttk.Button(nav, text="◀", style="UH.TButton",
                   command=lambda: self._move_p(-20)).pack(side=tk.LEFT,
                                                          expand=True, fill=tk.X)
        ttk.Button(nav, text="▶", style="UH.TButton",
                   command=lambda: self._move_p(20)).pack(side=tk.LEFT,
                                                          expand=True, fill=tk.X)
        self._loop()

    def _aim(self, e):
        self.px = e.x

    def _move_p(self, d):
        self.px = max(self.pw / 2, min(self.W - self.pw / 2, self.px + d))

    def _loop(self):
        if not self.winfo_exists():
            return
        if not self._alive or self.over:
            return
        self.bx += self.bvx
        self.by += self.bvy
        if self.bx < 4 or self.bx > self.W - 4:
            self.bvx *= -1
        # 电脑挡板（顶部）简单跟随
        if self.bx > self.W / 2:
            self.ay = min(self.W - self.pw, self.ay + 3)
        else:
            self.ay = max(0, self.ay - 3)
        if self.by < 10 and abs(self.bx - (self.ay + self.pw / 2)) < self.pw / 2:
            self.bvy *= -1
        if self.by > self.H - 10 and abs(self.bx - self.px) < self.pw / 2 \
                and self.bvy > 0:
            self.bvy *= -1
            self.score += 1
        if self.by > self.H:
            self.over = True
        self._draw()
        self.after(20, self._loop)

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        cv.create_rectangle(self.ay, 4, self.ay + self.pw, 4 + self.ah,
                            fill=ACCENT2, outline=BG)
        cv.create_rectangle(self.px - self.pw / 2, self.H - 14,
                            self.px + self.pw / 2, self.H - 8, fill=ACCENT,
                            outline=BG)
        cv.create_oval(self.bx - 4, self.by - 4, self.bx + 4, self.by + 4,
                       fill=DANGER, outline=DANGER)
        cv.create_text(self.W / 2, 18, text=f"得分 {self.score}" + (
            "" if not self.over else "  GAME OVER"),
                       fill=ACCENT, font=FONT_SMALL)


@_reg
class GameCatch(MiniGame):
    GAME_NAME = "接水果"
    GAME_CAT = "街机"

    def _build(self):
        self.cv = self._make_canvas()
        w = _cw()
        h = _ch()
        self.W, self.H = w, h
        self.px = w / 2
        self.pw = 40
        self.fruits = []
        self.score = 0
        self.t = 0
        self.cv.bind("<Button-1>", self._aim)
        self.bind("<Left>", lambda e: self._move_p(-24))
        self.bind("<Right>", lambda e: self._move_p(24))
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        ttk.Button(nav, text="◀", style="UH.TButton",
                   command=lambda: self._move_p(-24)).pack(side=tk.LEFT,
                                                          expand=True, fill=tk.X)
        ttk.Button(nav, text="▶", style="UH.TButton",
                   command=lambda: self._move_p(24)).pack(side=tk.LEFT,
                                                          expand=True, fill=tk.X)
        self._loop()

    def _aim(self, e):
        self.px = e.x

    def _move_p(self, d):
        self.px = max(self.pw / 2, min(self.W - self.pw / 2, self.px + d))

    def _loop(self):
        if not self.winfo_exists():
            return
        if not self._alive:
            return
        self.t += 1
        if self.t % 18 == 0:
            self.fruits.append([random.randint(10, self.W - 10), 0,
                                random.choice(["#ef476f", "#06d6a0",
                                               "#ffd166", "#c77dff"])])
        for f in self.fruits:
            f[1] += 4
        keep = []
        for f in self.fruits:
            if f[1] > self.H - 16 and abs(f[0] - self.px) < self.pw / 2:
                self.score += 1
            elif f[1] < self.H:
                keep.append(f)
        self.fruits = keep
        self._draw()
        self.after(25, self._loop)

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        for f in self.fruits:
            cv.create_oval(f[0] - 7, f[1] - 7, f[0] + 7, f[1] + 7, fill=f[2],
                           outline=f[2])
        cv.create_rectangle(self.px - self.pw / 2, self.H - 16,
                            self.px + self.pw / 2, self.H - 8, fill=ACCENT,
                            outline=BG)
        cv.create_text(self.W / 2, 14, text=f"接到 {self.score} 个",
                       fill=ACCENT, font=FONT_SMALL)


@_reg
class GameShoot(MiniGame):
    GAME_NAME = "打飞机"
    GAME_CAT = "街机"

    def _build(self):
        self.cv = self._make_canvas()
        w = _cw()
        h = _ch()
        self.W, self.H = w, h
        self.px = w / 2
        self.bullets = []
        self.enemies = []
        self.score = 0
        self.t = 0
        self.cv.bind("<Button-1>", self._fire)
        self.bind("<Left>", lambda e: self._move_p(-24))
        self.bind("<Right>", lambda e: self._move_p(24))
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        ttk.Button(nav, text="◀", style="UH.TButton",
                   command=lambda: self._move_p(-24)).pack(side=tk.LEFT,
                                                          expand=True, fill=tk.X)
        ttk.Button(nav, text="▶", style="UH.TButton",
                   command=lambda: self._move_p(24)).pack(side=tk.LEFT,
                                                          expand=True, fill=tk.X)
        ttk.Button(nav, text="开火", style="UH.TButton",
                   command=self._fire).pack(side=tk.LEFT, expand=True,
                                            fill=tk.X)
        self._loop()

    def _move_p(self, d):
        self.px = max(12, min(self.W - 12, self.px + d))

    def _fire(self, e=None):
        self.bullets.append([self.px, self.H - 30])

    def _loop(self):
        if not self.winfo_exists():
            return
        if not self._alive:
            return
        self.t += 1
        if self.t % 30 == 0:
            self.enemies.append([random.randint(10, self.W - 10), 0])
        for b in self.bullets:
            b[1] -= 8
        for e in self.enemies:
            e[1] += 3
        hit = []
        for e in self.enemies:
            er = e[1]
            for b in self.bullets:
                if abs(b[0] - e[0]) < 10 and abs(b[1] - e[1]) < 10:
                    hit.append((e, b))
        for e, b in hit:
            if e in self.enemies:
                self.enemies.remove(e)
            if b in self.bullets:
                self.bullets.remove(b)
            self.score += 1
        self.bullets = [b for b in self.bullets if b[1] > 0]
        self.enemies = [e for e in self.enemies if e[1] < self.H]
        self._draw()
        self.after(25, self._loop)

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        for b in self.bullets:
            cv.create_rectangle(b[0] - 1, b[1] - 5, b[0] + 1, b[1] + 5,
                                fill=ACCENT, outline=ACCENT)
        for e in self.enemies:
            cv.create_rectangle(e[0] - 8, e[1] - 6, e[0] + 8, e[1] + 6,
                                fill=DANGER, outline=DANGER)
        cv.create_polygon(self.px, self.H - 26, self.px - 10, self.H - 12,
                          self.px + 10, self.H - 12, fill=ACCENT2,
                          outline=ACCENT2)
        cv.create_text(self.W / 2, 14, text=f"击落 {self.score}",
                       fill=ACCENT, font=FONT_SMALL)


# ===================== 反应类 =====================
@_reg
class GameWhack(MiniGame):
    GAME_NAME = "打地鼠"
    GAME_CAT = "反应"

    def _build(self):
        self.n = 3
        self.moles = [False] * 9
        self.score = 0
        self.time = 30
        self.cv = self._make_canvas()
        self.cv.bind("<Button-1>", self._tap)
        self._loop()
        self._timer()

    def _timer(self):
        if not self.winfo_exists():
            return
        if not self._alive:
            return
        self.time -= 1
        if self.time <= 0:
            self._draw(True)
            return
        self.after(1000, self._timer)

    def _loop(self):
        if not self.winfo_exists():
            return
        if not self._alive or self.time <= 0:
            return
        self.moles = [random.random() < 0.3 for _ in range(9)]
        self._draw()
        self.after(700, self._loop)

    def _tap(self, e):
        if self.time <= 0:
            return
        w = _cw()
        cell = w / self.n
        c = int(e.x // cell)
        r = int((e.y - getattr(self, "_wy", 0)) // cell)
        if 0 <= r < self.n and 0 <= c < self.n and self.moles[r * self.n + c]:
            self.score += 1
            self.moles[r * self.n + c] = False
            self._draw()

    def _draw(self, stop=False):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        cell = w / self.n
        size = cell * self.n
        ox = 0
        oy = (h - size) // 2 + 6
        self._wx, self._wy, self._wc = ox, oy, cell
        for i in range(9):
            r, c = divmod(i, self.n)
            x = ox + c * cell
            y = oy + r * cell
            if self.moles[i]:
                cv.create_oval(x + cell * 0.2, y + cell * 0.2,
                               x + cell * 0.8, y + cell * 0.8, fill=DANGER,
                               outline=DANGER)
            else:
                cv.create_rectangle(x + cell * 0.25, y + cell * 0.4,
                                    x + cell * 0.75, y + cell * 0.85,
                                    fill=SURFACE2, outline=MUTED)
        cv.create_text(w / 2, 16,
                       text=f"得分 {self.score}  时间 {max(0, self.time)}s" +
                       ("  结束！" if stop else ""),
                       fill=ACCENT, font=FONT_SMALL)


@_reg
class GameStroop(MiniGame):
    GAME_NAME = "见色说字"
    GAME_CAT = "反应"

    COLORS = {"红": "#ef476f", "绿": "#06d6a0", "蓝": "#00b4d8",
              "黄": "#ffd166", "紫": "#c77dff"}

    def _build(self):
        self.score = 0
        self.q = 0
        self.cv = self._make_canvas()
        self._next()
        self._draw()

    def _next(self):
        names = list(self.COLORS)
        self.word = random.choice(names)
        self.ink = random.choice(names)
        opts = random.sample(names, 4)
        if self.ink not in opts:
            opts[0] = self.ink
        random.shuffle(opts)
        self.opts = opts

    def _choose(self, name):
        self.q += 1
        if name == self.ink:
            self.score += 1
        else:
            self.score -= 1
        self._next()
        self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        cv.create_text(w / 2, 20, text=f"得分 {self.score}  第{self.q + 1}题",
                       fill=ACCENT, font=FONT_SMALL)
        cv.create_text(w / 2, h * 0.28, text=self.word,
                       fill=self.COLORS[self.ink],
                       font=(FONT_NORMAL[0], 30, "bold"))
        cv.create_text(w / 2, h * 0.4, text="点『墨色』", fill=MUTED,
                       font=FONT_SMALL)
        bw = w / 2 - 10
        bh = 36
        for i, name in enumerate(self.opts):
            x = 8 + (i % 2) * (bw + 4)
            y = h * 0.5 + (i // 2) * (bh + 6)
            cv.create_rectangle(x, y, x + bw, y + bh, fill=SURFACE2,
                                outline=ACCENT)
            cv.create_text(x + bw / 2, y + bh / 2, text=name,
                           fill=self.COLORS[name], font=FONT_NORMAL)
            cv.tag_bind(cv.create_rectangle(x, y, x + bw, y + bh, fill="",
                            outline=""), "<Button-1>",
                        lambda e, nm=name: self._choose(nm))


@_reg
class GameReaction(MiniGame):
    GAME_NAME = "反应速度"
    GAME_CAT = "反应"

    def _build(self):
        self.cv = self._make_canvas()
        self.state = "wait"
        self.t0 = 0
        self.best = None
        self.cv.bind("<Button-1>", self._tap)
        self._draw()

    def _tap(self, e):
        if self.state == "wait":
            self.state = "go"
            self.t0 = time.time()
            self.after(random.randint(800, 2500), self._green)
        elif self.state == "go":
            dt = int((time.time() - self.t0) * 1000)
            if self.best is None or dt < self.best:
                self.best = dt
            self.state = "wait"
            self._draw(dt)
        elif self.state == "early":
            self.state = "wait"
            self._draw()

    def _green(self):
        if not self.winfo_exists():
            return
        if self.state == "go":
            self.state = "green"
            self._draw()

    def _draw(self, last=None):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        col = {"wait": SURFACE2, "go": DANGER, "green": "#06d6a0",
               "early": "#ffd166"}[self.state]
        cv.create_rectangle(0, 0, w, h, fill=col, outline=col)
        txt = {
            "wait": "点屏幕，变绿再点",
            "go": "太快了！等变绿",
            "green": "快点点屏幕！",
            "early": "别抢跑，重来",
        }[self.state]
        cv.create_text(w / 2, h / 2, text=txt, fill=TEXT, font=FONT_NORMAL)
        if last is not None:
            cv.create_text(w / 2, h / 2 - 40, text=f"{last} ms",
                           fill=TEXT, font=(FONT_NORMAL[0], 22, "bold"))
        if self.best is not None:
            cv.create_text(w / 2, h - 20, text=f"最佳 {self.best} ms",
                           fill=TEXT, font=FONT_SMALL)


@_reg
class GameSimon(MiniGame):
    GAME_NAME = "记忆顺序"
    GAME_CAT = "反应"

    def _build(self):
        self.colors = [DANGER, "#06d6a0", ACCENT, "#ffd166"]
        self.seq = []
        self.input = []
        self.showing = False
        self.cv = self._make_canvas()
        self.cv.bind("<Button-1>", self._tap)
        ttk.Button(self.body, text="开始", style="UH.TButton",
                   command=self._add).pack(fill=tk.X, padx=8, pady=4)
        self._draw()

    def _add(self):
        if self.showing:
            return
        self.seq.append(random.randint(0, 3))
        self.input = []
        self.showing = True
        self._show()

    def _flash(self, i):
        if not self.winfo_exists():
            return
        self._draw(highlight=i)
        self.after(300, lambda: self._draw())

    def _tap(self, e):
        if self.showing or not self.seq:
            return
        w = _cw()
        cell = w / 2
        c = int(e.x // cell)
        r = int((e.y - getattr(self, "_sy", 0)) // cell)
        i = (r * 2 + c) if 0 <= r < 2 and 0 <= c < 2 else -1
        if i < 0:
            return
        self.input.append(i)
        self._flash(i)
        if self.input != self.seq[:len(self.input)]:
            self.seq = []
            self.input = []
            self._draw(msg="错了！点开始重来")
        elif len(self.input) == len(self.seq):
            self._draw(msg="正确！点开始加长")

    def _draw(self, highlight=None, msg=None):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        cell = w / 2
        size = cell * 2
        ox = (w - size) / 2
        oy = (h - size) // 2 + 6
        self._sx, self._sy, self._sc = ox, oy, cell
        for i in range(4):
            r, c = divmod(i, 2)
            x = ox + c * cell
            y = oy + r * cell
            col = self.colors[i]
            if highlight == i:
                col = "#ffffff"
            cv.create_rectangle(x + 2, y + 2, x + cell - 2, y + cell - 2,
                                fill=col, outline=BG)
        cv.create_text(w / 2, 16,
                       text=msg or f"长度 {len(self.seq)}  记顺序点方块",
                       fill=ACCENT, font=FONT_SMALL)

    def _show(self):
        self._show_idx = 0
        self._run_show()

    def _run_show(self):
        if not self.winfo_exists():
            return
        if not self._alive or self._show_idx >= len(self.seq):
            self.showing = False
            self._draw()
            return
        i = self.seq[self._show_idx]
        self._flash(i)
        self._show_idx += 1
        self.after(600, self._run_show)


@_reg
class GameNumberGuess(MiniGame):
    GAME_NAME = "猜数字"
    GAME_CAT = "反应"

    def _build(self):
        self.ans = random.randint(1, 100)
        self.tries = 0
        self.done = False
        self.cv = self._make_canvas()
        self.guess = tk.StringVar(value="")
        self.entry = tk.Entry(self.body, textvariable=self.guess, bg=SURFACE2,
                              fg=TEXT, font=FONT_NORMAL, insertbackground=TEXT)
        self.entry.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(self.body, text="猜！", style="UH.TButton",
                   command=self._check).pack(fill=tk.X, padx=8, pady=4)
        self._num_pad(self.body, self._digit, range(0, 10), extra=["清除"])
        self._draw()

    def _digit(self, d):
        if d == "清除":
            self.guess.set("")
        else:
            cur = self.guess.get()
            if len(cur) < 3:
                self.guess.set(cur + str(d))

    def _check(self):
        if self.done:
            return
        try:
            v = int(self.guess.get())
        except ValueError:
            return
        self.tries += 1
        if v == self.ans:
            self.done = True
            self.msg = f"猜中了！用了 {self.tries} 次"
        elif v < self.ans:
            self.msg = "大一点 ↑"
        else:
            self.msg = "小一点 ↓"
        self.guess.set("")
        self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 120
        cv.create_text(w / 2, 20, text="1~100 猜数字", fill=ACCENT,
                       font=FONT_NORMAL)
        cv.create_text(w / 2, h / 2, text=getattr(self, "msg", "输入数字后点猜"),
                       fill=TEXT, font=(FONT_NORMAL[0], 18, "bold"))


@_reg
class GameBlackjack(MiniGame):
    GAME_NAME = "21点"
    GAME_CAT = "反应"

    def _build(self):
        self.cv = self._make_canvas()
        self._deal()
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        ttk.Button(nav, text="要牌", style="UH.TButton",
                   command=self._hit).pack(side=tk.LEFT, expand=True,
                                           fill=tk.X, padx=2)
        ttk.Button(nav, text="停牌", style="UH.TButton",
                   command=self._stand).pack(side=tk.LEFT, expand=True,
                                             fill=tk.X, padx=2)
        ttk.Button(nav, text="重开", style="UH.TButton",
                   command=self._deal).pack(side=tk.LEFT, expand=True,
                                            fill=tk.X, padx=2)
        self._draw()

    def _deck(self):
        d = []
        for v in range(1, 14):
            for _ in range(4):
                d.append(min(v, 10) if v > 10 else v)
        random.shuffle(d)
        return d

    def _deal(self):
        self.deck = self._deck()
        self.player = [self.deck.pop(), self.deck.pop()]
        self.dealer = [self.deck.pop(), self.deck.pop()]
        self.over = False
        self.msg = ""
        self._draw()

    def _val(self, hand):
        s = sum(hand)
        aces = hand.count(1)
        while s + 10 <= 21 and aces > 0:
            s += 10
            aces -= 1
        return s

    def _hit(self):
        if self.over:
            return
        self.player.append(self.deck.pop())
        if self._val(self.player) > 21:
            self.over = True
            self.msg = "爆了，你输"
        self._draw()

    def _stand(self):
        if self.over:
            return
        while self._val(self.dealer) < 17:
            self.dealer.append(self.deck.pop())
        pv, dv = self._val(self.player), self._val(self.dealer)
        if dv > 21 or pv > dv:
            self.msg = "你赢！"
        elif pv < dv:
            self.msg = "你输"
        else:
            self.msg = "平局"
        self.over = True
        self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 60
        cv.create_text(w / 2, 14, text="你的牌", fill=ACCENT, font=FONT_SMALL)
        cv.create_text(w / 2, 34, text=str(self.player), fill=TEXT,
                       font=FONT_NORMAL)
        cv.create_text(w / 2, h * 0.5 - 14, text=f"你={self._val(self.player)}",
                       fill=TEXT, font=FONT_NORMAL)
        cv.create_text(w / 2, h * 0.5 + 6, text="电脑的牌", fill=ACCENT,
                       font=FONT_SMALL)
        cv.create_text(w / 2, h * 0.5 + 26,
                       text=(str(self.dealer) if self.over else "[? , ?]"),
                       fill=TEXT, font=FONT_NORMAL)
        if self.over:
            cv.create_text(w / 2, h - 16,
                           text=self.msg + f"  电脑={self._val(self.dealer)}",
                           fill=DANGER, font=FONT_NORMAL)


@_reg
class GameHighLow(MiniGame):
    GAME_NAME = "比大小"
    GAME_CAT = "反应"

    def _build(self):
        self.cv = self._make_canvas()
        self.score = 50
        self.cur = random.randint(1, 13)
        self._draw()
        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill=tk.X)
        ttk.Button(nav, text="更大", style="UH.TButton",
                   command=lambda: self._guess(True)).pack(side=tk.LEFT,
                                                          expand=True, fill=tk.X,
                                                          padx=2)
        ttk.Button(nav, text="更小", style="UH.TButton",
                   command=lambda: self._guess(False)).pack(side=tk.LEFT,
                                                           expand=True,
                                                           fill=tk.X, padx=2)

    def _guess(self, higher):
        nxt = random.randint(1, 13)
        ok = (nxt >= self.cur) if higher else (nxt <= self.cur)
        self.score += 10 if ok else -10
        self.cur = nxt
        if self.score <= 0:
            self.score = 0
        self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch() - 40
        cv.create_text(w / 2, 20, text=f"积分 {self.score}", fill=ACCENT,
                       font=FONT_NORMAL)
        cv.create_text(w / 2, h / 2, text=f"当前 {self.cur}",
                       fill=TEXT, font=(FONT_NORMAL[0], 26, "bold"))
        cv.create_text(w / 2, h - 24, text="下一张更大还是更小？",
                       fill=MUTED, font=FONT_SMALL)


@_reg
class GameLife(MiniGame):
    GAME_NAME = "生命游戏"
    GAME_CAT = "反应"

    def _build(self):
        self.n = 30
        self.g = [[random.random() < 0.3 for _ in range(self.n)]
                  for _ in range(self.n)]
        self.cv = self._make_canvas()
        self._loop()

    def _step(self):
        ng = [[False] * self.n for _ in range(self.n)]
        for r in range(self.n):
            for c in range(self.n):
                cnt = 0
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == dc == 0:
                            continue
                        nr, nc = (r + dr) % self.n, (c + dc) % self.n
                        cnt += self.g[nr][nc]
                ng[r][c] = cnt == 3 or (self.g[r][c] and cnt == 2)
        self.g = ng

    def _loop(self):
        if not self.winfo_exists():
            return
        if not self._alive:
            return
        self._step()
        self._draw()
        self.after(200, self._loop)

    def _draw(self):
        cv = self.cv
        cv.delete("all")
        w = _cw()
        h = _ch()
        cell = min(w, h) / self.n
        for r in range(self.n):
            for c in range(self.n):
                if self.g[r][c]:
                    cv.create_rectangle(c * cell, r * cell,
                                        c * cell + cell, r * cell + cell,
                                        fill=ACCENT, outline=ACCENT)


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    GameCenter(root)
    root.mainloop()
