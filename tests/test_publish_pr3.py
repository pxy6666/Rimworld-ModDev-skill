"""Windows-friendly offline acceptance checks for the Workshop update."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import random
import struct
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "tools/mod_cli.py").is_file())
VARIANT = os.environ.get("RIMWORLD_TEST_VARIANT")
SCRIPTS = Path(VARIANT) / "rimworld-publish/scripts" if VARIANT else ROOT / "skills/rimworld-publish/scripts"
if not SCRIPTS.is_dir() and not VARIANT:
    SCRIPTS = ROOT / "basic/skills/rimworld-publish/scripts"
sys.path[:0] = [str(SCRIPTS.resolve()), str(ROOT / "tools")]
import mod_cli
import publish
import workshop_requirements


ITEM = 92001
ACCOUNT = 76561198000000001
REQUIRED_16 = 92002
REQUIRED_17 = 92003
EXISTING_OTHER = 92004
BIOTECH = 1826140


class OfflineSteam:
    def __init__(self):
        self.calls = []
        self.items = {EXISTING_OTHER, REQUIRED_16}
        self.apps = set()
        self.accept_apps = True
        self.read_failure = None
        self.dependency_writes = 0
        self.submit_error = None
        self.visibility = 2

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def logged_on(self):
        return True

    def steam_id(self):
        return ACCOUNT

    def query_details(self, item_id, language="english"):
        return {"fileId": item_id, "ownerSteamId": ACCOUNT, "consumerAppId": publish.APPID,
                "visibility": self.visibility, "previewUrl": "fixture://preview",
                "title": language, "description": "Existing description", "screenshots": []}

    def query_dependencies(self, item_id):
        if self.read_failure is not None:
            self.read_failure()
        return {"items": sorted(self.items), "apps": sorted(self.apps)}

    def create_item(self):
        self.calls.append(("create",))
        return ITEM, False

    def start_update(self, item_id):
        self.calls.append(("start", item_id))
        return item_id + 1

    def set_content(self, handle, path):
        if not (Path(path) / "About/About.xml").is_file():
            raise AssertionError("Steam must receive the verified Mod directory.")
        self.calls.append(("content",))

    def set_preview(self, handle, path):
        self.calls.append(("preview", Path(path).read_bytes()[:8]))

    def set_title(self, handle, value):
        self.calls.append(("title", value))

    def set_description(self, handle, value):
        self.calls.append(("description", value))

    def set_update_language(self, handle, value):
        self.calls.append(("language", value))

    def set_visibility(self, handle, value):
        self.visibility = value
        self.calls.append(("visibility", value))

    def submit(self, handle, note):
        self.calls.append(("submit", note))
        if self.submit_error is not None:
            raise self.submit_error
        return {"fileId": handle - 1, "needsAccept": False}

    def add_dependency(self, published_item, child):
        if published_item != ITEM:
            raise AssertionError("A dependency write must receive a PublishedFileId, not an update handle.")
        self.calls.append(("dependency", published_item, child))
        self.dependency_writes += 1
        self.items.add(child)

    def add_app_dependency(self, published_item, app):
        if published_item != ITEM:
            raise AssertionError("A DLC write must receive a PublishedFileId, not an update handle.")
        self.calls.append(("dlc", published_item, app))
        self.dependency_writes += 1
        if self.accept_apps:
            self.apps.add(app)


class WorkshopPr3Tests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.project = self.root / "project"
        self.about = self.project / "About"
        self.about.mkdir(parents=True)
        (self.about / "About.xml").write_text(
            f"""<ModMetaData>
              <name>Offline Workshop Fixture</name><author>Fixture</author>
              <packageId>fixture.workshop</packageId>
              <supportedVersions><li>1.6</li><li>1.7</li></supportedVersions>
              <modDependenciesByVersion>
                <v1.6><li><packageId>fixture.first</packageId><displayName>First dependency</displayName>
                  <steamWorkshopUrl>https://steamcommunity.com/sharedfiles/filedetails/?id={REQUIRED_16}</steamWorkshopUrl>
                </li></v1.6>
                <v1.7>
                  <li><packageId>fixture.second</packageId><displayName>Second dependency</displayName>
                    <steamWorkshopUrl>https://steamcommunity.com/workshop/filedetails/?id={REQUIRED_17}</steamWorkshopUrl>
                  </li>
                  <li><packageId>ludeon.rimworld.biotech</packageId><displayName>Biotech</displayName></li>
                </v1.7>
              </modDependenciesByVersion>
              <loadAfter><li>fixture.loadorder</li></loadAfter>
            </ModMetaData>""",
            encoding="utf-8",
        )
        mod_cli.write_json(self.project / "config/mod.json",
                           {"version": "1.7", "assemblyName": "Fixture", "targets": {"1.6": {}}})
        self.content = self.package()
        self.journal = self.root / "journal.json"
        self.sdk = self.root / "fixture.dll"
        self.sdk.touch()
        self.steam = OfflineSteam()
        self.upload_args = SimpleNamespace(journal=self.journal, sdk=self.sdk, timeout=2)
        local_run_dir = patch.object(publish, "DEFAULT_RUN_DIR", self.root / "run")
        local_run_dir.start()
        self.addCleanup(local_run_dir.stop)
        use_fake_index = patch.object(workshop_requirements, "workshop_package_index", return_value={})
        use_fake_index.start()
        self.addCleanup(use_fake_index.stop)

    def backend(self, *args, **kwargs):
        return self.steam

    def package(self):
        package = mod_cli.package(self.project, mod_cli.config(self.project))
        self.assertTrue(package["passed"], package)
        return Path(package["directory"])

    def command(self, *argv, expect=0):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = publish.main(list(argv))
        self.assertEqual(expect, code, err.getvalue())
        return json.loads(out.getvalue()) if code == 0 else err.getvalue()

    def plan(self, *flags, create=False, expect=0):
        mode = ("--create",) if create else ("--item-id", str(ITEM))
        return self.command("plan", "--content", str(self.content), "--journal", str(self.journal),
                            "--acceptance", "Reviewed release fixture", *mode, *flags, expect=expect)

    def upload(self):
        return publish.upload(self.upload_args, backend=self.backend)

    def locale_file(self, language, **text):
        path = self.root / f"{language}.json"
        path.write_text(json.dumps(text, ensure_ascii=False), encoding="utf-8")
        return f"{language}={path}"

    @staticmethod
    def step(state, operation):
        return next(step for step in state["steps"] if step["operation"] == operation)

    def test_content_only_does_not_change_any_page_fields_despite_about_dependencies(self):
        state = self.plan()
        self.assertEqual(["content"], [step["operation"] for step in state["steps"]])
        self.assertEqual({}, self.step(state, "content")["fields"])
        self.assertTrue(self.upload()["complete"])
        self.assertEqual([("start", ITEM), ("content",), ("submit", "")], self.steam.calls)

    def test_partial_locale_does_not_write_title_or_append_requirements_without_choice(self):
        self.plan("--locale", self.locale_file("schinese", description="这是新说明。"))
        self.assertTrue(self.upload()["complete"])
        self.assertEqual([("language", "schinese"), ("description", "这是新说明。")],
                         [call for call in self.steam.calls if call[0] in {"language", "description", "title"}])

    def test_requirement_text_updates_only_selected_description_slots(self):
        state = self.plan("--append-requirements", "--locale",
                          self.locale_file("schinese", description="这是新说明。"),
                          "--locale", self.locale_file("tchinese", title="新標題"))
        self.assertEqual({}, self.step(state, "content")["fields"])
        locales = {step["fields"]["language"]: step["fields"]
                   for step in state["steps"] if step["operation"] == "locale"}
        first = locales["schinese"]
        self.assertNotIn("title", first)
        self.assertTrue(first["description"].startswith("这是新说明。"))
        for text in ("First dependency", "Second dependency", "Biotech", "fixture.loadorder"):
            self.assertIn(text, first["description"])
        self.assertEqual({"language": "tchinese", "title": "新標題"}, locales["tchinese"])
        self.assertNotIn("dependencies", [step["operation"] for step in state["steps"]])

    def test_requirement_text_requires_a_selected_description(self):
        self.plan("--append-requirements", "--title", "New title", expect=1)
        self.assertFalse(self.journal.exists())

    def test_dependencies_are_opt_in_additive_and_do_not_submit_page_changes(self):
        state = self.plan("--add-dependencies")
        self.assertEqual({}, self.step(state, "content")["fields"])
        self.assertTrue(self.upload()["complete"])
        self.assertEqual({EXISTING_OTHER, REQUIRED_16, REQUIRED_17}, self.steam.items)
        self.assertEqual({BIOTECH}, self.steam.apps)
        self.assertEqual([("start", ITEM), ("content",), ("submit", ""),
                          ("dependency", ITEM, REQUIRED_17), ("dlc", ITEM, BIOTECH)], self.steam.calls)

    def test_unresolved_required_mod_is_reported_without_a_guessed_workshop_id(self):
        path = self.about / "About.xml"
        body = path.read_text(encoding="utf-8")
        path.write_text(body.replace("</v1.7>", "<li><packageId>fixture.localonly</packageId></li></v1.7>"),
                        encoding="utf-8")
        self.content = self.package()
        state = self.plan("--add-dependencies")
        self.assertEqual(["fixture.localonly"], state["unresolvedRequired"])
        self.assertEqual([REQUIRED_16, REQUIRED_17], self.step(state, "dependencies")["items"])
        completed = self.upload()
        self.assertEqual("done", self.step(completed, "dependencies")["state"])
        self.assertFalse(completed["dependenciesComplete"])
        self.assertEqual({EXISTING_OTHER, REQUIRED_16, REQUIRED_17}, self.steam.items)

    def test_malformed_and_foreign_workshop_urls_are_not_used_for_dependency_writes(self):
        path = self.about / "About.xml"
        body = path.read_text(encoding="utf-8").replace(
            f"https://steamcommunity.com/sharedfiles/filedetails/?id={REQUIRED_16}",
            "https://steamcommunity.com/sharedfiles/filedetails/?id=not-a-file-id",
        ).replace(
            f"https://steamcommunity.com/workshop/filedetails/?id={REQUIRED_17}",
            f"https://steamcommunity.com.example/workshop/filedetails/?id={REQUIRED_17}",
        )
        path.write_text(body, encoding="utf-8")
        self.content = self.package()
        state = self.plan("--add-dependencies")
        self.assertEqual({"fixture.first", "fixture.second"}, set(state["unresolvedRequired"]))
        self.assertEqual([], self.step(state, "dependencies")["items"])
        completed = self.upload()
        self.assertFalse(completed["dependenciesComplete"])
        self.assertNotIn("dependency", [call[0] for call in self.steam.calls])
        self.assertEqual({BIOTECH}, self.steam.apps)

    def test_conflicting_workshop_ids_for_the_same_versioned_dependency_are_not_written(self):
        path = self.about / "About.xml"
        extra = """<li><packageId>fixture.second</packageId>
                     <steamWorkshopUrl>https://steamcommunity.com/workshop/filedetails/?id=92005</steamWorkshopUrl>
                   </li>"""
        body = path.read_text(encoding="utf-8").replace("</v1.6>", extra + "</v1.6>")
        path.write_text(body, encoding="utf-8")
        self.content = self.package()
        state = self.plan("--add-dependencies")
        self.assertEqual(["fixture.second"], state["unresolvedRequired"])
        self.assertEqual([REQUIRED_16], self.step(state, "dependencies")["items"])
        self.upload()
        self.assertNotIn("dependency", [call[0] for call in self.steam.calls])

    def test_known_missing_dependency_resumes_without_uploading_content_again(self):
        self.plan("--add-dependencies")
        self.steam.accept_apps = False
        with patch.object(publish, "DEPENDENCY_VERIFY_SECONDS", 0, create=True):
            try:
                self.upload()
            except (publish.PublishError, publish.SteamworksError):
                pass
        state = publish.load(self.journal)
        self.assertEqual("done", self.step(state, "content")["state"])
        self.assertIn(self.step(state, "dependencies")["state"], {"failed", "pending"})
        self.assertIn(REQUIRED_17, self.steam.items)
        self.steam.calls.clear()
        self.steam.accept_apps = True
        self.assertTrue(self.upload()["complete"])
        self.assertEqual([("dlc", ITEM, BIOTECH)], self.steam.calls)

    def test_failed_dependency_read_back_after_a_write_blocks_automatic_replay(self):
        self.plan("--add-dependencies")

        def fail_after_write():
            if self.steam.dependency_writes:
                raise publish.SteamworksError("Interrupted dependency read-back")

        self.steam.read_failure = fail_after_write
        try:
            self.upload()
        except (publish.PublishError, publish.SteamworksError):
            pass
        self.assertEqual("unknown", self.step(publish.load(self.journal), "dependencies")["state"])
        self.steam.calls.clear()
        self.steam.read_failure = None
        with self.assertRaises(publish.PublishError):
            self.upload()
        self.assertEqual([], self.steam.calls)

    def test_oversize_jpeg_cover_preserves_displayed_exif_orientation(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is needed for compressed-image verification.")
        cover = self.root / "rotated.jpg"
        width, height = 1250, 750
        noise = random.Random(12).randbytes(width * height * 3)
        with Image.frombytes("RGB", (width, height), noise) as image:
            exif = image.getexif()
            exif[274] = 6  # Display this landscape JPEG as a portrait with a 90-degree rotation.
            image.save(cover, quality=100, subsampling=0, exif=exif)
        self.assertGreaterEqual(cover.stat().st_size, 1_000_000)
        state = self.plan("--preview", str(cover))
        asset = Path(self.step(state, "content")["fields"]["preview"]["path"])
        with Image.open(asset) as result:
            self.assertEqual("PNG", result.format)
            self.assertLess(result.width, result.height)
            self.assertGreaterEqual(result.width, 512)

    def test_dependency_query_failure_before_any_write_can_resume(self):
        self.plan("--add-dependencies")

        def fail_without_writing():
            raise publish.SteamworksError("Dependency query unavailable")

        self.steam.read_failure = fail_without_writing
        try:
            self.upload()
        except (publish.PublishError, publish.SteamworksError):
            pass
        state = publish.load(self.journal)
        self.assertEqual("done", self.step(state, "content")["state"])
        self.assertIn(self.step(state, "dependencies")["state"], {"failed", "pending"})
        self.assertEqual(0, self.steam.dependency_writes)
        self.steam.read_failure = None
        self.steam.calls.clear()
        self.assertTrue(self.upload()["complete"])
        self.assertEqual([("dependency", ITEM, REQUIRED_17), ("dlc", ITEM, BIOTECH)], self.steam.calls)

    def test_compression_preserves_original_and_existing_journal_asset(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is needed for compressed-image verification.")
        path = self.root / "cover.png"
        width, height = 1000, 800
        noise = random.Random(8).randbytes(width * height * 4)
        Image.frombytes("RGBA", (width, height), noise).save(path)
        original = path.read_bytes()
        self.assertGreaterEqual(len(original), 1_000_000)
        screenshot = self.root / "screenshot.png"
        Image.frombytes("RGB", (width, height), random.Random(10).randbytes(width * height * 3)).save(screenshot)
        screenshot_original = screenshot.read_bytes()
        self.assertGreaterEqual(len(screenshot_original), 1_000_000)
        state = self.plan("--preview", str(path), "--replace-screenshots", str(screenshot))
        fields = self.step(state, "content")["fields"]
        preview = fields["preview"]
        asset = Path(preview["path"])
        approved = asset.read_bytes()
        self.assertNotEqual(path, asset)
        self.assertLess(len(approved), 1_000_000)
        self.assertEqual(preview["sha256"], hashlib.sha256(approved).hexdigest())
        self.assertEqual(original, path.read_bytes())
        with Image.open(asset) as prepared:
            self.assertEqual("PNG", prepared.format)
            self.assertGreaterEqual(min(prepared.size), 512)
            self.assertLess(prepared.convert("RGBA").getchannel("A").getextrema()[0], 255)
        screenshot_asset = Path(fields["screenshots"][0]["path"])
        self.assertLess(screenshot_asset.stat().st_size, 1_000_000)
        with Image.open(screenshot_asset) as prepared:
            self.assertEqual("JPEG", prepared.format)
        self.assertEqual(screenshot_original, screenshot.read_bytes())
        another = self.root / "changed.png"
        Image.frombytes("RGBA", (width, height), random.Random(11).randbytes(len(noise))).save(another)
        self.plan("--preview", str(another), expect=1)
        self.assertEqual(approved, asset.read_bytes())

        asset.write_bytes(b"tampered")
        with self.assertRaises(publish.PublishError):
            self.upload()
        self.assertEqual([], self.steam.calls)

    def test_inspect_reads_requested_language_and_existing_dependencies_without_writes(self):
        seen = publish.inspect(SimpleNamespace(item_id=ITEM, sdk=self.sdk, timeout=2, language=["schinese"]),
                               backend=self.backend)
        self.assertEqual({"schinese": {"title": "schinese", "description": "Existing description"}}, seen["pages"])
        self.assertEqual({"items": sorted({EXISTING_OTHER, REQUIRED_16}), "apps": []}, seen["dependencies"])
        self.assertEqual([], self.steam.calls)

    def test_bind_is_explicit_requires_completed_upload_and_never_overwrites(self):
        def chunk(tag, contents):
            return (struct.pack(">I", len(contents)) + tag + contents
                    + struct.pack(">I", zlib.crc32(tag + contents)))

        preview = self.root / "cover.png"
        preview.write_bytes(b"\x89PNG\r\n\x1a\n"
                            + chunk(b"IHDR", struct.pack(">IIBBBBB", 512, 512, 8, 2, 0, 0, 0))
                            + chunk(b"IDAT", zlib.compress(bytes(512 * (1 + 512 * 3))))
                            + chunk(b"IEND", b""))
        self.plan("--project", str(self.project), "--title", "Initial title",
                  "--preview", str(preview), create=True)
        self.steam.submit_error = publish.SteamworksError("Definite submit rejection", result_code=8)
        with self.assertRaises(publish.SteamworksError):
            self.upload()
        bind_args = ("bind", "--journal", str(self.journal), "--project", str(self.project))
        self.command(*bind_args, expect=1)
        marker = self.about / "PublishedFileId.txt"
        self.assertFalse(marker.exists())
        self.steam.submit_error = None
        self.upload()
        self.assertFalse(marker.exists())

        marker.write_text(str(EXISTING_OTHER), encoding="ascii")
        self.command(*bind_args, expect=1)
        self.assertEqual(str(EXISTING_OTHER), marker.read_text(encoding="ascii").strip())
        marker.unlink()
        self.command(*bind_args)
        self.command(*bind_args)
        self.assertEqual(str(ITEM), marker.read_text(encoding="ascii").strip())


if __name__ == "__main__":
    unittest.main()
