from ggge_ai_2.uisim.contract import Overlay, ScreenIs, UiSim, UiState


class UiSimContract:
    """Subclass per implementation with a start state that has at least one operation."""

    def make(self) -> UiSim:
        raise NotImplementedError

    def test_start_state_has_an_operation(self):
        assert self.make().successors()

    def test_advance_returns_a_new_instance_and_keeps_the_old_one(self):
        sim = self.make()
        before = sim.state
        outcome = sim.successors()[0].outcomes[0]

        after = sim.advance(outcome)

        assert sim.state == before
        assert after.state == outcome.then

    def test_sync_returns_a_new_instance_and_keeps_the_old_one(self):
        sim = self.make()
        before = sim.state
        observed = UiState(before.screen, before.overlays ^ {Overlay.DIALOG}, before.map_mode)

        after = sim.sync(observed)

        assert sim.state == before
        assert after.state == observed

    def test_every_operation_assumes_the_current_screen_and_overlays(self):
        sim = self.make()
        current = ScreenIs(sim.state.screen, sim.state.overlays)

        assert all(current in op.precondition for op in sim.successors())
