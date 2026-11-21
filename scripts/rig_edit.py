
"""Explicit retargeting and proportion edits for a prepared Blender scene."""
from collections import defaultdict
from math import isfinite

import bpy
from mathutils import Vector


def bone_name(identifier):
    if isinstance(identifier, bool) or not isinstance(identifier, int) or not 0 <= identifier < 512:
        raise ValueError(f"Invalid MOD3 bone function ID: {identifier}")
    return f"MhBone_{identifier:03d}"


def point(values):
    if len(values) != 3 or not all(isfinite(x) for x in values):
        raise ValueError(f"Expected a finite XYZ point: {values}")
    return Vector(values)


def smoothstep(start, end, value):
    t = max(0.0, min(1.0, (value - start) / (end - start)))
    return t * t * (3.0 - 2.0 * t)


def mesh_object(name):
    obj = bpy.data.objects[name]
    if obj.type != "MESH" or obj.mode != "OBJECT":
        raise ValueError(f"Expected a mesh in Object Mode: {name}")
    return obj


def group_weight(vertex, group_index):
    return next((group.weight for group in vertex.groups if group.group == group_index), 0.0)


def assign_weights(obj, vertex_id, values, limit):
    selected = sorted(((weight, name) for name, weight in values.items() if weight > 1e-7),
                      key=lambda entry: (-entry[0], entry[1]))[:limit]
    total = sum(weight for weight, _ in selected)
    if total == 0:
        raise ValueError(f"{obj.name} vertex {vertex_id} has no mapped deform weight")
    for group in list(obj.data.vertices[vertex_id].groups):
        obj.vertex_groups[group.group].remove([vertex_id])
    for weight, name in selected:
        target = obj.vertex_groups.get(name)
        if target is None:
            target = obj.vertex_groups.new(name=name)
        target.add([vertex_id], weight / total, "REPLACE")


def retarget(spec):
    rig = bpy.data.objects[spec["rig"]]
    limit = spec.get("max_influences", 4)
    if rig.type != "ARMATURE" or limit not in (4, 8):
        raise ValueError("Retarget requires an armature and a 4- or 8-weight budget")
    mapping = {name: bone_name(identifier) for name, identifier in spec["groups"].items()}
    if set(mapping.values()) - set(rig.data.bones.keys()):
        raise ValueError("Group mapping contains an ID absent from the selected rig")
    ignored = set(spec.get("ignore_groups", []))
    if ignored & mapping.keys():
        raise ValueError("Ignored groups overlap with mapped groups")
    for name in spec["objects"]:
        obj = mesh_object(name)
        names = {group.index: group.name for group in obj.vertex_groups}
        moves = []
        for vertex in obj.data.vertices:
            weights = defaultdict(float)
            for group in vertex.groups:
                source = names[group.group]
                if source in ignored or group.weight <= 1e-7:
                    continue
                if source not in mapping:
                    raise ValueError(f"{obj.name}: positive weight in unmapped group {source!r}")
                weights[mapping[source]] += group.weight
            moves.append(weights)
        for index, weights in enumerate(moves):
            auxiliary = [(names[g.group], g.weight) for g in obj.data.vertices[index].groups
                         if names[g.group] in ignored]
            assign_weights(obj, index, weights, limit)
            for group, weight in auxiliary:
                obj.vertex_groups[group].add([index], weight, "REPLACE")
        for group in list(obj.vertex_groups):
            if group.name not in rig.data.bones and group.name not in ignored:
                obj.vertex_groups.remove(group)
        armatures = [mod for mod in obj.modifiers if mod.type == "ARMATURE"]
        if len(armatures) > 1:
            raise ValueError(f"Remove duplicate armature modifiers: {obj.name}")
        modifier = armatures[0] if armatures else obj.modifiers.new("MHWI Rig", "ARMATURE")
        modifier.object = rig
        transform = obj.matrix_world.copy()
        obj.parent = rig
        obj.matrix_world = transform
        print(f"RETARGET {obj.name}: {len(moves)} vertices")


def radial(spec):
    obj = mesh_object(spec["object"])
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    start, end = point(spec["start"]), point(spec["end"])
    axis = end - start
    length_squared = axis.length_squared
    if length_squared < 1e-8:
        raise ValueError("Profile requires distinct endpoints")
    windows = spec.get("window", [0.08, 0.43, 0.68, 0.995])
    a, b, c, d = windows
    gain = spec["gain"]
    if not 0 <= a < b <= c < d <= 1 or not isfinite(gain) or not -0.5 <= gain <= 0.5:
        raise ValueError("Invalid radial window or gain")
    mask_name = spec["mask"]
    mask = obj.vertex_groups[mask_name].index
    transform = obj.matrix_world
    inverse = transform.inverted()
    changed = 0
    maximum = 0.0
    shape_keys = obj.data.shape_keys
    origin = shape_keys.reference_key.data if shape_keys else obj.data.vertices
    shape_blocks = list(shape_keys.key_blocks) if shape_keys else []
    for vertex in obj.data.vertices:
        weight = group_weight(vertex, mask)
        if weight <= 0:
            continue
        position = transform @ origin[vertex.index].co
        t = (position - start).dot(axis) / length_squared
        strength = weight * gain * smoothstep(a, b, t) * (1 - smoothstep(c, d, t))
        delta = strength * (position - (start + t * axis))
        if delta.length < 1e-8:
            continue
        local_delta = inverse.to_3x3() @ delta
        if shape_blocks:
            for shape in shape_blocks:
                shape.data[vertex.index].co += local_delta
        else:
            vertex.co += local_delta
        changed += 1
        maximum = max(maximum, delta.length)
    if not changed:
        raise ValueError(f"{obj.name}: mask/window selected zero movable vertices")
    if spec.get("max_delta_m") is not None and maximum > spec["max_delta_m"]:
        raise ValueError(f"{obj.name}: move {maximum:.6f} m exceeds configured limit")
    if spec.get("clear_mask", True):
        obj.vertex_groups.remove(obj.vertex_groups[mask_name])
    if obj.data.has_custom_normals:
        print(f"NOTE {obj.name}: inspect/recalculate custom split normals before final export")
    obj.data.update()
    print(f"RADIAL {obj.name}: {changed} vertices, max {1000 * maximum:.3f} mm")
