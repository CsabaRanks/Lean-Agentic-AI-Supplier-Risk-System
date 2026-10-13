"""Presentation-only translations. Never translate persisted values or user-authored prose."""

from __future__ import annotations

import json
import re
from datetime import datetime
from functools import lru_cache
from numbers import Number
from pathlib import Path

import pandas as pd
import streamlit as st
from pydantic import ValidationError


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / "locales/messages.json").read_text(encoding="utf-8"))


def browser_language(locale: str | None) -> str:
    return "de" if locale and locale.lower().split("-")[0].split("_")[0] == "de" else "en"


def language() -> str:
    return st.session_state.get("language", "en")


def tr(message, **values) -> str:
    """Exact catalog lookup; unknown external content remains untouched."""
    if message is None:
        return "—"
    message = str(message)
    translated = catalog().get(message, {}).get(language(), message)
    return translated.format(**values) if values else translated


def number(value, spec: str = ",.2f") -> str:
    if value is None or pd.isna(value):
        return "—"
    if isinstance(value, bool):
        return tr("Yes" if value else "No")
    rendered = format(value, spec)
    if language() == "de":
        rendered = rendered.translate(str.maketrans(",.", ".,"))
        rendered = rendered.replace("%", " %")
    return rendered


def date(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    # Keep the recorded timezone explicit rather than silently converting it.
    pattern = "%d.%m.%Y %H:%M:%S" if language() == "de" else "%m/%d/%Y %H:%M:%S"
    return dt.strftime(pattern) + (f" UTC{dt:%z}" if dt.tzinfo else "")


def display_value(item) -> str:
    if item is None:
        return "—"
    if isinstance(item, bool):
        return tr("Yes" if item else "No")
    if isinstance(item, Number):
        return number(item, ",g")
    return tr(item)


def message(text) -> str:
    """Translate known generated backend messages without changing backend contracts.

    Templates use named slots, anchored to the complete message. Unknown provider
    responses are reported via error_text, never heuristically machine-translated.
    """
    text = str(text)
    if text in catalog():
        return tr(text)
    for pattern, translations in message_patterns():
        match = pattern.fullmatch(text)
        if match:
            return translations[language()].format(
                **{k: message_slot(k, v) for k, v in match.groupdict().items()}
            )
    return text


@lru_cache(maxsize=1)
def message_patterns():
    """Compile generated-message templates once, not once per table cell."""
    patterns = []
    for source, translations in catalog().items():
        fields = re.findall(r"\{([a-zA-Z][a-zA-Z0-9_]*)\}", source)
        if not fields or len(set(fields)) != len(fields):
            continue
        pattern = re.escape(source)
        for field in fields:
            pattern = pattern.replace(re.escape("{" + field + "}"), "(?P<" + field + ">.*?)")
        patterns.append((re.compile(pattern, re.DOTALL), translations))
    return patterns


def error_text(error) -> str:
    """Readable, localized validation errors; external diagnostics stay available as codes."""
    if isinstance(error, ValidationError):
        parts = []
        for item in error.errors(include_url=False):
            detail = item["msg"].removeprefix("Value error, ")
            translated = message(detail)
            if translated == detail and detail not in catalog():
                translated = tr("Invalid value ({code}).", code=item["type"])
            parts.append(f"{tr('.'.join(str(p) for p in item['loc']))}: {translated}")
        return "; ".join(parts)
    text = str(error)
    translated = message(text)
    if translated != text or text in catalog():
        return translated
    return tr("The operation could not be completed. Check the input and configuration.")


# Only application-owned columns are translated. Names, notes, reasons, comments,
# explanations and other user/provider text are deliberately absent.
TRANSLATED_COLUMNS = {
    "criterion",
    "factor",
    "view",
    "class",
    "risk_class",
    "performance_class",
    "origin",
    "kind",
    "expects",
    "level",
    "priority",
    "action",
    "owner",
    "review_cycle",
    "trigger",
    "rule",
    "status",
    "weights",
    "current",
    "proposed",
    "field",
    "main_drivers",
    "reasons",
}


def table(data, *, original_text=False, number_formats=None):
    """Style numbers/dates without coercing the dataframe's numeric sort values."""
    frame = data.data if hasattr(data, "data") and isinstance(data.data, pd.DataFrame) else data
    if not isinstance(frame, pd.DataFrame):
        return data
    styled = data if hasattr(data, "format") and not isinstance(data, pd.DataFrame) else frame.style
    formats = {}
    for col in frame.columns:
        if pd.api.types.is_numeric_dtype(frame[col]) and not pd.api.types.is_bool_dtype(frame[col]):
            spec = (number_formats or {}).get(col) or (
                ",.0f" if pd.api.types.is_integer_dtype(frame[col]) else ",.2f"
            )
            formats[col] = lambda x, s=spec: number(x, s)
        elif col in {"time", "recorded_at", "created_at"}:
            formats[col] = date
        elif col in TRANSLATED_COLUMNS and (
            not original_text or col in {"priority", "view", "criterion"}
        ):
            formats[col] = lambda x, c=col: cell_text(c, x)
    return styled.format(formats, na_rep="—")


def columns(frame, config=None):
    """Translated labels with stable column IDs (also used for editable tables)."""
    config = dict(config or {})
    for name in frame.columns:
        if name not in config:
            config[name] = tr(str(name))
        elif isinstance(config[name], str):
            config[name] = tr(config[name])
    return config


def dataframe(data, **kwargs):
    frame = data.data if hasattr(data, "data") and isinstance(data.data, pd.DataFrame) else data
    original_text = kwargs.pop("original_text", False)
    config = columns(frame, kwargs.pop("column_config", None))
    # Styler display values supply locale formatting. NumberColumn's format would
    # override these using the browser locale, which need not match the UI switch.
    number_formats = {}
    for key, entry in config.items():
        if isinstance(entry, dict):
            entry = dict(entry)
            typ = dict(entry.get("type_config") or {})
            if typ.get("type") == "number":
                display_format = typ.pop("format", None)
                if display_format == "percent":
                    number_formats[key] = ".0%"
                elif display_format and re.fullmatch(r"%\.\d+f", display_format):
                    number_formats[key] = "," + display_format[1:]
            entry["type_config"] = typ
            config[key] = entry
    return st.dataframe(
        table(data, original_text=original_text, number_formats=number_formats),
        column_config=config,
        **kwargs,
    )


def date_axis():
    return {"de": "%d.%m.%Y", "en": "%m/%d/%Y"}[language()]


def parse_input(text):
    """Accept a decimal comma in German; keep canonical CSV tokens valid in both languages."""
    if language() == "de" and re.fullmatch(r"[+-]?\d+,\d+", text.strip()):
        return text.replace(",", ".")
    return text


def data_editor(data, **kwargs):
    # Dynamic-row editors include column labels in their widget identity. Keep
    # their latest returned draft as the new base across a locale change. This
    # uses only the public editor return value, not private widget state.
    draft = None
    if kwargs.get("num_rows") == "dynamic":
        drafts = st.session_state.setdefault("editor_locale_drafts", {})
        key = kwargs["key"]
        draft = drafts.setdefault(key, {"language": language(), "base": data, "draft": data})
        if draft["language"] != language():
            draft["base"] = draft["draft"].copy(deep=True)
            draft["language"] = language()
        data = draft["base"]
    edited = st.data_editor(
        data, column_config=columns(data, kwargs.pop("column_config", None)), **kwargs
    )
    if draft is not None:
        draft["draft"] = edited.copy(deep=True)
    return edited


def option_labels(options, formatter=tr):
    """Freeze display labels for a render; callbacks need no session context."""
    rendered = {option: formatter(option) for option in options}
    return rendered.__getitem__


def message_slot(key, text):
    if key in {"reason", "scope", "sid", "model", "setting", "provider", "providers", "code"}:
        return text
    if key == "error":
        return error_text(text)
    if key == "criteria":
        return ", ".join(tr(x.strip()) for x in text.split(","))
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?%?", text):
        return text.replace(".", ",").replace("%", " %") if language() == "de" else text
    return message(text)


def cell_text(column, item):
    if item is None:
        return "—"
    if column == "main_drivers":
        return ", ".join(message(part) for part in str(item).split(", "))
    if column == "reasons":
        return "; ".join(message(part) for part in str(item).split("; "))
    return message(item)


def localized_chart(chart, **kwargs):
    """Vega-Lite's supported locale configuration; no browser DOM changes."""
    separators = {
        "de": {"decimal": ",", "thousands": "."},
        "en": {"decimal": ".", "thousands": ","},
    }
    locale = {"number": {**separators[language()], "grouping": [3], "currency": ["", ""]}}
    return st.altair_chart(chart.configure(locale=locale), **kwargs)


def selectbox(label, options, *, key, _parent=None, **kwargs):
    """Remount translated option labels while preserving the canonical selection.

    Streamlit 1.65 retains a selectbox's old selected display text when only its
    format_func changes. A language-specific widget key avoids that frontend
    cache; the separate canonical session value never changes with the locale.
    """
    options = list(options)
    widget_key = f"{key}__{language()}"
    current = st.session_state.get(key)
    if widget_key not in st.session_state and current in options:
        st.session_state[widget_key] = current
    selected = (_parent or st).selectbox(label, options, key=widget_key, **kwargs)
    st.session_state[key] = selected
    return selected


def multiselect(label, options, *, key, _parent=None, **kwargs):
    options = list(options)
    widget_key = f"{key}__{language()}"
    if widget_key not in st.session_state and key in st.session_state:
        st.session_state[widget_key] = [x for x in st.session_state[key] if x in options]
    selected = (_parent or st).multiselect(label, options, key=widget_key, **kwargs)
    st.session_state[key] = selected
    return selected
