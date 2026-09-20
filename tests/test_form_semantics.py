from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "municipal_diagnostico" / "templates"


class FormSemanticsParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = {}
        self.labels = []
        self.open_labels = []
        self.controls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        node_id = attrs.get("id", "")
        if node_id and "{{" not in node_id and "{%" not in node_id:
            self.ids[node_id] = self.ids.get(node_id, 0) + 1
        if tag == "label":
            label = {"for": attrs.get("for"), "controls": []}
            self.labels.append(label)
            self.open_labels.append(label)
        if tag in {"input", "select", "textarea"} and attrs.get("type") != "hidden":
            control = {
                "tag": tag,
                "id": attrs.get("id"),
                "name": attrs.get("name"),
                "aria": attrs.get("aria-label") or attrs.get("aria-labelledby"),
                "wrapped": bool(self.open_labels),
            }
            self.controls.append(control)
            if self.open_labels:
                self.open_labels[-1]["controls"].append(control)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "label" and self.open_labels:
            self.open_labels.pop()


def audit_template(path):
    parser = FormSemanticsParser()
    parser.feed(path.read_text(encoding="utf-8"))
    issues = []
    for node_id, count in parser.ids.items():
        if count > 1:
            issues.append(f"id duplicado: {node_id} ({count})")
    for label in parser.labels:
        target = label["for"]
        if target and target not in parser.ids and "{{" not in target:
            issues.append(f"label for sin destino: {target}")
        if not target and len(label["controls"]) > 1:
            names = [item["name"] or item["id"] or item["tag"] for item in label["controls"]]
            issues.append(f"label envuelve varios controles: {names}")
    targets = {label["for"] for label in parser.labels if label["for"]}
    for control in parser.controls:
        labelled = (
            control["wrapped"]
            or control["aria"]
            or (control["id"] and control["id"] in targets)
        )
        if not labelled:
            issues.append(
                f"control sin etiqueta: {control['tag']}[{control['name'] or control['id'] or 'sin nombre'}]"
            )
    return issues


def test_all_form_controls_have_unambiguous_labels_and_unique_static_ids():
    failures = {}
    for path in sorted(TEMPLATE_ROOT.rglob("*.html")):
        issues = audit_template(path)
        if issues:
            failures[path.relative_to(ROOT).as_posix()] = issues
    assert not failures, failures
