"""
Worker application for MuseTalk + Salad Job Queue.

This package runs inside the GPU worker container and exposes a small
HTTP API that the Salad HTTP Job Queue Worker can call:

- GET /hc       – health check
- POST /generate – run a single MuseTalk inference job and return results
"""

