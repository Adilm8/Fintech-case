"""CSV (UTF-8 BOM) and stdlib-only Unicode TrueType PDF export for payment check history."""

from __future__ import annotations

import csv
import io
import logging
import os
import struct
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from app.i18n import DEFAULT_LANG, Lang, t
from app.prod.schemas import Payment, PaymentScope

logger = logging.getLogger(__name__)

# Candidate system Unicode TrueType fonts supporting Cyrillic + Kazakh + Tenge.
_SYSTEM_TTF_CANDIDATES: tuple[str, ...] = (
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
)

_CSV_HEADERS: dict[Lang, tuple[str, ...]] = {
    "ru": (
        "ID платежа",
        "Дата",
        "Номер документа",
        "Статус",
        "Вердикт",
        "Балл риска",
        "Получатель",
        "БИН/ИИН",
        "ИИК",
        "БИК",
        "Сумма (KZT)",
        "Назначение платежа",
        "Заголовок проверки",
        "Причины и сигналы",
        "Рекомендация",
        "Согласование",
    ),
    "kk": (
        "Төлем ID",
        "Күні",
        "Құжат нөмірі",
        "Мәртебесі",
        "Қорытынды",
        "Тәуекел балы",
        "Алушы",
        "БСН/ЖСН",
        "ЖСК",
        "БСК",
        "Сома (KZT)",
        "Төлем мақсаты",
        "Тексеру тақырыбы",
        "Себептер мен белгілер",
        "Ұсыным",
        "Келісу",
    ),
    "en": (
        "Payment ID",
        "Date",
        "Document No",
        "Status",
        "Verdict",
        "Risk Score",
        "Recipient",
        "BIN/IIN",
        "IIK",
        "BIK",
        "Amount (KZT)",
        "Payment Purpose",
        "Check Headline",
        "Reasons & Signals",
        "Advice",
        "Approval",
    ),
}

_TRANSLIT_MAP: dict[str, str] = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "Yo",
    "Ж": "Zh", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "Kh", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Shch",
    "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "Ә": "A", "ә": "a", "Ғ": "Gh", "ғ": "gh", "Қ": "Q", "қ": "q",
    "Ң": "Ng", "ң": "ng", "Ө": "O", "ө": "o", "Ұ": "U", "ұ": "u",
    "Ү": "U", "ү": "u", "Һ": "H", "һ": "h", "І": "I", "і": "i",
    "₸": "KZT", "№": "No.", "«": '"', "»": '"', "—": "-", "–": "-", "·": "|", "×": "x",
}


