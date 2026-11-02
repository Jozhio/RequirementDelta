"""Narrow literal time changes; never infer a missing calendar anchor/year."""
from datetime import datetime
import re

_DURATION = re.compile(
    r'(?P<prefix>(?:应于|须于|必须于)收到(?P<event>[\u4e00-\u9fff]{1,20})后)'
    r'(?P<number>[1-9]\d{0,3})(?P<unit>日|天|小时)内(?P<action>提交|上传)'
)
_PARTIAL = re.compile(
    r'(?P<prefix>[\u4e00-\u9fff]{0,16}截止(?:时间为|为)?)'
    r'(?P<date>(?P<month>\d{1,2})月(?P<day>\d{1,2})日'
    r'(?:(?P<hour>\d{1,2}):(?P<minute>\d{2}))?)'
)
_UNSAFE = re.compile(r'不|无|未|仅|若|如果|除非|只有|所有|禁止|或者|或|之前|之后')


def bounded_time_change(a: str, b: str) -> tuple[str, str, str, str] | None:
    """Return kind, before, after, limitation ONLY for identical safe templates."""
    if _UNSAFE.search(a) or _UNSAFE.search(b):
        return None
    ma, mb = _DURATION.fullmatch(a), _DURATION.fullmatch(b)
    if ma and mb:
        if any(ma[k] != mb[k] for k in ('prefix', 'unit', 'action')):
            return None
        if ma['number'] == mb['number']:
            return None
        return ('DURATION', ma['number'] + ma['unit'], mb['number'] + mb['unit'],
                'Duration rule changed; reference-event date is unknown. No calendar deadline or user action inferred.')
    ma, mb = _PARTIAL.fullmatch(a), _PARTIAL.fullmatch(b)
    if ma and mb and ma['prefix'] == mb['prefix'] and ma['date'] != mb['date']:
        if bool(ma['hour']) != bool(mb['hour']):
            return None
        try:
            for m in (ma, mb):
                # Non-leap validation deliberately refuses Feb 29 without a year.
                datetime(2001, int(m['month']), int(m['day']), int(m['hour'] or 0), int(m['minute'] or 0))
        except ValueError:
            return None
        return ('DATE', ma['date'], mb['date'],
                'Literal month/day changed for the same event; year/timezone unknown. No absolute chronology inferred.')
    return None
