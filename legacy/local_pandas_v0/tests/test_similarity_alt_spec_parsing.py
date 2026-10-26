from bidtabs.reporting import extract_alt_spec_code, extract_spec_code


def test_no_false_alt_for_section_without_space():
    text = "3'HighBlueReflectiveMarkers (Section012200)"
    primary = extract_spec_code(text)
    alt = extract_alt_spec_code(text, primary)
    assert primary == "012200"
    assert alt == ""


def test_no_false_alt_from_non_spec_parenthetical_tokens():
    text = "B6 Valve Vault (SSVLT 1202) Concrete Repair (Section 012200)"
    primary = extract_spec_code(text)
    alt = extract_alt_spec_code(text, primary)
    assert primary == "012200"
    assert alt == ""


def test_alt_from_same_spec_parenthetical_only():
    text = "120-Inch Manhole (Sections 012200 and 334100)"
    primary = extract_spec_code(text)
    alt = extract_alt_spec_code(text, primary)
    assert primary == "012200"
    assert alt == "334100"
