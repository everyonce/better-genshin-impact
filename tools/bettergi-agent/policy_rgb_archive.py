"""Bounded, lossless recording transport; historical raw RGB/JSONL retain their original meaning."""
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import zlib

RGB192_BYTES = 192 * 192 * 3
PNG_MAX_BYTES = RGB192_BYTES + 8192
RECORDING_MAX_BYTES = 160 * 1024 * 1024
JOURNAL_MAX_DECODED_BYTES = 64 * 1024 * 1024
JOURNAL_MAX_ROWS = 20000
RECORDING_FORMAT = 'gzip-jsonl-png-rgb-v2'
PNG_ENCODING = 'png-rgb24-v1'
JOURNAL_ENCODING = 'gzip-jsonl-v1'
JOURNAL_NAMES = ('frames.jsonl', 'observations.jsonl', 'events.jsonl')
JOURNAL_FOOTER_RESERVE = 32
_RGB_FIELDS = {'file', 'format', 'width', 'height', 'bytes', 'sha256'}
_STORED_FIELDS = {'encoding', 'storedBytes', 'storedSha256'}


def _require(condition, message):
    """Keep malformed storage evidence a deterministic refusal before decoding or replay."""
    if not condition:
        raise ValueError(message)


def _sha(raw):
    """Hash the exact encoded or decoded bytes, without conflating their identities."""
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    """Require one canonical SHA256 string rather than accepting arbitrary metadata."""
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _path(directory, name):
    """Allow exactly one original file under the declared recording directory."""
    root = Path(directory).resolve()
    _require(isinstance(name, str) and Path(name).name == name and name not in ('', '.', '..'),
             'Recording evidence path or size differs')
    candidate = root / name
    path = candidate.resolve()
    _require(path.parent == root and path.name == name and candidate.absolute() == path,
             'Recording evidence path or size differs')
    _require(path.is_file() and path.stat().st_nlink == 1, 'Recording evidence is missing or linked')
    return path


def _bounded(path, maximum):
    """Bound both the initial size and the actual read if the file changes concurrently."""
    _require(type(maximum) is int and maximum > 0 and path.stat().st_size <= maximum,
             'Recording evidence exceeds its byte bound')
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    _require(len(raw) <= maximum, 'Recording evidence exceeds its byte bound')
    return raw


def recording_metadata(directory, recording=None):
    """Bind new-format declarations to the original seal; clean historical recordings stay raw."""
    root = Path(directory)
    seal_path = root / 'recording.json'
    seal = json.loads(_bounded(_path(root, 'recording.json'), 1024 * 1024)) if seal_path.is_file() else {}
    _require(isinstance(seal, dict), 'Invalid recording seal')
    declarations = [seal] + ([recording] if recording is not None else [])
    _require(all(isinstance(value, dict) for value in declarations), 'Invalid recording declaration')
    new = [value.get('recordingFormat') for value in declarations]
    if any(value is not None for value in new):
        _require(all(value == RECORDING_FORMAT for value in new), 'Recording format declaration differs')
        _require(isinstance(seal.get('journalFiles'),dict) and set(seal['journalFiles']) == set(JOURNAL_NAMES),
                 'Compressed journal declarations are incomplete')
        _require(type(seal.get('policyRgbStoredBytes')) is int and seal['policyRgbStoredBytes'] >= 0,
                 'Stored policy RGB byte count is missing')
        if recording is not None:
            _require(all(json.dumps(recording.get(key),sort_keys=True,allow_nan=False)
                         == json.dumps(seal.get(key),sort_keys=True,allow_nan=False) for key in
                         ('journalFiles', 'policyRgbStoredBytes')), 'Recording transport seal differs from the report')
        _require(not any((root / name).exists() for name in JOURNAL_NAMES), 'Mixed raw and compressed recording journals')
    else:
        _require(not any('journalFiles' in value or 'policyRgbStoredBytes' in value for value in declarations)
                 and not any((root / (name + '.gz')).exists() for name in JOURNAL_NAMES),
                 'Historical recording retains undeclared compressed evidence')
    return seal


