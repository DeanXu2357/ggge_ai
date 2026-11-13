from ggge_ai_2.mapparser.contract import MapScope
from tests.ggge_ai_2.dataset import Case


# Warning: the scope has no occluded rectangles until the element detectors cover the HUD
# (task B2 of roadmap section 8.14).
def scope_of(case: Case) -> MapScope:
    return MapScope((), case.screen == "player_phase_overview")
