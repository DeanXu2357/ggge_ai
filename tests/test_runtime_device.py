"""裝置通道：adb 呼叫組裝、危險帶白名單、解鎖節流、手勢重播。"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from ggge_ai.runtime.device import (
    Adb,
    Key,
    LiveDevice,
    LiveExecutor,
    Settle,
    Swipe,
    Tap,
    TapRefused,
    UnsupportedAction,
    check_tap,
)
from ggge_ai.runtime.perceive import Observation


@dataclass
class FakeAdb:
    commands: list[str] = field(default_factory=list)
    frame: bytes = b"\x89PNG"

    def screencap(self) -> bytes:
        return self.frame

    def shell(self, command: str) -> str:
        self.commands.append(command)
        return ""


@dataclass
class FakeKeyguard:
    checks: int = 0

    def ensure_unlocked(self) -> bool:
        self.checks += 1
        return True


@dataclass
class FakeActuator:
    taps: list[tuple[int, int, str]] = field(default_factory=list)
    swipes: list[tuple[int, int, int, int, float]] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)

    def tap(self, x: int, y: int, intent: str = "") -> None:
        self.taps.append((x, y, intent))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None:
        self.swipes.append((x1, y1, x2, y2, duration_s))

    def key(self, keycode: str) -> None:
        self.keys.append(keycode)


@dataclass
class Clock:
    now: float = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_adb_puts_the_serial_and_the_libusb_env_on_every_call():
    adb = Adb(serial="R5CRC37JBYJ")

    assert adb._argv("exec-out", "screencap -p") == [
        "adb",
        "-s",
        "R5CRC37JBYJ",
        "exec-out",
        "screencap -p",
    ]
    assert adb.env_extra["ADB_LIBUSB"] == "1"


def test_screencap_bytes_reach_the_caller_untouched():
    device = LiveDevice(adb=FakeAdb(frame=b"\x89PNG-native"))

    assert device.screenshot() == b"\x89PNG-native"


def test_taps_and_swipes_become_input_commands():
    adb = FakeAdb()
    device = LiveDevice(adb=adb)

    device.tap(100, 200)
    device.swipe(1164, 430, 1164, 60, 0.35)
    device.key("KEYCODE_HOME")

    assert adb.commands == [
        "input tap 100 200",
        "input swipe 1164 430 1164 60 350",
        "input keyevent KEYCODE_HOME",
    ]


def test_off_screen_coordinates_are_refused_before_they_reach_adb():
    """uiautomator2 對負座標直接 assert crash；這裡先擋下來並說清楚。"""
    adb = FakeAdb()
    device = LiveDevice(adb=adb)

    with pytest.raises(TapRefused):
        device.tap(-1, 100)
    with pytest.raises(TapRefused):
        device.tap(100, 2000)
    with pytest.raises(TapRefused):
        device.swipe(0, 0, 5000, 0)
    assert adb.commands == []


@pytest.mark.parametrize(
    ("point", "band"),
    [
        ((1487, 295), "auto_battle_tristate"),
        ((1773, 295), "auto_battle_tristate"),
        ((410, 860), "battle_menu_abandon"),
        ((752, 865), "battle_menu_abandon"),
        ((2042, 924), "bottom_right_confirm"),
        ((1496, 1010), "auto_deploy"),
        ((1815, 52), "auto_switch"),
    ],
)
def test_the_danger_bands_refuse_an_unintended_tap(point, band):
    with pytest.raises(TapRefused, match=band):
        check_tap(*point)


def test_only_the_declared_intent_gets_through_a_danger_band():
    check_tap(410, 860, intent="abandon")
    check_tap(1815, 52, intent="auto_switch")

    with pytest.raises(TapRefused):
        check_tap(410, 860, intent="auto_switch")
    with pytest.raises(TapRefused):
        # 自動戰鬥三選一沒有任何放行 intent——那是紅線，不是需要小心的操作。
        check_tap(1487, 295, intent="auto_battle_tristate")


def test_the_sortie_button_sits_clear_of_the_auto_deploy_band():
    """出擊 (1930,970) 不在任何帶內、必須無 intent 就放行；同一列左邊的自動編制
    (1496,1010) 會覆蓋編成，任何 intent 都不放行。"""
    check_tap(1930, 970)

    for intent in ("", "confirm", "abandon"):
        with pytest.raises(TapRefused, match="auto_deploy"):
            check_tap(1496, 1010, intent=intent)


def test_the_keyguard_hook_is_throttled_not_per_tap():
    """逐 tap 問一次要 dumpsys＋截圖，太貴；但吞掉的 tap 看起來就是什麼都沒
    發生，所以也不能不問。"""
    clock = Clock()
    keyguard = FakeKeyguard()
    device = LiveDevice(adb=FakeAdb(), keyguard=keyguard, unlock_every_s=30.0, clock=clock.monotonic)

    device.tap(1, 1)
    device.tap(2, 2)
    clock.now += 31.0
    device.tap(3, 3)

    assert keyguard.checks == 2


def test_forcing_the_keyguard_check_bypasses_the_throttle():
    clock = Clock()
    keyguard = FakeKeyguard()
    device = LiveDevice(adb=FakeAdb(), keyguard=keyguard, clock=clock.monotonic)

    device.ensure_unlocked()
    device.ensure_unlocked(force=True)

    assert keyguard.checks == 2


def test_the_executor_replays_a_gesture_sequence_in_order():
    actuator = FakeActuator()
    clock = Clock()
    executor = LiveExecutor(device=actuator, sleep=clock.sleep)

    executor.replay(
        (
            Tap(10, 20, settle_s=0.5),
            Swipe(1, 2, 3, 4, duration_s=0.7, settle_s=1.0),
            Key("KEYCODE_BACK", settle_s=0.25),
            Settle(0.25),
        ),
        label="probe",
    )

    assert actuator.taps == [(10, 20, "")]
    assert actuator.swipes == [(1, 2, 3, 4, 0.7)]
    assert actuator.keys == ["KEYCODE_BACK"]
    assert clock.now == pytest.approx(2.0)


def test_an_operation_that_carries_its_own_gestures_needs_no_plan():
    @dataclass(frozen=True)
    class Fix:
        label: str = "fix"
        gestures: tuple = (Tap(5, 5),)

    actuator = FakeActuator()
    executor = LiveExecutor(device=actuator, sleep=lambda _: None)

    executor.perform(Fix(), Observation(screen="whatever"))

    assert actuator.taps == [(5, 5, "")]


def test_a_planned_action_is_translated_by_its_plan():
    @dataclass(frozen=True)
    class Leave:
        label: str = "leave"

    actuator = FakeActuator()
    executor = LiveExecutor(
        device=actuator,
        plans={Leave: lambda action, observation: (Tap(7, 8, intent="abandon"),)},
        sleep=lambda _: None,
    )

    executor.perform(Leave(), Observation(screen="battle_map"))

    assert actuator.taps == [(7, 8, "abandon")]


def test_an_unplanned_action_stops_the_run_instead_of_doing_nothing():
    executor = LiveExecutor(device=FakeActuator(), sleep=lambda _: None)

    with pytest.raises(UnsupportedAction):
        executor.perform(object(), Observation(screen="battle_map"))


def test_the_executor_journals_what_it_replayed():
    @dataclass
    class FakeJournal:
        entries: list[dict] = field(default_factory=list)

        def record(self, kind: str, **fields) -> dict:
            entry = {"kind": kind, **fields}
            self.entries.append(entry)
            return entry

    journal = FakeJournal()
    executor = LiveExecutor(device=FakeActuator(), journal=journal, sleep=lambda _: None)

    executor.replay((Tap(1, 2),), label="probe")

    assert journal.entries[0]["kind"] == "perform"
    assert journal.entries[0]["label"] == "probe"
    assert len(journal.entries[0]["gestures"]) == 1
