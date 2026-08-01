# -*- coding: utf-8 -*-
"""
行空板 OS - 自制软键盘输入法

参考 qq_unihiker/ui.py 的屏幕键盘设计：
- 使用 grid 矩阵布局，每行/列 uniform 权重，确保 240x320 小屏上所有按键可见
- QWERTY 四行 + 123 符号四行
- 顶部输入框（弹窗模式）+ 候选条（带左右翻页箭头）
- 中文拼音输入，1000+ 常用字库（pinyin_dict.json）

两种用法：
1) 弹窗（路径输入等）：SoftKeyboard(master, target_entry, on_confirm=回调)
2) 嵌入（文本编辑器底部等）：Keyboard(master, embed=True,
                                  on_char=插入回调, on_backspace=删除回调,
                                  on_confirm=确认回调)
   嵌入模式下去掉顶部输入预览条和「取消」控制行，整块键盘可作为下半屏。
"""
import os
import json
import tkinter as tk

import theme
from theme import (
    BG, SURFACE, SURFACE2, HOVER, ACCENT, ACCENT2, DANGER,
    TEXT, MUTED, ON_ACCENT, FONT_NORMAL, FONT_SMALL, BOARD,
    apply_board_window,
)

_DICT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "pinyin_dict.json")

# 按键高度（board 模式更紧凑但不再细狗）
KEY_FONT = FONT_NORMAL
CAND_FONT = FONT_NORMAL