def recording_journal_path(directory, logical_name):
    """Resolve a logical journal using its explicit seal, never an extension fallback."""
    _require(logical_name in JOURNAL_NAMES, 'Unknown recording journal')
    seal = recording_metadata(directory)
    return _path(directory, logical_name + ('.gz' if seal.get('recordingFormat') == RECORDING_FORMAT else ''))


def recording_journal_decoded_size(directory, logical_name):
    """Reserve aggregate replay memory using logical bytes, not small compressed-file sizes."""
    _require(logical_name in JOURNAL_NAMES, 'Unknown recording journal')
    seal = recording_metadata(directory)
    if seal.get('recordingFormat') != RECORDING_FORMAT:
        return _path(directory,logical_name).stat().st_size
    size = seal['journalFiles'][logical_name].get('bytes')
    _require(type(size) is int and 0 <= size <= JOURNAL_MAX_DECODED_BYTES, 'Invalid decoded journal byte count')
    return size


def _journal_data(directory, logical_name, max_decoded_bytes, max_rows, *, retain_rows=False):
    """Verify a complete gzip member and its two hashes before exposing any replay rows."""
    _require(type(max_decoded_bytes) is int and 0 < max_decoded_bytes <= RECORDING_MAX_BYTES
             and type(max_rows) is int and max_rows > 0, 'Invalid recording decode bound')
    _require(logical_name in JOURNAL_NAMES, 'Unknown recording journal')
    seal = recording_metadata(directory)
    if seal.get('recordingFormat') != RECORDING_FORMAT:
        raw = _bounded(_path(directory, logical_name), max_decoded_bytes)
    else:
        max_decoded_bytes = min(max_decoded_bytes,JOURNAL_MAX_DECODED_BYTES)
        max_rows = min(max_rows,JOURNAL_MAX_ROWS)
        reference = seal['journalFiles'][logical_name]
        _require(isinstance(reference, dict)
                 and set(reference) == {'file', 'encoding', 'bytes', 'sha256', 'storedBytes', 'storedSha256', 'rows'}
                 and reference['file'] == logical_name + '.gz' and reference['encoding'] == JOURNAL_ENCODING
                 and type(reference['bytes']) is int and 0 <= reference['bytes'] <= max_decoded_bytes
                 and type(reference['storedBytes']) is int and 0 < reference['storedBytes'] <= RECORDING_MAX_BYTES
                 and type(reference['rows']) is int and 0 <= reference['rows'] <= max_rows
                 and _digest(reference['sha256']) and _digest(reference['storedSha256']),
                 'Invalid compressed journal reference')
        encoded = _bounded(_path(directory, reference['file']), reference['storedBytes'])
        _require(len(encoded) == reference['storedBytes'] and _sha(encoded) == reference['storedSha256'],
                 'Compressed journal bytes changed')
        decoder = zlib.decompressobj(31)
        try:
            raw = decoder.decompress(encoded, max_decoded_bytes + 1)
        except zlib.error as error:
            raise ValueError('Compressed journal is corrupt or incomplete') from error
        _require(len(raw) <= max_decoded_bytes and decoder.eof and not decoder.unused_data
                 and not decoder.unconsumed_tail, 'Compressed journal is truncated, concatenated, or exceeds its decode bound')
        _require(len(raw) == reference['bytes'] and _sha(raw) == reference['sha256'],
                 'Decoded journal bytes changed')
    lines = raw.splitlines()
    _require(len(lines) <= max_rows, 'Recording journal row bound exceeded')
    if seal.get('recordingFormat') == RECORDING_FORMAT:
        _require((not raw or raw.endswith(b'\n')) and all(line.strip() for line in lines)
                 and len(lines) == seal['journalFiles'][logical_name]['rows'], 'Compressed journal row coverage differs')
    rows = []
    validate_rows = logical_name in ('events.jsonl', 'frames.jsonl')
    if validate_rows or retain_rows:
        for line in lines:
            if not line.strip():
                continue
            row = json.loads(line)
            if retain_rows:
                rows.append(row)
            if not validate_rows:
                continue
            _require(isinstance(row,dict), 'Invalid recording journal row')
            declared = seal.get('recordingFormat') == RECORDING_FORMAT
            if logical_name == 'events.jsonl' and row.get('type') == 'episodeStart':
                if declared:
                    _require(row.get('recordingFormat') == RECORDING_FORMAT, 'Initial episode omitted its recording format')
                else:
                    _require('recordingFormat' not in row, 'Historical journal retains an undeclared recording format')
            if logical_name == 'frames.jsonl' and isinstance(row.get('policyRgb'),dict):
                reference = row['policyRgb']
                _require((reference.get('encoding') == PNG_ENCODING) == declared
                         and (declared or not (_STORED_FIELDS & reference.keys())),
                         'Policy RGB reference differs from the journal recording format')
    return raw, rows


