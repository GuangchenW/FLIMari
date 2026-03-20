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
	):
		if len(datasets) == 0 or len(features) == 0 or len(stats) == 0:
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

		# Build feature matrix
		matrix = []
		for ds in datasets:
			ds_feats = []
			for f in features:
				for s in stats:
					# Becomes [F*S, L] array, each subarray is the feature of labelled regions
					ds_feats.append(ds.image_feature(f, s, harmonic=harmonic))
			# Transpose so that each row is a labelled region in an image
			matrix.append(np.asarray(ds_feats, dtype=float).T)

		self.feature_matrix = np.concat(matrix, axis=0)
