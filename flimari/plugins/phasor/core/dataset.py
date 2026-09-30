from __future__ import annotations
import os
import uuid
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from phasorpy.phasor import phasor_from_signal
from phasorpy.filter import phasor_filter_median
from phasorpy.lifetime import (
	phasor_to_apparent_lifetime,
	phasor_to_normal_lifetime,
	phasor_to_lifetime_search,
)

from flimari.core import load_signal
from flimari.core.utils import str2color

if TYPE_CHECKING:
	from .calibration import Calibration

## --- Feature names --- ##
class FeatureNames:
	PHOTON_COUNT = "Photon Count"
	G = "Real Coordinate (G)"
	S = "Imaginary Coordinate (S)"
	PHI_LIFETIME = "Phase Lifetime"
	M_LIFETIME = "Modulation Lifetime"
	PROJ_LIFETIME = "Projected Normal Lifetime"
	AVG_LIFETIME = "Searched Average Lifetime"
	GEO_TAU_1 = "Searched Tau 1"
	GEO_TAU_2 = "Searched Tau 2"
	GEO_FRAC_1 = "Searched Alpha 1"
	GEO_FRAC_2 = "Searched Alpha 2"
	ALL = [
		PHOTON_COUNT,
		G,
		S,
		PHI_LIFETIME,
		M_LIFETIME,
		PROJ_LIFETIME,
		AVG_LIFETIME,
		GEO_TAU_1,
		GEO_TAU_2,
		GEO_FRAC_1,
		GEO_FRAC_2,
	]

## --- Morphological feature names --- ##
class MorphFeatureNames:
	AREA = "Area"
	AXIAL_RATIO = "Minor/Major Axis Ratio"
	PERIMETER = "Perimeter"
	CIRCULARITY = "Circularity"
	ECCENTRICITY = "Eccentricity"
	SOLIDITY = "Solidity"
	EXTENT = "Extent"
	ALL = [AREA, AXIAL_RATIO, PERIMETER, CIRCULARITY, ECCENTRICITY, SOLIDITY, EXTENT]

## --- Stats names --- ##
class StatsNames:
	MEDIAN = "Median"
	IQR = "Interquantile Range"
	MEAN = "Mean"
	STD = "Stddev"
	P10 = "10th Percentile"
	P90 = "90th Percentile"
	ALL = [MEDIAN, IQR, MEAN, STD, P10, P90]

## --- Dataset class --- ##
def persist(**kwargs):
	"""Mark a field as part of the saved state."""
	return field(metadata={"persist": True}, **kwargs)

