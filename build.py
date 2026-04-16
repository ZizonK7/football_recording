import os
import sys
import ctypes

import sys
import os

# --windowed 모드에서 입출력 에러 방지
if sys.stdin is None:
    sys.stdin = open(os.devnull, "r")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# 1. 작업표시줄 아이콘을 위해 AppUserModelID 설정
myappid = 'mycompany.myproduct.subproduct.version' # 임의의 고유 ID
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

# 2. 리소스 경로 찾는 함수 (빌드 후 아이콘 경로 깨짐 방지)
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# 예시: 아이콘 경로 설정
icon_path = resource_path("assets/thumbnail.ico")

# --- 여기에 나머지 프로그램 코드를 작성하세요 ---
print("프로그램 실행 중...")
input("종료하려면 엔터를 누르세요.")