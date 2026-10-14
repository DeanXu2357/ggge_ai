import time

Instant = float


def now() -> Instant:
    # Frame capture times and gesture times are compared directly ("only frames after t0"),
    # so every timestamp in ggge_ai_2 must come from this one clock.
    return time.monotonic()
