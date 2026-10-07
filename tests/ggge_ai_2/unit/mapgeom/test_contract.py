from __future__ import annotations

from ggge_ai_2.mapgeom.contract import Alignment


def test_alignment_takes_a_world_cell_to_its_view_cell():
    assert Alignment((10, 5)).to_view((12, 7)) == (2, 2)
