"""Minimal TIFF header reader — no rasterio/GDAL required.

Works for GeoTIFF. Parses TIFF IFD tags directly to pull out:
  - image width, height
  - bits per sample, sample format
  - NoData value
  - GDAL_NODATA ASCII tag (if present)
  - GeoKeyDirectoryTag + ModelPixelScaleTag (to sniff the CRS)
"""
import struct
import sys

TAG_IMAGE_WIDTH       = 256
TAG_IMAGE_LENGTH      = 257
TAG_BITS_PER_SAMPLE   = 258
TAG_SAMPLE_FORMAT     = 339
TAG_GDAL_NODATA       = 42113
TAG_MODEL_PIXEL_SCALE = 33550
TAG_MODEL_TIEPOINT    = 33922
TAG_GEO_KEY_DIR       = 34735

TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}


def read_ifd(f, offset, endian):
    f.seek(offset)
    count = struct.unpack(endian + "H", f.read(2))[0]
    tags = {}
    for _ in range(count):
        entry = f.read(12)
        tag, typ, n = struct.unpack(endian + "HHI", entry[:8])
        size = TYPE_SIZES.get(typ, 1) * n
        if size <= 4:
            raw = entry[8:8 + size]
        else:
            ptr = struct.unpack(endian + "I", entry[8:12])[0]
            here = f.tell()
            f.seek(ptr)
            raw = f.read(size)
            f.seek(here)
        tags[tag] = (typ, n, raw)
    next_ifd = struct.unpack(endian + "I", f.read(4))[0]
    return tags, next_ifd


def decode(tags, tag):
    if tag not in tags:
        return None
    typ, n, raw = tags[tag]
    if typ == 2:  # ASCII
        return raw.rstrip(b"\x00").decode("ascii", "replace")
    if typ == 3:  # SHORT
        return struct.unpack("<" + "H" * n, raw)
    if typ == 4:  # LONG
        return struct.unpack("<" + "I" * n, raw)
    if typ == 5:  # RATIONAL
        vals = struct.unpack("<" + "I" * (2 * n), raw)
        return [(vals[i], vals[i + 1]) for i in range(0, 2 * n, 2)]
    if typ == 12:  # DOUBLE
        return struct.unpack("<" + "d" * n, raw)
    return raw


def main(path):
    with open(path, "rb") as f:
        header = f.read(8)
        if header[:2] == b"II":
            endian = "<"
        elif header[:2] == b"MM":
            endian = ">"
        else:
            raise SystemExit("Not a TIFF file")
        magic = struct.unpack(endian + "H", header[2:4])[0]
        if magic != 42:
            raise SystemExit(f"Unexpected TIFF magic: {magic}")
        first_ifd = struct.unpack(endian + "I", header[4:8])[0]
        tags, _ = read_ifd(f, first_ifd, endian)

    w = decode(tags, TAG_IMAGE_WIDTH)
    h = decode(tags, TAG_IMAGE_LENGTH)
    bits = decode(tags, TAG_BITS_PER_SAMPLE)
    fmt = decode(tags, TAG_SAMPLE_FORMAT)
    nodata = decode(tags, TAG_GDAL_NODATA)
    scale = decode(tags, TAG_MODEL_PIXEL_SCALE)
    tie = decode(tags, TAG_MODEL_TIEPOINT)
    geokeys = decode(tags, TAG_GEO_KEY_DIR)

    print(f"File:          {path}")
    print(f"Size (WxH):    {w} x {h}")
    print(f"Bits/Sample:   {bits}")
    print(f"SampleFormat:  {fmt}   (1=uint, 2=int, 3=float)")
    print(f"GDAL_NODATA:   {nodata!r}")
    print(f"PixelScale:    {scale}")
    print(f"TiePoint:      {tie}")

    if geokeys and len(geokeys) >= 4:
        _, _, _, nkeys = geokeys[:4]
        print(f"GeoKeys:       {nkeys} key(s)")
        i = 4
        for _ in range(nkeys):
            key_id, tag_loc, count, value = geokeys[i:i + 4]
            i += 4
            if key_id == 2048:
                print(f"  GeographicType: {value}  (4326 = WGS84)")
            elif key_id == 3072:
                print(f"  ProjectedCSType: {value}")
            elif key_id == 1024:
                print(f"  GTModelType: {value}  (1=projected, 2=geographic)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/raw/RW/population.tif")