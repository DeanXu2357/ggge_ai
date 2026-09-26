from dataclasses import dataclass


@dataclass(frozen=True)
class Size:
    width: int
    height: int


# Build one Display at start-up and inject it into every coordinate conversion.
# Do not write the sizes anywhere else: the UI side and the map side convert
# separately, and two copies of a size drift apart when the stream scale changes.
@dataclass(frozen=True)
class Display:
    touch: Size
    frame: Size
