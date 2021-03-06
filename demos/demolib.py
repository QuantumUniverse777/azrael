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

import os
import sys
import time
import json
import subprocess

# Import 'setproctitle' *before* NumPy, even though it is not even used in this
# script. However, if it is import after NumPy then the various Azrael modules
# cannot rename themselves. No, I do not know why.
import setproctitle

import numpy as np

# Import the necessary Azrael modules.
p = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(p, '..'))
sys.path.insert(0, os.path.join(p, '../viewer'))
sys.path.insert(0, os.path.join(p, '../shared'))
del p

import model_import
import azutils
import azrael.aztypes as aztypes
from IPython import embed as ipshell
from azrael.aztypes import Template, FragMeta
from azrael.aztypes import CollShapeMeta, CollShapeEmpty, CollShapeSphere
from azrael.aztypes import CollShapeBox

# Determine the host/ports of all Azrael services.
azService = azutils.getAzraelServiceHosts('/etc/hosts')


def compileRawFragment(vert, uv, rgb):
    if not isinstance(vert, np.ndarray):
        vert = np.array(vert, np.float64)
    if not isinstance(uv, np.ndarray):
        uv = np.array(uv, np.float64)
    if not isinstance(rgb, np.ndarray):
        rgb = np.array(rgb, np.uint8)

    # Number of vertices.
    num_vert = np.prod(vert.shape) // 3
    num_rgb = np.prod(rgb.shape) // 3
    num_uv = np.prod(uv.shape) // 2

    # In the absence of UV data the RGB data must be a simple vector that
    # denotes vertex colors. If UV is a non-zero array then RGB must be a
    # image texture (3D array).
    if len(rgb) == 0:
        # No RGB or UV.
        assert len(uv) == 0
        width = height = None
    elif rgb.ndim == 1:
        # No UV map; RGB must denote one RGB triplet for each vertex.
        assert len(uv) == 0, (len(uv), rgb.shape)
        assert num_rgb == num_vert
        width = height = None
    elif rgb.ndim == 3:
        # UV map; RGB must be an image texture.
        width, height, depth = rgb.shape
        assert depth == 3
        assert num_uv == num_vert
    else:
        assert False

    model = {
        'vert': vert.tolist(),
        'uv': uv.tolist(),
        'rgb': rgb.flatten().tolist(),
        'width': width,
        'height': height,
    }

    return {'model.json': json.dumps(model).encode('utf8')}


def getFragMetaRaw(vert, uv, rgb, scale=1, pos=(0, 0, 0), rot=(0, 0, 0, 1)):
    """
    Return compiled FragMeta tuple for a modle in RAW format.
    """
    files = compileRawFragment(vert, uv, rgb)
    return FragMeta(fragtype='RAW', scale=scale, position=pos,
                    rotation=rot, files=files)


def getRigidBody(scale: (int, float)=1,
                 imass: (int, float)=1,
                 restitution: (int, float)=0.9,
                 com: (tuple, list)=(0, 0, 0),
                 inertia: (tuple, list)=(1, 1, 1),
                 paxis: (tuple, list)=(0, 0, 0, 1),
                 rotation: (tuple, list)=(0, 0, 0, 1),
                 position: (tuple, list, np.ndarray)=(0, 0, 0),
                 velocityLin: (tuple, list, np.ndarray)=(0, 0, 0),
                 velocityRot: (tuple, list, np.ndarray)=(0, 0, 0),
                 cshapes: dict=None,
                 linFactor: (tuple, list, np.ndarray)=(1, 1, 1),
                 rotFactor: (tuple, list, np.ndarray)=(1, 1, 1),
                 version: int=0):
    if cshapes is None:
        cshapes = CollShapeMeta(cstype='Sphere',
                                position=(0, 0, 0),
                                rotation=(0, 0, 0, 1),
                                csdata=CollShapeSphere(radius=1))
        cshapes = {'Sphere': cshapes}
    return aztypes.RigidBodyData(
        scale, imass, restitution, com, inertia, paxis,
        rotation, position, velocityLin, velocityRot, cshapes,
        linFactor, rotFactor, version)


