from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
	QPushButton,
	QColorDialog,
)

class ColorButton(QPushButton):
	"""
	A button for picking color. Shows a preview of the current color.

	When pressed, the napari color picker window will open. 
	"""
	colorChanged = Signal(object)

	def __init__(self, *args, color:str="#ff0000", **kwargs):
		"""
		Args:
			*args: Arguments for `QPushButton`.
			color: Initial color.
			**kwargs: Additional arguments.
		"""
		super().__init__(*args, **kwargs)

		self._color = None
		self._default = color
		self.set_color(self._default)
		self.pressed.connect(self._on_pick_color)

	## ------ Public API ------ ##
	def set_color(self, color):
		"""
		Args:
			color: Color in hex string format.
		"""
		if color != self._color:
			self._color = color
			self.colorChanged.emit(color)

		if self._color:
			self.setStyleSheet(f"background-color: {self._color};")
		else:
			self.setStyleSheet("")

	def get_color(self) -> str:
		"""
		Returns:
			Current color in hex string format.
		"""
		return self._color

	## ------ Internal ------ ##
	def _on_pick_color(self) -> None:
		dlg = QColorDialog(self.window())
		dlg.setStyleSheet("")
		if self._color:
			dlg.setCurrentColor(QColor(self._color))
		if dlg.exec_():
			self.set_color(dlg.currentColor().name())

	def mousePressEvent(self, e):
		if e.button() == Qt.RightButton:
			self.set_color(self._default)
		return super().mousePressEvent(e)