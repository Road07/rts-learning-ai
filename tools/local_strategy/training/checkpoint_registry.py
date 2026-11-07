"""Load the checkpoint registry by file, independent of the legacy benchmark name."""
from functools import lru_cache
import importlib.util
from pathlib import Path
import sys

@lru_cache(maxsize=1)
def module():
    path=Path(__file__).resolve().with_name('benchmark.py')
    spec=importlib.util.spec_from_file_location('_rts_checkpoint_registry',path)
    loaded=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=loaded
    spec.loader.exec_module(loaded)
    return loaded

def add(*args,**kwargs):
    return module().add(*args,**kwargs)
