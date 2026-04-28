from typing import TYPE_CHECKING

from qtpy.QtWidgets import (
	QWidget,
	QHBoxLayout,
	QVBoxLayout,
	QLabel,
	QPushButton,
	QFormLayout,
	QSpinBox,
	QDoubleSpinBox,
	QGroupBox
)
from qtpy.QtCore import Qt
import numpy as np
from napari import Viewer

from flimari.config.defaults import Defaults
from flimari.core import LayerManager

# HACK: Gotta clean up imports at some point
from .phasor.ui.calibration_widget import CalibrationWidget
from .phasor.ui.sample_manager_widget import SampleManagerWidget

class PhasorAnalysis(QWidget):
	def __init__(self, viewer:Viewer) -> None:
		super().__init__()
		self.viewer = viewer
		self.setWindowTitle("Phasor Analysis")
		# IMPORTANT: Initialize layer manager singleton
		LayerManager(self.viewer)
		self.defaults = Defaults()
		self._signal = None
		self._phasor = None
		self._calibration = None
		self._g = None
		self._s = None

		self._build()
		#self._test()

	def _build(self) -> None:
		layout = QVBoxLayout(self)

		cal_widget = CalibrationWidget(self)
		sample_manager_widget = SampleManagerWidget(self.viewer, cal_widget, self)
		layout.addWidget(cal_widget)
		layout.addWidget(sample_manager_widget)

