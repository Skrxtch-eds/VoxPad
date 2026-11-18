"""Persistent preferences and local history; never stores API keys."""
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
import os
import re
from pathlib import Path
import sqlite3
import threading

DEFAULTS = {
    'ui_theme': 'light', 'trigger_mode': 'hold',
    'shortcuts': {'dictate': [163]},
    'sounds': True, 'autostart': False, 'microphone': '',
    'microphone_fallback': True, 'background_mode': True, 'paused': False,
}

def migrate_settings(saved):
    settings = dict(DEFAULTS)
    settings.update({key: value for key, value in saved.items() if key in DEFAULTS})
    shortcuts = saved.get('shortcuts', {})
    chord = shortcuts.get('dictate') if isinstance(shortcuts, dict) else None
    if not isinstance(chord, list) or not chord or not all(type(key) is int and 1 <= key <= 255 for key in chord):
        chord = DEFAULTS['shortcuts']['dictate']
    settings['shortcuts'] = {'dictate': list(dict.fromkeys(chord))}
    for key, options in (('ui_theme', ('light','dark')), ('trigger_mode', ('hold','toggle'))):
        if settings[key] not in options: settings[key] = DEFAULTS[key]
    for key in ('sounds','autostart','microphone_fallback','background_mode','paused'):
        if not isinstance(settings[key], bool): settings[key] = DEFAULTS[key]
    if not isinstance(settings['microphone'], str): settings['microphone'] = ''
    return settings



