import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config
from ok.test.TaskTestCase import TaskTestCase
from tasks.launcher import LOGIN_PAGE_PATTERN, LauncherTask


class TestLauncherLoginPage(TaskTestCase):
    task_class = LauncherTask
    config = copy.deepcopy(config)

    @classmethod
    def setUpClass(cls):
        cls.config['gui'] = None
        # 测试运行会保存设备/任务配置，隔离到临时目录避免污染项目 configs
        cls._tmp_config = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp_config.cleanup)
        cls.config['config_folder'] = cls._tmp_config.name
        cls.config['screenshots_folder'] = str(Path(cls._tmp_config.name) / 'screenshots')
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
        self.assertTrue(self.task._is_in_main_world(), '新版主世界画面应同时匹配到背包和 Esc HUD 特征')
        self.assertFalse(self.task.ocr(match=LOGIN_PAGE_PATTERN), '新版主世界不应残留登录页按钮')


if __name__ == '__main__':
    unittest.main()
