import os
import sys
import cv2
import torch
import numpy as np

# Add DensePose path to sys.path
densepose_path = os.path.expanduser("~/Desktop/detectron2/projects/DensePose")
if densepose_path not in sys.path:
    sys.path.insert(0, densepose_path)

# Detectron2 + DensePose imports
from detectron2.config import get_cfg
from detectron2.engine import DefaultPredictor
from detectron2.utils.visualizer import Visualizer
from detectron2.data import MetadataCatalog

from densepose import add_densepose_config


def load_densepose_model():
    cfg = get_cfg()
    add_densepose_config(cfg)

    # Load YAML config from your elbow_rom/configs folder
    config_file = "configs/densepose_rcnn_R_50_FPN_s1x.yaml"
    cfg.merge_from_file(config_file)

    # Set the model weights path (update if you move model elsewhere)
    cfg.MODEL.WEIGHTS = "https://dl.fbaipublicfiles.com/densepose/densepose_rcnn_R_50_FPN_s1x/165712471/model_final_162be9.pkl"

    cfg.MODEL.DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = 0.5  # Filter weak detections
    predictor = DefaultPredictor(cfg)
    return predictor


def run_densepose_and_annotate(predictor, input_path, output_path):
    cap = cv2.VideoCapture(input_path)

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    metadata = MetadataCatalog.get("densepose_coco_2014_train")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        outputs = predictor(frame)
        v = Visualizer(frame[:, :, ::-1], metadata=metadata, scale=1.0)
        result = v.draw_instance_predictions(outputs["instances"].to("cpu"))

        annotated = result.get_image()[:, :, ::-1]
        out.write(annotated)

    cap.release()
    out.release()
    print(f"✅ Output video saved to: {output_path}")
