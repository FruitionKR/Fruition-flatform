# Fruition MVP

서비스 코드는 독립 저장소로 분리할 수 있도록 최상위 폴더로 구성합니다.

| 폴더 | 책임 | 독립 빌드 |
|---|---|---|
| [frontend](../../../frontend/README.md) | Next.js UI | `npm ci && npm run build` |
| [Access](../../../Access/README.md) | 인증·워크스페이스·권한 | `./gradlew test bootJar` |
| [Document](../../../Document/README.md) | 문서·채팅·Wiki API | `./gradlew test bootJar` |
| [AI](../../../AI/README.md) | pipeline·worker·converter | 자체 Python 의존성 및 Dockerfile |

명령은 해당 폴더에서 실행합니다. 통합 개발·AWS 준비는 루트 `infra/`, `k8s/`, `scripts/`가 담당합니다. [서비스 경계와 아키텍처](../architecture.md)를 참고하세요.


Fruition MVP는 사용자가 파일명을 정확히 기억하지 못해도, 개념이나 질문만으로 관련 Wiki page와 원본 근거를 찾을 수 있는지 검증하기 위한 웹 기반 지식화 데모입니다.

MVP의 핵심 가설은 단순 파일 검색이나 일반 RAG가 아니라, 업로드한 원본 문서를 LLM이 `source page`와 `concept page`로 컴파일하고, 이 Wiki page들을 그래프와 채팅 인터페이스에서 함께 탐색할 때 실제 사용 가치가 생긴다는 것입니다.

## 대상 사용자

초기 사용자는 논문, 강의자료, 과제 자료, 개인 필기처럼 한 주제에 묶인 문서를 많이 다루는 대학원생, 학부 연구생, 고학년 대학생입니다.

처음 검증할 문서 세트는 하나의 과목이나 연구 주제에 묶인 PDF, Markdown, 강의자료, 논문, 과제 자료입니다. MVP에서는 30~50개 정도의 문서를 기준으로, 비슷한 개념이 여러 파일에 흩어져 있어도 사용자가 원하는 원문과 Wiki page를 찾을 수 있는지 확인합니다.

## 핵심 사용자 경험

웹 데모는 로그인 없이 시작합니다.

사용자는 왼쪽 사이드바에 파일을 업로드하고, 업로드된 원본 파일을 flat list로 확인합니다. 원본 파일은 수정하지 않는 raw source로 보관하며, 그래프의 직접 node로 쓰지 않습니다.

LLM은 원본 문서를 읽고 원본을 대표하는 `source page`와 지식 단위인 `concept page`를 생성합니다. 화면의 메인 그래프는 원본 파일이 아니라 이 Wiki page들을 node로 보여주고, page 사이의 의미 관계를 edge로 표현합니다.

오른쪽 채팅 영역에서 사용자가 자연어로 질문하면, 시스템은 관련 Wiki page를 우선 읽고 답변합니다. 답변에 사용된 source/concept page와 연결 path는 그래프에서 함께 하이라이트합니다.

```text
왼쪽 사이드바
  원본 파일 목록

메인 왼쪽 영역
  Wiki graph
  - source page node
  - concept page node
  - page 간 연결 edge

메인 오른쪽 영역
  LLM 채팅
  - 질문 입력
  - Wiki 기반 답변
  - 답변에 사용된 node/path 하이라이트
```

## MVP 범위

MVP에서 반드시 검증할 흐름은 아래 하나입니다.

```text
문서 업로드 -> LLM Wiki page 생성 -> Wiki 기반 자연어 질문 -> 근거가 있는 답변 확인
```

최소 기능은 다음과 같습니다.

- 사용자가 PDF 또는 Markdown 문서 업로드
- 업로드한 문서에서 본문 텍스트 추출
- 원본 파일, 서비스 관리 정보, Wiki Markdown 분리 저장
- 고정된 Wiki 작성 가이드라인으로 source page와 concept page 생성
- 생성된 Wiki page 탐색
- source page에서 원본 출처 확인
- 자연어 질문에 대해 Wiki page 기반 답변 생성
- 답변에 사용된 Wiki page와 원본 근거 표시
- 문서 처리 성공/실패와 생성된 Wiki page를 최소 로그로 확인

## Wiki Page 모델

`source page`는 원본 문서 1개에 대응되는 요약/출처 페이지입니다. 원본 파일 URI, 문서 요약, 핵심 내용, 추출된 concept 목록, 원본 근거를 담습니다.

`concept page`는 문서에서 추출된 개념, 방법론, 기술, 문제, 주장 같은 지식 단위입니다. MVP에서는 `Definition`, `Key Points`, `Evidence`, `Related Concepts` 네 가지 섹션만 생성합니다.

이 구조의 목적은 원본 파일과 Wiki graph를 분리하는 것입니다. 원본은 보존 대상이고, 그래프에서 탐색되는 지식 단위는 LLM이 생성한 Wiki page입니다.

## 데이터 흐름

```text
원본 파일 업로드
  -> Object Storage의 sources/에 원본 저장
  -> AppDB의 documents에 파일 관리 정보 저장
  -> MarkItDown으로 본문 텍스트 추출
  -> LLM Wiki Builder가 source page 생성
  -> 문서에서 concept page 생성 또는 기존 concept page와 연결
  -> wiki_page_links로 Wiki page 간 관계 저장
  -> wiki_pages를 node, wiki_page_links를 edge로 화면 그래프 표시
  -> 사용자가 채팅하면 관련 Wiki page를 읽고 답변
  -> 답변에 사용된 node와 path를 그래프에서 하이라이트
```

## 저장 원칙

원본 파일과 Wiki Markdown은 같은 객체 스토리지에 저장하되 prefix를 분리합니다.

```text
sources/documents/{document_id}/original.{ext}
sources/documents/{document_id}/extracted.txt
wiki/sources/{document_slug}.md
wiki/concepts/{concept_slug}.md
```

AppDB는 파일 본문을 저장하지 않고, 문서 ID, 처리 상태, 원본 URI, 추출 텍스트 URI, Wiki page URI, page 연결 관계만 관리합니다.

## MVP에서 제외하는 것

아래 기능은 핵심 가설 검증 이후 확장 범위로 둡니다.

- 로그인, 팀, 권한, 외부 공유
- 별도 작업 큐와 재시도 시스템
- Elasticsearch, vector database, graph database
- Wiki page 승인/롤백, 감사 로그 고도화
- 중복 concept 병합과 모순 후보 탐지
- HWP/HWPX, OCR, 이미지 기반 문서 처리
- 채팅 답변을 새로운 Wiki page로 승격하는 기능

## 기술 방향

MVP는 Spring Boot 백엔드, PostgreSQL AppDB, S3 호환 Object Storage, 컨테이너 기반 PDF 변환 워커, 외부 LLM API를 중심으로 구성합니다.

현재 로컬 개발 인프라는 PostgreSQL과 MinIO를 기준으로 시작합니다. PDF 변환은 별도 converter 컨테이너에서 `pdfinfo`, `pdffonts`, `ocrmypdf`, `tesseract`, `ghostscript`, `markitdown[pdf]` 조합으로 처리하며, DOCX/PPTX/XLSX 등은 데모 필요에 따라 확장합니다.

상세 아키텍처는 [docs/architecture.md](../architecture.md), 데이터 모델은 [docs/data-model.md](../data-model.md)를 기준으로 관리합니다.

## 저작권

Copyright (c) 2026 Fruition KR
