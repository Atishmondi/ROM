import argparse
from densepose_utils import load_densepose_model, run_densepose_and_annotate

def main(input_path, output_path):
    print(f"[INFO] Loading DensePose model...")
    model = load_densepose_model()
    print(f"[INFO] Running DensePose on input video...")
    run_densepose_and_annotate(model, input_path, output_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Elbow ROM Analyzer with DensePose")
    parser.add_argument("--input", required=True, help="Path to the input video (e.g., hello.mp4)")
    parser.add_argument("--output", required=True, help="Path to save the output annotated video")
    args = parser.parse_args()

    main(args.input, args.output)
