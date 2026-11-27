"""Read the verified release's About.xml for an explicitly selected page update."""

import platform
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree

from steam_backend import APPID, _steam_library_roots, parse_file_id


WORKSHOP_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={}"
DLC = {
    "ludeon.rimworld": ("RimWorld", None),
    "ludeon.rimworld.royalty": ("RimWorld - Royalty", 1149640),
    "ludeon.rimworld.ideology": ("RimWorld - Ideology", 1392840),
    "ludeon.rimworld.biotech": ("RimWorld - Biotech", 1826140),
    "ludeon.rimworld.anomaly": ("RimWorld - Anomaly", 2380740),
    "ludeon.rimworld.odyssey": ("RimWorld - Odyssey", 3022790),
}


def workshop_id_from_url(url):
    try:
        parts = urlsplit(url)
        if (parts.scheme not in {"http", "https"} or parts.netloc.casefold() != "steamcommunity.com"
                or parts.path.rstrip("/") not in {"/sharedfiles/filedetails", "/workshop/filedetails"}):
            return None
        ids = parse_qs(parts.query).get("id", [])
        return parse_file_id(ids[0]) if len(ids) == 1 else None
    except ValueError:
        return None


def workshop_package_index(wanted):
    """Find unambiguous packageId matches in locally installed Workshop content."""
    matches = {key: {} for key in wanted}
    for library in _steam_library_roots(platform.system()):
        content = library / "steamapps" / "workshop" / "content" / str(APPID)
        try:
            items = list(content.iterdir())
        except OSError:
            continue
        for item in items:
            try:
                item_id = parse_file_id(item.name)
                about = ElementTree.parse(item / "About" / "About.xml")
            except (OSError, ValueError, ElementTree.ParseError):
                continue
            package = about.findtext("packageId", "").strip().casefold()
            if package in matches:
                matches[package][item_id] = about.findtext("name", "").strip()
    return {key: next(iter(found.items())) for key, found in matches.items() if len(found) == 1}


def version_key(version):
    return tuple(map(int, version.split(".")))


def effective_lists(root, name, versions):
    plain = root.findall(name + "/li")
    versioned = {child.tag.lstrip("vV"): child.findall("li") for child in root.findall(name + "ByVersion/*")}
    for index, version in enumerate(versions):
        previous = versions[index - 1] if index else None
        yield versioned.get(version, versioned.get(previous, plain))


def release_requirements(release):
    root = ElementTree.parse(release.content / "About" / "About.xml").getroot()
    versions = sorted(release.supported_versions, key=version_key)
    entries = {}
    for field in ("modDependencies", "loadAfter"):
        required = field == "modDependencies"
        for items in effective_lists(root, field, versions):
            for item in items:
                package = (item.findtext("packageId") or item.findtext("modIdentifier") or item.text or "").strip()
                if not package:
                    continue
                name = (item.findtext("displayName") or item.findtext("name") or "").strip()
                key = package.casefold()
                entry = entries.setdefault(key, {"packageId": package, "name": name or package,
                                                 "required": required, "itemIds": set()})
                entry["required"] |= required
                if name and entry["name"] == entry["packageId"]:
                    entry["name"] = name
                workshop_id = workshop_id_from_url(item.findtext("steamWorkshopUrl", "").strip())
                if workshop_id:
                    entry["itemIds"].add(workshop_id)

    wanted = {key for key, entry in entries.items() if key not in DLC and not entry["itemIds"]}
    installed = workshop_package_index(wanted) if wanted else {}
    for key, entry in entries.items():
        declared = entry.pop("itemIds")
        item_id, name = installed.get(key, (None, ""))
        if declared:
            item_id = next(iter(declared)) if len(declared) == 1 else None
        official_name, app_id = DLC.get(key, (None, None))
        entry["itemId"] = None if official_name else item_id
        entry["appId"] = app_id
        entry["official"] = official_name is not None
        entry["source"] = ("official" if official_name else "about" if len(declared) == 1
                           else "installed" if item_id else "unresolved")
        entry["candidateItemIds"] = sorted(declared) if len(declared) > 1 else []
        if official_name or (name and entry["name"] == entry["packageId"]):
            entry["name"] = official_name or name
    return list(entries.values())


def requirements_section(entries, language):
    chinese = language in ("schinese", "tchinese")
    blocks = []
    for required, english, translated in (
        (True, "Required", "必需"), (False, "Load order (optional)", "加载顺序（非必需）")
    ):
        lines = []
        for entry in entries:
            if entry["required"] != required:
                continue
            # Prevent metadata labels from inserting links or other page markup.
            name = entry["name"].replace("[", "［").replace("]", "］").replace("\r", " ").replace("\n", " ")
            if entry["itemId"]:
                name = f"[url={WORKSHOP_URL.format(entry['itemId'])}]{name}[/url]"
            elif not entry["official"] and entry["name"] != entry["packageId"]:
                package = entry["packageId"].replace("[", "［").replace("]", "］").splitlines()
                name += f" ({' '.join(package)})"
            if entry["appId"]:
                name += "（DLC）" if chinese else " (DLC)"
            lines.append(f"[*]{name}")
        if lines:
            blocks.extend([f"[b]{translated if chinese else english}[/b]", "[list]", *lines, "[/list]"])
    return "\n".join(blocks)
