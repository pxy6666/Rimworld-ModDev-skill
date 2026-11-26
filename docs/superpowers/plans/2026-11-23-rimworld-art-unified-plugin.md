# Unified RimWorld Plugin and rimworld-art Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the duplicated Basic/Image distribution with one plugin containing an independently discoverable `rimworld-art` skill, including mandatory apparel alignment and coordinate/layer/shader visual contracts.

**Architecture:** Establish `rimworld-moddev/` as the only plugin source, keep all non-art RimWorld workflows unchanged, and move image-specific behavior into `rimworld-art`. Add dependency-free Python contract tests for package shape, catalog routing, manifests, Markdown links, and the two specialized art workflows.

**Tech Stack:** Agent Skills Markdown, JSON plugin/marketplace manifests, Python 3.11+ `unittest`, Git file moves, existing `tools/mod_cli.py`.

**Spec:** `docs/superpowers/specs/2026-11-23-rimworld-art-design.md`

## Global Constraints

- The release breaking the split is version `2.0.0`; all plugin and marketplace version fields must agree.
- The canonical plugin name is `rimworld-moddev`; do not retain permanent Basic/Image aliases.
- The canonical source directory is `rimworld-moddev/`; no second `basic/` or `image/` skill tree may remain.
- `rimworld-art` must be independently discoverable and must not change gameplay values, XML bindings, or C# behavior without handing that work to `rimworld-mod`.
- Image generation requires a real, authorized tool. Never embed credentials, silently switch providers/models, or describe a prompt as a completed image.
- Apparel is not complete without a matching body-type baseline, preserved canvas/origin, a composited body-plus-apparel preview, and target-renderer layer evidence.
- Coordinate position, render ordering, and shader interpretation are separate contracts. A PNG change cannot substitute for layer/shader evidence.
- Preserve all 1.6/1.7, debug, migration, release, and publish entry points and data.
- Do not commit or push unless the user explicitly requests it after implementation.

## File Map

### Create

- `tests/test_plugin_structure.py`: repository-level package, marketplace, catalog, link, and art-contract tests.
- `rimworld-moddev/skills/rimworld-art/SKILL.md`: discoverable art task router and handoff contract.
- `rimworld-moddev/skills/rimworld-art/references/apparel-alignment.md`: body baseline, composite template, canvas preservation, alpha, and layer acceptance.
- `rimworld-moddev/skills/rimworld-art/references/render-space.md`: coordinate/layer/shader model plus the drone example.
- `rimworld-moddev/skills/rimworld-art/references/visual-acceptance.md`: source-to-file-to-binding-to-game visual states.

### Move

- `image/` to `rimworld-moddev/`; `image/skills/` becomes the only distributed skill tree.
- `rimworld-moddev/skills/rimworld-mod/references/image-pipeline.md` to `rimworld-moddev/skills/rimworld-art/references/image-sources.md`.
- `rimworld-moddev/skills/rimworld-mod/references/gfx-workflow.md` to `rimworld-moddev/skills/rimworld-art/references/gfx-batch.md`.

### Modify

- `rimworld-moddev/plugin.json`
- `rimworld-moddev/.antigravity-plugin/plugin.json`
- `rimworld-moddev/.claude-plugin/plugin.json`
- `rimworld-moddev/.codex-plugin/plugin.json`
- `rimworld-moddev/.cursor-plugin/plugin.json`
- `rimworld-moddev/.zcode-plugin/plugin.json`
- `marketplace.json`
- `.agents/plugins/marketplace.json`
- `.claude-plugin/marketplace.json`
- `.cursor-plugin/marketplace.json`
- `rimworld-moddev/skills/catalog.json`
- `rimworld-moddev/skills/rimworld-help/SKILL.md`
- `rimworld-moddev/skills/rimworld-setup/SKILL.md`
- `rimworld-moddev/skills/rimworld-mod/references/assets.md`
- `rimworld-moddev/skills/rimworld-mod/references/verification.md`
- `README.md`

### Remove

- `basic/` after all five known Basic/Image differences have been merged into the canonical package.
- The Basic/Image-only marketplace entries and installation language.
- Old `rimworld-mod` references to the moved image-pipeline and GFX files.

---

### Task 1: Establish failing plugin architecture tests

