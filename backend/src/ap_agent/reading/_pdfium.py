"""PDFium is not thread-safe, and cases run in parallel worker threads: every PDFium call holds this lock."""
import threading

PDFIUM_LOCK = threading.RLock()
