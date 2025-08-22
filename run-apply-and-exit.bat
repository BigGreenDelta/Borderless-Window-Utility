@echo off

pushd "%~dp0"

uv run python main.py --apply-and-exit

popd
