# 바통터치 · 업무 인수인계

Python 기반 업무자료 분석·AI 인수인계 웹 애플리케이션입니다. 최신 전체 기능을 Vercel 함수와 기존 공유 저장소를 통해 실행합니다.

- 새올 ID 소문자 정규화, 조직도 직원 매핑, 최초 직원 활성화 및 비밀번호 설정
- PDF·HWPX·XLSX·텍스트 자료 등록, 파일·폴더 선택, 출처 추적
- 공통 Gemini 엔진의 초안 생성·자료 질의응답·누락 점검·답변 반영안
- 검토·저장·후임자 선택·요청 발송·수락·보완·완료
- 인수인계별 양방향 대화·파일 첨부·읽음·알림·대화방 목록
- 남양주시 보고서 스타일 HTML·MD·HWPX 출력과 마지막 인계·인수 요약서

실제 AI 응답을 모의 응답으로 자동 대체하지 않습니다. 모의 모드는 명시적 테스트 설정에서만 사용합니다. 업무자료 외부 전송은 별도 승인 설정을 충족해야 합니다.

설정·직원정보·데이터베이스 파일은 저장소에 포함하지 않습니다. 직원정보 외부 저장 승인이 AI 업무자료 외부 전송 승인까지 의미하지는 않습니다.

실행 구성과 플랫폼 제한, 내부 조직도 연계 방법은 [DEPLOYMENT.md](DEPLOYMENT.md)를 확인하세요. [.env.example](.env.example)은 항목 안내용이며 실제 키를 입력하여 커밋하면 안 됩니다.

Vercel은 `vercel.json`을 사용합니다. 공유 DB가 연결되지 않으면 비영속 임시 DB로 대체하지 않습니다. 초기화는 백업과 건별 확인·최종 승인 뒤에만 진행합니다.


## 소스 구조와 실행

- `backend/batontouch/auth`: 로그인·세션·비밀번호·직원 계정
- `backend/batontouch/organization`: 조직도·직원 조회와 동기화
- `backend/batontouch/handover`: 문서 검토·요청·수신·완료
- `backend/batontouch/ai`, `studio`: Gemini 공통 엔진과 AI 대화
- `backend/batontouch/materials`: 업로드·텍스트 추출·출처
- `backend/batontouch/reports`: 문서 데이터·HTML·HWPX 생성
- `backend/batontouch/chat`: 대화방·읽음·알림
- `backend/batontouch/storage`: 공유 DB 연결·저장·진단
- `frontend/features`: 화면 기능별 소스
- `frontend/shared`: 공통 화면 기능
- `api/index.py`: 기존 Vercel API 진입점
- `templates`, `public`: 서식 원본·실제 사용하는 이미지와 영상
- `judge-test`: 심사용 가상자료와 공개 안내. 비공개 계정 파일은 Git 제외
- `tests`: 기능별 회귀 검사

기존 모듈명 호환 파일은 `backend/`에 모았습니다. 중복 구현이 아니라 같은 모듈 객체를 연결하므로 세션·캐시·설정 상태를 이중 생성하지 않습니다.

```powershell
python -m pip install -r requirements.txt
python frontend/build.py
python app.py
```

실제 공유 DB와 AI 설정은 기존 환경변수를 그대로 사용합니다. 환경파일을 자동 로드하거나 DB를 초기화하지 않습니다.

```powershell
python -m pip install -r requirements-test.txt
python tools/run_checks.py
python tools/run_checks.py --browser
```

브라우저 검사에는 Playwright와 설치된 Chromium 계열 브라우저가 필요합니다. `TEST_BROWSER`로 실행 파일 경로를 지정할 수 있습니다. 검사는 가상자료·분리된 저장소를 사용하며 운영 계정의 비밀번호를 재설정하지 않습니다.
