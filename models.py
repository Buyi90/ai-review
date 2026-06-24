from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# 本文件只放数据结构，避免 UI、AI、自动点击逻辑互相耦合。


@dataclass
class RegionBox:
    name: str
    kind: str
    x: int
    y: int
    width: int
    height: int
    color: str
    enabled: bool = True

    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegionBox":
        return cls(
            name=data.get("name", "未命名"),
            kind=data.get("kind", "recognition"),
            x=int(data.get("x", 100)),
            y=int(data.get("y", 100)),
            width=int(data.get("width", 300)),
            height=int(data.get("height", 180)),
            color=data.get("color", "#2e7d32"),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class Provider:
    name: str = "5plus1官方"
    endpoint: str = "https://api.ai.five-plus-one.com/v1/chat/completions"
    api_key: str = ""
    model: str = "aimarker-fast"
    reasoning_effort: str = "minimal"
    models: list[str] = field(default_factory=list)

    def available_models(self) -> list[str]:
        # 每个供应商保存自己的模型列表，当前模型不在列表时也保留，避免用户手动输入后丢失。
        values = [m for m in self.models if m]
        if self.model and self.model not in values:
            values.insert(0, self.model)
        return values


def default_providers() -> list[Provider]:
    # 目前统一走 OpenAI 兼容 Chat Completions 协议，服务商只负责端点、Key 和模型差异。
    return [
        Provider(
            name="5plus1官方",
            endpoint="https://api.ai.five-plus-one.com/v1/chat/completions",
            model="aimarker-fast",
            reasoning_effort="minimal",
            models=["aimarker-fast", "aimarker-pro"],
        ),
        Provider(
            name="火山引擎",
            endpoint="https://ark.cn-beijing.volces.com/api/v3/chat/completions",
            model="doubao-seed-2-0-pro-260215",
            models=["doubao-seed-2-0-lite-260428", "doubao-seed-2-0-pro-260215"],
        ),
        Provider(
            name="OpenAI兼容",
            endpoint="https://api.openai.com/v1/chat/completions",
            model="gpt-4o",
            models=["gpt-4o", "gpt-4o-mini"],
        ),
        Provider(
            name="自定义服务商",
            endpoint="",
            model="",
        ),
    ]


@dataclass
class ScoringUnit:
    label: str
    max_score: float = 0.0
    round_step: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoringUnit":
        return cls(
            label=data.get("label", "总分"),
            max_score=float(data.get("max_score", 0) or 0),
            round_step=float(data.get("round_step", 1) or 1),
        )


@dataclass
class ScoringSettings:
    max_score: float = 10.0
    round_step: float = 1.0
    round_method: str = "round"
    diligence_enabled: bool = False
    diligence_max_bonus: float = 3.0
    diligence_decay_power: float = 2.0
    diligence_criteria: str = "字数较多且书写较为工整"
    units: list[ScoringUnit] = field(default_factory=list)


@dataclass
class Workflow:
    mode: str = "normal"
    primary_enabled: bool = True
    dual_enabled: bool = False
    arbitration_enabled: bool = True
    dual_threshold: float = 2.0
    primary_provider_name: str = "5plus1官方"
    secondary_provider_name: str = "5plus1官方"
    arbitration_provider_name: str = "5plus1官方"
    secondary_provider: Provider = field(default_factory=lambda: Provider(model="aimarker-fast"))
    arbitration_provider: Provider = field(default_factory=lambda: Provider(model="aimarker-pro", reasoning_effort=""))
    target_count_enabled: bool = False
    target_count: int = 0
    retry_limit: int = 5
    confirm_before_submit: bool = True
    normal_countdown: int = 5
    unattended_countdown: int = 1
    next_paper_delay: float = 0.8


@dataclass
class AppConfig:
    active_preset: str = "默认配置"
    active_provider: str = "5plus1官方"
    providers: list[Provider] = field(default_factory=default_providers)
    question: str = ""
    answer: str = ""
    rubric: str = ""
    material_images: list[str] = field(default_factory=list)
    scoring: ScoringSettings = field(default_factory=ScoringSettings)
    workflow: Workflow = field(default_factory=Workflow)
    boxes: list[RegionBox] = field(default_factory=list)
    preprocess_level: int = 1
    recognition_margin: int = 0
    blank_detection_enabled: bool = False
    blank_threshold: float = 0.01
    save_images: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GradeResult:
    student_answer: str = "未能识别"
    score: float | None = None
    raw_score: float | None = None
    comment: str = ""
    scoring_basis: str = ""
    calculation: str = ""
    diligence_level: int = 0
    diligence_reason: str = ""
    sub_scores: list[dict[str, Any]] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    dual_eval: dict[str, Any] | None = None


def provider_from_dict(data: dict[str, Any]) -> Provider:
    return Provider(
        name=data.get("name", "OpenAI兼容"),
        endpoint=data.get("endpoint", ""),
        api_key=data.get("api_key", ""),
        model=data.get("model", ""),
        reasoning_effort=data.get("reasoning_effort", ""),
        models=[str(x).strip() for x in data.get("models", []) if str(x).strip()],
    )


def config_from_dict(data: dict[str, Any]) -> AppConfig:
    scoring_raw = data.get("scoring", {})
    scoring = ScoringSettings(
        max_score=float(scoring_raw.get("max_score", 10) or 10),
        round_step=float(scoring_raw.get("round_step", 1) or 1),
        round_method=scoring_raw.get("round_method", "round"),
        diligence_enabled=bool(scoring_raw.get("diligence_enabled", False)),
        diligence_max_bonus=float(scoring_raw.get("diligence_max_bonus", 3) or 3),
        diligence_decay_power=float(scoring_raw.get("diligence_decay_power", 2) or 2),
        diligence_criteria=scoring_raw.get("diligence_criteria", "字数较多且书写较为工整"),
        units=[ScoringUnit.from_dict(x) for x in scoring_raw.get("units", [])],
    )
    workflow_raw = data.get("workflow", {})
    workflow = Workflow(
        mode=workflow_raw.get("mode", "normal"),
        primary_enabled=bool(workflow_raw.get("primary_enabled", workflow_raw.get("primaryEnabled", True))),
        dual_enabled=bool(workflow_raw.get("dual_enabled", False)),
        arbitration_enabled=bool(workflow_raw.get("arbitration_enabled", workflow_raw.get("arbitrationEnabled", True))),
        dual_threshold=float(workflow_raw.get("dual_threshold", 2) or 2),
        primary_provider_name=workflow_raw.get("primary_provider_name", workflow_raw.get("primaryProviderName", data.get("active_provider", "5plus1官方"))),
        secondary_provider_name=workflow_raw.get("secondary_provider_name", workflow_raw.get("secondaryProviderName", "")),
        arbitration_provider_name=workflow_raw.get("arbitration_provider_name", workflow_raw.get("arbitrationProviderName", "")),
        secondary_provider=provider_from_dict(workflow_raw.get("secondary_provider", {})),
        arbitration_provider=provider_from_dict(workflow_raw.get("arbitration_provider", {})),
        target_count_enabled=bool(workflow_raw.get("target_count_enabled", False)),
        target_count=int(workflow_raw.get("target_count", 0) or 0),
        retry_limit=int(workflow_raw.get("retry_limit", 5) or 5),
        confirm_before_submit=bool(workflow_raw.get("confirm_before_submit", True)),
        normal_countdown=int(workflow_raw.get("normal_countdown", 5) or 5),
        unattended_countdown=int(workflow_raw.get("unattended_countdown", 1) or 1),
        next_paper_delay=float(workflow_raw.get("next_paper_delay", 0.8) or 0.8),
    )
    cfg = AppConfig(
        active_preset=data.get("active_preset", "默认配置"),
        active_provider=data.get("active_provider", data.get("activeProvider", "5plus1官方")),
        providers=_providers_from_raw(data.get("providers")),
        question=data.get("question", ""),
        answer=data.get("answer", ""),
        rubric=data.get("rubric", ""),
        material_images=[str(x) for x in data.get("material_images", data.get("materialImages", []))],
        scoring=scoring,
        workflow=workflow,
        boxes=[RegionBox.from_dict(x) for x in data.get("boxes", [])],
        preprocess_level=int(data.get("preprocess_level", 1) or 1),
        recognition_margin=int(data.get("recognition_margin", 0) or 0),
        blank_detection_enabled=bool(data.get("blank_detection_enabled", False)),
        blank_threshold=float(data.get("blank_threshold", 0.01) or 0.01),
        save_images=bool(data.get("save_images", True)),
    )
    names = {p.name for p in cfg.providers}
    if cfg.active_provider not in names and cfg.providers:
        cfg.active_provider = cfg.providers[0].name
    if not cfg.workflow.primary_provider_name or cfg.workflow.primary_provider_name not in names:
        cfg.workflow.primary_provider_name = cfg.active_provider
    if not cfg.workflow.secondary_provider_name or cfg.workflow.secondary_provider_name not in names:
        cfg.workflow.secondary_provider_name = cfg.workflow.secondary_provider.name if cfg.workflow.secondary_provider.name in names else cfg.active_provider
    if not cfg.workflow.arbitration_provider_name or cfg.workflow.arbitration_provider_name not in names:
        cfg.workflow.arbitration_provider_name = cfg.workflow.arbitration_provider.name if cfg.workflow.arbitration_provider.name in names else cfg.active_provider
    return cfg


def _providers_from_raw(raw: Any) -> list[Provider]:
    defaults = default_providers()
    default_by_name = {p.name: p for p in defaults}
    if not raw:
        return defaults
    providers: list[Provider] = []
    if isinstance(raw, dict):
        for name, value in raw.items():
            if isinstance(value, dict):
                item = {**value, "name": value.get("name", name)}
                providers.append(provider_from_dict(item))
    elif isinstance(raw, list):
        providers = [provider_from_dict(x) for x in raw if isinstance(x, dict)]
    if not providers:
        return defaults
    by_name = {p.name: p for p in providers}
    for name, provider in default_by_name.items():
        if name not in by_name:
            providers.append(provider)
        elif not by_name[name].models:
            by_name[name].models = list(provider.models)
            if not by_name[name].model:
                by_name[name].model = provider.model
    return providers