**Files:**
- Create: `tests/test_plugin_structure.py`

**Interfaces:**
- Consumes: repository root, package-relative JSON, Markdown skill files.
- Produces: executable assertions for the single-package shape, 12-skill catalog, unified manifests, valid links, and required art contracts.

- [ ] **Step 1: Create the contract test module**

```python
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "rimworld-moddev"
MARKETPLACES = (
    ROOT / "marketplace.json",
    ROOT / ".agents/plugins/marketplace.json",
    ROOT / ".claude-plugin/marketplace.json",
    ROOT / ".cursor-plugin/marketplace.json",
)
PLATFORM_MANIFESTS = (
    PACKAGE / "plugin.json",
    PACKAGE / ".antigravity-plugin/plugin.json",
    PACKAGE / ".claude-plugin/plugin.json",
    PACKAGE / ".codex-plugin/plugin.json",
    PACKAGE / ".cursor-plugin/plugin.json",
    PACKAGE / ".zcode-plugin/plugin.json",
)


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def source_path(source):
    if isinstance(source, dict):
        return source["path"]
    return source


class PluginStructureTest(unittest.TestCase):
    def test_only_canonical_package_exists(self):
        self.assertTrue(PACKAGE.is_dir())
        self.assertFalse((ROOT / "basic").exists())
        self.assertFalse((ROOT / "image").exists())

    def test_every_marketplace_has_one_unified_entry(self):
        for path in MARKETPLACES:
            with self.subTest(path=path):
                plugins = read_json(path)["plugins"]
                self.assertEqual(1, len(plugins))
                self.assertEqual("rimworld-moddev", plugins[0]["name"])
                self.assertEqual(
                    "rimworld-moddev",
                    source_path(plugins[0]["source"]).removeprefix("./"),
                )

    def test_platform_manifests_use_unified_identity(self):
        for path in PLATFORM_MANIFESTS:
            with self.subTest(path=path):
                manifest = read_json(path)
                self.assertEqual("rimworld-moddev", manifest["name"])
                self.assertEqual("2.0.0", manifest["version"])

    def test_catalog_matches_skill_directories(self):
        catalog = read_json(PACKAGE / "skills/catalog.json")
        catalog_names = {skill["name"] for skill in catalog["skills"]}
        skill_names = {
            child.name
            for child in (PACKAGE / "skills").iterdir()
            if child.is_dir() and (child / "SKILL.md").is_file()
        }
        self.assertEqual(skill_names, catalog_names)
        self.assertEqual(12, len(catalog_names))
        self.assertIn("rimworld-art", catalog_names)
        self.assertNotIn("imageOnly", catalog)

    def test_relative_markdown_links_resolve(self):
        pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for markdown in (PACKAGE / "skills").rglob("*.md"):
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
        art = PACKAGE / "skills/rimworld-art"
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the contract tests and confirm the intended red state**

Run: `python3 -m unittest discover -s tests -p 'test_plugin_structure.py' -v`

Expected: FAIL because `rimworld-moddev/`, the unified entries, and `rimworld-art` do not exist yet.

---

### Task 2: Build the canonical package and unified platform manifests

**Files:**
- Move: `image/` to `rimworld-moddev/`
- Modify: `rimworld-moddev/plugin.json`
- Modify: all six `rimworld-moddev/.*/plugin.json` manifests listed in the file map
- Remove: `basic/`

**Interfaces:**
- Consumes: the Image tree, which is the superset of Basic.
- Produces: one package identity at `rimworld-moddev/` with version `2.0.0`.

- [ ] **Step 1: Confirm the source merge boundary**

Run:

```bash
diff -qr basic/skills image/skills
```

Expected: differences are limited to `rimworld-help`, `rimworld-setup`, `rimworld-mod/references/assets.md`, `rimworld-mod/references/gfx-workflow.md`, plus `image-pipeline.md`. Treat Image as the superset; do not discard any data or scripts.

- [ ] **Step 2: Make Image the canonical source and remove the duplicate tree**

```bash
git mv image rimworld-moddev
git rm -r basic
```

Do not remove `rimworld-moddev/skills/` or any non-art data while deleting the duplicate.

- [ ] **Step 3: Update all package manifests**

Set every package manifest's `name` to `rimworld-moddev`, its `version` to `2.0.0`, and its description to a concise statement that it supports RimWorld 1.6/1.7 mod development plus the independent `rimworld-art` workflow. Preserve platform-specific schema fields such as `skills`, `displayName`, `suggestedPrompts`, author, and repository.

Use these concrete identity changes:

```text
name: rimworld-moddev
displayName, where present: RimWorld ModDev
keywords: rimworld, mod, skills, art
```

Replace the Antigravity prompt about choosing one version with a prompt that asks to use `rimworld-art` for an apparel or style task.

- [ ] **Step 4: Run package-focused tests**

Run:

```bash
python3 tests/test_plugin_structure.py \
  PluginStructureTest.test_only_canonical_package_exists \
  PluginStructureTest.test_platform_manifests_use_unified_identity -v
