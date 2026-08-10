$ErrorActionPreference = "Stop"

try {
    $toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $projectRoot = (Resolve-Path (Join-Path $toolsDir "..")).Path
    $silentLauncher = Join-Path $toolsDir "run_dashboard_silent.vbs"
    $batLauncher = Join-Path $toolsDir "run_dashboard.bat"

    # エラーが見えるように、通常のbat起動を優先します。
    if (Test-Path -LiteralPath $batLauncher) {
        $targetPath = $batLauncher
    } elseif (Test-Path -LiteralPath $silentLauncher) {
        $targetPath = $silentLauncher
    } else {
        throw "tools\run_dashboard.bat または tools\run_dashboard_silent.vbs が見つかりません。"
    }

    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktop "ロボットPCダッシュボード.lnk"
    $iconPath = Join-Path $projectRoot "assets\app_icon.ico"

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $targetPath
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = "ロボットPCダッシュボードを起動します"
    if (Test-Path -LiteralPath $iconPath) {
        $shortcut.IconLocation = $iconPath
    }
    $shortcut.Save()

    Write-Host "デスクトップショートカットを作成しました。"
    Write-Host "ショートカット: $shortcutPath"
    Write-Host "起動先: $targetPath"
    Write-Host "作業フォルダ: $projectRoot"
    if (Test-Path -LiteralPath $iconPath) {
        Write-Host "アイコン: $iconPath"
    } else {
        Write-Host "アイコン: 既定アイコン（assets\app_icon.ico が見つかりません）"
    }
} catch {
    Write-Host "ショートカット作成に失敗しました。"
    Write-Host "内容: $($_.Exception.Message)"
    exit 1
}
