from typing import TYPE_CHECKING

from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (
	QWidget,
	QPushButton,
)

if TYPE_CHECKING:
	import napari

class ThemedButton(QPushButton):
	"""
	A `QPushButton` with napari built-in icons that follows viewer theme change.

	See [https://github.com/napari/napari/tree/main/src/napari/resources/icons](https://github.com/napari/napari/tree/main/src/napari/resources/icons) for available icons.
	"""
	def __init__(self, *args, icon:str, viewer:"napari.Viewer", **kwargs):
		"""
		Args:
			*args: Arguments for `QPushButton`.
			icon: Name of the napari icon.
			viewer: Main viewer.
			**kwargs: Additional arguments.
		"""
		super().__init__(*args, **kwargs)
		self.viewer = viewer
		self.icon = icon
		self._apply_icons()
		viewer.events.theme.connect(self._apply_icons)

	def _apply_icons(self):
		theme = getattr(self.viewer, "theme", "dark")
		icon = QIcon()
		icon.addFile(f"theme_{theme}:/{self.icon}.svg", mode=QIcon.Normal, state=QIcon.Off)
		self.setIcon(icon)