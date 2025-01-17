"""
A logger object that consolidates messages incoming from ipcluster processes.
"""
import logging

import zmq
from jupyter_client.localinterfaces import localhost
from traitlets import Instance
from traitlets import List
from traitlets import Unicode
from traitlets.config.configurable import LoggingConfigurable
from zmq.eventloop import ioloop
from zmq.eventloop import zmqstream


class LogWatcher(LoggingConfigurable):
    """A simple class that receives messages on a SUB socket, as published
    by subclasses of `zmq.log.handlers.PUBHandler`, and logs them itself.

    This can subscribe to multiple topics, but defaults to all topics.
    """

    # configurables
    topics = List(
        [''],
        config=True,
        help="The ZMQ topics to subscribe to. Default is to subscribe to all messages",
    )
    url = Unicode(config=True, help="ZMQ url on which to listen for log messages")

    def _url_default(self):
        return 'tcp://%s:20202' % localhost()

    # internals
    stream = Instance('zmq.eventloop.zmqstream.ZMQStream', allow_none=True)

    context = Instance(zmq.Context)

    def _context_default(self):
        return zmq.Context.instance()

    loop = Instance('tornado.ioloop.IOLoop')

    def _loop_default(self):
        return ioloop.IOLoop.current()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        s = self.context.socket(zmq.SUB)
        s.bind(self.url)
        self.stream = zmqstream.ZMQStream(s, self.loop)
        self.subscribe()
        self.on_trait_change(self.subscribe, 'topics')

    def start(self):
        self.stream.on_recv(self.log_message)

    def stop(self):
        self.stream.stop_on_recv()

    def subscribe(self):
        """Update our SUB socket's subscriptions."""
        self.stream.setsockopt(zmq.UNSUBSCRIBE, '')
        if '' in self.topics:
            self.log.debug("Subscribing to: everything")
            self.stream.setsockopt(zmq.SUBSCRIBE, '')
        else:
            for topic in self.topics:
                self.log.debug("Subscribing to: %r" % (topic))
                self.stream.setsockopt(zmq.SUBSCRIBE, topic)

    def _extract_level(self, topic_str):
        """Turn 'engine.0.INFO.extra' into (logging.INFO, 'engine.0.extra')"""
        topics = topic_str.split('.')
        for idx, t in enumerate(topics):
            level = getattr(logging, t, None)
            if level is not None:
                break

        if level is None:
            level = logging.INFO
        else:
            topics.pop(idx)

        return level, '.'.join(topics)

    def log_message(self, raw):
        """receive and parse a message, then log it."""
        if len(raw) != 2 or '.' not in raw[0]:
            self.log.error("Invalid log message: %s" % raw)
            return
        else:
            topic, msg = raw
            # don't newline, since log messages always newline:
            topic, level_name = topic.rsplit('.', 1)
            level, topic = self._extract_level(topic)
            if msg[-1] == '\n':
                msg = msg[:-1]
            self.log.log(level, f"[{topic}] {msg}")
