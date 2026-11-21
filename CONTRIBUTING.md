# 贡献指南 / Contributing

中文和英文均可。报告问题时，请写明 Blender、MHW Model Editor 和 Python 版本、执行命令、受影响的装备部位、预期结果和实际观察。涉及摆动或穿模时，请补充可复现的姿势、动作和视角。上传前去掉本地路径、账号和私人素材。

Issues and pull requests are welcome in Chinese or English. Include tool versions, the command, the affected equipment slot, and the expected and observed behavior. For motion or clipping issues, include the action, pose, and camera angle that reproduce the problem. Use synthetic fixtures or material you have permission to share.

- Run `python -m unittest discover -s tests -v` before submitting.
- Keep the examples and usage instructions in sync with script arguments.
- For Blender changes, give the version and the import, export, or readback steps you exercised. Identify in-game observations separately from offline checks.
- Disclose substantial AI assistance and review the resulting changes.
