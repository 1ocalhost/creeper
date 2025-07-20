import os
import glob
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

    def push_path(src, dst):
        assert dst[-1] != '/'
        assert os.path.isfile(src), src
        included_items.append(dst)

    for rule in conf.include_file_path:
        if isinstance(rule, list):
            path, archive_name = rule
            transform[archive_name] = path
            push_path(*rule)
        else:
            push_path(rule, rule)

    def to_unix_path(path):
        return path.replace('\\', '/')

    for rule in conf.include_glob:
        file_list = glob.glob(rule)
        for path in map(to_unix_path, file_list):
            push_path(path, path)

    return included_items, transform


def get_parent_folders_gen(path):
    assert path[0] != '/'
    assert path[-1] != '/'
    parts = path.split('/')

    for i in range(len(parts) - 1):
        yield '/'.join(parts[:i + 1])


def ensure_parent_folders(items):
    item_set = set(items)
    result = []

    for item in items:
        for path in get_parent_folders_gen(item):
            if path not in item_set:
                item_set.add(path)
                result.append((True, path))
        result.append((False, item))

    return result


def make_zip_items(conf):
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
    zip_items = ensure_parent_folders(zip_items)
    return zip_items, transform


def pack(conf):
    zip_items, transform = make_zip_items(conf)
    output_path = Path(conf.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(output_path, 'w', ZIP_DEFLATED) as zf:
        for added_dir, path in zip_items:
            if added_dir:
                zf.writestr(path + '/', '')
                continue

            real_path = transform.get(path)
            if real_path:
                zf.write(real_path, path)
            else:
                zf.write(path)


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
        ],
        "include_glob": [
            "data/*.txt"
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
    parser.add_argument('--dir', help='working directory')
    parser.add_argument('--output', help='output zip file')
    return parser.parse_args()


def handle_cli_args():
    args = get_args()

    if args.dir:
        os.chdir(args.dir)

    conf = read_conf()
    if args.output:
        conf['output'] = args.output

    return conf


def main():
    conf = handle_cli_args()

    for key in [
        'exclude_self',
        'exclude_pack_script',
        'use_git_ignore'
            ]:
        if key not in conf:
            conf[key] = True

    for key in EXCLUDE_FILE_KEYS + \
            ['include_file_path', 'include_glob']:
        if key not in conf:
            conf[key] = []

    rename_conf_keys(conf)
    conf = AttrDict(conf)
    exclude_special(conf)
    pack(conf)


if __name__ == '__main__':
    main()
