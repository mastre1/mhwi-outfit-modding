
"""Localized MOD3 radial profile patch that preserves layout and skinning."""
from io import BytesIO
import math
from struct import pack_into, unpack_from

import numpy as np


def records(modules, parsed, data):
    file_mod3 = modules("mod3.file_mod3")
    lookup = {mesh.meshInfo.beforeFaceCount: mesh for layer in parsed.meshDict.values() for mesh in layer}
    header = parsed.header
    origin = header.meshOffset + 80 * header.meshCount + 4
    box_cursor = origin
    items = []
    for index in range(header.meshCount):
        info = file_mod3.MeshInfo()
        info.read(BytesIO(data[header.meshOffset + 80 * index:header.meshOffset + 80 * (index + 1)]))
        mesh = lookup[info.beforeFaceCount]
        if mesh.meshInfo.vertexOffset != info.vertexOffset:
            raise ValueError("Cannot identify unique physical mesh ordering")
        items.append((mesh, box_cursor))
        box_cursor += 144 * info.boundingBoxCount
    if (box_cursor != origin + 144 * parsed.bbCount or box_cursor > header.vertexOffset
            or len(lookup) != header.meshCount):
        raise ValueError("Unexpected per-mesh bounding box layout")
    return items


def to_game(point):
    x, y, z = point
    result = np.array([100 * x, 100 * z, -100 * y], dtype=float)
    if not np.all(np.isfinite(result)):
        raise ValueError("Invalid Blender-space profile endpoint")
    return result


def smooth_step_and_derivative(a, b, t):
    u = (t - a) / (b - a)
    if u <= 0:
        return 0, 0
    if u >= 1:
        return 1, 0
    return u * u * (3 - 2 * u), 6 * u * (1 - u) / (b - a)


def profile(positions, spec):
    start, end = to_game(spec["start"]), to_game(spec["end"])
    axis = end - start
    length_squared = axis @ axis
    gain = spec["gain"]
    a, b, c, d = spec.get("window", [0.08, 0.43, 0.68, 0.995])
    limit = spec["max_delta_m"]
    if (length_squared < 0.25 or not 0 <= a < b <= c < d <= 1
            or not -0.5 <= gain <= 0.5 or not 0 < limit <= 0.03):
        raise ValueError("Check axis, window, gain and max_delta_m (0 < limit <= 0.03)")
    grad_t = axis / length_squared
    radial_projection = np.eye(3) - np.outer(axis, grad_t)
    new = positions.copy()
    jacobians = {}
    for i, p in enumerate(positions):
        t = (p - start) @ grad_t
        if t <= a or t >= d:
            continue
        grow, grow_dt = smooth_step_and_derivative(a, b, t)
        fade, fade_dt = smooth_step_and_derivative(c, d, t)
        scale = gain * grow * (1 - fade)
        scale_dt = gain * (grow_dt * (1 - fade) - grow * fade_dt)
        radial = p - (start + t * axis)
        delta = scale * radial
        if np.linalg.norm(delta) < 1e-6:
            continue
        new[i] = p + delta
        jacobians[i] = np.eye(3) + scale * radial_projection + scale_dt * np.outer(radial, grad_t)
    max_delta = float(np.linalg.norm(new - positions, axis=1).max()) / 100
    if not jacobians or max_delta > limit:
        raise ValueError(f"Empty profile or move {max_delta:.6f} m exceeded {limit:.6f} m")
    return new, jacobians, max_delta


def direction(values):
    length = np.linalg.norm(values)
    if length <= 1e-8 or not math.isfinite(length):
        raise ValueError("Invalid normal/tangent on touched vertex")
    return values / length


def byte_vector(values):
    return np.clip(np.rint(values * 127), -127, 127).astype("i1").tobytes()


def inside_original_bound(points, header, parsed, group_id):
    def xyz(value):
        return np.array([value.x, value.y, value.z])

    if np.any(points < xyz(header.aabb.min) - 0.02) or np.any(points > xyz(header.aabb.max) + 0.02):
        raise ValueError("New points exceed original MOD3 AABB; use full Blender export")
    if np.any(np.linalg.norm(points - xyz(header.sphere), axis=1) > header.sphere.r + 0.02):
        raise ValueError("New points exceed original MOD3 sphere; use full Blender export")
    for group in parsed.meshGroupList:
        if group.groupID != group_id:
            continue
        x, y, z, radius = group.sphere
        if radius > 0 and np.any(np.linalg.norm(points - [x, y, z], axis=1) > radius + 0.02):
            raise ValueError("New points exceed original mesh-group sphere; use full Blender export")


