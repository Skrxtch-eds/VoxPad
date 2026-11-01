Option Explicit
Dim shell, files, folder, project, python, app, environment, arguments
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
folder = files.GetParentFolderName(WScript.ScriptFullName)
project = files.GetParentFolderName(folder)
python = files.BuildPath(project, ".venv\Scripts\pythonw.exe")
app = files.BuildPath(folder, "source\app.py")
Set environment = shell.Environment("Process")
If Not files.FileExists(python) Then
    ' Compatibility with the existing local installation.
    python = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
    If Not files.FileExists(python) Then
        MsgBox "Create .venv and install requirements.txt first. See README.md.", 48, "VoxPad"
        WScript.Quit 1
    End If
    environment("PYTHONPATH") = files.BuildPath(project, "work\vendor")
End If
shell.CurrentDirectory = folder
arguments = ""
If WScript.Arguments.Count > 0 Then
    If WScript.Arguments(0) = "--tray" Then arguments = " --tray"
End If
shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & app & Chr(34) & arguments, 0, False
