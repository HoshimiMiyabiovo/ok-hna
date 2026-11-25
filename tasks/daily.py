"""日常活跃：扫描「每日目标」全部任务并领取已完成奖励。

流程：主世界 → F3 图标（模板 main_world_f3_menu，备用 F3 快捷键）打开面板 →
左侧中间「日常活跃」入口 → 每日目标为横向卡片列表，一屏只露出 4 张多一点，
必须向左拖动才能拿全；拖动后画面不再变化即视为到达末尾。

卡片解析全部基于 OCR + 颜色：
- 进度徽章 x/y 作为每张卡的锚点，x>=y 视为已完成；
- 底部按钮带没有「前往/进行中/已领取」文字且金色占比够高 → 可领取；
- 领取后以顶部「当前活跃度」数字增长做硬校验，校验不过落截图并失败。

比例坐标来自 2026-11-26 实机截图（1919x1049/1051）。
"""

import re
import time

from ok import BaseTask, TaskDisabledException
from ok.feature.Box import Box
from ok.util.process import is_admin

from tasks.launcher import GAME_EXE, MAIN_WORLD_FEATURES, MAIN_WORLD_THRESHOLD, LauncherTask

F3_FEATURE = "main_world_f3_menu"

PANEL_TITLE_PATTERN = re.compile(r"打卡项目|日常活跃")
DAILY_TAB_PATTERN = re.compile(r"每日目标")
PROGRESS_PATTERN = re.compile(r"^(\d+)/(\d+)$")
REWARD_PATTERN = re.compile(r"\+?\s*(\d+)\s*活跃度?")
DIGITS_PATTERN = re.compile(r"^\d+$")
BUTTON_LABELS = ("领取", "前往", "进行中", "已领取")

GOLD_COLOR = {"r": (235, 255), "g": (160, 235), "b": (0, 135)}
MIN_CONFIDENCE = 0.85
GOLD_CLAIMABLE_MIN = 0.25
MAX_SCAN_PAGES = 6

# 以下相对坐标全部实测自 1919x1049/1051 截图
PANEL_HEADER_REGION = (0.15, 0.09, 0.40, 0.20)
DAILY_TAB_REGION = (0.16, 0.32, 0.42, 0.40)
ACTIVITY_TOTAL_REGION = (0.185, 0.25, 0.25, 0.33)
CARD_REGION = (0.175, 0.395, 0.900, 0.875)
FOOTER_REGION_Y = (0.782, 0.862)
CARD_HALF_WINDOW = 0.078
DAILY_TAB_POINT = (0.138, 0.399)
CLOSE_POINT = (0.873, 0.143)
DRAG_FROM = (0.80, 0.62)
DRAG_TO = (0.30, 0.62)


def normalize_title(text):
    # OCR 可能漏掉「」，跨页去重与展示统一用去空白、去书名号后的文本
    return re.sub(r"[\s「」]", "", text or "")


class DailyActivityTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "日常活跃"
        self.description = "扫描「日常活跃」每日目标（向左拖动翻页），领取已完成奖励"

    def run(self):
        if not is_admin():
            raise TaskDisabledException(
                "游戏进程以管理员权限运行，本程序必须以管理员身份启动才能操作游戏窗口（右键程序 → 以管理员身份运行）")
        self._ensure_in_main_world()
        self._open_daily_panel()
        self._scan_and_claim()
        self._close_panel()

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
            self._click_f3_entry()
            if self._wait_until(self._is_daily_panel_open, 5):
                opened = True
                break
            self.log_info(f"第 {attempt} 次点击 F3 后未出现面板，重试")
        if not opened:
            self._raise_with_evidence("未能打开 F3 面板（打卡项目/日常活跃）")
        if not self._is_daily_tab():
            self.log_info("切换到「日常活跃」签页")
            self.click(*DAILY_TAB_POINT, after_sleep=1.2)
            if not self._wait_until(self._is_daily_tab, 4):
                self._raise_with_evidence("未能切换到「日常活跃」签页")
        self.log_info("已进入日常活跃面板")

    def _click_f3_entry(self):
        # HUD 图标会随功能解锁增加而整体左移，放宽水平搜索范围
        f3 = self.find_one(F3_FEATURE, threshold=0.8, horizontal_variance=0.06, vertical_variance=0.02)
        if f3 is not None:
            self.log_info(f"点击主界面 F3 图标: {f3}")
            self.click(f3, after_sleep=1.2)
        else:
            self.log_info("未匹配到 F3 图标，改用 F3 快捷键")
            self.send_key('f3', after_sleep=1.2)

    def _scan_and_claim(self):
        total_before = self._read_activity_total()
        self.log_info(f"当前活跃度: {total_before}")
        seen = {}
        order = []
        claimed = []
        page = 0
        unchanged = 0
        prev_titles = None
        while page < MAX_SCAN_PAGES:
            self.next_frame()
            cards = self._parse_cards()
            if not cards:
                self._raise_with_evidence("当前页没有解析到任何每日目标卡片")
            page_titles = set()
            for card in cards:
                key = normalize_title(card['title'])
                page_titles.add(key)
                if key in seen:
                    continue
                seen[key] = card
                order.append(card)
                if card['claimable'] and self._claim_card(card):
                    card['claimed'] = True
                    claimed.append(card)
            self.log_info(f"第 {page + 1} 屏解析到 {len(cards)} 张卡片: {sorted(page_titles)}")
            if prev_titles is not None and page_titles == prev_titles:
                unchanged += 1
                if unchanged >= 2:
                    self.log_info("向左拖动后卡片不再变化，按已到列表末尾处理")
                    break
            else:
                unchanged = 0
            prev_titles = page_titles
            self.log_info("向左拖动卡片列表翻页")
            self._drag_cards_left()
            page += 1
        total_after = self._read_activity_total()
        if total_after < total_before:
            self._raise_with_evidence(f"活跃度出现倒退（{total_before} → {total_after}），请检查面板状态")
        self.log_info(f"每日目标共 {len(order)} 条:")
        for card in order:
            if card.get('claimed'):
                state = "已领取"
            elif card['claimable']:
                state = "可领取(未领到)"
            else:
                state = card['button'] or "未完成"
            self.log_info(f"  - {card['title']}  {card['progress']}  +{card['reward']}活跃度  [{state}]")
        self.log_info(f"本次领取 {len(claimed)} 条，活跃度 {total_before} → {total_after}")

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
                buttons.append(name)
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
        claimable = done and not buttons and gold >= GOLD_CLAIMABLE_MIN
        return {
            'title': title,
            'progress': anchor.name.strip(),
            'done': done,
            'reward': reward,
            'button': buttons[0] if buttons else None,
            'gold': round(gold, 3),
            'claimable': claimable,
            'claimed': False,
            'claim_x': int(reward_box.x + reward_box.width / 2) if reward_box else int(center_x),
            'claim_y': int((footer_top + footer_bottom) / 2),
        }

    def _claim_card(self, card):
        before = self._read_activity_total()
        for attempt in (1, 2):
            self.log_info(f"领取「{card['title']}」+{card['reward']}活跃度（第 {attempt} 次）")
            self.click(card['claim_x'], card['claim_y'], after_sleep=1.5)
            deadline = time.time() + 4
            while time.time() < deadline:
                total = self._read_activity_total()
                if total >= before + card['reward']:
                    self.log_info(f"活跃度 {before} → {total}，领取成功")
                    return True
                self.sleep(0.5)
        self._raise_with_evidence(f"点击领取「{card['title']}」后活跃度未增加（当前 {before}）")

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

    def _close_panel(self):
        if self._is_daily_panel_open():
            self.log_info("关闭日常活跃面板")
            self.click(*CLOSE_POINT, after_sleep=1)
        if not self._wait_until(self._is_in_main_world, 3):
            if not (self._escape_unknown_screens(4) and self._wait_until(self._is_in_main_world, 2)):
                self._raise_with_evidence("关闭面板后未能确认回到主世界")
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
