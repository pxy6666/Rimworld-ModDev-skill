"""Plan, publish, and resume a reviewed RimWorld release on Steam Workshop."""

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import time
from tempfile import NamedTemporaryFile, TemporaryDirectory
from xml.etree import ElementTree

from release_contract import ReleaseContractError, verify_release
from steam_backend import (APPID, DEFAULT_RUN_DIR, SteamworksError, SteamworksUGC, find_dylib,
                           parse_file_id, workshop_package_index)


VISIBILITY = {"public": 0, "friends-only": 1, "private": 2, "unlisted": 3}
WORKSHOP_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={}"
RELEASE_ERROR = (ReleaseContractError, OSError, ValueError, SteamworksError, ElementTree.ParseError)
# Steam rejects every uploaded preview/screenshot at this size (EResult 9/LimitExceeded).
IMAGE_BYTE_LIMIT = 1_000_000
DLC_NAMES = {
    "ludeon.rimworld": "RimWorld",
    "ludeon.rimworld.royalty": "RimWorld - Royalty",
    "ludeon.rimworld.ideology": "RimWorld - Ideology",
    "ludeon.rimworld.biotech": "RimWorld - Biotech",
    "ludeon.rimworld.anomaly": "RimWorld - Anomaly",
    "ludeon.rimworld.odyssey": "RimWorld - Odyssey",
}
# Steam store AppIDs of the DLC above; About.xml declares them by packageId.
DLC_APPS = {
    "ludeon.rimworld.royalty": 1149640,
    "ludeon.rimworld.ideology": 1392840,
    "ludeon.rimworld.biotech": 1826140,
    "ludeon.rimworld.anomaly": 2380740,
    "ludeon.rimworld.odyssey": 3022790,
}
# Steam accepts a dependency submit and reports OK even when its server drops the entries, so the
# step is judged by what the item holds afterwards.
DEPENDENCY_VERIFY_SECONDS = 60


class PublishError(ValueError):
    pass


class DependencyRejected(Exception):
    """Steam confirmed the submit but did not keep the dependencies."""

    def __init__(self, missing):
        names = [str(child) for child in missing["items"]] + [f"DLC {app}" for app in missing["apps"]]
        super().__init__("Steam did not keep the required dependencies: " + ", ".join(names))
        self.missing = missing


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, state):
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            json.dump(state, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + ".lock").open("a+b") as stream:
        if sys.platform == "win32":
            import msvcrt
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            acquire = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(stream, fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as error:
            raise PublishError("This journal is already in use.") from error
        try:
            yield
        finally:
            release()


def content_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def image_size(path):
    body = path.read_bytes()
    if body.startswith(b"\x89PNG\r\n\x1a\n") and len(body) >= 33 and body[8:16] == b"\0\0\0\rIHDR":
        return struct.unpack_from(">II", body, 16)
    if not body.startswith(b"\xff\xd8"):
        return None
    offset = 2
    while offset + 9 <= len(body) and body[offset] == 0xFF:
        while offset + 9 <= len(body) and body[offset + 1] == 0xFF:
            offset += 1
        marker = body[offset + 1]
        if marker in (0xD9, 0xDA):
            break
        length = int.from_bytes(body[offset + 2:offset + 4], "big")
        if length < 2 or offset + 2 + length > len(body):
            break
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC) and length >= 7:
            height, width = struct.unpack_from(">HH", body, offset + 5)
            return width, height
        offset += 2 + length
    return None


