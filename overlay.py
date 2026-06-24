from __future__ import annotations

import tkinter as tk
from typing import Callable

from models import RegionBox


# 全屏覆盖层用于拖拽和缩放三个操作框，颜色与用户要求保持一致。


class RegionOverlay(tk.Toplevel):
    def __init__(self, master: tk.Tk, boxes: list[RegionBox], on_done: Callable[[list[RegionBox]], None]):
        super().__init__(master)
        self.boxes = boxes
        self.on_done = on_done
        self.active_index: int | None = None
        self.mode = "move"
        self.start = (0, 0)
        self.original: RegionBox | None = None
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.35)
        self.configure(bg="black")
        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.hint = tk.Label(
            self,
            text="拖动彩色框调整位置；拖动右下角调整大小；Enter 保存；Esc 取消",
            bg="#111827",
            fg="white",
            padx=12,
            pady=8,
        )
        self.hint.place(x=20, y=20)
        self.canvas.bind("<ButtonPress-1>", self.on_down)
        self.canvas.bind("<B1-Motion>", self.on_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_up)
        self.bind("<Return>", lambda _e: self.finish())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.draw()

    def draw(self) -> None:
        self.canvas.delete("box")
        for i, box in enumerate(self.boxes):
            if not box.enabled:
                continue
            x1, y1, x2, y2 = box.rect()
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=box.color, width=4, tags=("box", f"box-{i}"))
            self.canvas.create_text(x1 + 10, y1 + 10, text=box.name, fill=box.color, anchor="nw", font=("Microsoft YaHei UI", 16, "bold"), tags="box")
            self.canvas.create_rectangle(x2 - 16, y2 - 16, x2, y2, fill=box.color, outline=box.color, tags="box")

    def hit_test(self, x: int, y: int) -> tuple[int | None, str]:
        for i in range(len(self.boxes) - 1, -1, -1):
            box = self.boxes[i]
            x1, y1, x2, y2 = box.rect()
            if x2 - 22 <= x <= x2 + 6 and y2 - 22 <= y <= y2 + 6:
                return i, "resize"
            if x1 <= x <= x2 and y1 <= y <= y2:
                return i, "move"
        return None, "move"

    def on_down(self, event) -> None:
        idx, mode = self.hit_test(event.x, event.y)
        self.active_index = idx
        self.mode = mode
        self.start = (event.x, event.y)
        if idx is not None:
            b = self.boxes[idx]
            self.original = RegionBox(b.name, b.kind, b.x, b.y, b.width, b.height, b.color, b.enabled)

    def on_move(self, event) -> None:
        if self.active_index is None or self.original is None:
            return
        dx = event.x - self.start[0]
        dy = event.y - self.start[1]
        box = self.boxes[self.active_index]
        if self.mode == "resize":
            box.width = max(40, self.original.width + dx)
            box.height = max(30, self.original.height + dy)
        else:
            box.x = max(0, self.original.x + dx)
            box.y = max(0, self.original.y + dy)
        self.draw()

    def on_up(self, _event) -> None:
        self.active_index = None
        self.original = None

    def finish(self) -> None:
        self.on_done(self.boxes)
        self.destroy()
