ZPM

# !/usr/bin/python3
# -*- coding:utf-8 _*-
"""
@version:
author:10186954
@time: 2018/09/05
@file: zpm.py
@function:
@modify:
"""
import csv
import json
import random
import string
import sys, os
import subprocess
import argparse

import re
import tempfile

import time, datetime

global user_id
user_id = None
home_path = os.path.expanduser('~')
log_file = os.path.join(home_path, '.zpm', 'logs.json')


def big_execl(cmd):
    out_temp = tempfile.SpooledTemporaryFile(max_size=100 * 1000)
    fileno = out_temp.fileno()
    obj = subprocess.Popen(cmd, shell=True, stdout=fileno, stderr=fileno, close_fds=True)
    obj.wait()
    out_temp.seek(0)
    lines = out_temp.read().decode('utf-8')
    return lines


def execl(cmd, print_res):
    res = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           close_fds=True)
    errinfo = res.stderr.read().decode('utf-8').strip()
    data = res.stdout.read().decode('utf-8').strip()
    if errinfo == '':
        if print_res:
            print(data)
        return data
    else:
        print(data)
        print(errinfo)
        print('---------')
        print('failed')
        return None


def get_id(name):
    find = re.compile(r'\d{8}')
    id = find.findall(name)
    return id[0]


def get_git_conf():
    global user_id
    if user_id is not None:
        return user_id
    git_conf_file = os.path.join(home_path, '.gitconfig')
    if not os.path.isfile(git_conf_file):
        return None
    with open(git_conf_file, 'r') as f:
        for line in f.readlines():
            if 'name' in line.strip():
                id = get_id(line.strip())
                user_id = id
                return id


def change_id(cmd):
    id = get_git_conf()
    if id is None:
        return None
    data = re.sub(r'12345678', id, cmd)
    return data