def _transliterate_ascii(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch in _TRANSLIT_MAP:
            out.append(_TRANSLIT_MAP[ch])
        elif 32 <= ord(ch) <= 126:
            out.append(ch)
        elif ch in ("\n", "\r", "\t"):
            out.append(" ")
        else:
            out.append("?")
    return "".join(out)


def _format_amount_plain(amount_kzt: float) -> str:
    whole = round(amount_kzt)
    if abs(amount_kzt - whole) < 0.005:
        return f"{whole:,}".replace(",", " ")
    return f"{amount_kzt:,.2f}".replace(",", " ")


def _clean_cell(text: str) -> str:
    return " ".join(text.replace("\r", " ").replace("\n", " ").split())


def render_payments_csv(
    payments: list[Payment],
    *,
    lang: Lang = DEFAULT_LANG,
) -> bytes:
    """Serialize payments and their localized check breakdown to UTF-8 BOM CSV for Excel."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(_CSV_HEADERS[lang])

    for p in payments:
        doc_date = p.doc_date or p.created_at[:10]
        status_label = t(f"prod.status.{p.status}", lang)
        verdict_label = t(f"prod.verdict.{p.check.verdict}", lang)
        headline = p.check.headline or p.check.headline_ru
        reasons = "; ".join(
            _clean_cell(sig.reason or sig.reason_ru) for sig in p.check.signals
        )
        advice = _clean_cell(p.check.next_action.text or p.check.next_action.text_ru)
        approval_str = p.approval.status if p.approval is not None else ""
        if p.approval is not None and p.approval.director_comment:
            approval_str = f"{approval_str}: {_clean_cell(p.approval.director_comment)}"

        writer.writerow(
            [
                p.id,
                doc_date,
                p.doc_number,
                status_label,
                verdict_label,
                p.check.score,
                _clean_cell(p.request.recipient_name),
                p.request.recipient_bin,
                p.request.recipient_iik,
                p.request.recipient_bik,
                f"{p.request.amount_kzt:.2f}",
                _clean_cell(p.request.purpose),
                _clean_cell(headline),
                reasons,
                advice,
                approval_str,
            ]
        )

    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Minimal stdlib-only PDF 1.4 writer with embedded TrueType Unicode font
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ParsedTTF:
    path: str
    raw_len: int
    compressed_data: bytes
    units_per_em: int
    bbox: tuple[int, int, int, int]
    ascent: int
    descent: int
    cmap: dict[int, int]  # Unicode codepoint -> glyph ID
    widths_1000: tuple[int, ...]  # glyph ID -> width in 1000-unit glyph space
    default_width: int

    def glyph_id(self, ch: str) -> int:
        cp = ord(ch)
        gid = self.cmap.get(cp)
        if gid is not None:
            return gid
        # Fallback for tenge or rare symbols if missing in a Linux font
        if ch == "₸":
            return self.cmap.get(ord("T"), 0)
        return self.cmap.get(ord("?"), 0)

    def char_width_1000(self, gid: int) -> int:
        if 0 <= gid < len(self.widths_1000):
            return self.widths_1000[gid]
        return self.default_width

    def text_width(self, text: str, font_size: float) -> float:
        total = 0
        for ch in text:
            total += self.char_width_1000(self.glyph_id(ch))
        return total * font_size / 1000.0


def _parse_ttf_tables(data: bytes) -> dict[str, tuple[int, int]]:
    if len(data) < 12:
        raise ValueError("Invalid TTF header")
    num_tables = struct.unpack(">H", data[4:6])[0]
    tables: dict[str, tuple[int, int]] = {}
    for i in range(num_tables):
        off = 12 + i * 16
        if off + 16 > len(data):
            break
        tag = data[off : off + 4].decode("latin1")
        t_off, t_len = struct.unpack(">II", data[off + 8 : off + 16])
        tables[tag] = (t_off, t_len)
    return tables


def _parse_cmap(data: bytes, cmap_off: int) -> dict[int, int]:
    num_subtables = struct.unpack(">H", data[cmap_off + 2 : cmap_off + 4])[0]
    best_fmt4: int | None = None
    best_fmt12: int | None = None
    for i in range(num_subtables):
        rec = cmap_off + 4 + i * 8
        pid, eid, sub_off = struct.unpack(">HHI", data[rec : rec + 8])
        abs_off = cmap_off + sub_off
        fmt = struct.unpack(">H", data[abs_off : abs_off + 2])[0]
        if (pid, eid) in ((3, 10), (0, 4)) and fmt == 12:
            best_fmt12 = abs_off
        elif (pid, eid) in ((3, 1), (0, 3)) and fmt == 4:
            best_fmt4 = abs_off

    mapping: dict[int, int] = {}
    if best_fmt12 is not None:
        num_groups = struct.unpack(">I", data[best_fmt12 + 12 : best_fmt12 + 16])[0]
        pos = best_fmt12 + 16
        for _ in range(num_groups):
            start_cp, end_cp, start_gid = struct.unpack(">III", data[pos : pos + 12])
            pos += 12
            if start_cp > 0xFFFF:
                continue
            capped_end = min(end_cp, 0xFFFF)
            for cp in range(start_cp, capped_end + 1):
                gid = start_gid + (cp - start_cp)
                if 0 < gid <= 0xFFFF:
                    mapping[cp] = gid
        if mapping:
            return mapping

    if best_fmt4 is None:
        raise ValueError("No Unicode cmap subtable found")

    p = best_fmt4
    seg_count = struct.unpack(">H", data[p + 6 : p + 8])[0] // 2
    end_codes = struct.unpack(f">{seg_count}H", data[p + 14 : p + 14 + 2 * seg_count])
    start_off = p + 16 + 2 * seg_count
    start_codes = struct.unpack(f">{seg_count}H", data[start_off : start_off + 2 * seg_count])
    delta_off = start_off + 2 * seg_count
    id_deltas = struct.unpack(f">{seg_count}h", data[delta_off : delta_off + 2 * seg_count])
    ro_off = delta_off + 2 * seg_count
    range_offsets = struct.unpack(f">{seg_count}H", data[ro_off : ro_off + 2 * seg_count])

    for i in range(seg_count):
        s_code = start_codes[i]
        e_code = end_codes[i]
        delta = id_deltas[i]
        ro = range_offsets[i]
        if s_code == 0xFFFF and e_code == 0xFFFF:
            continue
        for cp in range(s_code, e_code + 1):
            if ro == 0:
                gid = (cp + delta) & 0xFFFF
            else:
                gid_addr = ro_off + i * 2 + ro + (cp - s_code) * 2
                if gid_addr + 2 > len(data):
                    continue
                raw_gid = struct.unpack(">H", data[gid_addr : gid_addr + 2])[0]
                gid = (raw_gid + delta) & 0xFFFF if raw_gid != 0 else 0
            if gid != 0:
                mapping[cp] = gid
    return mapping


@lru_cache(maxsize=4)
def _load_ttf(font_path: str) -> _ParsedTTF:
    raw = Path(font_path).read_bytes()
    tables = _parse_ttf_tables(raw)
    for required in ("head", "hhea", "hmtx", "cmap"):
        if required not in tables:
            raise ValueError(f"TTF missing table {required}")

    head_off, _ = tables["head"]
    units_per_em = struct.unpack(">H", raw[head_off + 18 : head_off + 20])[0]
    x_min, y_min, x_max, y_max = struct.unpack(">hhhh", raw[head_off + 36 : head_off + 44])
    scale = 1000.0 / units_per_em

    hhea_off, _ = tables["hhea"]
    ascent_raw, descent_raw = struct.unpack(">hh", raw[hhea_off + 4 : hhea_off + 8])
    num_hmetrics = struct.unpack(">H", raw[hhea_off + 34 : hhea_off + 36])[0]

    hmtx_off, _ = tables["hmtx"]
    widths: list[int] = []
    for i in range(num_hmetrics):
        adv = struct.unpack(">H", raw[hmtx_off + i * 4 : hmtx_off + i * 4 + 2])[0]
        widths.append(round(adv * scale))
    default_width = widths[-1] if widths else 500

    cmap_off, _ = tables["cmap"]
    cmap = _parse_cmap(raw, cmap_off)
    # Verify Cyrillic coverage
    if ord("А") not in cmap or ord("я") not in cmap:
        raise ValueError("Font lacks Cyrillic glyphs")

    return _ParsedTTF(
        path=font_path,
        raw_len=len(raw),
        compressed_data=zlib.compress(raw, level=6),
        units_per_em=units_per_em,
        bbox=(
            round(x_min * scale),
            round(y_min * scale),
            round(x_max * scale),
            round(y_max * scale),
        ),
        ascent=round(ascent_raw * scale),
        descent=round(descent_raw * scale),
        cmap=cmap,
        widths_1000=tuple(widths),
        default_width=default_width,
    )


def find_system_ttf(extra_paths: Iterable[str] | None = None) -> _ParsedTTF | None:
    """Locate and load the first available system TrueType font with Cyrillic coverage."""
    env_font = os.environ.get("SHIELD_PDF_FONT")
    candidates: list[str] = []
    if extra_paths is not None:
        candidates.extend(extra_paths)
    elif env_font is not None:
        if not env_font.strip():
            return None
        candidates.append(env_font.strip())
    else:
        candidates.extend(_SYSTEM_TTF_CANDIDATES)

    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            return _load_ttf(candidate)
        except (OSError, ValueError, struct.error):
            logger.debug("Skipping incompatible TTF font candidate: %s", candidate)
    return None


def _pdf_escape_ascii(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _SimplePdfDoc:
    """Lightweight A4 multi-page PDF 1.4 generator supporting embedded TTF or Helvetica fallback."""

    PAGE_W: float = 595.28
    PAGE_H: float = 841.89
    MARGIN_X: float = 40.0
    MARGIN_TOP: float = 42.0
    MARGIN_BOTTOM: float = 46.0

    def __init__(self, font: _ParsedTTF | None) -> None:
        self.font = font
        self.used_gids: dict[int, int] = {}  # gid -> unicode codepoint
        self.pages: list[list[str]] = []
        self.y: float = self.PAGE_H - self.MARGIN_TOP
        self.new_page()

    @property
    def content_width(self) -> float:
        return self.PAGE_W - 2 * self.MARGIN_X

    def new_page(self) -> None:
        self.pages.append([])
        self.y = self.PAGE_H - self.MARGIN_TOP

    def ensure_space(self, height: float) -> None:
        if self.y - height < self.MARGIN_BOTTOM:
            self.new_page()

    def _emit(self, op: str) -> None:
        self.pages[-1].append(op)

    def measure(self, text: str, font_size: float) -> float:
        if self.font is not None:
            return self.font.text_width(text, font_size)
        return len(_transliterate_ascii(text)) * font_size * 0.54

    def wrap_text(self, text: str, font_size: float, max_width: float) -> list[str]:
        cleaned = _clean_cell(text)
        if not cleaned:
            return []
        words = cleaned.split(" ")
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip() if current else word
            if self.measure(candidate, font_size) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            # Break overly long token (e.g. long IIK/reference)
            if self.measure(word, font_size) <= max_width:
                current = word
            else:
                chunk = ""
                for ch in word:
                    if self.measure(chunk + ch, font_size) <= max_width:
                        chunk += ch
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = ch
                current = chunk
        if current:
            lines.append(current)
        return lines

    def draw_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: tuple[float, float, float] | None = None,
        stroke: tuple[float, float, float] | None = None,
        line_width: float = 0.75,
    ) -> None:
        parts = ["q"]
        if fill is not None:
            parts.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
        if stroke is not None:
            parts.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG")
            parts.append(f"{line_width:.2f} w")
        parts.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re")
        if fill is not None and stroke is not None:
            parts.append("B")
        elif fill is not None:
            parts.append("f")
        else:
            parts.append("S")
        parts.append("Q")
        self._emit(" ".join(parts))

    def draw_line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        stroke: tuple[float, float, float] = (0.88, 0.88, 0.91),
        line_width: float = 0.6,
    ) -> None:
        self._emit(
            f"q {stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG "
            f"{line_width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S Q"
        )

    def draw_text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        size: float = 9.5,
        color: tuple[float, float, float] = (0.11, 0.11, 0.12),
    ) -> None:
        if not text:
            return
        rgb = f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg"
        if self.font is not None:
            gids: list[str] = []
            for ch in text:
                gid = self.font.glyph_id(ch)
                if gid not in self.used_gids:
                    self.used_gids[gid] = ord(ch)
                gids.append(f"{gid:04X}")
            hex_str = "".join(gids)
            self._emit(f"BT {rgb} /F1 {size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm <{hex_str}> Tj ET")
        else:
            ascii_txt = _pdf_escape_ascii(_transliterate_ascii(text))
            self._emit(f"BT {rgb} /F1 {size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({ascii_txt}) Tj ET")

    def _build_tounicode_cmap(self) -> bytes:
        entries = sorted(self.used_gids.items())
        lines = [
            "/CIDInit /ProcSet findresource begin",
            "12 dict begin",
            "begincmap",
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
            "/CMapName /Adobe-Identity-UCS def",
            "/CMapType 2 def",
            "1 begincodespacerange",
            "<0000> <FFFF>",
            "endcodespacerange",
        ]
        chunk_size = 100
        for i in range(0, len(entries), chunk_size):
            chunk = entries[i : i + chunk_size]
            lines.append(f"{len(chunk)} beginbfchar")
            for gid, cp in chunk:
                lines.append(f"<{gid:04X}> <{cp:04X}>")
            lines.append("endbfchar")
        lines.extend(
            [
                "endcmap",
                "CMapName currentdict /CMap defineresource pop",
                "end",
                "end",
            ]
        )
        return "\n".join(lines).encode("ascii")

    def build_bytes(self, *, footer_left: str, lang: Lang) -> bytes:
        total_pages = len(self.pages)
        # Append page footers to every page before finalizing streams
        for idx, ops in enumerate(self.pages, start=1):
            footer_right = t("prod.export.page", lang, page=idx, pages=total_pages)
            line_y = self.MARGIN_BOTTOM - 14.0
            text_y = self.MARGIN_BOTTOM - 26.0
            ops.append(
                f"q 0.880 0.880 0.910 RG 0.50 w "
                f"{self.MARGIN_X:.2f} {line_y:.2f} m "
                f"{self.PAGE_W - self.MARGIN_X:.2f} {line_y:.2f} l S Q"
            )
            # Emit footer text using active font
            saved_pages = self.pages
            self.pages = [ops]
            self.draw_text(self.MARGIN_X, text_y, footer_left, size=8.0, color=(0.45, 0.45, 0.48))
            rw = self.measure(footer_right, 8.0)
            self.draw_text(
                self.PAGE_W - self.MARGIN_X - rw,
                text_y,
                footer_right,
                size=8.0,
                color=(0.45, 0.45, 0.48),
            )
            self.pages = saved_pages

        objects: list[bytes] = []

        def add_obj(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        # Reserve slots 1 (Catalog) and 2 (Pages)
        add_obj(b"")
        add_obj(b"")

        if self.font is not None:
            ttf_stream_dict = (
                f"<< /Length {len(self.font.compressed_data)} "
                f"/Length1 {self.font.raw_len} /Filter /FlateDecode >>\nstream\n"
            ).encode("ascii")
            font_file_id = add_obj(ttf_stream_dict + self.font.compressed_data + b"\nendstream")

            bx0, by0, bx1, by1 = self.font.bbox
            font_desc_id = add_obj(
                (
                    f"<< /Type /FontDescriptor /FontName /ShieldUnicodeSans "
                    f"/Flags 32 /FontBBox [{bx0} {by0} {bx1} {by1}] "
                    f"/ItalicAngle 0 /Ascent {self.font.ascent} /Descent {self.font.descent} "
                    f"/CapHeight {self.font.ascent} /StemV 80 /FontFile2 {font_file_id} 0 R >>"
                ).encode("ascii")
            )

            w_parts: list[str] = []
            for gid in sorted(self.used_gids.keys()):
                w_parts.append(f"{gid} [{self.font.char_width_1000(gid)}]")
            w_array = " ".join(w_parts)

            cid_font_id = add_obj(
                (
                    f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /ShieldUnicodeSans "
                    f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
                    f"/FontDescriptor {font_desc_id} 0 R /DW {self.font.default_width} "
                    f"/W [{w_array}] /CIDToGIDMap /Identity >>"
                ).encode("ascii")
            )

            cmap_bytes = zlib.compress(self._build_tounicode_cmap(), level=6)
            tounicode_id = add_obj(
                f"<< /Length {len(cmap_bytes)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
                + cmap_bytes
                + b"\nendstream"
            )

            font_id = add_obj(
                (
                    f"<< /Type /Font /Subtype /Type0 /BaseFont /ShieldUnicodeSans "
                    f"/Encoding /Identity-H /DescendantFonts [{cid_font_id} 0 R] "
                    f"/ToUnicode {tounicode_id} 0 R >>"
                ).encode("ascii")
            )
        else:
            font_id = add_obj(
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
            )

        page_ids: list[int] = []
        for ops in self.pages:
            stream_raw = "\n".join(ops).encode("ascii")
            stream_z = zlib.compress(stream_raw, level=6)
            content_id = add_obj(
                f"<< /Length {len(stream_z)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
                + stream_z
                + b"\nendstream"
            )
            page_id = add_obj(
                (
                    f"<< /Type /Page /Parent 2 0 R "
                    f"/MediaBox [0 0 {self.PAGE_W:.2f} {self.PAGE_H:.2f}] "
                    f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                    f"/Contents {content_id} 0 R >>"
                ).encode("ascii")
            )
            page_ids.append(page_id)

        kids_str = " ".join(f"{pid} 0 R" for pid in page_ids)
        objects[1] = f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_ids)} >>".encode("ascii")
        objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"

        out = io.BytesIO()
        out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: list[int] = [0]
        for idx, body in enumerate(objects, start=1):
            offsets.append(out.tell())
            out.write(f"{idx} 0 obj\n".encode("ascii"))
            out.write(body)
            out.write(b"\nendobj\n")

        xref_offset = out.tell()
        out.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        out.write(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            out.write(f"{off:010d} 00000 n \n".encode("ascii"))

        out.write(
            (
                f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF\n"
            ).encode("ascii")
        )
        return out.getvalue()


_VERDICT_RGB: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    # (accent/text rgb, soft bg rgb)
    "green": ((0.00, 0.50, 0.34), (0.91, 0.97, 0.95)),
    "yellow": ((0.71, 0.43, 0.02), (0.99, 0.96, 0.88)),
    "red": ((0.78, 0.14, 0.14), (0.99, 0.93, 0.93)),
    "grey": ((0.35, 0.39, 0.45), (0.94, 0.95, 0.96)),
    "invalid": ((0.60, 0.10, 0.10), (0.98, 0.91, 0.91)),
}


def render_payments_pdf(
    payments: list[Payment],
    *,
    company_label: str,
    scope: PaymentScope,
    today: date,
    date_from: str | None = None,
    date_to: str | None = None,
    lang: Lang = DEFAULT_LANG,
    font_paths: Iterable[str] | None = None,
) -> bytes:
    """Render a multi-page A4 PDF report ('Что проверить перед подписью') per payment."""
    font = find_system_ttf(font_paths)
    doc = _SimplePdfDoc(font)

    x0 = doc.MARGIN_X
    cw = doc.content_width

    # Header banner box
    banner_h = 74.0 if font is not None else 90.0
    banner_bottom = doc.y - banner_h
    doc.draw_rect(
        x0,
        banner_bottom,
        cw,
        banner_h,
        fill=(0.91, 0.97, 0.95),
        stroke=(0.00, 0.67, 0.46),
        line_width=1.0,
    )
    doc.draw_rect(x0, banner_bottom, 5.0, banner_h, fill=(0.00, 0.67, 0.46))

    doc.draw_text(
        x0 + 14.0,
        doc.y - 22.0,
        t("prod.export.pdf_title", lang),
        size=15.0,
        color=(0.02, 0.30, 0.21),
    )
    doc.draw_text(
        x0 + 14.0,
        doc.y - 38.0,
        t("prod.export.pdf_subtitle", lang),
        size=9.0,
        color=(0.24, 0.36, 0.32),
    )

    period_text = (
        f"{date_from or '...'} — {date_to or '...'}"
        if (date_from or date_to)
        else "—"
    )
    meta_line = (
        f"{t('prod.export.company', lang)}: {company_label}  |  "
        f"{t('prod.export.generated', lang)}: {today.isoformat()}  |  "
        f"{t('prod.export.scope', lang)}: {scope}  |  "
        f"{t('prod.export.period', lang)}: {period_text}  |  "
        f"{t('prod.export.total', lang)}: {len(payments)}"
    )
    meta_wrapped = doc.wrap_text(meta_line, 8.2, cw - 24.0)
    my = doc.y - 53.0
    for mline in meta_wrapped[:2]:
        doc.draw_text(x0 + 14.0, my, mline, size=8.2, color=(0.15, 0.25, 0.22))
        my -= 11.0

    if font is None:
        doc.draw_text(
            x0 + 14.0,
            banner_bottom + 7.0,
            "Note: No Cyrillic TTF font found on host; text transliterated to ASCII.",
            size=7.8,
            color=(0.65, 0.35, 0.05),
        )

    doc.y = banner_bottom - 14.0

    if not payments:
        doc.draw_text(x0, doc.y - 12.0, t("prod.export.empty", lang), size=10.5)
        return doc.build_bytes(footer_left=f"BCC Business Shield · {company_label}", lang=lang)

    inner_x = x0 + 13.0
    inner_w = cw - 22.0

    for p in payments:
        verdict = p.check.verdict
        accent_rgb, bg_rgb = _VERDICT_RGB.get(verdict, ((0.35, 0.39, 0.45), (0.94, 0.95, 0.96)))
        verdict_label = t(f"prod.verdict.{verdict}", lang)
        status_label = t(f"prod.status.{p.status}", lang)
        doc_date = p.doc_date or p.created_at[:10]
        amount_str = f"{_format_amount_plain(p.request.amount_kzt)} ₸"

        title_text = f"[{verdict_label.upper()}]  {p.request.recipient_name}"
        title_lines = doc.wrap_text(title_text, 10.5, inner_w - 115.0)

        doc_part = f"№ {p.doc_number} · " if p.doc_number else ""
        req_line = (
            f"{doc_part}{doc_date} · {status_label} · "
            f"{p.request.recipient_bin} · {p.request.recipient_iik} · {p.request.recipient_bik}"
        )
        req_lines = doc.wrap_text(req_line, 8.2, inner_w)

        purpose_lines = (
            doc.wrap_text(f"{t('prod.export.purpose', lang)}: {p.request.purpose}", 8.5, inner_w)
            if p.request.purpose
            else []
        )

        headline = p.check.headline or p.check.headline_ru
        headline_lines = doc.wrap_text(headline, 9.2, inner_w)

        reason_lines: list[str] = []
        if p.check.signals:
            for sig in p.check.signals:
                reason_txt = sig.reason or sig.reason_ru
                wrapped = doc.wrap_text(f"• {reason_txt}", 8.5, inner_w - 6.0)
                reason_lines.extend(wrapped)
        else:
            reason_lines = doc.wrap_text(t("prod.export.no_signals", lang), 8.5, inner_w - 6.0)

        advice_txt = p.check.next_action.text or p.check.next_action.text_ru
        advice_lines = doc.wrap_text(
            f"{t('prod.export.advice', lang)}: {advice_txt}",
            8.7,
            inner_w - 8.0,
        )

        approval_lines: list[str] = []
        if p.approval is not None:
            apr_text = f"{t('prod.export.approval', lang)}: {p.approval.status}"
            if p.approval.director_comment:
                apr_text += f" — {p.approval.director_comment}"
            approval_lines = doc.wrap_text(apr_text, 8.2, inner_w)

        # Precompute total card height so a payment card never splits mid-block
        card_h = (
            12.0  # top pad
            + max(1, len(title_lines)) * 13.5
            + len(req_lines) * 11.0
            + (len(purpose_lines) * 11.5 + 3.0 if purpose_lines else 0.0)
            + 6.0
            + len(headline_lines) * 12.0
            + 12.0  # reasons label
            + len(reason_lines) * 11.5
            + 8.0
            + len(advice_lines) * 11.8 + 10.0  # advice box
            + (len(approval_lines) * 11.0 + 4.0 if approval_lines else 0.0)
            + 10.0  # bottom pad
        )
        doc.ensure_space(card_h + 10.0)

        card_top = doc.y
        card_bottom = card_top - card_h

        # Outer card box + left verdict stripe
        doc.draw_rect(
            x0,
            card_bottom,
            cw,
            card_h,
            fill=(1.0, 1.0, 1.0),
            stroke=(0.86, 0.86, 0.89),
            line_width=0.7,
        )
        doc.draw_rect(x0, card_bottom, 4.5, card_h, fill=accent_rgb)

        cur_y = card_top - 16.0
        # Amount on right of first row
        amt_w = doc.measure(amount_str, 10.5)
        doc.draw_text(
            x0 + cw - 10.0 - amt_w,
            cur_y,
            amount_str,
            size=10.5,
            color=(0.08, 0.08, 0.10),
        )

        for idx, tline in enumerate(title_lines):
            doc.draw_text(
                inner_x,
                cur_y,
                tline,
                size=10.5,
                color=accent_rgb if idx == 0 else (0.11, 0.11, 0.12),
            )
            cur_y -= 13.5

        for rline in req_lines:
            doc.draw_text(inner_x, cur_y, rline, size=8.2, color=(0.40, 0.40, 0.44))
            cur_y -= 11.0

        if purpose_lines:
            cur_y -= 3.0
            for pline in purpose_lines:
                doc.draw_text(inner_x, cur_y, pline, size=8.5, color=(0.24, 0.24, 0.28))
                cur_y -= 11.5

        cur_y -= 3.0
        doc.draw_line(inner_x, cur_y + 4.0, x0 + cw - 10.0, cur_y + 4.0)
        cur_y -= 3.0

        for hline in headline_lines:
            doc.draw_text(inner_x, cur_y, hline, size=9.2, color=accent_rgb)
            cur_y -= 12.0

        doc.draw_text(
            inner_x,
            cur_y,
            f"{t('prod.export.reasons', lang)}:",
            size=8.3,
            color=(0.35, 0.35, 0.39),
        )
        cur_y -= 12.0
        for rs_line in reason_lines:
            doc.draw_text(inner_x + 4.0, cur_y, rs_line, size=8.5, color=(0.14, 0.14, 0.16))
            cur_y -= 11.5

        cur_y -= 4.0
        advice_box_h = len(advice_lines) * 11.8 + 10.0
        advice_box_bottom = cur_y - advice_box_h + 8.0
        doc.draw_rect(
            inner_x,
            advice_box_bottom,
            inner_w,
            advice_box_h,
            fill=bg_rgb,
            stroke=accent_rgb,
            line_width=0.45,
        )
        ay = cur_y - 3.5
        for aline in advice_lines:
            doc.draw_text(inner_x + 5.0, ay, aline, size=8.7, color=(0.10, 0.10, 0.12))
            ay -= 11.8
        cur_y = advice_box_bottom - 10.0

        if approval_lines:
            cur_y -= 2.0
            for apline in approval_lines:
                doc.draw_text(inner_x, cur_y, apline, size=8.2, color=(0.35, 0.35, 0.40))
                cur_y -= 11.0

        doc.y = card_bottom - 10.0

    return doc.build_bytes(footer_left=f"BCC Business Shield · {company_label}", lang=lang)
