"""One worker's bounded immutable-file admission; no native, model or input operations."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time


MAX_FILES = 2304
MAX_FILE_BYTES = 32 * 1024 * 1024
# R73 has 16 retained native generations; run39 measured 407.72 MiB across 1,809 pinned paths.
# Keep a finite 448 MiB aggregate while preserving every per-file, census and fresh-hash check.
MAX_TOTAL_BYTES = 448 * 1024 * 1024


def require(value, message):
    """Reject incomplete file authority instead of falling back to an unlocked cache."""
    if not value:
        raise ValueError(message)


def canonical(value):
    """Bind detached JSON context without relying on object serialization order."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def source_reader(path, flags):
    """Use the cleared V4 reader: allow other readers, deny writes and deletion."""
    import _winapi
    import msvcrt
    handle = _winapi.CreateFile(path, 0x80000000, 1, 0, 3, 0x00200080, 0)
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException as error:
        try:
            _winapi.CloseHandle(handle)
        except BaseException as cleanup_error:
            raise HandleCleanupError(error, [str(path) + ': ' + str(cleanup_error)]) from error
        raise


def file_identity(info):
    """Keep inode/volume/size distinct from fresh content verification."""
    return info.st_dev, info.st_ino, info.st_size


class HandleCleanupError(ValueError):
    """Preserve failed partial retirement even before a capability can transfer to the worker."""
    def __init__(self, original, errors):
        """Carry the primary failure and every known handle-close error into terminal accounting."""
        self.cleanup_errors = list(getattr(original, 'cleanup_errors', ())) + list(errors)
        super().__init__(str(original) + '; immutable handle cleanup: ' + '; '.join(errors))


