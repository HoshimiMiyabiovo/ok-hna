import copy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config
from ok.test.TaskTestCase import TaskTestCase
from tasks.launcher import (GAME_CAPTURE_CONFIG, LAUNCHER_CAPTURE_CONFIG, LOGIN_PAGE_PATTERN,
                            RESTART_REQUIRED_PATTERN, LauncherTask)


class TestLauncherLoginPage(TaskTestCase):
    task_class = LauncherTask
    config = copy.deepcopy(config)

    @classmethod
    def setUpClass(cls):
        cls.config['gui'] = None
        # 测试运行会保存设备/任务配置，隔离到临时目录避免污染项目 configs
        # 本机沙箱禁止删除临时目录里的子目录，tempfile.TemporaryDirectory 的清理会硬报错；
        # 这里用 mkdtemp + 忽略错误的 rmtree，隔离等价但清理失败不算测试失败
        cls._tmp_config = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls._tmp_config, True)
        cls.config['config_folder'] = str(cls._tmp_config)
        cls.config['screenshots_folder'] = str(cls._tmp_config / 'screenshots')
        super().setUpClass()

    def test_start_game_page_detected_as_login(self):
        self.set_image(str(ROOT / 'ok_templates' / 'login_start_game.png'))
        boxes = self.task.ocr(match=LOGIN_PAGE_PATTERN)
        self.assertTrue(boxes, '未识别到「开始游戏」按钮')
        self.assertFalse(self.task._is_in_main_world(), '登录页不应被判定为主世界')

    def test_click_start_page_detected_as_login(self):
        self.set_image(str(ROOT / 'ok_templates' / 'login_click_start.png'))
        boxes = self.task.ocr(match=LOGIN_PAGE_PATTERN)
        self.assertTrue(boxes, '未识别到「点击开始」')
        self.assertFalse(self.task._is_in_main_world(), '登录页不应被判定为主世界')

    def test_cutscene_not_main_world(self):
        self.set_image(str(ROOT / 'ok_templates' / 'in_game_cutscene.png'))
        self.assertFalse(self.task._is_in_main_world(), '过场剧情阶段不应被判定为主世界')
        self.assertFalse(self.task.ocr(match=LOGIN_PAGE_PATTERN), '过场阶段不应识别到登录页按钮')

    def test_updated_main_world_detected_by_hud(self):
        self.set_image(str(ROOT / 'ok_templates' / 'in_game_main_world_updated.png'))
        self.assertTrue(self.task._is_in_main_world(), '旧版主世界画面应同时匹配到背包和 Esc HUD 特征')
        self.assertFalse(self.task.ocr(match=LOGIN_PAGE_PATTERN), '主世界不应残留登录页按钮')

    def test_live_hud_main_world_detected(self):
        self.set_image(str(ROOT / 'ok_templates' / 'in_game_main_world_hud.png'))
        self.assertTrue(self.task._is_in_main_world(), '实机主世界帧应命中背包与 Esc HUD 特征')
        self.assertFalse(self.task.ocr(match=RESTART_REQUIRED_PATTERN), '主世界不应识别到重启提示')

    def test_restart_required_modal_detected(self):
        self.set_image(str(ROOT / 'ok_templates' / 'in_game_restart_required.png'))
        self.assertTrue(self.task._restart_required(), '应识别到「需要重启客户端」提示')
        self.assertFalse(self.task._is_in_main_world(), '重启提示页不是主世界')

    def test_game_uses_foreground_pynput(self):
        # 0.75.2 起游戏内 UI 忽略 PostMessage，必须用前台真实输入
        self.assertEqual(GAME_CAPTURE_CONFIG['windows']['interaction'], 'Pynput')
        self.assertEqual(LAUNCHER_CAPTURE_CONFIG['windows']['interaction'], 'Pynput')


if __name__ == '__main__':
    unittest.main()
