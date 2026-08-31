@echo off
REM ===========================================================================
REM  Injecte un cours (ZIP d'export) dans le LMS - en une commande, sans souris.
REM
REM    deploy_course.bat cours.zip                    (ajoute le cours)
REM    deploy_course.bat cours.zip --replace-all      (efface TOUT puis injecte)
REM    deploy_course.bat cours.zip --replace "IoT"    (remplace le cours "IoT")
REM
REM  100%% hors-ligne : aucun worker Celery requis, le ZIP source n'est pas modifie.
REM ===========================================================================
setlocal
cd /d "%~dp0"

if "%~1"=="" (
  echo Usage : deploy_course.bat ^<cours.zip^> [--replace-all ^| --replace "TITRE"]
  exit /b 1
)
if not exist "%~1" (
  echo Fichier introuvable : %~1
  exit /b 1
)

set "ZIP=%~1"
shift
set "ARGS="
:collect
if "%~1"=="" goto done
set "ARGS=%ARGS% %1"
shift
goto collect
:done

echo == Migrations (au cas ou le schema serait en retard) ==
python manage.py migrate --noinput

echo.
echo == Import du cours ==
python manage.py import_course "%ZIP%"%ARGS% -y

echo.
echo == Termine. Rechargez la page du catalogue pour voir le cours. ==
endlocal
