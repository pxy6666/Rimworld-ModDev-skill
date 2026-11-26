"""Verify a local package stage before handing its content to a publisher."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import xml.etree.ElementTree as ET


class ReleaseContractError(ValueError):
    """The selected folder cannot be established as a valid package stage."""


@dataclass(frozen=True)
class VerifiedRelease:
    content: Path
    package_id: str
    digest: str
    item_id: int | None
    receipt: Path
    manifest: Path
    supported_versions: tuple[str, ...]
    file_count: int


_PACKAGE_ID = re.compile(r'(?=.{1,60}\Z)[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)+\Z')
_VERSION = re.compile(r'[0-9]+\.[0-9]+\Z')
_HASH = re.compile(r'[0-9a-fA-F]{64}\Z')
_DEVICE = re.compile(r'(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[1-9¹²³])\Z', re.I)
_ITEM_MARKER = 'about/publishedfileid.txt'
_REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)


def _require(condition, message):
    if not condition:
        raise ReleaseContractError(message)


def _object(value, description):
    _require(isinstance(value, dict), f'{description} must be a JSON object.')
    return value


def _hash(value, description):
    _require(isinstance(value, str) and _HASH.fullmatch(value), f'Missing or invalid SHA256 for {description}.')
    return value.lower()


def _relative(value):
    # Validate using Windows rules on every host, before any path is joined.
    _require(isinstance(value, str) and value, 'Manifest/receipt paths must be nonempty strings.')
    for part in value.split('/'):
        _require(bool(part) and part not in ('.', '..') and part == part.rstrip(' .')
                 and not any(ch in '<>:"\\|?*' or ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF for ch in part)
                 and not _DEVICE.fullmatch(part.split('.', 1)[0].rstrip(' ')),
                 f'Unsafe staged relative path: {value!r}.')
    return value


def _kind(path):
    info = path.lstat()
    _require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & _REPARSE),
             f'Link or reparse point in release path: {path}.')
    if stat.S_ISDIR(info.st_mode):
        return 'directory'
    _require(stat.S_ISREG(info.st_mode), f'Nonregular file in release path: {path}.')
    _require(info.st_nlink <= 1, f'Hard link in release path: {path}.')
    return 'file'


def _directory(path):
    # Do not resolve first: that would strip away evidence of junctions or symlinks.
    path = Path(os.path.abspath(path))
    for component in (*reversed(path.parents), path):
        _require(_kind(component) == 'directory', f'Expected a release directory: {component}.')
    return path.resolve(strict=True)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f'Duplicate JSON key in package evidence: {key!r}.')
        result[key] = value
    return result


def _json(path):
    _require(_kind(path) == 'file', f'Expected a package evidence file: {path}.')
    return _object(json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique_pairs), path.name)


def _file_tree(content):
    files = {}
    folded = set()
    stack = [content]
    while stack:
        parent = stack.pop()
        children = list(parent.iterdir())
        _require(children, f'Empty folder cannot be accounted for by the package manifest: {parent}.')
        for child in children:
            rel = _relative(child.relative_to(content).as_posix())
            key = rel.casefold()
            _require(key not in folded, f'Windows case collision in the staged payload: {rel!r}.')
            folded.add(key)
            if _kind(child) == 'directory':
                _require(key != _ITEM_MARKER, 'PublishedFileId.txt must be a file.')
                stack.append(child)
            else:
                files[rel] = child
    return files


def _file_hash(path):
    _require(_kind(path) == 'file', f'Staged file was replaced: {path}.')
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _identity(files, manifest):
    about = files.get('About/About.xml')
    _require(about, 'Package stage is missing About/About.xml.')
    raw = about.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == manifest['About/About.xml'], 'About.xml changed while verifying.')
    root = ET.fromstring(raw)
    ids = root.findall('packageId')
    _require(root.tag == 'ModMetaData' and len(ids) == 1 and not len(ids[0]), 'Expected one packageId in About.xml ModMetaData.')
    package_id = (ids[0].text or '').strip()
    _require(_PACKAGE_ID.fullmatch(package_id), f'Invalid About.xml packageId: {package_id!r}.')
    declarations = root.findall('supportedVersions')
    _require(len(declarations) == 1, 'Expected one supportedVersions list in About.xml.')
    versions = tuple((tag.text or '').strip() for tag in declarations[0].findall('li'))
    _require(versions and all(_VERSION.fullmatch(v) for v in versions) and len(set(versions)) == len(versions),
             'About.xml must declare unique numeric supported versions.')
    return package_id, versions


def _local_item_id(files, manifest):
    rel = next((path for path in files if path.casefold() == _ITEM_MARKER), None)
    if rel is None:
        return None
    with files[rel].open('rb') as stream:
        data = stream.read(128)
        _require(not stream.read(1), 'PublishedFileId.txt has unexpected extra content.')
    _require(hashlib.sha256(data).hexdigest() == manifest[rel], 'PublishedFileId.txt changed while verifying.')
    value = data.decode('utf-8-sig').strip()
    _require(re.fullmatch(r'[0-9]{1,20}', value) and 0 < int(value) <= 2**64 - 1,
             'PublishedFileId.txt must contain one positive Steam item ID.')
    return int(value)


def _check_evidence(receipt, versions, package_id, manifest):
    _require(receipt.get('command') == 'package' and receipt.get('passed') is True,
             'Package receipt does not record successful packaging.')
    evidence = _object(receipt.get('evidence'), 'Package evidence')
    _require(evidence.get('published') is False and all(type(evidence.get(key)) is bool for key in ('loadTested', 'runtimeTested')),
             'Package receipt must record pre-publish evidence and explicit test states.')
    validation = _object(receipt.get('validation'), 'Package validation')
    _require(validation.get('command') == 'check' and validation.get('delivery') == 'release'
             and validation.get('passed') is True and validation.get('errors') == [],
             'Package receipt does not contain a successful release check.')
    artifacts = _object(receipt.get('targetArtifacts'), 'Target artifact evidence')
    audits = _object(receipt.get('targetContent'), 'Target content evidence')
    _require(set(artifacts) == set(audits) == set(versions),
             'Package target artifact and content evidence must cover every supported version exactly.')

    verified_dlls = set()
    compiled_paths = set()
    for version in versions:
        artifact = _object(artifacts[version], f'Target {version} artifact evidence')
        _require('compiled' in artifact and 'adopted' in artifact, f'Missing DLL evidence sections for {version}.')
        compiled = artifact['compiled']
        if compiled is not None:
            compiled = _object(compiled, f'Target {version} compiled receipt')
            config = _object(compiled.get('configInputs'), 'Compiled receipt configuration')
            build_evidence = _object(compiled.get('evidence'), 'Compilation evidence')
            name = compiled.get('output')
            _require(compiled.get('schema') in (1, 2) and compiled.get('target', config.get('version')) == version
                     and config.get('version') == version and build_evidence.get('compiled') is True
                     and isinstance(name, str) and PureWindowsPath(name).suffix.lower() == '.dll',
                     f'Invalid compiled DLL receipt for {version}.')
            rel = _relative(f'{version}/Assemblies/{PureWindowsPath(name).name}')
            _require(manifest.get(rel) == _hash(compiled.get('sha256'), rel), f'Compiled DLL does not match stage for {version}: {rel}.')
            compiled_paths.add(rel)
            verified_dlls.add(rel)
        for rel, entry in _object(artifact['adopted'], f'Target {version} adopted artifacts').items():
            _relative(rel)
            entry = _object(entry, f'Adopted artifact {rel}')
            _require(rel.lower().endswith('.dll') and entry.get('path') == rel and entry.get('reviewed') is True
                     and isinstance(entry.get('origin'), str) and bool(entry['origin'].strip()), f'Invalid adopted DLL record: {rel}.')
            _require(manifest.get(rel) == _hash(entry.get('sha256'), rel), f'Adopted DLL does not match stage: {rel}.')
            verified_dlls.add(rel)

    _require({p for p in manifest if p.lower().endswith('.dll')} == verified_dlls,
             'Staged DLLs do not match compiled/adopted artifact evidence.')
    for version in versions:
        audit = _object(audits[version], f'Target {version} content audit')
        audit_evidence = _object(audit.get('evidence'), 'Content audit evidence')
        _require(audit.get('schema') == 1 and audit.get('target') == version and audit.get('errors') == []
                 and isinstance(audit.get('packageId'), str) and audit['packageId'].strip().casefold() == package_id.casefold()
                 and audit_evidence.get('staticDiskOnly') is True and audit_evidence.get('gameLoaded') is False
                 and audit_evidence.get('patchExecution') is False and isinstance(audit.get('files'), list),
                 f'Invalid static content audit for {version}.')
        for item in audit['files']:
            item = _object(item, 'Target audit file')
            rel = _relative(item.get('path'))
            recorded = _hash(item.get('sha256'), rel)
            # Package may replace an older on-disk DLL with the exact compiled DLL
            # already independently bound above. Other audited files must match.
            _require(rel in manifest and (manifest[rel] == recorded or rel in compiled_paths),
                     f'Target content audit file no longer matches the stage for {version}: {rel}.')
    selected = _object(validation.get('contentLoad'), 'Release check content audit')
    target = selected.get('target')
    _require(isinstance(target, str) and target in audits and selected == audits[target],
             'Release validation is not bound to its selected target content audit.')
    _require('compiledReceipt' in receipt and receipt['compiledReceipt'] == artifacts[target]['compiled'],
             'Release receipt selected DLL evidence does not match its target.')


def verify_release(content: Path, expected_package_id: str | None = None) -> VerifiedRelease:
    """Verify a link-free exact stage offline; the tree digest is independent of its absolute path."""
    try:
        content = _directory(content)
        receipt_path = content.parent / 'release-receipt.json'
        manifest_path = content.parent / 'manifest.json'
        receipt = _json(receipt_path)
        selected = receipt.get('directory')
        _require(isinstance(selected, str) and Path(selected).is_absolute() and Path(os.path.abspath(selected)) == content,
                 'The sibling package receipt points to a different stage directory.')
        _hash(receipt.get('sha256'), 'package ZIP receipt')  # Do not read or depend on the sibling ZIP.
        manifest = {_relative(rel): _hash(sha, rel) for rel, sha in _json(manifest_path).items()}
        _require(type(receipt.get('files')) is int and receipt['files'] == len(manifest), 'Receipt and manifest file counts differ.')
        files = _file_tree(content)
        _require(set(files) == set(manifest),
                 f'Staged file set differs from manifest (missing: {sorted(set(manifest) - set(files))[:5]}; extra: {sorted(set(files) - set(manifest))[:5]}).')
        for rel, path in files.items():
            _require(_file_hash(path) == manifest[rel], f'Staged file SHA256 differs from manifest: {rel}.')
        package_id, versions = _identity(files, manifest)
        if expected_package_id is not None:
            _require(isinstance(expected_package_id, str) and expected_package_id.casefold() == package_id.casefold(),
                     f'Package ID differs from the expected identity: {package_id!r}.')
        _check_evidence(receipt, versions, package_id, manifest)
        item_id = _local_item_id(files, manifest)
        tree = json.dumps(sorted(manifest.items()), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        return VerifiedRelease(content, package_id, hashlib.sha256(tree).hexdigest(), item_id,
                               receipt_path, manifest_path, versions, len(files))
    except ReleaseContractError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, ET.ParseError) as exc:
        raise ReleaseContractError(f'Cannot verify package stage: {exc}') from exc
