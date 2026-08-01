# -*- coding: utf-8 -*-
"""
行空板 OS 全家桶 - 统一样式主题
配色针对行空板 2.8" 触摸彩屏(240x320)做了对比度优化，
在普通电脑上同样好看。

通过 set_board_mode(True) 切换到 240x320 小屏参数，
需在导入 filemanager/imageviewer/videoplayer 之前调用。

通过 set_theme("light"|"dark") 切换亮/暗主题，选择会持久化到
工作目录下的 .unihiker_theme，下次启动自动应用。
"""

import os
import threading

# ---------------- 主题调色板 ----------------
# 每个主题包含全部界面颜色常量。切换主题时整体套用。
_PALETTES = {
    "dark": {
        "BG": "#0f1115",          # 桌面背景（深空灰）
        "SURFACE": "#1b1f27",     # 窗口/面板
        "SURFACE2": "#262b36",    # 次级面板 / 悬浮
        "HOVER": "#2f3542",       # 列表项悬停
        "ACCENT": "#00b4d8",      # 主强调（青）
        "ACCENT2": "#ffb703",     # 次强调（琥珀）
        "DANGER": "#ef476f",      # 危险操作（删除）
        "TEXT": "#ffffff",        # 主文本（深色下纯白，增强对比）
        "MUTED": "#b0b6c0",       # 次要文本
        "ON_ACCENT": "#06222a",   # 强调色上的文字
        "COLOR_FOLDER": "#ffd166",
        "COLOR_IMAGE": "#06d6a0",
        "COLOR_VIDEO": "#ef476f",
        "COLOR_FILE": "#c5cbd5",
        "COLOR_PY": "#c77dff",
        "COLOR_TEXT": "#8ecae6",
        "COLOR_SHELL": "#80ed99",
    },
    "light": {
        "BG": "#f4f6f9",          # 桌面背景（浅灰白）
        "SURFACE": "#ffffff",     # 窗口/面板
        "SURFACE2": "#e8ecf1",    # 次级面板 / 悬浮
        "HOVER": "#dbe1e9",       # 列表项悬停
        "ACCENT": "#0077b6",      # 主强调（蓝）
        "ACCENT2": "#fb8500",     # 次强调（橙）
        "DANGER": "#d90429",      # 危险操作（红）
        "TEXT": "#161a20",        # 主文本
        "MUTED": "#5b636e",       # 次要文本
        "ON_ACCENT": "#ffffff",   # 强调色上的文字
        "COLOR_FOLDER": "#c98a1a",
        "COLOR_IMAGE": "#2a9d8f",
        "COLOR_VIDEO": "#d90429",
        "COLOR_FILE": "#6c757d",
        "COLOR_PY": "#7209b7",
        "COLOR_TEXT": "#1d6fa5",
        "COLOR_SHELL": "#2d6a4f",
    },
}

# 主题配置文件（工作目录下隐藏文件，记录当前选择）
_THEME_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           ".unihiker_theme")

THEME_NAME = "dark"


def _load_theme_name() -> str:
    try:
        with open(_THEME_FILE, "r", encoding="utf-8") as f:
            name = f.read().strip()
            if name in _PALETTES:
                return name
    except Exception:
        pass
    return "dark"


def _apply_palette(name: str):
    """把指定调色板套用到模块级颜色常量上。"""
    global BG, SURFACE, SURFACE2, HOVER, ACCENT, ACCENT2, DANGER
    global TEXT, MUTED, ON_ACCENT, COLOR_FOLDER, COLOR_IMAGE, COLOR_VIDEO
    global COLOR_FILE, COLOR_PY, COLOR_TEXT, COLOR_SHELL, THEME_NAME
    p = _PALETTES[name]
    BG = p["BG"]
    SURFACE = p["SURFACE"]
    SURFACE2 = p["SURFACE2"]
    HOVER = p["HOVER"]
    ACCENT = p["ACCENT"]
    ACCENT2 = p["ACCENT2"]
    DANGER = p["DANGER"]
    TEXT = p["TEXT"]
    MUTED = p["MUTED"]
    ON_ACCENT = p["ON_ACCENT"]
    COLOR_FOLDER = p["COLOR_FOLDER"]
    COLOR_IMAGE = p["COLOR_IMAGE"]
    COLOR_VIDEO = p["COLOR_VIDEO"]
    COLOR_FILE = p["COLOR_FILE"]
    COLOR_PY = p["COLOR_PY"]
    COLOR_TEXT = p["COLOR_TEXT"]
    COLOR_SHELL = p["COLOR_SHELL"]
    THEME_NAME = name


