"""Query bounded migration directions; never rewrite code or load assemblies."""
import argparse
import json
from pathlib import Path
import re
import sys

DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / 'references/compatibility-1.7.json'
PROFILES = ('defs', 'gameplay', 'ui', 'interfaces', 'engine', 'graphics', 'audio', 'optimization', 'library')


def load_catalog(path=DEFAULT_CATALOG):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema') != 1 or data.get('advisoryOnly') is not True or data.get('automaticReplacement') is not False:
        raise ValueError('Unsupported/non-advisory catalog')
    ids = set()
    for row in data['records']:
        if row['id'] in ids:
            raise ValueError('Duplicate record id: ' + row['id'])
        ids.add(row['id'])
        if not row['direction'] or not row['tests'] or not row['caveats']:
            raise ValueError('Record needs direction, caveats and tests: ' + row['id'])
        if any(ref not in data['sources'] for ref in row['evidence']):
            raise ValueError('Unknown evidence source: ' + row['id'])
        if not set(row['profiles']).issubset(PROFILES):
            raise ValueError('Unknown profile: ' + row['id'])
    return data


def normalize(value):
    return re.sub(r'[^a-z0-9]+', '', value.casefold())


def applicability(catalog, row, version=None, fingerprints=None):
    # Evidence applicability is distinct from recipe/game verification.
    sources = [catalog['sources'][ref] for ref in row['evidence']]
    target = [s for s in sources if s.get('sha256') and s['gameVersion'] == catalog['targetGameVersion']]
    historical = [s['gameVersion'] for s in sources if s['kind'] == 'historical_runtime_report']
    result = {'targetGameVersion': catalog['targetGameVersion'], 'historicalRuntimeVersions': sorted(set(historical)),
              'runtimeVerifiedOnTarget': row['runtimeVerifiedOnTarget'], 'state': 'target_not_supplied',
              'requiredTargetAssemblies': sorted({s['assembly'] for s in target})}
    if not version:
        return result
    if version.strip().casefold() != catalog['targetGameVersion'].casefold():
        result['state'] = 'different_or_incomplete_version_verify_relevant_entry'
        return result
    if not target:
        result['state'] = 'historical_report_only_target_not_verified'
        return result
    if fingerprints is None:
        result['state'] = 'version_matches_hashes_unchecked'
        return result
    mismatched = sorted({s['assembly'] for s in target if s['assembly'] in fingerprints and fingerprints[s['assembly']].casefold() != s['sha256']})
    missing = sorted({s['assembly'] for s in target if s['assembly'] not in fingerprints})
    if mismatched:
        result.update(state='source_changed_verify_relevant_entry', mismatchedAssemblies=mismatched)
    elif missing:
        result.update(state='source_hashes_incomplete', missingAssemblies=missing)
    else:
        result['state'] = 'source_hashes_match_recipe_still_requires_validation'
    return result


def query(catalog, text=None, record_id=None, profile=None, version=None, fingerprints=None, limit=3):
    if limit < 1 or limit > 25:
        raise ValueError('limit must be 1..25')
    needle = normalize(text or '')
    found = []
    for row in catalog['records']:
        if profile and profile not in row['profiles']:
            continue
        if record_id:
            match = row['id'].casefold() == record_id.casefold()
        elif text:
            terms = [normalize(t) for t in [row['symbol']] + row['aliases']]
            match = len(needle) >= 3 and any(needle == t or needle in t or (len(t) >= 6 and t in needle) for t in terms)
        else:
            match = True
        if match:
            found.append(row)
    refs = {ref for row in found[:limit] for ref in row['evidence']}
    return {'advisoryOnly': True, 'automaticReplacement': False, 'matched': len(found), 'ambiguous': len(found) > 1,
            'truncated': len(found) > limit, 'records': [{**r, 'applicability': applicability(catalog, r, version, fingerprints)} for r in found[:limit]],
            'sources': {ref: catalog['sources'][ref] for ref in sorted(refs)},
            'nextStep': '核对实际签名/用途和适用条件；按记录方向诊断，不自动替换。' if found else '表中未收录；只查当前接口及消费者，保留未验证项，不猜同名替代。'}


def markdown(catalog, profile=None):
    def cell(value):
        if isinstance(value, list): value = '；'.join(value)
        return str(value).replace('|', '\\|').replace('\n', ' ')
    lines = ['# RimWorld 1.7 接口兼容方案表', '', '由技能 compatibility-1.7.json 生成；唯一维护数据在技能源码中。', '',
             '静态基线：'+catalog['targetGameVersion']+'；历史运行报告：1.7.4976 rev1043。', '',
             '**这是查证与制作方向，不是自动替换表。所有条目尚无当前目标构建的游戏回归；查到后须读限制和测试条件。**', '',
             '| 编号 | 接口/症状 | 当前状态 | 制作/诊断方向 | 必测场景 |', '| --- | --- | --- | --- | --- |']
    for row in catalog['records']:
        if profile and profile not in row['profiles']: continue
        lines.append('| '+' | '.join(cell(row[key]) for key in ('id','symbol','observed','direction','tests'))+' |')
    lines += ['', '详细限制、证据哈希、适用类型与方案状态用技能 scripts/compatibility.py query --id <编号> 查询。',
              '依据失效接口的旧优化不默认迁移；独立有效功能可保留，针对 1.7 的新优化需要另行立项和测量。', '']
    return '\n'.join(lines)


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=DEFAULT_CATALOG)
    sub = parser.add_subparsers(dest='command', required=True)
    get = sub.add_parser('query')
    group = get.add_mutually_exclusive_group()
    group.add_argument('--query'); group.add_argument('--id')
    get.add_argument('--profile', choices=PROFILES)
    get.add_argument('--game-version'); get.add_argument('--fingerprints', type=Path)
    get.add_argument('--limit', type=int, default=3)
    table = sub.add_parser('table'); table.add_argument('--profile', choices=PROFILES)
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
        if args.command == 'table':
            print(markdown(catalog, args.profile))
            return 0
        fingerprints = None
        if args.fingerprints:
            fingerprints = json.loads(args.fingerprints.read_text(encoding='utf-8'))
            if not isinstance(fingerprints, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not re.fullmatch('[0-9a-fA-F]{64}', v) for k,v in fingerprints.items()):
                raise ValueError('fingerprints must map assembly names to SHA256 strings')
        result = query(catalog, args.query, args.id, args.profile, args.game_version, fingerprints, args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['matched'] else 1
    except (OSError, ValueError, KeyError, TypeError) as ex:
        print(json.dumps({'error': str(ex)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
