"""
Dataset whose phasor data comes from an external source
(e.g. napari-phasors) rather than from a FLIM file on disk.

The class inherits every method from Dataset (pixel_values, image_feature,
apply_filters, calibrate_phasor, …) and is therefore a drop-in replacement
everywhere a Dataset is expected.
"""
from __future__ import annotations
import uuid

import numpy as np

from .dataset import Dataset
from flimari.core.utils import str2color

from phasorpy.phasor import phasor_transform

class ExternalDataset(Dataset):
	"""
	Dataset populated from pre-computed data.

	Parameters
	----------
	data:
		Plain dict following the schema documented in ``flimari.bridge``.
	"""

	def __init__(self, data: dict) -> None:
		# Do NOT call super().__init__()
		# It requires a file path and would attempt to read a FLIM file.

		# NOTE: Might need to be careful here about pointers
		g = np.asarray(data["g"], dtype=float)
		s = np.asarray(data["s"], dtype=float)
		g_orig = np.asarray(data.get("g_original", g), dtype=float)
		s_orig = np.asarray(data.get("s_original", s), dtype=float)
		calibration_phase = np.asarray(data.get("calibration_phase"), dtype=float)
		calibration_modulation = np.asarray(data.get("calibration_modulation"), dtype=float)

		# FLIMari requires harmonic=[1, 2], i.e. shape [2, Y, X].
		g = _ensure_two_harmonics(g)
		s = _ensure_two_harmonics(s)
		g_orig = _ensure_two_harmonics(g_orig)
		s_orig = _ensure_two_harmonics(s_orig)

		self._init_state(
			id=uuid.uuid4(), # No file identity, fallback to uuid4
			name=data["name"], path=data["name"], channel=int(data.get("channel", 0)),
			frequency=float(data.get("frequency", 80.0)),
			counts=data.get("counts", None), # napari-phasors sends true per-pixel photon counts (mean × histogram bins)
			mean= np.asarray(data.get("mean", np.ones(g.shape[1:], dtype=float)), dtype=float),
			real_raw=g_orig, imag_raw=s_orig
		)

		self.real_calibrated, self.imag_calibrated = phasor_transform(
			g_orig, s_orig, calibration_phase[:,None,None], calibration_modulation[:,None,None]
		)
		self.g: np.ndarray = g
		self.s: np.ndarray = s

		# --- Mask --- #
		# napari-phasors marks excluded pixels as NaN in the working G/S.
		# Using finiteness of first harmonic as mask.
		self.mask: np.ndarray = np.isfinite(g[0]) & np.isfinite(s[0])

		# --- Filter parameters --- #
		# Record what napari-phasors already applied so the UI reflects it.
		self.min_count: int  = int(data.get("min_count", 0))
		self.max_count = data.get("max_count", 10000)
		self.kernel_size: int = int(data.get("filter_size", 3))
		self.repetition: int  = int(data.get("filter_repeat", 0))

		# Filtered counts: zero out masked pixels
		self.counts_filtered: np.ndarray = self.counts.copy()
		self.counts_filtered[~self.mask] = 0

		# --- Lifetime estimates --- #
		self.compute_lifetime_estimates()


# --- helpers --- #
def _ensure_two_harmonics(arr: np.ndarray) -> np.ndarray:
	"""Return arr with shape [Har, Y, X] and Har >= 2, padding with NaN if needed."""
	if arr.ndim == 2:
		arr = arr[np.newaxis]       # (Y, X) -> (1, Y, X)
	if arr.shape[0] < 2:
		pad = np.full_like(arr, np.nan)
		arr = np.concatenate([arr, pad], axis=0)
	return arr