```

Expected: both tests pass.

---

### Task 3: Unify root marketplace entries

**Files:**
- Modify: `marketplace.json`
- Modify: `.agents/plugins/marketplace.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `.cursor-plugin/marketplace.json`

**Interfaces:**
- Consumes: canonical package identity from Task 2.
- Produces: one installable plugin in every root marketplace.

- [ ] **Step 1: Replace each two-entry marketplace with one entry**

For string-source formats use:

```json
{
  "name": "rimworld-moddev",
  "source": "./rimworld-moddev",
  "version": "2.0.0"
}
```

For `.agents/plugins/marketplace.json`, preserve its native local-source object:

```json
{
  "name": "rimworld-moddev",
  "source": {"source": "local", "path": "./rimworld-moddev"},
  "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
  "category": "Developer Tools"
}
```

Preserve the owning name/interface, category, keywords, and platform-specific metadata. Remove the Basic/Image descriptions; replace the marketplace metadata with one sentence mentioning mod development, debugging, release, and art.

- [ ] **Step 2: Run the marketplace test**

Run:

```bash
python3 tests/test_plugin_structure.py \
  PluginStructureTest.test_every_marketplace_has_one_unified_entry -v
```

Expected: PASS.

---

### Task 4: Migrate generic image workflows without broken links

**Files:**
- Move: `rimworld-moddev/skills/rimworld-mod/references/image-pipeline.md`
- Move: `rimworld-moddev/skills/rimworld-mod/references/gfx-workflow.md`
- Create: `rimworld-moddev/skills/rimworld-art/references/visual-acceptance.md`
- Modify: `rimworld-moddev/skills/rimworld-mod/references/assets.md`
- Modify: `rimworld-moddev/skills/rimworld-mod/references/verification.md`
- Modify: `rimworld-moddev/skills/rimworld-help/SKILL.md`
- Modify: `rimworld-moddev/skills/rimworld-setup/SKILL.md`

**Interfaces:**
- Consumes: consumer/path specs from `rimworld-mod`; real image files or an authorized source.
- Produces: selected files, hashes/status, visual evidence, and a binding handoff for `rimworld-mod`.

- [ ] **Step 1: Move generic workflow documents**

```bash
mkdir -p rimworld-moddev/skills/rimworld-art/references
git mv \
  rimworld-moddev/skills/rimworld-mod/references/image-pipeline.md \
  rimworld-moddev/skills/rimworld-art/references/image-sources.md
git mv \
  rimworld-moddev/skills/rimworld-mod/references/gfx-workflow.md \
  rimworld-moddev/skills/rimworld-art/references/gfx-batch.md
```

In `image-sources.md`, replace the old links to `[制作循环](workflow.md)` and `[project-state.md](project-state.md)` with `../../rimworld-mod/references/workflow.md` and `../../rimworld-mod/references/project-state.md`. Keep the source-selection, capability probe, no-secret, failure, alpha, import, and evidence requirements.

In `gfx-batch.md`, replace the old `image-pipeline.md` link with `image-sources.md`, replace `assets.md` with `../../rimworld-mod/references/assets.md`, and preserve representative-sample-before-batch behavior.

- [ ] **Step 2: Add visual acceptance states**

Create `visual-acceptance.md` with exactly these states:

```text
待生成 → 已生成 → 已导入且文件已检查 → 已视觉检查 →
已绑定 → 已本机同步 → 已游戏验证
```

