
import itertools
import threading


def deep_get(d, path, default=None):
    """
    Take array or string as the path to a dict item and return the item or default if path does not exist.
    """
    if not d or not path:
        return d

    parts = path.split(".") if isinstance(path, str) else path
    return (
        deep_get(d.get(parts[0]), parts[1:], default)
        if d.get(parts[0]) is not None
        else default
    )


class FastWriteCounter(object):
    """
    https://github.com/jd/fastcounter
    https://julien.danjou.info/atomic-lock-free-counters-in-python/
    """

    __slots__ = (
        "_number_of_read",
        "_counter",
        "_lock",
        "_step",
    )

    def __init__(self, init=0, step=1):
        self._number_of_read = 0
        self._step = step
        self._counter = itertools.count(init, step)
        self._lock = threading.Lock()

    def increment(self):
        next(self._counter)

    @property
    def value(self):
        with self._lock:
            value = next(self._counter) - self._number_of_read
            self._number_of_read += self._step
        return value

