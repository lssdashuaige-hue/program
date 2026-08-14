@echo off
chcp 65001 >nul
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0configure-supabase-secret.ps1"
