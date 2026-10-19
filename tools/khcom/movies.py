"""Bounded movie framing and subtitle occurrence inventory for the US revision.

The parser preserves every opaque byte and does not claim to decode or encode
compressed video/audio. Rendering evidence is supplied by separate core runs.
"""
from collections import Counter
import math
import re
import struct

from .errors import KhcomError
from .rom import identify_bytes
from .text import extract_catalog, ROM_BASE
from .upstream import load_assetgen, read_source, SNAPSHOT, sha256

TABLES = (
    ('gMovieSubsOpening', 0x0886ab40, 3, True),
    ('gMovieSubs6FGoal', 0x0886ab70, 1, False),
    ('gMovieSubs12FE2', 0x0886ab80, 1, False),
    ('gMovieSubsEnding', 0x0886ab90, 14, True),
    ('gMovieSubsRikuEnding', 0x0886ac70, 10, True),
)


def parse_movie(data: bytes) -> dict:
    if len(data) < 32:
        raise KhcomError('movie_header', 'Cabeçalho de filme truncado.')
    width, height, fps, frames, audio_blocks, channels, rate, codec = struct.unpack_from('<IIfIIIII', data)
    if not width or width > 288 or width % 8 or not height or height > 160 or height % 8 or not math.isfinite(fps) or not 0 < fps <= 60:
        raise KhcomError('movie_dimensions', 'Dimensões ou taxa de frames não suportadas.')
    if not 0 < frames <= 65535 or channels not in (0, 1, 2) or audio_blocks > 65535 or codec not in (0, 1, 2):
        raise KhcomError('movie_profile', 'Contagens/canais/codec fora do perfil suportado.')
    at = 32

    def take(size: int) -> tuple[int, bytes]:
        nonlocal at
        begin = at
        if size < 0 or at + size > len(data):
            raise KhcomError('movie_range', 'Tabela ou payload excede o recurso.', offset=at, size=size)
        at += size
        return begin, data[begin:at]

    def u32() -> int:
        return struct.unpack('<I', take(4)[1])[0]

    def stream(count: int, kind: str) -> dict:
        type_length = u32()
        types_at, types = take(type_length)
        size_length, payload_length = u32(), u32()
        sizes_at, sizes = take(size_length)
        payload_at, payload = take(payload_length)
        if len(types) < count or len(sizes) < (count + 1) * 2:
            raise KhcomError('movie_table_count', 'Tabelas não cobrem os blocos declarados.', stream=kind)
        maximum = struct.unpack_from('<H', sizes)[0]
        lengths = struct.unpack_from('<' + 'H' * count, sizes, 2)
        if sum(lengths) != len(payload):
            raise KhcomError('movie_payload_size', 'Soma dos blocos difere do payload.', stream=kind)
        if kind == 'video' and any(value not in (0, 1, 2) for value in types[:count]):
            raise KhcomError('movie_frame_type', 'Tipo de frame desconhecido.')
        cursor = payload_at
        blocks = []
        for index, length in enumerate(lengths):
            if length > maximum or length % 4:
                raise KhcomError('movie_block_budget', 'Bloco excede a reserva ou alinhamento de 4 bytes.', stream=kind, index=index)
            blocks.append({'index': index, 'type': types[index], 'span': [cursor, cursor + length],
                           'size': length, 'sha256': sha256(data[cursor:cursor+length])})
            cursor += length
        return {'types_span': [types_at, types_at + len(types)], 'sizes_span': [sizes_at, sizes_at + len(sizes)],
                'type_padding_bytes': len(types) - count, 'size_padding_bytes': len(sizes) - (count+1)*2,
                'decode_buffer_maximum': maximum, 'payload_span': [payload_at, payload_at + len(payload)],
                'payload_sha256': sha256(payload), 'types': dict(Counter(types[:count])), 'blocks': blocks}

    video = stream(frames, 'video')
    audio = stream(audio_blocks, 'audio') if channels else None
    return {'width': width, 'height': height, 'fps': fps, 'frames': frames, 'audio_blocks': audio_blocks,
            'channels': channels, 'sample_rate': rate, 'audio_codec': codec, 'duration_seconds': frames/fps,
            'video': video, 'audio': audio, 'opaque_tail': {'span': [at, len(data)], 'sha256': sha256(data[at:]),
            'reusable': False}, 'decoded_video_work_bytes': width*height*2*2,
            'audio_buffer_bytes': 0x2000 if channels else 0, 'decode_buffer_bytes': max(video['decode_buffer_maximum'], 0 if audio is None else audio['decode_buffer_maximum'])}


