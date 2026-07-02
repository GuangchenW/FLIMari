"""
Bridge module for receiving data from external napari plugins.

napari-phasors (and other plugins) can call `import_from_napari_phasors()`
to transfer phasor data into FLIMari without a hard import dependency.

Protocol
--------
The bridge uses a callback registered by `SampleManagerWidget` when it
initialises.  External plugins call `import_from_napari_phasors()` with a
list of plain dicts; FLIMari converts each dict into an `ExternalDataset`.

Dict schema (all numpy arrays must be float64-compatible)::

    {
        "name":          str,            # display name / layer name
        "channel":       int,            # 0-based channel index
        "frequency":     float,          # laser repetition frequency in MHz
        "g":             ndarray,        # [Harmonics, Y, X] working phasor G
        "s":             ndarray,        # [Harmonics, Y, X] working phasor S
        "g_original":    ndarray,        # [Harmonics, Y, X] pre-calibration G  (optional)
        "s_original":    ndarray,        # [Harmonics, Y, X] pre-calibration S  (optional)
        "mean":          ndarray,        # [Y, X]    mean intensity       (optional)
        "counts":        ndarray,        # [Y, X]    true photon counts (mean × histogram bins) (optional, default mean)
        "min_count":     int,            # lower intensity threshold      (optional, default 0)
        "max_count":     int | None,     # upper intensity threshold      (optional, default None)
        "filter_size":   int,            # median filter kernel size      (optional, default 3)
        "filter_repeat": int,            # median filter repetitions      (optional, default 0)
    }
"""
from __future__ import annotations

from typing import Callable

_import_callback: Callable[[list[dict]], None] | None = None


def register_import_callback(fn: Callable[[list[dict]], None]) -> None:
    """Register the callback that FLIMari's SampleManagerWidget provides."""
    global _import_callback
    _import_callback = fn


def import_from_napari_phasors(data_list: list[dict]) -> None:
    """
    Transfer phasor data from napari-phasors into FLIMari.

    Parameters
    ----------
    data_list:
        One dict per image layer, following the schema above.

    Raises
    ------
    RuntimeError
        If FLIMari's SampleManagerWidget has not been opened yet.
    """
    if _import_callback is None:
        raise RuntimeError(
            "FLIMari is not ready to receive data. "
            "Open the FLIMari dock widget first."
        )
    _import_callback(data_list)
