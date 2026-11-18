; Current runtime-based online installer. VoxPad.nsi is the legacy offline build.
Unicode true
ManifestDPIAware true
!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

Name "VoxPad"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\VoxPad"
InstallDirRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails nevershow
ShowUninstDetails show
BrandingText "VoxPad ${VERSION}"
SetFont "Segoe UI" 9
VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1049 "ProductName" "VoxPad"
VIAddVersionKey /LANG=1049 "FileDescription" "Установка VoxPad"
VIAddVersionKey /LANG=1049 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1049 "LegalCopyright" "VoxPad contributors"
!define MUI_ICON "${ICON}"
!define MUI_UNICON "${ICON}"
!define MUI_BGCOLOR "F7F7F9"
!define MUI_TEXTCOLOR "111111"
!define MUI_ABORTWARNING
!define MUI_INSTFILESPAGE_HEADER_TEXT "Устанавливаем VoxPad"
!define MUI_INSTFILESPAGE_HEADER_SUBTEXT "Загрузка, проверка и распаковка приложения и модели."
!define MUI_FINISHPAGE_TITLE "VoxPad готов к работе"
!define MUI_FINISHPAGE_TEXT "Приложение и модель установлены.$\r$\nДля диктовки интернет больше не нужен.$\r$\n$\r$\nЗапускайте VoxPad.exe из папки установки или используйте выбранные ярлыки."
Page custom SettingsCreate SettingsLeave
!define MUI_PAGE_CUSTOMFUNCTION_SHOW InstallShow
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\VoxPad.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Запустить VoxPad"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Russian"

Var Dialog
Var ParentPath
Var FolderEdit
Var PathLabel
Var DesktopSwitch
Var MenuSwitch
Var StartupSwitch
Var DesktopEnabled
Var MenuEnabled
Var StartupEnabled
Var SwitchOn
Var SwitchOff
Var TestMode
Var Archive
Var WorkerArguments
Var Result
Var ProgressBar

Function InstallShow
  FindWindow $0 "#32770" "" $HWNDPARENT
  GetDlgItem $ProgressBar $0 1004
  ${NSD_AddStyle} $ProgressBar 0x8
  SendMessage $ProgressBar 0x040A 1 30
FunctionEnd

!macro Label X Y W H TEXT COLOR
  ${NSD_CreateLabel} ${X} ${Y} ${W} ${H} "${TEXT}"
  Pop $0
  SetCtlColors $0 "${COLOR}" "F7F7F9"
!macroend

!macro Switch HANDLE Y TEXT VALUE
  ${NSD_CreateCheckbox} 260u ${Y} 40u 18u "${TEXT}"
  Pop ${HANDLE}
  ${NSD_AddStyle} ${HANDLE} ${BS_BITMAP}|${BS_PUSHLIKE}|${BS_FLAT}
  System::Call 'uxtheme::SetWindowTheme(p ${HANDLE}, w "", w "")'
  ${NSD_SetState} ${HANDLE} ${VALUE}
  ${If} ${VALUE} == 1
    SendMessage ${HANDLE} ${BM_SETIMAGE} ${IMAGE_BITMAP} $SwitchOn
  ${Else}
    SendMessage ${HANDLE} ${BM_SETIMAGE} ${IMAGE_BITMAP} $SwitchOff
  ${EndIf}
  ${NSD_OnClick} ${HANDLE} ToggleSwitch
!macroend

Function ToggleSwitch
  Pop $0
  ${NSD_GetState} $0 $1
  ${If} $1 == 1
    SendMessage $0 ${BM_SETIMAGE} ${IMAGE_BITMAP} $SwitchOn
  ${Else}
    SendMessage $0 ${BM_SETIMAGE} ${IMAGE_BITMAP} $SwitchOff
  ${EndIf}
FunctionEnd

Function PathChanged
  Pop $0
  ${NSD_GetText} $FolderEdit $ParentPath
  ${NSD_SetText} $PathLabel "$ParentPath\VoxPad"
FunctionEnd

Function BrowseFolder
  Pop $0
  nsDialogs::SelectFolderDialog "Выберите папку, в которой будет создана папка VoxPad" "$ParentPath"
  Pop $0
  ${If} $0 != error
    ${NSD_SetText} $FolderEdit $0
  ${EndIf}
FunctionEnd

