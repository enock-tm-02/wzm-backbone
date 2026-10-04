"""Build the feature table: one row per work zone per 15-minute interval. Placeholder."""

FEATURE_COLUMNS = [
    # capacity
    "normal_lanes", "open_lanes", "shoulder_closed", "lane_width_ft", "work_type",
    "hard_barrier", "posted_speed_mph", "reduced_speed_mph", "heavy_vehicle_pct",
    "dist_onramp_mi", "dist_offramp_mi", "grade_pct",
    # demand
    "volume_vph", "v_c_ratio", "hour", "dow", "holiday", "event_nearby",
    # context
    "precip", "visibility", "night", "upstream_speed", "downstream_speed",
    "other_closures_5mi", "incident_nearby",
    # history
    "baseline_speed", "site_past_queue_mi", "days_since_start",
    # physics baseline
    "hcm_capacity_vph", "hcm_queue_miles",
]
LABEL_COLUMNS = ["queue_miles", "delay_veh_hours", "speed_drop_mph", "crashes"]


def build_feature_table() -> None:
    # TODO: join reconciled closures, speeds, volumes, weather, events by segment + interval
    raise NotImplementedError
