import sys
import time
import pytest
import IPython
import subprocess
import azrael.clerk
import azrael.clacks
import azrael.leonard
import azrael.database
import azrael.client
import azrael.vectorgrid
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

from azrael.test.test_clacks import killAzrael
from azrael.bullet.test_boost_bullet import isEqualBD

import numpy as np

ipshell = IPython.embed

# List all available engines. This simplifies the parameterisation of those
# tests that must pass for all engines.
allEngines = [
    azrael.leonard.LeonardBase,
    azrael.leonard.LeonardBullet,
    azrael.leonard.LeonardSweeping,
    azrael.leonard.LeonardDistributedZeroMQ]


def getLeonard(LeonardCls=azrael.leonard.LeonardBase):
    """
    Reset all databases and return a ``LeonardCls`` instance.

    This is a convenience function to reduce code duplication in test
    functions.

    :param cls LeonardCls: Leonard class to instantiate.
    """
    # Return a Leonard instance.
    leo = LeonardCls()
    leo.setup()
    return leo


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_setStateVariables_basic(clsLeonard):
    """
    Spawn an object, specify its State Variables explicitly, and verify the
    change propagated through Azrael.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard(clsLeonard)

    # Parameters and constants for this test.
    id_0 = 0
    id_1 = 1
    sv = bullet_data.BulletData()
    templateID = '_templateSphere'.encode('utf8')

    # State Vector.
    p = np.array([1, 2, 5])
    vl = np.array([8, 9, 10.5])
    vr = vl + 1
    data = bullet_data.BulletDataOverride(
        position=p, velocityLin=vl, velocityRot=vr)
    del p, vl, vr

    # Spawn a new object. It must have ID=1.
    assert physAPI.addCmdSpawn(id_1, sv, aabb=1.0).ok

    # Update the object's State Vector.
    assert physAPI.addCmdModifyStateVariable(id_1, data).ok

    # Step the simulation by 0 seconds. This will not change the simulation
    # state but pick up all the queued commands.
    leo.step(0, 10)

    # Verify that the attributes were correctly updated.
    ret = physAPI.getStateVariables([id_1])
    assert (ret.ok, len(ret.data)) == (True, 1)
    sv = ret.data[id_1]
    assert np.array_equal(sv.position, data.position)
    assert np.array_equal(sv.velocityLin, data.velocityLin)
    assert np.array_equal(sv.velocityRot, data.velocityRot)

    print('Test passed')


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_setStateVariables_advanced(clsLeonard):
    """
    Similar to test_setStateVariables_basic but modify the collision shape
    information as well, namely mass and the collision shape itself.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard(clsLeonard)

    # Parameters and constants for this test.
    cs_cube = [3, 1, 1, 1]
    cs_sphere = [3, 1, 1, 1]
    sv = bullet_data.BulletData(imass=2, scale=3, cshape=cs_sphere)
    templateID = '_templateSphere'.encode('utf8')

    # Spawn an object.
    objID = 1
    assert physAPI.addCmdSpawn(objID, sv, aabb=1.0).ok

    # Verify the SV data.
    leo.step(0, 10)
    ret = physAPI.getStateVariables([objID])
    assert ret.ok
    assert ret.data[objID].imass == 2
    assert ret.data[objID].scale == 3
    assert np.array_equal(ret.data[objID].cshape, cs_sphere)

    # Update the object's SV data.
    sv_new = bullet_data.BulletDataOverride(imass=4, scale=5, cshape=cs_cube)
    assert physAPI.addCmdModifyStateVariable(objID, sv_new).ok

    # Verify the SV data.
    leo.step(0, 10)
    ret = physAPI.getStateVariables([objID])
    assert (ret.ok, len(ret.data)) == (True, 1)
    sv = ret.data[objID]
    assert (sv.imass == 4) and (sv.scale == 5)
    assert np.array_equal(sv.cshape, cs_cube)

    print('Test passed')


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_move_single_object(clsLeonard):
    """
    Create a single object with non-zero initial speed and ensure Leonard moves
    it accordingly.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leonard = getLeonard(clsLeonard)

    # Constants and parameters for this test.
    id_0 = 0
    sv = bullet_data.BulletData()

    # Spawn an object.
    assert physAPI.addCmdSpawn(id_0, sv, aabb=1.0).ok

    # Advance the simulation by 1s and verify that nothing has moved.
    leonard.step(1.0, 60)
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert np.array_equal(ret.data[id_0].position, [0, 0, 0])

    # Give the object a velocity.
    sv = bullet_data.BulletDataOverride(velocityLin=np.array([1, 0, 0]))
    assert physAPI.addCmdModifyStateVariable(id_0, sv).ok

    # Advance the simulation by another second and verify the objects have
    # moved accordingly.
    leonard.step(1.0, 60)
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert 0.9 <= ret.data[id_0].position[0] < 1.1
    assert ret.data[id_0].position[1] == ret.data[id_0].position[2] == 0

    print('Test passed')


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_move_two_objects_no_collision(clsLeonard):
    """
    Same as previous test but with two objects.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leonard = getLeonard(clsLeonard)

    # Constants and parameters for this test.
    id_0, id_1 = 0, 1
    sv_0 = bullet_data.BulletData(position=[0, 0, 0], velocityLin=[1, 0, 0])
    sv_1 = bullet_data.BulletData(position=[0, 10, 0], velocityLin=[0, -1, 0])

    # Create two objects.
    assert physAPI.addCmdSpawn(id_0, sv_0, aabb=1).ok
    assert physAPI.addCmdSpawn(id_1, sv_1, aabb=1).ok

    # Advance the simulation by 1s and query the states of both objects.
    leonard.step(1.0, 60)
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    pos_0 = ret.data[id_0].position
    ret = physAPI.getStateVariables([id_1])
    assert ret.ok
    pos_1 = ret.data[id_1].position

    # Verify that the objects have moved according to their initial velocity.
    assert pos_0[1] == pos_0[2] == 0
    assert pos_1[0] == pos_1[2] == 0
    assert 0.9 <= pos_0[0] <= 1.1
    assert 8.9 <= pos_1[1] <= 9.1

    killAzrael()
    print('Test passed')


