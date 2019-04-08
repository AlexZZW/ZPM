#!/usr/bin/env python
# -*- coding:utf-8 _*-
"""
@version:
author:10186954
@time: 2018/09/05
@file: zpm.py
@function: zpm包管理器，代码下载
@modify:
"""
import csv
import json
import logging
import random
import string
import sys
import os
import subprocess
import argparse
import re
import tempfile
import time
import datetime

logging.basicConfig(level=logging.INFO)

CUR_DIR = os.getcwd()
HOME_DIR = os.path.expanduser('~')
RANDOM_NAME = ''.join(random.sample(string.ascii_letters + string.digits, 8))
ZPM_ROOT_DIR = os.path.join(HOME_DIR, '.zpm')
CONF_FILE_NAME = 'config.json'
CONF_FILE_1ST = os.path.join(CUR_DIR, CONF_FILE_NAME)
CONF_FILE_2ND = os.path.join(HOME_DIR, CONF_FILE_NAME)
CONF_FILE_3RD = os.path.join(ZPM_ROOT_DIR, 'repo', 'resources', CONF_FILE_NAME)
LOCAL_CACHE_DIR = os.path.join(ZPM_ROOT_DIR, 'cache')
LOCAL_REPO_DIR = os.path.join(ZPM_ROOT_DIR, 'repo')
LOCAL_LOG_FILE = os.path.join(ZPM_ROOT_DIR, 'logs.json')
GIT_CONF_FILE = os.path.join(HOME_DIR, '.gitconfig')
COMPANY = 'xxx'
USER_ID = None


def big_execl(cmd):
    out_temp = tempfile.SpooledTemporaryFile(max_size=100 * 1000)
    file_no = out_temp.fileno()
    obj = subprocess.Popen(cmd, shell=True, stdout=file_no, stderr=file_no, close_fds=True)
    obj.wait()
    out_temp.seek(0)
    lines = out_temp.read().decode('utf-8')
    return lines


def execl(cmd, print_res):
    res = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           close_fds=True)
    err_info = res.stderr.read().decode('utf-8').strip()
    data = res.stdout.read().decode('utf-8').strip()
    if err_info:
        logging.error(err_info)
        return None
    if print_res:
        logging.info(data)
    return data


def get_git_conf():
    pattern = re.compile(r'\d{8}')
    with open(GIT_CONF_FILE, 'r') as f:
        for line in f.readlines():
            if 'name' in line.strip():
                ids = pattern.findall(line.strip())
                logging.debug(f'get git config id:{ids}')
                global USER_ID
                USER_ID = ids[0]
                return ids[0]
    assert False, 'Git is not configured.See git config --list for more infomation.'


def change_id(cmd):
    uid = USER_ID if USER_ID else get_git_conf()
    data = re.sub(r'12345678', uid, cmd)
    return data


