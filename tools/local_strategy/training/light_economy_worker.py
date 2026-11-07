"""SB3-compatible environment worker without importing SB3/PyTorch.

All policy inference/training stays in the original parent process.
stdout is diagnostic only; authenticated Connection carries the protocol.
"""
import argparse
import sys
import traceback
import socket
from multiprocessing.connection import Client


def serve(remote):
    import cloudpickle
    env = None
    reset_info = {}
    try:
        command, payload = remote.recv()
        if command != 'init':
            raise ValueError('Expected initialization')
        env = cloudpickle.loads(payload)()
        if 'torch' in sys.modules:
            raise RuntimeError('Light environment worker unexpectedly imported torch')
        while True:
            command, data = remote.recv()
            if command == 'step':
                observation, reward, terminated, truncated, info = env.step(data)
                done = terminated or truncated
                info['TimeLimit.truncated'] = truncated and not terminated
                if done:
                    info['terminal_observation'] = observation
                    observation, reset_info = env.reset()
                remote.send((observation, reward, done, info, reset_info))
            elif command == 'reset':
                options = {'options': data[1]} if data[1] else {}
                observation, reset_info = env.reset(seed=data[0], **options)
                remote.send((observation, reset_info))
            elif command == 'get_spaces':
                remote.send((env.observation_space, env.action_space))
            elif command == 'env_method':
                remote.send(env.get_wrapper_attr(data[0])(*data[1], **data[2]))
            elif command == 'get_attr':
                remote.send(env.get_wrapper_attr(data))
            elif command == 'has_attr':
                try:
                    env.get_wrapper_attr(data); remote.send(True)
                except AttributeError:
                    remote.send(False)
            elif command == 'set_attr':
                remote.send(setattr(env, data[0], data[1]))
            elif command == 'is_wrapped':
                current = env
                found = False
                while hasattr(current, 'env'):
                    if isinstance(current, data):
                        found = True; break
                    current = current.env
                remote.send(found)
            elif command == 'render':
                remote.send(env.render())
            elif command == 'close':
                break
            else:
                raise ValueError('Unknown vector command: ' + command)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        if env is not None:
            env.close()
        remote.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--auth', required=True)
    args = parser.parse_args()
    remote = Client(('127.0.0.1', args.port), authkey=bytes.fromhex(args.auth))
    sock=socket.socket(fileno=remote.fileno())
    try:sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
    finally:sock.detach()
    serve(remote)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        traceback.print_exc()
        raise
