@echo off

REM Build Borderless-Window-Utility using uv and PyInstaller
REM Ensures uv is installed, installs dependencies, then builds the one-file exe

pushd "%~dp0\.."

REM One-time installer for uv (safe to call multiple times)
call setup_once.bat

REM Install dependencies from pyproject.toml/uv.lock
uv sync

REM Build executable
uv run pyinstaller --onefile --noconsole --name "Borderless-Window-Utility" --distpath ".dist" --workpath ".temp" --specpath ".temp" main.py

popd
