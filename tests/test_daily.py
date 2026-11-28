import copy
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config
from ok.feature.Box import Box
from ok.test.TaskTestCase import TaskTestCase
from tasks.daily import (BATTLE_RESULT_PATTERN, BLANK_CLOSE_PATTERN, BUTTON_LABELS, CONFIRM_PATTERN,
                          DUEL_BUTTON_REGION, DUEL_PATTERN, EXIT_PATTERN, LEVEL_CONFIRM_REGION,
                          LEVEL_WARNING_PATTERN, MILESTONE_CHEST_Y, STAMINA_BATTLE_REGION,
                          STAMINA_CARD_PATTERN, DailyActivityTask)
from tasks.welfare import WelfareTask

PAGE1 = 'in_game_daily_activity_1.png'
PAGE2 = 'in_game_daily_activity_2.png'
PAGE3 = 'in_game_daily_activity_3.png'
DAKA = 'in_game_daily_daka.png'
MAIN_UI = 'in_game_main_world_ui.png'
MAIN_WORLD = 'in_game_main_world_updated.png'
LIVE_HUD = 'in_game_main_world_hud.png'
SHOP_MATERIAL = 'in_game_stamina_shop_material.png'
SHOP_MIND = 'in_game_stamina_shop_mind.png'
BATTLE = 'in_game_battle_prepare.png'
LINEUP = 'in_game_battle_lineup.png'
LEVEL_WARNING = 'in_game_battle_level_warning.png'
RESULT = 'in_game_battle_result.png'
MILESTONE = 'in_game_daily_milestone.png'

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
        # 本机沙箱禁止删除临时目录里的子目录，tempfile.TemporaryDirectory 的清理会硬报错；
        # 这里用 mkdtemp + 忽略错误的 rmtree，隔离等价但清理失败不算测试失败
        cls._tmp_config = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls._tmp_config, True)
        cls.config['config_folder'] = str(cls._tmp_config)
        cls.config['screenshots_folder'] = str(cls._tmp_config / 'screenshots')
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

    def test_activity_cap_read(self):
        self._set(PAGE1)
        self.assertEqual(self.task._read_activity_cap(), 500)

    def test_milestone_labels_read(self):
        self._set(PAGE1)
        values = [value for value, _ in self.task._read_milestones()]
        self.assertEqual(values, [0, 100, 200, 300, 400, 500])

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
        self.assertGreater(login['gold'], 0.5, '领取点应落在整条金色按钮带上')
        self.assertTrue(820 <= login['claim_y'] <= 915, f'领取点必须在金色按钮带内: {login["claim_y"]}')
        self.assertEqual(by_title['在幸福伊亚再出发中收取1次奖励']['button'], '前往')
        self.assertEqual(by_title['赢得任意3场因缘对决']['button'], '进行中')
        self.assertFalse(by_title['赢得任意3场因缘对决']['claimable'])
        self.assertFalse(by_title['结缘1次野生精灵']['claimable'])

    def test_claimable_button_called_done(self):
        self.assertIn('已完成', BUTTON_LABELS, '「已完成」必须作为按钮标签而不是标题')

    def test_claim_at_cap_uses_card_state(self):
        card = {'title': '测试任务', 'reward': 100, 'claim_x': 10, 'claim_y': 20}
        with mock.patch.object(self.task, '_read_activity_cap', return_value=500), \
                mock.patch.object(self.task, '_read_activity_total', return_value=500), \
                mock.patch.object(self.task, '_is_card_claimable', side_effect=[True, False]) as state, \
                mock.patch.object(self.task, 'click') as click, \
                mock.patch.object(self.task, 'sleep'):
            self.assertTrue(self.task._claim_card(card), '满额时卡片变为不可领取即视为领取成功')
        self.assertEqual(click.call_count, 2, '第一次点击后卡片仍可领取，应重试一次')
        self.assertEqual(state.call_count, 2)

    def test_claim_at_cap_fails_when_card_stays_claimable(self):
        from ok import TaskDisabledException
        card = {'title': '测试任务', 'reward': 100, 'claim_x': 10, 'claim_y': 20}
        with mock.patch.object(self.task, '_read_activity_cap', return_value=500), \
                mock.patch.object(self.task, '_read_activity_total', return_value=500), \
                mock.patch.object(self.task, '_is_card_claimable', return_value=True), \
                mock.patch.object(self.task, '_raise_with_evidence',
                                  side_effect=TaskDisabledException('仍可领取')) as raise_evidence, \
                mock.patch.object(self.task, 'click'), \
                mock.patch.object(self.task, 'sleep'):
            with self.assertRaises(TaskDisabledException):
                self.task._claim_card(card)
        raise_evidence.assert_called_once()

    def test_level_warning_and_result_patterns(self):
        self.assertTrue(LEVEL_WARNING_PATTERN.search('推荐精灵等级为10级，当前上阵精灵平均等级为8级，是否确认继续挑战？'))
        self.assertFalse(LEVEL_WARNING_PATTERN.search('推荐精灵等级：10'),
                         '作战准备界面的「推荐精灵等级：10」不是确认弹窗，不能误判')
        self.assertTrue(CONFIRM_PATTERN.search('确认'))
        self.assertFalse(CONFIRM_PATTERN.search('确认挑战'))
        self.assertTrue(BATTLE_RESULT_PATTERN.search('挑战完成'))
        self.assertTrue(EXIT_PATTERN.search('退出'))
        self.assertTrue(BLANK_CLOSE_PATTERN.search('点击任意空白处关闭'))

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

    def test_f3_entry_feature_on_live_hud(self):
        self._set(LIVE_HUD)
        box = self.task.find_one('main_world_f3_menu', threshold=0.9,
                                 horizontal_variance=0.06, vertical_variance=0.02)
        self.assertIsNotNone(box, '实机主世界帧应匹配到 F3 图标')
        self.assertLess(abs(box.x - 1460), 3)
        self.assertLess(abs(box.y - 58), 3)

    def test_f3_entry_feature_found_after_hud_shift(self):
        self._set(MAIN_UI)
        box = self.task.find_one('main_world_f3_menu', threshold=0.8,
                                 horizontal_variance=0.06, vertical_variance=0.02)
        self.assertIsNotNone(box, 'HUD 图标整体左移后仍应通过方差搜索命中 F3')
        self.assertGreater(box.x, 1500)

    def test_f3_entry_feature_absent_on_panel(self):
        self._set(PAGE1)
        self.assertIsNone(
            self.task.find_one('main_world_f3_menu', threshold=0.8,
                               horizontal_variance=0.06, vertical_variance=0.02),
            '面板页面不应匹配到 F3 图标')

    def test_live_hud_is_main_world(self):
        self._set(LIVE_HUD)
        self.assertTrue(self.task._is_in_main_world(), '实机主世界帧应命主世界 HUD 双特征')
        self.assertFalse(self.task._is_daily_panel_open())


    # ---------- 消耗精力作战：勤劳是福 → 作战准备 → 挑战次数最大化 ----------

    def test_stamina_shop_rows_material(self):
        self._set(SHOP_MATERIAL)
        self.assertTrue(self.task._is_stamina_shop_open(), '「勤劳是福」精力商店应被识别')
        self.assertFalse(self.task._is_battle_prepare_open(), '精力商店不是作战界面')
        self.assertEqual(self.task._shop_tab_names(), ['基础材料', '心识领悟'])
        rows = self.task._parse_shop_rows()
        self.assertEqual([r['title'] for r in rows], ['勤劳致富的仙令', '熟能生巧的缘宝', '磨炼心志的砺砂'])
        self.assertEqual({r['cost'] for r in rows}, {20})
        first = rows[0]
        self.assertTrue(first['button_box'].x <= first['click_x'] <= first['button_box'].x + first['button_box'].width,
                        '点击点必须落在「前往」按钮内')
        self.assertLess(abs(first['click_y'] - 261), 3)

    def test_stamina_shop_rows_mind_tab(self):
        self._set(SHOP_MIND)
        rows = self.task._parse_shop_rows()
        self.assertEqual([r['title'] for r in rows], ['炼心', '锻形', '聚意', '凝魂'])
        self.assertEqual({r['cost'] for r in rows}, {40})

    def test_battle_prepare_screen(self):
        self._set(BATTLE)
        self.assertTrue(self.task._is_battle_prepare_open(), '「挑战次数」界面应被识别为作战准备')
        self.assertFalse(self.task._is_level_warning(),
                         '作战准备界面左上角的「推荐精灵等级：10」不能当成等级不足弹窗')
        self.assertFalse(self.task._is_stamina_shop_open())
        self.assertIn('勤劳致富的仙令', self.task._read_battle_header())
        self.assertEqual(self.task._read_battle_cost(), 20, '「挑战」按钮上的精力消耗应可读')
        self.assertEqual(self.task._read_stamina(STAMINA_BATTLE_REGION), (240, 240))
        self.assertIsNotNone(self.task.find_one('battle_challenge', threshold=0.8), '「挑战」按钮模板应命中')
        self.assertIsNotNone(self.task.find_one('battle_count_plus', threshold=0.8), '「+」按钮模板应命中')

    def test_daily_stamina_card_button_box(self):
        self._set(PAGE3)
        cards = {card['title']: card for card in self.task._parse_cards()}
        card = cards['消耗120精力']
        self.assertEqual((card['progress'], card['button'], card['reward']), ('0/120', '前往', 400))
        self.assertFalse(card['claimable'], '0/120 的金色「前往」按钮不是可领取')
        self.assertIsNotNone(card['button_box'])
        self.assertLess(abs(card['claim_x'] - 1207), 3, '「前往」按钮中心 x 应随 OCR 盒子走')
        self.assertLess(abs(card['claim_y'] - 868), 3, '「前往」按钮中心 y 应随 OCR 盒子走')
        self.assertIsNone(self.task.find_one('battle_challenge', threshold=0.8), '日常活跃页不应命中「挑战」模板')

    def test_daily_page_is_not_shop_or_battle(self):
        self._set(PAGE3)
        self.assertFalse(self.task._is_stamina_shop_open())
        self.assertFalse(self.task._is_battle_prepare_open())

    def test_stamina_card_pattern(self):
        self.assertTrue(STAMINA_CARD_PATTERN.search('消耗120精力'))
        self.assertFalse(STAMINA_CARD_PATTERN.search('完成1次英雄传奇'))

    def test_duel_lineup_screen(self):
        self._set(LINEUP)
        self.assertTrue(self.task._is_duel_lineup(), '「开始对决」阵容界面应被识别')
        self.assertFalse(self.task._is_battle_prepare_open(), '阵容界面不是挑战次数界面')
        self.assertFalse(self.task._is_stamina_shop_open())
        self.assertIsNotNone(self.task.find_one('battle_start_duel', threshold=0.8), '「开始对决」模板应命中')
        matches = self.task.ocr(box=self.task.box_of_screen(*DUEL_BUTTON_REGION), match=DUEL_PATTERN)
        self.assertTrue(matches, '底部按钮区应 OCR 出「开始对决」')
        self.assertLess(abs(matches[0].x - 1761), 3)
        self.assertLess(abs(matches[0].y - 1031), 3)

    def test_duel_lineup_absent_elsewhere(self):
        for name in (BATTLE, PAGE3, SHOP_MATERIAL):
            self._set(name)
            self.assertFalse(self.task._is_duel_lineup(), f'{name} 不应识别成阵容界面')
            self.assertIsNone(self.task.find_one('battle_start_duel', threshold=0.8),
                              f'{name} 不应命中「开始对决」模板')

    def test_level_warning_screen(self):
        self._set(LEVEL_WARNING)
        self.assertTrue(self.task._is_level_warning(), '实机等级不足弹窗应被识别')
        matches = self.task.ocr(box=self.task.box_of_screen(*LEVEL_CONFIRM_REGION), match=CONFIRM_PATTERN)
        self.assertTrue(matches, '等级提示弹窗内应能 OCR 到「确认」按钮')
        self.assertFalse(self.task._is_daily_panel_open())
        self.assertFalse(self.task._is_battle_prepare_open())
        self.assertFalse(self.task._is_in_main_world())

    def test_battle_result_screen(self):
        self._set(RESULT)
        self.assertTrue(self.task._is_battle_result(), '实机「挑战完成」结算界面应被识别')
        self.assertTrue(self.task.ocr(match=EXIT_PATTERN), '结算界面应能 OCR 到「退出」')
        self.assertFalse(self.task._is_daily_panel_open())
        self.assertFalse(self.task._is_stamina_shop_open())
        self.assertFalse(self.task._is_battle_prepare_open())
        self.assertFalse(self.task._is_duel_lineup())
        self.assertFalse(self.task._is_in_main_world())

    def test_daily_milestone_badges(self):
        self._set(MILESTONE)
        self.assertEqual(self.task._read_activity_total(), 500)
        x_by_value = dict(self.task._read_milestones())
        self.assertEqual(sorted(x_by_value), [0, 100, 200, 300, 400, 500])
        chest_y = int(self.task.height * MILESTONE_CHEST_Y)
        self.assertFalse(self.task._milestone_claimable(x_by_value[100], chest_y), '100 档已领取')
        for value in (200, 300, 400, 500):
            self.assertTrue(self.task._milestone_claimable(x_by_value[value], chest_y),
                            f'{value} 档带红点应判定为可领取')

    def test_start_duel_clicks_button(self):
        self._set(LINEUP)
        with mock.patch.object(self.task, 'click') as click, mock.patch.object(self.task, 'screenshot') as shot:
            self.task._start_duel(timeout=2)
        self.assertEqual(click.call_count, 1, '阵容界面应点一次「开始对决」')
        box = click.call_args.args[0]
        self.assertLess(abs(box.x - 1752), 3)
        self.assertLess(abs(box.y - 1024), 3)
        shot.assert_called_once()

    def test_new_templates_hide_account_uid(self):
        for name in (PAGE3, SHOP_MATERIAL, SHOP_MIND, BATTLE, LINEUP, LEVEL_WARNING, RESULT, MILESTONE):
            self._set(name)
            texts = [box.name for box in self.task.ocr(box=self.task.box_of_screen(0, 0.93, 1, 1.0))]
            self.assertFalse([text for text in texts if 'UID' in text.upper()], f'{name} 底栏仍能读出 UID: {texts}')
            self.assertFalse([text for text in texts if re.search(r'\d{6,}', text)], f'{name} 底栏仍能读出长数字: {texts}')

    def test_maximize_battle_count_stops_at_goal_budget(self):
        costs = [20, 40, 60, 80, 100, 120]
        with mock.patch.object(self.task, 'find_one', return_value=Box(1812, 895, 66, 66)), \
                mock.patch.object(self.task, '_read_battle_cost', side_effect=costs), \
                mock.patch.object(self.task, 'click') as click:
            self.assertEqual(self.task._maximize_battle_count(20, 0, 120), 120)
            self.assertEqual(click.call_count, 5, '20→120 只需点 5 次「+」')

    def test_maximize_battle_count_stops_when_capped(self):
        costs = [120, 120]
        with mock.patch.object(self.task, 'find_one', return_value=Box(1812, 895, 66, 66)), \
                mock.patch.object(self.task, '_read_battle_cost', side_effect=costs), \
                mock.patch.object(self.task, 'click') as click:
            self.assertEqual(self.task._maximize_battle_count(None, 0, 120), 120)
            self.assertEqual(click.call_count, 1, '消耗数字不再增长即视为已到上限')

    def test_stamina_round_skipped_when_goal_done(self):
        card = {'title': '消耗120精力', 'progress': '120/120', 'button': None, 'button_box': None}
        with mock.patch.object(self.task, '_find_stamina_card', return_value=card):
            self.assertFalse(self.task._run_stamina_battles(), '目标已完成时不应开战')

    def test_stamina_round_skipped_when_disabled(self):
        self.task.config['消耗精力作战'] = False
        try:
            with mock.patch.object(self.task, '_find_stamina_card', side_effect=AssertionError('不应查找卡片')):
                self.assertFalse(self.task._run_stamina_battles())
        finally:
            self.task.config['消耗精力作战'] = True

    # ---------- 领取前重新定位：扫描停在列表末尾，旧坐标会点到别的卡 ----------

    def test_locate_card_finds_visible_card(self):
        self._set(PAGE2)
        with mock.patch.object(self.task, '_rewind_cards'), \
                mock.patch.object(self.task, '_drag_cards_left') as drag:
            card = self.task._locate_card('消耗120精力')
        self.assertIsNotNone(card, '当前屏已有的卡片应直接定位到')
        self.assertEqual(card['progress'], '0/120')
        self.assertEqual(card['button'], '前往')
        drag.assert_not_called()

    def test_locate_card_pages_until_found(self):
        page1_cards = [{'title': '登录游戏', 'progress': '1/1', 'claimable': True}]
        page2_cards = [{'title': '消耗120精力', 'progress': '0/120', 'claimable': False}]
        with mock.patch.object(self.task, '_rewind_cards'), \
                mock.patch.object(self.task, 'next_frame'), \
                mock.patch.object(self.task, '_parse_cards', side_effect=[page1_cards, page2_cards]), \
                mock.patch.object(self.task, '_drag_cards_left') as drag:
            card = self.task._locate_card('消耗120精力')
        self.assertEqual(card, page2_cards[0], '第一屏没有时应左拖后在第二屏定位到')
        self.assertEqual(drag.call_count, 1)

    def test_locate_card_returns_none_when_missing(self):
        with mock.patch.object(self.task, '_rewind_cards'), \
                mock.patch.object(self.task, 'next_frame'), \
                mock.patch.object(self.task, '_parse_cards', return_value=[]), \
                mock.patch.object(self.task, '_drag_cards_left'):
            self.assertIsNone(self.task._locate_card('不存在任务'))

    def test_scan_claim_uses_fresh_card_coordinates(self):
        stale = {'title': '登录游戏', 'progress': '1/1', 'reward': 100, 'claimable': True,
                 'claim_x': 488, 'claim_y': 866, 'button': None}
        fresh = dict(stale, claim_x=1490, claim_y=870)
        with mock.patch.object(self.task, '_read_activity_total', return_value=0), \
                mock.patch.object(self.task, '_rewind_cards'), \
                mock.patch.object(self.task, '_scan_pages',
                                  side_effect=[[stale], [dict(stale, claimable=False)]]) as scan, \
                mock.patch.object(self.task, '_locate_card', return_value=fresh) as locate, \
                mock.patch.object(self.task, '_claim_card') as claim:
            self.task._scan_and_claim()
        self.assertEqual(scan.call_count, 2, '领取后应重新扫描确认没有剩余可领取')
        locate.assert_called_once_with('登录游戏')
        claim.assert_called_once_with(fresh)
        self.assertEqual(claim.call_args.args[0]['claim_x'], 1490, '必须点击回拖后重新定位的坐标')

    def test_scan_claim_fails_when_claimable_card_lost(self):
        from ok import TaskDisabledException
        stale = {'title': '登录游戏', 'progress': '1/1', 'reward': 100, 'claimable': True,
                 'claim_x': 488, 'claim_y': 866, 'button': None}
        with mock.patch.object(self.task, '_read_activity_total', return_value=0), \
                mock.patch.object(self.task, '_rewind_cards'), \
                mock.patch.object(self.task, '_scan_pages', return_value=[stale]), \
                mock.patch.object(self.task, '_locate_card', return_value=None), \
                mock.patch.object(self.task, '_claim_card') as claim, \
                mock.patch.object(self.task, '_raise_with_evidence',
                                  side_effect=TaskDisabledException('找不到卡片')):
            with self.assertRaises(TaskDisabledException):
                self.task._scan_and_claim()
        claim.assert_not_called()

    # ---------- 一条龙收尾：日常 → 帮会助力战令 + 邮件 ----------

    def test_daily_run_chains_welfare_after_panel_closed(self):
        welfare = mock.Mock()
        calls = mock.Mock()
        self.task.config['日常后领取福利'] = True
        try:
            with mock.patch('tasks.daily.is_admin', return_value=True), \
                    mock.patch.object(self.task.executor.device_manager, 'hwnd_window') as hwnd, \
                    mock.patch.object(self.task, '_ensure_in_main_world') as ensure, \
                    mock.patch.object(self.task, '_open_daily_panel') as open_panel, \
                    mock.patch.object(self.task, '_scan_and_claim') as scan, \
                    mock.patch.object(self.task, '_claim_milestones') as milestones, \
                    mock.patch.object(self.task, '_run_stamina_battles', return_value=False) as battle, \
                    mock.patch.object(self.task, '_close_panel') as close, \
                    mock.patch.object(self.task, 'get_task_by_class', return_value=welfare) as get_task:
                calls.attach_mock(hwnd.bring_to_front, 'focus')
                calls.attach_mock(ensure, 'ensure')
                calls.attach_mock(open_panel, 'open')
                calls.attach_mock(scan, 'scan')
                calls.attach_mock(milestones, 'milestones')
                calls.attach_mock(battle, 'battle')
                calls.attach_mock(close, 'close')
                calls.attach_mock(get_task, 'get_task')
                calls.attach_mock(welfare.run, 'welfare_run')
                self.task.run()
            self.assertEqual(calls.mock_calls, [
                mock.call.focus(), mock.call.ensure(), mock.call.open(), mock.call.scan(),
                mock.call.milestones(), mock.call.battle(), mock.call.close(),
                mock.call.get_task(WelfareTask), mock.call.welfare_run(),
            ], '必须先关闭日常面板并回到主世界，再启动福利领取')
        finally:
            self.task.config['日常后领取福利'] = True

    def test_welfare_after_daily_skips_when_disabled(self):
        self.task.config['日常后领取福利'] = False
        try:
            with mock.patch.object(self.task, 'get_task_by_class') as get_task:
                self.task._claim_welfare_after_daily()
            get_task.assert_not_called()
        finally:
            self.task.config['日常后领取福利'] = True

    def test_welfare_after_daily_requires_registration(self):
        from ok import TaskDisabledException
        with mock.patch.object(self.task, 'get_task_by_class', return_value=None):
            with self.assertRaises(TaskDisabledException):
                self.task._claim_welfare_after_daily()


if __name__ == '__main__':
    unittest.main()