Require separate evidence for each transition. Define file evidence as path/hash/container/dimensions/alpha/canvas; binding evidence as consumer/path/load root/Def; visual evidence as actual viewed composite or runtime result. State that file existence, successful generation, or static XML validation cannot skip later states.

- [ ] **Step 3: Retarget existing links without duplicating workflows**

In `assets.md`, retain source/need/consumer/resource-license rules, but replace image-generation instructions with:

```markdown
需要生成或编辑视觉素材时，将用途、消费者、版本、路径、方向、体型、图形类、drawSize、层级、shader、保留项和授权交给 [图像来源流程](../../rimworld-art/references/image-sources.md)；完成的资源按 [视觉验收](../../rimworld-art/references/visual-acceptance.md) 回交本流程。
```

In `verification.md`, retain the general image row and replace the old GFX link with `../../rimworld-art/references/visual-acceptance.md`. In `rimworld-help` and `rimworld-setup`, point the existing image-capability sentences directly to `../rimworld-art/references/image-sources.md`; Task 6 will later route those entries through the standalone `SKILL.md`.

- [ ] **Step 4: Run the link test**

Run:

```bash
python3 tests/test_plugin_structure.py \
  PluginStructureTest.test_relative_markdown_links_resolve -v
```

Expected: PASS after all moved and changed links resolve.

---

### Task 5: Create the art entry, apparel contract, and rendering-space contract

**Files:**
- Create: `rimworld-moddev/skills/rimworld-art/SKILL.md`
- Create: `rimworld-moddev/skills/rimworld-art/references/apparel-alignment.md`
- Create: `rimworld-moddev/skills/rimworld-art/references/render-space.md`

**Interfaces:**
- Consumes: apparel/body consumers from `rimworld-mod`, verified body textures, target renderer evidence, and an authorized image tool.
- Produces: an independently discoverable art entry plus complete alignment/render contracts and stop conditions.

- [ ] **Step 1: Create the art routing skill**

Create `SKILL.md` with frontmatter:

```markdown
---
name: rimworld-art
description: 为 RimWorld 1.6/1.7 的贴图、Apparel、动画与视觉渲染任务制作和验收素材；缺少真实工具或对位基准时明确停在资源缺口。
---
```

The body must explicitly:

1. classify ordinary assets, apparel, batch/GFX, and dynamic rendering;
2. route ordinary generation to `image-sources.md`;
3. route multi-direction/batch work to `gfx-batch.md`;
4. require `apparel-alignment.md` for worn graphics;
5. require `render-space.md` for flight, suspension, projectile, parallax, or layer-sensitive work;
6. hand final file/path/consumer evidence to `rimworld-mod` rather than editing Def/C# itself;
7. hand a post-binding visual failure to `rimworld-debug`;
8. preserve the source, authorization, model/tool, prompt/reference, file hash, and final evidence.

- [ ] **Step 2: Write `apparel-alignment.md`**

Include these mandatory sections and rules:

1. identify the actual Def, `wornGraphicPath`/equivalent, graphic class, body type, sex/age/race variants, direction set, `drawSize`, load root, layer, and shader;
2. locate a version-matched vanilla or upstream body texture for every supported consumer;
3. build a fixed-canvas composite template containing the body baseline and apparel work layer;
4. generate/edit apparel in the template without redrawing the body or adding checkerboards/backgrounds;
5. export only the apparel layer with the same canvas, origin, direction, alpha, and binary/soft alpha convention;
6. forbid automatic trim, crop, recenter, rotation, or unilateral rescale;
7. generate a body-plus-apparel composite for each body/sex/type/direction;
8. check shoulder, waist, arms, legs, feet, side orientation, North/South front/back ordering, outerwear interaction, Pack/Belt mode, and small-size readability;
9. stop if no matching body baseline, no separable layers, an unstable canvas, failed alignment, or unknown render-layer order;
10. treat body baselines as reference evidence, not automatically distributable assets.

End with the explicit rule:

```text
仅 PNG 可打开、仅尺寸相同或仅 apparel 单图看起来正确，都不构成对位通过。
```

- [ ] **Step 3: Write `render-space.md` at the architectural level**

Lead with these three dimensions, in this order:

