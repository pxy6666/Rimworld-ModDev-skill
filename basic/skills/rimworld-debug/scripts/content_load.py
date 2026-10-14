"""Read-only content-root audit, not a RimWorld loader or runtime Def proof."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import xml.etree.ElementTree as ET

ROLES = ('Defs', 'Patches', 'Languages', 'Textures', 'Sounds', 'Assemblies', 'ContentPacks')
CONDITIONS = {'IfModActive', 'IfModActiveAll', 'IfModNotActive'}
DEF_CONDITIONS = {'MayRequire', 'MayRequireAnyOf', 'MayRequireAllOf'}


def issue(code, message, file=None):
    return dict(code=code, message=message, **({'file': file} if file else {}))


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def linked(path):
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except OSError:
        return False


def child_ci(path, name):
    if not path.is_dir():
        return None
    return next((p for p in path.iterdir() if p.name.casefold() == name.casefold()), None)


def version(text):
    match = re.fullmatch(r'(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?', text)
    return tuple(int(v) if v is not None else -1 for v in match.groups()) if match else None


def select_roots(root, target, errors, warnings, unverified):
    """Known disk-selection rules; conditions remain unresolved candidates."""
    load = child_ci(root, 'LoadFolders.xml')
    source, group, entries = 'default-folders', None, None
    if load:
        doc = ET.parse(load).getroot()
        groups = {n.tag.casefold().removeprefix('v'): list(n) for n in doc}
        for label in groups:
            if label != 'default' and version(label) is None:
                unverified.append(issue('selection_format', 'Unrecognized version branch; inspect actual loader selection: ' + label, 'LoadFolders.xml'))
        if groups.get(target):
            group = target
        else:
            # Observed 1.7 sorts eligible version labels as strings, including
            # an explicitly empty exact list. Do not silently fill that list.
            older = [k for k in groups if version(k) and version(k) <= version(target)]
            group = max(older) if older else 'default' if 'default' in groups else None
        if group is not None:
            entries, source = groups[group], 'LoadFolders.xml'
            if group != target:
                warnings.append(issue('version_fallback', 'No populated exact branch; selected ' + group + ' for ' + target))
    roots = []
    if entries is not None:
        for entry in reversed(entries):
            text = (entry.text or '').replace('\\', '/')
            if text != text.strip():
                unverified.append(issue('root_whitespace', 'Loader keeps literal root whitespace; it was not normalized away', 'LoadFolders.xml'))
            relative = '.' if text == '/' else text
            path = PurePosixPath(relative)
            if not relative or path.is_absolute() or '..' in path.parts or ':' in relative:
                errors.append(issue('invalid_content_root', 'Invalid project-relative content root: ' + text, 'LoadFolders.xml'))
                continue
            unknown = set(entry.attrib) - CONDITIONS
            if unknown:
                warnings.append(issue('unsupported_folder_condition', 'LoadFolders attributes not supported by inspected 1.7 parser: ' + ', '.join(sorted(unknown)), 'LoadFolders.xml'))
            conditions = {k: v for k, v in entry.attrib.items() if k in CONDITIONS}
            roots.append(dict(relative=path.as_posix(), conditions=conditions, explicit=True))
    else:
        exact = root / target
        chosen = target if exact.is_dir() else None
        if chosen is None:
            candidates = [p.name for p in root.iterdir() if p.is_dir() and version(p.name)]
            older = [v for v in candidates if version(v) <= version(target)]
            chosen = max(older, key=version) if older else min(candidates, key=version) if candidates else None
        if chosen:
            roots.append(dict(relative=chosen, conditions={}, explicit=False))
        common = child_ci(root, 'Common')
        if common:
            roots.append(dict(relative=common.name, conditions={}, explicit=False))
        roots.append(dict(relative='.', conditions={}, explicit=False))
    if any(r['conditions'] for r in roots):
        unverified.append(issue('conditional_roots', 'Conditional roots are candidates; actual active-mod combination was not evaluated'))
    return roots, dict(source=source, versionGroup=group, confidence='static_candidates', ruleEvidence='1.6.4871 rev590 / 1.7.4977 rev1248 targeted DLL inspection; runtime not tested')


def disk_files(directory, root, unverified, active=None, inherited_link=False):
    """Read internal linked content, keeping lexical paths for package comparison."""
    active = set() if active is None else active
    real = directory.resolve()
    if not real.is_relative_to(root):
        unverified.append(issue('external_link', 'Content resolves outside mod root; not traversed', directory.relative_to(root).as_posix()))
        return
    if real in active:
        unverified.append(issue('link_cycle', 'Directory cycle; not traversed', directory.relative_to(root).as_posix()))
        return
    active = active | {real}
    for path in sorted(directory.iterdir()):
        is_linked = inherited_link or linked(directory) or linked(path)
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            unverified.append(issue('external_link', 'Content resolves outside mod root; not traversed', path.relative_to(root).as_posix()))
        elif path.is_dir():
            yield from disk_files(path, root, unverified, active, is_linked)
        elif path.is_file():
            yield path, is_linked


def audit(root, target, baseline_target=None, baseline_report=None):
    root = Path(root).resolve()
    if not root.is_dir() or not version(target) or (baseline_target and not version(baseline_target)):
        raise ValueError('Existing mod root and numeric target versions are required')
    errors, warnings, unverified = [], [], []
    try:
        roots, selection = select_roots(root, target, errors, warnings, unverified)
    except (OSError, ET.ParseError) as exc:
        roots, selection = [], dict(source='parse_failed', versionGroup=None, confidence='unknown')
        errors.append(issue('loadfolders_parse', str(exc), 'LoadFolders.xml'))
    chosen, conditional_files, shadowed = {}, [], []
    for entry in roots:
        directory = root / entry['relative']
        entry['exists'] = directory.is_dir()
        if not directory.resolve().is_relative_to(root):
            unverified.append(issue('external_root', 'Content root resolves outside mod; not traversed', entry['relative']))
            continue
        if not entry['exists']:
            warnings.append(issue('missing_content_root', 'Selected content root does not exist', entry['relative']))
            continue
        if directory.name.casefold() in {r.casefold() for r in ROLES} and not any(child_ci(directory, r) for r in ROLES):
            errors.append(issue('role_as_content_root', 'Entry is a role directory, not its parent content root; loader searches role subdirectories beneath it', entry['relative']))
        for role in ROLES:
            folder = child_ci(directory, role)
            if not folder or not folder.is_dir():
                continue
            for path, is_linked in disk_files(folder, root, unverified, inherited_link=linked(directory)):
                if role in ('Defs', 'Patches') and path.suffix.lower() != '.xml':
                    continue
                if role == 'Assemblies' and path.suffix.lower() != '.dll':
                    continue
                logical = role + '/' + path.relative_to(folder).as_posix()
                record = dict(path=path.relative_to(root).as_posix(), role=role, logical=logical,
                              sha256=digest(path), conditions=entry['conditions'], linked=is_linked)
                if entry['conditions']:
                    conditional_files.append(record)
                elif logical not in chosen:
                    chosen[logical] = record
                else:
                    shadowed.append(record['path'])
        archive = child_ci(directory, 'Assets.zip')
        if archive and archive.is_file():
            if not archive.resolve().is_relative_to(root):
                unverified.append(issue('external_link', 'Packed content resolves outside mod; not read', archive.relative_to(root).as_posix()))
            else:
                record = dict(path=archive.relative_to(root).as_posix(), role='ContentPacks', logical='Assets.zip',
                              sha256=digest(archive), conditions=entry['conditions'], linked=linked(directory) or linked(archive))
                if entry['conditions']:
                    conditional_files.append(record)
                elif record['logical'] not in chosen:
                    chosen[record['logical']] = record
                else:
                    shadowed.append(record['path'])
    files = list(chosen.values()) + conditional_files
    defs, conditional_defs = set(), set()
    for record in files:
        if record['role'] != 'Defs':
            continue
        try:
            xml = ET.parse(root / record['path']).getroot()
            if xml.tag != 'Defs':
                errors.append(issue('defs_root', 'Expected Defs XML root', record['path']))
            for node in xml:
                name = node.findtext('defName')
                if not name or node.get('Abstract', '').lower() == 'true':
                    continue
                key = node.tag + ':' + name.strip()
                (conditional_defs if record['conditions'] or DEF_CONDITIONS.intersection(node.attrib) else defs).add(key)
        except (OSError, ET.ParseError) as exc:
            errors.append(issue('selected_xml_parse', str(exc), record['path']))
    roles = {role: sum(f['role'] == role and not f['conditions'] for f in files) for role in ROLES}
    if not files:
        warnings.append(issue('empty_content_selection', 'Selected roots expose no recognized disk content; pure-system or pre-stage status still requires an explicit contract'))
    if roles['ContentPacks'] or any(f['role'] == 'ContentPacks' for f in files):
        unverified.append(issue('content_packs', 'Packed content is present but not decoded; disk inventory is not complete'))
    dlls = [f['path'] for f in files if f['role'] == 'Assemblies' and not f['conditions']]
    if any('1.6' in Path(p).parts for p in dlls) and any('1.7' in Path(p).parts for p in dlls):
        warnings.append(issue('mixed_version_dlls', 'Both version directories expose DLL candidates; inspect logical names and assembly identities before claiming isolation'))
    if any(Path(p).suffix.lower() == '.dll' for p in shadowed):
        warnings.append(issue('shadowed_dlls', 'Same logical DLL paths were shadowed by later roots; verify exact identities and other providers, not just filenames'))
    identity = None
    about = root / 'About/About.xml'
    if about.is_file():
        try:
            identity = ET.parse(about).getroot().findtext('packageId')
        except (OSError, ET.ParseError):
            unverified.append(issue('identity_unverified', 'About identity could not be parsed'))
    result = dict(schema=1, target=target, packageId=identity, selection=selection, roots=roots, files=files, defKeys=sorted(defs),
                  conditionalDefKeys=sorted(conditional_defs), roles=roles, shadowed=shadowed,
                  errors=errors, warnings=warnings, unverified=unverified, comparison=None,
                  evidence=dict(staticDiskOnly=True, gameLoaded=False, patchExecution=False))
    if baseline_target or baseline_report:
        baseline = baseline_report if baseline_report is not None else audit(root, baseline_target)
        required = {'schema', 'target', 'files', 'defKeys', 'roles', 'unverified', 'errors'}
        if not isinstance(baseline, dict) or not required.issubset(baseline) or baseline['schema'] != 1:
            raise ValueError('Baseline must be a saved content_load audit report')
        if baseline_target and baseline['target'] != baseline_target:
            raise ValueError('Baseline target does not match saved report')
        if identity and baseline.get('packageId') and identity.casefold() != baseline['packageId'].casefold():
            raise ValueError('Baseline belongs to another mod identity')
        missing = sorted(set(baseline['defKeys']) - defs)
        missing_roles = [r for r in ROLES if baseline['roles'][r] and not roles[r]]
        missing_files = sorted({f['logical'] for f in baseline['files'] if not f['conditions']} - set(chosen))
        old_hashes = {f['logical']: f['sha256'] for f in baseline['files'] if not f['conditions']}
        changed_files = sorted(key for key, record in chosen.items() if key in old_hashes and old_hashes[key] != record['sha256'])
        uncertain = bool(baseline['unverified'] or unverified or baseline.get('conditionalDefKeys') or conditional_defs or conditional_files or baseline['errors'])
        structural_unknown = bool(baseline['errors'] or any(x['code'] != 'conditional_roots' for x in baseline['unverified'] + unverified))
        result['comparison'] = dict(baseTarget=baseline['target'], baselineSource='saved_report' if baseline_report is not None else 'current_disk', missingDefKeys=missing, missingRoles=missing_roles,
                                    missingLogicalFiles=missing_files, changedLogicalFiles=changed_files, conditionalEvidence=uncertain)
        missing_known_defs = [key for key in missing if key not in conditional_defs]
        conditional_only = [key for key in missing if key in conditional_defs]
        if missing_known_defs:
            (warnings if structural_unknown else errors).append(issue('migration_defs_missing', 'Named static Def keys missing from all inspected candidates: ' + ', '.join(missing_known_defs[:20])))
        if conditional_only:
            warnings.append(issue('migration_defs_conditional', 'Previously unconditional definitions are only conditional candidates: ' + ', '.join(conditional_only[:20])))
        for role in missing_roles:
            uncertain_role = structural_unknown or any(f['role'] == role for f in conditional_files)
            (warnings if uncertain_role else errors).append(issue('migration_role_missing', 'Previously present content role is missing or only conditional: ' + role))
        if missing_files:
            warnings.append(issue('migration_file_difference', 'Logical files missing/renamed; record content migration or accepted changes: ' + ', '.join(missing_files[:20])))
        if changed_files:
            warnings.append(issue('migration_content_changed', 'Content bytes changed (DLL changes may be expected); record reasons and verify affected consumers: ' + ', '.join(changed_files[:20])))
        if baseline['errors']:
            unverified.append(issue('baseline_invalid', 'Baseline selection has static errors; fix source evidence before judging preservation'))
    result['passed'] = not errors
    return result


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check',))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--target', choices=('1.6', '1.7'), required=True)
    parser.add_argument('--baseline-target', choices=('1.6', '1.7'))
    parser.add_argument('--baseline-file', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.limit <= 200:
            raise ValueError('limit must be between 1 and 200')
        if args.out:
            output = args.out.resolve()
            if not output.is_relative_to(args.root.resolve()) or output.exists():
                raise ValueError('New audit output must stay inside mod root and not overwrite an existing record')
        baseline = json.loads(args.baseline_file.read_text(encoding='utf-8-sig')) if args.baseline_file else None
        result = audit(args.root, args.target, args.baseline_target, baseline)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        summary = {**result, 'files': result['files'][:args.limit], 'defKeys': result['defKeys'][:args.limit],
                   'fileCount': len(result['files']), 'defCount': len(result['defKeys']),
                   'truncated': len(result['files']) > args.limit or len(result['defKeys']) > args.limit}
        if result['comparison']:
            summary['comparison'] = {key: value[:args.limit] if isinstance(value, list) else value for key, value in result['comparison'].items()}
            summary['comparisonCounts'] = {key: len(value) for key, value in result['comparison'].items() if isinstance(value, list)}
            summary['truncated'] |= any(isinstance(value, list) and len(value) > args.limit for value in result['comparison'].values())
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if result['passed'] else 1
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        print(json.dumps(dict(passed=False, error=str(exc)), ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
