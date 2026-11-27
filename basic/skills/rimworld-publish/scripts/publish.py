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
from tempfile import NamedTemporaryFile, TemporaryDirectory, mkdtemp
from xml.etree import ElementTree

from release_contract import ReleaseContractError, verify_release
from steam_backend import APPID, DEFAULT_RUN_DIR, SteamworksError, SteamworksUGC, find_dylib, parse_file_id
from workshop_requirements import WORKSHOP_URL, release_requirements, requirements_section


VISIBILITY = {"public": 0, "friends-only": 1, "private": 2, "unlisted": 3}
RELEASE_ERROR = (ReleaseContractError, OSError, ValueError, SteamworksError, ElementTree.ParseError)
IMAGE_BYTE_LIMIT = 1_000_000
DEPENDENCY_VERIFY_SECONDS = 30


class PublishError(ValueError):
    pass


class DependenciesMissing(SteamworksError):
    def __init__(self, missing):
        super().__init__("Steam acknowledged the dependency calls, but some entries are absent on read-back.")
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


def check_image(path, main):
    dimensions = image_size(path)
    if not dimensions or min(dimensions) <= 0 or (main and min(dimensions) < 512):
        raise PublishError(f"Invalid image dimensions (main preview requires 512 by 512 or larger): {path}")


def compress_image(source, main, assets, label, source_bytes):
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise PublishError(f"{source.name} exceeds the 1 MB limit. Install Pillow or select a smaller image.") from error
    try:
        with Image.open(source, formats=("PNG", "JPEG")) as original:
            picture = ImageOps.exif_transpose(original)
    except Image.DecompressionBombError as error:
        raise PublishError(f"Choose a smaller image: {source}") from error
    with picture:
        width, height = picture.size
        shortest = min(width, height)
        if main and shortest < 512:
            raise PublishError(f"The main preview requires 512 by 512 or larger: {source}")
        alpha = "A" in picture.getbands() or "transparency" in picture.info
        picture = picture.convert("RGBA" if alpha else "RGB")
        as_png = main or alpha
        output = assets / (label + (".png" if as_png else ".jpg"))
        floor = 512 / shortest if main else 0
        scales = sorted({max(floor, scale) for scale in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.35, 0.25)},
                        reverse=True)
        for quantized in ((False, True) if as_png else (False,)):
            for scale in scales:
                dimensions = (max(1, round(width * scale)), max(1, round(height * scale)))
                frame = picture if scale == 1 else picture.resize(dimensions, Image.Resampling.LANCZOS)
                if as_png:
                    if quantized:
                        method = Image.Quantize.FASTOCTREE if alpha else Image.Quantize.MEDIANCUT
                        frame = frame.quantize(colors=256, method=method)
                    frame.save(output, optimize=True)
                else:
                    for quality in (90, 70, 50):
                        frame.save(output, quality=quality, optimize=True)
                        if output.stat().st_size < IMAGE_BYTE_LIMIT:
                            break
                length = output.stat().st_size
                if length < IMAGE_BYTE_LIMIT:
                    check_image(output, main)
                    return {"path": str(output), "sha256": content_hash(output), "compressedFrom": str(source),
                            "sourceBytes": source_bytes, "bytes": length, "quantized": quantized}
    raise PublishError(f"Could not compress under 1 MB. Select a smaller image: {source}")


def plan_images(args, journal, fields, cleanup):
    paths = {}
    if args.preview is not None:
        paths["preview"] = args.preview
    if args.replace_screenshots is not None:
        if len(args.replace_screenshots) > 20:
            raise PublishError("Supply up to 20 replacement screenshots.")
        paths.update({f"screenshot-{index}": path for index, path in enumerate(args.replace_screenshots)})
    assets = None
    prepared = {}
    for label, path in paths.items():
        source = path.resolve(strict=True)
        if source.suffix.lower() not in {".png", ".jpg", ".jpeg"} or not source.is_file():
            raise PublishError(f"Choose a PNG or JPEG image: {source}")
        main = label == "preview"
        length = source.stat().st_size
        if length < IMAGE_BYTE_LIMIT:
            check_image(source, main)
            prepared[label] = {"path": str(source), "sha256": content_hash(source)}
            continue
        if assets is None:
            assets = Path(mkdtemp(prefix="workshop-assets-", dir=journal.parent))
            cleanup.callback(shutil.rmtree, assets)
        prepared[label] = compress_image(source, main, assets, label, length)
    if args.preview is not None:
        fields["preview"] = prepared.pop("preview")
    if args.replace_screenshots is not None:
        fields["screenshots"] = list(prepared.values())


