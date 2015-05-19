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
To compile and test:
  >> python3 setup.py cleanall
  >> python3 setup.py build_ext --inplace

Python version of Bullet's Hello World program:
  >> python3 hello.py
"""
from cpython.object cimport Py_EQ, Py_NE

from basic cimport *
from collision_shapes cimport *
from transform cimport *
from motion_state cimport *
from collision_object cimport *
from rigid_body cimport *
from typed_constraint cimport *

# Important: the order of the includes matter; make sure it is compatible with
#            the class hierarchy!
include 'basic.pyx'
include 'collision_shapes.pyx'
include 'transform.pyx'
include 'motion_state.pyx'
include 'collision_object.pyx'
include 'rigid_body.pyx'
include 'typed_constraint.pyx'


cdef class BulletBase:
    """
    Framework class that sets up a complete simulation environment.
    """
    cdef btDefaultCollisionConfiguration *collisionConfiguration
    cdef btCollisionDispatcher *dispatcher
    cdef btDbvtBroadphase *pairCache
    cdef btSequentialImpulseConstraintSolver *solver
    cdef btDiscreteDynamicsWorld *dynamicsWorld
    cdef list _list_constraints

    def __cinit__(self):
        self.collisionConfiguration = new btDefaultCollisionConfiguration()
        self.dispatcher = new btCollisionDispatcher(self.collisionConfiguration)
        self.pairCache = new btDbvtBroadphase()
        self.solver = new btSequentialImpulseConstraintSolver()
        self.dynamicsWorld = new btDiscreteDynamicsWorld(
            self.dispatcher,
            # Downcast to the base class.
            <btBroadphaseInterface*>self.pairCache,
            self.solver,
            self.collisionConfiguration)
        self._list_constraints = []

    def __dealloc__(self):
        del self.dynamicsWorld
        del self.solver
        del self.pairCache
        del self.dispatcher
        del self.collisionConfiguration

    def setGravity(self, double x, double y, double z):
        self.dynamicsWorld.setGravity(btVector3(x, y, z))

    def getGravity(self):
        cdef btVector3 *r
        r = new btVector3(0, 0, 0)
        r[0] = self.dynamicsWorld.getGravity()
        x = <double>(r[0].x())
        y = <double>(r[0].y())
        z = <double>(r[0].z())
        del r
        return (x, y, z)

    def addRigidBody(self, RigidBody body):
        self.dynamicsWorld.addRigidBody(body.ptr_RigidBody)

    def addConstraint(self, TypedConstraint constraint):
        # Return immediately if the constraint has already been added.
        if constraint in self._list_constraints:
            return

        # Add the constraint.
        self._list_constraints.append(constraint)
        self.dynamicsWorld.addConstraint(constraint.ptr_TypedConstraint, False)

    def getConstraint(self, int index):
        try:
            return self._list_constraints[index]
        except IndexError:
            return None

    def iterateConstraints(self):
        return (_ for _ in self._list_constraints)

    def removeConstraint(self, TypedConstraint constraint):
        tmp = [_ for _ in self._list_constraints if _ != constraint]
        if len(tmp) == self._list_constraints:
            # `shape` was not in the list.
            return None
        else:
            self._list_constraints = tmp
            self.dynamicsWorld.removeConstraint(constraint.ptr_TypedConstraint)

    def getNumConstraints(self):
        if len(self._list_constraints) != self.dynamicsWorld.getNumConstraints():
            raise AssertionError(
                'Invalid #Constraints in DynamicsWorld')
        return self.dynamicsWorld.getNumConstraints()

    def stepSimulation(self, double timeStep, int maxSubSteps):
        self.dynamicsWorld.stepSimulation(
            btScalar(timeStep), maxSubSteps, btScalar(1.0 / 60.0))

    def removeRigidBody(self, RigidBody body):
        self.dynamicsWorld.removeRigidBody(body.ptr_RigidBody)
