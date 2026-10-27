"""JPEG segment normalization without pixel decompression or image persistence."""
import base64
from .recognition import AnalysisRequest


def sanitized_jpeg(image: AnalysisRequest) -> bytes:
    """Remove APP/EXIF/XMP/IPTC/comments, including between progressive scans.

    No location metadata survives. Pixels are already redrawn/oriented by iOS.
    This checks bounded JPEG structure, not entropy/pixel decoding correctness.
    """
    data = base64.b64decode(image.image_base64, validate=True)
    result = bytearray(b'\xff\xd8')
    offset, scan = 2, False
    while offset < len(data):
        if scan:
            start = offset
            while True:
                marker = data.find(b'\xff', offset)
                if marker < 0 or marker + 1 >= len(data):
                    raise ValueError('Invalid JPEG scan')
                following = data[marker + 1]
                if following == 0 or 0xD0 <= following <= 0xD7:
                    offset = marker + 2
                    continue
                result.extend(data[start:marker])
                offset, scan = marker, False
                break
        if offset + 1 >= len(data) or data[offset] != 255:
            raise ValueError('Invalid JPEG structure')
        while offset + 2 < len(data) and data[offset + 1] == 255:
            offset += 1
        marker = data[offset + 1]
        if marker == 0xD9:
            if offset + 2 != len(data):
                raise ValueError('Trailing JPEG data')
            return bytes(result) + b'\xff\xd9'
        if marker in (0, 0xD8) or 0xD0 <= marker <= 0xD7 or offset + 4 > len(data):
            raise ValueError('Invalid JPEG marker')
        length = int.from_bytes(data[offset + 2:offset + 4], 'big')
        end = offset + 2 + length
        if length < 2 or end > len(data):
            raise ValueError('Invalid JPEG segment')
        if not (0xE0 <= marker <= 0xEF or marker == 0xFE):
            result.extend(data[offset:end])
        scan = marker == 0xDA
        offset = end
    raise ValueError('JPEG end required')