class ZpmPull(object):
    def __init__(self, pdt, tag, path, local, ci, update, name, info):
        self.pdt = pdt
        self.tag = tag
        self.path = path if os.path.isabs(path) else os.path.abspath(os.path.join(CUR_DIR, path))
        self.local = local
        self.ci = ci
        self.update = update
        self.name = name
        self.info = info
        self.log_to_file = False

    @staticmethod
    def get_config():
        if os.path.isfile(CONF_FILE_1ST):
            conf_file = CONF_FILE_1ST
        elif os.path.isfile(CONF_FILE_2ND):
            conf_file = CONF_FILE_2ND
        elif os.path.isfile(CONF_FILE_3RD):
            conf_file = CONF_FILE_3RD
        else:
            conf_file = None
        assert conf_file is not None, 'No config file found,run "zpm config -i" first'
        logging.warning(f'load config from {conf_file}')
        with open(conf_file, 'r') as f:
            conf_data = json.load(f)
        return conf_data

    def get_remote_clone(self, cmd_b, repo, path, output):
        flag = '' if output else '@'
        domain_public = f'jenkins_fnnj@gerritro.{COMPANY}.com.cn'
        domain_private = f'12345678@gerritro.{COMPANY}.com.cn'
        port = '29418'
        if self.ci:
            return f'{flag}git clone -q {cmd_b} ssh://{domain_public}:{port}/{repo} {path}'
        else:
            hook_cmd = f'&& git config --global url."ssh://{domain_private}".pushInsteadOf \
                    ssh://{domain_private} && scp -p -P {port} {domain_private}:hooks/commit-msg'
            cmd_full = f'{flag}git clone -q {cmd_b} ssh://{domain_private}:{port}/{repo} {path} \
                        {hook_cmd} {path}/.git/hooks/'
            return change_id(cmd_full)

    def update_cache(self, cache_path, branch):
        if self.update:
            os.chdir(cache_path)
            if branch is not None:
                cmd = 'git checkout -q ' + branch
            else:
                cmd = 'git checkout -q master'
            logging.warning(f'update_cache in {cache_path} branch:{branch}')
            os.system(cmd)
            os.system('git pull -q')
            os.chdir(self.path)

    def download_cache(self, cmd_b, repo, path, cache_path):
        logging.warning(f'download_cache for {repo}')
        cmd = self.get_remote_clone(cmd_b, repo, path, True)
        del_cmd = 'rm -rf ' + cache_path
        os.chdir(LOCAL_CACHE_DIR)
        os.system(del_cmd)
        os.system(cmd)
        os.chdir(self.path)

    def get_git_cmd(self, repo, path, branch=None):
        cmd_b = f' -b {branch} ' if branch is not None else ''
        if self.local:  # 从本地缓存git目录clone,加速下载
            cache_path = os.path.join(LOCAL_CACHE_DIR, path)
            git_path = os.path.join(cache_path, '.git')
            if os.path.isdir(git_path):  # local git缓存库已经存在
                self.update_cache(cache_path, branch)
            else:
                self.download_cache(cmd_b, repo, path, cache_path)
            cmd_full = f'@git clone -q {cmd_b} {git_path} {path}'
        else:
            cmd_full = self.get_remote_clone(cmd_b, repo, path, False)
        return cmd_full

    def gen_makefile(self, repo_infos):
        m = open("Makefile", "w")
        m.write(" # This file is generated by zpm, do not edit!\n")
        m.write(".PHONY:all\n")
        for info in repo_infos:
            m.write(".PHONY:%s\n" % (info['repo']))
        m.write("\n# targets\n")
        for info in repo_infos:
            m.write("all:%s\n" % (info['repo']))
        m.write("\n# dependences\n")
        for info in repo_infos:
            if 'depend' in info and info['depend'] is not None:
                m.write("%s:%s\n" % (info['repo'], info['depend']))
            else:
                m.write("%s:\n" % (info['repo']))
            m.write("\t@echo $@\n")
            sub_path = info['path'] if 'path' in info and info['path'] is not None else info['repo']
            if 'branch' in info and info['branch'] is not None:
                cmd = self.get_git_cmd(info['repo'], sub_path, info['branch'])
            else:
                cmd = self.get_git_cmd(info['repo'], sub_path)
            m.write("\t%s\n" % cmd)
            if 'commit' in info and info['commit'] is not None:
                m.write("\tcd %s && git checkout %s\n" % (sub_path, info['commit']))
            m.write("\n")
        m.close()

    def gen_verinfo(self, repo_infos):
        git_cmd = 'git log -1 --pretty=format:%h'
        commit_infos = {}
        for info in repo_infos:
            sub_path = info['path'] if 'path' in info and info['path'] is not None else info['repo']
            os.chdir(sub_path)
            commit = execl(git_cmd, False)
            commit_infos[sub_path] = commit
            os.chdir(self.path)
        with open('verinfo', 'w') as f:
            json.dump(commit_infos, f)

    def write_logs(self):
        push = 'NO' if self.local is True else 'YES'
        data = {
            'name': self.name,
            'version': self.pdt + ':' + self.tag,
            'date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'push': push,
            'path': self.path
        }
        logging.info(data)
        if not self.log_to_file:
            return
        f = open(LOCAL_LOG_FILE, 'r')
        logs = json.load(f)
        f.close()
        logs.append(data)
        with open(LOCAL_LOG_FILE, 'w') as f:
            json.dump(logs, f)

    def print_head(self, repo_infos):
        if not self.info:
            return
        os.chdir(self.path)
        git_cmd = 'git log -1 --oneline'
        for info in repo_infos:
            sub_path = info['path'] if 'path' in info and info['path'] is not None else info['repo']
            os.chdir(sub_path)
            execl(git_cmd, True)
            os.chdir(self.path)

    def run(self):
        data_json = self.get_config()
        if not os.path.isdir(self.path):
            os.makedirs(self.path)
        os.chdir(self.path)
        self.gen_makefile(data_json[self.pdt][self.tag])
        result = os.system('make -j16')
        if result != 0:
            print('failed')
            return
        logging.info('make success')
        self.gen_verinfo(data_json[self.pdt][self.tag])
        self.write_logs()
        self.print_head(data_json[self.pdt][self.tag])


