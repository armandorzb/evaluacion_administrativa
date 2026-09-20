from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STYLE = (ROOT / "municipal_diagnostico" / "static" / "style.css").read_text(encoding="utf-8")
LIVE_TEMPLATE = (ROOT / "municipal_diagnostico" / "templates" / "live" / "templates.html").read_text(encoding="utf-8")
WELLBEING_TEMPLATE = (ROOT / "municipal_diagnostico" / "templates" / "bienestar" / "dashboard.html").read_text(encoding="utf-8")
WELLBEING_JS = (ROOT / "municipal_diagnostico" / "static" / "bienestar.js").read_text(encoding="utf-8")
APP_JS = (ROOT / "municipal_diagnostico" / "static" / "app.js").read_text(encoding="utf-8")


def test_hidden_live_configuration_sections_are_reliably_removed_from_layout():
    assert "[hidden]" in STYLE
    assert "display: none !important;" in STYLE
    assert 'data-live-config="multiple_choice" hidden' in LIVE_TEMPLATE


def test_mobile_internal_scroll_is_scoped_to_catalog_dialogs():
    assert re.search(
        r"\.catalog-dialog\s+\.catalog-form\s*\{[^}]*max-height:[^}]*overflow-y:\s*auto",
        STYLE,
        re.DOTALL,
    )


def test_wellbeing_profile_table_uses_responsive_cards_with_dynamic_labels():
    assert "wellbeing-profile-table js-responsive-table" in WELLBEING_TEMPLATE
    assert 'data-label="${escapeHtml(headers[0])}"' in WELLBEING_JS
    assert ".wellbeing-profile-panel > .table-wrap" in STYLE


def test_shared_modules_contain_grid_children_and_expose_long_select_values():
    assert ".table-wrap,\nform,\nfieldset" in STYLE
    assert "text-overflow: ellipsis;" in STYLE
    assert "function initializeSelectTitles()" in APP_JS
    assert "select.title = selectedText" in APP_JS
    assert "initializeSelectTitles();" in APP_JS
