# LimbusLyricSimulator

*项目灵感来源：[Limbus-Like-Lyric-Simulator](https://github.com/TempuraYMY0728/Limbus-Like-Lyric-Simulator)在此感谢[Tempura3](https://space.bilibili.com/3546955957406045)大佬开源的歌词显示方案*

# 已完成目标

* [X]  对原项目单个py文件的重构，使其易于二次开发
* [X]  使用SMTC服务代替了窗口句柄抓取

# 待实现目标

* [ ]  尝试获取播放进度（解决中途播放问题）
* [ ]  完成最小化到托盘，开机自启动
* [ ]  使用Nuitka代替PyInstaller打包,缩小体积
* [ ]  对项目结构进一步的优化解耦
* [ ]  使用PyRuff规范代码
* [ ]  解决歌词溢出屏幕的问题
* [ ]  一次显示多行歌词
* [ ]  异步网络请求

# 开发

本项目使用`uv`进行依赖管理，请clone项目之后进行：

```
uv sync
```

运行本项目：

```
uv run main.py
```

欢迎提交PR！
