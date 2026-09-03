"""
Deliberately empty of eager imports. Python always executes a package's
__init__.py before importing any of its submodules -- so `import
app.services.sandbox` (the worker's only dependency in this package; see
app/worker/main.py) previously dragged in extractors.py's pypdf/torch/
transformers stack too, no matter how light sandbox.py itself is. That
defeats the worker's lightweight-dependency design (see
docs/2_LAP_SOV_WORKER_SETUP.md: Node B needs Docker, not Ollama or any of
the document/vision extraction dependencies).

Existing `from app.services import DocumentStorage` etc. call sites keep
working unchanged via PEP 562 module __getattr__ below: the heavy import
only happens the first time one of these names is actually accessed, not
merely because some other submodule of this package was imported.
"""
from typing import Any

_LAZY_EXPORTS = {
    "DocumentStorage": "app.services.storage",
    "LocalDocumentStorage": "app.services.storage",
    "DocumentMetadataStore": "app.services.metadata_store",
    "DocumentExtractor": "app.services.extractors",
    "get_extractor": "app.services.extractors",
    "ExtractionError": "app.services.extractors",
    "ModelResourceManager": "app.services.model_resource_manager",
    "get_resource_manager": "app.services.model_resource_manager",
}


def __getattr__(name: str) -> Any:
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value  # cache on this package module so repeated access doesn't re-resolve
    return value
