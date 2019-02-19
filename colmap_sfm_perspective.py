import os
from write_template import write_template_perspective
from absolute_coordinate import triangualte_all_points
import numpy as np
from correct_init import correct_init
import json
import colmap_sfm_commands
from colmap.extract_sfm import extract_camera_dict, extract_all_to_dir

# for inspector
from lib.ply_np_converter import np2ply
from inspector.plot_reproj_err import plot_reproj_err
from check_align import check_align
from inspector.inspect_sfm import SparseInspector
import logging


def make_subdirs(sfm_dir):
    subdirs = [
                sfm_dir,
                os.path.join(sfm_dir, 'init_triangulate'),
                os.path.join(sfm_dir, 'corrected_triangulate'),
                os.path.join(sfm_dir, 'corrected_triangulate_ba')
    ]

    for item in subdirs:
        if not os.path.exists(item):
            os.mkdir(item)


def check_sfm(work_dir, sfm_dir):
    subdirs = [
                os.path.join(sfm_dir, 'init_triangulate'),
                os.path.join(sfm_dir, 'corrected_triangulate'),
                os.path.join(sfm_dir, 'corrected_triangulate_ba')
    ]

    for dir in subdirs:
        logging.info('\ninspecting {} ...'.format(dir))
        inspect_dir = dir + '_inspect'

        _, xyz_file, track_file = extract_all_to_dir(dir, inspect_dir)
        # triangulate points
        rpc_xyz_file = os.path.join(inspect_dir, 'kai_rpc_coordinates.txt')
        triangualte_all_points(work_dir, track_file, rpc_xyz_file, os.path.join(inspect_dir, '/tmp'))

        sfm_inspector = SparseInspector(dir, inspect_dir, camera_model='PERSPECTIVE')
        sfm_inspector.inspect_all()

        # check rpc_reproj_err and rpc_points
        rpc_coordinates = np.loadtxt(rpc_xyz_file)
        zone_number = rpc_coordinates[0, 3]
        zone_letter = 'N' if rpc_coordinates[0, 4] > 0 else 'S'
        comments = ['projection: UTM {}{}'.format(zone_number, zone_letter),]
        np2ply(rpc_coordinates[:, 0:3], os.path.join(inspect_dir, 'rpc_absolute_points.ply'), comments)
        plot_reproj_err(rpc_coordinates[:, -1], os.path.join(inspect_dir, 'rpc_reproj_err.jpg'))

        # check alignment
        source = np.loadtxt(xyz_file)[:, 0:3]
        target = rpc_coordinates[:, 0:3]
        check_align(work_dir, source, target)


def run_sfm(work_dir, sfm_dir, init_camera_file):
    make_subdirs(sfm_dir)

    with open(init_camera_file) as fp:
        init_camera_dict = json.load(fp)
    with open(os.path.join(sfm_dir, 'init_camera_dict.json'), 'w') as fp:
        json.dump(init_camera_dict, fp, indent=2, sort_keys=True)
    init_template = os.path.join(sfm_dir, 'init_template.json')
    write_template_perspective(init_camera_dict, init_template)

    img_dir = os.path.join(sfm_dir, 'images')
    db_file = os.path.join(sfm_dir, 'database.db')

    colmap_sfm_commands.run_sift_matching(img_dir, db_file, camera_model='PERSPECTIVE')

    out_dir = os.path.join(sfm_dir, 'init_triangulate')
    colmap_sfm_commands.run_point_triangulation(img_dir, db_file, out_dir, init_template)

    # extract tracks
    kai_dir = os.path.join(sfm_dir, 'init_triangulate_kai')
    _, xyz_file, track_file = extract_all_to_dir(out_dir, kai_dir)
    # triangulate points
    rpc_xyz_file = os.path.join(kai_dir, 'kai_rpc_coordinates.txt')
    triangualte_all_points(work_dir, track_file, rpc_xyz_file, os.path.join(kai_dir, '/tmp'))

    # load sfm coordinates and absolute coordinates
    source = np.loadtxt(xyz_file)[:, 0:3]
    target = np.loadtxt(rpc_xyz_file)[:, 0:3]

    # we change target to a local coordinate frame
    with open(os.path.join(work_dir, 'aoi.json')) as fp:
        aoi_dict = json.load(fp)
    aoi_ll_east = aoi_dict['x']
    aoi_ll_north = aoi_dict['y'] - aoi_dict['h']
    east = target[:, 0:1] - aoi_ll_east
    north = target[:, 1:2] - aoi_ll_north
    height = target[:, 2:3]
    target = np.hstack((east, north, height))

    # correct distortion in the scene
    corrected_camera_dict = correct_init(source, target, init_camera_dict)
    with open(os.path.join(sfm_dir, 'corrected_camera_dict.json'), 'w') as fp:
        json.dump(corrected_camera_dict, fp, indent=2, sort_keys=True)
    corrected_template = os.path.join(sfm_dir, 'corrected_template.json')
    write_template_perspective(corrected_camera_dict, corrected_template)
    out_dir = os.path.join(sfm_dir, 'corrected_triangulate')
    colmap_sfm_commands.run_point_triangulation(img_dir, db_file, out_dir, corrected_template)

    # substitute the coordinates in point3d.txt
    # extract tracks
    kai_dir = os.path.join(sfm_dir, 'corrected_triangulate_kai')
    _, _, track_file = extract_all_to_dir(out_dir, kai_dir)
    # triangulate points
    rpc_xyz_file = os.path.join(kai_dir, 'kai_rpc_coordinates.txt')
    triangualte_all_points(work_dir, track_file, rpc_xyz_file, os.path.join(kai_dir, '/tmp'))

    # load absolute coordinates
    target = np.loadtxt(rpc_xyz_file)[:, 0:3]

    # we change target to a local coordinate frame
    east = target[:, 0:1] - aoi_ll_east
    north = target[:, 1:2] - aoi_ll_north
    height = target[:, 2:3]

    os.rename(os.path.join(sfm_dir, 'corrected_triangulate/points3D.txt'), os.path.join(sfm_dir, 'corrected_triangulate/points3D.txt.bak'))
    point_id2xyz = {}
    with open(os.path.join(kai_dir, 'kai_track_ids.json')) as fp:
        track_ids = json.load(fp)
    for i in range(len(track_ids)):
        point_id2xyz[track_ids[i]] = ' {} {} {} '.format(east[i, 0], north[i, 0], height[i, 0])
    with open(os.path.join(sfm_dir, 'corrected_triangulate/points3D.txt.bak')) as fp:
        lines = fp.readlines()
    for i in range(3, len(lines)):
        tmp = lines[i].split(' ')
        if len(tmp) > 1:
            lines[i] = tmp[0] + point_id2xyz[int(tmp[0])] + ' '.join(tmp[4:])
    with open(os.path.join(sfm_dir, 'corrected_triangulate/points3D.txt'), 'w') as fp:
        fp.writelines(lines)

    # global bundle adjustment
    in_dir = os.path.join(sfm_dir, 'corrected_triangulate')
    out_dir = os.path.join(sfm_dir, 'corrected_triangulate_ba')
    colmap_sfm_commands.run_global_ba(in_dir, out_dir)

    # write final camera_dict
    camera_dict = extract_camera_dict(out_dir)
    with open(os.path.join(sfm_dir, 'final_camera_dict.json'), 'w') as fp:
        json.dump(camera_dict, fp, indent=2, sort_keys=True)
