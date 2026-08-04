# -*- coding: utf-8 -*-
"""
行空板 OS - 引脚控制中心
功能：
  · P0–P20 共 21 个引脚，每个可设置「读取模式」(数字输入) 或「控制模式」(数字输出)。
  · P0 为扩展板上的蜂鸣器引脚，单独提供蜂鸣器控制台：
      频率(Hz) / 时长(s) / 持续音 / 播放 / 停止 / 预设音名。
  · 板载 A 键返回桌面；无 pinpong / 无硬件时优雅降级（仅提示，不崩溃）。

硬件约束（来自 pinpong 官方文档）：
  · 所有引脚均支持数字输入 / 数字输出（3.3V）。
  · PWM 引脚：P0 P2 P3 P8 P9 P10 P16 P21 P22 P23。
  · ADC  引脚：P0 P1 P2 P3 P4 P10 P21 P22。
本工具统一按数字 IO 处理（读取模式=read_digital，控制模式=write_digital），
保证 P0–P20 全部可用；蜂鸣器走 P0 的 PWM 通道。
"""
import tkinter as tk
from tkinter import ttk, messagebox

import theme
from theme import (
    BG, SURFACE, SURFACE2, HOVER, ACCENT, ACCENT2, DANGER, TEXT, MUTED,
    ON_ACCENT, FONT_NORMAL, FONT_SMALL, BOARD, apply_board_window,
)

# ---------------- pinpong 懒加载（仅真机有该库/硬件） ----------------
_HW_READY = False
_HW_TRIED = False
_PP = {}  # 存放 Board / Pin / buzzer 等

_PIN_COUNT = 21  # P0..P20

# 预设音名（频率 Hz），用于蜂鸣器快捷按钮
_NOTES = [
    ("Do", 262), ("Re", 294), ("Mi", 330), ("Fa", 349),
    ("Sol", 392), ("La", 440), ("Si", 494), ("C5", 523),
]


def _ensure_hw():
    """初始化 pinpong 硬件连接，成功返回 True。只尝试一次，失败则降级。"""
    global _HW_READY, _HW_TRIED
    if _HW_TRIED:
        return _HW_READY
    _HW_TRIED = True
    try:
        from pinpong.board import Board, Pin, PWM, Tone
        from pinpong.extension.unihiker import buzzer
        # 行空板自动识别板型；多窗口/多次调用 begin() 在 pinpong 内幂等。
        Board().begin()
        _PP.update(Board=Board, Pin=Pin, PWM=PWM, Tone=Tone, buzzer=buzzer)
        _HW_READY = True
    except Exception as e:  # 开发机无库/无硬件
        _PP["err"] = e
        _HW_READY = False
    return _HW_READY


def _pin_const(idx):
    """返回 Pin.Px 常量对象，不存在返回 None。"""
    Pin = _PP.get("Pin")
    if Pin is None:
        return None
    return getattr(Pin, "P%d" % idx, None)


