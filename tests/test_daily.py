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
from tasks.daily import DailyActivityTask

PAGE1 = 'in_game_daily_activity_1.png'
PAGE2 = 'in_game_daily_activity_2.png'
DAKA = 'in_game_daily_daka.png'
MAIN_UI = 'in_game_main_world_ui.png'
MAIN_WORLD = 'in_game_main_world_updated.png'

PAGE1_TITLES = {
    '登录游戏',
    '在幸福伊亚再出发中收取1次奖励',
    '赢得任意3场因缘对决',
    '结缘1次野生精灵',
}
PAGE2_TITLES = {
    '赢得任意3场因缘对决',
    '结缘1次野生精灵',
    '消耗120精力',
    '完成1次英雄传奇',
}


class TestDailyActivity(TaskTestCase):
    task_class = DailyActivityTask
    config = copy.deepcopy(config)

    @classmethod
    def setUpClass(cls):
        cls.config['gui'] = None
        cls._tmp_config = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp_config.cleanup)
        cls.config['config_folder'] = cls._tmp_config.name
        cls.config['screenshots_folder'] = str(Path(cls._tmp_config.name) / 'screenshots')
        super().setUpClass()

    def _set(self, name):
        self.set_image(str(ROOT / 'ok_templates' / name))

    def test_daily_page_detected_as_panel_and_tab(self):
        self._set(PAGE1)
        self.assertTrue(self.task._is_daily_panel_open(), '第1屏应识别为 F3 面板')
        self.assertTrue(self.task._is_daily_tab(), '第1屏应识别为日常活跃签页')

    def test_daka_page_is_panel_but_not_daily_tab(self):
        self._set(DAKA)
        self.assertTrue(self.task._is_daily_panel_open(), '打卡项目页应识别为 F3 面板')
        self.assertFalse(self.task._is_daily_tab(), '打卡项目页不是日常活跃签页')

    def test_main_world_is_not_panel(self):
        self._set(MAIN_WORLD)
        self.assertFalse(self.task._is_daily_panel_open(), '主世界不应识别为面板')
        self.assertFalse(self.task._is_daily_tab(), '主世界不应识别为日常活跃签页')
        self.assertTrue(self.task._is_in_main_world(), '主世界 HUD 特征应命中')

    def test_activity_total_read(self):
        self._set(PAGE1)
        self.assertEqual(self.task._read_activity_total(), 0)

    def test_parse_page1_cards(self):
        self._set(PAGE1)
        cards = self.task._parse_cards()
        self.assertEqual(len(cards), 4, [c['title'] for c in cards])
        self.assertEqual({c['title'] for c in cards}, PAGE1_TITLES)
        by_title = {c['title']: c for c in cards}
        login = by_title['登录游戏']
        self.assertEqual(login['progress'], '1/1')
        self.assertEqual(login['reward'], 100)
        self.assertIsNone(login['button'])
        self.assertTrue(login['claimable'], '1/1 且金色底栏应判定为可领取')
        self.assertEqual(by_title['在幸福伊亚再出发中收取1次奖励']['button'], '前往')
        self.assertEqual(by_title['赢得任意3场因缘对决']['button'], '进行中')
        self.assertFalse(by_title['赢得任意3场因缘对决']['claimable'])
        self.assertFalse(by_title['结缘1次野生精灵']['claimable'])

    def test_parse_page2_cards(self):
        self._set(PAGE2)
        cards = self.task._parse_cards()
        self.assertEqual(len(cards), 4, [c['title'] for c in cards])
        self.assertEqual({c['title'] for c in cards}, PAGE2_TITLES)
        by_title = {c['title']: c for c in cards}
        self.assertEqual(by_title['消耗120精力']['progress'], '0/120')
        self.assertEqual(by_title['消耗120精力']['reward'], 400)
        self.assertEqual(by_title['完成1次英雄传奇']['button'], '前往')
        self.assertFalse(any(c['claimable'] for c in cards), '第2屏没有可领取卡片')

    def test_drag_pages_cover_all_six_tasks(self):
        self._set(PAGE1)
        first = {c['title'] for c in self.task._parse_cards()}
        self._set(PAGE2)
        second = {c['title'] for c in self.task._parse_cards()}
        self.assertEqual(len(first | second), 6, first | second)
        self.assertEqual(len(first & second), 2, '两屏应有两张重叠卡片用于对齐翻页')

    def test_f3_entry_feature_on_main_world(self):
        self._set(MAIN_UI)
        box = self.task.find_one('main_world_f3_menu', threshold=0.9)
        self.assertIsNotNone(box, '主世界截图应匹配到 F3 图标')
        self.assertLess(abs(box.x - 1561), 2)
        self.assertLess(abs(box.y - 37), 2)

    def test_f3_entry_feature_absent_on_panel(self):
        self._set(PAGE1)
        self.assertIsNone(self.task.find_one('main_world_f3_menu', threshold=0.8), '面板页面不应匹配到 F3 图标')


if __name__ == '__main__':
    unittest.main()
