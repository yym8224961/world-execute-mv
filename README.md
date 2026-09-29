# world.execute(me); —ascii

![world.execute(me);](docs/images/mv-cover.png)

Mili《world.execute(me);》的字符动画。支持中英字幕、原曲同步播放和终端字符动画。

## 单文件运行（推荐）

从本仓库的 **Releases** 下载 `world-execute-mv-macos.zip` 并解压。音乐、动画、字幕、频谱数据和音频播放组件已经内嵌在 `world-execute-mv.pyz` 内，无需另外下载或指定 MP3。

需要 **macOS 12 或更新版本、Python 3.9 或更新版本**。音频组件同时包含 Apple Silicon 和 Intel 架构。终端播放器自身只使用 Python 标准库。

在 macOS「终端」中进入解压目录运行：

```sh
python3 world-execute-mv.pyz
```

也可双击 `运行单文件.command`，在系统终端中播放。按空格开始。推荐全屏，终端至少 64 列 × 24 行，128 列 × 44 行及以上效果更好。

```sh
# 从 2:38.7 开始直接播放
python3 world-execute-mv.pyz --start 158.7 --autoplay
```

内嵌音乐是随程序封装的资源，不是加密或 DRM。播放时会解包到当前用户的临时目录，正常退出后清理；不会读取旧电脑 Downloads 中的文件。运行过程无需联网。

## 操作

| 按键 | 功能 |
| --- | --- |
| 空格 | 开始／暂停 |
| 左／右 | 后退／前进 5 秒 |
| R | 从头播放 |
| Q | 退出 |
| H | 显示全部帮助 |
| 1–5 | 跳转章节 |

## 从源码运行

仓库不保存音频文件。从源码运行或重新打包前，请将自己的音频放到本地 `media/song.mp3`。使用 Release 播放包无需此步骤。

### macOS

首次构建音频组件需要 Apple Command Line Tools（含 Swift 编译器）：

```sh
xcode-select --install
```

然后执行：

```sh
./run.sh
```

启动脚本在缺少 `audio-clock` 时自动编译本机架构。双击 `播放MV.command` 可在 macOS 系统终端中运行源码版。

### Windows

需要 Windows 10 1809+ 与 [uv](https://docs.astral.sh/uv/)。依赖管理由 uv 完成，播放器本身仍只用 Python 标准库，音频走系统自带的 MCI 引擎（`audio_clock_win.py`，与 macOS 音频组件同一套进程协议）：

```sh
uv run player.py
```

建议使用 Windows Terminal，窗口至少 128 列 × 44 行。按键操作与 macOS 完全一致。运行 `uv run python tests/test_win_smoke.py` 可执行 Windows 冒烟测试（会短暂播放一段很轻的测试音）。

## 重新打包

```sh
python3 tools/build_bundle.py
python3 tests/test_bundle.py
```

构建输出在 `dist/`：

- `world-execute-mv.pyz`：内嵌音乐的单文件播放器。
- `world-execute-mv-macos.zip`：包含播放器、启动器、说明的分发包。
- `SHA256SUMS.txt`：下载校验值。

音频以 macOS 音频时钟驱动画面；暂停、跳转时字幕与动画跟随音频时间。构建会生成 universal 音频组件，并在单文件包内记录各资源 SHA-256 以检查完整性。

## 收录范围

本仓库为项目归档，包含当前播放器、字幕、频谱和构建工具。音乐仅内嵌于 Release 播放包。

原曲与歌词：Mili《world.execute(me);》。本项目是个人创作与备份，未对原曲、歌词或其他第三方素材授予额外使用许可。
