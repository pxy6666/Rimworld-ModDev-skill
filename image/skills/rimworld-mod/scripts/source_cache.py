"""Optional local ILSpy source cache. This is source evidence, not an API index."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


SCHEMA = 1
TARGETS = ('1.6', '1.7')
MANAGED_DIRS = ('RimWorldWin64_Data', 'RimWorldLinux_Data', 'RimWorldMac_Data')
SOURCE_NOTE = 'Decompiled source evidence; confirm signatures against the selected DLL and test runtime behavior separately.'
IDENTITY_FIELDS = {'target', 'gameVersion', 'versionTextSha256', 'gameAssemblySha256', 'assemblyName', 'assemblySha256', 'assemblyKind'}


class CacheError(ValueError):
    def __init__(self, message, state='unavailable'):
        super().__init__(message)
        self.state = state


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _json_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def _identity(game_root, target, dll):
    if target not in TARGETS:
        raise CacheError('Choose a 1.6 or 1.7 target.')
    game = Path(game_root).resolve()
    raw_version = (game / 'Version.txt').read_bytes()
    version = raw_version.decode('utf-8-sig').strip()
    if not re.fullmatch(re.escape(target) + r'\.\d+(?:\s+rev\d+)?', version):
        raise CacheError(f'Version.txt identifies {version!r}, not target {target}.', 'version-mismatch')
    candidates = ([game / 'Assembly-CSharp.dll'] if target == '1.7' else
                  [game / folder / 'Managed' / 'Assembly-CSharp.dll' for folder in MANAGED_DIRS])
    core = next((p.resolve() for p in candidates if p.is_file()), None)
    if core is None:
        raise CacheError('Assembly-CSharp.dll missing in the selected target layout.')
    selected = Path(dll).resolve() if dll else core
    if selected.suffix.lower() != '.dll' or not selected.is_file():
        raise CacheError('Select a readable DLL for --dll.')
    game_sha = _sha(core)
    identity = {'target': target, 'gameVersion': version,
                'versionTextSha256': hashlib.sha256(raw_version).hexdigest(),
                'gameAssemblySha256': game_sha, 'assemblyName': selected.name,
                'assemblySha256': game_sha if selected == core else _sha(selected),
                'assemblyKind': 'game' if selected == core else 'upstream'}
    return identity, game, core, selected


def _cache_root(cache_dir):
    return Path(cache_dir or os.environ.get('RIMWORLD_SOURCE_CACHE_DIR') or '.local/source-cache').resolve()


def _key(fingerprint):
    return _json_hash({'schema': SCHEMA, 'fingerprint': fingerprint})


def _file_path(source_root, relative):
    path = (source_root / relative).resolve()
    if not path.is_relative_to(source_root) or not path.is_file() or path.suffix.lower() != '.cs':
        raise CacheError('Cached source file is missing or outside its source root.', 'incomplete')
    return path


def _manifest(entry, *, check_source=False):
    manifest = entry / 'manifest.json'
    if entry.is_symlink() or manifest.is_symlink():
        raise CacheError('Linked cache entries are not verified.', 'incomplete')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    fingerprint = data['fingerprint']
    if set(fingerprint) != IDENTITY_FIELDS or any(not isinstance(v, str) for v in fingerprint.values()):
        raise CacheError('Cache manifest has incomplete fingerprint fields.', 'incomplete')
    if (data.get('schema') != SCHEMA or data.get('cacheKey') != entry.name or
            _key(fingerprint) != entry.name or fingerprint['target'] != entry.parent.name):
        raise CacheError('Cache manifest identity does not match its location.', 'incomplete')
    if not data['tool'].get('version') or data['tool'].get('name') != 'ilspycmd':
        raise CacheError('Cache manifest has no ILSpy version evidence.', 'incomplete')
    if not isinstance(data['sourceFiles'], dict) or not data['sourceFiles'] or data['sourceFileCount'] != len(data['sourceFiles']):
        raise CacheError('Cache manifest has no valid source inventory.', 'incomplete')
    if check_source:
        source = (entry / 'source').resolve()
        if source.parent != entry.resolve() or not source.is_dir():
            raise CacheError('Cache source directory missing or linked elsewhere.', 'incomplete')
        anchor, expected = next(iter(data['sourceFiles'].items()))
        if _sha(_file_path(source, anchor)) != expected:
            raise CacheError('Cached source inventory sample has changed.', 'incomplete')
    return data


def _inspect_identity(fingerprint, cache_dir):
    key = _key(fingerprint)
    parent = _cache_root(cache_dir) / fingerprint['target']
    entry = parent / key
    report = dict(state='missing', target=fingerprint['target'], cacheKey=key, cacheRoot=str(parent.parent),
                  fingerprint=fingerprint, staleCandidates=[], unverifiedCandidates=[])
    if entry.exists():
        try:
            data = _manifest(entry, check_source=True)
            if data['fingerprint'] != fingerprint:
                raise CacheError('Cache fingerprint mismatch.', 'incomplete')
        except (CacheError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            report.update(state='incomplete', detail=str(exc))
        else:
            report.update(state='available', sourceRoot=str(entry / 'source'), manifest=str(entry / 'manifest.json'),
                          sourceFileCount=data['sourceFileCount'], tool=data['tool'], evidence=SOURCE_NOTE)
    if parent.is_dir() and report['state'] != 'available':
        for previous in sorted(parent.iterdir()):
            if previous == entry or not previous.is_dir():
                continue
            try:
                old = _manifest(previous)['fingerprint']
            except (CacheError, OSError, ValueError, TypeError, KeyError, AttributeError):
                if len(report['unverifiedCandidates']) < 8:
                    report['unverifiedCandidates'].append(str(previous))
                continue
            if (old['assemblyName'].casefold() == fingerprint['assemblyName'].casefold() and
                    old['assemblyKind'] == fingerprint['assemblyKind'] and len(report['staleCandidates']) < 8):
                report['staleCandidates'].append(dict(manifest=str(previous / 'manifest.json'),
                                                      gameVersion=old['gameVersion'], assemblySha256=old['assemblySha256']))
        if report['staleCandidates'] and report['state'] == 'missing':
            report['state'] = 'stale'
    return report


def inspect(game_root, target, cache_dir=None, *, dll=None):
    """Read-only exact-input probe; never requires ILSpy, never serves a stale source path."""
    try:
        fingerprint, _, _, _ = _identity(game_root, target, dll)
        return _inspect_identity(fingerprint, cache_dir)
    except (CacheError, OSError, ValueError, TypeError) as exc:
        return dict(state=getattr(exc, 'state', 'unavailable'), target=target, detail=str(exc))


def _executable(ilspy):
    command = str(ilspy) if ilspy else 'ilspycmd'
    path = shutil.which(command)
    if path is None and ilspy and Path(command).is_file():
        path = command
    if path is None:
        raise CacheError('ILSpy not found. Pass --ilspy for an existing ilspycmd executable; no download is attempted.')
    return str(Path(path).resolve())


def _run(args, *, timeout):
    result = subprocess.run(args, capture_output=True, encoding='utf-8', errors='replace', timeout=timeout)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-1600:]
        raise CacheError(f'ILSpy exited {result.returncode}: {detail}', 'failed')
    return result


def _private_cache_dir(root, game):
    skill_tree = Path(__file__).resolve().parents[2]
    projects = {skill_tree.parent, Path.cwd().resolve()}
    content = ('skills', 'variants', '.git', 'About', 'Defs', 'Patches', 'Assemblies', 'Textures',
               'Sounds', 'Languages', 'Common', *TARGETS)
    restricted = [game, skill_tree] + [p / name for p in projects for name in content]
    if root in projects or any(root.is_relative_to(p.resolve()) for p in restricted):
        raise CacheError('Choose a local cache directory outside the game, mod content, and skill distribution trees.')
    root.mkdir(parents=True, exist_ok=True)
    try:
        with (root / '.gitignore').open('x', encoding='utf-8') as stream:
            stream.write('# Local decompilation evidence; do not distribute.\n*\n')
    except FileExistsError:
        pass


def build(game_root, target, cache_dir=None, *, dll=None, ilspy=None):
    """One explicit ILSpy batch; commit the identity manifest last, without replacing a cache."""
    stage = None
    try:
        fingerprint, game, core, selected = _identity(game_root, target, dll)
        root = _cache_root(cache_dir)
        current = _inspect_identity(fingerprint, root)
        if current['state'] == 'available':
            return current | {'reused': True}
        if current['state'] == 'incomplete':
            raise CacheError('Existing cache entry is incomplete; preserve it and select another cache root.', 'incomplete')
        executable = _executable(ilspy)
        version = _run([executable, '--disable-updatecheck', '--version'], timeout=15).stdout.strip()
        if not version:
            raise CacheError('ILSpy did not report a version.', 'failed')
        _private_cache_dir(root, game)
        parent = root / target
        parent.mkdir(exist_ok=True)
        if parent.resolve() != parent:
            raise CacheError('Version cache directory redirects outside the cache root.')
        key = _key(fingerprint)
        entry = parent / key
        stage = Path(tempfile.mkdtemp(prefix=f'.{key[:12]}.building-', dir=parent))
        source = stage / 'source'
        source.mkdir()
        _run([executable, '--disable-updatecheck', '-p', '-r', str(core.parent), '-o', str(source), str(selected)], timeout=600)
        files = {p.relative_to(source).as_posix(): _sha(p) for p in sorted(source.rglob('*.cs')) if p.is_file()}
        if not files:
            raise CacheError('ILSpy completed without emitting C# source files.', 'failed')
        after, _, _, _ = _identity(game_root, target, dll)
        if after != fingerprint:
            raise CacheError('Game or selected DLL changed while decompiling; no cache manifest committed.', 'failed')
        tool = {'name': 'ilspycmd', 'version': version, 'executable': executable, 'mode': 'project'}
        manifest = dict(schema=SCHEMA, cacheKey=key, fingerprint=fingerprint, tool=tool, sourceFileCount=len(files),
                        sourceFiles=files, createdUtc=datetime.now(timezone.utc).isoformat(),
                        inputPaths=dict(gameRoot=str(game), gameAssembly=str(core), assembly=str(selected)))
        try:
            entry.mkdir()  # Exclusive publication; an existing tree is never overwritten.
        except FileExistsError:
            other = _inspect_identity(fingerprint, root)
            if other['state'] == 'available':
                return other | {'reused': True, 'retainedStaging': str(stage)}
            raise CacheError('Another cache entry already exists; no files replaced.', 'incomplete') from None
        source.rename(entry / 'source')
        pending_manifest = stage / 'manifest.json'
        pending_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        pending_manifest.rename(entry / 'manifest.json')
        stage.rmdir()
        return _inspect_identity(fingerprint, root) | {'reused': False}
    except (CacheError, OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        report = dict(state=getattr(exc, 'state', 'failed'), target=target, detail=str(exc))
        if stage is not None and stage.exists():
            report['retainedStaging'] = str(stage)
        return report


def locate(game_root, target, type_name, cache_dir=None, *, dll=None, member=None):
    """Return likely type paths, not proof of a type/member or an interpreted method body."""
    segment = r'[^\W\d]\w*(?:`\d+)?'
    if not re.fullmatch(segment + r'(?:[.+]' + segment + r')*', type_name):
        raise CacheError('Provide a qualified CLR type name, using + for nested types.')
    report = inspect(game_root, target, cache_dir, dll=dll)
    if report['state'] != 'available':
        return report
    outer = type_name.split('+', 1)[0]
    namespace, _, name = outer.rpartition('.')
    name = name.split('`', 1)[0]
    source = Path(report['sourceRoot']).resolve()
    data = _manifest(source.parent)
    rel = f'{namespace}/{name}.cs' if namespace else f'{name}.cs'
    paths = []
    if rel in data['sourceFiles']:
        try:
            path = _file_path(source, rel)
            if _sha(path) != data['sourceFiles'][rel]:
                raise CacheError('Candidate source changed since it was cached.', 'incomplete')
            paths.append(str(path))
        except CacheError as exc:
            return dict(state=exc.state, target=target, detail=str(exc))
    return report | dict(type=type_name, candidates=paths,
                         lookupState='candidate' if paths else 'not-located',
                         searchArgs=['rg', '-n', '-m', '12', '--fixed-strings', '--', member or name, *paths] if paths else
                                    ['rg', '-l', '-g', '*.cs', '--fixed-strings', '--', name, str(source)],
                         lookupNote='Filename/literal-text guidance only; an absent candidate is not an absent API.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'build', 'locate'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--game-root', required=True, help='Actual game directory containing Version.txt')
        cmd.add_argument('--target', required=True, choices=TARGETS)
        cmd.add_argument('--cache-dir', help='Local-only cache root (default: .local/source-cache)')
        cmd.add_argument('--dll', help='Optional upstream DLL; defaults to game Assembly-CSharp.dll')
        if name == 'build':
            cmd.add_argument('--ilspy', help='Existing ilspycmd executable; otherwise checks PATH')
        elif name == 'locate':
            cmd.add_argument('--type', required=True, dest='type_name')
            cmd.add_argument('--member', help='Optional literal member text for a bounded rg hint')
    args = vars(parser.parse_args(argv))
    command = args.pop('command')
    try:
        result = {'inspect': inspect, 'build': build, 'locate': locate}[command](**args)
    except (CacheError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        result = dict(state=getattr(exc, 'state', 'failed'), target=args['target'], detail=str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['state'] == 'available' else 1


if __name__ == '__main__':
    raise SystemExit(main())
