"""Trace the user's supplied icon artwork into editable SVGs (development only)."""
import argparse
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
import vtracer

ROOT = Path(__file__).resolve().parents[1]
SPECS = {
    'mic': ('main screen.png', (508,201,595,311), 132, True),
    'pause': ('main screen.png', (166,224,216,287), 73, False),
    'settings': ('main screen.png', (874,218,947,292), 82, False),
    'back': ('History.png', (880,227,942,282), 76, False),
    'copy': ('main screen.png', (902,1009,964,1070), 61, False),
    'delete': ('History.png', (883,438,938,498), 59, False),
    'history': ('main screen.png', (172,1197,247,1265), 80, False),
    'statistics': ('main screen.png', (621,1195,687,1260), 80, False),
    'edit': ('settings.png', (925,506,962,545), 34, False),
    'chevron': ('settings.png', (933,440,963,464), 26, False),
}


def trace(directory):
    output = ROOT/'docs/design/reference-icons'
    output.mkdir(parents=True,exist_ok=True)
    ns = '{http://www.w3.org/2000/svg}'
    ET.register_namespace('',ns[1:-1])
    contact = Image.new('RGB',(900, len(SPECS)*105),'#f5f5f7')
    from PIL import ImageDraw
    draw = ImageDraw.Draw(contact)
    with tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='icon-trace-') as temporary:
        for row,(name,(source,box,canvas,white)) in enumerate(SPECS.items()):
            crop = Image.open(directory/source).convert('RGB').crop(box)
            tracing_scale = 4
            luminance = np.asarray(crop.convert('L').resize(
                (crop.width*tracing_scale,crop.height*tracing_scale),Image.Resampling.LANCZOS))
            mask = luminance > 155 if white else luminance < 125
            ys,xs = np.where(mask)
            if not len(xs):raise ValueError('Empty icon: '+name)
            bitmap = Image.fromarray(np.where(mask,0,255).astype(np.uint8))
            bitmap_path = Path(temporary)/(name+'.png')
            vector_path = Path(temporary)/(name+'.svg')
            bitmap.save(bitmap_path)
            vtracer.convert_image_to_svg_py(str(bitmap_path),str(vector_path),colormode='binary',
                mode='spline',filter_speckle=8,corner_threshold=70,length_threshold=2.0,
                max_iterations=10,splice_threshold=45,path_precision=3)
            vector = ET.parse(vector_path).getroot()
            target = ET.Element(ns+'svg',{'viewBox':f'0 0 {canvas} {canvas}',
                                        'width':str(canvas),'height':str(canvas)})
            group = ET.SubElement(target,ns+'g',{'transform':
                f'translate({canvas/2-(xs.min()+xs.max()+1)/2/tracing_scale:.3f} '
                f'{canvas/2-(ys.min()+ys.max()+1)/2/tracing_scale:.3f}) scale({1/tracing_scale})'})
            for child in vector:
                if child.tag.endswith('path') or child.tag.endswith('g'):
                    group.append(child)
            ET.ElementTree(target).write(output/(name+'.svg'),encoding='unicode',xml_declaration=False)
            draw.text((15,row*105+35),name,fill='#101010')
            preview = crop.resize((crop.width*2,crop.height*2))
            preview.thumbnail((160,94))
            contact.paste(preview,(155,row*105+4))
    contact.save(ROOT/'work/qml-migration/reference-icon-crops.png')
    print(f'Traced {len(SPECS)} supplied reference icons into {output}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference_directory',type=Path)
    trace(parser.parse_args().reference_directory)
