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
OpenGL viewer for Azrael (Python 3 only).

You will need 'python3-pyside.qtopengl' and 'pyopengl'. On Ubuntu 14.04 you can
install them with the following commands:

  >> sudo apt-get install python3-pyside.qtopengl python3-opengl

"""

# Add the viewer directory to the Python path.
import os
import sys
import time
import json
import PIL
import demolib
import tempfile
import argparse
import requests
import model_import

import numpy as np
import OpenGL.GL as gl

import pyazrael
import azutils as util

from PyQt4 import QtCore, QtGui, QtOpenGL
from collections import namedtuple, OrderedDict
from pyazrael.aztypes import Template, CollShapeMeta, CollShapeBox, FragMeta


def parseCommandLine():
    """
    Parse program arguments.
    """
    # Create the parser.
    parser = argparse.ArgumentParser(
        description='Start an OpenGL viewer for Azrael')

    # Shorthand.
    padd = parser.add_argument

    # Add the command line options.
    padd('--addr', metavar='addr', type=str, default='',
         help='IP of Clerk (eg. "127.0.0.1")')
    padd('--port', metavar='addr', type=int, default=5555,
         help='Port of Clerk (eg. 5555)')

    param = parser.parse_args()

    if param.addr == '':
        param.addr = demolib.azService['clerk'].ip

    # run the parser.
    return param


def getFragMetaRaw(vert, uv, rgb, width, height):
    scale = 1
    pos = (0, 0, 0)
    rot = (0, 0, 0, 1)

    Model = namedtuple(
        'Model',
        'fragtype scale position rotation vert uv rgb width height'
    )
    return Model('RAW', scale, pos, rot, vert, uv, rgb, width, height)


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
                 cshapes: (tuple, list)=None,
                 linFactor: (tuple, list, np.ndarray)=(1, 1, 1),
                 rotFactor: (tuple, list, np.ndarray)=(1, 1, 1),
                 version: int=0):
    if cshapes is None:
        cshapes = CollShapeMeta(aid='',
                                cstype='Sphere',
                                position=(0, 0, 0),
                                rotation=(0, 0, 0, 1),
                                csdata=CollShapeSphere(radius=1))
        cshapes = {'': cshapes}
    return pyazrael.aztypes.RigidBodyData(
        scale, imass, restitution, com, inertia, paxis,
        rotation, position, velocityLin, velocityRot, cshapes,
        linFactor, rotFactor, version)


def perspective(fov, ar, near, far):
    """
    Return the perspective matrix.

    * ``fov``: field of view (radians, *not* degrees)
    * ``ar``: aspect ratio (ie. width / height)
    * ``near``: near clipping plane
    * ``far``: far clipping plane
    """
    fov = 1 / np.tan(fov / 2)
    mat = np.zeros((4, 4))
    mat[0, 0] = fov / ar
    mat[1, 1] = fov
    mat[2, 2] = (far + near) / (far - near)
    mat[2, 3] = -2 * far * near / (far - near)
    mat[3, 2] = 1
    return mat.astype(np.float32)


def getGeometriesCube(pos=np.zeros(3)):
    buf_vert = 0.5 * np.array([
        -1.0, -1.0, -1.0,   -1.0, -1.0, +1.0,   -1.0, +1.0, +1.0,
        +1.0, +1.0, -1.0,   -1.0, -1.0, -1.0,   -1.0, +1.0, -1.0,
        +1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,   +1.0, -1.0, -1.0,
        +1.0, +1.0, -1.0,   +1.0, -1.0, -1.0,   -1.0, -1.0, -1.0,
        -1.0, -1.0, -1.0,   -1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,
        +1.0, -1.0, +1.0,   -1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,
        -1.0, +1.0, +1.0,   -1.0, -1.0, +1.0,   +1.0, -1.0, +1.0,
        +1.0, +1.0, +1.0,   +1.0, -1.0, -1.0,   +1.0, +1.0, -1.0,
        +1.0, -1.0, -1.0,   +1.0, +1.0, +1.0,   +1.0, -1.0, +1.0,
        +1.0, +1.0, +1.0,   +1.0, +1.0, -1.0,   -1.0, +1.0, -1.0,
        +1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,   -1.0, +1.0, +1.0,
        +1.0, +1.0, +1.0,   -1.0, +1.0, +1.0,   +1.0, -1.0, +1.0])

    N = 3
    M = len(buf_vert) // N
    buf_vert = np.reshape(buf_vert, (M, N)) + pos
    return buf_vert.flatten()


class ImageWriter(QtCore.QObject):
    """
    Write screenshots to file.

    This instance can/should run in its own thread to avoid blocking the main
    thread.
    """

    # Signals must be class variables.
    sigUpdate = QtCore.pyqtSignal(float, QtGui.QImage)
    sigReset = QtCore.pyqtSignal()

    def __init__(self, baseDir):
        super().__init__()

        # Sanity check.
        assert isinstance(baseDir, str)

        # Remember the base directory.
        self.baseDir = baseDir

        # Connect the signals. The signals will be triggered from the main
        # thread.
        self.sigUpdate.connect(self.work)
        self.sigReset.connect(self.reset)

        # Auxiliary variables.
        self.imgCnt = 0
        self.videoDir = None

    @QtCore.pyqtSlot()
    def work(self, grabTime, img):
        """
        Write the images to disk (PNG format).
        """
        # Return immediately if the recorder has not been explicitly reset
        # yet.
        if self.videoDir is None:
            return

        # Build the file name and write the image.
        fname = 'frame_{0:05d}.png'.format(self.imgCnt)
        fname = os.path.join(self.videoDir, fname)
        img.save(fname)

        # Increase the image counter.
        self.imgCnt += 1

    @QtCore.pyqtSlot()
    def reset(self):
        """
        Create a new recording directory and reset the image counter.
        """
        # Reset the image counter.
        self.imgCnt = 0

        # Create a new time stamped directory.
        ts = time.strftime('%Y-%m-%d-%H:%M:%S', time.gmtime())
        self.videoDir = os.path.join(self.baseDir, ts)
        try:
            os.makedirs(self.videoDir)
        except FileExistsError:
            pass


class Camera:
    """
    A basic FPS camera.

    :param pos: Initial camera position
    :param phi: Horizontal angle (in Radians)
    :param theta: Vertical angle (in Radians)
    """
    def __init__(self, pos=[0, 0, 0], phi=0, theta=0):
        # Initial camera position.
        self.position = np.array(pos, dtype=np.float64)

        # Initial camera rotation.
        self.phi = phi
        self.theta = theta

        # Allocate the camera vectors.
        self.view = np.zeros(3, np.float64)
        self.right = np.zeros(3, np.float64)
        self.up = np.zeros(3, np.float64)

        # Update the 'view', 'right', and 'up' vectors according to 'phi' and
        # 'theta'.
        self.rotate(0, 0)

        # Sensitivity; only used in the convenience methods moveForward,
        # moveBackward, strafeLeft, strafeRight.
        self.translationSensitivity = 0.2

    def cameraMatrix(self):
        """
        Return the camera matrix.
        """
        # Translation matrix.
        trans = np.eye(4)
        trans[:3, 3] = -self.position

        # Rotation matrix to undo the camera rotation.
        rot = np.zeros((4, 4))
        rot[:3, :3] = np.vstack((self.right, self.up, self.view))
        rot[3, 3] = 1

        # Combine the matrices into one.
        return np.dot(rot, trans)

    def rotate(self, left, up):
        """
        Convenience method: rotate the camera.

        The ``left`` and ``up`` values specify the horizontal- and
        vertical rotation (in radians).
        """
        self.phi += left
        self.theta += up

        # Compute the viewing direction (z-axis in camera space).
        self.view[0] = np.sin(self.phi) * np.cos(self.theta)
        self.view[1] = np.sin(self.theta)
        self.view[2] = np.cos(self.theta) * np.cos(self.phi)

        # Compute the left-vector (x-axis in camera space).
        self.right[0] = -np.cos(self.phi)
        self.right[1] = 0
        self.right[2] = np.sin(self.phi)

        # Compute the up-vector (y-axis in camera space) from the previous two
        # vectors.
        self.up = -np.cross(self.view, self.right)

    def moveForward(self):
        """
        Convenience method: move camera forward a bit.
        """
        self.position += self.translationSensitivity * self.view

    def moveBackward(self):
        """
        Convenience method: move camera backward a bit.
        """
        self.position -= self.translationSensitivity * self.view

    def strafeLeft(self):
        """
        Convenience method: strafe a bit to the left.
        """
        self.position -= self.translationSensitivity * self.right

    def strafeRight(self):
        """
        Convenience method: strafe a bit to the right.
        """
        self.position += self.translationSensitivity * self.right


class ViewerWidget(QtOpenGL.QGLWidget):
    def __init__(self, addr_clerk: str,
                 port_clerk: int,
                 show_player: bool=True,
                 parent=None):
        super().__init__(parent)

        # Projectiles will disappear after ttl_projectile Seconds.
        self.ttl_projectile = 3.0
        self.projectiles = {}

        # If True then a dedicated player object will be created. Its position
        # will always coincide with that of the camera.
        self.show_player = show_player

        # Camera instance.
        self.camera = None

        # Collection of old and new state variables.
        self.oldSVs, self.newSVs = {}, {}

        # Address of Clerk.
        self.addr_clerk = addr_clerk
        self.port_clerk = port_clerk
        self.port_webapi = 8080

        # Place the window in the top left corner.
        self.setGeometry(0, 0, 640, 480)

        # Binary movement flags to indicate which keys are currently pressed.
        self.movement = {
            'forward': False,
            'backward': False,
            'left': False,
            'right': False}

        # Backup the current mouse position so that we can make it visible
        # again at the some position if the user chooses to use the mouse for
        # the desktop instead of the controlling the camera.
        self.lastMousePos = self.cursor().pos()

        # todo: find out how to keep the mouse inside the window.
        self.centerPos = self.width() // 2, self.height() // 2
        self.centerCursor()

        # If True, the mouse will control the camera instead of the cursor on
        # the desktop GUI.
        self.mouseGrab = False

        # Specify the field of view, aspect ratio, near- and far plane.
        self.fov = 45.0 * np.pi / 180.0
        self.aspect_ratio = 4 / 3
        self.near = 0.01
        self.far = 1000

        # Compute perspective matrix.
        self.matPerspective = perspective(self.fov, self.aspect_ratio,
                                          self.near, self.far)

        # The timer will re-start itself and trigger OpenGL updates.
        self.drawTimer = self.startTimer(500)

        # Frame counter and frame timer.
        self.frameCnt = 0
        self.lastFrameCnt = 0
        self.lastFrameTime = 0

        # Do no record a movie by default.
        self.recording = False

        # Instantiate ImageWriter...
        tmp = os.path.dirname(os.path.realpath(__file__))
        tmp = os.path.join(tmp, 'video')
        self.imgWriter = ImageWriter(tmp)

        # ... push it into a new thread...
        self.thread = QtCore.QThread()
        self.imgWriter.moveToThread(self.thread)

        # ... and start the thread.
        self.thread.start()

    def hasGeometryChanged(self, objID):
        """
        Return *True* if the geometry of ``objID`` has changed.
        """
        if objID not in self.oldSVs:
            return False

        cs_old = self.newSVs[objID]['rbs']['version']
        cs_new = self.oldSVs[objID]['rbs']['version']
        return (cs_old != cs_new)

    def upload2GPU(self, objID, fragID, frag):
        """
        Upload the ``frag`` geometry to the GPU.

        This method does not return anything but updates the GPU related
        instances variables instead.
        """
        # This is to mask a bug in WebServer: newly spawned objects can
        # become active before their geometry hits the DB.
        if len(frag.vert) == 0:
            return

        # Unpack the texture size.
        width, height = frag.width, frag.height

        # GPU needs float32 values for vertices and UV, and uint8 for RGB.
        buf_vert = np.array(frag.vert).astype(np.float32)
        buf_uv = np.array(frag.uv).astype(np.float32)
        buf_rgb = np.array(frag.rgb).astype(np.uint8)

        # Sanity checks.
        assert (len(buf_vert) % 9) == 0
        assert (len(buf_uv) % 2) == 0
        assert (len(buf_rgb) % 3) == 0
        if len(buf_uv) > 0:
            assert len(buf_vert) // 3 == len(buf_uv) // 2

        # Initialise the geometry arrays.
        if objID not in self.numVertices:
            self.numVertices[objID] = {}
            self.numVertices[objID] = {}
            self.vertex_array_object[objID] = {}
            self.textureBuffer[objID] = {}

        # Store the number of vertices.
        numVertices = len(buf_vert) // 3

        # Create a new VAO (Vertex Array Object) and bind it. All GPU
        # buffers created below can then be activated at once by binding
        # this VAO (see paintGL).
        VAO = gl.glGenVertexArrays(1)
        gl.glBindVertexArray(VAO)

        # Create two GPU buffers (no need to specify a size here).
        vertexBuffer, uvBuffer = gl.glGenBuffers(2)

        # Copy the vertex data to the first GPU buffer.
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vertexBuffer)
        gl.glBufferData(gl.GL_ARRAY_BUFFER, buf_vert, gl.GL_STATIC_DRAW)

        # Associate the vertex buffer with the Layout 0 variable in the
        # shader (see 'uv.vs') and specify its layout. Then enable
        # the buffer to ensure the GPU will draw it.
        gl.glVertexAttribPointer(0, 3, gl.GL_FLOAT, gl.GL_FALSE, 0, None)
        gl.glEnableVertexAttribArray(0)

        if (len(buf_rgb) == 0) or (len(buf_uv) == 0):
            if len(buf_rgb) == numVertices * 3:
                # No UV map, but vertex colors. Add the missing alpha values
                # but use the data as-is otherwise.
                buf_col = np.ones((numVertices, 4))
                tmp = np.reshape(buf_rgb, (len(buf_rgb) // 3, 3))
                buf_col[:, :3] = tmp / 255
                del tmp
            else:
                # Neither a UV map nor vertices are available: create random
                # colors.
                buf_col = np.random.rand(4 * numVertices)

            # Convert the vector to GPU compatible format.
            buf_col = buf_col.astype(np.float32)

            # Repeat with UV data. Each vertex has one associated (U,V)
            # pair to specify the position in the texture.
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, uvBuffer)
            gl.glBufferData(gl.GL_ARRAY_BUFFER, buf_col, gl.GL_STATIC_DRAW)

            # Color data is associated with Layout 1 (first parameter), has
            # four elements per vertex (second parameter), and each element
            # is a float32 (third parameter). The other three parameters
            # are of no interest here.
            gl.glVertexAttribPointer(
                1, 4, gl.GL_FLOAT, gl.GL_FALSE, 0, None)
            gl.glEnableVertexAttribArray(1)
            textureBuffer = None
        else:
            # Repeat with UV data. Each vertex has one associated (U,V)
            # pair to specify the position in the texture.
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, uvBuffer)
            gl.glBufferData(gl.GL_ARRAY_BUFFER, buf_uv, gl.GL_STATIC_DRAW)

            # UV data is associated with Layout 1 (first parameter), has
            # two elements per vertex (second parameter), and each element
            # is a float32 (third parameter). The other three parameters
            # are of no interest here.
            gl.glVertexAttribPointer(
                1, 2, gl.GL_FLOAT, gl.GL_FALSE, 0, None)
            gl.glEnableVertexAttribArray(1)

            # Create a new texture buffer on the GPU and bind it.
            textureBuffer = gl.glGenTextures(1)
            gl.glBindTexture(gl.GL_TEXTURE_2D, textureBuffer)

            # Upload texture to GPU (transpose the image first).
            buf_rgb = np.reshape(buf_rgb, (width, height, 3))
            buf_rgb = buf_rgb.transpose((1, 0, 2))
            gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, width, height,
                            0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, buf_rgb)

            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER,
                               gl.GL_NEAREST)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER,
                               gl.GL_NEAREST)

        # Assign the texture buffer.
        self.numVertices[objID][fragID] = numVertices
        self.textureBuffer[objID][fragID] = textureBuffer
        self.vertex_array_object[objID][fragID] = VAO

    def _removeObjectData(self, objID):
        vars = (self.numVertices, self.vertex_array_object,
                self.textureBuffer, self.newSVs)
        for v in vars:
            if objID in v:
                del v[objID]

    def loadGeometry(self):
        # Backup the latest state variables because we will download new ones
        # from Azrael shortly.
        self.oldSVs = self.newSVs

        # Get latest SV values.
        with util.Timeit('viewer.getV') as timeit:
            ret = self.client.getObjectStates(None)
            if not ret.ok:
                print('Could not retrieve the state variables -- Abort')
                self.close()

        # Remove all *None* entries (means Azrael does not know about them;
        # should be impossible but just to be sure).
        self.newSVs = {}
        for objID in ret.data:
            if ret.data[objID] is None:
                self._removeObjectData(objID)
            self.newSVs[objID] = ret.data[objID]

        # Remove all objects from the local scene for which Azrael did not
        # provid SV data.
        for objID in self.oldSVs:
            # Ignore the player object.
            if (objID in self.newSVs) or (objID == self.player_id):
                continue

            # Delete all fragment textures.
            for frag in self.textureBuffer[objID].values():
                gl.glDeleteTextures(frag)

            # Delete the corresponding entries in our meta variables.
#            gl.glDeleteBuffers(2, [1, 2])
            self._removeObjectData(objID)

        # The previous loop removed objects that do not exist anymore in
        # Azrael. This loop adds objects that now exist in Azrael but not yet
        # in our scene.
        for objID in list(self.newSVs.keys()):
            # Do not add anything if it is the player object itself.
            if objID == self.player_id:
                continue

            # Skip the object if we already have its model, unless the model
            # changed.
            if (objID in self.oldSVs) and not self.hasGeometryChanged(objID):
                continue

            # Download the latest geometry for this object; skip it if the
            # object does not exist (anymore).
            ret = self.client.getFragments([objID])
            if not ret.ok or ret.data is None or ret.data[objID] is None:
                self._removeObjectData(objID)
                continue

            # Fetch fragment model from Azrael and pass it to the GPU.
            base_url = 'http://{}:{}'.format(self.addr_clerk, self.port_webapi)
            for fragID, frag_data in ret.data[objID].items():
                if frag_data['fragtype'] == 'RAW':
                    url = base_url + frag_data['url_frag'] + '/model.json'
                    frag = requests.get(url).content
                    if len(frag) == 0:
                        self._removeObjectData(objID)
                        break
                    frag = json.loads(frag.decode('utf8'))
                    frag = getFragMetaRaw(
                        frag['vert'], frag['uv'], frag['rgb'],
                        frag['width'], frag['height']
                    )
                elif frag_data['fragtype'] == 'DAE':
                    url = base_url + frag_data['url_frag'] + '/' + fragID
                    frag = requests.get(url).content
                    if len(frag) == 0:
                        self._removeObjectData(objID)
                        break
                    with tempfile.TemporaryDirectory() as tmpdir:
                        open('model.dae', 'wb').write(frag)
                        mesh = model_import.loadModelAll('model.dae')

                    # The model may contain several sub-models. Each one has a
                    # set of vertices, UV- and texture maps. The following code
                    # simply flattens the three list-of-lists into three plain
                    # lists.
                    vert = np.array(mesh['vertices']).flatten()
                    uv = np.array(mesh['UV']).flatten()
                    rgb = np.array(mesh['RGB']).flatten()
                    width = height = None

                    # Ensure the data has the correct format.
                    vert = np.array(vert)
                    uv = np.array(uv, np.float32)
                    rgb = np.array(rgb, np.uint8)
                    frag = getFragMetaRaw(vert, uv, rgb, width, height)
                elif frag_data['fragtype'] == '3JS_V3':
                    # Model files in 3JS format. These are stored in a main
                    # JSON file plus (optional) texture files. Find the JSON
                    # file and log an error if there is not exactly one.
                    fnames = [_ for _ in frag_data['files']
                              if _.lower().endswith('.json')]
                    if len(fnames) != 1:
                        print('{} possible 3JS model candidates'.format(len(fnames)))
                        break

                    # Download the model.
                    url = base_url + frag_data['url_frag'] + '/' + fnames[0]
                    frag = requests.get(url).content
                    if len(frag) == 0:
                        self._removeObjectData(objID)
                        break

                    frag = json.loads(frag.decode('utf8'))
                    vert, uv, rgb = demolib.load3JSModel(frag)

                    # Download a texture file (if the model has one).
                    fnames = [_ for _ in frag_data['files']
                              if _.lower().endswith('.jpg')]
                    if len(fnames) > 0:
                        print('found texture')
                        url = base_url + frag_data['url_frag'] + '/' + fnames[0]
                        texture = requests.get(url).content
                        assert len(texture) > 0
                        with tempfile.TemporaryDirectory() as tmpdir:
                            open('texture.jpg', 'wb').write(texture)
                            img = PIL.Image.open(fnames[0])
                            width, height = img.size
                            img = np.array(img)
                            rgb = np.rollaxis(np.flipud(img), 1).flatten()
                            print('imported texture {}'.format(url))
                            del img
                        del url, texture
                    del fnames

                    frag = getFragMetaRaw(vert, uv, rgb, width, height)
                else:
                    continue
                self.upload2GPU(objID, fragID, frag)

        # Only draw visible triangles for this fragment.
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glDepthFunc(gl.GL_LESS)

    def defineProjectileTemplate(self):
        """
        Add template for all projectiles and return its name.

        Every projectile has the shape of the cube.
        """
        def _buildTemplate(name, imass, hlen, lf, rf):
            """
            Return a complete template for a cube object.
            This is a helper function only.
            """
            # Geometry and collision shape for platform.
            vert, cshapes = demolib.cubeGeometry(hlen, hlen, hlen)

            # Rigid body data for platforms (defines their physics, not appearance).
            body = demolib.getRigidBody(
                cshapes={'cs': cshapes},
                linFactor=lf,
                rotFactor=rf,
                imass=imass,
            )

            # Geometry for the platforms (defines their appearance, not physics).
            fm = demolib.getFragMetaRaw(
                vert=vert,
                uv=[],
                rgb=[],
                scale=1,
                pos=(0, 0, 0),
                rot=(0, 0, 0, 1)
            )
            frags = {'frag_1': fm}

            # Define the platform template and upload it to Azrael.
            return Template(name, body, frags, {}, {})

        # Add the player and projectile templates.
        ret = self.client.addTemplates([
            _buildTemplate('player', 0.2, 1.0, [0, 0, 0], [0, 0, 0]),
            _buildTemplate('projectile_A', 2, .2, [1, 1, 1], [1, 1, 1]),
            _buildTemplate('projectile_B', 0.2, 0.5, [1, 1, 1], [1, 1, 1]),
        ])

        # Check for errors.
        if not ret.ok:
            print('Viewer could not add new template: {}'.format(ret.msg))
            sys.exit(1)

        print('Created player and projectile templates')

    def removeProjectiles(self):
        """
        Remove all projectiles whose time to live has expired.
        """
        t0 = time.time()
        tmp = [k for (k, v) in self.projectiles.items() if t0 > v]
        [self.projectiles.pop(k) for k in tmp]
        if len(tmp) > 0:
            self.client.removeObjects(tmp)

    def initializeGL(self):
        """
        Create the graphics buffers and compile the shaders.
        """
        try:
            self._initializeGL()
        except Exception as err:
            print('OpenGL initialisation failed with the following error:')
            print('\n' + '-' * 79)
            print(err)
            import traceback
            traceback.print_exc(file=sys.stdout)
            print('-' * 79 + '\n')
            sys.exit(1)

    def _initializeGL(self):
        """
        Create the graphic buffers and compile the shaders.
        """
        # Connect to Azrael.
        self.client = pyazrael.AzraelClient(self.addr_clerk, self.port_clerk)

        print('Client connected')

        # Define a template for projectiles.
        self.defineProjectileTemplate()

        # Create the camera and place it (in the z-direction) between the
        # Cubes and Sphere generated  by the 'start' script, but out of their
        # way to the side.
        initPos = [0, 0, 10]
        self.camera = Camera(initPos, np.pi, 0)

        # Spawn the player object (it has the same shape as a projectile).
        if self.show_player:
            ret = self.client.spawn(
                [{'templateID': 'player', 'rbs': {'position': initPos}}]
            )
            if ret.ok:
                self.player_id = ret.data[0]
                print('Spawned player object <{}>'.format(self.player_id))
            else:
                print('Could not spawn player object (<{}>)'.format(ret.data))
                self.close()
        else:
            self.player_id = None

        # Initialise instance variables.
        self.numVertices = {}
        self.vertex_array_object = {}
        self.textureBuffer = {}
        self.shaderDict = {}

        # Background color.
        gl.glClearColor(0, 0, 0, 0)

        # Put the two possible shaders into dictionaries.
        fdir = os.path.dirname(os.path.abspath(__file__))
        vs = os.path.join(fdir, 'shaders/passthrough.vs')
        fs = os.path.join(fdir, 'shaders/passthrough.fs')
        self.shaderDict['passthrough'] = self.linkShaders(vs, fs)

        vs = os.path.join(fdir, 'shaders/uv.vs')
        fs = os.path.join(fdir, 'shaders/uv.fs')
        self.shaderDict['uv'] = self.linkShaders(vs, fs)

        # Load and compile all objects.
        self.loadGeometry()

    def buildModelMatrix(self, frag):
        # Build the scaling matrix for the overall object. The
        # lower-right entry must be 1.
        matScaleObj = frag['scale'] * np.eye(4)
        matScaleObj[3, 3] = 1

        # Convert the object Quaternion into a rotation matrix.
        q = frag['rotation']
        matRotObj = util.Quaternion(*q).toMatrix()

        # Build the model matrix for the overall object.
        matModelObj = np.eye(4)
        matModelObj[:3, 3] = frag['position']
        matModelObj = np.dot(matModelObj, np.dot(matRotObj, matScaleObj))
        return matModelObj

    def paintGL(self):
        try:
            with util.Timeit('viewer.paintGL') as timeit:
                self._paintGL()
        except Exception as err:
            print('Error in paintGL:')
            print('\n' + '-' * 79)
            print(err)
            import traceback
            traceback.print_exc(file=sys.stdout)
            print('-' * 79 + '\n')
            sys.exit(1)

    def _paintGL(self):
        """
        Paint the OpenGL scene.

        Qt calls this method whenever it needs re-painting (eg. window
        movement), or when the updateGL() method was called somewhere
        explicitly. In this script we use a timer to periodically trigger the
        updateGL() method for a smooth viewing experience.
        """
        # Update the position/rotation of the camera depending on the
        # currently pressed keys and mouse position.
        self.updateCamera()

        # Load the geometry of newly added objects.
        self.loadGeometry()

        # --------------------------------------------------------------------
        # Draw the scene.
        # --------------------------------------------------------------------
        # Clear the scene.
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

        # Compute the combined camera- and projection matrix.
        cameraMat = self.camera.cameraMatrix()
        matPerspCam = np.array(np.dot(self.matPerspective, cameraMat))

        # Convert it to the flat 32Bit format the GPU expects.
        matPerspCam = matPerspCam.astype(np.float32)
        matPerspCam = matPerspCam.flatten(order='F')

        with util.Timeit('viewer.loop') as timeit:
            for objID in self.newSVs:
                # Do not add anything if it is the player object itself.
                if objID == self.player_id:
                    continue

                # Compute the model matrix for the overall object.
                body = self.newSVs[objID]['rbs']
                tmp = {
                    'scale': body['scale'],
                    'position': body['position'],
                    'rotation': body['rotation']
                }
                matModelObj = self.buildModelMatrix(tmp)
                del body, tmp

                # Update each fragment in the scene based on the position,
                # rotation, and scale of the overall object.
                self._drawFragments(objID, matModelObj, matPerspCam)

        # --------------------------------------------------------------------
        # Display HUD for this frame.
        # --------------------------------------------------------------------
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glUseProgram(0)
        gl.glColor3f(0.5, 0.5, 0.5)
        hud = 'Frame {}'.format(self.frameCnt)
        if self.recording:
            hud += ', Recording On'
        self.renderText(0, 15, hud)

        # --------------------------------------------------------------------
        # Optional: save the frame buffer content to disk to record a video.
        # --------------------------------------------------------------------
        if self.recording:
            # Time how long it takes to grab the framebuffer.
            t0 = time.time()
            img = self.grabFrameBuffer()
            elapsed = float(1E3 * (time.time() - t0))

            # Send the image to a dedicated writer thread to avoid blocking
            # this thread more than necessary.
            self.imgWriter.sigUpdate.emit(elapsed, img)
            del t0, img, elapsed
        self.frameCnt += 1

    def _drawFragments(self, objID, matModelObj, matPerspCam):
        """
        Instruct the GPU to draw each fragment of ``objID``.

        The ``matModelObj`` and ``matPerspCam`` matrices will compute the world
        coordinates for the object. However, fragments are defined purely in
        object coordinate. This function will therefore scale, move, and rotate
        each fragment before it applies the world coordinate transformation.
        """
        frags = self.newSVs[objID]['frag']
        for fragID, frag in frags.items():
            # Convenience.
            textureHandle = self.textureBuffer[objID][fragID]
            VAO = self.vertex_array_object[objID][fragID]
            numVertices = self.numVertices[objID][fragID]

            # Activate the shader depending on whether or not we have a texture
            # for the current object.
            if textureHandle is None:
                shader = self.shaderDict['passthrough']
            else:
                shader = self.shaderDict['uv']

            # Compute the model matrix for the fragment.
            matModelFrag = self.buildModelMatrix(frag)

            # Combine the model matrix of the fragment and the overall object.
            matModelAll = np.dot(matModelObj, matModelFrag)

            # Convert it to the flat 32Bit format the GPU expects.
            matModelAll = matModelAll.astype(np.float32)
            matModelAll = matModelAll.flatten(order='F')

            # Activate the shader and obtain handles to Uniform variables.
            gl.glUseProgram(shader)
            tmp1 = 'projection_matrix'.encode('utf8')
            tmp2 = 'model_matrix'.encode('utf8')
            h_prjMat = gl.glGetUniformLocation(shader, tmp1)
            h_modMat = gl.glGetUniformLocation(shader, tmp2)
            del tmp1, tmp2

            # Activate the VAO and shader program.
            gl.glBindVertexArray(VAO)

            # Activate the texture (if we have one).
            if textureHandle is not None:
                gl.glBindTexture(gl.GL_TEXTURE_2D, textureHandle)
                gl.glActiveTexture(gl.GL_TEXTURE0)

            # Upload the model- and projection matrices to the GPU.
            gl.glUniformMatrix4fv(h_modMat, 1, gl.GL_FALSE, matModelAll)
            gl.glUniformMatrix4fv(h_prjMat, 1, gl.GL_FALSE, matPerspCam)

            # Draw all triangles.
            gl.glEnableVertexAttribArray(0)
            gl.glEnableVertexAttribArray(1)
            gl.glDrawArrays(gl.GL_TRIANGLES, 0, numVertices)
            if textureHandle is not None:
                gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

            # Unbind the entire VAO.
            gl.glDisableVertexAttribArray(1)
            gl.glDisableVertexAttribArray(0)
            gl.glBindVertexArray(0)

    def resizeGL(self, width, height):
        """
        Qt will call this if the viewport size changes.
        """
        gl.glViewport(0, 0, width, height)

    def compileShader(self, fname, shader_type):
        """
        Compile the ``shader_type`` stored in the file ``fname``.
        """
        shader = gl.glCreateShader(shader_type)
        gl.glShaderSource(shader, open(fname).read())
        gl.glCompileShader(shader)

        # Check for shader compilation errors.
        result = gl.glGetShaderiv(shader, gl.GL_COMPILE_STATUS)
        if result == 0:
            raise RuntimeError(gl.glGetShaderInfoLog(shader))
        return shader

    def linkShaders(self, vertex_shader, fragment_shader):
        """
        Compile- and link the vertex- and fragment shader.
        """
        # Compile the shaders.
        vs = self.compileShader(vertex_shader, gl.GL_VERTEX_SHADER)
        fs = self.compileShader(fragment_shader, gl.GL_FRAGMENT_SHADER)

        # Link shaders into a program.
        program = gl.glCreateProgram()
        gl.glAttachShader(program, vs)
        gl.glAttachShader(program, fs)
        gl.glLinkProgram(program)

        # Check for linking errors.
        result = gl.glGetProgramiv(program, gl.GL_LINK_STATUS)
        if result == 0:
            raise RuntimeError(gl.glGetProgramInfoLog(program))
        return program

    def updateCamera(self):
        """
        Translate and rotate the camera depending on the currently pressed keys
        and move position.
        """
        # Move the camera position depending on the currently pressed keys.
        if self.movement['forward']:
            self.camera.moveForward()
        if self.movement['backward']:
            self.camera.moveBackward()
        if self.movement['right']:
            self.camera.strafeRight()
        if self.movement['left']:
            self.camera.strafeLeft()

        pos = self.camera.position
        cs = CollShapeBox(1, 1, 1)
        cs = CollShapeMeta('box', (0, 0, 0), (0, 0, 0, 1), cs)
        attr = {'position': pos.tolist(), 'cshapes': {'player': cs}}
        if self.show_player:
            assert self.client.setRigidBodyData({self.player_id: attr}).ok
        del cs

        # Do not update the camera rotation if the mouse is not grabbed.
        if not self.mouseGrab:
            return

        # Get current cursor position.
        c = self.cursor()
        xpos, ypos = c.pos().x(), c.pos().y()

        # Convert mouse offset from default position to left/up rotation, then
        # reset the cursor to its default position.
        sensitivity = 0.003
        up = sensitivity * (self.centerPos[1] - ypos)
        left = sensitivity * (self.centerPos[0] - xpos)
        self.centerCursor()

        # Rotate the camera.
        self.camera.rotate(left, up)

    def centerCursor(self):
        """
        Place the cursor in the pre-defined center position.
        """
        c = self.cursor()
        center = QtCore.QPoint(*self.centerPos)
        c.setPos(center)
        c.setShape(QtCore.Qt.BlankCursor)
        self.setCursor(c)

    def keyPressEvent(self, key):
        """
        Qt will call this if a key was pressed.

        This method will simply set the corresponding movement flags, which
        will be used in the painGL method to actually update the camera
        position and rotation.
        """
        # Convert input to a string character. Qt will sometimes lump
        # characters together if they arrive quicker than the event loop can
        # call this event handler (eg. if you keep pressing 'e' the key.text()
        # function may return 'eee'). To ensure everything works as expected,
        # use cut off the excess characters.
        char = key.text()
        if len(char) > 1:
            char = char[0]
        if char == 'e':
            self.movement['forward'] = True
        elif char == 'd':
            self.movement['backward'] = True
        elif char == 'f':
            self.movement['right'] = True
        elif char == 's':
            self.movement['left'] = True
        elif key.key() == QtCore.Qt.Key_Return:
            self.mouseGrab = not self.mouseGrab
            c = self.cursor()
            if self.mouseGrab:
                self.lastMousePos = c.pos()
                self.centerCursor()
                c.setShape(QtCore.Qt.BlankCursor)
            else:
                c.setPos(self.lastMousePos)
                c.setShape(QtCore.Qt.ArrowCursor)
            self.setCursor(c)
            del c
        elif char == 'q':
            self.thread.quit()
            self.close()
        elif char == 'M':
            if self.recording:
                self.recording = False
            else:
                self.recording = True
                self.imgWriter.sigReset.emit()
        else:
            if len(key.text()) > 0:
                print('Unknown key <{}>'.format(key.text()))

    def keyReleaseEvent(self, key):
        """
        Triggered by Qt when a key is released.

        This method unsets the flag set by ``keyPressEvent``.
        """
        char = key.text()
        if char == 'e':
            self.movement['forward'] = False
        elif char == 'd':
            self.movement['backward'] = False
        elif char == 'f':
            self.movement['right'] = False
        elif char == 's':
            self.movement['left'] = False
        else:
            pass

    def mousePressEvent(self, event):
        button = event.button()

        # Name the projectile to associate it with this player.
        tag = {'parent': self.player_id, 'name': 'projectile', 'type': None}

        # Determine initial position and velocity of the new object.
        pos = self.camera.position + 3 * self.camera.view
        vel = self.camera.view

        if button == 1:
            # Faster but short lived projectile named 'A'.
            vel = 20 * vel
            tag['type'] = 'A'
            tname = 'projectile_A'
            ttl = 1 * self.ttl_projectile
        elif button == 2:
            # Slower but longer lived projectile named 'B'.
            vel = 5 * vel
            tag['type'] = 'B'
            tname = 'projectile_B'
            ttl = 5 * self.ttl_projectile
        else:
            print('Unknown button <{}>'.format(button))
            return

        # Spawn the projectile and check for errors.
        ret = self.client.spawn([{
            'templateID': tname,
            'rbs': {'position': pos.tolist(), 'velocityLin': vel.tolist()},
            'custom': json.dumps(tag),
        }])
        if not ret.ok:
            print('Could not spawn <{}>'.format(tname))

        # Record the time to live for the new projectile.
        t0 = time.time() + ttl
        self.projectiles.update({aid: t0 for aid in ret.data})

    def timerEvent(self, event):
        """
        Periodically call updateGL to process mouse/keyboard events and
        update the scene.
        """
        etime = time.time() - self.lastFrameTime
        if etime > 1:
            numFrames = self.frameCnt - self.lastFrameCnt
            util.logMetricQty('#FPS', int(numFrames / etime))
            self.lastFrameCnt = self.frameCnt
            self.lastFrameTime = time.time()

        self.killTimer(event.timerId())
        self.drawTimer = self.startTimer(20)
        self.updateGL()
        self.removeProjectiles()


def main():
    param = parseCommandLine()

    # Boiler plate for Qt application.
    app = QtGui.QApplication(['Viewer 3D'])
    widget = ViewerWidget(param.addr, param.port)
    widget.show()
    app.exec_()


if __name__ == '__main__':
    main()