def compress_image(source, main, assets, label):
    """Re-encode this exact picture under the Workshop limit; never substitute different art."""
    try:
        from PIL import Image
    except ImportError as error:
        raise PublishError(f"{source.name} is over the 1 MB Workshop limit. Install Pillow "
                           f"(python -m pip install pillow) to compress it automatically, or supply "
                           f"a smaller PNG/JPEG.") from error
    with Image.open(source) as picture:
        picture.load()
        assets.mkdir(parents=True, exist_ok=True)
        alpha = picture.mode in ("RGBA", "LA", "PA") or "transparency" in picture.info
        width, height = picture.size
        ladder = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5]
        if main and min(width, height) > 0:
            # The main preview must stay at or above 512x512 at every step.
            floor = 512 / min(width, height)
            ladder = [scale for scale in ladder if scale >= floor] or [min(floor, 1.0)]
        # Steam silently drops some JPEG main previews; keep the main preview PNG. Screenshots
        # upload reliably as JPEG, which also compresses photographic content far below 1 MB.
        encodings = [("png", {})] if main else [("jpg", {"quality": 90, "optimize": True}),
                                                ("jpg", {"quality": 70, "optimize": True}),
                                                ("jpg", {"quality": 50, "optimize": True})]
        for scale in ladder:
            frame = picture if scale == 1.0 else picture.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)
            base = frame.convert("RGBA" if alpha else "RGB") if main else frame.convert("RGB")
            for suffix, options in encodings:
                candidate = assets / f"{label}.{suffix}"
                base.save(candidate, format="PNG" if suffix == "png" else "JPEG", **options)
                if candidate.stat().st_size < IMAGE_BYTE_LIMIT:
                    return {"path": str(candidate), "sha256": content_hash(candidate),
                            "compressedFrom": str(source), "sourceBytes": source.stat().st_size,
                            "bytes": candidate.stat().st_size}
            if main:
                # Last resort for a preview that resists lossless PNG: 256-color quantization.
                candidate = assets / f"{label}.png"
                base.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG).save(
                    candidate, format="PNG", optimize=True)
                if candidate.stat().st_size < IMAGE_BYTE_LIMIT:
                    return {"path": str(candidate), "sha256": content_hash(candidate),
                            "compressedFrom": str(source), "sourceBytes": source.stat().st_size,
                            "bytes": candidate.stat().st_size, "quantized": True}
    raise PublishError(f"{source.name} could not be compressed under 1 MB"
                       + (" while keeping 512x512" if main else "")
                       + f". Supply a smaller{' PNG preview' if main else ' image'}: {source}")


def record_image(path, main, assets=None, label="image"):
    path = path.resolve(strict=True)
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise PublishError(f"Choose a PNG or JPEG image: {path}")
    if path.stat().st_size >= IMAGE_BYTE_LIMIT:
        if assets is None:
            raise PublishError(f"Choose a PNG or JPEG image under 1 MB: {path}")
        record = compress_image(path, main, assets, label)
    else:
        record = {"path": str(path), "sha256": content_hash(path)}
    dimensions = image_size(Path(record["path"]))
    if not dimensions or min(dimensions) <= 0 or (main and min(dimensions) < 512):
        raise PublishError(f"Invalid image dimensions (main preview requires 512 by 512 or larger): {path}")
    return record


def page_text(field, value):
    limit = 128 if field == "title" else 8000
    if not isinstance(value, str) or "\0" in value or len(value.encode("utf-8")) >= limit:
        raise PublishError(f"{field} must fit in {limit - 1} UTF-8 bytes and contain no NUL.")
    if not value.strip():
        raise PublishError(f"{field} must contain text.")
    return value


def language_code(code):
    if not re.fullmatch(r"[a-z]{2,32}", code):
        raise PublishError("Use a Steam API language code such as english or schinese.")
    return code


def project_item(project, wanted_package):
    if project is None:
        return None
    about = project.resolve(strict=True) / "About"
    package = ElementTree.parse(about / "About.xml").findtext("packageId", "").strip()
    if package.casefold() != wanted_package.casefold():
        raise PublishError("Project packageId and verified release packageId differ.")
    marker = about / "PublishedFileId.txt"
    return parse_file_id(marker.read_text(encoding="utf-8-sig").strip()) if marker.exists() else None


def workshop_id_from_url(url):
    match = re.search(r"[?&]id=([0-9]{1,20})", url or "")
    return int(match.group(1)) if match else None


