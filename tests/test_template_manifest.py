import cv2
import numpy as np
import pytest

from ggge_ai.vision.manifest import TemplateEntry, TemplateManifest

rng = np.random.default_rng(seed=7)


def make_screen(patches: dict[tuple[int, int], np.ndarray], size=(400, 300)) -> np.ndarray:
    img = np.full((size[1], size[0], 3), 32, dtype=np.uint8)
    for (x, y), patch in patches.items():
        ph, pw = patch.shape[:2]
        img[y : y + ph, x : x + pw] = patch
    return img


def patch(w=40, h=30):
    return rng.integers(0, 255, (h, w, 3), dtype=np.uint8)


@pytest.fixture
def workspace(tmp_path):
    anchor_a = patch()
    anchor_b = patch()
    button = patch(60, 24)

    screen_a = make_screen({(10, 10): anchor_a, (200, 250): button})
    screen_b = make_screen({(10, 10): anchor_b})

    root = tmp_path / "templates"
    (root / "screens").mkdir(parents=True)
    (root / "elements").mkdir(parents=True)
    cv2.imwrite(str(root / "screens/screen_a.png"), anchor_a)
    cv2.imwrite(str(root / "screens/screen_b.png"), anchor_b)
    cv2.imwrite(str(root / "elements/btn_go.png"), button)

    manifest = TemplateManifest(root=root)
    manifest.screens["screen_a"] = TemplateEntry(
        id="screen_a", file="screens/screen_a.png", search_region=(0, 0, 100, 100)
    )
    manifest.screens["screen_b"] = TemplateEntry(id="screen_b", file="screens/screen_b.png")
    manifest.elements["btn_go"] = TemplateEntry(
        id="btn_go", file="elements/btn_go.png", screen="screen_a"
    )
    manifest.save()
    return root, screen_a, screen_b


def test_manifest_round_trip(workspace):
    root, _, _ = workspace
    loaded = TemplateManifest.load(root)
    assert set(loaded.screens) == {"screen_a", "screen_b"}
    assert loaded.screens["screen_a"].search_region == (0, 0, 100, 100)
    assert loaded.elements["btn_go"].screen == "screen_a"
    assert loaded.element_ids_by_screen() == {"screen_a": ["btn_go"]}


def test_screen_classification(workspace):
    root, screen_a, screen_b = workspace
    recognizer = TemplateManifest.load(root).build_recognizer()

    top = recognizer.classify_screen(screen_a)[0]
    assert top.screen == "screen_a"
    assert top.confidence > 0.99

    top = recognizer.classify_screen(screen_b)[0]
    assert top.screen == "screen_b"


def test_element_detection_position(workspace):
    root, screen_a, _ = workspace
    recognizer = TemplateManifest.load(root).build_recognizer()
    elements = recognizer.detect_elements(screen_a, ["btn_go"])
    assert len(elements) == 1
    e = elements[0]
    assert e.confidence > 0.99
    assert e.bbox.x == 200 and e.bbox.y == 250


def test_missing_template_file_raises(tmp_path):
    manifest = TemplateManifest(root=tmp_path)
    manifest.screens["ghost"] = TemplateEntry(id="ghost", file="screens/ghost.png")
    with pytest.raises(FileNotFoundError):
        manifest.build_recognizer()
