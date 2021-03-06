# Copyright 2015, Oliver Nagy <olitheolix@gmail.com>
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
import json
import time
import pika
import pytest
import unittest.mock as mock
from azrael.aztypes import RetVal

from IPython import embed as ipshell
import azrael.eventstore as eventstore

MagicMock = mock.MagicMock


class TestUnitEventStore:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        pass

    def teardown_method(self, method):
        pass

    @mock.patch.object(eventstore.EventStore, 'setupRabbitMQ')
    def test_connect_when_setupRabbitMQ_does_not_raise(self, m_setupRabbitMQ):
        """
        Handle the return values of setupRabbitMQ correctly when it does not
        raise any exceptions.
        """
        # Constructor must set 'rmq' to None and not connect to RabbitMQ.
        es = eventstore.EventStore(topics=['#'])
        assert es.rmq is None
        assert m_setupRabbitMQ.call_count == 0

        # If the 'rmq' is not None then setupRabbitMQ must not be called.
        es.rmq = {'x': 'y'}
        assert m_setupRabbitMQ.call_count == 0
        assert es.connect() == (True, None, None)
        assert m_setupRabbitMQ.call_count == 0
        assert es.rmq == {'x': 'y'}

        # If the 'rmq' is None then setupRabbitMQ must be called and its return
        # value stored in the 'rmq' instance variable.
        es.rmq = None
        m_setupRabbitMQ.reset_mock()
        m_setupRabbitMQ.return_value = RetVal(True, None, {'foo': 'bar'})
        assert m_setupRabbitMQ.call_count == 0
        assert es.connect() == (True, None, None)
        assert m_setupRabbitMQ.call_count == 1
        assert es.rmq == {'foo': 'bar'}

    @mock.patch.object(eventstore.EventStore, 'setupRabbitMQ')
    def test_connect_when_setupRabbitMQ_raises_exception(self, m_setupRabbitMQ):
        """
        SetupRabbitMQ raises an error. Our 'setup' method must intercept them
        and return an error.
        """
        # Define possible exceptions.
        possible_exceptions = [
            pika.exceptions.ChannelClosed,
            pika.exceptions.ChannelError,
            pika.exceptions.ConnectionClosed,
        ]

        # Verify that each error is intercepted.
        for err in possible_exceptions:
            es = eventstore.EventStore(topics=['#'])
            m_setupRabbitMQ.mock_reset()
            m_setupRabbitMQ.side_effect = err
            assert not es.connect().ok

    def test_disconnect(self):
        # Get an EventStore instance.
        es = eventstore.EventStore(topics=['#'])

        # Must do nothing when es.rmq is None.
        es.rmq = None
        assert es.disconnect() == (True, None, None)

        # Specify RabbitMQ handles.
        m_chan = MagicMock()
        m_conn = MagicMock()
        es.rmq = {'chan': m_chan, 'conn': m_conn}

        # This time, 'disconnect' must call the close methods on the RabbitMQ
        # channel and connection, respectively.
        assert es.disconnect() == (True, None, None)
        m_chan.close.call_count == 1
        m_conn.close.call_count == 1
        assert es.rmq is None

    @mock.patch.object(eventstore.EventStore, '_blockingConsumePika')
    def test_blockingConsume_not_yet_connected(self, m__blockingConsumePika):
        """
        Our 'blockingConsume' function must automatically connect to RabbitMQ
        unless the connection already exists.
        """
        # Get an EventStore instance.
        es = eventstore.EventStore(topics=['#'])

        # 'blockingConsume' must return with an error if no RabbitMQ handles
        # are available.
        assert es.rmq is None
        assert m__blockingConsumePika.call_count == 0
        assert es.blockingConsume() == (False, 'Not yet connected', None)
        assert m__blockingConsumePika.call_count == 0

        # 'blockingConsume' must call the Pika handler if handles are available
        es.rmq = {'foo': 'bar'}
        m__blockingConsumePika.return_value = RetVal(True, None, None)
        assert m__blockingConsumePika.call_count == 0
        assert es.blockingConsume().ok
        assert m__blockingConsumePika.call_count == 1

    @mock.patch.object(eventstore.EventStore, 'connect')
    @mock.patch.object(eventstore.EventStore, 'disconnect')
    @mock.patch.object(eventstore.EventStore, 'blockingConsume')
    def test_run_auto_connect(self, m_blockingConsume, m_disconnect, m_connect):
        # Get an EventStore instance.
        es = eventstore.EventStore(topics=['#'])

        # 'blockingConsume' will return an error the first two times, and no
        # error the last time.
        m_blockingConsume.side_effect = [
            RetVal(False, None, None),
            RetVal(False, None, None),
            RetVal(True, None, None)
        ]

        # 'run' must call the 'connect' method whenever an error has occurred,
        # and exit once 'blockingConsume' returns without error (this
        # constitutes terminating the thread). Note: run always calls
        # 'disconnect' and 'connnect' before it makes any attempts to consume,
        # hence the '+1' in the test below.
        es.run()
        assert m_connect.call_count == 2 + 1
        assert m_disconnect.call_count == 2 + 1
        assert m_blockingConsume.call_count == 3

    def test_blockingConsume_when_pika_raises_error(self):
        """
        Creat mocked Pika handles and let 'start_consume' raise an error. Our
        own 'blockingConsume' must safely intercept the error.
        """
        # Create one EventStore instance and subscribed it to all topics.
        possible_exceptions = [
            pika.exceptions.ChannelClosed,
            pika.exceptions.ChannelError,
            pika.exceptions.ConnectionClosed,
        ]

        # Create an EventStore instance, mock out the RabbitMQ channel, and let
        # the 'start_consuming' method raise one of the various RabbitMQ errors
        # we want to intercept.
        for err in possible_exceptions:
            es = eventstore.EventStore(topics=['#'])
            m_chan = MagicMock()
            m_chan.start_consuming.side_effect = err
            es.rmq = {'chan': m_chan, 'conn': MagicMock(), 'name_queue': 'foo'}
            assert not es.blockingConsume().ok

    @mock.patch.object(eventstore.EventStore, 'connect')
    def test_publish_raises_no_error(self, m_connect):
        # Get an EventStore instance.
        es = eventstore.EventStore(topics=['#'])

        # Side effect function for the mock (see below).
        m_chan = MagicMock()
        rmq_mock_handles = {
            'chan': m_chan, 'conn': MagicMock(),
            'name_queue': 'foo', 'name_exchange': 'foo'
        }

        # Install mocked RabbitMQ as a side effect because the rest of the
        # connect function will assume they exist.
        def side_effect_fun():
            es.rmq = rmq_mock_handles

        # We expect the mocked 'connect' function to return success and install
        # the 'rmq' instance variable.
        m_connect.side_effect = side_effect_fun
        m_connect.return_value = RetVal(True, None, None)

        # Publish one message when no connection has been established yet.
        assert es.rmq is None
        assert m_chan.basic_publish.call_count == 0
        assert m_connect.call_count == 0
        assert es.publish(topic='foo', msg=b'bar') == (True, None, None)
        assert m_connect.call_count == 1
        assert m_chan.basic_publish.call_count == 1

        # Publish one message when the connection has already been established.
        es.rmq = rmq_mock_handles
        m_chan.reset_mock()
        m_connect.reset_mock()
        m_connect.return_value = RetVal(True, None, None)
        assert m_chan.basic_publish.call_count == 0
        assert m_connect.call_count == 0
        assert es.publish(topic='foo', msg=b'bar') == (True, None, None)
        assert m_connect.call_count == 0
        assert m_chan.basic_publish.call_count == 1

    def test_publish_raises_errors(self):
        """
        Our 'publish' method must safely intercept all errors raised by Pika's
        'basic_publish' method.
        """
        # Define possible exceptions.
        possible_exceptions = [
            pika.exceptions.ChannelClosed,
            pika.exceptions.ChannelError,
            pika.exceptions.ConnectionClosed,
        ]

        # Verify that each error is intercepted.
        for err in possible_exceptions:
            es = eventstore.EventStore(topics=['#'])
            m_chan = MagicMock()
            m_chan.basic_publish.side_effect = err
            es.rmq = {'chan': m_chan, 'conn': MagicMock(), 'name_exchange': 'foo'}
            assert not es.publish(topic='foo', msg=b'bar').ok


