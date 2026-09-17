@echo off
chcp 65001 >nul
echo AI 비서 자동 시작을 해제합니다...

set VBS_FILE=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AI_Assistant_Hybrid.vbs

if exist "%VBS_FILE%" (
    del "%VBS_FILE%"
    echo 완료! 다음 부팅부터 자동 실행되지 않습니다.
) else (
    echo 자동 시작이 등록되어 있지 않습니다.
)
pause
