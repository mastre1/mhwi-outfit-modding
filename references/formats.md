
# 文件结构、材质和贴图

## 拆解参考包

| 对象 | 重点记录 |
|---|---|
| MOD3 | 性别、部件、LOD、面数、组、实际材质名、功能 ID 和权重，参考件肩肘腕与髋膝踝静置变换 |
| MRL3 | MOD3 材质名的哈希、MMTR 材质类型、纹理资源的槽位及索引、透明和常量参数 |
| TEX | 尺寸、色彩空间、压缩、mip 与 alpha，是否取自包内独立命名空间 |
| CTC／CCL | 与 MOD3 匹配的动态功能 ID、每链节点、碰撞端点、文件的实际挂载槽 |
| EVBD／EVHL | 游戏的身体或头部显示规则，带了哪些可见性标志，以及是否对本案例有必要 |

女装路径通常是 `nativePC/pl/f_equip/pl123_0000/body/mod/f_body123_0000.mod3`，男性换 `m`；其他槽为 `helm / arm / wst / leg`。同槽 `mrl3 / ctc / ccl` 共享同一文件 stem。源包默认编号与用户最终改号是两件事。纹理目录如 `nativePC/MyOutfit/textures/cloth_albedo.tex`，MRL3 内用 `MyOutfit\textures\cloth_albedo`。安装变更由用户现有工具完成。合理选择真实可测试的编号。[装备编号一览](https://github.com/Ezekial711/MonsterHunterWorldModding/wiki/Armor-IDs)

## MRL3 材质路由

1. 先把源贴图区分为肤色、头发、眼睛、衣料、金属、半透明／镂空、发光等材质。先挑对应效果的原版或自有工作模板。皮肤、发片和透明服装往往需要不同的 MMTR。直接套相同模板会导致发片黑边、双层玻璃、过曝、错误高光或通道错位。
2. 需要新增材质、换 shader、改 alpha 或调常量时用 Model Editor 编辑 MRL3 从兼容模板复制槽，再改纹理和透明参数。保存后重新读回、看活动纹理。已有可用槽只换名字或路径时，脚本可做定长替换，保留原模板的 shader、属性、索引和大小。共享模板中同一个 texture table 条目被多个材质引用时会全量替换，若需要每个材质独立纹理应在插件拆槽后再导出。
3. MOD3 材质使用安全的 ASCII 短名。MHWI 常用材质哈希为 `crc32(ASCII 名称) XOR 0xffffffff`。输出时名称大小写和源记录一一对应。不要用 Blender 自动出的 `.001` 作为意图区分，导出器会去掉点后的部分。
4. MRL3 纹理表中某一条路径可能有多个引用，也可能没有任何活动使用。严格区分存在于全局槽表与活动材质所引用的 TEX。用插件的 MMTR 资源字典或 UI 确认目标材质实际使用槽。保留合法的原版共享资源引用，自有纹理必须在 ZIP 的相应目录里。
5. Alpha 在源图中有用途时保留，验证其语义是镂空阈值、渐变透明还是控制其他属性。看源文件、UV 和材质模板。眼睛或发尾材质出错先隔离 shader、透明和贴图索引，避免无依据地去掉 alpha。

```powershell
$Tex = Join-Path $Skill 'scripts\texture_material.py'
python $Tex mrl-info "$Work\template.mrl3"
python $Tex mrl-retarget "$Work\template.mrl3" "$Work\MyOutfit_body.mrl3" --recipe "$Work\mrl-retarget.json"
```

[材质配置例](../examples/mrl-retarget.json) 的键要与当前模板中的路径与名称完全匹配。定长脚本面向 MRL v12 的常见模型。以本机 MHW Model Editor 实际 parser 和模板为准。[MHW Model Editor](https://github.com/chikichikibangbang/MHW_Model_Editor)

## TEX 贴图

| 用途 | 常用压缩 | 游戏 TEX 编号 |
|---|---|---|
| Albedo、发光颜色 | BC7_UNORM_SRGB，保留必要 alpha | 31 |
| 两分量法线 | BC5_UNORM，线性，绿通道取向按 shader 和素材验证 | 26 |
| 混合粗糙度／金属／遮罩 | BC7_UNORM，线性，通道按 MMTR | 30 |
| 原版历史格式、普通色块或 HDR | BC1／BC6H 仅按模板或实际需求 | 22、23／28 |

1. 确认原图颜色空间和用途。Albedo／发光从 sRGB 艺术源得到；NM、遮罩和混合数据保持线性。法线外观凹凸反向时检查绿通道和 UV 切线。不要套用颜色校正到数据通道。大块连续 alpha 通常从已有成功样本的压缩和模板开始试。
2. 给 DDS 生成完整 mip，查看远处透明边、白边、UV 岛的外扩留边和小纹理误染。保持贴图对齐且优先合理使用 2 的幂；不用为了对齐随意拉伸源图或改变 UV。
3. 优先使用插件内转换。命令行流程用 texconv 将源图压成 DX10 DDS，再给脚本一张**已知可用且同格式同用途**的 TEX 作为头模板。脚本适用于单层二维 TEX。其他平台、数组、立方、特殊对齐或版本先用相应插件转换和验证。[texconv 参数](https://github.com/microsoft/DirectXTex/wiki/texconv)

```powershell
$Texconv = 'X:\Tools\texconv.exe'
$DdsDir = "$Work\dds"
& $Texconv -dx10 -f BC7_UNORM_SRGB -srgb -m 0 -o $DdsDir "$Work\cloth_albedo.png"
if ($LASTEXITCODE) { throw 'Albedo compress failed' }
& $Texconv -dx10 -f BC5_UNORM -m 0 -o $DdsDir "$Work\cloth_normal.png"
if ($LASTEXITCODE) { throw 'Normal compress failed' }
python $Tex dds-to-tex "$DdsDir\cloth_albedo.dds" "$Work\MyOutfit\textures\cloth_albedo.tex" --template "$Work\known_BC7_sRGB.tex"
python $Tex dds-to-tex "$DdsDir\cloth_normal.dds" "$Work\MyOutfit\textures\cloth_normal.tex" --template "$Work\known_BC5.tex"
python $Tex tex-info "$Work\MyOutfit\textures\cloth_albedo.tex"

# 拆回 DDS 供 DDS 编辑器或 texconv 检视
python $Tex tex-to-dds "$Work\MyOutfit\textures\cloth_albedo.tex" "$Work\albedo-check.dds"
```

TEX v16 二进制读回，常见单面 2D 模板头长 184，mip 个数／宽／高／层数／格式为 20／24／28／32／36 处的 u32。每级的通常是绝对偏移及一个零的高位，共 8 字节。从 184 开始，最后一项以后为压缩数据。BC1 每个 4×4 块 8 字节，BC5／BC6H／BC7 每个 4×4 块 16 字节，各级尺寸最小用 1 像素并以块向上取整。颜色标志与重复宽度字段由脚本用同格式模板重建。

MRL3 v12 头长 40，材质／纹理记录数是 16／20 的 u32；纹理／材质表偏移是 24／32 的 u64。纹理条目 272，路径起于条目 +16，可用 256 字节。材质条目 56，名称／MMTR／shader 哈希在 +4／+8／+12，资源块长度 +16，资源数在 +22 的 u16 且以实际条目×2 储存，绝对资源偏移在 +48。资源记录为四个 u32，第二项右移 12 匹配 MMTR 资源键，第三项对纹理槽是从 1 开始的表索引，对常量缓冲是块内地址。[Model Editor 格式实现](https://github.com/chikichikibangbang/MHW_Model_Editor)

## MOD3 小范围字节补丁

已有已验收的 MOD3，且目标是**只改一个分件的局部截面**时，优先试同尺寸补丁保留原权重、三角面、LOD、UV、骨架、同 stem 物理与全部其他文件。这条路线适合直轴附近的小臂等孤立皮肤段；同一子网格有互不相关的顶点落到轴向窗口时改用 Blender 遮罩。若要改身体边界、接缝、曲线跨部件布局或权重，回到 [制作与验证](build.md) 的工程路线。

1. 用 `audit` 查选定子网格的物理 `mesh_index`、材质和顶点数。在 Blender 静置视图检查世界坐标，给当前肘腕或截面填两点，设平滑窗口和最大允许位移。[局部补丁例](../examples/raw-profile.json)
2. 在新路径运行补丁。脚本限制 MOD3 v237，要求位置和法切线字段符合布局，检查新点在原全局 AABB、球和有效组球内，再依据受影响骨局部空间重算原包围记录。超出原界或涉及不存在的包围表时使用完整重导出。
3. 把导出的单件放进工作副本，恢复原同 stem 的其他 sidecar 和路径，再跑 `audit --check-mrl` 和动作检视。检查 byte diff 范围只覆盖选定分件位置、法切线和相应包围盒。模型变化应在固定且可复现的姿势中比较，并记录袖面和皮肤是否新增相交。

```powershell
& $Blender -b --factory-startup --python-exit-code 13 --python $Entry -- audit $Mod --check-mrl
& $Blender -b --factory-startup --python-exit-code 13 --python $Entry -- patch-profile $Mod "$Work\raw-profile.json" "$Work\body-profile-test.mod3"
if ($LASTEXITCODE) { throw 'Local MOD3 patch failed' }
```

布局依据如下。MOD3 v237 的 48、56、64、72、80、88 是骨、组、材质、mesh、顶点、面表起点的 u64。mesh 记录 80 字节。每个顶点区开始于头顶点起点加网格 `vertexOffset + blockSize × (vertexSub + vertexBase)`。从插件块字典查询 Position 和 NorTan 的真实位置。小改在原空间定义平滑径向映射。切线乘形变 Jacobian，法线乘逆转置，归一化后正交化切线并保留原切线符号字节。骨包围表为 `meshOffset + 80 × meshCount + 4`，每条 144 字节。对触及的骨，将当前受其影响的分件顶点按原骨世界矩阵的逆变到骨局部，重建该条 sphere／AABB／OBB，保留记录开头的索引和填充。出表前后按小端格式和原文件读回核对。[MOD3 读取与导出实现](https://github.com/chikichikibangbang/MHW_Model_Editor)

## 改号后的排查

用户用狩技盒子换好编号后，以改号版本的包或干净安装树为基线。对照 `Get-FileHash -Algorithm SHA256 -LiteralPath ...` 检查是否漏装同 stem sidecar 或被另一包覆盖。比较时以工具输出为准，允许工具合法地变更路径。先以实机能动部件作为基准，再检查没有效果的具体网格、骨号和权重。在五件齐备且文本路径正确时继续核对实际绑到的装备和 MRL3 活动资源，而不是反复改共同材质。
