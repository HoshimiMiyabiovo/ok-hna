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
from tasks.welfare import (GUILD_CLAIM_PATTERN, GUILD_CLAIM_REGION, MAIL_CLAIM_PATTERN,
                           MAIL_CLAIM_REGION, WelfareTask)

BATTLE_PASS = 'in_game_battle_pass.png'
BATTLE_PASS_CLAIMED = 'in_game_battle_pass_claimed.png'
GUILD_MISSION = 'in_game_guild_mission.png'
MAIL = 'in_game_mail.png'
MAIN_WORLD = 'in_game_main_world_updated.png'


class TestWelfare(TaskTestCase):
    task_class = WelfareTask
    config = copy.deepcopy(config)

    @classmethod
    def setUpClass(cls):
        cls.config['gui'] = None
        cls._tmp_config = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls._tmp_config, True)
        cls.config['config_folder'] = str(cls._tmp_config)
        cls.config['screenshots_folder'] = str(cls._tmp_config / 'screenshots')
        super().setUpClass()

    def _set(self, name):
        self.set_image(str(ROOT / 'ok_templates' / name))

    def test_battle_pass_panel_detected(self):
        self._set(BATTLE_PASS)
        self.assertTrue(self.task._is_battle_pass_open(), '实机帮会助力帧应识别为战令面板')
        self.assertFalse(self.task._is_mail_open())
        self.assertFalse(self.task._is_in_main_world())

    def test_claimed_battle_pass_panel_still_detected(self):
        self._set(BATTLE_PASS_CLAIMED)
        self.assertTrue(self.task._is_battle_pass_open(), '领取后仍停留在帮会助力面板')

    def test_claim_all_button_only_when_claimable(self):
        self._set(BATTLE_PASS)
        self.assertIsNotNone(self.task._guild_claim_button(), '奖励页有奖励可领时右下应有「一键领取」')
        self._set(BATTLE_PASS_CLAIMED)
        self.assertIsNone(self.task._guild_claim_button(), '领取后「一键领取」按钮应消失')
        self._set(GUILD_MISSION)
        self.assertIsNotNone(self.task._guild_claim_button(), '任务页有可领奖励时右下应有「一键领取」')

    def test_guild_sub_tabs_detected(self):
        self._set(BATTLE_PASS)
        self.assertTrue(self.task._is_guild_pass_tab(), '奖励页应 OCR 到「前行礼遇」')
        self.assertFalse(self.task._is_guild_mission_tab(), '奖励页不是任务页')
        self._set(GUILD_MISSION)
        self.assertTrue(self.task._is_guild_mission_tab(), '任务页应 OCR 到「本周任务/本期任务」')
        self.assertFalse(self.task._is_guild_pass_tab(), '任务页不是奖励页')
        self.assertTrue(self.task._is_battle_pass_open(), '两个子页都属于帮会助力面板')
        for name in (MAIL, MAIN_WORLD):
            self._set(name)
            self.assertFalse(self.task._is_guild_pass_tab(), f'{name} 不应识别为奖励页')
            self.assertFalse(self.task._is_guild_mission_tab(), f'{name} 不应识别为任务页')

    def test_guild_claim_pattern_region_matches_both_tabs(self):
        for name in (BATTLE_PASS, GUILD_MISSION):
            self._set(name)
            boxes = self.task.ocr(box=self.task.box_of_screen(*GUILD_CLAIM_REGION), match=GUILD_CLAIM_PATTERN)
            self.assertTrue(boxes, f'{name} 右下应能 OCR 到「一键领取」')

    def test_battle_pass_not_detected_elsewhere(self):
        for name in (MAIL, MAIN_WORLD):
            self._set(name)
            self.assertFalse(self.task._is_battle_pass_open(), f'{name} 不应识别为帮会助力面板')

    def test_mail_panel_detected(self):
        self._set(MAIL)
        self.assertTrue(self.task._is_mail_open(), '实机邮件帧应识别为邮件面板')
        self.assertFalse(self.task._is_battle_pass_open())
        self.assertFalse(self.task._is_menu_open())
        boxes = self.task.ocr(box=self.task.box_of_screen(*MAIL_CLAIM_REGION), match=MAIL_CLAIM_PATTERN)
        self.assertTrue(boxes, '邮件面板底部应有「全部领取」按钮（禁用态也带文字）')

    def test_mail_fixture_has_no_red_badge(self):
        self._set(MAIL)
        self.assertFalse(self.task._mail_has_red_badge(), '当日 4 封邮件附件均不可领，列表不应有红点')

    def test_battle_pass_claims_both_tabs_in_rounds(self):
        with mock.patch.object(self.task, 'send_key'), \
                mock.patch.object(self.task, '_wait_until', return_value=True), \
                mock.patch.object(self.task, '_claim_guild_pass_rewards',
                                  side_effect=[True, False]) as claim_pass, \
                mock.patch.object(self.task, '_claim_guild_mission_rewards',
                                  side_effect=[True, False]) as claim_mission, \
                mock.patch.object(self.task, '_close_battle_pass') as close:
            self.task._claim_battle_pass()
        self.assertEqual(claim_pass.call_count, 2, '第一轮领完任务页升级后，第二轮应回头再查奖励页')
        self.assertEqual(claim_mission.call_count, 2)
        close.assert_called_once()

    def test_battle_pass_skips_without_button(self):
        with mock.patch.object(self.task, 'send_key'), \
                mock.patch.object(self.task, '_wait_until', return_value=True), \
                mock.patch.object(self.task, '_claim_guild_pass_rewards', return_value=False), \
                mock.patch.object(self.task, '_claim_guild_mission_rewards', return_value=False), \
                mock.patch.object(self.task, '_close_battle_pass') as close:
            self.task._claim_battle_pass()
        close.assert_called_once()

    def test_guild_pass_tab_claim_flow(self):
        claim_box = Box(1438, 892, 105, 32, name='一键领取')
        with mock.patch.object(self.task, '_click_guild_rail'), \
                mock.patch.object(self.task, '_wait_until', return_value=True), \
                mock.patch.object(self.task, '_guild_claim_button', side_effect=[claim_box, None]), \
                mock.patch.object(self.task, 'click') as click, \
                mock.patch.object(self.task, 'screenshot'), \
                mock.patch.object(self.task, '_close_reward_popup') as close_popup:
            self.assertTrue(self.task._claim_guild_pass_rewards())
        self.assertEqual((click.call_args.args[0].x, click.call_args.args[0].y), (1438, 892))
        close_popup.assert_called_once()

    def test_guild_mission_claim_flow_requires_button_gone(self):
        claim_box = Box(1750, 890, 100, 30, name='一键领取')
        with mock.patch.object(self.task, '_click_guild_rail'), \
                mock.patch.object(self.task, '_wait_until', side_effect=[True, False]), \
                mock.patch.object(self.task, '_guild_claim_button', side_effect=[claim_box, None]), \
                mock.patch.object(self.task, 'click'), \
                mock.patch.object(self.task, 'screenshot'), \
                mock.patch.object(self.task, 'next_frame'), \
                mock.patch.object(self.task, 'sleep'):
            self.assertTrue(self.task._claim_guild_mission_rewards(), '任务页以按钮消失判定领取成功')

    def test_guild_mission_claim_fails_when_button_stays(self):
        from ok import TaskDisabledException
        claim_box = Box(1750, 890, 100, 30, name='一键领取')
        with mock.patch.object(self.task, '_click_guild_rail'), \
                mock.patch.object(self.task, '_wait_until', side_effect=[True, False]), \
                mock.patch.object(self.task, '_guild_claim_button', return_value=claim_box), \
                mock.patch.object(self.task, 'click'), \
                mock.patch.object(self.task, 'screenshot'), \
                mock.patch.object(self.task, 'next_frame'), \
                mock.patch.object(self.task, 'sleep'), \
                mock.patch.object(self.task, '_raise_with_evidence',
                                  side_effect=TaskDisabledException('按钮还在')):
            with self.assertRaises(TaskDisabledException):
                self.task._claim_guild_mission_rewards()

    def test_claim_mail_skips_when_disabled(self):
        with mock.patch.object(self.task, 'send_key'), \
                mock.patch.object(self.task, '_wait_until', side_effect=[True, True, False]), \
                mock.patch.object(self.task, '_mail_has_red_badge', return_value=False), \
                mock.patch.object(self.task, 'ocr', return_value=[Box(350, 1004, 102, 27)]), \
                mock.patch.object(self.task, 'click') as click, \
                mock.patch.object(self.task, '_close_mail') as close:
            self.task._claim_mail()
        self.assertEqual(click.call_count, 2, '先点邮件入口，再点一次「全部领取」确认无反应')
        self.assertEqual((click.call_args_list[1].args[0].x, click.call_args_list[1].args[0].y), (350, 1004))
        close.assert_called_once()

    def test_claim_mail_fails_when_red_badge_but_no_popup(self):
        from ok import TaskDisabledException
        with mock.patch.object(self.task, 'send_key'), \
                mock.patch.object(self.task, '_wait_until', side_effect=[True, True, False]), \
                mock.patch.object(self.task, '_mail_has_red_badge', return_value=True), \
                mock.patch.object(self.task, 'ocr', return_value=[Box(350, 1004, 102, 27)]), \
                mock.patch.object(self.task, 'click'), \
                mock.patch.object(self.task, '_raise_with_evidence',
                                  side_effect=TaskDisabledException('红点仍在但无弹窗')), \
                mock.patch.object(self.task, '_close_mail') as close:
            with self.assertRaises(TaskDisabledException):
                self.task._claim_mail()
        close.assert_not_called()

    def test_new_templates_hide_account_uid(self):
        for name in (BATTLE_PASS, BATTLE_PASS_CLAIMED, GUILD_MISSION, MAIL):
            self._set(name)
            texts = [box.name for box in self.task.ocr(box=self.task.box_of_screen(0, 0.93, 1, 1.0))]
            self.assertFalse([text for text in texts if 'UID' in text.upper()], f'{name} 底栏仍能读出 UID: {texts}')
            self.assertFalse([text for text in texts if re.search(r'\d{6,}', text)],
                             f'{name} 底栏仍能读出长数字: {texts}')


if __name__ == '__main__':
    unittest.main()
