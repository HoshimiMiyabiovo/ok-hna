# ok-hna

《崩坏：因缘精灵》（Nexus Anima）的自动化脚本工程，基于 [ok-script](https://github.com/ok-oldking/ok-script) 框架构建。

> **状态：开发中。** 启动链路已实机跑通（直启 exe / 登录页点击 / 主世界 HUD 确认 / 热更重启提示自动处理）。
> 日常活跃关键链路已实机验证：每日目标 6 条、领取校验（活跃度 0→100→400→500，上限 500）、
> 活跃度里程碑宝箱（100/200）、消耗精力作战（勤劳是福 → 6×20=120 精力 → 等级提示确认 → 多波自动战斗 →
> 「挑战完成」退出 → 体力/卡片进度双向校验）。剩余 3 条玩法任务（幸福伊亚、结缘、英雄传奇）目前只识别跳过；
> 改版后的任务完整一次运行待下次前台空闲时复验。

> **前台限制：** 0.75.2 起游戏内 UI 不再接受 PostMessage，运行任务时游戏窗口必须保持前台，脚本会接管鼠标键盘；
> 窗口切到后台会停止抓帧并跳过点击。启动/设备准备阶段仍用 PostMessage，进入游戏后自动切换为 Pynput。

![Python](https://img.shields.io/badge/python-3.12-3776AB)
![Platform](https://img.shields.io/badge/platform-Windows-0078D4)
![ok-script](https://img.shields.io/badge/ok--script-3.0.13-6E4AFF)

## 环境要求

- Windows 10 2004+ / Windows 11（依赖 WGC 采集）
- Python 3.12
- 游戏：崩坏：因缘精灵 PC 版，可执行文件 `NexusAnima.exe`
- 分辨率：16:9，推荐 1920×1080（最低 1280×720）
- 渲染：Direct3D 12

## 快速开始

```powershell
git clone https://github.com/HoshimiMiyabiovo/ok-hna.git
cd ok-hna

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\pip.exe install -r requirements.txt
```

两种启动方式：

| 方式 | 命令 | 用途 |
| --- | --- | --- |
| GUI | `.\.venv\Scripts\python.exe start_gui.py` | 手动选用游戏窗口、调配置、手动跑任务 |
| MCP（无界面） | `.\.venv\Scripts\python.exe start_mcp.py --port 8765` | 供 AI / 外部程序通过 MCP 调用；连接信息落在 `logs/mcp/connection.json` |

首次运行需要在 GUI 里选择一次游戏窗口，`configs/devices.json` 会记录窗口句柄与本机路径（该文件已被忽略，不会提交）。

## 目录结构

```
ok-hna/
├── config.py                 # ok-script 配置入口（游戏名、exe、采集/交互方式、OCR）
├── start_gui.py              # GUI 启动入口
├── start_mcp.py              # MCP 无界面启动入口
├── requirements.txt
├── configs/                  # GUI 与任务配置（多数为运行时生成）
├── tasks/
│   ├── launcher.py           # 启动链路任务：点击开始、登录、主世界 HUD 确认
│   └── daily.py              # 日常活跃：F3 面板扫描每日目标（向左拖动翻页）并领取
├── tests/
│   ├── test_launcher.py      # 用 ok_templates 整图做的回归测试
│   ├── test_daily.py         # 日常活跃面板识别 / 卡片解析 / F3 模板回归
│   └── run_all.py            # 逐模块子进程跑全部测试
├── ok_templates/             # 整图 + coco_annotations.json（模板源）
├── assets/templates/         # generate_templates 生成的特征切片（运行时用）
├── ok_tasks/                 # 自定义脚本任务
├── AGENTS.md                 # 仓库长期约定（运行环境、交互方式、素材与隐私、测试）
├── .agents/skills/           # ok-script 开发规范（模板生成、任务重载、写测试）
├── cache/                    # ONNX 优化缓存（忽略）
├── logs/                     # 运行日志与 MCP 产物（忽略）
└── screenshots/              # 运行时截图（忽略）
```

## 任务开发

> 动手前先读 [AGENTS.md](AGENTS.md)：里面写死了运行环境（管理员权限）、PostMessage 交互、主世界判定口径、素材打码与测试隔离等硬性约定。

- **启动链路**：`tasks/launcher.py` 按「登录页 → 点击开始 → 主世界 HUD 双特征确认」推进，识别失败时回退为「已在游戏中」。客户端弹出「下载完成，需要重启客户端」（热更）时自动 `WM_CLOSE` 优雅关闭并重启 exe，补丁在下次启动生效；连续重启上限 2 次。
- **日常活跃**：`tasks/daily.py` 从主世界按 F3 快捷键打开面板（图标模板 `main_world_f3_menu` 作为兜底），切到左侧「日常活跃」入口；每日目标是横向卡片列表，一屏只露 4 张多一点，任务会先把卡片拖回最左、再向左拖动直到卡片不再变化。可领取卡片没有文字按钮，按奖励文字下方的整条金色按钮带定位；领取后卡片会重排（已完成往右并显示 `已完成`），所以每领一张都重新扫描。活跃度硬校验读取左侧奖章数字，上限 500，满额后以卡片变为不可领取为准；随后领取带红点的 100/200/300/400/500 里程碑宝箱（点宝箱弹「获得奖励」，点空白关闭）。
- **消耗精力作战**：`tasks/daily.py` 在领取之后处理「消耗X精力」这类必须主动做才满的任务：点该卡「前往」进入「勤劳是福」精力商店 → 选一项体力任务（`体力材料` 可选，默认勤劳致富的仙令 20 精力/次）→ 在作战准备界面用模板 `battle_count_plus` 点「+」把挑战次数拉到上限（按目标剩余精力和 `最多战斗次数` 双重封顶）→ 模板 `battle_challenge` 点「挑战」→ 阵容界面（OCR `开始对决` / 模板 `battle_start_duel`）点「开始对决」→ 若弹出「推荐精灵等级…是否确认继续挑战」点「确认」→ 多波 3D 自动战斗（6 次实机约 6 分钟）→ 结算界面「挑战完成」点「退出」回作战准备 → 回日常面板。一场 6 次刚好 120 精力，同时把「赢得任意3场因缘对决」做掉；随后重扫一遍日常目标领取新完成的奖励。每轮都用「体力数字下降」+「卡片进度前进」双向校验，不成立就落截图和全量 OCR 失败。
- **模板资产**：不要手裁运行时截图当模板。整图放 `ok_templates/`，在 `ok_templates/coco_annotations.json` 里用 `CocoTemplateStore` 标注，再调用 `generate_templates` 生成到 `assets/templates/`，代码里用原始名字走 `find_feature` / `find_one`。
- **开发规范**：先读 `.agents/skills/ok-script-develop/SKILL.md`，它会指向 ok-script 自带的 `develop` / `generate-templates` / `write-test` / `reload-tasks` 说明。
- **回归测试**：`python -m tests.run_all`（逐模块子进程运行；ok-script 的 `TaskTestCase` 依赖 Qt 单例，同一进程只能跑一个测试类，直接 `pytest tests` 会因二次初始化失败）。

## MCP 工具

运行 `start_mcp.py` 后可通过 MCP 调用：

`list_skills`、`get_skill`、`list_tasks`、`reload_tasks`、`run_task`、`run_code`、`get_run_status`、`stop_task`、`exit_process`、`screenshot`

其中 `screenshot` 返回目标窗口的最新截图路径，`run_code` 可以直接执行一段 Python 探针（`self` 绑定一个临时 `BaseTask`）。

## 配置说明

`configs/` 下这些文件是**本机运行时状态**，已在 `.gitignore` 中排除：

| 文件 | 内容 |
| --- | --- |
| `devices.json` | 目标窗口句柄、游戏 exe 绝对路径、采集/交互方式 |
| `_ok.json` | 窗口位置与界面状态 |
| `LauncherTask.json` | 启动器路径 |
| `Notification.json` | 通知渠道（Discord / Telegram / 邮件等密钥） |

仓库里不含以上文件，克隆后首次运行由程序自行生成。

## 未包含的内容

`.venv/`（约 395 MB）、`cache/`（ONNX 优化模型）、`logs/`、`screenshots/`、`__pycache__/` 以及上面列出的本机配置。依赖请用 `requirements.txt` 重建。

## 免责声明

本项目仅供个人学习与自动化技术研究。请遵守《崩坏：因缘精灵》用户协议及米哈游相关规定。项目**不包含**内存修改、进程注入、破解或绕过保护机制，仅通过窗口截图与常规输入模拟操作。因使用本工具产生的账号风险、封禁或数据损失由使用者自行承担。游戏当前为测试版本（`0.75.2`），界面改动会导致识别失效，需同步更新模板。

## 致谢

- [ok-script](https://github.com/ok-oldking/ok-script)：任务框架、MCP、模板匹配与 OCR
- [ok-oldking](https://github.com/ok-oldking)：框架作者
