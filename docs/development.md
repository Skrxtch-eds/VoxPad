# Разработка VoxPad 0.6.2

## Среда

Windows x64, Python 3.14.10 x64. Runtime-зависимости закреплены в requirements.txt, инструменты сборки в requirements-build.txt, дополнительные инструменты замеров в requirements-dev.txt.

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe outputs\source\app.py
```

Исходники находятся в outputs/source. Данные исходников — outputs/Transcriber/data, модель — outputs/Transcriber/models. Личные данные и бинарные сборки исключены из Git.

## Архитектура

- app.py хранит версию и вызывает qt_app.py.
- qt_app.py создаёт единственное QQuickWindow, трей и mutex одного экземпляра.
- qt_controller.py связывает QML, фоновые workers аудио и ASR, последовательную очередь хранения и события.
- qml содержит четыре экрана и общие компоненты тем, переходов и состояний.
- audio_input.py подготавливает и повторно использует остановленный поток микрофона.
- engine.py и cpu_runtime.py выполняют преобразование в mono 16 кГц, inference и CPU-профиль.
- model_manager.py закрепляет ревизию, размеры и SHA-256 Parakeet, устанавливает её через временную папку.
- storage.py выполняет миграцию настроек, хранение SQLite, 100 записей истории, суточную статистику и повтор несохранённых результатов.
- windows_input.py реализует глобальную клавишу, буфер и защищённую по активному HWND команду вставки.
- qt_recording_overlay.py и recording_overlay.py показывают капсулу без перехвата фокуса.
- app_paths.py различает модельный каталог версии и общую data установленного приложения.

SQLite не блокирует выдачу текста и вставку. При ошибке базы текст остаётся в окне и по возможности сохраняется в data/unsaved. Идемпотентные квитанции исключают двойное увеличение статистики при повторе.

## Проверки

```powershell
.venv\Scripts\python.exe -m compileall -q outputs/source scripts tests
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.venv\Scripts\python.exe tests/qml_smoke.py
.venv\Scripts\python.exe tests/qml_dpi_qa.py
```

QML-проверки используют настоящий Qt Quick и отдельные данные. Реальная физическая клавиша, микрофон и появление текста в сторонних приложениях проверяются вручную. Скрипты замеров описаны в [отчёте ASR](asr-performance-2026-11-17.md). Старые отчёты сохраняют контекст своих измерений.

## Сборка

Установите модель через приложение перед локальной сборкой. Компилятор C# .NET Framework берётся из C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe. Для установщика нужен NSIS 3: makensis.exe в PATH, стандартной папке Program Files или распакованный work/tools/nsis-3.13. Другой путь передаётся через --nsis. CI загружает официальный NSIS 3.13 и проверяет закреплённый SHA-256 ZIP.

```powershell
.venv\Scripts\python.exe scripts/build_runtime_portable.py
.venv\Scripts\python.exe scripts/build_online_setup.py outputs/VoxPad-0.6.2-Windows-x64-runtime.zip
```

Первый скрипт сверяет RECORD зависимостей, копирует неизменённый Python, модули и Parakeet, компилирует небольшой Launcher.cs, формирует BUILD-MANIFEST.json и полный ZIP. Второй компилирует Setup.cs в консольный worker с версией, URL релиза и SHA-256 ZIP, рисует изображения переключателей и собирает scripts/OnlineSetup.nsi через makensis.exe. Переименование или пересборка ZIP требует пересборки установщика.

NSIS отвечает за русскоязычный интерфейс, выбор родительской папки, три переключателя, ярлыки, HKCU Run и регистрацию удаления без прав администратора. Worker использует .NET Framework 4.8 и TLS 1.2, загружает один комплект с GitHub, проверяет полный SHA-256 до распаковки, проверяет пути ZIP, размещает версию отдельно и переключает current.txt. Выбор автозапуска записывается в настройки приложения без изменения остальных полей. Лаунчер читает current.txt и запускает комплектный pythonw.exe с -I. installed.flag включает общую data. Старые версии сохраняются. Повторная установка той же версии использует её каталог. Защита от одновременной установки действует через отдельный mutex. Worker для удаления хранится в .setup; NSIS-деинсталлятор сохраняет data.

Автозапуск установленной версии использует корневой VoxPad.exe. Portable сохраняет самостоятельный каталог данных. Старые scripts/build_windows.py, VoxPad.spec и VoxPad.nsi относятся к прежнему формату PyInstaller, который текущий релиз не использует.

## Проверка дистрибутива

```powershell
.venv\Scripts\python.exe tests/runtime_portable_smoke.py outputs/VoxPad-0.6.2-Windows-x64-runtime.zip path/to/public-speech.wav
.venv\Scripts\python.exe tests/online_setup_smoke.py outputs/VoxPad-0.6.2-Setup-x64.exe outputs/VoxPad-0.6.2-Windows-x64-runtime.zip path/to/public-speech.wav
```

Проверяется установка в отдельную папку без изменения ярлыков/реестра, комплектный runtime, ASR, автозапуск по умолчанию и его отключение, повтор установки, сохранение остальных настроек и данных, удаление. Флаг --online дополнительно проверяет загрузку опубликованного ZIP. Перед выпуском проверьте установку в чистой Windows, обычный микрофон и Defender. Проверка на компьютере разработчика имеет ограниченный охват.

## Публикация

Обновите VERSION в app.py, README и docs/releases/<версия>.md. Запустите проверки и сборку. Закоммитьте исходники и документацию, отправьте коммит в GitHub.

```powershell
.venv\Scripts\python.exe scripts/github_release.py --target <полный-SHA-коммита> --publish
```

Скрипт использует сохранённую Git Credential Manager авторизацию без записи токена в файлы. Создаёт draft, загружает Setup, полный ZIP и контрольные суммы, затем публикует релиз. Уже опубликованные файлы не заменяются. При прерванной загрузке проверьте draft и удалите неполные вложения перед повтором. CI выполняет модульные проверки при push. Релизный workflow собирает ту же схему вручную через workflow_dispatch.

## Лицензии

Лицензия собственного кода пока не выбрана. Системный Segoe UI берётся из Windows. Уведомления значков находятся в assets/icons. Сборщик копирует лицензии Python и пакетов в licenses, а сведения — в THIRD-PARTY-NOTICES.txt.

Parakeet распространяется NVIDIA по CC BY 4.0. Источник — https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3. Используется ONNX-конвертация INT8 sherpa-onnx, источник и факт преобразования указаны в дистрибутиве. sherpa-onnx использует Apache-2.0. PySide6 Essentials / Qt распространяются на условиях, указанных в комплектных лицензиях. Исторические уведомления Tcl и FFmpeg сохранены в docs/licenses как материалы прежних сборок.


## Безопасность релизной среды

Сборка 0.6.2 использует официальный Python 3.14.10. Перед копированием проверяются действующие подписи Python Software Foundation у python.exe, pythonw.exe и python314.dll. Среда Codex для сборки runtime не используется. Зависимости устанавливаются в отдельный venv из requirements-build.txt.

Локальная проверенная копия Python получена из официального пакета NuGet python/3.14.10. SHA-256 пакета — f54ba67c9951c3d773ea47d2bb095150c037c399f0423a968bcda22809241784. CI использует actions/setup-python с закреплённой версией 3.14.10.

Перед публикацией выполните scripts/security_check.py --archive outputs/VoxPad-0.6.2-Windows-x64-runtime.zip --osv. Проверяются токены известных форматов, приватные ключи, пользовательские данные в ZIP и известные уязвимости версий всех поставляемых Python-пакетов. Сетевой запрос OSV содержит только названия и версии. Полный отчёт проверки находится в security-review-2026-11-18.md.