class zpm_pull(object):
    def __init__(self, pdt, tag, path, local, ci, update, name, print):
        self.pdt = pdt
        self.tag = tag
        self.path = path
        self.local = local
        self.ci = ci
        self.update = update
        self.name = name
        self.print = print
        self.cmd_path = os.getcwd()
        self.code_path = ''
        self.id = ''
        self.result = ''

    def get_path(self):
        if self.path is None:
            self.code_path = self.cmd_path
        elif os.path.isabs(self.path):
            self.code_path = self.path
        else:
            self.code_path = os.path.abspath(os.path.join(self.cmd_path, self.path))
        if not os.path.isdir(self.code_path):
            os.makedirs(self.code_path)

    def get_config(self):
        config_file = os.path.join(home_path, 'config.json')
        if not os.path.isfile(config_file):
            config_file = os.path.join(home_path, '.zpm', 'repo', 'resources', 'config.json')
            if not os.path.isfile(config_file):
                print('no config found,run "zpm config -i" first')
                return None
        with open(config_file, 'r') as f:
            load_dict = json.load(f)
        return load_dict

    def get_local_clone(self, cmd_b, git_path, path):
        return '@git clone -q ' + cmd_b + git_path + ' ' + path

    def get_remote_clone(self, cmd_b, repo, path, output=False):
        if output:
            flag = ''
        else:
            flag = '@'
        if self.ci:
            cmd1 = flag + 'git clone -q ' + cmd_b
            cmd2 = 'ssh://xxx@xxx.com.cn:29418/' + repo
            cmd_full = cmd1 + cmd2 + ' ' + path
        else:
            cmd1 = flag + "git clone -q " + cmd_b + "ssh://12345678@xxx.com.cn:29418/"
            cmd2 = '&& git config --global url."ssh://12345678@xxx.com.cn".pushInsteadOf \
                    ssh://12345678@xxx.com.cn \
                    && scp -p -P 29418 12345678@xxx.com.cn:hooks/commit-msg'
            cmd3 = '/.git/hooks/'
            cmd_full = cmd1 + repo + ' ' + path + ' ' + cmd2 + ' ' + path + cmd3
            cmd_full = change_id(cmd_full)
        return cmd_full

    def update_cache(self, cache_path, branch):
        if not self.update:
            return
        os.chdir(cache_path)
        if branch is not None:
            cmd = 'git checkout -q ' + branch
        else:
            cmd = 'git checkout -q master'
        print('update_cache')
        os.system(cmd)
        os.system('git pull -q')
        os.chdir(self.code_path)

    def download_cache(self, cmd_b, repo, path, cache_path):
        cmd = self.get_remote_clone(cmd_b, repo, path, True)
        del_cmd = 'rm -rf ' + cache_path
        cache_root_path = os.path.join(home_path, '.zpm', 'cache')
        os.chdir(cache_root_path)
        os.system(del_cmd)
        os.system(cmd)
        os.chdir(self.code_path)

    def get_git_cmd(self, repo, path=None, branch=None):
        if path is None:
            path = repo
        cmd_b = ''
        if branch is not None:
            cmd_b = ' -b ' + branch + ' '
        if self.local:
            cache_path = os.path.join(home_path, '.zpm', 'cache', path)
            git_path = os.path.join(cache_path, '.git')
            if os.path.isdir(git_path):
                self.update_cache(cache_path, branch)
            else:
                print('download_cache')
                self.download_cache(cmd_b, repo, path, cache_path)
            cmd_full = self.get_local_clone(cmd_b, git_path, path)
        else:
            cmd_full = self.get_remote_clone(cmd_b, repo, path)
        return cmd_full

    def generate_makefile(self, data_json):
        m = open("Makefile", "w")
        m.write(" # This file is generated by zpm, do not edit!\n")
        m.write(".PHONY:all\n")
        for info in (data_json[self.pdt][self.tag]):
            m.write(".PHONY:%s\n" % (info['repo']))
        m.write("\n# targets\n")
        for info in (data_json[self.pdt][self.tag]):
            m.write("all:%s\n" % (info['repo']))
        m.write("\n# dependences\n")
        for info in (data_json[self.pdt][self.tag]):
            if 'depend' in info and info['depend'] is not None:
                m.write("%s:%s\n" % (info['repo'], info['depend']))
            else:
                m.write("%s:\n" % (info['repo']))
            m.write("\t@echo $@\n")
            if 'path' in info and info['path'] is not None:
                sub_path = info['path']
            else:
                sub_path = info['repo']
            if 'branch' in info and info['branch'] is not None:
                cmd = self.get_git_cmd(info['repo'], sub_path, info['branch'])
            else:
                cmd = self.get_git_cmd(info['repo'], sub_path)
            m.write("\t%s\n" % cmd)
            if 'commit' in info and info['commit'] is not None:
                m.write("\tcd %s && git checkout %s\n" % (sub_path, info['commit']))
            m.write("\n")
        m.close()

    def generate_verinfo(self, data_json):
        os.chdir(self.code_path)
        git_cmd = 'git log -1 --pretty=format:%h'
        dict = {}
        # v = open("verinfo", "w")
        for info in (data_json[self.pdt][self.tag]):
            if 'path' in info and info['path'] is not None:
                sub_path = info['path']
            else:
                sub_path = info['repo']
            # v.write("%s\n" % sub_path)
            os.chdir(sub_path)
            commit = execl(git_cmd, False)
            # v.write("%s\n\n" % commit)
            dict[sub_path] = commit
            os.chdir(self.code_path)
        with open('verinfo', 'w') as f:
            json.dump(dict, f)
        # v.close()

    def get_name_date(self):
        nowTime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if self.name is not None:
            return self.name[0], nowTime
        else:
            ran_str = ''.join(random.sample(string.ascii_letters + string.digits, 8))
            return ran_str, nowTime

    def write_logs(self):
        name, date = self.get_name_date()
        if self.local is True:
            push = 'NO'
        else:
            push = 'YES'
        data = {
            'name': name,
            'version': self.pdt + ':' + self.tag,
            'date': date,
            'push': push,
            'path': self.code_path
        }
        print(data)
        return
        f = open(log_file, 'r')
        logs = json.load(f)
        f.close()
        logs.append(data)
        f = open(log_file, 'w')
        json.dump(logs, f)
        f.close()

    def print_head(self, data_json):
        os.chdir(self.code_path)
        git_cmd = 'git log -1 --oneline'
        for info in (data_json[self.pdt][self.tag]):
            if 'path' in info and info['path'] is not None:
                sub_path = info['path']
            else:
                sub_path = info['repo']
            print(sub_path)
            os.chdir(sub_path)
            execl(git_cmd, True)
            os.chdir(self.code_path)

    def run(self):
        data_json = self.get_config()
        if data_json is None:
            return
        self.get_path()
        print("checkout %s:%s to:%s\n" % (self.pdt, self.tag, self.code_path))
        os.chdir(self.code_path)
        self.generate_makefile(data_json)
        result = os.system('make -j16')
        # result = 0
        if result != 0:
            self.result = 'ERR'
            print('failed')
        else:
            self.result = 'OK'
            print('success')
        self.generate_verinfo(data_json)
        self.write_logs()
        if self.print:
            self.print_head(data_json)


