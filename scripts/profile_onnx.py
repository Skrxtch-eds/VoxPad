"""Opt-in sherpa/ORT operator profiling on local speech, in a fresh directory."""
import argparse
from collections import Counter
import gc
import json
from pathlib import Path
import sys
import time
from contextlib import nullcontext

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'outputs/source'))
from engine import Engine
from diagnostics import LatencyTrace
import soundfile as sf


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir',type=Path,required=True)
    parser.add_argument('--audio',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--threads',type=int,default=2)
    parser.add_argument('--app-profile',action='store_true')
    args=parser.parse_args()
    directory=args.output_dir.resolve();directory.mkdir(parents=True,exist_ok=False)
    config=directory/'provider.config'
    audio,rate=sf.read(args.audio,dtype='float32')
    if args.app_profile:
        from cpu_runtime import recognition_cpu
        policy=recognition_cpu('parakeet',args.threads)
    else:policy=nullcontext(None)
    with policy as cpu:
        settings=Path(cpu.provider.removeprefix('cpu:')).read_text('utf-8') if cpu and cpu.provider.startswith('cpu:') else ''
        config.write_text(settings+'ProfilingFilePrefix='+str(directory/'ort').replace('\\','/')+'\n','utf-8')
        engine=Engine(args.model_dir,threads=args.threads,provider='cpu:'+str(config))
        engine.warm_up()
    # A visible gap in each native session separates warm-up calls from speech,
    # without estimating ORT's private clock origin or counting the warm-up.
    time.sleep(1)
    trace=LatencyTrace()
    engine.transcribe(audio,rate,trace=trace)
    del engine;gc.collect()  # Session destruction flushes the native profile.
    profiles=[]
    components={}
    for path in directory.glob('ort*.json'):
        nodes=Counter();events=json.loads(path.read_text('utf-8'))
        for event in events:
            if event.get('cat')=='Node' and event.get('ph')=='X':
                nodes[event.get('args',{}).get('op_name','unknown')]+=event.get('dur',0)
        component=('encoder' if 'ConvInteger' in nodes else
                   'decoder' if 'DynamicQuantizeLSTM' in nodes or 'LSTM' in nodes else
                   'joiner' if 'DynamicQuantizeMatMul' in nodes and 'Relu' in nodes else None)
        runs=[e for e in events if e.get('name')=='model_run' and e.get('ph')=='X']
        gaps=[i for i in range(1,len(runs)) if runs[i]['ts']-runs[i-1]['ts']-runs[i-1]['dur']>900_000]
        measured=runs[gaps[0]:] if len(gaps)==1 else []
        if component and measured and component not in components:
            components[component]=sum(e['dur'] for e in measured)/1e6
        profiles.append(dict(file=path.name,inferred_component=component,
                             measured_speech_calls=len(measured),
                             node_microseconds_including_warmup=dict(nodes.most_common())))
    report=dict(profiles=profiles,
                audio_seconds=len(audio)/rate,
                cpu_profile=cpu.name if cpu else 'standard',
                component_times_seconds=components if len(components)==3 else None,
                inference_envelope_seconds=trace.report()['inference_ms']/1000,
                note='Components inferred from graph operators, not file order. Only model_run calls after the unique one-second warm-up gap are timed; profiling overhead is included. Missing/ambiguous profiles leave component totals unavailable.')
    (directory/'summary.json').write_text(json.dumps(report,indent=2),'utf-8')
    print(f'Native profile files: {len(profiles)}; see {directory / "summary.json"}')


if __name__=='__main__':main()
