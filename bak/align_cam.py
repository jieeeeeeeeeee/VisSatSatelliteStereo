import os
import numpy as np
import quaternion
import colmap.read_model as read_model
from lib.esti_similarity import esti_similarity, esti_similarity_ransac


def read_data(colmap_dir):
    init_dir = os.path.join(colmap_dir, 'init')

    init_cam_positions = {}

    with open(os.path.join(init_dir, 'images.txt')) as fp:
        lines = [l.strip() for l in fp.readlines()]
        # remove empty lines
        lines = [l.split() for l in lines if l]

        for l in lines:
            qvec = np.array([float(x) for x in l[1:5]])
            tvec = np.array([float(x) for x in l[5:8]]).reshape((-1, 1))
            R = quaternion.as_rotation_matrix(np.quaternion(qvec[0], qvec[1], qvec[2], qvec[3]))
            init_cam_positions[int(l[0])] = -np.dot(R.T, tvec)

    sparse_ba_dir = os.path.join(colmap_dir, 'sparse_ba')

    ba_cam_positions = {}
    _, images, _ = read_model.read_model(sparse_ba_dir, '.bin')
    for img_id in images:
        img = images[img_id]
        qvec = img.qvec
        tvec = img.tvec.reshape((-1, 1))
        R = quaternion.as_rotation_matrix(quaternion.from_float_array(qvec))
        ba_cam_positions[img_id] = -np.dot(R.T, tvec)

    # re-organize the array
    source = []
    target = []
    for id in init_cam_positions:
        source.append(ba_cam_positions[id].reshape((3, )))
        target.append(init_cam_positions[id].reshape((3, )))

    source = np.array(source)
    target = np.array(target)

    return source, target

def compute_transform(work_dir, use_ransac=False):
    colmap_dir = os.path.join(work_dir, 'colmap')

    source, target = read_data(colmap_dir)

    if use_ransac:
        c, R, t = esti_similarity_ransac(source, target)
    else:
        c, R, t = esti_similarity(source, target)

    return c, R, t


if __name__ == '__main__':
    import logging

    # logging.getLogger().setLevel(logging.INFO)
    # logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

    work_dir = '/data2/kz298/core3d_aoi/aoi-d4-jacksonville/'
    # work_dir = '/data2/kz298/core3d_aoi/aoi-d4-jacksonville-overlap/'

    log_file = os.path.join(work_dir, 'log_align_cam.txt')
    logging.basicConfig(filename=log_file, level=logging.INFO, filemode='w')

    from datetime import datetime
    logging.info('Starting at {} ...'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    c, R, t = compute_transform(work_dir)

    logging.info('Finishing at {} ...'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))