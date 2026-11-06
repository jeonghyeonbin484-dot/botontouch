# 전체 기능 Vercel 배포 구성

전체 Python 업무 기능, 조직도 조회, 직원 계정, AI 초안·누락 점검·질의응답, 요청·수락·완료, 채팅, HWPX 생성기를 포함합니다. 기능을 공개용 모의 구현으로 교체하지 않습니다.

## 저장소와 초기화
- 로컬 실제 DB 및 실제 직원정보는 배포 파일에 포함하지 않습니다.
- Vercel은 기존 DATABASE_URL의 공유 DB를 재사용합니다. DB 연결 실패 시 임시 DB로 대체하지 않습니다.
- 현재 호환 어댑터는 SQLite 스냅샷을 PostgreSQL에 원자적으로 저장합니다. 파일 원본과 채팅 첨부도 DB에 저장되어 재배포 후 유지됩니다.
- 요청 중 DB 잠금을 사용하므로 많은 동시 사용자용 운영 구조로 검증된 것은 아닙니다. 별도 객체 저장소·정규 PostgreSQL 테이블 전환이 필요합니다.
- 테스트 데이터는 건별 출처·건수 확인, DB/파일 백업, 최종 승인 전까지 삭제하지 않습니다. 계정·조직정보·감사 로그를 무조건 초기화하지 않습니다.

## 조직도 연결
두 경로를 모두 구현합니다.
1. 승인된 서버에서 직접 연결: BATON_ORG_TRANSPORT=direct, BATON_ORG_DIRECT_ENABLED=true, BATON_ORG_API_APPROVED=true, BATON_ORG_BASE_URL=승인된 서버 원점. 직원 식별 필드 BATON_ORG_EMPLOYEE_ID_FIELD는 실제 응답 확인 후 USER_ID 또는 USER_SID를 지정합니다. SAEOLL_ID와 혼용하지 않습니다.
2. 내부 서버에서 외부로 동기화: tools/sync_internal_organization.py 실행. 내부 API 주소·인증정보는 내부 서버의 organization.local.json에만 보관합니다. 해당 API를 인터넷으로 개방하지 않습니다.
   - 양쪽 서버: BATON_ORG_SYNC_SECRET에 동일한 32자 이상 무작위 전용 비밀값. 코드·Git·로그에 저장하지 않습니다.
   - Vercel: BATON_ORG_SYNC_ALLOWED=true
   - 내부 서버: BATON_SYNC_TARGET=https://botontouch-test.vercel.app, BATON_ORG_EXPORT_APPROVED=true
   - API에 재직 상태가 없으면 현재 직원 목록의 의미를 확인한 뒤 내부 서버에 BATON_ORG_CURRENT_LIST_CONFIRMED=true를 설정해야 합니다. 미확인 상태에서는 직원 전송하지 않습니다.
   - 실행: python tools/sync_internal_organization.py
   - 5분 이내 서명·일회용 nonce·중복 ID 충돌 검증. 수신자는 직원 식별값으로 유지합니다. 인사이동은 별도 이력, 미조회 직원을 임의 삭제하지 않습니다.
   - 정기 실행은 승인된 내부 서버의 Windows 작업 스케줄러 또는 systemd timer에서 설정합니다. Vercel 백그라운드 스레드를 정기 동기화 수단으로 사용하지 않습니다.

## 최초 계정 활성화
- 조직도에 SAEOLL_ID가 있는 신규 직원은 소문자 ID로 비활성 계정을 생성합니다. 알려지지 않은 무작위 비밀번호의 해시만 저장합니다.
- 공통 1234!만으로 실제 직원 계정에 로그인할 수 없습니다.
- 관리자가 승인된 별도 경로로 본인확인 후 직원 계정 관리 화면에서 활성화 코드를 발급합니다. 확인 기록을 남기고 24시간·1회용 코드를 안전하게 전달합니다.
- 직원은 로그인 화면의 직원 계정 활성화에서 새올 ID·코드·새 비밀번호를 입력합니다. 비밀번호 설정 전 내부 기능 이용 불가, 코드 재사용 불가.
- 기존 직원 비밀번호는 조직도 재조회로 초기화하지 않습니다. 비밀번호 초기화는 별도 관리자 승인 절차입니다.
- 새 서버에 관리자 계정이 없으면 BATON_BOOTSTRAP_TOKEN을 32자 이상으로 설정한 뒤 최초 관리자만 등록합니다. 자동 로그인은 없습니다.

## AI
- GEMINI_API_KEY는 서버 환경변수에만 보관, GEMINI_MODEL=gemini-3.1-flash-lite. 공통 엔진은 60초 전체 제한 및 일시적 503 제한 재시도를 유지합니다.
- AI_MODE=live를 지원하며 실패를 mock으로 대체하지 않습니다. mock은 테스트를 위해 명시한 경우에만 사용합니다.
- 기존 검증된 가상자료 제한은 BATON_AI_DATA_SCOPE=verified-fictional-only로 유지 가능합니다. 기존 BATON_STAFF_* 서버 승인 설정을 사용합니다.
- 실제 승인 업무자료를 처리하려면 BATON_AI_DATA_SCOPE=approved-materials와 AI_EXTERNAL_TRANSMISSION_ALLOWED=true, AI_APPROVED_WRITING_ALLOWED=true, BATON_AI_APPROVED_MATERIALS=true, 실제 AI_APPROVAL_REFERENCE가 모두 필요합니다. 직원정보 외부 저장 승인을 AI 자료 전송 승인으로 간주하지 않습니다.
- AI_DAILY_REQUEST_LIMIT 기본 10회. 입력·응답 원문·키를 감사 로그에 기록하지 않습니다.

## 플랫폼 제한
- 현 Vercel 함수 진입 경로는 요청 본문을 4MB 이하로 제한합니다. 파일 형식 처리 기능은 유지되지만 대용량 업로드에는 별도 객체 저장소·스트리밍 업로드 연결이 필요합니다.
- HWPX 템플릿과 글꼴 자산을 함수 번들에 포함합니다. 최종 HWPX 출처 표시는 제외하지만 저장된 출처 근거는 유지합니다.
- 채팅은 기존 SSE를 사용합니다. Vercel에서는 짧은 이벤트 응답 후 재연결하여 갱신하며, 발송 직후 메시지는 바로 조회합니다. 서버리스 SSE와 DB 영속 저장을 함께 회귀 검사합니다.

## 현재 필수 조치
공유 DB 제공업체 할당량이 초과된 상태에서는 로그인·동기화·조회·저장 검증이 불가능합니다. 같은 DB의 한도 해소가 먼저 필요합니다. 기존 DB를 임의로 새 DB로 바꾸거나 요금제를 변경하지 않습니다.