class zpm_conf(object):
    def __init__(self, init, export, push, clean):
        self.init = init
        self.export = export
        self.push = push
        self.clean = clean

    def get_remote_cmd(self):
        cmd = 'git remote add origin ssh://12345678@xxx.com.cn:29418/xxx/ci'
        cmd = change_id(cmd)
        hook = 'scp -p -P 29418 12345678@xxx.com.cn:hooks/commit-msg .git/hooks/'
        hook = change_id(hook)
        return cmd, hook

    def conf_init(self):
        id = get_git_conf()
        if id is None:
            print('failed for git config!')
            return
        cache_path = os.path.join(home_path, '.zpm', 'cache')
        if not os.path.isdir(cache_path):
            os.makedirs(cache_path)
        repo_path = os.path.join(home_path, '.zpm', 'repo')
        if not os.path.isdir(repo_path):
            os.makedirs(repo_path)
        title = {'name': 'NAME', 'version': 'VERSION', 'date': 'DATE', 'push': 'PUSHABLE', 'path': 'PATH'}
        data = [title]
        if not os.path.isfile(log_file):
            f = open(log_file, 'w')
            json.dump(data, f)
            f.close()
        if not os.path.isfile(log_file):
            print('error')
            return
        os.chdir(repo_path)
        remote_cmd, hook = self.get_remote_cmd()
        if remote_cmd is None or hook is None:
            print('error')
            return
        os.system('git init && git config core.sparseCheckout true')
        os.system('echo /resources/config.json > .git/info/sparse-checkout')
        os.system(remote_cmd)
        os.system(hook)
        os.system('git pull -q origin ossci')
        print('finish!')

    def conf_export(self):
        conf_file = os.path.join(home_path, '.zpm', 'repo', 'resources', 'config.json')
        home_file = os.path.join(home_path, 'config.json')
        if os.path.isfile(home_file):
            print("success !")
            return
        if os.path.isfile(conf_file):
            os.symlink(conf_file, home_file)
            print("success!")
        else:
            print("no config file found,recheck it!")

    def conf_push(self):
        conf_path = os.path.join(home_path, '.zpm', 'repo', 'resources')
        os.chdir(conf_path)
        os.system('git add config.json')
        os.system('git commit -m "change config.json"')
        os.system('git push -q origin HEAD:refs/for/ossci%r=xxx@xxx.com.cn')
        print('finish!')

    def conf_clean(self):
        conf_path = os.path.join(home_path, '.zpm')
        conf_link = os.path.join(home_path, 'config.json')
        cmd1 = 'rm -rf ' + conf_path
        cmd2 = 'rm -rf ' + conf_link
        os.system(cmd1)
        os.system(cmd2)
        print('finish!')

    def run(self):
        os.chdir(home_path)
        if self.init:
            self.conf_init()
            return
        if self.export:
            self.conf_export()
            return
        if self.push:
            self.conf_push()
            return
        if self.clean:
            self.conf_clean()
            return


class zpm_search(object):
    def __init__(self, pattern):
        self.pattern = pattern

    def run(self):
        print(self.pattern)
        print('---------')
        cmd = 'ssh -p 29418 12345678@xxx.com.cn gerrit ls-projects | grep ' + '"' + self.pattern + '"'
        cmd = change_id(cmd)
        execl(cmd, True)


class zpm_query(object):
    def __init__(self, pattern):
        self.pattern = pattern

    def remove_unnecessary_words(self, data):
        remove = re.compile(r'{"type":"stats","rowCount.*')
        ret_data = re.sub(remove, '', data)
        return ret_data

    def write_to_csv(self):
        pass

    def run(self):
        print(self.pattern)
        print('---------')
        cmd = 'ssh -p 29418 12345678@xxx.com.cn gerrit query --format=JSON ' + self.pattern
        cmd = change_id(cmd)
        # print(cmd)
        data = big_execl(cmd)
        list = data.splitlines()
        file = 'gerrit.csv'
        if os.path.isfile(file):
            os.remove(file)
        f = open(file, 'a', newline='')
        fieldnames = ['project', 'branch', 'id', 'number', 'subject',
                      'owner', 'url', 'createdOn', 'lastUpdated', 'status']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for json_str in list:
            json_data = json.loads(json_str)
            if json_str == list[-1]:
                print("records : ", json_data['rowCount'])
                break
            # print(json_data['createdOn'])
            writer.writerow({'project': json_data['project'],
                             'branch': json_data['branch'],
                             'id': json_data['id'],
                             'number': json_data['number'],
                             'subject': json_data['subject'].strip(),
                             'owner': json_data['owner']['name'],
                             'url': json_data['url'],
                             'createdOn': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(json_data['createdOn'])),
                             'lastUpdated': time.strftime("%Y-%m-%d %H:%M:%S",
                                                          time.localtime(json_data['lastUpdated'])),
                             'status': json_data['status']})
        f.close()


