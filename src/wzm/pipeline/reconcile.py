"""Match planned closures (permits/WZDx) to actual start/end times. Placeholder.

Plan: for each closure, look at segment speeds within +-2 h of the planned
start/end and take the first/last interval where speed < 80% of baseline.
"""


def reconcile_closures(closures: list[dict], speeds: list[dict]) -> list[dict]:
    # TODO
    raise NotImplementedError
