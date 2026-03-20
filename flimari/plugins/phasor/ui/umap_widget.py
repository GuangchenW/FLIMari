from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

import numpy as np

from qtpy.QtWidgets import (
	QWidget,
	QHBoxLayout,
	QVBoxLayout,
	QGridLayout,
	QGroupBox,
	QPushButton,
	QComboBox,
	QLabel,
	QListWidget,
	QListWidgetItem,
	QAbstractItemView,
	QCheckBox,
	QSpinBox,
	QDoubleSpinBox,
	QMessageBox,
	QFileDialog,
)

from flimari.core.widgets import MPLGraph
from flimari.plugins.phasor.core import FeatureNames, StatsNames, Dataset
from flimari.plugins.phasor.ml import NormalizationModes, FeatureWorkspace, normalize, do_pca, do_umap

import pandas as pd

try:
	from sklearn.cluster import KMeans, DBSCAN
except Exception:  # pragma: no cover
	KMeans = DBSCAN = None

class UMAPWidget(QWidget):
	"""
	Image-level UMAP + clustering (KMeans, DBSCAN).

	Each Dataset (image) -> one point in UMAP space.
	Features are computed by aggregating pixel features.
	"""

	def __init__(self, datasets:list["Dataset"], parent:QWidget|None = None):
		super().__init__(parent)
		self._datasets = datasets

		# Cached results for recoloring and export
		self._used_datasets: list["Dataset"] = []           # aligned to embedding rows
		self._feature_workspace: FeatureWorkspace = FeatureWorkspace()

		self._kmeans_labels: np.ndarray | None = None       # (n,)
		self._dbscan_labels: np.ndarray | None = None       # (n,)

		# Image-level inputs
		# NOTE: "g" and "s" use the chosen harmonic; others are scalar images.
		self.feature_items = FeatureNames.ALL

		# Aggregations computed per metric -> become final features
		self.stat_items = StatsNames.ALL

		self._build()
		self._set_status("Ready")

	## ------ UI ------ ##

	def _build(self) -> None:
		root = QVBoxLayout()
		self.setLayout(root)

		# Top control box layout
		ctrl_box = QHBoxLayout()
		root.addLayout(ctrl_box)

		# --- Left: feature selection --- #
		left = QVBoxLayout()
		# Features selection checklist
		left.addWidget(QLabel("Image features:"))
		self.feature_list = QListWidget()
		self.feature_list.setSelectionMode(QAbstractItemView.NoSelection)
		for feat in self.feature_items:
			it = QListWidgetItem(feat)
			it.setFlags(it.flags() | 16) # set checkable
			it.setCheckState(2 if feat in (FeatureNames.G, FeatureNames.S, FeatureNames.PROJ_LIFETIME) else 0)  # defaults
			self.feature_list.addItem(it)
		left.addWidget(self.feature_list)

		left.addWidget(QLabel("Feature stats:"))
		self.stats_list = QListWidget()
		self.stats_list.setSelectionMode(QAbstractItemView.NoSelection)
		for s in self.stat_items:
			it = QListWidgetItem(s)
			it.setFlags(it.flags() | 16) # set checkable
			it.setCheckState(2 if s in (StatsNames.MEDIAN, StatsNames.IQR) else 0) # defaults
			self.stats_list.addItem(it)
		left.addWidget(self.stats_list)

		# Harmonic selection
		harm_row = QHBoxLayout()
		harm_row.addWidget(QLabel("Phasor harmonic for g/s:"))
		self.harmonic_combo = QComboBox()
		self.harmonic_combo.addItems(["1", "2"])
		harm_row.addWidget(self.harmonic_combo)
		left.addLayout(harm_row)

		ctrl_box.addLayout(left)

		# --- Middle: dataset list --- #
		middle = QVBoxLayout()
		middle.addWidget(QLabel("Datasets"))
		self.dataset_list = QListWidget()
		self.dataset_list.setSelectionMode(self.dataset_list.ExtendedSelection)
		self.dataset_list.setSpacing(0)
		for ds in self._datasets:
			list_item = QListWidgetItem(ds.display_name())
			self.dataset_list.addItem(list_item)
			list_item.setSelected(True)
		self.dataset_list.itemSelectionChanged.connect(self._on_selection_changed)
		middle.addWidget(self.dataset_list)
		ctrl_box.addLayout(middle)

		# --- Right: UMAP + clustering controls --- #
		right = QVBoxLayout()
		ctrl_box.addLayout(right)
		# Preprocessing params
		pp_group = QGroupBox("Preprocessing")
		right.addWidget(pp_group)
		pp_grid = QGridLayout(pp_group)
		pp_grid.setContentsMargins(5,10,5,5)
		pp_grid.addWidget(QLabel("Normalization method:"), 0, 0)
		self.scaling_combo = QComboBox()
		self.scaling_combo.addItems(NormalizationModes.ALL)
		pp_grid.addWidget(self.scaling_combo, 0, 1, 1, 2)

		self.pca_check = QCheckBox("PCA before UMAP")
		self.pca_check.setChecked(True)
		pp_grid.addWidget(self.pca_check, 1, 0)

		self.pca_components = QSpinBox()
		self.pca_components.setMinimum(2)
		self.pca_components.setMaximum(32)
		self.pca_components.setValue(10)
		self.pca_components.setToolTip("Max PCA components (clamped to n_samples-1 and n_features).")
		pp_grid.addWidget(QLabel("Max components:"), 1, 1)
		pp_grid.addWidget(self.pca_components, 1, 2)

		# UMAP params
		umap_group = QGroupBox("UMAP params")
		right.addWidget(umap_group)
		umap_grid = QGridLayout(umap_group)
		umap_grid.setContentsMargins(5,10,5,5)
		umap_grid.addWidget(QLabel("n_neighbors:"), 0, 0)
		self.nn_spin = QSpinBox()
		self.nn_spin.setMinimum(2)
		self.nn_spin.setMaximum(200)
		self.nn_spin.setValue(10)
		umap_grid.addWidget(self.nn_spin, 0, 1)

		umap_grid.addWidget(QLabel("min_dist:"), 1, 0)
		self.md_spin = QDoubleSpinBox()
		self.md_spin.setDecimals(3)
		self.md_spin.setSingleStep(0.05)
		self.md_spin.setMinimum(0.0)
		self.md_spin.setMaximum(0.999)
		self.md_spin.setValue(0.3)
		umap_grid.addWidget(self.md_spin, 1, 1)

		umap_grid.addWidget(QLabel("dist_metric:"), 2, 0)
		self.umap_metric = QComboBox()
		self.umap_metric.addItems(["euclidean", "manhattan", "cosine"])
		umap_grid.addWidget(self.umap_metric, 2, 1)

		# --- UMAP buttons --- #
		self.btn_run = QPushButton("Run UMAP")
		self.btn_run.clicked.connect(self._on_run_umap_clicked)
		right.addWidget(self.btn_run)

		self.btn_clear = QPushButton("Clear plot")
		self.btn_clear.clicked.connect(self._on_clear_clicked)
		right.addWidget(self.btn_clear)

		self.btn_export = QPushButton("Export embedding (CSV)")
		self.btn_export.clicked.connect(self._on_export_clicked)
		right.addWidget(self.btn_export)

		# --- Clustering --- #
		right.addSpacing(10)
		cluster_group = QGroupBox("Clustering")
		right.addWidget(cluster_group)
		cluster_grid = QGridLayout(cluster_group)
		cluster_grid.setContentsMargins(5,10,5,5)
		# KMeans
		self.kmeans_check = QCheckBox("KMeans")
		self.kmeans_check.setChecked(True)
		cluster_grid.addWidget(self.kmeans_check, 0, 0)

		cluster_grid.addWidget(QLabel("num_cluster:"), 0, 1)
		self.k_spin = QSpinBox()
		self.k_spin.setMinimum(2)
		self.k_spin.setMaximum(100)
		self.k_spin.setValue(3)
		cluster_grid.addWidget(self.k_spin, 0, 2)

		# DBSCAN
		self.dbscan_check = QCheckBox("DBSCAN")
		self.dbscan_check.setChecked(False)
		cluster_grid.addWidget(self.dbscan_check, 1, 0)

		dbscan_grid = QGridLayout()
		cluster_grid.addLayout(dbscan_grid, 1, 1, 1, 2)

		dbscan_grid.addWidget(QLabel("eps:"), 0, 0)
		self.db_eps = QDoubleSpinBox()
		self.db_eps.setDecimals(3)
		self.db_eps.setSingleStep(0.05)
		self.db_eps.setMinimum(0.001)
		self.db_eps.setMaximum(1000.0)
		self.db_eps.setValue(0.5)
		dbscan_grid.addWidget(self.db_eps, 0, 1)

		dbscan_grid.addWidget(QLabel("min_samples:"), 1, 0)
		self.db_min_samples = QSpinBox()
		self.db_min_samples.setMinimum(2)
		self.db_min_samples.setValue(5)
		dbscan_grid.addWidget(self.db_min_samples, 1, 1)

		# Cluster button
		self.btn_cluster = QPushButton("Run clustering")
		self.btn_cluster.clicked.connect(self._on_run_clustering_clicked)
		right.addWidget(self.btn_cluster)

		# Annotations
		right.addSpacing(10)
		anno_row = QHBoxLayout()
		right.addLayout(anno_row)
		anno_row.addWidget(QLabel("Color by:"))
		self.color_combo = QComboBox()
		self.color_combo.addItems(["group", "kmeans", "dbscan"])
		self.color_combo.currentTextChanged.connect(lambda _: self._redraw())
		anno_row.addWidget(self.color_combo)

		self.annotate_check = QCheckBox("Annotate points")
		self.annotate_check.setChecked(False)
		self.annotate_check.stateChanged.connect(lambda _: self._redraw())
		anno_row.addWidget(self.annotate_check)

		# Status label
		self.status_label = QLabel("")
		right.addWidget(self.status_label)

		# Bottom: Graph
		self.graph = MPLGraph()
		root.addWidget(self.graph)

		# Init button states
		self._on_selection_changed()

	# ---------------- Public helpers ----------------

	def get_selected_datasets(self) -> list["Dataset"]:
		return [
			self._datasets[self.dataset_list.row(item)]
			for item in self.dataset_list.selectedItems()
		]

	## ------ Internal ------ ##
	def _set_status(self, status:str) -> None:
		self.status_label.setText(status)

	def _selected_metrics(self) -> list[str]:
		out = []
		for i in range(self.feature_list.count()):
			it = self.feature_list.item(i)
			if it.checkState() == 2:
				out.append(it.text())
		return out

	def _selected_stats(self) -> list[str]:
		out = []
		for i in range(self.stats_list.count()):
			it = self.stats_list.item(i)
			if it.checkState() == 2:
				out.append(it.text())
		return out

	def _build_feature_matrix(
		self,
		datasets: list["Dataset"],
		features: list[str],
		stats: list[str],
		harmonic: int,
	):
		self._feature_workspace.build_features(datasets, features, stats, harmonic)


	def _preprocess(self):
		mode = self.scaling_combo.currentText()
		normalize(self._feature_workspace, mode)

		if self.pca_check.isChecked():
			# Clip components to feasible range
			n_samples, n_features = self._feature_workspace.feature_matrix.shape
			max_comps = min(self.pca_components.value(), n_features, max(1, n_samples - 1))
			if max_comps >= 2:
				do_pca(self._feature_workspace, max_comps)

	def _run_umap(self):
		n_samples = self._feature_workspace.feature_matrix.shape[0]
		n_neighbors = min(self.nn_spin.value(), max(2, n_samples - 1))

		do_umap(
			self._feature_workspace,
			n_neighbors = n_neighbors,
			min_dist = self.md_spin.value(),
			metric = self.umap_metric.currentText(),
		)

	def _run_kmeans(self, emb: np.ndarray) -> np.ndarray:
		if KMeans is None:
			raise RuntimeError("scikit-learn is required for KMeans.")
		n = emb.shape[0]
		k = min(self.k_spin.value(), n)
		if k < 2:
			raise ValueError("KMeans requires k>=2 and at least 2 samples.")
		try:
			model = KMeans(n_clusters=k, random_state=0, n_init="auto")
		except TypeError:
			model = KMeans(n_clusters=k, random_state=0, n_init=10)
		return model.fit_predict(emb)

	def _run_dbscan(self, emb: np.ndarray) -> np.ndarray:
		if DBSCAN is None:
			raise RuntimeError("scikit-learn is required for DBSCAN.")
		eps = float(self.db_eps.value())
		min_samples = int(self.db_min_samples.value())
		return DBSCAN(eps=eps, min_samples=min_samples).fit_predict(emb)

	# ---------------- Plotting ----------------

	def _redraw(self) -> None:
		if not hasattr(self._feature_workspace, "umap") or len(self._used_datasets) == 0:
			return

		ax = self.graph.get_ax()
		ax.clear()

		x = self._feature_workspace.umap[:, 0]
		y = self._feature_workspace.umap[:, 1]

		color_mode = self.color_combo.currentText()

		if color_mode == "group":
			# Plot each group separately so legend is meaningful
			idx = 0
			used_labels = set()
			for md in self._feature_workspace.metadata:
				group = md["group"]
				count = md["count"]
				ax.scatter(
					x[idx:idx+count],
					y[idx:idx+count],
					label = group if group not in used_labels else "",
					c=md["color"]
				)
				# Record used group labels to prevent duplicate legends
				used_labels.add(group)
				idx += count

			ax.legend(loc="best", fontsize=8)

		elif color_mode == "kmeans":
			if self._kmeans_labels is None:
				ax.scatter(x, y)
				ax.set_title("UMAP (no KMeans labels yet)")
			else:
				ax.scatter(x, y, c=self._kmeans_labels, cmap="tab10")
				ax.set_title("UMAP colored by KMeans")

		elif color_mode == "dbscan":
			if self._dbscan_labels is None:
				ax.scatter(x, y)
				ax.set_title("UMAP (no DBSCAN labels yet)")
			else:
				ax.scatter(x, y, c=self._dbscan_labels, cmap="tab10")
				ax.set_title("UMAP colored by DBSCAN (-1 = noise)")
		else:
			ax.scatter(x, y)

		ax.set_xlabel("UMAP-1")
		ax.set_ylabel("UMAP-2")

		if self.annotate_check.isChecked():
			idx = 0
			for ds in self._used_datasets:
				for l in ds.labels_unique:
					ax.annotate(ds.name, (x[idx], y[idx]), fontsize=7, alpha=0.8)
					idx += 1

		self.graph.draw_idle()

	# ---------------- Callbacks ----------------

	def _on_run_umap_clicked(self) -> None:
		datasets = self.get_selected_datasets()

		metrics = self._selected_metrics()
		stats = self._selected_stats()
		if len(metrics) == 0 or len(stats) == 0:
			QMessageBox.warning(self, "No features selected", "Select at least 1 metric and 1 summary stat.")
			return

		harmonic = int(self.harmonic_combo.currentText())

		try:
			self._build_feature_matrix(datasets, metrics, stats, harmonic=harmonic)

			# TODO: Need to change this to accommodate rois
			# Drop datasets with any NaN feature (e.g. empty mask)
			"""
			good = np.isfinite(X).all(axis=1)
			if not np.all(good):
				dropped = [datasets[i].name for i in range(len(datasets)) if not good[i]]
				QMessageBox.warning(
					self,
					"Dropped datasets",
					"Some datasets had no valid pixels for the selected features and were dropped:\n"
					+ "\n".join(dropped),
				)
				datasets = [datasets[i] for i in range(len(datasets)) if good[i]]
				X = X[good]
			"""
			#if len(datasets) < 3:
			#	QMessageBox.warning(self, "Not enough valid datasets", "Too few valid datasets after filtering.")
			#	return

			self._preprocess()
			self._run_umap()

			self._used_datasets = datasets

			# Reset clustering caches
			self._kmeans_labels = None
			self._dbscan_labels = None

			X = self._feature_workspace.feature_matrix
			self._set_status(f"UMAP done. n={X.shape[0]}, d={X.shape[1]}")
			self._redraw()

		except Exception as e:
			QMessageBox.critical(self, "UMAP error", str(e))

	def _on_run_clustering_clicked(self) -> None:
		try:
			if self.kmeans_check.isChecked():
				self._kmeans_labels = self._run_kmeans(self._feature_workspace.umap)
			if self.dbscan_check.isChecked():
				self._dbscan_labels = self._run_dbscan(self._feature_workspace.umap)

			# If user picks a clustering color mode, redraw reflects it
			self._set_status("Clustering done.")
			self._redraw()

		except Exception as e:
			QMessageBox.critical(self, "Clustering error", str(e))

	def _on_export_clicked(self) -> None:
		if self._feature_workspace is None:
			QMessageBox.warning(self, "Nothing to export")
			return

		path, _ = QFileDialog.getSaveFileName(
			self,
			"Export embedding",
			"umap_embedding.csv",
			"CSV (*.csv)",
		)
		if not path: return

		try:
			rows = []
			idx = 0
			for md in self._feature_workspace.metadata:
				for i in range(md["count"]):
					row = {
						"name": md["name"],
						"region": i+1,
						"group": md["group"],
						"umap1": float(self._feature_workspace.umap[idx, 0]),
						"umap2": float(self._feature_workspace.umap[idx, 1]),
					}
					if self._kmeans_labels is not None:
						row["kmeans"] = int(self._kmeans_labels[idx])
					if self._dbscan_labels is not None:
						row["dbscan"] = int(self._dbscan_labels[idx])
					# Add features too
					for j, fn in enumerate(self._feature_workspace.feature_names):
						row[fn] = float(self._feature_workspace.feature_matrix[idx, j])
					rows.append(row)
					idx += 1

			if pd is not None:
				pd.DataFrame(rows).to_csv(path, index=False)
			else:
				# Minimal fallback
				import csv

				with open(path, "w", newline="", encoding="utf-8") as f:
					w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
					w.writeheader()
					w.writerows(rows)

			self._set_status(f"Exported: {path}")

		except Exception as e:
			QMessageBox.critical(self, "Export error", str(e))

	def _on_clear_clicked(self) -> None:
		self.graph.clear()
		self._set_status("Ready")
		self._used_datasets = []
		self._kmeans_labels = None
		self._dbscan_labels = None

	def _on_selection_changed(self) -> None:
		has_selected = len(self.dataset_list.selectedItems()) > 0
		self.btn_run.setEnabled(has_selected)
		self.btn_export.setEnabled(has_selected)
		self.btn_cluster.setEnabled(has_selected)

	def _make_item_name(self, dataset: "Dataset") -> str:
		return f"{dataset.name} (channel {dataset.channel}) [{dataset.group}]"
