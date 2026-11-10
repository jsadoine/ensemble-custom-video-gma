@echo off
REM Double-cliquer sur ce fichier pour lancer le pipeline vidéos -> BIDS.
REM Utilise config.toml s'il existe dans ce dossier, sinon pose les questions.
chcp 65001 > nul
cd /d "%~dp0"
if exist config.toml (
    pixi run python pipeline.py config.toml
) else (
    pixi run python pipeline.py
)
echo.
pause
