#!/usr/bin/env python3

import os
import sys
import hashlib
import logging
import argparse
import csv

CHUNK_SIZE = 4096
STATS = ['st_ino', 'st_dev', 'st_nlink', 'st_size', 'st_mtime_ns']

def get_info(path):
    result = {}
    result['path'] = path
    stat = os.stat(path)
    for st in STATS:
        result[st] = getattr(stat, st)
    return result

def md5(path):
    hash_md5 = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def index(paths, normalize=False, min_size=0, max_size=9223372036854775807, hashfunc=None):
    items = []
    for p in paths:
        for path, subdirs, files in os.walk(p):
            for name in files:
                file_path = os.path.join(path, name)
                if normalize:
                    file_path = os.path.realpath(file_path)
                info = get_info(file_path)
                if not min_size < info['st_size'] < max_size:
                    continue
                if hashfunc is not None:
                    info['hash'] = hashfunc(file_path)
                items.append(info)
    return items

def main():
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    
    parser = argparse.ArgumentParser(description='create an index of the given directories')
    parser.add_argument('paths', metavar='path', nargs='+', help='path to look for files in')
    parser.add_argument('csv', help='output csv path')
    parser.add_argument('--normalize', action='store_true', help='normalize paths')
    parser.add_argument('--min-size', type=int, default=0, help='minimal file size')
    parser.add_argument('--max-size', type=int, default=9223372036854775807, help='maximal file size')
    parser.add_argument('--hash', choices=['none','md5'], default='none', help='hash function to use')
    args = parser.parse_args()
    
    paths = [os.path.realpath(p) for p in args.paths]
    info_keys = ['path'] + STATS
    hashfunc = None
    if args.hash == 'md5':
        info_keys += ['hash']
        hashfunc = md5
    
    logging.info('looking for files in %s' % ('"' + '" "'.join(paths) + '"'))
    
    items = index(paths, normalize=args.normalize,
            min_size=args.min_size, max_size=args.max_size, hashfunc=hashfunc)

    logging.info('%d items found' % len(items))

    with open(args.csv, 'w') as f:
        writer = csv.DictWriter(f, fieldnames=info_keys)
        writer.writeheader()
        for i in items:
            writer.writerow(i)
    
    logging.info('done')

if __name__ == '__main__':
    code = main()
    sys.exit(code)

