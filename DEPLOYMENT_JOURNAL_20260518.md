# Azure 배포 작업 일지 (2026-05-18)

개인 Azure 계정으로 HR/IT 챗봇 PoC를 운영 직전 단계까지 진행.
App Service 배포 + Entra ID 인증 + Bot Service 등록 + JWT 인증 강화.

> **TL;DR**
> - 코드 변경 자체는 작음(`start_server.py` 1줄, `app.py` 6줄, `requirements.txt` 1줄).
> - 시간을 잡아먹은 건 **Azure 측 설정과 묵시적 디폴트 동작 6개**(쿼터, 압축, 로그 buffering, 포트 라우팅, PyJWT 의존성, audience 검증).
> - 정공법 진단 패턴은 항상 동일: **SSH로 프로세스·포트 확인 → 로그 스트림 → 환경 변수 → 코드.**

## 목차

> 🆕 **회사 PC 가실 분은 [Clean Path](#-회사-pc-클린-셋업-clean-path) 섹션부터 보세요.**
> 시행착오 없이 처음부터 따라가는 직선 경로입니다.

1. [오늘의 목표와 결과](#오늘의-목표와-결과)
2. [작업 타임라인](#작업-타임라인)
3. [완료한 작업](#완료한-작업)
4. [오늘 적용한 코드 변경](#오늘-적용한-코드-변경)
5. [주요 시행착오](#주요-시행착오)
6. [학습한 내용·교훈](#학습한-내용교훈)
7. [최종 아키텍처](#최종-아키텍처)
8. [생성한 리소스 정리](#생성한-리소스-정리)
9. [디버깅 플레이북](#디버깅-플레이북)
10. [🆕 회사 PC 클린 셋업 (Clean Path)](#-회사-pc-클린-셋업-clean-path)
11. [회사 PC 재작업 시 주의점](#회사-pc-재작업-시-주의점)
12. [다음 단계](#다음-단계)

---

## 오늘의 목표와 결과

| 단계 | 목표 | 결과 | 비고 |
|---|---|---|---|
| 1 | LangChain `create_agent` 도입 | ❌ 보류 | Co-agent 아키텍처상 불필요 — Copilot이 위에서 라우팅하므로 내부 도구 라우팅 중복 |
| 2 | Entra ID 앱 등록 | ✅ 완료 | Client ID / Secret / Tenant ID 모두 `.env`와 App Service 환경 변수에 저장 |
| 3 | App Service 배포 | ✅ 완료 | 시행착오 5건. 최종적으로 `GET /api/messages → 200 OK` 응답 확인 |
| 4 | Azure Bot Service + 웹 채팅 테스트 | ✅ 완료 | 일본어 답변 + 출처 부착 정상 확인 |
| 5 | JWT 인증을 Entra ID 자격증명으로 강화 | ✅ 완료 | `anonymous_allowed=False` + CLIENT_ID/SECRET/TENANT_ID 전달 |
| 6 | outbound 인증용 MsalConnectionManager 주입 | ✅ 완료 | 별도 패키지 + SERVICE_CONNECTION 등록 |

**총평**: 코드 자체는 거의 그대로지만, "왜 Azure에서만 안 도는지"를 한 단계씩 해체하는 데 하루가 거의 다 쓰임. 회사 PC에서 재현할 때는 이 일지 따라가면 1-2시간 안에 끝낼 수 있을 것.

---

## 작업 타임라인

대략적인 진행 흐름 (시각은 로그 기준 추정):

```
오전
├─ Task 1 (LangChain create_agent) 검토 → 보류 결정
│   ↳ "Copilot이 위에서 라우팅하니까 내부 라우팅 중복" 판단
│
├─ Entra ID 앱 등록 (hr-it-agent-bot)
│   ├─ Single tenant 선택
│   ├─ Client ID 확보
│   └─ Client Secret 발급 (값 vs 비밀 ID 구분: "값"이 실제 시크릿)
│
└─ App Service 생성 시도 → 쿼터 에러로 막힘
    ├─ Japan East: VM 쿼터 0
    ├─ East US: VM 쿼터 0
    ├─ Free Trial 한계 확인
    └─ Pay-as-you-go 업그레이드 ($200 크레딧 유지)

오후 (정공법 진입)
├─ South Central US, B1으로 App Service 생성 ✅
├─ GitHub Actions 연결, 첫 배포
│   └─ git push rejected → git pull --rebase로 해결
│
├─ 1차 실패: "build_index.py not found"
│   └─ WEBSITE_RUN_FROM_PACKAGE=0 추가 → 해결
│
├─ 2차 실패: 컨테이너 무한 재시작 (로그 없음)
│   ├─ SSH로 확인 → 프로세스/포트 멀쩡
│   ├─ Azure가 헬스 체크 실패로 죽이고 있음
│   └─ PYTHONUNBUFFERED=1 + WEBSITES_PORT=8000 → 해결
│
├─ GET /api/messages → 200 OK ✅
│
├─ Bot Service 생성 (hr-it-agent-bot-jp, F0)
│   └─ Messaging endpoint 연결
│
├─ 3차 실패: Web Chat 연결 timeout
│   └─ 로그: MissingCryptographyError (PyJWT 서명 검증 라이브러리 누락)
│       └─ cryptography>=42.0.0 추가 → 해결
│
├─ 4차 실패: "Invalid audience: <CLIENT_ID>"
│   └─ 원인: anonymous_allowed=True여도 토큰이 오면 검증은 발생
│       └─ AgentAuthConfiguration에 client_id/secret/tenant_id 전달 → 해결
│
└─ 5차 실패: "'NoneType' object has no attribute 'get_token_provider'"
    └─ 원인: CloudAdapter()의 connection_manager가 None
        ├─ 별도 패키지 microsoft-agents-authentication-msal 설치
        ├─ MsalConnectionManager 생성 ("SERVICE_CONNECTION" 키 필수)
        └─ CloudAdapter + RestChannelServiceClientFactory에 주입 → 해결

저녁
└─ DEPLOYMENT_JOURNAL_20260518.md 정리 (본 문서)
```

---

## 완료한 작업

### Entra ID 앱 등록

```
앱 이름:       hr-it-agent-bot
Client ID:    5527f98c-7b82-441d-9454-3e5dce13ab30
Tenant ID:    122fd281-c76e-46b6-b215-fb70af7058ef
Client Secret: 발급 + .env 저장 (6개월 만료)
계정 유형:     단일 테넌트 (Single Tenant)
```

**중간에 헷갈렸던 것**:
시크릿 발급 화면에서 "비밀 ID"와 "값" 두 가지가 보이는데, 실제로 쓰이는 건 **"값"** 컬럼. "비밀 ID"는 Azure 내부에서 시크릿을 식별하는 GUID일 뿐 인증에는 안 쓰임.
**값은 발급 직후 한 번만 표시되므로 즉시 `.env`에 옮겨 적어야 함.**

### App Service 배포

```
이름:        hr-it-agent-poc0518
리소스 그룹: rg-hr-agent
지역:        South Central US (Japan East 쿼터 부족으로 변경)
SKU:        기본 B1 ($12.41/월, ~$13)
URL:        https://hr-it-agent-poc0518-b4echwezajbpehfe.southcentralus-01.azurewebsites.net
런타임:     Python 3.11
배포 방식:  GitHub Actions (jinpark0219/ms-365-sdk-agent-copilot)
시작 명령:  python build_index.py && python app.py
```

### 환경 변수 (App Service)

총 12개 등록 (역할별 정리):

```
[Foundry / Azure OpenAI 모델 호출]
AZURE_OPENAI_ENDPOINT            = https://azure-agent-for-copilot.services.ai.azure.com
AZURE_OPENAI_API_KEY             = <Foundry key>
AZURE_OPENAI_API_VERSION         = 2024-10-21
AZURE_OPENAI_CHAT_DEPLOYMENT     = gpt-4o-mini
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = text-embedding-3-small

[Entra ID 인증]
CLIENT_ID      = 5527f98c-7b82-441d-9454-3e5dce13ab30
CLIENT_SECRET  = <비공개>
TENANT_ID      = 122fd281-c76e-46b6-b215-fb70af7058ef

[Azure App Service 동작 제어]
SCM_DO_BUILD_DURING_DEPLOYMENT = true   # pip install 자동 수행
WEBSITE_RUN_FROM_PACKAGE       = 0      # zstd 압축 해제, wwwroot에 직접 배치
WEBSITES_PORT                  = 8000   # 게이트웨이가 라우팅할 포트
PYTHONUNBUFFERED               = 1      # stdout 버퍼링 비활성화 (로그 즉시 출력)
```

### Azure Bot Service

```
이름:                hr-it-agent-bot-jp
Pricing tier:        F0 (무료)
Data residency:      Global
Microsoft App ID:    5527f98c-7b82-441d-9454-3e5dce13ab30 (Entra ID 재사용)
Messaging endpoint:  https://hr-it-agent-poc0518-b4echwezajbpehfe.southcentralus-01.azurewebsites.net/api/messages
채널:                Web Chat (활성)
```

---

## 오늘 적용한 코드 변경

배포 동안 코드 자체는 거의 안 건드렸지만, 다음 4개 지점이 핵심:

### 1. `start_server.py` — 0.0.0.0 바인딩 + 포트 환경 변수

**이전 (로컬 가정)**:
```python
run_app(APP, host="localhost", port=3978)
```

**이후 (클라우드 가정)**:
```python
run_app(APP, host="0.0.0.0", port=int(environ.get("PORT", 8000)))
```

이유: 컨테이너 내부에서 `localhost`로 바인딩하면 외부 게이트웨이에서 접근 불가.
`0.0.0.0`은 모든 네트워크 인터페이스에 바인딩. Azure App Service는 `PORT` 환경 변수로 포트를 알리는 게 표준 패턴이지만, 자동 감지가 잘 안 되는 경우가 있어서 `WEBSITES_PORT=8000`도 함께 지정.

### 2. `requirements.txt` — cryptography 명시

```diff
  langchain-text-splitters==1.1.2
+ cryptography>=42.0.0
```

이유: PyJWT는 기본 설치 시 서명 검증 라이브러리(`cryptography` 또는 `pycryptodome`) 미포함.
Bot Service가 JWT를 RS256으로 서명해서 보내는데, 이걸 검증하려면 `cryptography` 필요.
`pyjwt[crypto]` 형태로 extras를 쓰는 방법도 있지만, 명시적으로 추가하는 게 더 분명함.

### 3. `app.py` — JWT 검증 활성화

**이전 (PoC 초기, 인증 우회)**:
```python
if __name__ == "__main__":
    rag_index.load()
    try:
        start_server(AGENT_APP, AgentAuthConfiguration(anonymous_allowed=True))
    except Exception as error:
        raise error
```

**이후 (운영 직전 단계)**:
```python
if __name__ == "__main__":
    rag_index.load()
    try:
        # Entra ID で発行された JWT を検証する
        # - CLIENT_ID:     Bot Service が送ってくる token の aud(audience)
        # - TENANT_ID:     token 発行元テナントの限定
        # - CLIENT_SECRET: Agent 側が outbound 通信時に使用
        start_server(
            AGENT_APP,
            AgentAuthConfiguration(
                anonymous_allowed=False,
                client_id=os.getenv("CLIENT_ID"),
                client_secret=os.getenv("CLIENT_SECRET"),
                tenant_id=os.getenv("TENANT_ID"),
            ),
        )
    except Exception as error:
        raise error
```

이유: 시행착오 6번 참고. `anonymous_allowed=True`는 "토큰 없으면 통과"일 뿐, 토큰이 오면 검증은 항상 일어남. 그런데 검증기는 "기대 audience"를 모르기 때문에 매칭 실패 → `Invalid audience`. `client_id`를 넘기는 순간 SDK 내부의 `_jwt_patch_is_valid_aud()`가 정상 매칭함.

### 4. (보너스) `.gitignore` 정상화

`.env`가 절대 커밋되지 않게 유지. 오늘 커밋 로그 점검 시 한 번도 노출된 적 없음을 확인.

---

## 주요 시행착오

총 7건. 각각 30분~1시간씩 소비.

### 시행착오 1 — Free Trial 쿼터 부족

**증상**:
```
Operation cannot be completed without additional quota.
Current Limit (Total VMs): 0
```

**원인**:
- Azure Free Trial 구독은 VM 쿼터 **0**으로 시작
- Japan East, East US 등 거의 모든 지역에서 동일
- F1 무료 티어조차 막힘 (VM 쿼터 적용 대상)

**해결**:
- Pay-as-you-go 업그레이드 (카드는 이미 등록돼있음)
- $200 크레딧 그대로 유지 (24일 평가 기간 잔존)
- 업그레이드 직후 South Central US에서 B1 통과

**교훈**: 새 Azure 구독은 시작 단계에서 거의 모든 지역에서 쿼터 0. **Pay-as-you-go 업그레이드가 정공법.** Free Trial은 24일 평가용일 뿐 실제 배포는 거의 불가.

---

### 시행착오 2 — `output.tar.zst` 압축 해제 안 됨

**증상**:
```
python: can't open file '/home/site/wwwroot/build_index.py': [Errno 2] No such file or directory
WARNING: Could not find virtual environment directory /home/site/wwwroot/antenv.
```

**원인**:
- 2025~2026 Azure App Service의 새 배포 방식: 파일을 **`output.tar.zst`로 압축** (zstd)
- 기본적으로 `/tmp/<deploy-id>/`에 풀고 거기서 실행
- 그런데 시작 명령은 `/home/site/wwwroot/`에서 실행한다고 가정
- 경로 불일치로 "파일 없음"

**진단 단서**:
- Log stream에서 `Linux Container starting...` 다음에 `wwwroot/`에 build_index.py가 없다고 함
- SSH로 `/home/site/wwwroot/` 들어가보면 빈 디렉토리

**해결**:
환경 변수에 `WEBSITE_RUN_FROM_PACKAGE=0` 추가.
이러면 zstd 압축 풀어서 wwwroot에 직접 배치.

**교훈**: 2025~2026 Azure는 새 zstd 압축 디폴트 채택. **Python 시작 명령이 wwwroot 기반이면 명시적으로 OFF 처리 필요.** 이건 마이크로소프트 문서에도 잘 안 나옴.

---

### 시행착오 3 — 컨테이너 무한 재시작 (Silent crash)

**증상**:
```
07:13:06 - build_index.py 완료
... (5분 침묵) ...
07:18:29 - 컨테이너 재시작
```

**원인 1 — stdout buffering**:
- Python은 기본적으로 stdout/stderr buffer가 4KB
- `print()` 출력이 즉시 flush 안 됨
- Azure가 로그 안 보이니까 "죽은 줄" 알고 헬스 체크 실패 처리

**원인 2 — 포트 자동 감지 실패**:
- Azure App Service는 기본적으로 0.0.0.0:8000을 기대하지만 일부 환경에선 다른 포트 사용
- 게이트웨이가 어디로 요청 보낼지 모름 → 응답 없음 → 컨테이너 강제 재시작

**진단 — SSH로 직접 확인**:
```bash
# Azure Portal → SSH 콘솔
ps aux | grep python    # PID 보임, 프로세스 살아있음
netstat -tlnp | grep 8000  # 8000번 LISTEN 상태
curl localhost:8000/api/messages  # 응답 옴

# 즉, 서버는 살아있는데 Azure가 못 알아챔
```

**해결**:
- `PYTHONUNBUFFERED=1` 추가 → 즉시 로그 출력
- `WEBSITES_PORT=8000` 추가 → 게이트웨이가 올바른 포트로 라우팅
- `start_server.py` 수정 → `host="0.0.0.0"` 명시 (`localhost`면 컨테이너 내부에서만 바인딩)

**교훈**:
- **로그가 안 보인다고 죽은 게 아님.** SSH로 프로세스·포트 먼저 확인하는 게 가장 빠른 진단.
- Python 컨테이너는 `PYTHONUNBUFFERED=1`이 사실상 필수.
- 클라우드는 항상 `0.0.0.0` 바인딩.

---

### 시행착오 4 — JWT 서명 검증 실패 (cryptography 누락)

**증상** (Log stream):
```
File ".../jwt/api_jwk.py", line 69, in __init__
    raise MissingCryptographyError(
jwt.exceptions.MissingCryptographyError: ...
```

**원인**:
- Bot Service가 토큰을 **RS256으로 서명**해서 보냄
- PyJWT가 JWKS(JSON Web Key Set)로 서명 검증을 시도
- 하지만 RSA 검증에는 `cryptography` 패키지가 필요
- 우리 `requirements.txt`에 cryptography 명시 안 함 → 컨테이너에 미설치 상태

**해결**:
```diff
  langchain-text-splitters==1.1.2
+ cryptography>=42.0.0
```

**교훈**: PyJWT는 기본 설치 시 서명 검증 라이브러리 미포함.
JWT 서명 검증하려면 `pyjwt[crypto]` extras 또는 `cryptography` 명시 필수.

---

### 시행착오 5 — `host="localhost"` 가정

**증상**: Azure 배포 시 외부 접근 불가, 컨테이너 재시작 반복.

**원인**: 원본 `start_server.py`는 `host="localhost"` → 컨테이너 내부 루프백에만 바인딩.
외부 게이트웨이에서 접근 불가.

**해결**: `host="0.0.0.0"` + `port=int(environ.get("PORT", 8000))`

**교훈**: 로컬 개발 코드를 그대로 클라우드 배포할 때 가장 흔한 함정.
"잘 돌더라"는 로컬에서만 통하는 명제. 클라우드 가정 시 항상 `0.0.0.0`.

---

### 시행착오 6 — `anonymous_allowed=True`의 함정

**증상**:
```
Invalid audience: 5527f98c-7b82-441d-9454-3e5dce13ab30
Stack (most recent call last):
  File "/tmp/.../app.py", line 112, in <module>
    start_server(AGENT_APP, AgentAuthConfiguration(anonymous_allowed=True))
  ...
  File ".../microsoft_agents/hosting/core/authorization/jwt_token_validator.py",
    line 91, in validate_token
    logger.error(f"Invalid audience: {decoded_token['aud']}", stack_info=True)
```

audience로 출력된 값(`5527f98c-...`)이 **우리 CLIENT_ID**라는 게 결정적 단서.

**원인**:
이름과 달리 `anonymous_allowed=True`는 "JWT 검증을 끈다"는 의미가 **아님**.
정확한 의미는 다음과 같음:

```
anonymous_allowed=True  → "토큰이 없으면 통과시킴"  (검증은 토큰 있을 때만)
anonymous_allowed=False → "토큰이 없으면 거부"      (그리고 검증 수행)
```

즉 **둘 다 토큰이 오면 검증을 시도함.**
그런데 Bot Service는 항상 JWT를 보냄(이게 인증 모델).
검증 시 SDK는 `_jwt_patch_is_valid_aud()`로 audience가 등록된 CLIENT_ID와 일치하는지 확인하는데:

```python
# microsoft_agents/hosting/core/authorization/agent_auth_configuration.py 발췌
def _jwt_patch_is_valid_aud(self, aud: str) -> bool:
    for conn in self._connections.values():
        if not conn.CLIENT_ID:    # ← 여기서 CLIENT_ID 없으면 무조건 skip
            continue
        if aud.lower() == conn.CLIENT_ID.lower():
            return True
    return False   # ← 매칭되는 게 없으면 False
```

`anonymous_allowed=True`만 넣고 `client_id`를 안 넘기면 → `CLIENT_ID = None` → 위 루프에서 무조건 skip → 항상 `False` → "Invalid audience".

**해결**:
```python
start_server(
    AGENT_APP,
    AgentAuthConfiguration(
        anonymous_allowed=False,
        client_id=os.getenv("CLIENT_ID"),
        client_secret=os.getenv("CLIENT_SECRET"),
        tenant_id=os.getenv("TENANT_ID"),
    ),
)
```

`client_id`를 명시하는 순간 audience 매칭 성공.
부수적으로 `anonymous_allowed=False`로 바뀌면서 "토큰 없는 요청"도 거부 → 보안 강화.

**교훈**:
- `anonymous_allowed`는 이름이 misleading. **"토큰 없으면 통과시킬지" 옵션이지 "검증 끄기"가 아님.**
- PoC 단계라도 Bot Service와 연결하려면 `client_id` 전달은 사실상 필수.
- SDK 내부 소스를 한 번 열어서 검증 로직을 보는 게 디버깅에 결정적.

---

### 시행착오 7 — `CloudAdapter()` 빈 인자 + `connection_manager=None` 🆕

**증상**:
```
File ".../microsoft_agents/hosting/aiohttp/jwt_authorization_middleware.py", line 34
    return await handler(request)          ← JWT 검증은 통과!
File ".../microsoft_agents/hosting/core/channel_service_adapter.py", line 421
    await self._channel_service_client_factory.create_user_token_client(
File ".../microsoft_agents/hosting/core/rest_channel_service_client_factory.py", line 177
    token_provider = self._connection_manager.get_token_provider(
AttributeError: 'NoneType' object has no attribute 'get_token_provider'
```

핵심 단서: JWT 미들웨어는 통과(`line 34`에서 `return await handler(request)`). 그 다음 단계인 **outbound 통신용 token 발급**에서 죽음.

**원인**:
원래 코드:
```python
AGENT_APP = AgentApplication[TurnState](
    storage=MemoryStorage(), adapter=CloudAdapter()   # ← 빈 생성자
)
```

`CloudAdapter()`의 시그니처를 보면:
```python
def __init__(
    self,
    *,
    connection_manager: Connections = None,        # ← 기본값 None
    channel_service_client_factory: ChannelServiceClientFactoryBase = None,
):
```

`connection_manager=None`이라 SDK가 Bot Service로 응답을 보내려고 token을 발급하는 순간 None 참조로 죽음.

**더 큰 함정**: `microsoft-agents-hosting-core` 패키지에는 **`Connections` Protocol의 구현체가 들어있지 않음.** `AnonymousTokenProvider` 하나뿐. 실제 구현체는 **별도 패키지** `microsoft-agents-authentication-msal`에 들어있는 `MsalConnectionManager`. 이걸 따로 설치해야 함.

또 하나: `MsalConnectionManager`는 connection 이름이 **`"SERVICE_CONNECTION"`** 으로 하드코딩됨:
```python
if not self._connections.get("SERVICE_CONNECTION", None):
    raise ValueError("No service connection configuration provided.")
```

**해결**:

`requirements.txt`:
```diff
  microsoft-agents-activity==0.9.1
+ microsoft-agents-authentication-msal==0.9.1
```

`app.py`:
```python
from microsoft_agents.hosting.core import (
    ...,
    RestChannelServiceClientFactory,
)
from microsoft_agents.authentication.msal import MsalConnectionManager

SERVICE_AUTH_CONFIG = AgentAuthConfiguration(
    anonymous_allowed=False,
    client_id=os.getenv("CLIENT_ID"),
    client_secret=os.getenv("CLIENT_SECRET"),
    tenant_id=os.getenv("TENANT_ID"),
)

CONNECTION_MANAGER = MsalConnectionManager(
    connections_configurations={"SERVICE_CONNECTION": SERVICE_AUTH_CONFIG}
)

CHANNEL_SERVICE_FACTORY = RestChannelServiceClientFactory(
    connection_manager=CONNECTION_MANAGER
)

AGENT_APP = AgentApplication[TurnState](
    storage=MemoryStorage(),
    adapter=CloudAdapter(
        connection_manager=CONNECTION_MANAGER,
        channel_service_client_factory=CHANNEL_SERVICE_FACTORY,
    ),
)
```

**교훈**:
- 인증은 **inbound JWT 검증**과 **outbound token 발급** 두 가지가 따로 있음. 한쪽만 설정하면 안 됨.
- SDK는 모놀리식이 아니라 **인증 backend(MSAL)는 별도 패키지**로 분리. PyPI에서 `microsoft-agents-authentication-msal` 찾아서 설치 필요. 공식 문서에 잘 안 드러나는 부분.
- 매직 키 `"SERVICE_CONNECTION"`처럼 SDK가 특정 이름을 기대하는 경우 있음 — 소스 안 보면 시간 날림.
- **JWT 미들웨어 통과 = 인증 성공** 아님. 다음 단계인 outbound channel 통신까지 봐야 진짜 통과.

---

## 학습한 내용·교훈

### Azure App Service 패턴 정리

| 항목 | 알게 된 점 | 대응 |
|---|---|---|
| 신규 구독은 모든 지역 쿼터 0 | Free Trial은 사실상 사용 불가 | Pay-as-you-go 업그레이드 |
| 신규 배포는 zstd 압축 형식 | `output.tar.zst`로 들어옴 | `WEBSITE_RUN_FROM_PACKAGE=0` |
| 헬스 체크 타임아웃 5분 | 그 안에 응답 안 하면 강제 재시작 | 로그 안 보이면 SSH로 확인 |
| stdout buffering 기본 ON | Python 로그가 안 보임 | `PYTHONUNBUFFERED=1` |
| 포트 자동 감지 부정확 | 게이트웨이 라우팅 실패 | `WEBSITES_PORT` 명시 |
| host="localhost"는 컨테이너 내부만 | 외부 접근 불가 | `0.0.0.0` 바인딩 |

### Entra ID + Bot Service 통합 패턴

| 항목 | 알게 된 점 |
|---|---|
| Bot Service는 항상 JWT 보냄 | `anonymous_allowed`와 무관하게 토큰 옴 |
| PyJWT는 기본 설치 시 서명 검증 불가 | `cryptography` 패키지 필수 |
| Client Secret은 발급 후 1회만 표시 | `.env`에 즉시 저장. 잃으면 재발급 |
| 시크릿 화면의 "비밀 ID" vs "값" | 실제 인증에 쓰이는 건 **"값"** |
| Tenant ID는 Entra ID 개요에 항상 보임 | 따로 찾을 필요 없음 |
| App ID == Client ID (Bot Service 용어) | Bot Service에서 "App ID"라고 부르지만 같은 값 |
| `anonymous_allowed`는 이름이 헷갈림 | 검증 끄는 옵션 아님, 토큰 없을 때 정책일 뿐 |

### 디버깅 패턴 (정공법)

```
1. URL 직접 호출 (curl 또는 브라우저)
   → 응답 안 옴 / 5xx?

2. SSH로 직접 확인
   $ ps aux | grep python      → 프로세스 살아있나?
   $ netstat -tlnp | grep 8000 → 포트 LISTEN하나?
   $ curl localhost:8000/api/messages → 내부에서는 응답?
   
3. Log stream 패턴 매칭
   → "Invalid audience" → 인증 설정
   → "Cryptography" → 의존성
   → 침묵 → buffering / health check

4. 환경 변수 점검
   → 누락된 거 있는지
   → 값 오타 (TENANT_ID 등 36자 GUID 주의)

5. 코드 변경 (마지막 수단)
```

---

## 최종 아키텍처

```
[사용자 — 일본어 질문]
    ↓
[Azure Bot Service - hr-it-agent-bot-jp]
    ├─ JWT 토큰 발급 (RS256, aud = CLIENT_ID, iss = Entra ID)
    └─ POST /api/messages 전송 (Bearer token)
        ↓ HTTPS
[Azure App Service - hr-it-agent-poc0518]
    │
    ├─ aiohttp 서버 (0.0.0.0:8000)
    │
    ├─ JWT 미들웨어 (cryptography로 RS256 검증)
    │   ├─ JWKS 다운로드 (login.microsoftonline.com)
    │   ├─ 서명 검증
    │   ├─ issuer 검증 (sts.windows.net/<TENANT_ID>)
    │   ├─ audience 검증 (== CLIENT_ID)
    │   └─ 만료 검증
    │
    ├─ M365 Agents SDK 라우팅
    │   ├─ membersAdded → _help (환영 메시지)
    │   ├─ "/help"      → _help
    │   └─ message      → on_message  ─┐
    │                                  │
    ├─ RAG 검색 (FAISS + LangChain)    │
    │   ├─ 사용자 질의 임베딩            │
    │   ├─ 인메모리 FAISS index 검색     │
    │   ├─ TOP_K=5 청크 반환             │
    │   └─ format_context() (출처 포함)  │
    │                                  ↓
    └─ Azure OpenAI (Foundry) 호출
        ├─ gpt-4o-mini (chat completion)
        └─ text-embedding-3-small (질의 임베딩)
            ↓
        [답변 — 일본어, 출처 부착]
```

### 기술 스택 (현재 동작 중)

| 레이어 | 사용 기술 |
|---|---|
| 사용자 채널 | Azure Bot Service Web Chat |
| 게이트웨이 | Azure Bot Service |
| 호스팅 | Azure App Service (Linux, Python 3.11, B1) |
| 인증 | Entra ID OAuth 2.0 (Client ID + Secret + Tenant) |
| 토큰 검증 | PyJWT + cryptography (RS256, JWKS) |
| 웹 서버 | aiohttp |
| 에이전트 프레임워크 | Microsoft 365 Agents SDK (`microsoft-agents-hosting-aiohttp`) |
| LLM | Azure OpenAI / Foundry (`gpt-4o-mini`) |
| 임베딩 | Azure OpenAI / Foundry (`text-embedding-3-small`) |
| 벡터 검색 | FAISS (LangChain wrapper) |
| 청킹 | LangChain `MarkdownHeaderTextSplitter` |
| 배포 | GitHub Actions (`jinpark0219/ms-365-sdk-agent-copilot`) |

---

## 생성한 리소스 정리

### Azure 리소스 트리

```
구독: Azure subscription 1 (Pay-as-you-go, $200 크레딧 남음)
└─ Resource Group: rg-hr-agent (East US)
   ├─ App Service Plan:  ASP-rghragent-a039  (Linux, B1, ~$13/월)
   ├─ App Service:       hr-it-agent-poc0518 (Python 3.11)
   └─ Azure Bot Service: hr-it-agent-bot-jp  (F0, $0)

테넌트 레벨 (RG 외부)
└─ Entra ID App Registration: hr-it-agent-bot
   ├─ Application (client) ID: 5527f98c-7b82-441d-9454-3e5dce13ab30
   ├─ Tenant ID:               122fd281-c76e-46b6-b215-fb70af7058ef
   └─ Client Secret (6개월 만기)

별도 RG (Azure AI Foundry)
├─ Chat 배포:       gpt-4o-mini
└─ Embedding 배포: text-embedding-3-small
```

### 비용 예측 (월)

```
App Service Plan B1:   ~$13.0/월   (가장 비싼 항목)
Bot Service F0:        $0.0       (무료)
Foundry 모델 사용량:    ~$1.0/월    (PoC 트래픽 가정)
저장소·네트워크:        ~$0.5/월
────────────────────────────────
합계:                  ~$14.5/월

$200 크레딧으로 약 13개월 동작 가능 (현재 24일 평가 기간 잔존)
```

**비용 절감 옵션 (필요 시)**:
- B1 → F1 다운그레이드: $0/월 (단, 60분 idle 후 cold start 1-2초)
- App Service 사용 안 할 때 중지 → 시간당 과금 멈춤
- 회사 PC 이관 후 개인 리소스 삭제 → $0

---

## 디버깅 플레이북

오늘 학습한 진단 순서를 그대로 절차화. 회사 PC에서 같은 함정 만났을 때 바로 적용.

### "왜 안 됨?" 5분 체크리스트

```
1) Azure Portal → App Service → 개요
   - 상태가 "실행 중"인가?
   - "재시작" 버튼 시도해봤나?

2) Azure Portal → App Service → 환경 변수
   - 다음 12개 모두 있는가?
     □ AZURE_OPENAI_* (5개)
     □ CLIENT_ID / CLIENT_SECRET / TENANT_ID (3개)
     □ SCM_DO_BUILD_DURING_DEPLOYMENT
     □ WEBSITE_RUN_FROM_PACKAGE=0
     □ WEBSITES_PORT=8000
     □ PYTHONUNBUFFERED=1

3) Azure Portal → App Service → 로그 스트림
   - "Invalid audience" → 시행착오 6
   - "MissingCryptographyError" → 시행착오 4
   - "can't open file" → 시행착오 2
   - 침묵 → 시행착오 3

4) Azure Portal → App Service → SSH
   $ ps aux | grep python
   $ netstat -tlnp | grep 8000
   $ ls /home/site/wwwroot/

5) curl 직접
   $ curl https://<app-name>.azurewebsites.net/api/messages
   → 200 응답 와야 함 (빈 GET)
```

### Bot Service 측 체크

```
1) Bot Service → 설정 → Messaging endpoint
   - URL 끝에 /api/messages 붙어있나?
   - https인가?

2) Bot Service → 설정 → 구성
   - Microsoft App ID == Entra ID Client ID인가?

3) Bot Service → 채널 → Web Chat → 웹 채팅에서 테스트
   - 메시지 입력 시 App Service 로그에 요청 들어오나?
```

---

## 🆕 회사 PC 클린 셋업 (Clean Path)

오늘의 시행착오 7건을 **모두 선반영**한, 회사 PC에서 처음부터 따라갈 직선 경로입니다.
이 절차대로만 가면 시행착오 없이 약 3시간 안에 동일 환경 재현 가능.

### 전체 흐름

```
Phase 0  ローカル準備        (30분, 권한 신청과 병행)
Phase 1  権限申請            ⏳ 1-3일 대기 (외부 의존)
─────────── 권한 승인 대기 ───────────
Phase 2  Foundry モデル배포  (30분)
Phase 3  Entra ID 앱 등록    (15분)
Phase 4  로컬 검증            (30분, 선택)
Phase 5  App Service 생성    (30분)
Phase 6  환경 변수 등록       (15분)
Phase 7  배포 + 동작 검증     (15분)
Phase 8  Bot Service 생성    (15분)
Phase 9  E2E 검증            (10분)
Phase 10 실문서 교체          (별도 작업)
Phase 11 Teams/Copilot 통합  (별도 작업)
```

순수 작업 시간 약 **3시간**, 권한 대기 별도.

---

### Phase 0 — 로컬 준비 (권한 신청과 병행)

회사 PC에 다음 설치:

| 항목 | 명령 / 방법 |
|---|---|
| Python 3.11 | `winget install Python.Python.3.11` |
| Git | `winget install Git.Git` |
| GitHub CLI (선택) | `winget install GitHub.cli` |
| Azure CLI (선택) | `winget install Microsoft.AzureCLI` |
| VS Code | `winget install Microsoft.VisualStudioCode` |

그리고 회사 GitHub org `CollabCentralOrganization/m365-copilot-agent`에 본인 계정이 접근 가능한지 확인.

---

### Phase 1 — 권한 신청 (가장 먼저, IT에 이메일)

이게 가장 큰 외부 의존이므로 **무조건 첫날 신청**.

```
[회사 IT 헬프데스크 / M365 Admin 앞]

Azure / M365 권한 申請

理由: HR/IT 内部 Q&A エージェントの PoC 構築のため

必要な権限:
1. Azure サブスクリプション の Contributor 権限
2. Entra ID アプリ登録権限 (Application Developer 役割)
3. Azure AI Foundry の利用権限
4. (将来) Microsoft 365 Copilot ライセンス (Copilot Studio 連携時)
5. (将来) Teams アプリのサイドローディング許可

期間: PoC 期間中
```

> **TIP**: 1, 2, 3은 거의 동시에 필요. 4, 5는 Copilot 통합 단계에서. 한꺼번에 신청해두면 좋음.

---

### Phase 2 — Azure AI Foundry 모델 배포

권한 승인되면 진행.

1. [Azure AI Foundry](https://ai.azure.com/)에 회사 계정으로 로그인
2. 새 Project 만들기 (리전: **Japan East** 권장)
3. 좌측 메뉴 **Models + Endpoints** → **Deploy model** 클릭
4. 다음 2개 배포:

| 用途 | モデル | デプロイ名 (デフォルトでOK) |
|---|---|---|
| Chat | `gpt-4o-mini` | `gpt-4o-mini` |
| Embedding | `text-embedding-3-small` | `text-embedding-3-small` |

5. **다음 값을 메모**:
   - エンドポイント URL: `https://<resource>.services.ai.azure.com`
   - API Key (Key 1 でOK)
   - チャットデプロイ名
   - 埋め込みデプロイ名

---

### Phase 3 — Entra ID 앱 등록

1. [Entra ID 포털](https://entra.microsoft.com/) → **アプリの登録** → **新規登録**
2. 입력:
   - 名前: `hr-it-agent-bot` (또는 회사 명명규칙대로)
   - サポートされているアカウントの種類: **このディレクトリのみのシングルテナント**
   - リダイレクト URI: 비워둠
3. 생성 후 **概要** 화면에서:
   - **アプリケーション (クライアント) ID** 복사 → `CLIENT_ID`
   - **ディレクトリ (テナント) ID** 복사 → `TENANT_ID`
4. 좌측 **証明書とシークレット** → **新しいクライアントシークレット**:
   - 説明: `agent-secret`
   - 有効期限: 6ヶ月 (또는 회사 정책)
   - 작성 후 **"値" 컬럼을 즉시 복사** → `CLIENT_SECRET`

> ⚠️ **"値"는 한 번만 표시됨.** 한 번 페이지 이탈하면 다시 못 봄. 즉시 메모장에 저장. "비밀 ID"는 인증에 안 쓰임 (Azure 내부 식별자).

---

### Phase 4 — 로컬 검증 (선택, 권장)

Azure에 올리기 전에 로컬에서 한 번 동작 확인하면 마음이 편함.

```powershell
# 1. 클론
gh repo clone CollabCentralOrganization/m365-copilot-agent
cd m365-copilot-agent

# 2. Python 3.11 venv
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version    # Python 3.11.x 확인

# 3. 의존성
pip install -r requirements.txt

# 4. 환경변수
copy .env.example .env
notepad .env
```

`.env`에 입력:
```ini
AZURE_OPENAI_ENDPOINT=https://<회사-foundry>.services.ai.azure.com
AZURE_OPENAI_API_KEY=<Foundry Key>
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_CHAT_DEPLOYMENT=<채팅 배포명>
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=<임베딩 배포명>

CLIENT_ID=<Entra ID Client ID>
CLIENT_SECRET=<Entra ID Secret 値>
TENANT_ID=<Entra ID Tenant ID>

HR_CONTACT=HR: 内線XXXX     # 회사 실제 번호
IT_CONTACT=IT: 内線XXXX     # 회사 실제 번호

PORT=3978
```

```powershell
# 5. 인덱스 구축
python build_index.py

# 6. 서버 기동
python app.py

# 7. (별 터미널) Playground
npm install -g @microsoft/teams-app-test-tool
teamsapptester
```

브라우저에서 `年休は何日もらえますか?` 입력해서 답변 나오면 OK.

---

### Phase 5 — Azure App Service 생성

> ⚠️ Free Trial이면 VM 쿼터 0이라 실패함. **Pay-as-you-go 업그레이드 먼저** (회사 구독은 보통 PAYG).

1. [Azure Portal](https://portal.azure.com/) → **App Service** → **만들기**
2. 입력:
   - リソースグループ: 새로 또는 기존
   - 名前: `hr-it-agent-poc` (글로벌 unique)
   - パブリッシュ: **コード**
   - ランタイム: **Python 3.11**
   - OS: **Linux**
   - リージョン: Japan East (불가능하면 Japan West / Southeast Asia)
   - SKU: **Basic B1** ($13/月)
3. **検閲 + 작성**
4. 작성 완료 후 → **デプロイメント センター**:
   - 소스: **GitHub**
   - 조직: `CollabCentralOrganization`
   - リポ: `m365-copilot-agent`
   - 브랜치: `main`
   - 워크플로 형식: **添加** (자동 생성)
5. 저장 → GitHub Actions 워크플로 파일이 리포에 자동 추가됨

> 자동 추가된 워크플로 파일 때문에 다음 `git push`가 거부될 수 있음. 그땐 `git pull --rebase` 후 push.

---

### Phase 6 — App Service 환경변수 등록

App Service → **環境変数** → 다음 14개 모두 입력:

```ini
# Foundry
AZURE_OPENAI_ENDPOINT=https://<foundry>.services.ai.azure.com
AZURE_OPENAI_API_KEY=<Key>
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_CHAT_DEPLOYMENT=<배포명>
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=<배포명>

# Entra ID
CLIENT_ID=<...>
CLIENT_SECRET=<...>
TENANT_ID=<...>

# 案内 fallback (회사 실제 값)
HR_CONTACT=HR: 内線XXXX
IT_CONTACT=IT: 内線XXXX

# Azure App Service 動作制御 (必須)
SCM_DO_BUILD_DURING_DEPLOYMENT=true
WEBSITE_RUN_FROM_PACKAGE=0
WEBSITES_PORT=8000
PYTHONUNBUFFERED=1
```

마지막 4개가 **오늘 시행착오에서 학습한 핵심**. 이거 빠지면 컨테이너 무한 재시작 / 압축 안 풀림 / 로그 안 보임 발생.

그리고 시작 명령 설정:
```
App Service → 構成 → 一般設定 → スタートアップコマンド:
python build_index.py && python app.py
```

저장 후 **App Service 재시작**.

---

### Phase 7 — 첫 배포 + 동작 검증

이 단계에선 코드를 한 번 push해서 빌드 트리거.

```powershell
# 적당한 commit (예: README 갱신 등)
git commit --allow-empty -m "trigger initial deploy"
git push
```

GitHub Actions → 빌드 진행 확인 (보통 3-4분).
완료되면 App Service Log stream에서:

```
WS server started on http://0.0.0.0:8000
```

같은 메시지 보이면 정상 기동.

**HTTP 응답 확인** (PowerShell 또는 curl):
```powershell
curl https://<app-name>.azurewebsites.net/api/messages
```

기대 응답: **`HTTP 401 Unauthorized`** (토큰 없는 GET이라 거부되는 게 정상).
200/500/timeout이 오면 환경변수 확인 + Log stream 패턴 분석 (시행착오 1~7 참조).

---

### Phase 8 — Azure Bot Service 생성

1. Azure Portal → **Azure Bot** 검색 → **만들기**
2. 입력:
   - Bot ハンドル: `hr-it-agent-bot` (회사 명명규칙)
   - 가격 등급: **F0 (무료)**
   - Microsoft App ID: **既存のアプリ登録を使用** → Phase 3에서 만든 Entra ID 앱 선택
3. 작성 완료 후 → **構成**:
   - **Messaging endpoint**:
     ```
     https://<app-service-name>.azurewebsites.net/api/messages
     ```
   - 저장

4. **チャネル** → Web Chat은 기본 활성. 추후 Teams 추가는 별도 단계.

---

### Phase 9 — End-to-End 검증

1. Bot Service → **Test in Web Chat** 열기
2. 입력: `年休は何日もらえますか?`
3. 기대 응답:
   ```
   年休の付与基準は以下の通りです：
     • 入社1年目：15日
     • 2年目以降毎年1日追加（最大25日）

   出典: 「1.1 年次有給休暇」
   ```

샘플 문서가 그대로면 위 응답 나옴. **응답 시간 3-7초 이내**가 정상.

답변 오면 PoC 완료. 🎉

### 검증해야 할 동작 4가지

| 質問 | 確認できる事 |
|---|---|
| `年休は何日もらえますか?` | 기본 RAG 동작 |
| `リモートワーク時のセキュリティ要件を教えてください` | 멀티 문서 검색 |
| `今月の給与振込日はいつですか？` | 환각 방지 (회사 연락처 안내) |
| `/help` | 환영 메시지 |

---

### Phase 10 — 실제 사내 문서로 교체

PoC 동작 확인되면 가짜 데이터 → 진짜 데이터로 교체.

```powershell
# 1. 샘플 삭제
Remove-Item sample-docs/*.md

# 2. 진짜 사내 문서 배치
copy <회사문서경로>\*.md sample-docs\

# (선택) Word/PDF인 경우 사전 변환
# python -m markitdown input.docx > sample-docs/output.md  같은 도구 활용

# 3. 인덱스 재생성 + 검증 (로컬에서)
python build_index.py
python app.py
# Playground에서 실제 질문으로 정확도 확인

# 4. 만족하면 push (App Service에서 자동 재인덱스)
git add sample-docs/
git commit -m "chore: replace sample docs with real internal documents"
git push
```

> **주의**: 인덱스는 App Service의 컨테이너 부팅 시 `python build_index.py`로 다시 만들어짐. 즉 push만으로 충분.

---

### Phase 11 — Teams 채널 / Copilot Studio 통합 (별도 작업)

#### Teams 채널 추가 (1일, M365 Admin 협업)

```
Bot Service → チャネル → Microsoft Teams 추가
→ Teams 앱 매니페스트 작성 (manifest.json + 아이콘 2개)
→ M365 Admin에 사이드로딩 신청
→ Teams App Catalog에 배포
```

#### Copilot Studio 통합 (1-2주, 라이선스 + Admin 협업)

```
M365 Copilot 라이선스 확인
→ Copilot Studio에서 "Agent connector"로 우리 봇 등록
→ Bot Service App ID 입력
→ 트리거 키워드 / 라우팅 시나리오 정의 (예: "휴가", "VPN")
→ 회사 사용자에게 배포
```

이 두 단계는 **회사 환경 의존성이 크므로 본 일지의 범위 외**. 별도로 진행.

---

### 클린 셋업 체크리스트 (한눈에 보기)

```
[Phase 0 — 로컬]
□ Python 3.11 설치
□ Git, GitHub CLI 설치
□ VS Code 설치
□ 회사 GitHub 접근 확인

[Phase 1 — 권한 신청 (이메일)]
□ Azure Contributor 권한
□ Entra ID 앱 등록 권한
□ Foundry 사용 권한
□ (Phase 11) M365 Copilot 라이선스

[Phase 2 — Foundry]
□ 프로젝트 생성 (Japan East)
□ gpt-4o-mini 배포
□ text-embedding-3-small 배포
□ 엔드포인트/키 메모

[Phase 3 — Entra ID]
□ 앱 등록 (Single tenant)
□ Client ID 메모
□ Tenant ID 메모
□ Client Secret "값" 즉시 저장

[Phase 4 — 로컬 검증 (선택)]
□ clone + venv + pip install
□ .env 작성 (3개 그룹: Foundry / Entra / Contact)
□ python build_index.py
□ python app.py + Playground 동작 확인

[Phase 5 — App Service]
□ 구독이 Pay-as-you-go인지 확인
□ App Service 생성 (Linux, Python 3.11, B1)
□ GitHub Actions 연결

[Phase 6 — 환경 변수 (14개 必須)]
□ Foundry 5개
□ Entra ID 3개
□ HR_CONTACT / IT_CONTACT 2개
□ SCM_DO_BUILD_DURING_DEPLOYMENT=true
□ WEBSITE_RUN_FROM_PACKAGE=0
□ WEBSITES_PORT=8000
□ PYTHONUNBUFFERED=1
□ 시작 명령: python build_index.py && python app.py

[Phase 7 — 첫 배포]
□ git push로 빌드 트리거
□ Log stream 정상 메시지 확인
□ curl로 HTTP 401 확인

[Phase 8 — Bot Service]
□ Azure Bot 생성 (F0)
□ App ID = Entra ID Client ID
□ Messaging endpoint 설정

[Phase 9 — E2E 검증]
□ Test in Web Chat
□ 일본어 4종 질문 검증

[Phase 10 — 실문서]
□ sample-docs/ 비우고 진짜 문서
□ git push → 자동 재인덱스
□ 정확도 검증

[Phase 11 — 통합 (선택)]
□ Teams 채널
□ Copilot Studio
```

---

## 회사 PC 재작업 시 주의점

### 동일한 것 (그대로 재사용)

- 모든 Python 코드 (`*.py`)
- `requirements.txt`
- `sample-docs/*.md`
- Azure Portal 클릭 순서
- 시작 명령 (`python build_index.py && python app.py`)
- 환경 변수 **이름** (값은 다름)
- 본 일지

### 다른 것 (회사 환경별 값 새로 발급)

```
구독:        회사 Azure 구독
리소스 그룹: 회사 컨벤션 따름
App Service: 새 이름 (글로벌 unique)
Entra ID:    회사 테넌트, 새 앱 등록
   ├─ 새 Client ID
   ├─ 새 Client Secret (즉시 저장!)
   └─ 회사 Tenant ID
Foundry:     회사 Foundry 인스턴스
   ├─ 새 엔드포인트
   ├─ 새 키
   └─ 새 모델 배포명 (회사 컨벤션)
Bot Service: 새 이름
GitHub:      CollabCentralOrganization/m365-copilot-agent (이미 존재)
```

### 회사 환경 마찰 예상 지점

| 항목 | 위험도 | 대응 |
|---|---|---|
| Entra ID 앱 등록 권한 | 🔴 높음 | IT 신청 (Application Developer 역할 필요) |
| Azure 구독 Contributor 권한 | 🟡 중간 | IT가 권한 부여 |
| Foundry 모델 배포 권한 | 🟡 중간 | 회사 정책 확인 (대형 모델은 별도 승인) |
| 회사 GitHub org 접근 | 🟢 낮음 | 기존 계정으로 OK |
| App Service 비용 승인 | 🟡 중간 | $13/월 PoC 비용 사전 합의 |
| Teams 채널 활성화 (다음 단계) | 🔴 높음 | M365 Admin 협업 |
| Copilot Studio 등록 (다음 단계) | 🔴 높음 | M365 Copilot 라이선스 + Admin 승인 |
| 회사 네트워크 / 프록시 | 🟡 중간 | pip install 시 사내 미러 사용? |

### 회사 PC 재작업 권장 순서

```
[Day 1 — 권한 신청 + 로컬 준비]
□ 회사 Azure 구독 Contributor 권한 확인 (안 되면 IT 티켓)
□ Entra ID 앱 등록 권한 신청
□ Foundry 사용 권한 확인
□ (병행) 로컬 환경 셋업
   - git clone (회사 GitHub org)
   - python -m venv .venv
   - pip install -r requirements.txt
   - .env 파일 준비 (값은 비워둠)

[Day 2-3 — 권한 승인 후 인프라 구성]
□ Foundry 모델 배포 (gpt-4o-mini + text-embedding-3-small)
□ Entra ID 앱 등록 → CLIENT_ID / SECRET / TENANT_ID 확보
□ Azure 구독 업그레이드 확인 (회사면 보통 이미 PAYG)
□ App Service 생성 (B1, Python 3.11)
□ GitHub Actions 연결
□ 환경 변수 12개 등록 (본 일지 참고)
□ 배포 → SSH로 정상 동작 확인 → curl로 200 확인

[Day 3-4 — Bot 연결]
□ Bot Service 생성 (App ID = CLIENT_ID 재사용)
□ Messaging endpoint 설정
□ Web Chat에서 일본어 질문 테스트

[Day 5 이후]
□ 실제 사내 문서로 인덱스 교체 (HR + IT)
□ Teams 채널 활성화 검토
□ Copilot Studio 통합 (M365 Admin 협업)
□ A2A 연계 (AWS 측 팀과)
```

### 시간 예상

오늘의 시행착오를 알고 있는 상태로 회사 PC에서 재현하면:

| 단계 | 예상 소요 |
|---|---|
| 로컬 환경 셋업 | 30분 |
| 권한 신청·승인 대기 | 1-3일 (외부 요인) |
| Foundry 모델 배포 | 30분 |
| Entra ID 앱 등록 | 30분 |
| App Service 생성 + 환경 변수 + 배포 | 1시간 |
| Bot Service 생성 + 테스트 | 30분 |
| **순수 작업 시간 합계** | **약 3시간** |

오늘은 시행착오 포함 8시간 정도 걸렸음. 회사에선 이미 알고 있으니까 3시간이면 끝남.

---

## 오늘 만든 산출물

| 파일/리소스 | 위치 | 비고 |
|---|---|---|
| Python 코드 (4개 .py) | 개인 GitHub + 회사 GitHub | 동기화 완료 |
| `requirements.txt` | 동일 | cryptography 추가 |
| 샘플 문서 | `sample-docs/*.md` | 그대로 |
| `README.md` | 일본어 셋업 가이드 | 그대로 |
| `TECHNICAL_DECISIONS.md` | 기술 선정 근거 | 어제 작성 |
| `TODAY_PLAN_20260518.md` | 오늘 작업 계획 | 작업 직전 |
| **`DEPLOYMENT_JOURNAL_20260518.md`** | **본 문서 — 배포 일지** | 회사 PC 가서 그대로 참고 |
| Azure App Service | South Central US | 동작 중 |
| Azure Bot Service | Global | 동작 중 |
| Entra ID 앱 | 테넌트 | 등록 + 시크릿 보관 |

### Git 커밋 로그 (오늘분)

```
87c787f fix(auth): enable JWT validation with Entra ID credentials
0388d89 fix: add cryptography for JWT signature verification
18eeb39 trigger redeploy with WEBSITE_RUN_FROM_PACKAGE=0
36ab5c5 trigger redeploy after settings
00db018 trigger redeploy
2a383a1 Add or update the Azure App Service build and deployment workflow config
```

배포 트리거 commit이 많은 건 GitHub Actions 빌드 결과를 보기 위함이었음. 회사에선 한 번에 갈 수 있으니 깔끔할 것.

---

## ✅ 최종 검증 완료

**2026-05-18 — Bot Service Web Chat 실측**

질문 (일본어):
```
年休は何日もらえますか?
```

응답 (Markdown 렌더링됨):
```
年休の付与基準は以下の通りです：
  • 入社1年目：15日
  • 2年目以降毎年1日追加（最大25日）

出典: 1.1 年次有給休暇
```

검증된 동작:
- ✅ Bot Service JWT 전송 → 우리 서버 JWT 검증 통과
- ✅ outbound channel 통신 정상 (MsalConnectionManager 작동)
- ✅ RAG로 HR 정책 문서 정확히 검색
- ✅ Foundry `gpt-4o-mini`가 일본어 응답 생성
- ✅ 출처 섹션 자동 부착 (`1.1 年次有給休暇`)
- ✅ Markdown 형식 (bullet 리스트) 렌더링

**오늘 PoC 운영 직전 단계까지 완료. 회사 PC 이관 준비 완료.**

---

## 다음 단계

### 즉시 (오늘~내일)

| 우선순위 | 작업 | 비고 |
|---|---|---|
| ~~1~~ | ~~Bot Service Web Chat 일본어 동작 검증~~ | ✅ 완료 |
| ~~2~~ | ~~본 일지에 "최종 검증 완료" 추가~~ | ✅ 완료 |
| 1 | 추가 질문으로 RAG 폭 검증 (HR + IT 양쪽) | "VPN 접続方法は?" 등 |

### 단기 (1주 내)

| 우선순위 | 작업 | 비고 |
|---|---|---|
| 3 | 회사 PC로 인프라 이관 | 본 일지 그대로 참고 |
| 4 | 실제 사내 문서로 인덱스 교체 | HR + IT 실문서 |
| 5 | App Insights 연결 + 로깅 강화 | 운영 가시성 |
| 6 | 예산 알림 설정 ($20 임계) | 비용 안전망 |

### 중기 (1개월 내)

| 우선순위 | 작업 | 비고 |
|---|---|---|
| 7 | Teams 채널 활성화 | M365 Admin 협업 |
| 8 | Copilot Studio 통합 | 회사 라이선스 확인 |
| 9 | A2A 프로토콜로 AWS 팀 에이전트와 연계 | 본 프로젝트 핵심 목적 |

### 장기 (PoC → 운영)

| 우선순위 | 작업 | 비고 |
|---|---|---|
| 10 | FAISS → Azure AI Search 또는 Cosmos DB Vector 전환 | 영구 인덱스 |
| 11 | Slot 배포 + 무중단 업데이트 | 운영 패턴 |
| 12 | 다국어 지원 (일본어 외) | 비즈니스 요구에 따라 |
| 13 | RBAC 기반 문서 권한 분리 | HR 문서 vs 일반 문서 |

---

## 부록 A — 환경 변수 빠른 참조

회사 PC에서 그대로 복붙해서 쓸 수 있게 정리.

### 로컬 `.env` (개발용)

```bash
# --- Azure OpenAI / Foundry ---
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small

# --- Server (로컬) ---
PORT=3978

# --- Entra ID (로컬 테스트 시 비워도 OK) ---
CLIENT_ID=
CLIENT_SECRET=
TENANT_ID=
```

### Azure App Service 환경 변수 (운영용)

```
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_KEY
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
CLIENT_ID
CLIENT_SECRET
TENANT_ID
SCM_DO_BUILD_DURING_DEPLOYMENT=true
WEBSITE_RUN_FROM_PACKAGE=0
WEBSITES_PORT=8000
PYTHONUNBUFFERED=1
```

---

## 부록 B — 자주 보게 될 로그 패턴 빠른 진단표

| 로그 키워드 | 원인 | 해결 |
|---|---|---|
| `Operation cannot be completed without additional quota` | 구독 쿼터 0 | PAYG 업그레이드 |
| `can't open file '/home/site/wwwroot/build_index.py'` | zstd 압축 안 풀림 | `WEBSITE_RUN_FROM_PACKAGE=0` |
| 컨테이너 재시작 + 침묵 | stdout buffering + 포트 미감지 | `PYTHONUNBUFFERED=1` + `WEBSITES_PORT=8000` |
| `MissingCryptographyError` | PyJWT 의존성 누락 | `cryptography` 추가 |
| `Invalid audience: <GUID>` | CLIENT_ID 미전달 | `AgentAuthConfiguration(client_id=...)` |
| `'NoneType' object has no attribute 'get_token_provider'` | connection_manager 미주입 | `microsoft-agents-authentication-msal` 설치 + `MsalConnectionManager` 주입 |
| `No service connection configuration provided` | MsalConnectionManager 키 이름 오타 | dict 키를 정확히 `"SERVICE_CONNECTION"`으로 |
| `Invalid issuer` | TENANT_ID 불일치 | 환경 변수 확인 |
| `Signature verification failed` | CLIENT_SECRET 잘못됨 | Entra ID에서 재발급 |
| `Connection timeout` | App Service 죽음 또는 시작 중 | 로그 스트림 확인 |

---

*본 문서는 2026-05-18 작업 일지입니다. PoC 진척에 따라 갱신됩니다.*
*다음 갱신 예정: 회사 PC 이관 완료 시 / Bot Service 일본어 검증 완료 시.*
