from __future__ import annotations

from qfluentwidgets import FluentIcon

from src.tasks.map_trade.collector import Collector
from src.tasks.map_trade.navigator import Navigator
from src.tasks.map_trade.progress import ProgressStore
from src.tasks.map_trade.vision import Vision
from src.tasks.MapTradeTask import (
    MAP_OCR_THRESHOLD_KEY,
    MAP_VISION_THRESHOLD_KEY,
    MapAutomationTaskBase,
)


class MapCollectionTask(MapAutomationTaskBase):
    """Weekly map collection card with its own UI and configuration."""
    recover_home_on_failure = True
    start_from_home = True

    vision_threshold_key = MAP_VISION_THRESHOLD_KEY
    ocr_threshold_key = MAP_OCR_THRESHOLD_KEY
    task_log_name = "跑图"
    diagnostic_prefix = "map_collection"
    status_keys = [
        "启用",
        "状态",
        "当前阶段",
        "导航状态",
        "主页小屋按钮",
        "主页亮度",
        "主页抽抽乐 OCR",
        "目标卡带",
        "剧情角标",
        "卡带滚轮",
        "卡带吸取状态",
        "卡带压制状态",
        "卡带完成度",
        "箱庭确认信号",
        "箱庭技能组状态",
        "箱庭技能组切换",
        "箱庭进一步确认",
        "箱庭复合确认",
        "箱庭稳定确认",
        "箱庭交互按钮",
        "箱庭地图传送阵候选",
        "箱庭地图传送阵模板",
        "传送阵地图传送阵候选",
        "传送阵地图传送阵点击中心",
        "传送阵地图返回按钮",
        "采集进度",
        "区域地图",
        "探查倒计时",
        "探查图标",
        "吸收图标",
        "召集图标",
        "压制图标",
        "吸取次数",
        "召集次数",
        "压制次数",
        "吸收状态",
        "召集状态",
        "压制状态",
        "每日技能进度",
        "完成",
        "失败",
        "跳过",
        "Log",
        "Warning",
        "Error",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "每周跑图"
        self.description = (
            "按周进度跑剧情卡带；每天最多7张，每张安全区吸收1次，"
            "战斗区域1、2各执行吸收、召集、压制。"
        )
        self.icon = FluentIcon.GLOBE
        # Shown and part of 一键完成日常 (user, 2026-09-28): it runs every day
        # until the day's skill counts are used, progress kept per week
        # (reset Monday 08:00).
        self.group_name = "日常/周常"
        self.group_icon = FluentIcon.CALENDAR
        self.visible = True

        self.default_config.update(
            {
                "启用": True,
                "执行地图采集": True,
                MAP_VISION_THRESHOLD_KEY: 0.72,
                MAP_OCR_THRESHOLD_KEY: 0.20,
                "加载页面等待秒数": 15.0,
                "卡带单步重试次数": 2,
                "本次最多卡带数": 0,
                "跑图章节": "全部",
            }
        )
        self.config_description.update(
            {
                "执行地图采集": (
                    "按周进度处理剧情卡带；每日吸收上限21次，因此最多完成7张。"
                    "第14章在专用流程完成前安全跳过。"
                ),
                MAP_VISION_THRESHOLD_KEY: "卡带、导航与采集技能模板的最低匹配可信度。",
                MAP_OCR_THRESHOLD_KEY: "技能次数和按钮识别的最低可信度。",
                "加载页面等待秒数": "进入卡带、传送或换图后画面卡住多久算失败；自动移动中的时间不算。",
                "卡带单步重试次数": "单张卡带进入或单步操作失败时的尝试次数。",
                "本次最多卡带数": "本次运行最多完成几张卡带；0 表示直到今日技能次数用完。",
                "跑图章节": "只跑这些章节，例如 8-13 或 1,3,5，角色卡 R1-R7，活动卡 E1-E7；全部 = 不限。",
            }
        )
        self.config_type.update(
            {
                "执行地图采集": {
                    "sub_configs": {
                        True: [
                            MAP_VISION_THRESHOLD_KEY,
                            MAP_OCR_THRESHOLD_KEY,
                            "加载页面等待秒数",
                            "卡带单步重试次数",
                            "本次最多卡带数",
                        ]
                    }
                },
                MAP_VISION_THRESHOLD_KEY: {"min": 0.50, "max": 0.95, "step": 0.01},
                MAP_OCR_THRESHOLD_KEY: {"min": 0.05, "max": 0.95, "step": 0.01},
                "加载页面等待秒数": {"min": 10.0, "max": 120.0, "step": 1.0},
                "卡带单步重试次数": {"min": 1, "max": 5},
                "本次最多卡带数": {"min": 0, "max": 7},
            }
        )

    def run(self):
        if not bool(self.config.get("启用", True)):
            self.info_set("状态", "跑图已禁用。")
            return True
        return self._run_collection()

    def _run_collection(self):

        vision = Vision(self)
        navigator = Navigator(self, vision)
        progress = ProgressStore()
        progress.load()
        collector = Collector(self, vision, navigator, progress)
        return self._run_phases(
            navigator,
            (("地图采集", "执行地图采集", collector.run),),
        )


class MapRouteTestTask(MapCollectionTask):
    """Walk each chosen card's three collection maps without any skill.

    Leo 2026-09-29: skills are the same on every map and each chapter's can
    only be pressed once a week, so routes are tuned on their own.  Nothing
    is written to the weekly progress.
    """

    recover_home_on_failure = True
    start_from_home = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "跑图路线测试"
        self.description = "只走每章三张采集地图的路线，不放技能、不记进度（开发用）。"
        self.visible = False
        self.default_config.update({"测试章节": "1-7"})
        self.config_description.update({"测试章节": "例如 6、1-7、8,9,10、14；角色卡 R1、R1-R7；活动卡 E1-E7。"})

    def _chosen_cards(self):
        from src.tasks.map_trade.collector import chapter_filter
        from src.tasks.map_trade.models import COLLECTABLE_CARDS

        wanted = chapter_filter(self.config.get("测试章节", "1-7"))
        if wanted is None:
            return list(COLLECTABLE_CARDS)
        return [card for card in COLLECTABLE_CARDS if card.filter_key in wanted]

    def _run_collection(self):
        vision = Vision(self)
        navigator = Navigator(self, vision)
        progress = ProgressStore()
        progress.load()
        collector = Collector(self, vision, navigator, progress)
        results = []
        for card in self._chosen_cards():
            results.append(self._walk_card(navigator, collector, card))
            self.info_set("路线测试结果", "；".join(results))
        self.log_info("跑图路线测试：" + "；".join(results))
        navigator.return_home()
        return all("通过" in line for line in results)

    def _walk_card(self, navigator, collector, card) -> str:
        from time import monotonic

        started = monotonic()
        selected = navigator.select_collection_card(card.card_id, enter_visually_complete=True)
        if not selected.success:
            return f"{card.label} 进入卡带失败"
        here = navigator.current_collection_target(card)
        current = next((t for t in card.targets if t.key == here), None)
        steps = []
        order = list(card.targets)
        if here == order[-1].key:
            from src.tasks.map_trade.models import LAST_MAP_THEN_TOWN_CARD_IDS

            if card.card_id in LAST_MAP_THEN_TOWN_CARD_IDS:
                order = order[-1:] + order[:-1]
            else:
                order.reverse()
        elif here != order[0].key:
            # Same rule as the collector: anywhere else -> hunting ground (or 艾琳) -> town.
            reset = navigator.prepare_collection_main_area(card.card_id, via_hunting_ground=True)
            if not reset.success:
                return f"{card.label} 回主城失败（{reset.message}）"
            current = card.targets[0]
            steps.append("回主城→" + current.title + f"{monotonic() - started:.0f}s")
        restarted = False
        index = 0
        while index < len(order):
            target = order[index]
            step_start = monotonic()
            arrived = collector._go_to_collection_target(card, current, target)
            if arrived is not None and not arrived.success:
                self.log_warning(f"跑图路线测试：{card.label}前往{target.title}失败：{arrived.message}")
                if restarted:
                    return f"{card.label} {target.title} 失败（{arrived.message}）"
                # Same as the collector: one restart via the hunting ground
                # (or 艾琳) -> the town -> the forward route.
                restarted = True
                reset = navigator.prepare_collection_main_area(card.card_id, via_hunting_ground=True)
                if not reset.success:
                    return f"{card.label} 回主城失败（{reset.message}）"
                current = card.targets[0]
                order = list(card.targets)
                index = 0
                steps.append(f"{target.title}失败→回主城{monotonic() - step_start:.0f}s")
                continue
            index += 1
            current = target
            steps.append(f"{target.title}{monotonic() - step_start:.0f}s")
            self.log_info(f"跑图路线测试：{card.label}到达{target.title}。")
        return f"{card.label} 通过 {monotonic() - started:.0f}s（{' → '.join(steps)}）"
