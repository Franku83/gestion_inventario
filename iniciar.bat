@echo off
title Inventario Joyas
setlocal

REM Ir a la carpeta donde está este .bat (y manage.py)
cd /d "%~dp0"

REM Activar el entorno virtual
call "%~dp0venv\Scripts\activate.bat"

REM Verificación rápida (muestra el python del venv)
where python
python -c "import django; print('Django OK:', django.get_version())"

REM Migraciones (opcional)
python manage.py migrate

echo.
echo ==========================================
echo   Inventario Joyas iniciado
echo   Abre en el navegador:
echo   http://localhost:8000/
echo ==========================================
echo.

python manage.py runserver 0.0.0.0:8000

pause
endlocal
