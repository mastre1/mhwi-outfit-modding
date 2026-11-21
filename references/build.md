
# 制作与验证

## 建立工作区和调用方式

找出 Blender 可执行文件和实际的插件模块名。在 Blender 插件管理处查看模块，或运行脚本让它搜索包含 `mhw_model_editor` 的模块。项目实测组合为 Blender 4.3.2 与 `MHW_Model_Editor-main`。使用其他发行版前确认其入口和导出行为。插件应安装在本地 Blender 用户环境，并在 UI 中可用。[MHW Model Editor](https://github.com/chikichikibangbang/MHW_Model_Editor)

以下 PowerShell 7 命令从技能目录运行。工作路径和输入用当前项目的实际值。所有导出目标用尚不存在的名字。配置内的相对路径以进程工作目录为基准。

```powershell
$Skill = (Get-Location).Path
$Blender = 'X:\Apps\Blender 4.3\blender.exe'
$Work = 'X:\work\outfit'
$Source = 'X:\assets\character.fbx'
$Donor = 'X:\game-extract\pl\f_equip\pl123_0000'
$Entry = Join-Path $Skill 'scripts\mhwi_blender.py'
$env:MHWI_ADDON = 'MHW_Model_Editor-main'
$env:PYTHONUTF8 = '1'

& $Blender -b --factory-startup --python-exit-code 13 --python $Entry -- seed "$Work\seed.blend" --source $Source --donor "helm=$Donor\helm\mod\f_helm123_0000.mod3" --donor "body=$Donor\body\mod\f_body123_0000.mod3" --donor "arm=$Donor\arm\mod\f_arm123_0000.mod3" --donor "wst=$Donor\wst\mod\f_wst123_0000.mod3" --donor "leg=$Donor\leg\mod\f_leg123_0000.mod3"
if ($LASTEXITCODE) { throw 'Seed failed' }

& $Blender -b --factory-startup "$Work\ready.blend" --python-exit-code 13 --python $Entry -- layout
```

若插件自动识别成功可省略环境变量。也可将 `--addon 实际模块名` 放在 `seed / build / audit` 前。PMX 用 `--source 源文件.pmx --mmd-addon 实际模块名`。遇到 PMX 插件版本差异时，在 Blender UI 导入再 Append。用 `seed` 只导捐赠件时可省略 `--source`，再追加现有 Blender 工程。原版提取件包含用于校对的骨架和装备路径。[游戏文件提取说明](https://github.com/Ezekial711/MonsterHunterWorldModding/wiki/Extracting-Game-Files)

从合法工作副本拆解旧包或参考包。输出是新目录。开启 `--full-set` 时检查五件齐备，拆单件时省略。

```powershell
$Pack = Join-Path $Skill 'scripts\nativepc.py'
python $Pack inspect "$Work\reference.zip"
python $Pack unpack "$Work\reference.zip" "$Work\reference-unpacked"
```

## 静态贴合与分件

1. 在 Blender 开 `seed.blend` 后另存为 `ready.blend`。比较源模型 A／T 姿、原素材正侧面和捐赠骨架 rest pose。统一朝向、尺寸和对象变换，检查倒法线、非预期负缩放、骨架和网格坐标是否同系。保留源模型的 UV、alpha 和形态键所需的顶点结构。打开两视图对齐头颈、胸、髋、肩、肘、腕、掌根、膝和鞋底。贴合要同时看关节和衣服连缀，重点对齐自然活动支点。
2. 把源几何调整到当前捐赠骨架的静置姿态，避免源的 A/T 姿直接按原权重导出。可按肩到腕、髋到膝到踝分段，用源 rig 摆到目标 rest 后在副本上烘入网格，再按部件重绑。需要放大或压窄某段体型时，对皮肤及贴合层共用平滑映射，以肩、肘、腕等结构为界。跨部件同时调整时逐一核对共同坐标、关节和边缝。大幅改骨基线会影响游戏动画，优先贴合网格，已有充分读回和姿态证据时再动基础骨。
3. 每个导出件只放一个捐赠 Rig。处理集合中的占位和原壳网格，将准备好的目标网格移到该部件的 LOD 集合。保留捐赠件头属性、LOD 及 mesh group 约定。单材质一子网格，常见名称 `LOD_ALL_Group_0_Sub_0__MyMod_Cloth`；在 UI 对照导入后的骨架、LOD 集合和对象自定义属性。以实际模型约定为准。导出器默认读对象名 `__` 后的材质名，配置 `use_blender_material_names` 为真时优先取第一个 Blender 材质槽，两路都以首个点为分隔。使用无点的 ASCII 短名称。
4. 权重优先依原绑定语义映射，面部、发片、胸背、胯、腿、袖口、手和配件逐区处理。身体贴合层可在对应肢体做最近面及重心插值。选定区域后才启用 BVH 最近面，避免跨吸到另一条腿、手掌或裙层。紧贴关节的层沿同一处权重缝过渡，硬装饰控制为相近骨骼。独立长条衣料先由合理体骨承重，确认静态无误再加物理。检查正权重、归一化、最大影响数、反转面、极端插值与 UV。
5. 若源已带姿态合适的权重，可在构建 JSON 加 `retarget`。列出当前场景中 `rig`、`objects`、每个源组到编号的 `groups`，和需保留下来的辅助 `ignore_groups`。多对一会合并并按四权重或八权重限制归一化。未声明的非零组会报错。此操作重绑到目标 Rig。执行前完成静置贴合，并在保存后的检视工程检查变形。源模型无权重时先在 Blender 分区权重转移或手工涂。
6. 全身包用五件容器交付。根据分件决定是否把主体装入一个槽，其他槽使用极小、闭合或处于体内的带权重占位。这有助于控制游戏自行加载的默认网格。检查原版游戏当前的装备号、外观和头脸显示规则，再决定是否要携带 `.evbd`、`.evhl`。参考文件里存在同名标志不等于目标需要。空部件试装时要留意头发、原皮肤或内衣透出。[装备编号](https://github.com/Ezekial711/MonsterHunterWorldModding/wiki/Armor-IDs)

## 比例修订

**成品只差一点时保住已通过验收的边界。** 小臂变粗通常比整体缩手更符合手臂连续性，也降低手指、握武器、护腕和动画受影响的范围。判断依据是正面和侧面轮廓、腕部锥度和实际肘腕关节位置。如果小臂形状合理且真正缺陷在掌宽，再单独查手与武器握点。

1. 隔离皮肤子网格或给需要变化的顶点画一个独立 `PROFILE` 权重组。袖子和手没有调整需求时从选区移出。对最细的截面看前后左右，沿肘到腕取截面中心。用两个中心点建立近似轴，若弯曲明显优先沿多截面建中心线手工细调，或分多个不重叠的区域。
2. 在示例 JSON 的 `radial` 中填写 Blender 世界坐标（米）、遮罩和 `gain`。`window` 的四个 0–1 参数依次对应开始、达到最大、开始回落、归零。典型初值是约 8%–12% 径向变化，使用 `max_delta_m` 限制实际位移。部件带形态键时脚本给每一个 key 加相同的局部位移，保持现有相对位移。脚本修改几何后由插件重建导出所需数据，已有自定义 split normals 时先检查是否导致明暗边。
3. 修改前后比较肩肘腕和手轮廓、袖口、接缝和姿态。用手臂屈伸、扭转和持械检查近接触区域。可在 Blender 编辑或脚本用 `BVHTree.FromObject` 取袖面与皮肤的三角形交集，在同一组姿势前后对照新增交集。缝合边或故意重合的层先标记，以免把原来的交叠当回归。骨骼、姿态、顶点权重及已验收物理可从原版本复用。
4. 对于必须逐字节保留既有 MOD3 结构的微修，先冻结基线，再使用附带的就地格式补丁方法，详见 [文件结构](formats.md)。一般项目以 Blender 工作工程重新导出为更易检查和迭代的路线。

## 构建、纹理和打包

把 [build.json](../examples/build.json) 复制到工作区。按模型实际对象名和组名重写或移除示例块。示例默认展示一个带物理的 body，制作五件时按同一结构添加其他四个槽。每个要交付的槽提供匹配的 `mrl3`，物理只在拥有相应网格和骨架的槽填写。用 `ctc` 和 `ccl` 复用既有 sidecar，或用 `physics` 创建与追加，二者择一。使用 `--scene-output` 另存可查阅的已修改场景。若在该场景上继续修，仅填写下一步增量配置，已执行的增加骨链配置会拒绝重复 ID。另交独立检视工程时可用 Blender 的 Pack Resources 收齐有权携带的外部贴图。

```powershell
& $Blender -b --factory-startup "$Work\ready.blend" --python-exit-code 13 --python $Entry -- build "$Work\build.json" "$Work\export" --scene-output "$Work\inspection.blend"
if ($LASTEXITCODE) { throw 'Model export or readback failed' }

$Mod = "$Work\export\nativePC\pl\f_equip\pl123_0000\body\mod\f_body123_0000.mod3"
& $Blender -b --factory-startup --python-exit-code 13 --python $Entry -- audit $Mod --check-mrl
if ($LASTEXITCODE) { throw 'Model audit failed' }

Copy-Item -LiteralPath "$Work\MyOutfit" -Destination "$Work\export\nativePC" -Recurse
python $Pack pack "$Work\export" "$Work\outfit.zip" --full-set --texture-namespace MyOutfit/textures
if ($LASTEXITCODE) { throw 'Packing failed' }
python $Pack inspect "$Work\outfit.zip" --full-set --texture-namespace MyOutfit/textures
```

本例 `MyOutfit` 目录装的是材质引用的自有 TEX。原版共享纹理只引用游戏已经提供的路径。只借原版纹理时可省略自有命名空间检查。可先用 Blender audit 的 active_texture_slots 决定保留哪些实际引用，再整理模板的闲置路径。把可识别的预览或说明放在 ZIP 外，交付时 ZIP 内从 `nativePC/` 开始。现存编号由用户用狩技盒子等改编号和安装，改完检查安装目录与源 ZIP 对应模型和所有同 stem sidecar，具体方法见 [文件结构](formats.md)。

## 验收证据

- **离线几何。** 正面、侧面、背面和局部，实际休息姿势与持械、跑步／跨步、手肘弯曲、下蹲、武器挂背等代表姿态。记录可以复现穿插或拖拽的姿势。优先处理关节、服装开口、腿间前片、裙边和手部接触。
- **导出读回。** 核对网格、面数、LOD 和所有新增 CTC 节点功能 ID 及蒙皮影响。MOD3 读回会列同 stem MRL3、CTC／CCL 概况，并拒绝缺失物理骨或无远端权重的链。确认编号、贴图路径、透明类型、活动纹理、ZIP CRC 和五件齐备情况。
- **实机。** 在同一个可复现姿势和地点看首选目标编号，分别测静止、起跑、停步、转向、收放武器及换区。在暗处和强光下都看衣料、发片和眼睛。视频比单帧更能证明裙袖在运动。未实机时如实标为离线验证。