class ZpmConfigure(object):
    def __init__(self, init, export, push, clean):
        self.init = init
        self.export = export
        self.push = push
        self.clean = clean

    @staticmethod
    def get_remote_cmd():
        domain_private = f'12345678@gerritro.{COMPANY}.com.cn'
        port = '29418'
        cmd = f'git remote add origin ssh://{domain_private}:{port}/zxcsp/ci'
        cmd = change_id(cmd)
        hook = f'scp -p -P 29418 {domain_private}:hooks/commit-msg .git/hooks/'
        hook = change_id(hook)
        return cmd, hook

    def conf_init(self):
        get_git_conf()
        if not os.path.isdir(LOCAL_CACHE_DIR):
            os.makedirs(LOCAL_CACHE_DIR)
        if not os.path.isdir(LOCAL_REPO_DIR):
            os.makedirs(LOCAL_REPO_DIR)
        title = {'name': 'NAME', 'version': 'VERSION', 'date': 'DATE', 'push': 'PUSHABLE', 'path': 'PATH'}
        data = [title]
        if not os.path.isfile(LOCAL_LOG_FILE):
            with open(LOCAL_LOG_FILE, 'w') as f:
                json.dump(data, f)
        os.chdir(LOCAL_REPO_DIR)
        remote_cmd, hook = self.get_remote_cmd()
        os.system('git init && git config core.sparseCheckout true')  # 开启稀疏检出
        os.system('echo /resources/config.json > .git/info/sparse-checkout')  # 设置只检出的文件
        os.system(remote_cmd)
        os.system(hook)
        os.system('git pull -q origin ossci')
        logging.info('finish!')

    @staticmethod
    def conf_export():
        if os.path.isfile(CONF_FILE_2ND):
            logging.info("exist success !")
            return
        if os.path.isfile(CONF_FILE_3RD):
            os.symlink(CONF_FILE_3RD, CONF_FILE_2ND)
            logging.warning("link success!")
        else:
            logging.error("no config file found,recheck it!")

    @staticmethod
    def conf_push():
        conf_path = os.path.join(LOCAL_REPO_DIR, 'resources')
        os.chdir(conf_path)
        os.system('git add config.json')
        os.system('git commit -m "change config.json"')
        os.system('git push -q origin HEAD:refs/for/ossci')
        # os.system('git push -q origin HEAD:refs/for/ossci%r=xxx@xxx.com.cn')  add reviewer
        logging.info('finish!')

    @staticmethod
    def conf_clean():
        os.system(f'rm -rf {ZPM_ROOT_DIR}')
        os.system(f'rm -rf {CONF_FILE_2ND}')
        logging.info('finish!')

    def run(self):
        os.chdir(HOME_DIR)
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


class ZpmSearch(object):
    def __init__(self, pattern):
        self.pattern = pattern

    def run(self):
        domain_private = f'12345678@gerrit.{COMPANY}.com.cn'
        port = '29418'
        cmd = f'ssh -p {port} {domain_private} gerrit ls-projects | grep "{self.pattern}"'
        cmd = change_id(cmd)
        logging.debug(cmd)
        execl(cmd, True)


class ZpmQuery(object):
    def __init__(self, pattern):
        self.pattern = pattern

    def run(self):
        domain_private = f'12345678@gerrit.{COMPANY}.com.cn'
        port = '29418'
        cmd = f'ssh -p {port} {domain_private} gerrit query --format=JSON {self.pattern}'
        cmd = change_id(cmd)
        logging.debug(cmd)
        data = big_execl(cmd)
        gerrit_info_list = data.splitlines()
        file = 'gerrit.csv'
        if os.path.isfile(file):
            os.remove(file)
        with open(file, 'a', newline='') as f:
            fieldnames = ['project', 'branch', 'id', 'number', 'subject',
                          'owner', 'url', 'createdOn', 'lastUpdated', 'status']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for json_str in gerrit_info_list:
                json_data = json.loads(json_str)
                if json_str == gerrit_info_list[-1]:
                    logging.warning("records : ", json_data['rowCount'])
                    break
                writer.writerow({'project': json_data['project'],
                                 'branch': json_data['branch'],
                                 'id': json_data['id'],
                                 'number': json_data['number'],
                                 'subject': json_data['subject'].strip(),
                                 'owner': json_data['owner']['name'],
                                 'url': json_data['url'],
                                 'createdOn': time.strftime("%Y-%m-%d %H:%M:%S",
                                                            time.localtime(json_data['createdOn'])),
                                 'lastUpdated': time.strftime("%Y-%m-%d %H:%M:%S",
                                                              time.localtime(json_data['lastUpdated'])),
                                 'status': json_data['status']})