1. coordinate axes: logical movement, intended screen movement, and image canvas are distinct coordinate systems;
2. render layer: determines front/back occlusion and may be independent of pixel position;
3. shader/graphic pipeline: determines how coordinate movement and material are interpreted on screen.

Then define the combined contract as:

```text
目标位置/轨迹 + 应有遮挡顺序 + 目标渲染方式
```

Use the reference drone as an example only:

- map-plane movement plus a northward screen offset created the visible rise;
- the flyer used an elevated render layer for intended occlusion;
- the flying shader made the coordinate change render as takeoff/cruise/descent;
- the example is evidence, not a universal axis/layer/shader template.

End with handoff rules: `rimworld-art` defines expected visual behavior and evidence; `rimworld-mod` implements actual `DrawPos`, Def, layer, or shader changes; failures return to `rimworld-debug` with the three-part contract attached.

- [ ] **Step 4: Run the required-specialization assertions**

Run:

```bash
python3 tests/test_plugin_structure.py \
  PluginStructureTest.test_art_skill_has_required_specializations -v
```

Expected: PASS.

---

### Task 6: Wire catalog, help, setup, and cross-skill routing

**Files:**
- Modify: `rimworld-moddev/skills/catalog.json`
- Modify: `rimworld-moddev/skills/rimworld-help/SKILL.md`
- Modify: `rimworld-moddev/skills/rimworld-setup/SKILL.md`
- Modify: `rimworld-moddev/skills/rimworld-mod/references/assets.md`
- Modify: `rimworld-moddev/skills/rimworld-mod/references/verification.md`
- Test: `tests/test_plugin_structure.py`

**Interfaces:**
- Consumes: the `rimworld-art` skill from Tasks 4-5.
- Produces: 12 catalog entries and stable routes from existing skills.

- [ ] **Step 1: Add the art catalog entry**

Add:

```json
{
  "name": "rimworld-art",
  "targets": ["1.6", "1.7"],
  "requires": ["rimworld-mod", "rimworld-debug"]
}
```

Add `rimworld-art` to `rimworld-help`'s `requires` list. Remove the `imageOnly` property entirely. Keep all other 11 entries and target arrays unchanged.

- [ ] **Step 2: Route help to the standalone art entry**

Replace Task 4's temporary direct `image-sources.md` link with `../rimworld-art/SKILL.md`. Add short routing cases for:

- generate or edit a graphic;
- batch style consistency;
- apparel/worn graphic;
- animation or layer-sensitive rendering.

Do not list all technical fields in the help entry; point to the standalone skill.

- [ ] **Step 3: Route setup capability checks**

Keep setup's direct capability link at `../rimworld-art/references/image-sources.md`, because setup checks tools rather than running the full art entry. State that setup only verifies tool/edit/alpha capabilities and never starts a paid generation call.

- [ ] **Step 4: Route existing verification**

Confirm `rimworld-mod/references/verification.md` and `assets.md` return art work with the source-to-game acceptance states from `visual-acceptance.md`. Keep gameplay, XML, DLL, and functional behavior in the existing mod verification table; remove any remaining duplicate art instructions.

- [ ] **Step 5: Run catalog and link assertions**

Run:

```bash
python3 tests/test_plugin_structure.py \
  PluginStructureTest.test_catalog_matches_skill_directories \
  PluginStructureTest.test_relative_markdown_links_resolve -v
```

Expected: PASS with 12 entries and no old image-reference paths.

---

### Task 7: Rewrite installation and migration documentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the unified package/marketplace commands from Tasks 2-3.
- Produces: one install path and an explicit Basic/Image migration procedure.

- [ ] **Step 1: Rewrite the selection/install section**

Replace “选择 Basic 或 Image” with “统一安装；按任务调用”. Document `rimworld-art` as the 12th entry and explain that non-art workflows do not require image generation.
Set the documented current version to `2.0.0` and describe the single-plugin breaking change.

- [ ] **Step 2: Update all install commands**

Use `rimworld-moddev@rimworld-moddev-skill` for plugin-market installs and `./rimworld-moddev` for local Antigravity/Cursor-style installs. Replace manual copying from `basic/skills` or `image/skills` with copying all folders and `catalog.json` from `rimworld-moddev/skills`. Update every active hyperlink below `basic/skills/` or `image/skills/` to the matching canonical path below `rimworld-moddev/skills/`; route the old GFX link specifically to `rimworld-moddev/skills/rimworld-art/references/gfx-batch.md`.

