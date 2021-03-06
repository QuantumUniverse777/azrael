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
import base64
import json

import azrael.test.test
import azrael.aztypes as aztypes
import azrael.protocol as protocol

from IPython import embed as ipshell
from azrael.test.test import getP2P, get6DofSpring2
from azrael.test.test import getFragRaw, getFragDae, getRigidBody


class TestClerk:
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

    def getTestTemplate(self, templateID='templateID'):
        """
        Return a valid template with non-trivial data. The template contains
        multiple fragments (Raw and Collada), boosters, factories, and a rigid
        body.

        This is a convenience method only.
        """
        # Define a new object with two boosters and one factory unit.
        # The 'boosters' and 'factories' arguments are a list of named
        # tuples. Their first argument is the unit ID (Azrael does not
        # automatically assign any IDs).
        boosters = {
            '0': aztypes.Booster(position=(0, 1, 2), direction=(0, 0, 1), force=0),
            '1': aztypes.Booster(position=(6, 7, 8), direction=(0, 1, 0), force=0),
        }
        factories = {
            '0': aztypes.Factory(position=(0, 0, 0), direction=(0, 0, 1),
                                 templateID='_templateBox',
                                 exit_speed=(0.1, 0.5))
        }

        # Create some fragments...
        frags = {'f1': getFragRaw(), 'f2': getFragDae()}

        # ... and a body...
        body = getRigidBody(position=(1, 2, 3))

        # ... then compile and return the template.
        return azrael.test.test.getTemplate(
            templateID,
            rbs=body,
            fragments=frags,
            boosters=boosters,
            factories=factories)

    def test_addTemplate(self):
        """
        The codec must undo the Base64 encodings on all files in all fragments.
        """
        # Compile a valid Template structure.
        payload_src = [self.getTestTemplate('t1'), self.getTestTemplate('t2')]
        payload_dict = [_._asdict() for _ in payload_src]

        # Base64 encode all files because this is how the protocol on Clerk's
        # end expects it.
        for payload in payload_dict:
            for fragname in payload['fragments']:
                files = payload['fragments'][fragname]['files']
                files = {k: base64.b64encode(v).decode('utf8')
                         for k, v in files.items()}
                payload['fragments'][fragname]['files'] = files

        # Convert to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps({'templates': payload_dict}))
        dec = protocol.ToClerk_AddTemplates_Decode(enc)

        # The decoded template must match the original.
        assert dec['templates'] == payload_src

    def test_GetTemplate(self):
        """
        Verify the return format.
        """
        # Get a valid template.
        template = self.getTestTemplate()

        # Remove the content of all files because this is how Clerk will do it
        # too (files are only available via the web server).
        for fragname in template.fragments:
            files = template.fragments[fragname].files
            for k in files:
                files[k] = None

        # Clerk --> Client.
        payload = {template.aid: {
            'url_frag': 'http://somewhere',
            'template': template}
        }

        # Simulate wire transmission.
        enc = protocol.FromClerk_GetTemplates_Encode(payload)
        enc = json.loads(json.dumps(enc))

        r = enc[template.aid]
        assert r['url_frag'] == payload[template.aid]['url_frag']
        assert aztypes.Template(**r['template']) == payload[template.aid]['template']

    def test_ControlParts(self):
        """
        Test controlParts codec.
        """
        # Define the commands.
        cmd_boosters = {
            '0': aztypes.CmdBooster(force=0.2),
            '1': aztypes.CmdBooster(force=0.4),
        }
        cmd_factories = {
            '0': aztypes.CmdFactory(exit_speed=0),
            '2': aztypes.CmdFactory(exit_speed=0.4),
            '3': aztypes.CmdFactory(exit_speed=4),
        }
        objID = 1

        # ----------------------------------------------------------------------
        # Client --> Clerk.
        # ----------------------------------------------------------------------

        payload = {
            'objID': objID,
            'cmd_boosters': {k: v._asdict() for (k, v) in cmd_boosters.items()},
            'cmd_factories': {k: v._asdict() for (k, v) in cmd_factories.items()}
        }

        # Convert to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(payload))
        r = protocol.ToClerk_ControlParts_Decode(enc)

        # Decode- and verify the data.
        assert r['objID'] == objID
        assert r['cmd_boosters'] == cmd_boosters
        assert r['cmd_factories'] == cmd_factories

    def test_GetRigidBodyData(self):
        """
        Test codec for GetRigidBodyData.
        """
        # Clerk --> Client.
        frag_states = {
            '1': {'scale': 1, 'position': [0, 1, 2], 'rotation': [0, 0, 0, 1]},
            '2': {'scale': 2, 'position': [3, 4, 5], 'rotation': [1, 0, 0, 0]},
        }

        # The payload contains fragment- and body state data for each object.
        # The payload used here covers all cases where both, only one of the
        # two, or neither are defined.
        payload = {
            1: {'frag': frag_states, 'rbs': getRigidBody()},
            2: {'frag': {}, 'rbs': getRigidBody()},
            3: None,
        }
        del frag_states

        # Encode source data and simulate wire transmission.
        enc = protocol.FromClerk_GetRigidBodyData_Encode(payload)
        enc = json.loads(json.dumps(enc))

        # Verify that the rigid bodies survived the serialisation.
        for objID in [1, 2]:
            # Convenience.
            src = payload[objID]
            dst = enc[str(objID)]

            # Compile a rigid body from the returned data and compare it to the
            # original.
            assert src['rbs'] == aztypes.RigidBodyData(**dst['rbs'])

        assert enc['3'] is None

    def test_add_get_constraint(self):
        """
        Add- and get constraints.
        """
        # Define the constraints.
        p2p = getP2P(rb_a='1', rb_b='2', pivot_a=(0, 1, 2), pivot_b=(3, 4, 5))
        dof = get6DofSpring2(rb_a='1', rb_b='2')

        # ----------------------------------------------------------------------
        # Client --> Clerk.
        # ----------------------------------------------------------------------
        for con in (p2p, dof):
            payload = {'constraints': [con._asdict()]}
            # Convert to JSON and back (simulates the wire transmission).
            enc = json.loads(json.dumps(payload))

            # Decode the data.
            dec_con = protocol.ToClerk_AddConstraints_Decode(enc)
            dec_con = dec_con['constraints']
            assert len(dec_con) == 1
            assert dec_con[0] == con

        # ----------------------------------------------------------------------
        # Clerk --> Client
        # ----------------------------------------------------------------------
        for con in (p2p, dof):
            # Encode source data and simulate wire transmission.
            enc = protocol.FromClerk_GetConstraints_Encode([con])
            enc = json.loads(json.dumps(enc))

            # Decode the data.
            assert len(enc) == 1
            assert aztypes.ConstraintMeta(**enc[0]) == con

    def test_spawn(self):
        """
        Spawn objects.
        """
        # Compile a valid Template structure.
        payload = [
            {'templateID': 'tid_1', 'rbs': {'position': [0, 1, 2]}},
            {'templateID': 'tid_2', 'rbs': {'rotation': [0, 1, 0, 0]}},
        ]

        # Client --> Clerk: Convert to JSON and back (simulates the wire
        # transmission).
        enc = json.loads(json.dumps({'newObjects': payload}))
        dec = protocol.ToClerk_Spawn_Decode(enc)
        assert dec['newObjects'] == payload

    def test_getFragments(self):
        """
        Test getFragments.
        """
        # Clerk --> Client
        payload = {
            1: {'foo1': {'fragtype': 'raw', 'url_frag': 'http://foo1'},
                'bar1': {'fragtype': 'dae', 'url_frag': 'http://bar1'}},
            5: {'foo2': {'fragtype': 'raw', 'url_frag': 'http://foo2'},
                'bar2': {'fragtype': 'dae', 'url_frag': 'http://bar2'}}
        }
        enc = protocol.FromClerk_GetFragments_Encode(payload)
        dec = json.loads(json.dumps(enc))

        # Convert the IDs to integers and makey sure the payload survived.
        dec = {int(k): v for (k, v) in dec.items()}
        assert payload == dec
