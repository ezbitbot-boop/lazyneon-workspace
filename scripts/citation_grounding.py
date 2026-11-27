#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""citation_grounding.py — every concrete value a report cites must come from the evidence.

Extracts the values a report cites and checks each one against the evidence files (LLM-free):
  hash    hex digests (16+ chars) and abbreviated digests (``e3b0c4…b855``, 6+ chars per side)
  date    ISO/Korean/dotted dates and date-times (``2014. 12. 4.`` and ``2014-12-04`` are the same value)
  time    clock times without a date
  quote   "…", “…”, ‘…’, '…', 「…」, 『…』 spans
  file    file names with an extension and Windows paths
  number  numbers with a unit (건, 명, 원, 만원, %, bytes, MB …)
  person  Korean names with a title (``김민수 과장``) and names in person fields/columns (담당자, 작성자 …)
  tool    named forensic tools (Autopsy, EnCase, FTK Imager …) the report claims were used

Each value is
  grounded     present in an evidence file: plain text, text inside docx/hwpx/xlsx/pptx/odt members,
               after NFC normalisation and removing zero-width characters; dates compared after normalisation
  computed     equal to a value derivable from an evidence file: sha256/sha1/md5 of a file or archive member,
               a prefix/suffix of such a digest, a file size (bytes or KB/MB/GB, 1000 or 1024 based),
               or an evidence time shifted by ±9 h (UTC↔KST)
  labelled     not verifiable, but the line says the model derived it (계산/산출/환산/computed …); hashes never qualify
  hedged       not found, and the line marks it unverified (미확인, 미측정, INSUFFICIENT_DATA, unverified),
               or it is a quote/file the line says is absent (없음, 발견되지 않음, not found …)
  unsupported  none of the above — a likely invented value

Report-quality check: warns, does not decide admissibility. Values the model writes in its own voice without
quoting (indirect speech, paraphrase) are not checked; see verify_report.py and source_grounding.py for those.

CLI: python scripts/citation_grounding.py 보고서.md --evidence 증거폴더 [파일...] [--format table|json|both] [--strict]
Exit: 0 checked (unsupported values are listed), 1 --strict with unsupported values, 2 input error.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")
SPACE_RE = re.compile(r"\s+")
TEXT_CAP_BYTES = 32 * 1024 * 1024
MEMBER_CAP_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_HASH_MB = 256
ZIP_EXTS = {".docx", ".xlsx", ".pptx", ".hwpx", ".odt", ".ods", ".odp", ".zip"}
MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".heic", ".webp", ".bmp", ".tif", ".tiff", ".mp4", ".mov", ".avi", ".mkv",
              ".m4a", ".mp3", ".wav", ".aac", ".amr", ".3gp", ".ogg", ".e01", ".ex01", ".dd", ".raw", ".img", ".vmdk", ".iso"}
# A tag run that closes a paragraph/cell/row becomes a line break; run-internal tags vanish so split words rejoin.
XML_BREAK_RE = re.compile(r"</(?:\w+:)?(?:p|tc|tr|si|c|row|v|cell|subList|li|div|td|th|h\d)>|<(?:\w+:)?(?:br|tab|lineBreak)\b", re.I)
XML_TAGS_RE = re.compile(r"(?:<[^>]*>)+")

FULL_HEX_RE = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{16,128}(?![0-9A-Za-z])")
ABBREV_HEX_RE = re.compile(r"(?<![0-9A-Za-z])([0-9a-fA-F]{6,})?\s?(?:…|\.{2,3})\s?([0-9a-fA-F]{4,})?(?![0-9A-Za-z])")
DATE_RE = re.compile(
    r"(?<![\d.])(?P<y>(?:19|20)\d{2})\s*(?:[-./]|년)\s*(?P<m>\d{1,2})\s*(?:[-./]|월)\s*(?P<d>\d{1,2})(?![\d])(?:\s*(?:일|\.(?!\d)))?"
    r"(?:(?:\s*\([^)\n\d]{1,4}\))?(?:\s+|T|\s*,\s*)"
    r"(?:(?P<ap>오전|오후|AM|PM)\s*)?(?P<H>\d{1,2})\s*(?::|시)\s*(?P<M>\d{1,2})(?:\s*(?::|분)\s*(?P<S>\d{2})\s*초?)?(?:\.\d+)?(?![\d:])"
    r"(?:\s*(?P<ap2>AM|PM)(?![A-Za-z]))?(?P<tz>Z|\s*[+-]\d{2}:?\d{2}|\s*\(?(?:UTC|KST|GMT)(?:\s*[+-]\s*\d{1,2}(?::?\d{2})?)?\)?)?)?",
    re.I)