def page_text(field, value):
    limit = 128 if field == "title" else 8000
    if not isinstance(value, str) or "\0" in value or len(value.encode("utf-8")) >= limit:
        raise PublishError(f"{field} must fit in {limit - 1} UTF-8 bytes and contain no NUL.")
    if field == "title" and not value.strip():
        raise PublishError("Title must contain text.")
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

    fields = {}
    if args.title is not None:
        fields["title"] = page_text("title", args.title)
    if args.description_file is not None:
        fields["description"] = page_text("description", args.description_file.read_text(encoding="utf-8-sig"))
    if args.language is not None:
        if not fields:
            raise PublishError("--language requires a title or description update.")
        fields["language"] = language_code(args.language)
    primary_language = fields.get("language", "english") if fields else None
    if args.visibility or args.create:
        fields["visibility"] = args.visibility or "private"
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
        if not isinstance(entry, dict) or not entry or entry.keys() - {"title", "description"}:
            raise PublishError("A locale file must contain title and/or description only.")
        translated = {key: page_text(key, value) for key, value in entry.items()}
        steps.append({"operation": "locale", "state": "pending", "fields": {"language": code, **translated}})
    state = {
        "schema": 1, "appId": APPID, "packageId": release.package_id, "content": str(release.content),
        "contentDigest": release.digest, "acceptance": args.acceptance, "changelog": args.changelog,
        "itemId": next(iter(ids), None), "accountId": None, "needsAgreement": False, "steps": steps
    }
    if args.create and args.project is not None:
        state["sourceProject"] = str(args.project.resolve(strict=True))
    append = getattr(args, "append_requirements", False)
    add = getattr(args, "add_dependencies", False)
    if append or add:
        plan_requirements(release, state, append=append, add=add)
    with lock(journal), ExitStack() as cleanup:
        if journal.exists():
            raise PublishError("Journal already exists. Use status or upload to resume, or select a new path.")
        plan_images(args, journal, fields, cleanup)
        save(journal, state)
        cleanup.pop_all()
    return state


def plan_requirements(release, state, *, append, add):
    descriptions = [step["fields"] for step in state["steps"] if "description" in step.get("fields", {})]
    if append and not descriptions:
        raise PublishError("--append-requirements needs an explicitly selected description.")
    entries = release_requirements(release)
    state["requirements"] = entries
    if append:
        for fields in descriptions:
            section = requirements_section(entries, fields.get("language", "english"))
            description = fields["description"].rstrip()
            if section and not description.endswith(section):
                fields["description"] = page_text("description", f"{description}\n\n{section}".lstrip())
    if add:
        items = sorted({entry["itemId"] for entry in entries if entry["required"] and entry["itemId"]})
        apps = sorted({entry["appId"] for entry in entries if entry["required"] and entry["appId"]})
        required = [entry for entry in entries if entry["required"]]
        if state["itemId"] in items or any(entry["packageId"].casefold() == release.package_id.casefold()
                                           for entry in required):
            raise PublishError("The release declares the selected Workshop item as its own dependency.")
        state["unresolvedRequired"] = [entry["packageId"] for entry in required
                                       if not (entry["itemId"] or entry["official"])]
        if items or apps:
            state["steps"].append({"operation": "dependencies", "state": "pending", "items": items, "apps": apps})


def load(journal):
    state = read_json(journal)
    if state.get("schema") != 1 or state.get("appId") != APPID:
        raise PublishError("Unrecognized RimWorld publish journal.")
    return state


def public_status(state):
    state = dict(state)
    state["complete"] = all(step["state"] == "done" for step in state["steps"])
    if "unresolvedRequired" in state:
        state["dependenciesComplete"] = not state["unresolvedRequired"] and all(
            step["state"] == "done" for step in state["steps"] if step["operation"] == "dependencies")
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
    step.pop("missing", None)
    attempt = {"startedAt": datetime.now(timezone.utc).isoformat(), "state": "in_flight"}
    step.setdefault("attempts", []).append(attempt)
    save(journal, state)
    try:
        perform()
    except SteamworksError as error:
        step["state"] = "unknown" if error.outcome_unknown else "pending"
        if isinstance(error, DependenciesMissing):
            step["missing"] = error.missing
        attempt.update(state=step["state"], error=str(error), resultCode=error.result_code)
        save(journal, state)
        raise
    step["state"] = "done"
    step.pop("missing", None)
    attempt["state"] = "done"
    save(journal, state)


def missing_dependencies(steam, item_id, step):
    current = steam.query_dependencies(item_id)
    return {key: sorted(set(step[key]) - set(current[key])) for key in ("items", "apps")}


def add_dependencies(steam, item_id, missing, step):
    if item_id in missing["items"]:
        raise SteamworksError("The created item cannot be added as its own dependency.")
    for item in missing["items"]:
        steam.add_dependency(item_id, item)
    for app in missing["apps"]:
        steam.add_app_dependency(item_id, app)
    deadline = time.monotonic() + DEPENDENCY_VERIFY_SECONDS
    while True:
        try:
            outstanding = missing_dependencies(steam, item_id, step)
        except SteamworksError as error:
            raise SteamworksError(f"Could not verify dependencies after writing: {error}",
                                  result_code=error.result_code, outcome_unknown=True) from error
        if not any(outstanding.values()):
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DependenciesMissing(outstanding)
        time.sleep(min(2, remaining))


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
            missing = missing_dependencies(steam, item_id, step)
            if any(missing.values()):
                mutation(journal, state, step, lambda: add_dependencies(steam, item_id, missing, step))
            else:
                step["state"] = "done"
                step.pop("missing", None)
                save(journal, state)
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
        if step["state"] == "done":
            step.pop("missing", None)
        step.setdefault("resolutions", []).append({
            "resolvedAt": datetime.now(timezone.utc).isoformat(), "outcome": args.outcome,
            "evidence": args.evidence, "itemId": args.item_id,
        })
        save(args.journal, state)
    return public_status(state)


