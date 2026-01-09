from typing import TYPE_CHECKING

from qtpy.QtCore import Signal
from qtpy.QtWidgets import QWidget, QVBoxLayout

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

if TYPE_CHECKING:
	from matplotlib.axes import Axes

class MPLGraph(QWidget):
	"""
	A widget acting as container for a matplotlib figure canvas.

	Signals:

	- `canvasClicked(float, float)`: Emitted when the canvas is clicked at position (x,y). 
	"""
	canvasClicked = Signal(float, float)

	def __init__(self, dpi:int = 120, fig_pixels:int = 480, parent:QWidget|None = None):
		"""
		Args:
			dpi: -
			fig_pixels: -
			parent: -
		"""
		super().__init__(parent)
		self.dpi = dpi
		self.fig_pixels = fig_pixels

		self._build()

	def _build(self) -> None:
		root = QVBoxLayout(self)

		fsize = self.fig_pixels/self.dpi
		self._fig = Figure(figsize=(fsize, fsize), dpi=self.dpi)
		self._canvas = FigureCanvasQTAgg(self._fig)
		self._toolbar = NavigationToolbar2QT(self._canvas, self)
		self._ax = self._fig.add_subplot(111)
		# Connect canavs click event for placing ROIs
		self._fig.canvas.mpl_connect("button_press_event", self._on_mpl_click)

		root.addWidget(self._toolbar)
		root.addWidget(self._canvas, stretch=1)

	## ------ Public API ------ ##
	def get_ax(self) -> "Axes":
		"""
		Returns:
			Figure axes.
		"""
		return self._ax

	def draw_idle(self) -> None:
		"""Schedule canvas changes to be rendered."""
		self._canvas.draw_idle()

	def clear(self) -> None:
		"""Clear the axes and redraw."""
		self._ax.cla()
		self.draw_idle()

	## ------ Internal ------ ##
	def _on_mpl_click(self, event) -> None:
		"""
		Matplotlib 'button_press_event' handler.
		Emits (x, y) coordinate when the click occurs inside the axes.
		"""
		# Ignore clicks while toolbar is in an active mode (pan/zoom)
		if getattr(self._toolbar, "mode", ""):
			return
		# Ignore if not in our axes (there should only be one but safeguard)
		if event.inaxes is not self._ax:
			return
		if event.xdata is None or event.ydata is None:
			return
		x, y = float(event.xdata), float(event.ydata)
		self.canvasClicked.emit(x, y)