US_DATE_RE = re.compile(
    r"(?<![\d./])(?P<a>\d{1,2})/(?P<b>\d{1,2})/(?P<y>(?:19|20)\d{2})(?![\d/])"
    r"(?:\s+(?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2}))?(?![\d:])(?:\s*(?P<ap2>AM|PM)(?![A-Za-z]))?)?", re.I)
TIME_RE = re.compile(r"(?<![\d:.])(?:(?P<ap>오전|오후|AM|PM)\s*)?(?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2}))?(?![\d:])(?:\s*(?P<ap2>AM|PM)(?![A-Za-z]))?", re.I)
QUOTE_RES = [
    re.compile(r'"([^"\n]{1,400})"'),
    re.compile(r"“([^”\n]{1,400})”"),
    re.compile(r"‘([^’\n]{1,400})’"),
    re.compile(r"(?<![A-Za-z0-9])'([^'\n]{1,400})'(?![A-Za-z0-9])"),
    re.compile(r"「([^」\n]{1,400})」"),
    re.compile(r"『([^』\n]{1,400})』"),
]
LAW_TITLE_RE = re.compile(r"(?:법|법률|령|규칙|조례|협약|규정|지침)$")
DEFINED_TERM_AFTER_RE = re.compile(r"^\s*(?:이?라\s*한다|이?라고\s*한다|이하)")
ELISION_RE = re.compile(r"\(중략\)|\(후략\)|…|\.{3}")
EXT = ("xlsx|xls|docx|doc|pptx|ppt|pdf|hwpx|hwp|txt|csv|tsv|json|jsonl|log|lnk|pf|evtx|dat|db|sqlite|exe|dll|sys|reg|e01|ex01|"
       "dd|raw|img|zip|7z|rar|pst|ost|eml|msg|jpg|jpeg|png|gif|heic|webp|bmp|tiff?|mp4|mov|avi|mkv|m4a|mp3|wav|aac|amr|3gp|ogg|"
       "html?|xml|ini|bin|vhdx?|vmdk|ps1|bat|cmd|iso|plist|sqlite3|db-wal|kdbx|key|pem")
WINPATH_RE = re.compile(r"(?<![\w])[A-Za-z]:\\(?:[^\\\s|,;\"'`<>()\[\]]+\\)*[^\\\s|,;\"'`<>()\[\]]+")
# No spaces: "녹취 파일.m4a" is cited as "파일.m4a" and matched as the end of an evidence file name.
FILE_RE = re.compile(r"(?<![\w.\-/\\])[\w$~가-힣][\w\-$~가-힣]*(?:\.[\w\-$~가-힣]+)*?\.(?:" + EXT + r")(?![A-Za-z0-9_])", re.I)
UNIT_PART = (r"억\s*원|만\s*원|천\s*원|원|건|개|명|회|통|차례|페이지|쪽|프레임|퍼센트|%|바이트"
             r"|(?:bytes?|B|KB|KiB|MB|MiB|GB|GiB|TB|TiB|files?|records?|rows?|entries|messages?|items?|frames?|pages?)(?![A-Za-z])")
NUMBER_RE = re.compile(r"(?<![\w.,])(?P<n>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<f>\d+))?\s*(?P<u>" + UNIT_PART + r")", re.I)
SIZE_UNITS = {"b": 0, "byte": 0, "bytes": 0, "바이트": 0, "kb": 1, "kib": 1, "mb": 2, "mib": 2, "gb": 3, "gib": 3, "tb": 4, "tib": 4}
KO_UNIT = {"억": 10 ** 8, "만": 10 ** 4, "천": 10 ** 3}
KO_AMOUNT_RE = re.compile(r"(\d[\d,]*)\s*(억|만|천)\s*원?")
SURNAMES = "김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주우구민나진지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용"
TITLES = ("씨", "님", "대표", "과장", "부장", "팀장", "사원", "대리", "교수", "박사", "이사", "사장", "실장", "차장", "주임", "본부장",
          "센터장", "변호사", "검사", "판사", "수사관", "경위", "경사", "경장", "순경", "선임", "책임", "연구원", "직원")
