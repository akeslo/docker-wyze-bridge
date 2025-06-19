from threading import Thread
from typing import Dict

class AutoRemoveThread(Thread):
    def __init__(self, threads: Dict[str, Thread], key: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.threads = threads
        self.key = key

    def run(self):
        try:
            super().run()  # Run the thread's target function
        finally:
            # Remove self from dictionary when thread terminates
            self.threads.pop(self.key, None)