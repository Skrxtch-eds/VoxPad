"""Delayed contextual help and readable values without changing stored keys."""
import tkinter as tk
from ui_style import theme_for,UI_SCALE

class Tooltip:
    delay=700
    def __init__(self,widget,text):
        self.widget,self.text=widget,text
        self.job=None; self.window=None
        widget._tooltip=self
        widget.bind('<Enter>',self.schedule,add='+')
        for event in ('<Leave>','<ButtonPress>','<Destroy>','<Escape>','<FocusOut>'):
            widget.bind(event,self.hide,add='+')
        widget.bind('<F1>',self.show,add='+')

    def schedule(self,event=None):
        self.hide(); self.job=self.widget.after(self.delay,self.show)

    def show(self,event=None):
        self.job=None
        if self.window or not self.widget.winfo_exists(): return
        window=tk.Toplevel(self.widget); self.window=window
        window.withdraw(); window.overrideredirect(True); window.attributes('-topmost',True)
        theme=theme_for(getattr(self.widget.winfo_toplevel(),'theme_mode','system'))
        tk.Label(window,text=self.text,justify='left',wraplength=round(380*UI_SCALE),padx=round(12*UI_SCALE),pady=round(8*UI_SCALE),
                 bg=theme.secondary,fg=theme.text,font=('Segoe UI',10),relief='solid',borderwidth=1).pack()
        window.update_idletasks()
        x=self.widget.winfo_rootx()+10; y=self.widget.winfo_rooty()+self.widget.winfo_height()+7
        x=min(x,self.widget.winfo_screenwidth()-window.winfo_reqwidth()-10)
        if y+window.winfo_reqheight()>self.widget.winfo_screenheight()-12:
            y=self.widget.winfo_rooty()-window.winfo_reqheight()-7
        window.geometry(f'+{max(0,x)}+{max(0,y)}'); window.deiconify()

    def hide(self,event=None):
        if self.job:
            try:self.widget.after_cancel(self.job)
            except tk.TclError:pass
            self.job=None
        if self.window:
            try:self.window.destroy()
            except tk.TclError:pass
            self.window=None

class Choice:
    """The UI displays translated labels; get() returns the original stable key."""
    def __init__(self,value,options,translate):
        self.options=list(options)
        self.labels=[translate(str(item)) for item in options]
        self.variable=tk.StringVar(value=self.labels[self.options.index(value)])
    def get(self):
        return self.options[self.labels.index(self.variable.get())]

