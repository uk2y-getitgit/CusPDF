# 보고서 PDF 편집기 실행 파일(.exe) 만들기
# 사용: PowerShell에서 이 폴더로 이동한 뒤  .\build_exe.ps1
# 결과: build\dist\보고서PDF편집기\보고서PDF편집기.exe  (폴더째로 옮겨서 써야 함)

$root = $PSScriptRoot
& "$root\.venv\Scripts\pyinstaller.exe" "$root\main.py" --name "보고서PDF편집기" --windowed --noconfirm --clean `
  --icon "$root\app\resources\icon.ico" `
  --add-data "$root\app\resources;app\resources" `
  --exclude-module pandas --exclude-module numpy --exclude-module tkinter --exclude-module matplotlib --exclude-module pyhwpx `
  --distpath "$root\build\dist" --workpath "$root\build\work" --specpath "$root\build"

# 자체 점검 (화면 없이 변환·저장 확인): 시험 파일 폴더와 결과 폴더를 주면 결과 폴더에 selftest.log가 생긴다
#   & "$root\build\dist\보고서PDF편집기\보고서PDF편집기.exe" --selftest <시험 파일 폴더> <결과 폴더>