NAME_TITLE_RE = re.compile(r"(?<![가-힣])([" + SURNAMES + r"][가-힣]{2})\s?(?:" + "|".join(sorted(TITLES, key=len, reverse=True)) + r")")
NAME_TOKEN_RE = re.compile(r"(?<![가-힣])[" + SURNAMES + r"][가-힣]{2,3}(?![가-힣])")
PERSON_FIELD_RE = re.compile(r"담당|작성자|서명|확인자|수령인|인계자|인수자|분석자|분석관|검토자|의뢰인|피의자|용의자|사용자명|계정주|발신자|수신자|화자")
NAME_STOP = {"없음", "미상", "공란", "미기재", "해당", "해당없음", "기재", "기록", "자료", "확인", "확인불가", "미측정", "미확인", "비움", "기입",
             "예정", "추후", "별도", "본인", "담당", "분석", "작성", "보고", "법무", "정보", "제출", "수령", "이관", "보관", "복제", "서명",
             "방법", "일자", "시각", "조치", "기관", "불명", "주체", "확인자", "작성자", "담당자", "인계", "기록없음", "자료없음", "미입력",
             "관리자", "사용자", "피의자", "고소인", "의뢰인", "참고인", "수사관", "분석관", "검토자", "감정인", "이용자", "소유자", "정보없음"}
PARTICLES = ("으로", "에서", "에게", "께서", "에", "은", "는", "이", "가", "을", "를", "의", "로", "와", "과", "도", "만")
TOOLS = ["Autopsy", "Registry Explorer", "FTK Imager", "FTK", "Timeline Explorer", "EnCase", "X-Ways", "Magnet AXIOM", "AXIOM",
         "Cellebrite", "UFED", "Volatility", "KAPE", "Plaso", "log2timeline", "RegRipper", "Arsenal Image Mounter", "Guymager",
         "MFTECmd", "PECmd", "LECmd", "JLECmd", "EvtxECmd", "AmcacheParser", "ShellBags Explorer", "Sleuth Kit", "bulk_extractor",
         "USBDeview", "USB Detective", "Velociraptor", "HxD", "WinHex", "Belkasoft", "Oxygen Forensic", "R-Studio", "Recuva",
         "Hindsight", "BrowsingHistoryView", "Event Log Explorer", "Wireshark", "NirSoft", "Tableau"]
TOOL_ADVICE_RE = re.compile(r"권장|권고|필요|추가\s*(?:분석|검증|확인)|향후|가능|recommend|should|could|suggest", re.I)
COMPUTED_LABEL_RE = re.compile(r"계산|산출|환산|합산|변환|computed|calculated|derived|converted", re.I)
HEDGE_RE = re.compile(r"미확인|미측정|확인되지\s*않|INSUFFICIENT_DATA|unverified|not\s+verified", re.I)
# "보이스피싱"은 자료에 없음: a quote or file the report says is missing is not a claim that it exists.
ABSENT_RE = re.compile(r"발견되지\s*않|찾지\s*못|없음|없다|없었|없습니다|not\s+found|absent", re.I)
META_LINE_RE = re.compile(r"작성\s*일|작성\s*일자|작성\s*일시|보고\s*일|발행\s*일|출력\s*일|생성\s*일|report\s+date|prepared\s+on|generated\s+(?:on|at)|written\s+on", re.I)


def norm(text: str) -> str:
    """NFC, no zero-width characters, case-folded, whitespace collapsed."""
    return SPACE_RE.sub(" ", ZERO_WIDTH_RE.sub("", unicodedata.normalize("NFC", text))).casefold()


def decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", "ignore")
    if len(data) > 64 and data[1:200:2].count(0) > 40:
        return data.decode("utf-16-le", "ignore")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp949")
    except UnicodeDecodeError:
        return data.decode("utf-8", "ignore")


def xml_text(raw: str) -> str:
    return html.unescape(XML_TAGS_RE.sub(lambda m: "\n" if XML_BREAK_RE.search(m.group(0)) else "", raw))


def hour24(h: str, m: str, ap: str | None) -> tuple[int, int] | None:
    hh, mm = int(h), int(m)
    ap = (ap or "").upper()
    if ap in ("오후", "PM") and hh < 12:
        hh += 12
    elif ap in ("오전", "AM") and hh == 12:
        hh = 0
    return (hh, mm) if hh < 24 and mm < 60 else None


@dataclass
class Moment:
    date: str
    minute: str | None = None
    second: str | None = None