Function SettingsCreate
  !insertmacro MUI_HEADER_TEXT "Установка VoxPad" "Локальная диктовка. Всё необходимое — в одной папке."
  GetDlgItem $0 $HWNDPARENT 1
  SendMessage $0 ${WM_SETTEXT} 0 "STR:Установить"
  nsDialogs::Create 1018
  Pop $Dialog
  SetCtlColors $Dialog "111111" "F7F7F9"
  !insertmacro Label 0 0 300u 13u "Папка установки" "111111"
  ${NSD_CreateDirRequest} 0 17u 239u 15u "$ParentPath"
  Pop $FolderEdit
  ${NSD_OnChange} $FolderEdit PathChanged
  ${NSD_CreateBrowseButton} 247u 16u 53u 17u "Обзор…"
  Pop $0
  ${NSD_OnClick} $0 BrowseFolder
  !insertmacro Label 0 36u 300u 20u "$ParentPath\VoxPad" "77777A"
  StrCpy $PathLabel $0
  !insertmacro Label 0 63u 250u 16u "Ярлык на рабочем столе" "111111"
  !insertmacro Switch $DesktopSwitch 60u "Ярлык на рабочем столе" $DesktopEnabled
  !insertmacro Label 0 87u 250u 16u "Ярлык в меню «Пуск»" "111111"
  !insertmacro Switch $MenuSwitch 84u "Ярлык в меню «Пуск»" $MenuEnabled
  !insertmacro Label 0 111u 250u 16u "Запуск вместе с Windows" "111111"
  !insertmacro Switch $StartupSwitch 108u "Запуск вместе с Windows" $StartupEnabled
  !insertmacro Label 0 132u 300u 10u "Нужен интернет и 4 ГБ свободного места." "77777A"
  nsDialogs::Show
FunctionEnd

Function SettingsLeave
  ${NSD_GetText} $FolderEdit $ParentPath
  ${If} $ParentPath == ""
    MessageBox MB_OK|MB_ICONEXCLAMATION "Выберите папку установки."
    Abort
  ${EndIf}
  ; GetFullPathName also normalizes a trailing slash on drive roots.
  GetFullPathName $INSTDIR "$ParentPath\VoxPad"
  ${NSD_GetState} $DesktopSwitch $DesktopEnabled
  ${NSD_GetState} $MenuSwitch $MenuEnabled
  ${NSD_GetState} $StartupSwitch $StartupEnabled
FunctionEnd

Function CheckRunning
  ${If} $TestMode == 1
    Return
  ${EndIf}
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
  SetRegView 64
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "Нужна 64-битная Windows 10 или 11."
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_OK|MB_ICONSTOP "Нужна Windows 10 или 11."
    Abort
  ${EndIf}
  StrCpy $DesktopEnabled 1
  StrCpy $MenuEnabled 1
  StrCpy $StartupEnabled 1
  ${GetParameters} $0
  ${GetOptions} $0 "/TESTMODE" $1
  ${IfNot} ${Errors}
    StrCpy $TestMode 1
  ${EndIf}
  ClearErrors
  ${GetOptions} $0 "/ARCHIVE=" $Archive
  ClearErrors
  ${GetOptions} $0 "/DESKTOP=" $1
  ${IfNot} ${Errors}
    StrCpy $DesktopEnabled $1
  ${EndIf}
  ClearErrors
  ${GetOptions} $0 "/STARTMENU=" $1
  ${IfNot} ${Errors}
    StrCpy $MenuEnabled $1
  ${EndIf}
  ClearErrors
  ${GetOptions} $0 "/AUTOSTART=" $1
  ${IfNot} ${Errors}
    StrCpy $StartupEnabled $1
  ${EndIf}
  ${GetParent} $INSTDIR $ParentPath
  InitPluginsDir
  File /oname=$PLUGINSDIR\switch-0.bmp "${ASSETS}\switch-0.bmp"
  File /oname=$PLUGINSDIR\switch-1.bmp "${ASSETS}\switch-1.bmp"
  System::Call 'user32::GetDC(p 0) p.r0'
  System::Call 'gdi32::GetDeviceCaps(p r0, i 88) i.r1'
  System::Call 'user32::ReleaseDC(p 0, p r0)'
  IntOp $2 $1 * 56
  IntOp $2 $2 / 96
  IntOp $3 $1 * 28
  IntOp $3 $3 / 96
  System::Call 'user32::LoadImageW(p 0, w "$PLUGINSDIR\switch-0.bmp", i 0, i r2, i r3, i 0x10) p.s'
  Pop $SwitchOff
  System::Call 'user32::LoadImageW(p 0, w "$PLUGINSDIR\switch-1.bmp", i 0, i r2, i r3, i 0x10) p.s'
  Pop $SwitchOn
  Call CheckRunning
