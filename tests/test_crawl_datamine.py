"""The datamine crawler gives the same bytes for the same upstream (issue #74).

The fixture in tests/fixtures/datamine/ is a recorded slice of the four sources,
so the suite needs no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.crawl_datamine import (
    FORMULA_PATH,
    TABLE_PATHS,
    VERSION_PATH,
    crawl,
    formula_chain,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "datamine"
RECORDED = {
    VERSION_PATH: "version.json",
    TABLE_PATHS["unit"]: "unit.json",
    TABLE_PATHS["weapon"]: "weapon.json",
    TABLE_PATHS["stage"]: "stage.json",
    FORMULA_PATH: "formula.html",
}
VERSION = "202608161248"
SOURCE = "https://example.invalid"


def _fetch(path: str) -> bytes:
    return (FIXTURES / RECORDED[path]).read_bytes()


def _reordered(value):
    if isinstance(value, dict):
        return {key: _reordered(item) for key, item in reversed(list(value.items()))}
    if isinstance(value, list):
        return [_reordered(item) for item in value]
    return value


def _fetch_reordered(path: str) -> bytes:
    blob = _fetch(path)
    if path == FORMULA_PATH:
        return blob
    return json.dumps(_reordered(json.loads(blob)), ensure_ascii=False).encode("utf-8")


def _manifest(out_dir: Path) -> dict:
    return json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))


def test_the_dump_lands_under_the_version_stamp_of_the_source(tmp_path):
    out_dir = crawl(_fetch, tmp_path, SOURCE)

    assert out_dir == tmp_path / VERSION
    assert sorted(path.name for path in out_dir.iterdir()) == [
        "formula.json",
        "manifest.json",
        "stage.json",
        "unit.json",
        "weapon.json",
    ]


def test_the_manifest_counts_the_rows_of_every_container(tmp_path):
    files = _manifest(crawl(_fetch, tmp_path, SOURCE))["files"]

    assert files["unit.json"]["rows"] == {"unit": 2}
    assert files["weapon.json"]["rows"] == {"weapons": 3, "units": 1}
    assert files["stage.json"]["rows"] == {"stage": 3}
    assert files["formula.json"]["rows"] == {"lines": 17, "notes": 3}


def test_the_manifest_names_the_source_of_every_file(tmp_path):
    files = _manifest(crawl(_fetch, tmp_path, SOURCE))["files"]

    assert files["unit.json"]["path"] == TABLE_PATHS["unit"]
    assert files["formula.json"]["path"] == FORMULA_PATH
    assert files["formula.json"]["kind"] == "extracted"
    assert files["unit.json"]["kind"] == "json"


def test_the_manifest_names_the_address_that_the_run_crawled(tmp_path):
    assert _manifest(crawl(_fetch, tmp_path, SOURCE))["source"] == SOURCE


@pytest.mark.parametrize("version", ["../escape", "2026/08/16", "/absolute", "", "."])
def test_a_stamp_that_is_no_directory_name_stops_the_crawl(tmp_path, version):
    def fetch(path: str) -> bytes:
        if path != VERSION_PATH:
            return _fetch(path)
        return json.dumps({"version": version}).encode("utf-8")

    with pytest.raises(ValueError):
        crawl(fetch, tmp_path, SOURCE)
    assert list(tmp_path.iterdir()) == []


def test_a_publish_during_the_crawl_stops_the_crawl(tmp_path):
    stamps = [VERSION, "202700000000"]

    def fetch(path: str) -> bytes:
        if path != VERSION_PATH:
            return _fetch(path)
        return json.dumps({"version": stamps.pop(0)}).encode("utf-8")

    with pytest.raises(RuntimeError):
        crawl(fetch, tmp_path, SOURCE)
    assert list(tmp_path.iterdir()) == []


def test_the_tab_panel_search_reads_the_whole_opening_tag():
    page = _fetch(FORMULA_PATH).decode("utf-8")
    swapped = page.replace(
        '<div data-slot="tabs-content" class="flex-1 outline-none" id="bits-s56"'
        ' role="tabpanel" hidden="" tabindex="0" data-value="formula"',
        '<div data-value="formula" data-slot="tabs-content" class="flex-1 outline-none"'
        ' id="bits-s56" role="tabpanel" hidden="" tabindex="0"',
    )

    assert swapped != page
    assert formula_chain(swapped) == formula_chain(page)


def test_a_second_run_against_the_same_upstream_writes_the_same_bytes(tmp_path):
    first = crawl(_fetch, tmp_path / "first", SOURCE)
    second = crawl(_fetch, tmp_path / "second", SOURCE)

    for path in sorted(first.iterdir()):
        assert path.read_bytes() == (second / path.name).read_bytes(), path.name


def test_a_reordering_of_the_upstream_keys_writes_the_same_bytes(tmp_path):
    first = crawl(_fetch, tmp_path / "first", SOURCE)
    second = crawl(_fetch_reordered, tmp_path / "second", SOURCE)

    for path in sorted(first.iterdir()):
        assert path.read_bytes() == (second / path.name).read_bytes(), path.name


def test_the_formula_chain_is_the_damage_chain_of_the_page():
    chain = formula_chain(_fetch(FORMULA_PATH).decode("utf-8"))

    assert chain["lines"][0].startswith("characterStatRatio = ")
    assert chain["lines"][-1].startswith("finalDamage = ")
    terrain_line = "battleDamage = RoundUp((baseDamage + damageCorrection) * terrainCorrection)"
    assert terrain_line in chain["lines"]
    assert chain["notes"][0].startswith("For weapon with multiple types")


def test_the_formula_chain_holds_no_value_of_the_calculator_tab():
    chain = formula_chain(_fetch(FORMULA_PATH).decode("utf-8"))

    assert all("31855" not in line for line in chain["lines"] + chain["notes"])
