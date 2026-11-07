"""Opt-in immutable package cache. Each episode still gets a fresh process.

Cache fingerprints include engine bytes and all harness/controller inputs.
Hard links share immutable binaries; unsupported filesystems fall back to copy.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

FILES = ('OpenBFME.exe', 'OpenBFME.console.exe', 'OpenBFME.pck', 'openbfme.windows.template_debug.x86_64.dll')


def prepare_cached(engine, runtime, model, cache_root):
    from run_match import HERE, prepare, sha, read, write
    engine = Path(engine).resolve(); runtime = Path(runtime).resolve()
    source = [HERE/'run_match.py', HERE/'runtime_cache.py', HERE/'match_pack.py', HERE/'arena/simulation_match.gd',
              HERE/'model_only_controller.gd', HERE/'ai_diagnostics.gd']
    source += sorted(p for p in (HERE/'team_ai').rglob('*') if p.is_file() and p.suffix in ('.gd', '.json'))
    fingerprint = {'engine': {name: sha(engine/name) for name in FILES},
                   'source': {str(p.relative_to(HERE)): sha(p) for p in source}, 'model': model}
    key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
    root = Path(cache_root).resolve(); root.mkdir(parents=True, exist_ok=True)
    cache = root/key
    if not cache.exists():
        temporary = root/('.build-'+uuid.uuid4().hex); temporary.mkdir()
        identity = prepare(engine, temporary, model)
        manifest = {'fingerprint': fingerprint, 'identity': identity,
                    'files': {name: sha(temporary/name) for name in FILES}}
        write(temporary/'manifest.json', manifest)
        # No overwrite, shared mutable cache, or partial manifest is accepted.
        temporary.rename(cache)
    manifest = read(cache/'manifest.json')
    if manifest['fingerprint'] != fingerprint: raise ValueError('Runtime cache fingerprint mismatch')
    for name in FILES:
        source_path = cache/name if name == 'OpenBFME.pck' else engine/name
        if sha(source_path) != manifest['files'][name]: raise ValueError('Runtime cache bytes changed: '+name)
        try: os.link(source_path, runtime/name)
        except OSError: shutil.copy2(source_path, runtime/name)
    return manifest['identity']
