"""Detection view with source spans; never rewrite unrelated source text."""
import re
import unicodedata
from contextvars import ContextVar

_original_groups = ContextVar('pii_original_groups', default={})

def detection_view(text):
    chars, spans = [], []
    # Normalize a Hangul jamo/combining cluster together (NFD names included).
    clusters = re.finditer(r'[\u1100-\u11ff]+|.[\u0300-\u036f]*', text, re.S)
    for m in clusters:
        for ch in unicodedata.normalize('NFKC', m.group()):
            if unicodedata.category(ch) == 'Cf':
                continue
            if ch in '−‐‑‒–—﹘﹣': ch = '-'
            if ch.isdecimal(): ch = str(unicodedata.decimal(ch))
            chars.append(ch); spans.append((m.start(), m.end()))
    return ''.join(chars), spans

def original_value(value):
    return _original_groups.get().get(value, value)

class NormalizedPattern:
    def __init__(self, pattern): self.pattern = pattern
    def sub(self, callback, text):
        view, spans = detection_view(text)
        pieces, end = [], 0
        for m in self.pattern.finditer(view):
            start, stop = spans[m.start()][0], spans[m.end()-1][1]
            groups = {}
            for i in range(len(m.groups())+1):
                a,b=m.span(i)
                if a>=0 and b>a: groups[m.group(i)] = text[spans[a][0]:spans[b-1][1]]
            token = _original_groups.set(groups)
            try: replacement = callback(m) if callable(callback) else m.expand(callback)
            finally: _original_groups.reset(token)
            pieces.extend([text[end:start], text[start:stop] if replacement == m.group() else replacement])
            end=stop
        pieces.append(text[end:])
        return ''.join(pieces)
