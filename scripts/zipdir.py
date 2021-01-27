import os
import json
import argparse
from pathlib import Path
from subprocess import Popen, PIPE
from zipfile import ZipFile, ZIP_DEFLATED

PACK_IGNORE_FILENAME = 'zipdir.json'
EXCLUDE_FILE_KEYS = [
    'exclude_folder_path',
    'exclude_folder_name',
    'exclude_file_path',
    'exclude_file_name',
]


class AttrDict(dict):
    def __init__(self, dict_):
        super().__init__(dict_)

    def __getattr__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            return


class IgnoreRule:
    def __init__(self, conf):
        self.conf = conf
        self.split_path_rule('folder_path')

    def split_path_rule(self, rule_name):
        origin = self.conf[rule_name]
        self.conf[rule_name] = [x.split('/') for x in origin]

    def test_dir(self, path):
        for rule in self.conf.folder_name:
            if path.name == rule:
                return True

        for rule in self.conf.folder_path:
            if self.path_parts_startswith(path.parts, rule):
                return True

    def path_parts_startswith(self, parent, child):
        if len(parent) < len(child):
            return False

        for i in range(len(child)):
            if parent[i] != child[i]:
                return False
        return True

    def test_file(self, path):
        for rule in self.conf.file_name:
            if path.name == rule:
                return True

        for rule in self.conf.file_path:
            if path.as_posix() == rule:
                return True


def gen_work_dir(dir_path, ignore):
    for root, dirs, files in os.walk(dir_path):
        root_path = Path(root)
        if root != dir_path:
            if (ignore.test_dir(root_path)):
                continue
            yield root_path.as_posix()

        for file_ in files:
            file_path = root_path / file_
            if (ignore.test_file(file_path)):
                continue
            yield file_path.as_posix()


def git_check_ignore(path_list):
    args = ['git', 'check-ignore', '--stdin']
    p = Popen(args, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    input_ = '\n'.join(path_list).encode()
    output = p.communicate(input=input_)[0]
    ignored = output.decode().split('\n')
    return list(filter(None, ignored))


def get_included_items(conf):
    included_items = []
    transform = {}

    for rule in conf.include_file_path:
        if isinstance(rule, list):
            path, archive_name = rule
            included_items.append(path)
            transform[path] = archive_name
        else:
            included_items.append(rule)

    return included_items, transform


def pack(conf):
    ignore = IgnoreRule(conf)
    all_items = list(gen_work_dir('.', ignore))

    if conf.use_git_ignore:
        git_ignored = git_check_ignore(all_items)
        zip_items = set(all_items) - set(git_ignored)
    else:
        zip_items = all_items

    include_items, transform = get_included_items(conf)
    zip_items = set(zip_items) | set(include_items)
    zip_items = list(zip_items)
    zip_items.sort()

    output_path = Path(ignore.conf.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, 'w', ZIP_DEFLATED) as zf:
        for path in zip_items:
            archive_name = transform.get(path)
            zf.write(path, archive_name)


def exclude_special(conf):
    file_path = conf.file_path
    folder_path = conf.folder_path

    output_item = Path(conf.output).relative_to('.')
    if not output_item.as_posix().startswith('../'):
        file_path.append(output_item.as_posix())

    if conf.exclude_self:
        file_path.append(PACK_IGNORE_FILENAME)

    if conf.exclude_pack_script:
        cwd = os.getcwd()
        try:
            self_path = Path(__file__).relative_to(cwd)
            file_path.append(self_path.as_posix())
        except ValueError:
            pass

    if conf.use_git_ignore:
        folder_path.append('.git')
        file_path.append('.gitignore')


def read_conf():
    '''
    {
        "output": "pack.zip",
        "exclude_self": true,
        "exclude_pack_script": true,
        "use_git_ignore": true,
        "exclude_folder_path": [],
        "exclude_folder_name": [],
        "exclude_file_path": [],
        "exclude_file_name": [],
        "include_file_path": [
            "path/file",
            ["path", "transformed_path"]
        ]
    }
    '''

    try:
        with open(PACK_IGNORE_FILENAME) as f:
            ignore_data = f.read(1024 * 1024)
            return json.loads(ignore_data)
    except FileNotFoundError:
        return {}


def rename_conf_keys(conf):
    for key in EXCLUDE_FILE_KEYS:
        new_key = key[len('exclude_'):]
        conf[new_key] = conf.pop(key)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output')
    return parser.parse_args()


def main():
    conf = read_conf()
    args = get_args()
    if args.output:
        conf['output'] = args.output

    for key in [
        'exclude_self',
        'exclude_pack_script',
        'use_git_ignore'
            ]:
        if key not in conf:
            conf[key] = True

    for key in EXCLUDE_FILE_KEYS + \
            ['include_file_path']:
        if key not in conf:
            conf[key] = []

    rename_conf_keys(conf)
    conf = AttrDict(conf)
    exclude_special(conf)
    pack(conf)


if __name__ == '__main__':
    main()