def moments(text: str) -> Iterable[tuple[re.Match[str], list[Moment]]]:
    """Dates and date-times in canonical form; ambiguous day/month orders yield every valid reading."""
    def build(y: str, mo: int, d: int, h, mi, s, ap) -> Moment | None:
        try:
            day = datetime(int(y), mo, d)
        except ValueError:
            return None
        if h is None:
            return Moment(day.strftime("%Y-%m-%d"))
        hm = hour24(h, mi, ap)
        if hm is None:
            return None
        at = day.replace(hour=hm[0], minute=hm[1], second=int(s) if s and int(s) < 60 else 0)
        return Moment(at.strftime("%Y-%m-%d"), at.strftime("%Y-%m-%d %H:%M"), at.strftime("%Y-%m-%d %H:%M:%S") if s else None)
    for m in DATE_RE.finditer(text):
        one = build(m["y"], int(m["m"]), int(m["d"]), m["H"], m["M"], m["S"], m["ap"] or m["ap2"])
        if one:
            yield m, [one]
    for m in US_DATE_RE.finditer(text):
        a, b = int(m["a"]), int(m["b"])
        found = [x for x in (build(m["y"], a, b, m["H"], m["M"], m["S"], m["ap2"]), build(m["y"], b, a, m["H"], m["M"], m["S"], m["ap2"])) if x]
        if found:
            yield m, found


def clock(m: re.Match[str]) -> tuple[str, str | None] | None:
    hm = hour24(m["H"], m["M"], m["ap"] or m["ap2"])
    if hm is None or (m["S"] and int(m["S"]) > 59):
        return None
    minute = f"{hm[0]:02d}:{hm[1]:02d}"
    return minute, f"{minute}:{m['S']}" if m["S"] else None


def ko_amounts(text: str) -> Iterable[str]:
    for m in KO_AMOUNT_RE.finditer(text):
        yield str(int(m.group(1).replace(",", "")) * KO_UNIT[m.group(2)])


def num_key(n: str, f: str | None = None) -> str:
    whole = str(int(n.replace(",", "")))
    frac = (f or "").rstrip("0")
    return f"{whole}.{frac}" if frac else whole


@dataclass
class Evidence:
    texts: list[tuple[str, str]] = field(default_factory=list)  # (label, normalised text)
    digests: dict[str, str] = field(default_factory=dict)       # hex digest -> "sha256(file)"
    sizes: list[tuple[int, str]] = field(default_factory=list)
    names: set[str] = field(default_factory=set)
    files: int = 0
    unhashed: list[str] = field(default_factory=list)
    unread: list[str] = field(default_factory=list)

    def finish(self) -> None:
        self.blob = "\n".join(t for _, t in self.texts)
        self.blob_nospace = SPACE_RE.sub("", self.blob)
        self.hexes = {h.lower() for h in FULL_HEX_RE.findall(self.blob)}
        self.dates, self.minutes, self.seconds, self.clocks = set(), set(), set(), set()
        shifted: list[datetime] = []
        for _, found in moments(self.blob):
            for mo in found:
                self.dates.add(mo.date)
                if mo.minute:
                    self.minutes.add(mo.minute)
                    self.clocks.add(mo.minute[11:])
                    at = datetime.strptime(mo.second or mo.minute, "%Y-%m-%d %H:%M:%S" if mo.second else "%Y-%m-%d %H:%M")
                    shifted += [at + timedelta(hours=9), at - timedelta(hours=9)]
                if mo.second:
                    self.seconds.add(mo.second)
                    self.clocks.add(mo.second[11:])
        for m in TIME_RE.finditer(self.blob):
            c = clock(m)
            if c:
                self.clocks.update(x for x in c if x)
        self.tz_dates = {s.strftime("%Y-%m-%d") for s in shifted}
        self.tz_minutes = {s.strftime("%Y-%m-%d %H:%M") for s in shifted}
        self.tz_seconds = {s.strftime("%Y-%m-%d %H:%M:%S") for s in shifted}
        self.tz_clocks = {s.strftime("%H:%M") for s in shifted} | {s.strftime("%H:%M:%S") for s in shifted}
        flat = re.sub(r"(?<=\d),(?=\d{3})", "", self.blob)
        # Bare numbers only when they stand alone: digits inside dates, times, ids or "12건" do not count.
        self.numbers = {num_key(a, b) for a, b in re.findall(r"(?<![\w.:/-])(\d+)(?:\.(\d+))?(?![\w:/-]|\.\d)", flat)} | set(ko_amounts(self.blob))
        self.unit_numbers = {f"{num_key(m['n'], m['f'])} {SPACE_RE.sub('', m['u'])}" for m in NUMBER_RE.finditer(self.blob)}

    def where(self, needle: str) -> str | None:
        for label, text in self.texts:
            if needle in text:
                return label
        return None


