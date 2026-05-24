#Requires -Version 5
<#
One-time registration of the daily auto-ingest task in Windows Task Scheduler.
Run from an elevated PowerShell prompt.

  PS> .\scripts\install_task.ps1

To unregister later:
  PS> Unregister-ScheduledTask -TaskName FinanceTrackerAutoIngest -Confirm:$false
#>

$ErrorActionPreference = 'Stop'

$BatPath = "C:\home-proj\tracker\finance-app\scripts\run_auto_ingest.bat"
if (-not (Test-Path $BatPath)) {
    throw "Wrapper not found at $BatPath. Run from the repo root or fix the path."
}

$action = New-ScheduledTaskAction -Execute $BatPath
$trigger = New-ScheduledTaskTrigger -Daily -At 7:00am
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName "FinanceTrackerAutoIngest" `
    -Description "Runs the finance tracker auto-ingest pipeline daily at 07:00. Pulls Isracard transactions; OneZero requires manual OTP and is best run on-demand." `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Force

Write-Host "Registered task 'FinanceTrackerAutoIngest'. Next run:"
Get-ScheduledTask -TaskName FinanceTrackerAutoIngest | Get-ScheduledTaskInfo | Format-List TaskName, NextRunTime, LastRunTime, LastTaskResult
