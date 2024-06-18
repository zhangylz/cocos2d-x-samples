#!/usr/bin/env python
#coding=utf-8
#
# ./download-deps.py
#
# Downloads Cocos2D-x engine from official website:
# http://www.cocos2d-x.org/filedown/cocos2d-x-xxx.zip) and extracts the zip
# file
#
# Having the dependencies outside the official cocos2d-x repo helps prevent
# bloating the repo.
#

"""****************************************************************************
Copyright (c) 2014 cocos2d-x.org
Copyright (c) 2014 Chukong Technologies Inc.

http://www.cocos2d-x.org

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
****************************************************************************"""

import os.path
import zipfile
import shutil
import sys
import traceback
import distutils
import json

from optparse import OptionParser
from time import time
from distutils.dir_util import copy_tree, remove_tree
from hashlib import md5
from libs import format_template

class UnrecognizedFormat:
    def __init__(self, prompt):
        self._prompt = prompt

    def __str__(self):
        return self._prompt


class CocosZipInstaller(object):
    def __init__(self, workpath, config_path, remote_version_key=None):
        self._workpath = workpath
        self._config_path = config_path

        data = self.load_json_file(config_path)

        self._current_version = data["version"]
        self._downloadUrl = data["downloadUrl"]
        try:
            self._move_dirs = data["move_dirs"]
        except:
            self._move_dirs = None
        self._filename = self._current_version + '.zip'
        self._url = self._downloadUrl + self._filename
        self._zip_file_size = int(data["zip_file_size"])
        
        self._final_engine_folder_name = "cocos2d-x"
        self._extracted_folder_name = os.path.join(self._workpath, self._current_version)
        self._work_folder_name = os.path.join(self._workpath, 'libs', self._final_engine_folder_name)
    def get_input_value(self, prompt):
        ret = raw_input(prompt)
        ret.rstrip(" \t")
        return ret

    def download_file(self):
        print("==> Ready to download '%s' from '%s'" % (self._filename, self._url))
        import urllib2
        try:
            u = urllib2.urlopen(self._url)
        except urllib2.HTTPError as e:
            if e.code == 404:
                print("==> Error: Could not find the file from url: '%s'" % (self._url))
            print("==> Http request failed, error code: " + str(e.code) + ", reason: " + e.read())
            sys.exit(1)

        f = open(self._filename, 'wb')
        meta = u.info()
        content_len = meta.getheaders("Content-Length")
        file_size = 0
        if content_len and len(content_len) > 0:
            file_size = int(content_len[0])
        else:
            # github server may not reponse a header information which contains `Content-Length`,
            # therefore, the size needs to be written hardcode here. While server doesn't return
            # `Content-Length`, use it instead
            print("==> WARNING: Couldn't grab the file size from remote, use 'zip_file_size' section in '%s'" % self._config_path)
            file_size = self._zip_file_size

        print("==> Start to download, please wait ...")

        file_size_dl = 0
        block_sz = 8192
        block_size_per_second = 0
        old_time = time()

        status = ""
        while True:
            buffer = u.read(block_sz)
            if not buffer:
                print("%s%s" % (" " * len(status), "\r")),
                break

            file_size_dl += len(buffer)
            block_size_per_second += len(buffer)
            f.write(buffer)
            new_time = time()
            if (new_time - old_time) > 1:
                speed = block_size_per_second / (new_time - old_time) / 1000.0
                if file_size != 0:
                    percent = file_size_dl * 100. / file_size
                    status = r"Downloaded: %6dK / Total: %dK, Percent: %3.2f%%, Speed: %6.2f KB/S " % (file_size_dl / 1000, file_size / 1000, percent, speed)
                else:
                    status = r"Downloaded: %6dK, Speed: %6.2f KB/S " % (file_size_dl / 1000, speed)
                print(status),
                sys.stdout.flush()
                print("\r"),
                block_size_per_second = 0
                old_time = new_time

        print("==> Downloading finished!")
        f.close()

    def ensure_directory(self, target):
        if not os.path.exists(target):
            os.mkdir(target)

    def unpack_zipfile(self, extract_dir):
        """Unpack zip `filename` to `extract_dir`

        Raises ``UnrecognizedFormat`` if `filename` is not a zipfile (as determined
        by ``zipfile.is_zipfile()``).
        """

        self.ensure_directory(self._extracted_folder_name)

        if not zipfile.is_zipfile(self._filename):
            raise UnrecognizedFormat("%s is not a zip file" % (self._filename))

        print("==> Extracting files, please wait ...")
        z = zipfile.ZipFile(self._filename)
        try:
            for info in z.infolist():
                name = info.filename

                # don't extract absolute paths or ones with .. in them
                if name.startswith('/') or '..' in name:
                    continue

                target = os.path.join(extract_dir, *name.split('/'))
                if not target:
                    continue

                dirname = os.path.dirname(target)
                if not os.path.exists(dirname):
                     os.makedirs(dirname)

                if name.endswith('/'):
                    # directory
                    self.ensure_directory(target)
                else:
                    # file
                    data = z.read(info.filename)
                    f = open(target, 'wb')
                    try:
                        f.write(data)
                    finally:
                        f.close()
                        del data
                unix_attributes = info.external_attr >> 16
                if unix_attributes:
                    os.chmod(target, unix_attributes)
        finally:
            z.close()
            print("==> Extraction done!")

    def ask_to_delete_downloaded_zip_file(self):
        ret = self.get_input_value("==> Would you like to save '%s'? So you don't have to download it later. [Yes/no]: " % self._filename)
        ret = ret.strip()
        if ret != 'yes' and ret != 'y' and ret != 'no' and ret != 'n':
            print("==> Saving the dependency libraries by default")
            return False
        else:
            return True if ret == 'no' or ret == 'n' else False

    def download_zip_file(self):
        if not os.path.isfile(self._filename):
            self.download_file()
        try:
            if not zipfile.is_zipfile(self._filename):
                raise UnrecognizedFormat("%s is not a zip file" % (self._filename))
        except UnrecognizedFormat as e:
            print("==> Unrecognized zip format from your local '%s' file!" % (self._filename))
            if os.path.isfile(self._filename):
                os.remove(self._filename)
            print("==> Download it from internet again, please wait...")
            self.download_zip_file()

    def need_to_update(self):
        zipfile = os.path.join(self._workpath, self._filename)
        
        data = self.load_json_file(self._config_path)
        if os.path.exists(zipfile) and os.path.exists(self._work_folder_name):
            return False
        return True

    def md5_file(self, fileName):
        mObject = md5()
        fileData = open(fileName, 'rb')    #需要使用二进制格式读取文件内容
        mObject.update(fileData.read())
        fileData.close()
        return mObject.hexdigest()

    def load_json_file(self, file_path):
        if not os.path.isfile(file_path):
            raise Exception("Could not find (%s)" % (file_path))

        with open(file_path) as data_file:
            data = json.load(data_file)
        return data

    def run(self, workpath, folder_for_extracting, remove_downloaded, force_update, download_only):
        if not force_update and not self.need_to_update():
            print("==> Not need to update!")
            return

        if os.path.exists(self._extracted_folder_name):
            shutil.rmtree(self._extracted_folder_name)

        if os.path.exists(self._work_folder_name):
            shutil.rmtree(self._work_folder_name)

        # self.download_zip_file()

        if not download_only:
            print("extracted_folder_name ", self._extracted_folder_name)
            self.unpack_zipfile(self._extracted_folder_name)
            print("==> Copying files...")
            if not os.path.exists(folder_for_extracting):
                os.mkdir(folder_for_extracting)
            distutils.dir_util.copy_tree(self._extracted_folder_name, folder_for_extracting)
            os.rename(os.path.join(folder_for_extracting, self._current_version), self._work_folder_name);
            if self._move_dirs is not None:
                for srcDir in self._move_dirs.keys():
                    distDir = os.path.join( os.path.join(workpath, self._move_dirs[srcDir]), srcDir)
                    if os.path.exists(distDir):
                        shutil.rmtree(distDir)
                    shutil.move( os.path.join(folder_for_extracting, srcDir), distDir)
            print("==> Cleaning...")
            if os.path.exists(self._extracted_folder_name):
                shutil.rmtree(self._extracted_folder_name)

            print("==> Format template!")
            formatTemplate()

            if os.path.isfile(self._filename):
                if remove_downloaded is not None:
                    if remove_downloaded == 'yes':
                        os.remove(self._filename)
                elif self.ask_to_delete_downloaded_zip_file():
                    os.remove(self._filename)
        else:
            print("==> Download (%s) finish!" % self._filename)


