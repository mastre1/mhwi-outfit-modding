
"""Use Blender and MHW Model Editor to prepare, build and verify outfit assets."""
import argparse
from collections import Counter
from importlib import import_module
import json
import os
from pathlib import Path
from struct import unpack_from
import re
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

import addon_utils
import bpy

from physics import build as build_physics, ccl_ids, ctc_records
from rig_edit import radial, retarget
from texture_material import mrl_fields, name_hash


PARTS = {"helm", "body", "arm", "wst", "leg"}
MOD3_TYPE = "MHW_MOD3_COLLECTION"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_addon(module):
    if not module:
        candidates = [m.__name__ for m in addon_utils.modules(refresh=True)
                      if "mhw_model_editor" in m.__name__.lower()]
        if len(candidates) != 1:
            raise ValueError(f"Specify the installed Model Editor with --addon. Matches: {candidates}")
        module = candidates[0]
    addon_utils.enable(module, default_set=False, persistent=False)
    if not addon_utils.check(module)[1]:
        raise RuntimeError(f"Blender did not enable add-on {module}")
    prefix = f"{module}.addons.MHW_Model_Editor.modules"
    return lambda name: import_module(f"{prefix}.{name}")


def read_mod3(modules, path):
    opt = dict(importArmatureOnly=False, importBoundingBoxes=True, importAllLODs=True)
    raw = modules("mod3.file_mod3").readMod3File(str(path), opt)
    if raw is None:
        raise ValueError(f"MOD3 could not be read: {path}")
    parsed = modules("mod3.mod3_parser").ParsedMod3File()
    parsed.parse(raw, opt)
    if parsed.validMeshCount != parsed.header.meshCount:
        raise ValueError(f"MOD3 parser skipped meshes: {path}")
    return parsed


def audit(modules, path, check_mrl=False):
    mod = read_mod3(modules, path)
    names = mod.materialNameList
    bones = {int(i): int(fid) for i, fid in mod.skeleton.boneRemapDict.items()} if mod.skeleton else {}
    counts = Counter()
    meshes = []
    data = path.read_bytes()
    mesh_rows = {unpack_from("<I", data, mod.header.meshOffset + 80 * i + 28)[0]: i
                 for i in range(mod.header.meshCount)}
    for level, layer in mod.meshDict.items():
        for mesh in layer:
            used = Counter()
            weights = mesh.vertexDict.get("Weight", [])
            indices = mesh.vertexDict.get("Bone", [])
            for vertex_weights, vertex_bones in zip(weights, indices, strict=True):
                for weight, index in zip(vertex_weights, vertex_bones, strict=True):
                    if weight > 0.001:
                        if index not in bones:
                            raise ValueError(f"Vertex references unmapped bone index {index}")
                        used[bones[index]] += 1
            counts.update(used)
            meshes.append(dict(mesh_index=mesh_rows[mesh.meshInfo.beforeFaceCount], lod=level, vertices=int(mesh.meshInfo.vertexCount),
                               triangles=len(mesh.faceList), materials=[names[mesh.meshInfo.materialID]],
                               bone_ids=sorted(used)))
    report = dict(file=path.name, meshes=meshes, bones=sorted(bones.values()), materials=names)
    errors = []
    ctc, ccl = path.with_suffix(".ctc"), path.with_suffix(".ccl")
    if ctc.exists():
        lengths, ids, _ = ctc_records(ctc.read_bytes())
        if set(ids) - set(bones.values()):
            raise ValueError(f"CTC IDs missing from same-stem MOD3: {sorted(set(ids) - set(bones.values()))}")
        report["chains"] = []
        start = 0
        for length in lengths:
            chain = ids[start:start+length]
            start += length
            report["chains"].append(dict(ids=chain, weighted_vertices=[counts[i] for i in chain]))
            if length < 2 or not any(counts[i] for i in chain[1:]):
                errors.append(f"Chain {chain} has no effective distal weight")
    if ccl.exists():
        if not ctc.exists():
            raise ValueError("CCL requires a same-stem CTC")
        pairs = ccl_ids(ccl.read_bytes())
        if {i for pair in pairs for i in pair} - set(bones.values()):
            raise ValueError("CCL endpoints missing from same-stem MOD3")
        report["colliders"] = pairs
    if check_mrl:
        textures, materials = mrl_fields(path.with_suffix(".mrl3").read_bytes())
        missing = {name: f"{name_hash(name):08x}" for name in names
                   if name_hash(name) not in {v for _, v, *_ in materials}}
        if missing:
            errors.append(f"No matching MRL3 material hash: {missing}")
        report["texture_paths"] = [p for _, p in textures]
        material_dict = modules("mrl3.mrl3_dicts").get_master_material_dict()
        active = {name_hash(name): name for name in names}
        bindings = {}
        data = path.with_suffix(".mrl3").read_bytes()
        for _, value, mmtr, _, offset, count in materials:
            if value not in active:
                continue
            template = material_dict.get(str(mmtr))
            if not template:
                errors.append(f"Unrecognized MMTR {mmtr:08x} for {active[value]}")
                continue
            slots = {}
            for i in range(count):
                _, resource, index, _ = unpack_from("<4I", data, offset + 16 * i)
                definition = template["resourceDict"].get(str(resource >> 12), {})
                slot = definition.get("name", "")
                if slot.startswith("t") and index:
                    if index > len(textures):
                        errors.append(f"{active[value]}/{slot}: TEX slot {index} is outside the table")
                    else:
                        slots[slot] = textures[index - 1][1]
            bindings[active[value]] = slots
        report["active_texture_slots"] = bindings
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if errors:
        raise ValueError("; ".join(errors))


