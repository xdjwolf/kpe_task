#!/usr/bin/env python
# %%
# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
Created on Wed Dec  4 14:29:06 2019

@author: Or Duek
1st level analysis using FSL output
In this one we smooth using SUSAN, which takes longer. 
"""

from __future__ import print_function
from __future__ import division
from builtins import str
from builtins import range

import os  # system functions

import nipype.interfaces.io as nio  # Data i/o
import nipype.interfaces.fsl as fsl  # fsl
import nipype.interfaces.utility as util  # utility
import nipype.pipeline.engine as pe  # pypeline engine
import nipype.algorithms.modelgen as model  # model generation
#import nipype.algorithms.rapidart as ra  # artifact detection
from nipype.workflows.fmri.fsl.preprocess import create_susan_smooth
from nipype.interfaces.utility import Function
"""
Preliminaries
-------------

Setup any package specific configuration. The output file format for FSL
routines is being set to compressed NIFTI.
"""

fsl.FSLCommand.set_default_output_type('NIFTI_GZ')


data_dir = '/home/oad4/scratch60/kpe'
output_dir = '/home/oad4/scratch60/work/fsl_analysis_ses4'
removeTR = 4
fwhm = 4
tr = 1
session = '4' # choose session

# %% Methods
def _bids2nipypeinfo(in_file, events_file, regressors_file, removeTR = 4,
                     regressors_names=None,
                     motion_columns=None,
                     decimals=3, amplitude=1.0):
    from pathlib import Path
    import numpy as np
    import pandas as pd
    from nipype.interfaces.base.support import Bunch
    
    # Process the events file
    events = pd.read_csv(events_file, sep=r'\s+')

    bunch_fields = ['onsets', 'durations', 'amplitudes']

    if not motion_columns:
        from itertools import product
        motion_columns = ['_'.join(v) for v in product(('trans', 'rot'), 'xyz')]

    out_motion = Path('motion.par').resolve()

    regress_data = pd.read_csv(regressors_file, sep=r'\s+')
    np.savetxt(out_motion, regress_data[motion_columns].values[removeTR:,], '%g')
    if regressors_names is None:
        regressors_names = sorted(set(regress_data.columns) - set(motion_columns))

    if regressors_names:
        bunch_fields += ['regressor_names']
        bunch_fields += ['regressors']

    runinfo = Bunch(
        scans=in_file,
        conditions=list(set(events.trial_type_30.values)),
        **{k: [] for k in bunch_fields})

    for condition in runinfo.conditions:
        event = events[events.trial_type_30.str.match(condition)]

        runinfo.onsets.append(np.round(event.onset.values-removeTR, 3).tolist()) # added -removeTR to align to the onsets after removing X number of TRs from the scan
        runinfo.durations.append(np.round(event.duration.values, 3).tolist())
        if 'amplitudes' in events.columns:
            runinfo.amplitudes.append(np.round(event.amplitudes.values, 3).tolist())
        else:
            runinfo.amplitudes.append([amplitude] * len(event))

    if 'regressor_names' in bunch_fields:
        runinfo.regressor_names = regressors_names
        runinfo.regressors = regress_data[regressors_names].fillna(0.0).values[removeTR:,].T.tolist() # adding removeTR to cut the first rows

    return [runinfo], str(out_motion)
# %%
subject_list = ['008','1223','1253','1263','1293','1307','1315','1322','1339','1343','1351','1356','1364',
'1369','1387','1390','1403','1464','1468','1480','1499', '1561']
# Map field names to individual subject runs. 



infosource = pe.Node(util.IdentityInterface(fields=['subject_id'
                                            ],
                                    ),
                  name="infosource")
infosource.iterables = [('subject_id', subject_list)]

# SelectFiles - to grab the data (alternativ to DataGrabber)
templates = {'func': data_dir +  '/fmriprep/sub-{subject_id}/ses-' + session + '/func/sub-{subject_id}_ses-' + session + '_task-Memory_space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz',
             'mask': data_dir + '/fmriprep/sub-{subject_id}/ses-' + session + '/func/sub-{subject_id}_ses-' + session + '_task-Memory_space-MNI152NLin2009cAsym_desc-brain_mask.nii.gz',
             'regressors': data_dir + '/fmriprep/sub-{subject_id}/ses-' + session + '/func/sub-{subject_id}_ses-' + session + '_task-Memory_desc-confounds_regressors.tsv',
             'events':  data_dir + '/condition_files/withNumbers/sub-{subject_id}_ses-' + session + '_30sec_window' + '.csv'}
selectfiles = pe.Node(nio.SelectFiles(templates,
                               ),
                   name="selectfiles")
# %%

# Extract motion parameters from regressors file
runinfo = pe.Node(util.Function(
    input_names=['in_file', 'events_file', 'regressors_file', 'regressors_names', 'removeTR'],
    function=_bids2nipypeinfo, output_names=['info', 'realign_file']),
    name='runinfo')
runinfo.inputs.removeTR = removeTR

# Set the column names to be used from the confounds file
runinfo.inputs.regressors_names = ['dvars', 'framewise_displacement'] + \
    ['a_comp_cor_%02d' % i for i in range(6)] + ['cosine%02d' % i for i in range(4)]
# %%




skip = pe.Node(interface=fsl.ExtractROI(), name = 'skip') 
skip.inputs.t_min = removeTR
skip.inputs.t_size = -1

# %%

susan =  pe.Node(interface=fsl.SUSAN(), name = 'susan') #create_susan_smooth()
susan.inputs.fwhm = fwhm
susan.inputs.brightness_threshold = 1000.0


# %%
modelfit = pe.Workflow(name='modelfit', base_dir= output_dir)
"""
Use :class:`nipype.algorithms.modelgen.SpecifyModel` to generate design information.
"""

modelspec = pe.Node(interface=model.SpecifyModel(),                  
                    name="modelspec")

modelspec.inputs.input_units = 'secs'
modelspec.inputs.time_repetition = tr
modelspec.inputs.high_pass_filter_cutoff= 120
"""
Use :class:`nipype.interfaces.fsl.Level1Design` to generate a run specific fsf
file for analysis
"""

## Building contrasts
level1design = pe.Node(interface=fsl.Level1Design(), name="level1design")
cont1 = ['Trauma1_0>Sad1_0', 'T', ['trauma1_0', 'sad1_0'], [1, -1]]
cont2 = ['Trauma1_0>Relax1_0', 'T', ['trauma1_0', 'relax1_0'], [1, -1]]
cont3 = ['Sad1_0>Relax1_0', 'T', ['sad1_0', 'relax1_0'], [1, -1]]
cont4 = ['trauma1_0 > trauma2_0', 'T', ['trauma1_0', 'trauma2_0'], [1, -1]]
cont5 = ['Trauma1_0>Trauma1_2_3', 'T', ['trauma1_0', 'trauma1_2','trauma1_3'], [1, -0.5, -0.5]]
cont6 = ['Trauma1 > Trauma2', 'T', ['trauma1_0', 'trauma1_1', 'trauma1_2', 'trauma1_3', 'trauma2_0', 'trauma2_1', 'trauma2_2', 'trauma2_3'], [0.25, 0.25, 0.25, 0.25, -0.25, -0.25, -0.25, -0.25 ]]
contrasts = [cont1, cont2, cont3, cont4, cont5, cont6]


level1design.inputs.interscan_interval = tr
level1design.inputs.bases = {'dgamma': {'derivs': False}}
level1design.inputs.contrasts = contrasts
level1design.inputs.model_serial_correlations = True    
"""
Use :class:`nipype.interfaces.fsl.FEATModel` to generate a run specific mat
file for use by FILMGLS
"""

modelgen = pe.MapNode(
    interface=fsl.FEATModel(),
    name='modelgen',
    iterfield=['fsf_file', 'ev_files'])
"""
Use :class:`nipype.interfaces.fsl.FILMGLS` to estimate a model specified by a
mat file and a functional run
"""
mask =  pe.Node(interface= fsl.maths.ApplyMask(), name = 'mask')


modelestimate = pe.MapNode(
    interface=fsl.FILMGLS(smooth_autocorr=True, mask_size=5, threshold=1000),
    name='modelestimate',
    iterfield=['design_file', 'in_file', 'tcon_file'])


# %%
modelfit.connect([
    (infosource, selectfiles, [('subject_id', 'subject_id')]),
    (selectfiles, runinfo, [('events','events_file'),('regressors','regressors_file')]),
    (selectfiles, skip,[('func','in_file')]),
    (skip,susan,[('roi_file','in_file')]),
    
    (susan, runinfo, [('smoothed_file', 'in_file')]),
    (susan, modelspec, [('smoothed_file', 'functional_runs')]),
    (runinfo, modelspec, [('info', 'subject_info'), ('realign_file', 'realignment_parameters')]),
    (modelspec, level1design, [('session_info', 'session_info')]),
    (level1design, modelgen, [('fsf_files', 'fsf_file'), ('ev_files',
                                                          'ev_files')]),
   # (susan, changeTosrting, [('outputnode.smoothed_files', 'arr')]),
    (susan, mask, [('smoothed.file', 'in_file')]),
    (selectfiles, mask, [('mask', 'mask_file')]),
    (mask, modelestimate, [('out_file','in_file')]),
    (modelgen, modelestimate, [('design_file', 'design_file'),('con_file', 'tcon_file'),('fcon_file','fcon_file')]),
    
])
# %%
modelfit.run('MultiProc', plugin_args={'n_procs': 6})
