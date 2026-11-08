"""The names harness-health and this repo's setup check load from api_security_levels.py."""
import importlib.util
import re
import unittest
from pathlib import Path

import _path

LEVELS_FILE = _path.TOOL / "api_security_levels.py"
CONSUMED = ("TOOL", "LEVELS", "ENFORCED_FILES", "WORKFLOWS", "workspace_fields", "current_level",
            "required_files", "with_level", "project_hash", "tool_hash", "Refused", "apply_command",
            "RUNTIMES")


def load():
    spec = importlib.util.spec_from_file_location("_levels", str(LEVELS_FILE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LevelsTests(unittest.TestCase):
    def test_every_consumed_name_is_there(self):
        mod = load()
        for name in CONSUMED:
            self.assertTrue(hasattr(mod, name), name)

    def test_consumers_load_this_file_not_apply(self):
        for consumer in (_path.TOOL.parent.parent / "scripts" / "harness_health.py",
                         _path.TOOL.parent.parent / "scripts" / "check_setup.py"):
            if consumer.is_file():
                text = consumer.read_text(encoding="utf-8")
                self.assertIn("api_security_levels.py", text, consumer)
                self.assertNotIn('"apply.py"', text, consumer)

    def test_the_files_agree_on_the_names_they_share(self):
        # verify_approval.py is stdlib-only and runs alone from the base branch, so it keeps its own
        # copies; they must agree with the library and with what apply.py requires.
        lib = _path.TOOL / "python" / "api_security"
        texts = {p.name: p.read_text(encoding="utf-8") for p in (lib / "verify_approval.py", lib / "pins.py",
                                                                   lib / "check.py")}
        mod = load()
        for path in ("security/allowed_signers", "security/public-routes.txt",
                     ".github/workflows/security-check.yml", ".github/workflows/security-approval.yml"):
            self.assertIn(path, mod.ENFORCED_FILES)
            self.assertIn(path, texts["verify_approval.py"], path)
        for name in mod.WORKFLOWS:
            self.assertIn(f".github/workflows/{name}", texts["pins.py"], name)
        self.assertIn('"security/config.json"', texts["verify_approval.py"])
        self.assertTrue(re.search(r'security/config\.json|CONFIG', texts["check.py"]))
        self.assertTrue(re.search(r"security/public-routes\.txt", texts["check.py"]))


if __name__ == "__main__":
    unittest.main()
