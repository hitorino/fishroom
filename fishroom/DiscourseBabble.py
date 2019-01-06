#!/usr/bin/env python3
import requests
import requests.exceptions
import tornado
import tornado.web

import time
import re

from . import xss

from .base import BaseBotInstance, EmptyBot
from .bus import MessageBus, MsgDirection
from .models import (
    Message, ChannelType, MessageType, RichText, TextStyle, Color
)
from .textformat import TextFormatter
from .helpers import get_now_date_time, get_logger
from .config import config
from .IRC import IRCHandle

logger = get_logger("DiscourseBabble")

IRC_COLOR_RGB = [
        '#ffffff', # 0
        '#000000', # 1 
        '#00007f', 
        '#009300',
        '#ff0000',
        '#7f0000',
        '#9c009c',
        '#fc7f00',
        '#ffff00',
        '#00fc00',
        '#009300',
        '#00ffff',
        '#0000fc',
        '#ff00ff',
        '#7f7f7f',
        '#d2d2d2', #15
        '#888', # 16
]

def getWebhookHandler(dbh):
    class WebhookHandler(tornado.web.RequestHandler):
        def post(self):
            json = tornado.escape.json_decode(self.request.body)
            post = json.get('post', None)
            if post:
                topic_id = post.get('id', 0)
                current_user = post.get('username', '未知用户')
                message = post.get('cooked', '未知消息')
                dbh.on_sendmessage(topic_id, current_user, message)
            else:
                topic_id = json.get('topic_id',0)
                current_user = json.get('current_user', '未知用户')
                message = json.get('message', '未知消息')
                dbh.on_sendmessage(topic_id, current_user, message)
            self.write('Got a message.')
    return WebhookHandler
                
