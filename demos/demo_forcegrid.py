#!/usr/bin/python3

# Copyright 2014, Oliver Nagy <olitheolix@gmail.com>
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
Demonstrate the interaction of a force grid with objects.

To this end, this script will spawn a few cubes and a dedicated process to
periodically modify the force field in a wave-like fashion. The force
is the sole source of forces acting on the cubes and Leonard will thus, in
effect, simulate cubes "riding" the wave.
"""

# Add the viewer directory to the Python path.
import os
import sys
import time
import pymongo
import IPython
import logging
import argparse
import subprocess
import demo_default
import multiprocessing
import demo_default as demolib

import numpy as np
import matplotlib.pyplot as plt

# Import the necessary Azrael modules.
p = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(p, 'viewer'))
import model_import
import azrael.clerk
import azrael.clacks
import azrael.client
import azrael.util as util
import azrael.parts as parts
import azrael.config as config
import azrael.leonard as leonard
import azrael.database as database
import azrael.vectorgrid as vectorgrid
import azrael.physics_interface as physAPI
del p

# Convenience.
ipshell = IPython.embed
BulletDataOverride = physAPI.BulletDataOverride


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
    padd('--port', metavar='port', type=int, default=8080,
         help='Port number')
    padd('--cubes', metavar='X,Y,Z', type=str, default='1,1,1',
         help='Number of cubes in each dimension')
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
    try:
        cubes = [int(_) for _ in param.cubes.split(',')]
        assert len(cubes) == 3
        assert min(cubes) >= 0
        assert sum(cubes) >= 0
        param.cubes = cubes
    except (TypeError, ValueError, AssertionError):
        print('The <cubes> argument is invalid')
        sys.exit(1)

    return param


class UpdateGrid(multiprocessing.Process):
    """
    Update the force grid throughout the simulation.
    """
    def __init__(self, period_circ=1, period_lin=1):
        """
        Update the force grid values every ``period`` seconds.
        """
        super().__init__()
        self.period_lin = period_lin
        self.period_circ = period_circ

    def run(self):
        """
        Alternate the vector grid between 2 states.

        The first state is a rotational grid to make the cubes form a
        vortex. The second grid type simpy pulls all cubes towards the center.
        """
        # Convenience.
        vg = vectorgrid

        # Specify the spatial extend of the grid. Note that eg Nx=3 means the
        # grid extends from [-3, 3] in x-direction.
        Nx, Ny, Nz = 20, 20, 3

        # Lower left corner of the grid in space.
        ofs = np.array([-Nx, -Ny, 10 - Nz], np.float64)

        # Compute a counter clockwise oriented vector grid and another one the
        # always points to the center. Both calculations ignore the
        # z-dimension.
        force_rot = np.zeros((2 * Nx + 1, 2 * Ny + 1, 2 * Nz + 1, 3))
        force_lin = np.zeros_like(force_rot)
        for x in range(-Nx, Nx + 1):
            for y in range(-Ny, Ny + 1):
                # Magnitude and phase.
                r, phi = np.sqrt(x ** 2 + y ** 2), np.arctan2(y, x)

                # Normalise the vectors to ensure the velocity does not depend
                # on the distance from the origin.
                v = np.zeros(3, np.float64)
                if r > 1E-5:
                    v[0] = -np.sin(phi)
                    v[1] = np.cos(phi)

                # Assign the value.
                force_rot[x + Nx, y + Ny, :] = v

                # Points towards the center.
                v = -np.array([x, y, 0], np.float64)
                force_lin[x + Nx, y + Ny, :] = 0.1 * v

        while True:
            # Activate the circular grid.
            ret = vg.setRegion('force', ofs, 0.1 * force_rot)
            print('Circular force')
            if not ret.ok:
                print('Could not set force grid values')
            time.sleep(self.period_circ)

            # Activate the linear grid.
            ret = vg.setRegion('force', ofs, 0.1 * force_lin)
            print('Linear force')
            if not ret.ok:
                print('Could not set force grid values')
            time.sleep(self.period_lin)


def main():
    # Parse the command line.
    param = parseCommandLine()

    # Start the Azrael processes.
    with util.Timeit('Startup Time', True):
        subprocess.call(['pkill', 'killme'])
        procs = demolib.startAzrael(param)
    print('Azrael now live')

    # Start the process that periodically changes the force field. Add the
    # process handle to the list of processes.
    ug = UpdateGrid(period_circ=param.circular, period_lin=param.linear)
    ug.start()
    procs.insert(0, ug)

    # Start the Qt Viewer.
    demolib.launchQtViewer(param)

    # Shutdown Azrael.
    demolib.stopAzrael(procs)

    print('Clean shutdown')


if __name__ == '__main__':
    main()