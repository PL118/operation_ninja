@echo off
rem Lanceur Operation_ninja : se place dans le dossier du projet,
rem installe les dependances si besoin, puis demarre l'application.

cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Python est introuvable. Installez-le depuis https://www.python.org/
    pause
    exit /b 1
)

python -c "import flask, waitress" >nul 2>&1
if errorlevel 1 (
    echo Installation des dependances...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Echec de l'installation des dependances.
        pause
        exit /b 1
    )
)

python run.py %*

rem La fenetre reste ouverte si le programme s'est arrete sur une erreur.
if errorlevel 1 pause
