"""Check display metadata without importing the API or loading credentials."""

import ast
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
known = json.loads((root / "ui/src/i18n/messages/sources.json").read_text(encoding="utf-8"))
paths = [
    root / "api/services/workflow/dto.py",
    root / "api/services/configuration/registry.py",
    root / "api/schemas/widget_texts.py",
]
paths += list((root / "api/services/telephony/providers").rglob("*.py"))
paths += list((root / "api/services/integrations").rglob("node.py"))
issues = []
for path in paths:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        value = None
        if isinstance(node, ast.keyword) and node.arg in {
            "display_name", "description", "placeholder", "label", "title", "hint", "docs_label"
        }:
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
        elif (
            path.name == "widget_texts.py"
            and isinstance(node, ast.AnnAssign)
            and isinstance(node.value, ast.Constant)
        ):
            value = node.value.value
        if isinstance(value, str) and value not in known:
            issues.append(f"{path.relative_to(root)}:{node.lineno}: missing display metadata: {value}")
if issues:
    print("\n".join(issues))
    sys.exit(1)
print("Backend display metadata audit passed.")