def get_theme() -> str:
    return THEME_NAME


def set_theme(name: str) -> bool:
    """设置主题并持久化到配置文件。成功返回 True。

    注意：已打开的窗口不会自动重绘，切换后需重启界面（桌面设置里
    切换会自动重启进程）才能让全量组件生效。
    """
    if name not in _PALETTES:
        return False
    try:
        with open(_THEME_FILE, "w", encoding="utf-8") as f:
            f.write(name)
    except Exception:
        pass
    _apply_palette(name)
    return True


# 模块加载时应用已保存/默认的主题
THEME_NAME = _load_theme_name()
_apply_palette(THEME_NAME)


# ---------------- 字体 ----------------
# 行空板自带文泉驿/思源，电脑回退到系统无衬线
FONT = ("WenQuanYi Micro Hei", "Microsoft YaHei", "SimHei", "sans-serif")
FONT_TITLE = (FONT[0], 16, "bold")
FONT_NORMAL = (FONT[0], 12)
FONT_SMALL = (FONT[0], 10)

# ---------------- 窗口尺寸 ----------------
WIN_W = 760
WIN_H = 520

# 行空板物理分辨率（竖屏）
BOARD_W = 240
BOARD_H = 320

# 是否处于行空板小屏模式
BOARD = False

# ---------------- 文件类型识别 ----------------
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff")
VIDEO_EXT = (".mp4", ".avi", ".mkv", ".mov", ".webm", ".flv", ".m4v")
AUDIO_EXT = (".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac")
PY_EXT = (".py",)
SHELL_EXT = (".sh", ".bash")
TEXT_EXT = (
    ".txt", ".py", ".md", ".markdown", ".log", ".json", ".csv", ".tsv",
    ".ini", ".cfg", ".conf", ".yaml", ".yml", ".toml", ".sh", ".bash",
    ".c", ".h", ".cpp", ".hpp", ".java", ".js", ".ts", ".jsx", ".tsx",
    ".html", ".htm", ".xml", ".css", ".sql", ".r", ".pl", ".rb", ".go",
    ".rs", ".lua", ".vim", ".gitignore",
)


def is_image(name: str) -> bool:
    return name.lower().endswith(IMAGE_EXT)


def is_video(name: str) -> bool:
    return name.lower().endswith(VIDEO_EXT)


def is_audio(name: str) -> bool:
    return name.lower().endswith(AUDIO_EXT)


def is_python(name: str) -> bool:
    return name.lower().endswith(PY_EXT)


def is_shell(name: str) -> bool:
    return name.lower().endswith(SHELL_EXT)


def is_text(name: str) -> bool:
    """文本类文件：用文本编辑器打开（含 .py，可边看边改）。"""
    return name.lower().endswith(TEXT_EXT)


def set_board_mode(value: bool = True):
    """切换到行空板 240x320 模式。必须在导入各 App 模块前调用。"""
    global BOARD, FONT_TITLE, FONT_NORMAL, FONT_SMALL, WIN_W, WIN_H
    BOARD = value
    if value:
        FONT_TITLE = (FONT[0], 14, "bold")
        FONT_NORMAL = (FONT[0], 10)
        FONT_SMALL = (FONT[0], 8)
        WIN_W = BOARD_W
        WIN_H = BOARD_H


