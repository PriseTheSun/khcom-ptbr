"""Authored accent recipes; all base pixels must come from the user's ROM.

No original bitmap is embedded here. This is the experimentally verified V2
recipe, with native 8px typography still awaiting human review.
"""

import unicodedata

from .errors import KhcomError

REQUIRED = "áéíóúâêôãõçàÁÉÍÓÚÂÊÔÃÕÇÀ"
CAPITAL_ROWS = {
    "A": (1, 2, 4, 5, 6),
    "E": (1, 2, 3, 5, 6),
    "I": (1, 2, 3, 5, 6),
    "O": (1, 2, 3, 5, 6),
    "U": (1, 2, 3, 5, 6),
}
MARKS = {"\u0301": "acute", "\u0300": "grave", "\u0302": "circumflex",
         "\u0303": "tilde", "\u0327": "cedilla"}


def _generate8(character, base_rows, base_advance):
    """Return rows, advance and source-derived recipe metadata for one glyph.

    All coordinates are zero-based, X increases rightwards and Y downwards.
    Values 0/1/2/3 retain background/foreground/shadow/edge semantics. The
    caller owns encoding, original-glyph identity and the actual width table.
    """
    if not isinstance(character, str) or character not in REQUIRED or len(character) != 1:
        raise KhcomError("credits_recipe", "exactly one required NFC accented character is needed")
    decomposed = unicodedata.normalize("NFD", character)
    if len(decomposed) != 2 or decomposed[1] not in MARKS:
        raise KhcomError("credits_recipe", "unsupported accent decomposition")
    base, mark = decomposed[0], MARKS[decomposed[1]]
    if type(base_advance) is not int or not 3 <= base_advance <= 8:
        raise KhcomError("credits_recipe", "base advance must be an explicit supported width 3..8")
    if len(base_rows) != 8 or any(len(row) != 8 for row in base_rows):
        raise KhcomError("credits_recipe", "base glyph must be 8x8")
    if any(type(value) is not int or value not in range(4) for row in base_rows for value in row):
        raise KhcomError("credits_recipe", "base glyph contains non-2bpp values")
    original = [list(row) for row in base_rows]
    if any(value for row in original for value in row[base_advance:]):
        raise KhcomError("credits_recipe", "base glyph has pixels outside its declared draw width")
    result = [[0] * 8 for _ in range(8)]
    advance = max(base_advance, 5) if mark == "tilde" else base_advance
    row_map = []
    decisions = []
    ink = []
    edge = []
    shadow_rows = set()

    if mark == "cedilla":
        # Both C and c retain their original body rows, raised by one pixel.
        # The old baseline becomes Y5; the tail is foreground at Y6 and Y7.
        row_map = [(source, source - 1) for source in range(1, 8)]
        for source, target in row_map:
            result[target] = original[source].copy()
        ink = [(2, 6), (1, 7)]
        shadow_rows = {6, 7}
        decisions += ["base_and_existing_shadow_shifted_up_one_row",
                      "cedilla_tail_uses_last_two_rows",
                      "shadow_below_y7_deliberately_omitted"]
    else:
        if base.isupper():
            row_map = list(zip(CAPITAL_ROWS[base], range(2, 7))) + [(7, 7)]
            decisions.append("capital_body_compacted_to_five_rows_with_original_bottom_shadow")
            if base == "E":
                decisions.append("E_keeps_a_stem_row_between_top_and_middle_bars")
        else:
            row_map = [(row, row) for row in range(4 if base == "i" else 2, 8)]
        for source, target in row_map:
            result[target] = original[source].copy()

        if base == "i":
            # The original dot occupies Y2 and its shadow Y3. Replace both;
            # leave the original stem and shadow at Y4..7 exactly untouched.
            result[2] = [0] * 8
            result[3] = [0] * 8
            ink = [(2, 1), (1, 2)]
            shadow_rows = {1, 2, 3}
            decisions += ["i_original_dot_and_shadow_removed_y2_y3",
                          "i_acute_at_y1_y2_with_shadow_y3"]
        elif mark == "tilde":
            # Four foreground columns describe two opposite slopes; the
            # fifth column admits the right shadow within the draw width.
            ink = [(1, 0), (3, 0), (0, 1), (2, 1)]
            edge = [(1, 1), (3, 1)]
            shadow_rows = {0, 1}
            decisions += ["four_column_wave_with_edge_pixels",
                          "advance_at_least_five_to_retain_mark_and_shadow"]
        else:
            mark_width = 3 if mark == "circumflex" else 2
            left = (base_advance - 1 - mark_width + 1) // 2
            if mark == "acute":
                ink = [(left + 1, 0), (left, 1)]
            elif mark == "grave":
                ink = [(left, 0), (left + 1, 1)]
            elif mark == "circumflex":
                ink = [(left + 1, 0), (left, 1), (left + 2, 1)]
            else:
                raise KhcomError("credits_recipe", "unsupported non-cedilla accent")
            shadow_rows = {0, 1}
        decisions.append("accent_shadow_is_not_allowed_to_rewrite_base_body_rows")

    # Place all foreground first so accent strokes cannot erase each other.
    for x, y in ink:
        if not 0 <= x < advance or not 0 <= y < 8:
            raise KhcomError("credits_recipe", "authored accent exceeds drawing bounds")
        result[y][x] = 1
    for x, y in edge:
        if result[y][x] == 0:
            result[y][x] = 3
    shadow_skipped = []
    for x, y in ink:
        sx, sy = x + 1, y + 1
        if sx >= advance or sy >= 8 or sy not in shadow_rows:
            shadow_skipped.append([sx, sy])
        elif result[sy][sx] == 0:
            result[sy][sx] = 2
    if any(value for row in result for value in row[advance:]):
        raise KhcomError("credits_recipe", "output has pixels beyond its advertised draw width")
    if result == original:
        raise KhcomError("credits_recipe", "accent recipe did not change the glyph")
    return {
        "rows": [bytes(row) for row in result],
        "advance": advance,
        "metadata": {
            "recipe": "credits_ptbr_font8_v1",
            "character": character,
            "base_character": base,
            "accent": mark,
            "height_pixels": 8,
            "base_advance": base_advance,
            "output_advance": advance,
            "source_to_output_rows": row_map,
            "accent_foreground_coordinates": ink,
            "accent_edge_coordinates": edge,
            "omitted_shadow_coordinates": shadow_skipped,
            "decisions": decisions,
            "runtime_verified": False,
            "typography_approved": False,
            "limitations": [
                "Two accent rows and five capital-body rows leave no universal blank separator.",
                "Cedilla bases are one pixel higher and lose shadow below the 8px cell.",
                "Small tilde glyphs have increased advance and need fresh line-width validation.",
                "Distinct pixel matrices do not establish human legibility at native scale.",
            ],
        },
    }


