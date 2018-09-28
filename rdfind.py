#!/usr/bin/env python3

import os
import sys
import struct
import hashlib
import filecmp
import logging
import argparse
import time

CHUNK_SIZE = 4096
SMART_LIMIT = 2**10

def get_info(path):
    return { 'path': path, 'stat': os.stat(path) }

def relpath(info):
    return info['relpath']

def fileid(info):
    return info['stat'].st_dev, info['stat'].st_ino

def size(info):
    return info['stat'].st_size

def md5(info):
    hash_md5 = hashlib.md5()
    with open(info['path'], 'rb') as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def fasthash(info):
    # TODO: hash one chunk in the middle?
    # TODO: files smaller than 4 bytes?
    with open(info['path'], 'rb') as f:
        f.seek(size(info) // 2)
        return f.read(4)

def smarthash(info):
    if info['stat'].st_size < SMART_LIMIT:
        return md5(info)
    return fasthash(info)

def bytecmp(info1, info2):
    if info1['stat'].st_size != info2['stat'].st_size:
        return False
    if fileid(info1) == fileid(info2):
        return True
    return filecmp.cmp(info1['path'], info2['path'], shallow=False)

def group(items, reducer, min_size=1, visitor=None):
    items_by_key = {}
    groups_list = []
    items_count = 0
    grouped_count = 0
    for item in items:
        if visitor is not None:
            visitor(item)
        items_count += 1
        key = reducer(item)
        same_key_list = None
        if key not in items_by_key:
            same_key_list = items_by_key[key] = []
        else:
            same_key_list = items_by_key[key]
        if len(same_key_list) == min_size:
            groups_list.append(same_key_list)
            grouped_count += min_size
        if len(same_key_list) >= min_size:
            grouped_count += 1
        same_key_list.append(item)
    return items_count, grouped_count, groups_list

def selector(items, comperator, min_size=2, visitor=None):
    buckets = []
    groups_list = []
    items_count = 0
    grouped_count = 0
    for item in items:
        if visitor is not None:
            visitor(item)
        items_count += 1
        match = False
        for bucket in buckets:
            if not comperator(item, bucket[0]):
                continue
            if len(bucket) == min_size:
                groups_list.append(bucket)
                grouped_count += min_size
            if len(bucket) >= min_size:
                grouped_count += 1
            bucket.append(item)
            match = True
            break
        if not match:
            buckets.append([item])
    return items_count, grouped_count, groups_list

def by_first_parent(infos, parents):
    for p in parents:
        for i in infos:
            if i['path'].startswith(p):
                return i
    return None

def printProgressBar(p, prefix='', suffix='', decimals=1, length=50, fill='█'):
    percent = ("{0:." + str(decimals) + "f}").format(100 * p)
    filledLength = int(length * p)
    bar = fill * filledLength + '-' * (length - filledLength)
    if prefix: prefix = ' ' + prefix
    print('\r%s|%s| %s%% %s' % (prefix, bar, percent, suffix), end = '\r')
    if p >= 1:
        print()

def progress(total, prefix='', suffix='', decimals=1):
    i = 0
    last_p = 0
    def foo(*args):
        nonlocal i
        nonlocal last_p
        i += 1
        p = float(i) / total
        if p - last_p >= (10 ** -(2 + decimals)):
            printProgressBar(p, prefix=prefix, suffix=suffix)
            last_p = p
    return foo

def main():
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    
    # TODO: we could add an heuristic mode and probability limit (https://www.johndcook.com/blog/2017/01/10/probability-of-secure-hash-collisions/)
    parser = argparse.ArgumentParser(description='finds efficiently redundant files in different directories and replaces them with hard links')
    parser.add_argument('paths', metavar='path', nargs='+', help='path to look for files in')
    parser.add_argument('--dry-run', action='store_true', help='do not modify anything')
    parser.add_argument('--normalize', action='store_true', help='normalize paths')
    parser.add_argument('--groupby-relative', action='store_true', help='group files by relative path')
    parser.add_argument('--min-size', type=int, default=4096, help='minimal file size')
    parser.add_argument('--max-size', type=int, default=9223372036854775807, help='maximal file size')
    parser.add_argument('--merge', choices=['max', 'order'], default='max', help='merging strategy')
    parser.add_argument('--mtime', choices=['order', 'newest', 'merge'], default='order', help='mtime merge strategy')
    parser.add_argument('--smarthash', action='store_true', help='accelerate hashing for small files')
    args = parser.parse_args()
    
    # TODO: remove same file id first
    
    reducers = [size, smarthash if args.smarthash else md5]
    comperator = bytecmp
    
    if args.groupby_relative:
        reducers = [relpath] + reducers
    
    paths = [os.path.realpath(p) for p in args.paths]
    logging.info('looking for files in %s' % ('"' + '" "'.join(paths) + '"'))
    
    items = []
    for path in paths:
        for parent, subdirs, files in os.walk(path):
            for name in files:
                file_path = os.path.join(parent, name)
                if args.normalize:
                    file_path = os.path.realpath(file_path)
                info = get_info(file_path)
                if not args.min_size < info['stat'].st_size < args.max_size:
                    continue
                if args.groupby_relative:
                    info['relpath'] = os.path.join(os.path.relpath(parent, path), name)
                items.append(info)
    
    logging.info('%d items' % len(items))
    
    total = len(items)
    groups_list = [items]
    for i, reducer in enumerate(reducers):
        logging.info('use reducer %s (%d of %d)' % (reducer.__name__, i+1, len(reducers)))
        next_groups_list = []
        grouped_count = 0
        prog = progress(total)
        for g in groups_list:
            s = group(g, reducer, visitor=prog)
            grouped_count += s[1]
            next_groups_list.extend(s[-1])
        total = grouped_count
        groups_list = next_groups_list
        logging.info('%d itmes %d groups' % (grouped_count, len(groups_list)))
    
    logging.info('use comperator %s' % comperator.__name__)
    total = grouped_count
    next_groups_list = []
    grouped_count = 0
    prog = progress(total)
    for g in groups_list:
        s = selector(g, comperator, visitor=prog)
        grouped_count += s[1]
        next_groups_list.extend(s[-1])
    groups_list = next_groups_list
    logging.info('%d itmes %d groups' % (grouped_count, len(groups_list)))
    
    for g in groups_list:
        print('"' + '" "'.join(i['path'] for i in g) + '"')
    
    if args.dry_run:
        logging.info('done (dry run)')
        return
    
    logging.info('creating hardlinks...')
    
    for g in groups_list:
        origin = None
        if args.merge == 'max':
            grouped_by_fileid = group(g, fileid, min_size=0)
            origin = max(grouped_by_fileid[-1], key=lambda g: len(g))[0]
        elif args.merge == 'order':
            origin = by_first_parent(g, paths)
        
        mtime_ns = None
        if args.mtime == 'merge':
            mtime_ns = origin['stat'].st_mtime_ns
        elif args.mtime == 'order':
            mtime_ns = by_first_parent(g, paths)['stat'].st_mtime_ns
        elif args.mtime == 'max':
            mtime_ns = max((info['stat'].st_mtime_ns for info in g))
        os.utime(origin['path'], ns=(mtime_ns, mtime_ns))
        
        for info in g:
            if info['path'] == origin['path']:
                continue
            os.remove(info['path'])
            os.link(origin['path'], info['path'])
    
    logging.info('done')

if __name__ == '__main__':
    code = main()
    sys.exit(code)

