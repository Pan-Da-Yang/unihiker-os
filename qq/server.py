# server.py - 行空板 QQ 的 PC 端服务器（零依赖，TCP + JSON 行协议）
#
# 功能：
#   - 注册 / 登录（密码 sha256+salt，登录后下发 token）
#   - 好友码（6 位）添加好友，双向生效，在线方实时收到通知
#   - 创建群聊（按好友码邀请成员），群消息广播给在线成员
#   - 消息转发：在线实时推送 + 离线/历史全量存储（登录时同步）
#   - 内置“QQ小助手”机器人，注册即自动成为好友，可关键词应答
#
# 运行：  python server.py        （默认监听 0.0.0.0:8888）
# 数据：  users.json（同目录，自动创建）

import socket
import threading
import json
import hashlib
import os
import time
import random
import string
import secrets

HOST = "0.0.0.0"
PORT = 8888
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

lock = threading.RLock()
users = {}        # uid(int) -> dict
groups = {}       # gid(int) -> dict
by_name = {}      # username -> uid
by_code = {}      # friend_code -> uid
sessions = {}     # token -> uid
online = {}       # uid -> Handler（用于主动推送）
next_uid = 1
next_gid = 1
BOT_UID = 0


# ---------------- 持久化 ----------------
def load():
    global next_uid, next_gid
    if not os.path.exists(DATA_FILE):
        init_bot()
        return
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        users.clear(); groups.clear()
        users.update({int(k): v for k, v in data.get("users", {}).items()})
        groups.update({int(k): v for k, v in data.get("groups", {}).items()})
        next_uid = data.get("next_uid", (max(users) + 1 if users else 1))
        next_gid = data.get("next_gid", (max(groups) + 1 if groups else 1))
        rebuild_index()
        if BOT_UID not in users:
            init_bot()
        print(f"已加载 {len(users)} 个用户、{len(groups)} 个群")
    except Exception as e:
        print("load error:", e)
        users.clear(); groups.clear()
        init_bot()


def rebuild_index():
    by_name.clear(); by_code.clear()
    for uid, u in users.items():
        by_name[u["username"]] = uid
        if u.get("friend_code"):
            by_code[u["friend_code"]] = uid


def init_bot():
    global next_uid
    bot = {"uid": BOT_UID, "username": "QQ小助手", "pw_hash": "", "salt": "",
           "friend_code": "000000", "friends": [], "groups": [],
           "messages": [], "pending": [], "is_bot": True}
    users[BOT_UID] = bot
    by_name["QQ小助手"] = BOT_UID
    by_code["000000"] = BOT_UID
    save()


def save():
    with lock:
        data = {"users": {str(k): v for k, v in users.items()},
                "groups": {str(k): v for k, v in groups.items()},
                "next_uid": next_uid, "next_gid": next_gid}
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, DATA_FILE)


# ---------------- 工具 ----------------
def hash_pw(pw, salt):
    return hashlib.sha256((salt + pw).encode("utf-8")).hexdigest()


def gen_salt():
    return "".join(random.choices(string.ascii_letters + string.digits, k=8))


def make_code():
    while True:
        c = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if c not in by_code:
            return c


def push(uid, obj):
    h = online.get(uid)
    if h is not None:
        h.send(obj)
        return True
    return False


def bot_reply(text):
    t = text
    if any(k in t for k in ("时间", "几点", "现在")):
        return "现在时间是 " + time.strftime("%H:%M") + "，服务器状态良好~"
    if "日期" in t or "今天" in t or "星期" in t:
        w = "一二三四五六日"[int(time.strftime("%w"))]
        return "今天是 " + time.strftime("%Y-%m-%d") + "，星期" + w
    if "天气" in t:
        return "服务器暂时没接天气模块，不过可以帮你写个联网查天气的脚本~"
    if any(k in t for k in ("你好", "您好", "hi", "hello")):
        return "你好呀！我是跑在 PC 上的 QQ 小助手~"
    if "在吗" in t or "在不在" in t:
        return "在的在的，我一直在线！"
    if "爱" in t or "喜欢" in t:
        return "我也喜欢和你一起折腾这个联机 QQ^_^"
    if "?" in t or "？" in t:
        return random.choice(["这是个好问题！", "让我想想……", "你可以再具体说说吗？"])
    return random.choice(["嗯嗯，我在听~", "哈哈，有意思！", "收到收到！",
                          "这个想法不错哎。", "稍等，让我转转小脑瓜~"])


