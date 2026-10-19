"""Bounded semantic ownership of pointer-shaped words in reviewed US assets.

These profiles derive from upstream revision 5dc49b7 and the matching ELF.
Hashes identify source descriptions and encoded files, never grant free space.
"""
from pathlib import Path
import struct
from hashlib import sha256

from .errors import KhcomError
from .io import read_file

PROFILES = (
    {'symbol': 'gRikuBt10Tiles', 'format': 'gba_4bpp_tiles',
     'asset': 'build/us/gen/sprites_riku/riku_bt10.4bpp',
     'sha256': '00dc217cadf44b9d32d7aab745a40f520dd51f262b796c34a31d644cebc5b48e',
     'manifest': 'config/assets/sprites_riku.yaml',
     'manifest_sha256': '8bd272bb7b5d46c3e6816850e9f642bf25a1c03ed8087aa2ff4bee1ca0c4c90a'},
    {'symbol': 'gNiserikuDamageTiles', 'format': 'gba_4bpp_tiles',
     'asset': 'build/us/gen/sprites_hum/niseriku_damage.4bpp',
     'sha256': 'b436c113adeac1bdd92b40a851cb6c6df611da46af48389a02d7048094a5b5bd',
     'manifest': 'config/assets/sprites_hum.yaml',
     'manifest_sha256': 'f506bdbbc18ffcdaa3cd47c4ab92669d1dacc5ca2811fe8740075e11934640f1'},
    {'symbol': 'gCroudB02Tiles', 'format': 'gba_4bpp_tiles',
     'asset': 'build/us/gen/sprites_evt/croud_b02.4bpp',
     'sha256': '3ecef3cfaed0fe24163443117d47eb66a0e5d300b22e8ad5299546630e173ca1',
     'manifest': 'config/assets/sprites_evt.yaml',
     'manifest_sha256': '301fc595833e38d75c2d8c410a9383329b75d5f4f8431ee82c03c2f34c1dce10'},
    {'symbol': 'gBlockAudioData', 'format': 'khcom_audio_block_bitstream',
     'asset': 'build/us/gen/staff_roll_audio/gBlockAudioData.bin',
     'sha256': '565539f2ddfcac236389b3217c9f7a6a40359b7d314b53d78ff8b14e46aa245d',
     'manifest': 'config/assets/staff_roll_audio.yaml',
     'manifest_sha256': '53a7ecd42c71d077362fa67920b2a4fdc65479f4f50f76d6aac53d36144f7295'},
    {'symbol': 'gSor1ll56Tiles', 'format': 'gba_4bpp_tiles',
     'asset': 'build/us/gen/sprites_fld/sor1ll56.4bpp',
     'sha256': 'dd7e370ec890888577a1f38d93c695e6ffa32ea38d68ebf0d51161b86787eb4c',
     'manifest': 'config/assets/sprites_fld.yaml',
     'manifest_sha256': '504777c7a1b1ebde0754d9a9e42700182c9a68ae70f3e8e16519e3e6d243ac02'},
    {'symbol': 'gStaffRollRikuScene13Tiles', 'format': 'gba_4bpp_tiles',
     'asset': 'build/us/gen/sprites_staff_roll/gStaffRollRikuScene13Tiles.4bpp',
     'sha256': '7e98a4442a17c65272ea7e3211b3a66dda8087df32046e8af7fb387e03ad0b1f',
     'manifest': 'config/assets/sprites_staff_roll.yaml',
     'manifest_sha256': '3fd0609fe24f2b4488f8e648c52ad86e33c72802631e7bfc8966c150fcc8b93e'},
    {'symbol': 'gStaffRollRikuImage1Palette', 'format': 'gba_palette_u16',
     'asset': 'build/us/gen/sprites_staff_roll/gStaffRollRikuImage1Palette.gbapal',
     'sha256': '2b218916720da63ecb6dc4c5cda291f7db98b6a73d23e5302bdcf4531eded8a5',
     'manifest': 'config/assets/sprites_staff_roll.yaml',
     'manifest_sha256': '3fd0609fe24f2b4488f8e648c52ad86e33c72802631e7bfc8966c150fcc8b93e'},
    {'symbol': 'gMovieOpening', 'format': 'khcom_movie_video_packet',
     'asset': 'build/us/gen/movies/gMovieOpening.bin',
     'sha256': '99bbbc95a2f95883e52a9c9be911f8882c25d1a67ec2a950c440f40317f13313',
     'manifest': 'config/assets/movies.yaml',
     'manifest_sha256': '9fd0053733d1a0e29fc0bbfe9cae56abe3382327c19a649050fc522f7fdcfe78'},
    {'symbol': 'gMovieRikuEnding', 'format': 'khcom_movie_video_packet',
     'asset': 'build/us/gen/movies/gMovieRikuEnding.bin',
     'sha256': '750be215a2ee23b1b52e072a316f8401fb6cefbc29992ca89a11f6131b89ae52',
     'manifest': 'config/assets/movies.yaml',
     'manifest_sha256': '9fd0053733d1a0e29fc0bbfe9cae56abe3382327c19a649050fc522f7fdcfe78'},
)
AUDIO_SOURCES = {
    'src/sroll/sroll_tmr.c': '578f44f092769fefc534c987edc44d351126f21d7dcc994defcdce1f6d603a80',
    'src/lib/audio_block_codec.c': '88dd303c99b5791ce2167b1c1edbca6b27a2ff74d66ef9d4afc280326cbd2f9d',
}
MOVIE_SOURCES = {
    'asm/movie_codec.s': '68f282b8e26fd2f96f527a86519ceab9d9455968d3c85dcca809220670166e3b',
    'src/lib/movie_player.c': 'a60b626c8f6c19693cbaf95aefdf2844f816403feac28cdbdad279d01da90678',
}


