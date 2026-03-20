from sklearn.decomposition import PCA
import umap

from napari.utils.notifications import show_error, show_warning

def do_pca(workspace, n_components, random_state=42, using="feature_matrix"):
	if not hasattr(workspace, using):
		show_warning(f"Feature workspace has no attribute {using}. Fallback to the feature matrix")
		using = "feature_matrix"

	workspace.pca = PCA(n_components=n_components, random_state=random_state).fit_transform(getattr(workspace, using))

def do_umap(
	workspace,
	embed_dim = 2,
	n_neighbors = 10,
	min_dist = 0.3,
	metric = "euclidean",
	random_state = 42,
	n_jobs = 1,
	using = "pca",
):
	if not hasattr(workspace, using):
		show_warning(f"Feature workspace has no attribute {using}. Fallback to the feature matrix")
		using = "feature_matrix"

	reducer = umap.UMAP(
		n_neighbors = n_neighbors,
		min_dist = min_dist,
		metric = metric,
		random_state = random_state,
		n_jobs = n_jobs,
	)

	workspace.umap = reducer.fit_transform(getattr(workspace, using))