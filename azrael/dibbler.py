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

"""
Dibbler stored and provides all model files.

Dibbler itself is a stateless service to store and retrieve model files. For
that purpose it provides dedicated methods to store- and sanity check the
various model types supported in Azrael. Furthermore, it provides a simple
`getFile` method to fetch the latest version of any file, if it exists.

Internally, Dibbler uses Mongo's GridFS to actually store the files.

By design, Dibbler will be useful to Clerk instances to add/remove models, and
Clacks to serve them up via HTTP. Its stateless design makes it possible to
create as many instances as necessary.

.. note:: Dibbler sanity checks models but has hardly any safe guards for
          overwriting existing files or concurrent access, other than those
          provided by GridFS itself. This is deliberate, partially because
          GridFS makes this considerably harder than plain MongoDB, and mostly
          because the Clerks already take care of it with the meta data they
          store in MongoDB. After all, Dibbler is merely the storage engine for
          large files.
"""
import os
import json
import gridfs

import numpy as np
import azrael.config as config

from IPython import embed as ipshell
from azrael.types import typecheck, Template, RetVal
from azrael.types import FragDae, FragRaw, MetaFragment


@typecheck
def isGeometrySane(frag: FragRaw):
    """
    Return *True* if the geometry is consistent.

    :param Fragment frag: a geometry Fragment
    :return: Sucess
    :rtype: bool
    """
    # The number of vertices must be an integer multiple of 9 to
    # constitute a valid triangle mesh (every triangle has three
    # edges and every edge requires an (x, y, z) triplet to
    # describe its position).
    try:
        assert len(frag.vert) % 9 == 0
        assert len(frag.uv) % 2 == 0
        assert len(frag.rgb) % 3 == 0
    except AssertionError:
        return False
    return True


