"""US LayoutMsgGlyphsPage semantics; measurement is not an edit permission.

The constants follow the pinned msg.c implementation and were checked against
real event149/156 calls. Source tables supply advances; no display-wide box
budget or variable substitution is invented by this module.
"""
from __future__ import annotations

import struct
from .errors import KhcomError

END, NEWLINE, HIGHLIGHT, PLAIN = 0, 10, 0x4079, 0x4000
SPECIAL_GLYPHS = {0xE000: 25, 0x2191: 10, 0x2193: 11, 0x2190: 12,
                  0x2192: 13, 0x300C: 1, 0x300D: 2, 0x300E: 3,
                  0x300F: 4, 0x203B: 6, 0x266A: 18, 0x2642: 8,
                  0x2640: 9, 0x2605: 21, 0x25A0: 17}


def measure_event_pages(encoded: bytes, widths: list[int], *, origin: tuple[int, int],
                        alternate_palette: int | None, glyph_bounds: list | None = None) -> dict:
    """Return the exact page/advance sequence, rejecting undefined encodings.

    The renderer wraps *after* a glyph takes X past 155, advances 12 pixels
    per line and returns a new page after Y exceeds 24. Palette state resets
    on every page, as in the real consumer. Actual box clipping is separate.
    """
    if (not isinstance(encoded, bytes) or not 2 <= len(encoded) <= 128 * 1024
            or len(encoded) % 2):
        raise KhcomError("event_code_units", "Texto de evento exige unidades u16le completas e orçamento editorial.")
    if (not isinstance(widths, list) or len(widths) != 256
            or any(type(v) is not int or not 0 <= v <= 32767 for v in widths)):
        raise KhcomError("event_metrics", "Métricas precisam ser 256 larguras não negativas após conversão s16.")
    if (not isinstance(origin, (tuple, list)) or len(origin) != 2 or any(type(v) is not int for v in origin)
            or alternate_palette not in (None, 3, 5)):
        raise KhcomError("event_context", "Origem/paleta fora do contrato do consumidor de eventos US.")
    if glyph_bounds is not None:
        if (not isinstance(glyph_bounds, list) or len(glyph_bounds) != 256
                or any(bounds is not None and (not isinstance(bounds, list) or len(bounds) != 4
                    or any(type(v) is not int for v in bounds)
                    or not 0 <= bounds[0] < bounds[2] <= 16
                    or not 0 <= bounds[1] < bounds[3] <= 16) for bounds in glyph_bounds)):
            raise KhcomError("event_metrics", "Bounds devem acompanhar os 256 glifos de 16×16.")
    codes = struct.unpack(f"<{len(encoded)//2}H", encoded)
    if codes[-1] != END or END in codes[:-1]:
        raise KhcomError("event_terminator", "A linha exige um único terminador final.")
    pages, cursor = [], 0
    while True:
        start, x, y, highlight = cursor, 0, 0, False
        glyphs, controls = [], []
        while codes[cursor] != END:
            # Even NL writes the current sprite's position before branching.
            if len(glyphs) >= 128:
                raise KhcomError("event_glyph_capacity", "Página excede as 128 estruturas alocadas pelo renderer.")
            for marker, state, name in ((HIGHLIGHT, True, "HIGHLIGHT"), (PLAIN, False, "PLAIN")):
                if codes[cursor] == marker:
                    controls.append({"name": name, "code_unit": cursor})
                    highlight = state
                    cursor += 1
            code = codes[cursor]
            if code == END:
                raise KhcomError("terminal_palette_control", "Controle de paleta consumiria END e a cauda da reserva.", code_unit=cursor)
            if code in (HIGHLIGHT, PLAIN):
                raise KhcomError("event_palette_sequence", "Ordem/repetição de controles produziria glifo de fallback.", code_unit=cursor)
            if code == NEWLINE:
                controls.append({"name": "NL", "code_unit": cursor})
                x, y = 0, y + 12
            else:
                glyph = code if 32 <= code <= 255 else SPECIAL_GLYPHS.get(code)
                if glyph is None:
                    raise KhcomError("event_unmapped_glyph", "Código produziria glifo de fallback no consumidor US.", code_unit=cursor, value=code)
                if highlight and alternate_palette is None:
                    raise KhcomError("event_alternate_palette", "Esta ocorrência não inicializa paleta de destaque.", code_unit=cursor)
                record = {"code_unit": cursor, "code": code, "glyph_index": glyph,
                          "x": origin[0] + x, "y": origin[1] + y, "advance": widths[glyph],
                          "palette": alternate_palette if highlight else 0,
                          "kind": "space" if glyph == 32 else "latin" if 32 <= code <= 255 else "icon"}
                if glyph_bounds is not None:
                    bounds = glyph_bounds[glyph]
                    record["ink_bounds"] = None if bounds is None or glyph == 32 else [
                        record["x"] + bounds[0], record["y"] + bounds[1],
                        record["x"] + bounds[2], record["y"] + bounds[3]]
                glyphs.append(record)
                x += widths[glyph]
                if x > 155:
                    x, y = 0, y + 12
            cursor += 1
            if y > 24:
                break
        next_unit = cursor if y > 24 else None
        pages.append({"source_start_code_unit": start, "next_code_unit": next_unit,
                      "glyph_count": len(glyphs), "glyphs": glyphs, "controls": controls,
                      "palette_resets_at_page_start": True})
        if next_unit is None:
            break
    return {"renderer": "LayoutMsgGlyphsPage_US", "pages": pages, "page_count": len(pages),
            "total_glyphs": sum(page["glyph_count"] for page in pages),
            "origin": list(origin), "alternate_palette": alternate_palette,
            "dynamic_values": {"kind": "none", "scope": "literal input after any caller-side formatting"},
            "box_clipping_verified": False, "runtime_verified": False,
            "limitations": ["Advance wrapping is reproduced; actual clipping/portrait overlap needs an occurrence contract.",
                            "Caller-side substitutions and other renderers remain outside this measurement."]}
