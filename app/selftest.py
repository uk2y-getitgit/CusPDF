"""자체 점검: 실행 파일(.exe) 안에서도 변환·편집·저장이 되는지 확인한다 (개발자용, 화면 없음).

사용: 보고서PDF편집기.exe --selftest <시험 파일 폴더> <결과 폴더>
시험 파일 폴더의 hwp·엑셀·워드·사진·PDF를 변환해 하나로 합치고, 글자 검색과 저장을 해 본다.
결과는 <결과 폴더>\\selftest.log 에 적는다 (창 없는 실행 파일은 화면 출력이 없어서).
"""

import sys
import time
import traceback
from pathlib import Path


def run(source_dir: str, out_dir: str) -> int:
    from PySide6.QtCore import QCoreApplication, QEventLoop

    from app.convert.worker import Job, kind_of, start_worker
    from app.pdf.document import PdfDocument, load_source

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "selftest.log"
    lines: list[str] = []

    def log(text: str) -> None:
        lines.append(text)
        log_path.write_text("\n".join(lines), encoding="utf-8")

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    ok = True
    try:
        log(f"실행 파일: {sys.executable}  (frozen={getattr(sys, 'frozen', False)})")
        files = sorted(p for p in Path(source_dir).iterdir() if p.is_file() and kind_of(p))
        log(f"시험 파일 {len(files)}개: {', '.join(p.name for p in files)}")
        doc = PdfDocument()
        thread, worker = start_worker([Job(p, kind_of(p)) for p in files], None)
        loop = QEventLoop()
        results = []
        worker.converted.connect(lambda job, pdf, err: results.append((job, pdf, err)))
        worker.finished.connect(loop.quit)
        start = time.perf_counter()
        thread.start()
        loop.exec()
        thread.wait()
        for job, pdf, err in results:
            if err:
                ok = False
                log(f"  실패 {job.path.name}: {err}")
                continue
            source = load_source(pdf, job.kind, name=job.path.name, original=job.path)
            doc.insert_source(source, doc.page_count)
            log(f"  성공 {job.path.name} → {source.doc.page_count}쪽")
        worker.cleanup()
        log(f"변환 {time.perf_counter() - start:.1f}초, 합친 쪽 수 {doc.page_count}")
        if doc.page_count:
            doc.rotate([0])
            log(f"검색 '점검': {len(doc.search('점검'))}곳")
            target = out / "selftest_결과.pdf"
            doc.save(target)
            log(f"저장 {target.name} {target.stat().st_size // 1024}KB")
    except Exception:
        ok = False
        log("오류:\n" + traceback.format_exc())
    log("결과: " + ("통과" if ok else "실패"))
    app.quit()
    return 0 if ok else 1
