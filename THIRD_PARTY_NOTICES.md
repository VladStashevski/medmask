# Third-party OCR components

MedMask includes RapidOCR 3.9.2 and ONNX models derived from PaddleOCR. RapidOCR
and PaddleOCR are distributed under the Apache License 2.0.

- RapidOCR: https://github.com/RapidAI/RapidOCR
- PaddleOCR: https://github.com/PaddlePaddle/PaddleOCR
- Model manifest: `rapidocr/default_models.yaml` from RapidOCR 3.9.2

Bundled model checksums:

- `PP-OCRv6_det_small.onnx`: `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f`
- `ch_ppocr_mobile_v2.0_cls_mobile.onnx`: `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c`
- `cyrillic_PP-OCRv5_rec_mobile.onnx`: `90f761b4bfcce0c8c561c0cb5c887b0971d3ec01c32164bdf7374a35b0982711`

# PDF engine

MedMask uses PyMuPDF, which Artifex offers under the GNU Affero General Public
License v3.0 or a separate commercial license. This repository does not include
an Artifex commercial license. Distributing a closed-source MedMask build
therefore requires a separately obtained commercial license or full compliance
with the AGPL, including its corresponding-source obligations.

- PyMuPDF licensing: https://pymupdf.readthedocs.io/en/latest/about.html#license
- GNU AGPL v3: https://www.gnu.org/licenses/agpl-3.0.html

# Bundled font

MedMask includes Liberation Sans 2.1.5 (`LiberationSans-Regular.ttf`) so that
output PDFs do not depend on fonts installed in the operating system.

- Liberation Fonts: https://github.com/liberationfonts/liberation-fonts
- License: SIL Open Font License, Version 1.1
- Copyright (c) 2012 Red Hat, Inc. with Reserved Font Name Liberation;
  digitized data copyright (c) 2010 Google Corporation with Reserved Font Name
  Arimo, Tinos and Cousine.
- `LiberationSans-Regular.ttf`: `76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8`
