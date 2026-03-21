# segmentation/training/pointnet_trainer.py
"""
Training script for PointNet++ model on mesh point clouds.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import numpy as np
from typing import List, Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)


class PointNetSetAbstraction(nn.Module):
    """Set Abstraction layer from PointNet++."""

    def __init__(self, npoint: int, radius: float, nsample: int, in_channel: int, mlp: List[int]):
        super().__init__()
        self.npoint = npoint
        self.radius = radius
        self.nsample = nsample
        self.mlp_convs = nn.ModuleList()
        self.mlp_bns = nn.ModuleList()

        last_channel = in_channel
        for out_channel in mlp:
            self.mlp_convs.append(nn.Conv2d(last_channel, out_channel, 1))
            self.mlp_bns.append(nn.BatchNorm2d(out_channel))
            last_channel = out_channel

    def forward(self, xyz: torch.Tensor, points: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            xyz: (B, N, 3) coordinates
            points: (B, N, C) features
        Returns:
            new_xyz: (B, npoint, 3)
            new_points: (B, npoint, C')
        """
        new_xyz = self.index_points(xyz, self.farthest_point_sample(xyz, self.npoint))

        new_points = []
        for i in range(xyz.shape[0]):
            dists = self.square_distance(new_xyz[i:i+1], xyz[i:i+1])
            group_idx = dists.argsort()[:, :, :self.nsample]
            grouped_xyz = self.index_points(xyz[i:i+1], group_idx)
            grouped_xyz -= new_xyz[i:i+1].unsqueeze(2)

            if points is not None:
                grouped_points = self.index_points(points[i:i+1], group_idx)
                grouped_points = torch.cat([grouped_xyz, grouped_points], dim=-1)
            else:
                grouped_points = grouped_xyz

            grouped_points = grouped_points.permute(0, 3, 2, 1)  # (B, C, nsample, npoint)
            for j, conv in enumerate(self.mlp_convs):
                grouped_points = F.relu(self.mlp_bns[j](conv(grouped_points)))

            new_points.append(grouped_points.max(dim=2)[0])  # (B, C', npoint)

        new_points = torch.stack(new_points, dim=0).transpose(2, 1)  # (B, npoint, C')

        return new_xyz, new_points

    @staticmethod
    def farthest_point_sample(xyz: torch.Tensor, npoint: int) -> torch.Tensor:
        """Farthest point sampling."""
        device = xyz.device
        B, N, C = xyz.shape
        centroids = torch.zeros(B, npoint, dtype=torch.long).to(device)
        distance = torch.ones(B, N).to(device) * 1e10
        farthest = torch.randint(0, N, (B,), dtype=torch.long).to(device)

        batch_indices = torch.arange(B, dtype=torch.long).to(device)

        for i in range(npoint):
            centroids[:, i] = farthest
            centroid = xyz[batch_indices, farthest, :].view(B, 1, 3)
            dist = torch.sum((xyz - centroid) ** 2, -1)
            mask = dist < distance
            distance[mask] = dist[mask]
            farthest = torch.max(distance, -1)[1]

        return centroids

    @staticmethod
    def index_points(points: torch.Tensor, idx: torch.Tensor) -> torch.Tensor:
        """Index points."""
        device = points.device
        B = points.shape[0]
        view_shape = list(idx.shape)
        view_shape[1:] = [1] * (len(view_shape) - 1)
        repeat_shape = list(idx.shape)
        repeat_shape[0] = 1
        batch_indices = torch.arange(B, dtype=torch.long).to(device).view(view_shape).repeat(repeat_shape)
        new_points = points[batch_indices, idx, :]
        return new_points

    @staticmethod
    def square_distance(src: torch.Tensor, dst: torch.Tensor) -> torch.Tensor:
        """Calculate squared distance."""
        B, N, _ = src.shape
        _, M, _ = dst.shape
        dist = -2 * torch.matmul(src, dst.permute(0, 2, 1))
        dist += torch.sum(src ** 2, -1).view(B, N, 1)
        dist += torch.sum(dst ** 2, -1).view(B, 1, M)
        return dist


