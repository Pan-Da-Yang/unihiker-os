# netdiag.py - 在行空板上诊断为什么连不上服务器
#
# 用法（在板子终端里，进入 qq_unihiker 目录后运行）：
#     python3 netdiag.py
#
# 它会告诉你：APP 实际会连哪个地址、DNS 能不能解析、TCP 端口通不通、
# 以及板子到底有没有正常联网。无需服务器配合，纯本地探测。

import json
import os
import platform
import socket
import time

DEFAULT_SERVER = "win1q4t1r.xyz"
PORT = 8888
CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# 与 main.py 完全一致的判定：非 Windows = 行空板 / 树莓派等嵌入式设备
IS_NOT_WINDOWS = platform.system().lower() != "windows"
LOCALHOST_SET = ("127.0.0.1", "localhost", "::1")


def load_cfg():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def effective_target():
    cfg = load_cfg()
    saved = cfg.get("server_ip")
    if IS_NOT_WINDOWS and (not saved or saved in LOCALHOST_SET):
        return DEFAULT_SERVER, "(config 里是 %s，非 Windows 已回退到默认域名)" % saved
    return (saved or DEFAULT_SERVER), "(来自 config: %s)" % saved


def line(t):
    print("─" * 48)
    print(t)


def check_dns(host):
    line("[1] DNS 解析 %s" % host)
    try:
        t = time.time()
        infos = socket.getaddrinfo(host, PORT, proto=socket.IPPROTO_TCP)
        ip = infos[0][4][0]
        print("    ✓ 解析成功 -> %s  (%.2fs)" % (ip, time.time() - t))
        return ip
    except Exception as e:
        print("    ✗ 解析失败: %s" % e)
        print("    → 板子 DNS 不行，或板子没真正联网（检查 WiFi）")
        return None


def check_tcp(ip, host):
    line("[2] TCP 连接 %s:%d" % (host, PORT))
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(8)
        t = time.time()
        s.connect((ip, PORT))
        print("    ✓ 端口可达，用时 %.2fs" % (time.time() - t))
        s.close()
        return True
    except socket.timeout:
        print("    ✗ 连接超时（8s 无响应）")
        print("    → 多半是板子所在网络封锁了 8888 端口，或到服务器路由不通")
        return False
    except ConnectionRefusedError:
        print("    ✗ 被拒绝 (Connection refused)")
        print("    → 服务器没在 8888 监听，或防火墙挡了（但 PC 能连说明服务器是好的）")
        return False
    except Exception as e:
        print("    ✗ 连接失败: %s" % e)
        return False


def check_general_net():
    line("[3] 板子通用联网能力（连 8.8.8.8:53）")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(6)
        s.connect(("8.8.8.8", 53))
        print("    ✓ 板子能出公网（到 Google DNS 通）")
        s.close()
        return True
    except Exception as e:
        print("    ✗ 板子出不了公网: %s" % e)
        print("    → 板子 WiFi 没连上能上网的网络（可能还连着自己的热点/AP）")
        return False


def main():
    print("=" * 48)
    print("行空板 QQ 网络自检  (非Windows=%s)" % IS_NOT_WINDOWS)
    print("=" * 48)
    host, why = effective_target()
    line("[0] APP 实际会连的地址")
    print("    %s:%d  %s" % (host, PORT, why))

    ip = check_dns(host)
    if ip:
        check_tcp(ip, host)
    check_general_net()

    line("结论速查")
    print("  - 如果 [3] 失败：板子没联网，先搞 WiFi。")
    print("  - 如果 [1] 失败但 [3] 成功：板子 DNS 有问题/域名被拦。")
    print("  - 如果 [2] 超时但 [3] 成功：板子网络封锁了 8888 端口（换端口或换网络）。")
    print("  - 如果 [2] 成功：网络没问题，问题在别处（看服务器日志）。")


if __name__ == "__main__":
    main()
