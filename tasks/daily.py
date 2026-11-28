"""日常活跃：扫描「每日目标」全部任务并领取已完成奖励，顺带领取活跃度里程碑宝箱。

流程：主世界 → F3 快捷键打开面板（图标模板仅作兜底）→ 左侧第二个「日常活跃」入口 →
每日目标为横向卡片列表，一屏只露出 4 张多一点，必须向左拖动才能拿全；
拖动后画面不再变化即视为到达末尾。

卡片解析全部基于 OCR + 颜色：
- 进度徽章 x/y 作为每张卡的锚点，x>=y 视为已完成；
- 底部没有「前往/进行中/已领取/已完成」文字、且整条金色按钮带存在 → 可领取；
- 领取后以左侧活跃度奖章数字增长做硬校验；活跃度上限 500，满额后以卡片变为「已完成」为准；
- 领取会让卡片重排（已完成移到右侧），所以每领一张都重新扫描；
- 扫描会停在列表末尾，领取前必须回拖并重新定位卡片（2026-11-28 实机：直接点首页坐标会落到别的卡上）。
活跃度里程碑（100/200/300/400/500）宝箱带红点，点击弹出「获得奖励」，点空白处关闭。

领取完还有一步：日常目标里的「消耗120精力」只靠等日常做不满，必须主动去打。
点这张卡的「前往」进入「勤劳是福」精力商店 → 选一项体力任务（打哪个都行，
默认勤劳致富的仙令 20 精力/次）→ 在作战界面点「+」把挑战次数拉到上限 →
点「挑战」→ 阵容界面「开始对决」→ 若弹出「推荐精灵等级…是否确认继续挑战」点「确认」。
战斗是多波自动战斗（6 次约 6 分钟），结算界面为「挑战完成」，点「退出」回到作战准备。
一场 6 次刚好 120 精力，同时把「赢得任意3场因缘对决」一起做掉，回来再扫一遍领取奖励。
本轮作战以「体力数字下降 + 卡片进度前进」双向校验，任一不成立就落证据失败。
日常关闭面板回到主世界后，默认继续调用「领取福利」任务，把 F4 帮会助力（奖励页+任务页）与邮件接入一条龙；
DailyActivityTask 的「日常后领取福利」开关可单独关闭这一段。

实机输入：0.75.2 起 PostMessage 对游戏内 UI 无效，必须用 Pynput 真实输入并保持游戏前台。
比例坐标来自 2026-11-27 实机截图（1920x1080），旧版 1919x1049 素材仍兼容。
"""

import math
import re
import time

import cv2
import numpy as np

from ok import BaseTask, TaskDisabledException
from ok.feature.Box import Box
from ok.util.process import is_admin

from tasks.launcher import GAME_EXE, MAIN_WORLD_FEATURES, MAIN_WORLD_THRESHOLD, LauncherTask
from tasks.welfare import WelfareTask

F3_FEATURE = "main_world_f3_menu"

PANEL_TITLE_PATTERN = re.compile(r"打卡项目|日常活跃")
DAILY_TAB_PATTERN = re.compile(r"每日目标")
PROGRESS_PATTERN = re.compile(r"^(\d+)/(\d+)$")
REWARD_PATTERN = re.compile(r"\+?\s*(\d+)\s*活跃度?")
DIGITS_PATTERN = re.compile(r"^\d+$")
BUTTON_LABELS = ("领取", "前往", "进行中", "已领取", "已完成")

GOLD_COLOR = {"r": (235, 255), "g": (160, 235), "b": (0, 135)}
RED_BADGE_COLOR = {"r": (225, 255), "g": (40, 130), "b": (20, 120)}
MIN_CONFIDENCE = 0.85
GOLD_CLAIMABLE_MIN = 0.25
GOLD_CLAIM_ROW_MIN = 0.5
GOLD_CLAIM_MIN_HEIGHT = 15
MAX_SCAN_PAGES = 6
MAX_CLAIM_PASSES = 8

# 以下相对坐标全部实测自 1919x1049/1051 与 1920x1080 截图
PANEL_HEADER_REGION = (0.15, 0.09, 0.40, 0.20)
DAILY_TAB_REGION = (0.16, 0.32, 0.42, 0.40)
ACTIVITY_TOTAL_REGION = (0.185, 0.25, 0.25, 0.33)
ACTIVITY_BAR_REGION = (0.25, 0.24, 0.92, 0.30)
CARD_REGION = (0.175, 0.395, 0.900, 0.875)
FOOTER_REGION_Y = (0.782, 0.862)
CARD_HALF_WINDOW = 0.078
DAILY_TAB_POINT = (0.135, 0.380)
CLOSE_POINT = (0.873, 0.143)
DRAG_FROM = (0.80, 0.62)
DRAG_TO = (0.30, 0.62)
BLANK_CLOSE_POINT = (0.88, 0.88)
MILESTONE_CHEST_Y = 0.222
MILESTONE_BADGE_OFFSET = (8, -45, 45, 42)
MILESTONE_BADGE_MIN = 0.10
ACTIVITY_MAX_DEFAULT = 500
LEVEL_CONFIRM_REGION = (0.45, 0.60, 0.72, 0.69)