class PointNetPlusPlus(nn.Module):
    """PointNet++ model for manufacturability classification."""

    def __init__(self, num_classes: int = 5):
        super().__init__()

        # Set abstraction layers
        self.sa1 = PointNetSetAbstraction(512, 0.2, 32, 6, [64, 64, 128])  # 6 features: xyz + normals
        self.sa2 = PointNetSetAbstraction(128, 0.4, 64, 128, [128, 128, 256])
        self.sa3 = PointNetSetAbstraction(None, None, None, 256, [256, 512, 1024])

        # Feature propagation (simplified)
        self.fp3 = nn.Linear(1024, 256)
        self.fp2 = nn.Linear(256, 256)
        self.fp1 = nn.Linear(256, 128)

        # Classification head
        self.classifier = nn.Sequential(
            nn.Linear(128, 512),
            nn.BatchNorm1d(512),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(512, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(256, num_classes)
        )

    def forward(self, xyz: torch.Tensor) -> torch.Tensor:
        """
        Args:
            xyz: (B, N, 6) point cloud with normals
        Returns:
            logits: (B, num_classes)
        """
        B, _, _ = xyz.shape

        # Split coordinates and features
        l0_xyz = xyz[:, :, :3]  # (B, N, 3)
        l0_points = xyz[:, :, 3:]  # (B, N, 3) normals

        # Set abstraction
        l1_xyz, l1_points = self.sa1(l0_xyz, l0_points)
        l2_xyz, l2_points = self.sa2(l1_xyz, l1_points)
        l3_xyz, l3_points = self.sa3(l2_xyz, l2_points)

        # Feature propagation (simplified - just global pooling)
        x = l3_points.mean(dim=1)  # (B, 1024)

        # Classification
        x = self.classifier(x)
        return x


class PointCloudDataset(Dataset):
    """Dataset for point cloud data."""

    def __init__(self, point_clouds: List[torch.Tensor], labels: List[int]):
        self.point_clouds = point_clouds
        self.labels = labels

    def __len__(self):
        return len(self.point_clouds)

    def __getitem__(self, idx):
        return self.point_clouds[idx], self.labels[idx]


class PointNetTrainer:
    """Trainer for PointNet++ model."""

    def __init__(self, model: nn.Module, device: str = 'cuda' if torch.cuda.is_available() else 'cpu'):
        self.model = model.to(device)
        self.device = device
        self.optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        self.criterion = nn.CrossEntropyLoss()

    def train_epoch(self, train_loader: DataLoader) -> float:
        """Train for one epoch."""
        self.model.train()
        total_loss = 0

        for points, labels in train_loader:
            points = points.to(self.device)
            labels = labels.to(self.device)

            self.optimizer.zero_grad()
            outputs = self.model(points)
            loss = self.criterion(outputs, labels)
            loss.backward()
            self.optimizer.step()

            total_loss += loss.item()

        return total_loss / len(train_loader)

    def validate(self, val_loader: DataLoader) -> Tuple[float, float]:
        """Validate the model."""
        self.model.eval()
        total_loss = 0
        correct = 0
        total = 0

        with torch.no_grad():
            for points, labels in val_loader:
                points = points.to(self.device)
                labels = labels.to(self.device)

                outputs = self.model(points)
                loss = self.criterion(outputs, labels)
                total_loss += loss.item()

                _, predicted = outputs.max(1)
                total += labels.size(0)
                correct += predicted.eq(labels).sum().item()

        accuracy = correct / total
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
                torch.save(self.model.state_dict(), 'best_pointnet_model.pth')
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info(f"Early stopping at epoch {epoch+1}")
                    break

        return history


def create_dummy_point_cloud_dataset(num_samples: int = 1000, num_points: int = 1024,
                                   num_classes: int = 5) -> Tuple[List[torch.Tensor], List[int]]:
    """Create dummy point cloud dataset for testing."""
    point_clouds = []
    labels = []

    for _ in range(num_samples):
        # Random point cloud: xyz + normals
        points = torch.randn(num_points, 6)  # xyz + normal_xyz
        label = np.random.randint(0, num_classes)

        point_clouds.append(points)
        labels.append(label)

    return point_clouds, labels


def train_pointnet_model(num_epochs: int = 100, batch_size: int = 16) -> PointNetPlusPlus:
    """
    Train the PointNet++ model on manufacturability data.

    Returns:
        Trained model ready for ONNX export
    """
    # Create dummy dataset - replace with real data loading
    point_clouds, labels = create_dummy_point_cloud_dataset()
    train_size = int(0.8 * len(point_clouds))

    train_dataset = PointCloudDataset(point_clouds[:train_size], labels[:train_size])
    val_dataset = PointCloudDataset(point_clouds[train_size:], labels[train_size:])

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    # Initialize model
    model = PointNetPlusPlus(num_classes=5)

    # Train
    trainer = PointNetTrainer(model)
    history = trainer.train(train_loader, val_loader, num_epochs)

    # Load best model
    model.load_state_dict(torch.load('best_pointnet_model.pth'))

    return model