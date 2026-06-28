from __future__ import annotations

import tkinter as tk

# 统一管理界面外观：主题、字体、操作框配色与尺寸约束。
# 这样 UI 风格只需在此处维护一处，app.py / overlay.py 共用同一套常量。


# ttkbootstrap 主题名称 - 5种精选主题
AVAILABLE_THEMES = {
    "flatly": "清新蓝",
    "darkly": "深色暗黑",
    "cosmo": "现代橙",
    "minty": "薄荷绿",
    "superhero": "超级英雄",
}

THEME_NAME = "flatly"  # 默认主题

# 字体系统 - 改进视觉层次
FONT_FAMILY = "Microsoft YaHei UI"
FONT_BASE = (FONT_FAMILY, 11)  # 基础字号提升
FONT_SMALL = (FONT_FAMILY, 9)
FONT_LARGE = (FONT_FAMILY, 13)
FONT_TITLE = (FONT_FAMILY, 22, "bold")  # 标题更大
FONT_SUBTITLE = (FONT_FAMILY, 11)
FONT_SCORE = (FONT_FAMILY, 36, "bold")  # 专门的分数字体
FONT_MONO = ("Consolas", 10)

# 色彩系统 - 专业配色
COLORS = {
    "primary": "#2C3E50",      # 深蓝灰 - 主色
    "success": "#27AE60",      # 翠绿 - 成功/高分
    "warning": "#F39C12",      # 琥珀 - 警告/中分
    "danger": "#E74C3C",       # 珊瑚红 - 危险/低分
    "info": "#3498DB",         # 天蓝 - 信息
    "light": "#ECF0F1",        # 浅灰 - 背景
    "dark": "#2C3E50",         # 深色文字
    "muted": "#95A5A6",        # 灰色 - 次要信息
    "border": "#BDC3C7",       # 边框色
    "card_bg": "#FFFFFF",      # 卡片背景
    "hover": "#E8F4F8",        # 悬停效果
}

# 间距系统 - 超紧凑化
SPACING = {
    "xs": 1,    # 极小 - 同一元素内
    "sm": 2,    # 小 - 相关元素
    "md": 4,    # 中 - 表单行距
    "lg": 6,    # 大 - 卡片内边距
    "xl": 8,    # 超大 - 卡片外边距
    "xxl": 12,  # 保留用于特殊情况
}

# 表单专用紧凑间距
FORM_SPACING = {
    "label_entry": 1,   # 标签和输入框之间
    "row": 2,           # 行间距
    "section": 4,       # 分组间距
}

# 圆角系统
RADIUS = {
    "sm": 4,
    "md": 8,
    "lg": 12,
    "xl": 16,
    "round": 999,  # 完全圆角
}


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
    """让原生 tk.Text 跟随 ttkbootstrap 主题配色，边框清晰可见。"""
    widget.configure(
        background=COLORS["card_bg"],
        foreground=COLORS["dark"],
        insertbackground=COLORS["info"],
        selectbackground=COLORS["info"],
        selectforeground="#FFFFFF",
        relief="solid",          # 改为solid边框，更清晰
        borderwidth=1,           # 边框1px
        highlightthickness=1,    # 高亮边框1px
        highlightbackground=COLORS["border"],  # 边框颜色
        highlightcolor=COLORS["info"],         # 焦点时边框颜色
        padx=SPACING["md"],
        pady=SPACING["md"],
        font=FONT_MONO if mono else FONT_BASE,
        wrap="word",
    )


def style_listbox(widget: tk.Listbox, colors) -> None:
    """让原生 tk.Listbox 跟随主题配色，边框清晰可见。"""
    widget.configure(
        background=colors.inputbg,
        foreground=colors.inputfg,
        selectbackground=colors.primary,
        selectforeground=colors.selectfg,
        relief="solid",          # 改为solid边框，更清晰
        borderwidth=1,           # 边框1px
        highlightthickness=1,    # 高亮边框1px
        highlightbackground=colors.border,  # 边框颜色
        highlightcolor=colors.primary,      # 焦点时边框颜色
        activestyle="none",
        font=FONT_BASE,
    )
