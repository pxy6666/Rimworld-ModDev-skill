#!/usr/bin/env python3
"""Bounded batch lookups over exact local RimWorld inputs. Python 3.10+.

`type`: qualified or short type names. `member`/`refs`: Type::Name,
Type::Name(parameters), or Type::*; use the emitted memberQuery to disambiguate.
`def`: DefType:defName or defName (raw XML; no SDK needed).
"""
import argparse
from contextlib import ExitStack, closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

PROBE = Path(__file__).resolve().with_name('metadata-probe')
INDEX_SCHEMA = '1'
MAX_BATCH = 12
MAX_LIMIT = 25


class LookupError(ValueError):
    pass


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def game_identity(root, target):
    root = Path(root).resolve(strict=True)
    build = (root / 'Version.txt').read_text(encoding='utf-8-sig').strip()
    match = re.fullmatch(r'(1\.[67])\.\d+(?:\s+rev\d+)?', build)
    if not match or match[1] != target:
        raise LookupError(f'Game Version.txt is {build!r}, expected an exact {target} build.')
    candidates = ([root / 'Assembly-CSharp.dll'] if target == '1.7' else
                  list(root.glob('*_Data/Managed/Assembly-CSharp.dll')))
    files = [file for file in candidates if file.is_file()]
    if len(files) != 1:
        raise LookupError(f'Expected one Assembly-CSharp.dll in {target} layout; found {len(files)}.')
    return root, files[0], {'target': target, 'gameVersion': build, 'gameSha256': digest(files[0])}


def probe_fingerprint():
    return hashlib.sha256((digest(PROBE / 'Program.cs') + digest(PROBE / 'MetadataProbe.csproj')).encode()).hexdigest()


def dotnet_env(cache):
    return dict(os.environ, DOTNET_CLI_HOME=str(cache / 'dotnet-home'), DOTNET_NOLOGO='1',
                DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
                DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='true')


def dotnet_executable():
    dotnet = shutil.which('dotnet')
    if not dotnet:
        raise LookupError('A local .NET SDK 8+ is needed to create a new DLL index; raw Def queries do not require it.')
    return dotnet


