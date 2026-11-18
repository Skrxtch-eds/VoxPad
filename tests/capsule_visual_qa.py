"""Synthetic capsule previews and CPU timings; no desktop capture or microphone."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import statistics
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'outputs/source'))
from recording_overlay import CapsuleMotion, MonitorInfo, RecordingOverlay

OUT = ROOT / 'work/capsule-qa'


def renderer():
    info = MonitorInfo()
    info.size = ctypes.sizeof(info)
    info.monitor = wintypes.RECT(0, 0, 2880, 1920)
    info.work = wintypes.RECT(0, 0, 2880, 1872)
    result = RecordingOverlay.__new__(RecordingOverlay)
    result.configure_monitor(info)
    width, height = result.scaled(result.width), result.scaled(result.height)
    x = np.linspace(0, 1, width)[None, :, None]
    y = np.linspace(0, 1, height)[:, None, None]
    pixels = np.array([23, 48, 69]) + x * np.array([46, 25, 47]) + y * np.array([11, 15, 16])
    backdrop = Image.fromarray(np.uint8(pixels))
    draw = ImageDraw.Draw(backdrop)
    draw.rectangle((width * .56, 0, width * .66, height), fill='#9f8c86')
    started = time.perf_counter()
    result.prepare_surface(backdrop)
    preparation = (time.perf_counter() - started) * 1000
    return result, preparation


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    capsule, preparation = renderer()
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 18)
    sheet = Image.new('RGB', (1080, 740), '#10151f')
    draw = ImageDraw.Draw(sheet)
    draw.text((32, 20), 'VoxPad / liquid glass capsule', font=font, fill='#eef3ff')
    for index, amp in enumerate((0., .25, .55, .85, 1., .7)):
        image = capsule.render(.6 + index * .16, amp)
        x, y = 30 + index % 3 * 355, 62 + index // 3 * 220
        sheet.paste(image, (x, y), image)
        draw.text((x + 20, y + 180), f'Amplitude {amp:.2f}', font=font, fill='#acb9d0')
    draw.text((32, 525), '320 ms entrance: smooth rise / brake / expand', font=font, fill='#eef3ff')
    for index, milliseconds in enumerate((0, 60, 120, 180, 240, 320)):
        capsule.motion_phase = 'enter'
        capsule.motion_started = 0.
        motion = capsule.advance_motion(milliseconds / 1000)
        image = capsule.morph_frame(capsule.render(0., 0.), motion.shape)
        image.thumbnail((162, 126), Image.Resampling.LANCZOS)
        sheet.paste(image, (14 + index * 177 + (162 - image.width) // 2, 570 + (126 - image.height) // 2), image)
        draw.text((55 + index * 177, 704), f'{milliseconds} ms', font=font, fill='#acb9d0')
    sheet.save(OUT / 'capsule-contact-sheet.png')

    frames = []
    view_origin=(round(capsule.x+capsule.scaled(capsule.width)/2-210),
                 round(capsule.y+capsule.scaled(capsule.height)/2-140))
    taskbar_top=capsule.work_area[3]-view_origin[1]
    for index in range(150):
        elapsed = index / 60
        if elapsed <= capsule.enter_duration:
            capsule.motion_phase = 'enter'; capsule.motion_started = 0.
            motion = capsule.advance_motion(elapsed)
            amp = 0.
        elif elapsed < 2.:
            motion = CapsuleMotion()
            amp = (.5 + .5 * np.sin((elapsed - .3) * 4)) * .9
        else:
            capsule.motion_phase = 'exit'; capsule.motion_started = 2.
            capsule.exit_from = CapsuleMotion()
            motion = capsule.advance_motion(elapsed)
            amp = 0.
        image = capsule.morph_frame(capsule.render(elapsed, amp * motion.shape ** 2), motion.shape)
        capsule.motion=motion
        position=capsule.frame_position(image)
        image=capsule.clip_to_work_area(image,position)
        canvas = Image.new('RGB', (420, 340), '#10151f')
        desktop=ImageDraw.Draw(canvas)
        desktop.rectangle((0,taskbar_top,420,taskbar_top+48),fill='#202c3e')
        desktop.text((18,taskbar_top+12),'Synthetic taskbar / orb hidden behind it',font=font,fill='#acb9d0')
        if image is not None:
            alpha = image.getchannel('A').point(lambda value: round(value * motion.opacity))
            image.putalpha(alpha)
            canvas.paste(image,(position[0]-view_origin[0],position[1]-view_origin[1]),image)
        if index in (4,129):
            canvas.save(OUT/('taskbar-entrance.png' if index==4 else 'taskbar-exit.png'))
        frames.append(canvas)
    frames[0].save(OUT / 'capsule-motion.webp', save_all=True, append_images=frames[1:], duration=17, loop=0, quality=85)

    samples = []
    for index in range(245):
        start = time.perf_counter()
        capsule.render(index / 120, .7)
        if index >= 5:
            samples.append((time.perf_counter() - start) * 1000)
    result = dict(preparation_ms=round(preparation, 2), render_median_ms=round(statistics.median(samples), 2),
                  render_p95_ms=round(sorted(samples)[int(len(samples) * .95)], 2), target_fps=capsule.fps,
                  glass_source=(capsule.width*capsule.scale,capsule.height*capsule.scale),
                  wave_source=capsule.wave_size, output=capsule.output_frame.size)
    (OUT / 'timings.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