@dataclass(slots=True, init=False, eq=False, repr=False)
class Dataset:
	# --- Saved state --- #
	id: uuid.UUID = persist()
	name: str = persist()
	path: Path = persist()
	channel: int = persist()
	frequency: float = persist() # Last seen frequency (MHz)
	counts: np.ndarray = persist() # Photon counts summed over H axis
	mean: np.ndarray = persist()
	real_raw: np.ndarray = persist() # Raw phasor, harmonics [1, 2]
	imag_raw: np.ndarray = persist()
	real_calibrated: np.ndarray = persist()
	imag_calibrated: np.ndarray = persist()
	g: np.ndarray = persist() # Working phasor (calibrated, filtered, masked)
	s: np.ndarray = persist()
	mask: np.ndarray = persist() # Photon count threshold mask
	labels: np.ndarray = persist() # Pixel labels for ROI analysis
	min_count: int = persist()
	max_count: int = persist()
	kernel_size: int = persist()
	repetition: int = persist()
	group: str = persist()
	# --- Derived states --- #
	counts_filtered: np.ndarray
	phase_lifetime: np.ndarray
	modulation_lifetime: np.ndarray
	normal_lifetime: np.ndarray
	geo_lifetime: np.ndarray
	geo_fraction: np.ndarray
	avg_lifetime: np.ndarray
	labels_unique: np.ndarray
	color: str

	def __init__(self, path:str|Path, channel:int):
		path = Path(path)
		if not path.is_file():
			raise FileNotFoundError(path)
		
		signal = load_signal(path, channel)
		frequency = signal.attrs.get("frequency", 80)
		mean, real, imag = phasor_from_signal(signal, axis='H', harmonic=[1,2])
		counts = signal.sum(dim='H').to_numpy() # Sum of photon counts over H axis

		self._init_state(
			name=path.name, path=path, channel=channel, frequency=frequency,
			counts=counts, mean=mean, real_raw=real, imag_raw=imag
		)

		self.compute_lifetime_estimates()

	def _init_state(self, *, name, path, channel, frequency, counts, mean, real_raw, imag_raw) -> None:
		"""Declare attributes and set it to its default state."""
		self.id = uuid.uuid4() # Unique dataset id
		self.name, self.path, self.channel = name, path, channel
		self.frequency = frequency if frequency > 0 else 80 # Mhz
		self.counts, self.mean = counts, mean
		self.real_raw, self.imag_raw = real_raw, imag_raw
		self.real_calibrated, self.imag_calibrated = real_raw.copy(), imag_raw.copy()
		self.g, self.s = real_raw.copy(), imag_raw.copy()
		self.mask = np.ones(counts.shape, dtype=np.uint8)
		self.counts_filtered = counts.copy()
		self.min_count, self.max_count = 0, 10000
		self.kernel_size, self.repetition = 3, 0
		self.labels = np.ones(counts.shape, dtype=np.uint8)
		self.labels_unique = np.array([1])
		self.group = "default"
		self.color = str2color(self.group)

	## ------ Serialization ------ ##
	def to_dict(self) -> dict:
		d = {}
		for f in fields(self):
			if f.metadata.get("persist"):
				d[f.name] = _to_serializable(getattr(self, f.name))
		return d

	@classmethod
	def from_dict(cls, d:dict) -> Dataset:
		"""
		Returns a dataset from saved dictionary.
		"""
		ds = cls.__new__(cls) # Don't use __init__
		for f in fields(cls):
			if f.metadata.get("persist"):
				setattr(ds, f.name, d[f.name])
		# Restore rich types
		ds.id = uuid.UUID(d["id"])
		ds.path = Path(d["path"])
		ds.mask = ds.mask.astype(bool)
		# Rebuild derived states
		ds.counts_filtered = np.where(ds.mask, ds.counts, 0)
		ds.set_labels(d["labels"])
		ds.set_group(d["group"])
		ds.compute_lifetime_estimates()
		return ds

	## ------ Working functions ------ ##
	def calibrate_phasor(self, calibration:Calibration) -> None:
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

	def apply_filters(self) -> None:
		self.reset_gs()
		self.apply_median_filter()
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

	def apply_photon_mask(self) -> None:
		"""
		Mask g and s using the photon count mask.
		This turns the pixels outside the mask to nan.
		"""
		# Update photon thrshold mask
		self.mask = (self._photon_range_mask() == 1)
		# Set g and s to nan for both harmonics
		self.g[:,~self.mask] = np.nan; self.s[:,~self.mask] = np.nan
		# Update filtered photon counts
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

	def set_labels(self, labels:np.ndarray):
		"""
		Set pixel labels and update unique labels.
		"""
		self.labels = labels
		labels = labels[labels>0]
		self.labels_unique = np.unique_values(labels)

	def set_group(self, group:str) -> None:
		"""
		Set the group of this dataset.
		Also set the color using the group name.
		"""
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

	def pixel_values(self, metric:str, label:int=1, harmonic:int=1) -> np.ndarray:
		"""Return 1D float array of valid pixel values for a metric."""
		match metric:
			case FeatureNames.PHOTON_COUNT:
				vals = self.counts.astype(float)
			case FeatureNames.G:
				g, _ = self.get_phasor(harmonic=harmonic)
				vals = g
			case FeatureNames.S:
				_, s = self.get_phasor(harmonic=harmonic)
				vals = s
			case FeatureNames.PHI_LIFETIME:
				vals = self.phase_lifetime
			case FeatureNames.M_LIFETIME:
				vals = self.modulation_lifetime
			case FeatureNames.PROJ_LIFETIME:
				vals = self.normal_lifetime
			case FeatureNames.AVG_LIFETIME:
				vals = self.avg_lifetime
			case FeatureNames.GEO_TAU_1:
				vals = self.geo_lifetime[0]
			case FeatureNames.GEO_TAU_2:
				vals = self.geo_lifetime[1]
			case FeatureNames.GEO_FRAC_1:
				vals =	self.geo_fraction[0]
			case FeatureNames.GEO_FRAC_2:
				vals = self.geo_fraction[1]
			case _:
				raise KeyError(metric)

		keep = (self.labels == label) * self.mask
		vals = vals[keep].ravel()

		return vals[np.isfinite(vals)]

	def image_feature(self, feature:str, stat:str, harmonic:int=1) -> list:
		"""
		Compute image-level feature, collect all non-background labels.
		Return length L list containing the feature stats, where L is the number of labels.
		"""
		out = []
		for l in self.labels_unique:
			v = self.pixel_values(feature, label=l, harmonic=harmonic)
			if v.size == 0:
				out.append(np.nan)
				continue
			match stat:
				case StatsNames.MEDIAN:
					out.append(np.nanmedian(v))
				case StatsNames.MEAN:
					out.append(np.nanmean(v))
				case StatsNames.STD:
					out.append(np.nanstd(v))
				case StatsNames.IQR:
					q75, q25 = np.nanpercentile(v, [75, 25])
					out.append(q75 - q25)
				case StatsNames.P10:
					out.append(np.nanpercentile(v, 10))
				case StatsNames.P90:
					out.append(np.nanpercentile(v, 90))
				case _:
					raise KeyError(stat)
		return out

	def morphological_feature(self, morph_feat: str) -> list[float]:
		"""
		Return morphological feature values for each unique label.
		Computed on the raw labels mask, independent of the photon count threshold.
		"""
		from skimage.measure import regionprops
		props_map = {p.label: p for p in regionprops(self.labels)}
		out = []
		for l in self.labels_unique:
			props = props_map.get(l)
			if props is None:
				out.append(np.nan)
				continue
			match morph_feat:
				case MorphFeatureNames.AREA:
					out.append(float(props.area))
				case MorphFeatureNames.AXIAL_RATIO:
					out.append(float(props.axis_minor_length/props.axis_major_length))
				case MorphFeatureNames.PERIMETER:
					out.append(float(props.perimeter))
				case MorphFeatureNames.CIRCULARITY:
					p = props.perimeter
					out.append(4 * np.pi * props.area / p**2 if p > 0 else np.nan)
				case MorphFeatureNames.ECCENTRICITY:
					out.append(float(props.eccentricity))
				case MorphFeatureNames.SOLIDITY:
					out.append(float(props.solidity))
				case MorphFeatureNames.EXTENT:
					out.append(float(props.extent))
				case _:
					raise KeyError(morph_feat)
		return out

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

## --- Serialization helper --- ##
def _to_serializable(value):
	"""Convert a field value to a numpy array or a JSON-compatible scalar."""
	if isinstance(value, np.ndarray):
		return value
	if isinstance(value, np.generic): # numpy scalar
		return value.item()
	if isinstance(value, (uuid.UUID, Path)):
		return str(value)
	return value