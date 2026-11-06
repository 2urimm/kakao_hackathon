"""채팅 문장에서 예약 날짜/시간/인원 뽑기 (해커톤용 간단 규칙 기반).

  "내일 저녁 7시"      → 내일 19:00
  "11월 8일 7시 반"    → 11/8 19:30
  "금요일 6시 4명"     → 이번 금요일 18:00, 4명
  "다음주 토요일 12시" → 다음 주 토요일 12:00
  "19:30"             → 19:30

시간대 말(오전/오후/저녁...)이 없는 1~9시는 저녁(+12시간)으로 본다. 식당 예약이라 "7시" = 19시가 자연스러워서.
"""
import re
from datetime import date, datetime, time, timedelta

_KO_NUM = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9,
           "열": 10, "열한": 11, "열두": 12}
_NUM = r"(\d{1,2}|열한|열두|다섯|여섯|일곱|여덟|아홉|한|두|세|네|열)"
_WEEKDAYS = "월화수목금토일"

_RE_MONTH_DAY = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_RE_DAY = re.compile(r"(?<![\d월])(\d{1,2})\s*일(?!\s*(?:뒤|후|전|간|동안))")
_RE_WEEKDAY = re.compile(r"(다음\s*주|담주|이번\s*주)?\s*([월화수목금토일])요일")
_RE_HHMM = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")
_RE_HOUR = re.compile(rf"(오전|오후|아침|점심|낮|저녁|밤|새벽)?\s*{_NUM}\s*시(?!간)\s*(반|(\d{{1,2}})\s*분)?")
_RE_PARTY = re.compile(rf"{_NUM}\s*명|(\d{{1,2}})\s*인(?!분|원)")


def _num(s: str) -> int:
    return int(s) if s.isdigit() else _KO_NUM[s]


def parse_date(text: str, base: date) -> date | None:
    """text 에 날짜 표현이 있으면 그 날짜 (base = 그 말을 한 날)."""
    if m := _RE_MONTH_DAY.search(text):
        month, day = int(m[1]), int(m[2])
        for year in (base.year, base.year + 1):
            try:
                d = date(year, month, day)
            except ValueError:
                return None
            if d >= base:
                return d
        return None
    for word, add in (("글피", 3), ("모레", 2), ("내일", 1), ("오늘", 0), ("오늘밤", 0)):
        if word in text:
            return base + timedelta(days=add)
    if m := _RE_WEEKDAY.search(text):
        wd = _WEEKDAYS.index(m[2])
        if m[1] and m[1].replace(" ", "") in ("다음주", "담주"):
            return base - timedelta(days=base.weekday()) + timedelta(days=7 + wd)
        return base + timedelta(days=(wd - base.weekday()) % 7)
    if m := _RE_DAY.search(text):
        day = int(m[1])
        y, mo = base.year, base.month
        for _ in range(2):
            try:
                d = date(y, mo, day)
                if d >= base:
                    return d
            except ValueError:
                pass
            y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    return None


def parse_time(text: str) -> time | None:
    if m := _RE_HHMM.search(text):
        h, mi = int(m[1]), int(m[2])
        return time(h, mi) if h < 24 and mi < 60 else None
    if m := _RE_HOUR.search(text):
        ampm, h = m[1], _num(m[2])
        mi = 30 if m[3] == "반" else int(m[4] or 0)
        if ampm in ("오후", "저녁", "밤") and h < 12:
            h += 12
        elif ampm in ("점심", "낮") and h < 6:
            h += 12
        elif ampm is None and 1 <= h <= 9:
            h += 12
        if h == 24:
            h = 0
        return time(h, mi) if h < 24 and mi < 60 else None
    return None


def parse_party(text: str) -> int | None:
    if m := _RE_PARTY.search(text):
        n = _num(m[1]) if m[1] else int(m[2])
        return n if 1 <= n <= 100 else None
    return None


def parse_when(messages: list[tuple[str, datetime]], now: datetime) -> tuple[datetime | None, int | None]:
    """messages: (내용, 보낸 시각) 최신 → 오래된 순. 가장 최근에 말한 시간/날짜/인원을 쓴다.
    시간을 못 찾으면 (None, 인원). 날짜가 없으면 오늘, 이미 지난 시간이면 내일."""
    t = d = party = None
    for text, sent_at in messages:
        if t is None:
            t = parse_time(text)
        if d is None:
            d = parse_date(text, sent_at.date())
        if party is None:
            party = parse_party(text)
    if t is None:
        return None, party
    if d is not None:
        return datetime.combine(d, t), party
    when = datetime.combine(now.date(), t)
    if when <= now:
        when += timedelta(days=1)
    return when, party
