# Databricks notebook source
dbutils.fs.mkdirs("/Volumes/pop-poc/bidtab/exports")

# COMMAND ----------

import pandas as pd

tables = {
    "bronze_raw_rows": "`pop-poc`.`bidtab`.`bronze_raw_rows`",
    "silver_bid_items": "`pop-poc`.`bidtab`.`silver_bid_items`",
    "mart_bid_analysis": "`pop-poc`.`bidtab`.`mart_bid_analysis`",
    "ref_awarded_bids": "`pop-poc`.`bidtab`.`ref_awarded_bids`",
    "int_crosswalk": "`pop-poc`.`bidtab`.`int_crosswalk`",
    # crosswalk_unmapped_items
    "crosswalk_unmapped_items": "`pop-poc`.`bidtab`.`crosswalk_unmapped_items`",
}

output_path = "/Volumes/pop-poc/bidtab/exports"

for name, table in tables.items():
    df = spark.sql(f"SELECT * FROM {table}").toPandas()
    filepath = f"{output_path}/{name}.csv"
    df.to_csv(filepath, index=False)
    print(f"{name}: {len(df)} rows → {filepath}")