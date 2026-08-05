# net.py - 行空板 QQ 的客户端网络层（零依赖，TCP + JSON 行协议）
#
# 与服务端 server.py 配套：后台线程收消息，回调给 UI；
# 所有请求自动附带登录后下发的 token。

import socket
import threading
import json


class QQClient:
    def __init__(self, host, port, on_message):
        self.host = host
        self.port = port
        self.on_message = on_message   # callback(dict)
        self.sock = None
        self.token = None
        self.uid = None
        self.username = None
        self.running = False
        self.recv_thread = None
        self._buf = ""
        self._lock = threading.Lock()

    def connect(self, timeout=8):
        """连接服务器。成功返回 True，失败抛异常。"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((self.host, self.port))
        self.sock.settimeout(None)
        self.running = True
        self.recv_thread = threading.Thread(target=self._recv, daemon=True)
        self.recv_thread.start()
        return True

    def _send(self, obj):
        if self.sock is None or not self.running:
            return
        if self.token and "token" not in obj and obj.get("type") not in ("register", "login"):
            obj["token"] = self.token
        with self._lock:
            try:
                self.sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            except Exception:
                pass

    def _recv(self):
        while self.running:
            try:
                data = self.sock.recv(4096)
            except Exception:
                break
            if not data:
                break
            self._buf += data.decode("utf-8", "replace")
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                if msg.get("type") == "logged_in" and msg.get("ok"):
                    self.token = msg.get("token")
                    self.uid = msg.get("uid")
                    self.username = msg.get("username")
                elif msg.get("type") == "registered" and msg.get("ok"):
                    self.token = msg.get("token")
                    self.uid = msg.get("uid")
                    self.username = msg.get("username")
                if self.on_message:
                    self.on_message(msg)

    # --- 业务请求 ---
    def register(self, username, password):
        self._send({"type": "register", "username": username, "password": password})

    def login(self, username, password):
        self._send({"type": "login", "username": username, "password": password})

    def add_friend(self, code):
        self._send({"type": "add_friend", "code": code})

    def accept_friend(self, requester_uid):
        self._send({"type": "accept_friend", "uid": requester_uid})

    def reject_friend(self, requester_uid):
        self._send({"type": "reject_friend", "uid": requester_uid})

    def create_group(self, name, member_codes=None):
        self._send({"type": "create_group", "name": name,
                    "member_codes": member_codes or []})

    def send_message(self, text, to=None, to_group=None):
        self._send({"type": "message", "text": text, "to": to, "to_group": to_group})

    def request_state(self):
        self._send({"type": "list"})

    def close(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
