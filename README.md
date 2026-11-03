# 업무인수인계 바통터치 — 공개 테스트 배포본

Vercel 프로젝트: `botontouch-test`

이 저장소는 로컬 업무 시스템에서 분리한 **가상 데이터 전용** 배포본입니다.
실제 직원 명부, 내부 조직도 주소, 운영 DB, 첨부자료, 비밀번호, API 키 및 로컬 Git 이력은 포함하지 않습니다.

## 사용 흐름

1. 발급받은 가상 계정 `demo.a`로 로그인합니다.
2. **인수인계 시작하기**에서 가상 업무명과 작은 가상 파일을 등록합니다.
3. AI 초안 작성 → 직접 수정 → 저장을 진행합니다.
4. 가상 업무지원팀의 **가상 인수자**를 선택하여 요청합니다.
5. 별도 브라우저에서 `demo.b`로 로그인하면 받은 인수인계에서 확인·수락할 수 있습니다.
6. 인계자는 보낸 인수인계에서 최종 완료할 수 있습니다.

비밀번호는 저장소에 공개하지 않습니다. 사이트 소유자에게 별도로 전달합니다.
AI는 **테스트 응답이며 실제 AI가 아닙니다**. 외부 AI 또는 실제 조직도 호출 코드를 이 배포본에 포함하지 않았습니다.

## 배포 구조와 제한

- Python 3.12 / Vercel Python Function (`api/index.py`)
- 기존 HTML·CSS·JavaScript 화면과 Python 업무 로직 재사용
- Neon 무료 PostgreSQL에 작은 SQLite 스냅샷을 저장
- 요청별 PostgreSQL 행 잠금 → 임시 SQLite로 처리 → 공유 DB 커밋 성공 후 HTTP 응답
- 세션·문서·원본 파일·요청 이력을 공유 저장하여 함수 재시작 이후에도 보존
- 요청 종료 시 임시 DB 폴더 삭제. 영속 DB 연결이 없으면 저장 성공을 표시하지 않고 차단
- **요청/응답 4MB 이하**, 전체 테스트 DB 스냅샷 **20MB 이하**
- TXT·HWPX·텍스트형 PDF·XLSX 등록 / HWPX·DOCX 출력
- DOCX 입력, OCR, 실제 SSO·기관 조직도·실제 AI는 지원하지 않음

Vercel 함수의 본문 제한 때문에 로컬의 10MB 업로드 제한을 이 배포본에서는 4MB로 낮췄습니다.
파일은 인증된 API를 거쳐야 접근할 수 있으며 외부 공개 정적 파일로 저장하지 않습니다.

이 구조는 **소규모 시연·기능 검증 전용**입니다. 모든 요청을 직렬 처리하고 DB 전체를 전송하므로 다수 직원의 운영용으로 사용하면 안 됩니다.
운영 배포에는 업무 테이블의 PostgreSQL 전환, 별도 비공개 파일 저장소, 용량/백업/보존 정책과 부하 검증이 필요합니다.
무료 요금제의 할당량·휴면·플랫폼 제한은 별도로 적용됩니다.

## 환경변수 (Vercel 서버 전용)

`.env.example`에는 항목 이름만 있습니다. 실제 값은 Vercel 프로젝트 환경변수에 저장하세요.

- `DATABASE_URL`: 별도 Neon 테스트 DB의 연결 문자열
- `BATON_DEMO_PASSWORD`: 가상 계정용 무작위 비밀번호(16자 이상)
- `BATON_PUBLIC_ORIGIN`: 실제 HTTPS 배포 원점(선택). Vercel이 제공하는 프로젝트 주소도 허용

서버는 Argon2id 비밀번호 해시, HttpOnly·Secure·SameSite=Strict 쿠키, 실패 횟수 제한, 서버 측 문서·수신자 권한 검사를 유지합니다.

## 배포

```powershell
python web/build.py
npx.cmd vercel link --project botontouch-test
npx.cmd vercel integration add neon --name botontouch-test-db --billing-plan free_v3 --meta region=sin1 --meta auth=false --environment production --no-env-pull
# BATON_DEMO_PASSWORD는 CLI의 비밀 입력으로 추가합니다. Git에 저장하지 마세요.
npx.cmd vercel env add BATON_DEMO_PASSWORD production
npx.cmd vercel --prod
```

## 로컬 검증

```powershell
python -m pip install -r requirements.txt
python tests/test_cloud.py
```

자동 테스트는 가상 트랜잭션 저장소를 사용하며 외부 AI/조직도/실제 데이터베이스에 접속하지 않습니다.
실제 클라우드의 저장·재시작·동시성 검증은 배포 후 별도로 확인해야 합니다.
