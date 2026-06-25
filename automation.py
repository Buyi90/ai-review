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


def fill_scores(score_box: RegionBox, scores: list[float | int | str], switch_mode: str = "single") -> None:
    # 多小题打分时，先定位第一个打分框，再用用户配置的按键切到下一个输入位置。
    if not scores:
        return
    if switch_mode not in {"tab", "enter", "space"}:
        fill_score(score_box, scores[0])
        return
    click_box(score_box)
    time.sleep(0.1)
    key = "space" if switch_mode == "space" else switch_mode
    for index, score in enumerate(scores):
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)
        pyautogui.write(str(score), interval=0.01)
        if index < len(scores) - 1:
            pyautogui.press(key)
            time.sleep(0.1)


def click_submit(submit_box: RegionBox) -> None:
    click_box(submit_box)


def fill_and_submit(score_box: RegionBox, submit_box: RegionBox, score: float | int | str, scores: list[float | int | str] | None = None, switch_mode: str = "single") -> None:
    fill_scores(score_box, scores or [score], switch_mode)
    time.sleep(0.2)
    click_submit(submit_box)