def test_worker_respawn():
    """
    Ensure the objects move correctly even though the Workers will restart
    themselves after every step.

    The test code is similar to ``test_move_two_objects_no_collision``.
    """
    killAzrael()

    # Instantiate Leonard.
    leonard = azrael.leonard.LeonardDistributedZeroMQ()
    leonard.workerStepsUntilQuit = (1, 10)
    leonard.setup()

    # Constants and parameters for this test.
    id_0, id_1 = 0, 1
    cshape = [3, 1, 1, 1]
    sv_0 = bullet_data.BulletData(
        position=[0, 0, 0], velocityLin=[1, 0, 0], cshape=cshape)
    sv_1 = bullet_data.BulletData(
        position=[0, 10, 0], velocityLin=[0, -1, 0], cshape=cshape)

    # Create two objects.
    assert physAPI.addCmdSpawn(id_0, sv_0, aabb=1).ok
    assert physAPI.addCmdSpawn(id_1, sv_1, aabb=1).ok

    # Advance the simulation by 1s, but use many small time steps. This ensures
    # that the Workers will restart themselves frequently.
    for ii in range(60):
        leonard.step(1.0 / 60, 1)

    # Query the states of both objects.
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    pos_0 = ret.data[id_0].position
    ret = physAPI.getStateVariables([id_1])
    assert ret.ok
    pos_1 = ret.data[id_1].position

    # Verify that the objects have moved according to their initial velocity.
    assert pos_0[1] == pos_0[2] == 0
    assert pos_1[0] == pos_1[2] == 0
    assert 0.9 <= pos_0[0] <= 1.1
    assert 8.9 <= pos_1[1] <= 9.1

    # Clean up.
    killAzrael()
    print('Test passed')


