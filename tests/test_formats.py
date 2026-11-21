"""Asset-free checks for the standalone formats and ZIP commands."""
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from nativepc import audit
from texture_material import mrl_fields, name_hash, retarget, tex_data, to_dds, to_tex


def synthetic_tex():
    header = bytearray(184)
    header[:4] = b"TEX\0"
    struct.pack_into("<I", header, 4, 16)
    struct.pack_into("<IIIII", header, 20, 3, 4, 4, 1, 22)
    struct.pack_into("<I", header, 120, 4)
    for offset in (124, 136, 148):
        struct.pack_into("<I", header, offset, (4 << 16) | 2)
    table = struct.pack("<6I", 208, 0, 216, 0, 224, 0)
    return bytes(header) + table + bytes(range(24))


def synthetic_mrl():
    texture_table, material_table, resource = 40, 312, 368
    data = bytearray(resource + 16)
    struct.pack_into("<4sI", data, 0, b"MRL\0", 12)
    struct.pack_into("<IIQQ", data, 16, 1, 1, texture_table, material_table)
    texture = b"Example\\textures\\cloth"
    data[texture_table + 16:texture_table + 16 + len(texture)] = texture
    struct.pack_into("<4I", data, material_table + 4, name_hash("Cloth"), 100, 200, 16)
    struct.pack_into("<H", data, material_table + 22, 2)
    struct.pack_into("<Q", data, material_table + 48, resource)
    struct.pack_into("<4I", data, resource, 1, 4096, 1, 0)
    return bytes(data)


class TextureTests(unittest.TestCase):
    def test_exact_tex_round_trip(self):
        original = synthetic_tex()
        self.assertEqual(tex_data(original)[:4], (4, 4, 3, 22))
        self.assertEqual(to_tex(to_dds(original), original), original)

    def test_reject_truncated_texture(self):
        with self.assertRaisesRegex(ValueError, "payload size"):
            tex_data(synthetic_tex()[:-1])

    def test_mrl_retarget_preserves_resources(self):
        original = synthetic_mrl()
        recipe = {"material_names": {"Cloth": "NewCloth"},
                  "texture_paths": {"Example\\textures\\cloth": "Other/textures/new"}}
        result = retarget(original, recipe)
        textures, materials = mrl_fields(result)
        self.assertEqual(textures[0][1], r"Other\textures\new")
        self.assertEqual(materials[0][1], name_hash("NewCloth"))
        self.assertEqual(len(original), len(result))
        self.assertEqual(original[368:], result[368:])

    def test_reject_missing_template_name(self):
        with self.assertRaisesRegex(ValueError, "absent from template"):
            retarget(synthetic_mrl(), {"material_names": {"Missing": "NewCloth"}})


class PackageTests(unittest.TestCase):
    stem = "nativePC/pl/f_equip/pl123_0000/body/mod/f_body123_0000"

    def test_reject_mismatched_equipment_number(self):
        with self.assertRaisesRegex(ValueError, "numbering differs"):
            audit([self.stem.replace("body123", "body124") + ".mod3"])

    def test_reject_incomplete_full_set(self):
        with self.assertRaisesRegex(ValueError, "missing equipment slots"):
            audit([self.stem + ".mod3", self.stem + ".mrl3"], full_set=True)

    def test_pack_and_unpack_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, archive, extracted = root / "source", root / "out.zip", root / "unpacked"
            payload = {
                self.stem + ".mod3": b"synthetic-layout-only",
                self.stem + ".mrl3": synthetic_mrl(),
                "nativePC/Example/textures/cloth.tex": synthetic_tex(),
            }
            for path, contents in payload.items():
                target = source / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(contents)
            script = str(SCRIPTS / "nativepc.py")
            for args in (["pack", source, archive], ["unpack", archive, extracted]):
                command = [sys.executable, script, *map(str, args), "--texture-namespace", "Example/textures"]
                run = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual({p.relative_to(extracted).as_posix(): p.read_bytes()
                              for p in extracted.rglob("*") if p.is_file()}, payload)


if __name__ == "__main__":
    unittest.main()
