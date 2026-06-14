#!/bin/bash
# setup.sh — Full project environment setup from scratch for Linux (Debian/Ubuntu)

# Exit immediately if a command exits with a non-zero status
set -e

echo "============================================="
echo " Starting Full Bot Environment Setup "
echo "============================================="

# 1. Update system packages
echo "--> Updating package lists..."
apt-get update -y

# 2. Install dependencies (Python3, pip, venv, ffmpeg, wget)
echo "--> Installing System Dependencies (Python3, pip, venv, ffmpeg, wget)..."
apt-get install -y python3 python3-pip python3-venv ffmpeg wget curl git

# 3. Install/Update yt-dlp globally
echo "--> Installing latest yt-dlp binary..."
if command -v wget >/dev/null 2>&1; then
    wget https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -O /usr/local/bin/yt-dlp || true
    chmod a+rx /usr/local/bin/yt-dlp
else
    echo "wget not available, installing yt-dlp via pip..."
    python3 -m pip install -U yt-dlp
fi

# 4. Create local virtual environment
echo "--> Creating Python virtual environment (.venv)..."
if [ -d ".venv" ]; then
    echo "    Virtual environment already exists, resetting it..."
    rm -rf .venv
fi
python3 -m venv .venv

# 5. Activate virtual environment and install requirements
echo "--> Installing python dependencies from requirements.txt..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 6. Ensure directories exist
echo "--> Creating necessary directories..."
mkdir -p downloads

echo "============================================="
echo " Setup Completed Successfully! "
echo "============================================="
echo ""
echo "To run the bot:"
echo "1. Activate the environment:  source .venv/bin/activate"
echo "2. Run main.py:              python main.py"
echo ""
python main.py
