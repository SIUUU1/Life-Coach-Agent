# 🌱 Life Coach Agent

Streamlit 기반 채팅 UI와 OpenAI Agents SDK로 만든 라이프 코치 챗봇입니다.
동기부여, 자기계발, 습관 형성에 대한 조언을 웹 검색을 통해 근거 있게 제공하고,
대화 내용을 SQLite에 저장해 이전 맥락을 기억합니다.

## 주요 기능

- **Streamlit 채팅 인터페이스**: `st.chat_input`, `st.chat_message`로 구현한 대화형 UI
- **OpenAI Agents SDK (Agent + Runner)**: 에이전트 정의와 실행을 SDK로 처리
- **웹 검색 도구**: 내장 `WebSearchTool`로 동기부여 콘텐츠, 자기계발 팁, 습관 형성 전략을 검색
- **파일 검색 도구**: 개인 목표 문서(PDF/TXT)를 업로드해 OpenAI Vector Store에 인덱싱하고,
  `FileSearchTool`로 코치가 사용자의 목표·일기를 참조 — 웹 검색과 결합해 개인화된 조언 제공
- **세션 메모리 (SQLite)**: `SQLiteSession`을 사용해 대화 기록을 `coach_memory.db`에 자동 저장/조회
- **라이프 코치 페르소나**: 항상 한국어로, 격려하는 어조로 응답하며 구체적인 실천 방법을 제안

## 프로젝트 구조

```
.
├── app.py              # Streamlit 앱 (메인 로직)
├── main.py             # `uv run main.py`용 진입점 (내부적으로 streamlit run 실행)
├── requirements.txt    # 의존성 목록
├── sample_goals.txt     # 테스트용 샘플 목표 문서
├── .gitignore           # SQLite DB 파일 등 제외
└── images/              # README용 스크린샷

```

## 실행 결과

웹 검색을 통해 조언을 제공하는 모습:

![웹 검색 데모](images/search_demo1.png)
![웹 검색 데모](images/review_goals_test.png)


## 시작하기

### 1. 의존성 설치

```bash
pip install -r requirements.txt
# 또는 uv 사용 시
uv sync
```

### 2. 앱 실행

```bash
uv run main.py
# 또는
uv run streamlit run app.py
```

### 3. API 키 입력

브라우저에서 `http://localhost:8501`로 접속한 뒤, 사이드바에서 OpenAI API 키를 설정합니다.

1. **OpenAI API Key** 입력칸에 키(`sk-...`)를 붙여넣습니다.
2. **Save API Key** 버튼을 누르면 키가 적용되고 **입력칸이 사라져** 실수로 수정되지 않습니다.
3. 키를 바꾸려면 **Change API Key** 버튼을 누르면 입력칸이 다시 나타납니다.

입력한 키는 디스크에 저장되지 않고 현재 세션 메모리에만 유지됩니다.

### 4. 목표 문서 업로드 (파일 검색)

사이드바의 **📄 Goal documents**에서 개인 목표가 담긴 PDF/TXT 파일을 업로드하고
**Review my goals** 버튼을 누르면, 코치가 해당 문서를 검토해 개인화된 조언을 제공합니다.
테스트용으로 `sample_goals.txt`가 포함되어 있습니다.

## 참고

- 웹 검색(`WebSearchTool`)은 Responses API를 지원하는 모델(`gpt-4.1`, `gpt-4o` 계열)이 필요합니다.
- 대화 기록은 로컬 SQLite 파일(`coach_memory.db`)에 저장되며, 사이드바의 "Clear conversation" 버튼으로 초기화할 수 있습니다.
- API 키는 사이드바에서 입력 후 **Save API Key**로 적용하며(잠금), **Change API Key**로 다시 변경할 수 있습니다. 디스크에 저장되지 않고 현재 세션에서만 사용됩니다.
- `coach_memory.db`는 `.gitignore`에 포함되어 있어 커밋되지 않습니다.

## 👨‍💻 Author

안시우