"""Bounded reader/writer for KHCoM's matching ARM rectangular delta codec.

The grammar is derived from MovieDeltaCodecDecode and MovieDeltaCodecStart
at upstream 5dc49b7, not from a presumed third-party codec identity. Nodes are
owned here; callers consume this representation instead of reparsing packets.
Keyframes use two RGB555 endpoints and 16 two-bit selections per 16×16 cell,
followed by the matching horizontal and vertical interpolation passes.
"""
from dataclasses import dataclass
import struct

from .errors import KhcomError


@dataclass(frozen=True)
class Node:
    kind: str
    values: tuple[int, ...] = ()
    children: tuple['Node', ...] = ()


def halves(width: int, height: int, vertical: bool):
    if vertical:
        return ((0, 0, width//2, height), (width//2, 0, width//2, height))
    return ((0, 0, width, height//2), (0, height//2, width, height//2))


def dimensions(width: int, height: int):
    if not (8 <= width <= 288 and width % 8 == 0 and 8 <= height <= 160 and height % 8 == 0):
        raise KhcomError('delta_dimensions', 'Dimensões delta fora do perfil GBA.')


def parse_delta(packet: bytes, width=240, height=160) -> dict:
    dimensions(width, height)
    if not 8 <= len(packet) <= 65532 or len(packet) % 4:
        raise KhcomError('delta_packet', 'Pacote delta truncado ou desalinhado.')
    bits_size, colors_size = struct.unpack_from('<HH', packet)
    colors_at, motion_at = 4 + bits_size, 4 + bits_size + colors_size
    if not bits_size or bits_size % 4 or colors_size % 2 or motion_at > len(packet):
        raise KhcomError('delta_stream', 'Limites dos fluxos delta inválidos.')
    bit_count = 0
    color_pos, motion_pos = colors_at, motion_at

    def bit():
        nonlocal bit_count
        if bit_count >= bits_size*8:
            raise KhcomError('delta_bits', 'Árvore excede o fluxo de bits.')
        word = struct.unpack_from('<I', packet, 4+(bit_count//32)*4)[0]
        value = (word >> (31-bit_count%32)) & 1
        bit_count += 1
        return value

    def color():
        nonlocal color_pos
        if color_pos+2 > motion_at:
            raise KhcomError('delta_color', 'Árvore excede o fluxo de cores.')
        value = struct.unpack_from('<H', packet, color_pos)[0]
        color_pos += 2
        return value

    def motion():
        nonlocal motion_pos
        if motion_pos >= len(packet):
            raise KhcomError('delta_motion', 'Árvore excede o fluxo de movimento.')
        value = packet[motion_pos]
        motion_pos += 1
        return value

    def node(w, h):
        if not bit():
            return Node('motion', (motion(),)) if bit() else Node('copy')
        terminal = w*h == 2
        if not bit():
            if terminal:
                return Node('add', (motion(), color()))
            vertical = bool(bit()) if w > 1 and h > 1 else w > 1
            return Node('vertical' if vertical else 'horizontal', children=tuple(node(a,b) for _,_,a,b in halves(w,h,vertical)))
        if terminal:
            return Node('literal', (color(), color())) if bit() else Node('fill', (color(),))
        return Node('fill', (color(),)) if bit() else Node('add', (motion(), color()))

    nodes = tuple(node(8,8) for _ in range((width//8)*(height//8)))
    if motion_at-color_pos not in (0,2):
        raise KhcomError('delta_color_count', 'Cores não consumidas no pacote delta.', bytes=motion_at-color_pos)
    return {'nodes': nodes, 'width': width, 'height': height, 'bit_count': bit_count,
            'bits_size': bits_size, 'colors_size': colors_size, 'motion_size': motion_pos-motion_at,
            'color_padding': packet[color_pos:motion_at], 'tail': packet[motion_pos:], 'original': packet}


def encode_delta(nodes, width=240, height=160) -> bytes:
    dimensions(width,height)
    if len(nodes) != (width//8)*(height//8):
        raise KhcomError('delta_nodes', 'Contagem de blocos delta incorreta.')
    bits, colors, motions = [], bytearray(), bytearray()

    def color(v):
        if not 0 <= v <= 65535: raise KhcomError('delta_color_value', 'Cor delta fora de u16.')
        colors.extend(struct.pack('<H',v))

    def motion(v):
        if not 0 <= v <= 255: raise KhcomError('delta_motion_value', 'Vetor delta fora de u8.')
        motions.append(v)

    def write(n,w,h):
        terminal = w*h == 2
        if n.kind=='copy': bits.extend((0,0))
        elif n.kind=='motion': bits.extend((0,1)); motion(n.values[0])
        elif n.kind=='fill': bits.extend((1,1,0) if terminal else (1,1,1)); color(n.values[0])
        elif n.kind=='add': bits.extend((1,0) if terminal else (1,1,0)); motion(n.values[0]); color(n.values[1])
        elif n.kind=='literal' and terminal:
            bits.extend((1,1,1)); color(n.values[0]); color(n.values[1])
        elif n.kind in ('horizontal','vertical') and not terminal:
            vertical = n.kind=='vertical'
            if len(n.children)!=2 or (vertical and w==1) or (not vertical and h==1):
                raise KhcomError('delta_split', 'Partição delta inválida.')
            bits.extend((1,0))
            if w>1 and h>1:bits.append(int(vertical))
            for child,(_,_,a,b) in zip(n.children,halves(w,h,vertical),strict=True):write(child,a,b)
        else:raise KhcomError('delta_node', 'Operação delta inválida.', kind=n.kind)

    for n in nodes:write(n,8,8)
    bitstream=bytearray()
    for i in range(0,len(bits),32):
        word=sum(v<<(31-j) for j,v in enumerate(bits[i:i+32]))
        bitstream.extend(struct.pack('<I',word))
    colors.extend(bytes((-len(colors))%4))
    if max(len(bitstream),len(colors))>65535:raise KhcomError('delta_budget', 'Fluxo delta excede cabeçalho u16.')
    result=struct.pack('<HH',len(bitstream),len(colors))+bitstream+colors+motions
    return bytes(result)+bytes((-len(result))%4)


def decode_delta(parsed: dict, previous: list[int], *, postprocess=False) -> list[int]:
    width,height=parsed['width'],parsed['height']
    if len(previous)!=width*height or any(not 0<=x<=65535 for x in previous):
        raise KhcomError('delta_previous', 'Frame anterior não corresponde às dimensões/u16.')
    output=[0]*(width*height)

    def draw(n,x,y,w,h):
        if n.kind in ('horizontal','vertical'):
            for child,(dx,dy,a,b) in zip(n.children,halves(w,h,n.kind=='vertical'),strict=True):draw(child,x+dx,y+dy,a,b)
            return
        if n.kind=='literal':
            for i,v in enumerate(n.values):output[(y+i//w)*width+x+i%w]=v
            return
        if n.kind=='fill':
            for row in range(y,y+h):output[row*width+x:row*width+x+w]=[n.values[0]]*w
            return
        offset=0 if n.kind=='copy' else ((n.values[0]//16-8)*width+(n.values[0]%16-8))
        addition=n.values[1] if n.kind=='add' else 0
        for dy in range(h):
            start=(y+dy)*width+x+offset
            if start<0 or start+w>len(previous):raise KhcomError('delta_reference', 'Vetor delta sai do framebuffer.')
            for dx in range(0,w,2 if w>1 else 1):
                target=(y+dy)*width+x+dx
                if w==1:output[target]=(previous[start+dx]+addition)&65535
                else:
                    word=previous[start+dx]|(previous[start+dx+1]<<16)
                    word=(word+(addition|(addition<<16)))&0xffffffff
                    output[target],output[target+1]=word&65535,word>>16

    for index,n in enumerate(parsed['nodes']):draw(n,(index%(width//8))*8,(index//(width//8))*8,8,8)
    return postprocess_pixels(output,width,height) if postprocess else output


def postprocess_pixels(pixels: list[int],width=240,height=160) -> list[int]:
    dimensions(width,height)
    if len(pixels)!=width*height:raise KhcomError('delta_postprocess_size','Frame não corresponde às dimensões.')
    output=pixels[:]
    for y in range(height):
        for x in range(8,width,8):
            i=y*width+x;a,b=output[i-1:i+1]
            output[i]=(((a&0x7bdf)+(b&0x7bdf))>>1)|(b&0x0420)
    for y in range(8,height,8):
        for x in range(0,width,2):
            i=y*width+x
            a=output[i-width]|(output[i-width+1]<<16);b=output[i]|(output[i+1]<<16)
            word=(((a&0x7bdf7bdf)+(b&0x7bdf7bdf))>>1)|(b&0x04200420)
            output[i],output[i+1]=word&65535,word>>16
    return output


def keyframe_palette(a,b):
    c=sum(((2*((a>>s)&31)+((b>>s)&31)+1)//3)<<s for s in (0,5,10))
    d=sum(((((a>>s)&31)+2*((b>>s)&31)+1)//3)<<s for s in (0,5,10))
    return a,b,c,d


def encode_pixels(pixels: list[int], previous: list[int] | None = None, width=8, height=8) -> Node:
    """Choose a bounded lossless copy/fill/split/literal tree; no motion search."""
    if len(pixels)!=width*height or (previous is not None and len(previous)!=len(pixels)):
        raise KhcomError('delta_pixels', 'Pixels não correspondem ao bloco.')
    memo={}

    def solve(x,y,w,h):
        key=(x,y,w,h)
        if key in memo:return memo[key]
        vals=tuple(pixels[(y+j)*width+x+i] for j in range(h) for i in range(w))
        if previous is not None and all(previous[(y+j)*width+x+i]==pixels[(y+j)*width+x+i] for j in range(h) for i in range(w)):
            result=(2,Node('copy'))
        elif len(set(vals))==1:result=(19,Node('fill',(vals[0],)))
        elif w*h==2:result=(35,Node('literal',vals))
        else:
            choices=[]
            for vertical in (False,True):
                if (vertical and w==1) or (not vertical and h==1):continue
                children=[solve(x+dx,y+dy,a,b) for dx,dy,a,b in halves(w,h,vertical)]
                choices.append((2+int(w>1 and h>1)+sum(c[0] for c in children),Node('vertical' if vertical else 'horizontal',children=tuple(c[1] for c in children))))
            result=min(choices,key=lambda v:v[0])
        memo[key]=result
        return result
    return solve(0,0,width,height)[1]


def node_cost(node:Node,width:int,height:int) -> int:
    if node.kind=='copy':return 2
    if node.kind=='motion':return 10
    if node.kind=='fill':return 19
    if node.kind=='add':return 26 if width*height==2 else 27
    if node.kind=='literal':return 35
    return 2+int(width>1 and height>1)+sum(node_cost(child,w,h) for child,(_,_,w,h) in zip(node.children,halves(width,height,node.kind=='vertical'),strict=True))


def replace_delta_pixels(parsed:dict,previous:list[int],desired:list[int]) -> tuple[tuple[Node,...],int]:
    """Preserve unaffected leaves, including motion references, then minimize
    only changed subtrees. Rebuilding an entire 8×8 block for a changed 1×2
    leaf wastes the ROM's bounded packet budget and is intentionally avoided.
    """
    width,height=parsed['width'],parsed['height']
    if len(desired)!=width*height:raise KhcomError('delta_edit_size','Frame desejado não corresponde às dimensões.')
    decoded=decode_delta(parsed,previous)
    def block(p,x,y,w,h):return [p[(y+j)*width+x+i] for j in range(h) for i in range(w)]
    def replace(n,x,y,w,h):
        target=block(desired,x,y,w,h)
        if target==block(decoded,x,y,w,h):return n
        alternative=encode_pixels(target,block(previous,x,y,w,h),w,h)
        if n.children:
            children=tuple(replace(child,x+dx,y+dy,a,b) for child,(dx,dy,a,b) in zip(n.children,halves(w,h,n.kind=='vertical'),strict=True))
            preserved=Node(n.kind,children=children)
            if node_cost(preserved,w,h)<node_cost(alternative,w,h):return preserved
        return alternative
    nodes=tuple(replace(n,i%(width//8)*8,i//(width//8)*8,8,8) for i,n in enumerate(parsed['nodes']))
    return nodes,sum(a!=b for a,b in zip(nodes,parsed['nodes'],strict=True))


def decode_keyframe(packet: bytes, width=240, height=160) -> list[int]:
    dimensions(width,height)
    if width%16 or height%16 or len(packet)!=(width//16)*(height//16)*8:
        raise KhcomError('keyframe_size', 'Keyframe não corresponde à grade 16×16.')
    output=[0]*(width*height)
    at=0
    for by in range(0,height,16):
        for bx in range(0,width,16):
            a,b,selectors=struct.unpack_from('<HHI',packet,at);at+=8
            palette=keyframe_palette(a,b)
            for i in range(16):output[(by+(i//4)*4)*width+bx+(i%4)*4]=palette[(selectors>>(i*2))&3]

    def interpolate(a,b,mask=0x7bdf,rounding=0x420):
        aa,bb=a&mask,b&mask
        middle=((aa+bb)>>1)|(a&rounding)
        first=((aa+(middle&mask))>>1)|(a&rounding)
        third=(((middle&mask)+bb)>>1)|(b&rounding)
        return first,middle,third

    for y in range(0,height,4):
        for x in range(0,width-4,4):
            i=y*width+x;output[i+1:i+4]=interpolate(output[i],output[i+4])
        i=y*width+width-4;output[i+1:i+4]=[output[i]]*3
    for x in range(0,width,2):
        for y in range(0,height-4,4):
            i=y*width+x
            a=output[i]|(output[i+1]<<16);j=i+width*4;b=output[j]|(output[j+1]<<16)
            for d,v in enumerate(interpolate(a,b,0x7bdf7bdf,0x04200420),1):output[i+width*d],output[i+width*d+1]=v&65535,v>>16
        i=(height-4)*width+x
        for d in range(1,4):output[i+width*d:i+width*d+2]=output[i:i+2]
    return output


def paint_keyframe_selectors(packet: bytes,pixels: list[int],rectangle,width=240,height=160) -> bytes:
    """Quantize changed 4×4 anchors against each original keyframe palette.

    Endpoint bytes and all outside selectors remain exact. Interpolation can
    affect the three pixels preceding a changed anchor, which callers must
    include in their edit footprint. This is deliberately a lossy keyframe edit.
    """
    decode_keyframe(packet,width,height)
    if len(pixels)!=width*height:raise KhcomError('keyframe_pixels','Frame de edição inválido.')
    result=bytearray(packet)
    for by in range(0,height,16):
        for bx in range(0,width,16):
            offset=((by//16)*(width//16)+bx//16)*8
            a,b,selectors=struct.unpack_from('<HHI',packet,offset);palette=keyframe_palette(a,b)
            for i in range(16):
                x,y=bx+(i%4)*4,by+(i//4)*4
                if rectangle[0]<=x<rectangle[2] and rectangle[1]<=y<rectangle[3]:
                    color=pixels[y*width+x]
                    chosen=min(range(4),key=lambda v:sum((((palette[v]>>s)&31)-((color>>s)&31))**2 for s in (0,5,10)))
                    selectors=(selectors&~(3<<(i*2)))|(chosen<<(i*2))
            struct.pack_into('<I',result,offset+4,selectors)
    return bytes(result)
