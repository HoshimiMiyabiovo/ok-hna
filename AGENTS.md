# AGENTS.md

本文件是该仓库的长期约定，所有改动（含 AI 代理）必须遵守。

## 项目概况

- 崩坏：因缘精灵（Nexus Anima，进程 `NexusAnima.exe`）自动化，基于 ok-script 3.0.13。
- Python 一律使用项目解释器 `.venv\Scripts\python.exe`。
- 任务代码在 `tasks/`（在 `config.py` 的 `onetime_tasks` 注册），测试在 `tests/`。

## 运行环境（必须）

- 游戏进程以管理员权限运行：非管理员进程对游戏窗口 PostMessage/WGC 都会被系统拒绝（UIPI）。
- GUI 与开发用 MCP 运行时都必须以管理员启动；`start_gui.py` 会自动请求 UAC 提权。
- 开发 MCP：`.venv\Scripts\python.exe start_mcp.py`（同样需要提权），连接信息在 `logs/mcp/connections/`。

## 窗口交互与抓帧

- 游戏窗口的 interaction 用 `PostMessage`：可后台点击、后台抓帧，用户可同时用电脑。
- `Pynput` 仅在前台可用，且游戏不在前台时会停止抓帧（`should_capture` 返回 False），不要设为默认。
- `device_manager.ensure_capture()` 的 `windows.interaction` 只能传字符串（如 `"PostMessage"`）；
  传列表会把列表写进 `win_interaction_class`，后续 `isinstance` 直接崩溃。
  列表形式只用于 `config.py` 顶层 `windows.interaction` 的启动初始化。

## 界面状态判定

- 登录页：OCR 匹配 `开始游戏` / `点击开始`。
- 「已进入游戏」只认主世界 HUD：模板 `main_world_bag` 与 `main_world_esc_badge` **同时命中**（阈值 0.85）。
- 禁止用 UID 水印、账号信息、构建号等做状态判定；过场剧情/菜单不算进入主世界。
- 判定失败必须保存截图 + 全量 OCR 文本并报错，不允许“点了就算成功”或放宽口径凑成功。

## 图片素材与隐私（公开仓库）

- 实机截图入库前必须打码 UID 等个人标识（马赛克/遮挡），并用 OCR 复验读不出原文。
- 原图放 `ok_templates/`，标注写 `ok_templates/coco_annotations.json`（用 `CocoTemplateStore`），
  经 `generate_templates` 导出到 `assets/templates/`；任务里用原名称的 `find_one`/`find_feature`。
- `logs/`、`screenshots/`、`cache/`、`.venv/` 已在 `.gitignore`，运行日志与抓帧含明文 UID，禁止提交。
- 不得在代码、测试、素材、文档中写入账号 UID、token、密钥等敏感信息。

## 测试

- 运行：`.venv\Scripts\python.exe -m unittest tests.test_launcher`
- `TaskTestCase` 的 `config['config_folder']` 必须隔离到临时目录：测试运行会保存设备/任务配置，污染 `configs/`。
- 识别判定要有正样本 + 负样本（登录页、过场、主世界互相验证），并保留 `ok_templates/` 里的实机参考图。
