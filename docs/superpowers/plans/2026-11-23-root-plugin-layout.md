# Root Plugin Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repository root the single `rimworld-moddev` plugin, with one shared `skills/` tree and one platform-specific manifest directory per Agent.

**Architecture:** Move the canonical skills tree and manifests out of `rimworld-moddev/`, retain platform-specific JSON only in root hidden directories, and change every marketplace/tool/document path to resolve from the repository root. Contract tests will reject duplicate or stale package roots.

**Tech Stack:** Git file moves, Agent Skills Markdown, JSON plugin/marketplace manifests, Python 3.11+ `unittest`, existing `tools/mod_cli.py`.

**Spec:** `docs/superpowers/specs/2026-11-23-root-plugin-layout-design.md`

## Global Constraints

- The repository root is the only plugin root.
- Root `skills/` is the only source of RimWorld skills; do not copy it under any Agent directory.
- Preserve all 12 existing skill directories, scripts, data, references, and art fixtures.
- Platform adapter directories are `.agents/plugins`, `.antigravity-plugin`, `.claude-plugin`, `.codex-plugin`, `.cursor-plugin`, and `.zcode-plugin`.
- Every marketplace source resolves to `./`, and every platform manifest keeps plugin name `rimworld-moddev` and version `2.0.0`.
- Preserve each platform's native schema; copy no Codex-only `skills` field to a platform that does not currently accept it.
- Cursor keeps its existing hooks field; `plugin.json` files with an explicit `skills` field must resolve it to root `./skills/`.
- `rimworld-moddev/` and `rimworld-moddev/skills` must not remain.
- `tools/mod_cli.py` must fail clearly when root `skills/catalog.json` is missing; it must not fall back to a nested plugin path.
- Do not commit, push, publish, or create a pull request unless the user explicitly requests it after implementation.

## File Map

### Move

- `rimworld-moddev/skills/` → `skills/`
- `rimworld-moddev/.antigravity-plugin/` → `.antigravity-plugin/`
- `rimworld-moddev/.codex-plugin/` → `.codex-plugin/`
- `rimworld-moddev/.zcode-plugin/` → `.zcode-plugin/`
- `rimworld-moddev/.claude-plugin/plugin.json` → `.claude-plugin/plugin.json`
- `rimworld-moddev/.cursor-plugin/plugin.json` → `.cursor-plugin/plugin.json`

### Modify

- `tests/test_plugin_structure.py`
- `.agents/plugins/marketplace.json`
- `.claude-plugin/marketplace.json`
- `.cursor-plugin/marketplace.json`
- `marketplace.json`
- moved `.codex-plugin/plugin.json`
- moved `.cursor-plugin/plugin.json`
- `tools/mod_cli.py`
- `README.md`

### Delete

- `rimworld-moddev/plugin.json`
- empty `rimworld-moddev/` remnants

---

### Task 1: Rewrite root-layout contract tests first

**Files:**
- Modify: `tests/test_plugin_structure.py`

**Interfaces:**
- Consumes: current plugin files before any move.
- Produces: executable expected-state assertions for the final Superpowers-style layout.

- [ ] **Step 1: Change package constants and platform paths**

At the top of `tests/test_plugin_structure.py`, replace the nested package constant with the repository root:

```python
PACKAGE = ROOT
SKILLS = ROOT / "skills"
```

Replace `PLATFORM_MANIFESTS` with:

```python
PLATFORM_MANIFESTS = (
    ROOT / ".antigravity-plugin/plugin.json",
    ROOT / ".claude-plugin/plugin.json",
    ROOT / ".codex-plugin/plugin.json",
    ROOT / ".cursor-plugin/plugin.json",
    ROOT / ".zcode-plugin/plugin.json",
)
```

Keep the four marketplace constants.

- [ ] **Step 2: Assert the nested package is gone**

Rewrite `test_only_canonical_package_exists`:

```python
def test_only_canonical_package_exists(self):
    self.assertFalse((ROOT / "rimworld-moddev").exists())
    self.assertTrue(SKILLS.is_dir())
    self.assertFalse((ROOT / "basic").exists())
    self.assertFalse((ROOT / "image").exists())
```

