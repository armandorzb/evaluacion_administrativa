from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STYLE = (ROOT / "municipal_diagnostico" / "static" / "style.css").read_text(encoding="utf-8")
LIVE_TEMPLATE = (ROOT / "municipal_diagnostico" / "templates" / "live" / "templates.html").read_text(encoding="utf-8")
WELLBEING_TEMPLATE = (ROOT / "municipal_diagnostico" / "templates" / "bienestar" / "dashboard.html").read_text(encoding="utf-8")
WELLBEING_JS = (ROOT / "municipal_diagnostico" / "static" / "bienestar.js").read_text(encoding="utf-8")
APP_JS = (ROOT / "municipal_diagnostico" / "static" / "app.js").read_text(encoding="utf-8")
CAMPAIGN_CAPTURE = (ROOT / "municipal_diagnostico" / "templates" / "campaigns" / "respond.html").read_text(encoding="utf-8")
ISO9001_CAPTURE = (ROOT / "municipal_diagnostico" / "templates" / "iso9001" / "evaluation_detail.html").read_text(encoding="utf-8")
ISO45001_CAPTURE = (ROOT / "municipal_diagnostico" / "templates" / "iso45001" / "evaluation_detail.html").read_text(encoding="utf-8")
ISO45001_DOCUMENTS = (ROOT / "municipal_diagnostico" / "templates" / "iso45001" / "document_controls.html").read_text(encoding="utf-8")


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


def test_choice_bubbles_have_explicit_unique_control_targets():
    assert 'for="valor-{{ reactivo.id }}-{{ index }}"' in CAMPAIGN_CAPTURE
    assert 'id="valor-{{ reactivo.id }}-{{ index }}"' in CAMPAIGN_CAPTURE
    assert 'for="iso9001-calificacion-{{ reactive.id }}-{{ value }}"' in ISO9001_CAPTURE
    assert 'id="iso9001-calificacion-{{ reactive.id }}-{{ value }}"' in ISO9001_CAPTURE
    assert 'for="iso45001-calificacion-{{ reactive.id }}-{{ value }}"' in ISO45001_CAPTURE
    assert 'id="iso45001-calificacion-{{ reactive.id }}-{{ value }}"' in ISO45001_CAPTURE


def test_document_origin_pills_are_not_inside_checkbox_labels():
    assert 'class="list-row data-row document-point-row"' in ISO45001_CAPTURE
    assert 'for="captura-punto-{{ point.id }}"' in ISO45001_CAPTURE
    assert 'for="documentacion-punto-{{ point.id }}"' in ISO45001_DOCUMENTS
    assert '.document-point-row > .pill' in STYLE


def test_reading_text_uses_word_boundaries_and_choice_animation_does_not_scale():
    shared_reading_rule = STYLE.split("Shared reading and touch safeguards", 1)[1]
    assert "overflow-wrap: break-word;" in shared_reading_rule
    choice_animation = STYLE.split("@keyframes choice-pulse", 1)[1].split("}", 4)[0:4]
    assert all("transform: scale" not in rule for rule in choice_animation)
