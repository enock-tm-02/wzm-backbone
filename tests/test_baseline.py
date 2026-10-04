from wzm.models.baseline_hcm import WorkZone, capacity_vph, predict_queue, queue_discharge_rate


def test_closing_more_lanes_lowers_capacity():
    two_of_three = WorkZone(normal_lanes=3, open_lanes=2)
    one_of_three = WorkZone(normal_lanes=3, open_lanes=1)
    assert capacity_vph(one_of_three) < capacity_vph(two_of_three)
    assert queue_discharge_rate(one_of_three) < queue_discharge_rate(two_of_three)


def test_no_queue_below_capacity_and_queue_above():
    z = WorkZone(normal_lanes=2, open_lanes=1)
    cap = capacity_vph(z)
    light = predict_queue(z, [cap * 0.5] * 4)
    assert all(i["queued_vehicles"] == 0 for i in light)
    heavy = predict_queue(z, [cap * 1.3] * 4 + [cap * 0.5] * 8)
    peak = max(i["queue_miles"] for i in heavy)
    assert peak > 0
    assert heavy[-1]["queued_vehicles"] < max(i["queued_vehicles"] for i in heavy)
