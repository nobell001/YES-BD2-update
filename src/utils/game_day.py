"""Single source for the Brown Dust II game-day boundary.

The server refreshes daily content at 08:00 UTC+8 (00:00 UTC, no DST): the
in-game mission timer and the trade stock refresh both confirm it.  Weekly
content refreshes at the same hour on Monday.
"""

from datetime import timedelta, timezone

GAME_TZ = timezone(timedelta(hours=8))
DAILY_REFRESH_HOUR = 8
