# GPU edge image: PyTorch + CUDA runtime; requires NVIDIA Container Toolkit on the host.
FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/srv
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt opencv-python-headless sentence-transformers
# Optional TensorRT acceleration (match your CUDA): pip install torch-tensorrt
COPY ai_core /srv/ai_core
COPY security /srv/security
CMD ["python", "-m", "ai_core.vision.edge_service"]