class Dibbler:
    """
    Stateless storage backend for Azrael's models.
    """
    def __init__(self):
        # Create a GridFS handle.
        db = config.getMongoClient()['AzraelGridDB']
        self.fs = gridfs.GridFS(db)

    def reset(self):
        """
        Flush all models.

        :return: Success
        """
        # Find all versions of all files and delete everything.
        for _ in self.fs.find():
            self.fs.delete(_._id)
        return RetVal(True, None, None)

    def getNumFiles(self):
        """
        Return the number of distinct files in GridFS.

        ..note:: There may be more files in Dibbler because old versions of the
                 same files are not deleted. However, the returned corresponds
                 to the number of files with distinct file names.

        :return: Number of files in storage.
        """
        return RetVal(True, None, len(self.fs.list()))

    @typecheck
    def saveModelDae(self, location: str, model: MetaFragment):
        """
        Save the Collada ``model`` to ``location``.

        This will create the necessary files under ``location`` to store all
        the attached information.

        The "directory" structure will contain the Collada file named after the
        model (without the .dae extension), plus any texture files. For
        instance:
          location/model_name/model_name
          location/model_name/pic1.png
          location/model_name/pic2.jpg
          location/model_name/blah.jpg

        .. note:: ``location`` will usually look like a path and file name (eg.
                  '/instances/1/') but as far as the storage is
                  concerned, it is merely a prefix string (hopefully) unique to
                  this ``model``.

        :param str location: location where to store the ``model``.
        :param MetaFragment model: the Collada model itself.
        :return: success
        """
        # Sanity checks.
        try:
            data = FragDae(*model.data)
            assert isinstance(data.dae, bytes)
            for v in data.rgb.values():
                assert isinstance(v, bytes)
        except KeyError:
            msg = 'Invalid data types for Collada fragments'
            return RetVal(False, msg, None)

        # Save the dae file to "location/model_name/model_name".
        self.fs.put(data.dae, filename=os.path.join(location, model.name))

        # Save the textures. These are stored as dictionaries with the texture
        # file name as key and the data as a binary stream, eg,
        # {'house.jpg': b'abc', 'tree.png': b'def', ...}
        for name, rgb in data.rgb.items():
            self.fs.put(rgb, filename=os.path.join(location, name))

        return RetVal(True, None, 1.0)

    @typecheck
    def saveModelRaw(self, location: str, model: MetaFragment):
        """
        Save the Raw ``model`` to ``location``.

        This will create the necessary files under ``location`` to store all
        the attached information.

        The "directory" structure will contain only a single entry:
          location/model_name/model.json

        :param str location: directory where to store ``model``.
        :param MetaFragment model: the Raw model itself.
        :return: success
        """
        # Sanity checks.
        try:
            data = FragRaw(*model.data)
            assert isinstance(data.vert, list)
            assert isinstance(data.uv, list)
            assert isinstance(data.rgb, list)
        except (AssertionError, TypeError):
            msg = 'Invalid data types for Raw fragments'
            return RetVal(False, msg, None)

        if not isGeometrySane(data):
            msg = 'Invalid geometry for template <{}>'
            return RetVal(False, msg.format(model.name), None)

        # Save the fragments as JSON data to eg "templates/mymodel/model.json".
        self.fs.put(json.dumps(data._asdict()).encode('utf8'),
                    filename=os.path.join(location, 'model.json'))

        # Determine the largest possible side length of the
        # AABB. To find it, just determine the largest spatial
        # extent in any axis direction. That is the side length of
        # the AABB cube. Then multiply it with sqrt(3) to ensure
        # that any rotation angle of the object is covered. The
        # slightly larger value of sqrt(3.1) adds some slack.
        aabb = 0
        if len(data.vert) > 0:
            len_x = max(data.vert[0::3]) - min(data.vert[0::3])
            len_y = max(data.vert[1::3]) - min(data.vert[1::3])
            len_z = max(data.vert[2::3]) - min(data.vert[2::3])
            tmp = np.sqrt(3.1) * max(len_x, len_y, len_z)
            aabb = np.amax((aabb, tmp))

        return RetVal(True, None, aabb)

    @typecheck
    def _deleteSubLocation(self, url: str):
        """
        Delete all files under ``url``.

        This function is the equivalent of 'rm -rf url/*'. It always succeeds
        and returns the number of deleted files.

        :param str url: location (eg. '/instances/blah/')
        :return: number of deleted files
       """
        query = {'filename': {'$regex': '^{}/.*'.format(url)}}
        cnt = 0
        for _ in self.fs.find(query):
            self.fs.delete(_._id)
            cnt += 1
        return RetVal(True, None, cnt)

    @typecheck
    def saveModel(self, location: str, fragments: (tuple, list),
                  update: bool=False):
        """
        Save the ``model`` to ``location`` and return the success status.

        This function is merely a wrapper around dedicated methods to save
        individual fragment (eg Collada or Raw). It will store all
        ``fragments`` under the same ``location`` prefix and create a
        `meta.json` file to list all fragments, their names, and types.

        If ``update`` is *True* then 'location/meta.json' must already exist.

        .. note:: The ``update`` flag does not guarnatee that meta.json still
                  exists when the files are written because another Dibbler
                  from another process may delete it at the same time. It is
                  the responsibility of the caller (usually Clerk) to ensure
                  this does not happen.

        For instance, if location='/foo' the the "directory" structure in the
        model databae will look like this:
           /foo/meta.json
           /foo/frag_name_1/...
           /foo/frag_name_2/...
           ...

        The "meta.json" file contains a dictionary with the fragment names
        (keys) and their types (values), eg. {'foo': 'raw', 'bar': 'dae'}.

        :param str location: the common location prefix used for all
                             ``fragments``.
        :param list fragments: list of ``MetaFragment`` instances.
        :param bool update: if *True* then the ``location`` prefix must already
                             exist.
        :return: success.
        """
        if update:
            query = {'filename': {'$regex': '^' + location + '/meta.json'}}
            ret = self.fs.find_one(query)
            if ret is None:
                return RetVal(False, 'Model does not exist', None)

        # Store all fragment models for this template.
        aabb = -1
        frag_names = {}
        for frag in fragments:
            # Fragment directory, eg .../instances/mymodel/frag1
            frag_dir = os.path.join(location, frag.name)

            # Delete the current fragments and save the new ones.
            if frag.type == 'raw':
                self._deleteSubLocation(frag_dir)
                ret = self.saveModelRaw(frag_dir, frag)
            elif frag.type == 'dae':
                self._deleteSubLocation(frag_dir)
                ret = self.saveModelDae(frag_dir, frag)
            elif frag.type == '_none_':
                # Dummy fragment that tells us to remove it.
                ret = RetVal(False, None, None)
            else:
                # Unknown model format.
                msg = 'Unknown type <{}>'.format(frag.type)
                ret = RetVal(False, msg, None)

            # Delete the fragment directory if something went wrong and proceed to
            # the next fragment.
            if not ret.ok:
                self._deleteSubLocation(frag_dir)
                continue

            # Update the 'meta.json': it contains a dictionary with all fragment
            # names and their model type, eg. {'foo': 'raw', 'bar': 'dae', ...}
            frag_names[frag.name] = frag.type
            self.fs.put(json.dumps({'fragments': frag_names}).encode('utf8'),
                        filename=os.path.join(location, 'meta.json'))

            # Find the largest AABB.
            aabb = float(np.amax((ret.data, aabb)))

        # Sanity check: if the AABB was negative then not a single fragment was
        # valid. This is an error.
        if aabb < 0:
            msg = 'Model contains no valid fragments'
            return RetVal(False, msg, None)
        return RetVal(True, None, aabb)

    @typecheck
    def getTemplateDir(self, template_name: str):
        """
        Return the location of ``template_name``.

        This is a convenience method only to avoid code duplication. All it
        does is prefix ``template_name`` with the ``config.url_templates``
        value.

        :param str template_name: name of template (eg. 'foo')
        :return: location string (eg /templates/foo/').
        """
        return os.path.join(config.url_templates, template_name)

    @typecheck
    def getInstanceDir(self, objID: str):
        """
        Return the location of the object with ``objID``.

        This is a convenience method only to avoid code duplication. All it
        does is prefix ``template_name`` with the ``config.url_instances``
        value.

        :param str objID: object ID (eg. 8)
        :return: location string (eg /instances/8/').
        """
        return os.path.join(config.url_instances, objID)

    @typecheck
    def getFile(self, location: str):
        """
        Return the latest version of ``location``.

        If ``location`` does not exist then return an error.

        :param str location: the location to retrieve (eg.
                             '/instances/8/meta.json').
        :return: content of ``location`` (or *None* if an error occurred).
        :rtype: bytes
        """
        try:
            ret = self.fs.get_last_version(location)
        except gridfs.errors.NoFile as err:
            return RetVal(False, repr(err), None)
        except gridfs.errors.GridFSError as err:
            # All other GridFS errors.
            return RetVal(False, None, None)

        if ret is None:
            return RetVal(False, 'File not found', None)
        else:
            return RetVal(True, None, ret.read())
    
    @typecheck
    def addTemplate(self, model: Template):
        """
        Add the ``model`` to the template database.

        :param Template model: the model (eg Collad or Raw) to store.
        :return: success
        """
        location = self.getTemplateDir(model.name)
        ret = self.saveModel(location, model.fragments)
        if not ret.ok:
            return ret
        else:
            return RetVal(True, None, {'aabb': ret.data, 'url': location})

    @typecheck
    def spawnTemplate(self, name: str, objID: str):
        """
        .. note:: It is the caller's responsibility to ensure that ``objID`` is
                  unique. Dibbler will happily overwrite existing data.

        :param str name: the name of the template to spawn.
        :param str objID: the object ID
        :return: #file copied.
        """
        try:
            # 'objID', albeit a string, must correspond a valid integer.
            int(objID)
        except (TypeError, ValueError):
            msg = 'Invalid parameters in spawn command'
            return RetVal(False, msg, None)

        # Copy the model from the template- to the instance directory.
        src = self.getTemplateDir(name)
        dst = self.getInstanceDir(objID)

        # Copy every fragment from the template location to the instance
        # location.
        cnt = 0
        query = {'filename': {'$regex': '^{}/.*'.format(src)}}
        for f in self.fs.find(query):
            # Modify the original file name from eg
            # '/templates/temp_name/*' to '/instances/objID/*'.
            name = f.filename.replace(src, dst)

            # Copy the last version of the file.
            src_data = self.fs.get_last_version(f.filename)
            self.fs.put(src_data, filename=name)

            # Increment the file counter.
            cnt += 1

        if cnt == 0:
            # Did not copy any files.
            msg = 'Could not find template <{}>'.format(name)
            return RetVal(False, msg, None)
        else:
            # Found at least one template file to copy.
            url = config.url_instances + '/{}'.format(objID)
            return RetVal(True, None, {'url': url})

    @typecheck
    def updateFragments(self, objID: str, frags: (tuple, list)):
        """
        Overwrite all ``frags`` for ``objID``.

        This function will overwrite (or add) all specified ``frags`` unless
        their type is *_none_*. If the type is *_none_* then this method will
        delete the respective fragment and update the `meta.json` file
        accordingly.

        :param str objID: the object for which to update the ``fragments``.
        :param list frags: list of new ``MetaFragment`` instances.
        :return: see :func:`saveModel`
        """
        try:
            for _ in frags:
                assert isinstance(_, MetaFragment)
            # 'objID', albeit a string, it must correspond to a valid integer.
            int(objID)
        except (TypeError, ValueError):
            msg = 'Invalid parameters in updateFragments command'
            return RetVal(False, msg, None)

        # Overwrite all fragments for the instance with with ``objID``.
        location = self.getInstanceDir(objID)
        return self.saveModel(location, frags, update=True)

    @typecheck
    def deleteTemplate(self, location: str):
        """
        Delete the all files under ``location``.

        This function always succeeds but returns the number of actually
        deleted files. 

        :param str location: template location
        :return: #files deleted.
        """
        location = self.getTemplateDir(location)
        return self._deleteSubLocation(location)

    @typecheck
    def deleteInstance(self, objID: str):
        """
        Delete the all files belonging to the instance with ``objID``.

        This function always succeeds but returns the number of actually
        deleted files. 

        :param str objID: ID of object delete.
        :return: #files deleted.
        """
        location = self.getInstanceDir(objID)
        return self._deleteSubLocation(location)