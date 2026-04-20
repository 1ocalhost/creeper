@echo off
setlocal
set "PYTHONPYCACHEPREFIX=%TEMP%\pycache"
set "SCRIPTS=%~dp0\scripts"

py %SCRIPTS%\check_deps.py || call :_exit
py %SCRIPTS%\zipdir.py --dir src || call :_exit
py %SCRIPTS%\zipdir.py || call :_exit

if not exist out mkdir out
cd build_deps
creeper-installer.exe push python.zip ../out/installer.py.exe || call :_exit

cd ../out
py %SCRIPTS%\pack.py || call :_exit

@echo off
echo.
echo    ,_     _
echo     ^|\\_,-~/
echo     / _  _ ^|    ,--.
echo    (  @  @ ^)   / ,-'
echo     \  _T_/-._( (
echo     /         `. \\
echo    ^|         _  \ ^|
echo     \ \ ,  /      ^|
echo      ^|^| ^|-_\__   /
echo     ((_/`(____,-'
echo.
echo    Build succeeded!
timeout /t 1
exit

:_exit
echo.
pause
exit
