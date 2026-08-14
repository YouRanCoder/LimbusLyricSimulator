# LimbusLyricSimulator

*项目灵感来源：[Limbus-Like-Lyric-Simulator](https://github.com/TempuraYMY0728/Limbus-Like-Lyric-Simulator)在此感谢[Tempura3](https://space.bilibili.com/3546955957406045)大佬开源的歌词显示方案***

# 使用说明

如果你使用**3.0.0以下**的网易云，请安装`InfLink-rs`插件，之后取消勾选“使用网易云适配”

# 已完成目标

* [X]  对原项目单个py文件的重构，使其易于二次开发
* [X]  使用SMTC服务代替了窗口句柄抓取

# 待实现目标

* [X]  尝试获取播放进度（解决中途播放问题）
* [ ]  完成最小化到托盘，开机自启动
* [ ]  使用Nuitka代替PyInstaller打包,缩小体积
* [X]  对项目结构进一步的优化解耦
* [ ]  使用PyRuff规范代码
* [X]  解决歌词溢出屏幕的问题
* [X]  一次显示多行歌词
* [X]  异步网络请求
* [ ]  修复退出音乐软件打开另一个会发生非预期行为的问题
* [ ]  修复必须先打开音乐软件才能识别的问题

# 开发

本项目使用`uv`进行依赖管理，请clone项目之后进行：

```
uv sync
```

运行本项目：

```
uv run main.py
```

欢迎提交PR！如果喜欢请为我点一个Star，无比感谢
