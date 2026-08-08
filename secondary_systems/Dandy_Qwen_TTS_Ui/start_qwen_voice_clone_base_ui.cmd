@echo off
set "QWEN_VENV=R:\R_Drive_Substrate\Services\qwen_tts_312"
set "QWEN_ENGINE=R:\R_Drive_Substrate\Services\qwen_engine"
set "SOX_DIR=C:\Users\bryan\AppData\Local\Microsoft\WinGet\Packages\ChrisBagwell.SoX_Microsoft.Winget.Source_8wekyb3d8bbwe\sox-14.4.2"
set "PATH=%SOX_DIR%;%PATH%"
cd /d "%QWEN_ENGINE%"
"%QWEN_VENV%\Scripts\python.exe" -m qwen_tts.cli.demo Qwen/Qwen3-TTS-12Hz-1.7B-Base --ip 127.0.0.1 --port 8002 --device cuda:0 --dtype float16 --flash-attn
