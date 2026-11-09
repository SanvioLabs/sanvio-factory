"""Run with: python3 -m unittest discover -s tests

The product-wide names Sanvio Factory took: the marketplace, the dashboard mod and the picture of it.
"""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKET = "sanvio-factory"
DASHBOARD = ROOT / "examples" / "mods" / "factory-dashboard"
# The names that went, and the files allowed to keep saying them: history, and the tests that pin it.
OLD = ("harness-dashboard", "@sanvio-harness-starter")
HISTORY = ("CHANGELOG.md", "docs/upgrading-to-sanvio-factory.md", "tests/test_factory_names.py")


def tracked():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True,
                         check=True, timeout=30).stdout
    return [name for name in out.split("\0") if name]


class Marketplace(unittest.TestCase):
    def setUp(self):
        self.market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        self.settings = json.loads((ROOT / ".claude" / "settings.json").read_text())

    def test_the_marketplace_has_its_new_name(self):
        self.assertEqual(self.market["name"], MARKET)
        self.assertEqual(list(self.settings["extraKnownMarketplaces"]), [MARKET])

    def test_every_plugin_this_repo_turns_on_comes_from_it(self):
        enabled = self.settings["enabledPlugins"]
        self.assertTrue(enabled)
        for plugin in enabled:
            self.assertTrue(plugin.endswith("@" + MARKET), plugin)

    def test_the_dashboard_is_listed_under_its_new_name(self):
        listed = {plugin["name"]: plugin["source"] for plugin in self.market["plugins"]}
        self.assertEqual(listed.get("factory-dashboard"), "./examples/mods/factory-dashboard")
        self.assertNotIn("harness-dashboard", listed)


class Dashboard(unittest.TestCase):
    def test_the_mod_has_its_new_name_and_command(self):
        manifest = json.loads((DASHBOARD / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["name"], "factory-dashboard")
        register = (DASHBOARD / "hooks" / "register.tsx").read_text()
        self.assertIn("'factory-dashboard'", register)
        self.assertFalse((ROOT / "examples" / "mods" / "harness-dashboard").exists())

    def test_the_picture_moved_with_it(self):
        self.assertTrue((ROOT / "docs" / "factory-dashboard.svg").is_file())
        self.assertFalse((ROOT / "docs" / "harness-dashboard.svg").exists())


class NoOldName(unittest.TestCase):
    def test_no_tracked_file_keeps_an_old_name(self):
        for name in tracked():
            path = ROOT / name
            for old in OLD:
                self.assertNotIn(old, name)
                if name in HISTORY or name.startswith("docs/specs/") or not path.is_file():
                    continue
                self.assertNotIn(old, path.read_text(errors="replace"), (name, old))


if __name__ == "__main__":
    unittest.main()
