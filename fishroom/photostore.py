#!/usr/bin/env python3
import re
import json
import requests
import requests.exceptions
from base64 import b64encode
from .helpers import get_logger
import shutil,os


logger = get_logger(__name__)


class BasePhotoStore(object):

    def upload_image(self, filename, **kwargs):
        raise Exception("Not Implemented")

class LocalPhotoStore(object):
    def __init__(self, path, **kwargs):
        self.path = path

    def upload_image(self, filename=None, filedata=None, **kwargs):
        if filedata is None:
            shutil.copy2(filename, os.path.join(path, os.path.dirname(filename)))

class Imgur(BasePhotoStore):

    url = "https://api.imgur.com/3/image?_format=json"

    def __init__(self, client_id, **kwargs):
        self.client_id = client_id

    def upload_image(self, filename=None, filedata=None, **kwargs):
        if filedata is None:
            with open(filename, 'rb') as f:
                b64img = b64encode(f.read())
        else:
            b64img = b64encode(filedata)

        headers = {"Authorization": "Client-ID %s" % self.client_id}
        try:
            r = requests.post(
                self.url,
                headers=headers,
                data={
                    'image': b64img,
                    'type': 'base64',
                },
                timeout=5,
            )
        except requests.exceptions.Timeout:
            logger.error("Timeout uploading to Imgur")
            return None
        except:
            logger.exception("Unknown errror uploading to Imgur")
            return None

        try:
            ret = json.loads(r.text)
        except:
            return None
        if ret.get('status', None) != 200 or ret.get('success', False) != True:
            logger.error(
                "Error: Imgur returned error, {}".format(ret.get('data', ''))
            )
            return None

        link = ret.get('data', {}).get('link', None)
        return link if link is None else re.sub(r'^http:', 'https:', link)


class VimCN(BasePhotoStore):

    def __init__(self, url="https://img.vim-cn.com/", **kwargs):
        self.url = url

    def upload_image(self, filename=None, filedata=None, **kwargs) -> str:
        if filedata is None:
            files = {"image": open(filename, 'rb')}
        else:
            files = {"image": filedata}

        try:
            r = requests.post(self.url, files=files, timeout=5)
        except requests.exceptions.Timeout:
            logger.error("Timeout uploading to VimCN")
            return None
        except:
            logger.exception("Unknown errror uploading to VimCN")
            return None
        if not r.ok:
            return None
        return r.text.strip()


if __name__ == "__main__":
    import sys
    imgur = Imgur(sys.argv[1])
    print(imgur.upload_image(sys.argv[2]))


# vim: ts=4 sw=4 sts=4 expandtab
