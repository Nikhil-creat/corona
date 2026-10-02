"""Production inference path: RTSP frames → HybridSpatialNet (CUDA / TensorRT) → AnomalyEvent."""
from __future__ import annotations

import logging
import os

from ai_core.common.schemas import AnomalyEvent, Detection, TelemetryPacket

from .labels import CLASSES, MODALITY

log = logging.getLogger(__name__)


class FrameSource:
    """Reads an RTSP stream with OpenCV; yields RGB float tensors (3,H,W)."""

    def __init__(self, url: str, size: int = 224) -> None:
        import cv2

        self._cv2, self._size = cv2, size
        self._cap = cv2.VideoCapture(url)

    def read(self):
        import numpy as np

        ok, frame = self._cap.read()
        if not ok:
            return None
        frame = self._cv2.cvtColor(self._cv2.resize(frame, (self._size, self._size)), self._cv2.COLOR_BGR2RGB)
        return (frame.astype(np.float32) / 255.0).transpose(2, 0, 1)


class TorchDetector:
    def __init__(self, weights_path: str, use_tensorrt: bool = True) -> None:
        import torch

        from .model import HybridSpatialNet

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        net = HybridSpatialNet().eval().to(self.device)
        if os.path.exists(weights_path):
            net.load_state_dict(torch.load(weights_path, map_location=self.device))
        else:
            log.warning("weights %s not found — running with RANDOM weights (demo only)", weights_path)
        self.net = net.half() if self.device == "cuda" else net
        if use_tensorrt and self.device == "cuda":
            try:
                import torch_tensorrt

                example = torch.randn(1, 4, 224, 224, device=self.device, dtype=torch.half)
                self.net = torch_tensorrt.compile(self.net, inputs=[example], enabled_precisions={torch.half})
                log.info("TensorRT engine compiled")
            except Exception as exc:  # pragma: no cover
                log.warning("TensorRT unavailable (%s); using eager PyTorch", exc)

    def detect(self, rgb, thermal, pkt: TelemetryPacket, threshold: float = 0.6) -> AnomalyEvent | None:
        torch = self.torch
        t = thermal if thermal is not None else torch.zeros(1, rgb.shape[-2], rgb.shape[-1])
        x = torch.cat([torch.as_tensor(rgb), torch.as_tensor(t)], dim=0).unsqueeze(0).to(self.device)
        x = x.half() if self.device == "cuda" else x
        with torch.inference_mode():
            out = self.net(x)
        probs = out["logits"].float().softmax(-1)[0]
        idx = int(probs[1:].argmax()) + 1
        conf = float(probs[idx])
        if conf < threshold:
            return None
        cx, cy, w, h = (float(v) for v in out["box"].float()[0])
        det = Detection(label=CLASSES[idx], confidence=conf, bbox=(max(cx - w / 2, 0), max(cy - h / 2, 0), w, h))
        return AnomalyEvent(node_id=pkt.node_id, modality=MODALITY[CLASSES[idx]], label=CLASSES[idx],  # type: ignore[arg-type]
                            severity=float(out["severity"].float()[0]), confidence=conf, detections=[det], telemetry=pkt)


def export_onnx(weights: str, out: str = "hybrid_spatialnet.onnx") -> None:
    """Then: trtexec --onnx=hybrid_spatialnet.onnx --fp16 --saveEngine=hybrid_spatialnet.engine"""
    import torch

    from .model import HybridSpatialNet

    net = HybridSpatialNet().eval()
    net.load_state_dict(torch.load(weights, map_location="cpu"))
    torch.onnx.export(net, torch.randn(1, 4, 224, 224), out, opset_version=17, input_names=["x"],
                      output_names=["logits", "severity", "box"], dynamic_axes={"x": {0: "batch"}})
