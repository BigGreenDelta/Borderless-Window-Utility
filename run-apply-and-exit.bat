@echo off

pushd %~dp0

call tools/create_venv.bat -r requirements.txt

py main.py --apply-and-exit

popd
