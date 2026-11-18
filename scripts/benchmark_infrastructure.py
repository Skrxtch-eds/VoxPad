"""Isolate disk/UI-queue overhead with a stub ASR and stub Windows paste.

This is NOT an ASR speed test or a physical key-release-to-text measurement.
Real temporary SQLite is used, with no user data changes.
"""
import argparse
import json
import os
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path,default=root/'outputs/source')
    parser.add_argument('--repeats',type=int,default=31)
    parser.add_argument('--disk-delay',type=float,default=0)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.repeats<1 or args.disk_delay<0:parser.error('Invalid repeats or delay')
    os.environ['VOXPAD_BENCH_SOURCE']=str(args.source_dir.resolve())
    from benchmark_asr import pipeline
    import numpy as np
    class StubEngine:
        def transcribe(self,*args,**kwargs):return 'Infrastructure fixture',0.
    audio=np.full(5*48000,.01,dtype=np.float32)
    rows=[pipeline(StubEngine(),audio,48000,args.disk_delay)[1] for _ in range(args.repeats)]
    report=dict(scenario='headless_infrastructure_stub_asr',source_dir=str(args.source_dir),
                disk_delay_seconds=args.disk_delay,repeats=args.repeats,
                latency_p50_ms=float(np.percentile([r['pipeline_surrogate_seconds']*1000 for r in rows],50)),
                latency_p95_ms=float(np.percentile([r['pipeline_surrogate_seconds']*1000 for r in rows],95)),
                history_p50_ms=float(np.percentile([r['history_seconds']*1000 for r in rows],50)),
                runs=rows,physical_release_to_visible_text_ms=None)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),'utf-8')
    print({key:value for key,value in report.items() if key!='runs'})


if __name__=='__main__':main()
