from __future__ import annotations
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from .dataset import Dataset
from .external_dataset import ExternalDataset

if TYPE_CHECKING:
	from .calibration import Calibration

WORKSPACE_VERSION = 1
FILE_FILTER = "FLIMari workspace (*.npz)"

_DATASET_TYPES = {cls.__name__: cls for cls in {Dataset, ExternalDataset}}

class Workspace:
	"""
	Workspace containing the current work state.
	Included: 
		- Current datasets and their exact processing states.
	Not included:
		- Calibration parameters
		- ROI parameters
		- Analysis output layers
		- GUI states
		- ML parameters
	"""

	def __init__(self):
		self.datasets: dict[uuid.UUID, Dataset] = {}

	def __contains__(self, ds_id: uuid.UUID) -> bool:
		return ds_id in self.datasets

	def register_dataset(self, ds: Dataset) -> None:
		if ds.id in self.datasets:
			raise ValueError(f"Dataset {ds.display_name()} is already registered")
		self.datasets[ds.id] = ds

	def remove_dataset(self, ds: Dataset) -> None:
		self.datasets.pop(ds.id, None)

	def clear(self) -> None:
		self.datasets.clear()

	def save_to_disk(
		self,
		path: str|Path,
	) -> None:
		"""
		Write all registered datasets to `path`.
		"""
		meta = []
		# Array archive, keyed by dataset_id.<array_name>
		arrays: dict[str, np.ndarray] = {}
		for ds in self.datasets.values():
			d = ds.to_dict()
			d["type"] = type(ds).__name__ # Native or external dataset
			# Archive arrays and scalars separately
			for k in [k for k,v in d.items() if isinstance(v, np.ndarray)]:
				arrays[f"{ds.id}.{k}"] = d.pop(k)
			# Add the remaining values to meta
			meta.append(d)

		header = {"version": WORKSPACE_VERSION, "datasets": meta}
		np.savez_compressed(path, __meta__=np.array(json.dumps(header)), allow_pickle=False, **arrays)

	def load_from_disk(self, path: str|Path) -> None:
		with np.load(path, allow_pickle=False) as npz:
			header = json.loads(str(npz["__meta__"]))
			version = header.get("version")
			if version != WORKSPACE_VERSION:
				raise ValueError(f"Unsupported workspace version {version} (expected {WORKSPACE_VERSION})")

			datasets: dict[uuid.UUID, Dataset] = {}
			for d in header["datasets"]:
				prefix = f"{d['id']}."
				d.update({k[len(prefix):]: npz[k] for k in npz.files if k.startswith(prefix)})
				type_name = d.pop("type", Dataset.__name__)
				if type_name not in _DATASET_TYPES:
					raise ValueError(f"Unknown dataset type {type_name}")
				ds = _DATASET_TYPES[type_name].from_dict(d)
				datasets[ds.id] = ds

		self.datasets = datasets