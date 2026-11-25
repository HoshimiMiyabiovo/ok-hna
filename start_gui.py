import copy
import ctypes
import multiprocessing
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = ROOT / "logs" / "start_gui.log"
if sys.stdout is None or sys.stderr is None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    stream = open(LOG, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def ensure_admin():
    """游戏以管理员运行，非管理员无法点击/截图游戏窗口，启动时自动请求提权。"""
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except Exception:
        return
    script = str(Path(__file__).resolve())
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}"', str(ROOT), 1)
    if ret <= 32:
        raise SystemExit("需要管理员权限才能操作游戏窗口，请在 UAC 弹窗中允许")
    raise SystemExit(0)


def main():
    from config import config

    app_config = copy.deepcopy(config)
    app_config.setdefault("mcp", {})["enabled"] = False

    import ok

    ok.OK(app_config).start()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    ensure_admin()
    main()
