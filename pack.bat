@echo off
set PATH=%~dp0\scripts;%PATH%

check_deps.py || call :_exit
zipdir.py --dir src || call :_exit
zipdir.py || call :_exit

if not exist out mkdir out
cd build_deps
creeper-installer.exe push python.zip ../out/installer.py.exe || call :_exit

cd ../out
pack.py || call :_exit

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