def refresh_boxes(modules, result, parsed, mesh, offset, positions, changed):
    fields = mesh.vertexDict
    if parsed.skeleton is None or not fields.get("Bone") or not mesh.meshInfo.boundingBoxCount:
        raise ValueError("Raw patch expects a skinned mesh with a per-bone bounding table")
    affected = {b for i in changed for b, weight in zip(fields["Bone"][i], fields["Weight"][i], strict=True)
                if weight > 1e-6}
    verts_by_bone = {bone: [] for bone in affected}
    for i, (bones, weights) in enumerate(zip(fields["Bone"], fields["Weight"], strict=True)):
        for bone, weight in zip(bones, weights, strict=True):
            if weight > 1e-6 and bone in affected:
                verts_by_bone[bone].append(positions[i])
    box_class = modules("mod3.file_mod3").BoneBoundingBox
    calculate = modules("mod3.mod3_functions").calulateBoundingBoxes
    boxes = 0
    for i in range(mesh.meshInfo.boundingBoxCount):
        at = offset + 144 * i
        bone, = unpack_from("<H", result, at)
        if bone not in affected:
            continue
        verts = np.array(verts_by_bone[bone])
        homogeneous = np.column_stack([verts, np.ones(len(verts))])
        local = (homogeneous @ np.linalg.inv(parsed.skeleton.worldMatList[bone]))[:, :3]
        box = box_class()
        box.boneIndex = bone
        calculate(local, box, hasOBB=True)
        out = BytesIO()
        box.write(out)
        packed = out.getvalue()
        if len(packed) != 144:
            raise ValueError("Unexpected bounding box record size")
        result[at+16:at+144] = packed[16:]
        boxes += 1
    if not boxes:
        raise ValueError("No bounding boxes match the affected bones")
    return boxes


def apply(modules, parsed, data, recipe):
    if parsed.header.version != 237:
        raise ValueError("Raw patch accepts only verified MOD3 v237")
    if not recipe["profiles"]:
        raise ValueError("Specify at least one profile")
    items = records(modules, parsed, data)
    result = bytearray(data)
    headers = modules("mrl3.mrl3_dicts").get_block_format_dict()
    patched = set()
    for spec in recipe["profiles"]:
        index = spec["mesh_index"]
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(items):
            raise ValueError(f"Invalid physical mesh index {index}")
        mesh, boxes_at = items[index]
        info = mesh.meshInfo
        if parsed.materialNameList[info.materialID] != spec["expected_material"]:
            raise ValueError(f"Unexpected material on mesh {index}")
        if spec.get("expected_vertices", info.vertexCount) != info.vertexCount:
            raise ValueError(f"Unexpected vertex count on mesh {index}")
        origin = parsed.header.vertexOffset + info.vertexOffset + info.blockSize * (info.vertexSub + info.vertexBase)
        if origin < parsed.header.vertexOffset or origin + info.blockSize * info.vertexCount > parsed.header.faceOffset:
            raise ValueError("Vertex records exceed MOD3 vertex buffer")
        layout = headers[str(info.blockType)]["prop"]
        offsets = {}
        cursor = 0
        for field, size in layout.items():
            offsets[field] = cursor
            cursor += size
        if cursor != info.blockSize or layout.get("Position") != 12 or layout.get("NorTan") != 8:
            raise ValueError("Unsupported MOD3 vertex field layout")
        positions = np.array(mesh.vertexDict["Position"], dtype=float)
        for i in range(len(positions)):
            address = origin + info.blockSize * i + offsets["Position"]
            positions[i] = unpack_from("<3f", result, address)
        new, jacobians, max_delta = profile(positions, spec)
        inside_original_bound(new[list(jacobians)], parsed.header, parsed, info.groupID)
        for i, jacobian in jacobians.items():
            address = origin + info.blockSize * i
            if address in patched:
                raise ValueError("Two profiles try to edit the same packed vertex")
            patched.add(address)
            normal_at = address + offsets["NorTan"]
            normal = np.array(unpack_from("<3b", result, normal_at), dtype=float)
            tangent = np.array(unpack_from("<3b", result, normal_at + 4), dtype=float)
            normal = direction(np.linalg.solve(jacobian.T, normal))
            tangent = jacobian @ tangent
            tangent = direction(tangent - normal * (normal @ tangent))
            result[normal_at:normal_at+3] = byte_vector(normal)
            result[normal_at+4:normal_at+7] = byte_vector(tangent)
            pack_into("<3f", result, address + offsets["Position"], *new[i])
        boxes = refresh_boxes(modules, result, parsed, mesh, boxes_at, new, jacobians)
        print(f"RAW PROFILE mesh {index}: {len(jacobians)} vertices, max {1000*max_delta:.3f} mm, {boxes} boxes")
    return bytes(result)
