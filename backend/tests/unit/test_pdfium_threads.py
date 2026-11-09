"""PDFium is not thread-safe: parallel cases must not crash the process."""
import subprocess
import sys
import textwrap

from ap_agent.core.config import REPO_ROOT


def test_parallel_pdf_reading_does_not_crash(tmp_path):
    code = textwrap.dedent(f"""
        import sys, threading
        sys.path[:0] = [{str(REPO_ROOT / 'backend' / 'src')!r}]
        from pathlib import Path
        from ap_agent.reading.render import render_pages
        from ap_agent.reading.pdfinfo import inspect_pdf
        from ap_agent.reading.text_layer import text_layer
        pdfs = [Path({str(REPO_ROOT / 'samples' / 'pdf')!r}) / f'S0{{i}}.pdf' for i in range(1, 9)]
        def go(i):
            for k in range(4):
                inspect_pdf(pdfs[i]); text_layer(pdfs[i]); render_pages(pdfs[i], Path({str(tmp_path)!r}) / f'{{i}}-{{k}}')
        ts = [threading.Thread(target=go, args=(i,)) for i in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        print('ok')
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180)
    assert r.returncode == 0 and "ok" in r.stdout and "access violation" not in r.stderr, r.stderr[-800:]
