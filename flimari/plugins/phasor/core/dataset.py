import os
from pathlib import Path
from typing import TYPE_CHECKING
from dataclasses import dataclass, field

import numpy as np

from phasorpy.phasor import phasor_from_signal, phasor_filter_median
from phasorpy.lifetime import (
	phasor_to_apparent_lifetime,
	phasor_to_normal_lifetime,
	phasor_to_lifetime_search,
)

from flimari.core.io import load_signal
from flimari.core.utils import str2color

if TYPE_CHECKING:
	import xarray

class Dataset:
	__slots__ = ("path", "name", "channel", "frequency", "counts", "counts_filtered",
		"mean", "real_raw", "imag_raw", "real_calibrated", "imag_calibrated", "g", "s",
		"phase_lifetime", "modulation_lifetime", "normal_lifetime", "geo_lifetime", "geo_fraction", "avg_lifetime",
		"max_count", "min_count", "kernel_size", "repetition", "mask", "group", "color")

	def __init__(self, path:str|Path, channel:int):
		if not os.path.isfile(path):
			raise OSError(2, "No such file or directory", os.path.basename(path))
		# Essential data definition
		self.path: str|Path = path
		self.name: str = os.path.basename(path)
		self.channel: int = channel
		signal = load_signal(path, channel)

		# Derived attributes
		self.counts: np.ndarray = signal.sum(dim='H').to_numpy() # Sum of photon counts over H axis
		self.counts_filtered: np.ndarray = self.counts.copy() # Photon counts but filtered with threshold
		# Raw immutable phasor attributes
		self.mean, self.real_raw, self.imag_raw = phasor_from_signal(signal, axis='H', harmonic=[1,2])
		# Last seen frequency (MHz)
		self.frequency: float = signal.attrs.get("frequency", 80)
		self.frequency = self.frequency if self.frequency > 0 else 80
		# Calibrated phasors
		self.real_calibrated: np.ndarray = self.real_raw.copy()
		self.imag_calibrated: np.ndarray = self.imag_raw.copy()
		# Working data copy
		self.g: np.ndarray = self.real_calibrated.copy()
		self.s: np.ndarray = self.imag_calibrated.copy()
		# Compute apprent and normal lifetimes
		self.compute_lifetime_estimates()

		# Filter parameters
		self.min_count: int = 0
		self.max_count: int = 10000
		self.kernel_size: int = 3
		self.repetition: int = 0
		# Cached photon count thresholding mask
		self.mask = np.ones_like(self.mean, dtype=np.uint8)

		# Misc attributes
		self.group: str = "default"
		self.color: str = str2color(self.group)

	def calibrate_phasor(self, calibration:"Calibration") -> None:
		self.real_calibrated, self.imag_calibrated = calibration.compute_calibrated_phasor(self.real_raw, self.imag_raw)
		# Update last seen frequency if calibration is provided
		if calibration and calibration.frequency > 0:
			self.frequency = calibration.frequency
		# Every time we re-calibrate, re-compute working data
		self.apply_filters()

	def compute_lifetime_estimates(self) -> None:
		"""
		Compute and cache lifetime estimates.
		"""
		self.phase_lifetime, self.modulation_lifetime = phasor_to_apparent_lifetime(*self.get_phasor(), frequency=self.frequency)
		self.normal_lifetime = phasor_to_normal_lifetime(*self.get_phasor(), frequency=self.frequency)
		self.geo_lifetime, self.geo_fraction = phasor_to_lifetime_search(self.g, self.s, frequency=self.frequency)
		self.avg_lifetime = (self.geo_lifetime*self.geo_fraction).sum(axis=0)
		#DEBUG
		self.avg_lifetime[self.avg_lifetime>10] = np.nan

	## ------ Working functions ------ ##
	def apply_filters(self) -> None:
		self.reset_gs()
		self.apply_median_filter()
		self.update_photon_mask()
		self.apply_photon_mask()
		# We always update lifetime estimates to keep everything in sync
		self.compute_lifetime_estimates()

	def apply_median_filter(self) -> None:
		"""
		Apply median filter to g and s.
		"""
		if self.kernel_size < 3: return
		if self.repetition < 1: return
		_, self.g, self.s = phasor_filter_median(self.mean, self.g, self.s, repeat=self.repetition, size=self.kernel_size)

	def update_photon_mask(self) -> None:
		"""
		Update mask based on current photon count threshold
		"""
		labels = self._photon_range_mask()
		self.mask = (labels == 1)

	def apply_photon_mask(self) -> None:
		"""
		Mask g and s using the photon count mask.
		This turns the pixels outside the mask to nan.
		"""
		self.g[:,~self.mask] = np.nan; self.s[:,~self.mask] = np.nan
		self.counts_filtered = self.counts.copy()
		self.counts_filtered[~self.mask] = 0 # numpy int cannot be nan

	def reset_gs(self) -> None:
		"""
		Reset g and s to calibrated phasor.
		"""
		self.g = self.real_calibrated.copy()
		self.s = self.imag_calibrated.copy()

	## ------ Public API ------ ##
	def get_phasor(self, harmonic:int=1):
		"""
		Return g and s coordinates of the specified harmonic.
		Default return the fundamental frequency.
		"""
		idx = harmonic-1
		if idx not in range(self.g.shape[0]):
			raise ValueError(f"Harmonic {harmonic} outside range")
		return self.g[idx], self.s[idx]

	def set_group(self, group:str) -> None:
		self.group = group
		self.color = str2color(group)

	def summarize(self) -> dict:
		# TODO: Maybe find a way to standarize the property names
		out = {}
		out["name"] = self.name
		out["channel"] = self.channel
		out["group"] = self.group
		out["photon_count"] = self.counts[self.mask]
		out["phi_lifetime"] = self.phase_lifetime[self.mask]
		out["m_lifetime"] = self.modulation_lifetime[self.mask]
		out["proj_lifetime"] = self.normal_lifetime[self.mask]
		out["avg_lifetime"] = self.avg_lifetime[self.mask]
		return out

	def pixel_values(self, metric:str, harmonic:int=1) -> np.ndarray:
		"""Return 1D float array of valid pixel values for a metric."""
		match metric:
			case "photon_count":
				vals = self.counts[self.mask].astype(float).ravel()
			case "g":
				g, _ = self.get_phasor(harmonic=harmonic)
				vals = g.ravel()
			case "s":
				_, s = self.get_phasor(harmonic=harmonic)
				vals = s.ravel()
			case "phi_lifetime":
				vals = self.phase_lifetime.ravel()
			case "m_lifetime":
				vals = self.modulation_lifetime.ravel()
			case "proj_lifetime":
				vals = self.normal_lifetime.ravel()
			case "avg_lifetime":
				vals = self.avg_lifetime.ravel()
			case "geo_tau1":
				vals = self.geo_lifetime[0].ravel()
			case "geo_tau2":
				vals = self.geo_lifetime[1].ravel()
			case "geo_frac1":
				vals =	self.geo_fraction[0].ravel()
			case "geo_frac2":
				vals = ds.geo_fraction[1].ravel()
			case _:
				raise KeyError(metric)

		return vals[np.isfinite(vals)]

	def image_feature(self, metric:str, stat:str, harmonic:int=1) -> float:
		"""Compute one image-level feature = summary stat over pixel values."""
		v = self.pixel_values(metric, harmonic=harmonic)
		if v.size == 0:
			return np.nan
		if stat == "median":
			return np.nanmedian(v)
		if stat == "mean":
			return np.nanmean(v)
		if stat == "std":
			return np.nanstd(v)
		if stat == "iqr":
			q75, q25 = np.nanpercentile(v, [75, 25])
			return q75 - q25
		if stat == "p10":
			return np.nanpercentile(v, 10)
		if stat == "p90":
			return np.nanpercentile(v, 90)
		raise KeyError(stat)

	def display_name(self) -> str:
		return f"{self.name} (C{self.channel+1}) [{self.group}]"

	## ------ Internal ------ ##
	def _photon_range_mask(self) -> np.ndarray:
		"""
		Return a labels mask (Y,X) with values: 0=low, 1=kept, 2=high.
		"""
		low = self.counts < self.min_count
		high = self.counts > self.max_count
		kept = ~(low|high)

		labels = np.zeros_like(self.counts, dtype=np.uint8)
		labels[kept] = 1
		labels[high] = 2
		return labels

