"""Local RimWorld checks and build receipts; does not emulate the game loader."""
from __future__ import annotations
import argparse
import fnmatch
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
import zipfile

IGNORED = {'.git', '.agents', '.cursor', '.local', 'refs', 'bin', 'obj', '.vs', '__pycache__'}
# Waylith/Brutal are the shipped 1.7 engine modules, not generic SDK vendor libraries.
FORBIDDEN_DLL = re.compile(r'^(0Harmony|Assembly-CSharp|RimWorld|mscorlib|netstandard|UnityEngine.*|UnityStubs|Waylith.*|Brutal.*|System.*|Microsoft\.(CSharp|VisualBasic.*|Win32.*)|coreclr|clrjit|hostfxr|hostpolicy)\.dll$', re.I)
BUILD_KEYS = ('version', 'assemblyName', 'languageVersion', 'sourceDir', 'references',
              'sourceInclude', 'sourceExclude', 'defines', 'targetFramework', 'gameReferences', 'artifactMode')
PATH_KEYS = {'gameRoot', 'harmonyDll', 'pythonExe', 'referencePaths', 'frameworkReferenceDir'}

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def unique_path(root, kind, suffix=''):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return root / '.local' / kind / (stamp + '-' + uuid.uuid4().hex[:8] + suffix)

def within(root, path):
    target = Path(path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f'Output must stay inside project: {target}')
    return target


def bundled_skills():
    distribution = Path(__file__).resolve().parents[1]
    source = distribution / 'skills'
    if not (source / 'catalog.json').is_file():
        raise FileNotFoundError(f'Bundled skills catalog missing: {source / "catalog.json"}')
    return source

