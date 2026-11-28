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
from tasks.welfare import (BATTLE_PASS_CLAIM_PATTERN, BATTLE_PASS_CLAIM_REGION, MAIL_CLAIM_PATTERN,
                           MAIL_CLAIM_REGION, WelfareTask)

BATTLE_PASS = 'in_game_battle_pass.png'
BATTLE_PASS_CLAIMED = 'in_game_battle_pass_claimed.png'
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
        boxes = self.task.ocr(box=self.task.box_of_screen(*BATTLE_PASS_CLAIM_REGION),
                              match=BATTLE_PASS_CLAIM_PATTERN)
        self.assertTrue(boxes, '有奖励可领时右下应有「一键领取」')
        self._set(BATTLE_PASS_CLAIMED)
        boxes = self.task.ocr(box=self.task.box_of_screen(*BATTLE_PASS_CLAIM_REGION),
                              match=BATTLE_PASS_CLAIM_PATTERN)
        self.assertFalse(boxes, '领取后「一键领取」按钮应消失')

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

    def test_claim_battle_pass_clicks_once_and_verifies(self):
        claim_box = Box(1438, 892, 105, 32, name='一键领取')
        with mock.patch.object(self.task, 'send_key') as send_key, \
                mock.patch.object(self.task, '_wait_until', return_value=True), \
                mock.patch.object(self.task, 'ocr',
                                  side_effect=[[claim_box], [], [], []]) as ocr, \
                mock.patch.object(self.task, 'click') as click, \
                mock.patch.object(self.task, 'screenshot'):
            self.task._claim_battle_pass()
        clicked = click.call_args_list[0].args[0]
        self.assertEqual((clicked.x, clicked.y), (1438, 892), '应点击「一键领取」按钮')
        send_key.assert_any_call('esc', after_sleep=1.2)
        self.assertEqual(ocr.call_count, 4, '按钮/弹窗/残留按钮/空白提示各查一次')

    def test_claim_battle_pass_skips_without_button(self):
        with mock.patch.object(self.task, 'send_key'), \
                mock.patch.object(self.task, '_wait_until', return_value=True), \
                mock.patch.object(self.task, 'ocr', return_value=[]), \
                mock.patch.object(self.task, 'click') as click, \
                mock.patch.object(self.task, '_close_battle_pass') as close:
            self.task._claim_battle_pass()
        click.assert_not_called()
        close.assert_called_once()

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
        for name in (BATTLE_PASS, BATTLE_PASS_CLAIMED, MAIL):
            self._set(name)
            texts = [box.name for box in self.task.ocr(box=self.task.box_of_screen(0, 0.93, 1, 1.0))]
            self.assertFalse([text for text in texts if 'UID' in text.upper()], f'{name} 底栏仍能读出 UID: {texts}')
            self.assertFalse([text for text in texts if re.search(r'\d{6,}', text)],
                             f'{name} 底栏仍能读出长数字: {texts}')


if __name__ == '__main__':
    unittest.main()