def _generate16(character, base_rows):
    base,mark=unicodedata.normalize('NFD',character)
    rows=[list(r) for r in base_rows]
    edits=[]
    if base=='i':
        for y in (3,4):
            for x in range(8):rows[y][x]=0
        edits.append('Removed original i dot at rows 3/4, preserving stem and baseline.')
    if mark=='\u0327':
        # The existing C/c descender space has two unused rows below shadow.
        foreground={(3,14),(2,15)}
        edits.append('Cedilla tail occupies rows 14/15 below preserved C/c; lower shadow cannot extend past cell and is intentionally omitted.')
    else:
        y=0 if base.isupper() else 3
        center=2 if base in 'AEIOUaeou' else 1
        if mark=='\u0301':foreground={(center+1,y),(center,y+1)}
        elif mark=='\u0300':foreground={(center-1,y),(center,y+1)}
        elif mark=='\u0302':foreground={(center,y),(center-1,y+1),(center+1,y+1)}
        elif mark=='\u0303':foreground={(center-1,y),(center+1,y),(center-2,y+1),(center,y+1)}
        else:raise KhcomError("credits_recipe", "Acento não suportado.", character=character)
        edits.append('Accent uses two foreground rows plus right/down shadow in the blank space above the original base.')
    for x,y in foreground:
        if not (0 <= x < 8 and 0 <= y < 16) or rows[y][x] != 0:
            raise KhcomError("credits_recipe", "Acento sobrescreveria a base.", character=character, x=x, y=y)
    # Add shadow only in unused cells; it never erases the base or accent ink.
    for x,y in sorted(foreground):
        for sx,sy in ((x+1,y),(x,y+1),(x+1,y+1)):
            if 0<=sx<8 and 0<=sy<16 and (sx,sy) not in foreground and rows[sy][sx]==0:rows[sy][sx]=2
    for x,y in foreground:rows[y][x]=1
    occupied=[(x,y) for y,row in enumerate(rows) for x,v in enumerate(row) if v]
    width=max(x for x,y in occupied)+1
    if not 1 <= width <= 8:
        raise KhcomError("credits_recipe", "Largura resultante inválida.")
    return rows,{'character':character,'base':base,'mark':mark,'advance':width,'accent_foreground':sorted(map(list,foreground)),'recipe_notes':edits,'ink_bounds':[min(x for x,y in occupied),min(y for x,y in occupied),width,max(y for x,y in occupied)+1]}


def generate_accent(character: str, base_rows, base_advance: int) -> dict:
    """Generate one supported 2bpp cell; retain the caller's input unchanged."""
    if not isinstance(character, str) or len(character) != 1 or character not in REQUIRED:
        raise KhcomError("credits_recipe", "Selecione um acento NFC do perfil PT-BR.")
    if (not isinstance(base_rows, (list, tuple)) or len(base_rows) not in (8, 16)
            or any(not isinstance(row, (list, tuple, bytes)) or len(row) != 8 for row in base_rows)
            or any(type(value) is not int or not 0 <= value < 4 for row in base_rows for value in row)):
        raise KhcomError("credits_recipe", "A base deve ser uma matriz 8×8 ou 8×16 de pixels 2bpp.")
    if type(base_advance) is not int or not 3 <= base_advance <= 8:
        raise KhcomError("credits_recipe", "Avanço da base fora de 3–8 pixels.")
    if any(value for row in base_rows for value in row[base_advance:]):
        raise KhcomError("credits_recipe", "Pixels da base excedem seu avanço.")
    if not any(value == 1 for row in base_rows for value in row):
        raise KhcomError("credits_recipe", "A base não contém primeiro plano.")
    if len(base_rows) == 8:
        return _generate8(character, base_rows, base_advance)
    rows, metadata = _generate16(character, base_rows)
    return {"rows": [bytes(row) for row in rows], "advance": metadata["advance"],
            "metadata": {**metadata, "recipe": "credits_ptbr_font16_v2",
                         "typography_approved": False, "runtime_verified": False}}