# ---------------- 连接处理 ----------------
class Handler(threading.Thread):
    def __init__(self, conn, addr):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.uid = None
        self.token = None
        self.buf = ""
        self.send_lock = threading.Lock()

    def run(self):
        try:
            for line in self._lines():
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                try:
                    self.handle(msg)
                except Exception as e:
                    print("handle error:", e)
        finally:
            self.disconnect()

    def _lines(self):
        while True:
            try:
                data = self.conn.recv(4096)
            except Exception:
                break
            if not data:
                break
            self.buf += data.decode("utf-8", "replace")
            while "\n" in self.buf:
                line, self.buf = self.buf.split("\n", 1)
                line = line.strip()
                if line:
                    yield line

    def send(self, obj):
        try:
            with self.send_lock:
                self.conn.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        except Exception:
            pass

    # --- 鉴权 ---
    def _auth(self, msg):
        token = msg.get("token")
        with lock:
            uid = sessions.get(token)
        if uid is None:
            self.send({"type": "error", "msg": "请先登录"})
            return None
        self.uid = uid
        return uid

    def handle(self, msg):
        t = msg.get("type")
        if t == "register":
            self.do_register(msg)
        elif t == "login":
            self.do_login(msg)
        elif t == "add_friend":
            uid = self._auth(msg)
            if uid is not None:
                self.do_add_friend(msg, uid)
        elif t == "accept_friend":
            uid = self._auth(msg)
            if uid is not None:
                self.do_accept_friend(msg, uid)
        elif t == "reject_friend":
            uid = self._auth(msg)
            if uid is not None:
                self.do_reject_friend(msg, uid)
        elif t == "create_group":
            uid = self._auth(msg)
            if uid is not None:
                self.do_create_group(msg, uid)
        elif t == "message":
            uid = self._auth(msg)
            if uid is not None:
                self.do_message(msg, uid)
        elif t == "list":
            uid = self._auth(msg)
            if uid is not None:
                self._send_state(uid)
        elif t == "logout":
            self.disconnect()
        else:
            self.send({"type": "error", "msg": "未知请求: %s" % t})

    # --- 注册 ---
    def do_register(self, msg):
        username = (msg.get("username") or "").strip()
        pw = msg.get("password") or ""
        if not username or not pw:
            return self.send({"type": "error", "msg": "用户名和密码不能为空"})
        if len(username) > 20 or len(pw) > 40:
            return self.send({"type": "error", "msg": "用户名/密码过长"})
        with lock:
            if username in by_name:
                return self.send({"type": "error", "msg": "用户名已存在"})
            global next_uid
            uid = next_uid
            next_uid += 1
            salt = gen_salt()
            u = {"uid": uid, "username": username, "salt": salt,
                 "pw_hash": hash_pw(pw, salt), "friend_code": make_code(),
                 "friends": [BOT_UID], "groups": [], "messages": [], "pending": [],
                 "is_bot": False}
            users[uid] = u
            by_name[username] = uid
            by_code[u["friend_code"]] = uid
            users[BOT_UID]["friends"].append(uid)
            save()
        token = self._new_session(uid)
        with lock:
            online[uid] = self   # 注册即视为在线，便于收发推送
        self.send({"type": "registered", "ok": True, "uid": uid,
                   "friend_code": u["friend_code"], "token": token,
                   "username": username})
        self._send_state(uid)

    # --- 登录 ---
    def do_login(self, msg):
        username = (msg.get("username") or "").strip()
        pw = msg.get("password") or ""
        with lock:
            uid = by_name.get(username)
            if uid is None:
                return self.send({"type": "error", "msg": "用户不存在"})
            u = users[uid]
            if u.get("is_bot"):
                return self.send({"type": "error", "msg": "不能登录机器人"})
            if u["pw_hash"] != hash_pw(pw, u["salt"]):
                return self.send({"type": "error", "msg": "密码错误"})
        token = self._new_session(uid)
        self.uid = uid
        with lock:
            online[uid] = self
        self.send({"type": "logged_in", "ok": True, "uid": uid,
                   "username": username, "friend_code": u["friend_code"],
                   "token": token})
        self._send_state(uid)

    def _new_session(self, uid):
        token = secrets.token_hex(16)
        with lock:
            sessions[token] = uid
        self.token = token
        self.uid = uid
        return token

    # --- 下发完整状态（联系人 + 群 + 历史） ---
    def _send_state(self, uid):
        with lock:
            u = users[uid]
            contacts = []
            for fuid in u["friends"]:
                fu = users.get(fuid)
                if not fu:
                    continue
                contacts.append({"uid": fuid, "username": fu["username"],
                                 "friend_code": fu.get("friend_code", ""),
                                 "online": fuid in online,
                                 "is_bot": fu.get("is_bot", False)})
            gl = []
            for gid in u["groups"]:
                g = groups.get(gid)
                if not g:
                    continue
                gl.append({"gid": gid, "name": g["name"],
                           "members": [users[m]["username"] for m in g["members"] if m in users]})
            history = [{"peer": m["peer"], "from": m["from"],
                        "text": m["text"], "ts": m["ts"]}
                       for m in u.get("messages", [])]
            pending_list = []
            for ruid in u.get("pending", []):
                ru = users.get(ruid)
                if ru:
                    pending_list.append({"uid": ruid, "username": ru["username"],
                                         "friend_code": ru.get("friend_code", "")})
        self.send({"type": "state", "contacts": contacts,
                   "groups": gl, "history": history, "pending": pending_list})

    # --- 添加好友（发送申请，对方接受后才会成为好友） ---
    def do_add_friend(self, msg, uid):
        code = (msg.get("code") or "").strip().upper()
        with lock:
            target = by_code.get(code)
            if target is None:
                return self.send({"type": "error", "msg": "好友码不存在"})
            if target == uid:
                return self.send({"type": "error", "msg": "不能添加自己"})
            u = users[uid]
            if target in u["friends"]:
                return self.send({"type": "error", "msg": "已经是好友了"})
            tgt_pending = users[target].setdefault("pending", [])
            if uid in tgt_pending:
                return self.send({"type": "error",
                                  "msg": "好友申请已发送，等待对方通过"})
            tgt_pending.append(uid)
            save()
            tu = users[target]
            contact = {"uid": target, "username": tu["username"],
                       "friend_code": tu.get("friend_code", "")}
        self.send({"type": "request_sent", "ok": True,
                   "to_uid": target, "to_name": tu["username"],
                   "to_code": tu.get("friend_code", "")})
        push(target, {"type": "friend_request", "from_uid": uid,
                      "from_name": users[uid]["username"],
                      "from_code": users[uid].get("friend_code", "")})

    # --- 接受好友申请 ---
    def do_accept_friend(self, msg, uid):
        try:
            ruid = int(msg.get("uid"))
        except Exception:
            return self.send({"type": "error", "msg": "无效申请"})
        with lock:
            p = users[uid].setdefault("pending", [])
            if ruid not in p:
                return self.send({"type": "error", "msg": "没有该好友申请"})
            p.remove(ruid)
            users[uid]["friends"].append(ruid)
            users[ruid]["friends"].append(uid)
            ru = users[ruid]
            save()
            contact_to_requester = {
                "uid": uid, "username": users[uid]["username"],
                "friend_code": users[uid].get("friend_code", ""),
                "online": uid in online, "is_bot": False}
            contact_to_accepter = {
                "uid": ruid, "username": ru["username"],
                "friend_code": ru.get("friend_code", ""),
                "online": ruid in online,
                "is_bot": ru.get("is_bot", False)}
        # 推送给申请方：已成为好友
        push(ruid, {"type": "new_friend", "contact": contact_to_requester})
        self.send({"type": "request_accepted", "ok": True,
                   "contact": contact_to_accepter})

    # --- 拒绝好友申请 ---
    def do_reject_friend(self, msg, uid):
        try:
            ruid = int(msg.get("uid"))
        except Exception:
            return self.send({"type": "error", "msg": "无效申请"})
        with lock:
            p = users[uid].setdefault("pending", [])
            if ruid in p:
                p.remove(ruid)
                save()
        push(ruid, {"type": "request_rejected", "from_uid": uid,
                    "from_name": users[uid]["username"]})
        self.send({"type": "request_rejected_ack", "ok": True})

    # --- 创建群聊 ---
    def do_create_group(self, msg, uid):
        name = (msg.get("name") or "群聊").strip()[:20] or "群聊"
        codes = msg.get("member_codes") or []
        with lock:
            global next_gid
            gid = next_gid
            next_gid += 1
            members = [uid]
            for c in codes:
                t = by_code.get(str(c).strip().upper())
                if t is not None and t not in members:
                    members.append(t)
            g = {"gid": gid, "name": name, "owner": uid,
                 "members": members, "history": []}
            groups[gid] = g
            for m in members:
                if m in users:
                    users[m]["groups"].append(gid)
            save()
            glist = [users[m]["username"] for m in members if m in users]
        self.send({"type": "group_created", "ok": True,
                   "group": {"gid": gid, "name": name, "members": glist}})
        for m in members:
            if m != uid:
                push(m, {"type": "new_group", "group": {
                    "gid": gid, "name": name, "members": glist}})

    # --- 发消息 ---
    def do_message(self, msg, uid):
        text = (msg.get("text") or "").strip()
        if not text:
            return
        text = text[:500]
        ts = time.strftime("%H:%M")
        with lock:
            u = users[uid]
            uname = u["username"]
        if msg.get("to_group"):
            gid = msg["to_group"]
            with lock:
                g = groups.get(gid)
                if not g or uid not in g["members"]:
                    return self.send({"type": "error", "msg": "不在该群"})
                g["history"].append({"from": uid, "from_name": uname,
                                     "text": text, "ts": ts})
                g["history"] = g["history"][-200:]
                members = list(g["members"])
                for m in members:
                    users[m]["messages"].append(
                        {"peer": "g:%d" % gid, "from": uid, "from_name": uname,
                         "text": text, "ts": ts})
                    users[m]["messages"] = users[m]["messages"][-200:]
                save()
            for m in members:
                if m != uid:
                    push(m, {"type": "msg", "from": uid, "from_name": uname,
                             "group": gid, "text": text, "ts": ts})
            self.send({"type": "sent", "ok": True})
        else:
            try:
                to = int(msg.get("to"))
            except Exception:
                return self.send({"type": "error", "msg": "无效接收者"})
            with lock:
                if to not in users:
                    return self.send({"type": "error", "msg": "用户不存在"})
                users[uid]["messages"].append(
                    {"peer": to, "from": uid, "from_name": uname, "text": text, "ts": ts})
                users[uid]["messages"] = users[uid]["messages"][-200:]
                users[to]["messages"].append(
                    {"peer": uid, "from": uid, "from_name": uname, "text": text, "ts": ts})
                users[to]["messages"] = users[to]["messages"][-200:]
                save()
                toname = users[to]["username"]
            is_bot = False
            with lock:
                is_bot = users[to].get("is_bot", False)
            push(to, {"type": "msg", "from": uid, "from_name": uname,
                      "text": text, "ts": ts})
            if is_bot:
                reply = bot_reply(text)
                rts = time.strftime("%H:%M")
                with lock:
                    users[uid]["messages"].append(
                        {"peer": to, "from": to, "text": reply, "ts": rts})
                    users[uid]["messages"] = users[uid]["messages"][-200:]
                    save()
                self.send({"type": "msg", "from": to, "from_name": toname,
                           "text": reply, "ts": rts})
            self.send({"type": "sent", "ok": True})

    def disconnect(self):
        with lock:
            if self.token and sessions.get(self.token) == self.uid:
                sessions.pop(self.token, None)
            if self.uid is not None and online.get(self.uid) is self:
                online.pop(self.uid, None)
            self.uid = None
            self.token = None


def main():
    load()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(64)
    print("QQ 服务器已启动，监听 %s:%d" % (HOST, PORT))
    print("板子端连接时填本机局域网 IP（用 ipconfig / ifconfig 查）")
    try:
        while True:
            conn, addr = srv.accept()
            Handler(conn, addr).start()
    except KeyboardInterrupt:
        print("\n服务器已关闭")


if __name__ == "__main__":
    main()
