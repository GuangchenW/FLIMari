from typing import Optional, TYPE_CHECKING
from enum import Enum
import numpy as np

from napari.utils import DirectLabelColormap

if TYPE_CHECKING:
	import napari

class LayerType(Enum):
	IMAGE = 1
	LABEL = 2

class LayerManager:
	"""
	A singleton class for managing image layers created by FLIMari.
	"""
	_instance = None

	def __new__(cls, *arg, **kwarg):
		if cls._instance is None:
			inst = super().__new__(cls)
			# State must be initialized here, since __init__ runs on every LayerManager() call.
			# Stores a nested dictionary containing the spec to build each layer:
			#	{"data": ndarray, "display_name": str, "kwargs": dict}
			# Keyed by:
			#	key: unique key of the data
			#	kind: the kind of layer this is
			inst.layer_data = {}
			# Keys whose layers should be present in the viewer
			inst._shown: set[str] = set()
			cls._instance = inst
		return cls._instance

	def __init__(self, viewer:Optional["napari.Viewer"]=None):
		# HACK: A little hacky. We need to ensure that the first call to the constructor 
		# supplies the viewer. Fortunately, we can create the LayerManager in the app shell.
		# Since we know every module will be using it.
		if viewer: self.viewer = viewer

	## ------ Public API ------ ##
	def add_layer(
		self, data:np.ndarray, *, 
		key:str, kind:LayerType, display_name:str = "", 
		overwrite:bool = False, **kwargs) -> None:
		"""
		Register layer data, or overwrite an existing one.
		The napari layer is only added/updated if `key` is shown (see `show_layers`).

		Args:
			data: The data to display.
			key: Unique key of the data, stored in layer metadata.
			kind: The layer's `LayerType`.
			display_name: Name of the layer shown in the UI.
			overwrite: Whether to overwrite if a layer with the same `LayerType` and `key` already exists.
			**kwargs: Optional arguments for the add layer call to napari.
		"""
		# Drop unset kwargs (e.g. colormap=None) so they don't interfere with stored ones
		kwargs = {k: v for k, v in kwargs.items() if v is not None}
		spec = self._get_spec(key, kind)
		# If no data registered yet, register in dict.
		# Or, if data registered and overwrite, replace data.
		if spec is None:
			self.layer_data.setdefault(key, {})[kind] = {
				"data": data,
				"display_name": display_name,
				"kwargs": kwargs
			}
		elif overwrite:
			spec["data"] = data
			spec["display_name"] = display_name or spec["display_name"]
			spec["kwargs"].update(kwargs)
		# Added to viewer if layer is not hidden
		if key in self._shown: self._sync_layer(key, kind, overwrite)

	def add_image(self, data:np.ndarray, *, key:str, overwrite:bool=False, **kwargs) -> None:
		"""
		Add an image layer to the viewer.
		Wrapper function for `add_layer`.

		Args:
			data: The image to display.
			key: Unique key of the data, stored in layer metadata.
			overwrite: Whether to overwrite if layer already exists.
			**kwargs: Optional arguments for `napari.Viewer.add_image`.
		"""
		self.add_layer(data, key=key, kind=LayerType.IMAGE, overwrite=overwrite, **kwargs)

	def add_label(self, data:np.ndarray, *, key:str, cdict:dict=None, overwrite:bool=False, **kwargs) -> None:
		"""
		Add a label layer to the viewer.
		Wrapper function for `add_layer`.

		Args:
			data: The labels to display.
			key: Unique key of the data, stored in layer metadata.
			cdict: Color dictionary for `DirectLabelColormap`, used to color the labels.
			overwrite: Whether to overwrite if layer already exists.
			**kwargs: Optional arguments for `napari.Viewer.add_image`.
		"""
		cmap = DirectLabelColormap(color_dict=cdict) if cdict else None
		self.add_layer(data, key=key, kind=LayerType.LABEL, overwrite=overwrite, colormap=cmap, **kwargs)

	def get_layer_data(self, key:str, kind:LayerType) -> np.ndarray:
		"""
		Args:
			key: Unique key of the data (in metadata, not display name).
			kind: `LayerType` of the layer.

		Returns:
			Data stored in the layer. If no data is stored, return `None`.
		"""
		spec = self._get_spec(key, kind)
		return None if spec is None else spec["data"]

	def show_layers(self, key:str) -> None:
		"""
		Add all stored layers related to `key` to the viewer.
		"""
		self._shown.add(key)
		# Add image first so labels sit on top
		for kind in (LayerType.IMAGE, LayerType.LABEL):
			self._sync_layer(key, kind)

	def hide_layers(self, key:str) -> None:
		"""
		Remove all layers related to `key` from the viewer, keeping their data stored.
		"""
		self._shown.discard(key)
		for kind in LayerType:
			self.remove_layer(key, kind)

	def is_shown(self, key:str) -> bool:
		return key in self._shown

	def forget(self, key:str) -> None:
		"""
		Remove all layers related to `key` from the viewer and drop their stored data.
		"""
		self.hide_layers(key)
		self.layer_data.pop(key, None)

	def remove_layer(self, key:str, kind:LayerType) -> None:
		"""
		Remove the first layer with the given metadata key.

		Args:
			key: Unique key of the data.
			kind: Target `LayerType`.
		"""
		layer = self._find_layer(key, kind)
		# This safely handles when user removed layer using built-in UI
		# and then uses the plugin buttons in data row.
		if layer is not None:
			self.viewer.layers.remove(layer)

	## ------ Internal ------ ##
	def _get_spec(self, key:str, kind:LayerType) -> dict|None:
		l1 = self.layer_data.get(key)
		return None if l1 is None else l1.get(kind)

	def _sync_layer(self, key:str, kind:LayerType, overwrite:bool=False) -> None:
		"""
		Sync the viewer layer with the stored spec. Add if missing, update if `overwrite`.
		"""
		spec = self._get_spec(key, kind)
		if spec is None: return
		layer = self._find_layer(key, kind)
		if layer is None:
			# Make metadata
			tag = self._make_tag(key, kind)
			# If display name is empty, default to key
			display_name = spec["display_name"] or key
			# Add layer
			match kind:
				case LayerType.IMAGE:
					self.viewer.add_image(spec["data"], name=display_name, metadata=tag, **spec["kwargs"])
				case LayerType.LABEL:
					self.viewer.add_labels(spec["data"], name=display_name, metadata=tag, **spec["kwargs"])
		elif overwrite:
			# If layer exists, replace its data
			layer.data = spec["data"]
			# If it is label layer, update colormap as well
			if kind == LayerType.LABEL:
				cmap = spec["kwargs"].get("colormap")
				if cmap: layer.colormap = cmap

	def _make_tag(self, key:str, kind:LayerType) -> dict:
		return {
			"flimari": {
				"key": key,
				"kind": kind,
				"version": 2
			}
		}

	def _find_layer(self, key:str, kind:LayerType) -> "napari.layers.Layer":
		"""
		Iterate through all layers and find first that has matching metadata.
		"""
		for lyr in self.viewer.layers:
			meta = getattr(lyr, "metadata", {})
			fs = meta.get("flimari")
			if fs and fs.get("key") == key and fs.get("kind") == kind:
				return lyr
		return None
