from ggge_ai_2.screenmodel.contract import ModelElement, ModelScreen, SeenElement
from ggge_ai_2.screenmodel.definition import Need, ScreenDefinition
from ggge_ai_2.screenmodel.definition_model import DefinitionScreenModel


def test_judges_no_screen_but_lists_every_screen_when_several_match() -> None:
    model = DefinitionScreenModel(
        (
            ScreenDefinition(ModelScreen.BATTLE_INFO_PREVIEW, (Need(ModelElement.FAST_FORWARD),)),
            ScreenDefinition(ModelScreen.UNIT_DETAIL_SUMMARY, (Need(ModelElement.TAP_TO_NEXT),)),
        )
    )

    judgment = model.judge(
        [
            SeenElement(ModelElement.FAST_FORWARD, None, (0, 0, 10, 10)),
            SeenElement(ModelElement.TAP_TO_NEXT, None, (0, 20, 10, 30)),
        ]
    )

    assert judgment.screen is None
    assert judgment.matched == {ModelScreen.BATTLE_INFO_PREVIEW, ModelScreen.UNIT_DETAIL_SUMMARY}
