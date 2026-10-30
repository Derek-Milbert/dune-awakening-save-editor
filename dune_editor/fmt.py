"""Codec for the Dune: Awakening property container format.

Every value is introduced by a tag byte T:  hi = T >> 4, lo = T & 15.

  lo 7  string         lo 3  integer (decimal text)         lo 5  float (decimal text)
  lo 8  long string (escaped JSON text, e.g. the character appearance descriptor)
        payload length n = hi        if hi < 12
                           next u8   if hi == 12 (0xc?)
                           next u16  if hi == 13 (0xd?, big endian)
                           next u32  if hi == 14 (0xe?, big endian)
  lo 12 (0xc) struct   -> payload is  key,value,key,value ...   (keys are strings)
  lo 11 (0xb) array    -> payload is  value,value,...
        payload byte-size encoded exactly like a scalar length above
  lo 1 / 2   boolean   (single byte, 1 and 2)

Integers and floats are kept as the original text so a decode/encode round trip is lossless.
"""
from __future__ import annotations


class FormatError(Exception):
    pass


class LongKey(str):
    """A struct key stored as a long string (tag lo-nibble 8), e.g. (TagName="Skills.Perk.X")."""


class Node:
    __slots__ = ('kind', 'value')
    # kind: 's' string, 'i' int, 'f' float, 'b' bool(1|2), 'S' struct [(key, Node)], 'A' array [Node]

    def __init__(self, kind, value):
        self.kind = kind
        self.value = value

    def __repr__(self):
        return f'Node({self.kind!r}, {self.value!r})'

    # ---- convenience --------------------------------------------------
    def get(self, key):
        """First value of a struct key, or None."""
        if self.kind != 'S':
            return None
        for k, v in self.value:
            if k == key:
                return v
        return None

    def set_scalar(self, key, text):
        node = self.get(key)
        if node is None:
            raise KeyError(key)
        node.value = str(text)

    def to_py(self):
        if self.kind == 'S':
            return {'__struct__': [(k, v.to_py()) for k, v in self.value]}
        if self.kind == 'A':
            return [v.to_py() for v in self.value]
        if self.kind == 'i':
            return int(self.value)
        if self.kind == 'f':
            return float(self.value)
        return self.value


def _read_len(b, i, hi):
    if hi < 12:
        return hi, i
    if hi == 12:
        return b[i], i + 1
    if hi == 13:
        return int.from_bytes(b[i:i + 2], 'big'), i + 2
    if hi == 14:
        return int.from_bytes(b[i:i + 4], 'big'), i + 4
    raise FormatError(f'bad length nibble {hi:#x} at {i}')


def _write_len(n):
    """Return (hi nibble, extra length bytes) for payload length n."""
    if n < 12:
        return n, b''
    if n < 256:
        return 12, bytes([n])
    if n < 65536:
        return 13, n.to_bytes(2, 'big')
    return 14, n.to_bytes(4, 'big')


def decode_value(b: bytes, i: int):
    """Decode one value at offset i -> (Node, next offset)."""
    t = b[i]
    hi, lo = t >> 4, t & 15
    i += 1
    if lo in (1, 2) and hi == 0:
        return Node('b', lo), i
    if lo in (3, 5, 7, 8):
        n, i = _read_len(b, i, hi)
        raw = b[i:i + n]
        if len(raw) != n:
            raise FormatError('truncated scalar')
        i += n
        text = raw.decode('utf-8')
        return Node({3: 'i', 5: 'f', 7: 's', 8: 'j'}[lo], text), i
    if lo in (11, 12):
        n, i = _read_len(b, i, hi)
        end = i + n
        if end > len(b):
            raise FormatError(f'container overruns data at {i}')
        items = []
        while i < end:
            if lo == 12:
                kpos = i
                knode, i = decode_value(b, i)
                if knode.kind not in ('s', 'j'):
                    raise FormatError(f'struct key is not a string at offset {kpos}: {b[kpos:kpos + 40]!r}')
                vnode, i = decode_value(b, i)
                key = LongKey(knode.value) if knode.kind == 'j' else knode.value
                items.append((key, vnode))
            else:
                vnode, i = decode_value(b, i)
                items.append(vnode)
        if i != end:
            raise FormatError('container size mismatch')
        return Node('S' if lo == 12 else 'A', items), end
    raise FormatError(f'unknown tag {t:#04x} at {i - 1}')


def encode_value(node: Node) -> bytes:
    k = node.kind
    if k == 'b':
        return bytes([node.value])
    if k in ('i', 'f', 's', 'j'):
        raw = str(node.value).encode('utf-8')
        hi, extra = _write_len(len(raw))
        return bytes([(hi << 4) | {'i': 3, 'f': 5, 's': 7, 'j': 8}[k]]) + extra + raw
    if k == 'S':
        body = b''.join(
            encode_value(Node('j' if isinstance(key, LongKey) else 's', key)) + encode_value(v)
            for key, v in node.value)
        lo = 12
    elif k == 'A':
        body = b''.join(encode_value(v) for v in node.value)
        lo = 11
    else:
        raise FormatError(f'cannot encode kind {k}')
    hi, extra = _write_len(len(body))
    return bytes([(hi << 4) | lo]) + extra + body


def decode(b: bytes) -> Node:
    node, end = decode_value(b, 0)
    if end != len(b):
        raise FormatError(f'{len(b) - end} trailing bytes')
    return node


def encode(node: Node) -> bytes:
    return encode_value(node)


def find_all(node: Node, key: str, path=()):
    """Yield (path, value Node) for every struct key == key anywhere in the tree."""
    if node.kind == 'S':
        for k, v in node.value:
            if k == key:
                yield path + (k,), v
            yield from find_all(v, key, path + (k,))
    elif node.kind == 'A':
        for idx, v in enumerate(node.value):
            yield from find_all(v, key, path + (idx,))
