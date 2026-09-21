"""Killable native collectors. No camera or raw inventory crosses this pipe.

Each subprocess owns its detector state and returns minimized Result objects.
A timeout retires the collector until a new, consented session starts.
"""
import multiprocessing as mp
import threading
import time
from .models import Result


def _collect(pipe, detector_type):
    detector = detector_type()
    try:
        while pipe.recv() == 'scan':
            try:
                result = detector.scan({})
            except (ImportError, NotImplementedError):
                result = Result(detector.name, 'unsupported', 'Required platform API or optional dependency is unavailable.')
            except Exception:
                result = Result(detector.name, 'error', 'Probe failed or permission was denied; coverage is unknown.')
            pipe.send(result)
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        pipe.close()


class NativeProbe:
    def __init__(self, detector_type, timeout=3):
        self.detector_type = detector_type
        self.name, self.scope = detector_type.name, detector_type.scope
        self.timeout = timeout
        self.process = self.pipe = None
        self.closed = threading.Event()
        self.lifecycle = threading.Lock()

    def scan(self, context):
        # Serialize creation against close. Waiting on native APIs occurs only
        # in the child, never under this lifecycle lock or the engine lock.
        with self.lifecycle:
            if self.closed.is_set():
                return self._unavailable()
            if self.process is None:
                parent, child = mp.get_context('spawn').Pipe()
                self.pipe = parent
                self.process = mp.get_context('spawn').Process(
                    target=_collect, args=(child, self.detector_type), daemon=True)
                try:
                    self.process.start()
                except Exception:
                    parent.close()
                    self.process = self.pipe = None
                    raise
                finally:
                    child.close()
            pipe = self.pipe
        deadline = time.monotonic() + self.timeout
        try:
            pipe.send('scan')
            while not self.closed.is_set() and time.monotonic() < deadline:
                if pipe.poll(.05):
                    return pipe.recv()
        except (EOFError, BrokenPipeError, OSError, TypeError):
            pass
        self.close()
        return self._unavailable()

    def _unavailable(self):
        return Result(self.name, 'error', 'Native collector stopped or exceeded its deadline; coverage is unknown. Start a new session to retry.')

    def close(self):
        self.closed.set()
        with self.lifecycle:
            process, pipe = self.process, self.pipe
            if process is not None:
                # No cooperative pipe send: a blocked receiver must not delay stop.
                if process.is_alive():
                    process.terminate()
                process.join(timeout=.2)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=.2)
                if process.is_alive():
                    raise RuntimeError('Native collector did not exit')
                self.process = None
            if pipe is not None:
                pipe.close()
                self.pipe = None
