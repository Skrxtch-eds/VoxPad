"""Regenerate library icon PNGs; install requirements-dev.txt first."""
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
import qtawesome

ROOT = Path(__file__).resolve().parents[1]
ICONS = {
    'mic': 'ph.microphone-light', 'pause': 'ph.pause-fill',
    'play': 'ph.play-fill', 'stop': 'ph.stop-fill',
    'settings': 'mdi6.cog-outline', 'back': 'ph.arrow-left',
    'copy': 'ph.copy', 'delete': 'ph.trash-simple',
    'history': 'ph.clock-counter-clockwise', 'statistics': 'ph.chart-bar',
    'edit': 'ph.pencil-simple', 'chevron': 'ph.caret-down',
}
LUCIDE = {'settings':'settings', 'copy':'copy', 'delete':'trash-2', 'history':'history',
          'statistics':'chart-no-axes-column-increasing', 'edit':'pencil',
          'chevron':'chevron-down', 'back':'arrow-left'}


if __name__ == '__main__':
    app = QApplication([])
    directory = ROOT / 'outputs/source/assets/icons'
    directory.mkdir(parents=True, exist_ok=True)
    for name, glyph in ICONS.items():
        for suffix, color in [('', '#101010'), ('-white', '#ffffff')]:
            target = str(directory/(name+suffix+'.png'))
            reference = ROOT/'docs/design/reference-icons'/(name+'.svg')
            if reference.exists() or name in LUCIDE:
                path = reference if reference.exists() else ROOT/'docs/design/lucide'/(LUCIDE[name]+'.svg')
                svg = path.read_text('utf-8')
                svg = svg.replace('currentColor',color).replace('fill="#000000"',f'fill="{color}"').replace('fill="black"',f'fill="{color}"')
                renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
                image = QImage(256,256,QImage.Format_ARGB32_Premultiplied)
                image.fill(Qt.transparent)
                painter = QPainter(image)
                renderer.render(painter)
                painter.end()
                image.save(target)
            else:
                qtawesome.icon(glyph, color=color).pixmap(256,256).save(target)
    print(f'Generated {len(ICONS)*2} library icon assets')
