"""Batch raw Def and ParentName lookup. Does not execute the game loader."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET


def xml_files(folder):
    """Use directory metadata, avoiding per-file resolve calls on ordinary files."""
    pending = [folder]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if not (getattr(entry.stat(follow_symlinks=False), 'st_file_attributes', 0) & 0x400):
                        pending.append(Path(entry.path))
                elif entry.name.lower().endswith('.xml') and entry.is_file(follow_symlinks=False):
                    st = entry.stat(follow_symlinks=False)
                    if not getattr(st, 'st_file_attributes', 0) & 0x400:
                        yield Path(entry.path), (st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def load_index(db, roots):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, stamp TEXT, sha TEXT, scope TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS nodes (path TEXT, tag TEXT, name TEXT, template TEXT, xml TEXT);
        CREATE INDEX IF NOT EXISTS node_names ON nodes(name);
        CREATE INDEX IF NOT EXISTS node_templates ON nodes(template);
        CREATE INDEX IF NOT EXISTS node_files ON nodes(path);
    ''')
    seen = set()
    reindexed = 0
    with db:
        db.execute('BEGIN IMMEDIATE')
        previous = {path: stamp for path, stamp in db.execute('SELECT path, stamp FROM files WHERE error IS NULL')}
        for folder, role in roots:
            for path, stat_stamp in xml_files(folder):
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                stamp = ':'.join(map(str, stat_stamp))
                if previous.get(key) == stamp:
                    continue
                reindexed += 1
                db.execute('DELETE FROM nodes WHERE path=?', (key,))
                try:
                    body = path.read_bytes()
                    xml = ET.fromstring(body)
                    if xml.tag != 'Defs':
                        raise ValueError('Expected Defs root')
                    rows = []
                    for node in xml:
                        name = (node.findtext('defName') or '').strip()
                        template = node.get('Name')
                        if name or template:
                            rows.append((key, node.tag, name, template, ET.tostring(node, encoding='unicode').strip()))
                    db.executemany('INSERT INTO nodes VALUES (?,?,?,?,?)', rows)
                    db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?,NULL)', (key, stamp, hashlib.sha256(body).hexdigest(), role))
                except (OSError, ValueError, ET.ParseError) as exc:
                    db.execute('INSERT OR REPLACE INTO files VALUES (?,?,NULL,?,?)', (key, stamp, role, str(exc)))
        for (removed,) in db.execute('SELECT path FROM files').fetchall():
            if removed not in seen:
                db.execute('DELETE FROM nodes WHERE path=?', (removed,))
                db.execute('DELETE FROM files WHERE path=?', (removed,))
    return len(seen), reindexed


def query_defs(game_root, requests, limit, *, def_roots=(), cache_dir=None, identity=None):
    if not requests or len(requests) > 24 or not 1 <= limit <= 50:
        raise ValueError('Use 1–24 Def queries and a limit between 1 and 50')
    keys = []
    for query in requests:
        tag, sep, name = query.partition(':')
        name = (name if sep else tag).strip()
        tag = tag.strip() if sep else None
        if not name or (sep and not tag):
            raise ValueError('Expected defName or Type:defName: ' + query)
        keys.append((tag, name))
    data = Path(game_root).resolve() / 'Data'
    roots = [(p, 'installed game data') for p in sorted(data.glob('*/Defs')) if p.is_dir()]
    for directory in def_roots:
        directory = Path(directory).resolve()
        if directory.name.casefold() != 'defs':
            directory /= 'Defs'
        if not directory.is_dir():
            raise ValueError('No Defs directory at explicitly supplied root: ' + str(directory))
        roots.append((directory, 'explicit source; load selection unverified'))
    roots = [(folder.resolve(), role) for folder, role in roots]
    location = ':memory:'
    if cache_dir is not None:
        directory = Path(cache_dir).resolve()
        game = Path(game_root).resolve()
        if directory.is_relative_to(game):
            raise ValueError('Place Def index outside the game installation')
        directory.mkdir(parents=True, exist_ok=True)
        version_path = game / 'Version.txt'
        stamp = identity if identity is not None else version_path.read_text(encoding='utf-8-sig').strip() if version_path.exists() else None
        index_key = hashlib.sha256(json.dumps([str(game), stamp, [(str(p), role) for p, role in roots]], sort_keys=True).encode()).hexdigest()
        location = directory / ('defs-v1-' + index_key + '.sqlite3')

    with closing(sqlite3.connect(location, timeout=60)) as db:
        count, reindexed = load_index(db, roots)
        return read_matches(db, requests, keys, limit, count, reindexed)


def read_matches(db, requests, keys, limit, count, reindexed):
    def rows(column, value, tag=None):
        clause = ' AND nodes.tag=?' if tag else ''
        args = (value, tag) if tag else (value,)
        join = ' FROM nodes JOIN files USING(path) WHERE nodes.' + column + '=?' + clause
        total = db.execute('SELECT count(*)' + join, args).fetchone()[0]
        records = []
        for path, sha, scope, xml in db.execute('SELECT path, sha, scope, xml' + join + ' ORDER BY path LIMIT ?', (*args, min(limit, 3))):
            records.append((ET.fromstring(xml), {'path': path, 'sha256': sha, 'scope': scope}, xml))
        return total, records

    def describe(record, cap):
        node, source, snippet = record
        return {'type': node.tag, 'defName': node.findtext('defName'), 'attributes': dict(node.attrib),
                'source': source, 'xml': snippet[:cap], 'xmlTruncated': len(snippet) > cap}

    def parents(record):
        chain, seen = [], set()
        key = record[0].get('ParentName')
        while key and len(chain) < 8:
            if key in seen:
                chain.append({'name': key, 'state': 'cycle'})
                break
            seen.add(key)
            total, options = rows('template', key)
            if total != 1:
                chain.append({'name': key, 'state': 'ambiguous' if total else 'not_found_in_scanned_xml',
                              'candidateCount': total, 'candidates': [describe(r, 500) for r in options]})
                break
            chain.append({'name': key, 'state': 'candidate', **describe(options[0], 1200)})
            key = options[0][0].get('ParentName')
        if key and len(chain) == 8 and chain[-1]['state'] == 'candidate':
            chain.append({'name': key, 'state': 'depth_limit'})
        return chain

    results = []
    for query, (tag, name) in zip(requests, keys):
        total, selected = rows('name', name, tag)
        results.append({'query': query, 'state': 'found' if total == 1 else 'ambiguous' if total else 'not_found_in_scanned_xml',
                        'matchCount': total, 'matches': [{**describe(r, 3200), 'parentChain': parents(r)} for r in selected]})
    issues = [{'path': path, 'reason': error} for path, error in db.execute('SELECT path,error FROM files WHERE error IS NOT NULL LIMIT 10')]
    return {'queries': results, 'scannedFileCount': count, 'reindexedFileCount': reindexed,
            'issueCount': db.execute('SELECT count(*) FROM files WHERE error IS NOT NULL').fetchone()[0], 'issues': issues,
            'scope': 'Raw installed and explicit-root XML, refreshed by file stamps; hashes identify parsed snapshots. No active DLC/mod selection, inheritance merge, patches or runtime resolution. Linked descendants not scanned.'}
