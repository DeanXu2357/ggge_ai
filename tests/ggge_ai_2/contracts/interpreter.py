from ggge_ai_2.interpreter.contract import Interpreter
from ggge_ai_2.stream.contract import Frame
from ggge_ai_2.uisim.contract import Screen, UiState
from ggge_ai_2.verdict import Verdict


class InterpreterContract:
    """Subclass per implementation with one known frame and one unmodeled frame."""

    def make(self) -> Interpreter:
        raise NotImplementedError

    def known_frame(self) -> tuple[Frame, UiState]:
        raise NotImplementedError

    def unknown_frame(self) -> Frame:
        raise NotImplementedError

    def test_known_frame_reads_as_its_state(self):
        frame, state = self.known_frame()

        assert self.make().interpret(frame) == state

    def test_every_fact_of_the_known_state_holds(self):
        frame, state = self.known_frame()
        interpreter = self.make()

        assert all(interpreter.verify(frame, fact) is Verdict.HOLDS for fact in state.facts())

    def test_unmodeled_frame_reads_as_none(self):
        assert self.make().interpret(self.unknown_frame()) is None

    def test_answer_stays_inside_the_candidates(self):
        frame, state = self.known_frame()
        candidates = frozenset(Screen) - {state.screen}
        answer = self.make().interpret(frame, candidates)

        assert answer is None or answer.screen in candidates

    def test_verify_answers_with_a_verdict_on_an_unmodeled_frame(self):
        frame, state = self.known_frame()
        verdict = self.make().verify(self.unknown_frame(), state.facts()[0])

        assert verdict in set(Verdict)
