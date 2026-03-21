# segmentation/model_registry.py
"""
Model registry for versioning and managing ONNX models.
"""

import os
import json
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ModelMetadata:
    """Metadata for a registered model."""

    def __init__(self, name: str, version: str, model_type: str, path: str,
                 metrics: Dict[str, float], created_at: str = None):
        self.name = name
        self.version = version
        self.model_type = model_type  # 'gnn' or 'pointnet'
        self.path = path
        self.metrics = metrics
        self.created_at = created_at or datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'version': self.version,
            'model_type': self.model_type,
            'path': self.path,
            'metrics': self.metrics,
            'created_at': self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelMetadata':
        return cls(
            name=data['name'],
            version=data['version'],
            model_type=data['model_type'],
            path=data['path'],
            metrics=data['metrics'],
            created_at=data['created_at']
        )


class ModelRegistry:
    """Registry for managing ML model versions."""

    def __init__(self, registry_path: str = 'model_registry.json'):
        self.registry_path = registry_path
        self.models: Dict[str, ModelMetadata] = {}
        self.load_registry()

    def load_registry(self) -> None:
        """Load registry from disk."""
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, 'r') as f:
                    data = json.load(f)
                    for key, model_data in data.items():
                        self.models[key] = ModelMetadata.from_dict(model_data)
                logger.info(f"Loaded {len(self.models)} models from registry")
            except Exception as e:
                logger.warning(f"Failed to load registry: {e}")
        else:
            logger.info("No existing registry found, starting fresh")

    def save_registry(self) -> None:
        """Save registry to disk."""
        data = {key: model.to_dict() for key, model in self.models.items()}
        with open(self.registry_path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {len(self.models)} models to registry")

    def register_model(self, name: str, model_type: str, model_path: str,
                      metrics: Dict[str, float], version: str = None) -> str:
        """
        Register a new model version.

        Args:
            name: Model name
            model_type: 'gnn' or 'pointnet'
            model_path: Path to ONNX model file
            metrics: Training/validation metrics
            version: Version string (auto-generated if None)

        Returns:
            Model key for retrieval
        """
        if version is None:
            # Auto-generate version based on file hash if available
            if os.path.exists(model_path):
                version = self._get_file_hash(model_path)
            else:
                # Fall back to timestamp-based version for missing files
                version = datetime.now().strftime('%Y%m%d%H%M%S')

        key = f"{name}_{model_type}_{version}"

        if key in self.models:
            logger.warning(f"Model {key} already exists, overwriting")

        metadata = ModelMetadata(
            name=name,
            version=version,
            model_type=model_type,
            path=model_path,
            metrics=metrics
        )

        self.models[key] = metadata
        self.save_registry()

        logger.info(f"Registered model: {key}")
        return key

    def get_model(self, name: str, model_type: str, version: str = 'latest') -> Optional[ModelMetadata]:
        """
        Retrieve a model from the registry.

        Args:
            name: Model name
            model_type: 'gnn' or 'pointnet'
            version: Version string or 'latest'

        Returns:
            ModelMetadata if found, None otherwise
        """
        if version == 'latest':
            # Find latest version for this name/type
            candidates = [
                model for model in self.models.values()
                if model.name == name and model.model_type == model_type
            ]
            if not candidates:
                return None

            # Sort by creation time
            candidates.sort(key=lambda m: m.created_at, reverse=True)
            return candidates[0]
        else:
            key = f"{name}_{model_type}_{version}"
            return self.models.get(key)

    def list_models(self, name: str = None, model_type: str = None) -> List[ModelMetadata]:
        """
        List registered models, optionally filtered.

        Args:
            name: Filter by model name
            model_type: Filter by model type

        Returns:
            List of matching ModelMetadata
        """
        models = list(self.models.values())

        if name:
            models = [m for m in models if m.name == name]
        if model_type:
            models = [m for m in models if m.model_type == model_type]

        return models

    def delete_model(self, name: str, model_type: str, version: str) -> bool:
        """
        Delete a model from registry.

        Args:
            name: Model name
            model_type: 'gnn' or 'pointnet'
            version: Version string

        Returns:
            True if deleted, False if not found
        """
        key = f"{name}_{model_type}_{version}"
        if key in self.models:
            del self.models[key]
            self.save_registry()
            logger.info(f"Deleted model: {key}")
            return True
        return False

    def get_active_models(self) -> Dict[str, ModelMetadata]:
        """
        Get the currently active (latest) models for each type.

        Returns:
            Dictionary with 'gnn' and 'pointnet' keys
        """
        active = {}
        for model_type in ['gnn', 'pointnet']:
            model = self.get_model('manufacturability', model_type, 'latest')
            if model:
                active[model_type] = model
        return active

    @staticmethod
    def _get_file_hash(file_path: str) -> str:
        """Generate hash of model file for versioning."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()[:8]  # First 8 chars for version