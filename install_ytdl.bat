@echo off
echo === Installing yt-dlp and ffmpeg on Windows via winget ===

echo Checking for winget...
where winget >nul 2>nul
if %errorlevel% neq 0 (
    echo Winget is not installed. Please install yt-dlp manually or run: pip install -U yt-dlp
    pause
    exit /b
)

echo === Installing ffmpeg (required for format merging) ===
winget install Gyan.FFmpeg --silent --accept-source-agreements --accept-package-agreements

echo === Installing yt-dlp ===
winget install yt-dlp --silent --accept-source-agreements --accept-package-agreements

echo === Done! Please restart your terminal/command prompt to apply changes. ===
pause
