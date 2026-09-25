@echo off
REM ============================================================
REM  STORM-SHIFT — avvio rapido (doppio click)
REM  Lancia lo script PowerShell completo, che gestisce
REM  credenziali, controllo porta e health-check.
REM ============================================================

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-StormShift.ps1" -OpenBrowser

REM Se qualcosa va storto, la finestra resta aperta per leggere l'errore
if errorlevel 1 (
    echo.
    echo [!] Avvio non riuscito. Leggi il messaggio qui sopra.
    pause
)