BLANK_CLOSE_PATTERN = re.compile(r"点击任意空白处关闭")
REWARD_POPUP_PATTERN = re.compile(r"获得奖励")
# 作战准备界面左上角也有「推荐精灵等级：10」，不能拿它当弹窗特征；
# 只有「推荐…是否确认继续挑战」的确认弹窗才含这句话
LEVEL_WARNING_PATTERN = re.compile(r"是否确认继续挑战")
CONFIRM_PATTERN = re.compile(r"^确认$")
BATTLE_RESULT_PATTERN = re.compile(r"挑战完成|再次挑战")
EXIT_PATTERN = re.compile(r"^退出$")

# 消耗精力作战：日常活跃「消耗X精力」→ 勤劳是福 → 作战准备 → 挑战
BUTTON_GO = "前往"
STAMINA_CARD_PATTERN = re.compile(r"消耗\s*\d+\s*精力")
SHOP_TITLE_PATTERN = re.compile(r"勤劳是福")
BATTLE_COUNT_PATTERN = re.compile(r"挑战次数")
CHALLENGE_PATTERN = re.compile(r"^挑战$")
DUEL_PATTERN = re.compile(r"开始对决")
STAMINA_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)")
NUMBER_IN_TEXT_PATTERN = re.compile(r"(\d+)")

SHOP_PLUS_FEATURE = "battle_count_plus"
CHALLENGE_FEATURE = "battle_challenge"
DUEL_FEATURE = "battle_start_duel"
SHOP_TABS = ("基础材料", "心识领悟")
SHOP_TASK_TITLES = ("勤劳致富的仙令", "熟能生巧的缘宝", "磨炼心志的砺砂", "炼心", "锻形", "聚意", "凝魂")

# 全部实测自 1919x1079 截图；面板内元素位置固定，用比例框定位后再靠 OCR 取实际盒子
SHOP_TITLE_REGION = (0.15, 0.09, 0.42, 0.17)
SHOP_TAB_REGION = (0.17, 0.19, 0.30, 0.37)
SHOP_ROWS_REGION = (0.46, 0.18, 0.87, 0.70)
SHOP_ROW_BAND = 0.022
BATTLE_HEADER_REGION = (0.03, 0.005, 0.22, 0.065)
BATTLE_COUNT_REGION = (0.78, 0.78, 0.95, 0.87)
BATTLE_BUTTON_REGION = (0.70, 0.86, 0.98, 0.98)
STAMINA_PANEL_REGION = (0.72, 0.10, 0.85, 0.18)
STAMINA_BATTLE_REGION = (0.82, 0.005, 0.94, 0.07)
DUEL_BUTTON_REGION = (0.85, 0.93, 1.0, 1.0)


def normalize_title(text):
    # OCR 可能漏掉「」，跨页去重与展示统一用去空白、去书名号后的文本
    return re.sub(r"[\s「」]", "", text or "")


class DailyActivityTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "日常活跃"
        self.description = "扫描「日常活跃」每日目标、消耗精力作战补活跃度，完成后继续领取帮会助力战令与邮件"
        self.default_config.update({
            '消耗精力作战': True,
            '体力材料': SHOP_TASK_TITLES[0],
            '最多战斗次数': 6,
            '作战轮数': 1,
            '作战等待秒数': 600,
            '日常后领取福利': True,
        })
        self.config_description.update({
            '消耗精力作战': '日常目标里有「消耗精力」时，前往勤劳是福打一场并把挑战次数拉到上限，顺带完成对战任务',
            '体力材料': '在勤劳是福里打哪个体力任务；找不到配置项时退回当前页签第一项',
            '最多战斗次数': '单场战斗的挑战次数上限，默认 6（20 精力/次刚好凑满 120）',
            '作战轮数': '最多连打几轮；一轮通常就能把「消耗X精力」做满',
            '作战等待秒数': '点击「开始对决」后等待结算的最长秒数，6 次挑战实机约 6 分钟',
            '日常后领取福利': '日常结束后继续领取 F4 帮会助力（奖励页+任务页）与邮件附件',
        })
        self.config_type.update({
            '体力材料': {'type': 'drop_down', 'options': list(SHOP_TASK_TITLES)},
            '最多战斗次数': {'min': 1, 'max': 10},
            '作战轮数': {'min': 1, 'max': 3},
            '作战等待秒数': {'min': 120, 'max': 1200},
        })

    def run(self):
        if not is_admin():
            raise TaskDisabledException(
                "游戏进程以管理员权限运行，本程序必须以管理员身份启动才能操作游戏窗口（右键程序 → 以管理员身份运行）")
        self.hwnd.bring_to_front()
        self._ensure_in_main_world()
        self._open_daily_panel()
        self._scan_and_claim()
        self._claim_milestones()
        if self._run_stamina_battles():
            self.log_info("作战完成后重新扫描每日目标，领取新完成的奖励")
            self._scan_and_claim()
            self._claim_milestones()
        self._close_panel()
        self._claim_welfare_after_daily()

    def _claim_welfare_after_daily(self):
        if not self.config.get('日常后领取福利', True):
            self.log_info('已关闭「日常后领取福利」，跳过帮会助力与邮件领取')
            return
        welfare = self.get_task_by_class(WelfareTask)
        if welfare is None:
            raise TaskDisabledException('福利领取任务未注册，无法在一条龙中领取帮会助力与邮件')
        self.log_info('日常已完成，继续领取帮会助力战令与邮件')
        welfare.run()

    def _ensure_in_main_world(self):
        launcher = self.get_task_by_class(LauncherTask)
        if launcher is None:
            raise TaskDisabledException("启动任务未注册，无法自动进入游戏")
        if launcher._find_process(GAME_EXE):
            launcher._attach_game()
            if self._wait_until(self._is_in_main_world, 2):
                self.log_info("已在主世界")
                return
            self.log_info("当前不在主世界（可能有残留面板），先尝试关闭")
            if self._escape_unknown_screens() and self._wait_until(self._is_in_main_world, 2):
                self.log_info("已回到主世界")
                return
            self.log_info("残留界面关不掉，交给启动任务走进入链路")
        launcher.run()
        if not self._wait_until(self._is_in_main_world, 3):
            self._raise_with_evidence("启动任务结束后仍未确认主世界")

    def _escape_unknown_screens(self, attempts=6):
        for _ in range(attempts):
            self.next_frame()
            if self._is_in_main_world():
                return True
            if self._close_blank_popup():
                continue
            if self._is_daily_panel_open():
                self.click(*CLOSE_POINT, after_sleep=1)
            else:
                self.send_key('esc', after_sleep=1)
        self.next_frame()
        return self._is_in_main_world()

    def _open_daily_panel(self):
        self.log_info("打开 F3 面板")
        opened = False
        for attempt in range(1, 4):
            self._close_blank_popup()
            self._click_f3_entry(attempt)
            if self._wait_until(self._is_daily_panel_open, 5):
                opened = True
                break
            self.log_info(f"第 {attempt} 次尝试打开 F3 面板失败，重试")
        if not opened:
            self._raise_with_evidence("未能打开 F3 面板（打卡项目/日常活跃）")
        if not self._is_daily_tab():
            self.log_info("切换到「日常活跃」签页")
            for _ in range(2):
                self.click(*DAILY_TAB_POINT, after_sleep=1.2)
                if self._wait_until(self._is_daily_tab, 4):
                    break
            else:
                self._raise_with_evidence("未能切换到「日常活跃」签页")
        self.log_info("已进入日常活跃面板")

    def _click_f3_entry(self, attempt=1):
        # F3 快捷键最稳定；图标模板只作兜底（HUD 会随功能解锁整体左移）
        if attempt == 1:
            self.log_info("按 F3 快捷键打开面板")
            self.send_key('f3', after_sleep=1.2)
            return
        f3 = self.find_one(F3_FEATURE, threshold=0.8, horizontal_variance=0.06, vertical_variance=0.02)
        if f3 is not None:
            # 模板框含左侧留白，图标中心约在框宽 72% 处
            x = int(f3.x + f3.width * 0.72)
            y = int(f3.y + f3.height / 2)
            self.log_info(f"点击主界面 F3 图标: ({x}, {y}) {f3}")
            self.click(x, y, after_sleep=1.2)
        else:
            self.log_info("未匹配到 F3 图标，改用 F3 快捷键")
            self.send_key('f3', after_sleep=1.2)

    def _scan_and_claim(self):
        total_before = self._read_activity_total()
        self.log_info(f"当前活跃度: {total_before}")
        claimed = []
        order = {}
        for _ in range(MAX_CLAIM_PASSES):
            # 领取会让卡片重排（已完成往右挪），每领一张都从头重新扫描
            self._rewind_cards()
            cards = self._scan_pages()
            if not cards:
                self._raise_with_evidence("没有解析到任何每日目标卡片")
            order = {normalize_title(card['title']): card for card in cards}
            claimables = [card for card in cards if card['claimable']]
            if not claimables:
                break
            card = self._locate_card(claimables[0]['title'])
            if card is None:
                self._raise_with_evidence(f"扫描到可领取卡片「{claimables[0]['title']}」，但回拖后在任何一屏都找不到它")
            if not card['claimable']:
                # 卡片状态在扫描后发生了变化，重新扫描而不是拿旧坐标硬点
                self.log_warning(f"重新定位到的「{card['title']}」已不可领取（{card['button'] or '无按钮'}），重新扫描")
                continue
            self._claim_card(card)
            claimed.append(card)
        else:
            self.log_warning(f"连续领取 {MAX_CLAIM_PASSES} 轮后仍有可领取卡片，停止以免误点")
        total_after = self._read_activity_total()
        if total_after < total_before:
            self._raise_with_evidence(f"活跃度出现倒退（{total_before} → {total_after}），请检查面板状态")
        self.log_info(f"每日目标共 {len(order)} 条:")
        for key, card in order.items():
            if card['claimable']:
                state = "可领取(未领到)"
            elif any(normalize_title(c['title']) == key for c in claimed):
                state = "已领取"
            else:
                state = card['button'] or "未完成"
            self.log_info(f"  - {card['title']}  {card['progress']}  +{card['reward']}活跃度  [{state}]")
        self.log_info(f"本次领取 {len(claimed)} 条，活跃度 {total_before} → {total_after}")

    def _scan_pages(self):
        cards = []
        seen = set()
        unchanged = 0
        prev_titles = None
        for page in range(MAX_SCAN_PAGES):
            self.next_frame()
            page_cards = self._parse_cards()
            if not page_cards:
                self._raise_with_evidence("当前页没有解析到任何每日目标卡片")
            page_titles = set()
            for card in page_cards:
                key = normalize_title(card['title'])
                page_titles.add(key)
                if key in seen:
                    continue
                seen.add(key)
                cards.append(card)
            self.log_info(f"第 {page + 1} 屏解析到 {len(page_cards)} 张卡片: {sorted(page_titles)}")
            if prev_titles is not None and page_titles == prev_titles:
                unchanged += 1
                if unchanged >= 2:
                    self.log_info("向左拖动后卡片不再变化，按已到列表末尾处理")
                    break
            else:
                unchanged = 0
            prev_titles = page_titles
            self._drag_cards_left()
        return cards

    def _parse_cards(self):
        boxes = [b for b in self.ocr(box=self.box_of_screen(*CARD_REGION)) if b.confidence >= MIN_CONFIDENCE]
        anchors = sorted((b for b in boxes if PROGRESS_PATTERN.match(b.name.strip())), key=lambda b: b.x)
        half_window = CARD_HALF_WINDOW * self.width
        cards = []
        for anchor in anchors:
            center_x = anchor.x + anchor.width / 2
            column = [b for b in boxes if abs(b.x + b.width / 2 - center_x) <= half_window]
            card = self._build_card(anchor, column, center_x)
            if card is not None:
                cards.append(card)
        return cards

    def _build_card(self, anchor, boxes, center_x):
        reward_box = None
        reward = None
        buttons = []
        title_boxes = []
        for box in boxes:
            name = box.name.strip()
            if box is anchor or PROGRESS_PATTERN.match(name):
                continue
            match = REWARD_PATTERN.search(name)
            if match:
                reward_box = box
                reward = int(match.group(1))
                continue
            if name in BUTTON_LABELS:
                buttons.append(box)
                continue
            title_boxes.append(box)
        if reward is None:
            return None
        if reward_box is not None:
            title_boxes = [b for b in title_boxes if b.y + b.height / 2 < reward_box.y]
        title_boxes = [b for b in title_boxes if b.y >= anchor.y + anchor.height - 8]
        title = normalize_title(''.join(b.name for b in sorted(title_boxes, key=lambda b: (b.y, b.x))))
        if len(title) < 2:
            return None
        progress_match = PROGRESS_PATTERN.match(anchor.name.strip())
        done = int(progress_match.group(1)) >= int(progress_match.group(2)) > 0
        footer_top = FOOTER_REGION_Y[0] * self.height
        footer_bottom = FOOTER_REGION_Y[1] * self.height
        footer = Box(center_x - CARD_HALF_WINDOW * self.width, footer_top,
                     CARD_HALF_WINDOW * self.width * 2, footer_bottom - footer_top)
        gold = self.calculate_color_percentage(GOLD_COLOR, footer)
        button_box = buttons[0] if buttons else None
        claim_button = None
        if done and not buttons and reward_box is not None:
            claim_button = self._find_claim_button(center_x, reward_box)
        if claim_button is not None:
            gold = claim_button.confidence
            claim_x = int(claim_button.x + claim_button.width / 2)
            claim_y = int(claim_button.y + claim_button.height / 2)
            claimable = True
        else:
            claimable = done and not buttons and gold >= GOLD_CLAIMABLE_MIN
            claim_x = int(button_box.x + button_box.width / 2) if button_box is not None \
                else (int(reward_box.x + reward_box.width / 2) if reward_box else int(center_x))
            claim_y = int(button_box.y + button_box.height / 2) if button_box is not None \
                else int((footer_top + footer_bottom) / 2)
        return {
            'title': title,
            'progress': anchor.name.strip(),
            'done': done,
            'reward': reward,
            'button': button_box.name.strip() if button_box is not None else None,
            'button_box': button_box,
            'gold': round(gold, 3),
            'claimable': claimable,
            'claimed': False,
            'claim_x': claim_x,
            'claim_y': claim_y,
        }

    def _find_claim_button(self, center_x, reward_box):
        """在奖励文字下方按整行金色占比找领取按钮，避免依赖固定纵向坐标。"""
        frame = self.frame
        if frame is None:
            return None
        half = int(CARD_HALF_WINDOW * self.width)
        x1 = max(0, int(center_x - half))
        x2 = min(self.width, int(center_x + half))
        y1 = max(0, int(reward_box.y + reward_box.height))
        y2 = min(self.height, int(CARD_REGION[3] * self.height) + int(self.height * 0.07))
        if x2 - x1 < 10 or y2 - y1 < 10:
            return None
        region = frame[y1:y2, x1:x2, :3]
        mask = cv2.inRange(region, (GOLD_COLOR['b'][0], GOLD_COLOR['g'][0], GOLD_COLOR['r'][0]),
                           (GOLD_COLOR['b'][1], GOLD_COLOR['g'][1], GOLD_COLOR['r'][1]))
        ratios = mask.mean(axis=1) / 255
        rows = np.where(ratios >= GOLD_CLAIM_ROW_MIN)[0]
        if len(rows) < GOLD_CLAIM_MIN_HEIGHT:
            return None
        runs = np.split(rows, np.where(np.diff(rows) > 3)[0] + 1)
        run = max(runs, key=len)
        if len(run) < GOLD_CLAIM_MIN_HEIGHT:
            return None
        top = y1 + int(run[0])
        height = int(run[-1] - run[0]) + 1
        return Box(x1, top, x2 - x1, height, name='claim_button',
                   confidence=float(ratios[run].mean()))

    def _claim_card(self, card):
        cap = self._read_activity_cap()
        before = self._read_activity_total()
        for attempt in (1, 2):
            expected = min(before + card['reward'], cap)
            self.log_info(f"领取「{card['title']}」+{card['reward']}活跃度（第 {attempt} 次，目标 {expected}/{cap}）")
            self.click(card['claim_x'], card['claim_y'], after_sleep=1.5)
            deadline = time.time() + 4
            while time.time() < deadline:
                total = self._read_activity_total()
                if total >= expected:
                    if before >= cap and self._is_card_claimable(card['title']):
                        self.log_warning('活跃度已满，但卡片仍显示可领取，重新点击')
                        break
                    self.log_info(f"活跃度 {before} → {total}，领取成功")
                    return True
                self.sleep(0.5)
        self._raise_with_evidence(f"点击领取「{card['title']}」后活跃度未达到预期（当前 {before}，上限 {cap}）")

    def _is_card_claimable(self, title):
        key = normalize_title(title)
        return any(normalize_title(card['title']) == key and card['claimable'] for card in self._parse_cards())

    def _read_activity_cap(self):
        boxes = self.ocr(box=self.box_of_screen(*ACTIVITY_BAR_REGION))
        values = [int(box.name.strip()) for box in boxes
                  if DIGITS_PATTERN.match(box.name.strip()) and 0 < int(box.name.strip()) <= 9999]
        return max(values) if values else ACTIVITY_MAX_DEFAULT

    def _read_milestones(self):
        boxes = self.ocr(box=self.box_of_screen(*ACTIVITY_BAR_REGION))
        milestones = sorted(((int(box.name.strip()), int(box.x + box.width / 2)) for box in boxes
                             if DIGITS_PATTERN.match(box.name.strip())), key=lambda item: item[1])
        return milestones

    def _milestone_claimable(self, x, chest_y):
        dx, dy, width, height = MILESTONE_BADGE_OFFSET
        badge = Box(x + dx, chest_y + dy, width, height)
        return self.calculate_color_percentage(RED_BADGE_COLOR, badge) >= MILESTONE_BADGE_MIN

    def _claim_milestones(self):
        total = self._read_activity_total()
        milestones = self._read_milestones()
        if not milestones:
            self.log_warning('无法读取活跃度里程碑，跳过里程碑宝箱')
            return
        chest_y = int(self.height * MILESTONE_CHEST_Y)
        claimed = 0
        for value, x in milestones:
            if value <= 0 or value > total:
                continue
            if not self._milestone_claimable(x, chest_y):
                continue
            self.log_info(f"领取 {value} 活跃度里程碑宝箱")
            self.click(x, chest_y, after_sleep=1.5)
            if not self._wait_until(self._is_reward_popup, 4):
                self.log_warning(f"{value} 活跃度里程碑点击后没有出现「获得奖励」弹窗，跳过")
                continue
            self.screenshot(f'daily_milestone_{value}')
            self._close_reward_popup()
            claimed += 1
        if claimed:
            self.log_info(f'本次领取 {claimed} 个活跃度里程碑宝箱')

    def _is_reward_popup(self):
        return bool(self.ocr(match=REWARD_POPUP_PATTERN))

    def _close_reward_popup(self):
        for _ in range(3):
            self.click(*BLANK_CLOSE_POINT, after_sleep=1.0)
            self.next_frame()
            if not self._is_reward_popup():
                return True
        self.log_warning('「获得奖励」弹窗未能关闭')
        return False

    def _close_blank_popup(self):
        if not self.ocr(match=BLANK_CLOSE_PATTERN):
            return False
        self.log_info('关闭「点击任意空白处关闭」提示框')
        self.click(*BLANK_CLOSE_POINT, after_sleep=1.0)
        return True

    def _read_activity_total(self):
        for _ in range(3):
            self.next_frame()
            boxes = self.ocr(box=self.box_of_screen(*ACTIVITY_TOTAL_REGION))
            for box in boxes:
                text = box.name.strip()
                if DIGITS_PATTERN.match(text):
                    return int(text)
            self.sleep(0.4)
        self._raise_with_evidence("无法读取顶部活跃度数字")

    def _drag_cards_left(self):
        self.swipe(int(self.width * DRAG_FROM[0]), int(self.height * DRAG_FROM[1]),
                   int(self.width * DRAG_TO[0]), int(self.height * DRAG_TO[1]),
                   duration=1.0, after_sleep=0.8)

    def _drag_cards_right(self):
        self.swipe(int(self.width * DRAG_TO[0]), int(self.height * DRAG_TO[1]),
                   int(self.width * DRAG_FROM[0]), int(self.height * DRAG_FROM[1]),
                   duration=1.0, after_sleep=0.8)

    def _page_title_set(self):
        return {normalize_title(card['title']) for card in self._parse_cards()}

    def _rewind_cards(self):
        """把卡片列表拖回最左侧，保证扫描总从第一屏开始。"""
        self.next_frame()
        previous = self._page_title_set()
        for _ in range(MAX_SCAN_PAGES):
            if not previous:
                return
            self._drag_cards_right()
            self.next_frame()
            current = self._page_title_set()
            if current == previous:
                return
            previous = current

    def _locate_card(self, title):
        """回到列表最左侧后逐屏查找指定卡片，返回当前滚动位置下的最新坐标。"""
        key = normalize_title(title)
        self._rewind_cards()
        for _ in range(MAX_SCAN_PAGES):
            self.next_frame()
            for card in self._parse_cards():
                if normalize_title(card['title']) == key:
                    return card
            self._drag_cards_left()
        return None

    # ---------- 消耗精力作战：日常活跃 → 勤劳是福 → 作战准备 → 挑战 ----------

    def _card_progress(self, card):
        match = PROGRESS_PATTERN.match(card['progress'].strip())
        if not match:
            return False, 0, 0
        current, target = int(match.group(1)), int(match.group(2))
        return target > 0 and current >= target, current, target

    def _find_stamina_card(self):
        self._rewind_cards()
        for _ in range(MAX_SCAN_PAGES):
            cards = self._parse_cards()
            matches = [card for card in cards if STAMINA_CARD_PATTERN.search(card['title'])]
            if matches:
                return matches[0]
            self.log_info("当前屏没有「消耗精力」任务，向左翻页继续找")
            self._drag_cards_left()
        return None

    def _run_stamina_battles(self):
        if not self.config.get('消耗精力作战', True):
            self.log_info('已关闭「消耗精力作战」，跳过精力任务')
            return False
        rounds = max(1, int(self.config.get('作战轮数', 1) or 1))
        ran = False
        for index in range(1, rounds + 1):
            card = self._find_stamina_card()
            if card is None:
                self.log_info('日常目标里没有找到「消耗精力」任务，跳过作战')
                return ran
            done, current, target = self._card_progress(card)
            if done:
                self.log_info(f"「{card['title']}」已完成（{card['progress']}），无需作战")
                return ran
            if card['button'] != BUTTON_GO:
                self.log_warning(f"「{card['title']}」不是「前往」状态（{card['button']}），跳过作战")
                return ran
            self.log_info(f"第 {index} 轮消耗精力作战：任务进度 {current}/{target}")
            self._battle_round(card, current, target)
            ran = True
        return ran

    def _battle_round(self, card, current, target):
        self.click(card['button_box'], after_sleep=1.5)
        if not self._wait_until(self._is_stamina_shop_open, 6):
            self._raise_with_evidence('点击「消耗精力」的「前往」后没有进入「勤劳是福」精力商店')
        row = self._open_shop_row()
        if not self._wait_until(self._is_battle_prepare_open, 10):
            self._raise_with_evidence(f"从「{row['title']}」进入作战失败，未识别到「挑战次数」界面")
        header = self._read_battle_header()
        if header and normalize_title(row['title']) not in normalize_title(header):
            self.log_warning(f"作战界面标题「{header}」与所选体力任务「{row['title']}」不一致")
        cost = self._maximize_battle_count(row['cost'], current, target)
        stamina_before = self._read_stamina(STAMINA_BATTLE_REGION)
        self.log_info(f"本轮计划消耗 {cost} 精力，作战前体力 {stamina_before}")
        self._click_challenge()
        self._start_duel()
        self._confirm_level_warning()
        state = self._wait_battle_finished(self._battle_timeout())
        self.log_info(f"作战结束，当前界面: {state}")
        self.screenshot('daily_battle_finished')
        self._return_to_daily_panel()
        self._verify_battle_round(card, current, cost, stamina_before)

    def _maximize_battle_count(self, unit_cost, current, target):
        plus = self.find_one(SHOP_PLUS_FEATURE, threshold=0.8)
        if plus is None:
            self._raise_with_evidence(f'作战界面没有匹配到「+」按钮模板 {SHOP_PLUS_FEATURE}')
        cost = self._read_battle_cost()
        if cost is None:
            self._raise_with_evidence('作战界面读不到「挑战」按钮上的消耗数字，无法确认战斗次数')
        cap = max(1, int(self.config.get('最多战斗次数', 6) or 6))
        if unit_cost:
            needed = max(unit_cost, target - current)
            cap = max(1, min(cap, math.ceil(needed / unit_cost)))
            self.log_info(f"目标还剩 {max(0, target - current)} 精力，本轮挑战次数上限 {cap}")
        target_cost = cap * unit_cost if unit_cost else None
        clicks = 0
        while clicks < cap + 2:
            if target_cost is not None and cost >= target_cost:
                break
            previous = cost
            self.click(plus, after_sleep=0.4)
            clicks += 1
            cost = self._read_battle_cost()
            if cost is None:
                self.log_warning('点「+」之后读不到消耗数字，停止增加战斗次数')
                break
            if cost <= previous:
                self.log_info(f'战斗次数已到上限（消耗 {previous} → {cost}）')
                break
        self.log_info(f"挑战次数拉满，提示消耗 {cost} 精力（点「+」{clicks} 次）")
        return cost

    def _verify_battle_round(self, card, current, cost, stamina_before):
        verified = False
        after = self._read_stamina(STAMINA_PANEL_REGION)
        if stamina_before and after:
            verified = True
            spent = stamina_before[0] - after[0]
            self.log_info(f"体力 {stamina_before[0]} → {after[0]}，本轮减少 {spent}（挑战提示消耗 {cost}）")
            if spent <= 0:
                self._raise_with_evidence(f'作战后体力没有减少（{stamina_before[0]} → {after[0]}），判定作战未生效')
            if cost and spent > cost:
                self._raise_with_evidence(f'体力减少 {spent} 超过挑战提示的 {cost}，请人工确认作战界面是否改版')
        else:
            self.log_warning('读不到顶部体力数字，跳过体力校验')
        fresh = self._find_stamina_card()
        if fresh is None:
            self.log_warning('作战后没找到「消耗精力」卡片，跳过进度校验')
            if not verified:
                self._raise_with_evidence('作战后既读不到体力数字也找不到「消耗精力」卡片，无法确认作战已生效')
            return
        verified = True
        done, now_current, _ = self._card_progress(fresh)
        self.log_info(f"「{card['title']}」进度 {card['progress']} → {fresh['progress']}")
        if not done and now_current <= current:
            self._raise_with_evidence(f"作战后「{card['title']}」进度没有前进（{card['progress']}）")

    def _open_shop_row(self):
        wanted = str(self.config.get('体力材料') or '').strip()
        row = self._pick_shop_row(self._parse_shop_rows(), wanted)
        if row is not None:
            return self._enter_shop_row(row)
        for tab in SHOP_TABS:
            if tab not in self._shop_tab_names():
                continue
            if not self._click_shop_tab(tab):
                continue
            row = self._pick_shop_row(self._parse_shop_rows(), wanted)
            if row is not None:
                return self._enter_shop_row(row)
        rows = self._parse_shop_rows()
        if not rows:
            self._raise_with_evidence('「勤劳是福」右侧没有解析到任何可前往的体力任务')
        self.log_warning(f"没有找到体力材料「{wanted}」，改用当前页签第一项「{rows[0]['title']}」")
        return self._enter_shop_row(rows[0])

    def _pick_shop_row(self, rows, wanted):
        if not rows:
            return None
        if not wanted:
            return rows[0]
        for row in rows:
            if wanted in row['title']:
                return row
        return None

    def _enter_shop_row(self, row):
        if row['cost'] is None:
            self.log_warning(f"「{row['title']}」读不到单次精力消耗，跳过目标预算规划")
        self.log_info(f"前往体力任务「{row['title']}」，单次消耗 {row['cost']} 精力")
        self.click(row['click_x'], row['click_y'], after_sleep=2)
        return row

    def _parse_shop_rows(self):
        boxes = [box for box in self.ocr(box=self.box_of_screen(*SHOP_ROWS_REGION)) if box.confidence >= MIN_CONFIDENCE]
        buttons = sorted((box for box in boxes if box.name.strip() == BUTTON_GO), key=lambda box: box.y)
        band = SHOP_ROW_BAND * self.height
        rows = []
        for button in buttons:
            center_y = button.y + button.height / 2
            row_boxes = [box for box in boxes
                         if abs(box.y + box.height / 2 - center_y) <= band and box.x + box.width <= button.x]
            cost = None
            for box in sorted(row_boxes, key=lambda item: -item.x):
                match = NUMBER_IN_TEXT_PATTERN.search(box.name)
                if match:
                    cost = int(match.group(1))
                    break
            title = normalize_title(''.join(box.name for box in sorted(row_boxes, key=lambda item: item.x)
                                            if not NUMBER_IN_TEXT_PATTERN.search(box.name)))
            if not title:
                continue
            rows.append({
                'title': title,
                'cost': cost,
                'button_box': button,
                'click_x': int(button.x + button.width / 2),
                'click_y': int(center_y),
            })
        return rows

    def _shop_tab_names(self):
        boxes = self.ocr(box=self.box_of_screen(*SHOP_TAB_REGION))
        return [box.name.strip() for box in boxes if box.name.strip() in SHOP_TABS]

    def _click_shop_tab(self, name):
        for box in self.ocr(box=self.box_of_screen(*SHOP_TAB_REGION)):
            if box.name.strip() == name:
                self.log_info(f"切换到「{name}」页签")
                self.click(box, after_sleep=1.0)
                return True
        return False

    def _read_battle_header(self):
        boxes = self.ocr(box=self.box_of_screen(*BATTLE_HEADER_REGION))
        return ''.join(box.name for box in sorted(boxes, key=lambda item: item.x)).strip()

    def _read_battle_cost(self):
        for box in self.ocr(box=self.box_of_screen(*BATTLE_BUTTON_REGION)):
            text = box.name.strip()
            if CHALLENGE_PATTERN.match(text):
                continue
            match = NUMBER_IN_TEXT_PATTERN.search(text)
            if match:
                return int(match.group(1))
        return None

    def _read_stamina(self, region):
        for box in self.ocr(box=self.box_of_screen(*region)):
            match = STAMINA_PATTERN.search(box.name)
            if match:
                return int(match.group(1)), int(match.group(2))
        return None

    def _click_challenge(self):
        box = self.find_one(CHALLENGE_FEATURE, threshold=0.8)
        if box is None:
            matches = self.ocr(box=self.box_of_screen(*BATTLE_BUTTON_REGION), match=CHALLENGE_PATTERN)
            box = matches[0] if matches else None
        if box is None:
            self._raise_with_evidence('作战界面没有找到「挑战」按钮')
        self.log_info(f'点击「挑战」开始战斗: {box}')
        self.click(box, after_sleep=3)
        self.screenshot('daily_battle_started')

    def _is_duel_lineup(self):
        return bool(self.ocr(box=self.box_of_screen(*DUEL_BUTTON_REGION), match=DUEL_PATTERN))

    def _start_duel(self, timeout=20):
        if not self._wait_until(self._is_duel_lineup, timeout):
            self._raise_with_evidence(f'点「挑战」后 {timeout} 秒内没出现「开始对决」阵容界面')
        box = self.find_one(DUEL_FEATURE, threshold=0.8)
        if box is None:
            matches = self.ocr(box=self.box_of_screen(*DUEL_BUTTON_REGION), match=DUEL_PATTERN)
            box = matches[0] if matches else None
        if box is None:
            self._raise_with_evidence('阵容界面没有找到「开始对决」按钮')
        self.log_info(f'点击「开始对决」: {box}')
        self.click(box, after_sleep=3)
        self.screenshot('daily_duel_started')

    def _battle_timeout(self):
        return max(120, int(self.config.get('作战等待秒数', 600) or 600))

    def _wait_battle_finished(self, timeout):
        # 先等作战准备/阵容界面被战斗画面顶掉，否则会把"刚开打"误判成"已经打完"
        leave_deadline = time.time() + 30
        while time.time() < leave_deadline:
            self.next_frame()
            if self._is_level_warning():
                self._confirm_level_warning(2)
                continue
            if not self._is_battle_prepare_open() and not self._is_duel_lineup():
                break
            self.sleep(1)
        else:
            self.log_warning('点「开始对决」30 秒后仍停在准备/阵容界面，继续按结算等待')
        deadline = time.time() + timeout
        last_log = time.time()
        while time.time() < deadline:
            self.next_frame()
            if self._is_battle_result():
                return 'result'
            if self._is_daily_panel_open():
                return 'daily'
            if self._is_stamina_shop_open():
                return 'shop'
            if self._is_duel_lineup():
                return 'lineup'
            if self._is_battle_prepare_open():
                return 'battle'
            if self._is_in_main_world():
                return 'main'
            if self._is_level_warning():
                self._confirm_level_warning(2)
            if time.time() - last_log > 15:
                self.log_info('作战进行中，等待结算…')
                last_log = time.time()
            self.sleep(2)
        self._raise_with_evidence(f'等待作战结算超时（{timeout} 秒内没有回到已知界面）')

    def _return_to_daily_panel(self):
        for _ in range(30):
            self.next_frame()
            if self._is_daily_panel_open():
                return
            if self._close_blank_popup():
                continue
            if self._is_battle_result():
                self._exit_battle_result()
                continue
            if self._is_level_warning():
                self._confirm_level_warning(2)
                continue
            if self._is_stamina_shop_open():
                self.log_info('从「勤劳是福」切回日常活跃签页')
                self.click(*DAILY_TAB_POINT, after_sleep=1.2)
                if self._wait_until(self._is_daily_panel_open, 3):
                    return
                self.log_info('切签页失败，关闭 F3 面板回主世界重开')
                self.click(*CLOSE_POINT, after_sleep=1.2)
            elif self._is_duel_lineup():
                self.log_info('退出对决阵容界面')
                self.send_key('esc', after_sleep=1.5)
            elif self._is_battle_prepare_open():
                self.log_info('退出作战界面')
                self.send_key('esc', after_sleep=1.2)
            elif self._is_in_main_world():
                self.log_info('已回到主世界，重新打开 F3 面板')
                self._open_daily_panel()
                return
            else:
                self.sleep(1)
        self._raise_with_evidence('作战结束后没能回到日常活跃面板')

    def _is_battle_result(self):
        return bool(self.ocr(match=BATTLE_RESULT_PATTERN))

    def _is_level_warning(self):
        return bool(self.ocr(match=LEVEL_WARNING_PATTERN))

    def _confirm_level_warning(self, timeout=6):
        if not self._wait_until(self._is_level_warning, timeout):
            return False
        matches = self.ocr(box=self.box_of_screen(*LEVEL_CONFIRM_REGION), match=CONFIRM_PATTERN)
        if not matches:
            self._raise_with_evidence('作战前出现等级不足提示，但没找到「确认」按钮')
        self.log_info('上阵精灵等级低于推荐，点击「确认」继续挑战')
        self.screenshot('daily_battle_level_warning')
        self.click(matches[0], after_sleep=2)
        return True

    def _exit_battle_result(self):
        matches = self.ocr(match=EXIT_PATTERN)
        if not matches:
            self._raise_with_evidence('战斗结算界面没有找到「退出」按钮')
        self.log_info('战斗结算完成，点击「退出」')
        self.screenshot('daily_battle_result')
        self.click(matches[0], after_sleep=2)

    def _is_stamina_shop_open(self):
        return bool(self.ocr(box=self.box_of_screen(*SHOP_TITLE_REGION), match=SHOP_TITLE_PATTERN))

    def _is_battle_prepare_open(self):
        return bool(self.ocr(box=self.box_of_screen(*BATTLE_COUNT_REGION), match=BATTLE_COUNT_PATTERN))


    def _close_panel(self):
        for _ in range(5):
            self.next_frame()
            if self._close_blank_popup():
                continue
            if self._is_reward_popup():
                self._close_reward_popup()
                continue
            if self._is_daily_panel_open():
                self.log_info("关闭日常活跃面板")
                self.click(*CLOSE_POINT, after_sleep=1)
            if self._wait_until(self._is_in_main_world, 3):
                break
        else:
            if not (self._escape_unknown_screens(4) and self._wait_until(self._is_in_main_world, 2)):
                self._raise_with_evidence("关闭面板后未能确认回到主世界")
        self._close_blank_popup()
        self.log_info("已回到主世界")

    def _is_in_main_world(self):
        return all(self.find_one(name, threshold=MAIN_WORLD_THRESHOLD) for name in MAIN_WORLD_FEATURES)

    def _is_daily_panel_open(self):
        return bool(self.ocr(box=self.box_of_screen(*PANEL_HEADER_REGION), match=PANEL_TITLE_PATTERN))

    def _is_daily_tab(self):
        return bool(self.ocr(box=self.box_of_screen(*DAILY_TAB_REGION), match=DAILY_TAB_PATTERN))

    def _wait_until(self, predicate, timeout, interval=0.5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.next_frame()
            if predicate():
                return True
            self.sleep(interval)
        return False

    def _raise_with_evidence(self, reason):
        self.screenshot("daily_activity_failed")
        self.ocr(log=True)
        raise TaskDisabledException(f"{reason}，已保存截图与当前全量 OCR 文本，请检查界面是否改版或停在未知页面")