def read_recording_jsonl(directory, logical_name, *, max_decoded_bytes=JOURNAL_MAX_DECODED_BYTES, max_rows=JOURNAL_MAX_ROWS):
    """Return ordered original dictionaries and the decoded journal SHA256 under explicit bounds."""
    # Reuse the dictionaries already parsed for format validation. Transport and
    # every row remain validated before any result escapes this call.
    raw, rows = _journal_data(directory, logical_name, max_decoded_bytes, max_rows, retain_rows=True)
    _require(all(isinstance(row, dict) for row in rows), 'Invalid recording journal row')
    return rows, _sha(raw)


def open_recording_jsonl(path, *, max_decoded_bytes=JOURNAL_MAX_DECODED_BYTES, max_rows=JOURNAL_MAX_ROWS):
    """Provide the original UTF8 lines for existing streaming readers after bounded transport validation."""
    path = Path(path)
    name = path.name.removesuffix('.gz')
    _require(name in JOURNAL_NAMES and path.name in (name,recording_journal_path(path.parent,name).name),
             'Recording journal path differs from its declared transport')
    raw, _ = _journal_data(path.parent, name, max_decoded_bytes, max_rows)
    return io.StringIO(raw.decode('utf-8'))


class RecordingJournal:
    """One lossless gzip member; only the recorder worker serializes, compresses, and writes."""
    def __init__(self, directory, logical_name, reserve=None):
        _require(logical_name in JOURNAL_NAMES, 'Unknown recording journal')
        self.name = logical_name + '.gz'
        self.stream = (Path(directory) / self.name).open('xb')
        self.encoder = zlib.compressobj(1, zlib.DEFLATED, 31)
        self.reserve = reserve
        self.decoded_digest = hashlib.sha256()
        self.stored_digest = hashlib.sha256()
        self.decoded_bytes = self.stored_bytes = self.rows = 0
        self.closed = False

    def __enter__(self):
        """Let the recorder close every opened journal even when later setup fails."""
        return self

    def __exit__(self, _kind, error, _traceback):
        """Retain the original exception while still attempting footer and handle cleanup."""
        try:
            self.close()
        except Exception as cleanup:
            if error is not None:
                raise RuntimeError(f'{error}; journal cleanup failed: {cleanup}') from error
            raise

    def write(self, text):
        """Reserve physical bytes before a complete row and commit compressor state only after writing."""
        _require(not self.closed and isinstance(text, str) and text.endswith('\n') and text.count('\n') == 1,
                 'Journal writes require one complete original JSONL row')
        raw = text.encode('utf-8')
        # The measured 35-second crop-rich scout journal needs about 42 MB.
        # Keep finite replay bounds independent of the compressed 160 MiB session cap.
        _require(self.decoded_bytes + len(raw) <= JOURNAL_MAX_DECODED_BYTES and self.rows < JOURNAL_MAX_ROWS,
                 'Recording journal exceeds its bounded decoded size or row count')
        candidate = self.encoder.copy()
        encoded = candidate.compress(raw) + candidate.flush(zlib.Z_SYNC_FLUSH)
        if self.reserve is not None:
            self.reserve(len(encoded))
        self.stream.write(encoded)
        self.encoder = candidate
        self.decoded_digest.update(raw)
        self.stored_digest.update(encoded)
        self.decoded_bytes += len(raw)
        self.stored_bytes += len(encoded)
        self.rows += 1

    def flush(self):
        """Flush already compressed complete rows without ending their shared dictionary."""
        self.stream.flush()

    def tell(self):
        """Return physical bytes, unlike GzipFile.tell(), which counts decoded bytes."""
        return self.stored_bytes

    def reference(self):
        """Expose independently checkable encoded and decoded identities after closure."""
        _require(self.closed, 'Journal transport has not closed')
        return dict(file=self.name, encoding=JOURNAL_ENCODING, bytes=self.decoded_bytes,
                    sha256=self.decoded_digest.hexdigest(), storedBytes=self.stored_bytes,
                    storedSha256=self.stored_digest.hexdigest(), rows=self.rows)

    def close(self):
        """Finalize within the pre-reserved footer budget and always close the file handle."""
        if self.closed:
            return
        try:
            footer = self.encoder.flush(zlib.Z_FINISH)
            _require(len(footer) <= JOURNAL_FOOTER_RESERVE, 'Journal footer exceeds its reserved budget')
            self.stream.write(footer)
            self.stored_digest.update(footer)
            self.stored_bytes += len(footer)
            self.stream.flush()
        finally:
            self.stream.close()
            self.closed = True


