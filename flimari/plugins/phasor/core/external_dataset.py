"""
ExternalDataset — a Dataset whose phasor data comes from an external source
(e.g. napari-phasors) rather than from a FLIM file on disk.

The class inherits every method from Dataset (pixel_values, image_feature,
apply_filters, calibrate_phasor, …) and is therefore a drop-in replacement
everywhere a Dataset is expected.
"""
from __future__ import annotations

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
		# Do NOT call super().__init__() — it requires a file path and would
		# attempt to read a FLIM file.  We populate all inherited slots here.

		self.name = str(data["name"])
		self.path = self.name # use name as placeholder

		self.channel = int(data.get("channel", 0))

		self.frequency = float(data.get("frequency", 80.0))
		if self.frequency <= 0: self.frequency = 80.0

		# --- Phasor coordinates --- #
		# TODO: Might need to be careful here about pointers
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

		self.real_raw = g_orig
		self.imag_raw = s_orig
		self.real_calibrated, self.imag_calibrated = phasor_transform(
			g_orig, s_orig, calibration_phase[:,None,None], calibration_modulation[:,None,None])
		self.g: np.ndarray = g
		self.s: np.ndarray = s

		# --- Intensity image --- #
		mean_default = np.ones(g.shape[1:], dtype=float)
		mean = np.asarray(data.get("mean", mean_default), dtype=float)
		self.mean = mean
		# HACK: No good way to get photon counts, use mean as placeholder
		self.counts = mean

		# --- Mask --- #
		# napari-phasors marks excluded pixels as NaN in the working G/S.
		# Using finiteness of first harmonic as mask.
		self.mask: np.ndarray = np.isfinite(g[0]) & np.isfinite(s[0])

		# --- Filter parameters --- #
		# Record what napari-phasors already applied so the UI reflects it.
		# BUG: napari-phasors uses mean threshold, not photon count threshold
		self.min_count: int  = int(data.get("min_count", 0))
		max_count = data.get("max_count", None)
		self.max_count: int  = int(max_count) if max_count is not None else int(1e9)
		self.kernel_size: int = int(data.get("filter_size", 3))
		self.repetition: int  = int(data.get("filter_repeat", 0))

		# Filtered counts: zero out masked pixels (ints can't be NaN)
		self.counts_filtered: np.ndarray = mean.copy()
		self.counts_filtered[~self.mask] = 0

		# --- Lifetime estimates --- #
		# Reuse the inherited computation; NaN phasors propagate to NaN lifetimes.
		self.compute_lifetime_estimates()

		# --- Labels / ROI --- #
		self.labels: np.ndarray        = np.ones(g.shape[1:], dtype=np.uint8)
		self.labels_unique: np.ndarray = np.array([1])

		# --- Metadata --- #
		self.group: str  = "default"
		self.color: str  = str2color(self.group)

	# Override display_name to make the origin visible in the UI.
	def display_name(self) -> str:
		return f"{self.name} [napari-phasors/{self.group}]"


# --- helpers --- #
def _ensure_two_harmonics(arr: np.ndarray) -> np.ndarray:
	"""Return arr with shape [Har, Y, X] and Har >= 2, padding with NaN if needed."""
	if arr.ndim == 2:
		arr = arr[np.newaxis]       # (Y, X) → (1, Y, X)
	if arr.shape[0] < 2:
		pad = np.full_like(arr, np.nan)
		arr = np.concatenate([arr, pad], axis=0)
	return arr
