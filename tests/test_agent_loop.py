from ggge_ai.agent.loop import AgentLoop, LoopConfig
from ggge_ai.goap.action import Action, ExecutionContext
from ggge_ai.domain.goals import ReachScreen
from ggge_ai.domain.translate import to_world_state
from ggge_ai.perception.base import GameState


class FakeDevice:
    """Simulates screen transitions driven by executed actions."""

    def __init__(self, initial_screen, flaky_at=None):
        self.screen = initial_screen
        self.flaky_at = flaky_at
        self.taps = 0


class FakeNavigate(Action):
    def __init__(self, device, from_screen, to_screen):
        self.device = device
        self.name = f"{from_screen}->{to_screen}"
        self.preconditions = {"screen": from_screen}
        self.effects = {"screen": to_screen}

    def execute(self, ctx: ExecutionContext) -> bool:
        self.device.taps += 1
        if self.device.flaky_at == self.device.taps:
            return True  # tap landed but screen did not change
        self.device.screen = self.effects["screen"]
        return True


class FakePerception:
    def __init__(self, device):
        self.device = device

    def observe(self) -> GameState:
        return GameState(screen=self.device.screen, screen_confidence=1.0)


class NullActuator:
    def tap(self, x, y):
        pass

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        pass

    def key(self, keycode):
        pass


def make_loop(device, actions, max_failures=3):
    return AgentLoop(
        perception=FakePerception(device),
        actuator=NullActuator(),
        translator=to_world_state,
        actions=actions,
        config=LoopConfig(settle_delay_s=0, max_consecutive_failures=max_failures),
    )


def chain(device):
    return [
        FakeNavigate(device, "title", "main_menu"),
        FakeNavigate(device, "main_menu", "stage_select"),
        FakeNavigate(device, "stage_select", "battle_map"),
    ]


def test_reaches_goal_through_chain():
    device = FakeDevice("title")
    loop = make_loop(device, chain(device))
    assert loop.run(ReachScreen("battle_map"))
    assert device.screen == "battle_map"


def test_goal_already_satisfied():
    device = FakeDevice("battle_map")
    loop = make_loop(device, chain(device))
    assert loop.run(ReachScreen("battle_map"))
    assert device.taps == 0


def test_recovers_from_transient_failure_by_replanning():
    device = FakeDevice("title", flaky_at=2)
    loop = make_loop(device, chain(device))
    assert loop.run(ReachScreen("battle_map"))
    assert device.taps == 4


def test_gives_up_when_goal_unreachable():
    device = FakeDevice("battle_map")
    loop = make_loop(device, chain(device))
    assert not loop.run(ReachScreen("title"))