def _add_digests(ev: Evidence, data: bytes, label: str) -> None:
    for algo in ("sha256", "sha1", "md5"):
        ev.digests.setdefault(hashlib.new(algo, data).hexdigest(), f"{algo}({label})")


def _hash_file(path: Path) -> dict[str, str]:
    algos = {a: hashlib.new(a) for a in ("sha256", "sha1", "md5")}
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            for h in algos.values():
                h.update(chunk)
    return {a: h.hexdigest() for a, h in algos.items()}


def _read_pdf(path: Path) -> str:
    try:
        import pymupdf  # type: ignore
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError:
            return ""
    try:
        with pymupdf.open(str(path)) as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception:
        return ""


def iter_files(paths: Iterable[Path], exclude: set[Path]) -> Iterable[tuple[Path, str]]:
    for base in paths:
        if base.is_file():
            if base.resolve() not in exclude:
                yield base, base.name
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                p = Path(dirpath) / name
                if p.resolve() in exclude or p.is_symlink():
                    continue
                yield p, Path(os.path.relpath(p, base.parent)).as_posix()


def load_evidence(paths: Iterable[Path], exclude: Iterable[Path] = (), max_hash_mb: int = DEFAULT_MAX_HASH_MB) -> Evidence:
    ev = Evidence()
    skip = {Path(p).resolve() for p in exclude}
    for path, label in iter_files(paths, skip):
        ev.files += 1
        ev.names.add(norm(path.name))
        size = path.stat().st_size
        ev.sizes.append((size, label))
        if size <= max_hash_mb * 1024 * 1024:
            for algo, digest in _hash_file(path).items():
                ev.digests.setdefault(digest, f"{algo}({label})")
        else:
            ev.unhashed.append(label)
        ext = path.suffix.lower()
        if ext in MEDIA_EXTS or size > TEXT_CAP_BYTES:
            if ext not in MEDIA_EXTS:
                ev.unread.append(label)
            continue
        if ext == ".pdf":
            ev.texts.append((label, norm(_read_pdf(path))))
            continue
        data = path.read_bytes()
        if ext in ZIP_EXTS or zipfile.is_zipfile(path):
            try:
                with zipfile.ZipFile(path) as zf:
                    for info in zf.infolist():
                        if info.is_dir() or info.file_size > MEMBER_CAP_BYTES:
                            continue
                        member = zf.read(info)
                        mlabel = f"{label}!{info.filename}"
                        ev.names.add(norm(Path(info.filename).name))
                        _add_digests(ev, member, mlabel)
                        ev.sizes.append((info.file_size, mlabel))
                        text = decode(member)
                        if info.filename.lower().endswith((".xml", ".rels", ".html", ".htm", ".xhtml")):
                            text = xml_text(text)
                        ev.texts.append((mlabel, norm(text)))
                continue
            except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError):
                pass
        text = decode(data)
        if ext in (".xml", ".html", ".htm", ".xhtml"):
            text = text + "\n" + xml_text(text)
        if ext in (".json", ".jsonl"):
            text = text + "\n" + text.replace("\\\\", "\\")
        ev.texts.append((label, norm(text)))
    ev.finish()
    return ev


@dataclass
class Citation:
    kind: str
    value: str
    line: int
    status: str = "unsupported"
    via: str = ""