def release_requirements(release):
    """Collect the dependencies About.xml declares for every supported version, with Workshop links."""
    root = ElementTree.parse(release.content / "About" / "About.xml").getroot()
    versions = sorted(release.supported_versions, key=lambda version: tuple(map(int, version.split("."))))
    entries, seen = [], {}

    def add(package, name, url, required):
        key = package.casefold()
        if not package:
            return
        if key in seen:
            seen[key]["required"] = seen[key]["required"] or required
            return
        entry = {"packageId": package, "name": name or package,
                 "itemId": workshop_id_from_url(url), "dlc": key in DLC_NAMES, "required": required}
        seen[key] = entry
        entries.append(entry)

    def text(value):
        return (value or "").strip()

    def dependencies(items):
        for item in items:
            # 1.7 declares packageId/displayName; older About.xml files used modIdentifier/name.
            add(text(item.findtext("packageId") or item.findtext("modIdentifier")),
                 text(item.findtext("displayName") or item.findtext("name")),
                 text(item.findtext("steamWorkshopUrl")), True)

    def load_order(items):
        for item in items:
            # loadAfter lists bare packageIds.
            add(text(item.text or item.findtext("packageId")), text(item.findtext("displayName")), "", False)

    def effective(name):
        """Lists as each supported version sees them: a versioned list replaces the plain one."""
        node = root.find(name + "ByVersion")
        versioned = {} if node is None else {
            child.tag.lstrip("vV").casefold(): child.findall("li") for child in node}
        plain = root.findall(name + "/li")
        for index, version in enumerate(versions):
            items = versioned.get(version.casefold())
            if items is None and index:
                # ModMetaData falls back to the next lower supported version.
                items = versioned.get(versions[index - 1].casefold())
            yield plain if items is None else items

    for required_list, order_list in zip(effective("modDependencies"), effective("loadAfter")):
        dependencies(required_list)
        load_order(order_list)
    if any(entry["itemId"] is None and not entry["dlc"] for entry in entries):
        installed = workshop_package_index()
        for entry in entries:
            if entry["itemId"] is None and not entry["dlc"]:
                found = installed.get(entry["packageId"].casefold())
                if found:
                    entry["itemId"] = found[0]
                    if entry["name"] == entry["packageId"] and found[1]:
                        entry["name"] = found[1]
    return entries


def requirements_section(entries, language):
    """Render the About.xml dependencies as a BBCode block for one Steam language slot."""
    chinese = language in ("schinese", "tchinese")

    def line(entry):
        name = DLC_NAMES.get(entry["packageId"].casefold(), entry["name"]) if entry["dlc"] else entry["name"]
        text = f"[url={WORKSHOP_URL.format(entry['itemId'])}]{name}[/url]" if entry["itemId"] else name
        if entry["dlc"]:
            text += "（DLC）" if chinese else " (DLC)"
        elif not entry["itemId"]:
            text += f" ({entry['packageId']})"
        return f"[*]{text}"

    required = [entry for entry in entries if entry["required"]]
    ordered = [entry for entry in entries if not entry["required"]]
    blocks = []
    if required:
        blocks.append("[b]" + ("必需" if chinese else "Required") + "[/b]")
        blocks += ["[list]", *[line(entry) for entry in required], "[/list]"]
    if ordered:
        blocks.append("[b]" + ("加载顺序（非必需）" if chinese else "Load order (optional)") + "[/b]")
        blocks += ["[list]", *[line(entry) for entry in ordered], "[/list]"]
    return "\n".join(blocks)


def append_requirements(text, section):
    return text.rstrip() + "\n\n" + section if section else text