def probe_binary(cache, fingerprint):
    dotnet = dotnet_executable()
    env = dotnet_env(cache)
    ready = cache / f'probe-{fingerprint}'
    result = ready / 'MetadataProbe.dll'
    if result.is_file():
        return dotnet, result
    listed = subprocess.run([dotnet, '--list-sdks'], env=env, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', check=True, timeout=30)
    majors = [int(match[1]) for line in listed.stdout.splitlines()
              if (match := re.match(r'^(\d+)\.', line)) and int(match[1]) >= 8]
    if not majors:
        raise LookupError('No local .NET SDK 8+ found; use a matching existing index or inspect via local MCP/DecompilerServer.')
    with tempfile.TemporaryDirectory(prefix='probe-build-', dir=cache) as temp:
        temp = Path(temp)
        shutil.copyfile(PROBE / 'Program.cs', temp / 'Program.cs')
        project = (PROBE / 'MetadataProbe.csproj').read_text(encoding='utf-8')
        (temp / 'MetadataProbe.csproj').write_text(
            project.replace('>net8.0<', f'>net{max(majors)}.0<'), encoding='utf-8')
        (temp / 'no-package-sources').mkdir()
        out = temp / 'tool'
        build = subprocess.run(
            [dotnet, 'build', str(temp / 'MetadataProbe.csproj'), '-c', 'Release', '-o', str(out),
             f'-p:RestoreSources={temp / "no-package-sources"}',
             '--nologo', '--verbosity', 'quiet'], cwd=temp, env=env, capture_output=True,
            text=True, encoding='utf-8', errors='replace', timeout=120)
        if build.returncode != 0:
            raise LookupError('Could not build offline metadata reader: ' + (build.stdout + build.stderr)[-1800:])
        try:
            out.rename(ready)
        except OSError:
            if not result.is_file():
                raise
    return dotnet, result


SQL = '''
CREATE TABLE manifest (id INTEGER PRIMARY KEY CHECK (id=1), data TEXT NOT NULL);
CREATE TABLE types (name TEXT PRIMARY KEY, short_name TEXT, base_short_name TEXT, parent TEXT, flags TEXT, public INTEGER);
CREATE TABLE members (token INTEGER PRIMARY KEY, type TEXT, kind TEXT, name TEXT, signature TEXT, identity TEXT,
                      display_key TEXT, flags TEXT, parameters TEXT);
CREATE TABLE operands (caller INTEGER, target_assembly TEXT, target_version TEXT, target_type TEXT,
                       target_name TEXT, target_identity TEXT, target_kind TEXT, opcode TEXT, occurrences INTEGER);
'''

INSERTS = {'type': 'INSERT INTO types VALUES (?,?,?,?,?,?)',
           'member': 'INSERT INTO members VALUES (?,?,?,?,?,?,?,?,?)',
           'ref': 'INSERT INTO operands VALUES (?,?,?,?,?,?,?,?,?)'}


def readonly(path):
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def manifest(path):
    with closing(readonly(path)) as conn:
        row = conn.execute('SELECT data FROM manifest WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {}


def build_index(path, assembly, expected, cache):
    dotnet, probe = probe_binary(cache, expected['probe'])
    fd, temp_name = tempfile.mkstemp(suffix='.sqlite', prefix='index-building-', dir=cache)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with closing(sqlite3.connect(temp)) as db, tempfile.TemporaryFile(dir=cache) as stderr:
            db.executescript('PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;' + SQL)
            batches = {kind: [] for kind in INSERTS}
            header = done = None
            with subprocess.Popen([dotnet, str(probe), str(assembly), expected['mode']], stdout=subprocess.PIPE,
                                  stderr=stderr, env=dotnet_env(cache), text=True, encoding='utf-8') as process:
                try:
                    for line in process.stdout:
                        kind, *row = json.loads(line)
                        if kind == 'header':
                            header = row
                            if row[2] != expected['assemblySha256']:
                                raise LookupError('Assembly changed while being read; rerun with a stable installation.')
                        elif kind == 'done':
                            done = row
                        else:
                            if kind == 'type':
                                row.insert(2, re.sub(r'`\d+$', '', row[1]))
                            elif kind == 'member' and row[-1] is not None:
                                row[-1] = json.dumps(row[-1], separators=(',', ':'))
                            batches[kind].append(row)
                            if len(batches[kind]) >= 4096:
                                db.executemany(INSERTS[kind], batches[kind])
                                batches[kind].clear()
                    code = process.wait(timeout=15)
                except BaseException:
                    process.kill()
                    raise
            if code or header is None or done is None:
                stderr.seek(0)
                raise LookupError(f'PE metadata reader failed for {assembly.name}: ' + stderr.read(1200).decode('utf-8', 'replace'))
            for kind, rows in batches.items():
                db.executemany(INSERTS[kind], rows)
            db.executescript('CREATE INDEX short_type ON types(short_name); CREATE INDEX short_base_type ON types(base_short_name);'
                             'CREATE INDEX member_names ON members(type,name);')
            if expected['mode'] == 'refs':
                db.execute('CREATE INDEX operand_targets ON operands(target_type,target_name,target_assembly,target_version)')
            metadata = dict(expected, assembly=header[0], version=header[1], scannedIlMethods=done[0], ilScanErrors=done[1])
            db.execute('INSERT INTO manifest VALUES (1,?)', (json.dumps(metadata),))
            db.commit()
        try:
            temp.replace(path)
        except OSError:
            if not path.is_file() or not manifest_matches(path, expected):
                raise
    finally:
        temp.unlink(missing_ok=True)


def manifest_matches(path, expected):
    try:
        actual = manifest(path)
        return all(actual.get(k) == v for k, v in expected.items())
    except (OSError, ValueError, sqlite3.Error):
        return False


def ensure_index(assembly, identity, cache, mode, assembly_hash=None):
    expected = dict(identity, schema=INDEX_SCHEMA, probe=probe_fingerprint(), mode=mode,
                    assemblySha256=assembly_hash or digest(assembly))
    def address(metadata):
        key = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
        return cache / f'{metadata["mode"]}-{key}.sqlite'
    path = address(expected)
    if manifest_matches(path, expected):
        return path
    if mode == 'decl':
        extended = dict(expected, mode='refs')
        extended_path = address(extended)
        if manifest_matches(extended_path, extended):
            return extended_path
    build_index(path, assembly, expected, cache)
    return path


def match_types(books, term):
    rows = [(db, meta, row) for db, meta in books
            for row in db.execute('SELECT * FROM types WHERE name=?', (term,))]
    if rows or '.' in term or '+' in term:
        return rows
    return [(db, meta, row) for db, meta in books for row in db.execute(
        'SELECT * FROM types WHERE short_name=? OR base_short_name=? ORDER BY name', (term, term))]


def source(meta):
    return {'assembly': meta['assembly'], 'version': meta['version'], 'sha256': meta['assemblySha256']}


def type_row(meta, row):
    return dict(source(meta), type=row['name'], parent=row['parent'], flags=row['flags'],
                effectivePublic=bool(row['public']))


def member_row(meta, row):
    return dict(source(meta), type=row['type'], name=row['name'], kind=row['kind'], signature=row['signature'],
                flags=row['flags'], token=f"0x{row['token']:08x}",
                memberQuery=row['type'] + '::' + row['signature'],
                parameters=json.loads(row['parameters']) if row['parameters'] else None)


def member_parts(request):
    type_name, sep, member = request.partition('::')
    if not sep or not type_name or not member:
        raise LookupError(f'Use Type::Member, Type::Signature, or Type::*: {request!r}.')
    return type_name, member


def select_members(db, type_name, member, limit=None):
    if member == '*':
        condition, values = 'type=?', (type_name,)
    else:
        normalized = member.replace(' ', '')
        condition = "type=? AND (name=? OR replace(display_key,' ','')=? OR replace(signature,' ','')=?)"
        values = (type_name, member, normalized, normalized)
    count = db.execute('SELECT count(*) FROM members WHERE ' + condition, values).fetchone()[0]
    sql = 'SELECT * FROM members WHERE ' + condition + ' ORDER BY name,signature,token'
    return count, db.execute(sql + (' LIMIT ?' if limit is not None else ''),
                             (*values, limit) if limit is not None else values).fetchall()


def result(request, state, count=0, matches=(), **details):
    return dict(query=request, state=state, matchCount=count, truncated=count > len(matches),
                matches=list(matches), **details)


def lookup_one(kind, books, request, limit):
    type_name, member = (request, None) if kind == 'type' else member_parts(request)
    types = match_types(books, type_name)
    if len(types) > 1 or kind == 'type':
        state = 'ambiguous' if len(types) > 1 else 'found' if types else 'not_covered'
        return result(request, state, len(types), [type_row(meta, row) for _, meta, row in types[:limit]])
    if kind == 'member':
        if not types:
            return result(request, 'not_covered')
        db, meta, found = types[0]
        count, rows = select_members(db, found['name'], member, limit)
        state = 'ambiguous' if count > 1 and member != '*' else 'found' if count else 'not_covered'
        return result(request, state, count, [member_row(meta, row) for row in rows])
    return refs_one(books, request, type_name, member, types, limit)


def refs_one(books, request, type_name, member, types, limit):
    if types:
        db, meta, found = types[0]
        type_name = found['name']
        condition = 'r.target_type=? AND r.target_assembly=? AND r.target_version=?'
        args = (type_name, meta['assembly'], meta['version'])
        if member != '*':
            count, rows = select_members(db, type_name, member, limit)
            if not count:
                return result(request, 'not_covered', note='No matching declared member; inherited members need their declaring type.')
            if count > 1:
                return result(request, 'ambiguous', count, [member_row(meta, row) for row in rows])
            condition += ' AND r.target_kind=? AND r.target_identity=?'
            args += (rows[0]['kind'], rows[0]['identity'])
    else:
        if '.' not in type_name:
            return result(request, 'not_covered', note='Use the fully qualified target type or add its DLL explicitly.')
        if '(' in member or ' ' in member:
            return result(request, 'not_covered', note='For signature selection, add the declaring DLL explicitly.')
        condition, args = 'r.target_type=?', (type_name,)
        if member != '*':
            condition += ' AND r.target_name=?'
            args += (member,)
            targets = set()
            for db, _ in books:
                targets.update(tuple(row) for row in db.execute(
                    'SELECT DISTINCT r.target_assembly,r.target_version,r.target_kind,r.target_identity '
                    'FROM operands r WHERE ' + condition, args))
            if len(targets) > 1:
                candidates = [{'assembly': a, 'version': v, 'kind': k, 'operandSignature': sig}
                              for a, v, k, sig in sorted(targets)[:limit]]
                return result(request, 'ambiguous', len(targets), candidates, note='Add the declaring DLL to select a signature.')
    total = 0
    matches = []
    for db, meta in books:
        total += db.execute('SELECT count(*) FROM operands r WHERE ' + condition, args).fetchone()[0]
        left = limit - len(matches)
        if left <= 0:
            continue
        rows = db.execute('SELECT m.type, m.signature, r.target_assembly, r.target_version, r.target_type, '
                          'r.target_name, r.target_identity, r.target_kind, r.opcode, r.occurrences '
                          'FROM operands r JOIN members m ON m.token=r.caller WHERE ' + condition +
                          ' ORDER BY r.caller,r.opcode LIMIT ?', (*args, left))
        matches.extend(dict(source(meta), callerType=r['type'], callerSignature=r['signature'],
                            targetAssembly=r['target_assembly'], targetVersion=r['target_version'], targetType=r['target_type'],
                            targetName=r['target_name'], operandSignature=r['target_identity'], targetKind=r['target_kind'],
                            opcode=r['opcode'], occurrences=r['occurrences']) for r in rows)
    return result(request, 'found' if total else 'not_covered', total, matches)


def private_cache_dir(path, game_root, upstream_roots=()):
    cache = Path(path).resolve()
    skill_tree = Path(__file__).resolve().parents[2]
    protected_names = {'skills', 'variants', '.agents', '.git', 'about', 'defs', 'patches',
                       'assemblies', 'textures', 'sounds', 'languages', 'common', '1.6', '1.7'}
    if (cache in {Path.cwd().resolve(), skill_tree.parent} or cache.is_relative_to(game_root) or
            cache.is_relative_to(skill_tree) or any(part.casefold() in protected_names for part in cache.parts) or
            any(cache.is_relative_to(Path(root).resolve()) for root in upstream_roots)):
        raise LookupError('Choose a local cache outside the game, mod content, and skill distribution trees (e.g. .local/lookup).')
    return cache


def run(args):
    if not 1 <= args.limit <= MAX_LIMIT or len(args.requests) > MAX_BATCH:
        raise LookupError(f'Use 1–{MAX_LIMIT} hits per query and at most {MAX_BATCH} queries per batch.')
    root, game, identity = game_identity(args.game_root, args.target)
    memory_only = args.command == 'def' and getattr(args, 'no_cache', False)
    cache = None if memory_only else private_cache_dir(args.cache_dir, root, getattr(args, 'def_root', ()))
    if args.command == 'def':
        from lookup_defs import query_defs
        return {'state': 'found', 'identity': identity, 'results':
                query_defs(root, args.requests, args.limit, def_roots=args.def_root,
                           cache_dir=cache, identity=identity)}
    cache.mkdir(parents=True, exist_ok=True)
    mode = 'refs' if args.command == 'refs' else 'decl'
    input_files = {identity['gameSha256']: game}
    for supplied in args.dll:
        path = supplied.resolve(strict=True)
        if path.suffix.lower() != '.dll' or not path.is_file():
            raise LookupError(f'Explicit upstream input must be a DLL: {path.name}')
        input_files.setdefault(digest(path), path)
    with ExitStack() as stack:
        books = []
        for sha, assembly in input_files.items():
            index = ensure_index(assembly, identity, cache, mode, assembly_hash=sha)
            books.append((stack.enter_context(closing(readonly(index))), manifest(index)))
        results = [lookup_one(args.command, books, request, args.limit) for request in args.requests]
    assemblies = [dict(source(meta), scannedIlMethods=meta['scannedIlMethods'], ilScanErrors=meta['ilScanErrors'])
                  for _, meta in books]
    note = ('PE metadata; declarations only, no XML legality or runtime claims. Unresolved names are not proof of absence.'
            if mode == 'decl' else 'Direct static IL member operands only, with recorded assembly scopes. No call graph, virtual/interface dispatch, reflection, Harmony, runtime binding, or absence guarantee.')
    return {'state': 'found', 'identity': identity, 'assemblies': assemblies, 'results': results, 'note': note}


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('type', 'member', 'refs', 'def'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--game-root', type=Path, required=True)
        cmd.add_argument('--target', choices=('1.6', '1.7'), required=True)
        cmd.add_argument('--cache-dir', type=Path, default=Path('.local/lookup'))
        cmd.add_argument('--limit', type=int, default=5)
        if name == 'def':
            cmd.add_argument('--def-root', type=Path, action='append', default=[])
            cmd.add_argument('--no-cache', action='store_true', help='Scan raw XML in memory without writing a local index')
        else:
            cmd.add_argument('--dll', type=Path, action='append', default=[])
        cmd.add_argument('requests', nargs='+')
    try:
        output = run(parser.parse_args(argv))
    except (ValueError, OSError, KeyError, ImportError, sqlite3.Error, subprocess.SubprocessError) as exc:
        output = {'state': 'parse_failed', 'error': str(exc)}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 2 if output['state'] == 'parse_failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
