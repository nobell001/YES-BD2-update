"""主页's cartridge machine (P) and the 游戏卡珍藏集 page it opens.

镜中之战 is entered from here, never through 返回战场: entering any card makes
it the recent one, so after 常客 返回战场 led into 格鲁菲餐厅 and PVP failed
(clone 2026-10-11).  Leo: 「一律回主頁 進鏡中之戰」, 「從主頁進 就點右下角的卡帶
p按鍵那邊」.  The machine shows the recent card's art, so it is pressed by its
place once 主页 is confirmed, never matched by its picture.

All points are 1920x1080 reference, read from Leo's 4K frames of 10-11.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.utils.ocr_utils import normalize_ocr_text

HOME_CARTRIDGE_MACHINE_POINT = (1691, 980)
HOME_CARTRIDGE_MACHINE_ATTEMPTS = 2
# Leo 10-11: 「可以不只認p嗎 感覺不夠穩」, then 「認p就好 f上面是直接返回卡帶」 and
# 「如果識別不穩時 也可以按畫面上固定位置右下角那一大塊」.  Before the press the P
# key cap under the machine must show on two frames in a row; it never
# changes with the recent card.  Live 4K/2K/1080p 主页: 0.95-0.98; 珍藏集,
# 餐厅, 公会, fields: no match.  Unsteady → the same fixed place is pressed
# anyway and the 珍藏集 title still decides.
HOME_KEYCAP_P_ROI = (1648, 1002, 90, 86)
HOME_KEYCAP_STEADY_FRAMES = 2
HOME_KEYCAP_READS = 4

COLLECTION_TITLE_PATTERNS = ("游戏卡珍藏集", "遊戲卡珍藏集")
COLLECTION_TITLE_ROI = (200, 10, 400, 80)
BATTLE_ROW_PATTERNS = ("战斗玩法游戏卡带", "戰鬥玩法遊戲卡帶")

# From a row header's left edge and middle to the centre of the row's first
# card (MIRROR WARS under 战斗玩法), clear of the card's "+" corner button.
FIRST_CARD_OFFSET = (108, 120)
CARD_PITCH_X = 280
# A card whose centre would sit below this is cut off by the screen edge.
CARD_LOWEST_Y = 1000

# Where the shelf is scrolled when the wanted row is not on screen.
COLLECTION_SCROLL_POINT = (0.5, 0.55)
COLLECTION_SCROLL_NOTCHES = 3
COLLECTION_SCROLLS_UP = 2
COLLECTION_SCROLLS_DOWN = 4
# Two reads of the header must agree this closely before a card is pressed.
ROW_HEADER_AGREE_PX = 15


@dataclass(frozen=True)
class RowHeader:
    left: float
    middle: float


def find_row_header(boxes, patterns, frame_size) -> RowHeader | None:
    """The row header's left edge and middle in 1080p reference pixels."""

    width, height = frame_size
    wanted = [normalize_ocr_text(pattern) for pattern in patterns]
    for box in boxes:
        label = normalize_ocr_text(getattr(box, "name", ""))
        if not any(pattern in label for pattern in wanted):
            continue
        values = [getattr(box, key, None) for key in ("x", "y", "width", "height")]
        if any(value is None for value in values):
            continue
        x, y, _box_width, box_height = (float(value) for value in values)
        return RowHeader(
            left=x * 1920 / width,
            middle=(y + box_height / 2) * 1080 / height,
        )
    return None


def row_card_point(header: RowHeader, column: int = 0) -> tuple[int, int] | None:
    """Centre of the row's card in ``column``; None while it is cut off."""

    x = round(header.left + FIRST_CARD_OFFSET[0] + CARD_PITCH_X * column)
    y = round(header.middle + FIRST_CARD_OFFSET[1])
    if y > CARD_LOWEST_Y:
        return None
    return x, y


def headers_agree(first: RowHeader, second: RowHeader) -> bool:
    return (
        abs(first.left - second.left) <= ROW_HEADER_AGREE_PX
        and abs(first.middle - second.middle) <= ROW_HEADER_AGREE_PX
    )