def loadBoosterCubeBlender():
    """
    Load the Spaceship (if you want to call it that) from "boostercube.dae".

    This function is custom made for the Blender model of the cube with
    boosters because the model file is broken (no idea if the fault is with me,
    Blender, or the AssImp library).

    In particular, the ``loadModel`` function will only return the vertices for
    the body (cube) and *one* thruster (instead of six). To remedy, this
    function will attach a copy of that thruster to each side of the cube.  It
    will manually assign the colors too.
    """

    # Load the Collada model.
    p = os.path.dirname(os.path.abspath(__file__))
    fname = os.path.join(p, 'models', 'boostercube', 'boostercube.dae')
    vert, uv, rgb = loadModel(fname)
    del uv, rgb

    # Extract the body and thruster component.
    body, thruster_z = np.array(vert[0]), np.array(vert[1])

    # The body should be a unit cube, but I do not know what Blender created
    # exactly. Therefore, determine the average position values (which should
    # all have the same value except for the sign).
    body_scale = np.mean(np.abs(body))

    # Reduce the thruster size, translate it to the cube's surface, and
    # duplicate on -z axis.
    thruster_z = 0.3 * np.reshape(thruster_z, (len(thruster_z) // 3, 3))
    thruster_z += [0, 0, -.6]
    thruster_z = thruster_z.flatten()
    thruster_z = np.hstack((thruster_z, -thruster_z))

    # Reshape the vertices into an N x 3 matrix and duplicate for the other
    # four thrusters.
    thruster_z = np.reshape(thruster_z, (len(thruster_z) // 3, 3))
    thruster_x, thruster_y = np.array(thruster_z), np.array(thruster_z)

    # We will compute the thrusters for the remaining two cube faces with a
    # 90degree rotation around the x- and y axis.
    s2 = 1 / np.sqrt(2)
    quat_x = azutils.Quaternion(s2, 0, 0, s2)
    quat_y = azutils.Quaternion(0, s2, 0, s2)
    for ii, (tx, ty) in enumerate(zip(thruster_x, thruster_y)):
        thruster_x[ii] = quat_x * tx
        thruster_y[ii] = quat_y * ty

    # Flatten the arrays.
    thruster_z = thruster_z.flatten()
    thruster_x = thruster_x.flatten()
    thruster_y = thruster_y.flatten()

    # Combine all thrusters and the body into a single triangle mesh. Then
    # scale the entire mesh to ensure the cube part is indeed a unit cube.
    vert = np.hstack((thruster_z, thruster_x, thruster_y, body))
    vert /= body_scale

    # Assign the same base color to all three thrusters.
    rgb_thruster = np.tile([0.8, 0, 0], len(thruster_x) // 3)
    rgb_thrusters = np.tile(rgb_thruster, 3)

    # Assign a color to the body.
    rgb_body = np.tile([0.8, 0.8, 0.8], len(body) // 3)

    # Flatten the RGB vectors to match the vertex vector.
    rgb = np.hstack((rgb_thrusters, rgb_body))
    del rgb_thruster, rgb_thrusters, rgb_body

    # Add some "noise" to the blueish flame color.
    rgb += 0.2 * (np.random.rand(len(rgb)) - 0.5)

    # Scale the RGB values from [0, 1] to a [0, 255] integers.
    rgb = rgb.clip(0, 1)
    rgb = np.array(rgb * 255, np.uint8)

    # Return the model data (it has no UV data).
    uv = []
    return vert, uv, rgb


def loadSphere(radius: float=1.0):
    """
    Return the collision shape and vertices for a sphere with ``radius``.

    Args:
        radius (float): sphere radius (must be >= 0.01).

    Returns:
        (vert, colshapes): the vertices and collision shape for the sphere.
    """
    assert radius >= 0.01
    p = os.path.dirname(os.path.abspath(__file__))
    fname = os.path.join(p, 'models', 'sphere', 'sphere.obj')
    vert, uv, rgb = loadModel(fname)
    vert *= radius
    cshapes = CollShapeMeta(cstype='Sphere',
                            position=(0, 0, 0),
                            rotation=(0, 0, 0, 1),
                            csdata=CollShapeSphere(radius=radius))
    return vert, cshapes


def loadModel(fname):
    """
    Load 3D model from ``fname`` and return the vertices, UV, and RGB arrays.
    """
    # Load the model.
    print('  Importing <{}>... '.format(fname), end='', flush=True)
    mesh = model_import.loadModelAll(fname)

    # The model may contain several sub-models. Each one has a set of vertices,
    # UV- and texture maps. The following code simply flattens the three lists
    # of lists into just three lists.
    vert = np.array(mesh['vertices']).flatten()
    uv = np.array(mesh['UV'])
    rgb = np.array(mesh['RGB'])
    print('done')

    return vert, uv, rgb


def cubeGeometry(hlen_x=1.0, hlen_y=1.0, hlen_z=1.0):
    """
    Return the vertices and collision shape for a Box.

    The parameters ``hlen_*`` are the half lengths of the box in the respective
    dimension.
    """
    # Vertices that define a Cube.
    vert = 1 * np.array([
        -1.0, -1.0, -1.0,   -1.0, -1.0, +1.0,   -1.0, +1.0, +1.0,
        -1.0, -1.0, -1.0,   -1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,
        +1.0, -1.0, -1.0,   +1.0, +1.0, +1.0,   +1.0, -1.0, +1.0,
        +1.0, -1.0, -1.0,   +1.0, +1.0, -1.0,   +1.0, +1.0, +1.0,
        +1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,   +1.0, -1.0, -1.0,
        +1.0, -1.0, +1.0,   -1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,
        +1.0, +1.0, +1.0,   +1.0, +1.0, -1.0,   -1.0, +1.0, -1.0,
        +1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,   -1.0, +1.0, +1.0,
        +1.0, +1.0, -1.0,   -1.0, -1.0, -1.0,   -1.0, +1.0, -1.0,
        +1.0, +1.0, -1.0,   +1.0, -1.0, -1.0,   -1.0, -1.0, -1.0,
        -1.0, +1.0, +1.0,   -1.0, -1.0, +1.0,   +1.0, -1.0, +1.0,
        +1.0, +1.0, +1.0,   -1.0, +1.0, +1.0,   +1.0, -1.0, +1.0
    ])

    # Scale the x/y/z dimensions.
    vert[0::3] *= hlen_x
    vert[1::3] *= hlen_y
    vert[2::3] *= hlen_z

    # Convenience.
    box = CollShapeBox(hlen_x, hlen_y, hlen_z)
    cs = CollShapeMeta('box', (0, 0, 0), (0, 0, 0, 1), box)
    return vert, cs


def launchQtViewer():
    """
    Launch the Qt Viewer in a separate process and return its handle.

    The calling process will probably want to use handle.poll(),
    handle.wait(), etc to monitor the viewer process. For details see:

    https://docs.python.org/3.5/library/subprocess.html#subprocess.Popen
    """
    # Construct the absolute path the the viewer script.
    this_dir = os.path.dirname(os.path.abspath(__file__))
    fname = os.path.join(this_dir, 'viewer.py')

    # Spawn the viewer process and return its handle.
    return subprocess.Popen(['python', fname])


def waitForever():
    """
    Wait forever and intercept keyboard interrup.

    This is a covenience function because the logic shows up in most demos.
    """
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        pass


def getFragMeta3JS(filenames, scale=1, pos=(0, 0, 0), rot=(0, 0, 0, 1)):
    """
    Return compiled FragMeta tuple for a ThreeJS model.
    """
    # Load all model files.
    files = {fname: open(fname, 'rb').read() for fname in filenames}

    # Wrap the geometry data into a FragMeta tuple.
    return FragMeta(fragtype='3JS_V3',
                    scale=scale,
                    position=pos,
                    rotation=rot,
                    files=files)


def load3JSModel(data_json):
    """
    Load a model file in ThreeJS format.

    The model specification is here:
    https://github.com/mrdoob/three.js/wiki/JSON-Model-format-3
    """
    # Unpack and reshape the 'vertices', and 'UVs' for convenience. These are
    # essentially look up tables (LUT) to match up the indexes specified in the
    # 'faces' array (see below) to particular vertex/uv coordinates.
    vertex_LUT = np.array(data_json['vertices'])
    uv_LUT = np.array(data_json['uvs'][0])
    assert len(vertex_LUT) % 3 == 0
    assert len(uv_LUT) % 2 == 0

    # Reshape the flat vertex and uv arrays into [:, 3] and [:, 2] arrays,
    # respectively. This will come in handy for indexing later.
    vertex_LUT = vertex_LUT.reshape((len(vertex_LUT) // 3, 3))
    uv_LUT = uv_LUT.reshape((len(uv_LUT) // 2, 2))

    # Initialise the output structure.
    out = {'faces': [], 'uv': [], 'rgb': []}

    # The ThreeJS format stores all its information about vertices, their UV
    # coordinates, etc in an array called 'faces'. All entries in that array
    # are integers. The first integer is a command word (see spec). It
    # specifies the vertex indexes and (optionally) other characteristics, for
    # instance UV coordinates. This means the command word determines how many
    # of the integers that follow constitute one face. The first integer after
    # those is the next command word, etc.
    #
    # Interpret the face data and convert it to coordinates for vertices, UV,
    # and colour properties.
    ofs = 0
    faces = data_json['faces']
    while ofs < len(faces):
        # Command word (always one integer).
        cmd = faces[ofs]
        ofs += 1

        # Extract the bits of the command word according to the format
        # specification.
        isQuad = True if cmd & 1 else False
        hasMaterial = True if cmd & 2 else False
        hasUV = True if cmd & 4 else False
        hasVertexUV = True if cmd & 8 else False
        hasNormal = True if cmd & 16 else False
        hasVertexNormal = True if cmd & 32 else False
        hasColor = True if cmd & 64 else False
        hasVertexColor = True if cmd & 128 else False

        # Triangle or Quad (three or four integers).
        if isQuad:
            out['faces'].append(faces[ofs:ofs + 4])
            ofs += 4
        else:
            out['faces'].append(faces[ofs:ofs + 3])
            ofs += 3

        # Face material (one integer).
        if hasMaterial:
            out['rgb'].append(faces[ofs:ofs + 1][0])
            ofs += 1

        # Face UV (one integer).
        if hasUV:
            ofs += 1

        # Vertex UVs (0, 3, or 4 integers).
        if hasVertexUV:
            if isQuad:
                out['uv'].append(faces[ofs:ofs + 4])
                ofs += 4
            else:
                out['uv'].append(faces[ofs:ofs + 3])
                ofs += 3

        # Face normal (one integer).
        if hasNormal:
            ofs += 1

        # Vertex normals.
        if hasVertexNormal:
            ofs += 4 if isQuad else 3

        # Face color (one integer).
        if hasColor:
            ofs += 1

        # Vertex color.
        if hasVertexColor:
            ofs += 4 if isQuad else 3

    # Compile the vertex array that will be uploaded to the GPU (presumably).
    # The values are based on the indices that we parsed from the 'faces' field
    # above.
    vert = []
    for el in out['faces']:
        tmp = vertex_LUT[el].flatten()
        vert.extend(list(tmp))

    # Compile UV values.
    uvs = []
    for el in out['uv']:
        tmp = uv_LUT[el].flatten()
        uvs.extend(list(tmp))

    # Compile the material colors. Materials have various color components but
    # for now this will only return the ambient component.
    rgb = []
    for el in out['rgb']:
        mat = data_json['materials'][el]
        rgb.extend(mat['colorAmbient'])

    # Sanity checks.
    try:
        assert len(vert) % (3 * 3) == 0
        assert len(uvs) % (2 * 3) == 0
    except AssertionError:
        return [], [], []

    num_vert = len(vert) // 3

    np.random.seed(0)
    rgb = np.random.rand(3 * num_vert)
    rgb = (255 * rgb).astype(np.uint8).tolist()

    return vert, uvs, rgb
