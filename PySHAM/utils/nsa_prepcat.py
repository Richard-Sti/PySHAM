import os
from mpi4py import MPI

import numpy as np

import pymangle
from astropy.io import fits
from astropy.cosmology import FlatLambdaCDM

comm = MPI.COMM_WORLD
rank = comm.Get_rank()  # Labels the individual processes/cores
size = comm.Get_size()  # Total number of processes/cores

path = "/mnt/zfsusers/rstiskalek/pysham/data/nsa_v1.fits"
catalog = fits.open(path)[1].data

# Unpack the catalog
RA, DEC, Z = [catalog[p] for p in ('RA', 'DEC', 'ZDIST')]
# Take only objects within some sky location
IDS1 = np.where(np.logical_and(DEC > -10, DEC < 66))[0]
IDS2 = np.where(np.logical_and(RA > 100, RA < 260))[0]
IDS3 = np.where(np.logical_and(Z > 0.01, Z < 0.25))[0]
IDS = np.intersect1d(np.intersect1d(IDS1, IDS2), IDS3)

RA, DEC, Z = [p[IDS] for p in (RA, DEC, Z)]

MS_ELPETRO = catalog['ELPETRO_MASS'][IDS]
Mr_ELPETRO, Kcorr_ELPETRO = [(catalog[p][:, 4])[IDS]
                             for p in ('ELPETRO_ABSMAG', 'ELPETRO_KCORRECT')]

MS_SERSIC = catalog['SERSIC_MASS'][IDS]
Mr_SERSIC, Kcorr_SERSIC = [(catalog[p][:, 4])[IDS]
                           for p in ('SERSIC_ABSMAG', 'SERSIC_KCORRECT')]
# Get the polygons
path = "/mnt/zfsusers/rstiskalek/pysham/data/tmp_lss_geometry.ply"
m = pymangle.Mangle(path)
# Split job between procs
Ngal = RA.size
N_per_proc = int(np.floor(Ngal/size))
out_file = "outB_{}.dat".format(rank)
# Make sure last proc does the rest of the gals
if rank != size - 1:
    start = rank*N_per_proc
    end = (rank+1) * N_per_proc
    output = m.contains(RA[start:end], DEC[start:end])
else:
    start = rank * N_per_proc
    output = m.contains(RA[start:], DEC[start:])
np.savetxt(out_file, output)

# This causes threads to wait until they've all finished
buff = np.zeros(1)
if rank == 0:
    for i in range(1, size):
        comm.Recv(buff, source=i)
else:
    comm.Send(buff, dest=0)
# At end, a single thread does things like concatenate the files
if rank == 0:
    string = 'cat `find ./ -name "outB_*" | sort -V` > outB.dat'
    os.system(string)
    string = 'rm outB_*.dat'
    os.system(string)

    in_polygon = np.loadtxt("outB.dat")
    print("Shape of pol is ", in_polygon.shape, RA.shape)
    os.system("rm outB.dat")
    # Calculate apparent magnitude and comoving distance
    cosmo = FlatLambdaCDM(H0=100, Om0=0.295)
    cdist = cosmo.comoving_distance(Z).value  # this returns Mpc

    apMr_ELPETRO = Mr_ELPETRO + 25 + 5*np.log10((1 + Z)*cdist) + Kcorr_ELPETRO
    apMr_SERSIC = Mr_SERSIC + 25 + 5*np.log10((1 + Z)*cdist) + Kcorr_SERSIC

    Nmock = RA.size
    labels = ('RA', 'DEC', 'Z', 'dist',
              'ELPETRO_Mr', 'ELPETRO_MS', 'ELPETRO_apMr', 'ELPETRO_Kcorr',
              'SERSIC_Mr', 'SERSIC_MS', 'SERSIC_apMr', 'SERSIC_Kcorr',
              'IN_POL')
    data = (RA, DEC, Z, cdist,
            Mr_ELPETRO, MS_ELPETRO, apMr_ELPETRO, Kcorr_ELPETRO,
            Mr_SERSIC, MS_SERSIC, apMr_SERSIC, Kcorr_SERSIC,
            in_polygon)
    formats = ['float64'] * 12 + ['bool']
    catalog = np.zeros(Nmock, dtype={'names': labels,
                                     'formats': formats})
    for p, d in zip(labels, data):
        catalog[p] = np.ravel(d)

    np.save('/mnt/zfsusers/rstiskalek/pysham/data/NSAcatalog_wpols.npy',
            catalog)
