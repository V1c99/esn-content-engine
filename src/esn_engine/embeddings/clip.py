"""CLIP ViT-B/32 on onnxruntime. No torch anywhere.

Only the text encoder is needed to answer a query. The vision encoder is here for adding new
media to the library later.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

# CLIP was trained with these, so the same numbers have to be used or the embeddings do not
# land in the same space as the ones already in the database.
MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32).reshape(3, 1, 1)
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32).reshape(3, 1, 1)

CONTEXT_LENGTH = 77
START_TOKEN = 49406
END_TOKEN = 49407
IMAGE_SIZE = 224


def _session(path: Path) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])


def _pooled_output(session: ort.InferenceSession) -> str:
    """The name of the output that holds the 512 numbers.

    The exported graph has more than one output and the order is not guaranteed, so it is
    picked by shape rather than by position.
    """
    for output in session.get_outputs():
        shape = output.shape
        if len(shape) == 2 and str(shape[-1]) == "512":
            return str(output.name)
    return str(session.get_outputs()[0].name)


class TextEncoder:
    """Turns a query into a 512-number vector."""

    def __init__(self, models_dir: Path) -> None:
        self._session = _session(models_dir / "clip_text.onnx")
        self._tokenizer = Tokenizer.from_file(str(models_dir / "tokenizer.json"))
        self._input_names = [i.name for i in self._session.get_inputs()]
        self._output = _pooled_output(self._session)

    def _tokenise(self, texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
        ids, masks = [], []
        for t in texts:
            encoded = self._tokenizer.encode(t).ids
            if not encoded or encoded[0] != START_TOKEN:
                encoded = [START_TOKEN, *encoded]
            if len(encoded) >= CONTEXT_LENGTH:
                encoded = [*encoded[: CONTEXT_LENGTH - 1], END_TOKEN]
            else:
                encoded = [*encoded, END_TOKEN]
            mask = [1] * len(encoded) + [0] * (CONTEXT_LENGTH - len(encoded))
            encoded = encoded + [0] * (CONTEXT_LENGTH - len(encoded))
            ids.append(encoded[:CONTEXT_LENGTH])
            masks.append(mask[:CONTEXT_LENGTH])
        return np.array(ids, dtype=np.int64), np.array(masks, dtype=np.int64)

    def embed(self, texts: list[str]) -> np.ndarray:
        ids, mask = self._tokenise(texts)
        feed = {name: (mask if "mask" in name.lower() else ids) for name in self._input_names}
        out = np.asarray(self._session.run([self._output], feed)[0], dtype=np.float32)
        if out.ndim == 3:
            out = out[:, 0, :]
        return _unit(out)

    def embed_one(self, text: str) -> list[float]:
        return [float(x) for x in self.embed([text])[0]]


class VisionEncoder:
    """Turns an image into a 512-number vector. Used when adding new media."""

    def __init__(self, models_dir: Path) -> None:
        self._session = _session(models_dir / "clip_vision.onnx")
        self._input = self._session.get_inputs()[0].name
        self._output = _pooled_output(self._session)

    @staticmethod
    def preprocess(image: object) -> np.ndarray:
        """Resize on the shortest side, then centre crop, the way CLIP expects.

        Squashing the image to 224x224 instead would change the aspect ratio and the
        embeddings come out slightly different from the ones already stored.
        """
        from PIL import Image

        if not isinstance(image, Image.Image):
            raise TypeError("preprocess needs a PIL image")
        width, height = image.size
        scale = IMAGE_SIZE / min(width, height)
        new_w = max(IMAGE_SIZE, round(width * scale))
        new_h = max(IMAGE_SIZE, round(height * scale))
        resized = image.resize((new_w, new_h), Image.Resampling.BICUBIC)
        left = (new_w - IMAGE_SIZE) // 2
        top = (new_h - IMAGE_SIZE) // 2
        cropped = resized.crop((left, top, left + IMAGE_SIZE, top + IMAGE_SIZE))

        array = np.asarray(cropped, dtype=np.float32) / 255.0
        if array.ndim == 2:
            array = np.stack([array] * 3, axis=-1)
        array = array[:, :, :3].transpose(2, 0, 1)
        return (array - MEAN) / STD

    def embed(self, batch: list[np.ndarray]) -> np.ndarray:
        x = np.stack(batch).astype(np.float32)
        out = np.asarray(self._session.run([self._output], {self._input: x})[0], dtype=np.float32)
        if out.ndim == 3:
            out = out[:, 0, :]
        return _unit(out)


def _unit(vectors: np.ndarray) -> np.ndarray:
    """L2 normalise, so cosine distance is the same thing as a dot product."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    unit: np.ndarray = vectors / (norms + 1e-8)
    return unit
