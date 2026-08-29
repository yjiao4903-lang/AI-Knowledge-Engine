# Backend 依赖安装脚本（Windows / PowerShell）
# 依赖管理方案：pip + pyproject.toml + backend/requirements-lock.txt
#
# 顺序很重要：必须先装 AMD ROCm torch，再装其余依赖，
# 否则 pip 会从 PyPI 拉入 CUDA/CPU 版 torch 覆盖 ROCm 版。
#
# 版本裁决（M0 实测）：
#   torch==2.9.1+rocm7.13.0 + rocm-sdk 7.13.0（legacy stable index）
#   不要升级到 rocm-sdk 10.0.0 / whl-next —— 其 Windows HIP runtime 在
#   kernel launch 时存在 0xC0000005 崩溃回归（TheRock issue #4958 一类）。

$ErrorActionPreference = "Stop"
$VenvPython = "D:\AI-Knowledge-Engine\.venv\Scripts\python.exe"
$TorchIndex = "https://repo.amd.com/rocm/whl-multi-arch/"

Write-Host "==> Step 1: install PyTorch ROCm 7.13.0 (gfx1100) from AMD legacy stable index"
& $VenvPython -m pip install --index-url $TorchIndex `
    "torch==2.9.1+rocm7.13.0" `
    "amd-torch-device-gfx1100==2.9.1+rocm7.13.0" `
    "rocm-sdk-core==7.13.0" `
    "rocm-sdk-libraries==7.13.0" `
    "rocm-sdk-device-gfx1100==7.13.0"

Write-Host "==> Step 2: install backend dependencies from pyproject.toml"
& $VenvPython -m pip install -e "D:\AI-Knowledge-Engine\backend[dev]"

Write-Host "==> Step 3: freeze lock file"
& $VenvPython -m pip freeze | Out-File -Encoding utf8 "D:\AI-Knowledge-Engine\backend\requirements-lock.txt"

Write-Host "==> Step 4: M0 smoke test (GPU, CPU fallback automatic)"
powershell -ExecutionPolicy Bypass -File "D:\AI-Knowledge-Engine\scripts\run_m0_smoke.ps1"

Write-Host "Done."
