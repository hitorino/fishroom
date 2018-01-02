#!/usr/bin/env python3
import ssl
import time
import irc
import irc.client
import random
from .base import BaseBotInstance, EmptyBot
from .bus import MessageBus, MsgDirection
from .models import (
    Message, ChannelType, MessageType, RichText, TextStyle, Color
)
from .textformat import TextFormatter, IRCCtrl
from .helpers import get_now_date_time, get_logger
from .config import config


logger = get_logger("IRC")


class IRCHandle(BaseBotInstance):
    """\
    Handle IRC connection
    """

    ChanTag = ChannelType.IRC

    def __init__(self, server, port, usessl, nickname, channels, blacklist=[], password=None):
        irc.client.ServerConnection.buffer_class.errors = 'replace'

        self.nickname = nickname
        self.channels = channels
        self.blacklist = set(blacklist)

        self.reactor = irc.client.Reactor()
        self.irc_conn = self.reactor.server()

        logger.info("connecting to {}:{}".format(server, port))
        if usessl:
            logger.debug("using ssl to connect...")
            ssl_factory = irc.connection.Factory(wrapper=ssl.wrap_socket)
            self.irc_conn.connect(
                server, port, nickname, password=password, connect_factory=ssl_factory)
        else:
            self.irc_conn.connect(server, port, nickname, password=password)
        self.irc_conn.last_pong = time.time()
        self.reactor.scheduler.execute_every(60, self.keep_alive_ping)

        for msg in ("welcome", "join", "privmsg", "pubmsg",
                    "action", "pong", "nicknameinuse"):
            self.irc_conn.add_global_handler(msg, getattr(self, "on_"+msg))

    def __del__(self):
        self.irc_conn.disconnect("I'll be back")

    def keep_alive_ping(self):
        try:
            if time.time() - self.irc_conn.last_pong > 360:
                raise irc.client.ServerNotConnectedError('ping timeout!')
                self.irc_conn.last_pong = time.time()
            self.irc_conn.ping(self.irc_conn.get_server_name())
        except irc.client.ServerNotConnectedError:
            logger.info('Reconnecting...')
            self.irc_conn.reconnect()
            self.irc_conn.last_pong = time.time()

    def on_pong(self, conn, event):
        conn.last_pong = time.time()

    def on_welcome(self, conn, event):
        for c in self.channels:
            if irc.client.is_channel(c):
                conn.join(c)

    def on_join(self, conn, event):
        logger.info(event.source + ' ' + event.target)

    def on_privmsg(self, conn, event):
        irc_nick = event.source[:event.source.index('!')]
        if irc_nick in self.blacklist:
            return

        rich_text = TextFormatter.parseIRC(event.arguments[0])
        content = rich_text.toPlain()
        # if only normal text is available
        if len(rich_text) == 1 and rich_text[0][0].is_normal():
            rich_text = None

        date, time = get_now_date_time()
        mtype = MessageType.Command \
            if self.is_cmd(content) \
            else MessageType.Text

        msg = Message(
            ChannelType.IRC, irc_nick, event.target, content,
            mtype=mtype, date=date, time=time, rich_text=rich_text
        )
        self.send_to_bus(self, msg)

    def on_pubmsg(self, conn, event):
        return self.on_privmsg(conn, event)

    def on_action(self, conn, event):
        irc_nick = event.source[:event.source.index('!')]
        if irc_nick in self.blacklist:
            return
        content = random.choice(('🐠', '🐟', '🐡', '🐬', '🐳', '🐋', '🦈', '🐙')) + \
            " {} {}".format(irc_nick, event.arguments[0])
        date, time = get_now_date_time()
        mtype = MessageType.Event
        msg = Message(
            ChannelType.IRC, irc_nick, event.target, content,
            mtype=mtype, date=date, time=time
        )
        self.send_to_bus(self, msg)

    def on_nicknameinuse(self, conn, event):
        conn.nick(conn.get_nickname() + "_")

    def rich_message(self, content, sender=None, color=None, reply_quote=""):
        if color and sender:
            return RichText([
                (TextStyle(color=color), "[{}] ".format(sender)),
                (TextStyle(color=Color(15)), "{}".format(reply_quote)),
                (TextStyle(), "{}".format(content)),
            ])
        else:
            tmpl = "{content}" if sender is None else "[{sender}] {content}"
            return RichText([
                (TextStyle(), tmpl.format(content=content, sender=sender))
            ])

    def send_msg(self, target, content, sender=None, first=False, **kwargs):
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
        if first and 'reply_text' in kwargs:
            reply_to = kwargs['reply_to']
            reply_text = kwargs['reply_text']
            if len(reply_text) > 8:
                reply_text = reply_text[:8] + '...'
            reply_quote = "「Re {reply_to}: {reply_text}」".format(
                reply_text=reply_text, reply_to=reply_to)

        msg = self.rich_message(content, sender=sender, color=color,
                                reply_quote=reply_quote)
        msg = self.formatRichText(msg)
        try:
            self.irc_conn.privmsg(target, msg)
        except irc.client.ServerNotConnectedError:
            logger.warning("Server not connected")
            self.irc_conn.reconnect()
        except irc.client.InvalidCharacters:
            logger.warning("Invalid character in msg: %s", repr(msg))
        time.sleep(0.5)

    def formatRichText(self, rich_text: RichText):
        formated_text = ""
        for ts, text in rich_text:
            if not text:
                continue
            if ts.is_normal():
                formated_text += text
                continue
            ctrl = []
            if ts.is_bold():
                ctrl.append(IRCCtrl.BOLD)
            if ts.is_italic():
                ctrl.append(IRCCtrl.ITALIC)
            if ts.is_underline():
                ctrl.append(IRCCtrl.UNDERLINE)
            if ts.has_color():
                ctrl.append(IRCCtrl.COLOR)
                if ts.color.bg:
                    ctrl.append("{},{}".format(ts.color.fg, ts.color.bg))
                else:
                    ctrl.append("{}".format(ts.color.fg))
            formated_text += "".join(ctrl) + text + IRCCtrl.RESET
        return formated_text

    def send_to_bus(self, msg):
        raise Exception("Not implemented")


