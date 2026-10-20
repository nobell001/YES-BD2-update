"""梦幻广场 (Fantasia Square): how its cartridge is picked and how it is told
apart from other fields.  Shared by 广场女神像 and 跑商, which trades at the
square's merchant since Leo 2026-10-20 (「跑商商人我想遷移到廣場去做」)."""

from pathlib import Path

from src.utils.calibration import FHD_1080, HD_720
from src.utils.vision_models import TemplateSpec

# Slot 2 of the 生活玩法游戏卡带 tab on the quick-switch page (1080p client).
SQUARE_CARTRIDGE_SLOT_POINT = (331 / FHD_1080.width, 970 / FHD_1080.height)


def _hd720_to_1080_roi(x: int, y: int, width: int, height: int) -> tuple[int, int, int, int]:
    def point(px: int, py: int) -> tuple[int, int]:
        return (
            round(px * FHD_1080.width / HD_720.width),
            round(py * FHD_1080.height / HD_720.height),
        )

    left, top = point(x, y)
    right, bottom = point(x + width, y + height)
    return left, top, max(1, right - left), max(1, bottom - top)


# The mirror icon in the square's bottom bar (虚拟角色); the 镜中之战 hub and
# the story fields have none (Leo's 2K frames 2026-10-20: 0.952 in the square,
# no match in the hub).
FANTASIA_SQUARE_TEMPLATE = TemplateSpec(
    name="fantasia_square",
    file_name="image/Mirror_FantasiaSquare_Ico.png",
    threshold_key="梦幻广场阈值",
    default_threshold=0.78,
    roi=_hd720_to_1080_roi(656, 622, 77, 66),
)

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "recognition-assets" / "template-assets"


def square_shown(frame, config, cache: dict) -> bool:
    """The square's bottom-bar icon on this frame."""
    from src.utils import task_vision

    config = config or {}
    result = task_vision.match_template(
        frame, FANTASIA_SQUARE_TEMPLATE, config, TEMPLATE_DIR, cache, min_size=5
    )
    return task_vision.passes_match(result, FANTASIA_SQUARE_TEMPLATE, config)
