# 2026-06-26 代码优化与 UI 美化

## 完成项目

### 1. UI 主题现代化
- **引入 ttkbootstrap**：从原生 tkinter `clam` 主题升级到 ttkbootstrap `litera` 主题
- **创建 theme.py**：集中管理配色、字体、操作框尺寸常量
  - `THEME_NAME = "litera"`（浅色现代主题，可改为 `"darkly"` 深色主题）
  - `FONT_FAMILY`、`FONT_BASE`、`FONT_TITLE` 等字体常量
  - `BOX_META`：三类操作框（识别框/打分框/提交框）的配色与默认尺寸
  - `BOX_MIN_SIZE`：各框最小尺寸约束
  - `style_text()`、`style_listbox()`：让原生 tk.Text/Listbox 跟随主题配色

### 2. 主界面美化 (app.py)
- **继承 ttk.Window**：启用 ttkbootstrap 主题引擎
- **重设计头部**：双行标题（主标题 + 副标题），状态指示器右对齐
- **语义化按钮配色**：
  - 主操作：`SUCCESS`（开始批改）
  - 调试/信息：`INFO`（调试批改、仅识别框截图）
  - 危险操作：`DANGER`（停止批改、删除）
  - 次要操作：`SECONDARY + OUTLINE`（检查配置、导出）
- **统一 Text/Listbox 配色**：通过 `_register_text()` / `_register_listbox()` 注册并应用主题配色

### 3. 代码优化
- **去重操作框常量**：`add_box()` 从 `theme.BOX_META` 读取配色与尺寸
- **统一尺寸校验**：`_validate_ready_to_grade()` 使用 `_box_too_small()` 和 `theme.BOX_MIN_SIZE`
- **字体统一**：所有硬编码字体（Microsoft YaHei / Segoe UI）替换为 `theme.FONT_FAMILY`
  - 影响文件：app.py, overlay.py, correction_dialog.py, submit_dialog.py

### 4. 文档更新
- **requirements.txt**：新增 `ttkbootstrap>=1.10.1`
- **README.md**：
  - 依赖说明新增 ttkbootstrap
  - 目录结构新增 theme.py 说明
  - 修正 "##目录结构" 标题格式

### 5. 插件安装
- **Superpowers** (v6.0.3)：obra/superpowers-marketplace
- **UI UX Pro Max** (v2.6.2)：nextlevelbuilder/ui-ux-pro-max-skill

## 验证结果
✅ 所有 .py 文件编译通过（py_compile）  
✅ 主窗口实例化成功（6 个 tab、7 个 Text、2 个 Listbox）  
✅ 主题 "litera" 正确加载  
✅ 对话框（correction_dialog / submit_dialog）字体已统一  

## 如何切换主题
编辑 `theme.py` 第 10 行：
```python
THEME_NAME = "darkly"  # 深色主题
# 其他可选：superhero, cyborg, solar, vapor 等
```

## 技术栈
- **UI 框架**：ttkbootstrap (基于 tkinter)
- **图像处理**：Pillow
- **自动化**：pyautogui
- **HTTP 客户端**：requests
