#!/usr/bin/env python3
import sleekxmpp
from .bus import MessageBus, MsgDirection
from .base import BaseBotInstance, EmptyBot
from .models import Message, ChannelType, MessageType
from .helpers import get_now_date_time
from .config import config


class XMPPHandle(sleekxmpp.ClientXMPP, BaseBotInstance):
    ChanTag = ChannelType.XMPP

    def __init__(self, server, port, jid, password, rooms, nick):
        sleekxmpp.ClientXMPP.__init__(self, jid, password)

        self.rooms = rooms
        self.nick = nick

        self.add_event_handler("session_start", self.on_start)
        self.add_event_handler("groupchat_message", self.on_muc_message)

        self.register_plugin('xep_0045')  # Multi-User Chat
        self.register_plugin('xep_0199')  # XMPP Ping

        self.srvaddress = (server, port)

        # if not self.connect((server, port)):
        #     raise Exception("Unable to connect to XMPP server")

    def on_start(self, event):
        self.get_roster()
        self.send_presence()
        for room in self.rooms:
            self.plugin['xep_0045'].joinMUC(
                room, self.nick, wait=True)
            print("[xmpp] joined room %s" % room)

    def on_muc_message(self, msg):
        if msg['mucnick'] != self.nick and msg['id']:
            date, time = get_now_date_time()
            mtype = MessageType.Command \
                if self.is_cmd(msg['body']) \
                else MessageType.Text

            msg = Message(
                ChannelType.XMPP,
                msg['mucnick'], msg['from'].bare, msg['body'],
                mtype=mtype, date=date, time=time)
            self.send_to_bus(self, msg)

    def msg_tmpl(self, sender=None, reply_quote="", reply_to=""):
        return "{content}" if sender is None else \
            "[{sender}] {reply_quote}{content}"

    def send_msg(self, target, content, sender=None, first=False, **kwargs):
        tmpl = self.msg_tmpl(sender)
        reply_quote = ""
        if first and 'reply_text' in kwargs:
            reply_to = kwargs['reply_to']
            reply_text = kwargs['reply_text']
            if len(reply_text) > 5:
                reply_text = reply_text[:5] + '...'
                reply_quote = "「Re {reply_to}: {reply_text}」".format(
                    reply_text=reply_text, reply_to=reply_to)

        mbody = tmpl.format(sender=sender, content=content,
                            reply_quote=reply_quote)

        self.send_message(mto=target, mbody=mbody, mtype='groupchat')

    def send_to_bus(self, msg):
        raise Exception("Not implemented")


def XMPP2FishroomThread(xmpp_handle: XMPPHandle, bus: MessageBus):
    if xmpp_handle is None or isinstance(xmpp_handle, EmptyBot):
        return

    def send_to_bus(self, msg):
        bus.publish(msg)

    xmpp_handle.send_to_bus = send_to_bus
    xmpp_handle.connect(xmpp_handle.srvaddress, reattempt=True)
    xmpp_handle.process(block=True)


def Fishroom2XMPPThread(xmpp_handle: XMPPHandle, bus: MessageBus):
    if xmpp_handle is None or isinstance(xmpp_handle, EmptyBot):
        return
    for msg in bus.message_stream():
        xmpp_handle.forward_msg_from_fishroom(msg)


def init():
    from .db import get_redis
    redis_client = get_redis()
    im2fish_bus = MessageBus(redis_client, MsgDirection.im2fish)
    fish2im_bus = MessageBus(redis_client, MsgDirection.fish2im)

    rooms = [b["xmpp"] for _, b in config['bindings'].items() if "xmpp" in b]
    server = config['xmpp']['server']
    port = config['xmpp']['port']
    nickname = config['xmpp']['nick']
    jid = config['xmpp']['jid']
    password = config['xmpp']['password']

    return (
        XMPPHandle(server, port, jid, password, rooms, nickname),
        im2fish_bus, fish2im_bus,
    )


def main():
    if "xmpp" not in config:
        return

    from .runner import run_threads
    bot, im2fish_bus, fish2im_bus = init()
    run_threads([
        (XMPP2FishroomThread, (bot, im2fish_bus, ), ),
        (Fishroom2XMPPThread, (bot, fish2im_bus, ), ),
    ])


def test():
    rooms = [b["xmpp"] for _, b in config['bindings'].items()]
    server = config['xmpp']['server']
    port = config['xmpp']['port']
    nickname = config['xmpp']['nick']
    jid = config['xmpp']['jid']
    password = config['xmpp']['password']

    xmpp_handle = XMPPHandle(server, port, jid, password, rooms, nickname)

    def send_to_bus(self, msg):
        print(msg.dumps())
    xmpp_handle.send_to_bus = send_to_bus
    xmpp_handle.process(block=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", default=False, action="store_true")
    args = parser.parse_args()

    if args.test:
        test()
    else:
        main()

# vim: ts=4 sw=4 sts=4 expandtab
