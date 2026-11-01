"""Normalize dictation spelling and apply the chosen insertion ending."""
import re

_RUSSIAN_TOKEN=re.compile(r'(?<!\w)(?:[А-Яа-яЁё]|<unk>)+(?!\w)')


def normalize_transcript(text):
    """Use ё for <unk>, retaining Russian casing and existing ё/Ё letters."""
    def restore(match):
        word=match.group()
        if '<unk>' not in word:return word
        letters=word.replace('<unk>','')
        restored=word.replace('<unk>','Ё' if letters and letters.isupper() else 'ё')
        prefix=text[:match.start()].rstrip(' \t\r\n"«(—')
        if word.startswith('<unk>') and (not prefix or prefix[-1] in '.!?…'):
            restored=restored[0].upper()+restored[1:]
        return restored
    text=_RUSSIAN_TOKEN.sub(restore,text)
    return text.replace('<unk>','ё').replace('е\u0308','ё').replace('Е\u0308','Ё')

def format_ending(text, mode):
    text = text.rstrip()
    if not text:
        return '', False
    if mode == 'space':
        if text.endswith('.') and not text.endswith('..'):
            text=text[:-1].rstrip()
        return text + ' ', False
    if mode in ('period_space', 'period_enter'):
        if text[-1] not in '.!?…。！？':
            text += '.'
        return (text + ' ', False) if mode == 'period_space' else (text, True)
    raise ValueError('Unknown text ending')
