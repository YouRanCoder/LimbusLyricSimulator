# LimbusLyricSimulator

> 灵感来源：[Limbus-Like-Lyric-Simulator](https://github.com/TempuraYMY0728/Limbus-Like-Lyric-Simulator)，感谢 [Tempura3](https://space.bilibili.com/3546955957406045) 开源的歌词显示方案。

# 使用说明

- **网易云音乐（3.0.0 以下版本）**：请安装 `infink-rs` 插件，然后取消勾选「使用网易云适配」。
  如果你的网易云过于卡顿，也请安装`infink-rs` 插件之后取消勾选「使用网易云适配」（这个问题实在是太玄学了）
- **酷狗音乐**：目前无法从 SMTC 服务读取播放进度，歌词只能从头播放。如需要进度同步，可考虑第三方如：[MoeKoeMusic](https://github.com/MoeKoeMusic/MoeKoeMusic)（第三方软件存在一定风险，请自行斟酌使用，注意保护个人信息）。
- **伴奏（Inst）过滤**：编辑 `lyric_config.json`，可以修改匹配伴奏的正则。

# 已完成

- [X]  将原项目重构为多模块结构，便于二次开发
- [X]  使用 SMTC 服务替代窗口句柄抓取
- [X]  控制面板基于 PyQt-Fluent-Widgets 重构（侧边导航分页 + Fluent 设置卡片）
- [X]  获取播放进度，解决中途播放的问题
- [X]  最小化到托盘、开机自启动
- [X]  进一步优化项目结构、解耦
- [X]  解决歌词溢出屏幕的问题
- [X]  支持一次显示多行歌词
- [X]  异步网络请求
- [X]  修复必须先打开音乐软件才能识别的问题
- [X]  修复对 Inst 类伴奏仍显示歌词的问题

# 待实现

- [ ]  使用 Nuitka 代替 PyInstaller 打包，缩小体积
- [ ]  使用 PyRuff 规范代码
- [ ]  修复退出音乐软件后打开另一个会触发非预期行为的问题
- [ ]  中英文同时演出

# 开发

本项目使用 `uv` 管理依赖，clone 之后执行：

```
uv sync
```

运行：

```
uv run main.py
```

欢迎提交 PR！如果喜欢本项目，还请点个 Star，感谢支持！

# 许可证

本项目基于 [GPL-3.0](LICENSE) 协议开源
