import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT
SKILLS = ROOT / "skills"
MARKETPLACES = (
    ROOT / "marketplace.json",
    ROOT / ".agents/plugins/marketplace.json",
    ROOT / ".claude-plugin/marketplace.json",
    ROOT / ".cursor-plugin/marketplace.json",
)
PLATFORM_MANIFESTS = (
    ROOT / ".antigravity-plugin/plugin.json",
    ROOT / ".claude-plugin/plugin.json",
    ROOT / ".codex-plugin/plugin.json",
    ROOT / ".cursor-plugin/plugin.json",
    ROOT / ".zcode-plugin/plugin.json",
)


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def source_path(source):
    if isinstance(source, dict):
        return source.get("path", source.get("url"))
    return source


class PluginStructureTest(unittest.TestCase):
    def test_cli_uses_canonical_bundled_skills(self):
        module_path = ROOT / "tools/mod_cli.py"
        spec = importlib.util.spec_from_file_location("mod_cli", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        skills = SKILLS
        self.assertEqual(skills, module.bundled_skills())
        self.assertTrue(
            (skills / "rimworld-debug/scripts/content_load.py").is_file()
        )
        self.assertTrue(
            (skills / "rimworld-mod/scripts/source_cache.py").is_file()
        )

    def test_cli_reports_missing_bundled_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / "tools"
            tools.mkdir()
            module_path = tools / "mod_cli.py"
            shutil.copy2(ROOT / "tools/mod_cli.py", module_path)

            spec = importlib.util.spec_from_file_location(
                "isolated_mod_cli", module_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            with self.assertRaisesRegex(
                FileNotFoundError, "Bundled skills catalog missing"
            ):
                module.bundled_skills()

    def test_only_canonical_package_exists(self):
        self.assertFalse((ROOT / "rimworld-moddev").exists())
        self.assertTrue(SKILLS.is_dir())
        self.assertFalse((ROOT / "basic").exists())
        self.assertFalse((ROOT / "image").exists())

    def test_every_marketplace_has_one_unified_entry(self):
        for path in MARKETPLACES:
            with self.subTest(path=path):
                plugins = read_json(path)["plugins"]
                self.assertEqual(1, len(plugins))
                self.assertEqual("rimworld-moddev", plugins[0]["name"])
                self.assertIn(source_path(plugins[0]["source"]), (".", "./"))

    def test_copilot_marketplace_has_required_owner_and_url_source(self):
        marketplace = read_json(ROOT / "marketplace.json")
        self.assertEqual("rimworld-moddev-skill", marketplace["name"])
        owner = marketplace.get("owner")
        self.assertIsInstance(owner, dict, "Copilot marketplace owner is required")
        self.assertEqual("pxy6666", owner.get("name"))
        plugin = marketplace["plugins"][0]
        self.assertIn(source_path(plugin["source"]), (".", "./"))

    def test_readme_documents_github_copilot_cli_install(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "copilot plugin marketplace add pxy6666/Rimworld-ModDev-skill",
            readme,
        )
        self.assertIn(
            "copilot plugin install rimworld-moddev@rimworld-moddev-skill",
            readme,
        )

    def test_platform_manifests_use_unified_identity(self):
        for path in PLATFORM_MANIFESTS:
            with self.subTest(path=path):
                manifest = read_json(path)
                self.assertEqual("rimworld-moddev", manifest["name"])
                self.assertEqual("2.1.0", manifest["version"])

    def test_platform_skill_paths_resolve_from_plugin_root(self):
        for platform in (".codex-plugin", ".cursor-plugin"):
            with self.subTest(platform=platform):
                manifest = read_json(ROOT / platform / "plugin.json")
                skills_path = (ROOT / manifest["skills"]).resolve()
                self.assertEqual(SKILLS.resolve(), skills_path)

    def test_catalog_matches_skill_directories(self):
        catalog = read_json(SKILLS / "catalog.json")
        catalog_names = {skill["name"] for skill in catalog["skills"]}
        skill_names = {
            child.name
            for child in SKILLS.iterdir()
            if child.is_dir() and (child / "SKILL.md").is_file()
        }
        self.assertEqual(skill_names, catalog_names)
        self.assertEqual(13, len(catalog_names))
        self.assertIn("rimworld-art", catalog_names)
        self.assertIn("rimworld-sound", catalog_names)
        self.assertEqual(
            {
                "rimworld-16-debug",
                "rimworld-16-mod",
                "rimworld-17-debug",
                "rimworld-17-migrate",
                "rimworld-17-mod",
                "rimworld-debug",
                "rimworld-help",
                "rimworld-mod",
                "rimworld-publish",
                "rimworld-release",
                "rimworld-setup",
                "rimworld-art",
                "rimworld-sound",
            },
            catalog_names,
        )
        self.assertNotIn("imageOnly", catalog)
        duplicates = list(ROOT.rglob("skills/catalog.json"))
        self.assertEqual([SKILLS / "catalog.json"], duplicates)

    def test_relative_markdown_links_resolve(self):
        pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for markdown in SKILLS.rglob("*.md"):
            text = markdown.read_text(encoding="utf-8")
            for target in pattern.findall(text):
                if "://" in target or target.startswith("#"):
                    continue
                relative = target.split("#", 1)[0]
                with self.subTest(source=markdown, target=target):
                    self.assertTrue(
                        (markdown.parent / relative).resolve().exists(),
                        f"{markdown}: unresolved link {target}",
                    )

    def test_art_skill_has_required_specializations(self):
        art = SKILLS / "rimworld-art"
        expected = {
            "apparel-alignment.md",
            "render-space.md",
            "image-sources.md",
            "gfx-batch.md",
            "visual-acceptance.md",
        }
        self.assertEqual(
            expected,
            {path.name for path in (art / "references").glob("*.md")},
        )
        skill = (art / "SKILL.md").read_text(encoding="utf-8")
        apparel = (art / "references/apparel-alignment.md").read_text(
            encoding="utf-8"
        )
        render = (art / "references/render-space.md").read_text(
            encoding="utf-8"
        )
        for phrase in ("name: rimworld-art", "rimworld-mod", "apparel"):
            self.assertIn(phrase, skill)
        for phrase in ("body", "canvas", "alpha", "South", "North", "trim"):
            self.assertIn(phrase, apparel)
        for phrase in ("坐标轴", "图层", "着色器", "无人机", "三者"):
            self.assertIn(phrase, render)

    def test_sound_skill_has_required_specializations(self):
        sound = SKILLS / "rimworld-sound"
        expected = {
            "sound-brief.md",
            "sound-production.md",
            "looping-and-sync.md",
            "loudness-and-format.md",
            "sound-acceptance.md",
        }
        self.assertEqual(
            expected,
            {path.name for path in (sound / "references").glob("*.md")},
        )
        skill = (sound / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "name: rimworld-sound",
            "rimworld-mod",
            "rimworld-debug",
            "SoundDef",
            "试听",
            "循环",
            "响度",
        ):
            self.assertIn(phrase, skill)


if __name__ == "__main__":
    unittest.main()
