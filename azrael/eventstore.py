# Copyright 2016, Oliver Nagy <olitheolix@gmail.com>
#
# This file is part of Azrael (https://github.com/olitheolix/azrael)
#
# Azrael is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# Azrael is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Azrael. If not, see <http://www.gnu.org/licenses/>.

"""
Provide a uniform API to publish events and subscribes to topics.
"""

import os
import time
import pika
import logging
import threading

import azrael.config as config
from azrael.aztypes import typecheck, RetVal

from IPython import embed as ipshell

# Create module logger.
logit = logging.getLogger('azrael.' + __name__)


class EventStore(threading.Thread):
    """
    Provide functionality to publish and receive messages.

    This class is a thin wrapper around the Pika bindings for RabbitMQ. It
    is implemented as a thread to queue up messages in the background. Use
    ``getMessages`` to fetch those messages and remove them from the queue.

    The ``topics`` parameter specifies the topics to which this instance will
    subscribe. However, this only affects which message can be received. It
    does not affect the ``publish`` method at all.

    Args:
        topics (list[str]): the topics to subscribe.
    """
    @typecheck
    def __init__(self, topics: (tuple, list)):
        super().__init__(daemon=True)

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Store the topics we want to subscribe to.
        self.topics = topics

        # Buffer for received messages is initially empty.
        self.messages = []

        # We will periodically check this flag and terminate the thread once it
        # changes its value to True.
        self._terminate = False

        # Specify polling timeout. Smaller values make the class more
        # responsive in the event of a shutdown. However, smaller values also
        # means invoking the GIL more frequently which slows down the main
        # thread.
        self._timeout = 0.2

        # We do not connect to RabbitMQ in the ctor (see `connect` method).
        self.rmq = None

    def connect(self):
        """Connect to the Broker.

        There is usually no need to call this method explicitly.

        Note: this method is a wrapper. The actual connection happens in
        :meth:`~setupRabbitMQ`.

        Returns:
            Success (RetVal): True if successful, False if Pika raised an error.
        """

        # Do nothing if we still have connection handles (use the `disconnect`
        # method to close the connection first).
        if self.rmq is not None:
            return RetVal(True, None, None)

        # Connect to RabbitMQ and intercept any Pika exceptions.
        try:
            ret = self.setupRabbitMQ()
            self.logit.info('Connected to RabbitMQ')
        except (pika.exceptions.ConnectionClosed,
                pika.exceptions.ChannelClosed,
                pika.exceptions.ChannelError):
            self.logit.warning('Could not connected to RabbitMQ')
            ret = RetVal(False, 'Pika error', None)

        # Return any errors verbatim.
        if not ret.ok:
            return ret

        # Connection to RabbitMQ was successful - store the connection
        # parameters in 'rmq'.
        self.rmq = ret.data
        return RetVal(True, None, None)

    def disconnect(self):
        """Disconnect from the broker.

        This method does nothing if there is no connection.

        Returns:
            Success (RetVal): True if successful, False if Pika raised an error.
        """
        # Return immediately if we have no connection handles.
        if self.rmq is None:
            return RetVal(True, None, None)

        # Close first the channel and then the connection. Ignore any errors.
        for name in ['chan', 'conn']:
            try:
                self.rmq[name].close()
                self.logit.info('Disconnected from RabbitMQ')
            except (pika.exceptions.ChannelClosed,
                    pika.exceptions.ChannelError,
                    pika.exceptions.ConnectionClosed,
                    KeyError):
                pass

        # Remove the handles.
        self.rmq = None
        return RetVal(True, None, None)

    def setupRabbitMQ(self):
        """Establish the connection with RabbitMQ.

        Raises:
            All possible Pika errors.

        Returns:
            Success (RetVal): Always True.
        """
        # Connect to the specified exchange of RabbitMQ.
        exchange_name = 'azevents'
        conn_param = pika.ConnectionParameters(
            host=config.azService['rabbitmq'].ip,
            port=config.azService['rabbitmq'].port,
        )
        conn = pika.BlockingConnection(conn_param)

        # Create and configure the channel. All deliveries must be confirmed.
        chan = conn.channel()
        chan.confirm_delivery()
        chan.basic_qos(prefetch_size=0, prefetch_count=0, all_channels=False)

        # Create a Topic exchange.
        chan.exchange_declare(exchange='azevents', type='topic')
        queue_name = chan.queue_declare(exclusive=True).method.queue

        # Setup the callbacks.
        for topic in self.topics:
            chan.queue_bind(
                exchange=exchange_name,
                queue=queue_name,
                routing_key=topic,
            )

        # Gather all RabbitMQ handles in a single dictionary and store it in an
        # instance variable.
        handles = {
            'conn': conn,
            'chan': chan,
            'name_queue': queue_name,
            'name_exchange': exchange_name
        }
        return RetVal(True, None, handles)

    def onMessage(self):
        """
        For user to overload. Triggers after a message was received.
        """
        pass

    def onTimeout(self):
        """Triggers after the periodic timer expired.

        User can overload this function to trigger custom callbacks.
        """
        pass

    def _onMessage(self, ch, method, properties, body):
        """Pika/RabbitMQ callback for when a message arrives - do not overload.

        Handle the incoming message, trigger the user callback
        :meth:`~onMessage`. This method will also terminate the event loop if
        the user has called :meth:`~stop` previously.

        Args:
            See Pika documentation.
        """
        # Add the message to the local cache.
        self.messages.append((method.routing_key, body))

        # Trigger the callback.
        self.onMessage()

        # Terminate the event loop if the '_terminate' flag has been set.
        if self._terminate is True:
            self.rmq['chan'].stop_consuming()

    def _onTimeout(self):
        """Pika/RabbitMQ callback for timeouts - do not overload.

        Terminate the event loop if :meth:`~stop` has been called.
        """
        self.onTimeout()
        if self._terminate is True:
            self.rmq['chan'].stop_consuming()
        else:
            self.rmq['conn'].add_timeout(self._timeout, self._onTimeout)

    def stop(self):
        """Signal the thread to terminate itself.

        This method sets an internal flag but does *not* terminate the thread.
        Instead, the callback methods for messages or timeout will check that
        flag and terminate the event loop. This is necessary because
        :meth:`~stop` will be called from a different thread.
        """
        self.logit.info('Got <stop> signal')
        self._terminate = True

    def getMessages(self):
        """Return all cached messages.

        Subsequent calls to this method will not return old messages.

        Returns:
            Success (RetVal): Always True.
        """
        msg = list(self.messages)
        self.messages = self.messages[len(msg):]
        return RetVal(True, None, msg)

    @typecheck
    def publish(self, topic: str, msg: bytes):
        """Publish the binary ``msg`` to ``topic``.

        The ``topic`` must be a `.` delimited string, for instance
        'foo.bar.something'.

        This method will automatically connect to RabbitMQ.

        Returns an error if the message could not be transmitted.

        Args:
            topic (str): the topic to publish on
            msg (bytes): the payload.
        Return:
            Success (RetVal): True if successful, False otherwise.
        """
        # Connect to RabbitMQ if not already connected.
        if self.rmq is None:
            self.connect()

        # Publish the message and intercept possible errors.
        try:
            self.rmq['chan'].basic_publish(
                exchange=self.rmq['name_exchange'],
                routing_key=topic,
                body=msg,
            )
        except pika.exceptions.ChannelClosed:
            msg = 'Channel Closed'
            self.logit.warning('Could not publish message <{}>'.format(msg))
            return RetVal(False, msg, None)
        except pika.exceptions.ChannelError:
            msg = 'Channel Error'
            self.logit.warning('Could not publish message <{}>'.format(msg))
            return RetVal(False, msg, None)
        except pika.exceptions.ConnectionClosed:
            msg = 'Connection Closed'
            self.logit.warning('Could not publish message <{}>'.format(msg))
            return RetVal(False, msg, None)
        return RetVal(True, None, None)

    def _blockingConsumePika(self):
        """Pika specific portion of :meth:`~blockingConsume`.

        Auxiliary method that triggers the blocking consumption via the Pika
        wrapper.
        """
        # Install timeout callback.
        self.rmq['conn'].add_timeout(self._timeout, self._onTimeout)

        # Install message callback for the subscribed keys.
        self.rmq['chan'].basic_consume(
            self._onMessage,
            queue=self.rmq['name_queue'], no_ack=False
        )
        self.rmq['chan'].start_consuming()

    def blockingConsume(self):
        """Connect to RabbitMQ and commence the message consumption.

        This method also installs callbacks for when messages arrive or the
        timeout counter expires.

        Note: this method does not return of its own accord. The only two
        scenarios where it does return is if an exception is thrown or one of
        the callbacks explicitly terminates the event loop.

        Returns:
            Success (RetVal): True if no errors were raised, False otherwise.
        """
        if self.rmq is None:
            return RetVal(False, 'Not yet connected', None)

        # Commence Pika's event loop. This will block indefinitely. To stop it,
        # another thread must call the 'stop' method.
        try:
            self._blockingConsumePika()
            return RetVal(True, None, None)
        except pika.exceptions.ChannelClosed:
            msg = 'Channel Closed'
            self.logit.warning('Error in consume loop (<{}>)'.format(msg))
            return RetVal(False, msg, None)
        except pika.exceptions.ChannelError:
            msg = 'Channel Error'
            self.logit.warning('Error in consume loop (<{}>)'.format(msg))
            return RetVal(False, msg, None)
        except pika.exceptions.ConnectionClosed:
            msg = 'Connection Closed'
            self.logit.warning('Error in consume loop (<{}>)'.format(msg))
            return RetVal(False, msg, None)

    def run(self):
        """ Establish connection and start consuming.

        This method typically runs in a new thread and blocks until the
        user calls :meth:`~stop` from another thread.

        This method also returns if the connection to the broker has been
        severed too many times.
        """
        # Establish the connection (break the existing one if necessary).
        self.disconnect()
        self.connect()

        # Consume messages until it voluntarily quits or reaches the retry
        # limit.
        retries = 0
        while not self.blockingConsume().ok:
            self.disconnect()
            time.sleep(0.2)
            self.connect()
            retries += 1
            assert retries < 1000
