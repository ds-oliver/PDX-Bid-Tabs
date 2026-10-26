from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR / "golden"))

# Spark needs JDK 17. Fall back to a Homebrew openjdk@17 keg when JAVA_HOME is unset.
_BREW_JDK = Path("/opt/homebrew/opt/openjdk@17")
if "JAVA_HOME" not in os.environ and _BREW_JDK.exists():
    os.environ["JAVA_HOME"] = str(_BREW_JDK)


def pytest_addoption(parser):
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Rewrite tests/golden/snapshots/ from the current reference run instead of comparing.",
    )


@pytest.fixture(scope="session")
def spark(tmp_path_factory):
    from bidtab_pipeline.io.local_spark import get_local_spark

    session = get_local_spark(tmp_path_factory.mktemp("spark_warehouse"))
    yield session
    session.stop()


@pytest.fixture(scope="session")
def reference_outputs(spark, tmp_path_factory):
    """Run the unchanged reference notebooks on every synthetic scenario, once per session."""
    from scenarios import run_reference_scenarios

    return run_reference_scenarios(spark, tmp_path_factory.mktemp("reference_volumes"))
