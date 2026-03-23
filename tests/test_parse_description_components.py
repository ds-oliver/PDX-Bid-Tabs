from bidtabs.parse_items import parse_description_components, parse_item_fields


def test_markings_item_p620():
    spec, alt, core, ptype = parse_description_components("Markings (Item P-620)")
    assert spec == "P-620"
    assert alt == ""
    assert core == "Markings"
    assert ptype.startswith("ITEM")


def test_remove_bollard_section_024113():
    spec, alt, core, ptype = parse_description_components("Remove Bollard - Embedded (Section 024113)")
    assert spec == "024113"
    assert alt == ""
    assert core == "Remove Bollard - Embedded"
    assert ptype.startswith("SECTION")


def test_sections_two_codes():
    spec, alt, core, ptype = parse_description_components("12-Inch STS (Sections 012200 and 334100)")
    assert spec == "012200"
    assert alt == "334100"
    assert core == "12-Inch STS"
    assert ptype.startswith("SECTION")


def test_sections_three_codes():
    spec, alt, core, ptype = parse_description_components("Fill Material, Topsoil (Sections 012200, 312000, and 329113)")
    assert spec == "012200"
    assert alt == "312000 | 329113"
    assert core == "Fill Material, Topsoil"
    assert ptype.startswith("SECTION")


def test_unclassified_ambiguous_parentheses():
    spec, alt, core, ptype = parse_description_components("Borrow Excavation (P-152)")
    assert spec == "UNCLASSIFIED"
    assert alt == ""
    assert core == "Borrow Excavation (P-152)"
    assert ptype.startswith("UNCLASSIFIED")


def test_business_examples_exact_from_spec():
    e1 = parse_item_fields("Concrete to Asphalt Joint Seal\n(Item P-605)")
    assert e1["spec_code_primary"] == "P-605"
    assert e1["item"] == "Concrete to Asphalt Joint Seal"
    assert e1["supplemental_description"] == ""
    assert e1["item_display"] == "P-605 - Concrete to Asphalt Joint Seal"

    e2 = parse_item_fields("Concrete to Concrete Joint Seal (Silicone)\n(Item P-605)")
    assert e2["spec_code_primary"] == "P-605"
    assert e2["item"] == "Concrete to Concrete Joint Seal"
    assert e2["supplemental_description"] == "Silicone"
    assert e2["item_display"] == "P-605 - Concrete to Concrete Joint Seal"

    e3 = parse_item_fields("PCC Spall Panel Repair, 1-5 SF\n(Section 012200)")
    assert e3["spec_code_primary"] == "012200"
    assert e3["item"] == "PCC Spall Panel Repair"
    assert e3["supplemental_description"] == "1-5 SF"
    assert e3["item_display"] == "012200 - PCC Spall Panel Repair"

    e4 = parse_item_fields("PCC Spall Panel Repair, 5-15 SF\n(Section 012200)")
    assert e4["spec_code_primary"] == "012200"
    assert e4["item"] == "PCC Spall Panel Repair"
    assert e4["supplemental_description"] == "5-15 SF"
    assert e4["item_display"] == "012200 - PCC Spall Panel Repair"


def test_comma_list_guardrail_does_not_split():
    e = parse_item_fields("Mobilization, Cleanup, and Demobilization (Section 012200)")
    assert e["spec_code_primary"] == "012200"
    assert e["item"] == "Mobilization, Cleanup, and Demobilization"
    assert e["supplemental_description"] == ""
    assert e["item_display"] == "012200 - Mobilization, Cleanup, and Demobilization"


def test_comma_measurement_qualifier_splits_on_last_comma():
    e = parse_item_fields("Pavement Removal and Disposal, 6-inch Depth (Sections 012200 and 024113)")
    assert e["spec_code_primary"] == "012200"
    assert e["spec_code_alternates"] == "024113"
    assert e["item"] == "Pavement Removal and Disposal"
    assert e["supplemental_description"] == "6-inch Depth"
    assert e["item_display"] == "012200 - Pavement Removal and Disposal"


def test_comma_variant_keywords_split():
    o = parse_item_fields("PCC Crack Repair, Original (Section 012200)")
    r = parse_item_fields("PCC Crack Repair, Renewal (Section 012200)")

    assert o["item"] == "PCC Crack Repair"
    assert o["supplemental_description"] == "Original"
    assert r["item"] == "PCC Crack Repair"
    assert r["supplemental_description"] == "Renewal"


def test_dash_separator_qualifier_split():
    e = parse_item_fields("Asphalt Pavement Removal - 2-3 Inch Depth (Section 320117)")
    assert e["spec_code_primary"] == "320117"
    assert e["item"] == "Asphalt Pavement Removal"
    assert e["supplemental_description"] == "2-3 Inch Depth"
    assert e["item_display"] == "320117 - Asphalt Pavement Removal"


def test_cast_in_place_not_split_on_dash():
    e = parse_item_fields("Cast-in-Place Concrete Curb (Section 321613)")
    assert e["spec_code_primary"] == "321613"
    assert e["item"] == "Cast-in-Place Concrete Curb"
    assert e["supplemental_description"] == ""


def test_jammed_tokens_and_dash_normalization():
    e = parse_item_fields("ExistingManholeAdjustmenttoGrade-Cleanout (Section312300)")
    assert e["spec_code_primary"] == "312300"
    assert e["item"] == "Existing Manhole Adjustment to Grade"
    assert e["supplemental_description"] == "Cleanout"
    assert e["item_display"] == "312300 - Existing Manhole Adjustment to Grade"


def test_leading_measurement_becomes_supplemental():
    e = parse_item_fields("10-Foot Chain Link Fence with Slats and Barbed Wire (Section 323113)")
    assert e["spec_code_primary"] == "323113"
    assert e["item"] == "Chain Link Fence with Slats and Barbed Wire"
    assert e["supplemental_description"] == "10-Foot"
    assert e["item_display"] == "323113 - Chain Link Fence with Slats and Barbed Wire"


def test_installpf_compact_suffix_becomes_supplemental():
    e = parse_item_fields('InstallPF12"Diameter,24"DeepBaseCanwithPFCoverinNewACPShoulder (Section344300)')
    assert e["spec_code_primary"] == "344300"
    assert e["item"] == "InstallPF"
    assert e["supplemental_description"] == '12"Diameter,24"DeepBaseCanwithPFCoverinNewACPShoulder'


def test_topsoil_parenthetical_compact_qualifier():
    e = parse_item_fields('Topsoil(ObtainedOnStieorRemovedfromStockpile) (ItemT-905)')
    assert e["spec_code_primary"] == "T-905"
    assert e["item"] == "Topsoil"
    assert e["supplemental_description"] == "ObtainedOnStieorRemovedfromStockpile"


def test_hxw_prefix_compact_measurement_supplemental():
    e = parse_item_fields("8'HX14'WCulvert (ItemD-701)")
    assert e["spec_code_primary"] == "D-701"
    assert e["item"] == "Culvert"
    assert e["supplemental_description"] == "8'HX14'W"


def test_surface_preparation_dash_compact_suffix():
    e = parse_item_fields("SurfacePreparation-NewPavementSurface (ItemP-620)")
    assert e["spec_code_primary"] == "P-620"
    assert e["item"] == "SurfacePreparation"
    assert e["supplemental_description"] == "NewPavementSurface"


def test_three_foot_prefix_compact_supplemental():
    e = parse_item_fields("3'HighBlueReflectiveMarkers (Section012200)")
    assert e["spec_code_primary"] == "012200"
    assert e["item"] == "HighBlueReflectiveMarkers"
    assert e["supplemental_description"] == "3'"
