#!/usr/bin/env python3
"""Check dependencies without importing optional packages."""
import importlib.util
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
modules = {name: importlib.util.find_spec(module) is not None
           for name, module in [("python-pptx", "pptx"), ("Pillow", "PIL")]}
resources = {name: (root / name).is_file() for name in
             ["assets/themes.json", "scripts/builder.py", "scripts/validate_deck.py"]}
office = shutil.which("soffice") or shutil.which("libreoffice")
poppler = shutil.which("pdftoppm") or shutil.which("pdftocairo")
ready = all(modules.values()) and all(resources.values())
print(json.dumps({"ready": ready, "modules": modules, "resources": resources,
                  "render_available": bool(office and poppler)}, indent=2))
raise SystemExit(0 if ready else 2)
