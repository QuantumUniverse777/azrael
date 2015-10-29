# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
Test the Websocket version of the Client.

The tests for ``Client`` automatically test the Websocket
version. However, some tests, especially for the initial connection are
specific to this client type. Only these are covered here.
"""

import os
import sys
import client
import pytest
import wsclient
import azrael.web
import azrael.clerk

from IPython import embed as ipshell

p = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(p, '../'))
import azrael.clerk


Client = client.Client
WSClient = wsclient.WSClient


def test_custom_objid():
    """
    Create two clients. The first automatically gets an ID assigned,
    whereas the second one specifies one explicitly.

    This behaviour matches that of `Client`` but is not automatically
    inherited because the ``WSClient`` is not a client itself but a
    wrapper to communicate with the client instance in WebServer.
    """
    # Start Clerk.
    clerk = azrael.clerk.Clerk()
    clerk.start()

    # Start WebServer.
    web = azrael.web.WebServer()
    web.start()

    # Convenience.
    ip = '127.0.0.1'
    port = 8080

    # Instantiate a WSClient without specifiying an object ID.
    client_0 = wsclient.WSClient(ip, port)

    # Ping Clerk to verify the connection is live.
    ret = client_0.ping()
    assert (ret.ok, ret.data) == (True, 'pong clerk')

    # Instantiate another WSClient. This time specify an ID. Note: the ID
    # need not exist albeit object specific commands will subsequently fail.
    client_1 = wsclient.WSClient(ip, port)

    # Ping Clerk again to verify the connection is live.
    ret = client_1.ping()
    assert (ret.ok, ret.data) == (True, 'pong clerk')

    # Shutdown the system.
    clerk.terminate()
    web.terminate()
    clerk.join(timeout=3)
    web.join(timeout=3)

    print('Test passed')


def test_ping_WebServer():
    """
    Start services and send Ping to WebServer. Then terminate the WebServer and
    verify that the ping fails.
    """
    # Convenience.
    ip = '127.0.0.1'
    port = 8080

    # Start the services.
    clerk = azrael.clerk.Clerk()
    web = azrael.web.WebServer()
    clerk.start()
    web.start()

    # Create a Websocket client.
    client = WSClient(ip=ip, port=port, timeout=1)

    # Ping Clerk via the Web service.
    assert client.ping()
    assert client.pingWebserver().ok

    # Terminate the services.
    clerk.terminate()
    web.terminate()
    clerk.join()
    web.join()

    # Ping must now be impossible.
    with pytest.raises(ConnectionRefusedError):
        WSClient(ip=ip, port=port, timeout=1)

    assert not client.pingWebserver().ok
