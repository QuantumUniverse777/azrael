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
Build a chain of cubes.

fixme:
 - clean up
 - increase damping of the objects to avoid the perpetual jumpiness
 - the 6Dof constraint is working but ill configured
 - the code assumes there are at least 4 cubes

"""
import os
import sys
import time
import argparse
import PIL.Image
import multiprocessing

import numpy as np
import demolib

# Import the necessary Azrael modules.
import azrael.aztypes as aztypes
import pyazrael
import azrael.startup
import azutils
import azrael.config as config
import azrael.leo_api as leoAPI
import azrael.vectorgrid as vectorgrid

from azrael.aztypes import Template
from azrael.aztypes import CollShapeMeta, CollShapeEmpty, CollShapeSphere
from azrael.aztypes import CollShapeBox, ConstraintMeta, ConstraintP2P
from azrael.aztypes import Constraint6DofSpring2

from IPython import embed as ipshell


def parseCommandLine():
    """
    Parse program arguments.
    """
    # Create the parser.
    parser = argparse.ArgumentParser(
        description=('Azrael Demo Script'),
        formatter_class=argparse.RawTextHelpFormatter)

    # Shorthand.
    padd = parser.add_argument

    # Add the command line options.
    padd('--noviewer', action='store_true', default=False,
         help='Do not spawn a viewer')
    padd('--noinit', action='store_true', default=False,
         help='Do not load any models')
    padd('--loglevel', type=int, metavar='level', default=1,
         help='Specify error log level (0: Debug, 1:Info)')
    padd('--reset', type=int, metavar='T', default=-1,
         help='Simulation will reset every T seconds')
    padd('--linear', type=int, metavar='T', default=2,
         help='Duration of linear grid (in seconds)')
    padd('--circular', type=int, metavar='T', default=5,
         help='Duration of circular grid (in seconds)')

    # Run the parser.
    param = parser.parse_args()
    return param


def spawnCubes(numCols, numRows, numLayers, center=(0, 0, 0)):
    """
    Spawn multiple cubes in a regular grid.

    The number of cubes equals ``numCols`` * ``numRows`` * ``numLayers``. The
    center of this "prism" is at ``center``.

    Every cube has two boosters and two factories. The factories can themselves
    spawn more (purely passive) cubes.
    """
    # Get a Client instance.
    client = pyazrael.AzraelClient()

    # Geometry and collision shape for cube.
    vert, cs = demolib.cubeGeometry()

    # Assign the UV coordinates. Each vertex needs a coordinate pair. That
    # means each triangle needs 6 coordinates. And the cube has 12 triangles.
    uv = np.zeros(12 * 6, np.float64)
    uv[0:6] = [0, 0, 1, 0, 1, 1]
    uv[6:12] = [0, 0, 1, 1, 0, 1]
    uv[12:18] = [1, 0, 0, 1, 0, 0]
    uv[18:24] = [1, 0, 1, 1, 0, 1]
    uv[24:30] = [0, 0, 1, 1, 0, 1]
    uv[30:36] = [0, 0, 1, 0, 1, 1]
    uv[36:42] = [1, 1, 1, 0, 0, 0]
    uv[42:48] = [1, 1, 0, 0, 0, 1]
    uv[48:54] = [0, 1, 1, 0, 1, 1]
    uv[54:60] = [0, 1, 0, 0, 1, 0]
    uv[60:66] = [0, 1, 0, 0, 1, 0]
    uv[66:72] = [1, 1, 0, 1, 1, 0]

    uv = np.array(uv, np.float64)

    # Compile the path to the texture file.
    path_base = os.path.dirname(os.path.abspath(__file__))
    path_base = os.path.join(path_base, '..', 'azrael', 'static', 'img')
    fname = os.path.join(path_base, 'texture_5.jpg')

    # Load the texture and convert it to flat vector because this is how OpenGL
    # will want it.
    img = PIL.Image.open(fname)
    img = np.array(img)
    rgb = np.rollaxis(np.flipud(img), 1).flatten()

    # ----------------------------------------------------------------------
    # Define a cube with boosters and factories.
    # ----------------------------------------------------------------------
    # Two boosters, one left, one right. Both point in the same direction.
    boosters = {
        '0': aztypes.Booster(position=[+0.05, 0, 0], direction=[0, 0, 1], force=0),
        '1': aztypes.Booster(position=[-0.05, 0, 0], direction=[0, 0, 1], force=0)
    }

    # ----------------------------------------------------------------------
    # Define more booster cubes, each with a different texture.
    # ----------------------------------------------------------------------
    tID_cube = {}
    templates = []
    texture_errors = 0
    for ii in range(numRows * numCols * numLayers):
        # File name of texture.
        fname = os.path.join(path_base, 'texture_{}.jpg'.format(ii + 1))

        # Load the texture image. If the image is unavailable do not endow the
        # cube with a texture.
        try:
            img = PIL.Image.open(fname)
            img = np.array(img)
            rgb = np.rollaxis(np.flipud(img), 1)
            curUV = uv
        except FileNotFoundError:
            texture_errors += 1
            rgb = curUV = np.array([])

        # Create the template.
        tID = ('BoosterCube_{}'.format(ii))
        frags = {'frag_1': demolib.getFragMetaRaw(vert, curUV, rgb),
                 'frag_2': demolib.getFragMetaRaw(vert, curUV, rgb)}
        body = demolib.getRigidBody(cshapes={'0': cs})
        tmp = Template(tID, body, frags, boosters, {})
        templates.append(tmp)

        # Add the templateID to a dictionary because we will need it in the
        # next step to spawn the templates.
        tID_cube[ii] = tID
        del frags, tmp, tID, fname

    if texture_errors > 0:
        print('Could not load texture for {} of the {} objects'
              .format(texture_errors, ii + 1))

    # Define all templates.
    print('Adding {} templates: '.format(ii + 1), end='', flush=True)
    t0 = time.time()
    assert client.addTemplates(templates).ok
    print('{:.1f}s'.format(time.time() - t0))

    # ----------------------------------------------------------------------
    # Spawn the differently textured cubes in a regular grid.
    # ----------------------------------------------------------------------
    allObjs = []
    cube_idx = 0
    cube_spacing = 0.0

    # Determine the template and position for every cube. The cubes are *not*
    # spawned in this loop, but afterwards.
    print('Compiling scene: ', end='', flush=True)
    t0 = time.time()
    for row in range(numRows):
        for col in range(numCols):
            for lay in range(numLayers):
                # Base position of cube.
                pos = np.array([col, row, lay], np.float64)

                # Add space in between cubes.
                pos *= -(4 + cube_spacing)

                # Correct the cube's position to ensure the center of the
                # grid coincides with the origin.
                pos[0] += (numCols // 2) * (1 + cube_spacing)
                pos[1] += (numRows // 2) * (1 + cube_spacing)
                pos[2] += (numLayers // 2) * (1 + cube_spacing)

                # Move the grid to position ``center``.
                pos += np.array(center)

                # Store the position and template for this cube.
                allObjs.append({'template': tID_cube[cube_idx],
                                'position': pos})
                cube_idx += 1
                del pos

    # Since the first four cubes will be chained together we need at least four
    # of them!
    assert len(allObjs) >= 4

    allObjs = []
    pos_0 = [2, 0, -10]
    pos_1 = [-2, 0, -10]
    pos_2 = [-6, 0, -10]
    pos_3 = [-10, 0, -10]
    allObjs.append({'templateID': tID_cube[0], 'rbs': {'position': pos_0}})
    allObjs.append({'templateID': tID_cube[1], 'rbs': {'position': pos_1}})
    allObjs.append({'templateID': tID_cube[2], 'rbs': {'position': pos_2}})
    allObjs.append({'templateID': tID_cube[3], 'rbs': {'position': pos_3}})

    # The first object cannot move (only rotate). It serves as an anchor for
    # the connected bodies.
    allObjs[0]['rbs']['linFactor'] = [0, 0, 0]
    allObjs[0]['rbs']['rotFactor'] = [1, 1, 1]

    # Add a small damping factor to all bodies to avoid them moving around
    # perpetually.
    for oo in allObjs[1:]:
        oo['rbs']['linFactor'] = [0.9, 0.9, 0.9]
        oo['rbs']['rotFactor'] = [0.9, 0.9, 0.9]

    print('{:,} objects ({:.1f}s)'.format(len(allObjs), time.time() - t0))
    del cube_idx, cube_spacing, row, col, lay

    # Spawn the cubes from the templates at the just determined positions.
    print('Spawning {} objects: '.format(len(allObjs)), end='', flush=True)
    t0 = time.time()
    ret = client.spawn(allObjs)
    assert ret.ok
    objIDs = ret.data
    print('{:.1f}s'.format(time.time() - t0))

    # Define the constraints.
    p2p_0 = ConstraintP2P(pivot_a=[-2, 0, 0], pivot_b=[2, 0, 0])
    p2p_1 = ConstraintP2P(pivot_a=[-2, 0, 0], pivot_b=[2, 0, 0])
    p2p_2 = ConstraintP2P(pivot_a=[-2, 0, 0], pivot_b=[2, 0, 0])
    dof = Constraint6DofSpring2(
        frameInA=[0, 0, 0, 0, 0, 0, 1],
        frameInB=[0, 0, 0, 0, 0, 0, 1],
        stiffness=[2, 2, 2, 1, 1, 1],
        damping=[1, 1, 1, 1, 1, 1],
        equilibrium=[-2, -2, -2, 0, 0, 0],
        linLimitLo=[-4.5, -4.5, -4.5],
        linLimitHi=[4.5, 4.5, 4.5],
        rotLimitLo=[-0.1, -0.2, -0.3],
        rotLimitHi=[0.1, 0.2, 0.3],
        bounce=[1, 1.5, 2],
        enableSpring=[True, False, False, False, False, False])
    constraints = [
        ConstraintMeta('', 'p2p', objIDs[0], objIDs[1], p2p_0),
        ConstraintMeta('', 'p2p', objIDs[1], objIDs[2], p2p_1),
        ConstraintMeta('', '6DOFSPRING2', objIDs[2], objIDs[3], dof),
    ]
    assert client.addConstraints(constraints) == (
        True, None, [True] * len(constraints))


def main():
    # Parse the command line.
    param = parseCommandLine()

    assert vectorgrid.resetGrid('force').ok

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)

    # Start Azrael services.
    with azutils.Timeit('Startup Time', True):
        az.start()
        if not param.noinit:
            # Spawn four cubes in a row.
            spawnCubes(4, 1, 1, center=(0, 0, 10))

        # Launch a dedicated process to periodically reset the simulation.
        time.sleep(2)

    print('Azrael now live')

    # Either wait forever or start the Qt Viewer and wait for it to return.
    if param.noviewer:
        demolib.waitForever()
    else:
        viewer = demolib.launchQtViewer()
        viewer.wait()

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