class HeldFiles:
    """Own read-sharing-only handles and rehash their current bytes before one admission."""
    def __init__(self, pins, *, empty_sources=()):
        """Acquire the complete bounded set while paused, closing every partial acquisition."""
        self.rows = {}
        self.directories = {}
        self.closed = False
        self.empty_sources = frozenset(Path(path).absolute() for path in empty_sources)
        require(isinstance(pins, dict) and 0 < len(pins) <= MAX_FILES, 'Invalid immutable file census')
        normalized = {}
        for name, digest in pins.items():
            path = Path(name).absolute()
            require(not str(path).startswith(('\\\\', '//')) and path.resolve(strict=True) == path
                and isinstance(digest, str) and re.fullmatch('[a-f0-9]{64}', digest), 'Unsafe immutable file or pin')
            require(path not in normalized or normalized[path] == digest, 'Conflicting immutable file pins')
            normalized[path] = digest
        require(self.empty_sources <= set(normalized)
            and all(path.suffix == '.py' for path in self.empty_sources), 'Empty bytes are limited to declared Python sources')
        try:
            total = 0
            for path, digest in sorted(normalized.items(), key=lambda row: str(row[0])):
                stream = open(path, 'rb', opener=source_reader)
                try:
                    os.set_inheritable(stream.fileno(), False)
                    info = os.fstat(stream.fileno())
                    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                        and (info.st_size > 0 or path in self.empty_sources)
                        and info.st_size <= MAX_FILE_BYTES, 'Linked, empty or unbounded immutable file')
                    total += info.st_size
                    require(total <= MAX_TOTAL_BYTES, 'Immutable file byte budget exceeded')
                    self.rows[path] = (stream, file_identity(info), digest)
                except BaseException as error:
                    try:
                        stream.close()
                    except BaseException as cleanup_error:
                        raise HandleCleanupError(error, [str(path) + ': ' + str(cleanup_error)]) from error
                    raise
                # A parent rename/junction substitution must not turn a held inode into a path-only cache.
                for directory in path.parents:
                    if directory not in self.directories:
                        info = directory.stat(follow_symlinks=False)
                        require(stat.S_ISDIR(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                            'Redirected immutable parent directory')
                        self.directories[directory] = (info.st_dev, info.st_ino)
            self.verify()
        except BaseException as error:
            errors = self.close()
            if errors:
                raise HandleCleanupError(error, errors) from error
            raise

    def verify(self):
        """Freshly read every held byte; retain path identity without repeated full-path resolution."""
        require(not self.closed, 'Immutable handles are retired')
        for path, identity in self.directories.items():
            info = path.stat(follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == identity
                and not getattr(info, 'st_file_attributes', 0) & 0x400, 'Immutable parent namespace changed')
        actual, total = {}, 0
        for path, (stream, identity, expected) in self.rows.items():
            info, current = os.fstat(stream.fileno()), path.stat(follow_symlinks=False)
            require(file_identity(info) == file_identity(current) == identity
                and stat.S_ISREG(current.st_mode) and info.st_nlink == current.st_nlink == 1
                and not getattr(current, 'st_file_attributes', 0) & 0x400
                and not os.get_inheritable(stream.fileno()), 'Immutable file identity or handle changed')
            stream.seek(0)
            raw = stream.read(info.st_size + 1)
            digest = hashlib.sha256(raw).hexdigest()
            require(len(raw) == info.st_size and digest == expected, 'Immutable held bytes changed: ' + str(path))
            actual[str(path)] = digest
            total += len(raw)
        require(total <= MAX_TOTAL_BYTES, 'Immutable file byte budget changed')
        return actual, total

    def close(self):
        """Attempt every close and retain all failures without replacing the original exception."""
        errors = []
        for path, (stream, identity, digest) in reversed(list(self.rows.items())):
            try:
                stream.close()
            except BaseException as error:
                errors.append(str(path) + ': ' + str(error))
        self.closed = True
        return errors


def owner_inputs(path, artifacts, validate_owner):
    """Enumerate the current finite owner's complete immutable replay inputs, then validate normally.

    This mirrors only map_owner's explicit R58..R73 evidence names and package-selection rule.
    Its actual reader set is checked by an independent read-trace regression; no new owner is admitted here.
    """
    artifacts = Path(artifacts).resolve()
    pins, packages, seen = {}, {}, set()
    def add(path, maximum=4 * 1024 * 1024):
        """Pin one original byte sequence under the existing artifacts root."""
        path = Path(path).absolute()
        require(path.resolve(strict=True) == path and path.is_relative_to(artifacts), 'Owner source escaped artifacts')
        with path.open('rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 < info.st_size <= maximum,
                'Invalid bounded owner source')
            raw = stream.read(info.st_size + 1)
        require(len(raw) == info.st_size, 'Owner source changed size')
        digest = hashlib.sha256(raw).hexdigest()
        require(str(path) not in pins or pins[str(path)] == digest, 'Owner source changed during collection')
        pins[str(path)] = digest
        return raw
    cursor = Path(path).absolute()
    while cursor.name != 'warm-launcher.json':
        require(cursor.name == 'map-owner-lineage.json' and cursor not in seen and len(seen) < 16,
            'Owner closure exceeds the finite lineage')
        seen.add(cursor)
        receipt = json.loads(add(cursor))
        folder = cursor.parent
        for name in ('before.json', 'preflight.json', 'ensure-child.json'):
            add(folder / name)
        if 'protectedGame' in receipt:
            add(folder / 'game-before.json')
        selected = json.loads(add(folder / 'ensure-child.json'))['selectedPackage']
        target = Path(selected['targetDirectory']).absolute()
        match = re.fullmatch(r'release-r(5[89]|6[0-9]|7[0123])', target.parent.name)
        require(match is not None and target == artifacts / target.parent.name / 'BetterGI-English-win-x64',
            'Unexpected owner package scope')
        number = int(match[1])
        original = artifacts / ('release-r' + str(number))
        present = original.exists()
        release = original if present else artifacts / 'release-retention/package-witnesses' / original.name
        packages[str(original)] = dict(originalPresent=present, selected=str(release))
        add(release / 'build-manifest.json', 65536)
        for extension in ('exe', 'dll'):
            add(release / 'BetterGI-English-win-x64' / ('BetterGI.' + extension), MAX_FILE_BYTES)
        cursor = Path(receipt['prior']).absolute()
    add(cursor)
    add(cursor.with_name('handoff-audit.json'))
    owner = validate_owner(path)
    return owner, pins, packages


class PausedAdmission:
    """Keep one run's semantic precheck and held-byte authority in this worker only."""
    def __init__(self, context, pins, empty_sources, census, expected_census, packages, report):
        """Accept only the caller's completed paused validations, never reconstruct from a ready file."""
        self.context = canonical(context)
        self.census = census
        self.expected_census = copy.deepcopy(expected_census)
        self.packages = copy.deepcopy(packages)
        self.report = report
        self.consumed = False
        self.closed = False
        self.files = HeldFiles(pins, empty_sources=empty_sources)
        report.update(version=1, kind='per-worker-held-immutable-admission-v1',
            preparedAtUnixNs=time.time_ns(), fileCount=len(self.files.rows),
            contextSha256=hashlib.sha256(self.context).hexdigest(),
            immutableFiles={str(path):row[2] for path,row in self.files.rows.items()},
            maximumFiles=MAX_FILES, maximumBytes=MAX_TOTAL_BYTES, maximumFileBytes=MAX_FILE_BYTES,
            denyWriteDelete=True, checkpointContentHeld=False, freshHashReadRequired=True,
            consumed=False, closed=False)

    def consume(self, context, report, liveness):
        """Spend the private capability once, checking STOP around all fresh immutable byte reads."""
        require(not self.closed and not self.consumed and report is self.report, 'Missing, foreign or consumed immutable admission')
        self.consumed = True
        report['consumed'] = True
        require(canonical(context()) == self.context, 'Immutable admission belongs to another run or context')
        liveness()
        require(self.census() == self.expected_census, 'Current source census changed after paused precheck')
        for original, choice in self.packages.items():
            require(Path(original).exists() is choice['originalPresent'], 'Historical package selection changed')
        began = time.perf_counter_ns()
        actual, size = self.files.verify()
        report.update(freshHashBytes=size, freshHashMilliseconds=(time.perf_counter_ns()-began)/1e6)
        require(canonical(context()) == self.context, 'Immutable admission context changed during final reading')
        require(self.census() == self.expected_census, 'Current source census changed during final reading')
        for original, choice in self.packages.items():
            require(Path(original).exists() is choice['originalPresent'], 'Historical package selection changed during final reading')
        liveness()
        return actual

    def close(self):
        """Retire every source handle on success, STOP, failure or unknown native outcome."""
        if self.closed:
            return []
        self.closed = True
        errors = self.files.close()
        self.report.update(closed=not errors, closedAtUnixNs=time.time_ns(), closeErrors=errors)
        return errors
