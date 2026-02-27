from typing import List, Dict, Any, TYPE_CHECKING

from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
	QWidget,
	QVBoxLayout,
	QGroupBox,
	QGridLayout,
	QLabel,
	QSpinBox,
	QComboBox,
	QPushButton,
	QListWidget,
	QListWidgetItem
)

import matplotlib.pyplot as plt

if TYPE_CHECKING:
	from ..core import Dataset

class PhasorControlPanel(QGroupBox):
	"""
	Control panel for phasor graph.
	Contains controls for adjusting plotting method and various filtering parameters.
	Also contains the ajustable list of datasets for this plotting instance.
	The user may select a non-empty subset from the list to work with.
	"""
	plotPhasor = Signal()
	mapRoi = Signal()

	def __init__(
		self,
		datasets: list["Dataset"],
		parent: QWidget|None = None
	) -> None:
		super().__init__("Control", parent)
		self._datasets = datasets

		self._build()

	## ------ UI ------ ##
	def _build(self) -> None:
		ctrl_grid = QGridLayout()
		ctrl_grid.setContentsMargins(5,10,5,5)
		self.setLayout(ctrl_grid)

		# Plot mode 
		mode_label = QLabel("Plot mode")
		self.mode_combo_box = QComboBox()
		self.mode_combo_box.addItem("contour")
		self.mode_combo_box.addItem("scatter")
		self.mode_combo_box.addItem("hist2d")
		ctrl_grid.addWidget(mode_label, 0, 0)
		ctrl_grid.addWidget(self.mode_combo_box, 0, 1)
		# Color map
		cmap_label = QLabel("Color map")
		self.cmap_combo_box = QComboBox()
		self.cmap_combo_box.addItem("by group")
		cmap_names = plt.colormaps()
		for name in cmap_names:
			self.cmap_combo_box.addItem(name)
		self.cmap_combo_box.setCurrentText("by group")
		ctrl_grid.addWidget(cmap_label, 0, 2)
		ctrl_grid.addWidget(self.cmap_combo_box, 0, 3)
		# Last row: Draw button
		self.btn_draw = QPushButton("Draw")
		self.btn_draw.clicked.connect(self._on_btn_draw_clicked)
		self.btn_map = QPushButton("Map ROI")
		self.btn_map.clicked.connect(self._on_btn_map_clicked)
		ctrl_grid.addWidget(self.btn_draw, 1, 0, 1, 2)
		ctrl_grid.addWidget(self.btn_map, 1, 2, 1, 2)

		# --- Right side: dataset management
		# A list widget where user can select dataset(s) to draw on the plot
		self.dataset_list = QListWidget()
		self.dataset_list.setSelectionMode(self.dataset_list.ExtendedSelection)
		self.dataset_list.setSpacing(0)
		for ds in self._datasets:
			list_item = QListWidgetItem(ds.display_name())
			self.dataset_list.addItem(list_item)
			# We want all datasets to be selected at the start
			# because we will immediately plot them
			list_item.setSelected(True)
		self.dataset_list.itemSelectionChanged.connect(self._on_selection_changed)
		self._on_selection_changed()
		ctrl_grid.addWidget(self.dataset_list, 0, 4, 2, 1)

	## ------ Public API ------ ##
	def get_selected_datasets(self) -> list["Dataset"]:
		return [
			self._datasets[self.dataset_list.row(item)]
			for item in self.dataset_list.selectedItems()
		]

	def get_params(self) -> Dict[str,Any]:
		"""
		Return a dictionary of control parameters. The keys match those in PhasorGraphWidget.draw_dataset.
		mode: plotting mode
		cmap: colormap or 'by group'
		"""
		params = {}
		params["mode"] = self.mode_combo_box.currentText()
		params["cmap"] = self.cmap_combo_box.currentText()
		return params

	## ------ Internal ------ ##
	def _on_btn_draw_clicked(self) -> None:
		self.plotPhasor.emit()

	def _on_btn_map_clicked(self) -> None:
		self.mapRoi.emit()

	def _on_selection_changed(self) -> None:
		"""
		Disable the draw button if no dataset item is selected.
		"""
		has_selected = len(self.dataset_list.selectedItems())>0
		self.btn_draw.setEnabled(has_selected)