def bind(args):
    journal = args.journal.resolve()
    with lock(journal):
        state = load(journal)
        if (not state["itemId"] or not any(step["operation"] == "create" for step in state["steps"])
                or any(step["state"] != "done" for step in state["steps"])):
            raise PublishError("Bind only after a --create plan has finished uploading.")
        recorded = state.get("boundProject") or state.get("sourceProject")
        selected = args.project or (Path(recorded) if recorded else None)
        if selected is None:
            raise PublishError("Supply --project with the source mod project root.")
        project = selected.resolve(strict=True)
        if recorded and project != Path(recorded):
            raise PublishError("Select the source project recorded by the journal.")
        # An immutable release receipt would be invalidated by writing a marker into its content.
        if project.is_relative_to(Path(state["content"])):
            raise PublishError("Bind the source project, outside the verified release directory.")
        about = project / "About"
        marker = about / "PublishedFileId.txt"
        if about.resolve(strict=True) != about or marker.is_symlink():
            raise PublishError("Bind requires a project-local About directory and marker.")
        expected = state["itemId"]
        existing = project_item(project, state["packageId"])
        if existing is None:
            try:
                with marker.open("x", encoding="ascii") as output:
                    output.write(f"{expected}\n")
            except FileExistsError:
                existing = project_item(project, state["packageId"])
                if existing is None:
                    raise
        if existing not in (None, expected):
            raise PublishError(f"The project is already bound to Workshop item {existing}.")
        state["boundProject"] = str(project)
        save(journal, state)
    return public_status(state)


def inspect(args, backend=SteamworksUGC):
    languages = dict.fromkeys(language_code(value) for value in args.language or ["english"])
    sdk = find_dylib(args.sdk)
    if not sdk:
        raise PublishError("RimWorld Steamworks SDK was not found. Supply --sdk with its absolute path.")
    with backend(sdk.resolve(), DEFAULT_RUN_DIR, timeout=args.timeout) as steam:
        if not steam.logged_on():
            raise PublishError("Sign in to the Steam desktop client before reading the Workshop item.")
        pages = {}
        for language in languages:
            details = steam.query_details(args.item_id, language)
            if details["fileId"] != args.item_id or details["consumerAppId"] != APPID:
                raise PublishError("Select an existing RimWorld Workshop item.")
            pages[language] = {"title": details["title"], "description": details["description"]}
        visibility = {number: name for name, number in VISIBILITY.items()}
        result = {
            "itemId": args.item_id, "workshopUrl": WORKSHOP_URL.format(args.item_id),
            "owned": details["ownerSteamId"] == steam.steam_id(),
            "visibility": visibility.get(details["visibility"], details["visibility"]),
            "previewUrl": details["previewUrl"], "pages": pages,
            "screenshots": [entry["url"] for entry in details["screenshots"] if entry["type"] == 0],
        }
        try:
            result["dependencies"] = steam.query_dependencies(args.item_id)
        except SteamworksError as error:
            result["dependenciesError"] = str(error)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "upload", "status", "resolve", "bind", "inspect"):
        command = commands.add_parser(name)
        if name != "inspect":
            command.add_argument("--journal", required=True, type=Path)
        if name in ("plan", "bind"):
            command.add_argument("--project", type=Path)
        if name == "plan":
            command.add_argument("--content", required=True, type=Path)
            command.add_argument("--acceptance", required=True)
            mode = command.add_mutually_exclusive_group()
            mode.add_argument("--create", action="store_true")
            mode.add_argument("--item-id", type=parse_file_id)
            command.add_argument("--title")
            command.add_argument("--description-file", type=Path)
            command.add_argument("--preview", type=Path)
            command.add_argument("--visibility", choices=VISIBILITY)
            command.add_argument("--language")
            command.add_argument("--changelog", default="")
            command.add_argument("--locale", action="append", default=[])
            command.add_argument("--replace-screenshots", nargs="*", type=Path)
            command.add_argument("--append-requirements", action="store_true",
                                 help="Append verified About.xml requirements to explicitly selected descriptions.")
            command.add_argument("--add-dependencies", action="store_true",
                                 help="Add resolvable hard Workshop and DLC dependencies after content upload.")
        if name in ("upload", "inspect"):
            command.add_argument("--sdk", type=Path)
            command.add_argument("--timeout", type=int, default=600)
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
