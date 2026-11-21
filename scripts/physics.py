
"""Build MHWI CTC/CCL from explicit Blender-space bone and cloth masks."""
from math import isfinite, radians
from pathlib import Path
from struct import pack_into, unpack_from

import bpy
from mathutils import Vector

from rig_edit import assign_weights, bone_name, group_weight, mesh_object, point, smoothstep


def ctc_records(data):
    if len(data) < 80 or data[:8] != b"CTC\0\x1c\0\0\0":
        raise ValueError("Expected MHWI CTC v28")
    chains, nodes = unpack_from("<II", data, 16)
    split = 80 + chains * 80
    if split + 112 * nodes != len(data):
        raise ValueError("CTC size disagrees with chain/node counts")
    lengths = [unpack_from("<I", data, 80 + 80 * i)[0] for i in range(chains)]
    if sum(lengths) != nodes:
        raise ValueError("CTC chain lengths disagree with node total")
    ids = [unpack_from("<H", data, split + 112 * i + 72)[0] for i in range(nodes)]
    return lengths, ids, split


def ccl_ids(data):
    if len(data) < 16 or data[:4] != b"CCL\0":
        raise ValueError("Expected MHWI CCL")
    count, size = unpack_from("<II", data, 8)
    if size != count * 64 or len(data) != 16 + size:
        raise ValueError("CCL size disagrees with collider count")
    return [unpack_from("<HH", data, 20 + i * 64) for i in range(count)]


def append_ctc(base, new):
    base_lengths, base_ids, cut = ctc_records(base)
    new_lengths, new_ids, new_cut = ctc_records(new)
    if set(base_ids) & set(new_ids):
        raise ValueError("New physics IDs overlap with base CTC")
    header = bytearray(base[:80])
    pack_into("<II", header, 16, len(base_lengths) + len(new_lengths), len(base_ids) + len(new_ids))
    return bytes(header) + base[80:cut] + new[80:new_cut] + base[cut:] + new[new_cut:]


def append_ccl(base, new):
    count = len(ccl_ids(base)) + len(ccl_ids(new))
    if base[4:8] != new[4:8]:
        raise ValueError("Base and new CCL headers have different versions")
    header = bytearray(base[:16])
    pack_into("<II", header, 8, count, count * 64)
    return bytes(header) + base[16:] + new[16:]


def projection(position, points):
    """Return the closest segment and its local parameter along the polyline."""
    best = None
    for i, (start, end) in enumerate(zip(points, points[1:])):
        segment = end - start
        t = min(1.0, max(0.0, (position - start).dot(segment) / segment.length_squared))
        distance = (position - (start + t * segment)).length_squared
        if best is None or distance < best[0]:
            best = (distance, i, t)
    return best[1:]


def chains_from_recipe(spec, rig, assigned, forbidden):
    plans = []
    for config in spec["chains"]:
        names = [bone_name(i) for i in config["ids"]]
        points = [point(x) for x in config["points"]]
        parent = bone_name(config["anchor"])
        if (len(names) < 2 or len(names) != len(points) or len(set(names)) != len(names)
                or set(names) & (assigned | forbidden) or parent not in rig.data.bones):
            raise ValueError(f"Check node IDs, XYZ points, anchor and reserved IDs: {config['ids']}")
        if min((b - a).length for a, b in zip(points, points[1:])) < 0.005:
            raise ValueError("Use at least 5 mm between adjacent physics pivots")
        assigned.update(names)
        plans.append((config, names, points, parent))
    if len(rig.data.bones) + len(assigned) > 255:
        raise ValueError("Bone count exceeds MOD3's 255-bone budget")
    return plans


