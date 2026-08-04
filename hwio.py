# -*- coding: utf-8 -*-
"""
行空板 OS - 共享硬件 IO 模块
为「编曲」「图形化编程」等需要操作板载硬件的 App 提供统一、懒加载、可降级的接口：

  · ensure_hw()  : 初始化 pinpong（仅真机有该库/硬件），只尝试一次。
  · hw_ready()   : 是否初始化成功。
  · pin_const(i) : 取 Pin.Pi 常量。
  · tone(freq,ms): 播一个音。板子走 P0 蜂鸣器；开发机尝试 pygame 回退；都不可用则静默。
  · tone_stop()  : 停掉当前发声。
  · pin_set(i,v) : 数字输出 高/低。
  · pin_get(i)   : 数字输入读值（0/1/None）。
  · bind_a(handler): 绑定板载 A 键回调（子线程触发，需 handler 自行切回主线程）。

无库 / 无硬件（开发机）时所有写/读/发声操作安全降级，不会抛异常、不会崩。
"""
import time

import theme
from theme import BOARD

_HW_READY = False
_HW_TRIED = False
_PP = {}  # 存放 Board / Pin / buzzer 等

# 预设音名（频率 Hz），供「编曲」「蜂鸣器」等复用
_NOTES = [
    ("Do", 262), ("Re", 294), ("Mi", 330), ("Fa", 349),
    ("Sol", 392), ("La", 440), ("Si", 494), ("C5", 523),
]


def ensure_hw():
    """初始化 pinpong 硬件连接，成功返回 True。只尝试一次，失败则降级。"""
    global _HW_READY, _HW_TRIED
    if _HW_TRIED:
        return _HW_READY
    _HW_TRIED = True
    try:
        from pinpong.board import Board, Pin, PWM, Tone
        from pinpong.extension.unihiker import buzzer
        # 行空板自动识别板型；多次调用 begin() 在 pinpong 内幂等。
        Board().begin()
        _PP.update(Board=Board, Pin=Pin, PWM=PWM, Tone=Tone, buzzer=buzzer)
        _HW_READY = True
    except Exception as e:  # 开发机无库/无硬件
        _PP["err"] = e
        _HW_READY = False
    return _HW_READY


def hw_ready():
    return _HW_READY


def pin_const(idx):
    """返回 Pin.Px 常量对象，不存在返回 None。"""
    Pin = _PP.get("Pin")
    if Pin is None:
        return None
    return getattr(Pin, "P%d" % idx, None)


def tone(freq, dur_ms=None):
    """播放一个音。dur_ms 为 None 表示持续音（需 tone_stop 停止）。
    返回 True 表示已尝试发声（不保证真的响）。"""
    if not isinstance(freq, (int, float)) or freq <= 0:
        return False
    if _HW_READY:
        try:
            bz = _PP.get("buzzer")
            if bz is None:
                return False
            const = pin_const(0)
            if const is not None:
                bz.redirect(const)  # 蜂鸣器重定向到 P0
            bz.pitch(int(freq))
            return True
        except Exception:
            return False
    # 开发机回退：用 pygame 合成一个短正弦（best-effort，无库则静默）
    try:
        import math
        import array
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, channels=1)
        if dur_ms is None:
            dur_ms = 200
        n = max(1, int(44100 * dur_ms / 1000))
        amp = 12000
        buf = array.array("h")
        for i in range(n):
            buf.append(int(amp * math.sin(2 * math.pi * freq * i / 44100)))
        pygame.mixer.Sound(buf).play()
        return True
    except Exception:
        return False


def tone_stop():
    if _HW_READY:
        try:
            _PP.get("buzzer").stop()
        except Exception:
            pass
        return
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.stop()
    except Exception:
        pass


def pin_set(idx, val):
    """数字输出：val 为真 → 高(1)，否则低(0)。成功返回 True。"""
    if not _HW_READY:
        return False
    try:
        Pin = _PP.get("Pin")
        const = pin_const(idx)
        if const is None:
            return False
        p = Pin(const, Pin.OUT)
        p.write_digital(1 if val else 0)
        return True
    except Exception:
        return False


def pin_get(idx):
    """数字输入读值，返回 0/1；失败或无硬件返回 None。"""
    if not _HW_READY:
        return None
    try:
        Pin = _PP.get("Pin")
        const = pin_const(idx)
        if const is None:
            return None
        p = Pin(const, Pin.IN)
        return p.read_digital()
    except Exception:
        return None


def bind_a(handler):
    """绑定板载 A 键回调（IRQ_RISING）。无硬件则忽略。"""
    if not _HW_READY:
        return
    try:
        from pinpong.extension.unihiker import button_a
        Pin = _PP.get("Pin")
        button_a.irq(trigger=Pin.IRQ_RISING, handler=handler)
    except Exception:
        pass
