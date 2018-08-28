#!/usr/bin/env python3

import os
import sys
import hashlib
import filecmp
import logging
import argparse

CHUNK_SIZE = 4096

def size(path):
    statinfo = os.stat(path)
    return statinfo.st_size

def md5(path):
    hash_md5 = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def bytecmp(path1, path2):
    stat1 = os.stat(path1)
    stat2 = os.stat(path2)
    if stat1.st_size != stat1.st_size:
        return False
    if (stat1.st_dev, stat1.st_ino) == (stat2.st_dev, stat2.st_ino):
        return True
    return filecmp.cmp(path1, path2, shallow=False)

def preselector(items, reducer):
    items_by_key = {}
    non_uniques_list = []
    items_count = 0
    non_unique_count = 0
    for item in items:
        items_count += 1
        key = reducer(item)
        same_key_list = None
        if key not in items_by_key:
            same_key_list = items_by_key[key] = []
        else:
            same_key_list = items_by_key[key]
            if len(same_key_list) == 1:
                non_uniques_list.append(same_key_list)
                non_unique_count += 1
            non_unique_count += 1
        same_key_list.append(item)
    return items_count, non_unique_count, non_uniques_list

def selector(items, comperator):
    buckets = []
    non_uniques_list = []
    items_count = 0
    non_unique_count = 0
    for item in items:
        items_count += 1
        match = False
        for bucket in buckets:
            if not comperator(item, bucket[0]):
                continue
            if len(bucket) == 1:
                non_uniques_list.append(bucket)
                non_unique_count += 1
            non_unique_count += 1
            bucket.append(item)
            match = True
            break
        if not match:
            buckets.append([item])
    return items_count, non_unique_count, non_uniques_list

def main():
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    
    parser = argparse.ArgumentParser(description='finds efficiently redundant files in different directories and replaces them with hard links')
    parser.add_argument('paths', metavar='path', nargs='+', help='path to look for files in')
    parser.add_argument('--dry-run', action='store_true', help='do not modify anything')
    parser.add_argument('--normalize', action='store_true', help='normalize paths')
    args = parser.parse_args()
    
    # TODO: we could use md5 for small files and something like 4-byte in the middle for large files
    reducers = [size]
    comperator = bytecmp
    
    logging.info('looking for files in %s' % ('"' + '" "'.join(args.paths) + '"'))
    
    # TODO: option to ignore links while searching
    all_paths = set([])
    for p in args.paths:
        for path, subdirs, files in os.walk(p):
            for name in files:
                file_path = os.path.join(path, name)
                if args.normalize:
                    file_path = os.path.realpath(file_path)
                all_paths.add(file_path)
    all_paths = list(all_paths)
    
    logging.info('non-unique %d' % len(all_paths))
    
    non_uniques_list = [all_paths]
    for reducer in reducers:
        logging.info('use reducer %s' % str(reducer))
        next_non_uniques_list = []
        non_unique_count = 0
        for non_uniques in non_uniques_list:
            s = preselector(non_uniques, reducer)
            non_unique_count += s[1]
            next_non_uniques_list.extend(s[-1])
        non_uniques_list = next_non_uniques_list
        logging.info('non-unique %d groups %d' % (non_unique_count, len(non_uniques_list)))
    
    logging.info('use comperator %s' % str(comperator))
    next_non_uniques_list = []
    non_unique_count = 0
    for non_uniques in non_uniques_list:
        s = selector(non_uniques, comperator)
        non_unique_count += s[1]
        next_non_uniques_list.extend(s[-1])
    non_uniques_list = next_non_uniques_list
    logging.info('non-unique %d groups %d' % (non_unique_count, len(non_uniques_list)))
    
    for non_uniques in non_uniques_list:
        print('"' + '" "'.join(non_uniques) + '"')
    
    if args.dry_run:
        logging.info('done (dry run)')
        return
    
    logging.info('creating hardlinks...')
    
    for non_uniques in non_uniques_list:
        for path in non_uniques[1:]:
            os.remove(path)
            os.link(non_uniques[0], path)
    
    logging.info('done')

if __name__ == '__main__':
    code = main()
    sys.exit(code)

