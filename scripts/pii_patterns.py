"""Shared Korean PII detector patterns and normalization for both entry points."""
import json
from pathlib import Path
import re
# ── 주민등록번호 / 외국인등록번호 ──────────────────────────────────
# 6자리 생년월일 - 성별코드 + 일련. 유효 생월일만 후보로 잡아 오탐을 줄인다.
# 성별코드 1~4는 주민등록번호, 5~8은 외국인등록번호다.
#
# 경계 주의: \b를 쓰면 안 된다. 한국어 조사는 띄어쓰기 없이 숫자에 바로
# 붙으므로("901212-1234568임을") 숫자-한글 사이에 단어 경계가 생기지 않는다.
# (\w도 마찬가지 — 한글은 \w다.) 따라서 숫자 경계만 검사한다:
#   (?<!\d) 앞이 숫자가 아니면 시작, (?!\d) 뒤가 숫자가 아니면 끝.
# 이러면 조사가 붙어도 잡히고, 더 긴 숫자열의 일부는 잡지 않는다.
_RRN_RE = re.compile(
    r"(?<!\d)(?P<birth>\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))"
    r"(?P<sep>[-\s.]*)(?P<sex>[1-8])(?P<rest>\d{6})(?!\d)"
)
_RRN_WEIGHTS = (2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5)

# ── 여권 / 운전면허 / 외국인등록번호 (형식매칭+경고 수준) ──────────
# 여권: 구형 M+8자리 (예: M22000000)와 신형 M+3자리+영문+4자리
# (예: M123A4567). 대소문자를 가리지 않는다. 운전면허: 2-2-6-2
# (예: 12-34-567890-12). 외국인등록번호: RRN과 동일 생년월일+구분자+
# 성별코드 5~8+6자리. RRN 가중치로 체크섬 검증을 시도하되 실패해도
# 마스킹한다(틀린 번호≠비개인정보).
_PASSPORT_RE = re.compile(
    r"(?<![A-Za-z0-9])([MSRmsr])(?:\d{8}|\d{3}[A-Za-z]\d{4})(?![A-Za-z0-9])"
)
_DRIVER_LICENSE_RE = re.compile(r"(?<!\d)(\d{2})[-\s.]+(\d{2})[-\s.]+(\d{6})[-\s.]+(\d{2})(?!\d)")
_FOREIGNER_RE = re.compile(
    r"(?<!\d)(?P<birth>\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))"
    r"(?P<sep>[-\s.]*)(?P<sex>[5-8])(?P<rest>\d{6})(?!\d)"
)

# ── 카드번호 (16자리, Luhn 통과분만 확정) ──────────────────────────
# 계좌번호보다 먼저 적용해 4그룹 이중 매칭을 막는다.
_CARD_RE = re.compile(
    r"(?<!\d)(\d{4})[-\s.]*(\d{4})[-\s.]*(\d{4})[-\s.]*(\d{4})(?!\d)"
)

# ── 전화/휴대폰 ─────────────────────────────────────────────────────
# 휴대폰은 구분자 생략까지 지원(01012345678). 유선은 구분자(-, 공백, 점)
# 필수 — 무구분자 유선은 오탐이 커서 landline_nodelim 옵션으로만 켠다.
_MOBILE_RE = re.compile(r"(?<!\d)((?:(?:\(\+82\)|\+82|0082)[-\s.]*(?:\(0\)|0)?1[0136789])|01[0136789])[-\s.]*(\d{3,4})[-\s.]*(\d{4})(?!\d)")
_PHONE_RE = re.compile(r"(?<!\d)((?:(?:\+82|0082)[-\s.]*(?:\(0\)|0)?(?:2|[3-6]\d)|02|0[3-6]\d|070|050\d|\(0\d{1,2}\)))(?:(?<=\))\s*|[-\s.]+)(\d{3,4})[-\s.]+(\d{4})(?!\d)")
_LANDLINE_NODELIM_RE = re.compile(r"(?<!\d)((?:(?:\+82|0082)[-\s.]*(?:\(0\)|0)?(?:2|[3-6]\d)|02|0[3-6]\d|070|050\d))(\d{3,4})(\d{4})(?!\d)")

# Issuer phone exemptions are opt-in and never shipped with real values.
ISSUER_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "issuer.json"


def load_issuer_phone_allowlist(config_path=None):
    """Read local configuration per operation; missing/invalid data exempts nothing.

    phone accepts a string or a list of strings. Other issuer metadata does not
    implicitly exempt matching personal names, addresses or account numbers.
    """
    path = ISSUER_CONFIG_PATH if config_path is None else Path(config_path)
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    if not isinstance(config, dict):
        return frozenset()
    phones = config.get("phone", "")
    if isinstance(phones, str):
        phones = [phones]
    if not isinstance(phones, list):
        return frozenset()
    return frozenset(
        re.sub(r"\D", "", phone) for phone in phones
        if isinstance(phone, str) and re.fullmatch(r"[0-9()+ .-]+", phone)
        and re.sub(r"\D", "", phone)
    )


# ── 계좌번호 (은행 무관 3~5그룹 형식, 끝 4자리만 유지) ─────────────
# 첫 그룹은 최소 3자리로 둬 운전면허(2-2-6-2)와의 충돌을 피한다.
_ACCOUNT_RE = re.compile(r"(?<!\d)(\d{3,6})[-\s.]+(\d{2,6})[-\s.]+(\d{2,6})(?:[-\s.]+(\d{2,6}))?(?:[-\s.]+(\d{2,6}))?(?!\d)")
# 날짜(2024-01-16)와 0으로 시작하는 번호판별 값은 계좌로 오탐하지 않는다.
_DATEISH_RE = re.compile(r"^(19|20)\d{2}[-\s.]+(0[1-9]|1[0-2])[-\s.]+(0[1-9]|[12]\d|3[01])$")

# ── 이메일 ──────────────────────────────────────────────────────────
# 이메일은 숫자 경계가 아니라 로컬파트/도메인 문자 집합으로 경계를 잡는다
# ("example.com이다"처럼 조사가 붙어도 잡히도록).
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*"
    r"@([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![A-Za-z0-9.-])"
)

# ── 이름 (opt-in: 성씨 사전 + 호칭/라벨 패턴) ─────────────────────
# 맨 앞 글자가 성씨여야 하고, 직함/역할명(사장님·고객님 등)은 제외한다.
# 사전 없는 전수 이름 탐지는 오탐이 커서 기본 타입에 넣지 않는다.
_KOREAN_SURNAMES = frozenset(
    "김이박최정강조윤장임한오서신권황안송류홍전고문양손배백허유남심노하곽"
    "성차주우구민진지엄채원천방공현함변염여추도소석선설마길연위표명기반"
    "왕금옥육인맹제모탁국은편예봉"
)
_NAME_BLOCKLIST = frozenset({
    "사장", "부장", "과장", "차장", "팀장", "대리", "주임", "회장", "부회장",
    "선생", "고객", "회원", "사용자", "담당", "원장", "교수", "박사", "학생",
    "어머", "아버", "할머", "할아버", "손님", "어르신", "여러분", "국민",
    "주민", "시민", "관계자", "관련자", "책임자", "담당자", "작성자",
})
# 라벨 뒤의 이름: "성명: 김철수", "피고인 이영희는" — 라벨은 보존하고 이름만 마스킹.
# 이름 그룹은 비탐욕 — "김철수는"처럼 조사를 이름에 삼키지 않는다.
_LABELED_NAME_RE = re.compile(
    r"(성명|이름|성함|대표자|신청인|피고인|피해자|원고|피고|참고인|의뢰인|상대방|조사대상자|고객명|수신인|발신인|보낸사람|받는사람)[:：]?\s*([가-힣]{3}|[가-힣]{2,4}?)"
    r"(?=[은는이가을를도의과와께]|[^가-힣]|$)"
)
# 호칭 붙은 이름: "김철수님", "이영희 씨", "박대리님께서" — 성씨 사전 + 블록리스트로
# 오탐을 걸러내고, 호칭 뒤에는 조사나 비한글이 와야 한다(연속 한글 단어 오인 방지).
_HONORIFIC_NAME_RE = re.compile(
    r"(?<![가-힣])([가-힣]{2,4})\s*(씨|님|귀하)"
    r"(?=[은는이가을를도의과와께한테에게]|[^가-힣]|$)"
)

# ── 주소 (opt-in: 시도+시군구+도로명/지번 구조 필수) ────────────────
# 번지수/호수를 포함하는 완전한 구조만 잡는다 — "서울시 강남구" 같은
# 지역명만으로는 마스킹하지 않는다(개인 식별 정보가 아니므로).
_ADDR_RE = re.compile(
    r"[가-힣]{2,}(?:특별시|광역시|특별자치시|특별자치도|시|도)\s+"
    r"[가-힣]{1,10}(?:시|군|구)\s+"
    r"(?:[가-힣0-9]{1,10}(?:로|길)|[가-힣]{1,10}(?:읍|면|동|리))"
    r"\s*\d+(?:-\d+)*(?:번지?|호)?(?:\s*\d+층|\s*\d+호)?"
)


from pii_normalize import NormalizedPattern, original_value
_LABELED_ACCOUNT_RE = re.compile(r"((?:계좌번호|계좌)\s*[:：]?\s*)(\d{10,16})(?!\d)")
for _pattern_name in ("_LABELED_ACCOUNT_RE", "_RRN_RE", "_MOBILE_RE", "_PHONE_RE", "_LANDLINE_NODELIM_RE", "_CARD_RE", "_ACCOUNT_RE", "_EMAIL_RE", "_PASSPORT_RE", "_DRIVER_LICENSE_RE", "_FOREIGNER_RE", "_LABELED_NAME_RE", "_HONORIFIC_NAME_RE", "_ADDR_RE"):
    globals()[_pattern_name] = NormalizedPattern(globals()[_pattern_name])

