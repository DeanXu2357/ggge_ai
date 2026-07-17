"""Data-bound stage content: what the game presents, held as data.

Everything here is content in the mechanism/content split
(docs/agent-architecture.md): unit kit numbers and their transcription
shapes (kit), the grounding of a spec into a simulator unit (grounding),
stage definition files (stage_def), the conditions-to-objective compiler
(objectives) and the offline stage opening (stage_sim). The package
binds perceived or transcribed data to the sim's world model; it depends
on sim, planner and the shared roster vocabulary only -- never on
perception, vision, actuation or the controller. The battle layer is a
consumer.
"""