def plan(args):
    release = verify_release(args.content)
    journal = args.journal.resolve()
    if journal.is_relative_to(release.content):
        raise PublishError("Store the journal outside the verified release content.")
    ids = {value for value in (release.item_id, project_item(args.project, release.package_id), args.item_id)
           if value is not None}
    if len(ids) > 1:
        raise PublishError("The release, project or explicit Workshop item IDs disagree.")
    if args.create == bool(ids):
        raise PublishError("Choose --create for an unbound release, or provide its existing Workshop item ID.")
    if not args.acceptance.strip():
        raise PublishError("Record the acceptance scope or evidence for this release.")
    if args.create and (args.title is None or args.preview is None):
        raise PublishError("A new item requires an explicit title and main preview.")
    if not args.create and not args.changelog.strip():
        raise PublishError("An update requires a change note.")

    primary_language = "english" if args.language is None else language_code(args.language)
    requirements = release_requirements(release)
    assets = journal.parent / (journal.name + ".assets")
    fields = {}
    if args.title is not None:
        fields["title"] = page_text("title", args.title)
    description = page_text("description", args.description_file.read_text(encoding="utf-8-sig"))
    fields["description"] = page_text(
        "description", append_requirements(description, requirements_section(requirements, primary_language)))
    if args.language is not None:
        fields["language"] = primary_language
    if args.preview is not None:
        fields["preview"] = record_image(args.preview, main=True, assets=assets, label="preview")
    if args.visibility or args.create:
        fields["visibility"] = args.visibility or "private"
    if args.replace_screenshots is not None:
        if len(args.replace_screenshots) > 20:
            raise PublishError("Supply up to 20 replacement screenshots.")
        fields["screenshots"] = [record_image(path, main=False, assets=assets, label=f"screenshot-{index}")
                                 for index, path in enumerate(args.replace_screenshots)]
    if "\0" in args.changelog:
        raise PublishError("Change note must contain no NUL.")

    steps = [{"operation": "create", "state": "pending"}] if args.create else []
    steps.append({"operation": "content", "state": "pending", "fields": fields})
    languages = {primary_language}
    for spec in args.locale:
        code, separator, filename = spec.partition("=")
        if not separator or not filename:
            raise PublishError("Supply --locale as LANGUAGE=FILE.")
        code = language_code(code)
        if code in languages:
            raise PublishError("Plan at most one title/description update for each language.")
        languages.add(code)
        entry = read_json(Path(filename))
        if not isinstance(entry, dict) or entry.keys() != {"title", "description"}:
            # Steam keeps each language slot on its own, so a slot needs both.
            raise PublishError("A locale file must contain exactly a title and a description.")
        entry["description"] = append_requirements(entry["description"], requirements_section(requirements, code))
        translated = {key: page_text(key, value) for key, value in entry.items()}
        steps.append({"operation": "locale", "state": "pending", "fields": {"language": code, **translated}})
    required = [entry for entry in requirements if entry["required"]]
    items = [entry["itemId"] for entry in required if not entry["dlc"] and entry["itemId"]]
    apps = [DLC_APPS[entry["packageId"].casefold()] for entry in required if entry["packageId"].casefold() in DLC_APPS]
    unresolved = [{"packageId": entry["packageId"], "name": entry["name"]}
                  for entry in required if not entry["dlc"] and not entry["itemId"]]
    if items or apps:
        steps.append({"operation": "dependencies", "state": "pending", "items": items, "apps": apps})
    state = {
        "schema": 1, "appId": APPID, "packageId": release.package_id, "content": str(release.content),
        "contentDigest": release.digest, "acceptance": args.acceptance, "changelog": args.changelog,
        "itemId": next(iter(ids), None), "accountId": None, "needsAgreement": False,
        "project": str(args.project.resolve()) if args.project else None,
        "marker": "pending" if args.create else None,
        "requirements": {"entries": requirements, "items": items, "apps": apps, "unresolved": unresolved},
        "steps": steps,
    }
    with lock(journal):
        if journal.exists():
            raise PublishError("Journal already exists. Use status or upload to resume, or select a new path.")
        save(journal, state)
    return state


def load(journal):
    state = read_json(journal)
    if state.get("schema") != 1 or state.get("appId") != APPID:
        raise PublishError("Unrecognized RimWorld publish journal.")
    return state


def public_status(state):
    state = dict(state)
    incomplete = [{"item": step["operation"], "state": step["state"]}
                  for step in state["steps"] if step["state"] != "done"]
    if state.get("marker") == "pending":
        incomplete.append({"item": "marker", "state": "pending"})
    # Required mods without a Workshop ID cannot become Required Items by tool.
    incomplete += [{"item": "dependencies", "state": "unresolved", **entry}
                   for entry in state.get("requirements", {}).get("unresolved", [])]
    state["incomplete"] = incomplete
    state["complete"] = not incomplete
    if state["itemId"]:
        state["workshopUrl"] = WORKSHOP_URL.format(state["itemId"])
    return state


