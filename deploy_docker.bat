@echo off
chcp 65001 >nul
title Cocos RAG - Docker 一键部署

echo ===================================================
echo       Cocos RAG MCP Server Docker 一键部署脚本
echo ===================================================
echo.

:: 1. 检查 Docker 是否安装
where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Docker，请先安装 Docker Desktop。
    echo 下载地址: https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

:: 2. 检查 Docker 引擎是否正在运行
docker info >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] Docker 引擎未启动！
    echo 请先在系统托盘或开始菜单中打开 Docker Desktop，等待启动完毕后再重试。
    echo.
    pause
    exit /b 1
)

echo [信息] Docker 环境检测通过，准备构建并启动容器...
echo.

:: 3. 启动 docker-compose (兼容 docker compose 和 docker-compose)
docker compose version >nul 2>nul
if %errorlevel% equ 0 (
    docker compose up -d --build
) else (
    docker-compose up -d --build
)

if %errorlevel% neq 0 (
    echo.
    echo [错误] 容器构建或启动失败，请检查上方报错日志。
    pause
    exit /b 1
)

:: 4. 输出成功信息与连接指引
echo.
echo ===================================================
echo [成功] Cocos RAG 服务已在后台平稳运行！
echo ===================================================
echo.
echo [MCP 连接信息]
echo 你的 MCP 服务现在支持 SSE (Server-Sent Events) 模式。
echo 如果在本机连接，URL 为: http://localhost:8000/sse
echo.
echo 如果在其他电脑连接，请把 localhost 替换为这台机器的局域网 IP:
echo 例如: http://192.168.x.x:8000/sse
echo.
echo [管理指令]
echo 查看运行日志: docker logs -f cocos-rag
echo 停止服务:     docker compose down
echo.
echo 按任意键退出本窗口...
pause >nul