def available_collections():
    for col in bpy.data.collections:
        if col.get("~TYPE") != MOD3_TYPE:
            continue
        items = [dict(name=obj.name, type=obj.type,
                      groups=[g.name for g in obj.vertex_groups if not g.name.startswith("MhBone_")])
                 for obj in col.all_objects if obj.type in {"MESH", "ARMATURE"}]
        print(json.dumps({"collection": col.name, "objects": items}, ensure_ascii=False))


def save(path):
    if path.exists():
        raise ValueError(f"Provide a new blend path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path.resolve()), copy=True)


def seed(args, modules):
    if args.output.exists():
        raise ValueError("Provide a new blend path")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    by_part = set()
    for entry in args.donor:
        part, path = entry.split("=", 1)
        if part not in PARTS or part in by_part:
            raise ValueError(f"Invalid or repeated donor part: {part}")
        by_part.add(part)
        before = set(bpy.data.collections)
        options = dict(clearScene=False, createCollections=True, addNestedCollections=False,
                       loadMaterials=False, loadMrl3Data=False, loadPhysics=False, mrl3Path="",
                       importBoundingBoxes=False, importArmatureOnly=False, importAllLODs=True,
                       ArmatureDisplayType="STICK", BonesDisplaySize=0.02)
        modules("mod3.blender_mod3").importMHWMod3File(str(Path(path).resolve()), options)
        found = [col for col in bpy.data.collections if col not in before and col.get("~TYPE") == MOD3_TYPE]
        if len(found) != 1:
            raise ValueError(f"Expected one donor collection for {path}")
        found[0].name = f"MHWI_{part}"
    if args.source:
        ext = args.source.suffix.lower()
        if ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=str(args.source.resolve()))
        elif ext == ".pmx":
            addon_utils.enable(args.mmd_addon, default_set=False, persistent=False)
            bpy.ops.mmd_tools.import_model(filepath=str(args.source.resolve()))
        else:
            raise ValueError("Use FBX or PMX, or append other source formats in Blender first")
    available_collections()
    save(args.output)


def export_part(modules, collection, model, use_names):
    opt = dict(targetCollection=collection, invisibleMantlesModFix=False, selectedOnly=False,
               visibleOnly=False, autoSolveRepeatedUVs=True, preserveSharpEdges=False,
               useBlenderMaterialName=use_names)
    passed = modules("mod3.blender_mod3").exportMHWMod3File(str(model), opt)
    if not passed or not model.is_file():
        raise ValueError(f"MOD3 export failed for {collection.name}")