# Each explanation describes the consequence, not an implementation detail.
HELP={'Sound volume': ('Volume of the start/end recording cues only. 0% is silent. System volume is unchanged.',
                  'Громкость только звуков начала и завершения записи. 0% — без звука. Системная громкость не '
                  'меняется.'),
 'Preview sound': ('Play the start cue at the chosen volume before saving.',
                   'Проигрывает звук начала записи с выбранной громкостью до сохранения настроек.'),
 'Language': ('Choose the language of menus and settings. This does not change the language of your speech.',
              'Язык меню и настроек. Не меняет язык распознаваемой речи.'),
 'Recording mode': ('Hold: keep the shortcut pressed while speaking. Toggle: press once to start and again to finish.',
                    'Удержание: говори, пока клавиша нажата. Переключение: нажми один раз для начала и ещё раз для '
                    'завершения.'),
 'Text ending': ('Choose what is added after a dictation. Period + Enter can send a message immediately. Existing '
                 'question and exclamation marks are preserved.',
                 'Выбери окончание диктовки. Вариант «знак в конце + Enter» может сразу отправить сообщение. Уже '
                 'стоящие ? и ! сохраняются.'),
 'Paste automatically': ('Insert the result into the field where dictation started. If that window loses focus, the '
                         'text stays available for copying.',
                         'Вставляет результат в поле, где началась диктовка. Если ты перешёл в другое окно, текст '
                         'остаётся доступен для копирования.'),
 'Feedback sounds': ('Short tones mark the start, end and errors of recording. They do not change recognition '
                     'accuracy.',
                     'Короткие сигналы отмечают начало, завершение записи и ошибки. На точность распознавания не '
                     'влияют.'),
 'Mute system audio during recording': ('Temporarily mute your default speakers while recording. Restore their '
                                        'previous mute state afterward; volume is not changed.',
                                        'На время записи отключает звук системных динамиков. После записи возвращает '
                                        'прежнее состояние; уровень громкости не меняет.'),
 'Start with Windows (in tray)': ('Start after you sign in to Windows, without opening the main window. Open it using '
                                  'the icon near the clock.',
                                  'Запускает программу после входа в Windows без основного окна. Открыть её можно '
                                  'через значок возле часов.'),
 'Show capsule': ('Show the glass indicator while the microphone records. When off, dictation still works from the '
                  'tray.',
                  'Показывает стеклянную капсулу во время записи. Если выключить, диктовка продолжит работать через '
                  'трей.'),
 'Glass blur': ('Blur the desktop visible through the capsule. This affects appearance only, not the wave or speech '
                'recognition.',
                'Размывает фон, видимый сквозь капсулу. Меняет только внешний вид, а не волну или качество '
                'распознавания.'),
 'Wave color': ('Choose the color of the sound wave inside the capsule. Its height still follows microphone loudness.',
                'Выбирает цвет звуковой волны внутри капсулы. Её высота по-прежнему зависит от громкости микрофона.'),
 'Default appearance': ('Reset glass blur and wave color. Other settings and your transcripts stay unchanged.',
                        'Возвращает исходные размытие стекла и цвет волны. Остальные настройки и тексты сохраняются.'),
 'Export folder': ('Audio and video imports create TXT files here. Existing files are preserved and new filenames '
                   'receive a number.',
                   'В эту папку сохраняются TXT после обработки аудио и видео. Существующие файлы сохраняются, новым '
                   'при совпадении имени добавляется номер.'),
 'Dictation': ('Assign the main recording shortcut. Left and right modifiers are distinct. Click Capture, press the '
               'combination, then release all keys.',
               'Основная клавиша записи. Левые и правые Ctrl, Shift и Alt различаются. Нажми «Назначить», введи '
               'сочетание и отпусти все клавиши.'),
 'History': ('Assign a shortcut to open the last 100 transcripts. Opening history does not start the microphone.',
             'Сочетание для открытия последних 100 расшифровок. Открытие истории не включает микрофон.'),
 'Ending: space': ('Use this shortcut to dictate with a space at the end. A single final period is removed; !, ? and '
                   'ellipses remain.',
                   'Диктовка с пробелом в конце. Одна последняя точка удаляется; !, ? и многоточие сохраняются.'),
 'Ending: period + space': ('Use this shortcut to finish with punctuation and a space. A period is added if no final '
                            'punctuation exists.',
                            'Диктовка со знаком в конце и пробелом. Если конечного знака нет, добавляется точка.'),
 'Ending: period + Enter': ('Use this shortcut to finish with punctuation and send Enter after insertion. In a chat '
                            'this may send the message.',
                            'После вставки текста со знаком в конце нажимает Enter. В чате это может отправить '
                            'сообщение.'),
 'Expected language': ('A language hint for Whisper. Parakeet detects the language itself; GigaAM recognises Russian '
                       'only.',
                       'Подсказка языка для Whisper. Parakeet определяет язык сам; GigaAM распознаёт только русский.'),
 'Models': ('Choose a recognition engine. Download installs its files locally; Use activates it. Compare quality on '
            'your own speech.',
            'Выбор движка распознавания. «Скачать» загружает его файлы, «Выбрать» включает модель. Сравнивай качество '
            'на своей речи.'),
 'Download': ('Download model files to this computer. Internet is needed for the download, but not for subsequent '
              'recognition.',
              'Загружает модель на компьютер. Интернет нужен для загрузки, но не для последующего распознавания.'),
 'Use': ('Load this installed model for future recordings. Finish your current recording before switching.',
         'Загружает установленную модель для следующих записей. Перед переключением заверши текущую запись.'),
 'Remove': ('Delete an inactive model to free disk space. Transcripts remain. The active model cannot be deleted.',
            'Удаляет неактивную модель для освобождения места. Тексты сохраняются. Активную модель удалить нельзя.'),
 'Cancel download': ('Request cancellation of the current model download. A network operation may take a moment to '
                     'stop.',
                     'Отменяет текущую загрузку модели. Остановка сетевой операции может занять некоторое время.'),
 'Update package': ('Choose an update ZIP provided for this application. Settings, history and model files are '
                    'preserved.',
                    'Выбирает ZIP обновления для этой программы. Настройки, история и файлы моделей сохраняются.'),
 'Microphone': ('Remember this recording device. The default option follows the microphone selected in Windows.',
                'Запоминает выбранное устройство. Вариант по умолчанию использует микрофон, выбранный в Windows.')}
