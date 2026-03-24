import pandas as pd

from bidtabs.model import _extract_alt_code


def test_extract_alt_code_sections():
    desc = "Abandon Existing Structure (Sections 012200 and 334100)"
    primary, alt = _extract_alt_code(desc)
    assert primary == "012200"
    assert alt == "334100"


def test_extract_alt_code_item():
    desc = "SubbaseCourse (ItemP-154)"
    primary, alt = _extract_alt_code(desc)
    assert primary == "P-154"
    assert alt == ""


def test_dim_pay_item_includes_raw_and_canonical():
    # Basic sanity: canonical should drop embedded quotes if present
    from bidtabs.model import build_dim_pay_item

    df = pd.DataFrame(
        {
            "item_code_raw": ["P-154"],
            "item_code_norm": ["P-154"],
            "section_code_raw": [""],
            "section_code_norm": [""],
            "item_description_raw": ['"InstallPFLEDRunwayEdgeLight"'],
            "item_description_clean": ['"InstallPFLEDRunwayEdgeLight"'],
        }
    )
    dim = build_dim_pay_item(df)
    assert dim.loc[0, "item_desc_raw"] == '"InstallPFLEDRunwayEdgeLight"'
    assert dim.loc[0, "item_desc_canonical"] == "InstallPFLEDRunwayEdgeLight"
