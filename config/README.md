# 발신기관 설정

`issuer.example.json`을 `issuer.json`으로 복사해 로컬 발신기관 정보를 입력합니다.
`issuer.json`은 gitignore 대상이며 예제의 모든 값은 비어 있습니다.

`mask_korean_pii.py`의 일반 마스킹과 Vault 토큰화는 매 호출마다 이 저장소의
`config/issuer.json`을 읽습니다. `phone`에 명시한 전화번호만 예외로 보존합니다.
여러 번호는 문자열 배열로 입력할 수 있으며 하이픈·공백·점은 비교 시 무시합니다.
설정이 없거나 비었거나 잘못된 JSON이면 전화번호 예외는 없습니다.
Python 호출에서는 `issuer_config=Path(...)`로 별도 설정 파일을 지정할 수 있습니다.

`organization`, `address`, `account`, `author`, `seal_image`는 발신기관 메타데이터입니다.
이 필드들은 개인정보 탐지·마스킹 예외를 자동으로 만들지 않습니다.