def apply_board_window(win: object):
    """对小屏窗口统一去边框并铺满 240x320。"""
    if not BOARD:
        return
    try:
        win.overrideredirect(True)
    except Exception:
        pass
    win.geometry(f"{BOARD_W}x{BOARD_H}+0+0")
    win.resizable(False, False)


def board_padding():
    """返回当前模式下的默认边距。"""
    return 2 if BOARD else 6


# ---------------- 行空板板载 A 键返回（真机专用） ----------------
_board_btn_lock = False
_board_btn_inited = False


def setup_board_button(win: object):
    """为窗口注册行空板板载 A 物理按键：按下即关闭当前窗口返回桌面。

    仅真机有效；开发机无 pinpong 库/无硬件时静默跳过。
    回调会在子线程触发，内部切回 tkinter 主线程执行 destroy。
    """
    global _board_btn_inited
    try:
        from pinpong.board import Board, Pin
        from pinpong.extension.unihiker import button_a
        if not _board_btn_inited:
            with threading.Lock():
                if not _board_btn_inited:
                    Board().begin()
                    _board_btn_inited = True

        def _on_a(pin):
            try:
                if win.winfo_exists():
                    # 必须用 lambda 延迟取值：若本窗口是被 spawn_window 打开的，
                    # spawn_window 会事后把 destroy 重写成“关闭时恢复父窗口”的版本。
                    # 直接传 win.destroy 会在 __init__ 时绑死原始引用，绕过恢复逻辑，
                    # 导致按 A 键返回后父窗口（文件管理器/桌面）停在 withdraw → 露出控制台。
                    win.after(0, lambda: win.destroy())
            except Exception:
                pass

        button_a.irq(trigger=Pin.IRQ_RISING, handler=_on_a)
    except Exception:
        pass


def spawn_window(parent, factory, *args, **kwargs):
    """在行空板（无窗口管理器）上打开子窗口的标准方式：

    1. 创建子窗口；
    2. 隐藏父窗口，保证同一时刻只有唯一可见、可交互的窗口
       （避免新窗口开在桌面/上层窗口**之下**，或焦点错乱导致
       “点哪儿都没反应”）；
    3. 子窗口关闭时自动恢复父窗口。

    返回子窗口对象。注意：factory 必须返回窗口（或 None）。
    """
    child = factory(*args, **kwargs)
    if child is None:
        return None

    pw = parent
    was_viewable = False
    try:
        was_viewable = pw.winfo_exists() and pw.winfo_viewable()
    except Exception:
        pass

    def _restore():
        try:
            if was_viewable and pw.winfo_exists() and not pw.winfo_viewable():
                pw.deiconify()
                pw.lift()
        except Exception:
            pass

    real_destroy = child.destroy

    def _destroy():
        try:
            real_destroy()
        finally:
            _restore()

    child.destroy = _destroy
    try:
        child.protocol("WM_DELETE_WINDOW", _destroy)
    except Exception:
        pass

    if was_viewable:
        try:
            pw.withdraw()
        except Exception:
            pass

    try:
        child.lift()
        child.update_idletasks()
    except Exception:
        pass
    return child


# ---------------- 音量（0-100） ----------------
_VOLUME_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            ".unihiker_volume")
VOLUME = 70


def _load_volume() -> int:
    try:
        with open(_VOLUME_FILE, "r", encoding="utf-8") as f:
            v = int(f.read().strip())
            if 0 <= v <= 100:
                return v
    except Exception:
        pass
    return 70


def get_volume() -> int:
    return VOLUME


def set_volume(v: int) -> int:
    """设置音量(0-100)并持久化，返回实际写入值。"""
    global VOLUME
    v = max(0, min(100, int(v)))
    VOLUME = v
    try:
        with open(_VOLUME_FILE, "w", encoding="utf-8") as f:
            f.write(str(v))
    except Exception:
        pass
    return v


VOLUME = _load_volume()