def test_sweeping_2objects():
    """
    Ensure the Sweeping algorithm finds the correct sets.

    The algorithm takes a list of dictionarys and returns a list of lists.

    The input dictionary each contains the AABB coordinates. The output list
    contains the set of overlapping AABBs.
    """
    killAzrael()

    # Convenience variables.
    sweeping = azrael.leonard.sweeping
    labels = np.arange(2)

    # Two orthogonal objects.
    aabbs = [{'x': [4, 5], 'y': [3.5, 4], 'z': [5, 6.5]},
             {'x': [1, 2], 'y': [3.5, 4], 'z': [5, 6.5]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([1]), set([0])])

    # Repeat the test but use a different set of labels.
    res = sweeping(aabbs, np.array([3, 10], np.int64), 'x').data
    assert sorted(res) == sorted([set([10]), set([3])])

    # One object inside the other.
    aabbs = [{'x': [2, 4], 'y': [3.5, 4], 'z': [5, 6.5]},
             {'x': [1, 5], 'y': [3.5, 4], 'z': [5, 6.5]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([1, 0])])

    # Partially overlapping to the right of the first object.
    aabbs = [{'x': [1, 5], 'y': [3.5, 4], 'z': [5, 6.5]},
             {'x': [2, 4], 'y': [3.5, 4], 'z': [5, 6.5]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([1, 0])])

    # Partially overlapping to the left of the first object.
    aabbs = [{'x': [1, 5], 'y': [3.5, 4], 'z': [5, 6.5]},
             {'x': [2, 4], 'y': [3.5, 4], 'z': [5, 6.5]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([1, 0])])

    # Test Sweeping in the 'y' and 'z' dimension as well.
    aabbs = [{'x': [1, 5], 'y': [1, 5], 'z': [1, 5]},
             {'x': [2, 4], 'y': [2, 4], 'z': [2, 4]}]
    assert sweeping(aabbs, labels, 'x') == sweeping(aabbs, labels, 'y')
    assert sweeping(aabbs, labels, 'x') == sweeping(aabbs, labels, 'z')

    # Pass no object to the Sweeping algorithm.
    assert sweeping([], np.array([], np.int64), 'x').data == []

    # Pass only a single object to the Sweeping algorithm.
    aabbs = [{'x': [1, 5], 'y': [3.5, 4], 'z': [5, 6.5]}]
    res = sweeping(aabbs, np.array([0], np.int64), 'x').data
    assert sorted(res) == sorted([set([0])])

    print('Test passed')


def test_sweeping_3objects():
    """
    Same as test_sweeping_2objects but with three objects.
    """
    killAzrael()

    # Convenience variable.
    sweeping = azrael.leonard.sweeping
    labels = np.arange(3)

    # Three non-overlapping objects.
    aabbs = [{'x': [1, 2]}, {'x': [3, 4]}, {'x': [5, 6]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([0]), set([1]), set([2])])

    # First and second overlap.
    aabbs = [{'x': [1, 2]}, {'x': [1.5, 4]}, {'x': [5, 6]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([0, 1]), set([2])])

    # Repeat test with different labels.
    res = sweeping(aabbs, np.array([2, 4, 10], np.int64), 'x').data
    assert sorted(res) == sorted([set([2, 4]), set([10])])

    # First overlaps with second, second overlaps with third, but third does
    # not overlap with first. The algorithm must nevertheless return all three
    # in a single set.
    aabbs = [{'x': [1, 2]}, {'x': [1.5, 4]}, {'x': [3, 6]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([0, 1, 2])])

    # First and third overlap.
    aabbs = [{'x': [1, 2]}, {'x': [10, 11]}, {'x': [0, 1.5]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([0, 2]), set([1])])

    print('Test passed')


