# selftest_full.py - 行空板 QQ 联机版完整端到端自测
#
# 覆盖：注册 -> 加好友 -> 建群 -> 私聊 -> 群聊 -> 机器人 -> 离线消息
# 用法：先启动 server.py，再跑本脚本（默认 127.0.0.1:8888）
import sys, time, threading
sys.path.insert(0, "C:/Users/潘杨/WorkBuddy/2026-07-21-03-41-39/qq_unihiker")
from net import QQClient

HOST, PORT = "127.0.0.1", 8888
results = []   # (name, ok, detail)

class Client:
    def __init__(self, label):
        self.label = label
        self.events = []
        self.lock = threading.Lock()
        self.c = QQClient(HOST, PORT, self._cb)
    def _cb(self, msg):
        with self.lock:
            self.events.append(msg)
        # print(f"[{self.label}] <<< {msg}")
    def connect(self):
        self.c.connect()
    def wait(self, types, timeout=5.0):
        """等待 events 中出现 type 属于 types 的第一个事件，返回它"""
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                for m in self.events:
                    if m.get("type") in types:
                        return m
            time.sleep(0.05)
        return None
    def drain(self):
        with self.lock:
            self.events.clear()
    def reg(self, uname, pw="123456"):
        self.drain()
        self.c.register(uname, pw)
        return self.wait({"registered", "error"})
    def login(self, uname, pw="123456"):
        self.drain()
        self.c.login(uname, pw)
        return self.wait({"logged_in", "error"})
    def add_friend(self, code):
        self.drain()
        self.c.add_friend(code)
        return self.wait({"request_sent", "error"})
    def accept(self, uid):
        self.drain()
        self.c.accept_friend(uid)
        return self.wait({"request_accepted", "error"})
    def create_group(self, name, codes):
        self.drain()
        self.c.create_group(name, codes)
        return self.wait({"group_created", "error"})
    def send(self, text, to=None, to_group=None):
        self.drain()
        self.c.send_message(text, to=to, to_group=to_group)
        return self.wait({"sent", "error"})
    def close(self):
        self.c.close()

def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (("  -- " + detail) if detail else ""))

ts = str(int(time.time()))[-6:]
A, B = "alice_"+ts, "bob_"+ts
ca, cb = Client("A"), Client("B")

# 启动连接
ca.connect(); cb.connect()
ra = ca.reg(A)
rb = cb.reg(B)
check("注册 alice", bool(ra and ra.get("ok")), str(ra))
check("注册 bob",   bool(rb and rb.get("ok")), str(rb))
if not (ra and ra.get("ok") and rb and rb.get("ok")):
    print("注册失败，终止"); sys.exit(1)

codeA, codeB = ra["friend_code"], rb["friend_code"]
print(f"alice code={codeA}  bob code={codeB}")

# 1) 发好友申请
ca.drain(); cb.drain()
r = ca.add_friend(codeB)
check("发送好友申请(request_sent)", bool(r and r.get("ok")), str(r))
fr = cb.wait({"friend_request"})
check("对方收到好友申请推送(friend_request)", bool(fr), str(fr))

# 2) 对方接受 -> 双方成为好友
cb.drain(); ca.drain()
ra_ack = cb.accept(ca.c.uid)
check("接受方收到 request_accepted", bool(ra_ack and ra_ack.get("ok")), str(ra_ack))
nf = ca.wait({"new_friend"})
check("申请方收到 new_friend 推送(已成为好友)", bool(nf), str(nf))

# 3) 双方联系人互含对方
ca.drain(); cb.drain()
ca.c.request_state(); cb.c.request_state()
st_a = ca.wait({"state"}); st_b = cb.wait({"state"})
a_has_b = st_a and any(c.get("uid")==cb.c.uid for c in st_a.get("contacts",[]))
b_has_a = st_b and any(c.get("uid")==ca.c.uid for c in st_b.get("contacts",[]))
check("alice 的联系人含 bob", a_has_b)
check("bob 的联系人含 alice", b_has_a)

# 2) 建群（alice 建，拉 bob）
ca.drain(); cb.drain()
g = ca.create_group("测试群", [codeB])
check("创建群聊", bool(g and g.get("ok")), str(g))
ng = cb.wait({"new_group"})
check("对方收到 new_group 推送", bool(ng), str(ng))
gid = g["group"]["gid"] if g and g.get("ok") else None

# 3) 私聊：alice -> bob
cb.drain()
m = ca.send("你好 bob，这是私聊测试", to=cb.c.uid)
check("发送私聊", bool(m and m.get("ok")), str(m))
bm = cb.wait({"msg"})
check("bob 实时收到私聊", bool(bm) and bm.get("text") == "你好 bob，这是私聊测试",
      str(bm))

# 4) 群聊：alice -> 群
cb.drain()
m2 = ca.send("群消息来啦", to_group=gid)
check("发送群聊", bool(m2 and m2.get("ok")), str(m2))
bg = cb.wait({"msg"})
check("bob 实时收到群消息", bool(bg) and bg.get("from") == ca.c.uid and bg.get("group") == gid,
      str(bg))

# 5) 机器人：bob -> QQ小助手
bot_uid = 0
m3 = cb.send("你好啊", to=bot_uid)
check("发消息给机器人", bool(m3 and m3.get("ok")), str(m3))
# 机器人回给发送方（bob 自己收到 msg from bot）
br = cb.wait({"msg"})
check("收到机器人回复", bool(br) and br.get("from") == bot_uid and "你好" in br.get("text",""),
      str(br))

# 6) 离线消息：断开 bob，alice 发私聊给 bob，再重连看历史
cb.close()
time.sleep(0.3)
ca.send("你离线时我发的消息", to=cb.c.uid)
time.sleep(0.3)
# bob 重新连接登录
cb2 = Client("B2")
cb2.connect()
rl = cb2.login(B)
check("bob 重新登录", bool(rl and rl.get("ok")), str(rl))
# 历史状态里应包含离线消息
st = cb2.wait({"state"})
offline_found = False
if st:
    for h in st.get("history", []):
        if h.get("text") == "你离线时我发的消息":
            offline_found = True
check("离线消息在历史中下发", offline_found, str([h.get("text") for h in (st or {}).get("history",[])]))

# 汇总
print("\n=== 汇总 ===")
passed = sum(1 for _, ok, _ in results if ok)
print(f"{passed}/{len(results)} 通过")
ca.close(); cb2.close()
sys.exit(0 if passed == len(results) else 1)
