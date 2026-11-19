import asyncio
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from app.services.retrieval_service import RetrievedChunk

logger = logging.getLogger(__name__)
REPOSITORY = "onnx-community/bge-reranker-v2-m3-ONNX"
REVISION = "90213ff"
MODEL_FILE = Path("onnx/model_quantized.onnx")
TOKENIZER_FILE = Path("tokenizer.json")
CANDIDATE_LIMIT = 8
BATCH_SIZE = 4
# Cancelling a request cannot stop a running ONNX batch. A single worker keeps CPU and RAM bounded.
_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag-reranker")


def model_path(storage_directory: Path) -> Path:
    return storage_directory.parent / "model-cache" / "bge-reranker-v2-m3"


def prepare_model(model_directory: Path) -> None:
    from huggingface_hub import hf_hub_download

    for filename in (TOKENIZER_FILE, MODEL_FILE):
        hf_hub_download(
            REPOSITORY, filename.as_posix(), revision=REVISION, local_dir=model_directory
        )


@lru_cache(maxsize=1)
def _load_model(model_directory: Path):
    import onnxruntime as ort
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(model_directory / TOKENIZER_FILE))
    tokenizer.enable_truncation(max_length=384)
    tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
    config = ort.SessionOptions()
    config.intra_op_num_threads = 4
    session = ort.InferenceSession(
        str(model_directory / MODEL_FILE), sess_options=config, providers=["CPUExecutionProvider"]
    )
    return tokenizer, session


def _score(model_directory: Path, query: str, candidates: list[RetrievedChunk]) -> list[float]:
    import numpy as np

    tokenizer, session = _load_model(model_directory)
    scores: list[float] = []
    for start in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[start : start + BATCH_SIZE]
        encoded = tokenizer.encode_batch([(query, chunk.content) for chunk in batch])
        inputs = {
            "input_ids": [item.ids for item in encoded],
            "attention_mask": [item.attention_mask for item in encoded],
            "token_type_ids": [item.type_ids for item in encoded],
        }
        logits = session.run(
            None,
            {
                item.name: np.asarray(inputs[item.name], dtype=np.int64)
                for item in session.get_inputs()
            },
        )[0]
        scores.extend(logits.reshape(-1).tolist())
    if len(scores) != len(candidates) or not all(math.isfinite(score) for score in scores):
        raise ValueError("Reranker geçersiz skor döndürdü.")
    return scores


async def rerank_chunks(
    *, model_directory: Path, query: str, candidates: list[RetrievedChunk], strict: bool = False
) -> list[RetrievedChunk]:
    if len(candidates) < 2:
        return candidates
    try:
        scores = await asyncio.get_running_loop().run_in_executor(
            _worker, _score, model_directory, query, candidates
        )
    except Exception:
        if strict:
            raise
        logger.warning("Reranker kullanılamadı, hibrit sıralama kullanılıyor.", exc_info=True)
        return candidates

    order = sorted(range(len(candidates)), key=scores.__getitem__, reverse=True)
    return [candidates[index] for index in order]
