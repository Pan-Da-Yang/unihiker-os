# -*- coding: utf-8 -*-
"""
行空板 OS - 文本编辑器（TextEditor）

布局（240x320 小屏）：
  · 顶部一行：返回 / 文件名 / 保存
  · 上半屏：文本内容（带右侧可拖动滚动条）
  · 下半屏：嵌入的软键盘输入法（Keyboard 控件）

从文件管理器打开文本类文件（.txt/.py/.md/.json ...）时自动进入本编辑器。
支持中英文输入、光标处插入、退格，并可保存到原文件。
"""
import os
import tkinter as tk

import theme
from theme import (
    BG, SURFACE, SURFACE2, HOVER, ACCENT, ACCENT2, DANGER,
    TEXT, MUTED, ON_ACCENT, FONT_NORMAL, FONT_SMALL, BOARD,
    apply_board_window, setup_board_button,
)
from softkeyboard import Keyboard


class TextEditor(tk.Toplevel):
    def __init__(self, master, path):
        super().__init__(master)
        self.title("文本编辑器")
        self.configure(bg=BG)
        apply_board_window(self)
        self.geometry(f"{theme.BOARD_W if BOARD else theme.WIN_W}x"
                      f"{theme.BOARD_H if BOARD else theme.WIN_H}")
        self.master = master
        self.path = path
        self._build_ui()
        self._load()
        setup_board_button(self)
        self.text.focus_set()

    # ---------------- UI ----------------
    def _build_ui(self):
        px = 2 if BOARD else 4
        py = 3 if BOARD else 6

        # 顶栏
        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill=tk.X)
        tk.Button(bar, text="返回", command=lambda: self.destroy(),
                  bg=DANGER, fg="#fff", font=FONT_NORMAL,
                  activebackground="#c9184a", relief=tk.FLAT, bd=0,
                  highlightthickness=0).pack(side=tk.LEFT, padx=4, pady=py)
        self.title_lbl = tk.Label(bar, text=os.path.basename(self.path),
                                  bg=SURFACE, fg=TEXT, font=FONT_SMALL,
                                  anchor=tk.W)
        self.title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        tk.Button(bar, text="保存", command=self._save,
                  bg="#06d6a0", fg="#06231d", font=FONT_NORMAL,
                  activebackground=ACCENT2, relief=tk.FLAT, bd=0,
                  highlightthickness=0).pack(side=tk.RIGHT, padx=4, pady=py)

        # 上半：文本区 + 滚动条（board 模式固定高度，避免 Text 默认高度把键盘挤没）
        text_h = 130 if BOARD else 360
        mid = tk.Frame(self, bg=BG, height=text_h)
        mid.pack(fill=tk.X, padx=2, pady=2)
        mid.pack_propagate(False)
        self.text = tk.Text(mid, bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                            font=FONT_SMALL, relief=tk.FLAT,
                            wrap=tk.WORD if BOARD else tk.NONE,
                            undo=True, borderwidth=0, padx=4, pady=4)
        self.vscroll = tk.Scrollbar(
            mid, orient=tk.VERTICAL,
            command=self.text.yview,
            width=18 if BOARD else 20,
            troughcolor=SURFACE2, bg=ACCENT,
            activebackground=ACCENT2,
            highlightthickness=0, bd=0, relief=tk.FLAT,
        )
        # 必须先 pack 滚动条，否则在 pack_propagate(False) 的容器里会被挤成 1x1
        self.vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.text.configure(yscrollcommand=self.vscroll.set)
        self.text.bind("<<Modified>>", self._on_modified)

        # 下半：嵌入输入法（占满剩余空间）
        self.kbd = Keyboard(self, embed=True,
                            on_char=self._on_char,
                            on_backspace=self._on_back,
                            on_confirm=self._save)
        self.kbd.pack(fill=tk.BOTH, expand=True)

    # ---------------- 输入法回调 ----------------
    def _on_char(self, ch):
        try:
            self.text.insert(tk.INSERT, ch)
        except Exception:
            try:
                self.text.insert(tk.END, ch)
            except Exception:
                pass
        self.text.see(tk.INSERT)

    def _on_back(self):
        # 删除光标前的一个字符；光标已在开头时不操作（不会报错）
        try:
            if self.text.index(tk.INSERT) == "1.0":
                return
            self.text.delete(tk.INSERT + "-1c", tk.INSERT)
        except Exception:
            try:
                self.text.delete(tk.END + "-1c", tk.END)
            except Exception:
                pass

    # ---------------- 读写 ----------------
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            content = f"# 无法读取文件：{e}\n"
        self.text.insert("1.0", content)
        self.text.edit_modified(False)

    def _save(self, *_):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(self.text.get("1.0", tk.END))
            self._flash("已保存 ✓")
            self.text.edit_modified(False)
        except Exception as e:
            self._flash(f"保存失败：{e}")

    def _on_modified(self, _=None):
        if self.text.edit_modified():
            self.title_lbl.config(text=os.path.basename(self.path) + " ●")

    def _flash(self, msg):
        prev = os.path.basename(self.path)
        self.title_lbl.config(text=msg)
        self.after(1200, lambda: self.title_lbl.config(text=prev))


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else __file__
    root = tk.Tk()
    root.withdraw()
    TextEditor(root, p)
    root.mainloop()
