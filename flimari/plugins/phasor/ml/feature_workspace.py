from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
	from flimari.plugins.phasor.core import Dataset

class FeatureWorkspace:
	def __init__(self, feature_names=None, feature_matrix=None, metadata=None):
		self.feature_names: list[str] = feature_names
		self.feature_matrix: np.ndarray = feature_matrix
		self.metadata: list = metadata

	def build_features(
		self,
		datasets:list["Dataset"],
		features:list[str],
		stats:list[str],
		harmonic:int = 1,
		morph_features:list[str] = (),
	):
		if len(datasets) == 0 or (len(features) == 0 and len(morph_features) == 0):
			return
		if len(features) > 0 and len(stats) == 0:
			return

		# Build metadata
		self.metadata = []
		for ds in datasets:
			self.metadata.append({
				"name": ds.name,
				"group": ds.group,
				"color": ds.color,
				"count": len(ds.labels_unique),
			})

		# Make list of feature names
		self.feature_names = []
		for f in features:
			for s in stats:
				self.feature_names.append(f"{f}:{s}")
		for mf in morph_features:
			self.feature_names.append(mf)

		# Build feature matrix
		matrix = []
		for ds in datasets:
			ds_feats = []
			for f in features:
				for s in stats:
					# Becomes [F*S+M, L] array, each subarray is the feature of labelled regions
					ds_feats.append(ds.image_feature(f, s, harmonic=harmonic))
			for mf in morph_features:
				ds_feats.append(ds.morphological_feature(mf))
			# Transpose so that each row is a labelled region in an image
			matrix.append(np.asarray(ds_feats, dtype=float).T)

		self.feature_matrix = np.concatenate(matrix, axis=0)

		# Drop rows with any NaN (labels whose pixel mask is empty for some feature).
		# Update metadata counts so plotting offsets remain consistent.
		valid = np.isfinite(self.feature_matrix).all(axis=1)
		if not np.all(valid):
			self.feature_matrix = self.feature_matrix[valid]
			idx = 0
			for md in self.metadata:
				count = md["count"]
				md["count"] = int(valid[idx:idx + count].sum())
				idx += count

	def del_attr(self, attr:str):
		if hasattr(self, attr): delattr(self, attr)