def config(root, target=None):
    cfg = dict(schema=1, version='1.6', assemblyName='Mod', sourceDir='Source', languageVersion='7.3', references=[],
               sourceInclude=[], sourceExclude=[], defines=[], targetFramework=None, gameReferences=None, artifactMode='compiled')
    shared, local = {}, {}
    for name in ('mod.json', 'mod.local.json'):
        path = root / 'config' / name
        if path.exists():
            values = json.loads(path.read_text(encoding='utf-8-sig'))
            if name == 'mod.local.json' and set(values) - (PATH_KEYS | {'targets'}):
                raise ValueError('Local configuration accepts environment paths only; use mod.json for build settings')
            if name == 'mod.local.json':
                local = values
            else:
                shared = values
    cfg.update(shared)
    selected = target or cfg['version']
    targets = shared.get('targets', {})
    if not isinstance(targets, dict) or any(k not in ('1.6', '1.7') or not isinstance(v, dict) for k, v in targets.items()):
        raise ValueError('targets must map 1.6/1.7 to target build settings')
    if target and selected != cfg['version'] and selected not in targets:
        raise ValueError('Target is not configured: ' + selected)
    cfg.update(targets.get(selected, {}))
    cfg['version'] = selected
    cfg['_configuredVersions'] = sorted(set(targets) | {shared.get('version', '1.6')})
    local_targets = local.get('targets', {})
    if not isinstance(local_targets, dict) or any(k not in ('1.6', '1.7') or not isinstance(v, dict) or set(v) - PATH_KEYS for k, v in local_targets.items()):
        raise ValueError('Local targets accept environment paths only')
    cfg.update({k: v for k, v in local.items() if k != 'targets'})
    cfg.update(local_targets.get(selected, {}))
    cfg.pop('targets', None)
    for key in ('version', 'assemblyName', 'sourceDir'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', cfg[key]) or cfg[key] in ('.', '..'):
            raise ValueError(f'Unsafe config {key}')
    refs = cfg['references']
    if not isinstance(refs, list) or any(not isinstance(r, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', r) for r in refs):
        raise ValueError('references must contain assembly reference identifiers')
    if len(refs) != len(set(refs)):
        raise ValueError('Duplicate reference identifier')
    if not isinstance(cfg.get('referencePaths', {}), dict):
        raise ValueError('referencePaths must map reference identifiers to DLL paths')
    for key in ('sourceInclude', 'sourceExclude', 'defines'):
        if not isinstance(cfg[key], list) or any(not isinstance(v, str) or not v for v in cfg[key]):
            raise ValueError(key + ' must be a list of nonempty strings')
    for pattern in cfg['sourceInclude'] + cfg['sourceExclude']:
        if Path(pattern).is_absolute() or '..' in Path(pattern.replace('\\', '/')).parts or ':' in pattern:
            raise ValueError('Source patterns must stay project-relative')
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', v) for v in cfg['defines']):
        raise ValueError('Invalid conditional compilation symbol')
    if cfg['artifactMode'] not in ('compiled', 'prebuilt'):
        raise ValueError('artifactMode must be compiled or prebuilt')
    if cfg['gameReferences'] is not None and (not isinstance(cfg['gameReferences'], list) or any(not isinstance(v, str) or Path(v).name != v or not v.endswith('.dll') for v in cfg['gameReferences'])):
        raise ValueError('gameReferences must be DLL filenames in the game assembly directory')
    for key in ('gameRoot', 'harmonyDll', 'frameworkReferenceDir'):
        if cfg.get(key):
            cfg[key] = str((root / cfg[key]).resolve())
    return cfg

def reference_bindings(root, cfg):
    result = {}
    for identifier in cfg.get('references', []):
        value = cfg.get('referencePaths', {}).get(identifier)
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Missing local referencePaths entry: ' + identifier)
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if not path.is_file() or path.suffix.lower() != '.dll':
            raise ValueError('Missing DLL reference: ' + identifier)
        result[identifier] = str(path)
    return result

def linked_path(path):
    """Directory junctions are links too; never silently flatten them for release."""
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def tracked(root):
    files = {}
    for folder, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if d not in IGNORED and not linked_path(Path(folder, d)))
        for name in sorted(names):
            path = Path(folder, name)
            if not linked_path(path) and name != 'mod.local.json' and not name.endswith(('.pyc', '.user')):
                files[path.relative_to(root).as_posix()] = digest(path)
    return files

def xml_inventory(root, files):
    defs, deps, errors = {}, [], []
    for rel in files:
        if not rel.lower().endswith('.xml'):
            continue
        try:
            node = ET.parse(root / rel).getroot()
        except (ET.ParseError, OSError) as exc:
            errors.append(dict(code='xml_parse', file=rel, message=str(exc)))
            continue
        if rel == 'About/About.xml':
            deps = sorted({(n.text or '').strip().lower() for n in node.findall('./modDependencies/li/packageId') if n.text})
        if 'Defs' in Path(rel).parts:
            if node.tag != 'Defs':
                errors.append(dict(code='defs_root', file=rel, message='Expected Defs root'))
            for item in node:
                name = item.findtext('defName')
                if name:
                    defs.setdefault(item.tag + ':' + name.strip(), []).append(rel)
        if 'Patches' in Path(rel).parts:
            if node.tag != 'Patch':
                errors.append(dict(code='patch_root', file=rel, message='Expected Patch root'))
            for xpath in node.iter('xpath'):
                if not (xpath.text or '').strip():
                    errors.append(dict(code='empty_xpath', file=rel, message='Empty xpath'))
    return defs, deps, errors

def take_snapshot(root, cfg=None):
    files = tracked(root)
    defs, deps, errors = xml_inventory(root, files)
    result = dict(schema=1, root=str(root.resolve()), createdUtc=datetime.now(timezone.utc).isoformat(),
                  files=files, defKeys=sorted(defs), dependencies=deps, xmlProblems=errors)
    if cfg:
        result['target'] = cfg['version']
    return result

def content_load_report(root, target, baseline_target=None, baseline_report=None):
    """Use the shipped portable auditor; never claim a reconstructed game loader."""
    script = bundled_skills() / 'rimworld-debug/scripts/content_load.py'
    if not script.is_file():
        return dict(schema=1, target=target, roots=[], files=[], errors=[], warnings=[],
                    unverified=[dict(code='content_auditor_missing', message='Content-root audit unavailable: restore the project content_load.py helper before release')])
    spec = importlib.util.spec_from_file_location('rimworld_content_load', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.audit(root, target, baseline_target, baseline_report)


def check(root, cfg, profile=None, baseline=None, allowed_dependencies=(), delivery='edit', require_supported=True,
          baseline_target=None, baseline_report=None):
    current = take_snapshot(root, cfg)
    defs, deps, _ = xml_inventory(root, current['files'])
    errors, warnings, unverified, changed = list(current['xmlProblems']), [], [], []
    content = content_load_report(root, cfg['version'], baseline_target, baseline_report)
    errors.extend(content['errors'])
    warnings.extend(content['warnings'])
    unverified.extend(content['unverified'])
    errors.extend(dict(code='foreign_dll', file=item['path'], message='Do not bundle game/framework assemblies')
                  for item in content.get('files', []) if item['path'] not in current['files']
                  and 'Assemblies' in Path(item['path']).parts and FORBIDDEN_DLL.fullmatch(Path(item['path']).name))
    about = root / 'About/About.xml'
    if not about.exists():
        errors.append(dict(code='about_missing', message='Missing About/About.xml'))
    elif not any(e.get('file') == 'About/About.xml' for e in errors):
        meta = ET.parse(about).getroot()
        if meta.tag != 'ModMetaData':
            errors.append(dict(code='about_root', message='Expected ModMetaData root'))
        for field in ('name', 'author', 'packageId'):
            if not (meta.findtext(field) or '').strip():
                errors.append(dict(code='about_field', message='Missing ' + field))
        versions = [(n.text or '').strip() for n in meta.findall('./supportedVersions/li')]
        if cfg['version'] not in versions:
            if require_supported:
                errors.append(dict(code='version', message='Configured version is absent from supportedVersions'))
            else:
                warnings.append(dict(code='version_pending', message='Compilation target is configured but not yet declared in supportedVersions'))
                unverified.append('Pending support declaration: compilation evidence does not establish compatibility or release readiness')
        if len(versions) > 1:
            unverified.append('Other supported versions need separate loader/build tests')
        after = {(n.text or '').strip().lower() for n in meta.findall('./loadAfter/li')}
        warnings.extend(dict(code='load_order', message='Check dependency loading order: ' + d) for d in deps if d not in after)
    for key, locations in defs.items():
        if cfg.get('defPrefix') and not key.split(':', 1)[1].startswith(cfg['defPrefix']):
            warnings.append(dict(code='def_prefix', message=f'{key} differs from project prefix; inspect intent, do not auto-rename'))
        if len(locations) > 1:
            groups = {next((p for p in Path(x).parts if re.fullmatch(r'\d+\.\d+', p)), 'common') for x in locations}
            if len(groups) > 1:
                unverified.append(f'Duplicate {key} spans load folders; verify version/LoadFolders selection')
            else:
                errors.append(dict(code='duplicate_def', message=key, files=locations))
    errors.extend(dict(code='foreign_dll', file=p, message='Do not bundle game/framework assemblies')
                  for p in current['files'] if 'Assemblies' in Path(p).parts and FORBIDDEN_DLL.fullmatch(Path(p).name))
    if profile:
        if baseline is None:
            errors.append(dict(code='baseline_required', message='A scope profile requires a pre-change snapshot'))
        elif baseline.get('schema') != 1 or Path(baseline.get('root', '')).resolve() != root.resolve():
            errors.append(dict(code='baseline_root', message='Snapshot project/schema mismatch'))
        elif baseline.get('target') and baseline['target'] != cfg['version']:
            errors.append(dict(code='baseline_target', message='Snapshot target mismatch'))
        else:
            old = baseline['files']
            changed = sorted(p for p in set(old) | set(current['files']) if old.get(p) != current['files'].get(p))
            if profile in ('L1', 'L2', 'L4'):
                for p in changed:
                    if (p.lower().startswith(cfg['sourceDir'].lower() + '/') and p.lower().endswith(('.cs', '.csproj'))) or p.lower().endswith('.dll'):
                        errors.append(dict(code='scope_code', file=p, message=profile + ' disallows source/DLL changes'))
            if profile == 'L1':
                errors.extend(dict(code='scope_new_def', message='L1 added ' + k) for k in sorted(set(current['defKeys']) - set(baseline['defKeys'])))
                errors.extend(dict(code='scope_removed_def', message='L1 removed ' + k) for k in sorted(set(baseline['defKeys']) - set(current['defKeys'])))
            allowed = {d.lower() for d in allowed_dependencies}
            errors.extend(dict(code='scope_dependency', message='New dependency not declared as allowed: ' + d)
                          for d in sorted(set(deps) - set(baseline['dependencies']) - allowed))
            if set(current['defKeys']) != set(baseline['defKeys']):
                warnings.append(dict(code='def_identity', message='Def identities changed; inspect references and save compatibility'))
        unverified.append('Purpose, optional references, C# types and Harmony target changes require semantic review')
    unverified.extend(['XML inheritance, cross-references, Class bindings and full PatchOperation execution are not emulated',
                       'Cross-mod asset resolution requires loader/visual verification',
                       'Game loading, gameplay, saves and visual correctness were not tested'])
    return dict(command='check', passed=not errors, profile=profile, delivery=delivery,
                errors=errors, warnings=warnings, unverified=unverified, changedFiles=changed, contentLoad=content)

def source_inputs(root, cfg):
    result = {}
    def matches(rel, patterns):
        # **/ also permits zero directories, unlike fnmatch alone.
        return any(fnmatch.fnmatchcase(rel, pat.replace('\\', '/')) or
                   fnmatch.fnmatchcase(rel, pat.replace('\\', '/').replace('**/', '')) for pat in patterns)
    for p in sorted((root / cfg['sourceDir']).rglob('*.cs')):
        rel = p.relative_to(root).as_posix()
        if any(x in ('bin', 'obj') for x in p.parts) or p.is_symlink():
            continue
        within(root, p)
        if cfg.get('sourceInclude') and not matches(rel, cfg['sourceInclude']):
            continue
        if matches(rel, cfg.get('sourceExclude', [])):
            continue
        result[rel] = digest(p)
    # An accidental two-version recursive build is unsafe even if it might compile.
    version_parts = {part for rel in result for part in Path(rel).parts[:-1] if part in ('1.6', '1.7')}
    if version_parts - {cfg['version']}:
        raise ValueError('Sources from another target selected; configure sourceInclude/sourceExclude')
    return result

def game_paths(cfg):
    game = Path(cfg.get('gameRoot') or r'D:\Program Files (x86)\Steam\steamapps\common\RimWorld')
    managed = game if cfg['version'] == '1.7' else next((game / d / 'Managed' for d in ('RimWorldWin64_Data', 'RimWorldLinux_Data', 'RimWorldMac_Data')
                    if (game / d / 'Managed').is_dir()), game / 'RimWorldWin64_Data/Managed')
    workshop = game.parent.parent / 'workshop/content/294100/2009463077'
    # Read the provider's version selection rather than guessing Current. Conditional
    # or ambiguous folders require an explicit local DLL path, not an arbitrary pick.
    selected = []
    folders = workshop / 'LoadFolders.xml'
    if folders.exists():
        for entry in ET.parse(folders).getroot().findall('./v' + cfg['version'] + '/li'):
            if not entry.attrib:
                folder = (entry.text or '').strip()
                if folder and '..' not in Path(folder).parts and not Path(folder).is_absolute():
                    candidate = workshop / folder / 'Assemblies/0Harmony.dll'
                    if candidate.is_file():
                        selected.append(candidate)
    harmony = Path(cfg['harmonyDll']) if cfg.get('harmonyDll') else (selected[0] if len(selected) == 1 else workshop / '__configure_harmonyDll__/0Harmony.dll')
    return game, managed, harmony


def compilation_references(root, cfg, inputs):
    _, managed, harmony = game_paths(cfg)
    tfm = cfg.get('targetFramework') or ('legacy-mono' if cfg['version'] == '1.6' else None)
    if not tfm:
        raise ValueError('1.7 C# target requires explicit targetFramework; do not infer it from the game runtime')
    libraries = cfg.get('gameReferences')
    if libraries is None:
        libraries = (['Assembly-CSharp.dll', 'UnityStubs.dll', 'Waylith.dll', 'Waylith.UnityCompat.dll'] if cfg['version'] == '1.7'
                     else ['Assembly-CSharp.dll', 'UnityEngine.CoreModule.dll', 'UnityEngine.IMGUIModule.dll'])
    paths = [managed / n for n in libraries]
    framework = cfg.get('frameworkReferenceDir')
    if framework:
        reference_dir = Path(framework)
        if not reference_dir.is_dir():
            raise ValueError('frameworkReferenceDir missing')
        paths += sorted(reference_dir.glob('*.dll'))
    elif tfm == 'legacy-mono' and cfg['version'] == '1.6':
        paths += [managed / n for n in ('mscorlib.dll', 'System.dll', 'System.Core.dll', 'netstandard.dll')]
    elif tfm == 'net10.0':
        dotnet = shutil.which('dotnet')
        if not dotnet:
            raise ValueError('.NET SDK required for framework reference-pack discovery')
        sdks = subprocess.run([dotnet, '--list-sdks'], capture_output=True, text=True, check=True).stdout
        candidates = []
        for sdk_path in re.findall(r'\[([^\]]+)\]', sdks):
            packs = Path(sdk_path).parent / 'packs/Microsoft.NETCore.App.Ref'
            if packs.is_dir():
                candidates += [p / 'ref/net10.0' for p in packs.glob('10.*') if (p / 'ref/net10.0').is_dir()]
        if not candidates:
            raise ValueError('net10.0 reference pack missing; configure frameworkReferenceDir or use the original build')
        reference_dir = max(candidates, key=lambda p: tuple(int(v) for v in re.findall(r'\d+', p.parent.parent.name)))
        paths += sorted(reference_dir.glob('*.dll'))
    else:
        raise ValueError('This framework requires explicit frameworkReferenceDir or the upstream native build: ' + str(tfm))
    if not paths or any(not p.is_file() for p in paths):
        raise ValueError('Missing compilation reference: ' + ', '.join(str(p) for p in paths if not p.is_file()))
    if any('HarmonyLib' in (root / p).read_text(encoding='utf-8-sig') for p in inputs):
        if not harmony.is_file():
            raise ValueError('Harmony reference missing; configure the selected provider DLL')
        paths.append(harmony)
    paths += [Path(p) for p in reference_bindings(root, cfg).values()]
    return {str(p.resolve()): digest(p) for p in paths}

def lookup_evidence_status(root, target, game, assembly, game_version):
    """Report lookup provenance independently of build readiness."""
    skill = bundled_skills() / 'rimworld-mod'
    profile_file = skill / 'data/profiles' / (target + '.json')
    actual_hash = digest(assembly) if assembly.is_file() else None
    profile = dict(state='unverified', actualVersion=game_version, actualSha256=actual_hash)
    if profile_file.is_file():
        try:
            record = json.loads(profile_file.read_text(encoding='utf-8'))
            expected = next(x['sha256'] for x in record['assemblies'] if x['name'] == 'Assembly-CSharp')
            expected_version = record['game']['versionText']
            state = ('unverified' if not game_version or not actual_hash else
                     'matched' if game_version == expected_version and actual_hash == expected else 'stale')
            profile.update(state=state, expectedVersion=expected_version, expectedSha256=expected)
        except (OSError, ValueError, KeyError, StopIteration, TypeError):
            profile['state'] = 'parse_failed'
    source = dict(state='unavailable')
    helper = skill / 'scripts/source_cache.py'
    if helper.is_file() and actual_hash and game_version:
        try:
            spec = importlib.util.spec_from_file_location('rimworld_source_cache_status', helper)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            source = module.inspect(game, target, root / '.local/source-cache')
        except (OSError, ValueError, ImportError, RuntimeError) as exc:
            source = dict(state='unverified', message=str(exc))
    legacy = root / '.local/decomp/Vanilla'
    if legacy.is_dir():
        source['legacyUnverified'] = str(legacy)
    bundled_ilspy = root / '.local/tools/ilspycmd.exe'
    return dict(profile=profile, sourceCache=source,
                ilspy=shutil.which('ilspycmd') or (str(bundled_ilspy) if bundled_ilspy.is_file() else None))


def doctor(root, cfg):
    game, managed, harmony = game_paths(cfg)
    inputs = source_inputs(root, cfg)
    needs_harmony = any('HarmonyLib' in (root / p).read_text(encoding='utf-8-sig') for p in inputs)
    env = dict(gameRoot=str(game), gameVersion=(game / 'Version.txt').read_text(encoding='utf-8-sig').strip() if (game / 'Version.txt').exists() else None,
               managedFound=(managed / 'Assembly-CSharp.dll').exists(), harmonyFound=harmony.exists(), harmonyRequired=needs_harmony,
               dotnet=shutil.which('dotnet'), python=sys.executable, configuredVersion=cfg['version'])
    errors, warnings = [], []
    if not env['managedFound']:
        errors.append(dict(code='game_missing', message='Configure gameRoot in config/mod.local.json'))
    if inputs and not env['dotnet']:
        errors.append(dict(code='dotnet_missing', message='.NET SDK required'))
    if needs_harmony and not harmony.exists():
        errors.append(dict(code='harmony_missing', message='Configure harmonyDll; no download performed'))
    if env['gameVersion'] and not env['gameVersion'].startswith(cfg['version'] + '.'):
        errors.append(dict(code='game_version', message='Installed game differs from configured version'))
    try:
        env['assemblyReferences'] = reference_bindings(root, cfg)
        if inputs and env['managedFound']:
            resolved = compilation_references(root, cfg, inputs)
            env['compilationReferenceCount'] = len(resolved)
            env['targetFramework'] = cfg.get('targetFramework') or 'legacy-mono'
    except ValueError as exc:
        errors.append(dict(code='reference_missing', message=str(exc)))
    env['harmonySelection'] = 'Configured/discovered DLL only; actual loaded provider remains unverified'
    evidence = lookup_evidence_status(root, cfg['version'], game, managed / 'Assembly-CSharp.dll', env['gameVersion'])
    env['lookupEvidence'] = evidence
    if evidence['profile']['state'] == 'stale':
        warnings.append(dict(code='lookup_profile_stale', message='Bundled exact-build profile differs from installed files; query the matching local installation instead'))
    if evidence['sourceCache'].get('state') == 'stale' or evidence['sourceCache'].get('staleCandidates'):
        warnings.append(dict(code='decomp_stale', message='Other source cache builds exist; use only a matching cache for source evidence'))
    if evidence['sourceCache'].get('legacyUnverified'):
        warnings.append(dict(code='decomp_unverified', message='Legacy decompile folder is not a verified source cache; do not infer its build from timestamps'))
    return dict(command='doctor', passed=not errors, environment=env, errors=errors, warnings=warnings)

def build(root, cfg, stage=False):
    preflight = check(root, cfg, require_supported=cfg['version'] not in cfg.get('_configuredVersions', []))
    if not preflight['passed']:
        return preflight
    pending = [w for w in preflight['warnings'] if w['code'] == 'version_pending']
    inputs = source_inputs(root, cfg)
    if not inputs:
        return dict(command='build', passed=True, notApplicable='No C# sources; no DLL generated', warnings=pending,
                    unverified=['Support declaration pending; no compatibility evidence'] if pending else [])
    preflight = doctor(root, cfg)
    if not preflight['passed']:
        return preflight
    out = unique_path(root, 'build/' + cfg['version']) / (cfg['assemblyName'] + '.dll')
    game, managed, harmony = game_paths(cfg)
    executable = shutil.which('pwsh') or shutil.which('powershell')
    if not executable:
        raise ValueError('PowerShell required for Source/build.ps1')
    refs = compilation_references(root, cfg, inputs)
    plan = dict(schema=1, root=str(root.resolve()), target=cfg['version'], output=str(out),
                sources=[str(root / p) for p in inputs], references=list(refs),
                languageVersion=cfg['languageVersion'], defines=cfg['defines'], targetFramework=cfg.get('targetFramework'),
                sourceInputs=inputs, referenceHashes=refs)
    plan_path = out.parent / 'build-plan.json'
    write_json(plan_path, plan)
    call = [executable, '-NoProfile', '-File', str(root / cfg['sourceDir'] / 'build.ps1'), '-BuildPlan', str(plan_path)]
    result = subprocess.run(call, cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        return dict(command='build', passed=False, errors=[dict(code='compiler', message=result.stdout + result.stderr)])
    if source_inputs(root, cfg) != inputs or any(digest(p) != h for p, h in refs.items()):
        raise ValueError('Build inputs changed during compilation; discard output and rebuild')
    bindings = reference_bindings(root, cfg)
    refs.update({p: digest(p) for p in bindings.values()})
    receipt = dict(schema=2, target=cfg['version'], gameVersion=preflight['environment']['gameVersion'],
                   createdUtc=datetime.now(timezone.utc).isoformat(), sourceInputs=inputs, references=refs,
                   referenceBindings=bindings,
                   configInputs={k: cfg[k] for k in BUILD_KEYS}, buildScriptHash=digest(root / cfg['sourceDir'] / 'build.ps1'),
                   buildPlan=str(plan_path), buildPlanHash=digest(plan_path),
                   output=str(out), sha256=digest(out), compilerOutput=result.stdout.strip(),
                   evidence=dict(compiled=True, loadTested=False, runtimeTested=False))
    if stage:
        target = root / cfg['version'] / 'Assemblies' / out.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, target)
        receipt['stagedOutput'] = str(target)
    write_json(out.parent / 'receipt.json', receipt)
    write_json(root / '.local/build-receipts' / (cfg['version'] + '.json'), receipt)
    return dict(command='build', passed=True, receipt=receipt, warnings=pending,
                unverified=['Game loading/behavior not tested'] + (['Support declaration pending; compilation is not compatibility evidence'] if pending else []))

def verified_receipt(root, cfg):
    path = root / '.local/build-receipts' / (cfg['version'] + '.json')
    # Legacy single-target receipts remain readable, but never establish another target.
    if not path.exists():
        path = root / '.local/latest-build.json'
    if not path.exists():
        raise ValueError('Build first; compilation receipt missing for ' + cfg['version'])
    receipt = json.loads(path.read_text(encoding='utf-8'))
    recorded_config = receipt.get('configInputs', {})
    if receipt.get('schema', 1) == 1:
        recorded_config = dict(sourceInclude=[], sourceExclude=[], defines=[], targetFramework=None,
                               gameReferences=None, artifactMode='compiled') | recorded_config
    if receipt.get('sourceInputs') != source_inputs(root, cfg) or recorded_config != {k: cfg[k] for k in BUILD_KEYS}:
        raise ValueError('Source/config changed; rebuild before packaging')
    if receipt.get('target', receipt.get('configInputs', {}).get('version')) != cfg['version']:
        raise ValueError('Build receipt target mismatch')
    if receipt.get('buildScriptHash') != digest(root / cfg['sourceDir'] / 'build.ps1'):
        raise ValueError('Build script changed; rebuild before packaging')
    if receipt.get('referenceBindings', {}) != reference_bindings(root, cfg):
        raise ValueError('Reference paths changed; rebuild before packaging')
    if any(not Path(p).exists() or digest(p) != h for p, h in receipt['references'].items()):
        raise ValueError('Compilation references changed; rebuild before packaging')
    if receipt['references'] != compilation_references(root, cfg, source_inputs(root, cfg)):
        raise ValueError('Compilation reference selection changed; rebuild before packaging')
    if receipt.get('schema') == 2:
        plan = within(root, receipt['buildPlan'])
        if not plan.is_file() or digest(plan) != receipt['buildPlanHash']:
            raise ValueError('Build plan changed; rebuild before packaging')
        game, _, _ = game_paths(cfg)
        version_file = game / 'Version.txt'
        if not version_file.exists() or version_file.read_text(encoding='utf-8-sig').strip() != receipt['gameVersion']:
            raise ValueError('Game build changed; rebuild before packaging')
    output = within(root, receipt['output'])
    if not output.exists() or digest(output) != receipt['sha256']:
        raise ValueError('Build output missing or changed')
    return receipt


def adopted_artifacts(root, version):
    path = root / '.local/artifacts' / version / 'adopted.json'
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('target') != version or data.get('schema') != 1:
        raise ValueError('Adopted artifact target/schema mismatch: ' + version)
    result = {}
    for entry in data.get('artifacts', []):
        filename = entry.get('path', '')
        artifact = within(root, root / filename)
        if not filename or artifact.suffix.lower() != '.dll' or not artifact.is_file() or digest(artifact) != entry.get('sha256'):
            raise ValueError('Adopted artifact missing/changed: ' + filename)
        if not entry.get('reviewed') or not isinstance(entry.get('origin'), str) or not entry['origin'].strip():
            raise ValueError('Adopted artifact requires explicit origin and review: ' + filename)
        if filename in result:
            raise ValueError('Duplicate adopted artifact record: ' + filename)
        result[filename] = entry
    return result


def package(root, cfg, baseline_target=None, baseline_report=None):
    validation = check(root, cfg, delivery='release', baseline_target=baseline_target, baseline_report=baseline_report)
    if not validation['passed']:
        return validation
    chosen = {'About', 'Textures', 'Sounds', 'Languages', 'Common', 'Defs', 'Patches', 'Assemblies', cfg['version']}
    meta = ET.parse(root / 'About/About.xml').getroot()
    versions = [(n.text or '').strip() for n in meta.findall('./supportedVersions/li')]
    chosen.update(versions)
    loaded_folders = {v: ['.', v] for v in versions}
    unsupported_folders = []
    folders = root / 'LoadFolders.xml'
    if folders.exists():
        loading = ET.parse(folders).getroot()
        for version in versions:
            selection = loading.find('v' + version)
            if selection is None:
                selection = loading.find('default')
            if selection is None:
                raise ValueError('LoadFolders has no selection for supported target: ' + version)
            loaded_folders[version] = [(entry.text or '').strip().replace('\\', '/').rstrip('/') or '.' for entry in selection.findall('li')]
        for selection in loading:
            if selection.tag.startswith('v') and selection.tag[1:] not in versions:
                unsupported_folders += [(entry.text or '').strip().replace('\\', '/').rstrip('/') for entry in selection.findall('li')]
        for entry in loading.iter('li'):
            folder = (entry.text or '').strip().replace('\\', '/').rstrip('/')
            if folder and folder != '.':
                within(root, root / folder)
                chosen.add(folder)
    files = tracked(root)
    included = [rel for rel in files if any(rel.startswith(folder + '/') for folder in chosen)]
    # Development junctions can resolve locally while the link-free archive omits them.
    # Compare observable content paths against actual packaged inputs, not all repository XML.
    content_reports = {}
    for version in versions:
        content = content_load_report(root, version, baseline_target if version == cfg['version'] else None,
                                      baseline_report if version == cfg['version'] else None)
        content_reports[version] = content
        if any(item.get('code') == 'content_auditor_missing' for item in content['unverified']):
            raise ValueError('Cannot verify release content roots: project content auditor missing')
        if content['errors']:
            raise ValueError('Target content validation failed for ' + version + ': ' + '; '.join(e['message'] + (' [' + e['file'] + ']' if e.get('file') else '') for e in content['errors']))
        missing = sorted({item['path'] for item in content['files'] if item['path'] not in included})
        if missing:
            raise ValueError('Selected content omitted from archive for ' + version + ' (materialize links inside release input): ' + ', '.join(missing))
        if any(item.get('code') in ('external_link', 'external_root', 'link_unverified', 'link_cycle') for item in content['unverified']):
            raise ValueError('Selected external/unknown links cannot be verified for release: ' + version)
    def loaded(version, rel):
        return any(rel.startswith(folder + '/') if folder != '.' else rel.startswith('Assemblies/')
                   for folder in loaded_folders[version])
    for rel in included:
        if Path(rel).suffix.lower() != '.dll':
            continue
        if FORBIDDEN_DLL.fullmatch(Path(rel).name):
            raise ValueError('Do not bundle game/framework references: ' + rel)
        if any(re.fullmatch(r'\d+\.\d+', part) and part not in versions for part in Path(rel).parts):
            raise ValueError('Included DLL belongs to an undeclared target: ' + rel)
        if any(folder and rel.startswith(folder + '/') for folder in unsupported_folders):
            raise ValueError('Included DLL selected by an undeclared LoadFolders target: ' + rel)
    receipts, adopted = {}, {}
    for version in versions:
        target_cfg = cfg if version == cfg['version'] else config(root, version)
        report = check(root, target_cfg, delivery='release')
        if not report['passed']:
            raise ValueError('Target validation failed: ' + version + ': ' + '; '.join(e['message'] + (' [' + e['file'] + ']' if e.get('file') else '') for e in report['errors']))
        if target_cfg['artifactMode'] == 'compiled' and source_inputs(root, target_cfg):
            receipts[version] = verified_receipt(root, target_cfg)
        adopted[version] = adopted_artifacts(root, version)
    covered = set()
    for version in versions:
        receipt = receipts.get(version)
        target_cfg = cfg if version == cfg['version'] else config(root, version)
        if receipt:
            output_rel = version + '/Assemblies/' + target_cfg['assemblyName'] + '.dll'
            if not loaded(version, output_rel):
                raise ValueError('Compiled DLL is not selected by target LoadFolders: ' + output_rel)
            covered.add(output_rel)
        # A prebuilt record is target-specific even if a shared folder is reused.
        relevant = [rel for rel in included if Path(rel).suffix.lower() == '.dll' and loaded(version, rel)]
        for rel in relevant:
            if rel not in covered and rel not in adopted[version]:
                raise ValueError('DLL lacks compiled/adopted evidence for ' + version + ': ' + rel)
    # Unsupported version folders named by LoadFolders must not smuggle unverified DLLs.
    for rel in included:
        if Path(rel).suffix.lower() == '.dll':
            if rel not in covered and not any(rel in records for records in adopted.values()):
                raise ValueError('Unverified included DLL: ' + rel)
    base = unique_path(root, 'releases')
    dest = base / cfg['assemblyName']
    dest.mkdir(parents=True)
    for rel in files:
        p = Path(rel)
        notice = p.name.lower() in {'license', 'license.txt', 'license.md', 'copying', 'copying.txt', 'notice', 'notice.txt', 'notice.md', 'third_party_notices.md'} and len(p.parts) == 1
        if not any(rel.startswith(folder + '/') for folder in chosen) and rel != 'LoadFolders.xml' and not notice:
            continue
        if rel in covered:
            continue
        target = within(dest, dest / rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
    for version, receipt in receipts.items():
        target = dest / version / 'Assemblies' / Path(receipt['output']).name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(receipt['output'], target)
    manifest = {p.relative_to(dest).as_posix(): digest(p) for p in sorted(dest.rglob('*')) if p.is_file()}
    for version in versions:
        content = content_reports[version]
        missing = sorted({item['path'] for item in content['files'] if item['path'] not in manifest})
        if missing:
            raise ValueError('Final archive content missing for ' + version + ': ' + ', '.join(missing))
    write_json(base / 'manifest.json', manifest)
    archive = base / (cfg['assemblyName'] + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel in manifest:
            zf.write(dest / rel, cfg['assemblyName'] + '/' + rel)
    result = dict(command='package', passed=True, directory=str(dest), zip=str(archive), sha256=digest(archive),
                  files=len(manifest), validation=validation, compiledReceipt=receipts.get(cfg['version']),
                  targetArtifacts={v: dict(compiled=receipts.get(v), adopted=adopted[v]) for v in versions},
                  targetContent=content_reports,
                  evidence=dict(loadTested=False, runtimeTested=False, published=False))
    write_json(base / 'release-receipt.json', result)
    return result

ERROR_LINE = re.compile(r'exception|could not resolve|error|failed|duplicate stacktrace', re.I)

def scan_log(text):
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if ERROR_LINE.search(line)]
    counts = Counter(lines[i] for i in hits)
    return dict(candidateCount=len(hits), groups=[dict(line=line, count=count) for line, count in counts.most_common()],
                firstContext=lines[max(0, hits[0] - 3):hits[0] + 26] if hits else [],
                unverified=['Heuristic matching; no candidates does not prove correct loading/gameplay'])

def log_report(root, filename=None, baseline=None, cfg=None):
    log_dir = Path(os.environ.get('USERPROFILE', str(Path.home()))) / 'AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios'
    path = Path(filename) if filename else (log_dir / 'Logs/Player.log' if (log_dir / 'Logs/Player.log').is_file() else log_dir / 'Player.log')
    body = path.read_bytes()
    dest = unique_path(root, 'logs', '.log')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    result = scan_log(body.decode('utf-8-sig', errors='replace'))
    result.update(command='log', passed=True, source=str(path.resolve()), snapshot=str(dest), sha256=hashlib.sha256(body).hexdigest(),
                  modifiedUtc=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())
    text = body.decode('utf-8-sig', errors='replace')
    observed = re.search(r'(?:RimWorld\s+|Version[: ]+)(1\.[67]\.\d+(?:\s+rev\d+)?)', text, re.I)
    result['observedGameVersion'] = observed.group(1) if observed else None
    result['target'] = cfg['version'] if cfg else None
    result['targetEvidence'] = ('version-mismatch' if cfg and observed and not observed.group(1).startswith(cfg['version'] + '.')
                                else 'series-matches-build-session-unverified' if cfg and observed else 'unverified')
    result['unverified'].append('Version text does not bind this log to the current DLL, build or game session')
    if baseline:
        prior = scan_log(Path(baseline).read_text(encoding='utf-8-sig', errors='replace'))
        old = {g['line']: g['count'] for g in prior['groups']}
        result['increasedGroups'] = [g for g in result['groups'] if g['count'] > old.get(g['line'], 0)]
    write_json(dest.with_suffix('.json'), result)
    return result

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('doctor', 'snapshot', 'check', 'build', 'log', 'package'))
    p.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    p.add_argument('--target', choices=('1.6', '1.7'), help='Select an explicitly configured build target')
    p.add_argument('--json', action='store_true')
    p.add_argument('--profile', choices=('L1', 'L2', 'L3', 'L4', 'L5', 'L6'))
    p.add_argument('--delivery', choices=('edit', 'standalone', 'complete', 'release'), default='edit')
    p.add_argument('--baseline')
    p.add_argument('--baseline-target', choices=('1.6', '1.7'), help='Compare observable content with another version (check/package only); separate from scope snapshot')
    p.add_argument('--baseline-file', help='Saved content_load audit report before migration (check/package only)')
    p.add_argument('--allow-dependency', action='append', default=[])
    p.add_argument('--out')
    p.add_argument('--file')
    p.add_argument('--stage', action='store_true')
    args = p.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        cfg = config(root, args.target)
        if (args.baseline_target or args.baseline_file) and args.command not in ('check', 'package'):
            raise ValueError('--baseline-target/--baseline-file are only valid with check/package')
        content_baseline = json.loads(Path(args.baseline_file).read_text(encoding='utf-8-sig')) if args.baseline_file else None
        if args.command == 'doctor':
            result = doctor(root, cfg)
        elif args.command == 'snapshot':
            dest = within(root, Path(args.out).absolute()) if args.out else unique_path(root, 'snapshots', '.json')
            if dest.exists():
                raise ValueError('Snapshot exists; preserve original baseline')
            write_json(dest, take_snapshot(root, cfg))
            result = dict(command='snapshot', passed=True, snapshot=str(dest))
        elif args.command == 'check':
            prior = json.loads(Path(args.baseline).read_text(encoding='utf-8-sig')) if args.baseline else None
            result = check(root, cfg, args.profile, prior, args.allow_dependency, args.delivery,
                           baseline_target=args.baseline_target, baseline_report=content_baseline)
        elif args.command == 'build':
            result = build(root, cfg, args.stage)
        elif args.command == 'package':
            result = package(root, cfg, args.baseline_target, content_baseline)
        else:
            result = log_report(root, args.file, args.baseline, cfg)
    except (ValueError, KeyError, OSError, ET.ParseError, subprocess.SubprocessError) as exc:
        result = dict(command=args.command, passed=False, errors=[dict(code='operation', message=str(exc))])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result['command']}: {'PASS' if result['passed'] else 'FAIL'}")
        for key in ('snapshot', 'directory', 'zip'):
            if key in result:
                print(f'{key}: {result[key]}')
        if 'environment' in result:
            print(json.dumps(result['environment'], ensure_ascii=False, indent=2))
        if 'receipt' in result:
            print('output: ' + result['receipt']['output'])
        content_reports = result.get('targetContent', {})
        if 'contentLoad' in result:
            content_reports = {result['contentLoad']['target']: result['contentLoad']}
        for target, content in content_reports.items():
            roots = ', '.join(entry['relative'] for entry in content['roots']) or '(none)'
            print('content ' + target + ': roots=' + roots + '; observable Def keys=' + str(len(content.get('defKeys', []))) + '; static disk evidence only')
        for group in ('errors', 'warnings', 'unverified'):
            for value in result.get(group, []):
                print(group + ': ' + (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)))
        if args.command == 'log' and result['passed']:
            print(f"candidate errors: {result['candidateCount']}; details saved beside snapshot")
    return 0 if result['passed'] else 1

if __name__ == '__main__':
    sys.exit(main())
