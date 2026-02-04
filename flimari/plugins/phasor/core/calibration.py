from pathlib import Path
import numpy as np
from phasorpy.phasor import phasor_from_signal, phasor_center, phasor_transform, phasor_divide
from phasorpy.lifetime import phasor_from_lifetime, polar_from_reference_phasor

from flimari.core.io import load_signal

class Calibration:

	MODE_MAPPING = "Reference phasor"
	MODE_IRF = "IRF"

	def __init__(self) -> None:
		self.path: str|Path = "" # Path to reference
		self.signal = None # Reference signal
		self.ref_mean = None # Reference signal intensities
		self.ref_real = None # Reference signal real component (g)
		self.ref_imag = None # Reference signal imaginary component (s)

		# Laser frequency of used for calibration
		# (not necessarily from metadata, may be set by user)
		self.frequency: float = 0.0
		self.phase_zero: float = 0.0 # phi calibration
		self.modulation_zero: float = 1.0 # m calibration

		self.mode: Literal["Mapping", "IRF"] = "Mapping" # Method of calibration

	def load(self, path:str|Path, channel:int=0) -> None:
		"""
		Load reference signals and compute phasor.
		"""
		self.signal = load_signal(path, channel)
		self.path = path

		# Compute phasor coordinates
		self.ref_mean, self.ref_real, self.ref_imag = phasor_from_signal(self.signal, axis='H', harmonic=[1,2])

	def calibrate(self, frequency, lifetime) -> None:
		if self.signal is None:
			raise ValueError("Reference signal is None")

		# Store frequency used for calibration
		self.frequency = frequency

		# Get phase and modulation shifts
		self.phase_zero, self.modulation_zero = polar_from_reference_phasor(
			*phasor_center(
				self.ref_mean,
				self.ref_real,
				self.ref_imag,
			)[1:],
			*phasor_from_lifetime(
				frequency,
				lifetime,
			),
		)
		print(self.phase_zero.shape)

	def compute_calibrated_phasor(self, real, imag):
		"""
		Transform the given phasor coordinates using self.phase_zero and self.modulation_zero.
		Returns the transformed real and imaginary components.
		"""
		if self.mode == "Mapping":
			# We need to add empty axis so the phase and modulation harmonics can be broadcasted correctly.
			return phasor_transform(real, imag, self.phase_zero[:,None,None], self.modulation_zero[:,None,None])
		elif self.mode == "IRF":
			# Deconvolution through complex division
			return phasor_divide(real, imag, self.ref_real, self.ref_imag)
		else:
			raise ValueError("Unknown calibration method: %s" % self.mode)

	def get_signal_attribute(self, attr:str):
		"""
		Return the signal attribute (if exists) or None.
		"""
		return self.signal.attrs.get(attr, None)

	def get_calibration(self):
		"""
		Return the phase and modulation shift.
		For now, only handles the 2D case.
		"""
		return self.phase_zero, self.modulation_zero