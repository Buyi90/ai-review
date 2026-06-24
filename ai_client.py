from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import requests

from image_tools import image_to_base64
from models import AppConfig, GradeResult, Provider


# AI 模块复刻脚本的结构化提示词、解析器、双评和仲裁逻辑。


StreamCallback = Callable[[str], None]


def _field_text(value: str) -> str:
    return value.strip() if value else ""


def build_prompt(config: AppConfig) -> str:
    max_score = config.scoring.max_score
    if config.scoring.units:
        max_score = sum(u.max_score for u in config.scoring.units)
    prompt = "你是一位严格的阅卷老师。请只根据截图中识别框内的学生答案进行 OCR 和评分。\n\n===== 输入信息 ====="
    if _field_text(config.question):
        prompt += f"\n【题目】\n{config.question}"
    if _field_text(config.answer):
        prompt += f"\n【标准答案】\n{config.answer}"
    if _field_text(config.rubric):
        prompt += f"\n【评分标准】\n{config.rubric}"
    prompt += f"\n【满分】\n满分{max_score:g}分"
    if config.scoring.units:
        prompt += "\n【分小题】"
        for unit in config.scoring.units:
            prompt += f"\n{unit.label}: 满分{unit.max_score:g}分"
    prompt += "\n\n===== 输出要求 =====\n你必须严格按照以下格式输出，不得添加其他段落：\n\n【答案复述】\n逐条列出学生答案要点。\n\n【评分依据】\n逐项说明得分和扣分点。\n\n【分数计算】\n写出计算公式。"
    if config.scoring.units:
        for unit in config.scoring.units:
            prompt += f"\n\n{unit.label}分数：一个数字\n{unit.label}评语：简短说明"
    prompt += "\n\n【得分】\n一个数字，可以是小数。"
    if config.scoring.diligence_enabled:
        prompt += f"\n\n【勤勉度】\n等级：1-5 的整数\n依据：参考标准：{config.scoring.diligence_criteria}"
    prompt += "\n\n===== 重要约束 =====\n1. 被划掉、涂改、涂抹覆盖的内容视为无效，只评判最终保留的答案。\n2. 如果无法识别学生答案，在【答案复述】写“未能识别”。\n3. 【得分】必须只包含数字。"
    return prompt


def _image_content_from_b64(image_b64: str) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}


def _material_image_b64s(config: AppConfig) -> list[str]:
    # 评分材料图片来自用户手动添加的题目/答案/评分标准截图，只作为参考材料发送。
    values: list[str] = []
    for path in config.material_images:
        try:
            data = Path(path).read_bytes()
            import base64
            values.append(base64.b64encode(data).decode("ascii"))
        except Exception:
            continue
    return values


def call_openai_compatible(provider: Provider, prompt: str, image_b64: str, on_stream: StreamCallback | None = None, extra_image_b64s: list[str] | None = None) -> str:
    if not provider.api_key:
        raise RuntimeError("请先填写 API Key")
    content = [{"type": "text", "text": prompt}]
    for extra in extra_image_b64s or []:
        content.append(_image_content_from_b64(extra))
    content.append(_image_content_from_b64(image_b64))
    body: dict[str, Any] = {
        "model": provider.model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 2048,
        "stream": False,
    }
    if provider.reasoning_effort:
        body["reasoning_effort"] = provider.reasoning_effort
    response = requests.post(
        provider.endpoint,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {provider.api_key}"},
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        timeout=90,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"API 报错 {response.status_code}: {response.text[:500]}")
    data = response.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if on_stream:
        on_stream(text)
    return text


def test_provider(provider: Provider) -> str:
    # 服务商测试不带图片，便于快速验证 endpoint、key、model 是否可用。
    if not provider.api_key:
        raise RuntimeError("请先填写 API Key")
    body: dict[str, Any] = {
        "model": provider.model,
        "messages": [{"role": "user", "content": "请只回复：连接成功"}],
        "max_tokens": 16,
        "stream": False,
    }
    if provider.reasoning_effort:
        body["reasoning_effort"] = provider.reasoning_effort
    response = requests.post(
        provider.endpoint,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {provider.api_key}"},
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        timeout=30,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"API 报错 {response.status_code}: {response.text[:500]}")
    data = response.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip() or "连接成功"


def extract_score(text: str | None, max_score: float) -> float | None:
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    value = float(match.group(0))
    return min(max(value, 0), max_score if max_score > 0 else 999)