def policy_rgb_filename(index, frame_id, encoding=None):
    """Bind both native source identity and contiguous video index to the selected exact-pixel format."""
    _require(type(index) is int and 0 <= index < 100000000 and type(frame_id) is int and 0 <= frame_id < 1000000000000,
             'Invalid policy RGB frame index')
    _require(encoding in (None, PNG_ENCODING), 'Unknown policy RGB encoding')
    return f'policy-{index:08d}-frame-{frame_id:012d}.rgb' + ('.png' if encoding else '')


def write_policy_rgb(directory, index, metadata, pixels, *, encoding=None, reserve=None):
    """Encode only on the writer; retain the historical raw default for original callers and fixtures."""
    if (metadata['width'], metadata['height']) != (192, 192) or type(pixels) is not bytes or len(pixels) != RGB192_BYTES:
        raise ValueError('Exact policy retention requires immutable complete RGB192 bytes')
    name = policy_rgb_filename(index, metadata['frameId'], encoding)
    encoded = pixels
    if encoding == PNG_ENCODING:
        from PIL import Image
        output = io.BytesIO()
        with Image.frombytes('RGB', (192, 192), pixels) as image:
            image.save(output, format='PNG', compress_level=6, optimize=False)
        encoded = output.getvalue()
        _require(len(encoded) <= PNG_MAX_BYTES, 'Encoded policy RGB exceeds its bound')
    reference = dict(file=name, format='rgb24', width=192, height=192, bytes=len(pixels), sha256=_sha(pixels))
    if encoding is not None:
        reference.update(encoding=encoding, storedBytes=len(encoded), storedSha256=_sha(encoded))
    if reserve is not None:
        reserve(len(encoded))
    with (Path(directory) / name).open('xb') as output:
        output.write(encoded)
    return reference


