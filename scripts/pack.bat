@echo off

cd ..\src
..\scripts\zipdir.py
move /Y src.pyc ..
cd ..
scripts\zipdir.py
del src.pyc

echo.
echo # build succeeded! #
pause
