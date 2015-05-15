from azBullet cimport *
from basic cimport *
from collision_shapes cimport *
from transform cimport *
from motion_state cimport *
from collision_object cimport *
from rigid_body cimport *

cdef extern from "btBulletDynamicsCommon.h":
    cdef cppclass btRigidBody:
        btRigidBody(
            btScalar mass,
            btMotionState *motionState,
            btCollisionShape *collisionShape,
            btVector3 &localInertia)

        # getMotionState
        btMotionState *getMotionState()
        void setMotionState(btMotionState*)

        # {get,set}Restitution
        void setRestitution(btScalar r)
        btScalar getRestitution()

        # CenterOfMassTransform.
        void setCenterOfMassTransform(const btTransform &xform)
        btTransform &getCenterOfMassTransform()

        # ------------------------------------------------------------
        void forceActivationState(int newState)

        # Mass- and inertia related.
        btScalar getInvMass()
        btVector3 &getInvInertiaDiagLocal()
        void setMassProps(btScalar mass, const btVector3 &inertia)

        # Force functions: clearForces, applyForce, applyTorque,
        #                  applyCentralForce, getTotalForce, getTotalTorque
        void clearForces()
        void applyForce(const btVector3& force, const btVector3& rel_pos)
        void applyTorque(const btVector3& torque)
        void applyCentralForce(const btVector3& force)
        const btVector3& getTotalForce()
        const btVector3& getTotalTorque()

        # setSleepingThresholds and get{Linear,Angular}SleepingThreshold
        void setSleepingThresholds(btScalar linear, btScalar angular)
        btScalar getLinearSleepingThreshold()
        btScalar getAngularSleepingThreshold()

        # {set,get}Friction
        void setFriction (btScalar frict)
        btScalar getFriction()

        # {set,get}Damping
        void setDamping(btScalar lin_damping, btScalar ang_damping)
        btScalar getLinearDamping()
        btScalar getAngularDamping()

        # {set,get}{Linear,Angular}Factor
        void setLinearFactor(const btVector3& linearFactor)
        void setAngularFactor(const btVector3& angFac)
        btVector3& getLinearFactor()
        btVector3& getAngularFactor()

        # {get,set}{Linear,Angular}Velocity
        void setAngularVelocity(const btVector3& ang_vel)
        void setLinearVelocity(const btVector3& lin_vel)
        btVector3& getLinearVelocity()
        btVector3& getAngularVelocity()