class Keyboard(tk.Frame):
    """可嵌入的软键盘控件。通过回调把按键事件交给上层处理：

    - on_char(ch)       ：插入一个字符（字母/数字/符号/空格/选中的汉字）
    - on_backspace()    ：删除光标前的一个字符
    - on_confirm(*_=None)：确认（弹窗：关闭；嵌入：保存等）
    - on_cancel(*_=None) ：取消（弹窗：关闭；嵌入：通常不用）

    键盘内部维护拼音缓冲与候选状态，仅在“选定汉字 / 英文 / 符号 / 空格”
    时通过 on_char 把最终字符交给上层，因此上层控件（Entry 或 Text）
    始终持有真实文本，输入法只负责“组字”。
    """

    def __init__(self, master, on_char, on_backspace,
                 on_confirm=None, on_cancel=None, embed=False, board=BOARD,
                 get_base_text=None):
        super().__init__(master, bg=BG)
        self.on_char = on_char
        self.on_backspace = on_backspace
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.embed = embed
        self.board = board
        self.get_base_text = get_base_text

        self.pinyin = ""
        self.mode = "en"          # "zh" / "en"
        self.layer = "abc"        # "abc" / "123"
        self.caps = False
        self.page = 0
        self.candidates = []
        self._dict = self._load_dict()
        self.disp_lbl = None

        self._build_ui()
        self._update_candidates()
        self._render_keys()
        self._refresh_display()

    # ---------------- 数据 ----------------
    @staticmethod
    def _load_dict():
        try:
            with open(_DICT_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and d:
                return d
        except Exception:
            pass
        return {"ni": ["你", "拟"], "wo": ["我"], "hao": ["好"],
                "de": ["的"], "shi": ["是"], "bu": ["不"], "le": ["了"]}

    # ---------------- UI ----------------
    def _build_ui(self):
        px = 1 if self.board else 2
        py = 1 if self.board else 2

        # 1) 当前输入预览条（仅弹窗模式需要，嵌入模式用上层文本区代替）
        if not self.embed:
            self.disp_frame = tk.Frame(self, bg=SURFACE,
                                       height=24 if self.board else 30)
            self.disp_frame.pack_propagate(False)
            self.disp_frame.pack(fill=tk.X, padx=px, pady=(py, 0))
            self.disp_lbl = tk.Label(self.disp_frame, text="", bg=SURFACE,
                                     fg=TEXT, font=FONT_SMALL, anchor=tk.W,
                                     padx=4)
            self.disp_lbl.pack(fill=tk.BOTH, expand=True)

        # 2) 候选条（紧跟输入框，始终显示左右箭头；中间单字方正显示）
        self.cand_frame = tk.Frame(self, bg=SURFACE2,
                                   height=30 if self.board else 38)
        self.cand_frame.pack_propagate(False)
        self.cand_frame.pack(fill=tk.X, padx=px, pady=py)

        # 3) 按键区
        self.keys_frame = tk.Frame(self, bg=BG)
        self.keys_frame.pack(fill=tk.BOTH, expand=True, padx=px, pady=py)

        # 4) 底部控制行（仅弹窗模式：完成 / 取消）
        if not self.embed:
            ctrl = tk.Frame(self, bg=SURFACE)
            ctrl.pack(fill=tk.X, padx=px, pady=py)
            tk.Button(ctrl, text="完成", command=self._confirm,
                      bg="#06d6a0", fg="#06231d", font=FONT_NORMAL,
                      activebackground=ACCENT2, relief=tk.RAISED, bd=1,
                      highlightthickness=0).pack(side=tk.RIGHT, fill=tk.X,
                                                  expand=True, padx=px, pady=py)
            tk.Button(ctrl, text="取消", command=self._cancel,
                      bg=DANGER, fg="#fff", font=FONT_NORMAL,
                      activebackground="#c9184a", relief=tk.RAISED, bd=1,
                      highlightthickness=0).pack(side=tk.RIGHT, fill=tk.X,
                                                  expand=True, padx=px, pady=py)

    # ---------------- 按键矩阵 ----------------
    def _render_keys(self):
        for w in self.keys_frame.grid_slaves():
            w.destroy()

        mode_tag = "中" if self.mode == "zh" else "EN"

        if self.layer == "abc":
            rows_data = [
                list("qwertyuiop"),
                list("asdfghjkl;"),
                ["^"] + list("zxcvbnm,.") + ["<-"],
                [mode_tag, "123", "空格", ".", "<-", "完成"],
            ]
        else:
            rows_data = [
                list("1234567890"),
                list("-_/\\@#!$%&"),
                list("()=+[]{}:~"),
                [mode_tag, "abc", "空格", ".", "<-", "完成"],
            ]

        for ri, row_data in enumerate(rows_data):
            for ci, k in enumerate(row_data):
                btn = self._make_key_button(k)
                btn.grid(row=ri, column=ci, sticky="nsew", padx=1, pady=1,
                         ipadx=1, ipady=2 if self.board else 3)
                self.keys_frame.columnconfigure(ci, weight=1, uniform="key")
            self.keys_frame.rowconfigure(ri, weight=1, uniform="keyrow")

    def _make_key_button(self, k):
        if k in ("<-",):
            disp = "←"; bg_c = SURFACE2; fg_c = TEXT
        elif k == "^":
            disp = "⇧"; bg_c = SURFACE2; fg_c = TEXT
        elif k in ("中", "EN"):
            disp = k
            bg_c = ACCENT if self.mode == "zh" else SURFACE2
            fg_c = ON_ACCENT if self.mode == "zh" else TEXT
        elif k in ("123", "abc"):
            disp = k; bg_c = SURFACE2; fg_c = TEXT
        elif k == "空格":
            disp = "空格"; bg_c = SURFACE; fg_c = TEXT
        elif k == "完成":
            disp = "完成"; bg_c = "#06d6a0"; fg_c = "#06231d"
        elif k == ".":
            disp = "."; bg_c = SURFACE; fg_c = TEXT
        else:
            disp = k.upper() if (self.caps and k.isalpha()) else k
            bg_c = SURFACE; fg_c = TEXT

        btn = tk.Button(
            self.keys_frame, text=disp,
            bg=bg_c, fg=fg_c, font=KEY_FONT,
            activebackground=HOVER, activeforeground=TEXT,
            relief=tk.RAISED, bd=1, highlightthickness=0,
            padx=1, pady=1,
        )
        btn.bind("<Button-1>", lambda ev, kk=k: self._key_press(kk))
        return btn

    # ---------------- 候选字 ----------------
    def _update_candidates(self):
        if self.mode != "zh" or not self.pinyin:
            self.candidates = []
        else:
            matches = self._dict.get(self.pinyin, [])
            extra = []
            for py, chars in self._dict.items():
                if py.startswith(self.pinyin) and py != self.pinyin:
                    extra.extend(chars)
            seen = set()
            out = []
            for c in matches + extra:
                if c not in seen:
                    seen.add(c)
                    out.append(c)
            self.candidates = out
        self.page = 0
        self._render_candidates()

    def _render_candidates(self):
        for w in self.cand_frame.winfo_children():
            w.destroy()

        per = 4
        total = len(self.candidates)
        pages = (total + per - 1) // per if total else 1

        # 左箭头
        left = tk.Button(self.cand_frame, text="‹", bg=SURFACE2, fg=TEXT,
                         font=FONT_NORMAL, relief=tk.RAISED, bd=1,
                         highlightthickness=0)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=1)
        if self.mode == "zh" and self.pinyin and self.page > 0:
            left.config(command=lambda: self._page(-1))
        else:
            left.config(state=tk.DISABLED, bg=SURFACE, fg=MUTED)

        # 中间候选区：每页 4 个方正汉字
        if self.mode != "zh" or not self.pinyin:
            hint = "中文模式：打拼音出汉字" if self.mode == "zh" else "英文直输模式"
            tk.Label(self.cand_frame, text=hint, bg=SURFACE2, fg=MUTED,
                     font=FONT_SMALL, anchor=tk.CENTER).pack(
                         side=tk.LEFT, fill=tk.Y, expand=True)
        elif total == 0:
            tk.Label(self.cand_frame, text=f'无匹配: "{self.pinyin}"',
                     bg="#5a1a1a", fg=TEXT, font=FONT_SMALL, anchor=tk.CENTER).pack(
                         side=tk.LEFT, fill=tk.Y, expand=True)
        else:
            mid_frame = tk.Frame(self.cand_frame, bg=SURFACE2)
            mid_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            size = 28 if self.board else 34
            start = self.page * per
            for ch in self.candidates[start:start + per]:
                cvs = tk.Canvas(mid_frame, width=size, height=size,
                                bg=ACCENT, highlightthickness=0)
                cvs.create_text(size // 2, size // 2, text=ch, fill=ON_ACCENT,
                                font=FONT_NORMAL, anchor=tk.CENTER)
                cvs.bind("<Button-1>", lambda ev, cch=ch: self._select(cch))
                cvs.pack(side=tk.LEFT, padx=1, pady=1)

        # 右箭头
        right = tk.Button(self.cand_frame, text="›", bg=SURFACE2, fg=TEXT,
                          font=FONT_NORMAL, relief=tk.RAISED, bd=1,
                          highlightthickness=0)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=1)
        if self.mode == "zh" and self.pinyin and self.page < pages - 1:
            right.config(command=lambda: self._page(1))
        else:
            right.config(state=tk.DISABLED, bg=SURFACE, fg=MUTED)

    def _page(self, d):
        per = 4
        pages = (len(self.candidates) + per - 1) // per
        self.page = max(0, min(pages - 1, self.page + d))
        self._render_candidates()

    # ---------------- 交互 ----------------
    def _key_press(self, ch):
        if ch == "<-":
            self._back()
        elif ch == "^":
            self.caps = not self.caps
            self._render_keys()
        elif ch == "空格":
            self._space()
        elif ch == "完成":
            self._confirm()
        elif ch == "123":
            self.layer = "123"
            self._render_keys()
        elif ch == "abc":
            self.layer = "abc"
            self._render_keys()
        elif ch in ("中", "EN"):
            self.mode = "zh" if self.mode == "en" else "en"
            self.pinyin = ""
            self._update_candidates()
            self._render_keys()
            self._refresh_display()
        else:
            # 字母 / 数字 / 符号
            if self.layer == "123":
                self.on_char(ch)
            elif self.mode == "zh" and ch.isalpha():
                self.pinyin += ch.lower()
                self._update_candidates()
            else:
                self.on_char(ch.upper() if (self.caps and ch.isalpha()) else ch)
            self._refresh_display()

    def _back(self):
        if self.mode == "zh" and self.pinyin:
            self.pinyin = self.pinyin[:-1]
            self._update_candidates()
        elif self.on_backspace:
            self.on_backspace()
        self._refresh_display()

    def _space(self):
        if self.mode == "zh" and self.pinyin:
            if self.candidates:
                self._select(self.candidates[0])
            else:
                self.pinyin = ""
                self._update_candidates()
        else:
            self.on_char(" ")
        self._refresh_display()

    def _select(self, ch):
        self.on_char(ch)
        self.pinyin = ""
        self.candidates = []
        self.page = 0
        self._update_candidates()
        self._refresh_display()

    def _refresh_display(self):
        if self.disp_lbl is None:
            return
        base = ""
        if self.get_base_text:
            try:
                base = self.get_base_text()
            except Exception:
                base = ""
        mode = "[中]" if self.mode == "zh" else "[EN]"
        py = f" {self.pinyin}|" if (self.mode == "zh" and self.pinyin) else ""
        self.disp_lbl.config(text=f"{base}{mode}{py}")

    def _confirm(self, *_):
        if self.on_confirm:
            try:
                self.on_confirm()
            except Exception:
                pass

    def _cancel(self, *_):
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass


