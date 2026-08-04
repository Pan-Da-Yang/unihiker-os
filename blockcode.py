# -*- coding: utf-8 -*-
"""
行空板 OS - 图形化编程（积木式，控制板载硬件）
  · 调色板添加积木：引脚输出 / 蜂鸣 / 等待 / 循环。
  · 程序列表：每个积木一张卡片，可 ▲▼ 排序、✕ 删除、点选高亮。
  · 运行：按列表顺序在板子上执行（引脚高低、蜂鸣、延时、循环重复其后）；
         开发机无硬件时退化为「可视化模拟」（仅高亮，不出声不动）。
  · 循环积木：重复它「之后」的所有积木 N 次。
  · 板载 A 键停止运行。
"""
import time
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import theme
from theme import (
    BG, SURFACE, SURFACE2, HOVER, ACCENT, ACCENT2, DANGER, TEXT, MUTED,
    ON_ACCENT, FONT_NORMAL, FONT_SMALL, BOARD, apply_board_window,
)
import hwio

# 积木类型元信息：标签、配色
_KIND = {
    "out":  ("引脚输出", ACCENT),
    "buzz": ("蜂鸣", "#f4a261"),
    "wait": ("等待", "#8d99ae"),
    "loop": ("循环", ACCENT2),
}


class BlockCode(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("图形编程")
        self.configure(bg=BG)
        apply_board_window(self)
        self.master = master

        self.hw = hwio.ensure_hw()
        self.blocks = []          # 积木字典列表
        self._next_id = 1
        self._cards = {}          # _id -> 卡片 Frame
        self._running = False
        self._stop_flag = False
        self._run_id = 0
        self.repeat_n = 1
        self._q = queue.Queue()   # 线程→主线程 的 UI 更新桥（高亮/结束信号）

        self._build_ui()
        self._bind_board_key()
        if not self.hw:
            self.hw_lbl.config(text="无硬件(模拟)")
        self._rebuild()
        # 主线程轮询器：把工作线程丢进队列的高亮请求安全地应用到 UI
        self._poll_q()

    # ============ UI ============
    def _build_ui(self):
        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill=tk.X)
        px = 2 if BOARD else 4
        ttk.Button(bar, text="返回", command=lambda: self.destroy(),
                   style="UH.Danger.TButton").pack(side=tk.LEFT, padx=px, pady=4)
        tk.Label(bar, text="图形编程", bg=SURFACE, fg=TEXT,
                 font=FONT_NORMAL).pack(side=tk.LEFT, padx=2)
        self.hw_lbl = tk.Label(bar, text="", bg=SURFACE, fg=MUTED,
                               font=FONT_SMALL, anchor=tk.E)
        self.hw_lbl.pack(side=tk.RIGHT, padx=4)

        # 调色板
        pal = tk.Frame(self, bg=BG)
        pal.pack(fill=tk.X, pady=2)
        for kind in ("out", "buzz", "wait", "loop"):
            label, _ = _KIND[kind]
            ttk.Button(pal, text="+" + label, width=6,
                       command=lambda k=kind: self._ask(k),
                       style="UH.Num.TButton").pack(side=tk.LEFT, padx=1,
                                                     expand=True, fill=tk.X)

        # 程序列表（可滚动）
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.canvas.create_window((0, 0), window=self.inner, anchor=tk.NW)
        self.inner.bind("<Configure>", self._on_configure)

        # 运行栏
        run = tk.Frame(self, bg=BG)
        run.pack(fill=tk.X, pady=2)
        # 重复 N 次
        ttk.Button(run, text="−", width=3, command=lambda: self._step_repeat(-1),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=1)
        self.rep_lbl = tk.Label(run, text="×1", bg=BG, fg=TEXT,
                                font=FONT_SMALL, width=4, anchor=tk.CENTER)
        self.rep_lbl.pack(side=tk.LEFT, padx=1)
        ttk.Button(run, text="+", width=3, command=lambda: self._step_repeat(1),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=1)
        tk.Label(run, text="重复", bg=BG, fg=MUTED,
                 font=FONT_SMALL).pack(side=tk.LEFT, padx=2)
        self._run_btn = ttk.Button(run, text="运行", width=4, command=self._run,
                                    style="UH.TButton")
        self._run_btn.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ttk.Button(run, text="停止", width=4, command=self._stop,
                   style="UH.Danger.TButton").pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ttk.Button(run, text="清空", width=4, command=self._clear,
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)

        self._style()

    # ============ 参数对话框 ============
    def _ask(self, kind):
        d = tk.Toplevel(self)
        label, color = _KIND[kind]
        d.title(label)
        d.configure(bg=BG)
        apply_board_window(d)
        vars_ = {}
        body = tk.Frame(d, bg=BG)
        body.pack(padx=8, pady=8)

        if kind == "out":
            vars_["pin"] = tk.IntVar(value=0)
            vars_["val"] = tk.IntVar(value=1)
            self._stepper(body, "引脚", vars_["pin"], 0, 20, 1)
            # 高/低 切换
            row = tk.Frame(body, bg=BG)
            row.pack(fill=tk.X, pady=4)
            btn = tk.Button(row, text="高", bg=SURFACE, fg=ACCENT,
                            font=FONT_NORMAL, relief=tk.FLAT, width=8,
                            command=lambda: (vars_["val"].set(1), btn.config(text="高", fg=ACCENT)))
            btn.pack(side=tk.LEFT, padx=4)
            btn2 = tk.Button(row, text="低", bg=SURFACE2, fg=MUTED,
                             font=FONT_NORMAL, relief=tk.FLAT, width=8,
                             command=lambda: (vars_["val"].set(0), btn2.config(text="低", fg=MUTED)))
            btn2.pack(side=tk.LEFT, padx=4)
            # 备注：初始化为“高”
            btn.config(text="高", fg=ACCENT)
            btn2.config(text="低", fg=MUTED)
        elif kind == "buzz":
            vars_["freq"] = tk.IntVar(value=440)
            vars_["dur"] = tk.DoubleVar(value=0.3)
            self._stepper(body, "频率(Hz)", vars_["freq"], 50, 4000, 20)
            self._stepper(body, "时长(s)", vars_["dur"], 0.1, 10.0, 0.1)
        elif kind == "wait":
            vars_["sec"] = tk.DoubleVar(value=1.0)
            self._stepper(body, "时长(s)", vars_["sec"], 0.1, 30.0, 0.1)
        elif kind == "loop":
            vars_["n"] = tk.IntVar(value=2)
            self._stepper(body, "重复次数", vars_["n"], 1, 99, 1)

        foot = tk.Frame(d, bg=BG)
        foot.pack(fill=tk.X, pady=(4, 8), padx=8)
        ttk.Button(foot, text="确定", command=lambda: self._confirm(kind, vars_, d),
                   style="UH.TButton").pack(side=tk.RIGHT, padx=4)
        ttk.Button(foot, text="取消", command=lambda: d.destroy(),
                   style="UH.Num.TButton").pack(side=tk.RIGHT, padx=4)

    def _stepper(self, parent, name, var, lo, hi, step):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=name, bg=BG, fg=MUTED,
                 font=FONT_SMALL, width=10, anchor=tk.W).pack(side=tk.LEFT)
        ttk.Button(row, text="−", width=3,
                   command=lambda: self._stp(var, -step, lo, hi),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2)
        lbl = tk.Label(row, text=self._fmt(var.get()), bg=BG, fg=TEXT,
                       font=FONT_NORMAL, width=6, anchor=tk.CENTER)
        lbl.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="+", width=3,
                   command=lambda: self._stp(var, step, lo, hi),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2)
        # 让 label 跟随变量
        var.trace_add("write", lambda *a, l=lbl, v=var: l.config(text=self._fmt(v.get())))

    def _stp(self, var, d, lo, hi):
        cur = var.get()
        nxt = round(cur + d, 2)
        nxt = max(lo, min(hi, nxt))
        var.set(nxt)

    def _fmt(self, v):
        if isinstance(v, float):
            return ("%.2f" % v).rstrip("0").rstrip(".")
        return str(v)

    def _confirm(self, kind, vars_, dlg):
        b = {"type": kind, "_id": self._next_id}
        self._next_id += 1
        if kind == "out":
            b.update(pin=vars_["pin"].get(), val=vars_["val"].get())
        elif kind == "buzz":
            b.update(freq=vars_["freq"].get(), dur=vars_["dur"].get())
        elif kind == "wait":
            b.update(sec=vars_["sec"].get())
        elif kind == "loop":
            b.update(n=vars_["n"].get())
        self.blocks.append(b)
        dlg.destroy()
        self._rebuild()

    # ============ 程序列表 ============
    def _summary(self, b):
        if b["type"] == "out":
            return "引脚输出   P%d   %s" % (b["pin"], "高" if b["val"] else "低")
        if b["type"] == "buzz":
            return "蜂鸣   %dHz   %.1fs" % (b["freq"], b["dur"])
        if b["type"] == "wait":
            return "等待   %.1fs" % b["sec"]
        if b["type"] == "loop":
            return "循环   ×%d（重复其后）" % b["n"]
        return "?"

    def _rebuild(self):
        for w in list(self._cards.values()):
            try:
                w.destroy()
            except Exception:
                pass
        self._cards = {}
        if not self.blocks:
            tk.Label(self.inner, text="点上方「+积木」添加指令",
                     bg=BG, fg=MUTED, font=FONT_SMALL).pack(pady=20)
            return
        for i, b in enumerate(self.blocks):
            self._card(b, i)

    def _card(self, b, i):
        label, color = _KIND[b["type"]]
        f = tk.Frame(self.inner, bg=SURFACE, bd=1, relief=tk.FLAT)
        f.pack(fill=tk.X, pady=2, padx=2)
        # 左侧色标
        tk.Frame(f, bg=color, width=5).pack(side=tk.LEFT, fill=tk.Y)
        # 文本
        tk.Label(f, text=self._summary(b), bg=SURFACE, fg=TEXT,
                 font=FONT_SMALL, anchor=tk.W).pack(side=tk.LEFT, padx=4,
                                                     fill=tk.X, expand=True)
        # 操作
        ops = tk.Frame(f, bg=SURFACE)
        ops.pack(side=tk.RIGHT)
        ttk.Button(ops, text="▲", width=2,
                   command=lambda idx=i: self._move(idx, -1),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=1)
        ttk.Button(ops, text="▼", width=2,
                   command=lambda idx=i: self._move(idx, 1),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=1)
        ttk.Button(ops, text="✕", width=2,
                   command=lambda idx=i: self._del(idx),
                   style="UH.Danger.TButton").pack(side=tk.LEFT, padx=1)
        self._cards[b["_id"]] = f

    def _move(self, i, d):
        j = i + d
        if 0 <= j < len(self.blocks):
            self.blocks[i], self.blocks[j] = self.blocks[j], self.blocks[i]
            self._rebuild()

    def _del(self, i):
        b = self.blocks.pop(i)
        self._rebuild()

    def _clear(self):
        self._stop()
        self.blocks = []
        self._rebuild()

    def _step_repeat(self, d):
        self.repeat_n = max(1, min(99, self.repeat_n + d))
        self.rep_lbl.config(text="×%d" % self.repeat_n)

    # ============ 执行 ============
    def _run(self):
        if self._running:
            return
        if not self.blocks:
            messagebox.showinfo("提示", "先添加积木再运行")
            return
        self._running = True
        self._stop_flag = False
        self.run_btn_ref().config(state="disabled")
        rid = self._run_id + 1
        self._run_id = rid
        t = threading.Thread(target=self._exec, args=(rid,), daemon=True)
        t.start()

    def run_btn_ref(self):
        # 运行按钮引用（在 _build_ui 中存一份）
        return self._run_btn

    def _exec(self, rid):
        seq = list(self.blocks)
        for _ in range(max(1, self.repeat_n)):
            if self._stop_flag or rid != self._run_id:
                return
            self._exec_seq(seq, rid)
        self._q.put(None)  # 结束信号，由主线程轮询器调用 _finish

    def _exec_seq(self, seq, rid):
        i = 0
        while i < len(seq):
            if self._stop_flag or rid != self._run_id:
                return
            b = seq[i]
            if b["type"] == "loop":
                n = max(1, b["n"])
                seg = seq[i + 1:]
                for _2 in range(n):
                    if self._stop_flag or rid != self._run_id:
                        return
                    self._exec_seq(seg, rid)
                i = len(seq)
            else:
                self._exec_one(b, rid)
                i += 1

    def _exec_one(self, b, rid):
        self._q.put(b["_id"])  # 请求高亮（主线程安全应用）
        if b["type"] == "out":
            hwio.pin_set(b["pin"], b["val"])
            time.sleep(0.06)
        elif b["type"] == "buzz":
            hwio.tone(b["freq"])
            time.sleep(b["dur"])
            hwio.tone_stop()
        elif b["type"] == "wait":
            time.sleep(b["sec"])
        time.sleep(0.02)
        if self._stop_flag or rid != self._run_id:
            return

    def _finish(self):
        self._running = False
        try:
            self._run_btn.config(state="normal")
        except Exception:
            pass
        self._highlight(None)

    def _poll_q(self):
        """主线程轮询器：取出工作线程放入队列的 UI 请求并安全执行。
        None = 运行结束信号。"""
        try:
            while True:
                item = self._q.get_nowait()
                if item is None:
                    self._finish()
                    return  # 结束，停止轮询
                self._highlight(item)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(60, self._poll_q)

    def _stop(self):
        self._stop_flag = True
        self._running = False
        hwio.tone_stop()
        try:
            self._run_btn.config(state="normal")
        except Exception:
            pass
        self._highlight(None)

    def _highlight(self, bid):
        for _id, f in self._cards.items():
            try:
                if _id == bid:
                    f.config(bg=HOVER)
                else:
                    f.config(bg=SURFACE)
            except Exception:
                pass

    def _on_configure(self, event):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            pass

    # ============ 板载 A 键停止 ============
    def _bind_board_key(self):
        if not self.hw:
            return
        hwio.bind_a(self._on_a)

    def _on_a(self, pin):
        try:
            if self.winfo_exists():
                self.after(0, self._stop)
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
    BlockCode(root)
    root.mainloop()
