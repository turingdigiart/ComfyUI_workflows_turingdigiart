<#
  setup.ps1 —— 把本仓库的 workflows/ 接到 ComfyUI 的工作流目录。

  为什么用 junction：工作流在 UI 里手工改完必须立刻成为 Git 工作区里的改动，
  复制一份做不到（会分叉）。junction 让"ComfyUI 看到的"和"Git 管的"是同一份文件。

  默认只报告，不动作。加 -Apply 才真正执行。
  用法:
    powershell -File scripts/setup.ps1                 # 预演
    powershell -File scripts/setup.ps1 -Apply          # 执行
#>
[CmdletBinding()]
param(
  [string]$ComfyUIRoot = 'E:\RAE_ToolRoot\comfyui\ComfyUI_windows_portable\ComfyUI',
  # 注意：参数默认值里取不到 $PSScriptRoot（PS 5.1 行为），先留空，下面再补
  [string]$RepoRoot = '',
  [switch]$Apply
)

$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) {
  $here = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
  if (-not $here) { throw '无法确定脚本目录，请用 -RepoRoot 显式指定仓库根' }
  $RepoRoot = Split-Path -Parent $here
}
$repoWorkflows = Join-Path $RepoRoot 'workflows'
$comfyWorkflows = Join-Path $ComfyUIRoot 'user\default\workflows'

Write-Host "仓库工作流目录: $repoWorkflows"
Write-Host "ComfyUI 工作流目录: $comfyWorkflows"
if (-not (Test-Path $repoWorkflows)) { throw "仓库里没有 workflows/：$repoWorkflows" }

$item = Get-Item -LiteralPath $comfyWorkflows -ErrorAction SilentlyContinue
if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
  $target = (Get-Item -LiteralPath $comfyWorkflows).Target
  Write-Host "已是指向 $target 的链接 —— 无需处理。" -ForegroundColor Green
  exit 0
}

$existing = @(Get-ChildItem -LiteralPath $comfyWorkflows -File -ErrorAction SilentlyContinue)
Write-Host ("现状：真实目录，含 {0} 个文件" -f $existing.Count)

if (-not $Apply) {
  Write-Host ''
  Write-Host '预演（未做任何改动）。执行 -Apply 将：' -ForegroundColor Yellow
  Write-Host "  1. 把现有 $($existing.Count) 个工作流复制到 $repoWorkflows（若仓库为空）"
  Write-Host "  2. 把原目录改名为 workflows_backup_<yyyyMMdd_HHmmss>"
  Write-Host "  3. 建立 junction：$comfyWorkflows → $repoWorkflows"
  exit 0
}

if ($existing.Count -gt 0 -and @(Get-ChildItem -LiteralPath $repoWorkflows -File -Recurse).Count -eq 0) {
  Copy-Item -Path (Join-Path $comfyWorkflows '*') -Destination $repoWorkflows -Recurse -Force
  Write-Host ("已复制 {0} 个文件进仓库" -f $existing.Count)
}

$backup = "$comfyWorkflows`_backup_" + (Get-Date -Format 'yyyyMMdd_HHmmss')
Rename-Item -LiteralPath $comfyWorkflows -NewName (Split-Path $backup -Leaf)
& cmd /c mklink /J "$comfyWorkflows" "$repoWorkflows" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "建立 junction 失败，原目录仍在 $backup" }

Write-Host "完成：$comfyWorkflows → $repoWorkflows" -ForegroundColor Green
Write-Host "原目录备份在 $backup" -ForegroundColor DarkGray