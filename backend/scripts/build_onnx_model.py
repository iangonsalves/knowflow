"""Download the pinned E5 ONNX graph and dynamically quantize it for generic CPUs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from huggingface_hub import hf_hub_download
from onnx import checker, load
from onnxruntime.quantization import QuantType, quantize_dynamic

MODEL = "intfloat/e5-small-v2"
REVISION = "ffb93f3bd4047442299a41ebb6fa998a38507c52"
MODEL_ONNX_SHA256 = "4b8205be2a3c5fc53c6534d76a2012064f7309c162b806f2889c6ec8ec4fdcba"
OUTPUT = Path(os.environ.get("KNOWFLOW_ONNX_ARTIFACT_DIR", "/opt/knowflow-model/e5-small-v2"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source_model = Path(hf_hub_download(repo_id=MODEL, filename="model.onnx", revision=REVISION))
    tokenizer = Path(hf_hub_download(repo_id=MODEL, filename="tokenizer.json", revision=REVISION))
    actual_hash = sha256_file(source_model)
    if actual_hash != MODEL_ONNX_SHA256:
        raise SystemExit(f"Pinned ONNX graph SHA-256 mismatch: {actual_hash}")

    output_model = OUTPUT / "model.onnx"
    quantize_dynamic(
        model_input=str(source_model),
        model_output=str(output_model),
        op_types_to_quantize=["MatMul"],
        per_channel=True,
        reduce_range=False,
        weight_type=QuantType.QInt8,
    )
    checker.check_model(load(str(output_model), load_external_data=True))
    tokenizer_target = OUTPUT / "tokenizer.json"
    tokenizer_target.write_bytes(tokenizer.read_bytes())
    manifest = {
        "model": MODEL,
        "revision": REVISION,
        "source_onnx_sha256": actual_hash,
        "quantization": "ONNX Runtime dynamic QInt8 MatMul, per-channel weights",
        "cpu_execution_provider": "CPUExecutionProvider",
        "isa_requirement": "generic CPU; no AVX512/VNNI-specific artifact",
        "dimensions": 384,
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "normalization": "L2",
        "source_model_bytes": source_model.stat().st_size,
        "quantized_model_bytes": output_model.stat().st_size,
        "tokenizer_bytes": tokenizer_target.stat().st_size,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