def build(args, modules):
    if not bpy.data.filepath:
        raise ValueError("Open the prepared .blend before running build")
    if args.output.exists() or args.scene_output and args.scene_output.exists():
        raise ValueError("Provide new output paths")
    recipe = load_json(args.recipe)
    sex, number = recipe["sex"], recipe["number"]
    if sex not in {"f", "m"} or not re.fullmatch(r"\d{3}_\d{4}", number, re.ASCII):
        raise ValueError("Expected equipment format such as f / 123_0000")
    if not recipe["parts"] or set(recipe["parts"]) - PARTS:
        raise ValueError("Invalid part keys")
    for spec in recipe.get("retarget", []):
        retarget(spec)
    for spec in recipe.get("radial", []):
        radial(spec)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="mhwi-build-", dir=args.output.parent) as tmp:
        work = Path(tmp)
        payload = work / "payload"
        for part, spec in recipe["parts"].items():
            collection = bpy.data.collections[spec["collection"]]
            if collection.get("~TYPE") != MOD3_TYPE:
                raise ValueError(f"Expected a donor MOD3 collection: {collection.name}")
            armatures = [o for o in collection.all_objects if o.type == "ARMATURE"]
            meshes = [o for o in collection.all_objects if o.type == "MESH"]
            if len(armatures) != 1 or not meshes:
                raise ValueError(f"{part}: expected exactly one rig and at least one mesh")
            rig = armatures[0]
            folder = payload / "nativePC" / "pl" / f"{sex}_equip" / f"pl{number}" / part / "mod"
            folder.mkdir(parents=True)
            model = folder / f"{sex}_{part}{number}.mod3"
            ctc, ccl = None, None
            if "physics" in spec:
                if "ctc" in spec or "ccl" in spec:
                    raise ValueError(f"{part}: use physics or existing CTC/CCL paths")
                bound = {item["object"] for chain in spec["physics"]["chains"] for item in chain["bind"]}
                if bound - {obj.name for obj in meshes}:
                    raise ValueError(f"{part}: physics binding is outside the exported collection")
                ctc, ccl = build_physics(spec["physics"], rig, modules, work)
            else:
                if spec.get("ctc"):
                    ctc = Path(spec["ctc"]).read_bytes()
                if spec.get("ccl"):
                    ccl = Path(spec["ccl"]).read_bytes()
            if ctc is not None:
                model.with_suffix(".ctc").write_bytes(ctc)
            if ccl is not None:
                model.with_suffix(".ccl").write_bytes(ccl)
            for ext in ("mrl3", "evbd", "evhl"):
                if spec.get(ext):
                    model.with_suffix("." + ext).write_bytes(Path(spec[ext]).read_bytes())
            export_part(modules, collection, model, spec.get("use_blender_material_names", False))
            audit(modules, model, check_mrl=bool(spec.get("mrl3")))
        if args.scene_output:
            save(args.scene_output)
        payload.rename(args.output)


def patch_raw(args, modules):
    from raw_profile import apply

    if args.output.suffix.lower() != ".mod3" or args.output.exists():
        raise ValueError("Provide a new .mod3 path")
    original = args.model.read_bytes()
    result = apply(modules, read_mod3(modules, args.model), original, load_json(args.recipe))
    if len(result) != len(original):
        raise ValueError("A raw patch cannot change the file length")
    with TemporaryDirectory(prefix="mhwi-profile-", dir=args.output.parent) as work:
        trial = Path(work) / args.output.name
        trial.write_bytes(result)
        audit(modules, trial)
        trial.rename(args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addon", default=os.environ.get("MHWI_ADDON"))
    sub = parser.add_subparsers(dest="action", required=True)
    seed_parser = sub.add_parser("seed")
    seed_parser.add_argument("output", type=Path)
    seed_parser.add_argument("--donor", action="append", required=True, metavar="SLOT=PATH")
    seed_parser.add_argument("--source", type=Path)
    seed_parser.add_argument("--mmd-addon", default="mmd_tools")
    sub.add_parser("layout")
    build_parser = sub.add_parser("build")
    build_parser.add_argument("recipe", type=Path)
    build_parser.add_argument("output", type=Path)
    build_parser.add_argument("--scene-output", type=Path)
    audit_parser = sub.add_parser("audit")
    audit_parser.add_argument("model", type=Path)
    audit_parser.add_argument("--check-mrl", action="store_true")
    patch_parser = sub.add_parser("patch-profile")
    patch_parser.add_argument("model", type=Path)
    patch_parser.add_argument("recipe", type=Path)
    patch_parser.add_argument("output", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    if args.action == "layout":
        available_collections()
        return
    modules = load_addon(args.addon)
    if args.action == "seed":
        seed(args, modules)
    elif args.action == "build":
        build(args, modules)
    elif args.action == "patch-profile":
        patch_raw(args, modules)
    else:
        audit(modules, args.model, args.check_mrl)


if __name__ == "__main__":
    main()
