# 2. CLIP through ONNX Runtime instead of PyTorch

- Date: 2026-07-29
- Status: accepted

## Context

The search needs CLIP to turn a query into a vector in the same space as the images. The
normal way to do that is `torch` plus `open_clip`, which is what the first version used.

That pulls about 2.5 GB of wheels into the image for one function, turning a text string into
512 numbers. The container is meant to be something a person can pull and run.

## Decision

Export the CLIP ViT-B/32 text and vision encoders to ONNX once, and run them with
`onnxruntime` on the CPU. No torch anywhere in the dependencies. The tokenizer is the
HuggingFace `tokenizers` one, loaded from `tokenizer.json`.

## Consequences

Good: the runtime dependency is `onnxruntime` instead of torch. Only the text encoder is
needed to answer a search, which is 254 MB, and the vision encoder is only needed when new
media is added. Loading the session takes 1.24 s so it happens once at startup, and a query
embedding then takes a median of 21.8 ms.

Bad: the model is frozen. Fine tuning it is no longer a small change, it means going back to
torch, retraining and exporting again. If a newer CLIP is wanted, everything has to be
re-embedded because vectors from two different models cannot be compared.

The preprocessing is now mine to maintain. CLIP resizes on the shortest side and centre
crops, and it normalises with its own mean and standard deviation. Getting any of that wrong
puts new items slightly off from the 2,334 already stored. Nothing crashes, the results just
get worse, so the preprocessing has its own tests.

The weights are not in the repository. They are 600 MB, so they get mounted into the
container instead.
