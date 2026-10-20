import os
from pathlib import Path


def write_ready_marker(environment_variable):
    path = os.environ.get(environment_variable)
    if path:
        Path(path).touch()
