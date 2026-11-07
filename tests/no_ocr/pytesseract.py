"""Shadow pytesseract in test subprocesses so pages are never OCRed.

CI has no tesseract; this keeps local runs on the same path and fast. The one test
that exercises OCR on purpose runs without this directory on PYTHONPATH.
"""

raise ImportError("OCR is disabled in the test suite")
