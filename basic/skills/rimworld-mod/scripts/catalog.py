#!/usr/bin/env python3
"""Read-only, bounded queries against exact-build metadata catalogs.

Examples:
  python catalog.py profile --target 1.7
  python catalog.py query --target 1.7 --type Verse.ThingDef --symbol comps
  python catalog.py query --target 1.7 --purpose ui --limit 8
  python catalog.py recipes --target 1.7 --purpose ui
  python catalog.py verify --target 1.7 --game-root PATH --harmony-root PATH

Partial catalogs cannot prove game-wide absence. No game/DLL code is executed.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_DATA = Path(__file__).resolve().parent.parent / 'data'


class CatalogError(ValueError):
    pass


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CatalogError(f'Cannot read {Path(path).name}: {exc}') from exc


def load_contract(data_dir):
    path = Path(data_dir) / 'catalog-contract.json'
    return read_json(path if path.exists() else DEFAULT_DATA / 'catalog-contract.json')


def load_profile(target, data_dir=DEFAULT_DATA):
    if target not in ('1.6', '1.7'):
        raise CatalogError('Select target 1.6 or 1.7 explicitly.')
    profile = read_json(Path(data_dir) / 'profiles' / (target + '.json'))
    contract = load_contract(data_dir)
    required = contract['profileRequired']
    if not isinstance(profile, dict) or any(k not in profile for k in required):
        raise CatalogError('Invalid profile contract.')
    if profile['schema'] != 1 or profile['target'] != target:
        raise CatalogError('Profile schema/target mismatch.')
    for assembly in profile['assemblies']:
        if not all(k in assembly for k in contract['assemblyIdentity']):
            raise CatalogError('Incomplete assembly identity.')
        if not all(k in assembly for k in ('relativePath', 'origin')):
            raise CatalogError('Missing local-verification layout.')
        if not isinstance(assembly['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', assembly['sha256']):
            raise CatalogError('Invalid assembly hash.')
    return profile


def load_catalog(profile, data_dir=DEFAULT_DATA):
    contract = load_contract(data_dir)
    catalog = read_json(Path(data_dir) / 'api' / (profile['target'] + '.json'))
    if not isinstance(catalog, dict) or catalog.get('schema') != 1 or catalog.get('profileId') != profile['id']:
        raise CatalogError('Catalog schema/profile mismatch.')
    known = {(a['name'], a['sha256']) for a in profile['assemblies']}
    symbols = catalog.get('symbols')
    if not isinstance(symbols, list) or not isinstance(catalog.get('coverage'), list):
        raise CatalogError('Invalid symbol/coverage collection.')
    covered_types = set()
    for scope in catalog['coverage']:
        if (scope.get('assembly'), scope.get('sha256')) not in known or not isinstance(scope.get('types'), list):
            raise CatalogError('Coverage provenance does not match profile.')
        covered_types.update((scope['assembly'], name) for name in scope['types'])
    seen = set()
    for row in symbols:
        if not isinstance(row, dict) or any(k not in row for k in contract['symbolRequired']) or 'assemblySha256' not in row:
            raise CatalogError('Incomplete symbol contract.')
        if row['profileId'] != profile['id'] or (row['assembly'], row['assemblySha256']) not in known:
            raise CatalogError('Symbol provenance does not match profile.')
        if (row['assembly'], row['type']) not in covered_types:
            raise CatalogError('Symbol is outside declared coverage.')
        if not isinstance(row['evidence'], dict) or row['evidence'].get('level') not in contract['evidenceLevels']:
            raise CatalogError('Unsupported evidence level.')
        if row['id'] in seen:
            raise CatalogError('Duplicate symbol identity.')
        expected_id = '|'.join((row['profileId'], row['assemblySha256'], row['type'], row['kind'], row['signature']))
        if row['id'] != expected_id:
            raise CatalogError('Symbol id does not encode profile/hash/type/kind/signature.')
        seen.add(row['id'])
    return catalog


def query(profile, catalog, *, type_name=None, symbol=None, purpose=None,
          assembly=None, kind=None, symbol_id=None, public_only=False, limit=5):
    if not 1 <= limit <= 50:
        raise CatalogError('Limit must be between 1 and 50.')
    if not any((type_name, symbol, purpose, symbol_id)):
        raise CatalogError('Supply a type, symbol, purpose or full symbol id; do not dump the catalog.')
    visible_types = {(r['assembly'], r['type']) for r in catalog['symbols']
                     if r['kind'] == 'type' and r.get('effectivePublic')}
    matches = []
    for row in catalog['symbols']:
        if type_name and row['type'] != type_name:
            continue
        if symbol and row.get('name') != symbol:
            continue
        if purpose and row.get('purpose') != purpose:
            continue
        if assembly and row['assembly'] != assembly:
            continue
        if kind and row['kind'] != kind:
            continue
        if symbol_id and row['id'] != symbol_id:
            continue
        if public_only and ((row['assembly'], row['type']) not in visible_types or
                            (row['kind'] != 'type' and not row.get('isPublic'))):
            continue
        matches.append(row)
    selection = bool(symbol or symbol_id)
    state = 'ambiguous' if selection and len(matches) > 1 else 'found' if matches else 'not_covered'
    purposes = {row.get('purpose') for row in matches[:limit]}
    references = ['../references/version-data.md', '../references/usage-examples.md']
    if 'harmony' in purposes or purpose == 'harmony':
        references.append('../references/harmony-versions.md')
    return {'state': state, 'profileId': profile['id'], 'target': profile['target'],
            'sourceProfile': '../data/profiles/' + profile['target'] + '.json',
            'references': references,
            'mode': 'selection' if selection else 'browse',
            'matchCount': len(matches), 'truncated': len(matches) > limit,
            'symbols': matches[:limit],
            'note': 'Metadata declarations only. Visibility is not an extension contract or XML-valid-field proof. Partial coverage: no match does not prove absence; inspect inherited members and missing assemblies separately. Defaults/constraints and runtime behavior are not captured.'}


def load_recipes(profile, catalog, data_dir=DEFAULT_DATA):
    contract = load_contract(data_dir)
    document = read_json(Path(data_dir) / 'recipes.json')
    if not isinstance(document, dict) or document.get('schema') != 1 or not isinstance(document.get('recipes'), list):
        raise CatalogError('Invalid recipe collection/schema.')
    known_symbols = {row['id'] for row in catalog['symbols']}
    seen = set()
    applicable = []
    for row in document['recipes']:
        if not isinstance(row, dict) or any(key not in row for key in contract['recipeRequired']):
            raise CatalogError('Incomplete recipe contract.')
        if row['id'] in seen:
            raise CatalogError('Duplicate recipe identity.')
        seen.add(row['id'])
        if not isinstance(row['profileIds'], dict) or not isinstance(row['symbolsByTarget'], dict):
            raise CatalogError('Invalid recipe target linkage.')
        if set(row['profileIds']) != set(row['symbolsByTarget']) or not set(row['profileIds']).issubset({'1.6', '1.7'}):
            raise CatalogError('Recipe profile/symbol targets mismatch.')
        if not isinstance(row['evidence'], dict):
            raise CatalogError('Invalid recipe evidence.')
        for target, profile_id in row['profileIds'].items():
            anchors = row['symbolsByTarget'][target]
            if not isinstance(anchors, list) or any(not isinstance(anchor, str) or not anchor.startswith(profile_id + '|') for anchor in anchors):
                raise CatalogError('Recipe anchor profile mismatch.')
        target = profile['target']
        if target not in row['profileIds']:
            continue
        if row['profileIds'][target] != profile['id']:
            raise CatalogError('Recipe target profile does not match selected catalog.')
        if not all(anchor in known_symbols for anchor in row['symbolsByTarget'][target]):
            raise CatalogError('Recipe refers to uncovered/unknown symbols.')
        applicable.append(row)
    return applicable


def query_recipes(profile, recipes, *, purpose=None, recipe_id=None, limit=5):
    if not 1 <= limit <= 50:
        raise CatalogError('Limit must be between 1 and 50.')
    if not (purpose or recipe_id):
        raise CatalogError('Supply a recipe purpose or id; do not dump the collection.')
    matches = [row for row in recipes if (not purpose or row['purpose'] == purpose)
               and (not recipe_id or row['id'] == recipe_id)]
    selected = []
    for row in matches[:limit]:
        item = {key: value for key, value in row.items() if key not in ('profileIds', 'symbolsByTarget')}
        item.update(profileId=profile['id'], symbols=row['symbolsByTarget'][profile['target']])
        selected.append(item)
    return {'state': 'found' if matches else 'not_covered', 'profileId': profile['id'],
            'matchCount': len(matches), 'truncated': len(matches) > limit, 'recipes': selected,
            'note': 'Selected candidate recipes with checked metadata anchors. Recipe evidence is unchanged: metadata linkage does not prove compilation or consumer/runtime behavior.'}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify(profile, *, game_root=None, harmony_root=None):
    roots = {'game': Path(game_root).resolve() if game_root else None,
             'harmony': Path(harmony_root).resolve() if harmony_root else None}
    checks = []
    for item in profile['assemblies']:
        root = roots.get(item['origin'])
        row = {'assembly': item['name'], 'origin': item['origin'], 'expectedSha256': item['sha256']}
        if root is None:
            row['state'] = 'not_covered'
            row['reason'] = 'No local root supplied.'
        else:
            path = (root / item['relativePath']).resolve()
            if not path.is_relative_to(root):
                raise CatalogError('Assembly relativePath escapes supplied root.')
            try:
                actual = sha256(path)
                row.update(observedSha256=actual, state='found' if actual == item['sha256'] else 'stale')
            except OSError as exc:
                row.update(state='parse_failed', reason=str(exc))
        checks.append(row)
    if game_root:
        try:
            actual = (roots['game'] / 'Version.txt').read_text(encoding='utf-8-sig').strip()
            checks.append({'file': 'Version.txt', 'state': 'found' if actual == profile['game']['versionText'] else 'stale',
                           'observed': actual, 'expected': profile['game']['versionText']})
        except OSError as exc:
            checks.append({'file': 'Version.txt', 'state': 'parse_failed', 'reason': str(exc)})
    states = {r['state'] for r in checks}
    state = next((s for s in ('stale', 'parse_failed', 'not_covered') if s in states), 'found')
    return {'state': state, 'profileId': profile['id'], 'checks': checks,
            'note': 'File identity only; does not prove loaded Harmony provider, DLC/mod combination, binding or gameplay.'}


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('profile', 'query', 'recipes', 'verify'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--target', required=True, choices=('1.6', '1.7'))
        cmd.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
        if name == 'query':
            cmd.add_argument('--type', dest='type_name')
            cmd.add_argument('--symbol')
            cmd.add_argument('--id', dest='symbol_id')
            cmd.add_argument('--purpose')
            cmd.add_argument('--assembly')
            cmd.add_argument('--kind', choices=('type', 'field', 'method'))
            cmd.add_argument('--public', action='store_true', dest='public_only')
            cmd.add_argument('--limit', type=int, default=5)
        if name == 'verify':
            cmd.add_argument('--game-root', type=Path)
            cmd.add_argument('--harmony-root', type=Path)
        if name == 'recipes':
            cmd.add_argument('--purpose')
            cmd.add_argument('--id', dest='recipe_id')
            cmd.add_argument('--limit', type=int, default=5)
    args = parser.parse_args(argv)
    try:
        profile = load_profile(args.target, args.data_dir)
        if args.command == 'profile':
            result = {'state': 'found', 'profile': profile}
        elif args.command == 'query':
            result = query(profile, load_catalog(profile, args.data_dir), **{
                k: getattr(args, k) for k in ('type_name', 'symbol', 'purpose', 'assembly', 'kind', 'symbol_id', 'public_only', 'limit')})
        elif args.command == 'recipes':
            result = query_recipes(profile, load_recipes(profile, load_catalog(profile, args.data_dir), args.data_dir),
                                   purpose=args.purpose, recipe_id=args.recipe_id, limit=args.limit)
        else:
            result = verify(profile, game_root=args.game_root, harmony_root=args.harmony_root)
    except (CatalogError, TypeError, KeyError) as exc:
        result = {'state': 'parse_failed', 'error': str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 3 if result['state'] == 'stale' else 2 if result['state'] == 'parse_failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
