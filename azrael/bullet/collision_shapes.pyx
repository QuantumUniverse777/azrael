cimport cython
from collections import namedtuple
ChildElement = namedtuple('ChildElement', 'transform cshape')

cdef class CollisionShape:
    cdef btCollisionShape *ptr_CollisionShape

    def __cinit__(self):
        self.ptr_CollisionShape = NULL

    def __repr__(self):
        return 'Unknown Generic'

    def setLocalScaling(self, Vec3 scaling):
        self.ptr_CollisionShape.setLocalScaling(scaling.ptr_Vector3[0])

    def getLocalScaling(self):
        v = Vec3()
        v.ptr_Vector3[0] = self.ptr_CollisionShape.getLocalScaling()
        return v

    def calculateLocalInertia(self, double mass):
        inertia = Vec3(0, 0, 0)
        self.ptr_CollisionShape.calculateLocalInertia(
            btScalar(mass), inertia.ptr_Vector3[0])
        return inertia

    def getName(self):
        return self.ptr_CollisionShape.getName()


cdef class ConcaveShape(CollisionShape):
    cdef btConcaveShape *ptr_ConcaveShape

    def __cinit__(self):
        self.ptr_ConcaveShape = NULL

    def __repr__(self):
        return 'Unknown Concave'


cdef class StaticPlaneShape(ConcaveShape):
    cdef btStaticPlaneShape *ptr_StaticPlaneShape

    def __cinit__(self):
        self.ptr_StaticPlaneShape = NULL

    def __init__(self, Vec3 v, double plane_const):
        self.ptr_StaticPlaneShape = new btStaticPlaneShape(
                v.ptr_Vector3[0], btScalar(plane_const))

        # Assign the base pointers.
        self.ptr_ConcaveShape = <btConcaveShape*>self.ptr_StaticPlaneShape
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_StaticPlaneShape

    def __dealloc__(self):
        if self.ptr_StaticPlaneShape != NULL:
            del self.ptr_StaticPlaneShape

    def __repr__(self):
        s = ('Static Plane:\n'
             '  Normal: {:.2f}, {:.2f}, {:.2f}\n'
             '  Thickness: {:.2f}')
        cdef btVector3 v = self.ptr_StaticPlaneShape.getPlaneNormal()
        cdef double f = <double>self.ptr_StaticPlaneShape.getPlaneConstant()
        s = s.format(
            <double>v.x(),
            <double>v.y(),
            <double>v.z(),
            <double>f)
        return s


cdef class EmptyShape(ConcaveShape):
    cdef btEmptyShape *ptr_EmptyShape

    def __cinit__(self):
        self.ptr_EmptyShape = NULL

    def __init__(self):
        self.ptr_EmptyShape = new btEmptyShape()

        # Assign the base pointers.
        self.ptr_ConcaveShape = <btConcaveShape*>self.ptr_EmptyShape
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_EmptyShape

    def __dealloc__(self):
        if self.ptr_EmptyShape != NULL:
            del self.ptr_EmptyShape

    def __repr__(self):
        return 'Empty'


cdef class ConvexShape(CollisionShape):
    cdef btConvexShape *ptr_ConvexShape

    def __cinit__(self):
        self.ptr_ConvexShape = NULL

    def __repr__(self):
        return 'Unknown Convex'


cdef class ConvexInternalShape(ConvexShape):
    cdef btConvexInternalShape *ptr_ConvexInternalShape

    def __cinit__(self):
        self.ptr_ConvexInternalShape = NULL

    def __repr__(self):
        return 'Unknown ConvexInternal'


cdef class SphereShape(ConvexInternalShape):
    cdef btSphereShape *ptr_SphereShape

    def __cinit__(self):
        self.ptr_SphereShape = NULL

    def __init__(self, double radius):
        self.ptr_SphereShape = new btSphereShape(btScalar(radius))

        # Assign the base pointers.
        self.ptr_ConvexInternalShape = <btConvexInternalShape*>self.ptr_SphereShape
        self.ptr_ConvexShape = <btConvexShape*>self.ptr_SphereShape
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_SphereShape

    def __dealloc__(self):
        if self.ptr_SphereShape != NULL:
            del self.ptr_SphereShape

    def getRadius(self):
        return <double> self.ptr_SphereShape.getRadius()

    def __repr__(self):
        s = 'Sphere:\n  Radius: {:.2f}'
        s = s.format(<double>self.ptr_SphereShape.getRadius())
        return s


cdef class PolyhedralConvexShape(ConvexInternalShape):
    cdef btPolyhedralConvexShape *ptr_PolyhedralConvexShape

    def __cinit__(self):
        self.ptr_PolyhedralConvexShape = NULL

    def __repr__(self):
        return 'Unknown PolyhedralConvex'