class Checker:
    def __init__(self, ev: Evidence, report_name: str = ""):
        self.ev = ev
        self.items: list[Citation] = []
        self.seen: set[tuple[str, str]] = set()
        self.own_names = {norm(report_name)} if report_name else set()
        self.plugin_names = {norm(p.name) for d in ("scripts", "skills", "bin") for p in (ROOT / d).rglob("*") if p.is_file()}

    def add(self, kind: str, value: str, key: str, line_no: int, line: str, result: tuple[str, str] | None) -> None:
        if (kind, key) in self.seen:
            return
        self.seen.add((kind, key))
        status, via = result or ("unsupported", "")
        if status == "unsupported":
            if kind != "hash" and COMPUTED_LABEL_RE.search(line):
                status, via = "labelled", "line marks the value as computed"
            elif HEDGE_RE.search(line) or kind in ("quote", "file") and ABSENT_RE.search(line):
                status, via = "hedged", "line marks the value as unverified or absent"
        self.items.append(Citation(kind, value.strip(), line_no, status, via))

    # -- per-kind checks -------------------------------------------------------------
    def text(self, needle: str) -> tuple[str, str] | None:
        if not needle:
            return None
        where = self.ev.where(needle)
        if where:
            return "grounded", where
        if SPACE_RE.sub("", needle) in self.ev.blob_nospace:
            return "grounded", "evidence text (whitespace-insensitive)"
        return None

    def hash_full(self, h: str) -> tuple[str, str] | None:
        h = h.lower()
        if h in self.ev.hexes:
            return "grounded", self.ev.where(h) or "evidence text"
        if h in self.ev.digests:
            return "computed", self.ev.digests[h]
        return None

    def hash_abbrev(self, head: str, tail: str) -> tuple[str, str] | None:
        head, tail = head.lower(), tail.lower()
        for h in self.ev.hexes:
            if h.startswith(head) and h.endswith(tail):
                return "grounded", f"abbreviation of {h[:12]}… in evidence"
        for h, how in self.ev.digests.items():
            if h.startswith(head) and h.endswith(tail):
                return "computed", f"abbreviation of {how}"
        return None

    def moment(self, raw: str, found: list[Moment]) -> tuple[str, str] | None:
        literal = self.text(norm(raw))
        for mo in found:
            if mo.second:
                exact, shifted = mo.second in self.ev.seconds, mo.second in self.ev.tz_seconds
            elif mo.minute:
                exact, shifted = mo.minute in self.ev.minutes, mo.minute in self.ev.tz_minutes
            else:
                exact, shifted = mo.date in self.ev.dates, mo.date in self.ev.tz_dates
            if exact:
                return literal or ("grounded", "same date/time in another format")
            if shifted:
                return "computed", "evidence time shifted by 9 h (UTC↔KST)"
        return literal

    def clock(self, keys: tuple[str, str | None]) -> tuple[str, str] | None:
        minute, second = keys
        key = second or minute
        if key in self.ev.clocks:
            return "grounded", "time of day in evidence"
        if key in self.ev.tz_clocks:
            return "computed", "evidence time shifted by 9 h (UTC↔KST)"
        return None

    def quote(self, content: str) -> tuple[str, str] | None:
        n = norm(content).strip(" .,。!?;:")
        parts = [p.strip(" .,") for p in ELISION_RE.split(n) if len(p.strip(" .,")) >= 2]
        results = [self.text(p) for p in parts]
        if parts and all(results):
            return results[0]
        return None

    def number(self, m: re.Match[str]) -> tuple[str, str] | None:
        unit = SPACE_RE.sub("", m["u"]).lower()
        key = num_key(m["n"], m["f"])
        value = float(key)
        if unit[:1] in KO_UNIT and unit.endswith("원"):
            amount = str(int(value * KO_UNIT[unit[0]]))
            if amount in self.ev.numbers or f"{amount} 원" in self.ev.unit_numbers:
                return "grounded", "same amount in evidence"
        if f"{key} {unit}" in self.ev.unit_numbers:
            return "grounded", "same number and unit in evidence"
        if key in self.ev.numbers:
            return "grounded", "same number in evidence"
        power = SIZE_UNITS.get(unit)
        if power is not None:
            places = len((m["f"] or "").rstrip("0"))
            for size, label in self.ev.sizes:
                for base in (1000, 1024):
                    scaled = size / base ** power
                    if round(scaled, places) == value or (places == 0 and int(scaled) == value):
                        return "computed", f"size of {label}"
        return None

    def file(self, name: str) -> tuple[str, str] | None:
        n = norm(name)
        base = norm(re.split(r"[\\/]", name)[-1])
        if any(known == base or known.endswith(base) and not known[-len(base) - 1].isalnum() for known in self.ev.names):
            return "grounded", "evidence file name"
        return self.text(n) or self.text(base)

    # -- report walk -------------------------------------------------------------------
    def check(self, report: str) -> list[Citation]:
        in_fence = False
        person_cols: list[int] = []
        for no, raw in enumerate(report.splitlines(), 1):
            line = ZERO_WIDTH_RE.sub("", unicodedata.normalize("NFC", raw))
            if re.match(r"\s*(?:```|~~~)", line):
                in_fence = not in_fence
                continue
            meta = bool(META_LINE_RE.search(line))
            code_spans = [] if in_fence else [m.span() for m in re.finditer(r"`[^`\n]*`", line)]
            prose = (" " * len(line)) if in_fence else mask(line, code_spans)
            if not in_fence:
                self.quotes(prose, no, line)
            work = line
            for m in ABBREV_HEX_RE.finditer(work):
                head, tail = m.group(1) or "", m.group(2) or ""
                if len(head) + len(tail) < 6 or not re.search(r"\d", head + tail) or (head and len(head) < 6 and not tail):
                    continue
                self.add("hash", m.group(0), f"{head.lower()}…{tail.lower()}", no, line, self.hash_abbrev(head, tail))
                work = mask(work, [m.span()])
            for m in FULL_HEX_RE.finditer(work):
                h = m.group(0)
                if re.search(r"[a-fA-F]", h) and re.search(r"\d", h):
                    self.add("hash", h, h.lower(), no, line, self.hash_full(h))
                    work = mask(work, [m.span()])
            for m in WINPATH_RE.finditer(work):
                path = re.sub(r"(\.[A-Za-z0-9]{1,5})[가-힣]+$", r"\1", m.group(0))  # drop a trailing Korean particle
                self.add("file", path, norm(path), no, line, self.file(path))
                work = mask(work, [m.span()])
            for m in FILE_RE.finditer(work):
                name = m.group(0).strip()
                if norm(name) in self.own_names or norm(name) in self.plugin_names or re.fullmatch(r"[\d.]+", name.rsplit(".", 1)[0]):
                    continue
                self.add("file", name, norm(name), no, line, self.file(name))
                work = mask(work, [m.span()])
            for m, found in list(moments(work)):
                if not meta:
                    key = found[0].second or found[0].minute or found[0].date
                    self.add("date", m.group(0), key, no, line, self.moment(m.group(0), found))
                work = mask(work, [m.span()])
            for m in TIME_RE.finditer(work):
                c = clock(m)
                if c and not meta:
                    self.add("time", m.group(0), c[1] or c[0], no, line, self.clock(c))
                work = mask(work, [m.span()])
            if in_fence:
                continue
            rest = mask(work, code_spans)
            for m in NUMBER_RE.finditer(rest):
                key = f"{num_key(m['n'], m['f'])} {SPACE_RE.sub('', m['u']).lower()}"
                self.add("number", m.group(0), key, no, line, self.number(m))
            self.persons(rest, no, line, person_cols)
            person_cols[:] = self.table_person_columns(rest, person_cols)
            if not TOOL_ADVICE_RE.search(rest):
                taken: list[tuple[int, int]] = []
                for tool in sorted(TOOLS, key=len, reverse=True):
                    for m in re.finditer(r"(?<![A-Za-z])" + re.escape(tool) + r"(?![A-Za-z])", rest, re.I):
                        if any(a < m.end() and m.start() < b for a, b in taken):
                            continue
                        taken.append(m.span())
                        self.add("tool", tool, tool.lower(), no, line, self.text(norm(tool)))
        return self.items

    def quotes(self, prose: str, no: int, line: str) -> None:
        for rx in QUOTE_RES:
            for m in rx.finditer(prose):
                content = m.group(1)
                stripped = content.strip()
                # A span opening on punctuation is the gap between two quotes, not a quote.
                if not stripped or stripped[0] in ",.;:)(]}·-–—":
                    continue
                if len(re.findall(r"[A-Za-z가-힣]", stripped)) < 2 or len(stripped) < 4:
                    continue
                if FULL_HEX_RE.fullmatch(stripped) or FILE_RE.fullmatch(stripped) or DATE_RE.fullmatch(stripped):
                    continue
                if rx.pattern.startswith(("「", "『")) and LAW_TITLE_RE.search(stripped):
                    continue
                if DEFINED_TERM_AFTER_RE.match(prose[m.end():]) or prose[:m.start()].rstrip().endswith("이하"):
                    continue
                self.add("quote", stripped, norm(stripped), no, line, self.quote(stripped))

    def persons(self, rest: str, no: int, line: str, person_cols: list[int]) -> None:
        def check_name(tok: str) -> None:
            base = next((tok[: -len(p)] for p in PARTICLES if tok.endswith(p) and len(tok) - len(p) >= 3), tok)
            if {tok, base} & NAME_STOP:
                return
            if self.text(norm(base)) or self.text(norm(tok)):
                self.add("person", base, base, no, line, ("grounded", self.ev.where(norm(base)) or "evidence text"))
                return
            self.add("person", base, base, no, line, None)
        for m in NAME_TITLE_RE.finditer(rest):
            check_name(m.group(1))
        cells: list[str] = []
        stripped = rest.strip()
        if stripped.startswith("|") and person_cols:
            row = [c.strip() for c in stripped.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) or not c for c in row):
                cells = [row[i] for i in person_cols if i < len(row)]
        elif not stripped.startswith("|"):
            fm = re.match(r"\s*[-*•]?\s*\**([^:：*|]{1,20}?)\**\s*[:：]\s*(.+)", rest)
            if fm and PERSON_FIELD_RE.search(fm.group(1)):
                cells = [fm.group(2)]
        for cell in cells:
            for tok in NAME_TOKEN_RE.findall(cell):
                check_name(tok)

    @staticmethod
    def table_person_columns(rest: str, current: list[int]) -> list[int]:
        stripped = rest.strip()
        if not stripped.startswith("|"):
            return []
        row = [c.strip() for c in stripped.strip("|").split("|")]
        if any(PERSON_FIELD_RE.search(c) for c in row) and not any(NAME_TOKEN_RE.fullmatch(c) for c in row):
            return [i for i, c in enumerate(row) if PERSON_FIELD_RE.search(c)]
        return current