def _decode_png(encoded):
    """Accept only the bounded RGB8 PNG subset emitted here, including exact CRC and stream termination."""
    _require(encoded.startswith(b'\x89PNG\r\n\x1a\n'), 'Invalid policy RGB PNG signature')
    offset = 8
    chunks = []
    compressed = []
    while offset < len(encoded):
        _require(offset + 12 <= len(encoded), 'Truncated policy RGB PNG chunk')
        length = struct.unpack_from('>I', encoded, offset)[0]
        kind = encoded[offset + 4:offset + 8]
        end = offset + 12 + length
        _require(end <= len(encoded) and kind in (b'IHDR', b'IDAT', b'IEND'), 'Unsupported policy RGB PNG chunk')
        data = encoded[offset + 8:offset + 8 + length]
        _require(zlib.crc32(kind + data) & 0xffffffff == struct.unpack_from('>I', encoded, end - 4)[0],
                 'Policy RGB PNG checksum changed')
        chunks.append(kind)
        if kind == b'IHDR':
            _require(chunks == [b'IHDR'] and data == struct.pack('>IIBBBBB', 192, 192, 8, 2, 0, 0, 0),
                     'Policy RGB PNG dimensions or color format changed')
        elif kind == b'IDAT':
            _require(chunks[0] == b'IHDR' and b'IEND' not in chunks, 'Policy RGB PNG chunk order changed')
            compressed.append(data)
        else:
            _require(length == 0 and end == len(encoded) and compressed, 'Policy RGB PNG has trailing or missing data')
        offset = end
    _require(chunks and chunks[-1] == b'IEND', 'Policy RGB PNG is incomplete')
    expected = (192 * 3 + 1) * 192
    decoder = zlib.decompressobj()
    try:
        scanlines = decoder.decompress(b''.join(compressed), expected + 1)
    except zlib.error as error:
        raise ValueError('Policy RGB PNG data is corrupt') from error
    _require(len(scanlines) == expected and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
             'Policy RGB PNG exceeds its exact decoded bound')
    from PIL import Image
    with Image.open(io.BytesIO(encoded)) as image:
        _require(image.mode == 'RGB' and image.size == (192, 192), 'Policy RGB PNG geometry changed')
        return image.tobytes()


def _read_policy_rgb(directory, reference, *, index=None, frame_id=None, recording=None):
    """Validate storage, decode bounds and exact pixels once for both public verification APIs."""
    _require(isinstance(reference, dict) and reference.get('encoding') in (None, PNG_ENCODING),
             'Invalid exact policy RGB reference')
    encoding = reference.get('encoding')
    _require(set(reference) == _RGB_FIELDS | (_STORED_FIELDS if encoding else set())
             and reference.get('format') == 'rgb24'
             and all(type(reference.get(key)) is int and reference[key] == value
                     for key, value in (('width', 192), ('height', 192), ('bytes', RGB192_BYTES)))
             and _digest(reference.get('sha256')), 'Invalid exact policy RGB reference')
    if index is not None or frame_id is not None:
        _require(reference['file'] == policy_rgb_filename(index, frame_id, encoding), 'Policy RGB filename differs from its frame/index')
    if recording is not None:
        seal = recording_metadata(directory, recording)
        _require((encoding == PNG_ENCODING) == (seal.get('recordingFormat') == RECORDING_FORMAT),
                 'Policy RGB encoding differs from its recording declaration')
    path = _path(directory, reference['file'])
    _require(str(path).endswith('.rgb.png' if encoding else '.rgb'), 'Exact policy RGB path or size differs')
    if encoding:
        _require(type(reference['storedBytes']) is int and 0 < reference['storedBytes'] <= PNG_MAX_BYTES
                 and _digest(reference['storedSha256']), 'Invalid stored policy RGB reference')
        encoded = _bounded(path, reference['storedBytes'])
        _require(len(encoded) == reference['storedBytes'] and _sha(encoded) == reference['storedSha256'],
                 'Stored policy RGB bytes changed')
        raw = _decode_png(encoded)
    else:
        _require(path.stat().st_size == RGB192_BYTES, 'Exact policy RGB path or size differs')
        raw = _bounded(path, RGB192_BYTES)
    _require(len(raw) == RGB192_BYTES and _sha(raw) == reference['sha256'], 'Exact policy RGB bytes changed')
    return path, raw


def read_policy_rgb(directory, reference, *, index=None, frame_id=None, recording=None):
    """Return immutable exact RGB192 bytes for either explicitly declared storage format."""
    return _read_policy_rgb(directory, reference, index=index, frame_id=frame_id, recording=recording)[1]


def verify_policy_rgb_file(directory, reference, *, index=None, frame_id=None, recording=None):
    """Verify decoded pixels and return the encoded evidence path for physical-file manifests."""
    return _read_policy_rgb(directory, reference, index=index, frame_id=frame_id, recording=recording)[0]


def verify_policy_rgb(directory, reference):
    """Preserve the historical raw-path API; encoded files require an explicit decoded-byte reader."""
    _require(isinstance(reference, dict) and 'encoding' not in reference,
             'Encoded policy RGB requires read_policy_rgb')
    return _read_policy_rgb(directory, reference)[0]
