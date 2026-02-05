import os
from pathlib import Path
from typing import Dict, Optional, List, TYPE_CHECKING

import numpy as np

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (
	QWidget,
	QHBoxLayout,
	QVBoxLayout,
	QGridLayout,
	QGroupBox,
	QFormLayout,
	QPushButton,
	QLineEdit,
	QComboBox,
	QFileDialog,
	QLabel,
	QSpinBox,
	QListWidget,
	QListWidgetItem,
	QStyle
)

from flimari.core.napari import LayerManager
from flimari.core.io import load_signal
from flimari.core.widgets import ThemedButton, Indicator
from .phasor_plot_widget import PhasorPlotWidget
from .summary_widget import SummaryWidget
from .umap_widget import UMAPWidget
from ..core import Dataset

if TYPE_CHECKING:
	import xarray
	import napari
	# HACK: still feels a bit hacky
	from .calibration_widget import CalibrationWidget
	from ..core import Calibration

class DatasetRow(QWidget):
	show_clicked = Signal()

	def __init__(
		self,
		dataset:Dataset,
		viewer:"napari.Viewer",
		parent:Optional[QWidget]=None
	):
		super().__init__(parent)
		self.name = dataset.name
		self.dataset = dataset
		self.viewer = viewer
		self._list: QListWidget|None = None
		self._item: QListWidgetItem|None = None

		self._build()
		self._on_show()

	## ------ UI ------ ##
	def _build(self) -> None:
		layout = QHBoxLayout(self)
		self.label = QLabel(self.dataset.display_name())
		self.btn_delete = ThemedButton(icon="delete", viewer=self.viewer)
		self.btn_delete.setToolTip("Remove dataset")
		self.btn_delete.clicked.connect(self._on_removal)
		# TODO: Change behavior of eye button
		self.btn_show = ThemedButton(icon="visibility", viewer=self.viewer)
		self.btn_show.setToolTip("Focus in layer viewer")
		self.btn_show.clicked.connect(lambda : LayerManager().focus_on_layers(self.dataset.name))
		# Dropbox for selecting the lifetime to visualize
		self.lifetime_combo_box = QComboBox()
		self.lifetime_combo_box.setToolTip((
			"Select lifetime estimations.\n'non': original signal\n'phi': apparent phase lifetime\n"
			"'M': apparent modulation lifetime\nproj: projected lifetime\navg: average geometric-search lifetime"
		))
		self.lifetime_combo_box.addItems(["none", "phi", "M", "proj", "avg"])
		self.lifetime_combo_box.currentIndexChanged.connect(lambda i : self._on_show())
		# Indicator for calibration status
		self.indicator = Indicator()
		self.indicator.set_state("bad")
		# Since I am too lazy to implement a confirm delete dialog,
		# put label in the middle to prevent missclick of buttons
		layout.addWidget(self.btn_delete, 0)
		layout.addWidget(self.label, 1)
		layout.addWidget(self.lifetime_combo_box, 0)
		layout.addWidget(self.btn_show, 0)
		layout.addWidget(self.indicator, 0)

	## ------ Public API ------ ##
	def bind(self, listw:QListWidget, item:QListWidgetItem) -> None:
		"""
		Bind the associated list widget item and parent list so removal is easier.
		"""
		self._list = listw
		self._item = item

	def calibrate_phasor(self, calibration:"Calibration") -> None:
		"""
		Calibrate the phasor coordinate of dataset against the provided calibration.
		"""
		self.dataset.calibrate_phasor(calibration)
		self.indicator.set_state("ok")

	def mark_stale(self) -> None:
		"""
		Mark this dataset as stale (calibration has changed).
		"""
		if self.indicator.state() == "ok":
			self.indicator.set_state("warn")

	def set_text(self, text:str) -> None:
		self.label.setText(text)

	## ------ Internal ------ ##
	def _on_removal(self) -> None:
		if not (self._list and self._item):
			raise RuntimeError("Something is very wrong")
			return
		r = self._list.row(self._item) # Get the row index
		self._list.takeItem(r) # Remove from list
		self.deleteLater() # Delete the widget; let gc handle the list item
		# TODO: Remove the associated layers?

	def _on_show(self) -> None:
		if self.dataset is None:
			raise RuntimeError(f"Sample {self.name} does not have a dataset")
		# Show lifetime map
		match self.lifetime_combo_box.currentText():
			case "none":
				LayerManager().add_image(self.dataset.counts_filtered, name=self.dataset.name, overwrite=True)
			case "phi":
				LayerManager().add_image(self.dataset.phase_lifetime, name=self.dataset.name, overwrite=True)
			case "M":
				LayerManager().add_image(self.dataset.modulation_lifetime, name=self.dataset.name, overwrite=True)
			case "proj":
				LayerManager().add_image(self.dataset.normal_lifetime, name=self.dataset.name, overwrite=True)
			case "avg":
				LayerManager().add_image(self.dataset.avg_lifetime, name=self.dataset.name, overwrite=True)

