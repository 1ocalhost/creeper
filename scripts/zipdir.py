import os
import json
from pathlib import Path
from subprocess import Popen, PIPE
from zipfile import ZipFile, ZIP_DEFLATED

PACK_IGNORE_FILENAME = 'zipdir_ignore.json'


class DefaultValueDict(dict):
    def __init__(self, dict_, default_values, fallback):
        super().__init__(dict_)
        self.default_values = default_values
        self.fallback = fallback

    def __getattr__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            return self.default_values.get(key, self.fallback)


class IgnoreRule:
    def __init__(self, conf={}):
        if conf:
            self.conf = DefaultValueDict(conf, {
                'use_git_ignore': True,
            }, [])
            self.split_path_rule('forder_path')

    def split_path_rule(self, rule_name):
        origin = self.conf[rule_name]
        self.conf[rule_name] = [x.split('/') for x in origin]

    def test_dir(self, path):
        for rule in self.conf.forder_name:
            if path.name == rule:
                return True

        for rule in self.conf.forder_path:
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


def gen_work_dir(dir_path='.', ignore=IgnoreRule()):
    for root, dirs, files in os.walk(dir_path):
        root_path = Path(root)
        if root != '.':
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


def pack(ignore_conf):
    ignore = IgnoreRule(ignore_conf)
    all_items = list(gen_work_dir(ignore=ignore))

    if ignore.conf.use_git_ignore:
        git_ignored = git_check_ignore(all_items)
        zip_items = set(all_items) - set(git_ignored)
        zip_items = [x for x in all_items if x in zip_items]
    else:
        zip_items = all_items

    with ZipFile(ignore.conf.output, 'w', ZIP_DEFLATED) as zf:
        for path in zip_items:
            zf.write(path)


def exclude_special(ignore_conf):
    file_path = ignore_conf['file_path']
    file_path.append(ignore_conf['output'])

    if ignore_conf['exclude_self']:
        file_path.append(PACK_IGNORE_FILENAME)

    if ignore_conf['exclude_pack_script']:
        cwd = Path(os.getcwd())
        try:
            self_path = Path(__file__).relative_to(cwd)
            file_path.append(self_path.as_posix())
        except ValueError:
            pass


def main():
    buildin_pack_ignore_json = '''
    {
        "output": "pack.zip",
        "exclude_self": true,
        "exclude_pack_script": true,
        "use_git_ignore": true,
        "forder_path": [".git", ".vscode"],
        "folder_name": [],
        "file_path": [".gitignore"],
        "file_name": []
    }
    '''

    if Path(PACK_IGNORE_FILENAME).is_file():
        with open(PACK_IGNORE_FILENAME) as f:
            ignore_data = f.read(1024 * 1024)
    else:
        ignore_data = buildin_pack_ignore_json
        print('Using build-in configure.')

    ignore_conf = json.loads(ignore_data)
    exclude_special(ignore_conf)
    pack(ignore_conf)


if __name__ == '__main__':
    main()
