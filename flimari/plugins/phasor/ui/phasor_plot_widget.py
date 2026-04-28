from typing import Optional, TYPE_CHECKING

import numpy as np

from qtpy.QtWidgets import (
	QWidget,
	QHBoxLayout,
	QVBoxLayout,
)
from matplotlib.colors import to_rgb

from flimari.core import LayerManager
from ..core import labels_from_roi
from .phasor_plot_graph import PhasorGraphWidget
from .phasor_plot_control import PhasorControlPanel
from .phasor_plot_roi import RoiManagerWidget

if TYPE_CHECKING:
	import napari
	from ..core import Dataset

class PhasorPlotWidget(QWidget):
	"""
	A QWidget for hosting a phasorpy PhasorPlot and the associated matplotlib figure.
	"""
	def __init__(
		self, 
		viewer: "napari.Viewer",
		datasets: list["Dataset"],
		frequency: float|None = None,
		parent: QWidget|None = None,
	) -> None:
		super().__init__(parent)
		self.viewer = viewer
		self.frequency: float|None = frequency
		self._datasets = datasets

		self._build()
		# Draw graph with default parameters
		self._on_plot_phasor()

	## ------ UI ------ ##
	def _build(self) -> None:
		root = QVBoxLayout(self)
		root.setContentsMargins(5,5,5,5)

		# Parameters control panel
		self.control_panel = PhasorControlPanel(self._datasets)
		self.control_panel.plotPhasor.connect(self._on_plot_phasor)
		self.control_panel.mapRoi.connect(self._on_map_roi)
		root.addWidget(self.control_panel)

		# Phasor plot and roi management
		bottom = QHBoxLayout()
		root.addLayout(bottom, stretch=1)
		# Left: PhasorPlot
		# TODO: DPI and pixels from config files?
		self.phasor_graph_widget = PhasorGraphWidget(self.frequency, 120, 480)
		bottom.addWidget(self.phasor_graph_widget, stretch=1)

		# Right: Cirlular ROI management panel
		self.roi_manager = RoiManagerWidget(self.phasor_graph_widget.get_ax(), self.viewer)
		bottom.addWidget(self.roi_manager, stretch=0)

		# Connect ROI manager to the graph click signal
		self.phasor_graph_widget.canvasClicked.connect(self.roi_manager.move_selected_roi)

	## ------ Internal ------ ##
	def _on_map_roi(self) -> None:
		"""
		Get the list of ROIs, make label and add layer for each dataset.
		Uses the processed (filtered) g, s coords instead of raw real, imag.
		"""
		roi_list = self.roi_manager.collect_roi()
		color_dict = { None:(0,0,0) }
		for i, roi in enumerate(roi_list):
			color_dict[i+1] = to_rgb(roi.color) # Covert to 0-1 float RGB tuple
		for ds in self._datasets:
			labels = labels_from_roi(*ds.get_phasor(), roi_list)
			LayerManager().add_label(
				labels,
				name=ds.name,
				display_name = ds.name+".roi",
				cdict=color_dict,
				overwrite=True
			)

	def _on_plot_phasor(self) -> None:
		datasets = self.control_panel.get_selected_datasets()
		params = self.control_panel.get_params()
		if len(datasets) <= 0: return # Should not happen but safeguard

		self.phasor_graph_widget.clear()
		self.phasor_graph_widget.draw_datasets(datasets, **params)
