"""Gradient-boosted impact models (queue, delay, speed drop). Placeholder.

Plan: read the feature table (one row per zone per 15 min), add the HCM baseline
as a feature, train LightGBM with quantile loss (P10/P50/P90), hold out whole
work zones, log to MLflow. Needs `pip install .[ml]`.
"""

TARGETS = ("queue_miles", "delay_veh_hours", "speed_drop_mph")
QUANTILES = (0.1, 0.5, 0.9)


def train(feature_table_path: str) -> None:
    # TODO: load parquet, group-kfold by zone_id, fit one model per target x quantile
    raise NotImplementedError("model training is a placeholder until the feature table exists")
