---
name: mhwi-outfit-modding
description: 为《怪物猎人 世界／冰原》制作、改修或排查可改编号的猎人服装、全身外观和角色移植 MOD。适用于 Blender 与 MHW Model Editor 工作流，涵盖 FBX／PMX 预处理、MOD3 骨架映射和体态、MRL3／TEX 材质贴图、尾巴／裙摆／袖子 CTC 与 CCL、nativePC 打包及实机排查。在需要修复比例、穿模、只有部分物理生效、材质异常或改编号后失效时使用。
---

# 怪猎世界／冰原外观 MOD 制作

把整个技能文件夹交给接手者，打开此文件作为入口。需要项目级发现时，可将整份目录复制到该项目自己的 `.agents/skills/mhwi-outfit-modding` 中。下面的文件路径均相对于技能目录。

## 先确认输入

- 找到可用于当前用途的角色模型、纹理和作者声明。FBX 或 PMX 均可，优先选择已有可用骨架、清晰材质槽和适合当前用途的来源。保留原素材与已验收包，所有试验输出到单独工作目录。
- 找到同目标性别且结构可靠的 MHWI 原版或自有模型作为捐赠骨架和容器。参考 MOD 可以只读拆解并记录实际表现。骨架和材质容器提供技术接口，服装轮廓、风格和分件由当前模型决定。
- 准备本机 Blender、已可用的 MHW Model Editor、Python 3.10+。PMX 需要与本机 Blender 兼容的 MMD Tools。贴图重压需要 texconv 或 Model Editor 的转换能力。工具精确版本和启动方式见 [制作与验证](references/build.md)。

## 工作顺序

1. **拆解和建基线。** 审计捐赠骨架、装备路径、材质槽和可运行的物理路径。全身外观规划 `helm / body / arm / wst / leg` 五件，局部替换只打包需要的部位。默认编号用来交付，换号时整套同 stem 文件同步迁移。先用静态版证明几何、材质和路径正确。
2. **贴合静态模型。** 统一坐标和尺度，校对肩、肘、腕、髋、膝、踝与头颈，按语义映射权重并做站立、抬臂、握拳、跨步和蹲伏检查。服装、饰物和身体接缝一起看。反馈仅涉及一个局部时，按配量、小范围、带遮罩的方式修。见 [制作与验证](references/build.md)。
3. **匹配材质。** MOD3 材质名对应 MRL3 材质记录，再根据有效纹理槽配置 TEX。独立纹理命名空间随包分发，换装备编号时材质路径可保持稳定。见 [材质和文件结构](references/formats.md)。
4. **加物理。** 先做一条能验证的链，再为每片衣料绘制明确遮罩，按局部中心线布新骨。MOD3 必须含同一组功能 ID、正确的父子关系和非零网格权重，CTC 和 CCL 要随同 stem 导出。见 [新建物理与排错](references/physics.md)。
5. **交付。** 验证模型、材质哈希、物理 ID 和权重、纹理依赖与 ZIP 布局。以可由用户改编号的 `nativePC` ZIP 为主要交付，按需提供 Blender 检视工程。实机验收独立于离线读回。遇到具体症状时查看 [诊断与对照](references/diagnostics.md) 和 [外观移植案例复盘](references/case-study.md)。

## 可直接调用的文件

- [mhwi_blender.py](scripts/mhwi_blender.py) 导入捐赠件和源模型、列出可导出集合、运行配置、重新读取 MOD3 并校验同 stem 物理和材质。
- [rig_edit.py](scripts/rig_edit.py) 显式权重映射和局部径向轮廓微调，由 Blender 主脚本调用。
- [physics.py](scripts/physics.py) 建骨链、分配渐变权重、生成或追加 CTC／CCL，由 Blender 主脚本调用。
- [raw_profile.py](scripts/raw_profile.py) 用定长 MOD3 补丁做局部体态微调，由 Blender 主脚本的 patch-profile 调用。
- [texture_material.py](scripts/texture_material.py) MHWI TEX 与 DX10 DDS 转换，MRL3 检查和等长重定向。
- [nativepc.py](scripts/nativepc.py) 审计、展开和打包 nativePC ZIP。
- [构建配置](examples/build.json) 和 [材质重定向配置](examples/mrl-retarget.json) 给出字段和示例。按当前模型填写路径、组名、坐标、部件和骨号。

此技能整合项目内 `mhwi-blender-modding` 的导入导出、贴图和修模操作，以及 `mhwi-mod-anatomy` 的成品拆解、格式关系和诊断方法。
