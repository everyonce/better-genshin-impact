"""Bind combat workers to a direct command or one exact Windows venv redirector."""
import hashlib
import os
from pathlib import Path
import stat


def require(value, message):
    """Refuse unproved ancestry instead of allowing arbitrary broker descendants."""
    if not value:
        raise ValueError(message)


def runtime_contract(resources, reader=None):
    """Pin the selected executable and, only for a real venv, its exact base interpreter."""
    files = {}
    def read(path):
        """Hash a bounded original interpreter/config file, allowing archived replay."""
        path = Path(path).absolute()
        require(path == path.resolve() and not str(path).startswith(('\\\\', '//')), 'Python runtime path is linked or remote')
        if reader is not None:
            raw = reader(path)
        else:
            with path.open('rb') as stream:
                info = os.fstat(stream.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 < info.st_size <= 4 * 1024 * 1024,
                        'Python runtime source is not bounded')
                raw = stream.read(info.st_size + 1)
            require(len(raw) == info.st_size, 'Python runtime source changed while reading')
        require(type(raw) is bytes and 0 < len(raw) <= 4 * 1024 * 1024, 'Python runtime source is not bounded')
        files[str(path)] = hashlib.sha256(raw).hexdigest()
        return raw
    executable = Path(resources['gpuPython']).absolute()
    read(executable)
    cfg = executable.parent.parent / 'pyvenv.cfg'
    # Archived replay determines venv presence from its declared source set;
    # callers never use the current installed cfg to reinterpret history.
    has_cfg = cfg.exists() if reader is None else getattr(reader, 'venv', False)
    if not has_cfg:
        return dict(version=1, kind='direct-python-v1', executable=str(executable), files=files)
    require(executable.parent.name.lower() == 'scripts' and executable.name.lower() == 'python.exe',
            'Only the exact Windows venv Python redirector is supported')
    values = {}
    for line in read(cfg).decode('utf-8-sig').splitlines():
        key, separator, value = line.partition('=')
        if separator:
            require(key.strip() not in values, 'Duplicate Python venv setting')
            values[key.strip()] = value.strip()
    base = Path(values.get('executable', '')).absolute()
    require(base.name.lower() == 'python.exe' and base.parent == Path(values.get('home', '')).absolute()
        and values.get('include-system-site-packages') == 'false' and base != executable,
        'The planned venv base interpreter is ambiguous')
    read(base)
    # The ordinary RDP broker always selects the background pythonw variant.
    runner = Path(resources['runnerPython']).absolute()
    require(runner == base, 'Combat orchestration must use the pinned base Python, not a second venv redirector')
    background = base.with_name('pythonw.exe')
    read(background)
    return dict(version=1, kind='windows-venv-redirector-v1', executable=str(executable),
        baseExecutable=str(base), brokerExecutable=str(background), configuration=str(cfg), files=files)


def worker_ancestry(contract, process_id, parent_id, reader):
    """Read exactly the worker, its parent and (for a venv) the broker while alive."""
    if contract['kind'] != 'windows-venv-redirector-v1':
        return None
    worker, parent = reader(process_id), reader(parent_id)
    require(worker['parentProcessId'] == parent_id and Path(worker['executable']) == Path(contract['baseExecutable']),
            'Live combat worker is not the pinned venv interpreter')
    runner = reader(parent['parentProcessId'])
    chain = [worker, parent, runner]
    validate_chain(chain, contract, worker['windowsSessionId'])
    return chain


def validate_identity(row, session):
    """Require a complete typed native creation/image witness for one exact session."""
    require(isinstance(row, dict) and set(row) == {'processId', 'parentProcessId', 'windowsSessionId',
        'executable', 'startedFileTime'} and all(type(row.get(key)) is int and row[key] > 0 for key in
        ('processId', 'parentProcessId', 'windowsSessionId', 'startedFileTime'))
        and row['windowsSessionId'] == session and isinstance(row.get('executable'), str)
        and Path(row['executable']).is_absolute(), 'Invalid live Windows process identity')


def validate_chain(chain, contract, session):
    """Permit one redirector edge only, with exact images, live times and session joins."""
    require(isinstance(chain, list) and len(chain) == 3 and contract.get('kind') == 'windows-venv-redirector-v1',
            'Missing exact Windows venv ancestry')
    for row in chain:
        validate_identity(row, session)
    worker, shim, runner = chain
    require(len({row['processId'] for row in chain}) == 3
        and worker['parentProcessId'] == shim['processId'] and shim['parentProcessId'] == runner['processId']
        and runner['startedFileTime'] <= shim['startedFileTime'] <= worker['startedFileTime']
        and Path(worker['executable']) == Path(contract['baseExecutable'])
        and Path(shim['executable']) == Path(contract['executable'])
        and Path(runner['executable']) == Path(contract['brokerExecutable']), 'Windows venv ancestry differs from the pinned runtime')


def verify_worker_broker(worker, broker, contract=None):
    """Keep old direct-parent replay strict; new venv runs require the broker's original command identity."""
    command = broker.get('commandIdentity')
    if contract is None:
        require(not any(key in worker for key in ('processIdentity', 'launchAncestry'))
            and not any(key in broker for key in ('commandIdentity', 'commandProcessId')),
            'Undeclared process witnesses cannot select historical replay')
        require(worker.get('parentProcessId') == broker.get('runnerProcessId'),
                'Historical worker is not the original direct broker child')
        return
    require(isinstance(contract, dict) and contract.get('kind') in ('direct-python-v1', 'windows-venv-redirector-v1')
        and isinstance(command, dict) and type(broker.get('commandProcessId')) is int,
        'New combat runs require the broker suspended-command witness')
    if worker.get('parentProcessId') == broker.get('runnerProcessId'):
        require(contract['kind'] == 'direct-python-v1',
                'A venv redirector cannot be promoted to the base worker')
        require('launchAncestry' not in worker, 'Direct worker retained a contradictory ancestry')
        if command is not None or 'commandProcessId' in broker:
            validate_identity(command, worker.get('windowsSessionId'))
            require(isinstance(command, dict) and command.get('processId') == broker.get('commandProcessId') == worker.get('processId')
                and command.get('parentProcessId') == broker.get('runnerProcessId')
                and command.get('windowsSessionId') == worker.get('windowsSessionId'), 'Direct command identity differs')
            require(worker.get('processIdentity') == command
                and (contract is None or Path(command['executable']) == Path(contract['executable'])),
                'Direct process creation/image witness differs')
        return
    require(isinstance(contract, dict) and contract.get('kind') == 'windows-venv-redirector-v1',
            'Worker is not a direct broker child and lacks a pinned venv contract')
    chain = worker.get('launchAncestry')
    validate_chain(chain, contract, worker.get('windowsSessionId'))
    current, shim, runner = chain
    require(current['processId'] == worker.get('processId') and current['parentProcessId'] == worker.get('parentProcessId')
        and current == worker.get('processIdentity')
        and shim == command and shim['processId'] == broker.get('commandProcessId')
        and runner['processId'] == broker.get('runnerProcessId'), 'Broker did not create this exact venv command/worker chain')
