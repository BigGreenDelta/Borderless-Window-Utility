@echo off

pushd %~dp0

if not exist ".venv" (
    echo Creating virtual environment...
    py -3.12 -m venv .venv
)

call .venv/Scripts/activate.bat

py -m pip install --quiet --disable-pip-version-check -r requirements.txt

py main.py --apply-and-exit

popd
