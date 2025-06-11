#!/usr/bin/env python

from pathlib import Path
from argparse import ArgumentParser, Namespace, ArgumentDefaultsHelpFormatter

import os
import re
import glob
from chris_plugin import chris_plugin, PathMapper
from nii2dcm.run import run_nii2dcm
import pydicom as dcm

__version__ = '0.1.0'

DISPLAY_TITLE = r"""
adc-to-zmap: nii-to-dcm
"""


parser = ArgumentParser(description='adc-to-zmap: nii-to-dcm',
                        formatter_class=ArgumentDefaultsHelpFormatter)
# The main function of this *ChRIS* plugin is denoted by this ``@chris_plugin`` "decorator."
# Some metadata about the plugin is specified here. There is more metadata specified in setup.py.
#
# documentation: https://fnndsc.github.io/chris_plugin/chris_plugin.html#chris_plugin


@chris_plugin(
    parser=parser,
    title='adc-to-zmap-nii-to-dcm',
    category='',                 # ref. https://chrisstore.co/plugins
    min_memory_limit='1Gi',    # supported units: Mi, Gi
    min_cpu_limit='1000m',       # millicores, e.g. "1000m" = 1 CPU core
    min_gpu_limit=0              # set min_gpu_limit=1 to enable GPU
)
def main(options: Namespace, inputdir: Path, outputdir: Path):
    """
    *ChRIS* plugins usually have two positional arguments: an **input directory** containing
    input files and an **output directory** where to write output files. Command-line arguments
    are passed to this main method implicitly when ``main()`` is called below without parameters.

    :param options: non-positional arguments parsed by the parser given to @chris_plugin
    :param inputdir: directory containing (read-only) input files
    :param outputdir: directory where to write output files
    """
    '''
    Typical directory structure:

    *_ss_zmap.nii.gz
    **/*.dcm
    '''

    inputdir_str = str(inputdir)
    outputdir_str = str(outputdir)

    nii_fileinfos = _get_nii_fileinfos(inputdir_str)
    dcm_fileinfos = _get_dcm_fileinfos(inputdir_str)
    nii_dcm_pairs = _nii_dcm_pairs(nii_fileinfos, dcm_fileinfos)

    print(f'adc-to-zmap-nii-to-dcm: to dcm: nii_fileinfos: {len(nii_fileinfos)} nii_dcm_pairs: {len(nii_dcm_pairs)}')  # noqa

    for nii_fileinfo, dcm_fileinfo in nii_dcm_pairs:
        nii_filename = nii_fileinfo['filename']
        dcm_filename = dcm_fileinfo['filename']
        out_dir = _get_outdir(outputdir_str, nii_filename)
        run_nii2dcm(Path(nii_filename), Path(out_dir), 'MR', Path(dcm_filename))


def _get_nii_fileinfos(inputdir: str):
    filenames = os.listdir(inputdir)
    valid_filenames = list(filter(lambda x: x.endswith('.nii.gz'), filenames))
    nii_fileinfos = list(map(_get_nii_fileinfo, valid_filenames))
    return nii_fileinfos


def _get_nii_fileinfo(filename: str):
    prompt = re.sub(r'_ss_zmap\.nii\.gz$', '', filename)
    base_filename = os.path.basename(filename)
    return {'filename': filename, 'prompt': prompt, 'base_filename': base_filename}


def _get_dcm_fileinfos(inputdir: str):
    dcm_fileinfos = []
    for root, the_dirs, the_filenames in os.walk(inputdir):
        filenames = list(the_filenames)
        valid_filenames = list(filter(lambda x: x.endswith('.dcm'), filenames))
        if not valid_filenames:
            continue

        full_filename = f'{root}/{valid_filenames[0]}'
        dcm_fileinfo = _get_dcm_fileinfo(full_filename)
        dcm_fileinfos.append(dcm_fileinfo)

    print(f'[INFO] _get_dcm_fileinfos: to return: {len(dcm_fileinfos)}')

    return dcm_fileinfos


def _get_dcm_fileinfo(filename):
    '''
    https://raw.githubusercontent.com/rordenlab/dcm2niix/master/FILENAMING.md
    '''

    the_base_filename = os.path.basename(filename)
    dir_basename = os.path.basename(os.path.dirname(filename))

    base_filename = f'{dir_basename}/{the_base_filename}'

    the_dcm = dcm.dcmread(filename)

    # folder_name = 'incoming'
    protocol_name = None
    try:
        protocol_name = the_dcm.data_element('ProtocolName').value
    except Exception as e:
        print(f'[WARN] _get_dcm_filename: {base_filename} unable to get protocol name from ProtocolName e: {e}')  # noqa
        protocol_name = None

    if protocol_name is None:
        try:
            protocol_name = the_dcm.data_element('SequenceName').value
        except Exception as e:
            print(f'[WARN] _get_dcm_filename: {base_filename} unable to get protocol name from SequenceName e: {e}')  # noqa
            protocol_name = ''

    description = ''
    try:
        description = the_dcm.data_element('SeriesDescription').value
    except Exception as e:
        print(f'[WARN] _get_dcm_filename: {base_filename} unable to get description e: {e}')  # noqa
        description = ''

    the_date = ''
    try:
        the_date = the_dcm[0x08, 0x20].value
    except Exception as e:
        print(f'[WARN] _get_dcm_filename: {base_filename} unable to get date e: {e}')  # noqa
        the_date = ''

    the_time = ''
    try:
        the_time = the_dcm[0x08, 0x30].value
    except Exception as e:
        print(f'[WARN] _get_dcm_filename: {base_filename} unable to get time e: {e}')  # noqa
        the_time = ''

    series_no = ''
    try:
        series_no = the_dcm[0x20, 0x11].value
    except Exception as e:
        print(f'[WARN] _get_dcm_filename: {base_filename} unable to get series-no e: {e}')  # noqa
        series_no = ''

    prompt = f'{protocol_name}_{description}_{the_date}_{the_time}_{series_no}'
    prompt = re.sub(r' ', '_', prompt)

    print(f'[INFO] _get_dcm_fileinfo: to return: {base_filename}: prompt: {prompt}')  # noqa

    return {'filename': filename, 'prompt': prompt, 'base_filename': base_filename}


def _nii_dcm_pairs(nii_fileinfos: list, dcm_fileinfos: list):
    dcm_fileinfo_map = {each['prompt']: each for each in dcm_fileinfos}

    pairs = [(each, dcm_fileinfo_map.get(each['prompt'], None)) for each in nii_fileinfos]

    invalid_pairs = list(filter(lambda x: x[1] is None, pairs))
    for idx, (nii_fileinfo, dcm_fileinfo) in enumerate(invalid_pairs):
        print(f"[WARN] ({idx}/{len(invalid_pairs)}) {nii_fileinfo['base_filename']}: no dcm pair")

    valid_pairs = list(filter(lambda x: x[1] is not None, pairs))
    for idx, (nii_fileinfo, dcm_fileinfo) in enumerate(valid_pairs):
        print(f"[INFO] ({idx}/{len(invalid_pairs)}) {nii_fileinfo['base_filename']}: {dcm_fileinfo['base_filename']}")  # noqa

    return valid_pairs


def _get_outdir(outputdir: str, nii_filename: str):
    nii_basename = os.path.basename(nii_filename)
    nii_prefix = re.sub(r'\.nii\.gz$', '', nii_basename)

    return f'{outputdir}/{nii_prefix}'


if __name__ == '__main__':
    main()