def _check_python_version():
    major_ver = sys.version_info[0]
    if major_ver > 2:
        print ("The python version is %d.%d. But python 2.x is required. (Version 2.7 is well tested)\n"
               "Download it here: https://www.python.org/" % (major_ver, sys.version_info[1]))
        return False

    return True

def formatTemplate():
    projectObj = format_template.ProjectFormat()
    projectObj.modify_files(format_template.ProjectFormat.KEY_MODIFY_CFG, projectObj.modify_file)
    projectObj.modify_files(format_template.ProjectFormat.KEY_MODIFY_MUL_LINE_CFG, projectObj.modify_mul_line_file)


def main():
    workpath = os.path.dirname(os.path.realpath(__file__))

    if not _check_python_version():
        exit()

    parser = OptionParser()
    parser.add_option('-r', '--remove-download',
                      action="store", type="string", dest='remove_downloaded', default=None,
                      help="Whether to remove downloaded zip file, 'yes' or 'no'")

    parser.add_option("-f", "--force-update",
                      action="store_true", dest="force_update", default=False,
                      help="Whether to force update the third party libraries")

    parser.add_option("-d", "--download-only",
                      action="store_true", dest="download_only", default=False,
                      help="Only download zip file of the third party libraries, will not extract it")

    (opts, args) = parser.parse_args()

    print("=======================================================")
    print("==> Prepare to download cocos2d-x engine!")
    external_path = os.path.join(workpath, 'libs')
    installer = CocosZipInstaller(workpath, os.path.join(workpath, 'libs', 'config.json'))
    installer.run(workpath, external_path, opts.remove_downloaded, opts.force_update, opts.download_only)

# -------------- main --------------
if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
