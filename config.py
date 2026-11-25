from pathlib import Path

ROOT = Path(__file__).resolve().parent

version = "0.1.0"

config = {
    "version": version,
    "gui_title": "ok-hna",
    "game_name": "崩坏：因缘精灵",
    "gui": {"type": "qt"},
    "debug": False,
    "custom_tasks": True,
    "config_folder": str(ROOT / "configs"),
    "screenshots_folder": str(ROOT / "screenshots"),
    "ocr": {
        "lib": "onnxocr",
        "auto_simplify": True,
        "params": {
            "use_npu": False,
        },
    },
    "windows": {
        "exe": ["NexusAnima.exe"],
        # 游戏以管理员运行，程序需管理员权限；PostMessage 可后台点击并保持抓帧
        "interaction": ["PostMessage", "Pynput"],
        "capture_method": ["WGC", "BitBlt_RenderFull", "BitBlt"],
        "check_hdr": False,
        "force_no_hdr": False,
        "require_bg": False,
        "start_exe": False,
    },
    "start_timeout": 120,
    "supported_resolution": {
        "ratio": "16:9",
        "min_size": (1280, 720),
    },
    "template_matching": {
        "template_folder": str(ROOT / "assets" / "templates"),
        "default_threshold": 0.8,
    },
    "onetime_tasks": [
        ["tasks.launcher", "LauncherTask"],
        ["tasks.daily", "DailyActivityTask"],
    ],
    "trigger_tasks": [],
    "mcp": {
        "enabled": False,
        "port": 8765,
        "artifact_directory": str(ROOT / "logs" / "mcp"),
    },
}
