"""Record three local references once, then benchmark them automatically."""
import argparse
import json
import os
from pathlib import Path

import sounddevice as sd
import soundfile as sf

PHRASES = (
    ('short_ru', 3, 'Сегодня хорошая погода.'),
    ('mixed_technical', 8, 'Открой GitHub, проверь pull request и запусти Python тесты для ONNX Runtime.'),
    ('long_ru', 15, 'Это проверка локального распознавания речи. Программа должна сохранить начало и конец фразы, правильно записать русские слова и английские названия, а затем быстро вставить готовый текст.'),
)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--device',type=int)
    parser.add_argument('--list-devices',action='store_true')
    args=parser.parse_args()
    if args.list_devices:
        print(sd.query_devices());return
    args.output_dir.mkdir(parents=True,exist_ok=True)
    manifest=args.output_dir/'manifest.json'
    if manifest.exists() or any((args.output_dir/(key+'.wav')).exists() for key,_,_ in PHRASES):
        parser.error('Choose a fresh directory; existing originals are never overwritten')
    rate=int(sd.query_devices(args.device,'input')['default_samplerate'])
    clips=[]
    for key,seconds,reference in PHRASES:
        print(f'\nRead this phrase within {seconds} seconds:\n{reference}')
        input('Press Enter when ready. Recording starts immediately: ')
        print('Recording…',flush=True)
        recording=sd.rec(seconds*rate,samplerate=rate,channels=1,dtype='float32',device=args.device)
        sd.wait()
        path=args.output_dir/(key+'.wav')
        with path.open('xb') as stream:
            sf.write(stream,recording,rate,format='WAV',subtype='FLOAT')
            stream.flush();os.fsync(stream.fileno())
        exact=input('If you said a different phrase, enter the exact words; otherwise press Enter: ').strip()
        clips.append(dict(id=key,path=path.name,reference=exact or reference))
        # Persist progress after each clip so an interrupted session retains it.
        temporary=manifest.with_suffix('.json.tmp')
        with temporary.open('w',encoding='utf-8') as stream:
            json.dump(clips,stream,ensure_ascii=False,indent=2)
            stream.flush();os.fsync(stream.fileno())
        temporary.replace(manifest)
    print(f'Local references saved: {manifest}')


if __name__=='__main__':main()
