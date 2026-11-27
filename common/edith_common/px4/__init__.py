"""PX4 behaviour shared by MockVehicle, the companion's AssetAdapter and the lint (C62).

Owned by WS-D (docs/OWNERS.yaml) although it sits under ``common/``. See docs/spec/sim.md §2.
"""

from edith_common.px4 import classify, encode, failsafe, modes, search
from edith_common.px4.classify import classify as classify_msg
from edith_common.px4.failsafe import DllFailsafe, dll_countdown_s
from edith_common.px4.modes import mode_from_name, mode_name
from edith_common.px4.search import leg_spacing_m, plan_search

__all__ = [
    "DllFailsafe", "classify", "classify_msg", "dll_countdown_s", "encode", "failsafe",
    "leg_spacing_m", "mode_from_name", "mode_name", "modes", "plan_search", "search",
]
