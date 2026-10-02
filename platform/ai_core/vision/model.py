"""Hybrid EfficientNet-V2 (local texture) + Vision Transformer (global context) multi-modal spatial anomaly net.

Input : 4 channels = RGB optical + 1 thermal (zero-fill if no thermal camera)
Heads : class logits, severity∈[0,1], bounding box (cx,cy,w,h)∈[0,1]
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torchvision.models as tvm

from .labels import CLASSES


class HybridSpatialNet(nn.Module):
    def __init__(self, num_classes: int = len(CLASSES), embed_dim: int = 256, vit_layers: int = 2,
                 heads: int = 8, pretrained: bool = False) -> None:
        super().__init__()
        weights = tvm.EfficientNet_V2_S_Weights.DEFAULT if pretrained else None
        backbone = tvm.efficientnet_v2_s(weights=weights).features
        old = backbone[0][0]
        new = nn.Conv2d(4, old.out_channels, old.kernel_size, old.stride, old.padding, bias=False)
        with torch.no_grad():
            new.weight[:, :3] = old.weight
            new.weight[:, 3:] = old.weight.mean(dim=1, keepdim=True)  # thermal channel initialised from mean RGB filter
        backbone[0][0] = new
        self.cnn = backbone
        self.proj = nn.Conv2d(1280, embed_dim, kernel_size=1)
        self.cls = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.pos = nn.Parameter(torch.zeros(1, 1 + 14 * 14, embed_dim))  # resized at runtime if input differs
        layer = nn.TransformerEncoderLayer(embed_dim, heads, embed_dim * 4, dropout=0.1, batch_first=True, norm_first=True)
        self.vit = nn.TransformerEncoder(layer, vit_layers)
        self.norm = nn.LayerNorm(embed_dim)
        self.head_cls = nn.Linear(embed_dim, num_classes)
        self.head_sev = nn.Sequential(nn.Linear(embed_dim, 64), nn.GELU(), nn.Linear(64, 1), nn.Sigmoid())
        self.head_box = nn.Sequential(nn.Linear(embed_dim, 64), nn.GELU(), nn.Linear(64, 4), nn.Sigmoid())
        nn.init.trunc_normal_(self.pos, std=0.02)
        nn.init.trunc_normal_(self.cls, std=0.02)

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        f = self.proj(self.cnn(x))                       # B,C,H,W
        b, c, h, w = f.shape
        tokens = f.flatten(2).transpose(1, 2)            # B,HW,C
        tokens = torch.cat([self.cls.expand(b, -1, -1), tokens], dim=1)
        pos = self.pos
        if pos.shape[1] != tokens.shape[1]:
            grid = pos[:, 1:].transpose(1, 2).reshape(1, c, 14, 14)
            grid = nn.functional.interpolate(grid, size=(h, w), mode="bilinear", align_corners=False)
            pos = torch.cat([pos[:, :1], grid.flatten(2).transpose(1, 2)], dim=1)
        z = self.norm(self.vit(tokens + pos))[:, 0]
        return {"logits": self.head_cls(z), "severity": self.head_sev(z).squeeze(-1), "box": self.head_box(z)}
