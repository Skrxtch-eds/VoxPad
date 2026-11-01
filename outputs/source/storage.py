"""Persistent preferences and local history; never stores API keys."""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import sqlite3
import threading

DEFAULTS = {
    'language': 'en', 'ui_theme': 'system', 'trigger_mode': 'hold',
    'shortcuts': {'dictate': [163], 'history': [162, 160, 72]},
    'ending': 'period_space',
    'capsule_enabled': True,
    'wave_color': '#ffffff', 'glass_blur': .60,
    'sounds': True, 'sound_volume':100, 'auto_paste': True, 'autostart': False, 'mute_recording': False,
    'microphone': '', 'export_folder': '', 'model': 'parakeet',
    'speech_language': 'auto', 'ai_enabled': False,
    'microphone_fallback':True, 'background_mode':True,
    'save_unfinished':True, 'paused':False,
}


def local_recording_time(created):
    """Format old and new records using the computer's local time zone."""
    try:
        moment=datetime.fromtimestamp(created) if isinstance(created,(int,float)) else datetime.fromisoformat(created)
        return moment.astimezone().strftime('%Y-%m-%d %H:%M:%S')
    except (TypeError,ValueError,OverflowError,OSError):
        return str(created)[:19].replace('T',' ')


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.settings_path = self.directory / 'settings.json'
        self.database_path = self.directory / 'history.sqlite3'
        self.settings = json.loads(json.dumps(DEFAULTS))
        if self.settings_path.is_file():
            try:
                saved = json.loads(self.settings_path.read_text('utf-8'))
                if isinstance(saved, dict):
                    self.settings.update(saved)
                    # Migrate removed controls without changing unrelated preferences.
                    for name in ('remove_interjections','punctuation','ending_shortcuts','sound_start_enabled','sound_stop_enabled'):
                        self.settings.pop(name,None)
            except (ValueError, OSError):
                # Retain the damaged file for recovery; do not overwrite on load.
                pass
        # The current interface has no AI controls. Legacy profiles are retained,
        # but their old enable flag must not reactivate an invisible network flow.
        self.settings['ai_enabled']=False
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
            ''')

    def connect(self):
        return sqlite3.connect(self.database_path, timeout=10)

    def save(self, changes):
        with self.lock:
            updated = dict(self.settings)
            updated.update(changes)
            # Secrets are stored separately in Windows Credential Manager.
            if any('key' in name.lower() or 'token' in name.lower() for name in changes):
                raise ValueError('Secrets must not be stored in preferences')
            temp = self.settings_path.with_suffix('.json.tmp')
            with temp.open('w', encoding='utf-8') as stream:
                json.dump(updated, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.settings_path)
            self.settings = updated

    def add(self, text, audio_seconds, processing_seconds, source='microphone'):
        text = text.strip()
        if not text:
            return
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO history(created,text,audio_seconds,processing_seconds,source) VALUES(?,?,?,?,?)',
                       (datetime.now(timezone.utc).isoformat(), text, audio_seconds, processing_seconds, source))
            db.execute('DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT 100)')
            if source in ('microphone','recovery'):
                db.execute('''UPDATE stats SET dictations=dictations+1, characters=characters+?,
                    words=words+?, audio_seconds=audio_seconds+?, processing_seconds=processing_seconds+? WHERE id=1''',
                           (len(text), len(re.findall(r"[^\W_]+(?:['’-][^\W_]+)*",text)), audio_seconds, processing_seconds))

    def history(self, query=''):
        with closing(self.connect()) as db:
            db.row_factory = sqlite3.Row
            # instr treats user search literally, including % and underscores.
            return [dict(row) for row in db.execute('SELECT * FROM history ORDER BY id DESC LIMIT 100')
                    if query.casefold() in row['text'].casefold()]

    def delete(self, identifier):
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM history WHERE id=?', (identifier,))

    def clear_history(self):
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM history')

    def statistics(self):
        with closing(self.connect()) as db:
            db.row_factory = sqlite3.Row
            result = dict(db.execute('SELECT * FROM stats WHERE id=1').fetchone())
        count = result['dictations']
        result['average_processing_seconds'] = result['processing_seconds'] / count if count else 0
        return result
