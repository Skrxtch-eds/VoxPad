"""Shutdown's completion event must remain available to its dedicated timer."""
import queue
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'outputs/source'))
from qt_controller import Controller


class ShutdownQueueTests(unittest.TestCase):
    def test_poll_stops_when_event_handler_begins_shutdown(self):
        state = SimpleNamespace(active=True, events=queue.Queue(), _phase='ready', preview=True)
        state.events.put(('smoke_finished', True))

        def handle(kind, value):
            self.assertEqual(kind, 'smoke_finished')
            state.active = False
            state.events.put(('closed', None))

        state.handle_event = handle
        Controller.poll(state)
        self.assertEqual(state.events.get_nowait(), ('closed', None))


if __name__ == '__main__':
    unittest.main()