@pytest.mark.parametrize('dim', [0, 1, 2])
def test_computeCollisionSetsAABB(dim):
    """
    Create a sequence of 10 test objects. Their position only differs in the
    ``dim`` dimension.

    Then use subsets of these 10 objects to test basic collision detection.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard(azrael.leonard.LeonardBase)

    # Create several objects for this test.
    all_id = list(range(10))

    if dim == 0:
        SVs = [bullet_data.BulletData(position=[_, 0, 0]) for _ in range(10)]
    elif dim == 1:
        SVs = [bullet_data.BulletData(position=[0, _, 0]) for _ in range(10)]
    elif dim == 2:
        SVs = [bullet_data.BulletData(position=[0, 0, _]) for _ in range(10)]
    else:
        print('Invalid dimension for this test')
        assert False

    # Add all objects to the SV DB.
    for objID, sv in zip(all_id, SVs):
        assert physAPI.addCmdSpawn(objID, sv, aabb=1.0).ok
    del SVs

    # Retrieve all SVs as Leonard does.
    leo.step(0, 60)
    assert len(all_id) == len(leo.allObjects)

    def ccsWrapper(test_objIDs, expected_objIDs):
        """
        Assert that all ``test_objIDs`` resulted in the ``expected_objIDs``.

        This is merely a convenience wrapper to facilitate readable tests.

        This wrapper converts the human readable entries in ``IDs_hr``  into
        the internally used binary format. It then passes this new list, along
        with the corresponding SVs, to the collision detection algorithm.
        Finally, it converts the returned list of object sets back into human
        readable list of object sets and compares them for equality.
        """
        # Compile the set of SVs for curIDs.
        SVs = {_: leo.allObjects[_] for _ in test_objIDs}
        AABBs = {_: leo.allAABBs[_] for _ in test_objIDs}

        # Determine the list of potential collision sets.
        ret = azrael.leonard.computeCollisionSetsAABB(SVs, AABBs)
        assert ret.ok

        # Convert the reference data to a sorted list of sets.
        expected_objIDs = sorted([set(_) for _ in expected_objIDs])
        res = sorted([set(_) for _ in ret.data])

        # Return the equality of the two list of lists.
        assert expected_objIDs == res

    # Two non-overlapping objects.
    ccsWrapper([0, 9], [[0], [9]])

    # Two overlapping objects.
    ccsWrapper([0, 1], [[0, 1]])

    # Three sets.
    ccsWrapper([0, 1, 5, 8, 9], [[0, 1], [5], [8, 9]])

    # Same test, but objects are passed in a different sequence. This must not
    # alter the test outcome.
    ccsWrapper([0, 5, 1, 9, 8], [[0, 1], [5], [8, 9]])

    # All objects must form one connected set.
    ccsWrapper(list(range(10)), [list(range(10))])

    print('Test passed')


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_force_grid(clsLeonard):
    """
    Create a force grid and ensure Leonard applies its values to the center of
    the mass.
    """
    killAzrael()

    # Convenience.
    vg = azrael.vectorgrid

    # Reset the SV database and instantiate a Leonard.
    leonard = getLeonard(clsLeonard)

    # Constants and parameters for this test.
    id_0 = 0
    sv = bullet_data.BulletData()

    # Spawn one object.
    assert physAPI.addCmdSpawn(id_0, sv, aabb=1).ok

    # Advance the simulation by 1s and verify that nothing has moved.
    leonard.step(1.0, 60)
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert np.array_equal(ret.data[id_0].position, [0, 0, 0])

    # Define a force grid.
    assert vg.defineGrid(name='force', elDim=3, granularity=1).ok

    # Specify a non-zero value somewhere away from the object. This means the
    # object must still not move.
    pos = np.array([1, 2, 3], np.float64)
    value = np.ones(3, np.float64)
    assert vg.setValue('force', pos, value).ok

    # Step the simulation and verify the object remained where it was.
    leonard.step(1.0, 60)
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert np.array_equal(ret.data[id_0].position, [0, 0, 0])

    # Specify a grid value of 1 Newton in x-direction.
    pos = np.array([0, 0, 0], np.float64)
    value = np.array([1, 0, 0], np.float64)
    assert vg.setValue('force', pos, value).ok

    # Step the simulation and verify the object moved accordingly.
    leonard.step(1.0, 60)

    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert 0.4 <= ret.data[id_0].position[0] < 0.6
    assert ret.data[id_0].position[1] == ret.data[id_0].position[2] == 0

    # Cleanup.
    killAzrael()
    print('Test passed')


def test_create_work_package_without_objects():
    """
    Create, fetch, update, and count Bullet work packages.

    This test does not insert any objects into the simulation. It only tests
    the general functionality to add, retrieve, and update work packages.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard and Worker.
    leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

    # Constants.
    id_1, id_2 = 1, 2
    dt, maxsteps = 2, 3

    # Invalid call: list of IDs must not be empty.
    assert not leo.createWorkPackage([], dt, maxsteps).ok

    # Invalid call: Leonard has not object with ID 10.
    assert not leo.createWorkPackage([10], dt, maxsteps).ok

    # Test data.
    data_0 = bullet_data.BulletData(imass=1)

    # Add two new objects to Leonard.
    assert physAPI.addCmdSpawn(id_1, data_0, aabb=1).ok
    assert physAPI.addCmdSpawn(id_2, data_0, aabb=1).ok
    leo.processCommandsAndSync()

    # Create a work package for two object IDs. The WPID must be 1.
    ret = leo.createWorkPackage([id_1], dt, maxsteps)
    ret_wpid, ret_wpdata = ret.data['wpid'], ret.data['wpdata']
    assert (ret.ok, ret_wpid, len(ret_wpdata)) == (True, 0, 1)

    # Create a second WP. This one must have WPID=2 and contain two objects.
    ret = leo.createWorkPackage([id_1, id_2], dt, maxsteps)
    ret_wpid, ret_wpdata = ret.data['wpid'], ret.data['wpdata']
    assert (ret.ok, ret_wpid, len(ret_wpdata)) == (True, 1, 2)

    # Cleanup.
    killAzrael()
    print('Test passed')