cdef class BoxShape(PolyhedralConvexShape):
    cdef btBoxShape *ptr_BoxShape

    def __cinit__(self):
        self.ptr_BoxShape = NULL

    def __init__(self, Vec3 v):
        self.ptr_BoxShape = new btBoxShape(v.ptr_Vector3[0])

        # Assign the base pointers.
        self.ptr_PolyhedralConvexShape = <btPolyhedralConvexShape*>self.ptr_BoxShape
        self.ptr_ConvexInternalShape = <btConvexInternalShape*>self.ptr_BoxShape
        self.ptr_ConvexShape = <btConvexShape*>self.ptr_BoxShape
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_BoxShape

    def __dealloc__(self):
        if self.ptr_BoxShape != NULL:
            del self.ptr_BoxShape

    def __repr__(self):
        cdef btVector3 v = self.ptr_BoxShape.getHalfExtentsWithMargin()
        s = 'BoxShape:\n Half Widths: {:.2f}, {:.2f}, {:.2f}'
        s = s.format(<double>v.x(), <double>v.y(), <double>v.z())
        return s

    def getHalfExtentsWithMargin(self):
        v = Vec3(0, 0, 0)
        v.ptr_Vector3[0] = self.ptr_BoxShape.getHalfExtentsWithMargin()
        return v

    def getHalfExtentsWithoutMargin(self):
        v = Vec3(0, 0, 0)
        v.ptr_Vector3[0] = self.ptr_BoxShape.getHalfExtentsWithoutMargin()
        return v


cdef class CompoundShape(CollisionShape):
    cdef btCompoundShape *ptr_CompoundShape
    cdef list _list_cs

    def __cinit__(self):
        self.ptr_CompoundShape = NULL
        self._list_cs = []

    def __init__(self, bint enableDynamicAabbTree=True):
        self.ptr_CompoundShape = new btCompoundShape(enableDynamicAabbTree)

        # Assign the base pointers.
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_CompoundShape

    def __dealloc__(self):
        if self.ptr_CompoundShape != NULL:
            del self.ptr_CompoundShape

    def __iter__(self):
        # Return the iterator over all collision shapes.
        return (_.cshape for _ in self._list_cs)

    def __repr__(self):
        n = self.getNumChildShapes()
        if n == 0:
            return 'Compound (No children)'
        elif n == 1:
            return 'Compound (1 child)'
        else:
            return 'Compound ({} children)'.format(n)

    def addChildShape(self, Transform localTransform, CollisionShape shape):
        self._list_cs.append(ChildElement(localTransform, shape))
        self.ptr_CompoundShape.addChildShape(
            localTransform.ptr_Transform[0],
            shape.ptr_CollisionShape)

    def getChildShape(self, int index):
        if not (0 <= index < self.getNumChildShapes()):
            return None
        return self._list_cs[index].cshape

    def removeChildShape(self, CollisionShape shape):
        tmp = [_ for _ in self._list_cs if _.cshape != shape]
        if len(tmp) == self._list_cs:
            # `shape` was not in the list.
            return None
        else:
            self._list_cs = tmp
            self.ptr_CompoundShape.removeChildShape(shape.ptr_CollisionShape)

    def getNumChildShapes(self):
        if len(self._list_cs) != self.ptr_CompoundShape.getNumChildShapes():
            raise AssertionError(
                'Invalid #ChildShapes in CompoundShape')
        return self.ptr_CompoundShape.getNumChildShapes()

    def calculatePrincipalAxisTransform(self, masses):
        # There must be as many masses as there are child shapes.
        if len(masses) != self.ptr_CompoundShape.getNumChildShapes():
            raise AssertionError('Incorrect number of masses')

        # Instantiate a Vec3 and Transform class. These will be passed by
        # reference into 'calculatePrincipalAxisTransform'.
        inertia, principal = Vec3(), Transform()

        # Do not attempt to compute any inertia without bodies.
        if self.ptr_CompoundShape.getNumChildShapes() == 0:
            return inertia, principal

        # Convert the list of masses to an array of btScalars.
        cdef btScalar* ptr_masses = new btScalar(len(masses))
        for idx, mass in enumerate(masses):
            ptr_masses[idx] = btScalar(mass)

        self.ptr_CompoundShape.calculatePrincipalAxisTransform(
                ptr_masses,
                principal.ptr_Transform[0],
                inertia.ptr_Vector3[0]
        )

        # Return the Inertia and its principal axis.
        return inertia, principal

    def getChildTransform(self, int index):
        t = Transform()
        t.ptr_Transform[0] = self.ptr_CompoundShape.getChildTransform(index)
        return t

    def updateChildTransform(self, int idx, Transform t, bint recalculateAABB=True):
        self.ptr_CompoundShape.updateChildTransform(
            idx,
            t.ptr_Transform[0],
            recalculateAABB
        )
