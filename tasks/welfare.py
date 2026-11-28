"""福利领取：F4「帮会助力」赛季战令（奖励页+任务页）领取 + Esc 菜单邮件附件领取。

流程（从主世界开始，结束回主世界）：
1. 帮会助力：按 F4 打开面板（标题 OCR `帮会助力` + 右上 `规则说明`）。
   左侧图标栏切换子页：礼物图标=奖励页（OCR `前行礼遇`/`人脉拓展`），剪贴板图标=任务页（OCR `本周任务`/`本期任务`）。
   两个子页右下都有「一键领取」：存在才算有可领取奖励。
   - 奖励页点击后必须弹「获得奖励」，关闭后按钮必须消失；
   - 任务页领取只加战令经验，可能只出现「帮会助力」等级提升（没有奖励弹窗），
     以「按钮消失」为硬校验；领取升级后奖励页会出现新的可领奖励，所以两页循环领取直到都点不动。
   最后 Esc 关闭面板。
2. 邮件：Esc 打开菜单（OCR `因缘等级`）→ 点左侧纸飞机图标进「邮件」（OCR `邮件数`）→
   底部「全部领取」在无可领附件时是灰色禁用态（点击无反应，邮件列表也无红点）；
   列表有红点（RGB≈250,80,60）时点「全部领取」必须弹「获得奖励」，领取后红点必须消失。

2026-11-28 实机：奖励页 1/2 级与升级后的 3 级奖励已领取（弹窗 + 按钮消失）；
任务页「累计消耗精力400点」一键领取验证通过（周经验 2700→5400、等级 2→3、按钮与左侧红点消失）。
邮件 4 封均为已读调研信、附件不可领（全部领取禁用、点附件只弹物品说明），
「有红点 → 全部领取」的路径等新邮件到来后再实机复验。

活动面板（F1，七日签到 / 伊亚观光之旅）的礼盒与「前往」按钮对 Pynput 注入点击无响应
（2026-11-28 实机多次尝试），本任务不包含活动领取。
"""

import re
import time

from ok import BaseTask, TaskDisabledException
from ok.util.process import is_admin

from tasks.launcher import GAME_EXE, MAIN_WORLD_FEATURES, MAIN_WORLD_THRESHOLD, LauncherTask

# F4 帮会助力（赛季战令）面板
BATTLE_PASS_TITLE_PATTERN = re.compile(r"帮会助力")
BATTLE_PASS_MENU_PATTERN = re.compile(r"规则说明|购买等级")
GUILD_CLAIM_PATTERN = re.compile(r"^一键领取$")
GUILD_PASS_TAB_PATTERN = re.compile(r"前行礼遇|人脉拓展")
GUILD_MISSION_TAB_PATTERN = re.compile(r"本周任务|本期任务")

# Esc 菜单与邮件面板
MENU_PATTERN = re.compile(r"因缘等级|主角详情")
MAIL_TITLE_PATTERN = re.compile(r"邮件数|删除已读")
MAIL_CLAIM_PATTERN = re.compile(r"^全部领取$")

REWARD_POPUP_PATTERN = re.compile(r"获得奖励")
BLANK_CLOSE_PATTERN = re.compile(r"点击任意空白处关闭")

RED_BADGE_COLOR = {"r": (225, 255), "g": (40, 130), "b": (20, 120)}
MAIL_LIST_RED_MIN = 0.0005

BATTLE_PASS_TITLE_REGION = (0.03, 0.005, 0.22, 0.09)
BATTLE_PASS_MENU_REGION = (0.75, 0.005, 1.0, 0.09)
GUILD_PASS_TAB_REGION = (0.05, 0.40, 0.24, 0.55)
GUILD_MISSION_TAB_REGION = (0.10, 0.34, 0.22, 0.60)
GUILD_CLAIM_REGION = (0.60, 0.78, 0.98, 0.97)
GUILD_PASS_RAIL = (0.031, 0.166)
GUILD_MISSION_RAIL = (0.031, 0.241)
MAIL_LIST_REGION = (0.02, 0.08, 0.23, 0.55)
MAIL_CLAIM_REGION = (0.10, 0.88, 0.28, 0.97)
MAIL_ENTRY_POINT = (0.133, 0.293)
POPUP_CLOSE_POINT = (0.90, 0.90)
MAX_GUILD_CLAIM_ROUNDS = 5


class WelfareTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "领取福利"
        self.description = "F4「帮会助力」赛季战令一键领取，以及邮件附件全部领取"
        self.default_config.update({
            '领取战令奖励': True,
            '领取邮件附件': True,
        })
        self.config_description.update({
            '领取战令奖励': '按 F4 打开帮会助力面板，奖励页与任务页有「一键领取」时循环领取（任务页奖励会给战令经验）',
            '领取邮件附件': '从 Esc 菜单进入邮件，有可领附件时点「全部领取」',
        })

    def run(self):
        if not is_admin():
            raise TaskDisabledException(
                "游戏进程以管理员权限运行，本程序必须以管理员身份启动才能操作游戏窗口（右键程序 → 以管理员身份运行）")
        self.hwnd.bring_to_front()
        self._ensure_in_main_world()
        if self.config.get('领取战令奖励', True):
            self._claim_battle_pass()
        if self.config.get('领取邮件附件', True):
            self._claim_mail()
        if not (self._wait_until(self._is_in_main_world, 3)):
            self._raise_with_evidence('福利领取结束后未能确认回到主世界')
        self.log_info('福利领取完成，已回到主世界')

    # ---------- 帮会助力（赛季战令） ----------

    def _claim_battle_pass(self):
        self.log_info('打开 F4 帮会助力面板')
        opened = False
        for attempt in range(1, 4):
            self.send_key('f4', after_sleep=1.5)
            if self._wait_until(self._is_battle_pass_open, 5):
                opened = True
                break
            self.log_info(f'第 {attempt} 次按 F4 未识别到帮会助力面板，重试')
        if not opened:
            self._raise_with_evidence('按 F4 后未识别到「帮会助力」面板')
        claimed_any = False
        for round_index in range(1, MAX_GUILD_CLAIM_ROUNDS + 1):
            # 任务页领取会给战令经验，升级后奖励页会解锁新奖励，所以两页循环领
            pass_claimed = self._claim_guild_pass_rewards()
            mission_claimed = self._claim_guild_mission_rewards()
            if not (pass_claimed or mission_claimed):
                break
            claimed_any = True
            self.log_info(f'帮会助力第 {round_index} 轮领取完成（奖励页 {pass_claimed}，任务页 {mission_claimed}）')
        else:
            self.next_frame()
            if self._guild_claim_button() is not None:
                self._raise_with_evidence(
                    f'连续 {MAX_GUILD_CLAIM_ROUNDS} 轮后帮会助力仍有「一键领取」，奖励可能没有领完')
        if not claimed_any:
            self.log_info('帮会助力当前没有可领取奖励')
        self._close_battle_pass()

    def _claim_guild_pass_rewards(self):
        self._click_guild_rail(GUILD_PASS_RAIL)
        if not self._wait_until(self._is_guild_pass_tab, 4):
            self._raise_with_evidence('帮会助力面板没有切到奖励页（前行礼遇/人脉拓展）')
        box = self._guild_claim_button()
        if box is None:
            return False
        self.log_info(f'奖励页点击「一键领取」: {box}')
        self.click(box, after_sleep=2)
        if not self._wait_until(self._is_reward_popup, 5):
            self._raise_with_evidence('奖励页点击「一键领取」后没有出现「获得奖励」弹窗')
        self.screenshot('welfare_battle_pass_reward')
        self._close_reward_popup()
        if self._guild_claim_button() is not None:
            self._raise_with_evidence('奖励页领取后「一键领取」按钮仍然存在')
        self.log_info('帮会助力奖励页已领取')
        return True

    def _claim_guild_mission_rewards(self):
        self._click_guild_rail(GUILD_MISSION_RAIL)
        if not self._wait_until(self._is_guild_mission_tab, 4):
            self._raise_with_evidence('帮会助力面板没有切到任务页（本周任务/本期任务）')
        box = self._guild_claim_button()
        if box is None:
            return False
        self.log_info(f'任务页点击「一键领取」: {box}')
        self.click(box, after_sleep=1.5)
        if self._wait_until(self._is_reward_popup, 3):
            self._close_reward_popup()
        self.screenshot('welfare_guild_mission_claimed')
        # 任务页领取只加战令经验（可能只弹「等级提升」），以按钮消失为硬校验
        for _ in range(16):
            self.next_frame()
            if self._guild_claim_button() is None:
                self.log_info('帮会助力任务页已领取')
                return True
            self.sleep(0.5)
        self._raise_with_evidence('任务页点击「一键领取」后按钮仍然存在，奖励可能没有领到')

    def _guild_claim_button(self):
        matches = self.ocr(box=self.box_of_screen(*GUILD_CLAIM_REGION), match=GUILD_CLAIM_PATTERN)
        return matches[0] if matches else None

    def _click_guild_rail(self, point):
        self.click(int(self.width * point[0]), int(self.height * point[1]), after_sleep=1.5)

    def _is_guild_pass_tab(self):
        return bool(self.ocr(box=self.box_of_screen(*GUILD_PASS_TAB_REGION), match=GUILD_PASS_TAB_PATTERN))

    def _is_guild_mission_tab(self):
        return bool(self.ocr(box=self.box_of_screen(*GUILD_MISSION_TAB_REGION), match=GUILD_MISSION_TAB_PATTERN))

    def _close_battle_pass(self):
        for _ in range(3):
            if self._close_blank_popup():
                continue
            self.send_key('esc', after_sleep=1.2)
            if self._wait_until(self._is_in_main_world, 3):
                return
        self._raise_with_evidence('关闭帮会助力面板后未回到主世界')

    # ---------- 邮件 ----------

    def _claim_mail(self):
        self.log_info('通过 Esc 菜单进入邮件')
        self.send_key('esc', after_sleep=1.2)
        if not self._wait_until(self._is_menu_open, 4):
            self._raise_with_evidence('按 Esc 后未识别到菜单（因缘等级/主角详情）')
        self.click(int(self.width * MAIL_ENTRY_POINT[0]), int(self.height * MAIL_ENTRY_POINT[1]), after_sleep=1.8)
        if not self._wait_until(self._is_mail_open, 5):
            self._raise_with_evidence('菜单里点击邮件图标后未识别到「邮件」面板')
        self.next_frame()
        claimable = self._mail_has_red_badge()
        boxes = self.ocr(box=self.box_of_screen(*MAIL_CLAIM_REGION), match=MAIL_CLAIM_PATTERN)
        if not boxes:
            self.log_info('邮件面板没有「全部领取」按钮，跳过邮件领取')
        else:
            self.click(boxes[0], after_sleep=2)
            if self._wait_until(self._is_reward_popup, 5):
                self.screenshot('welfare_mail_reward')
                self._close_reward_popup()
                self.next_frame()
                if claimable and self._mail_has_red_badge():
                    self._raise_with_evidence('点击「全部领取」并关闭弹窗后，邮件列表仍有红点')
                self.log_info('邮件附件已领取')
            elif claimable:
                self._raise_with_evidence('邮件列表检测到红点，但点击「全部领取」没有出现「获得奖励」弹窗')
            else:
                self.log_info('邮件列表没有红点，「全部领取」为禁用态，当前没有可领取附件')
        self._close_mail()

    def _close_mail(self):
        for _ in range(4):
            if self._close_blank_popup():
                continue
            self.send_key('esc', after_sleep=1.2)
            if self._wait_until(self._is_in_main_world, 2.5):
                return
        self._raise_with_evidence('关闭邮件面板后未能回到主世界')

    def _mail_has_red_badge(self):
        ratio = self.calculate_color_percentage(RED_BADGE_COLOR, self.box_of_screen(*MAIL_LIST_REGION))
        self.log_info(f'邮件列表红点占比 {ratio:.4f}（阈值 {MAIL_LIST_RED_MIN}）')
        return ratio >= MAIL_LIST_RED_MIN

    # ---------- 通用 ----------

    def _is_battle_pass_open(self):
        return (bool(self.ocr(box=self.box_of_screen(*BATTLE_PASS_TITLE_REGION), match=BATTLE_PASS_TITLE_PATTERN))
                and bool(self.ocr(box=self.box_of_screen(*BATTLE_PASS_MENU_REGION), match=BATTLE_PASS_MENU_PATTERN)))

    def _is_menu_open(self):
        return bool(self.ocr(match=MENU_PATTERN))

    def _is_mail_open(self):
        return bool(self.ocr(match=MAIL_TITLE_PATTERN))

    def _is_reward_popup(self):
        return bool(self.ocr(match=REWARD_POPUP_PATTERN))

    def _close_reward_popup(self):
        for _ in range(3):
            self.click(int(self.width * POPUP_CLOSE_POINT[0]), int(self.height * POPUP_CLOSE_POINT[1]),
                       after_sleep=1.0)
            self.next_frame()
            if not self._is_reward_popup():
                return True
        self._raise_with_evidence('「获得奖励」弹窗未能关闭')

    def _close_blank_popup(self):
        if not self.ocr(match=BLANK_CLOSE_PATTERN):
            return False
        self.log_info('关闭「点击任意空白处关闭」提示框')
        self.click(int(self.width * POPUP_CLOSE_POINT[0]), int(self.height * POPUP_CLOSE_POINT[1]), after_sleep=1.0)
        return True

    def _ensure_in_main_world(self):
        launcher = self.get_task_by_class(LauncherTask)
        if launcher is None:
            raise TaskDisabledException('启动任务未注册，无法自动进入游戏')
        if launcher._find_process(GAME_EXE):
            launcher._attach_game()
            if self._wait_until(self._is_in_main_world, 2):
                self.log_info('已在主世界')
                return
            self.log_info('当前不在主世界（可能有残留面板），先尝试关闭')
            if self._escape_unknown_screens() and self._wait_until(self._is_in_main_world, 2):
                self.log_info('已回到主世界')
                return
            self.log_info('残留界面关不掉，交给启动任务走进入链路')
        launcher.run()
        if not self._wait_until(self._is_in_main_world, 3):
            self._raise_with_evidence('启动任务结束后仍未确认主世界')

    def _escape_unknown_screens(self, attempts=6):
        for _ in range(attempts):
            self.next_frame()
            if self._is_in_main_world():
                return True
            if self._close_blank_popup():
                continue
            self.send_key('esc', after_sleep=1.0)
        self.next_frame()
        return self._is_in_main_world()

    def _is_in_main_world(self):
        return all(self.find_one(name, threshold=MAIN_WORLD_THRESHOLD) for name in MAIN_WORLD_FEATURES)

    def _wait_until(self, predicate, timeout, interval=0.5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.next_frame()
            if predicate():
                return True
            self.sleep(interval)
        return False

    def _raise_with_evidence(self, reason):
        self.screenshot('welfare_failed')
        self.ocr(log=True)
        raise TaskDisabledException(f'{reason}，已保存截图与当前全量 OCR 文本，请检查界面是否改版或停在未知页面')