def pull(args):
    logging.debug(args)
    logging.info(f'will checkout {args.pdt}:{args.tag} to {args.work}')
    aa = ZpmPull(args.pdt, args.tag, args.work, args.local, args.ci, args.update, args.name, args.info)
    aa.run()


def config(args):
    logging.debug(args)
    conf = ZpmConfigure(args.init, args.export, args.push, args.clean)
    conf.run()


def ps(args):
    logging.debug(args)
    with open(LOCAL_LOG_FILE, 'r') as f:
        logs = json.load(f)
    for log in logs:
        print("{0:8}\t{1:10}\t{2:20}\t{3:8}\t{4}".format(log['name'],
                                                         log['version'], log['date'], log['push'], log['path']))


def rm(args):
    logging.debug(args)
    with open(LOCAL_LOG_FILE, 'r') as f:
        logs = json.load(f)
    for log in logs:
        if args.name == log['name']:
            path = log['path']
            if os.path.isdir(path):
                logging.warning(f'remove {args.name} in {path}')
                os.system(f'rm -rf {path}')
            logs.remove(log)
    with open(LOCAL_LOG_FILE, 'w') as f:
        json.dump(logs, f)


def search(args):
    logging.debug(args)
    ss = ZpmSearch(args.pattern)
    ss.run()


def query(args):
    logging.debug(args)
    qq = ZpmQuery(args.pattern)
    qq.run()


class PullAction(argparse.Action):
    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        if nargs:
            raise ValueError("nargs not allowed")
        super(PullAction, self).__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        logging.debug('%r %r' % (namespace, values))
        colon_cnt = values.count(":")
        assert colon_cnt < 2, "please input [PRODUCT:TAG]\n"
        _pdt = values.split(":")[0] if colon_cnt == 1 else values
        _tag = values.split(":")[1] if colon_cnt == 1 else 'default'
        logging.debug('%r %r' % (_pdt, _tag))
        setattr(namespace, 'pdt', _pdt)
        setattr(namespace, 'tag', _tag)


def main():
    assert len(sys.argv) >= 2, "Run zpm -h for more information."
    assert os.path.isfile(GIT_CONF_FILE), f'please make sure {GIT_CONF_FILE} is exist,which is needed.'
    parse = argparse.ArgumentParser(prog='python3 zpm', usage='%(prog)s',
                                    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                    description="zxcsp package manager, version : 0.2",
                                    epilog="Run '%(prog)s COMMAND --help' for more information on a command.")
    parse.add_argument('--version', action='version', version='%(prog)s 0.1')

    subparsers = parse.add_subparsers(title='COMMANDS')

    parser_pull = subparsers.add_parser('pull', help='download code version')
    parser_pull.add_argument('pdt_tag', metavar='PRODUCT:TAG', action=PullAction,
                             help='specify the tag and product to download,see in config.json')
    parser_pull.add_argument('-n', '--name', nargs='?', const=RANDOM_NAME, default=RANDOM_NAME,
                             help='Assign a name to the code version')
    parser_pull.add_argument('-w', '--work', nargs='?', const=CUR_DIR, default=CUR_DIR,
                             help='Assign the directory to store the code')
    parser_pull.add_argument('-l', action='store_true', dest='local',
                             help='Using local cache repertories instead of gerrit')
    parser_pull.add_argument('-u', action='store_true', dest='update',
                             help='Update local cache repertories before download')
    parser_pull.add_argument('-c', action='store_true', dest='ci', help='Running for ci,a special tag')
    parser_pull.add_argument('-p', action='store_true', dest='info', help='Print head commit info')
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