Include this exact manual target tree:

```text
YourMod/.agents/skills/
├── catalog.json
├── rimworld-16-mod/
├── rimworld-16-debug/
├── rimworld-17-mod/
├── rimworld-17-debug/
├── rimworld-17-migrate/
├── rimworld-art/
├── rimworld-help/
├── rimworld-setup/
├── rimworld-mod/
├── rimworld-debug/
├── rimworld-release/
└── rimworld-publish/
```

- [ ] **Step 3: Add migration instructions**

Document a one-time 2.0.0 migration:

1. remove/disable `rimworld-moddev-basic` or `rimworld-moddev-image`;
2. install `rimworld-moddev`;
3. keep using existing mod/debug/migration/release/publish entry points;
4. call or let `rimworld-help` route to `rimworld-art` for image tasks.

Retain only migration references to `basic` and `image`; remove them from active installation and feature-selection language.

- [ ] **Step 4: Document art acceptance**

Add a concise section explaining:

- representative sample before batch generation;
- body-plus-apparel composite for worn graphics;
- coordinate, render layer, and shader as separate checks;
- source-to-game acceptance states;
- no generated-file success claim without actual tool output and later binding evidence.

- [ ] **Step 5: Check README references**

Run:

```bash
rg -n 'basic/skills|image/skills|rimworld-moddev-basic|rimworld-moddev-image' README.md
```

Expected: matches occur only in the 2.0.0 migration subsection, not active install commands or capability descriptions.

---

### Task 8: Run full package and regression validation

**Files:**
- Modify only when failures identify a real path or contract issue.
- Test: `tests/test_plugin_structure.py`
- Test: every JSON manifest and existing Python CLI.

**Interfaces:**
- Consumes: all completed Tasks 2-7.
- Produces: a clean single-plugin package with valid links and preserved non-art workflows.

- [ ] **Step 1: Run all repository contract tests**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Parse every JSON file in the package and marketplaces**

Run:

```bash
find rimworld-moddev .agents .claude-plugin .cursor-plugin -name '*.json' -print0 \
  | xargs -0 -n1 python3 -m json.tool >/dev/null
python3 -m json.tool marketplace.json >/dev/null
```

Expected: exit code 0 and no parse output.

- [ ] **Step 3: Check removed and stale routing references**

Run:

```bash
test ! -d basic && test ! -d image
rg -n 'rimworld-mod/references/(image-pipeline|gfx-workflow)\\.md' \
  rimworld-moddev README.md \
  && exit 1 || true
rg -n 'rimworld-moddev-basic|rimworld-moddev-image' \
  --glob '!docs/superpowers/specs/**' \
  --glob '!docs/superpowers/plans/**'
```

Expected: old directories are absent, old in-package links return no matches, and old plugin names appear only in README migration text plus non-active historical design/plan text.

- [ ] **Step 4: Preserve the existing tool entry point**

Run:

```bash
python3 tools/mod_cli.py --help >/dev/null
git --no-pager diff --check
```

Expected: exit code 0; the unified packaging did not break the release packager or introduce whitespace errors.

- [ ] **Step 5: Inspect the final changed-file boundary**

Run:

```bash
git --no-pager status --short
git --no-pager diff --stat
```

Expected: changes are limited to the canonical package rename, new art files, market/README updates, tests, and the two design-plan documents. No target-project files, generated release packages, or credentials are present.

## Final Plan Self-Review

- [ ] Plugin structure: Tasks 2-3 remove duplication and implement one identity.
- [ ] Skill discovery: Tasks 5 and 6 implement the 12th entry and all routes.
- [ ] Generic art: Task 4 preserves source selection, batch behavior, and visual states.
- [ ] Apparel: Task 5 implements body baselines, composite templates, canvas/origin preservation, layer evidence, and hard stop conditions.
- [ ] Render space: Task 5 defines coordinate, layer, and shader as separate dimensions and uses the drone as an example rather than a universal template.
- [ ] Migration: Task 7 gives the one-time 2.0.0 uninstall/install path without permanent aliases.
- [ ] Regression: Task 8 validates JSON, links, catalog, old paths, and the existing CLI.
