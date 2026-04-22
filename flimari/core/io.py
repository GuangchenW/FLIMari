from pathlib import Path
from typing import Any
from phasorpy.io import (
	signal_from_ptu,
	signal_from_imspector_tiff
)

def load_signal(path:str|Path, channel:int=0) -> Any:
	"""Load a FLIM dataset via phasorpy IO.

	Returns a signal (xarray.DataArray) if successful.
	Rasies IOErrors on failure. 
	"""
	p = Path(path)
	if not p.exists():
		raise IOError(f"File not found: {p}")

	# Decide file loader based on file extension
	suffix = p.suffix.lower()
	try:
		if suffix in {".tif", ".tiff"}:
			try:
				sig = signal_from_imspector_tiff(p)
			except ValueError as e:
				print(".tiff/.tif files has to be of ImSpector origin due to metadata requirements.")
				raise
		elif suffix == ".ptu":
			sig = signal_from_ptu(p, frame=-1, channel=channel)
			print(sig)
		else:
			raise IOError(f"Unsupported extensions: {suffix}")
		return sig
	except Exception as e:
		raise IOError(f"Failed to load {p}: {e}") from e