def prepare(state, directory):
    release = verify_release(Path(state["content"]), state["packageId"])
    if release.digest != state["contentDigest"]:
        raise PublishError("The release has changed since approval. Review and plan the new release.")
    content = None
    images = {}
    for step in state["steps"]:
        if step["state"] == "done" or step["operation"] != "content":
            continue
        content = directory / "artifact" / release.content.name
        shutil.copytree(release.content, content, symlinks=True)
        shutil.copyfile(release.manifest, content.parent / "manifest.json")
        receipt = read_json(release.receipt)
        receipt["directory"] = str(content)
        save(content.parent / "release-receipt.json", receipt)
        if verify_release(content, release.package_id).digest != state["contentDigest"]:
            raise PublishError("The verified release could not be materialized unchanged.")
        fields = step["fields"]
        assets = fields.get("screenshots", [])
        if "preview" in fields:
            assets = [fields["preview"], *assets]
        for index, asset in enumerate(assets):
            original = Path(asset["path"])
            copied = directory / ("page-" + str(index) + original.suffix)
            shutil.copyfile(original, copied)
            if content_hash(copied) != asset["sha256"]:
                raise PublishError(f"Page image has changed since approval: {original}")
            images[asset["path"]] = copied
    return content, images


def check_item(steam, item_id, account):
    details = steam.query_details(item_id)
    if (details.get("fileId") != item_id or details.get("consumerAppId") != APPID
            or details.get("ownerSteamId") != account):
        raise PublishError("The selected item must belong to the logged-in account and RimWorld.")
    return details


def stage_steam_update(steam, item_id, step, details, content, images):
    fields = step["fields"]
    handle = steam.start_update(item_id)
    if "language" in fields:
        steam.set_update_language(handle, fields["language"])
    if "title" in fields:
        steam.set_title(handle, fields["title"])
    if "description" in fields:
        steam.set_description(handle, fields["description"])
    if "visibility" in fields:
        steam.set_visibility(handle, VISIBILITY[fields["visibility"]])
    if "preview" in fields:
        steam.set_preview(handle, images[fields["preview"]["path"]])
    if "screenshots" in fields:
        previews = details["screenshots"]
        image_indices = sorted((preview["index"] for preview in previews if preview["type"] == 0), reverse=True)
        if len(previews) - len(image_indices) + len(fields["screenshots"]) > 20:
            raise PublishError("The new screenshots plus retained previews would exceed the gallery limit.")
        for index in image_indices:
            steam.remove_screenshot(handle, index)
        for entry in fields["screenshots"]:
            steam.add_screenshot(handle, images[entry["path"]])
    if step["operation"] == "content":
        steam.set_content(handle, content)
    return handle


def mutation(journal, state, step, perform):
    step["state"] = "in_flight"
    attempt = {"startedAt": datetime.now(timezone.utc).isoformat(), "state": "in_flight"}
    step.setdefault("attempts", []).append(attempt)
    save(journal, state)
    try:
        perform()
    except DependencyRejected as error:
        # Steam took the submit; a read-back shows it did not keep the change.
        step.update(state="failed", missing=error.missing)
        attempt.update(state="failed", error=str(error))
        save(journal, state)
    except SteamworksError as error:
        step["state"] = "unknown" if error.outcome_unknown else "pending"
        attempt.update(state=step["state"], error=str(error), resultCode=error.result_code)
        save(journal, state)
        raise
    else:
        step["state"] = "done"
        step.pop("missing", None)
        attempt["state"] = "done"
        save(journal, state)


def apply_dependencies(steam, item_id, step):
    """Write the Required Items and DLC dependencies Steam is missing, then confirm by read-back."""
    def missing():
        current = steam.query_dependencies(item_id)
        return {"items": [child for child in step["items"] if child not in current["items"]],
                "apps": [app for app in step["apps"] if app not in current["apps"]]}

    outstanding = missing()
    if outstanding["items"] or outstanding["apps"]:
        handle = steam.start_update(item_id)
        for child in outstanding["items"]:
            steam.add_dependency(handle, child)
        for app in outstanding["apps"]:
            steam.add_app_dependency(handle, app)
        steam.submit(handle, "")
        outstanding = missing()
    deadline = time.monotonic() + DEPENDENCY_VERIFY_SECONDS
    while outstanding["items"] or outstanding["apps"]:
        if time.monotonic() >= deadline:
            raise DependencyRejected(outstanding)
        time.sleep(5)
        outstanding = missing()


