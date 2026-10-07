from bidtabs.cli import build_parser


def test_cli_exposes_three_stage_commands():
    parser = build_parser()
    help_text = parser.format_help()
    assert "extract" in help_text
    assert "build-model" in help_text
    assert "build-reports" in help_text