def add_bones(rig, plans):
    bpy.ops.object.select_all(action="DESELECT")
    rig.hide_set(False)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        inverse = rig.matrix_world.inverted()
        for _, names, points, parent in plans:
            for name, pos in zip(names, points):
                bone = rig.data.edit_bones.new(name)
                bone.head = inverse @ pos
                bone.tail = bone.head + Vector((0, 0, 0.05))
                bone.roll = 0
                bone.parent = rig.data.edit_bones[parent]
                bone.use_connect = False
                bone["Mod3_Bone_Unkn"] = 1.0
                parent = name
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def paint(rig, plans, limit):
    selections = []
    used_vertices = set()
    masks = set()
    for config, names, points, _ in plans:
        start, end = config.get("root_fade_segments", [0.0, 1.25])
        strength = config.get("strength", 0.95)
        if not 0 <= start < end <= len(points) - 1 or not 0 < strength <= 1:
            raise ValueError("Check root fade range and strength")
        for binding in config["bind"]:
            obj = mesh_object(binding["object"])
            modifiers = [m for m in obj.modifiers if m.type == "ARMATURE"]
            if len(modifiers) != 1 or modifiers[0].object != rig:
                raise ValueError(f"{obj.name}: connect this mesh to the selected MOD3 rig first")
            mask = obj.vertex_groups[binding["mask"]]
            keep_mask = binding.get("keep_mask", False)
            if not keep_mask:
                masks.add((obj.name, mask.name))
            existing_names = {g.index: g.name for g in obj.vertex_groups if g.name in rig.data.bones}
            count = 0
            for vertex in obj.data.vertices:
                weight = group_weight(vertex, mask.index)
                if weight <= 0:
                    continue
                index, t = projection(obj.matrix_world @ vertex.co, points)
                fraction = strength * weight * smoothstep(start, end, index + t)
                if fraction < 1e-5:
                    continue
                key = (obj.name, vertex.index)
                if key in used_vertices:
                    raise ValueError(f"Overlapping chain masks at {key}; split or paint a dedicated blend")
                used_vertices.add(key)
                old = {existing_names[g.group]: g.weight for g in vertex.groups
                       if g.group in existing_names and g.weight > 0}
                total = sum(old.values())
                if total <= 0:
                    raise ValueError(f"{key}: original vertex requires a deform anchor")
                values = {name: w * (1 - fraction) / total for name, w in old.items()}
                values[names[index]] = fraction * (1 - t)
                values[names[index + 1]] = fraction * t
                selections.append((obj, vertex.index, values))
                count += 1
            if not count:
                raise ValueError(f"{obj.name}/{mask.name}: no effective dynamic weight")
            print(f"PHYSICS MASK {obj.name}/{mask.name}: {count} vertices")
    for obj, index, values in selections:
        # Preserve auxiliary masks until every planned change has used them.
        auxiliary = [(obj.vertex_groups[g.group].name, g.weight)
                     for g in obj.data.vertices[index].groups if g.group not in
                     {vg.index for vg in obj.vertex_groups if vg.name in rig.data.bones}]
        assign_weights(obj, index, values, limit)
        for name, weight in auxiliary:
            obj.vertex_groups[name].add([index], weight, "REPLACE")
    for name, group in sorted(masks):
        obj = bpy.data.objects[name]
        obj.vertex_groups.remove(obj.vertex_groups[group])
    if not selections:
        raise ValueError("Physics recipe has no mesh binding")


