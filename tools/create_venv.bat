pushd %~dp0/..

if not exist ".venv" (
    echo Creating virtual environment...
    py -3.12 -m venv .venv
)

call .venv/Scripts/activate.bat

if not "%~1"=="" py -m pip install --quiet --disable-pip-version-check %*

popd
