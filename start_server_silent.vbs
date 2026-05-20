' Inicia el server de Demo Company Chat en segundo plano (sin ventana visible).
' Pone un acceso directo a este archivo en la carpeta Startup de Windows
' para que arranque automaticamente al prender la PC.
' Para detenerlo, abri el Administrador de Tareas y matas el proceso "python.exe" que corre uvicorn.

Set objShell = CreateObject("WScript.Shell")
strScriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
objShell.CurrentDirectory = strScriptDir
objShell.Run "python -m uvicorn main:app --host 0.0.0.0 --port 8000", 0, False
