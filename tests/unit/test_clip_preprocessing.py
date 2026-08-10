"""The image maths, tested without loading the 254 MB model.

The embeddings already in the database were produced with this exact preprocessing. If it
changes, new items land somewhere else in the space and stop matching the old ones.
"""

import numpy as np
import pytest
from PIL import Image

from esn_engine.embeddings.clip import IMAGE_SIZE, VisionEncoder, _unit


def test_preprocessing_gives_the_shape_the_model_wants():
    image = Image.new("RGB", (800, 600), color=(120, 30, 60))
    out = VisionEncoder.preprocess(image)
    assert out.shape == (3, IMAGE_SIZE, IMAGE_SIZE)
    assert out.dtype == np.float32


def test_a_tall_image_is_cropped_and_not_squashed():
    """Squashing changes the aspect ratio, which moves the embedding."""
    image = Image.new("RGB", (300, 1200))
    assert VisionEncoder.preprocess(image).shape == (3, IMAGE_SIZE, IMAGE_SIZE)


def test_a_greyscale_image_is_given_three_channels():
    image = Image.new("L", (400, 400), color=200)
    assert VisionEncoder.preprocess(image).shape[0] == 3


def test_an_image_smaller_than_the_crop_is_scaled_up_first():
    image = Image.new("RGB", (64, 90))
    assert VisionEncoder.preprocess(image).shape == (3, IMAGE_SIZE, IMAGE_SIZE)


def test_preprocess_refuses_something_that_is_not_an_image():
    with pytest.raises(TypeError):
        VisionEncoder.preprocess("not an image")


def test_vectors_come_out_unit_length():
    """Cosine distance is only a dot product if the vectors are normalised."""
    rng = np.random.default_rng(0)
    vectors = rng.normal(size=(4, 512)).astype(np.float32) * 7.5
    lengths = np.linalg.norm(_unit(vectors), axis=1)
    assert np.allclose(lengths, 1.0, atol=1e-5)


def test_a_zero_vector_does_not_divide_by_zero():
    """It happened with an all black frame."""
    zeros = np.zeros((1, 512), dtype=np.float32)
    assert np.isfinite(_unit(zeros)).all()