class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.settings_path = self.directory / 'settings.json'
        self.database_path = self.directory / 'history.sqlite3'
        self.settings = migrate_settings({})
        if self.settings_path.is_file():
            try:
                saved = json.loads(self.settings_path.read_text('utf-8'))
                if isinstance(saved, dict):
                    self.settings = migrate_settings(saved)
            except (ValueError, OSError):
                # Retain the damaged file for recovery; do not overwrite on load.
                pass
        with closing(self.connect()) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY, created TEXT NOT NULL,
                    text TEXT NOT NULL, audio_seconds REAL NOT NULL,
                    processing_seconds REAL NOT NULL, source TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY CHECK(id=1), dictations INTEGER DEFAULT 0,
                    characters INTEGER DEFAULT 0, words INTEGER DEFAULT 0,
                    audio_seconds REAL DEFAULT 0, processing_seconds REAL DEFAULT 0);
                INSERT OR IGNORE INTO stats(id) VALUES(1);
                CREATE TABLE IF NOT EXISTS result_receipts (identifier TEXT PRIMARY KEY);
            ''')
            # Daily counters survive the 100-item history limit and user deletion.
            # Backfill once from available history; older deleted data cannot be inferred.
            daily_exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_stats'").fetchone()
            db.execute('''CREATE TABLE IF NOT EXISTS daily_stats (
                day TEXT PRIMARY KEY, words INTEGER NOT NULL DEFAULT 0,
                dictations INTEGER NOT NULL DEFAULT 0, audio_seconds REAL NOT NULL DEFAULT 0)''')
            if not daily_exists:
                for created, text, seconds in db.execute("SELECT created,text,audio_seconds FROM history WHERE source='microphone'").fetchall():
                    try:
                        day = datetime.fromisoformat(created).astimezone().date().isoformat()
                    except (ValueError, TypeError):
                        continue
                    db.execute('''INSERT INTO daily_stats VALUES(?,?,1,?) ON CONFLICT(day) DO UPDATE SET
                        words=words+excluded.words, dictations=dictations+1,
                        audio_seconds=audio_seconds+excluded.audio_seconds''',
                        (day, self.word_count(text), seconds))

    def connect(self):
        return sqlite3.connect(self.database_path, timeout=10)

    def save(self, changes):
        with self.lock:
            updated = migrate_settings({**self.settings, **changes})
            # The dictation application has no credential fields.
            if any('key' in name.lower() or 'token' in name.lower() for name in changes):
                raise ValueError('Secrets must not be stored in preferences')
            temp = self.settings_path.with_suffix('.json.tmp')
            with temp.open('w', encoding='utf-8') as stream:
                json.dump(updated, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.settings_path)
            self.settings = updated

    def add(self, text, audio_seconds, processing_seconds, source='microphone', identifier=None):
        text = text.strip()
        if not text:
            return False
        with closing(self.connect()) as db, db:
            if identifier is not None:
                inserted=db.execute('INSERT OR IGNORE INTO result_receipts VALUES(?)',(identifier,))
                if not inserted.rowcount:return False
            now = datetime.now(timezone.utc)
            db.execute('INSERT INTO history(created,text,audio_seconds,processing_seconds,source) VALUES(?,?,?,?,?)',
                       (now.isoformat(), text, audio_seconds, processing_seconds, source))
            db.execute('DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT 100)')
            if source == 'microphone':
                words = self.word_count(text)
                db.execute('''UPDATE stats SET dictations=dictations+1, characters=characters+?,
                    words=words+?, audio_seconds=audio_seconds+?, processing_seconds=processing_seconds+? WHERE id=1''',
                           (len(text), words, audio_seconds, processing_seconds))
                db.execute('''INSERT INTO daily_stats VALUES(?,?,1,?) ON CONFLICT(day) DO UPDATE SET
                    words=words+excluded.words, dictations=dictations+1,
                    audio_seconds=audio_seconds+excluded.audio_seconds''',
                    (now.astimezone().date().isoformat(), words, audio_seconds))
        return True

    @staticmethod
    def word_count(text):
        return len(re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", text))

    def daily_statistics(self, today=None):
        today = today or datetime.now().astimezone().date()
        days = [(today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
        with closing(self.connect()) as db:
            db.row_factory = sqlite3.Row
            rows = {row['day']: dict(row) for row in db.execute(
                'SELECT * FROM daily_stats WHERE day BETWEEN ? AND ?', (days[0], days[-1]))}
        return [rows.get(day, dict(day=day, words=0, dictations=0, audio_seconds=0.0)) for day in days]

    def retain_result(self, identifier, text, audio_seconds, processing_seconds):
        """Durable text fallback if SQLite fails; microphone audio stays in memory."""
        if not re.fullmatch(r'[a-f0-9]{32}',identifier):raise ValueError('Invalid result identifier')
        directory=self.directory/'unsaved';directory.mkdir(parents=True,exist_ok=True)
        target=directory/(identifier+'.json');temporary=target.with_suffix('.json.tmp')
        with temporary.open('w',encoding='utf-8') as stream:
            json.dump(dict(identifier=identifier,text=text,audio_seconds=audio_seconds,
                           processing_seconds=processing_seconds),stream,ensure_ascii=False)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target)

    def retry_unsaved(self):
        """Idempotent retry; a crash after COMMIT cannot duplicate statistics."""
        retained=0
        for path in (self.directory/'unsaved').glob('*.json'):
            try:
                value=json.loads(path.read_text('utf-8'))
                if value['identifier']!=path.stem or not re.fullmatch(r'[a-f0-9]{32}',path.stem):raise ValueError()
                self.add(value['text'],float(value['audio_seconds']),float(value['processing_seconds']),
                         identifier=value['identifier'])
                path.unlink()
            except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):retained+=1
        return retained

    def history(self):
        with closing(self.connect()) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM history ORDER BY id DESC LIMIT 100')]

    def delete(self, identifier):
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM history WHERE id=?', (identifier,))

    def statistics(self):
        with closing(self.connect()) as db:
            db.row_factory = sqlite3.Row
            result = dict(db.execute('SELECT * FROM stats WHERE id=1').fetchone())
        count = result['dictations']
        result['average_processing_seconds'] = result['processing_seconds'] / count if count else 0
        return result
