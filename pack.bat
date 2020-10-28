@echo off
set PATH=%~dp0\scripts;%PATH%

cd src
zipdir.py --output "../out/src.zip" || (pause & exit)

cd ..
zipdir.py || (pause & exit)

if not exist out mkdir out
cd out
creeper-installer.py-3.8.6.exe push app.zip creeper.exe || (pause & exit)

echo # build succeeded! #
pause