- [ ] **Step 3: Assert root marketplace sources and root manifest paths**

Update `test_every_marketplace_has_one_unified_entry` so every normalized source explicitly names the repository root:

```python
source = source_path(plugins[0]["source"])
self.assertIn(source, (".", "./"))
```

The test must also normalize a future Agents `{"url": "./"}` source:

```python
def source_path(source):
    if isinstance(source, dict):
        return source.get("path", source.get("url"))
    return source
```

Keep the one-entry and plugin-name checks. Version presence remains format-specific; enforce `2.0.0` in platform manifests rather than guessing marketplace fields that a platform does not define.

- [ ] **Step 4: Assert explicit skill pointers resolve from root**

Add:

```python
def test_platform_skill_paths_resolve_from_plugin_root(self):
    for platform in (".codex-plugin", ".cursor-plugin"):
        with self.subTest(platform=platform):
            manifest_path = ROOT / platform / "plugin.json"
            manifest = read_json(manifest_path)
            skills_path = (ROOT / manifest["skills"]).resolve()
            self.assertEqual(SKILLS.resolve(), skills_path)
```

Cursor's test must continue to assert that `hooks` exists if the current manifest already contains it.

- [ ] **Step 5: Assert there is one skills source**

Change `test_catalog_matches_skill_directories` to use `SKILLS`, and add:

```python
duplicates = list(ROOT.rglob("skills/catalog.json"))
self.assertEqual([SKILLS / "catalog.json"], duplicates)
```

Change `test_relative_markdown_links_resolve` and `test_art_skill_has_required_specializations` to use `SKILLS` and `SKILLS / "rimworld-art"`.

- [ ] **Step 6: Run the tests and verify the intended red state**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Expected: FAIL because root `skills/`, root platform `plugin.json` files, and root marketplace sources do not exist yet. Failures must specifically mention the not-yet-migrated root layout, not regressions inside the art fixture tests.

---

### Task 2: Move the canonical skills and platform manifests to the repository root

**Files:**
- Move: `rimworld-moddev/skills/` to `skills/`
- Move: `rimworld-moddev/.antigravity-plugin/` to `.antigravity-plugin/`
- Move: `rimworld-moddev/.codex-plugin/` to `.codex-plugin/`
- Move: `rimworld-moddev/.zcode-plugin/` to `.zcode-plugin/`
- Move: `rimworld-moddev/.claude-plugin/plugin.json` to `.claude-plugin/plugin.json`
- Move: `rimworld-moddev/.cursor-plugin/plugin.json` to `.cursor-plugin/plugin.json`
- Delete: `rimworld-moddev/plugin.json`

**Interfaces:**
- Consumes: the current 12-skill canonical tree from `rimworld-moddev/skills`.
- Produces: one root `skills/` tree and six root adapter directories.

- [ ] **Step 1: Move the shared source tree**

```bash
git mv rimworld-moddev/skills skills
```

Do not edit any skill file while moving.

- [ ] **Step 2: Move platform-only directories that do not yet exist at root**

```bash
git mv rimworld-moddev/.antigravity-plugin .antigravity-plugin
git mv rimworld-moddev/.codex-plugin .codex-plugin
git mv rimworld-moddev/.zcode-plugin .zcode-plugin
```

Check that no target existed before each move.

- [ ] **Step 3: Merge Claude and Cursor manifests into existing root directories**

```bash
git mv rimworld-moddev/.claude-plugin/plugin.json .claude-plugin/plugin.json
git mv rimworld-moddev/.cursor-plugin/plugin.json .cursor-plugin/plugin.json
```

Leave `.claude-plugin/marketplace.json` and `.cursor-plugin/marketplace.json` in place.

- [ ] **Step 4: Remove the obsolete nested package**

```bash
git rm rimworld-moddev/plugin.json
rmdir rimworld-moddev/.claude-plugin
rmdir rimworld-moddev/.cursor-plugin
rmdir rimworld-moddev
```

Use `find rimworld-moddev -maxdepth 3 -print` first if an `rmdir` refuses to continue; do not delete uninspected files.

