@echo off

REM Build Borderless-Window-Utility using uv and PyInstaller
REM Produces a console Textual app plus a silent headless helper exe

pushd "%~dp0\.."

REM One-time installer for uv (safe to call multiple times)
call setup_once.bat

REM Install dependencies from pyproject.toml/uv.lock
uv sync

REM Build Textual console executable
uv run pyinstaller --onefile --collect-data textual --collect-all rich --name "Borderless-Window-Utility" --distpath ".dist" --workpath ".temp" --specpath ".temp" main.py

REM Build silent headless executable for auto-apply workflows
uv run pyinstaller --onefile --noconsole --name "Borderless-Window-Utility-Headless" --distpath ".dist" --workpath ".temp" --specpath ".temp" main_headless.py

copy /Y "presets.ini" ".dist\presets.ini" >nul

popd