def run_steps(journal, state, steam, content, images, item_lock):
    if not steam.logged_on():
        raise PublishError("Sign in to the Windows Steam desktop client before uploading.")
    account = steam.steam_id()
    if not account or state["accountId"] not in (None, account):
        raise PublishError("Resume this journal on the same Steam account used before.")
    state["accountId"] = account
    save(journal, state)
    if state["itemId"]:
        item_lock(state["itemId"])
    for step in state["steps"]:
        if step["state"] == "done":
            continue
        if step["operation"] == "create":
            def create():
                item_id, agreement = steam.create_item()
                state["itemId"] = item_id
                state["needsAgreement"] = agreement
            mutation(journal, state, step, create)
            item_lock(state["itemId"])
            continue
        item_id = state["itemId"]
        details = check_item(steam, item_id, account)
        if step["operation"] == "dependencies":
            mutation(journal, state, step, lambda: apply_dependencies(steam, item_id, step))
            continue
        handle = stage_steam_update(steam, item_id, step, details, content, images)
        if "screenshots" in step["fields"] and check_item(steam, item_id, account)["screenshots"] != details["screenshots"]:
            raise PublishError("The Workshop gallery changed during preparation. Review it before retrying.")
        note = state["changelog"] if step["operation"] == "content" else ""

        def submit():
            result = steam.submit(handle, note)
            if result.get("fileId") != item_id:
                raise SteamworksError("Steam returned an unexpected item ID.", outcome_unknown=True)
            state["needsAgreement"] |= result["needsAccept"]
        mutation(journal, state, step, submit)


def upload(args, backend=SteamworksUGC):
    journal = args.journal.resolve()
    with lock(journal):
        state = load(journal)
        if any(step["state"] in {"unknown", "in_flight"} for step in state["steps"]):
            raise PublishError("Steam may have applied the previous step. Verify its outcome, then use resolve.")
        if all(step["state"] == "done" for step in state["steps"]):
            return public_status(state)
        sdk_path = find_dylib(args.sdk)
        if not sdk_path:
            raise PublishError("RimWorld Steamworks SDK was not found. Supply --sdk with its absolute path.")
        lock_dir = DEFAULT_RUN_DIR / "publish-locks"
        package_key = hashlib.sha256(state["packageId"].casefold().encode("utf-8")).hexdigest()
        with ExitStack() as stack:
            stack.enter_context(lock(lock_dir / ("package-" + package_key)))
            temporary = stack.enter_context(TemporaryDirectory(prefix="rimworld-workshop-", dir=journal.parent))
            content, images = prepare(state, Path(temporary))
            steam = stack.enter_context(backend(sdk_path.resolve(), DEFAULT_RUN_DIR, timeout=args.timeout))
            # Steam init changes the process working directory.
            run_steps(journal, state, steam, content, images,
                      lambda item: stack.enter_context(lock(lock_dir / ("item-" + str(item)))))
    return public_status(state)


def resolve(args):
    with lock(args.journal):
        state = load(args.journal)
        step = next((entry for entry in state["steps"] if entry["state"] in {"in_flight", "unknown"}), None)
        if step is None:
            raise PublishError("This journal has no operation awaiting resolution.")
        if not args.evidence.strip():
            raise PublishError("Record authoritative evidence for the outcome.")
        recovered_creation = step["operation"] == "create" and args.outcome == "completed"
        if recovered_creation != bool(args.item_id):
            raise PublishError("An item ID is required only to recover a confirmed successful creation.")
        if recovered_creation:
            state["itemId"] = args.item_id
        step["state"] = "done" if args.outcome == "completed" else "pending"
        step.setdefault("resolutions", []).append({
            "resolvedAt": datetime.now(timezone.utc).isoformat(), "outcome": args.outcome,
            "evidence": args.evidence, "itemId": args.item_id,
        })
        save(args.journal, state)
    return public_status(state)