class PinControl(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("引脚控制")
        self.configure(bg=BG)
        apply_board_window(self)
        self.master = master

        self.hw = _ensure_hw()

        # 每个引脚的状态字典
        #  mode: 'none' | 'read' | 'control'
        #  obj : Pin 对象（进入 read/control 时创建）
        #  state: 控制模式下当前输出 0/1
        self.pins = {}
        self._after_ids = set()
        self._bz_playing = False
        self._bz_stop_id = None
        self._bz_redirected = False

        self._build_ui()
        self._bind_board_key()

        if self.hw:
            # 启动读取轮询
            self._poll()
        else:
            self.hw_lbl.config(text="无硬件")

    # ============ UI ============
    def _build_ui(self):
        # ---- 顶部栏 ----
        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill=tk.X)
        px = 2 if BOARD else 4
        ttk.Button(bar, text="返回", command=lambda: self.destroy(),
                   style="UH.Danger.TButton").pack(side=tk.LEFT, padx=px, pady=4)
        tk.Label(bar, text="引脚控制", bg=SURFACE, fg=TEXT,
                 font=FONT_NORMAL).pack(side=tk.LEFT, padx=2)
        self.hw_lbl = tk.Label(bar, text="", bg=SURFACE, fg=MUTED,
                               font=FONT_SMALL, anchor=tk.E)
        self.hw_lbl.pack(side=tk.RIGHT, padx=4)

        # ---- 蜂鸣器控制台 (P0) ----
        self._build_buzzer()

        # ---- 引脚列表 (P0–P20，可滚动) ----
        self._build_pin_list()

        self._style()

    def _build_buzzer(self):
        f = tk.LabelFrame(self, text="蜂鸣器 (P0)",
                          bg=SURFACE, fg=ACCENT2, font=FONT_SMALL,
                          relief=tk.FLAT, bd=1, highlightthickness=0)
        f.pack(fill=tk.X, padx=6, pady=(4, 2))

        self.bz_freq = tk.IntVar(value=440)
        self.bz_dur = tk.DoubleVar(value=0.5)
        self.bz_forever = tk.BooleanVar(value=False)

        # 频率行
        rf = tk.Frame(f, bg=SURFACE)
        rf.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(rf, text="−", width=3,
                   command=lambda: self._bz_step_freq(-20),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2)
        self.bz_freq_lbl = tk.Label(rf, text="440 Hz", bg=SURFACE, fg=TEXT,
                                    font=FONT_SMALL, width=8, anchor=tk.CENTER)
        self.bz_freq_lbl.pack(side=tk.LEFT, padx=2)
        ttk.Button(rf, text="+", width=3,
                   command=lambda: self._bz_step_freq(20),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2)
        tk.Checkbutton(rf, text="持续", variable=self.bz_forever,
                       bg=SURFACE, fg=MUTED, selectcolor=SURFACE,
                       activebackground=SURFACE, font=FONT_SMALL,
                       command=self._bz_forever_toggle).pack(side=tk.RIGHT, padx=2)

        # 时长行
        rd = tk.Frame(f, bg=SURFACE)
        rd.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(rd, text="−", width=3,
                   command=lambda: self._bz_step_dur(-0.1),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2)
        self.bz_dur_lbl = tk.Label(rd, text="0.5 s", bg=SURFACE, fg=TEXT,
                                   font=FONT_SMALL, width=8, anchor=tk.CENTER)
        self.bz_dur_lbl.pack(side=tk.LEFT, padx=2)
        ttk.Button(rd, text="+", width=3,
                   command=lambda: self._bz_step_dur(0.1),
                   style="UH.Num.TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(rd, text="播放", command=self._bz_play,
                   style="UH.TButton").pack(side=tk.RIGHT, padx=2)
        ttk.Button(rd, text="停止", command=self._bz_stop,
                   style="UH.Danger.TButton").pack(side=tk.RIGHT, padx=2)

        # 预设音名
        rnote = tk.Frame(f, bg=SURFACE)
        rnote.pack(fill=tk.X, padx=4, pady=(2, 4))
        for name, hz in _NOTES:
            ttk.Button(rnote, text=name, command=lambda h=hz: self._bz_preset(h),
                       style="UH.Num.TButton").pack(side=tk.LEFT, padx=1, expand=True, fill=tk.X)

    def _build_pin_list(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 2))

        # 滚动导航条
        nav = tk.Frame(outer, bg=BG)
        nav.pack(fill=tk.X)
        tk.Label(nav, text="数字引脚 P0–P20", bg=BG, fg=MUTED,
                 font=FONT_SMALL).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav, text="▲", width=3,
                   command=lambda: self._scroll(-3),
                   style="UH.Num.TButton").pack(side=tk.RIGHT, padx=1)
        ttk.Button(nav, text="▼", width=3,
                   command=lambda: self._scroll(3),
                   style="UH.Num.TButton").pack(side=tk.RIGHT, padx=1)
        ttk.Button(nav, text="全部释放", command=self._release_all,
                   style="UH.Num.TButton").pack(side=tk.RIGHT, padx=2)

        # 可滚动区域
        self.canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.canvas.create_window((0, 0), window=self.inner, anchor=tk.NW)
        self.inner.bind("<Configure>", self._on_frame_configure)

        for idx in range(_PIN_COUNT):
            self._make_pin_row(idx)

    def _make_pin_row(self, idx):
        row = tk.Frame(self.inner, bg=BG)
        row.pack(fill=tk.X, pady=1)

        if idx == 0:
            # P0 = 蜂鸣器专用入口
            tk.Label(row, text="P0", bg=BG, fg=ACCENT2, font=FONT_SMALL,
                     width=4, anchor=tk.W).pack(side=tk.LEFT)
            tk.Label(row, text="蜂鸣器", bg=BG, fg=MUTED, font=FONT_SMALL,
                     width=6, anchor=tk.W).pack(side=tk.LEFT, padx=2)
            ttk.Button(row, text="蜂鸣器", command=self._bz_beep,
                       style="UH.TButton").pack(side=tk.LEFT, padx=2)
            self.pins[idx] = {"mode": "buzzer", "obj": None}
            return

        tk.Label(row, text="P%d" % idx, bg=BG, fg=TEXT, font=FONT_SMALL,
                 width=4, anchor=tk.W).pack(side=tk.LEFT)

        mode_btn = ttk.Button(row, text="未用", width=6,
                              command=lambda i=idx: self._cycle_mode(i),
                              style="UH.Num.TButton")
        mode_btn.pack(side=tk.LEFT, padx=2)

        val_lbl = tk.Label(row, text="—", bg=BG, fg=MUTED, font=FONT_SMALL,
                           width=5, anchor=tk.CENTER)
        val_lbl.pack(side=tk.LEFT, padx=2)

        act_btn = ttk.Button(row, text="开", width=4,
                             command=lambda i=idx: self._toggle_out(i),
                             style="UH.TButton")
        # 控制模式时才显示，起初隐藏
        self.pins[idx] = {"mode": "none", "obj": None, "state": 0,
                          "mode_btn": mode_btn, "val_lbl": val_lbl,
                          "act_btn": act_btn}

    # ============ 蜂鸣器逻辑 ============
    def _bz_redirect(self):
        if not self.hw or self._bz_redirected:
            return
        try:
            const = _pin_const(0)
            if const is not None:
                _PP["buzzer"].redirect(const)  # 蜂鸣器重定向到 P0
            self._bz_redirected = True
        except Exception as e:
            messagebox.showerror("蜂鸣器", "P0 重定向失败：%s" % e)

    def _bz_step_freq(self, d):
        v = max(50, min(4000, self.bz_freq.get() + d))
        self.bz_freq.set(v)
        self.bz_freq_lbl.config(text="%d Hz" % v)

    def _bz_step_dur(self, d):
        v = max(0.1, min(10.0, round(self.bz_dur.get() + d, 1)))
        self.bz_dur.set(v)
        self.bz_dur_lbl.config(text="%.1f s" % v)

    def _bz_forever_toggle(self):
        if self.bz_forever.get():
            self.bz_dur_lbl.config(text="持续", fg=ACCENT2)
        else:
            self.bz_dur_lbl.config(text="%.1f s" % self.bz_dur.get(), fg=TEXT)

    def _bz_play(self):
        if not self.hw:
            messagebox.showinfo("提示", "当前环境未检测到 pinpong / 行空板硬件")
            return
        self._bz_redirect()
        try:
            f = self.bz_freq.get()
            _PP["buzzer"].pitch(f)  # 后台持续播放该频率
            self._bz_playing = True
            if not self.bz_forever.get():
                dur = int(self.bz_dur.get() * 1000)
                self._bz_stop_id = self.after(dur, self._bz_stop)
        except Exception as e:
            messagebox.showerror("蜂鸣器", "播放失败：%s" % e)

    def _bz_preset(self, hz):
        self.bz_freq.set(hz)
        self.bz_freq_lbl.config(text="%d Hz" % hz)
        self.bz_forever.set(False)
        self.bz_dur_lbl.config(text="%.1f s" % self.bz_dur.get(), fg=TEXT)
        self._bz_play()

    def _bz_beep(self):
        """P0 列表项快捷蜂鸣：按当前频率响 0.3s。"""
        if not self.hw:
            messagebox.showinfo("提示", "当前环境未检测到 pinpong / 行空板硬件")
            return
        prev_freq = self.bz_freq.get()
        self._bz_redirect()
        try:
            _PP["buzzer"].pitch(prev_freq)
            self.after(300, self._bz_stop)
        except Exception as e:
            messagebox.showerror("蜂鸣器", "蜂鸣失败：%s" % e)

    def _bz_stop(self):
        if self._bz_stop_id is not None:
            try:
                self.after_cancel(self._bz_stop_id)
            except Exception:
                pass
            self._bz_stop_id = None
        if not self.hw:
            return
        try:
            _PP["buzzer"].stop()
        except Exception:
            pass
        self._bz_playing = False

    # ============ 引脚模式/控制 ============
    def _cycle_mode(self, idx):
        p = self.pins[idx]
        order = ["none", "read", "control"]
        cur = p["mode"]
        nxt = order[(order.index(cur) + 1) % len(order)]
        self._set_mode(idx, nxt)

    def _set_mode(self, idx, mode):
        p = self.pins[idx]
        # 收掉旧对象
        if p["obj"] is not None:
            try:
                del p["obj"]
            except Exception:
                pass
            p["obj"] = None

        if mode == "none":
            p["mode"] = "none"
            p["mode_btn"].config(text="未用")
            p["val_lbl"].config(text="—", fg=MUTED)
            p["val_lbl"].pack(side=tk.LEFT, padx=2)
            p["act_btn"].pack_forget()
            return

        if not self.hw:
            messagebox.showinfo("提示", "当前环境未检测到 pinpong / 行空板硬件")
            return

        const = _pin_const(idx)
        if const is None:
            messagebox.showerror("引脚", "P%d 在该硬件上不可用" % idx)
            return

        pin_cls = _PP.get("Pin")
        try:
            if mode == "read":
                p["obj"] = pin_cls(const, pin_cls.IN)
                p["mode"] = "read"
                p["mode_btn"].config(text="读取")
                p["val_lbl"].pack(side=tk.LEFT, padx=2)
                p["act_btn"].pack_forget()
            else:  # control
                p["obj"] = pin_cls(const, pin_cls.OUT)
                p["state"] = 0
                p["obj"].write_digital(0)
                p["mode"] = "control"
                p["mode_btn"].config(text="控制")
                p["val_lbl"].pack_forget()
                p["act_btn"].config(text="关")
                p["act_btn"].pack(side=tk.LEFT, padx=2)
        except Exception as e:
            messagebox.showerror("引脚", "P%d 初始化失败：%s" % (idx, e))
            p["mode"] = "none"
            p["mode_btn"].config(text="未用")

    def _toggle_out(self, idx):
        p = self.pins[idx]
        if p["mode"] != "control" or p["obj"] is None:
            return
        p["state"] = 1 - p["state"]
        try:
            p["obj"].write_digital(p["state"])
        except Exception as e:
            messagebox.showerror("引脚", "P%d 写入失败：%s" % (idx, e))
            return
        p["act_btn"].config(text="开" if p["state"] else "关")

    def _release_all(self):
        for idx in range(_PIN_COUNT):
            p = self.pins[idx]
            if p.get("mode") in ("read", "control"):
                self._set_mode(idx, "none")

    # ============ 读值轮询 ============
    def _poll(self):
        if not self.winfo_exists():
            return
        for idx in range(_PIN_COUNT):
            p = self.pins[idx]
            if p.get("mode") != "read" or p.get("obj") is None:
                continue
            try:
                v = p["obj"].read_digital()
                if v:
                    p["val_lbl"].config(text="高", fg=ACCENT)
                else:
                    p["val_lbl"].config(text="低", fg=MUTED)
            except Exception:
                p["val_lbl"].config(text="ERR", fg=DANGER)
        self._safe_after(500, self._poll)

    # ============ 滚动 ============
    def _scroll(self, units):
        try:
            self.canvas.yview_scroll(units, "units")
        except Exception:
            pass

    def _on_frame_configure(self, event):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            pass

    # ============ 板载 A 键返回 ============
    def _bind_board_key(self):
        if not self.hw:
            return
        try:
            from pinpong.extension.unihiker import button_a
            Pin = _PP.get("Pin")
            button_a.irq(trigger=Pin.IRQ_RISING, handler=self._on_a)
        except Exception:
            pass

    def _on_a(self, pin):
        # 回调在子线程触发，切回主线程销毁窗口
        try:
            if self.winfo_exists():
                self.after(0, lambda: self.destroy())
        except Exception:
            pass

    # ============ after 安全封装 ============
    def _safe_after(self, ms, cb):
        aid = self.after(ms, cb)
        self._after_ids.add(aid)
        return aid

    # ============ 样式 ============
    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass
        # 覆盖默认 TButton width（否则被主题默认 72px 撑爆导致按钮缺失）
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
    import sys
    root = tk.Tk()
    root.withdraw()
    PinControl(root)
    root.mainloop()
