"""Randomized delay helper so website scraping doesn't hammer target servers."""
import random
import time


class RandomDelay:
    def __init__(self, min_seconds: float = 1.5, max_seconds: float = 4.0):
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds

    def wait(self):
        delay = random.uniform(self.min_seconds, self.max_seconds)
        time.sleep(delay)
        return delay
