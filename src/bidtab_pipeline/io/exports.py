"""CSV snapshot exports: port of reference notebook 05.

Writes the six tables to <volume_root>/exports/<name>.csv with pandas, as 05
does, and prints one line per table.
"""

from __future__ import annotations

from typing import Any

from pyspark.sql import SparkSession

from bidtab_pipeline.contracts import EXPORTED_TABLES
from bidtab_pipeline.io.volumes import make_dirs
from bidtab_pipeline.settings import Settings

EXPORTS_VOLUME = "exports"


def export_csvs(spark: SparkSession, settings: Settings, dbutils: Any = None) -> None:
    output_path = settings.volume(EXPORTS_VOLUME)
    make_dirs(output_path, dbutils)

    tables = {name: settings.table(name) for name in EXPORTED_TABLES}
    for name, table in tables.items():
        df = spark.sql(f"SELECT * FROM {table}").toPandas()
        filepath = f"{output_path}/{name}.csv"
        df.to_csv(filepath, index=False)
        print(f"{name}: {len(df)} rows → {filepath}")