def parse_response(text: str, config: AppConfig) -> GradeResult:
    sections: dict[str, str] = {}
    for match in re.finditer(r"【([^】]+)】\s*([\s\S]*?)(?=【|$)", text):
        sections[match.group(1).strip()] = match.group(2).strip()
    max_score = config.scoring.max_score
    if config.scoring.units:
        max_score = sum(u.max_score for u in config.scoring.units)
    score = extract_score(sections.get("得分") or sections.get("最终得分") or sections.get("总分"), max_score)
    if score is None:
        legacy = re.search(r"(?:分数|得分|总分)[：:]\s*(-?\d+(?:\.\d+)?)", text)
        if legacy:
            score = min(max(float(legacy.group(1)), 0), max_score)
    sub_scores = []
    for unit in config.scoring.units:
        unit_score = extract_score(sections.get(f"{unit.label}分数"), unit.max_score)
        comment = sections.get(f"{unit.label}评语", "")
        if unit_score is not None:
            sub_scores.append({"label": unit.label, "score": unit_score, "maxScore": unit.max_score, "comment": comment})
    diligence_level = 0
    diligence_reason = ""
    if sections.get("勤勉度"):
        level_match = re.search(r"等级[：:]\s*(\d)", sections["勤勉度"])
        if level_match:
            diligence_level = min(max(int(level_match.group(1)), 1), 5)
        reason_match = re.search(r"依据[：:]\s*(.+)", sections["勤勉度"])
        if reason_match:
            diligence_reason = reason_match.group(1).strip()
    return GradeResult(
        student_answer=sections.get("答案复述", "未能识别"),
        score=score,
        raw_score=score,
        comment=sections.get("评分依据", text),
        scoring_basis=sections.get("评分依据", ""),
        calculation=sections.get("分数计算", ""),
        diligence_level=diligence_level,
        diligence_reason=diligence_reason,
        sub_scores=sub_scores,
        sections=sections,
    )


def grade_image(config: AppConfig, image, provider: Provider, on_stream: StreamCallback | None = None) -> GradeResult:
    prompt = build_prompt(config)
    raw = call_openai_compatible(provider, prompt, image_to_base64(image), on_stream, _material_image_b64s(config))
    return parse_response(raw, config)


def build_arbitration_prompt(config: AppConfig, a: GradeResult, b: GradeResult) -> str:
    return (
        "你是阅卷仲裁专家。两位老师对同一份试卷评分有分歧，请独立审阅截图后裁定。\n\n"
        f"老师A评分：{a.score}，依据：{a.comment}\n"
        f"老师B评分：{b.score}，依据：{b.comment}\n\n"
        f"题目：{config.question}\n标准答案：{config.answer}\n评分标准：{config.rubric}\n\n"
        "严格按以下格式输出：\n【答案复述】\n...\n【独立评分依据】\n...\n【仲裁分析】\n...\n【最终得分】\n一个数字"
    )


def grade_dual(config: AppConfig, image, provider: Provider, on_stream: StreamCallback | None = None) -> GradeResult:
    first = grade_image(config, image, provider, on_stream)
    if not config.workflow.dual_enabled:
        return first
    second = grade_image(config, image, config.workflow.secondary_provider, None)
    if first.score is None:
        return second
    if second.score is None:
        return first
    diff = abs(first.score - second.score)
    if diff <= config.workflow.dual_threshold:
        final = first
        final.score = round((first.score + second.score) / 2, 2)
        final.raw_score = final.score
        final.dual_eval = {"scoreA": first.score, "scoreB": second.score, "diff": diff, "result": "共识"}
        return final
    if not config.workflow.arbitration_enabled:
        score_a, score_b = first.score, second.score
        first.score = round((score_a + score_b) / 2, 2)
        first.raw_score = first.score
        first.dual_eval = {"scoreA": score_a, "scoreB": score_b, "diff": diff, "result": "未启用仲裁，取平均"}
        return first
    prompt = build_arbitration_prompt(config, first, second)
    raw = call_openai_compatible(config.workflow.arbitration_provider, prompt, image_to_base64(image), on_stream, _material_image_b64s(config))
    arb = parse_response(raw, config)
    arb.dual_eval = {"scoreA": first.score, "scoreB": second.score, "diff": diff, "result": "仲裁", "arbScore": arb.score}
    return arb
