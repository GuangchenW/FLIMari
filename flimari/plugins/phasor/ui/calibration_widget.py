from typing import Dict, Optional

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
	QWidget,
	QHBoxLayout,
	QVBoxLayout,
	QGroupBox,
	QFormLayout,
	QGridLayout,
	QPushButton,
	QLineEdit,
	QFileDialog,
	QLabel,
	QSpinBox,
	QComboBox,
	QStyle
)

from flimari.core.widgets import AutoDoubleSpinBox
from ..core import Calibration


class CalibrationWidget(QGroupBox):
	"""
	UI for loading a reference file for phasor calibration.
	"""
	calibrationChanged = Signal()

	def __init__(self, parent:Optional[QWidget]=None) -> None:
		super().__init__(parent)
		self._ref_path: str = ""
		self.calibration = Calibration() # Calibration info container

		self._build()
		#self._apply_mode()

	## ------ Public API ------ ##
	def get_calibration(self):
		return self.calibration

	## ------ UI ------ ##
	def _build(self) -> None:
		self.setTitle("Reference (Calibration)")
		layout = QVBoxLayout()
		self.setLayout(layout)

		header = QGridLayout()
		layout.addLayout(header)
		# Channel selection
		# This must be determined by the user before loading the file
		lb_channel = QLabel("Channel:")
		self.channel_selector = QSpinBox()
		self.channel_selector.setRange(1, 99)
		header.addWidget(lb_channel, 0, 0)
		header.addWidget(self.channel_selector, 0, 1)
		# Calibration mode
		lb_mode = QLabel("Calibration mode:")
		header.addWidget(lb_mode, 0, 2)
		# Mode selection
		self.mode_selector = QComboBox()
		self.mode_selector.addItems([self.calibration.MODE_MAPPING, self.calibration.MODE_IRF])
		self.mode_selector.currentTextChanged.connect(self._on_mode_changed)
		header.addWidget(self.mode_selector, 0, 3)
		# File path display
		self.le_ref_status = QLineEdit()
		self.le_ref_status.setReadOnly(True)
		self.le_ref_status.setPlaceholderText("No file selected")
		header.addWidget(self.le_ref_status, 1, 0, 1, 3)
		# File selection button
		self.btn_browse_ref = QPushButton("Browse file...")
		self.btn_browse_ref.clicked.connect(self._on_browse_file)
		header.addWidget(self.btn_browse_ref, 1, 3)

		# Lifetime mapping-only acquisition parameters
		self.param_container = QWidget()
		param_form = QGridLayout(self.param_container)
		layout.addWidget(self.param_container, 1)
		# Params
		lb_laser_freq = QLabel("Laser freq.")
		self.laser_freq = AutoDoubleSpinBox()
		self.laser_freq.set_range(1.0, 1e3)
		self.laser_freq.set_suffix("MHz")
		self.laser_freq.set_value(80.0, as_default=True)
		param_form.addWidget(lb_laser_freq, 0, 0)
		param_form.addWidget(self.laser_freq, 0, 1)

		lb_ref_lifetime = QLabel("Ref. lifetime")
		self.ref_lifetime = AutoDoubleSpinBox()
		self.ref_lifetime.set_suffix("ns")
		self.ref_lifetime.set_value(4, as_default=True)
		param_form.addWidget(lb_ref_lifetime, 0, 2)
		param_form.addWidget(self.ref_lifetime, 0, 3)

		# Calibration button
		self.btn_compute = QPushButton("Compute calibration")
		self.btn_compute.clicked.connect(self._on_calibration_btn_pressed)
		self.btn_compute.setEnabled(False)
		param_form.addWidget(self.btn_compute, 1, 0, 1, 4)

		# Calibration parameters
		lb_phase_shift = QLabel("Phase")
		self.phase_shift = QLineEdit()
		self.phase_shift.setReadOnly(True)
		self.phase_shift.setText(str(0.0))
		param_form.addWidget(lb_phase_shift, 2, 0)
		param_form.addWidget(self.phase_shift, 2, 1)

		lb_modulation_shift = QLabel("Modulation")
		self.modulation_shift = QLineEdit()
		self.modulation_shift.setReadOnly(True)
		self.modulation_shift.setText(str(1.0))
		param_form.addWidget(lb_modulation_shift, 2, 2)
		param_form.addWidget(self.modulation_shift, 2, 3)

	## ------ Callbacks ------ ##
	def _on_browse_file(self) -> None:
		path, _ = QFileDialog.getOpenFileName(
			self,
			"Select reference file",
			self._ref_path or "",
			"FLIM files (*.tif *.tiff *.ptu);;All files (*)"
		)
		if not path:
			self.le_ref_status.setText("Invalid or unsupported file")
			return

		self._ref_path = path
		self.le_ref_status.setText("Loading...")

		# Load reference file and update status to file path
		try:
			channel = self.channel_selector.value()-1
			self.calibration.load(path, channel)
			self.calibration.mode = self.mode_selector.currentText
		except Exception as e:
			self.le_ref_status.setText(f"Error: {type(e).__name__}")
			return

		self.le_ref_status.setText(path)

		# Try to detect and set laser frequency
		freq = self.calibration.get_signal_attribute("frequency")
		if not freq is None:
			self.laser_freq.set_value(freq)

		# Finally, enable the calibration button
		self.btn_compute.setEnabled(True)

	def _on_mode_changed(self, mode:str) -> None:
		self.calibration.mode = mode

		is_mapping = (mode == self.calibration.MODE_MAPPING)
		self.param_container.setVisible(is_mapping)
		
	def _on_calibration_btn_pressed(self) -> None:
		frequency = self.laser_freq.value()
		lifetime = self.ref_lifetime.value()
		self.calibration.calibrate(frequency, lifetime)
		phi, m = self.calibration.get_calibration()
		self.phase_shift.setText(str(phi[0]))
		self.modulation_shift.setText(str(m[0]))
		self.calibrationChanged.emit()
