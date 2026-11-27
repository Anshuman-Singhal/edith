"""Edge perception (WS-E, PLAN §3.5, D8).

Pipeline per feed: FrameSource (RTP H.264 + SEI frame_id, sidecar FrameMeta) or OffloadDetector
(``[Detection]`` on UDP 5800+i) → Scheduler → detector (tiled YOLOX-Tiny) → geo (pixel → ground,
CE90) → ground-plane ENU Kalman tracker (or the motion-compensated image-plane tracker for
``geo_quality: pseudo`` replay feeds) → fusion across drones → novelty → friendly association.

Machine detections are always affiliation ``unknown`` (I6). This package never imports
``edith_sim`` and never reads frame truth.
"""
