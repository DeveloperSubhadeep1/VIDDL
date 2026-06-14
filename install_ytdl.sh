#!/bin/bash
# Install script for yt-dlp and ffmpeg on Linux (Debian/Ubuntu)

echo "=== Updating package list ==="
sudo apt-get update

echo "=== Installing ffmpeg (required for merging audio/video) ==="
sudo apt-get install -y ffmpeg

echo "=== Installing/Updating yt-dlp ==="
# Downloading the latest binary directly from GitHub is recommended over apt-get (which gets outdated)
sudo wget https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -O /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp

echo "=== Verification ==="
yt-dlp --version
ffmpeg -version | head -n 1

echo "Done! yt-dlp and ffmpeg are installed successfully."