- [ ] **Step 5: Run layout and catalog tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_plugin_structure.py \
  PluginStructureTest.test_only_canonical_package_exists \
  PluginStructureTest.test_catalog_matches_skill_directories \
  PluginStructureTest.test_relative_markdown_links_resolve -v
```

Expected: the root-layout and catalog/link tests pass. Marketplace and manifest-path tests may remain red until Tasks 3-4.

---

### Task 3: Unify platform manifests and marketplace sources at root

**Files:**
- Modify: `.agents/plugins/marketplace.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `.cursor-plugin/marketplace.json`
- Modify: `marketplace.json`
- Modify: `.codex-plugin/plugin.json`
- Modify: `.cursor-plugin/plugin.json`
- Verify unchanged schema: `.antigravity-plugin/plugin.json`
- Verify unchanged schema: `.claude-plugin/plugin.json`
- Verify unchanged schema: `.zcode-plugin/plugin.json`

**Interfaces:**
- Consumes: root adapter directories from Task 2.
- Produces: one plugin identity and one root-resolving install source for every market.

- [ ] **Step 1: Make marketplace sources point to the repository root**

For string-source marketplaces:

```json
"source": "./"
```

For `.agents/plugins/marketplace.json`, preserve its object format and set only the location field:

```json
"source": {"source": "local", "path": "./"}
```

If implementation evidence shows this client accepts Superpowers-style `{"source":"url","url":"./"}`, use that native form only after confirming the marketplace schema accepts it; otherwise retain the existing `local/path` shape.

Preserve marketplace name, interface, policy, category, version, description, author/owner, and keywords.

- [ ] **Step 2: Preserve root platform metadata**

For each moved `plugin.json`:

- keep `"name": "rimworld-moddev"`;
- keep `"version": "2.0.0"`;
- keep the platform's author, repository, display name, suggested prompts, keywords, and any extra schema fields;
- do not add fields merely because another platform uses them.

- [ ] **Step 3: Fix explicit skill roots**

Set:

```json
// .codex-plugin/plugin.json
"skills": "./skills/"
```

```json
// .cursor-plugin/plugin.json
"skills": "./skills/"
```

Keep Cursor's existing `hooks` field unchanged.

- [ ] **Step 4: Run manifest and marketplace tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_plugin_structure.py \
  PluginStructureTest.test_every_marketplace_has_one_unified_entry \
  PluginStructureTest.test_platform_manifests_use_unified_identity \
  PluginStructureTest.test_platform_skill_paths_resolve_from_plugin_root -v
```

Expected: PASS for all four marketplaces and five platform `plugin.json` files; the sixth adapter directory is `.agents/plugins`, which carries a marketplace rather than a plugin manifest.

---

### Task 4: Point tools and documentation at the root plugin

**Files:**
- Modify: `tools/mod_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: root `skills/` and root marketplaces from Tasks 2-3.
- Produces: root-resolving CLI behavior and one documented installation model.

- [ ] **Step 1: Simplify `bundled_skills()`**

Replace the nested fallback in `tools/mod_cli.py` with:

```python
def bundled_skills():
    distribution = Path(__file__).resolve().parents[1]
    source = distribution / "skills"
    if not (source / "catalog.json").is_file():
        raise FileNotFoundError(
            f"Bundled skills catalog missing: {source / 'catalog.json'}"
        )
    return source
```

Do not swallow the error or return a missing path.

- [ ] **Step 2: Rewrite README install roots**

Update README so:

- the plugin root is `.`, not `./rimworld-moddev`;
- local Antigravity/Cursor-style install selects/imports the repository root;
- manual installation copies `skills/` from the repository root;
- active reference links begin with `skills/...`;
- the 2.0.0 migration text points existing installs at the new root update rather than a nested package;
- old Basic/Image names remain only where they are historical migration references.

Replace stale active instructions such as:

```text
agy plugin validate ./rimworld-moddev
agy plugin install ./rimworld-moddev
rimworld-moddev/skills/...
```

with:

```text
agy plugin validate .
agy plugin install .
skills/...
```

