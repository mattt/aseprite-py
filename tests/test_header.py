from aseprite import Sprite
from aseprite._binary import FILE_MAGIC, FRAME_MAGIC, HEADER_SIZE, Reader


def test_written_header_and_frame() -> None:
    sprite = Sprite(8, 4)
    sprite.add_frame(33)
    data = sprite.to_bytes()
    assert len(data) >= HEADER_SIZE + 16
    header = Reader(data, 0, HEADER_SIZE)
    assert header.u32() == len(data)
    assert header.u16() == FILE_MAGIC
    assert header.u16() == 1
    assert header.u16() == 8
    assert header.u16() == 4
    assert header.u16() == 32
    frame = Reader(data, HEADER_SIZE)
    frame_size = frame.u32()
    assert frame.u16() == FRAME_MAGIC
    assert frame_size >= 16
    assert HEADER_SIZE + frame_size == len(data)
