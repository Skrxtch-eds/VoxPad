"""Launch VoxPad's PySide6 / Qt Quick interface."""

VERSION = '0.6.2'

def main():
    from qt_app import main as run
    return run()


if __name__ == '__main__':
    main()
