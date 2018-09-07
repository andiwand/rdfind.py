#!/usr/bin/env python3

import os
import sys
import struct
import hashlib
import filecmp
import logging
import argparse

CHUNK_SIZE = 4096
SMART_LIMIT = 2**10

def get_info(path):
    return { 'path': path, 'stat': os.stat(path) }

def paths(infos):
    return (info['path'] for info in infos)

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

def group(items, reducer, min_size=1):
    items_by_key = {}
    groups_list = []
    items_count = 0
    grouped_count = 0
    for item in items:
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
        elif len(same_key_list) >= min_size:
            grouped_count += 1
        same_key_list.append(item)
    return items_count, grouped_count, groups_list

def selector(items, comperator, min_size=1):
    buckets = []
    groups_list = []
    items_count = 0
    grouped_count = 0
    for item in items:
        items_count += 1
        match = False
        for bucket in buckets:
            if not comperator(item, bucket[0]):
                continue
            if len(bucket) == min_size:
                groups_list.append(bucket)
                grouped_count += min_size
            elif len(bucket) >= min_size:
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

def main():
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    
    # TODO: add verbose mode
    # TODO: add progress
    # TODO: we could add an heuristic mode and probability limit (https://www.johndcook.com/blog/2017/01/10/probability-of-secure-hash-collisions/)
    parser = argparse.ArgumentParser(description='finds efficiently redundant files in different directories and replaces them with hard links')
    parser.add_argument('paths', metavar='path', nargs='+', help='path to look for files in')
    parser.add_argument('--dry-run', action='store_true', help='do not modify anything')
    parser.add_argument('--normalize', action='store_true', help='normalize paths')
    parser.add_argument('--min-size', type=int, default=4096, help='minimal file size')
    parser.add_argument('--max-size', type=int, default=9223372036854775807, help='maximal file size')
    parser.add_argument('--merge', choices=['max', 'order'], default='max', help='merging strategy')
    parser.add_argument('--mtime', choices=['order', 'newest', 'merge'], default='order', help='mtime merge strategy')
    args = parser.parse_args()
    
    # TODO: group by fileid
    
    reducers = [size, md5]
    comperator = bytecmp
    
    paths = [os.path.realpath(p) for p in args.paths]
    logging.info('looking for files in %s' % ('"' + '" "'.join(paths) + '"'))
    
    items = []
    for p in paths:
        for path, subdirs, files in os.walk(p):
            for name in files:
                file_path = os.path.join(path, name)
                if args.normalize:
                    file_path = os.path.realpath(file_path)
                info = get_info(file_path)
                if args.min_size < info['stat'].st_size < args.max_size:
                    items.append(info)
    
    logging.info('%d items' % len(items))
    
    groups_list = [items]
    for reducer in reducers:
        logging.info('use reducer %s' % str(reducer))
        next_groups_list = []
        grouped_count = 0
        for g in groups_list:
            s = group(g, reducer)
            grouped_count += s[1]
            next_groups_list.extend(s[-1])
        groups_list = next_groups_list
        logging.info('%d itmes %d groups' % (grouped_count, len(groups_list)))
    
    logging.info('use comperator %s' % str(comperator))
    next_groups_list = []
    grouped_count = 0
    for g in groups_list:
        s = selector(g, comperator)
        grouped_count += s[1]
        next_groups_list.extend(s[-1])
    groups_list = next_groups_list
    logging.info('%d itmes %d groups' % (grouped_count, len(groups_list)))
    
    for g in groups_list:
        print('"' + '" "'.join(paths(g)) + '"')
    
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
            origin = by_first_parent(groups_list, paths)
        
        # TODO: use integer; example file wrike/attachments/IEABQIGWIYBZW6DI-LOGSOL_EU-DSGVO_Datenschutzerklaerung.pdf
        mtime_ns = None
        if args.mtime == 'merge':
            mtime_ns = origin['stat'].st_mtime_ns
        elif args.mtime == 'order':
            mtime_ns = by_first_parent(groups_list, paths)['stat'].st_mtime_ns
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

