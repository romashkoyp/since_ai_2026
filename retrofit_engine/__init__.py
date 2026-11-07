"""RETROFIT AI engine: Joice's physics rules + the hybrid ML diagnostician, as a drop-in package.

Function call:
    from retrofit_engine import predict, to_template_csv, read_table
    result = predict(datasheet_df, telemetry_df, baseline=baseline_df)     # JSON-ready dict
API:
    from retrofit_engine.router import router; app.include_router(router)
"""
from .engine import model_info, predict, to_template_csv
from .inputs import read_table

__all__ = ["predict", "to_template_csv", "read_table", "model_info"]
