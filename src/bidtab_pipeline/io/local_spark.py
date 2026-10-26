"""Local Spark session that behaves like the job's Databricks compute where it matters.

Used by tests and local runs only. On Databricks the notebooks use the
platform-provided `spark`.

Settings that differ from open-source Spark defaults and change baseline results:
- `spark.sql.sources.default=delta`: `CREATE OR REPLACE TABLE ... AS` with no
  USING clause creates a Delta table on Databricks. Open-source Spark would
  pick Parquet, which does not support REPLACE TABLE AS SELECT.
- Arrow conversion on: Databricks enables it by default. Without it,
  `spark.createDataFrame(pandas_df)` infers types row by row and fails on
  string columns that hold NaN (03 loads the crosswalk with dtype=str).
- Session time zone UTC, matching the workspace default.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pyspark.sql import SparkSession

DATABRICKS_LIKE_CONF = {
    "spark.sql.extensions": "io.delta.sql.DeltaSparkSessionExtension",
    "spark.sql.catalog.spark_catalog": "org.apache.spark.sql.delta.catalog.DeltaCatalog",
    "spark.sql.sources.default": "delta",
    "spark.sql.execution.arrow.pyspark.enabled": "true",
    "spark.sql.session.timeZone": "UTC",
}

_LOCAL_ONLY_CONF = {
    "spark.ui.enabled": "false",
    "spark.sql.shuffle.partitions": "2",
    "spark.default.parallelism": "2",
}


def get_local_spark(warehouse_dir: str | Path, app_name: str = "bidtab-local") -> SparkSession:
    """Return a local Spark session with Delta, configured like the job's compute.

    The warehouse directory is fixed when the first session starts. Later calls
    return the same session.
    """
    from delta import configure_spark_with_delta_pip

    # UDF workers (02 registers normalize_description) must use the driver's interpreter.
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    builder = SparkSession.builder.master("local[2]").appName(app_name)
    for key, value in {**DATABRICKS_LIKE_CONF, **_LOCAL_ONLY_CONF}.items():
        builder = builder.config(key, value)
    builder = builder.config("spark.sql.warehouse.dir", str(Path(warehouse_dir).resolve()))
    builder = builder.config("spark.driver.extraJavaOptions", f"-Dderby.system.home={Path(warehouse_dir).resolve()}")
    spark = configure_spark_with_delta_pip(builder).getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark
