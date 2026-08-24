' Launches start-native-stack.ps1 with genuinely no visible window.
'
' WHY THIS FILE EXISTS: Task Scheduler running powershell.exe flashes a console
' every single run. `-WindowStyle Hidden` cannot prevent it, because PowerShell
' applies that style AFTER the console host has already been created and drawn.
' wscript.exe is a GUI-subsystem executable — it never allocates a console at
' all — and Run()'s windowStyle=0 starts the child hidden from the first frame,
' so there is nothing to flash.
'
' This is the same pattern keepalive_launcher.vbs already uses in the sustena
' repo, and the reason is written up in gyygs.ke/infra/watchdog.sh's header too.
' The 5-minute flash was this lesson being relearned the hard way.

Set objShell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
psScript = scriptDir & "\start-native-stack.ps1"

cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & psScript & """"

' 0 = SW_HIDE, False = don't wait for it to exit
objShell.Run cmd, 0, False