class TestIntegrationEventStore:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        pass

    def teardown_method(self, method):
        pass

    def createEventStoreClients(self, num_clients: int, topics: list):
        """
        Return a of connected EventStore clients.

        The list will contain `num_client` thread handles.

        This method does not return until all threads have successfully
        established a connection to RabbitMQ.
        """
        # Spawn the threads.
        es = [eventstore.EventStore(topics=topics) for _ in range(3)]
        [_.start() for _ in es]

        # Wait until each thread updated its 'rmq' attribute.
        while True:
            if len([_.rmq for _ in es if _.rmq is None]) == 0:
                return es
            time.sleep(0.5)
            print('waiting')

    def test_shutdown(self):
        """
        Verify that the EventStore threads shut down properly. Threads must be
        cooperative in this regard because Python lacks the mechanism to
        forcefully terminate them.
        """
        # Create an EventStore instance and subscribe it to all topics.
        es = self.createEventStoreClients(num_clients=1, topics=['#'])[0]

        # Tell the thread to stop. Wait at most one Second, then verify it has
        # really stopped.
        es.stop()
        es.join(1.0)
        assert not es.is_alive()

        # Repeat the above test with many threads.
        threads = [eventstore.EventStore(topics=['#']) for _ in range(100)]
        [_.start() for _ in threads]
        time.sleep(0.2)
        [_.stop() for _ in threads]
        [_.join(1.0) for _ in threads]
        for thread in threads:
            assert not thread.is_alive()
        del threads

    def test_basic_publishing(self):
        """
        Create an EventStore instance that listens for all messages. Then
        publish some messages and verify they arrive as expected.
        """
        # Create an EventStore instance and subscribe it to all topics.
        es = self.createEventStoreClients(num_clients=1, topics=['#'])[0]

        # Create a dedicated publisher instance because the class does not play
        # nice when called from different threads.
        pub = eventstore.EventStore(topics=['foo'])

        # No messages must have arrived yet.
        assert es.getMessages() == (True, None, [])

        # Publish our test messages.
        assert pub.publish(topic='foo', msg=b'bar0').ok
        assert pub.publish(topic='foo', msg=b'bar1').ok

        # Wait until the client received at least two messages (RabbitMQ incurs
        # some latency).
        for ii in range(10):
            time.sleep(0.1)
            if len(es.messages) >= 2:
                break
            assert ii < 9

        # Verify we got both messages.
        ret = es.getMessages()
        assert ret.ok
        assert ret.data == [
            ('foo', b'bar0'),
            ('foo', b'bar1'),
        ]

        # There must be no new messages.
        assert es.getMessages() == (True, None, [])

        # Stop the thread.
        es.stop()
        es.join()

    def test_invalid_key(self):
        """
        Similar test as before, but this time we subscribe to a particular
        topic instead of all topics. That is, publish three message, two to
        the topic we subscribed to, and one to another topic. We should only
        receive two messages.
        """
        # Create an EventStore instance and subscribe it to the 'foo' topic.
        es = self.createEventStoreClients(num_clients=1, topics=['foo'])[0]

        # No messages must have arrived yet.
        assert es.getMessages() == (True, None, [])

        # Create a dedicated publisher instance because the class does not play
        # nice when called from different threads.
        pub = eventstore.EventStore(topics=['foo'])

        # Publish our test messages.
        pub.publish(topic='foo', msg=b'bar0')
        pub.publish(topic='blah', msg=b'bar1')
        pub.publish(topic='foo', msg=b'bar2')

        # Wait until the client received at least two messages (RabbitMQ incurs
        # some latency).
        for ii in range(10):
            time.sleep(0.1)
            if len(es.messages) >= 2:
                break
            assert ii < 9

        # Verify that we got the two messages for our topic.
        ret = es.getMessages()
        assert ret.ok
        assert ret.data == [
            ('foo', b'bar0'),
            ('foo', b'bar2'),
        ]

        # Stop the thread.
        es.stop()
        es.join()

    def test_multiple_receivers(self):
        """
        Create several listeners and verify they all receive the message.
        """
        # Start several event store threads and subscribe them to 'foo'.
        es = self.createEventStoreClients(num_clients=3, topics=['foo'])

        # Create a dedicated publisher instance because the class does not play
        # nice when called from different threads.
        pub = eventstore.EventStore(topics=['foo'])

        # Publish our test messages.
        pub.publish(topic='foo', msg=b'bar0')
        pub.publish(topic='blah', msg=b'bar1')
        pub.publish(topic='foo', msg=b'bar2')

        # Wait until each client received at least two messages (RabbitMQ incurs
        # some latency).
        for ii in range(10):
            time.sleep(0.1)
            if min([len(_.messages) for _ in es]) >= 2:
                break
            assert ii < 9

        # Verify each client got both messages.
        for thread in es:
            ret = thread.getMessages()
            assert ret.ok
            assert ret.data == [
                ('foo', b'bar0'),
                ('foo', b'bar2'),
            ]

        # Stop the threads.
        [_.stop() for _ in es]
        [_.join() for _ in es]

    def test_listen_for_multiple_topics(self):
        """
        Subscribe two multiple topics at once.
        """
        # Create an EventStore instance and subscribe it to all messages.
        es = self.createEventStoreClients(num_clients=1, topics=['foo', 'bar'])[0]

        # Create a dedicated publisher instance because the class does not play
        # nice when called from different threads.
        pub = eventstore.EventStore(topics=['foo'])

        # Publish our test messages.
        pub.publish(topic='foo', msg=b'0')
        pub.publish(topic='blah', msg=b'1')
        pub.publish(topic='bar', msg=b'2')

        # Wait until the client received at least two messages (RabbitMQ incurs
        # some latency).
        for ii in range(10):
            time.sleep(0.1)
            if len(es.messages) >= 2:
                break
            assert ii < 9

        # Verify we got the message published for 'foo' and 'bar'.
        ret = es.getMessages()
        assert ret.ok
        assert ret.data == [
            ('foo', b'0'),
            ('bar', b'2'),
        ]

        # Stop the thread.
        es.stop()
        es.join()
