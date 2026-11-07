"""Gate child creation until the GUI has assigned this process to its private job."""
import argparse
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate', type=Path, required=True)
    parser.add_argument('--mode', choices=('train', 'random', 'check'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--parallel', type=int, default=8)
    parser.add_argument('--timesteps', type=int, default=200000)
    args = parser.parse_args()
    deadline = time.monotonic() + 30
    while not args.gate.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('Launcher gate timed out')
        time.sleep(.05)
    if args.mode == 'check':
        print('Launcher process gate OK; no training started.', flush=True)
        return 0
    script = Path(__file__).with_name('train_economy.py' if args.mode == 'train' else 'random_economy.py')
    command = [sys.executable, '-u', str(script), '--output', str(args.output)]
    if args.mode == 'train':
        command += ['--parallel', str(args.parallel), '--timesteps', str(args.timesteps),'--light-workers','--reuse-package']
    return subprocess.call(command)


if __name__ == '__main__':
    raise SystemExit(main())
