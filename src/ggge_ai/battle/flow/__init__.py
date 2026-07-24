"""In-battle flow layer: a third GOAP planner (戰略層 / 流程層 / 戰術層) that
owns the map-setup dance (回到 hub → 收合列表 → 開格線 → zoom → 掃描 → 關格線)
as declarative Action/Goal over the same ``goap`` A* the AgentLoop uses.

Round 2.0 delivers the kernel only: the perception->WorldState translator
(``vocabulary``), the repair/navigation actions (``actions``) and the tick
loop (``controller2``). The macro/content actions (LoadStageDef,
RunCoverageScan, SurveyUnit ...) and the SyncInitialMap goal are Round 2.1.
"""
