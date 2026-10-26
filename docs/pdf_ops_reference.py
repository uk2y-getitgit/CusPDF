# PDF 처리 참고 코드 (호환성 시험에 사용한 코드)
# - 합치기, 일부 쪽 넣기, 빈 페이지, 회전, 간지, 글자 덮어쓰기, 회전 쪽 쪽번호, 글꼴 부분 포함 저장 예시
# - 실제 구현 시 구조는 CLAUDE.md의 폴더 구조를 따르고, 이 파일은 동작 확인용으로만 참고한다.

import pymupdf, io
from PIL import Image, ImageDraw
SERIF='/tmp/KoreanSerif.ttf'; SANSB='/tmp/KoreanSerif.ttf'
A4=pymupdf.paper_rect('a4')
fs=pymupdf.Font(fontfile=SERIF); fb=pymupdf.Font(fontfile=SANSB)

def write(page, items):
    tw=pymupdf.TextWriter(page.rect)
    for (x,y,t,font,size) in items: tw.append((x,y),t,font=font,fontsize=size)
    tw.write_text(page)

# 1) 한글로 만든 것처럼 보이는 본문 4쪽
body=pymupdf.open()
pages=[[(150,300,'2026년 정기 안전점검 보고서',fb,22),(200,420,'점검 일자: 2026. 10. 20.',fs,13),(200,445,'점검 기관: [회사명]',fs,13)],
       [(70,90,'1. 점검 개요',fb,15),(70,130,'측정 항목: 균열 폭, 콘크리트 반발경도',fs,11)],
       [(70,90,'2. 점검 결과 요약',fb,15),(70,130,'외벽: 부분 보수 필요 (C등급)',fs,11)],
       [(70,90,'3. 종합 의견',fb,15),(70,130,'외벽 3층 북측에서 폭 0.3mm 균열이 확인되었다.',fs,11)]]
for it in pages: write(body.new_page(width=A4.width,height=A4.height), it)

# 2) 첨부: 엑셀처럼 표가 있는 PDF
xl=pymupdf.open(); p=xl.new_page(width=A4.width,height=A4.height)
write(p,[(70,90,'첨부. 균열 측정 데이터',fb,15)])
for r in range(5):
    for c in range(3):
        rc=pymupdf.Rect(70+c*150,120+r*28,220+c*150,148+r*28); p.draw_rect(rc,color=(0.6,0.6,0.6),width=0.7)
write(p,[(78,139,'위치',fb,10),(228,139,'균열 폭(mm)',fb,10),(378,139,'판정',fb,10),(78,167,'3층 북측 외벽',fs,10),(228,167,'0.30',fs,10),(378,167,'보수',fs,10)])

# 3) 첨부: 휴대폰 사진(JPG) -> PDF 쪽
img=Image.new('RGB',(1200,900),(185,193,201)); d=ImageDraw.Draw(img); d.line([(600,80),(640,400),(590,820)],fill=(60,60,60),width=10)
buf=io.BytesIO(); img.save(buf,'JPEG',quality=85)
ph=pymupdf.open(); pp=ph.new_page(width=A4.width,height=A4.height)
pp.insert_image(pymupdf.Rect(60,80,A4.width-60,80+(A4.width-120)*0.75),stream=buf.getvalue())
write(pp,[(230,560,'현장사진_01 (3층 북측 외벽)',fs,11)])

# 4) 다른 기관 PDF 5쪽 (일부만 가져올 예정)
ext=pymupdf.open()
for i,t in enumerate(['회신 공문','붙임 1. 보수 계획서','붙임 2. 공정표','붙임 3. 사진 대장','붙임 4. 담당자 연락처']):
    write(ext.new_page(width=A4.width,height=A4.height),[(70,90,t,fb,15),(70,130,f'기관회신공문.pdf {i+1}쪽',fs,11)])

# ---- 프로그램 동작 재현 ----
doc=pymupdf.open(); doc.insert_pdf(body)          # 열기
doc.insert_pdf(xl)                                 # 파일 넣기(엑셀 변환본)
doc.insert_pdf(ph)                                 # 파일 넣기(사진)
doc.insert_pdf(ext, from_page=1, to_page=2)        # 옆 창: 2~3쪽만 넣기
doc.new_page(pno=2, width=A4.width, height=A4.height)  # 2쪽 뒤 빈 페이지 추가
doc[-1].set_rotation(90)                           # 회전
# 간지
dv=doc.new_page(pno=5,width=A4.width,height=A4.height); write(dv,[(200,420,'첨부 1. 균열 측정 데이터',fb,20)])
# 2단계 덮어쓰기 글자 수정: 표지 날짜
cover=doc[0]; hit=cover.search_for('2026. 10. 20.')[0]
cover.add_redact_annot(hit, fill=(1,1,1))
cover.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
write(cover,[(hit.x0, hit.y1-2.6,'2026. 10. 22.',fs,13)])
# 쪽번호 (표지 제외) - 회전된 쪽은 "보이는 방향" 기준으로 위치 계산
n=len(doc)
for i in range(1,n):
    pg=doc[i]; r=pg.rect; txt=f'- {i} -'
    w=fs.text_length(txt, fontsize=10)
    pv=pymupdf.Point(r.width/2-w/2, r.height-30)
    pg.insert_text(pv*pg.derotation_matrix, txt, fontsize=10, fontname='kr', fontfile=SERIF, rotate=pg.rotation)
doc.subset_fonts()
doc.save('보고서_호환성시험.pdf', garbage=4, deflate=True, clean=True)
print('pages',len(doc))
