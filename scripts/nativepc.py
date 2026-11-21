
"""Inspect, extract or pack local MHWI outfit deliverables."""
import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

sys.dont_write_bytecode = True
from texture_material import mrl_fields, tex_data

MODEL = re.compile(
    r"nativepc/pl/([fm])_equip/pl(\d{3}_\d{4})/(helm|body|arm|wst|leg)/mod/"
    r"([fm])_(helm|body|arm|wst|leg)(\d{3}_\d{4})\.(mod3|mrl3|ctc|ccl)", re.I
)
PARTS = {"helm", "body", "arm", "wst", "leg"}


def audit(paths, full_set=False):
    seen, grouped = set(), {}
    for raw in paths:
        path = PurePosixPath(raw)
        if ("\\" in raw or path.as_posix() != raw or ":" in raw or ".." in path.parts
                or len(path.parts) < 2 or path.parts[0].lower() != "nativepc"):
            raise ValueError(f"Only canonical paths below nativePC are accepted: {raw}")
        if raw.casefold() in seen:
            raise ValueError(f"Duplicate path: {raw}")
        seen.add(raw.casefold())
        match = MODEL.fullmatch(raw)
        if not match:
            if re.search(r"\.(mod3|mrl3|ctc|ccl)$", raw, re.I):
                raise ValueError(f"Unexpected model sidecar layout: {raw}")
            continue
        sex, number, part, file_sex, file_part, file_number, ext = match.groups()
        if (sex.lower(), part.lower(), number) != (file_sex.lower(), file_part.lower(), file_number):
            raise ValueError(f"File numbering differs from directories: {raw}")
        grouped.setdefault((sex.lower(), number), {}).setdefault(part.lower(), set()).add(ext.lower())
    if not grouped:
        raise ValueError("No MHWI equipment models found")
    for key, parts in grouped.items():
        if full_set and set(parts) != PARTS:
            raise ValueError(f"{key}: missing equipment slots {sorted(PARTS - parts.keys())}")
        for part, files in parts.items():
            if not {"mod3", "mrl3"} <= files or "ccl" in files and "ctc" not in files:
                raise ValueError(f"{key} {part}: incomplete same-stem asset set: {sorted(files)}")
    return {f"{sex}:{number}": {part: sorted(ext) for part, ext in sorted(parts.items())}
            for (sex, number), parts in sorted(grouped.items())}


def verify_textures(names, read_bytes, namespace):
    if not re.fullmatch(r"[A-Za-z0-9_/-]+", namespace) or namespace.startswith(("/", "nativePC/")):
        raise ValueError("Use a dedicated relative nativePC texture namespace such as MyOutfit/textures")
    prefix = namespace.rstrip("/").casefold() + "/"
    files = {name.casefold(): name for name in names}
    required = set()
    for mrl in (name for name in names if name.lower().endswith(".mrl3")):
        paths, _ = mrl_fields(read_bytes(mrl))
        for _, path in paths:
            relative = path.replace("\\", "/").casefold()
            if relative.startswith(prefix):
                required.add(f"nativepc/{relative}.tex")
    if not required:
        raise ValueError(f"No MRL3 texture references under namespace {namespace}")
    if missing := required - files.keys():
        raise ValueError(f"Missing TEX under custom namespace: {sorted(missing)}")
    for name in sorted(required):
        tex_data(read_bytes(files[name]))
    return len(required)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inspect", "unpack", "pack"])
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--full-set", action="store_true")
    parser.add_argument("--texture-namespace", help="Verify referenced TEX under a custom directory")
    args = parser.parse_args()
    if args.action != "inspect" and (args.output is None or args.output.exists()):
        parser.error("provide a new output path")
    extra = {}
    if args.source.is_dir():
        names = sorted(p.relative_to(args.source).as_posix()
                       for p in (args.source / "nativePC").rglob("*") if p.is_file())
        contents = audit(names, args.full_set)
        if args.texture_namespace:
            extra["verified_textures"] = verify_textures(names, lambda name: (args.source / name).read_bytes(),
                                                        args.texture_namespace)
        if args.action == "unpack":
            parser.error("unpack requires a ZIP")
        if args.action == "pack":
            if args.output.resolve().is_relative_to((args.source / "nativePC").resolve()):
                parser.error("output must be outside nativePC")
            with ZipFile(args.output, "x", compression=ZIP_DEFLATED) as archive:
                for name in names:
                    archive.write(args.source / name, name)
    else:
        if args.action == "pack":
            parser.error("pack requires a folder whose child is nativePC")
        with ZipFile(args.source) as archive:
            names = [entry.filename for entry in archive.infolist() if not entry.is_dir()]
            contents = audit(names, args.full_set)
            if args.texture_namespace:
                extra["verified_textures"] = verify_textures(names, archive.read, args.texture_namespace)
            if bad := archive.testzip():
                raise ValueError(f"ZIP CRC failure: {bad}")
            if args.action == "unpack":
                args.output.mkdir(parents=True)
                for name in names:
                    archive.extract(name, args.output)
    print(json.dumps({"files": len(names), "sets": contents, **extra}, indent=2))


if __name__ == "__main__":
    main()
