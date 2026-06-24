from __future__ import annotations

import time

import pyautogui

from models import RegionBox


# 桌面端无法直接访问网页 DOM，因此用用户设置的打分框和提交框完成自动操作。


pyautogui.FAILSAFE = True


def click_box(box: RegionBox) -> None:
    x, y = box.center()
    pyautogui.click(x, y)


def fill_score(score_box: RegionBox, score: float | int | str) -> None:
    click_box(score_box)
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.05)
    pyautogui.write(str(score), interval=0.01)


def click_submit(submit_box: RegionBox) -> None:
    click_box(submit_box)


def fill_and_submit(score_box: RegionBox, submit_box: RegionBox, score: float | int | str) -> None:
    fill_score(score_box, score)
    time.sleep(0.2)
    click_submit(submit_box)
