@echo off

pushd %~dp0/..

call create_venv.bat -r requirements.txt

pyinstaller --onefile --noconsole --name "Borderless-Window-Utility" --distpath ".dist" --workpath ".temp" --specpath ".temp" main.py

popd
