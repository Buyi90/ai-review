from __future__ import annotations

import tkinter as tk

# 统一管理界面外观：主题、字体、操作框配色与尺寸约束。
# 这样 UI 风格只需在此处维护一处，app.py / overlay.py 共用同一套常量。


# ttkbootstrap 主题名称。"litera" 是干净的浅色现代主题；
# 如需深色界面可改为 "darkly" 或 "superhero"。
THEME_NAME = "litera"

FONT_FAMILY = "Microsoft YaHei UI"
FONT_BASE = (FONT_FAMILY, 10)
FONT_SMALL = (FONT_FAMILY, 9)
FONT_TITLE = (FONT_FAMILY, 18, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 10)
FONT_MONO = ("Consolas", 10)


# 三类操作框的中文名、配色与默认尺寸（add_box 时使用）。
BOX_META = {
    "recognition": {"name": "识别框", "color": "#2e7d32", "size": (520, 280)},
    "score": {"name": "打分框", "color": "#1565c0", "size": (140, 56)},
    "submit": {"name": "提交框", "color": "#ef6c00", "size": (150, 60)},
}

# 各类操作框允许的最小尺寸（宽, 高），用于批改前的合法性校验。
BOX_MIN_SIZE = {
    "recognition": (50, 50),
    "score": (30, 20),
    "submit": (40, 20),
}


def box_color(kind: str) -> str:
    return BOX_META.get(kind, {}).get("color", "#1565c0")


def style_text(widget: tk.Text, colors, *, mono: bool = False) -> None:
    """让原生 tk.Text 跟随 ttkbootstrap 主题配色（ttk 无法直接管控 tk.Text）。"""
    widget.configure(
        background=colors.inputbg,
        foreground=colors.inputfg,
        insertbackground=colors.inputfg,
        selectbackground=colors.primary,
        selectforeground=colors.selectfg,
        relief="flat",
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=colors.border,
        highlightcolor=colors.primary,
        padx=10,
        pady=8,
        font=FONT_MONO if mono else FONT_BASE,
        wrap="word",
    )


def style_listbox(widget: tk.Listbox, colors) -> None:
    """让原生 tk.Listbox 跟随主题配色。"""
    widget.configure(
        background=colors.inputbg,
        foreground=colors.inputfg,
        selectbackground=colors.primary,
        selectforeground=colors.selectfg,
        relief="flat",
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=colors.border,
        highlightcolor=colors.primary,
        activestyle="none",
        font=FONT_BASE,
    )
