#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jan 16 12:30:22 2020

@author: Or Duek
Build a simple pipline that takes subject's native space seed2voxel images and turns them to MNI'
"""
import nipype.interfaces.io as nio  # Data i/o
from nipype.pipeline import engine as pe
from nipype.interfaces.ants import ApplyTransforms
import nipype.interfaces.utility as util  # utility
import os


seed_dir = '/media/Data/KPE_results/seed2voxel/native_space'
input_dir = '/media/Data/KPE_BIDS/derivatives/fmriprep'
output_dir = '/media/Data/KPE_results/seedVoxel/MNI_space'
data_dir = 'media/Data/work'
ses = '1'

subject_list = ['008','1223','1253','1263','1293','1307','1315','1322','1339', '1343','1351','1356','1364','1369','1387','1390','1403','1464','1468','1480','1499']

infosource = pe.Node(util.IdentityInterface(fields=['subject_id'
                                            ],
                                    ),
                  name="infosource")
infosource.iterables = [('subject_id', subject_list)]

# SelectFiles - to grab the data (alternativ to DataGrabber)

templates = {'stat': os.path.join(seed_dir, 'trauma_seed_leftAmg_sub-{subject_id}_ses-' + ses + '_z.nii.gz'),
             'reference_image': os.path.join(input_dir, 'sub-{subject_id}/anat/sub-{subject_id}_space-MNI152NLin2009cAsym_desc-preproc_T1w.nii.gz'),
             'transform_file': os.path.join(input_dir, 'sub-{subject_id}/anat/sub-{subject_id}_from-T1w_to-MNI152NLin2009cAsym_mode-image_xfm.h5')}
             

selectfiles = pe.Node(nio.SelectFiles(templates),  name="selectfiles")

def sendOutput(subject_id):
    import os
    output_dir = '/media/Data/KPE_results/seed2voxel/MNI_space'
    output_file = os.path.join(output_dir, 'trauma_seed_leftAmg_sub-'+subject_id + '_ses-1_z_MNI.nii.gz')
    return output_file

sendOut = pe.Node(name="sendOut",
                  interface=util.Function(input_names=['subject_id'],
                                     output_names=['output_file'],
                                     function=sendOutput))
#'output_file': os.path.join(output_dir, 'trauma_seed_leftAmg_sub-{subject_id}_ses-' + ses + '_z_MNI.nii.gz')
at = pe.Node(ApplyTransforms(), name = 'at')
# at = ApplyTransforms()
# at.inputs.input_image = '/home/or/kpe_task_analysis/trauma_seed_leftAmg_sub-1263_ses-1_z.nii.gz'
# at.inputs.reference_image = T1_mni_file
# at.inputs.transforms = h5_file
# at.inputs.output_image = output_file + 'MNI' + '.nii.gz'
# at.cmdline


wfANT = pe.Workflow(name="ants", base_dir="/media/Data/work/antsTransform")

wfANT.connect([
     (infosource, selectfiles, [('subject_id', 'subject_id')]),
     (infosource, sendOut, [('subject_id', 'subject_id')]),
     (sendOut, at, [('output_file','output_image')]),
     (selectfiles, at, [('stat','input_image'), ('reference_image','reference_image'), ('transform_file','transforms')])
    ])


wfANT.run('MultiProc', plugin_args={'n_procs': 5})
