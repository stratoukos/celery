from __future__ import absolute_import

from kombu.utils import cached_property
from kombu.utils.eventio import poll, READ, WRITE, ERR

from celery.utils.timer2 import Schedule


class BoundedSemaphore(object):

    def __init__(self, value=1):
        self.initial_value = self.value = value
        self._waiting = []

    def grow(self):
        self.initial_value += 1

    def shrink(self):
        self.initial_value -= 1

    def acquire(self, callback, *partial_args, **partial_kwargs):
        if self.value <= 0:
            self._waiting.append((callback, partial_args))
            return False
        else:
            self.value = max(self.value - 1, 0)
            callback(*partial_args, **partial_kwargs)
            return True

    def release(self):
        self.value = min(self.value + 1, self.initial_value)
        if self._waiting:
            waiter, args = self._waiting.pop()
            waiter(*args)

    def clear(self):
        pass


class Hub(object):
    READ, WRITE, ERR = READ, WRITE, ERR

    def __init__(self, timer=None):
        self.fdmap = {}
        self.poller = poll()
        self.timer = Schedule() if timer is None else timer

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return self.close()

    def fire_timers(self, min_delay=1, max_delay=10, max_timers=10):
        delay = None
        if self.timer._queue:
            for i in xrange(max_timers):
                delay, entry = self.scheduler.next()
                if entry is None:
                    break
                self.timer.apply_entry(entry)
        return min(max(delay, min_delay), max_delay)

    def add(self, fd, callback, flags):
        self.poller.register(fd, flags)
        try:
            fileno = fd.fileno()
        except AttributeError:
            fileno = fd
        self.fdmap[fileno] = callback

    def add_reader(self, fd, callback):
        return self.add(fd, callback, READ | ERR)

    def add_writer(self, fd, callback):
        return self.add(fd, callback, WRITE)

    def update_readers(self, *maps):
        [self.add_reader(*x) for row in maps for x in row.iteritems()]

    def update_writers(self, *maps):
        [self.add_writer(*x) for row in maps for x in row.iteritems()]

    def remove(self, fd):
        try:
            self.poller.unregister(fd)
        except (KeyError, OSError):
            pass

    def close(self):
        [self.remove(fd) for fd in self.fdmap.keys()]
        self.poller.close()

    @cached_property
    def scheduler(self):
        return iter(self.timer)