def inventory_movies(data: bytes) -> dict:
    identify_bytes(data)
    owner = load_assetgen()
    manifest = owner.Manifest(SNAPSHOT/'config/assets/movies.yaml')
    manifest.members('us')
    movies = []
    for entry in manifest.entries:
        start = entry['us']['address'] - ROM_BASE
        size = manifest.size(entry, 'us')
        raw = data[start:start+size]
        if len(raw) != size:
            raise KhcomError('movie_resource', 'Filme fora da ROM.')
        movies.append({'symbol': entry['name'], 'span': [start, start+size], 'sha256': sha256(raw), **parse_movie(raw)})
    catalog = extract_catalog(data)
    text = {item['id'].split('/')[-1]: item for item in catalog['items'] if item['id'].startswith('us/movie_subtitle_text/')}
    source = read_source('src/evt/mode_movie.c')
    us = source.decode().split('#ifdef VERSION_US', 1)[1].split('#endif', 1)[0]
    occurrences = []
    for name, address, count, active in TABLES:
        match = re.search(r'const MovieSub '+name+r'\['+str(count)+r'\] = \{(.*?)\};', us, re.S)
        if match is None:
            raise KhcomError('movie_subtitle_source', 'Tabela US não encontrada na fonte fixada.', table=name)
        rows = re.findall(r'\{\s*(\d+),\s*(\d+),\s*(\w+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\}', match[1])
        if len(rows) != count:
            raise KhcomError('movie_subtitle_count', 'Tabela de legendas não corresponde à contagem.')
        for index, row in enumerate(rows):
            frame, x, symbol, line, duration, palette = row
            item = text.get(symbol)
            if item is None:
                raise KhcomError('movie_subtitle_text', 'Legenda fora do catálogo.', symbol=symbol)
            expected = (int(frame), int(x), ROM_BASE+item['source_span']['start'], int(line), int(duration), int(palette))
            offset = address - ROM_BASE + index*16
            observed = struct.unpack_from('<hhIBxHH', data, offset)
            if observed != expected:
                raise KhcomError('movie_subtitle_record', 'Registro de legenda difere da fonte fixada.', table=name, index=index)
            occurrences.append({'table': name, 'index': index, 'id': item['id'], 'record_span': [offset, offset+16],
                                'frame': int(frame), 'x': int(x), 'line': int(line), 'duration': int(duration),
                                'palette': int(palette), 'text_span': item['source_span'], 'source_text': item['source_text'],
                                'selected_by_us_movie_mode': active,
                                'selection_reason': 'selected table' if active else 'mode selects NULL and count 0; declared blank placeholder remains inventoried'})
    return {'schema': 'khcom-movies-v1', 'rom_sha256': sha256(data), 'movies': movies, 'subtitle_occurrences': occurrences,
            'declared_frames': sum(movie['frames'] for movie in movies), 'declared_subtitle_rows': len(occurrences),
            'selected_subtitle_rows': sum(row['selected_by_us_movie_mode'] for row in occurrences),
            'source': {'path': 'src/evt/mode_movie.c', 'sha256': sha256(source)},
            'limitations': ['Packet framing is validated; video/audio codecs are not reimplemented.',
                            'Frame capture, raster text review and subtitle rendering are independent runtime evidence.',
                            'Opaque tails are preserved and never considered free space.']}


def build_opening_subtitle_probe(data: bytes) -> tuple[bytes, dict]:
    """Three fixed opening lines; no video codec, timing or address is changed."""
    from .graphics import extract_fonts
    from .upstream import load_textgen

    inventory = inventory_movies(data)
    rows = [row for row in inventory['subtitle_occurrences'] if row['table'] == 'gMovieSubsOpening']
    translations = ('Adiante há o que você precisa―{END}', '―mas, para obter, perderá{END}', '            algo precioso.{END}')
    codec = load_textgen().load_charmap('us')['game']
    fonts, _files = extract_fonts(data)
    widths = fonts['latin_metrics']['values']
    glyphs = next(font for font in fonts['fonts'] if font['id'] == 'message_latin')['glyphs']
    output = bytearray(data)
    changes = []
    for row, translated in zip(rows, translations, strict=True):
        encoded = codec.encode(translated, row['id'])
        codes = struct.unpack('<' + 'H' * (len(encoded)//2), encoded)[:-1]
        source = row['text_span']
        if len(encoded) > source['end'] - source['start']:
            raise KhcomError('movie_subtitle_capacity', 'Legenda excede reserva original.', id=row['id'])
        advances, indices = [], []
        for code in codes:
            if code == 32:
                if advances:
                    advances[-1] += 3  # CopyLatinGlyphsToVram adds spaces to the preceding glyph.
                continue
            glyph = 25 if code == 0xe000 else code
            if not (32 <= glyph <= 255 or glyph == 25) or not glyphs[glyph]['nonzero_pixels']:
                raise KhcomError('movie_subtitle_glyph', 'Glifo sem contrato neste piloto.', code=code)
            indices.append(glyph)
            advances.append(widths[glyph])
        if len(indices) > 40 or sum(advances) > 240:
            raise KhcomError('movie_subtitle_width', 'Legenda excede buffers ou largura de tela.', id=row['id'])
        x = row['x'] + 120 - sum(advances)//2
        occupied = []
        for glyph, advance in zip(indices, advances, strict=True):
            box = glyphs[glyph]['bounds']
            occupied.append([x+box[0], x+box[2]])
            x += advance
        if min(span[0] for span in occupied) < 0 or max(span[1] for span in occupied) > 240:
            raise KhcomError('movie_subtitle_ink', 'Pixels da legenda ultrapassam a tela.', id=row['id'])
        output[source['start']:source['start']+len(encoded)] = encoded
        changes.append({**row, 'translation': translated, 'encoded_bytes': len(encoded),
                        'non_space_glyphs': len(indices), 'advance_pixels': sum(advances),
                        'ink_x': [min(span[0] for span in occupied), max(span[1] for span in occupied)],
                        'glyph_indices': indices, 'tail_bytes_preserved': source['end']-source['start']-len(encoded)})
    result = bytes(output)
    return result, {'schema': 'khcom-opening-subtitle-probe-v1', 'source_sha256': sha256(data), 'target_sha256': sha256(result),
                    'changes': changes, 'movie_count': len(inventory['movies']), 'compressed_movies_unchanged': True,
                    'subtitle_records_unchanged': True, 'timing_unchanged': True, 'rom_size': len(result),
                    'state': 'diagnostic_candidate_requires_runtime_comparison', 'release_approved': False,
                    'font_contract': 'CopyLatinGlyphsToVram US: non-space slots, +3 advance for subsequent spaces, E000->glyph25, max40 glyphs/line',
                    'limitations': ['Only three fixed opening subtitle occurrences; not full audiovisual localization.',
                                    'Rasterized logo and all other subtitles require their own coverage records.']}
