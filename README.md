# MHWI Outfit Modding

[English README](README.en.md) · [技能入口](SKILL.md) · [MIT 许可证](LICENSE)

一套面向《怪物猎人 世界／冰原》的 Blender 外观 MOD 制作技能和脚本。使用自备角色模型，制作可改装备编号的猎人外观。流程涵盖骨架和权重、体态微调、尾巴／裙摆／袖子物理、材质贴图和 `nativePC` 打包。

> **AI 制作声明**：本项目初始公开版本的工作流、代码、文档、示例和测试均由 AI 全程制作。项目维护者提供需求、实机反馈和发布授权。第三方工具和参考资料见[来源与致谢](THIRD_PARTY_NOTICES.md)。

## 快速开始

1. 克隆或下载仓库。交给代理时，将整个目录复制到目标项目的 `.agents/skills/mhwi-outfit-modding`，或者直接让代理读取 [SKILL.md](SKILL.md)。
2. 准备有权使用的模型和贴图、对应猎人骨架的 MHWI 捐赠模型，以及安装了 MHW Model Editor 的 Blender。集成流程在 Windows 上用 Blender 4.3.2 验证。命令行贴图和 ZIP 工具需要 Python 3.10+。PMX 导入另需兼容版本的 MMD Tools，手工压缩 DDS 可使用 texconv。
3. 按[制作手册](references/build.md)完成静置贴合和分件。把[构建示例](examples/build.json)复制到工作目录，填写当前模型的实际路径、网格名、骨号、遮罩和节点坐标。先验证静态版，再加物理。

```powershell
git clone https://github.com/mastre1/mhwi-outfit-modding.git
Set-Location mhwi-outfit-modding
python scripts/nativepc.py inspect 'X:\work\outfit.zip' --full-set
```

最后一条命令检查已有的五件套 ZIP。检查单件或部分装备时可省略 `--full-set`。

## 制作手册

| 任务 | 文档 |
| --- | --- |
| 导入、骨架贴合、体态调整与导出 | [制作与验证](references/build.md) |
| 新建或追加裙摆、袖子与尾巴骨链，配置碰撞 | [物理制作](references/physics.md) |
| 匹配 MRL3、制作 TEX、核对改号路径 | [文件结构和材质](references/formats.md) |
| 排查穿模、僵硬裙袖、斑驳暗影和异常高光 | [诊断与对照](references/diagnostics.md) · [案例复盘](references/case-study.md) |

## 验证与贡献

```powershell
python -m unittest discover -s tests -v
```

自动检查使用合成数据，覆盖 TEX 往返、MRL3 重定向和 ZIP 布局。完成具体作品后，还要做 Blender 导出读回和游戏内摆动、碰撞与穿模检查。欢迎用可公开的最小复现提交 Issue 或 PR。参见[贡献说明](CONTRIBUTING.md)。

[MIT](LICENSE) 适用于本仓库发布的原创文档、脚本、示例和测试。模型、贴图、游戏资源和第三方工具需自行取得并遵循各自的条款。
