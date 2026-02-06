from typing import Optional, Literal, TYPE_CHECKING

from qtpy.QtCore import Signal
from qtpy.QtWidgets import QWidget, QVBoxLayout

import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

from phasorpy.plot import PhasorPlot

from flimari.core.widgets import MPLGraph

if TYPE_CHECKING:
	from ..core import Dataset
	from matplotlib.axes import Axes

class PhasorGraphWidget(MPLGraph):
	"""
	QWidget container for matplotlib figure and phasor plot related APIs.
	"""
	def __init__(
		self,
		frequency: float|None = None,
		dpi: int = 120,
		fig_pixels: int = 480,
		parent: QWidget|None = None
	) -> None:
		super().__init__(dpi=dpi, fig_pixels=fig_pixels, parent=parent)
		self.frequency = frequency
		self._pp = PhasorPlot(ax=self.get_ax(), frequency=self.frequency)
		self.curated_colors = [
			"limegreen",
			"blue",
			"brown",
			"chocolate",
			"orange",
			"teal",
			"darkviolet",
			"yellowgreen",
			"magenta",
			"red",
		]
		self.draw_idle()

	## ------ Public API ------ ##
	def clear(self) -> None:
		"""
		Reset the plot.
		"""
		# This is nasty, but I don't think there is a more reliable way?
		xlim = self._ax.get_xlim()
		ylim = self._ax.get_ylim()
		xscale = self._ax.get_xscale()
		yscale = self._ax.get_yscale()
		aspect = self._ax.get_aspect()
		# HACK: Save the circle ROI patches before clearing and add back.
		# This works, but not scalable once we add arrows, component analysis, etc.
		patches = self._ax.patches[:]
		self._ax.cla()
		for p in patches:
			self._ax.add_patch(p)
		self._ax.set_xlim(xlim)
		self._ax.set_ylim(ylim)
		self._ax.set_xscale(xscale)
		self._ax.set_yscale(yscale)
		self._ax.set_aspect(aspect)

		if self.frequency:
			self._ax.set_title(f"Phasor plot ({self.frequency} MHz)")
		else:
			self._ax.set_title("Phasor plot")
		self._ax.set_xlabel("G, real")
		self._ax.set_ylabel("S, imag")
		self._draw_semicircle()

	def draw_datasets(
		self,
		datasets: list["Dataset"],
		mode: Literal["scatter","hist2d","contour"] = "contour",
		cmap: str = "by group"
	) -> None:
		"""
		Plot the phasor of a list of datasets.
		If cmap == 'by group', the color defined within datasets are used.
		Otheriwse, use the specified cmap for all datasets.
		"""
		legend = {}
		for ds in datasets:
			if cmap == "by group":
				group = ds.group
				legend[group] = ds.color
				self.draw_dataset(ds, mode)
			else:
				self.draw_dataset(ds, mode, cmap)

		# Make legend if color by group
		if cmap == "by group":
			handles = [
				Patch(facecolor=color, edgecolor='none', label=group)
				for group, color in legend.items()
			]
			self._ax.legend(handles=handles, title="Group", fontsize="small", title_fontsize="small", loc="upper right")

		self.draw_idle()


	def draw_dataset(
		self,
		dataset: "Dataset",
		mode: Literal["scatter","hist2d","contour"],
		cmap: str|None = None
	) -> None:
		"""
		Plot the given dataset.
		:param mode: Plotting mode. Accepts plot, hist2d, contour.
		:param color: Plot color. 
		"""
		# Slice only meaningful values for efficient plotting
		# TODO: Figure out exactly how to handle g s returns
		g, s = dataset.get_phasor()
		g = g[dataset.mask]
		s = s[dataset.mask]
		match mode:
			case "scatter":
				self._pp.plot(g, s, fmt=',', alpha = 0.5, color=dataset.color)
			case "hist2d":
				self._pp.hist2d(g, s, cmap=cmap)
			case "contour":
				if cmap is None:
					# HACK: hide lowest level by forcing line width 0
					self._pp.contour(g, s, colors=dataset.color, linewidths=[0,1,1,1,1,1,1])
				else:
					self._pp.contour(g, s, cmap=cmap)

	## ------ Internal ------ ##
	def _draw_semicircle(self) -> None:
		# We have to give it frequency here because apparently PhasorPlot does not
		# keep track of the frequency value given in init.
		self._pp.semicircle(frequency=self.frequency, lifetime=[0.5,1,2,4,8])