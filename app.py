from __future__ import annotations

import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from ai_client import grade_dual, grade_with_optional_ocr, test_provider
from automation import fill_and_submit, fill_scores
from history import add_history, clear_history, export_csv, export_docx, export_html, export_json, export_pdf, export_xlsx
from image_tools import black_pixel_ratio, capture_region, image_to_base64, is_blank, preprocess_image
from image_tools import image_quality_report
from models import AppConfig, Provider, RegionBox, config_from_dict
from overlay import RegionOverlay
from scoring import apply_scoring
from storage import CONFIG_FILE, PRESETS_FILE, clear_blank_reference, load_blank_reference, load_config, load_presets, save_blank_reference, save_config, save_presets


# 主 UI 使用标准库 tkinter，方便直接运行和打包为 exe。


class AIMarkerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI 自动阅卷桌面端")
        self.geometry("1160x760")
        self.minsize(1040, 680)
        self.config_data: AppConfig = load_config()
        self.status_var = tk.StringVar(value="就绪")
        self.progress_var = tk.StringVar(value="0/0")
        self.running = False
        self.current_result: dict[str, Any] | None = None
        self.current_image = None
        self.loop_count = 0
        self.continuous = False
        self.skip_blank_once = False
        self.work_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._build_style()
        self._build()
        self.after(150, self._poll_queue)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Primary.TButton", padding=(14, 8))
        style.configure("Danger.TButton", foreground="#b42318")

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="AI 自动阅卷桌面端", style="Title.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.status_var).pack(side="right")

        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)
        self._build_work_tab()
        self._build_config_tab()
        self._build_provider_tab()
        self._build_box_tab()
        self._build_history_tab()
        self._build_preset_tab()

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Label(footer, text="批阅进度").pack(side="left")
        ttk.Label(footer, textvariable=self.progress_var).pack(side="left", padx=8)
        ttk.Button(footer, text="保存配置", command=self.save_all).pack(side="right")

    def _build_work_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(tab, text="批改")
        left = ttk.Frame(tab)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        right = ttk.Frame(tab)
        right.pack(side="right", fill="y")

        ttk.Label(left, text="AI 输出").pack(anchor="w")
        self.output = tk.Text(left, wrap="word", height=22)
        self.output.pack(fill="both", expand=True, pady=(4, 10))
        self.output.tag_config("muted", foreground="#667085")

        ttk.Label(left, text="识别答案").pack(anchor="w")
        self.answer_view = tk.Text(left, wrap="word", height=6)
        self.answer_view.pack(fill="x", pady=(4, 0))

        # 开始批改弹窗输入份数，直接进入连续批改模式
        ttk.Button(right, text="开始批改", style="Primary.TButton", command=self.start_grading).pack(fill="x", pady=4)
        ttk.Button(right, text="调试批改", command=self.debug_once).pack(fill="x", pady=4)
        ttk.Button(right, text="停止批改", command=self.stop).pack(fill="x", pady=4)
        ttk.Button(right, text="检查配置", command=self.check_readiness).pack(fill="x", pady=4)
        ttk.Separator(right).pack(fill="x", pady=10)
        ttk.Button(right, text="仅识别框截图", command=self.preview_capture).pack(fill="x", pady=4)
        ttk.Separator(right).pack(fill="x", pady=10)
        ttk.Button(right, text="采集空白卡范本", command=self.capture_blank_reference).pack(fill="x", pady=4)
        ttk.Button(right, text="清除空白卡范本", command=lambda: (clear_blank_reference(), self.set_status("空白卡范本已清除"))).pack(fill="x", pady=4)

    def _build_config_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(tab, text="配置")
        form = ttk.Frame(tab)
        form.pack(fill="both", expand=True)

        self.active_provider = tk.StringVar(value=self.config_data.active_provider)
        self.primary_enabled = tk.BooleanVar(value=self.config_data.workflow.primary_enabled)
        self.secondary_enabled = tk.BooleanVar(value=self.config_data.workflow.dual_enabled)
        self.arbitration_enabled = tk.BooleanVar(value=self.config_data.workflow.arbitration_enabled)
        self.primary_provider = tk.StringVar(value=self.config_data.workflow.primary_provider_name)
        self.secondary_provider = tk.StringVar(value=self.config_data.workflow.secondary_provider_name)
        self.arbitration_provider = tk.StringVar(value=self.config_data.workflow.arbitration_provider_name)
        self.ocr_provider = tk.StringVar(value=self.config_data.workflow.ocr_provider_name)
        self.primary_model = tk.StringVar(value=(self.get_provider_by_name(self.primary_provider.get()) or self.get_active_provider()).model)
        self.secondary_model = tk.StringVar(value=(self.get_provider_by_name(self.secondary_provider.get()) or self.get_active_provider()).model)
        self.arbitration_model = tk.StringVar(value=(self.get_provider_by_name(self.arbitration_provider.get()) or self.get_active_provider()).model)
        self.ocr_model = tk.StringVar(value=(self.get_provider_by_name(self.ocr_provider.get()) or self.get_active_provider()).model)
        self.recognition_mode = tk.StringVar(value=self.config_data.workflow.recognition_mode)
        self.mode = tk.StringVar(value=self.config_data.workflow.mode)
        self.grade_level = tk.StringVar(value=self.config_data.grade_level)
        self.subject = tk.StringVar(value=self.config_data.subject)
        self.question_type = tk.StringVar(value=self.config_data.question_type)
        self.max_score = tk.StringVar(value=str(self.config_data.scoring.max_score))
        self.round_step = tk.StringVar(value=str(self.config_data.scoring.round_step))
        self.round_method = tk.StringVar(value=self.config_data.scoring.round_method)
        self.diligence_enabled = tk.BooleanVar(value=self.config_data.scoring.diligence_enabled)
        self.diligence_bonus = tk.StringVar(value=str(self.config_data.scoring.diligence_max_bonus))
        self.save_images = tk.BooleanVar(value=self.config_data.save_images)
        self.preprocess = tk.IntVar(value=self.config_data.preprocess_level)
        self.recognition_margin = tk.StringVar(value=str(self.config_data.recognition_margin))
        self.blank_enabled = tk.BooleanVar(value=self.config_data.blank_detection_enabled)
        self.capture_delay = tk.StringVar(value=str(self.config_data.workflow.capture_delay))
        self.scoring_delay = tk.StringVar(value=str(self.config_data.workflow.scoring_delay))
        self.next_paper_delay = tk.StringVar(value=str(self.config_data.workflow.next_paper_delay))
        self.score_switch_mode = tk.StringVar(value=self.config_data.workflow.score_switch_mode)
        self.target_enabled = tk.BooleanVar(value=self.config_data.workflow.target_count_enabled)
        self.target_count = tk.StringVar(value=str(self.config_data.workflow.target_count))

        row = 0
        ttk.Checkbutton(form, text="启用主评", variable=self.primary_enabled).grid(row=row, column=1, sticky="w", pady=6)
        row += 1
        row = self._provider_model_row(form, row, "主评", self.primary_provider, self.primary_model)
        ttk.Checkbutton(form, text="启用副评", variable=self.secondary_enabled).grid(row=row, column=1, sticky="w", pady=6)
        row += 1
        row = self._provider_model_row(form, row, "副评", self.secondary_provider, self.secondary_model)
        ttk.Checkbutton(form, text="启用仲裁", variable=self.arbitration_enabled).grid(row=row, column=1, sticky="w", pady=6)
        row += 1
        row = self._provider_model_row(form, row, "仲裁", self.arbitration_provider, self.arbitration_model)
        ttk.Label(form, text="识别方式").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Combobox(form, textvariable=self.recognition_mode, values=["direct", "ocr_first"], state="readonly").grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        row = self._provider_model_row(form, row, "独立OCR", self.ocr_provider, self.ocr_model)
        self.dual_threshold = tk.StringVar(value=str(self.config_data.workflow.dual_threshold))
        row = self._entry(form, row, "仲裁阈值", self.dual_threshold)
        ttk.Label(form, text="批改模式").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Combobox(form, textvariable=self.mode, values=["normal", "trial", "unattended"], state="readonly").grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        row = self._entry(form, row, "满分", self.max_score)
        row = self._entry(form, row, "取整步长", self.round_step)
        ttk.Label(form, text="取整方式").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Combobox(form, textvariable=self.round_method, values=["round", "floor", "ceil"], state="readonly").grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        ttk.Checkbutton(form, text="启用勤勉加分", variable=self.diligence_enabled).grid(row=row, column=1, sticky="w", pady=6)
        row += 1
        row = self._entry(form, row, "勤勉最高加分", self.diligence_bonus)
        ttk.Checkbutton(form, text="保存答题卡截图到历史", variable=self.save_images).grid(row=row, column=1, sticky="w", pady=6)
        row += 1
        ttk.Label(form, text="OCR 预处理").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Scale(form, from_=0, to=3, variable=self.preprocess, orient="horizontal").grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        row = self._entry(form, row, "识别框内边距(px)", self.recognition_margin)
        ttk.Checkbutton(form, text="启用空白答题卡检测", variable=self.blank_enabled).grid(row=row, column=1, sticky="w", pady=6)
        row += 1
        # 连续批改使用自动提交，不再需要人工确认和倒计时
        row = self._entry(form, row, "取卡延时(秒)", self.capture_delay)
        row = self._entry(form, row, "打分延时(秒)", self.scoring_delay)
        row = self._entry(form, row, "批改间隔延时(秒)", self.next_paper_delay)
        ttk.Label(form, text="多打分框切换").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Combobox(form, textvariable=self.score_switch_mode, values=["single", "tab", "enter", "space"], state="readonly").grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        ttk.Checkbutton(form, text="限制批阅份数", variable=self.target_enabled).grid(row=row, column=1, sticky="w", pady=6)
        row += 1
        row = self._entry(form, row, "目标份数", self.target_count)

        text_area = ttk.Frame(form)
        text_area.grid(row=0, column=2, rowspan=12, sticky="nsew", padx=(20, 0))
        meta = ttk.Frame(text_area)
        meta.pack(fill="x", pady=(0, 8))
        for label, var in [("年级", self.grade_level), ("学科", self.subject), ("题型", self.question_type)]:
            block = ttk.Frame(meta)
            block.pack(side="left", fill="x", expand=True, padx=(0, 6))
            ttk.Label(block, text=label).pack(anchor="w")
            ttk.Entry(block, textvariable=var).pack(fill="x")
        self.question = self._labeled_text(text_area, "题目内容", self.config_data.question, 6)
        self.answer = self._labeled_text(text_area, "参考答案", self.config_data.answer, 6)
        self.rubric = self._labeled_text(text_area, "评分标准", self.config_data.rubric, 8)
        material_panel = ttk.LabelFrame(text_area, text="评分材料图片")
        material_panel.pack(fill="x", pady=(0, 10))
        material_bar = ttk.Frame(material_panel)
        material_bar.pack(fill="x", padx=8, pady=6)
        ttk.Button(material_bar, text="添加图片", command=self.add_material_images).pack(side="left", padx=3)
        ttk.Button(material_bar, text="删除选中", command=self.remove_material_image).pack(side="left", padx=3)
        ttk.Button(material_bar, text="打开图片", command=self.open_material_image).pack(side="left", padx=3)
        self.material_list = tk.Listbox(material_panel, height=4)
        self.material_list.pack(fill="x", padx=8, pady=(0, 8))
        self.refresh_material_images()

        # 分小题评分来自脚本的 scoring.units，桌面端用表格维护。
        unit_panel = ttk.LabelFrame(form, text="分小题评分")
        unit_panel.grid(row=row + 1, column=0, columnspan=3, sticky="nsew", pady=(16, 0))
        unit_bar = ttk.Frame(unit_panel)
        unit_bar.pack(fill="x", padx=8, pady=8)
        ttk.Button(unit_bar, text="添加小题", command=self.add_unit).pack(side="left", padx=4)
        ttk.Button(unit_bar, text="删除选中", command=self.remove_unit).pack(side="left", padx=4)
        ttk.Button(unit_bar, text="应用小题表", command=self.apply_units_from_table).pack(side="left", padx=4)
        self.unit_tree = ttk.Treeview(unit_panel, columns=("label", "max", "step"), show="headings", height=5)
        for col, title, width in [("label", "小题", 180), ("max", "满分", 100), ("step", "取整步长", 100)]:
            self.unit_tree.heading(col, text=title)
            self.unit_tree.column(col, width=width)
        self.unit_tree.pack(fill="x", padx=8, pady=(0, 8))
        self.unit_tree.bind("<Double-1>", self.edit_unit_cell)
        self.refresh_units()

        form.columnconfigure(1, weight=1)
        form.columnconfigure(2, weight=2)
        form.rowconfigure(11, weight=1)

    def _build_provider_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(tab, text="服务商")
        left = ttk.Frame(tab)
        left.pack(side="left", fill="y", padx=(0, 12))
        right = ttk.Frame(tab)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="AI 服务商").pack(anchor="w")
        self.provider_tree = ttk.Treeview(left, columns=("name", "model"), show="headings", height=18)
        self.provider_tree.heading("name", text="名称")
        self.provider_tree.heading("model", text="模型")
        self.provider_tree.column("name", width=140)
        self.provider_tree.column("model", width=180)
        self.provider_tree.pack(fill="y", expand=True, pady=(4, 8))
        self.provider_tree.bind("<<TreeviewSelect>>", self.on_provider_select)
        ttk.Button(left, text="新增服务商", command=self.add_provider).pack(fill="x", pady=3)
        ttk.Button(left, text="复制选中", command=self.copy_provider).pack(fill="x", pady=3)
        ttk.Button(left, text="删除选中", command=self.delete_provider).pack(fill="x", pady=3)
        ttk.Button(left, text="保存服务商", command=self.save_provider_from_form).pack(fill="x", pady=(12, 3))
        ttk.Button(left, text="设为主评", command=self.set_selected_as_primary).pack(fill="x", pady=3)
        ttk.Button(left, text="测试连接", command=self.test_selected_provider).pack(fill="x", pady=3)

        self.provider_name_var = tk.StringVar()
        self.provider_endpoint_var = tk.StringVar()
        self.provider_key_var = tk.StringVar()
        self.provider_model_var = tk.StringVar()
        self.provider_models_var = tk.StringVar()
        self.provider_reasoning_var = tk.StringVar()
        self.provider_source_var = tk.StringVar(value="network")
        self.provider_test_prompt_var = tk.StringVar(value="请只回复：连接成功")

        row = 0
        row = self._entry(right, row, "名称", self.provider_name_var)
        ttk.Label(right, text="模型来源").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Combobox(right, textvariable=self.provider_source_var, values=["network", "local", "lan", "custom"], state="readonly").grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        row = self._entry(right, row, "API 端点", self.provider_endpoint_var)
        row = self._entry(right, row, "API Key", self.provider_key_var, show="*")
        ttk.Label(right, text="当前模型").grid(row=row, column=0, sticky="w", pady=6)
        self.provider_model_combo = ttk.Combobox(right, textvariable=self.provider_model_var)
        self.provider_model_combo.grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        row = self._entry(right, row, "模型列表(逗号分隔)", self.provider_models_var)
        row = self._entry(right, row, "推理强度", self.provider_reasoning_var)
        row = self._entry(right, row, "测试对话", self.provider_test_prompt_var)
        ttk.Label(right, text="内置示例支持 5plus1 官方、火山方舟和 OpenAI 兼容接口；自定义服务商只要兼容 /chat/completions 即可。").grid(row=row, column=0, columnspan=2, sticky="w", pady=(16, 6))
        right.columnconfigure(1, weight=1)
        self.refresh_provider_tree()

    def _build_box_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(tab, text="操作框")
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="+识别框", command=lambda: self.add_box("recognition")).pack(side="left", padx=4)
        ttk.Button(toolbar, text="+打分框", command=lambda: self.add_box("score")).pack(side="left", padx=4)
        ttk.Button(toolbar, text="+提交框", command=lambda: self.add_box("submit")).pack(side="left", padx=4)
        ttk.Button(toolbar, text="打开拖拽调整", command=self.open_overlay).pack(side="left", padx=12)

        columns = ("name", "kind", "x", "y", "w", "h")
        self.box_tree = ttk.Treeview(tab, columns=columns, show="headings", height=12)
        for c, title in zip(columns, ["名称", "类型", "X", "Y", "宽", "高"]):
            self.box_tree.heading(c, text=title)
            self.box_tree.column(c, width=100)
        self.box_tree.pack(fill="both", expand=True)
        self.refresh_boxes()

    def _build_history_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(tab, text="历史")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="刷新", command=self.refresh_history).pack(side="left", padx=4)
        ttk.Button(bar, text="导出 JSON", command=lambda: self._export(export_json)).pack(side="left", padx=4)
        ttk.Button(bar, text="导出 CSV", command=lambda: self._export(export_csv)).pack(side="left", padx=4)
        ttk.Button(bar, text="导出 HTML", command=lambda: self._export(export_html)).pack(side="left", padx=4)
        ttk.Button(bar, text="导出 Word", command=lambda: self._export(export_docx)).pack(side="left", padx=4)
        ttk.Button(bar, text="导出 Excel", command=lambda: self._export(export_xlsx)).pack(side="left", padx=4)
        ttk.Button(bar, text="导出 PDF", command=lambda: self._export(export_pdf)).pack(side="left", padx=4)
        ttk.Button(bar, text="清空历史", command=self.clear_history_records).pack(side="left", padx=4)
        self.history_text = tk.Text(tab, wrap="word")
        self.history_text.pack(fill="both", expand=True)
        self.refresh_history()

    def _build_preset_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(tab, text="方案")
        left = ttk.Frame(tab)
        left.pack(side="left", fill="y", padx=(0, 12))
        right = ttk.Frame(tab)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="配置方案").pack(anchor="w")
        self.preset_list = tk.Listbox(left, height=18, width=28)
        self.preset_list.pack(fill="y", expand=True, pady=(4, 8))
        self.preset_list.bind("<<ListboxSelect>>", self._on_preset_select)
        ttk.Button(left, text="载入选中方案", command=self.load_selected_preset).pack(fill="x", pady=3)
        ttk.Button(left, text="保存为当前方案", command=self.save_current_preset).pack(fill="x", pady=3)
        ttk.Button(left, text="另存为新方案", command=self.save_as_preset).pack(fill="x", pady=3)
        ttk.Button(left, text="删除选中方案", command=self.delete_selected_preset).pack(fill="x", pady=3)
        ttk.Button(left, text="补足10套标准", command=self.ensure_ten_presets).pack(fill="x", pady=3)
        ttk.Button(left, text="导出全部配置", command=self.export_settings).pack(fill="x", pady=(12, 3))
        ttk.Button(left, text="导入配置", command=self.import_settings).pack(fill="x", pady=3)

        self.preset_name_var = tk.StringVar(value=self.config_data.active_preset)
        ttk.Label(right, text="方案名称").pack(anchor="w")
        ttk.Entry(right, textvariable=self.preset_name_var).pack(fill="x", pady=(4, 12))
        ttk.Label(right, text="方案说明").pack(anchor="w")
        self.preset_info = tk.Text(right, height=14, wrap="word")
        self.preset_info.pack(fill="both", expand=True, pady=(4, 0))
        self.refresh_presets()

    def _entry(self, parent, row: int, label: str, var: tk.Variable, show: str | None = None) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=var, show=show).grid(row=row, column=1, sticky="ew", pady=6)
        return row + 1

    def _provider_model_row(self, parent, row: int, label: str, provider_var: tk.StringVar, model_var: tk.StringVar) -> int:
        # 主评/副评/仲裁都可以独立选择服务商和该服务商下的模型。
        ttk.Label(parent, text=f"{label}服务商").grid(row=row, column=0, sticky="w", pady=6)
        line = ttk.Frame(parent)
        line.grid(row=row, column=1, sticky="ew", pady=6)
        provider_combo = ttk.Combobox(line, textvariable=provider_var, values=self.provider_names(), state="readonly", width=18)
        model_combo = ttk.Combobox(line, textvariable=model_var, values=self.model_names(provider_var.get()), width=28)
        provider_combo.pack(side="left", fill="x", expand=True, padx=(0, 6))
        model_combo.pack(side="left", fill="x", expand=True)
        provider_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_role_provider_changed(provider_var, model_var, model_combo))
        if not hasattr(self, "role_model_combos"):
            self.role_model_combos = []
        self.role_model_combos.append((provider_var, model_var, provider_combo, model_combo))
        return row + 1

    def _labeled_text(self, parent, label: str, value: str, height: int) -> tk.Text:
        ttk.Label(parent, text=label).pack(anchor="w")
        text = tk.Text(parent, height=height, wrap="word")
        text.pack(fill="both", expand=True, pady=(4, 10))
        text.insert("1.0", value)
        return text

    def set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.update_idletasks()

    def save_all(self) -> None:
        self._apply_role_models_to_providers()
        self.config_data.active_provider = self.primary_provider.get() or self.config_data.active_provider
        self.config_data.workflow.primary_enabled = self.primary_enabled.get()
        self.config_data.workflow.dual_enabled = self.secondary_enabled.get()
        self.config_data.workflow.arbitration_enabled = self.arbitration_enabled.get()
        self.config_data.workflow.primary_provider_name = self.primary_provider.get()
        self.config_data.workflow.secondary_provider_name = self.secondary_provider.get()
        self.config_data.workflow.arbitration_provider_name = self.arbitration_provider.get()
        self.config_data.workflow.ocr_provider_name = self.ocr_provider.get()
        self.config_data.workflow.secondary_provider = self.get_provider_by_name(self.secondary_provider.get()) or self.config_data.workflow.secondary_provider
        self.config_data.workflow.arbitration_provider = self.get_provider_by_name(self.arbitration_provider.get()) or self.config_data.workflow.arbitration_provider
        self.config_data.workflow.ocr_provider = self.get_provider_by_name(self.ocr_provider.get()) or self.config_data.workflow.ocr_provider
        self.config_data.workflow.mode = self.mode.get()
        self.config_data.workflow.recognition_mode = self.recognition_mode.get()
        self.config_data.workflow.dual_threshold = float(self.dual_threshold.get() or 2)
        self.config_data.workflow.capture_delay = float(self.capture_delay.get() or 0)
        self.config_data.workflow.scoring_delay = float(self.scoring_delay.get() or 0)
        self.config_data.workflow.next_paper_delay = float(self.next_paper_delay.get() or 0.8)
        self.config_data.workflow.score_switch_mode = self.score_switch_mode.get()
        self.config_data.workflow.target_count_enabled = self.target_enabled.get()
        self.config_data.workflow.target_count = int(float(self.target_count.get() or 0))
        self.config_data.scoring.max_score = float(self.max_score.get() or 0)
        self.config_data.scoring.round_step = float(self.round_step.get() or 1)
        self.config_data.scoring.round_method = self.round_method.get()
        self.config_data.scoring.diligence_enabled = self.diligence_enabled.get()
        self.config_data.scoring.diligence_max_bonus = float(self.diligence_bonus.get() or 0)
        self.apply_units_from_table(show_status=False)
        self.config_data.preprocess_level = int(self.preprocess.get())
        self.config_data.recognition_margin = int(float(self.recognition_margin.get() or 0))
        self.config_data.blank_detection_enabled = self.blank_enabled.get()
        self.config_data.save_images = self.save_images.get()
        self.config_data.grade_level = self.grade_level.get().strip()
        self.config_data.subject = self.subject.get().strip()
        self.config_data.question_type = self.question_type.get().strip()
        self.config_data.question = self.question.get("1.0", "end").strip()
        self.config_data.answer = self.answer.get("1.0", "end").strip()
        self.config_data.rubric = self.rubric.get("1.0", "end").strip()
        save_config(self.config_data)
        self.refresh_boxes()
        self.set_status("配置已保存")

    def apply_config_to_ui(self) -> None:
        self.active_provider.set(self.config_data.active_provider)
        self.primary_enabled.set(self.config_data.workflow.primary_enabled)
        self.secondary_enabled.set(self.config_data.workflow.dual_enabled)
        self.arbitration_enabled.set(self.config_data.workflow.arbitration_enabled)
        self.primary_provider.set(self.config_data.workflow.primary_provider_name)
        self.secondary_provider.set(self.config_data.workflow.secondary_provider_name)
        self.arbitration_provider.set(self.config_data.workflow.arbitration_provider_name)
        self.ocr_provider.set(self.config_data.workflow.ocr_provider_name)
        self.primary_model.set((self.get_provider_by_name(self.primary_provider.get()) or self.get_active_provider()).model)
        self.secondary_model.set((self.get_provider_by_name(self.secondary_provider.get()) or self.get_active_provider()).model)
        self.arbitration_model.set((self.get_provider_by_name(self.arbitration_provider.get()) or self.get_active_provider()).model)
        self.ocr_model.set((self.get_provider_by_name(self.ocr_provider.get()) or self.get_active_provider()).model)
        self.mode.set(self.config_data.workflow.mode)
        self.recognition_mode.set(self.config_data.workflow.recognition_mode)
        self.grade_level.set(self.config_data.grade_level)
        self.subject.set(self.config_data.subject)
        self.question_type.set(self.config_data.question_type)
        self.max_score.set(str(self.config_data.scoring.max_score))
        self.round_step.set(str(self.config_data.scoring.round_step))
        self.round_method.set(self.config_data.scoring.round_method)
        self.diligence_enabled.set(self.config_data.scoring.diligence_enabled)
        self.diligence_bonus.set(str(self.config_data.scoring.diligence_max_bonus))
        self.save_images.set(self.config_data.save_images)
        self.preprocess.set(self.config_data.preprocess_level)
        self.recognition_margin.set(str(self.config_data.recognition_margin))
        self.blank_enabled.set(self.config_data.blank_detection_enabled)
        self.dual_threshold.set(str(self.config_data.workflow.dual_threshold))
        self.capture_delay.set(str(self.config_data.workflow.capture_delay))
        self.scoring_delay.set(str(self.config_data.workflow.scoring_delay))
        self.next_paper_delay.set(str(self.config_data.workflow.next_paper_delay))
        self.score_switch_mode.set(self.config_data.workflow.score_switch_mode)
        self.target_enabled.set(self.config_data.workflow.target_count_enabled)
        self.target_count.set(str(self.config_data.workflow.target_count))
        self.question.delete("1.0", "end")
        self.question.insert("1.0", self.config_data.question)
        self.answer.delete("1.0", "end")
        self.answer.insert("1.0", self.config_data.answer)
        self.rubric.delete("1.0", "end")
        self.rubric.insert("1.0", self.config_data.rubric)
        self.refresh_units()
        self.refresh_boxes()
        self.refresh_provider_tree()
        self.refresh_provider_combos()
        self.refresh_material_images()

    def refresh_material_images(self) -> None:
        if not hasattr(self, "material_list"):
            return
        self.material_list.delete(0, "end")
        for path in self.config_data.material_images:
            self.material_list.insert("end", path)

    def add_material_images(self) -> None:
        paths = filedialog.askopenfilenames(filetypes=[("图片文件", "*.png;*.jpg;*.jpeg;*.bmp;*.webp"), ("所有文件", "*.*")])
        if not paths:
            return
        existing = set(self.config_data.material_images)
        for path in paths:
            if path not in existing:
                self.config_data.material_images.append(path)
        self.refresh_material_images()
        self.set_status(f"已添加评分材料图片：{len(paths)}张")

    def remove_material_image(self) -> None:
        if not hasattr(self, "material_list"):
            return
        selected = list(self.material_list.curselection())
        for index in reversed(selected):
            if 0 <= index < len(self.config_data.material_images):
                self.config_data.material_images.pop(index)
        self.refresh_material_images()

    def open_material_image(self) -> None:
        if not hasattr(self, "material_list"):
            return
        selected = self.material_list.curselection()
        if not selected:
            return
        path = self.config_data.material_images[selected[0]]
        os.startfile(path)

    def refresh_units(self) -> None:
        if not hasattr(self, "unit_tree"):
            return
        self.unit_tree.delete(*self.unit_tree.get_children())
        for i, unit in enumerate(self.config_data.scoring.units):
            self.unit_tree.insert("", "end", iid=str(i), values=(unit.label, unit.max_score, unit.round_step))

    def add_unit(self) -> None:
        from models import ScoringUnit
        self.config_data.scoring.units.append(ScoringUnit(label=f"第{len(self.config_data.scoring.units) + 1}题", max_score=0, round_step=1))
        self.refresh_units()

    def remove_unit(self) -> None:
        selected = self.unit_tree.selection()
        if not selected:
            return
        indexes = sorted((int(x) for x in selected), reverse=True)
        for i in indexes:
            if 0 <= i < len(self.config_data.scoring.units):
                self.config_data.scoring.units.pop(i)
        self.refresh_units()

    def edit_unit_cell(self, event) -> None:
        item_id = self.unit_tree.identify_row(event.y)
        column = self.unit_tree.identify_column(event.x)
        if not item_id or column not in ("#1", "#2", "#3"):
            return
        col_index = int(column[1:]) - 1
        x, y, w, h = self.unit_tree.bbox(item_id, column)
        values = list(self.unit_tree.item(item_id, "values"))
        editor = ttk.Entry(self.unit_tree)
        editor.insert(0, values[col_index])
        editor.place(x=x, y=y, width=w, height=h)
        editor.focus_set()

        def commit(_event=None) -> None:
            values[col_index] = editor.get()
            self.unit_tree.item(item_id, values=values)
            editor.destroy()

        editor.bind("<Return>", commit)
        editor.bind("<FocusOut>", commit)

    def apply_units_from_table(self, show_status: bool = True) -> None:
        from models import ScoringUnit
        units = []
        for item in self.unit_tree.get_children() if hasattr(self, "unit_tree") else []:
            label, max_score, step = self.unit_tree.item(item, "values")
            if str(label).strip():
                units.append(ScoringUnit(str(label).strip(), float(max_score or 0), float(step or 1)))
        self.config_data.scoring.units = units
        if units:
            self.config_data.scoring.max_score = sum(u.max_score for u in units)
            self.max_score.set(str(self.config_data.scoring.max_score))
        if show_status:
            self.set_status("小题表已应用")

    def get_box(self, kind: str) -> RegionBox | None:
        return next((b for b in self.config_data.boxes if b.kind == kind and b.enabled), None)

    def add_box(self, kind: str) -> None:
        palette = {"recognition": ("识别框", "#2e7d32", 520, 280), "score": ("打分框", "#1565c0", 140, 56), "submit": ("提交框", "#ef6c00", 150, 60)}
        name, color, w, h = palette[kind]
        self.config_data.boxes.append(RegionBox(name, kind, 180 + len(self.config_data.boxes) * 30, 180, w, h, color))
        self.refresh_boxes()
        self.open_overlay()

    def refresh_boxes(self) -> None:
        if not hasattr(self, "box_tree"):
            return
        self.box_tree.delete(*self.box_tree.get_children())
        for i, b in enumerate(self.config_data.boxes):
            self.box_tree.insert("", "end", iid=str(i), values=(b.name, b.kind, b.x, b.y, b.width, b.height))

    def open_overlay(self) -> None:
        def done(boxes: list[RegionBox]) -> None:
            self.config_data.boxes = boxes
            save_config(self.config_data)
            self.refresh_boxes()
            self.set_status("操作框位置已保存")
        RegionOverlay(self, self.config_data.boxes, done)

    def preview_capture(self) -> None:
        box = self.get_box("recognition")
        if not box:
            messagebox.showerror("缺少识别框", "请先添加识别框")
            return
        img = preprocess_image(capture_region(box, self.config_data.recognition_margin), self.config_data.preprocess_level)
        report = image_quality_report(img)
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG 图片", "*.png")])
        if path:
            img.save(path)
            self.set_status(f"截图已保存：{path}；质量：{report['level']}，尺寸 {report['width']}x{report['height']}")

    def start_grading(self) -> None:
        """执行全量配置检查后，开启连续批改。"""
        self.save_all()
        
        # 第一步：全量配置检查
        problems = self._validate_ready_to_grade()
        if problems:
            messagebox.showerror("准备不足，无法启动批改", "\n\n".join(problems))
            return
        
        # 第二步：快速预检（截一张图验证质量）
        preview_ok = self._preview_before_grading()
        if not preview_ok:
            return
        
        # 第三步：确认开始
        target = self.config_data.workflow.target_count if self.config_data.workflow.target_count_enabled else 0
        msg = f"即将开始连续批改，目标份数：{target if target > 0 else '无限'}\n\n各项配置均已检查无误，点击确认开始自动批改。"
        if messagebox.askokcancel("准备开始", msg):
            self._start_continuous_grading()
    
    def _validate_ready_to_grade(self) -> list[str]:
        """全量检查，确保所有批改必要条件都满足。返回问题列表。"""
        problems = []
        
        # 检查三个操作框
        recog_box = self.get_box("recognition")
        score_box = self.get_box("score")
        submit_box = self.get_box("submit")
        
        if not recog_box:
            problems.append("❌ 识别框缺失\n请在主界面添加识别框，用于截取答题区域。")
        elif recog_box.width < 50 or recog_box.height < 50:
            problems.append("❌ 识别框过小\n识别框尺寸应至少 50×50px，请调整大小。")
        
        if not score_box:
            problems.append("❌ 打分框缺失\n请添加打分框，AI 分数需要填入此区域。")
        elif score_box.width < 30 or score_box.height < 20:
            problems.append("❌ 打分框过小\n打分框应能容纳分数，请调整大小。")
        
        if not submit_box:
            problems.append("❌ 提交框缺失\n请添加提交框，用于自动点击提交。")
        elif submit_box.width < 40 or submit_box.height < 20:
            problems.append("❌ 提交框过小\n提交框应能正常点击，请调整大小。")
        
        # 检查 AI 参数
        if not self.config_data.workflow.primary_enabled:
            problems.append('❌ 主评未启用\n请在配置面板勾选"启用主评"。')
        else:
            provider = self.get_active_provider()
            if not provider.endpoint:
                problems.append("❌ 主评 API 端点缺失\n请填写 API Endpoint。")
            if not provider.api_key:
                problems.append("❌ 主评 API Key 缺失\n请填写 API Key。")
            if not provider.model:
                problems.append("❌ 主评模型名称缺失\n请选择或填写模型名称。")
        
        # 检查 OCR 参数
        if self.config_data.workflow.recognition_mode == "ocr_first":
            ocr_provider = self.get_provider_by_name(self.config_data.workflow.ocr_provider_name)
            if not ocr_provider:
                problems.append("❌ OCR 服务商不存在\n请在配置面板检查 OCR 供应商设置。")
            else:
                if not ocr_provider.endpoint:
                    problems.append("❌ OCR API 端点缺失\n请填写 OCR API Endpoint。")
                if not ocr_provider.api_key:
                    problems.append("❌ OCR API Key 缺失\n请填写 OCR API Key。")
                if not ocr_provider.model:
                    problems.append("❌ OCR 模型名称缺失\n请选择或填写 OCR 模型。")
        
        # 检查评分依据
        if not (self.config_data.question or self.config_data.answer or self.config_data.rubric or self.config_data.material_images):
            problems.append("❌ 评分依据不足\n请至少填写题目、参考答案或评分标准之一。")
        
        # 检查批改份数
        if self.config_data.workflow.target_count_enabled:
            if self.config_data.workflow.target_count <= 0:
                problems.append("❌ 目标份数设置错误\n启用限制时，份数应大于 0。")
        
        return problems
    
    def _preview_before_grading(self) -> bool:
        """截一张图并检查质量，确保识别框位置和大小合适。"""
        try:
            recog_box = self.get_box("recognition")
            if not recog_box:
                messagebox.showerror("预检失败", "无法找到识别框")
                return False
            
            # 截图
            img = preprocess_image(
                capture_region(recog_box, self.config_data.recognition_margin),
                self.config_data.preprocess_level
            )
            quality = image_quality_report(img)
            
            # 检查图像质量
            issues = []
            if quality['width'] < 50 or quality['height'] < 50:
                issues.append(f"图像尺寸过小：{quality['width']}×{quality['height']}px")
            
            if quality['dark_ratio'] > 0.95:
                issues.append("图像过暗（暗像素占比 >95%），可能无法识别")
            elif quality['dark_ratio'] < 0.05:
                issues.append("图像过亮（暗像素占比 <5%），可能无法识别")
            
            if quality['level'] == "低":
                issues.append("图像质量评估为低，建议检查光线和对焦")
            
            if issues:
                msg = "识别框预检发现问题：\n\n" + "\n".join(f"• {i}" for i in issues)
                msg += "\n\n是否继续？（建议先调整截图框位置或光线）"
                if not messagebox.askokcancel("预检警告", msg):
                    return False
            else:
                messagebox.showinfo("预检通过", f"识别框质量良好\n尺寸：{quality['width']}×{quality['height']}px，质量：{quality['level']}\n准备好了，点确认开始")
            
            return True
        except Exception as e:
            messagebox.showerror("预检出错", f"截图或质量检查失败：{str(e)}")
            return False
    
    def _start_continuous_grading(self) -> None:
        """开启连续批改模式，直接自动填分和提交。"""
        self.save_all()
        problems = self.validate_config(require_submit=False)
        if problems:
            messagebox.showerror("配置未就绪", "\n".join(problems))
            return
        self.running = True
        self.continuous = True
        self.skip_blank_once = False
        self.loop_count = 0
        # 自动填分提交，不需要确认窗口
        threading.Thread(target=self._loop_worker, daemon=True).start()
    
    def start_once(self) -> None:
        """调试专用：单份批改，不自动提交。"""
        self.save_all()
        problems = self.validate_config(require_submit=False)
        if problems:
            messagebox.showerror("配置未就绪", "\n".join(problems))
            return
        self.running = True
        self.continuous = False
        self.skip_blank_once = False
        threading.Thread(target=self._grade_once_worker, kwargs={"auto_submit": False}, daemon=True).start()

    def debug_once(self) -> None:
        self.save_all()
        problems = self.validate_config(require_submit=False)
        if problems:
            messagebox.showerror("调试批改不可用", "\n".join(problems))
            return
        self.running = True
        self.continuous = False
        self.skip_blank_once = False
        self.set_status("调试批改：仅处理一份，不自动提交")
        threading.Thread(target=self._grade_once_worker, kwargs={"auto_submit": False}, daemon=True).start()

    def stop(self) -> None:
        self.running = False
        self.continuous = False
        self.set_status("已停止")

    def validate_config(self, require_submit: bool) -> list[str]:
        problems: list[str] = []
        if not self.get_box("recognition"):
            problems.append("缺少识别框。")
        if require_submit:
            if not self.get_box("score"):
                problems.append("连续自动提交需要打分框。")
            if not self.get_box("submit"):
                problems.append("连续自动提交需要提交框。")
        if not self.config_data.workflow.primary_enabled:
            problems.append("主评未启用。")
        provider = self.get_active_provider()
        if not provider.endpoint:
            problems.append("主评服务商缺少 API 端点。")
        if not provider.api_key:
            problems.append("主评服务商缺少 API Key。")
        if not provider.model:
            problems.append("主评服务商缺少模型名称。")
        if self.config_data.workflow.recognition_mode == "ocr_first":
            ocr_provider = self.get_provider_by_name(self.config_data.workflow.ocr_provider_name)
            if not ocr_provider:
                problems.append("独立 OCR 服务商不存在。")
            else:
                if not ocr_provider.endpoint:
                    problems.append("独立 OCR 服务商缺少 API 端点。")
                if not ocr_provider.api_key:
                    problems.append("独立 OCR 服务商缺少 API Key。")
                if not ocr_provider.model:
                    problems.append("独立 OCR 服务商缺少模型名称。")
        if not (self.config_data.question or self.config_data.answer or self.config_data.rubric or self.config_data.material_images):
            problems.append("题目、参考答案、评分标准或评分材料图片至少填写一项。")
        return problems

    def check_readiness(self) -> None:
        self.save_all()
        problems = self.validate_config(require_submit=False)
        if problems:
            messagebox.showwarning("配置未就绪", "\n".join(problems))
            self.set_status("配置未就绪")
            return
        messagebox.showinfo("配置检查", "基础配置已就绪。调试批改不会要求打分框和提交框；连续自动提交前请确认操作框位置。")
        self.set_status("配置已就绪")

    def _loop_worker(self) -> None:
        target = self.config_data.workflow.target_count if self.config_data.workflow.target_count_enabled else 0
        count = 0
        while self.running:
            if target and count >= target:
                self.work_queue.put(("status", "已达到目标份数，自动停止"))
                self.running = False
                break
            self._grade_once_worker(auto_submit=True)
            count += 1
            self.loop_count = count
            self.work_queue.put(("progress", f"{count}/{target or '不限'}"))
            time.sleep(max(0.1, self.config_data.workflow.next_paper_delay))

    def _grade_once_worker(self, auto_submit: bool = False) -> None:
        try:
            recog = self.get_box("recognition")
            score_box = self.get_box("score")
            submit_box = self.get_box("submit")
            if not recog:
                raise RuntimeError("缺少识别框")
            capture_wait = max(0, self.config_data.workflow.capture_delay)
            if capture_wait:
                self.work_queue.put(("status", f"等待取卡稳定 {capture_wait:g} 秒"))
                time.sleep(capture_wait)
            self.work_queue.put(("status", "正在截取识别框"))
            img = preprocess_image(capture_region(recog, self.config_data.recognition_margin), self.config_data.preprocess_level)
            quality = image_quality_report(img)
            self.work_queue.put(("output", f"识别区质量：{quality['level']}，尺寸 {quality['width']}x{quality['height']}，暗像素占比 {quality['dark_ratio'] * 100:.2f}%\n"))
            if self.config_data.blank_detection_enabled and not self.skip_blank_once:
                ref = load_blank_reference()
                if ref:
                    cur = black_pixel_ratio(img)
                    blank, reason = is_blank(cur, ref, self.config_data.blank_threshold)
                    self.work_queue.put(("output", f"空白检测：{reason}\n"))
            if blank:
                        result = {"student_answer": "空白答题卡", "ai_score": 0, "final_score": 0, "comment": "空白答题卡，自动判 0 分", "is_blank_card": True, "max_score": self._max_score()}
                        self.work_queue.put(("result", (result, img, auto_submit)))
                        # 连续批改时自动填分和提交
                        if auto_submit and score_box and submit_box and self.continuous:
                            fill_and_submit(score_box, submit_box, 0, switch_mode=self.config_data.workflow.score_switch_mode)
                        return
            self.skip_blank_once = False
            self.work_queue.put(("status", "正在调用 AI"))
            provider = self.get_active_provider()
            if not self.config_data.workflow.primary_enabled:
                raise RuntimeError("主评未启用，请在配置页打开主评开关")
            callback = lambda text: self.work_queue.put(("output", text))
            grade = grade_dual(self.config_data, img, provider, callback) if self.config_data.workflow.dual_enabled else grade_with_optional_ocr(self.config_data, img, provider, callback)
            scored = apply_scoring(grade, self.config_data.scoring)
            result = {
                "student_answer": grade.student_answer,
                "ai_score": grade.raw_score,
                "final_score": scored["final_score"],
                "comment": grade.comment,
                "basis": grade.scoring_basis,
                "calculation": grade.calculation,
                "sub_scores": scored["sub_scores"],
                "bonus": scored["bonus"],
                "dual_eval": grade.dual_eval,
                "max_score": self._max_score(),
                "quality": quality,
                "image_base64": image_to_base64(img) if self.config_data.save_images else "",
            }
            self.work_queue.put(("result", (result, img, auto_submit)))
            # 连续批改时自动填分和提交
            if auto_submit and score_box and submit_box and scored["final_score"] is not None and self.continuous:
                scoring_wait = max(0, self.config_data.workflow.scoring_delay)
                if scoring_wait:
                    time.sleep(scoring_wait)
                fill_and_submit(score_box, submit_box, scored["final_score"], self._score_values_for_fill(result), self.config_data.workflow.score_switch_mode)
        except Exception as exc:
            self.work_queue.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.work_queue.get_nowait()
                if kind == "status":
                    self.set_status(payload)
                elif kind == "progress":
                    self.progress_var.set(payload)
                elif kind == "output":
                    self.output.delete("1.0", "end")
                    self.output.insert("1.0", payload)
                elif kind == "result":
                    if isinstance(payload, tuple):
                        result, image, auto_submit = payload
                    else:
                        result, image, auto_submit = payload, None, False
                    self._show_result(result, image, auto_submit)
                elif kind == "error":
                    self.set_status("出错")
                    messagebox.showerror("批改失败", payload)
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _show_result(self, result: dict[str, Any], image=None, auto_submit: bool = False) -> None:
        """展示批改结果，连续批改时不弹窗。"""
        self.current_result = result
        self.current_image = image
        self.answer_view.delete("1.0", "end")
        self.answer_view.insert("1.0", result.get("student_answer", ""))
        self.output.insert("end", f"\n\n最终得分：{result.get('final_score')}\n")
        self._save_history_record(result)
        self.refresh_history()
        # 连续批改时自动填分提交后即返回，无需弹窗确认
        self.set_status("批改完成，已自动提交" if self.continuous else "批改完成")

    def _save_history_record(self, result: dict[str, Any], corrected: bool = False) -> None:
        add_history({
            "preset": self.config_data.active_preset,
            "mode": self.config_data.workflow.mode,
            "student_answer": result.get("student_answer", ""),
            "ai_score": result.get("ai_score"),
            "final_score": result.get("final_score"),
            "comment": result.get("comment", ""),
            "corrected": corrected,
            "sub_scores": result.get("sub_scores", []),
            "bonus": result.get("bonus", 0),
            "dual_eval": result.get("dual_eval"),
            "image_base64": result.get("image_base64", ""),
        })

    def capture_blank_reference(self) -> None:
        box = self.get_box("recognition")
        if not box:
            messagebox.showerror("缺少识别框", "请先添加识别框")
            return
        img = preprocess_image(capture_region(box, self.config_data.recognition_margin), self.config_data.preprocess_level)
        data = black_pixel_ratio(img)
        save_blank_reference(data)
        self.set_status(f"空白卡范本已保存，占比 {data['ratio'] * 100:.2f}%")

    def _max_score(self) -> float:
        return sum(u.max_score for u in self.config_data.scoring.units) if self.config_data.scoring.units else self.config_data.scoring.max_score

    def provider_names(self) -> list[str]:
        return [p.name for p in self.config_data.providers]

    def model_names(self, provider_name: str) -> list[str]:
        provider = self.get_provider_by_name(provider_name)
        return provider.available_models() if provider else []

    def on_role_provider_changed(self, provider_var: tk.StringVar, model_var: tk.StringVar, model_combo: ttk.Combobox) -> None:
        models = self.model_names(provider_var.get())
        model_combo.configure(values=models)
        if models:
            model_var.set(models[0])

    def _apply_role_models_to_providers(self) -> None:
        # 角色下拉框里的模型会写回对应供应商，保证每家供应商保留自己的 endpoint/key/model。
        for provider_name, model in [
            (self.primary_provider.get(), self.primary_model.get()),
            (self.secondary_provider.get(), self.secondary_model.get()),
            (self.arbitration_provider.get(), self.arbitration_model.get()),
            (self.ocr_provider.get(), self.ocr_model.get()),
        ]:
            provider = self.get_provider_by_name(provider_name)
            if provider and model:
                provider.model = model
                if model not in provider.models:
                    provider.models.insert(0, model)

    def get_provider_by_name(self, name: str) -> Provider | None:
        return next((p for p in self.config_data.providers if p.name == name), None)

    def get_active_provider(self) -> Provider:
        provider_name = self.config_data.workflow.primary_provider_name or self.config_data.active_provider
        provider = self.get_provider_by_name(provider_name) or (self.config_data.providers[0] if self.config_data.providers else Provider())
        self.config_data.active_provider = provider.name
        return provider

    def refresh_provider_combos(self) -> None:
        names = self.provider_names()
        for provider_var, model_var, provider_combo, model_combo in getattr(self, "role_model_combos", []):
            provider_combo.configure(values=names)
            if provider_var.get() not in names and names:
                provider_var.set(names[0])
            models = self.model_names(provider_var.get())
            model_combo.configure(values=models)
            if model_var.get() not in models and models:
                model_var.set(models[0])

    def refresh_provider_tree(self) -> None:
        if not hasattr(self, "provider_tree"):
            return
        self.provider_tree.delete(*self.provider_tree.get_children())
        for index, provider in enumerate(self.config_data.providers):
            marker = " *" if provider.name == self.config_data.active_provider else ""
            self.provider_tree.insert("", "end", iid=str(index), values=(provider.name + marker, provider.model))
        self.refresh_provider_combos()

    def _selected_provider_index(self) -> int | None:
        if not hasattr(self, "provider_tree"):
            return None
        selected = self.provider_tree.selection()
        if not selected:
            return None
        return int(selected[0])

    def on_provider_select(self, _event=None) -> None:
        index = self._selected_provider_index()
        if index is None or index >= len(self.config_data.providers):
            return
        provider = self.config_data.providers[index]
        self.provider_name_var.set(provider.name)
        self.provider_endpoint_var.set(provider.endpoint)
        self.provider_key_var.set(provider.api_key)
        self.provider_model_var.set(provider.model)
        self.provider_models_var.set(", ".join(provider.available_models()))
        if hasattr(self, "provider_model_combo"):
            self.provider_model_combo.configure(values=provider.available_models())
        self.provider_reasoning_var.set(provider.reasoning_effort)
        self.provider_source_var.set(provider.source)

    def add_provider(self) -> None:
        base = "自定义服务商"
        names = set(self.provider_names())
        name = base
        i = 2
        while name in names:
            name = f"{base}{i}"
            i += 1
        self.config_data.providers.append(Provider(name=name))
        self.refresh_provider_tree()
        self.provider_tree.selection_set(str(len(self.config_data.providers) - 1))
        self.on_provider_select()

    def copy_provider(self) -> None:
        index = self._selected_provider_index()
        if index is None:
            return
        src = self.config_data.providers[index]
        names = set(self.provider_names())
        name = f"{src.name}副本"
        i = 2
        while name in names:
            name = f"{src.name}副本{i}"
            i += 1
        self.config_data.providers.append(Provider(name, src.endpoint, src.api_key, src.model, src.reasoning_effort, list(src.models)))
        self.refresh_provider_tree()

    def delete_provider(self) -> None:
        index = self._selected_provider_index()
        if index is None:
            return
        if len(self.config_data.providers) <= 1:
            messagebox.showinfo("不能删除", "至少保留一个服务商")
            return
        removed = self.config_data.providers.pop(index)
        if self.config_data.active_provider == removed.name:
            self.config_data.active_provider = self.config_data.providers[0].name
            self.active_provider.set(self.config_data.active_provider)
        fallback = self.config_data.providers[0].name
        for var in (self.primary_provider, self.secondary_provider, self.arbitration_provider, self.ocr_provider):
            if var.get() == removed.name:
                var.set(fallback)
        self.refresh_provider_tree()
        self.set_status(f"已删除服务商：{removed.name}")

    def save_provider_from_form(self) -> None:
        index = self._selected_provider_index()
        if index is None:
            messagebox.showinfo("未选择服务商", "请先选择一个服务商")
            return
        old_name = self.config_data.providers[index].name
        new_name = self.provider_name_var.get().strip()
        if not new_name:
            messagebox.showerror("名称错误", "服务商名称不能为空")
            return
        for i, provider in enumerate(self.config_data.providers):
            if i != index and provider.name == new_name:
                messagebox.showerror("名称重复", "服务商名称不能重复")
                return
        provider = self.config_data.providers[index]
        provider.name = new_name
        provider.endpoint = self.provider_endpoint_var.get().strip()
        provider.api_key = self.provider_key_var.get().strip()
        provider.model = self.provider_model_var.get().strip()
        provider.source = self.provider_source_var.get().strip() or "network"
        models = [x.strip() for x in self.provider_models_var.get().replace("\n", ",").split(",") if x.strip()]
        if provider.model and provider.model not in models:
            models.insert(0, provider.model)
        provider.models = models
        provider.reasoning_effort = self.provider_reasoning_var.get().strip()
        if self.config_data.active_provider == old_name:
            self.config_data.active_provider = new_name
            self.active_provider.set(new_name)
        if self.primary_provider.get() == old_name:
            self.primary_provider.set(new_name)
        if self.secondary_provider.get() == old_name:
            self.secondary_provider.set(new_name)
        if self.arbitration_provider.get() == old_name:
            self.arbitration_provider.set(new_name)
        if self.ocr_provider.get() == old_name:
            self.ocr_provider.set(new_name)
        save_config(self.config_data)
        self.refresh_provider_tree()
        self.set_status(f"服务商已保存：{new_name}")

    def set_selected_as_primary(self) -> None:
        index = self._selected_provider_index()
        if index is None:
            return
        provider = self.config_data.providers[index]
        self.config_data.active_provider = provider.name
        self.active_provider.set(provider.name)
        self.refresh_provider_tree()
        self.set_status(f"主评服务商：{provider.name}")

    def test_selected_provider(self) -> None:
        index = self._selected_provider_index()
        if index is None:
            messagebox.showinfo("未选择服务商", "请先选择一个服务商")
            return
        self.save_provider_from_form()
        provider = self.config_data.providers[index]
        self.set_status(f"正在测试服务商：{provider.name}")

        def worker() -> None:
            try:
                text = test_provider(provider, self.provider_test_prompt_var.get().strip() or "请只回复：连接成功")
                self.work_queue.put(("status", f"{provider.name} 连接成功：{text[:40]}"))
            except Exception as exc:
                self.work_queue.put(("error", f"{provider.name} 测试失败：{exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_presets(self) -> None:
        if not hasattr(self, "preset_list"):
            return
        self.preset_list.delete(0, "end")
        presets = load_presets()
        for name in presets:
            self.preset_list.insert("end", name)
        self._update_preset_info()

    def _on_preset_select(self, _event=None) -> None:
        self._update_preset_info()

    def _selected_preset_name(self) -> str | None:
        if not hasattr(self, "preset_list"):
            return None
        selected = self.preset_list.curselection()
        if not selected:
            return None
        return self.preset_list.get(selected[0])

    def _update_preset_info(self) -> None:
        if not hasattr(self, "preset_info"):
            return
        name = self._selected_preset_name() or self.config_data.active_preset
        presets = load_presets()
        data = presets.get(name, {})
        self.preset_info.delete("1.0", "end")
        if data:
            scoring = data.get("scoring", {})
            workflow = data.get("workflow", {})
            primary_name = workflow.get("primary_provider_name") or data.get("active_provider", "")
            self.preset_info.insert("1.0", f"当前方案：{name}\n主评服务商：{primary_name}\n副评：{'开启' if workflow.get('dual_enabled') else '关闭'}\n仲裁：{'开启' if workflow.get('arbitration_enabled', True) else '关闭'}\n满分：{scoring.get('max_score', '')}\n小题数：{len(scoring.get('units', []) or [])}\n模式：{workflow.get('mode', '')}\n空白检测：{'开启' if data.get('blank_detection_enabled') else '关闭'}")

    def load_selected_preset(self) -> None:
        name = self._selected_preset_name()
        if not name:
            messagebox.showinfo("未选择方案", "请先选择一个配置方案")
            return
        data = load_presets().get(name)
        if not data:
            return
        self.config_data = config_from_dict(data)
        self.config_data.active_preset = name
        self.preset_name_var.set(name)
        self.apply_config_to_ui()
        save_config(self.config_data)
        self.set_status(f"已载入方案：{name}")

    def save_current_preset(self) -> None:
        self.save_all()
        name = self.preset_name_var.get().strip() or self.config_data.active_preset
        self.config_data.active_preset = name
        presets = load_presets()
        presets[name] = self.config_data.to_dict()
        save_presets(presets)
        save_config(self.config_data)
        self.refresh_presets()
        self.set_status(f"方案已保存：{name}")

    def save_as_preset(self) -> None:
        self.save_all()
        name = self.preset_name_var.get().strip()
        if not name:
            messagebox.showerror("缺少名称", "请输入方案名称")
            return
        self.config_data.active_preset = name
        presets = load_presets()
        presets[name] = self.config_data.to_dict()
        save_presets(presets)
        self.refresh_presets()
        self.set_status(f"已另存方案：{name}")

    def delete_selected_preset(self) -> None:
        name = self._selected_preset_name()
        if not name:
            return
        presets = load_presets()
        if len(presets) <= 1:
            messagebox.showinfo("不能删除", "至少保留一个方案")
            return
        presets.pop(name, None)
        save_presets(presets)
        self.refresh_presets()
        self.set_status(f"已删除方案：{name}")

    def ensure_ten_presets(self) -> None:
        self.save_all()
        presets = load_presets()
        base = self.config_data.to_dict()
        for index in range(1, 11):
            name = f"评分标准{index}"
            presets.setdefault(name, {**base, "active_preset": name})
        save_presets(presets)
        self.refresh_presets()
        self.set_status("已补足10套评分标准方案")

    def refresh_history(self) -> None:
        from storage import load_history
        if not hasattr(self, "history_text"):
            return
        self.history_text.delete("1.0", "end")
        for r in load_history()[:100]:
            tm = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r.get("timestamp", 0)))
            self.history_text.insert("end", f"{tm} | {r.get('final_score')}分 | {r.get('student_answer', '')[:80]}\n")

    def _export(self, func) -> None:
        path = func()
        self.set_status(f"已导出：{path}")

    def clear_history_records(self) -> None:
        if messagebox.askyesno("清空历史", "确定要清空所有评阅历史吗？"):
            clear_history()
            self.refresh_history()
            self.set_status("历史记录已清空")

    def export_settings(self) -> None:
        self.save_all()
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 文件", "*.json")], initialfile="AI阅卷配置备份.json")
        if not path:
            return
        payload = {"config": self.config_data.to_dict(), "presets": load_presets()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        self.set_status(f"配置已导出：{path}")

    def import_settings(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON 文件", "*.json")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if "presets" in payload:
            save_presets(payload["presets"])
        if "config" in payload:
            self.config_data = config_from_dict(payload["config"])
            save_config(self.config_data)
            self.apply_config_to_ui()
        elif CONFIG_FILE.exists():
            self.config_data = load_config()
            self.apply_config_to_ui()
        if PRESETS_FILE.exists():
            self.refresh_presets()
        self.set_status("配置已导入")


def run_app() -> None:
    AIMarkerApp().mainloop()