FunctionEnd

Function .onGUIEnd
  System::Call 'gdi32::DeleteObject(p $SwitchOff)'
  System::Call 'gdi32::DeleteObject(p $SwitchOn)'
FunctionEnd

Section "VoxPad"
  Call CheckRunning
  SetOutPath "$PLUGINSDIR"
  File /oname=InstallWorker.exe "${WORKER}"
  StrCpy $WorkerArguments '--target="$INSTDIR" --autostart=$StartupEnabled'
  ${If} $TestMode == 1
    StrCpy $WorkerArguments '$WorkerArguments --test-mode'
  ${EndIf}
  ${If} $Archive != ""
    StrCpy $WorkerArguments '$WorkerArguments --archive="$Archive"'
  ${EndIf}
  DetailPrint "Скачивание приложения и модели. Это может занять несколько минут…"
  nsExec::ExecToLog /OEM '"$PLUGINSDIR\InstallWorker.exe" $WorkerArguments'
  Pop $Result
  SendMessage $ProgressBar 0x040A 0 0
  ${If} $Result != 0
    SetErrorLevel 1
    IfSilent +2
    MessageBox MB_OK|MB_ICONSTOP "Установка не завершена. Проверьте интернет и свободное место.$\r$\nПодробности: $TEMP\VoxPad-setup-error.log"
    Abort "Установка не завершена."
  ${EndIf}
  SetOutPath "$INSTDIR\.setup"
  CopyFiles /SILENT "$PLUGINSDIR\InstallWorker.exe" "$INSTDIR\.setup\InstallWorker.exe"
  WriteINIStr "$INSTDIR\.setup\install.ini" "Integration" "TestMode" "$TestMode"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  SetOutPath "$INSTDIR"
  ${If} $TestMode != 1
    ${If} $DesktopEnabled == 1
      CreateShortcut "$DESKTOP\VoxPad.lnk" "$INSTDIR\VoxPad.exe"
    ${Else}
      Delete "$DESKTOP\VoxPad.lnk"
    ${EndIf}
    ${If} $MenuEnabled == 1
      CreateShortcut "$SMPROGRAMS\VoxPad.lnk" "$INSTDIR\VoxPad.exe"
    ${Else}
      Delete "$SMPROGRAMS\VoxPad.lnk"
    ${EndIf}
    ${If} $StartupEnabled == 1
      WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "ParakeetTranscriber" '$\"$INSTDIR\VoxPad.exe$\" --tray'
    ${Else}
      DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "ParakeetTranscriber"
    ${EndIf}
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "DisplayName" "VoxPad"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "DisplayVersion" "${VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "DisplayIcon" "$INSTDIR\VoxPad.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "NoRepair" 1
  ${EndIf}
SectionEnd

Function un.onInit
  SetShellVarContext current
  SetRegView 64
  ReadINIStr $TestMode "$INSTDIR\.setup\install.ini" "Integration" "TestMode"
FunctionEnd

Section "Uninstall"
  StrCpy $WorkerArguments '--remove-files --target="$INSTDIR"'
  ${If} $TestMode == 1
    StrCpy $WorkerArguments '$WorkerArguments --test-mode'
  ${EndIf}
  nsExec::ExecToLog /OEM '"$INSTDIR\.setup\InstallWorker.exe" $WorkerArguments'
  Pop $Result
  ${If} $Result != 0
    SetErrorLevel 1
    Abort "Не удалось удалить VoxPad. Закройте приложение через трей и повторите."
  ${EndIf}
  ${If} $TestMode != 1
    ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad" "InstallLocation"
    ${If} $0 == $INSTDIR
      Delete "$DESKTOP\VoxPad.lnk"
      Delete "$SMPROGRAMS\VoxPad.lnk"
      DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxPad"
    ${EndIf}
    ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "ParakeetTranscriber"
    ${If} $0 == '$\"$INSTDIR\VoxPad.exe$\" --tray'
    ${OrIf} $0 == '$INSTDIR\VoxPad.exe --tray'
      DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "ParakeetTranscriber"
    ${EndIf}
  ${EndIf}
  Delete "$INSTDIR\.setup\InstallWorker.exe"
  Delete "$INSTDIR\.setup\install.ini"
  RMDir "$INSTDIR\.setup"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
