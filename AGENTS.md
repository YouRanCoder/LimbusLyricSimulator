# AGENTS.md

Windows-only PyQt5 desktop app: Limbus-style floating lyric display synced to Chinese music players (NetEase Cloud Music, Kugou, QQ Music). Reads playback via SMTC (winrt) or the `netease-cloudmusic-detector` library. Will not work on Linux/macOS.

## Commands

- Setup: `uv sync` (uv is the only supported tool; there is no `requirements.txt`)
- Run: `uv run main.py`
- Logs: written to `log/` as `app_YYYYMMDD_HHMMSS.log` (UTF-8, configured in `config/logging_setup.py`); `log/` is gitignored. When the user reports a bug, ask for the latest log file.

## Architecture

- `main.py` is the entrypoint: wires `SettingsManager` → `LyricWindow` + `ControlPanel` → `AppController.set_ui()`, then runs a `qasync` event loop (PyQt5 + asyncio must share one loop).
- Layering is strict: `core/` (business) never imports `ui/`, and vice versa. `core/app_controller.py` is the only module that knows both sides.
- `config/` = settings persistence + defaults (`lyric_config.json` at repo root; defaults live in `config/settings.py`). `core/settings_manager.py` is the runtime wrapper.
- Fetcher factory: `select_fetcher()`/`create_fetcher()` in `core/fetcher.py`. Only `网易云音乐` maps to `FetcherByNetEase` (supports `CAP_PROGRESS`); all other players (QQ音乐, 酷狗音乐, custom) fall back to `FetcherBySMTC`, which has NO progress capability. Adding a new player is config-only (add to `lyric_config.json` `players`), and it will be SMTC-based unless it gets its own fetcher.
- Real playback progress polling (`QTimer` 200ms) in `app_controller.py` only activates when the current fetcher declares `CAP_PROGRESS`.

## Conventions & gotchas

- All comments, docstrings, log messages, and status strings are written in Chinese. Match this.
- **License**: the project is GPLv3 (see `LICENSE`). Reason: `ui/` is built on `PyQt-Fluent-Widgets` (GPLv3); keep that dependency and license in mind, do not re-introduce MIT-only claims.
- **UI stack**: `ui/control_panel.py` is a `qfluentwidgets.FluentWindow` with 4 navigation pages (`ui/pages/*`), built from Fluent `SettingCard` rows. `ui/lyric_window.py` + `ui/fading_line.py` are custom-painting overlays and deliberately do NOT use Fluent widgets.
- qfluentwidgets `ComboBox.addItem` signature is `(text, icon=None, userData=None)` — pass `userData=` as keyword, otherwise the second arg is treated as an icon.
- `test/` and `*.spec` are gitignored and not tracked; keep it that way.
- Packaging (PyInstaller `main.spec`, Nuitka) is dev-only; `pyproject.toml` has `[tool.uv] package = false`.
- `.python-version` pins 3.14; keep in sync with `requires-python`.
