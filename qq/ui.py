# ui.py - 行空板版 QQ 的 tkinter 界面（240x320 竖屏，联机版）
#
# 布局（纯 pack + grid 混合）：
#   root
#   ├── host        (pack fill=both expand=True)   主内容区，各页面切换
#   └── kb_frame    (pack side=bottom)              屏幕键盘
#        ├── cand_bar      (pack)  候选条 / 提示
#        ├── draft_bar     (pack)  编辑栏 [中]/[EN] + 当前内容
#        └── keys_frame    (grid)  按键区（qwerty/123 矩阵）
#
# 键盘页：auth / chat / add_friend / create_group → 键盘自动显示
# 非键盘页：contacts / menu → 键盘隐藏

import tkinter as tk
import platform
import os
import time
import json

# ======================== 常量 ========================
SCREEN_W, SCREEN_H = 240, 320
QQ_BLUE   = "#12b7f5"
CHAT_BG   = "#ededed"
LIST_BG   = "#f5f5f5"
SENT_BUB  = "#95ec69"
RECV_BUB  = "#ffffff"
TEXT_DARK = "#222222"
MUTE_GRAY = "#999999"
HEADER_H  = 30
ONLINE    = "#3ac34a"
OFFLINE   = "#cccccc"
RED       = "#fa5151"
KB_BG     = "#d0d3d9"
KEY_BG    = "#fafafa"
KEY_FG    = TEXT_DARK
KEY_FONT_SIZE = 10
KEY_HEIGHT  = 22          # 每个按键行固定高度（4行=88 + cand16 + draft16 = ~120px总键盘）

IS_UNIHIKER = (platform.system().lower() != "windows") and (
    os.path.exists("/etc/unihiker") or os.path.exists("/sys/devices/platform/board_info")
)
FAMILY = "WenQuanYi Micro Hei" if IS_UNIHIKER else "Microsoft YaHei"

PINYIN = {}
try:
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pinyin.json")
    with open(_p, encoding="utf-8") as f:
        PINYIN = json.load(f)
except Exception:
    print("[WARN] pinyin.json 未加载")


def F(size, weight="normal"):
    return (FAMILY, size, weight)


def round_rect(c, x, y, w, h, r, fill, outline=None, width=1):
    if outline is None:
        outline = fill
    ids = []
    ids.append(c.create_arc(x, y, x+2*r, y+2*r, start=90, extent=90,
                            fill=fill, outline=outline, width=width))
    ids.append(c.create_arc(x+w-2*r, y, x+w, y+2*r, start=0, extent=90,
                            fill=fill, outline=outline, width=width))
    ids.append(c.create_arc(x, y+h-2*r, x+2*r, y+h, start=180, extent=90,
                            fill=fill, outline=outline, width=width))
    ids.append(c.create_arc(x+w-2*r, y+h-2*r, x+w, y+h, start=270, extent=90,
                            fill=fill, outline=outline, width=width))
    ids.append(c.create_rectangle(x+r, y, x+w-r, y+h, fill=fill,
                                  outline=outline, width=width))
    ids.append(c.create_rectangle(x, y+r, x+w, y+h-r, fill=fill,
                                  outline=outline, width=width))
    return ids


def make_avatar(parent, ch, color, size=36, bg="white"):
    c = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0)
    pad = 2
    c.create_oval(pad, pad, size-pad, size-pad, fill=color, outline="")
    c.create_text(size/2, size/2+1, text=ch, fill="white", font=F(14, "bold"))
    return c


class Message:
    __slots__ = ("sender_name", "text", "ts", "mine")
    def __init__(self, sender_name, text, ts, mine):
        self.sender_name = sender_name
        self.text = text
        self.ts = ts
        self.mine = mine


