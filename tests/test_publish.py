"""Offline checks for the publish planner. No Steam session is opened."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock
import zlib


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "rimworld-publish" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import publish  # noqa: E402
import steam_backend  # noqa: E402
from release_contract import VerifiedRelease  # noqa: E402


PACKAGE = "lzzd.example"
ITEM = 99
HARMONY = 2009463077
FORTIFIED = 3498575851
BIOTECH = 1826140
WORKSHOP = "https://steamcommunity.com/sharedfiles/filedetails/?id="
ABOUT = """<?xml version="1.0" encoding="utf-8"?>
<ModMetaData>
  <name>Example</name>
  <packageId>lzzd.example</packageId>
  <supportedVersions>{versions}</supportedVersions>
{dependencies}
</ModMetaData>
"""
# Declared the way RimWorld 1.7 reads it: one list per version, and bare ids for load order.
RESOLVABLE = f"""  <modDependenciesByVersion>
    <v1.7>
      <li>
        <packageId>brrainz.harmony</packageId>
        <displayName>Harmony</displayName>
        <steamWorkshopUrl>https://steamcommunity.com/workshop/filedetails/?id={HARMONY}</steamWorkshopUrl>
      </li>
      <li>
        <packageId>ludeon.rimworld.biotech</packageId>
        <displayName>Biotech</displayName>
      </li>
    </v1.7>
  </modDependenciesByVersion>"""
VERSIONED = RESOLVABLE.replace(
    "    </v1.7>",
    """      <li>
        <packageId>local.only</packageId>
        <displayName>Local Library</displayName>
      </li>
    </v1.7>""",
) + """
  <loadAfter>
    <li>brrainz.harmony</li>
    <li>AOBA.Framework</li>
  </loadAfter>"""
LEGACY = f"""  <modDependencies>
    <li>
      <packageId>brrainz.harmony</packageId>
      <name>Harmony</name>
      <steamWorkshopUrl>{WORKSHOP}{HARMONY}</steamWorkshopUrl>
    </li>
  </modDependencies>
  <loadAfter>
    <li>Aoba.Framework</li>
  </loadAfter>"""
ENGLISH_SECTION = (
    f"[b]Required[/b]\n[list]\n[*][url={WORKSHOP}{HARMONY}]Harmony[/url]\n[*]RimWorld - Biotech (DLC)\n"
    "[*]Local Library (local.only)\n[/list]\n"
    f"[b]Load order (optional)[/b]\n[list]\n[*][url={WORKSHOP}{FORTIFIED}]"
    "Fortified Features Framework[/url]\n[/list]"
)
CHINESE_SECTION = (
    f"[b]必需[/b]\n[list]\n[*][url={WORKSHOP}{HARMONY}]Harmony[/url]\n[*]RimWorld - Biotech（DLC）\n"
    "[*]Local Library (local.only)\n[/list]\n"
    f"[b]加载顺序（非必需）[/b]\n[list]\n[*][url={WORKSHOP}{FORTIFIED}]"
    "Fortified Features Framework[/url]\n[/list]"
)


def preview(path, size=512):
    """A valid solid-colour RGBA PNG; the plan only needs to read its dimensions."""

    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))

    row = b"\0" + b"\0\0\0\0" * size
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * size))
        + chunk(b"IEND", b"")
    )


class FakeSteam:
    """The surface publish.upload uses, over one in-memory Workshop item."""

    def __init__(self, dylib=None, run_dir=None, timeout=600):
        self.account = 76561198000000001
        self.created = 12345
        self.item = None
        self.held = set()
        self.queued = set()
        self.keeps_dependencies = True
        self.visibility = 2
        self.pages = {"english": {"title": "Example", "description": "Body", "previewUrl": "p", "screenshots": []},
                      "schinese": {"title": "示例", "description": "正文", "previewUrl": "p", "screenshots": []}}
        self.log = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def logged_on(self):
        return True

    def steam_id(self):
        return self.account

    def create_item(self):
        self.log.append(("create", self.created))
        return self.created, False

    def query_details(self, item_id, language="english"):
        return {"fileId": item_id, "consumerAppId": publish.APPID, "ownerSteamId": self.account,
                "visibility": self.visibility, **self.pages.get(language, self.pages["english"])}

    def query_dependencies(self, item_id):
        return {"items": sorted(value for kind, value in self.held if kind == "items"),
                "apps": sorted(value for kind, value in self.held if kind == "apps")}

    def start_update(self, item_id):
        self.item = item_id
        return object()

    def set_title(self, handle, text):
        self.log.append(("title", text))

    def set_description(self, handle, text):
        self.log.append(("description", text))

    def set_visibility(self, handle, value):
        self.log.append(("visibility", value))

    def set_preview(self, handle, path):
        self.log.append(("preview", Path(path).name))

    def set_content(self, handle, path):
        self.log.append(("content", Path(path).name))

    def add_dependency(self, handle, child):
        self.log.append(("add_dependency", child))
        self.queued.add(("items", child))

    def add_app_dependency(self, handle, app):
        self.log.append(("add_app_dependency", app))
        self.queued.add(("apps", app))

    def submit(self, handle, changenote=""):
        self.log.append(("submit", changenote, sorted(self.queued)))
        if self.keeps_dependencies:
            self.held |= self.queued
        self.queued = set()
        return {"result": 1, "needsAccept": False, "fileId": self.item}


class PublishCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.work = self.root / "work"
        self.work.mkdir()
        self.description = self.work / "description.txt"
        self.description.write_text("Body of the page.", encoding="utf-8")
        self.project = self.root / "project"
        (self.project / "About").mkdir(parents=True)
        (self.project / "About" / "About.xml").write_text(
            ABOUT.format(versions="<li>1.7</li>", dependencies=""), encoding="utf-8")
        self.steam = FakeSteam()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(publish, "DEFAULT_RUN_DIR", self.root / "run"))
        self.stack.enter_context(mock.patch.object(publish, "find_dylib", return_value=self.root / "lib.so"))
        self.stack.enter_context(mock.patch.object(publish, "DEPENDENCY_VERIFY_SECONDS", 0))
        self.stack.enter_context(mock.patch.object(publish, "workshop_package_index", return_value={
            "aoba.framework": (FORTIFIED, "Fortified Features Framework")}))

    def release(self, dependencies=VERSIONED, versions=("1.7",)):
        """A staged release whose verification is replaced by the contract it would return."""
        stage = self.root / f"release-{len(list(self.root.iterdir()))}"
        content = stage / "Example"
        (content / "About").mkdir(parents=True)
        (content / "About" / "About.xml").write_text(
            ABOUT.format(versions="".join(f"<li>{version}</li>" for version in versions),
                         dependencies=dependencies), encoding="utf-8")
        (content / "Defs").mkdir()
        (content / "Defs" / "A.xml").write_text("<Defs/>", encoding="utf-8")
        (stage / "manifest.json").write_text("{}", encoding="utf-8")
        (stage / "release-receipt.json").write_text("{}", encoding="utf-8")
        verified = VerifiedRelease(content, PACKAGE, "d" * 64, None, stage / "release-receipt.json",
                                   stage / "manifest.json", tuple(versions), 2)
        self.stack.enter_context(mock.patch.object(publish, "verify_release", return_value=verified))
        return verified

    def run_command(self, *argv, code=0):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(code, publish.main([*argv]))
        return json.loads(out.getvalue()) if code == 0 else err.getvalue()

    def plan(self, content, *extra, journal="plan.json"):
        path = self.work / journal
        state = self.run_command("plan", "--content", str(content), "--journal", str(path),
                                 "--acceptance", "static checks", "--description-file", str(self.description),
                                 *extra)
        return path, state

    def upload(self, journal):
        """upload() takes its Steam backend by argument; the CLI wrapper only parses arguments."""
        args = types.SimpleNamespace(journal=Path(journal), sdk=None, timeout=600)
        return publish.upload(args, backend=lambda *args, **kwargs: self.steam)

    def plan_update(self, dependencies=RESOLVABLE):
        return self.plan(self.release(dependencies).content, "--item-id", str(ITEM), "--changelog", "Note")[0]

    @staticmethod
    def step(state, operation):
        return next(step for step in state["steps"] if step["operation"] == operation)


class RequirementTests(PublishCase):
    def entries(self, dependencies=VERSIONED, versions=("1.7",)):
        return publish.release_requirements(self.release(dependencies, versions))

    def test_versioned_declarations_and_bare_load_order_are_read(self):
        entries = {entry["packageId"].casefold(): entry for entry in self.entries()}
        self.assertEqual(4, len(entries))
        harmony = entries["brrainz.harmony"]
        self.assertEqual(("Harmony", HARMONY, False, True),
                         (harmony["name"], harmony["itemId"], harmony["dlc"], harmony["required"]))
        biotech = entries["ludeon.rimworld.biotech"]
        self.assertEqual((None, True, True), (biotech["itemId"], biotech["dlc"], biotech["required"]))
        local = entries["local.only"]
        self.assertEqual((None, False, True), (local["itemId"], local["dlc"], local["required"]))
        # loadAfter alone is a load-order hint; its link comes from the installed Workshop content.
        framework = entries["aoba.framework"]
        self.assertEqual(("Fortified Features Framework", FORTIFIED, False),
                         (framework["name"], framework["itemId"], framework["required"]))

    def test_legacy_declarations_are_still_read(self):
        entries = {entry["packageId"].casefold(): entry for entry in self.entries(LEGACY)}
        self.assertEqual(("Harmony", HARMONY, True),
                         (entries["brrainz.harmony"]["name"], entries["brrainz.harmony"]["itemId"],
                          entries["brrainz.harmony"]["required"]))
        self.assertEqual((FORTIFIED, False),
                         (entries["aoba.framework"]["itemId"], entries["aoba.framework"]["required"]))

    def test_supported_versions_are_unioned_with_fallback_to_the_lower_one(self):
        dependencies = """  <modDependenciesByVersion>
    <v1.6>
      <li><packageId>a.one</packageId><displayName>One</displayName></li>
      <li><packageId>a.two</packageId><displayName>Two</displayName></li>
    </v1.6>
    <v1.7>
      <li><packageId>a.one</packageId><displayName>One</displayName></li>
    </v1.7>
  </modDependenciesByVersion>"""
        self.assertEqual(["a.one", "a.two"],
                         sorted(entry["packageId"] for entry in self.entries(dependencies, ("1.6", "1.7"))))
        # With no list of its own, 1.7 sees 1.6's list rather than nothing.
        fallback = dependencies.replace("v1.7>", "v1.8>")
        self.assertEqual(["a.one", "a.two"],
                         sorted(entry["packageId"] for entry in self.entries(fallback, ("1.6", "1.7"))))

    def test_without_dependencies_nothing_is_appended(self):
        self.assertEqual([], self.entries(""))
        self.assertEqual("", publish.requirements_section([], "english"))
        self.assertEqual("Body of the page.", publish.append_requirements("Body of the page.", ""))


class PlanTests(PublishCase):
    def plan_argv(self, content, *extra):
        return ["plan", "--content", str(content), "--journal", str(self.work / "plan.json"),
                "--acceptance", "static checks", *extra]

    def test_plan_requires_a_description_and_has_no_requirements_opt_out(self):
        content = self.release().content
        for extra in (["--item-id", str(ITEM)],
                      ["--item-id", str(ITEM), "--description-file", str(self.description),
                       "--changelog", "Note", "--append-requirements"]):
            with self.subTest(extra=extra), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                publish.main(self.plan_argv(content, *extra))

    def test_update_requires_a_change_note(self):
        error = self.run_command(*self.plan_argv(self.release().content, "--item-id", str(ITEM),
                                                 "--description-file", str(self.description)), code=1)
        self.assertIn("An update requires a change note.", error)
        self.assertFalse((self.work / "plan.json").exists())

    def test_plan_carries_description_requirements_and_required_items(self):
        _, state = self.plan(self.release().content, "--item-id", str(ITEM), "--changelog", "Fix the cloak layer.")
        self.assertEqual("Body of the page.\n\n" + ENGLISH_SECTION,
                         self.step(state, "content")["fields"]["description"])
        dependencies = self.step(state, "dependencies")
        self.assertEqual({"items": [HARMONY], "apps": [BIOTECH]},
                         {key: dependencies[key] for key in ("items", "apps")})
        self.assertEqual([{"packageId": "local.only", "name": "Local Library"}],
                         state["requirements"]["unresolved"])
        self.assertEqual("Fix the cloak layer.", state["changelog"])
        # A required mod without a Workshop ID stays open until it is handled by hand.
        self.assertEqual([{"item": "content", "state": "pending"},
                          {"item": "dependencies", "state": "pending"},
                          {"item": "dependencies", "state": "unresolved", "packageId": "local.only",
                           "name": "Local Library"}], state["incomplete"])
        self.assertFalse(state["complete"])

    def test_every_language_slot_gets_the_section_and_needs_a_title(self):
        content = self.release().content
        partial = self.work / "partial.json"
        partial.write_text(json.dumps({"description": "页面正文。"}, ensure_ascii=False), encoding="utf-8")
        error = self.run_command(*self.plan_argv(content, "--item-id", str(ITEM),
                                                 "--description-file", str(self.description),
                                                 "--changelog", "Note", "--locale",
                                                 f"schinese={partial}"), code=1)
        self.assertIn("A locale file must contain exactly a title and a description.", error)
        complete = self.work / "schinese.json"
        complete.write_text(json.dumps({"title": "示例", "description": "页面正文。"}, ensure_ascii=False),
                            encoding="utf-8")
        _, state = self.plan(content, "--item-id", str(ITEM), "--changelog", "Note",
                             "--locale", f"schinese={complete}")
        slot = self.step(state, "locale")["fields"]
        self.assertEqual(("schinese", "示例"), (slot["language"], slot["title"]))
        self.assertEqual("页面正文。\n\n" + CHINESE_SECTION, slot["description"])

    def test_blank_description_is_rejected(self):
        self.description.write_text("  \n", encoding="utf-8")
        error = self.run_command(*self.plan_argv(self.release().content, "--item-id", str(ITEM),
                                                 "--description-file", str(self.description),
                                                 "--changelog", "Note"), code=1)
        self.assertIn("description must contain text.", error)

    def test_create_still_requires_title_and_preview(self):
        error = self.run_command(*self.plan_argv(self.release().content, "--create",
                                                 "--description-file", str(self.description)), code=1)
        self.assertIn("A new item requires an explicit title and main preview.", error)


class UploadTests(PublishCase):
    def test_required_items_already_held_are_not_submitted_again(self):
        self.steam.held = {("items", HARMONY), ("apps", BIOTECH)}
        state = self.upload(self.plan_update())
        self.assertEqual([], [entry for entry in self.steam.log if entry[0].startswith("add_")
                              or (entry[0] == "submit" and entry[1] == "")])
        self.assertEqual("done", self.step(state, "dependencies")["state"])
        self.assertTrue(state["complete"])

    def test_required_items_are_written_and_confirmed_by_read_back(self):
        state = self.upload(self.plan_update())
        log = self.steam.log
        self.assertEqual([("add_dependency", HARMONY), ("add_app_dependency", BIOTECH)],
                         [entry for entry in log if entry[0].startswith("add_")])
        self.assertEqual([("submit", "", [("apps", BIOTECH), ("items", HARMONY)])],
                         [entry for entry in log if entry[0] == "submit" and entry[1] == ""])
        self.assertEqual("done", self.step(state, "dependencies")["state"])
        self.assertTrue(state["complete"])

    def test_dependencies_steam_drops_are_reported_as_failed_not_done(self):
        self.steam.keeps_dependencies = False
        state = self.upload(self.plan_update())
        self.assertEqual("done", self.step(state, "content")["state"])
        failed = self.step(state, "dependencies")
        self.assertEqual(("failed", {"items": [HARMONY], "apps": [BIOTECH]}),
                         (failed["state"], failed["missing"]))
        self.assertIn("Steam did not keep the required dependencies", failed["attempts"][-1]["error"])
        self.assertEqual([{"item": "dependencies", "state": "failed"}], state["incomplete"])
        self.assertFalse(state["complete"])
        # Once Steam holds them, a resumed upload confirms by read-back without submitting again.
        self.steam.held = {("items", HARMONY), ("apps", BIOTECH)}
        state = self.upload(self.work / "plan.json")
        self.assertEqual(1, sum(1 for entry in self.steam.log if entry[0] == "submit" and entry[1] == ""))
        self.assertNotIn("missing", self.step(state, "dependencies"))
        self.assertTrue(state["complete"])

    def create(self, *extra, journal="plan.json"):
        preview(self.work / "preview.png")
        content = self.release(dependencies="").content
        path, _ = self.plan(content, "--create", "--title", "Example",
                            "--preview", str(self.work / "preview.png"), journal=journal, *extra)
        return path, self.upload(path)

    def test_a_new_item_is_bound_to_the_project_before_the_publish_is_complete(self):
        journal, state = self.create("--project", str(self.project))
        marker = self.project / "About" / "PublishedFileId.txt"
        self.assertEqual(12345, state["itemId"])
        self.assertIn({"item": "marker", "state": "pending"}, state["incomplete"])
        self.assertFalse(state["complete"])
        self.assertFalse(marker.exists())
        bound = self.run_command("bind", "--journal", str(journal))
        self.assertEqual(b"12345", marker.read_bytes())
        self.assertEqual([], bound["incomplete"])
        self.assertTrue(bound["complete"])
        self.assertTrue(self.run_command("bind", "--journal", str(journal))["complete"])

    def test_bind_never_moves_a_project_to_another_item(self):
        journal, _ = self.create(journal="unbound.json")
        marker = self.project / "About" / "PublishedFileId.txt"
        marker.write_text("777", encoding="ascii")
        error = self.run_command("bind", "--journal", str(journal), "--project", str(self.project), code=1)
        self.assertIn("already bound to Workshop item 777", error)
        self.assertEqual(b"777", marker.read_bytes())

    def test_bind_waits_for_a_created_item(self):
        preview(self.work / "preview.png")
        path, _ = self.plan(self.release(dependencies="").content, "--create", "--project", str(self.project),
                            "--title", "Example", "--preview", str(self.work / "preview.png"))
        error = self.run_command("bind", "--journal", str(path), code=1)
        self.assertIn("Bind only after the creation step", error)

    def test_inspect_reads_the_page_and_dependencies_without_a_journal(self):
        self.steam.held = {("items", HARMONY), ("apps", BIOTECH)}
        args = types.SimpleNamespace(item_id=ITEM, sdk=None, timeout=600, language=None)
        seen = publish.inspect(args, backend=lambda *args, **kwargs: self.steam)
        self.assertEqual(("private", True, {"items": [HARMONY], "apps": [BIOTECH]}),
                         (seen["visibility"], seen["owned"], seen["dependencies"]))
        self.assertEqual({"english": {"title": "Example", "description": "Body"}}, seen["pages"])
        args.language = ["english", "schinese"]
        seen = publish.inspect(args, backend=lambda *args, **kwargs: self.steam)
        self.assertEqual({"english", "schinese"}, set(seen["pages"]))
        self.assertEqual([], self.steam.log)

    def test_journals_from_before_required_items_still_report(self):
        state = publish.public_status({"schema": 1, "appId": publish.APPID, "steps": [], "itemId": 5})
        self.assertEqual([], state["incomplete"])
        self.assertTrue(state["complete"])


class DependencyReadBackTests(unittest.TestCase):
    ITEM = 3845115353

    def steam(self, message):
        """A backend whose GetAppDependencies call answers with exactly these bytes."""
        steam = steam_backend.SteamworksUGC.__new__(steam_backend.SteamworksUGC)
        steam._types = steam_backend._abi(4)
        reply = steam._types["appDependencies"].from_buffer_copy(bytes(message))
        for patcher in (mock.patch.object(steam, "_ugc_call", return_value=7),
                        mock.patch.object(steam, "_wait_apicall", return_value=reply)):
            patcher.start()
            self.addCleanup(patcher.stop)
        return steam

    @staticmethod
    def message(file_offset, apps_offset, item=3845115353, result=1):
        payload = bytearray(148)
        struct.pack_into("<i", payload, 0, result)
        struct.pack_into("<Q", payload, file_offset, item)
        struct.pack_into("<I", payload, apps_offset, BIOTECH)
        struct.pack_into("<I", payload, 144, 1)
        return payload

    def test_both_known_platform_layouts_decode(self):
        for name, offsets in (("pack-4 (macOS, observed)", (4, 12)), ("pack-8 (Windows)", (8, 16))):
            with self.subTest(name=name):
                self.assertEqual([BIOTECH], self.steam(self.message(*offsets))._app_dependencies(self.ITEM))

    def test_a_layout_that_does_not_name_the_item_is_not_trusted(self):
        with self.assertRaisesRegex(steam_backend.SteamworksError, "布局"):
            self.steam(self.message(8, 16))._app_dependencies(HARMONY)

    def test_a_failed_read_is_an_error(self):
        with self.assertRaisesRegex(steam_backend.SteamworksError, "AccessDenied"):
            self.steam(self.message(4, 12, result=15))._app_dependencies(self.ITEM)

    def test_a_library_without_the_calls_fails_only_when_they_are_used(self):
        steam = steam_backend.SteamworksUGC.__new__(steam_backend.SteamworksUGC)
        steam._lib = types.SimpleNamespace()
        with self.assertRaisesRegex(steam_backend.SteamworksError, "缺少必需项目"):
            steam.add_dependency(1, HARMONY)

    def test_the_calls_bind_on_first_use(self):
        names = ("AddDependency", "AddAppDependency", "SetReturnChildren", "GetQueryUGCChildren",
                 "GetAppDependencies")
        steam = steam_backend.SteamworksUGC.__new__(steam_backend.SteamworksUGC)
        steam._lib = mock.Mock(spec=["SteamAPI_ISteamUGC_" + name for name in names])
        steam._ugc = None
        steam.add_dependency(1, HARMONY)
        steam.add_app_dependency(1, BIOTECH)
        steam._lib.SteamAPI_ISteamUGC_AddDependency.assert_called_once_with(None, 1, HARMONY)
        steam._lib.SteamAPI_ISteamUGC_AddAppDependency.assert_called_once_with(None, 1, BIOTECH)


if __name__ == "__main__":
    unittest.main()
