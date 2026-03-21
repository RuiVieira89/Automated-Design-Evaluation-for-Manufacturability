# segmentation/training/gnn_trainer.py
"""
Training script for PyTorch Geometric GNN model on B-Rep feature graphs.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GCNConv, global_mean_pool
from torch_geometric.data import DataLoader, Data
import numpy as np
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)


class ManufacturabilityGNN(nn.Module):
    """GNN model for manufacturability classification on B-Rep graphs."""

    def __init__(self, num_node_features: int, num_classes: int, hidden_dim: int = 64):
        super().__init__()
        self.conv1 = GCNConv(num_node_features, hidden_dim)
        self.conv2 = GCNConv(hidden_dim, hidden_dim)
        self.conv3 = GCNConv(hidden_dim, hidden_dim)
        self.classifier = nn.Linear(hidden_dim, num_classes)

    def forward(self, x, edge_index, batch):
        # Graph convolutions
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=0.5, training=self.training)

        x = self.conv2(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=0.5, training=self.training)

        x = self.conv3(x, edge_index)
        x = F.relu(x)

        # Global pooling
        x = global_mean_pool(x, batch)

        # Classification
        x = self.classifier(x)
        return F.log_softmax(x, dim=1)


class GNNTrainer:
    """Trainer for the manufacturability GNN model."""

    def __init__(self, model: nn.Module, device: str = 'cuda' if torch.cuda.is_available() else 'cpu'):
        self.model = model.to(device)
        self.device = device
        self.optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        self.criterion = nn.NLLLoss()

    def train_epoch(self, train_loader: DataLoader) -> float:
        """Train for one epoch."""
        self.model.train()
        total_loss = 0

        for data in train_loader:
            data = data.to(self.device)
            self.optimizer.zero_grad()

            out = self.model(data.x, data.edge_index, data.batch)
            loss = self.criterion(out, data.y)
            loss.backward()
            self.optimizer.step()

            total_loss += loss.item()

        return total_loss / len(train_loader)

    def validate(self, val_loader: DataLoader) -> Tuple[float, float]:
        """Validate the model."""
        self.model.eval()
        total_loss = 0
        correct = 0

        with torch.no_grad():
            for data in val_loader:
                data = data.to(self.device)
                out = self.model(data.x, data.edge_index, data.batch)
                loss = self.criterion(out, data.y)
                total_loss += loss.item()

                pred = out.argmax(dim=1)
                correct += (pred == data.y).sum().item()

        accuracy = correct / len(val_loader.dataset)
        avg_loss = total_loss / len(val_loader)

        return avg_loss, accuracy

    def train(self, train_loader: DataLoader, val_loader: DataLoader,
              num_epochs: int = 100, patience: int = 10) -> Dict[str, Any]:
        """Full training loop with early stopping."""
        best_val_acc = 0
        patience_counter = 0
        history = {'train_loss': [], 'val_loss': [], 'val_acc': []}

        for epoch in range(num_epochs):
            train_loss = self.train_epoch(train_loader)
            val_loss, val_acc = self.validate(val_loader)

            history['train_loss'].append(train_loss)
            history['val_loss'].append(val_loss)
            history['val_acc'].append(val_acc)

            logger.info(f"Epoch {epoch+1}/{num_epochs}: Train Loss={train_loss:.4f}, "
                       f"Val Loss={val_loss:.4f}, Val Acc={val_acc:.4f}")

            # Early stopping
            if val_acc > best_val_acc:
                best_val_acc = val_acc
                patience_counter = 0
                # Save best model
                torch.save(self.model.state_dict(), 'best_gnn_model.pth')
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info(f"Early stopping at epoch {epoch+1}")
                    break

        return history


def create_dummy_dataset(num_samples: int = 1000, num_classes: int = 5) -> List[Data]:
    """Create dummy dataset for testing. Replace with real data."""

    dataset = []
    for _ in range(num_samples):
        # Random graph with 10-50 nodes
        num_nodes = np.random.randint(10, 50)
        num_edges = np.random.randint(num_nodes, num_nodes * 3)

        # Random node features (6 features as in BRepGraphBuilder)
        x = torch.randn(num_nodes, 6)

        # Random edges
        edge_index = torch.randint(0, num_nodes, (2, num_edges))

        # Random label
        y = torch.randint(0, num_classes, (1,)).squeeze()

        data = Data(x=x, edge_index=edge_index, y=y)
        dataset.append(data)

    return dataset


def train_gnn_model(num_epochs: int = 100, batch_size: int = 32) -> ManufacturabilityGNN:
    """
    Train the GNN model on manufacturability data.

    Returns:
        Trained model ready for ONNX export
    """
    # Create dummy dataset - replace with real data loading
    dataset = create_dummy_dataset()
    train_size = int(0.8 * len(dataset))
    train_dataset = dataset[:train_size]
    val_dataset = dataset[train_size:]

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    # Initialize model
    num_node_features = 6  # From BRepGraphBuilder
    num_classes = 5  # Number of manufacturability classes
    model = ManufacturabilityGNN(num_node_features, num_classes)

    # Train
    trainer = GNNTrainer(model)
    history = trainer.train(train_loader, val_loader, num_epochs)

    # Load best model
    model.load_state_dict(torch.load('best_gnn_model.pth'))

    return model