def _verified(root: Path, path: str, expected: str) -> tuple[bytes, dict]:
    data = read_file(root / path, 4 << 20)
    digest = sha256(data).hexdigest()
    if digest != expected:
        raise KhcomError('matching_asset_identity', 'Fonte ou recurso diverge do perfil fixado.', path=path)
    return data, {'path': str((root / path).absolute()), 'sha256': digest, 'size': len(data)}


def audio_payload_at(data: bytes, target: int) -> dict | None:
    """ReadNextAudioBlock framing, not an audio decoder or pointer table."""
    at = 0
    index = 0
    while at + 4 <= len(data):
        header = struct.unpack_from('<I', data, at)[0]
        if header & 255 != 0x53:
            return None
        size = (((header >> 8) & 0xff00) + (header >> 24)) * 4
        if size < 4 or at + size > len(data):
            raise KhcomError('matching_audio_framing', 'Bloco de áudio excede o recurso.', block=index)
        if at + 4 <= target and target + 4 <= at + size:
            return {'block_index': index, 'block_span': [at, at + size], 'payload_span': [at + 4, at + size]}
        at += size
        index += 1
    return None


def classify_encoded_words(words: list[dict], rom: bytes, root: Path, symbols: list[dict]) -> None:
    by_name = {s['name']: s for s in symbols if s['binding'] == 'STB_GLOBAL'}
    for profile in PROFILES:
        symbol = by_name.get(profile['symbol'])
        if symbol is None:
            raise KhcomError('matching_asset_symbol', 'Símbolo do perfil não está presente no ELF.', symbol=profile['symbol'])
        asset, asset_identity = _verified(root, profile['asset'], profile['sha256'])
        _manifest, manifest_identity = _verified(root, profile['manifest'], profile['manifest_sha256'])
        start = symbol['address'] - 0x08000000
        end = start + len(asset)
        if start < 0 or end > len(rom) or asset != rom[start:end]:
            raise KhcomError('matching_asset_rom', 'Recurso codificado não reproduz a ROM.', symbol=profile['symbol'])
        for word in words:
            offset = word['source_offset']
            if not start <= offset or offset + 4 > end:
                continue
            if word['relocation'] is not None:
                raise KhcomError('matching_asset_pointer', 'Recurso codificado contém relocação inesperada.', offset=offset)
            evidence = {'symbol': profile['symbol'], 'span': [start, end], 'format': profile['format'],
                        'asset': asset_identity, 'manifest': manifest_identity, 'bytes_equal_rom': True}
            if profile['format'] == 'khcom_audio_block_bitstream':
                payload = audio_payload_at(asset, offset - start)
                if payload is None:
                    continue
                evidence['audio_block'] = payload
                evidence['decoder_sources'] = [_verified(root, path, digest)[1] for path, digest in AUDIO_SOURCES.items()]
                evidence['interpretation'] = 'ReadNextAudioBlock passes this payload to DecodeAudioBlock; bytes are consumed by the bit reader.'
            elif profile['format']=='khcom_movie_video_packet':
                from .movies import parse_movie
                from .movie_delta import decode_keyframe,parse_delta
                movie=parse_movie(asset)
                packet=next((p for p in movie['video']['blocks'] if p['span'][0]<=offset-start and offset-start+4<=p['span'][1]),None)
                if packet is None:continue
                a,b=packet['span']
                if packet['type']==0:decode_keyframe(asset[a:b],movie['width'],movie['height'])
                else:parse_delta(asset[a:b],movie['width'],movie['height'])
                evidence['movie_packet']=packet
                evidence['decoder_sources']=[_verified(root,path,digest)[1] for path,digest in MOVIE_SOURCES.items()]
                evidence['interpretation']='The typed movie packet is consumed by the verified video codec, not loaded as a ROM pointer table.'
            elif profile['format']=='gba_palette_u16':
                if len(asset)%2:raise KhcomError('matching_palette','Paleta não contém palavras u16 completas.')
                evidence['palette_word_index']=(offset-start)//2
                evidence['interpretation']='Each u16 is a GBA palette color; original high bits are retained.'
            else:
                if len(asset) % 32:
                    raise KhcomError('matching_tiles', 'Dados 4bpp não contêm tiles completos.')
                evidence['tile_index'] = (offset - start) // 32
                evidence['interpretation'] = 'Each byte encodes two palette indices in uncompressed 8x8 4bpp tiles.'
            word['classification'] = 'encoded_asset_data_verified'
            word['encoded_asset'] = evidence