def IRC2FishroomThread(irc_handle: IRCHandle, bus: MessageBus):
    if irc_handle is None or isinstance(irc_handle, EmptyBot):
        return

    def send_to_bus(self, msg):
        bus.publish(msg)

    irc_handle.send_to_bus = send_to_bus
    irc_handle.reactor.process_forever(60)


def Fishroom2IRCThread(irc_handle: IRCHandle, bus: MessageBus):
    if irc_handle is None or isinstance(irc_handle, EmptyBot):
        return
    for msg in bus.message_stream():
        irc_handle.forward_msg_from_fishroom(msg)


def init():
    from .db import get_redis
    redis_client = get_redis()
    im2fish_bus = MessageBus(redis_client, MsgDirection.im2fish)
    fish2im_bus = MessageBus(redis_client, MsgDirection.fish2im)

    irc_channels = [b["irc"] for _, b in config['bindings'].items() if "irc" in b]
    server = config['irc']['server']
    port = config['irc']['port']
    nickname = config['irc']['nick']
    usessl = config['irc']['ssl']
    blacklist = config['irc']['blacklist']
    password = config['irc']['password']

    return (
        IRCHandle(server, port, usessl, nickname, irc_channels, blacklist, password),
        im2fish_bus, fish2im_bus,
    )


def main():
    if "irc" not in config:
        logger.error("IRC config not found in config.py! exiting...")
        return

    from .runner import run_threads
    bot, im2fish_bus, fish2im_bus = init()
    run_threads([
        (IRC2FishroomThread, (bot, im2fish_bus, ), ),
        (Fishroom2IRCThread, (bot, fish2im_bus, ), ),
    ])


def test():
    irc_channels = [b["irc"] for _, b in config['bindings'].items()]
    server = config['irc']['server']
    port = config['irc']['port']
    nickname = config['irc']['nick']
    usessl = config['irc']['ssl']

    irc_handle = IRCHandle(server, port, usessl, nickname, irc_channels)

    def send_to_bus(self, msg):
        print(msg.dumps())
    irc_handle.send_to_bus = send_to_bus
    irc_handle.reactor.process_forever(60)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", default=False, action="store_true")
    args = parser.parse_args()

    if args.test:
        test()
    else:
        main()

# vim: ts=4 sw=4 sts=4 expandtab
