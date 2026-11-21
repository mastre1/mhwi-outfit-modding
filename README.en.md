# MHWI Outfit Modding

[简体中文](README.md) · [Agent skill](SKILL.md) · [MIT License](LICENSE)

A Blender workflow and agent skill for making outfit mods for *Monster Hunter World: Iceborne*. Use your own character assets to build outfits that can be reassigned to other equipment IDs. The workflow covers rig mapping, skin weights, localized shape edits, cloth physics, materials, textures, and `nativePC` packaging.

> **AI authorship disclosure.** AI created the entire initial public version, including the workflow, code, documentation, examples, and tests. The maintainer supplied requirements, in-game feedback, and authorization to publish. See [third-party notices](THIRD_PARTY_NOTICES.md) for external tools and references.

## Quick start

1. Clone or download the repository. Give the entire directory to your agent with [SKILL.md](SKILL.md) as its entry point. For project-level discovery, copy the directory to `.agents/skills/mhwi-outfit-modding` in the target project.
2. Prepare a model and textures you may use, a compatible MHWI donor model with the target hunter rig, and Blender with MHW Model Editor installed. The integration was checked on Windows with Blender 4.3.2. Standalone ZIP and texture commands require Python 3.10+. PMX import requires compatible MMD Tools. DirectXTex's texconv can compress source images to DDS.
3. Copy the [example recipe](examples/build.json) into a separate working directory and replace the placeholder paths, mesh names, masks, bone IDs, and coordinates with values for your model. Verify a static export first, then add physics.

```powershell
git clone https://github.com/mastre1/mhwi-outfit-modding.git
Set-Location mhwi-outfit-modding
python scripts/nativepc.py inspect 'X:\work\outfit.zip' --full-set
```

The final command audits a full-set ZIP you already have. Omit `--full-set` for a partial outfit.

## Build an outfit

1. Run the Blender entry point `scripts/mhwi_blender.py` with `seed` to import donor MOD3s and an optional FBX or PMX. In the resulting scene, fit the source mesh to the donor rest pose, separate its materials into submeshes, assign them to the required export collections, and prepare skin weights and masks.
2. Run `build` on the prepared blend file with your JSON recipe. It can remap skin weights, adjust a masked area such as a forearm, and create or append CTC chains and CCL colliders. Pair each chain with the mesh and rig in the same equipment part, and verify that distal vertices follow the chain.
3. Pair each MOD3 with its MRL3 and required TEX files. Use `scripts/texture_material.py` for TEX/DX10 DDS conversion and fixed-size MRL3 name or texture-path changes. Use a separate namespace for custom textures so equipment ID changes leave their paths valid.
4. Run the Blender `audit` command to check material hashes and physics bindings. Use `scripts/nativepc.py pack` to build and verify the package. For a full outfit, check the helm, body, arm, waist, and leg slots. Verify motion and clipping in the game at the intended equipment ID.

| Guide | What it covers |
| --- | --- |
| [Build and verification](references/build.md) | PowerShell commands, rig fit, local edits, and export |
| [Physics](references/physics.md) | Chains, masks, tapered weights, colliders, and diagnostics |
| [File formats and materials](references/formats.md) | MOD3, MRL3, TEX, and equipment replacement paths |
| [Diagnostics](references/diagnostics.md) and [case study](references/case-study.md) | How to isolate symptoms, choose a fix, and verify the result |

The skill and detailed guides are written in Simplified Chinese. The command examples and JSON keys can be used as shown.

## Verification and contributions

```powershell
python -m unittest discover -s tests -v
```

The automated tests use synthetic data to check TEX round-trips, MRL3 retargeting, and ZIP layout. Blender readback and in-game cloth movement, collision, and clipping are separate checks for each outfit. See the [contribution guide](CONTRIBUTING.md) for reporting issues and submitting changes.

The [MIT License](LICENSE) applies to original repository code, documentation, examples, and tests. Obtain any models, textures, game assets, and third-party tools separately under their respective terms.
