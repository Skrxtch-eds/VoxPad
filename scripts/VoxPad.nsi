Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

Name "VoxPad"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\VoxPad"
InstallDirRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "InstallLocation"
RequestExecutionLevel user
SetCompressor zlib
ShowInstDetails show
ShowUninstDetails show
BrandingText "VoxPad ${VERSION}"
VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1049 "ProductName" "VoxPad"
VIAddVersionKey /LANG=1049 "FileDescription" "Установка VoxPad"
VIAddVersionKey /LANG=1049 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1049 "LegalCopyright" "VoxPad contributors"
!define MUI_ICON "${ICON}"
!define MUI_UNICON "${ICON}"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Установка VoxPad"
!define MUI_WELCOMEPAGE_TEXT "Диктовка и расшифровка файлов на вашем компьютере.$\r$\n$\r$\nPython, библиотеки и модель Parakeet уже включены. Интернет для первого запуска не нужен.$\r$\n$\r$\nУстановка доступна без прав администратора."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\VoxPad.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Запустить VoxPad"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Russian"

Var TestMode

Function CheckRunning
  System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\ParakeetTranscriber") p.r0'
  ${If} $0 != 0
    System::Call 'kernel32::CloseHandle(p r0)'
    IfSilent +2
    MessageBox MB_OK|MB_ICONEXCLAMATION "Закройте VoxPad через значок в трее и повторите установку."
    SetErrorLevel 2
    Abort
  ${EndIf}
FunctionEnd

Function .onInit
  SetShellVarContext current
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "Для VoxPad нужна 64-битная Windows 10 или 11."
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_OK|MB_ICONSTOP "Для VoxPad нужна Windows 10 или 11."
    Abort
  ${EndIf}
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/TESTMODE" $1
  ${IfNot} ${Errors}
    StrCpy $TestMode "1"
  ${EndIf}
  Call CheckRunning
FunctionEnd

Section "VoxPad"
  SetOutPath "$INSTDIR"
  File "${BUNDLE}\VoxPad.exe"
  File /r "${BUNDLE}\_internal"
  File /r "${BUNDLE}\models"
  File /r "${BUNDLE}\licenses"
  File "${BUNDLE}\THIRD-PARTY-NOTICES.txt"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  ${If} $TestMode != "1"
    CreateDirectory "$SMPROGRAMS\VoxPad"
    CreateShortcut "$SMPROGRAMS\VoxPad\VoxPad.lnk" "$INSTDIR\VoxPad.exe"
    CreateShortcut "$DESKTOP\VoxPad.lnk" "$INSTDIR\VoxPad.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "DisplayName" "VoxPad"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "DisplayVersion" "${VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "DisplayIcon" "$INSTDIR\VoxPad.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "NoRepair" 1
  ${EndIf}
SectionEnd

Function un.onInit
  SetShellVarContext current
  System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\ParakeetTranscriber") p.r0'
  ${If} $0 != 0
    System::Call 'kernel32::CloseHandle(p r0)'
    IfSilent +2
    MessageBox MB_OK|MB_ICONEXCLAMATION "Закройте VoxPad через значок в трее и повторите удаление."
    SetErrorLevel 2
    Abort
  ${EndIf}
FunctionEnd

Section "Uninstall"
  ; Remove only the bundled application. Keep data and additional models.
  Delete "$INSTDIR\VoxPad.exe"
  RMDir /r "$INSTDIR\_internal"
  RMDir /r "$INSTDIR\licenses"
  Delete "$INSTDIR\THIRD-PARTY-NOTICES.txt"
  Delete "$INSTDIR\models\sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8\encoder.int8.onnx"
  Delete "$INSTDIR\models\sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8\decoder.int8.onnx"
  Delete "$INSTDIR\models\sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8\joiner.int8.onnx"
  Delete "$INSTDIR\models\sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8\tokens.txt"
  RMDir "$INSTDIR\models\sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
  RMDir "$INSTDIR\models"
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "InstallLocation"
  ${If} $0 == $INSTDIR
    Delete "$SMPROGRAMS\VoxPad\VoxPad.lnk"
    RMDir "$SMPROGRAMS\VoxPad"
    Delete "$DESKTOP\VoxPad.lnk"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad"
  ${EndIf}
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "ParakeetTranscriber"
  ${If} $0 == '$\"$INSTDIR\VoxPad.exe$\" --tray'
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "ParakeetTranscriber"
  ${EndIf}
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
