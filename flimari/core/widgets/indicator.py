from qtpy.QtCore import Signal
from qtpy.QtWidgets import QFrame

class Indicator(QFrame):
	"""
	An indicator light widget with named states.
	
	Signals:
    
        - `stateChanged(str)`: Emitted when the state changes.
	"""
	stateChanged = Signal(str)

	def __init__(
		self,
		diameter: int = 12,
		*,
		states: dict[str, str] | None = None,
		off_color: str = "#bdc3c7",
		parent=None
	):
		"""
		Args:
			diameter: Size of the indicator.
			states: State name to color hex string mappings. Default to 
				`{ "ok": "#2ecc71", "warn": "#f1c40f", "bad": "#e74c3c" }`
			off_color: Color for when the indicator is off.
			parent: -
		"""
		super().__init__(parent)
		self._diameter = diameter
		self._off_color = off_color
		# TODO: Standarize these color schemes
		self._states = states or {
			"ok": "#2ecc71",
			"warn": "#f1c40f",
			"bad": "#e74c3c",
		}
		# current state name
		self._state_name: str = "off"

		self.setFixedSize(self._diameter, self._diameter)
		self.setStyleSheet("")
		self._apply()

	## ------ Public API ------ ##
	def set_off(self) -> None:
		"""
		Turn off the indicator.
		"""
		self._set_state("off")

	def set_state(self, name:str) -> None:
		"""
		Args:
			name: -
		"""
		self._set_state(name)

	def state(self) -> str:
		"""
		Returns:
			Current state.
		"""
		return self._state_name

	## ------ Internal ------ ##
	def _set_state(self, name:str, silent:bool=False) -> None:
		if name != "off" and name not in self._states:
			raise KeyError(f"Unknown state name '{name}'. Allowed: {list(self._states)}")
		if name == self._state_name:
			return
		self._state_name = name
		self._apply()
		if not silent:
			self.stateChanged.emit(self._state_name)

	def _apply(self) -> None:
		color = self._off_color if self._state_name == "off" else self._states[self._state_name]
		r = self._diameter // 2
		self.setStyleSheet(f"QFrame{{background:{color}; border-radius:{r}px}}")