- [ ] **Step 3: Update CLI regression assertion**

In `tests/test_plugin_structure.py`, change `test_cli_uses_canonical_bundled_skills` to expect `ROOT / "skills"` and add imports for `shutil` and `tempfile`. Then add an explicit missing-catalog behavior test with a module copied into an otherwise empty temporary plugin root:

```python
def test_cli_reports_missing_bundled_skills(self):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        tools = root / "tools"
        tools.mkdir()
        module_path = tools / "mod_cli.py"
        shutil.copy2(ROOT / "tools/mod_cli.py", module_path)

        spec = importlib.util.spec_from_file_location("isolated_mod_cli", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with self.assertRaisesRegex(
            FileNotFoundError, "Bundled skills catalog missing"
        ):
            module.bundled_skills()
```

- [ ] **Step 4: Run CLI, README, and link checks**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_plugin_structure.py \
  PluginStructureTest.test_cli_uses_canonical_bundled_skills \
  PluginStructureTest.test_relative_markdown_links_resolve -v
python3 tools/mod_cli.py --help >/dev/null
rg -n 'rimworld-moddev/skills|\\./rimworld-moddev|basic/skills|image/skills' README.md
```

Expected: tests and CLI help pass; the README search returns no active nested-install paths.

---

### Task 5: Run full migration regression and inspect package boundary

**Files:**
- Test: all files in `tests/`

**Interfaces:**
- Consumes: the integrated root layout, manifests, marketplace files, tools, and docs.
- Produces: one clean, root-resolving plugin with all prior evidence preserved.

- [ ] **Step 1: Run the full test suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Expected: every structure, art fixture, tool helper, link, and catalog test passes.

- [ ] **Step 2: Parse every JSON document**

Run:

```bash
find . -path './.git' -prune -o -name '*.json' -print0 \
  | xargs -0 -n1 python3 -m json.tool >/dev/null
```

Expected: exit 0.

- [ ] **Step 3: Prove there is no nested or stale source**

Run:

```bash
test ! -e rimworld-moddev
test "$(find . -path './.git' -prune -o -name catalog.json -print | wc -l | tr -d ' ')" = "1"
rg -n 'rimworld-moddev/skills|\"source\"\\s*:\\s*\"\\./rimworld-moddev\"|basic/skills|image/skills' \
  --glob '!docs/superpowers/specs/**' \
  --glob '!docs/superpowers/plans/**'
```

Expected: the nested directory and stale references do not exist. The search returns no active matches; historical migration references may remain only in README prose outside path/link syntax.

- [ ] **Step 4: Verify the bundled CLI helpers from root**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
from tools.mod_cli import bundled_skills

skills = bundled_skills()
assert skills == Path.cwd() / "skills"
assert (skills / "rimworld-debug/scripts/content_load.py").is_file()
assert (skills / "rimworld-mod/scripts/source_cache.py").is_file()
print(skills)
PY
```

Expected: print the repository's root `skills/` path and exit 0.

- [ ] **Step 5: Check final boundaries**

Run:

```bash
git --no-pager diff --check
git --no-pager status --short
git --no-pager diff --stat
find skills -maxdepth 2 -name SKILL.md -print | sort
```

Expected: no whitespace errors, no `rimworld-moddev/` directory, exactly 12 `SKILL.md` files, and only planned moves/manifest/path/document/test updates.

## Final Plan Self-Review

- [ ] Root source: Tasks 2 and 5 make `skills/` the only skills source.
- [ ] Per-Agent adapters: Task 2 moves each manifest into its root hidden platform directory; Task 3 preserves schemas.
- [ ] Marketplace roots: Task 3 points every marketplace at `./`.
- [ ] CLI behavior: Task 4 removes the stale nested fallback and verifies a clear missing-catalog error.
- [ ] README: Task 4 removes nested install roots and manual copy paths.
- [ ] Compatibility: Task 3 preserves Cursor hooks, explicit Codex/Cursor skill roots, and each marketplace's native source shape.
- [ ] Regression: Task 5 verifies JSON, links, catalog, art fixtures, stale paths, and shipped helper resolution.