def pull(args):
    print('---------')
    # print(args)
    if args.pt.count(":") == 0:
        pdt = args.pt
        tag = 'default'
    elif args.pt.count(":") == 1:
        pdt = args.pt.split(":")[0]
        tag = args.pt.split(":")[1]
    else:
        print("please input [PRODUCT:TAG]\n")
        return
    # print(pdt, tag)
    if args.workpath is not None:
        aa = zpm_pull(pdt, tag, args.workpath[0], args.l, args.c, args.u, args.name, args.p)
    else:
        aa = zpm_pull(pdt, tag, None, args.l, args.c, args.u, args.name, args.p)
    aa.run()


def config(args):
    # print(args)
    conf = zpm_conf(args.init, args.export, args.push, args.clean)
    conf.run()


def ps(args):
    # print(args)
    f = open(log_file, 'r')
    logs = json.load(f)
    for log in logs:
        print("{0:8}\t{1:10}\t{2:20}\t{3:8}\t{4}".format(log['name'], log['version'], log['date'], log['push'],log['path']))
    f.close()


def rm(args):
    f = open(log_file, 'r')
    logs = json.load(f)
    f.close()
    for log in logs:
        if args.name == log['name']:
            print(args.name)
            path = log['path']
            cmd = 'rm -rf ' + path
            if os.path.isdir(path):
                os.system(cmd)
            logs.remove(log)
    f = open(log_file, 'w')
    json.dump(logs, f)
    f.close()
    print('finish!')


def search(args):
    ss = zpm_search(args.pattern)
    ss.run()


def query(args):
    qq = zpm_query(args.pattern)
    qq.run()


def main():
    if len(sys.argv) < 2:
        print("Run zpm -h for more information.")
        return

    parse = argparse.ArgumentParser(prog='python3 zpm', usage='%(prog)s',
                                    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                    description="zxcsp package manager, version : 0.2",
                                    epilog="Run '%(prog)s COMMAND --help' for more information on a command.")
    parse.add_argument('--version', action='version', version='%(prog)s 0.1')

    subparsers = parse.add_subparsers(title='COMMANDS')

    parser_pull = subparsers.add_parser('pull', help='download code version')
    parser_pull.add_argument('pt', metavar='PRODUCT:TAG',
                             help='specify the tag and product to download,see in config.json')
    parser_pull.add_argument('-n', '--name', nargs=1, help='Assign a name to the code version')
    parser_pull.add_argument('-w', '--workpath', nargs=1, help='Assign the directory to store the code')
    parser_pull.add_argument('-l', action='store_true', help='Using local cache repertories instead of gerrit')
    parser_pull.add_argument('-u', action='store_true', help='Update local cache repertories before download')
    parser_pull.add_argument('-c', action='store_true', help='Running for ci,a special tag')
    parser_pull.add_argument('-p', action='store_true', help='Print head commit info')
    parser_pull.set_defaults(func=pull)

    parser_config = subparsers.add_parser('config', help='handle with config file')
    conf_group = parser_config.add_mutually_exclusive_group()
    conf_group.add_argument('-i', '--init', action='store_true', help='Initialization once before run')
    conf_group.add_argument('-e', '--export', action='store_true', help='Export config.json to home directory')
    conf_group.add_argument('-p', '--push', action='store_true', help='Push the change of config')
    conf_group.add_argument('-c', '--clean', action='store_true', help='Remove all config file')
    parser_config.set_defaults(func=config)

    parser_ps = subparsers.add_parser('ps', help='list downloaded code version')
    parser_ps.set_defaults(func=ps)

    parser_rm = subparsers.add_parser('rm', help='remove code version')
    # rm_group = parser_rm.add_mutually_exclusive_group()
    # rm_group.add_argument('-n', '--name', nargs=1, help='Remove the code version with a name')
    # rm_group.add_argument('-a', '--all', action='store_true', help='Remove all code version')
    parser_rm.add_argument('name', metavar='NAME', help='Remove the code version with a name')
    parser_rm.set_defaults(func=rm)

    parser_search = subparsers.add_parser('search', help='search for repertories')
    parser_search.add_argument('pattern', metavar='PATTERN', help='Assign the string of repertories to search')
    parser_search.set_defaults(func=search)

    parser_query = subparsers.add_parser('query', help='query changes of gerrit repertories')
    parser_query.add_argument('pattern', metavar='PATTERN', help='Assign the string of changes to query')
    parser_query.set_defaults(func=query)

    args = parse.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
