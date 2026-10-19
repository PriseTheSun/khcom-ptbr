"""ROM-derived opening subtitle raster recipe, using the verified movie codecs.

The user's title decision is Corrente de Memórias; Kingdom Hearts and brands
remain intact. This replaces the subtitle line only in the opening movie.
All original pixels/fonts are read from the supplied ROM, never bundled here.
"""
import struct

from .errors import KhcomError
from .graphics import extract_fonts
from .movie_delta import decode_delta, decode_keyframe, encode_delta, parse_delta, postprocess_pixels, paint_keyframe_selectors, replace_delta_pixels
from .movies import inventory_movies
from .upstream import load_assetgen, sha256

TITLE='CORRENTE DE MEMÓRIAS'
RECT=(48,72,192,88)
FIRST,LAST=1520,1610


def _plate(data):
    fonts,files=extract_fonts(data)
    owner=load_assetgen().sprite_sheet
    atlas_w,_h,pixels=owner.read_png(files['message_latin.png'])
    widths=fonts['latin_metrics']['values']
    def rgb(r,g,b):return r|(g<<5)|(b<<10)
    w,h=RECT[2]-RECT[0],RECT[3]-RECT[1]
    plate=[rgb(2,3,5)]*(w*h)
    for y in range(h):
        for x in range(w):
            if y in (0,h-1):plate[y*w+x]=rgb(15,14,8)
    advance=sum(3 if c==' ' else widths[ord(c)] for c in TITLE)
    x=(w-advance)//2
    for char in TITLE:
        if char==' ':x+=3;continue
        code=ord(char);sx=(code%(atlas_w//16))*16;sy=(code//(atlas_w//16))*16
        for yy in range(16):
            for xx in range(16):
                value=pixels[(sy+yy)*atlas_w+sx+xx]
                px,py=x+xx,2+yy
                if value and not (0<=px<w and 0<=py<h):raise KhcomError('movie_title_ink','Título raster excede o retângulo.')
                if value:plate[py*w+px]=rgb(31,30,23) if value==2 else rgb(9,8,4)
        x+=widths[code]
    return plate,{'text':TITLE,'rectangle':list(RECT),'advance_pixels':advance,
                  'font_source':'message_latin','font_png_sha256':sha256(files['message_latin.png']),
                  'decision':'User explicitly requested Corrente de Memórias; preserve Kingdom Hearts and brands.'}


def build_opening_title_probe(data: bytes) -> tuple[bytes,dict]:
    inventory=inventory_movies(data)
    movie=inventory['movies'][0]
    if movie['symbol']!='gMovieOpening' or movie['frames']!=1617:raise KhcomError('movie_title_profile','Perfil de abertura divergente.')
    start,end=movie['span'];raw=data[start:end];video=movie['video'];plate,art=_plate(data)
    replacement={};previous=modified_previous=None;changes=[]
    for frame in video['blocks'][:LAST+1]:
        index=frame['index'];a,b=frame['span'];packet=raw[a:b]
        if frame['type']==0:original=decode_keyframe(packet)
        else:
            parsed=parse_delta(packet)
            original_pre=decode_delta(parsed,previous)
            original=postprocess_pixels(original_pre) if frame['type']==2 else original_pre
        if index>=FIRST:
            desired=(original if frame['type']==0 else original_pre)[:]
            # The original subtitle fades in with the logo over ten frames.
            # A compact dark plaque removes every original English glyph; its
            # text and borders follow the logo fade without blending English.
            fade_in=min(10,index-FIRST+1)
            fade_out=16 if index<1603 else (15,14,13,12,10,8,6,4)[index-1603]
            for yy in range(RECT[3]-RECT[1]):
                for xx in range(RECT[2]-RECT[0]):
                    pos=(RECT[1]+yy)*240+RECT[0]+xx
                    foreground=plate[yy*(RECT[2]-RECT[0])+xx]
                    desired[pos]=sum(((((foreground>>s)&31)*fade_in//10)*fade_out//16)<<s for s in (0,5,10))
            if frame['type']==0:
                encoded=paint_keyframe_selectors(packet,desired,RECT)
                desired=decode_keyframe(encoded);changed_blocks=None
            else:
                nodes,changed_blocks=replace_delta_pixels(parsed,modified_previous,desired)
                encoded=encode_delta(nodes)
                if decode_delta(parse_delta(encoded),modified_previous)!=desired:raise KhcomError('movie_title_roundtrip','Encoder divergiu do frame desejado.',frame=index)
                if frame['type']==2:desired=postprocess_pixels(desired)
            if len(encoded)>video['decode_buffer_maximum']:raise KhcomError('movie_title_buffer','Frame traduzido excede buffer.',frame=index,size=len(encoded))
            replacement[index]=encoded
            changes.append({'frame':index,'source_bytes':len(packet),'encoded_bytes':len(encoded),'reencoded_blocks':changed_blocks,
                            'source_type':frame['type'],'target_type':frame['type'],'decoded_rgb555_sha256':sha256(struct.pack('<38400H',*desired))})
            modified_previous=desired
        else:modified_previous=original
        previous=original
    source_total=sum(video['blocks'][i]['size'] for i in replacement)
    encoded_total=sum(map(len,replacement.values()))
    slack=source_total-encoded_total
    if slack<0:raise KhcomError('movie_title_capacity','Segmento traduzido excede o payload original.',extra=-slack)
    # Padding is in the owned delta packet after all consumed streams. Neither
    # the movie's opaque tail nor any other ROM region is used for capacity.
    for i,encoded in list(replacement.items()):
        padding=min(slack,max(0,video['blocks'][i]['size']-len(encoded)))
        replacement[i]=encoded+bytes(padding);slack-=padding
    for i,encoded in list(replacement.items()):
        padding=0 if video['blocks'][i]['type']==0 else min(slack,video['decode_buffer_maximum']-len(encoded))
        replacement[i]=encoded+bytes(padding);slack-=padding
    if slack:raise KhcomError('movie_title_padding','Reserva de padding insuficiente.')
    asset=bytearray(raw);payload=[]
    for frame in video['blocks']:
        i=frame['index'];a,b=frame['span'];packet=replacement.get(i,raw[a:b]);payload.append(packet)
        if i in replacement:
            struct.pack_into('<H',asset,video['sizes_span'][0]+2*(i+1),len(packet))
    joined=b''.join(payload);pa,pb=video['payload_span']
    if len(joined)!=pb-pa:raise KhcomError('movie_title_payload','Tamanho do payload mudou.')
    asset[pa:pb]=joined
    target=bytearray(data);target[start:end]=asset
    if len(target)!=len(data) or asset[pb:]!=raw[pb:]:raise KhcomError('movie_title_identity','Áudio, cauda ou tamanho alterado.')
    report={'schema':'khcom-opening-raster-title-probe-v1','source_sha256':sha256(data),'target_sha256':sha256(target),
            'movie_symbol':movie['symbol'],'movie_span':movie['span'],'art':art,'frame_range':[FIRST,LAST],
            'source_segment_bytes':source_total,'encoded_segment_bytes':encoded_total,'owned_packet_padding_bytes':source_total-encoded_total,
            'decode_buffer_limit':video['decode_buffer_maximum'],'maximum_encoded_frame':max(c['encoded_bytes'] for c in changes),
            'audio_and_tail_identical':True,'frame_count_and_fps_identical':True,'all_other_movie_resources_identical':True,
            'changes':changes,'status':'candidate_requires_independent_runtime_visual_verification'}
    return bytes(target),report
