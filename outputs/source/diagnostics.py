"""Opt-in local latency diagnostics; no waveforms, transcript or window titles."""
from contextlib import contextmanager
import json
from pathlib import Path
import threading
import time
import uuid

_write_lock = threading.Lock()


class LatencyTrace:
    def __init__(self, timing=None, output=None):
        timing = timing or {}
        self.identifier = uuid.uuid4().hex
        self.output = Path(output) if output else None
        self.lock = threading.Lock()
        now = time.perf_counter_ns()
        self.marks = {name: timing[name] for name in
                      ('hook_received_ns', 'input_event_ns', 'ui_received_ns') if name in timing}
        self.marks.setdefault('ui_received_ns', now)
        self.stages = {}
        self.audio_seconds = 0.
        self.pasted = False
        self.metadata = {}

    def mark(self, name):
        with self.lock: self.marks[name] = time.perf_counter_ns()

    @contextmanager
    def span(self, name):
        start = time.perf_counter_ns()
        try: yield
        finally:
            with self.lock: self.stages[name] = self.stages.get(name, 0) + time.perf_counter_ns() - start

    def report(self):
        with self.lock:
            marks, stages = dict(self.marks), dict(self.stages)
        def interval(start, end):
            return (marks[end]-marks[start])/1e6 if start in marks and end in marks else None
        audio_ms=sum(stages.get(key,0) for key in ('concatenate','mono16k','accept_waveform'))/1e6
        inference_ms=stages.get('inference',0)/1e6
        ui_to_command=interval('ui_received_ns','paste_command_done_ns')
        return dict(schema=1, id=self.identifier, audio_seconds=self.audio_seconds,
                    **self.metadata,
                    clock='perf_counter_ns', pasted=bool(self.pasted),
                    stages_ms={key: value/1e6 for key,value in stages.items()},
                    marks_ms={key: (value-marks['ui_received_ns'])/1e6 for key,value in marks.items()},
                    windows_delivery_ms=interval('input_event_ns','hook_received_ns'),
                    ui_dispatch_ms=interval('hook_received_ns','ui_received_ns'),
                    worker_start_ms=interval('worker_created_ns','worker_started_ns'),
                    hook_to_paste_command_ms=interval('hook_received_ns','paste_command_done_ns') if self.pasted else None,
                    input_event_to_paste_command_ms=interval('input_event_ns','paste_command_done_ns') if self.pasted else None,
                    ui_to_text_ready_ms=interval('ui_received_ns','text_ready_ns'),
                    ui_to_text_set_ms=interval('ui_received_ns','ui_text_set_ns'),
                    inference_ms=inference_ms,audio_preparation_ms=audio_ms,
                    other_wall_before_paste_ms=max(0,ui_to_command-inference_ms-audio_ms) if ui_to_command is not None else None,
                    physical_release_to_visible_text_ms=None,
                    note='Windows input time is a millisecond estimate; SendInput completion is not target rendering.')

    def write(self):
        if not self.output: return
        try:
            line = json.dumps(self.report(), ensure_ascii=True) + '\n'
            with _write_lock:
                self.output.parent.mkdir(parents=True, exist_ok=True)
                with self.output.open('a', encoding='utf-8') as stream: stream.write(line)
        except OSError:
            pass  # Diagnostics must never discard a successful dictation.
