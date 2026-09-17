@echo off
chcp 65001 >nul
echo ================================================
echo    AI 비서 (하이브리드) 자동 시작 설정 도구
echo ================================================
echo.

:: Python 설치 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 먼저 설치해주세요.
    echo 설치 시 [Add Python to PATH] 체크박스를 꼭 선택하세요!
    pause
    exit /b 1
)
echo [1/4] Python 확인 완료!

set SCRIPT_DIR=%~dp0
set LAUNCHER=%SCRIPT_DIR%launcher.pyw

if not exist "%LAUNCHER%" (
    echo [오류] launcher.pyw 파일을 찾을 수 없습니다.
    echo 이 배치 파일과 launcher.pyw가 같은 폴더에 있어야 합니다.
    pause
    exit /b 1
)
echo [2/4] 스크립트 경로 확인 완료! (%LAUNCHER%)

:: 의존성 설치
echo [3/4] 필요한 패키지를 설치합니다... (인터넷 연결 필요, 시간이 걸릴 수 있어요)
pip install -r "%SCRIPT_DIR%requirements.txt"
if errorlevel 1 (
    echo [경고] 일부 패키지 설치에 실패했을 수 있어요. 위 오류 메시지를 확인해주세요.
)

:: Windows 시작프로그램 등록 (창 없이 백그라운드 실행되는 VBS 사용)
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set VBS_FILE=%STARTUP_DIR%\AI_Assistant_Hybrid.vbs

echo Set objShell = CreateObject("WScript.Shell") > "%VBS_FILE%"
echo objShell.CurrentDirectory = "%SCRIPT_DIR%" >> "%VBS_FILE%"
echo objShell.Run "pythonw ""%LAUNCHER%""", 0, False >> "%VBS_FILE%"

echo [4/4] 시작프로그램 등록 완료!
echo.
echo ================================================
echo  설정이 완료되었습니다!
echo ================================================
echo.
echo - 다음 부팅부터 AI 비서 창이 자동으로 뜹니다.
echo - 지금 바로 실행하려면:
echo     pythonw "%LAUNCHER%"
echo - 자동 시작을 해제하려면 remove_startup.bat 을 실행하세요.
echo - 처음 실행 후 창 안의 ⚙ 설정에서 Anthropic API 키를 등록하면
echo   자유 대화 기능도 사용할 수 있어요.
echo.
pause