def make_ctc(module, plans, output):
    file = module.CTCFile()
    for config, names, points, _ in plans:
        chain = module.Chain()
        chain.NodeCount = len(names)
        collision = config.get("collision", 0)
        if collision not in (0, 4, 6):
            raise ValueError("Use 0, 4 or 6 as CTC collision flags")
        chain.CollisionAttrFlag.asInt32 = collision
        gravity = config.get("gravity", 240)
        chain.Damping = config.get("damping", 0.14)
        chain.TransForceCoef = config.get("transfer", 0.30)
        chain.SpringCoef = config.get("spring", 0.02)
        chain.WindRate = config.get("wind", 0.08)
        radius = config.get("radius_cm", 1.4)
        angle = config.get("angle_deg", 35.0)
        mass = config.get("mass", 1.0)
        elastic = config.get("elastic", 1.0)
        values = (gravity, chain.Damping, chain.TransForceCoef, chain.SpringCoef, chain.WindRate,
                  radius, angle, mass, elastic)
        if not all(isfinite(x) and x >= 0 for x in values) or not 0 < angle <= 180 or mass == 0:
            raise ValueError("Nonfinite or out-of-range CTC settings")
        chain.Gravity = [0, -gravity, 0]
        file.ChainList.append(chain)
        for i, identifier in enumerate(config["ids"]):
            delta = points[i + 1] - points[i] if i + 1 < len(points) else points[i] - points[i - 1]
            direction = Vector((delta.x, delta.z, -delta.y)).normalized()
            frame = Vector((1, 0, 0)).rotation_difference(direction).to_matrix()
            node = module.Node()
            node.NodeMatrix.matrix = [list(row) for row in frame.transposed().to_4x4()]
            node.IsParent = int(i == 0)
            node.BoneFunctionID = identifier
            node.BoneColRadius = radius
            node.AngleLimitRadius = radians(angle)
            node.Mass = mass
            node.ElasticCoef = elastic
            file.NodeList.append(node)
    file.Header.ChainCount = len(file.ChainList)
    file.Header.NodeCount = len(file.NodeList)
    module.writeCTCFile(file, str(output))


def make_ccl(module, spec, rig, output):
    file = module.CCLFile()
    for rule in spec:
        item = module.Collision()
        item.StartID, item.EndID = rule["start_id"], rule["end_id"]
        if any(bone_name(i) not in rig.data.bones for i in (item.StartID, item.EndID)):
            raise ValueError("CCL anchor is absent from the selected MOD3 rig")
        item.StartPos = list(point(rule.get("start_cm", [0, 0, 0])))
        item.EndPos = list(point(rule.get("end_cm", [0, 0, 0])))
        item.ColRadius = rule["radius_cm"]
        if not isfinite(item.ColRadius) or item.ColRadius <= 0:
            raise ValueError("CCL capsule radius must be positive")
        file.CollisionList.append(item)
    file.Header.ColCount = len(file.CollisionList)
    file.Header.ColTotalOffset = 64 * len(file.CollisionList)
    module.writeCCLFile(file, str(output))


def build(spec, rig, modules, folder):
    assigned = set()
    forbidden = {bone_name(i) for i in spec.get("reserved_ids", [])}
    plans = chains_from_recipe(spec, rig, assigned, forbidden | set(rig.data.bones.keys()))
    if not plans:
        raise ValueError("Provide at least one chain, or omit the physics recipe")
    limit = spec.get("max_influences", 4)
    if limit not in (4, 8):
        raise ValueError("Choose 4 or 8 influences based on the mesh's export format")
    base_ctc = Path(spec["base_ctc"]).read_bytes() if spec.get("base_ctc") else None
    base_ccl = Path(spec["base_ccl"]).read_bytes() if spec.get("base_ccl") else None
    if base_ccl and not base_ctc:
        raise ValueError("Supply the paired base_ctc when preserving an existing base_ccl")
    if not (spec.get("colliders") or base_ccl) and any(c.get("collision", 0) for c, *_ in plans):
        raise ValueError("Model collision enabled, but no CCL provided/generated")
    add_bones(rig, plans)
    paint(rig, plans, limit)
    ctc_path, ccl_path = folder / "new.ctc", folder / "new.ccl"
    make_ctc(modules("ctc.file_ctc"), plans, ctc_path)
    ctc = ctc_path.read_bytes()
    if base_ctc:
        ctc = append_ctc(base_ctc, ctc)
    ccl = base_ccl
    if spec.get("colliders"):
        make_ccl(modules("ccl.file_ccl"), spec["colliders"], rig, ccl_path)
        new_ccl = ccl_path.read_bytes()
        ccl = append_ccl(base_ccl, new_ccl) if base_ccl else new_ccl
    return ctc, ccl
