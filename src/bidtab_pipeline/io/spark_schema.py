"""Spark StructTypes built from the column contracts in bidtab_pipeline.contracts."""

from __future__ import annotations

from pyspark.sql.types import (
    BooleanType,
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

_TYPES = {
    "string": StringType,
    "int": IntegerType,
    "bigint": LongType,
    "double": DoubleType,
    "boolean": BooleanType,
    "date": DateType,
    "timestamp": TimestampType,
}


def struct_type(columns, exclude: tuple[str, ...] = ()) -> StructType:
    return StructType([StructField(name, _TYPES[kind](), True) for name, kind in columns if name not in exclude])
