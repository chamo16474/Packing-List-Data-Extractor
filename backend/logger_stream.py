import logging
import threading
import queue
from typing import Dict

_local = threading.local()

class StreamLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.queues: Dict[str, queue.Queue] = {}

    def emit(self, record):
        job_id = getattr(_local, "job_id", None)
        if job_id and job_id in self.queues:
            try:
                msg = self.format(record)
                self.queues[job_id].put(msg)
            except Exception:
                self.handleError(record)

    def add_job(self, job_id: str):
        self.queues[job_id] = queue.Queue()
        
    def end_job(self, job_id: str):
        if job_id in self.queues:
            self.queues[job_id].put("DONE")

stream_handler = StreamLogHandler()
formatter = logging.Formatter("%(levelname)s | %(name)s | %(message)s")
stream_handler.setFormatter(formatter)

# Add to root logger so it catches everything
logging.getLogger().addHandler(stream_handler)
logging.getLogger().setLevel(logging.INFO)

def set_current_job_id(job_id: str):
    _local.job_id = job_id