def bind(args):
    """Record a newly created item in the project, as the game's uploader does after a first upload."""
    with lock(args.journal):
        state = load(args.journal)
        if state.get("marker") == "written":
            return public_status(state)
        created = state.get("marker") == "pending" and state["itemId"] and any(
            step["operation"] == "create" and step["state"] == "done" for step in state["steps"])
        if not created:
            raise PublishError("Bind only after the creation step of a --create plan has succeeded.")
        project = args.project or (Path(state["project"]) if state.get("project") else None)
        if project is None:
            raise PublishError("Supply --project with the mod project root.")
        project = project.expanduser().resolve(strict=True)
        existing = project_item(project, state["packageId"])
        if existing not in (None, state["itemId"]):
            raise PublishError(
                f"The project is already bound to Workshop item {existing}; not overwriting it.")
        if existing is None:
            (project / "About" / "PublishedFileId.txt").write_text(str(state["itemId"]), encoding="ascii")
        state["marker"] = "written"
        save(args.journal, state)
    return public_status(state)


def inspect(args, backend=SteamworksUGC):
    """Read what Steam holds for one item, page languages included; nothing is changed."""
    sdk_path = find_dylib(args.sdk)
    if not sdk_path:
        raise PublishError("RimWorld Steamworks SDK was not found. Supply --sdk with its absolute path.")
    with backend(sdk_path.resolve(), DEFAULT_RUN_DIR, timeout=args.timeout) as steam:
        if not steam.logged_on():
            raise PublishError("Sign in to the Steam desktop client before reading the Workshop item.")
        account = steam.steam_id()
        details = steam.query_details(args.item_id)
        if details.get("fileId") != args.item_id or details.get("consumerAppId") != APPID:
            raise PublishError("Select an existing RimWorld Workshop item.")
        pages = {language_code(language): steam.query_details(args.item_id, language)
                 for language in args.language or ["english"]}
        dependencies = steam.query_dependencies(args.item_id)
    visibility = {value: name for name, value in VISIBILITY.items()}
    return {"itemId": args.item_id, "workshopUrl": WORKSHOP_URL.format(args.item_id),
            "owned": details.get("ownerSteamId") == account,
            "visibility": visibility.get(details["visibility"], details["visibility"]),
            "previewUrl": details["previewUrl"],
            "screenshots": [entry["url"] for entry in details["screenshots"] if entry["type"] == 0],
            "dependencies": dependencies,
            "pages": {language: {"title": page["title"], "description": page["description"]}
                      for language, page in pages.items()}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "upload", "status", "resolve", "bind", "inspect"):
        command = commands.add_parser(name)
        if name in ("plan", "bind"):
            command.add_argument("--project", type=Path)
        if name in ("upload", "inspect"):
            command.add_argument("--sdk", type=Path)
            command.add_argument("--timeout", type=int, default=600)
        if name != "inspect":
            command.add_argument("--journal", required=True, type=Path)
        if name == "plan":
            command.add_argument("--content", required=True, type=Path)
            command.add_argument("--acceptance", required=True)
            mode = command.add_mutually_exclusive_group()
            mode.add_argument("--create", action="store_true")
            mode.add_argument("--item-id", type=parse_file_id)
            command.add_argument("--title")
            command.add_argument("--description-file", required=True, type=Path)
            command.add_argument("--preview", type=Path)
            command.add_argument("--visibility", choices=VISIBILITY)
            command.add_argument("--language")
            command.add_argument("--changelog", default="")
            command.add_argument("--locale", action="append", default=[])
            command.add_argument("--replace-screenshots", nargs="*", type=Path)
        if name == "inspect":
            command.add_argument("--item-id", required=True, type=parse_file_id)
            command.add_argument("--language", action="append")
        if name == "resolve":
            command.add_argument("--outcome", required=True, choices=("completed", "failed"))
            command.add_argument("--evidence", required=True)
            command.add_argument("--item-id", type=parse_file_id)
    args = parser.parse_args(argv)
    try:
        if args.command in ("upload", "inspect") and args.timeout <= 0:
            raise PublishError("--timeout must be positive.")
        if args.command == "plan":
            result = public_status(plan(args))
        elif args.command == "upload":
            result = upload(args)
        elif args.command == "status":
            result = public_status(load(args.journal))
        elif args.command == "bind":
            result = bind(args)
        elif args.command == "inspect":
            result = inspect(args)
        else:
            result = resolve(args)
    except RELEASE_ERROR as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
