from datetime import datetime


class Cache(object):
    """
    Simple cache class to cache anything.
    """

    def __init__(self, expiry_time=60):
        self.expiry_time = expiry_time
        self.cache = {}
        self._timestamps = {}

    def get(self, key):
        return self.cache.get(key)

    def get_timestamp(self, key):
        return self._timestamps.get(key)

    def set(self, key, value):
        self.cache[key] = value
        self._timestamps[key] = datetime.utcnow()

    def delete(self, key):
        del self.cache[key]
        del self._timestamps[key]

    def is_expired(self, key):
        if key not in self._timestamps.keys():
            return True

        return (datetime.utcnow() - self._timestamps[key]).seconds > self.expiry_time

    def has(self, key):
        return key in self.cache.keys()

    def clear(self):
        self.cache = {}

    def __contains__(self, key):
        return key in self.cache.keys() and key in self._timestamps.keys()

    def __getitem__(self, key):
        return self.cache[key]

    def __setitem__(self, key, value):
        self.cache[key] = value
        self._timestamps[key] = datetime.utcnow()

    def __delitem__(self, key):
        del self.cache[key]
        del self._timestamps[key]

    def __len__(self):
        return len(self.cache)

    def __iter__(self):
        return iter(self.cache)

    def __repr__(self):
        return repr(self.cache)

    def __str__(self):
        return str(self.cache)
