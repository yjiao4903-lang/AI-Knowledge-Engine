# M0 冒烟测试包装脚本：GPU 崩溃（0xC0000005 为进程级故障，无法在 Python 内捕获）时
# 自动以 CPU fallback 重跑，保证 M0 不被 GPU 问题阻塞。

$ErrorActionPreference = "Continue"
$VenvPython = "D:\AI-Knowledge-Engine\.venv\Scripts\python.exe"
$Root = "D:\AI-Knowledge-Engine"

Write-Host "==> Running M0 smoke test on GPU..."
& $VenvPython $Root\backend\scripts\m0_smoke_test.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "GPU smoke test passed."
    exit 0
}

Write-Host "==> GPU smoke test failed (exit=$LASTEXITCODE). Retrying with CPU fallback..."
& $VenvPython $Root\backend\scripts\m0_smoke_test.py --force-device cpu
if ($LASTEXITCODE -eq 0) {
    Write-Host "CPU fallback smoke test passed."
    exit 0
}

Write-Host "Smoke test failed on both GPU and CPU."
exit 1
