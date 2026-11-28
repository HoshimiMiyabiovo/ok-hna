import os
import re
import time

import psutil
import win32gui
from ok import BaseTask, TaskDisabledException, og
from ok.util.process import execute, is_admin

GAME_EXE = "NexusAnima.exe"
LAUNCHER_EXE = "launcher.exe"
DEFAULT_LAUNCHER_PATH = r"H:\Program Files\Game\Nexus Anima\launcher.exe"

LOGIN_PAGE_PATTERN = re.compile(r"开始游戏|点击开始")
RESTART_REQUIRED_PATTERN = re.compile(r"需要重启客户端|重启客户端")
MAIN_WORLD_FEATURES = ("main_world_bag", "main_world_esc_badge")
MAIN_WORLD_THRESHOLD = 0.70
MAX_CLIENT_RESTARTS = 2
WM_CLOSE = 0x0010

GAME_CAPTURE_CONFIG = {
    "windows": {
        "exe": GAME_EXE,
        # ensure_capture 的 interaction 只接受字符串（传列表会破坏 interacting 类解析）；
        # 0.75.2 起游戏内 UI 忽略 PostMessage 注入，必须用 Pynput 真实输入；
        # Pynput 要求窗口前台（on_run 会自动切前台），后台状态下不会点击也不会抓帧
        "interaction": "Pynput",
        "capture_method": ["WGC", "BitBlt_RenderFull", "BitBlt"],
    }
}

LAUNCHER_CAPTURE_CONFIG = {
    "windows": {
        "exe": LAUNCHER_EXE,
        # 启动器同样走真实点击，保证与游戏内交互方式一致
        "interaction": "Pynput",
        "capture_method": ["WGC", "BitBlt_RenderFull", "BitBlt"],
    }
}


class LauncherTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "启动游戏"
        self.description = "启动启动器并进入游戏：点击启动器与游戏登录页的开始按钮，确认进入主世界"
        self.default_config.update({"Launcher Path": DEFAULT_LAUNCHER_PATH})
        self._restart_count = 0

    def run(self):
        if not is_admin():
            raise TaskDisabledException(
                "游戏进程以管理员权限运行，本程序必须以管理员身份启动才能操作游戏窗口（右键程序 → 以管理员身份运行）")
        self._restart_count = 0
        if self._find_process(GAME_EXE):
            self.log_info("游戏已在运行，直接切换到游戏窗口")
            self._attach_game()
            self._enter_game(already_running=True)
            return

        self._start_launcher()
        if not self._wait_process(LAUNCHER_EXE, 120):
            raise TaskDisabledException("等待启动器进程超时")
        self._ensure_capture(LAUNCHER_CAPTURE_CONFIG)
        self._click_start()

        self.log_info("等待游戏进程启动")
        if not self._wait_process(GAME_EXE, 600):
            raise TaskDisabledException("等待游戏进程超时，请确认启动器已登录且没有卡在更新")
        self._attach_game()
        self._enter_game()

    def _attach_game(self):
        self._ensure_capture(GAME_CAPTURE_CONFIG)
        # Pynput 只在前台抓帧/点击，切完截图目标立刻把游戏窗口切到前台
        self.hwnd.bring_to_front()
        self._wait_connection()
        error = og.app.start_controller.check_resolution()
        if error:
            raise TaskDisabledException(error)
        self.log_info("游戏截图已就绪")

    def _enter_game(self, already_running=False):
        deadline = time.time() + (60 if already_running else 300)
        # Pynput 只在前台点击/抓帧，先把游戏窗口切到前台
        self.hwnd.bring_to_front()
        while time.time() < deadline:
            self.next_frame()
            if self._is_in_main_world():
                self.log_info("已进入主世界（HUD 特征已确认）")
                return
            if self._restart_required():
                self._restart_game_client()
                return self._enter_game(already_running=True)
            if self.ocr(match=LOGIN_PAGE_PATTERN):
                self._click_login_until_ingame()
                return
            self.sleep(1)
        self._raise_enter_game_failed("等待登录页或主世界界面超时")

    def _click_login_until_ingame(self, timeout=600):
        deadline = time.time() + timeout
        last_click = 0.0
        while time.time() < deadline:
            self.next_frame()
            if self._is_in_main_world():
                self.log_info("已进入主世界（HUD 特征已确认）")
                return
            if self._restart_required():
                self._restart_game_client()
                return self._click_login_until_ingame(timeout=timeout)
            boxes = self.ocr(match=LOGIN_PAGE_PATTERN)
            if boxes and time.time() - last_click >= 3:
                if not self.hwnd.is_foreground():
                    self.log_info("将游戏窗口切换到前台")
                    self.hwnd.bring_to_front()
                    self.sleep(0.5)
                box = boxes[0]
                self.log_info(f"点击登录页按钮: {box.name} {box}")
                self.click(box, after_sleep=1.5)
                last_click = time.time()
            else:
                self.sleep(1)
        self._raise_enter_game_failed("点击登录页按钮后未确认进入主世界")

    def _is_in_main_world(self):
        return all(self.find_one(name, threshold=MAIN_WORLD_THRESHOLD) for name in MAIN_WORLD_FEATURES)

    def _restart_required(self):
        return bool(self.ocr(match=RESTART_REQUIRED_PATTERN))

    def _restart_game_client(self):
        if self._restart_count >= MAX_CLIENT_RESTARTS:
            self._raise_enter_game_failed(
                f"客户端已连续 {self._restart_count} 次要求重启应用更新，放弃重试")
        self._restart_count += 1
        self.screenshot("client_restart_required")
        self.ocr(log=True)
        process = self._find_process(GAME_EXE)
        if process is None:
            raise TaskDisabledException("客户端要求重启，但找不到游戏进程")
        try:
            exe_path = process.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            raise TaskDisabledException(f"客户端要求重启，但读取游戏路径失败: {exc}")
        self.log_info(f"客户端提示需要重启应用更新，关闭并重启: {exe_path}")
        self._close_game_window()
        if not self._wait_process_gone(GAME_EXE, 20):
            process = self._find_process(GAME_EXE)
            if process is not None:
                process.terminate()
            if not self._wait_process_gone(GAME_EXE, 15):
                raise TaskDisabledException("关闭游戏进程失败，无法应用客户端更新")
        if not execute(exe_path):
            raise TaskDisabledException(f"重启游戏失败: {exe_path}")
        if not self._wait_process(GAME_EXE, 180):
            raise TaskDisabledException("等待游戏重启进程超时")
        self._attach_game()
        self.log_info("客户端已重启，继续进入游戏")

    def _close_game_window(self):
        hwnd = getattr(self.hwnd, "hwnd", None)
        if hwnd:
            self.log_info("发送 WM_CLOSE 关闭游戏窗口")
            try:
                win32gui.PostMessage(hwnd, WM_CLOSE, 0, 0)
            except Exception as exc:
                self.log_info(f"WM_CLOSE 发送失败: {exc}")
        self.sleep(2)

    def _wait_process_gone(self, exe_name, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._find_process(exe_name):
                return True
            self.sleep(1)
        return False

    def _raise_enter_game_failed(self, reason):
        self.screenshot("enter_game_failed")
        self.ocr(log=True)
        raise TaskDisabledException(f"{reason}，已保存截图与当前全量 OCR 文本，请检查是否有新弹窗、更新提示或网络异常")

    def _start_launcher(self):
        if self._find_process(LAUNCHER_EXE):
            self.log_info("启动器已在运行")
            return
        launcher_path = self.config.get("Launcher Path") or DEFAULT_LAUNCHER_PATH
        if not os.path.isfile(launcher_path):
            raise TaskDisabledException(f"启动器路径不存在: {launcher_path}")
        self.log_info(f"启动启动器: {launcher_path}")
        if not execute(launcher_path):
            raise TaskDisabledException(f"启动器启动失败: {launcher_path}")

    def _click_start(self, timeout=180):
        self.log_info("在启动器中查找「开始游戏」按钮")
        self.hwnd.bring_to_front()
        start = time.time()
        while time.time() - start < timeout:
            self.next_frame()
            boxes = self.ocr(match=["开始游戏", "进入游戏"], log=True)
            if boxes:
                box = max(boxes, key=lambda b: b.y)
                self.log_info(f"点击启动器按钮: {box.name} {box}")
                self.click(box, after_sleep=2)
                return
            update = self.ocr(match=["更新"], box=self.box_of_screen(0.55, 0.7, 1.0, 1.0), log=True)
            if update:
                raise TaskDisabledException("启动器需要更新游戏，请先完成更新后再运行")
            self.sleep(1)
        raise TaskDisabledException("启动器未找到「开始游戏」按钮，可能未登录或界面有变化")

    def _find_process(self, exe_name):
        for process in psutil.process_iter(["name"]):
            try:
                if (process.info["name"] or "").lower() == exe_name.lower():
                    return process
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def _wait_process(self, exe_name, timeout):
        start = time.time()
        while time.time() - start < timeout:
            if self._find_process(exe_name):
                return True
            self.sleep(2)
        return False

    def _ensure_capture(self, capture_config, timeout=120):
        last_error = None
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.log_info(f"切换截图目标: {capture_config['windows']['exe']}")
                self.executor.device_manager.ensure_capture(capture_config)
                return
            except Exception as e:
                last_error = e
                self.log_info(f"切换截图目标失败，重试中: {e}")
                self.sleep(2)
        raise TaskDisabledException(f"无法切换到目标窗口: {last_error}")

    def _wait_connection(self, timeout=30):
        start = time.time()
        while time.time() - start < timeout:
            if self.executor.connected():
                return
            self.executor.device_manager.refresh()
            self.sleep(2)
        raise TaskDisabledException("游戏截图连接超时")
