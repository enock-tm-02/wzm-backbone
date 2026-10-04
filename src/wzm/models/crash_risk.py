"""Crash risk relative to the same segment without a closure. Placeholder.

Plan: Poisson / negative binomial (or LightGBM with poisson objective) on
exposure (VMT), closure type, queue features; report risk ratio vs. baseline.
"""


def relative_risk(zone_id: str, interval_start: str) -> float:
    # TODO: implement once crash and closure history are joined
    raise NotImplementedError
