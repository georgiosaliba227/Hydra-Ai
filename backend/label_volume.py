"""Metric label evidence only; never a verified measurement or serving inference."""
from decimal import Decimal, InvalidOperation
import re

_METRIC = re.compile(r"(?<![\w.,+\-])(\d{1,4}(?:\.\d{1,4})?)\s*(ml|millilit(?:er|re)s?|l|lit(?:er|re)s?)\b", re.I)
_NET = re.compile(r"\b(?:net\s*(?:contents?|volume)?|(?:bottle|container|can)\s*(?:size|volume))\s*:?\s*", re.I)
_SERVING = re.compile(r"\b(?:servings?|portions?|per|nutrition(?:al)?)\b", re.I)


def label_capacity_ml(text: str | None) -> int | None:
    """Prefer explicit net/container text; reject serving and conflicting sizes.

    No fluid-ounce conversion: US/Imperial ambiguity is not resolved by an
    unlabeled 'fl oz'. The mL member of a dual-unit label is usable directly.
    """
    if not text:
        return None
    sections=[]
    markers=list(_NET.finditer(text))
    if markers:
        for index,marker in enumerate(markers):
            section=text[marker.end():markers[index+1].start() if index+1<len(markers) else len(text)]
            sections.append(_SERVING.split(section,maxsplit=1)[0])
    elif _SERVING.search(text):
        return None
    else:
        sections=[text]
    sizes=set()
    for section in sections:
        for match in _METRIC.finditer(section):
            try:
                value=Decimal(match[1])*(1 if match[2].lower().startswith('m') else 1000)
            except InvalidOperation:
                return None
            if value!=value.to_integral_value() or not 1<=value<=5000:
                return None
            sizes.add(int(value))
    return sizes.pop() if len(sizes)==1 else None