def mask(text: str, spans: Iterable[tuple[int, int]]) -> str:
    chars = list(text)
    for a, b in spans:
        chars[a:b] = " " * (b - a)
    return "".join(chars)


STATUSES = ("grounded", "computed", "labelled", "hedged", "unsupported")
KINDS = ("hash", "date", "time", "quote", "file", "number", "person", "tool")


def check_report(report_path: Path, evidence_paths: list[Path], max_hash_mb: int = DEFAULT_MAX_HASH_MB) -> dict:
    report = report_path.read_text(encoding="utf-8-sig", errors="replace")
    ev = load_evidence(evidence_paths, exclude=[report_path], max_hash_mb=max_hash_mb)
    items = Checker(ev, report_path.name).check(report)
    counts = {s: sum(1 for i in items if i.status == s) for s in STATUSES}
    by_kind = {k: sum(1 for i in items if i.kind == k and i.status == "unsupported") for k in KINDS}
    return {
        "report": str(report_path),
        "evidence": {"paths": [str(p) for p in evidence_paths], "files": ev.files, "not_hashed": ev.unhashed, "text_not_read": ev.unread},
        "cited": len(items),
        **counts,
        "unsupported_by_kind": {k: v for k, v in by_kind.items() if v},
        "items": [i.__dict__ for i in items],
    }


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def table(result: dict) -> str:
    rows = [("line", "kind", "status", "value", "via")]
    order = {s: n for n, s in enumerate(reversed(STATUSES))}
    for it in sorted(result["items"], key=lambda i: (order[i["status"]], i["line"])):
        value = it["value"] if len(it["value"]) <= 48 else it["value"][:45] + "..."
        via = it["via"] if len(it["via"]) <= 48 else it["via"][:45] + "..."
        rows.append((str(it["line"]), it["kind"], it["status"], value, via))
    widths = [max(_width(r[i]) for r in rows) for i in range(4)]
    lines = ["  ".join(c + " " * (widths[i] - _width(c)) if i < 4 else c for i, c in enumerate(r)).rstrip() for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths) + "  ---")
    summary = (f"cited {result['cited']} | grounded {result['grounded']} | computed {result['computed']} | "
               f"labelled {result['labelled']} | hedged {result['hedged']} | unsupported {result['unsupported']}")
    return "\n".join(lines + ["", summary])


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        getattr(stream, "reconfigure", lambda **_: None)(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Check that values cited in a report come from the evidence files")
    ap.add_argument("report", type=Path)
    ap.add_argument("--evidence", type=Path, nargs="+", required=True, help="evidence folders or files")
    ap.add_argument("--format", choices=("table", "json", "both"), default="both")
    ap.add_argument("--json", action="store_const", const="json", dest="format", help="same as --format json")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any cited value is unsupported")
    ap.add_argument("--max-hash-mb", type=int, default=DEFAULT_MAX_HASH_MB, help="hash evidence files up to this size")
    args = ap.parse_args(argv)
    if not args.report.is_file():
        print(f"report not found: {args.report}", file=sys.stderr)
        return 2
    missing = [str(p) for p in args.evidence if not p.exists()]
    if missing:
        print(f"evidence not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    result = check_report(args.report, args.evidence, args.max_hash_mb)
    if args.format in ("table", "both"):
        print(table(result))
    if args.format == "both":
        print()
    if args.format in ("json", "both"):
        print(json.dumps(result, ensure_ascii=False, indent=None if args.format == "json" else 1))
    return 1 if args.strict and result["unsupported"] else 0


if __name__ == "__main__":
    sys.exit(main())
