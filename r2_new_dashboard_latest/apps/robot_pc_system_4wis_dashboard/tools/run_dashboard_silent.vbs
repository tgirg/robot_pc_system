' ロボットPCダッシュボード 静音起動ランチャー
' このVBS自身の場所から tools\run_dashboard.bat を探して起動します。
Option Explicit

Dim fso, shell, scriptDir, projectRoot, batPath, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(scriptDir)
batPath = fso.BuildPath(scriptDir, "run_dashboard.bat")

If Not fso.FileExists(batPath) Then
    MsgBox "tools\run_dashboard.bat が見つかりません。プロジェクト配置を確認してください。", vbCritical, "ロボットPCダッシュボード"
    WScript.Quit 1
End If

shell.CurrentDirectory = projectRoot
command = "cmd.exe /c """ & batPath & """"
' 第2引数 0 はコンソールを表示しない設定です。
shell.Run command, 0, False