class SoftKeyboard(tk.Toplevel):
    """弹窗输入法：把键盘结果实时写回 target（Entry/Text），点完成回调。"""

    def __init__(self, master, target, on_confirm=None):
        super().__init__(master)
        self.title("输入法")
        self.configure(bg=BG)
        apply_board_window(self)
        self.geometry(f"{theme.BOARD_W if BOARD else theme.WIN_W}x"
                      f"{theme.BOARD_H if BOARD else theme.WIN_H}")
        self.target = target
        self.on_confirm = on_confirm

        kbd = Keyboard(self, embed=False,
                       on_char=self._ins, on_backspace=self._del,
                       on_confirm=self._confirm, on_cancel=self.destroy,
                       get_base_text=self._get_target_text)
        kbd.pack(fill=tk.BOTH, expand=True)

    def _get_target_text(self):
        if self.target is None:
            return ""
        if isinstance(self.target, tk.Text):
            return self.target.get("1.0", tk.END).rstrip("\n")
        return self.target.get()

    def _ins(self, ch):
        if not self.target:
            return
        # 优先插入到光标处（尊重用户在输入框里点击的位置）
        try:
            self.target.insert(tk.INSERT, ch)
        except Exception:
            try:
                self.target.insert(tk.END, ch)
            except Exception:
                pass

    def _del(self):
        if not self.target:
            return
        # 删除光标前的一个字符。
        # 注意：tk.Entry 只认整数索引；tk.Text 才支持 "insert - 1c" 字符偏移。
        # 之前统一用 "-1c" 语法导致 Entry 退格抛 TclError 被吞掉 -> 表现为“按了没反应”。
        try:
            idx = self.target.index(tk.INSERT)
        except Exception:
            idx = None
        if isinstance(idx, int):                      # tk.Entry
            if idx <= 0:
                return
            try:
                self.target.delete(idx - 1, idx)
            except Exception:
                pass
            return
        if idx == "1.0":                             # tk.Text 已在开头
            return
        try:
            self.target.delete(tk.INSERT + "-1c", tk.INSERT)
        except Exception:
            try:
                self.target.delete(tk.END + "-1c", tk.END)
            except Exception:
                pass

    def _confirm(self, *_):
        if self.on_confirm:
            try:
                self.on_confirm(self.target.get() if self.target else "")
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    e = tk.Entry(root)
    e.pack()
    SoftKeyboard(root, e)
    root.mainloop()
