@echo off
chcp 65001 >nul
git pull
pip install -r requirements.txt
python -m playwright install chromium
python main.py
pause