def test_create_work_package_with_objects():
    """
    Create, fetch, and update Bullet work packages.

    Similar to test_create_work_package_without_objects but now the there are
    actual objects in the simulation.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

    # Convenience.
    data_1 = bullet_data.BulletData(imass=1)
    data_2 = bullet_data.BulletData(imass=2)
    data_3 = bullet_data.BulletData(imass=3)
    wpid = 1
    id_1, id_2 = 1, 2
    WPData = azrael.leonard.WPData
    WPMeta = azrael.leonard.WPMeta

    # Spawn new objects.
    assert physAPI.addCmdSpawn(id_1, data_1, aabb=1)
    assert physAPI.addCmdSpawn(id_2, data_2, aabb=1)
    leo.processCommandsAndSync()

    # Add ID1 and ID2 to the WP. The WPID must be 1.
    ret = leo.createWorkPackage([id_1, id_2], dt=3, maxsteps=4)

    # Check the WP content.
    data = [WPData(*_) for _ in ret.data['wpdata']]
    meta = WPMeta(*ret.data['wpmeta'])
    assert (meta.dt, meta.maxsteps) == (3, 4)
    assert (ret.ok, len(data)) == (True, 2)
    assert (data[0].id, data[1].id) == (id_1, id_2)
    assert isEqualBD(data[0].sv, data_1)
    assert isEqualBD(data[1].sv, data_2)
    assert np.array_equal(data[0].central_force, [0, 0, 0])
    assert np.array_equal(data[1].central_force, [0, 0, 0])

    # Create a new State Vector to replace the old one.
    data_4 = bullet_data.BulletData(imass=4)
    z = [0, 0, 0]
    newWP = [WPData(id_1, data_4, z, z)]
    del z

    # Check the State Vector value in the current Leonard cache.
    assert isEqualBD(leo.allObjects[id_1], data_1)

    # Update the State Vector in the Leonard cache and verify the new values.
    leo.updateLocalCacheFromWP(newWP)
    assert isEqualBD(leo.allObjects[id_1], data_4)

    # Cleanup.
    killAzrael()
    print('Test passed')


if __name__ == '__main__':
    test_create_work_package_with_objects()
    test_create_work_package_without_objects()

    test_worker_respawn()
    test_sweeping_2objects()
    test_sweeping_3objects()
    test_computeCollisionSetsAABB(0)

    for _engine in allEngines:
        print('\nEngine: {}'.format(_engine))
        test_force_grid(_engine)
        test_setStateVariables_advanced(_engine)
        test_setStateVariables_basic(_engine)
        test_move_single_object(_engine)
        test_move_two_objects_no_collision(_engine)
