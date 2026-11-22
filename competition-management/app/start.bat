@echo off
chcp 65001 >nul
title 竞赛管理平台 - 启动器

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

echo.
echo  ============================================================
echo   数学建模比赛管理系统  ^|  一键启动
echo  ============================================================
echo.

rem 支持只启动单个服务：start.bat backend / start.bat frontend
if /i "%~1"=="backend"  goto start_backend
if /i "%~1"=="frontend" goto start_frontend

if not exist "%BACKEND%\.venv\Scripts\python.exe" (
    echo  [错误] 缺少后端虚拟环境：%BACKEND%\.venv
    echo  修复：在 backend 目录执行 python -m venv .venv 再 pip install -e .
    echo.
    pause
    exit /b 1
)

if not exist "%FRONTEND%\node_modules" (
    echo  [错误] 缺少前端依赖：%FRONTEND%\node_modules
    echo  修复：在 frontend 目录执行 pnpm install
    echo.
    pause
    exit /b 1
)

echo  启动后端 API  ......  http://127.0.0.1:8000
echo  启动前端页面  ......  http://127.0.0.1:5173
echo.
start "MMCM-Backend"  cmd /c call "%~f0" backend
start "MMCM-Frontend" cmd /c call "%~f0" frontend

echo  服务已在新窗口启动，约 6 秒后打开浏览器。
ping -n 7 127.0.0.1 >nul
start "" "http://127.0.0.1:5173"

echo.
echo  账号：admin@example.edu / teacher@example.edu / judge@example.edu
echo  密码：Passw0rd!
echo  接口文档：http://127.0.0.1:8000/docs
echo  停止服务：关闭两个服务窗口，或在窗口里按 Ctrl+C
echo.
pause
exit /b 0

:start_backend
cd /d "%BACKEND%"
title MMCM - 后端 API (8000)
"%BACKEND%\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
echo.
echo  后端已退出。
pause
exit /b 0

:start_frontend
cd /d "%FRONTEND%"
title MMCM - 前端页面 (5173)
call pnpm dev
echo.
echo  前端已退出。
pause
exit /b 0
