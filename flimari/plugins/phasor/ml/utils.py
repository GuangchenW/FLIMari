from sklearn.preprocessing import StandardScaler, RobustScaler

from napari.utils.notifications import show_error

class NormalizationModes:
	NONE = "None"
	ZSCORE = "z-score"
	ROBUST = "Robust"
	ALL = [ROBUST, ZSCORE, NONE]

def normalize(workspace, mode=NormalizationModes.NONE):
	match mode:
		case NormalizationModes.NONE:
			pass
		case NormalizationModes.ZSCORE:
			workspace.feature_matrix = StandardScaler().fit_transform(workspace.feature_matrix)
		case NormalizationModes.ROBUST:
			workspace.feature_matrix = RobustScaler().fit_transform(workspace.feature_matrix)
		case _:
			show_error(f"Unknown scaling mode: {mode}")