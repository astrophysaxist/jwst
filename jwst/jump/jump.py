import time
import logging

import numpy as np
from ..datamodels import dqflags 
from ..lib import reffile_utils
from . import twopoint_difference as twopt
from . import yintercept as yint


log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

def detect_jumps (input_model, gain_model, readnoise_model,
                  rejection_threshold, do_yint, signal_threshold):
    """
    This is the high-level controlling routine for the jump detection process.
    It loads and sets the various input data and parameters needed by each of
    the individual detection methods and then calls the detection methods in
    turn.

    Note that the detection methods are currently setup on the assumption
    that the input science and error data arrays will be in units of
    electrons, hence this routine scales those input arrays by the detector
    gain. The methods assume that the read noise values will be in units
    of DN.

    The gain is applied to the science data and error arrays using the
    appropriate instrument- and detector-dependent values for each pixel of an
    image.  Also, a 2-dimensional read noise array with appropriate values for
    each pixel is passed to the detection methods.
    """

    # Load the data arrays that we need from the input model
    output_model = input_model.copy()
    data = input_model.data
    err  = input_model.err
    gdq  = input_model.groupdq
    pdq  = input_model.pixeldq

    ngroups = data.shape[1]
    nframes = input_model.meta.exposure.nframes

    # Get 2D gain and read noise values from their respective models
    if reffile_utils.ref_matches_sci(input_model, gain_model):
        gain_2d = gain_model.data
    else:
        log.info('Extracting gain subarray to match science data')
        gain_2d = reffile_utils.get_subarray_data(input_model, gain_model)

    if reffile_utils.ref_matches_sci(input_model, readnoise_model):
        readnoise_2d = readnoise_model.data
    else:
        log.info('Extracting readnoise subarray to match science data')
        readnoise_2d = reffile_utils.get_subarray_data(input_model, readnoise_model)

    # Flag the pixeldq where the gain is <=0 or NaN so they will be ignored
    wh_g = np.where( gain_2d <= 0.)  
    if len(wh_g[0] > 0):
        pdq[wh_g] = np.bitwise_or( pdq[wh_g], dqflags.pixel['NO_GAIN_VALUE'] )
        pdq[wh_g] = np.bitwise_or( pdq[wh_g], dqflags.pixel['DO_NOT_USE'] ) 

    wh_g = np.where( np.isnan( gain_2d ))
    if len(wh_g[0] > 0):
        pdq[wh_g] = np.bitwise_or( pdq[wh_g], dqflags.pixel['NO_GAIN_VALUE'] )
        pdq[wh_g] = np.bitwise_or( pdq[wh_g], dqflags.pixel['DO_NOT_USE'] ) 

    # Apply gain to the SCI, ERR, and readnoise arrays so they're in units 
    #   of electrons

    data *= gain_2d
    err  *= gain_2d
    readnoise_2d *= gain_2d

    # Apply the 2-point difference method as a first pass
    log.info('Executing two-point difference method')
    start = time.time()

    median_slopes = twopt.find_crs(data, gdq, readnoise_2d,
                                           rejection_threshold, nframes)

    elapsed = time.time() - start
    log.debug('Elapsed time = %g sec' %elapsed)

    # Apply the y-intercept method as a second pass, if requested
    if do_yint:

        # Set up the ramp time array for the y-intercept method
        group_time = output_model.meta.exposure.group_time
        times = np.array([(k+1)*group_time for k in range(ngroups)])
        median_slopes /= group_time

        # Now apply the y-intercept method
        log.info('Executing yintercept method')
        start = time.time()
        yint.find_crs(data, err, gdq, times, readnoise_2d,
                        rejection_threshold, signal_threshold, median_slopes)
        elapsed = time.time() - start
        log.debug('Elapsed time = %g sec' %elapsed)

    # Update the DQ arrays of the output model with the jump detection results
    output_model.groupdq = gdq
    output_model.pixeldq = pdq

    return output_model