class DiscourseBabbleHandle(BaseBotInstance):
    ChanTag = ChannelType.DiscourseBabble
    SupportMultiline = True
    #rich_message = IRCHandle.rich_message
    send_to_bus = None
    def __init__(self, base_url, username, api_key, topic_ids):
        debug=config['debug']
        self.username = username
        self.base_url = base_url
        self.api_key = api_key
        self.topic_ids = topic_ids
        application = tornado.web.Application([
            (r"/sendmessage", getWebhookHandler(self)),
        ],debug=debug, autoreload=debug)
        application.listen(config['babble']['webhook_port'],address=config['babble'].get('webhook_host', '0.0.0.0'))

    def listen(self):
        tornado.ioloop.IOLoop.instance().start()

    def on_sendmessage(self, topic_id, current_user, message):
        if current_user == self.username:
            return
        date, time = get_now_date_time()
        # images = [m.group(1) for m in re.finditer(r'!\[.*\]\(.+\)',message)]
        logger.debug(message)
        m = re.search(r'<img[\s\w"=]+?src="([^"]+)".*?>', message)
        media_url = ''
        mtype = MessageType.Text
        if m:
            logger.debug(m)
            mtype = MessageType.Photo
            media_url = m.group(1)
        if re.search(r'^http', media_url)==None:
            if media_url.startswith('/uploads/'):
                media_url = self.base_url + media_url
        logger.debug(media_url)
        msg = Message(
                ChannelType.DiscourseBabble,
                current_user, topic_id,
                xss.cooked_unescape(message),
                mtype=mtype,media_url=media_url,
                date=date,time=time
        )
        self.send_to_bus(self,msg)

    def do_send_request(self, topic_id, text):
        if topic_id not in self.topic_ids:
            return
        requests.post(self.base_url
                +'/babble/topics/'
                +'%d'%int(topic_id)
                +'/posts',
                data = {
                    'api_user':self.username,
                    'api_key':self.api_key,
                    'raw': text,
                    'topic_id': '%d'%int(topic_id)
                    })

    def send_msg(self, target, content, sender=None, first=False, raw=None, **kwargs):
        # color that fits both dark and light background
        color_avail = (2, 3, 4, 5, 6, 7, 10, 12, 13)
        color = None

        if sender:
            # color defined at http://www.mirc.com/colors.html
            # background_num = sum([ord(i) for i in sender]) % 16
            cidx = sum([ord(i) for i in sender]) % len(color_avail)
            foreground_num = color_avail[cidx]
            color = Color(foreground_num)  # + ',' + str(background_num)

        reply_quote = ""
        if 'reply_text' in kwargs:
            reply_to = kwargs['reply_to']
            reply_text = kwargs['reply_text']
            if len(reply_text) > 8:
                reply_text = reply_text[:8] + '...'
            reply_quote = "[b]{reply_to}[/b]<br/>{reply_text}".format(reply_text=reply_text.strip(), reply_to=reply_to)
        try:
            channel = raw.channel.capitalize()
            channel = xss.replace(channel, [[r'[Ii][Rr][Cc]',r'IRC'],['Babble','hitorino']])
        except AttributeError:
            channel = None
        msg = self.rich_message(content, sender=sender, color=color,
                                reply_quote=reply_quote, channel=channel)
        msg = self.formatRichText(msg)
        if raw is not None:
            if raw.mtype in (MessageType.Photo, MessageType.Sticker):
                msg += "\n![](%s)" % (raw.media_url,)
        self.do_send_request(target, msg)
        time.sleep(0.5)

    def rich_message(self, content, sender=None, color=None, reply_quote="", channel=""):
        if color and sender:
            return RichText([
                (TextStyle(color=color,bold=1), "{}".format(sender)),
                (TextStyle(color=Color(16)), " {} 用户\n".format(channel)),
                (TextStyle(color=Color(16)), "{}\n".format(reply_quote)),
                (TextStyle(), "{}".format(xss.md_escape(content))),
            ])
        else:
            tmpl = "{content}" if sender is None else "[{sender}] {content}"
            return RichText([
                (TextStyle(), tmpl.format(content=content, sender=sender))
            ])

    def formatRichText(self, rich_text: RichText):
        formated_text = ""
        for ts, text in rich_text:
            if not text:
                continue
            if ts.is_normal():
                formated_text += text
                continue
            ctrl = []
            def bold(text):
                if not ts.is_bold():
                    return text
                return "[b]{}[/b]".format(text)
            def italic(text):
                if not ts.is_italic():
                    return text
                return "[i]{}[/i]".format(text)
            def underline(text):
                if not ts.is_underline():
                    return text
                return "[u]{}[/u]".format(text)
            def fgcolor(text,color):
                return '[color={}]{}[/color]'.format(IRC_COLOR_RGB[color],text)
            def bgcolor(text,color):
                return '[bgcolor={}]{}[/bgcolor]'.format(IRC_COLOR_RGB[color],text)
            def color(text):
                if not ts.has_color():
                    return text
                if ts.color.bg:
                    return bgcolor(fgcolor(text,ts.color.fg),ts.color.bg)
                else:
                    return fgcolor(text, ts.color.fg)
            formated_text += (underline(italic(bold(color(text)))))
        return formated_text

def Babble2FishroomThread(irc_handle: DiscourseBabbleHandle, bus: MessageBus):
    if irc_handle is None or isinstance(irc_handle, EmptyBot):
        return
    def send_to_bus(self, msg):
        logger.debug(msg)
        bus.publish(msg)
    irc_handle.send_to_bus=send_to_bus
    irc_handle.listen()


def Fishroom2BabbleThread(irc_handle, bus):
    if irc_handle is None or isinstance(irc_handle, EmptyBot):
        return
    for msg in bus.message_stream():
        irc_handle.forward_msg_from_fishroom(msg)

def init():
    from .db import get_redis
    redis_client = get_redis()
    im2fish_bus = MessageBus(redis_client, MsgDirection.im2fish)
    fish2im_bus = MessageBus(redis_client, MsgDirection.fish2im)

    babble_idnumbers = [b["babble"] for _, b in config['bindings'].items() if "babble" in b]
    base_url = config['babble']['base_url']
    username = config['babble']['username']
    api_key = config['babble']['api_key']

    return (
        DiscourseBabbleHandle(base_url, username, api_key, babble_idnumbers),
        im2fish_bus, fish2im_bus,
    )


def main():
    if "babble" not in config:
        logger.error("Babble config not found in config.py! exiting...")
        return

    from .runner import run_threads
    bot, im2fish_bus, fish2im_bus = init()
    run_threads([
        (Babble2FishroomThread, (bot, im2fish_bus, ), ),
        (Fishroom2BabbleThread, (bot, fish2im_bus, ), ),
    ])

main()
# vim: ts=4 sw=4 sts=4 expandtab