class SampleManagerWidget(QWidget):
	def __init__(
		self,
		viewer: "napari.viewer.Viewer",
		cal_widget: "CalibrationWidget",
		parent: QWidget|None = None,
	):
		# NOTE: The viewer is passed around because it is needed for determining 
		# the icon to use depending on lihgt and dark theme.
		super().__init__(parent)
		self.viewer = viewer
		# HACK: Still not a big fan of how this dependency is set up.
		# Ideally we don't need to inject this dependency at all.
		self.calibration = cal_widget.calibration
		# Set up connect to update status od datasets
		cal_widget.calibrationChanged.connect(self._mark_all_stale)
		self.param_names: list[str] = ["min_count", "max_count", "kernel_size", "repetition"]

		self._build()

	## ------ UI ------ ##
	def _build(self) -> None:
		root = QVBoxLayout()
		self.setLayout(root)

		#  --- Dataset controls --- 
		dataset_control = QGroupBox("Dataset control")
		dataset_control_layout = QGridLayout(dataset_control)
		dataset_control_layout.setContentsMargins(5,10,5,5)
		root.addWidget(dataset_control)

		# File loading
		self.le_channel = QLabel()
		self.le_channel.setText("Channel:")
		self.channel_selector = QSpinBox()
		self.channel_selector.setRange(1, 99)
		self.btn_browse_file = QPushButton("Browse file...")
		self.btn_browse_file.clicked.connect(self._on_browse_file)
		dataset_control_layout.addWidget(self.le_channel, 0, 0)
		dataset_control_layout.addWidget(self.channel_selector, 0, 1)
		dataset_control_layout.addWidget(self.btn_browse_file, 0, 2, 1, 2)

		# Grouping
		self.le_group = QLineEdit()
		self.le_group.setPlaceholderText("Enter group name")
		self.btn_assign_group = QPushButton("Group selected")
		self.btn_assign_group.setToolTip("Assign selected datasets to the group name entered above")
		self.btn_assign_group.clicked.connect(self._on_btn_assign_group_clicked)
		dataset_control_layout.addWidget(self.le_group, 1, 0)
		dataset_control_layout.addWidget(self.btn_assign_group, 1, 1)
		# Calibration
		self.calibration_mode = QComboBox()
		self.calibration_mode.addItem("Mapping")
		self.calibration_mode.addItem("IRF")
		self.calibration_mode.setToolTip(
			"Select phasor calibration method.\n"
			"'Mapping': Transform phasors using a sample with a known mono-exponential lifetime.\n"
			"'IRF': Deconvolution using the Instrument Response Function/SHG."
		)
		self.btn_calibrate = QPushButton("Calibrate selected")
		self.btn_calibrate.clicked.connect(self._on_calibrate_selected)
		dataset_control_layout.addWidget(self.calibration_mode, 1, 2)
		dataset_control_layout.addWidget(self.btn_calibrate, 1, 3)

		# Filter control
		# Second row: photon count thresholding
		min_count_label = QLabel("Min photon count")
		max_count_label = QLabel("Max photon count")
		self.min_count = QSpinBox()
		self.min_count.setRange(0, int(1e9))
		self.min_count.setValue(0)
		self.max_count = QSpinBox()
		self.max_count.setRange(1, int(1e9))
		self.max_count.setValue(10000)
		dataset_control_layout.addWidget(min_count_label, 2, 0)
		dataset_control_layout.addWidget(self.min_count, 2, 1)
		dataset_control_layout.addWidget(max_count_label, 2, 2)
		dataset_control_layout.addWidget(self.max_count, 2, 3)
		# Second row: median filter
		kernel_size_label = QLabel("Median filter size")
		repetition_label = QLabel("Median filter repetition")
		self.kernel_size = QSpinBox()
		self.kernel_size.setRange(2, 99)
		self.kernel_size.setValue(3)
		self.repetition = QSpinBox()
		self.repetition.setRange(0, 99)
		self.repetition.setValue(0)
		dataset_control_layout.addWidget(kernel_size_label, 3, 0)
		dataset_control_layout.addWidget(self.kernel_size, 3, 1)
		dataset_control_layout.addWidget(repetition_label, 3, 2)
		dataset_control_layout.addWidget(self.repetition, 3, 3)
		# Apply filter button
		self.btn_apply_filter = QPushButton("Apply filter")
		self.btn_apply_filter.clicked.connect(self._on_btn_apply_filter_clicked)
		dataset_control_layout.addWidget(self.btn_apply_filter, 4, 0, 1, 4)
		# To make the special text work as intended,
		# while making the instantiation easy to understand,
		# we decrement the minimum of these spinbox by 1
		for name in self.param_names:
			spinbox = getattr(self, name)
			spinbox.setSpecialValueText("...")
			spinbox.setMinimum(spinbox.minimum()-1)

		# --- Dataset list ---
		self.dataset_list = QListWidget()
		self.dataset_list.setSelectionMode(self.dataset_list.ExtendedSelection)
		self.dataset_list.setSpacing(0)
		self.dataset_list.itemSelectionChanged.connect(self._on_selection_changed)
		root.addWidget(self.dataset_list)

		# Open phasor plot button
		self.btn_visualize = QPushButton("Visualize selected in phasor plot")
		self.btn_visualize.clicked.connect(self._on_visualize_selected)
		root.addWidget(self.btn_visualize)

		# Summary statistics access button
		self.btn_summary = QPushButton("View/Export Summary")
		self.btn_summary.setToolTip("View/Export summary statistics of selected samples")
		self.btn_summary.clicked.connect(self._on_btn_summary_clicked)
		root.addWidget(self.btn_summary)

		# UMAP analysis button
		self.btn_umap = QPushButton("UMAP Analysis")
		self.btn_umap.setToolTip("Perform UMAP analysis on selected datasets")
		self.btn_umap.clicked.connect(self._on_btn_umap_clicked)
		root.addWidget(self.btn_umap)

		# Initialize the state of all selection related buttons
		self._on_selection_changed()

	## ------ Public API ------ ##
	def get_selected_rows(self) -> List[DatasetRow]:
		"""
		Return the selected DatasetRow QWidget.
		"""
		selected = self.dataset_list.selectedItems()
		return [self.dataset_list.itemWidget(item) for item in selected]

	def get_selected_datasets(self) -> List[Dataset]:
		"""
		Return the list of selected Dataset dataclass instance.
		"""
		return [row.dataset for row in self.get_selected_rows()]

	## ------ Internal ------ ##
	def _on_browse_file(self) -> None:
		"""
		Prompt for file selection, then load file as phasorpy signal.
		Store the loaded signal as Dataset object along with metadata.
		Then create a DatasetRow and insert into the list widget. 
		"""
		paths, _ = QFileDialog.getOpenFileNames(
			self,
			"Select sample file(s)",
			"",
			"FLIM files (*.tif *.tiff *.ptu);;All files (*)"
		)
		selected_channel = self.channel_selector.value()-1
		for path in paths:
			ds = Dataset(path=path, channel=selected_channel)

			item = QListWidgetItem(self.dataset_list)
			row = DatasetRow(ds, self.viewer)
			row.bind(self.dataset_list, item) 
			item.setSizeHint(row.sizeHint())
			self.dataset_list.addItem(item)
			self.dataset_list.setItemWidget(item, row)
	
	def _on_selection_changed(self) -> None:
		"""
		Only for determining the active state of compute and visualize buttons.
		Disable the buttons if no item is selected.
		"""
		has_selected = len(self.dataset_list.selectedItems())>0
		self.btn_assign_group.setEnabled(has_selected)
		self.btn_calibrate.setEnabled(has_selected)
		self.btn_apply_filter.setEnabled(has_selected)
		self.btn_visualize.setEnabled(has_selected)
		self.btn_summary.setEnabled(has_selected)
		self.btn_umap.setEnabled(has_selected)
		if has_selected:
			selection_values = self._validate_datasets_consistency(self.get_selected_datasets())
			for k, v in selection_values.items():
				spinbox = getattr(self, k)
				spinbox.setValue(spinbox.minimum() if v is None else v)

	def _on_calibrate_selected(self) -> None:
		"""
		Get the DatasetRow widget in the list items and make them compute phasor given the calibration.
		"""
		rows = self.get_selected_rows()
		for r in rows:
			r.calibrate_phasor(self.calibration)

	def _on_btn_assign_group_clicked(self) -> None:
		"""
		Set the group of selected datasets to the group specified in le_group.
		Then refresh the names of selected list items.
		"""
		group = self.le_group.text()
		if not group: group = "default"
		for item in self.dataset_list.selectedItems():
			dataset_row = self.dataset_list.itemWidget(item)
			dataset = dataset_row.dataset
			dataset.set_group(group)
			dataset_row.set_text(dataset.display_name())

	def _on_btn_apply_filter_clicked(self) -> None:
		dataset_rows = self.get_selected_rows()
		param_vals = self._get_filter_param_values()
		for row in dataset_rows:
			ds = row.dataset
			for name in self.param_names:
				# Only set if the value is not None, i.e. the spinbox is not special text
				if param_vals[name] is not None:
					setattr(ds, name, param_vals[name])
			ds.apply_filters()
			row._on_show()

	def _get_filter_param_values(self) -> dict[str,int]:
		param_vals = {}
		for name in self.param_names:
			spinbox = getattr(self, name)
			val = spinbox.value()
			param_vals[name] = None if val == spinbox.minimum() else val
		return param_vals
	
	def _on_visualize_selected(self) -> None:
		"""
		Take all selected datasets, filter for those that have phasor computed,
		Instantiate a new PhasorPlorWidget instance and initialize with the datasets.
		If no selected datasets have phasor, simply return.
		"""
		datasets = self.get_selected_datasets()
		if len(datasets) <= 0: return
		# Make plot widget
		phasor_plot_widget = PhasorPlotWidget(self.viewer, datasets, frequency=self.calibration.frequency)
		# NOTE: For some reason, area="right" leads to layout problems of the canvas. I'm unsure why.
		phasor_plot_dock = self.viewer.window.add_dock_widget(phasor_plot_widget, name="Phasor Plot", area="bottom")
		phasor_plot_dock.setFloating(True)
		phasor_plot_dock.setAllowedAreas(Qt.NoDockWidgetArea)

	def _on_btn_summary_clicked(self) -> None:
		datasets = self.get_selected_datasets()
		if len(datasets) <= 0: return
		# Make summary widget
		summary_widget = SummaryWidget(datasets)
		dock = self.viewer.window.add_dock_widget(summary_widget, name="Phasor Summary", area="bottom")
		dock.setFloating(True)
		# TODO: Perhaps we want to set this as undockable as well?

	def _on_btn_umap_clicked(self) -> None:
		datasets = self.get_selected_datasets()
		if len(datasets) <= 0: return
		# Make UMAP widget
		umap_widget = UMAPWidget(datasets)
		dock = self.viewer.window.add_dock_widget(umap_widget, name="UMAP Analysis", area="bottom")
		dock.setFloating(True)

	def _mark_all_stale(self) -> None:
		# DANGER: manually changing phi_0 and m_0 does not trigger this
		for i in range(self.dataset_list.count()):
			item = self.dataset_list.item(i)
			row = self.dataset_list.itemWidget(item)
			row.mark_stale()

	def _validate_datasets_consistency(self, datasets:list["Dataset"]) -> dict[str,int|None]:
		"""
		Return the filter parameters stored in selected datasets.
		If the parameter value match for all selected datasets, return the value.
		Otherwise, return None
		"""
		attrs = ("min_count", "max_count", "kernel_size", "repetition")
		baseline = datasets[0]
		values = {name: getattr(baseline, name) for name in attrs}

		# Compare subsequent datasets to the baseline, invalidating if mismatch.
		for ds in datasets[1:]:
			for name in attrs:
				if values[name] is not None and getattr(ds, name) != values[name]:
					values[name] = None

		return values
