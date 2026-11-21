
"""Audit and retarget MRL3, or convert 2D BC textures between TEX and DX10 DDS."""
import argparse
import json
import struct
import zlib
from pathlib import Path, PureWindowsPath

# Format code: (DXGI format, bytes per 4x4 block, TEX color flag)
FORMATS = {22: (71, 8, 0), 23: (72, 8, 0), 26: (83, 16, 0), 28: (95, 16, 1),
           30: (98, 16, 1), 31: (99, 16, 1)}
DXGI_TO_TEX = {info[0]: code for code, info in FORMATS.items()}
TEX_HEADER = 184


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def mip_sizes(width, height, count, code):
    if not (0 < width <= 16384 and 0 < height <= 16384
            and 0 < count <= max(width, height).bit_length() and code in FORMATS):
        raise ValueError(f"Unsupported size, mip count or format: {width}×{height}, {count}, {code}")
    block = FORMATS[code][1]
    return [((max(1, width >> i) + 3) // 4) * ((max(1, height >> i) + 3) // 4) * block
            for i in range(count)]


def tex_data(data):
    if len(data) < TEX_HEADER or data[:4] != b"TEX\0" or u32(data, 4) != 16:
        raise ValueError("Expected an MHWI TEX v16 texture")
    count, width, height, layers, code = struct.unpack_from("<IIIII", data, 20)
    if layers != 1:
        raise ValueError("Only single-surface 2D TEX is supported")
    sizes = mip_sizes(width, height, count, code)
    cursor = TEX_HEADER + 8 * count
    start = cursor
    for index, size in enumerate(sizes):
        offset, high = struct.unpack_from("<II", data, TEX_HEADER + 8 * index)
        if offset != cursor or high != 0:
            raise ValueError(f"Noncanonical mip offset at level {index}: {offset}, {high}")
        cursor += size
    if cursor != len(data):
        raise ValueError(f"TEX payload size differs: {cursor} expected, {len(data)} actual")
    return width, height, count, code, data[start:]


def dds_data(data):
    if len(data) < 148 or data[:4] != b"DDS " or data[84:88] != b"DX10":
        raise ValueError("Use texconv -dx10 to produce a DX10 DDS")
    if u32(data, 4) != 124 or u32(data, 76) != 32:
        raise ValueError("Unexpected DDS header sizes")
    height, width = struct.unpack_from("<II", data, 12)
    count = u32(data, 28) or 1
    dxgi, dim, flags, array_size = struct.unpack_from("<4I", data, 128)
    if dim != 3 or flags != 0 or array_size != 1 or dxgi not in DXGI_TO_TEX:
        raise ValueError("Only supported BC single-surface 2D DDS is accepted")
    code = DXGI_TO_TEX[dxgi]
    payload = data[148:]
    if len(payload) != sum(mip_sizes(width, height, count, code)):
        raise ValueError("DDS payload size disagrees with its mip metadata")
    return width, height, count, code, payload


def to_dds(data):
    width, height, count, code, payload = tex_data(data)
    header = bytearray(148)
    header[:4] = b"DDS "
    flags = 0x81007 | (0x20000 if count > 1 else 0)
    caps = 0x401008 if count > 1 else 0x1000
    struct.pack_into("<7I", header, 4, 124, flags, height, width,
                     mip_sizes(width, height, count, code)[0], 0, count)
    struct.pack_into("<II4s", header, 76, 32, 4, b"DX10")
    struct.pack_into("<I", header, 108, caps)
    struct.pack_into("<5I", header, 128, FORMATS[code][0], 3, 0, 1, 0)
    return bytes(header) + payload


def to_tex(data, template):
    width, height, count, code, payload = dds_data(data)
    _, _, _, template_code, _ = tex_data(template)
    if code != template_code:
        raise ValueError("Choose a working TEX template with the same format and usage")
    header = bytearray(template[:TEX_HEADER])
    struct.pack_into("<IIIII", header, 20, count, width, height, 1, code)
    struct.pack_into("<I", header, 68, FORMATS[code][2])
    struct.pack_into("<I", header, 120, width)
    for field in (124, 136, 148):
        struct.pack_into("<I", header, field, (width << 16) | (width >> 1))
    table = bytearray()
    cursor = TEX_HEADER + 8 * count
    for size in mip_sizes(width, height, count, code):
        table.extend(struct.pack("<II", cursor, 0))
        cursor += size
    result = bytes(header + table) + payload
    tex_data(result)
    return result


def name_hash(name):
    return zlib.crc32(name.encode("ascii")) ^ 0xFFFFFFFF


def mrl_fields(data):
    if len(data) < 40 or data[:4] != b"MRL\0":
        raise ValueError("Expected MHWI MRL3")
    version = u32(data, 4)
    if version != 12:
        raise ValueError(f"Unsupported MRL version: {version}")
    nm, nt, to, mo = struct.unpack_from("<IIQQ", data, 16)
    if not (40 <= to <= to + 272 * nt <= mo <= mo + 56 * nm <= len(data)):
        raise ValueError("MRL3 materials or texture table extends outside file")
    textures, materials = [], []
    for index in range(nt):
        start = to + index * 272 + 16
        path = bytes(data[start:start+256]).split(b"\0", 1)[0].decode("ascii")
        textures.append((start, path))
    for index in range(nm):
        at = mo + index * 56
        value, mmtr, shader = struct.unpack_from("<III", data, at+4)
        size = u32(data, at+16)
        count, = struct.unpack_from("<H", data, at+22)
        offset, = struct.unpack_from("<Q", data, at+48)
        if count % 2 or count * 8 > size or offset + size > len(data):
            raise ValueError(f"Invalid resource block for material {value:08x}")
        materials.append((at+4, value, mmtr, shader, offset, count // 2))
    return textures, materials


def retarget(data, recipe):
    textures, materials = mrl_fields(data)
    result = bytearray(data)
    texture_paths = recipe.get("texture_paths", {})
    material_names = {name_hash(k): name_hash(v) for k, v in recipe.get("material_names", {}).items()}
    if texture_paths.keys() - {name for _, name in textures}:
        raise ValueError("Texture path to replace is absent from template; inspect first")
    if material_names.keys() - {value for _, value, *_ in materials}:
        raise ValueError("Material name to replace is absent from template; inspect first")
    for start, name in textures:
        if name in texture_paths:
            target = texture_paths[name].replace("/", "\\")
            path = PureWindowsPath(target)
            encoded = target.encode("ascii")
            if (not target or path.anchor or ".." in path.parts or ":" in target
                    or path.suffix.lower() == ".tex" or path.parts[0].casefold() == "nativepc"
                    or b"\0" in encoded or len(encoded) >= 256):
                raise ValueError(f"Invalid relative TEX path: {target}")
            result[start:start+256] = encoded.ljust(256, b"\0")
    seen = set()
    for at, value, *_ in materials:
        value = material_names.get(value, value)
        if value in seen:
            raise ValueError("Retargeted material names collide")
        seen.add(value)
        struct.pack_into("<I", result, at, value)
    mrl_fields(result)
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["tex-info", "tex-to-dds", "dds-to-tex", "mrl-info", "mrl-retarget"])
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--template", type=Path)
    parser.add_argument("--recipe", type=Path)
    args = parser.parse_args()
    if args.action not in {"tex-info", "mrl-info"} and (args.output is None or args.output.exists()):
        parser.error("provide a new output path")
    data = args.source.read_bytes()
    if args.action == "tex-info":
        width, height, mips, code, _ = tex_data(data)
        print(json.dumps(dict(width=width, height=height, mips=mips, tex_format=code)))
        return
    if args.action == "mrl-info":
        textures, materials = mrl_fields(data)
        print(json.dumps({"texture_table": [path for _, path in textures],
                          "materials": [{"name_hash": f"{value:08x}", "mmtr_hash": f"{mmtr:08x}", "shader_hash": f"{shader:08x}",
                                         "records": [struct.unpack_from("<4I", data, off+16*i)
                                                     for i in range(count)]}
                                        for _, value, mmtr, shader, off, count in materials]}, indent=2))
        return
    if args.action == "tex-to-dds":
        result = to_dds(data)
    elif args.action == "dds-to-tex" and args.template:
        result = to_tex(data, args.template.read_bytes())
    elif args.action == "mrl-retarget" and args.recipe:
        result = retarget(data, json.loads(args.recipe.read_text(encoding="utf-8-sig")))
    else:
        parser.error("dds-to-tex requires --template; mrl-retarget requires --recipe")
    with args.output.open("xb") as stream:
        stream.write(result)


if __name__ == "__main__":
    main()
