"""Normalize dictation spelling and preserve model punctuation at insertion."""
import re

_RUSSIAN_TOKEN=re.compile(r'(?<!\w)(?:[А-Яа-яЁё]|<unk>)+(?!\w)')


def normalize_transcript(text):
    """Retain the legacy Russian-word repair, without guessing other unknowns.

    <unk> is not a universal spelling of ё. In isolation, other languages and
    apparent paired quotation markers, retain the uncertainty explicitly.
    """
    def restore(match):
        word=match.group()
        if '<unk>' not in word:return word
        letters=word.replace('<unk>','')
        if not letters or (word.startswith('<unk>') and word.endswith('<unk>')):return word
        restored=word.replace('<unk>','Ё' if letters and letters.isupper() else 'ё')
        prefix=text[:match.start()].rstrip(' \t\r\n"«(—')
        if word.startswith('<unk>') and (not prefix or prefix[-1] in '.!?…'):
            restored=restored[0].upper()+restored[1:]
        return restored
    text=_RUSSIAN_TOKEN.sub(restore,text)
    return text.replace('е\u0308','ё').replace('Е\u0308','Ё')

def format_ending(text):
    text=text.rstrip()
    return text+' ' if text else ''
