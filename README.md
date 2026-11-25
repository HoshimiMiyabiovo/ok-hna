# ok-hna

《崩坏：因缘精灵》（Nexus Anima）的自动化脚本工程，基于 [ok-script](https://github.com/ok-oldking/ok-script) 框架构建。

> **状态：开发中。** 目前只实现了启动链路（启动器 → 点击开始 → 进入游戏并确认 UID），玩法任务待补充。

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
│   └── launcher.py           # 启动链路任务：点击开始、登录、UID 水印确认
├── tests/
│   └── test_launcher.py      # 用 ok_templates 整图做的回归测试
├── ok_templates/             # 整图 + coco_annotations.json（模板源）
├── assets/templates/         # generate_templates 生成的特征切片（运行时用）
├── ok_tasks/                 # 自定义脚本任务
├── .agents/skills/           # ok-script 开发规范（模板生成、任务重载、写测试）
├── cache/                    # ONNX 优化缓存（忽略）
├── logs/                     # 运行日志与 MCP 产物（忽略）
└── screenshots/              # 运行时截图（忽略）
```

## 任务开发

- **启动链路**：`tasks/launcher.py` 按「登录页 → 点击开始 → 读取 UID 水印」推进，识别失败时回退为「已在游戏中」。
- **模板资产**：不要手裁运行时截图当模板。整图放 `ok_templates/`，在 `ok_templates/coco_annotations.json` 里用 `CocoTemplateStore` 标注，再调用 `generate_templates` 生成到 `assets/templates/`，代码里用原始名字走 `find_feature` / `find_one`。
- **开发规范**：先读 `.agents/skills/ok-script-develop/SKILL.md`，它会指向 ok-script 自带的 `develop` / `generate-templates` / `write-test` / `reload-tasks` 说明。
- **回归测试**：`python -m pytest tests`，用 `ok_templates/` 里的整图作为测试夹具。

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