class QQApp:

    # ---------- 页面类型：哪些页面需要键盘 ----------
    KB_PAGES = frozenset({"auth", "chat", "add_friend", "create_group"})

    def __init__(self, root, client):
        self.root = root
        self.client = client
        self.me = None
        self.contacts = {}
        self.groups = {}
        self.messages = {}
        self.uid_names = {}
        self.unread = {}
        self.pending = {}        # 待接受的好友申请 {uid: {uid,username,friend_code}}
        self.pending_btn = None  # 菜单里"待接受"按钮引用（用于更新未读徽标）
        self.current = None
        self.draft = ""
        self.fields = {k: "" for k in (
            "username", "password", "friendcode",
            "groupname", "groupcodes", "serverip")}
        self.kb_mode = "abc"
        self.caps = False
        self.ime_on = False
        self.ime_py = ""
        self.ime_cands = []
        self.input_target = None
        self.current_page = None
        self.on_retry = None
        self._drag_y = 0
        self._drag_active = False

        # ====== 主内容区（上面）======
        self.host = tk.Frame(root)
        self.host.pack(fill="both", expand=True)

        # 各页面
        self.screens = {}
        self.screens["auth"]         = self._build_auth()
        self.screens["contacts"]     = self._build_contacts()
        self.screens["chat"]         = self._build_chat()
        self.screens["menu"]         = self._build_menu()
        self.screens["add_friend"]   = self._build_add_friend()
        self.screens["create_group"] = self._build_create_group()
        self.screens["mycode"]      = self._build_mycode()
        self.screens["pending"]      = self._build_pending()

        # ====== 键盘区（下面）======
        self.kb_frame = tk.Frame(root, bg=KB_BG)

        # -- 候选条 --
        self.cand_bar = tk.Frame(self.kb_frame, bg="#e8ecf4", height=18)
        self.cand_bar.pack_propagate(False)
        self.cand_bar.pack(fill="x", padx=2, pady=(1,0))

        # -- 编辑栏（显示当前输入内容 + 中/EN 模式）--
        self.draft_bar = tk.Frame(self.kb_frame, bg="#c8ccd4", height=20)
        self.draft_bar.pack_propagate(False)
        self.draft_bar.pack(fill="x", padx=2, pady=1)
        self.kb_draft_lbl = tk.Label(self.draft_bar, text="[EN] ", fg=TEXT_DARK,
                                     bg="#ffffff", font=F(10), anchor="w", padx=6)
        self.kb_draft_lbl.pack(side="left", fill="both", expand=True, padx=3, pady=2)

        # -- 按键区（grid 矩阵布局）--
        self.keys_frame = tk.Frame(self.kb_frame, bg=KB_BG)
        self.keys_frame.pack(fill="both", expand=True, padx=2, pady=(0,1))

        # 构建按键（初始 abc 布局）
        self._build_keys()

        # 默认隐藏键盘
        self.kb_shown = False
        self._kb_hide()

        self._bind_pc_keys()

        # 启动时显示登录页（带键盘）
        self._goto("auth")
        self.set_target("username")

    # ================================================================
    #  页面切换
    # ================================================================
    def _goto(self, page_name):
        """切换到指定页面，同时控制键盘显隐"""
        for name, scr in self.screens.items():
            if name != page_name:
                scr.pack_forget()
        self.screens[page_name].pack(fill="both", expand=True)
        self.current_page = page_name
        self.input_target = None
        self.ime_py = ""

        # 键盘控制
        if page_name in self.KB_PAGES:
            self._kb_show()
        else:
            self._kb_hide()

        self._render_cands()
        self._refresh_display()

    # ---- 快捷跳转 ----
    def show_contacts(self):   self._goto("contacts")
    def _open_menu(self):      self._goto("menu")
    def _open_add_friend(self):self._goto("add_friend"); self.set_target("friendcode")
    def _open_create_group(self):self._goto("create_group"); self.set_target("groupname")
    def _open_mycode(self):    self._goto("mycode")
    def _open_pending(self):   self._goto("pending"); self._refresh_pending()

    # ================================================================
    #  键盘 显示/隐藏
    # ================================================================
    def _kb_show(self):
        if not self.kb_shown:
            self.kb_frame.pack(side="bottom", fill="x")
            self.kb_shown = True

    def _kb_hide(self):
        if self.kb_shown:
            self.kb_frame.pack_forget()
            self.kb_shown = False

    # ================================================================
    #  登录/注册页
    # ================================================================
    def _build_auth(self):
        f = tk.Frame(self.host, bg=LIST_BG)

        # 标题栏
        hdr = tk.Frame(f, bg=QQ_BLUE, height=HEADER_H)
        hdr.pack_propagate(False); hdr.pack(fill="x")
        tk.Label(hdr, text="QQ", fg="white", bg=QQ_BLUE,
                 font=F(16, "bold")).pack(side="left", padx=12)

        body = tk.Frame(f, bg=LIST_BG)
        body.pack(fill="both", expand=True, padx=10, pady=4)

        # 状态提示
        self.status_lbl = tk.Label(body, text="", fg=RED, bg=LIST_BG,
                                   font=F(9), anchor="w", wraplength=220)
        self.status_lbl.pack(fill="x", pady=(0,4))

        def input_row(label_text, target_key):
            row = tk.Frame(body, bg="white", height=30)
            row.pack_propagate(False); row.pack(fill="x", pady=1)
            lbl = tk.Label(row, text=label_text, fg=MUTE_GRAY, bg="white",
                           font=F(11), anchor="w", padx=8)
            lbl.pack(fill="both", expand=True)
            for w in (row, lbl):
                w.bind("<Button-1>", lambda e, t=target_key: self.set_target(t))
            return lbl

        self.server_lbl = input_row("服务器 IP", "serverip")
        self.user_lbl   = input_row("用户名",   "username")
        self.pass_lbl   = input_row("密码",     "password")

        # 按钮
        login_btn = tk.Label(body, text="登 录", fg="white", bg=QQ_BLUE,
                             font=F(14, "bold"), height=1)
        login_btn.pack(fill="x", pady=(6,2))
        login_btn.bind("<Button-1>", lambda e: self.do_login())

        reg_btn = tk.Label(body, text="注册新账号", fg=QQ_BLUE, bg="white",
                           font=F(12), height=1)
        reg_btn.pack(fill="x", pady=2)
        reg_btn.bind("<Button-1>", lambda e: self.do_register())

        self.retry_btn = tk.Label(body, text="[ 重试连接 ]", fg="white",
                                  bg="#e0a000", font=F(11), height=1)
        self.retry_btn.bind("<Button-1>", lambda e: self._do_retry())

        return f

    def _set_status(self, text, is_error=True):
        if getattr(self, "status_lbl", None):
            self.status_lbl.config(text=text,
                                   fg=RED if is_error else ONLINE)

    def do_login(self):
        self._commit_ime()
        u = self.fields["username"].strip()
        p = self.fields["password"]
        if not u or not p:
            return self._set_status("请填用户名和密码")
        self._set_status("连接中...", is_error=False)
        # 确保已连接
        if self.client.sock is None:
            if self.on_retry:
                self.on_retry()
        self.root.after(400, lambda: self.client.login(u, p))

    def do_register(self):
        self._commit_ime()
        u = self.fields["username"].strip()
        p = self.fields["password"]
        if not u or not p:
            return self._set_status("请填用户名和密码")
        self._set_status("")
        self.client.register(u, p)

    # ================================================================
    #  联系人列表
    # ================================================================
    def _build_contacts(self):
        f = tk.Frame(self.host, bg=LIST_BG)
        hdr = tk.Frame(f, bg=QQ_BLUE, height=HEADER_H)
        hdr.pack_propagate(False); hdr.pack(fill="x")
        tk.Label(hdr, text="QQ", fg="white", bg=QQ_BLUE,
                 font=F(16, "bold")).pack(side="left", padx=12)
        plus = tk.Label(hdr, text="+", fg="white", bg=QQ_BLUE,
                        font=F(16, "bold"))
        plus.pack(side="right", padx=12)
        plus.bind("<Button-1>", lambda e: self._open_menu())

        canvas = tk.Canvas(f, bg=LIST_BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        inner = tk.Frame(canvas, bg=LIST_BG)
        canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        self._bind_scroll(canvas)
        self.ctc_canvas = canvas
        self.ctc_inner  = inner
        return f

    def _refresh_contacts(self):
        for w in self.ctc_inner.winfo_children():
            w.destroy()
        for uid, c in self.contacts.items():
            self._ctc_row(uid, c["username"], self._preview(uid),
                          c.get("online"), self.unread.get(uid,0), False)
        for gid, g in self.groups.items():
            peer = "g:%d"%gid
            self._ctc_row(peer, g["name"], self._preview(peer),
                          True, self.unread.get(peer,0), True)
        self.ctc_canvas.configure(scrollregion=self.ctc_canvas.bbox("all"))

    def _preview(self, peer):
        ms = self.messages.get(peer, [])
        return ms[-1].text if ms else ""

    def _ctc_row(self, peer, name, preview, online, uc, is_grp):
        row = tk.Frame(self.ctc_inner, bg="white", height=48)
        row.pack_propagate(False); row.pack(fill="x")
        clr = "#9b59b6" if is_grp else QQ_BLUE
        make_avatar(row, name[0] if name else "?", clr).pack(
            side="left", padx=(8,6), pady=6)
        tb = tk.Frame(row, bg="white")
        tb.pack(side="left", fill="both", expand=True, pady=6)
        tag = "[群] " if is_grp else ""
        tk.Label(tb, text=tag+name, bg="white", fg=TEXT_DARK,
                 font=F(11,"bold"), anchor="w").pack(anchor="w")
        tk.Label(tb, text=preview or "", bg="white", fg=MUTE_GRAY,
                 font=F(9), anchor="w").pack(anchor="w")
        rt = tk.Frame(row, bg="white")
        rt.pack(side="right", padx=6)
        if not is_grp:
            tk.Label(rt, text="*", fg=ONLINE if online else OFFLINE,
                     font=F(7)).pack(anchor="e")
        if uc:
            tk.Label(rt, text=str(uc), fg="white", bg=RED,
                     font=F(8)).pack(anchor="e")
        tk.Frame(self.ctc_inner, bg="#eee", height=1).pack(fill="x")
        self._bind_tap(row, "<Button-1>",
                       lambda _, p=peer: self.open_chat(p))

    # ================================================================
    #  + 菜单
    # ================================================================
    def _build_menu(self):
        f = tk.Frame(self.host, bg=LIST_BG)
        hdr = tk.Frame(f, bg=QQ_BLUE, height=HEADER_H)
        hdr.pack_propagate(False); hdr.pack(fill="x")
        bk = tk.Label(hdr, text="<", fg="white", bg=QQ_BLUE,
                      font=F(14,"bold"))
        bk.pack(side="left", padx=(6,4))
        bk.bind("<Button-1>", lambda e: self.show_contacts())
        tk.Label(hdr, text="添加", fg="white", bg=QQ_BLUE,
                 font=F(14,"bold")).pack(side="left")
        hdr.pack(fill="x")
        body = tk.Frame(f, bg=LIST_BG)
        body.pack(fill="both", expand=True, padx=16, pady=16)
        items = [
            ("添加好友",   QQ_BLUE, lambda: self._open_add_friend()),
            ("创建群聊",   "#67c23a", lambda: self._open_create_group()),
            ("我的好友码", "#f0a020", lambda: self._open_mycode()),
            ("待接受的好友申请", "#e0a000", lambda: self._open_pending()),
        ]
        for label, color, cb in items:
            b = tk.Label(body, text=label, fg="white", bg=color,
                         font=F(14,"bold"), height=2)
            b.pack(fill="x", pady=6)
            b.bind("<Button-1>", lambda e, c=cb: c())
            if "待接受" in label:
                self.pending_btn = b
        self._refresh_pending_badge()
        return f

    # ================================================================
    #  添加好友
    # ================================================================
    def _build_add_friend(self):
        f = tk.Frame(self.host, bg=LIST_BG)
        hdr = tk.Frame(f, bg=QQ_BLUE, height=HEADER_H)
        hdr.pack_propagate(False); hdr.pack(fill="x")
        bk = tk.Label(hdr, text="<", fg="white", bg=QQ_BLUE,
                      font=F(13))
        bk.pack(side="left", padx=(6,4))
        bk.bind("<Button-1>", lambda e: self.show_contacts())
        tk.Label(hdr, text="添加好友", fg="white", bg=QQ_BLUE,
                 font=F(13)).pack(side="left")
        hdr.pack(fill="x")
        body = tk.Frame(f, bg=LIST_BG)
        body.pack(fill="both", expand=True, padx=14, pady=8)
        self.af_st = tk.Label(body, text="", fg=RED, bg=LIST_BG, font=F(9))
        self.af_st.pack(fill="x", pady=(0,4))
        lab = tk.Label(body, text="对方好友码", fg=MUTE_GRAY, bg="white",
                       font=F(11), anchor="w", padx=8)
        lab.pack(fill="x", pady=3); self.af_lbl = lab
        lab.bind("<Button-1>", lambda e: self.set_target("friendcode"))
        ok = tk.Label(body, text="确定", fg="white", bg=QQ_BLUE,
                       font=F(13,"bold"), height=2)
        ok.pack(fill="x", pady=8)
        ok.bind("<Button-1>", lambda e: self._do_af())
        return f

    def _do_af(self):
        self._commit_ime()
        code = self.fields["friendcode"].strip().upper()
        if not code: return self.af_st.config(text="请输入好友码")
        self.af_st.config(text="发送中...")
        self.client.add_friend(code)
        self.fields["friendcode"] = ""
        self._refresh_display()

    # ================================================================
    #  待接受的好友申请
    # ================================================================
    def _build_pending(self):
        f = tk.Frame(self.host, bg=LIST_BG)
        hdr = tk.Frame(f, bg=QQ_BLUE, height=HEADER_H)
        hdr.pack_propagate(False); hdr.pack(fill="x")
        bk = tk.Label(hdr, text="<", fg="white", bg=QQ_BLUE, font=F(13))
        bk.pack(side="left", padx=(6,4))
        bk.bind("<Button-1>", lambda e: self.show_contacts())
        tk.Label(hdr, text="待接受的好友申请", fg="white", bg=QQ_BLUE,
                 font=F(13)).pack(side="left")
        hdr.pack(fill="x")
        self.pending_hint = tk.Label(f, text="", fg=MUTE_GRAY, bg=LIST_BG,
                                     font=F(10))
        self.pending_hint.pack(fill="x", pady=4)
        canvas = tk.Canvas(f, bg=LIST_BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        inner = tk.Frame(canvas, bg=LIST_BG)
        canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        self._bind_scroll(canvas)
        self.pending_canvas = canvas
        self.pending_inner  = inner
        return f

    def _refresh_pending(self):
        if not getattr(self, "pending_inner", None):
            return
        for w in self.pending_inner.winfo_children():
            w.destroy()
        if not self.pending:
            self.pending_hint.config(text="暂无新的好友申请")
            self.pending_canvas.configure(scrollregion=(0,0,1,1))
            return
        self.pending_hint.config(text="以下用户申请加你为好友：")
        for ruid, r in self.pending.items():
            row = tk.Frame(self.pending_inner, bg="white", height=58)
            row.pack_propagate(False); row.pack(fill="x", pady=2)
            make_avatar(row, (r.get("username") or "?")[0], "#e0a000").pack(
                side="left", padx=(8,6), pady=8)
            tb = tk.Frame(row, bg="white")
            tb.pack(side="left", fill="both", expand=True, pady=6)
            tk.Label(tb, text=r.get("username","") or "", bg="white",
                     fg=TEXT_DARK, font=F(11,"bold"), anchor="w").pack(anchor="w")
            tk.Label(tb, text="好友码: "+str(r.get("friend_code","")), bg="white",
                     fg=MUTE_GRAY, font=F(9), anchor="w").pack(anchor="w")
            btnbox = tk.Frame(row, bg="white")
            btnbox.pack(side="right", padx=6)
            acc = tk.Label(btnbox, text="接受", fg="white", bg=ONLINE,
                           font=F(10,"bold"))
            acc.pack(pady=(0,3))
            acc.bind("<Button-1>", lambda e, u=ruid: self._do_accept(u))
            rej = tk.Label(btnbox, text="拒绝", fg="white", bg=RED, font=F(9))
            rej.pack()
            rej.bind("<Button-1>", lambda e, u=ruid: self._do_reject(u))
        self.pending_canvas.configure(scrollregion=self.pending_canvas.bbox("all"))

    def _do_accept(self, requester_uid):
        self.client.accept_friend(requester_uid)

    def _do_reject(self, requester_uid):
        self.pending.pop(requester_uid, None)
        self._refresh_pending(); self._refresh_pending_badge()
        self.client.reject_friend(requester_uid)

    def _refresh_pending_badge(self):
        if getattr(self, "pending_btn", None):
            n = len(self.pending)
            self.pending_btn.config(
                text="待接受的好友申请" + ((" (%d)" % n) if n else ""))



    # ================================================================
    #  我的好友码
    # ================================================================
    def _build_mycode(self):
        f = tk.Frame(self.host, bg=LIST_BG)
        hdr = tk.Frame(f, bg=QQ_BLUE, height=HEADER_H)
        hdr.pack_propagate(False); hdr.pack(fill="x")
        bk = tk.Label(hdr, text="<", fg="white", bg=QQ_BLUE, font=F(13))
        bk.pack(side="left", padx=(6,4))
        bk.bind("<Button-1>", lambda e: self.show_contacts())
        tk.Label(hdr, text="我的好友码", fg="white", bg=QQ_BLUE,
                 font=F(13)).pack(side="left")
        hdr.pack(fill="x")
        body = tk.Frame(f, bg=LIST_BG)
        body.pack(fill="both", expand=True, padx=16, pady=24)
        tk.Label(body, text="把好友码发给好友，对方用添加好友即可加你",
                 fg=MUTE_GRAY, bg=LIST_BG, font=F(11), justify="center").pack(pady=(0,16))
        self.code_box = tk.Label(body, text="----", fg="#222222",
                                 bg="white", font=F(26,"bold"), width=8,
                                 height=2, relief="ridge", borderwidth=2)
        self.code_box.pack(fill="x", pady=10)
        self.code_hint = tk.Label(body, text="", fg=MUTE_GRAY, bg=LIST_BG,
                                   font=F(10), justify="center")
        self.code_hint.pack(pady=6)
        return f

    def _refresh_mycode(self):
        if getattr(self, "code_box", None):
            code = (self.me or {}).get("friend_code", "")
            if code:
                self.code_box.config(text=code)
                self.code_hint.config(text="长按或截图发给好友")
            else:
                self.code_box.config(text="未登录")
                self.code_hint.config(text="请先登录/注册")

    # ================================================================
    #  创建群聊
    # ================================================================
    def _build_create_group(self):
        f = tk.Frame(self.host, bg=LIST_BG)
        hdr = tk.Frame(f, bg=QQ_BLUE, height=HEADER_H)
        hdr.pack_propagate(False); hdr.pack(fill="x")
        bk = tk.Label(hdr, text="<", fg="white", bg=QQ_BLUE,
                      font=F(13))
        bk.pack(side="left", padx=(6,4))
        bk.bind("<Button-1>", lambda e: self.show_contacts())
        tk.Label(hdr, text="创建群聊", fg="white", bg=QQ_BLUE,
                 font=F(13)).pack(side="left")
        hdr.pack(fill="x")
        body = tk.Frame(f, bg=LIST_BG)
        body.pack(fill="both", expand=True, padx=14, pady=8)
        self.cg_st = tk.Label(body, text="", fg=RED, bg=LIST_BG, font=F(9))
        self.cg_st.pack(fill="x", pady=(0,4))
        for txt, key in [("群名称","groupname"),
                         ("成员好友码(逗号分隔)","groupcodes")]:
            lab = tk.Label(body, text=txt, fg=MUTE_GRAY, bg="white",
                           font=F(11), anchor="w", padx=8)
            lab.pack(fill="x", pady=3)
            setattr(self, "cg_"+key[0]+"_lbl", lab)
            lab.bind("<Button-1>", lambda e, k=key: self.set_target(k))
        ok = tk.Label(body, text="创建", fg="white", bg="#67c23a",
                       font=F(13,"bold"), height=2)
        ok.pack(fill="x", pady=8)
        ok.bind("<Button-1>", lambda e: self._do_cg())
        return f

    def _do_cg(self):
        self._commit_ime()
        name = self.fields["groupname"].strip() or "群聊"
        codes = [c.strip().upper() for c in self.fields["groupcodes"].split(",")
                 if c.strip()]
        self.client.create_group(name, codes)
        self.fields["groupname"] = ""
        self.fields["groupcodes"] = ""
        self._refresh_display()

    # ================================================================
    #  聊天页
    # ================================================================
    def _build_chat(self):
        f = tk.Frame(self.host, bg=CHAT_BG)
        hdr = tk.Frame(f, bg=QQ_BLUE, height=HEADER_H)
        hdr.pack_propagate(False); hdr.pack(fill="x")
        bk = tk.Label(hdr, text="<", fg="white", bg=QQ_BLUE, font=F(18))
        bk.pack(side="left", padx=(6,0))
        bk.bind("<Button-1>", lambda e: self.show_contacts())
        self.chat_title = tk.Label(hdr, text="", fg="white", bg=QQ_BLUE,
                                   font=F(13,"bold"))
        self.chat_title.pack(side="left", padx=4)
        hdr.pack(fill="x")
        self.msg_canvas = tk.Canvas(f, bg=CHAT_BG, highlightthickness=0)
        self.msg_canvas.pack(fill="both", expand=True)
        self._bind_scroll(self.msg_canvas)
        ibar = tk.Frame(f, height=34, bg="#f0f0f0")
        ibar.pack_propagate(False); ibar.pack(fill="x")
        self.draft_label = tk.Label(ibar, text="输入消息…", fg=MUTE_GRAY,
                                    bg="#fff", font=F(10), anchor="w", padx=6)
        self.draft_label.pack(side="left", fill="both", expand=True,
                               padx=(6,4), pady=4)
        self.draft_label.bind("<Button-1>",
                              lambda e: self.set_target("draft"))
        snd = tk.Label(ibar, text="发送", fg="white", bg=QQ_BLUE,
                       font=F(11,"bold"), width=5)
        snd.pack(side="right", padx=(0,6), pady=4)
        snd.bind("<Button-1>", lambda e: self.send_message())
        return f

    def open_chat(self, peer):
        self.current = peer; self.unread[peer] = 0
        if isinstance(peer, str) and peer.startswith("g:"):
            name = self.groups.get(int(peer[2:]),{}).get("name","群聊")
        else:
            name = self.contacts.get(peer,{}).get("username","聊天")
        self.chat_title.config(text=name)
        self._goto("chat")
        self.render_msgs()

    def send_message(self):
        self._commit_ime()
        t = self.draft.strip()
        if not t or self.current is None: return
        peer = self.current
        if isinstance(peer,str) and peer.startswith("g:"):
            self.client.send_message(t, to_group=int(peer[2:]))
        else:
            self.client.send_message(t, to=peer)
        self.messages.setdefault(peer,[]).append(
            Message(self.me["username"], t, time.strftime("%H:%M"), True))
        self.draft = ""; self.render_msgs(); self._refresh_display()

    # ================================================================
    #  屏幕键盘 —— grid 矩阵布局（每个按键都是真实可见的 Button）
    # ================================================================
    def _build_keys(self):
        """构建/重建所有按键，使用 grid 布局到 keys_frame"""
        # 清除旧按键
        for w in self.keys_frame.grid_slaves():
            w.destroy()

        ime_tag = "中" if self.ime_on else "EN"

        if self.kb_mode == "abc":
            # 4 行布局 —— 压缩到能在 320px 屏幕内显示
            rows_data = [
                list("qwertyuiop"),
                list("asdfghjkl;"),
                ["^"] + list("zxcvbnm,.") + ["<-"],
                [ime_tag, "123", " ", ".", "<-", ">"],
            ]
        else:
            # 数字/符号模式 —— 3 行更紧凑
            rows_data = [
                list("1234567890"),
                list("-_@#!$%&*()"),
                [ime_tag, "abc", " ", ".", "<-", ">"],
            ]

        for ri, row_data in enumerate(rows_data):
            n_cols = len(row_data)
            for ci, k in enumerate(row_data):
                btn = self._make_key_button(k)
                btn.grid(row=ri, column=ci, sticky="nsew", padx=1, pady=1)
                # 让每列等宽
                self.keys_frame.columnconfigure(ci, weight=1, uniform="key")

        # 让每行等高
        for ri in range(len(rows_data)):
            self.keys_frame.rowconfigure(ri, weight=1, uniform="key")

    def _make_key_button(self, k):
        """创建单个按键按钮（返回一个 tk.Button 或 tk.Label）"""
        # ---- 决定外观 ----
        if k == "<":
            disp = "<-"
            bg_c, fg_c = "#ddd", TEXT_DARK
            ft = F(KEY_FONT_SIZE)
        elif k == "^":
            disp = "^"; bg_c, fg_c = "#ddd", TEXT_DARK; ft = F(KEY_FONT_SIZE)
        elif k == ">":
            disp = "↵"   # 回车/确认（上下文感知：聊天=发送，登录=登录，加好友=确定，建群=创建）
            bg_c, fg_c = QQ_BLUE, "white"; ft = F(KEY_FONT_SIZE, "bold")
        elif k in ("中", "EN"):
            disp = k
            bg_c = "#a8d4ff" if self.ime_on else "#e0e0e0"
            fg_c = "#0044aa"; ft = F(KEY_FONT_SIZE, "bold")
        elif k in ("123", "abc"):
            disp = k; bg_c, fg_c = "#ddd", TEXT_DARK; ft = F(9)
        elif k == " ":
            disp = "空格"; bg_c, fg_c = "#eee", TEXT_DARK; ft = F(KEY_FONT_SIZE)
        elif k == ".":
            disp = "."; bg_c, fg_c = "#eee", TEXT_DARK; ft = F(KEY_FONT_SIZE)
        else:
            # 字母/数字
            disp = k.upper() if (self.caps and k.isalpha()) else k
            bg_c, fg_c = KEY_BG, KEY_FG; ft = F(KEY_FONT_SIZE)

        btn = tk.Button(
            self.keys_frame,
            text=disp,
            bg=bg_c, fg=fg_c, font=ft,
            activebackground="#ccc", activeforeground=TEXT_DARK,
            relief="raised", bd=1,
            highlightthickness=0,
            padx=2, pady=2,
        )
        btn.bind("<Button-1>", lambda ev, kk=k: self._key_press(kk))
        return btn

    def _key_press(self, ch):
        if ch == "<":
            # 退格
            if self.ime_on and self.ime_py:
                self.ime_py = self.ime_py[:-1]
                self._render_cands()
            else:
                self._del_char()
        elif ch == " ":
            # 空格
            if self.ime_on and self.ime_py:
                if self.ime_cands:
                    self._commit(self.ime_cands[0])
                else:
                    self._type(self.ime_py); self.ime_py=""
                    self._render_cands()
            else:
                self._type(" ")
        elif ch == ">":
            # 回车/确认（上下文感知，见 _confirm）
            self._confirm()
        elif ch == "123":
            self.kb_mode = "123"; self._build_keys()
        elif ch == "abc":
            self.kb_mode = "abc"; self._build_keys()
        elif ch == "^":
            self.caps = not self.caps; self._build_keys()
        elif ch in ("中", "EN"):
            self._commit_ime()       # 切中文/英文前先把未选拼音提交，避免丢字
            self.ime_on = not self.ime_on
            self.ime_py = ""
            self._render_cands()
            self._build_keys()
        elif ch == "<-":
            # 退格键 → 删除最后一个字符
            if self.ime_py:
                self.ime_py = self.ime_py[:-1]
                self._render_cands()
            else:
                self._del_char()
        else:
            ascii_field = self.input_target in ("friendcode", "groupcodes")
            if self.ime_on and self.kb_mode=="abc" and len(ch)==1 and ch.isalpha() and not ascii_field:
                self.ime_py += ch.lower()
                self._render_cands()
            else:
                self._type(ch)
        self._refresh_display()

    def _type(self, ch):
        if self.input_target == "draft":
            self.draft += ch
        elif self.input_target:
            self.fields[self.input_target] += ch

    def _del_char(self):
        if self.input_target == "draft":
            self.draft = self.draft[:-1]
        elif self.input_target:
            self.fields[self.input_target] = \
                self.fields[self.input_target][:-1]

    def _commit(self, char):
        self._type(char); self.ime_py = ""; self._render_cands()

    def _commit_ime(self):
        """把当前未确认的拼音缓冲提交进输入框（有候选取第一个，否则原样提交）。"""
        if self.ime_py:
            if self.ime_cands:
                self._commit(self.ime_cands[0])
            else:
                self._type(self.ime_py); self.ime_py = ""
                self._render_cands()

    def _confirm(self):
        """回车/确认键（↵）：先提交残留拼音，再按当前页面触发对应动作。"""
        self._commit_ime()
        page = self.current_page
        if self.input_target == "draft":
            self.send_message()
        elif page == "auth":
            self.do_login()
        elif page == "add_friend":
            self._do_af()
        elif page == "create_group":
            self._do_cg()

    # ================================================================
    #  候选条渲染
    # ================================================================
    def _render_cands(self):
        for w in self.cand_bar.winfo_children(): w.destroy()
        if self.ime_on and self.ime_py:
            cs = PINYIN.get(self.ime_py, [])
            self.ime_cands = cs[:8]
            if cs:
                for c in self.ime_cands:
                    b = tk.Button(self.cand_bar, text=c, bg="#fff",
                                  fg=TEXT_DARK, font=F(13,"bold"),
                                  relief="raised", bd=1, padx=5, pady=1)
                    b.pack(side="left", padx=1, pady=1)
                    b.bind("<Button-1>",
                           lambda e, ch=c: self._commit(ch))
            else:
                tk.Label(self.cand_bar,
                         text='无匹配: "%s"' % self.ime_py,
                         bg="#ffe0e0", fg=RED, font=F(9)).pack(
                             side="left", padx=3)
        else:
            self.ime_cands = []
            hint = "中文模式：打拼音出汉字" if self.ime_on else "英文直输模式"
            tk.Label(self.cand_bar, text=hint, bg="#e8ecf4",
                     fg=TEXT_DARK, font=F(9,"bold")).pack(side="left", padx=4)

    # ================================================================
    #  输入焦点 & 显示刷新
    # ================================================================
    def set_target(self, target):
        self._commit_ime()   # 切到别的输入框前，先把未确认的拼音提交，避免丢字
        self.input_target = target
        # 纯 ASCII 字段（IP/用户名/密码/好友码/群码）强制英文模式，避免拼音吞掉字母
        if target in ("serverip", "username", "password",
                      "friendcode", "groupcodes"):
            self.ime_on = False
        self._highlight(target)
        self._refresh_display()

    def _highlight(self, target):
        m = {
            "serverip":   getattr(self, "server_lbl", None),
            "username":   getattr(self, "user_lbl",   None),
            "password":   getattr(self, "pass_lbl",   None),
            "friendcode": getattr(self, "af_lbl",     None),
            "groupname":  getattr(self, "cg_g_lbl",   None),
            "groupcodes":getattr(self, "cg_c_lbl",   None),
        }
        for k, lbl in m.items():
            if not lbl: continue
            if k == target:
                lbl.config(bg="#d6ebff", fg=TEXT_DARK)
            else:
                lbl.config(bg="white", fg=MUTE_GRAY)

    def _refresh_display(self):
        f = self.fields
        pairs = [
            ("serverip",   getattr(self, "server_lbl", None),
             lambda v: (v, TEXT_DARK) if v else ("请输入服务器IP", MUTE_GRAY)),
            ("username",   getattr(self, "user_lbl",   None),
             lambda v: (v, TEXT_DARK) if v else ("请输入用户名", MUTE_GRAY)),
            ("password",   getattr(self, "pass_lbl",   None),
             lambda v: ("*"*len(v), TEXT_DARK) if v else ("请输入密码", MUTE_GRAY)),
            ("friendcode", getattr(self, "af_lbl",     None),
             lambda v: (v, TEXT_DARK) if v else ("对方好友码", MUTE_GRAY)),
            ("groupname",  getattr(self, "cg_g_lbl",   None),
             lambda v: (v, TEXT_DARK) if v else ("群名称", MUTE_GRAY)),
            ("groupcodes",getattr(self, "cg_c_lbl",   None),
             lambda v: (v, TEXT_DARK) if v else ("成员好友码(逗号分隔)", MUTE_GRAY)),
        ]
        for key, lbl, fmt in pairs:
            if lbl:
                text, color = fmt(f[key])
                lbl.config(text=text, fg=color)

        if getattr(self, "draft_label", None) and self.input_target=="draft":
            self.draft_label.config(
                text=self.draft or "输入消息…",
                fg=TEXT_DARK if self.draft else MUTE_GRAY)

        self._refresh_mycode()

        if getattr(self, "kb_draft_lbl", None):
            # 当前输入框中文名，让提示一眼看清在填哪个字段
            field_names = {
                "serverip":   "IP",
                "username":   "用户名",
                "password":   "密码",
                "friendcode": "好友码",
                "groupname":  "群名",
                "groupcodes": "成员码",
                "draft":      "消息",
            }
            tgt = (self.draft if self.input_target=="draft"
                   else f.get(self.input_target,"") if self.input_target else "")
            field_label = field_names.get(self.input_target, "")
            py_part = (self.ime_py+"|") if (self.ime_on and self.ime_py) else ""
            mode = "[中]" if self.ime_on else "[EN]"
            if self.input_target == "password" and tgt:
                shown = "*"*len(tgt)   # 密码用圆点隐藏
            else:
                shown = tgt
            hint = f"{mode} {field_label}: {py_part}{shown}" if field_label else f"{mode} {py_part}{shown}"
            self.kb_draft_lbl.config(text=hint)

    # ================================================================
    #  消息气泡
    # ================================================================
    def render_msgs(self):
        c = self.msg_canvas; c.delete("all")
        y = 4; prev_ts = None
        ms = self.messages.get(self.current, [])
        is_grp = isinstance(self.current,str) and self.current.startswith("g:")
        for m in ms:
            if m.ts != prev_ts:
                c.create_text(SCREEN_W//2, y, text=m.ts, font=F(8),
                              fill=MUTE_GRAY, anchor="n")
                y += 13; prev_ts = m.ts
            if is_grp and not m.mine:
                c.create_text(8, y, text=m.sender_name, font=F(8),
                              fill="#aaa", anchor="nw")
                y += 11
            y = self._bubble(m, y)
        c.configure(scrollregion=(0,0,SCREEN_W,max(y,1)))
        c.yview_moveto(1.0)

    def _bubble(self, m, y):
        MW = 164; P = 5
        tmp = self.msg_canvas.create_text(0,0,text=m.text,font=F(10),
                                          width=MW,anchor="nw",fill=TEXT_DARK)
        bb = self.msg_canvas.bbox(tmp)
        tw,th = bb[2]-bb[0], bb[3]-bb[1]
        self.msg_canvas.delete(tmp)
        bw,bh = tw+P*2, th+P*2
        bx = SCREEN_W-bw-6 if m.mine else 6
        fill = SENT_BUB if m.mine else RECV_BUB
        rr = round_rect(self.msg_canvas, bx,y,bw,bh,6,fill)
        tx = self.msg_canvas.create_text(bx+P,y+P,text=m.text,
                                         font=F(10),width=MW,
                                         anchor="nw",fill=TEXT_DARK)
        for item in rr: self.msg_canvas.lower(item,tx)
        return y+bh+5

    # ================================================================
    #  网络回调
    # ================================================================
    def on_net(self, msg):
        t = msg.get("type")
        if t in ("logged_in","registered"):
            self.me = {"uid":msg["uid"],"username":msg["username"],
                        "friend_code":msg.get("friend_code","")}
            self._set_status("")
            self._goto("contacts")
        elif t == "state":
            self._apply_state(msg); self._goto("contacts")
        elif t == "error":
            self._on_err(msg.get("msg",""))
        elif t == "friend_added":
            self._add_ct(msg["contact"]); self.show_contacts()
        elif t == "new_friend":
            self._add_ct(msg["contact"])
        elif t == "friend_request":
            self._on_friend_request(msg)
        elif t == "request_sent":
            if self.current_page == "add_friend" and hasattr(self, "af_st"):
                self.af_st.config(text="好友申请已发送，等待对方通过")
        elif t == "request_accepted":
            c = msg.get("contact", {})
            self.pending.pop(c.get("uid"), None)
            self._add_ct(c); self._refresh_pending(); self._refresh_pending_badge()
            self.show_contacts()
        elif t == "request_rejected":
            self._set_status("%s 拒绝了你的好友申请" %
                             msg.get("from_name", "对方"), is_error=False)
        elif t == "group_created":
            self._add_gp(msg["group"]); self.show_contacts()
        elif t == "new_group":
            self._add_gp(msg["group"])
        elif t == "msg":
            self._incoming(msg)

    def _on_err(self, text):
        self._set_status(text)
        if self.current_page=="add_friend" and hasattr(self,'af_st'):
            self.af_st.config(text=text)
        if self.current_page=="create_group" and hasattr(self,'cg_st'):
            self.cg_st.config(text=text)

    def _on_friend_request(self, msg):
        ruid = msg.get("from_uid")
        if ruid is None:
            return
        self.pending[ruid] = {"uid": ruid,
                              "username": msg.get("from_name",""),
                              "friend_code": msg.get("from_code","")}
        self._refresh_pending(); self._refresh_pending_badge()
        self._set_status("%s 申请加你为好友" % msg.get("from_name",""),
                         is_error=False)

    def _apply_state(self, msg):
        self.contacts={}; self.groups={}; self.messages={}; self.pending={}
        for c in msg.get("contacts",[]):
            self.contacts[c["uid"]]=c; self.uid_names[c["uid"]]=c["username"]
        for g in msg.get("groups",[]):
            self.groups[g["gid"]]=g
        for p in msg.get("pending", []):
            self.pending[p["uid"]] = p
        for h in msg.get("history",[]):
            peer=h["peer"]; mine=h.get("from")==self.me["uid"]
            nm=h.get("from_name") or self.uid_names.get(h.get("from"),"??")
            self.messages.setdefault(peer,[]).append(
                Message(nm,h["text"],h.get("ts",""),mine))
        self._refresh_contacts(); self._refresh_pending(); self._refresh_pending_badge()

    def _add_ct(self, c):
        self.contacts[c["uid"]]=c; self.uid_names[c["uid"]]=c["username"]
        self._refresh_contacts()

    def _add_gp(self, g):
        self.groups[g["gid"]]=g; self._refresh_contacts()

    def _incoming(self, msg):
        if msg.get("group") is not None:
            peer="g:%d"%msg["group"]
        else:
            peer=msg["from"]
        sn=msg.get("from_name","")
        mine=msg.get("from")==self.me["uid"]
        self.uid_names[msg.get("from")]=sn
        self.messages.setdefault(peer,[]).append(
            Message(sn,msg["text"],msg.get("ts",""),mine))
        if self.current_page=="chat" and self.current==peer:
            self.render_msgs()
        else:
            self.unread[peer]=self.unread.get(peer,0)+1
            if self.current_page=="contacts":
                self._refresh_contacts()

    # ---- 连接状态 ----
    def _on_connected(self):
        self._set_status("")
        if hasattr(self,'retry_btn'): self.retry_btn.pack_forget()
    def _on_conn_fail(self, host="?", port=8888, text=""):
        t = (text or "").lower()
        if "timed out" in t or "timeout" in t:
            reason = "超时：检查板子WiFi/联网，或服务器IP是否正确"
        elif "refused" in t:
            reason = "被拒绝：服务器没开 / 端口不对"
        elif "getaddrinfo" in t or "name or service" in t or "nodename" in t or "not known" in t:
            reason = "域名解析失败：DNS 无法解析，检查板子联网"
        elif "unreachable" in t or "no route" in t or "network is down" in t:
            reason = "网络不可达：板子没连上任何网络"
        else:
            reason = (text or "未知错误")[:40]
        msg = "连不上 %s:%d\n%s" % (host, port, reason)
        self._set_status(msg)
        if hasattr(self,'retry_btn'): self.retry_btn.pack(fill="x",pady=4)
    def _do_retry(self):
        if self.on_retry: self.on_retry()

    # ================================================================
    #  通用工具
    # ================================================================
    def _bind_scroll(self, cv):
        cv.configure(yscrollincrement=1)
        def dn(e): self._drag_active=True; self._drag_y=e.y
        def mv(e):
            if self._drag_active:
                cv.yview_scroll(int(self._drag_y-e.y),"units")
                self._drag_y=e.y
        def up(e): self._drag_active=False
        cv.bind("<ButtonPress-1>",dn)
        cv.bind("<B1-Motion>",mv)
        cv.bind("<ButtonRelease-1>",up)
        try: cv.bind("<MouseWheel>",
                     lambda e:cv.yview_scroll(-int(e.delta//120),"units"))
        except: pass

    def _bind_tap(self, widget, seq, cb):
        try: widget.bind(seq, cb)
        except: pass
        for ch in widget.winfo_children():
            self._bind_tap(ch, seq, cb)

    def _bind_pc_keys(self):
        def onk(e):
            if not self.input_target: return
            if e.keysym=="Return":
                self._confirm()
                return
            if e.keysym=="BackSpace":
                self._del_char(); self._refresh_display(); return
            if e.keysym=="space":
                if self.ime_on and self.ime_py:
                    if self.ime_cands: self._commit(self.ime_cands[0])
                    else: self._type(self.ime_py);self.ime_py="";self._render_cands()
                else: self._type(" ")
                self._refresh_display(); return
            if len(e.char)==1 and e.char.isprintable():
                if self.ime_on and e.char.isalpha():
                    self.ime_py+=e.char.lower();self._render_cands()
                else:
                    self._type(e.char)
                self._refresh_display()
        self.root.bind("<Key>", onk)
