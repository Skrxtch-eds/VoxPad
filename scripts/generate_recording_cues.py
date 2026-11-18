"""Synthesize VoxPad's original warm glass cues. No downloaded samples."""
from pathlib import Path
import json

import numpy as np
from scipy.signal import resample_poly
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'outputs/source/assets'
RATE = 48000
OVERSAMPLE = 4


def glass_note(time, frequency, onset, decay, gain):
    age = np.maximum(time - onset, 0.)
    # The tiny pitch relaxation and short overtones give a rounded glass pluck.
    phase = 2 * np.pi * frequency * (age + .012 * .012 * (1 - np.exp(-age / .012)))
    envelope = (1 - np.exp(-age / .006)) ** 2 * np.exp(-age / decay)
    fundamental = np.sin(phase)
    overtones = .13 * np.sin(phase * 2.003) * np.exp(-age / .045)
    overtones += .025 * np.sin(phase * 3.997) * np.exp(-age / .022)
    return gain * envelope * (fundamental + overtones) * (time >= onset)


def cue(kind):
    duration = .260 if kind == 'start' else .330
    time = np.arange(round(duration * RATE * OVERSAMPLE)) / (RATE * OVERSAMPLE)
    if kind == 'start':
        # A4 with a gentle E5 answer: lower, warm and inviting.
        notes = ((440., .008, .060, 1.), (659.255, .050, .055, .38))
        peak = .46
    else:
        # E5 and A5: a brighter, higher resolution in the same tonal palette.
        notes = ((659.255, .008, .075, .9), (880., .058, .070, .42))
        peak = .42
    dry = sum(glass_note(time, *note) for note in notes)
    channels = []
    for reflections in (((.013, .065), (.031, .035)), ((.019, .065), (.037, .035))):
        channel = dry.copy()
        for delay, gain in reflections:
            shift = round(delay * RATE * OVERSAMPLE)
            channel[shift:] += dry[:-shift] * gain
        channels.append(channel)
    audio = resample_poly(np.stack(channels, axis=1), 1, OVERSAMPLE, axis=0)
    # Silence at both boundaries prevents clicks, even on very short retriggers.
    fade = round(.030 * RATE)
    audio[-fade:] *= np.linspace(1., 0., fade)[:, None] ** 2
    audio *= peak / np.max(np.abs(audio))
    audio[0] = audio[-1] = 0.
    return audio


def main():
    result = {}
    for kind in ('start', 'stop'):
        audio = cue(kind)
        path = ASSETS / f'record-{kind}.wav'
        sf.write(path, audio, RATE, subtype='PCM_16')
        result[kind] = dict(path=str(path), duration_ms=round(len(audio) / RATE * 1000),
                            peak=round(float(np.max(np.abs(audio))), 3),
                            rms=round(float(np.sqrt(np.mean(audio ** 2))), 3))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
