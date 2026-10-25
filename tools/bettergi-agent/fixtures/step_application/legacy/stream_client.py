"""Historical Bridge class as test data; never import or call its native constructor."""
class Bridge:
    """Serialize request/response pairs on the same-user local named pipe."""
    def __init__(self, name):
        if not re.fullmatch(r'BetterGI\.Agent\.[A-Za-z0-9_.-]{1,100}', name):
            raise ValueError('Use a local pipe name beginning BetterGI.Agent.')
        if os.name != 'nt':
            raise RuntimeError('The BetterGI bridge requires Windows')
        self.handle = open('\\\\.\\pipe\\' + name, 'r+b', buffering=0)
        self.lock = threading.Lock()
        try:
            self.hello, payload = self._read()
            if (self.hello.get('version') != 1 or self.hello.get('type') != 'hello' or payload
                    or not self.hello.get('sessionId') or not self.hello.get('ownerEpoch')
                    or self.hello.get('goalVersion') != 1):
                raise ValueError('Unsupported BetterGI bridge handshake')
        except Exception:
            self.handle.close()
            raise

    def _exact(self, length):
        chunks = bytearray()
        while len(chunks) < length:
            chunk = self.handle.read(length-len(chunks))
            if not chunk:
                raise EOFError('BetterGI disconnected; input owner must release held input')
            chunks.extend(chunk)
        return bytes(chunks)

    def _read(self):
        length = struct.unpack('<I', self._exact(4))[0]
        if not 0 < length <= 4 * 1024 * 1024:
            raise ValueError('Invalid JSON packet length')
        raw_header = self._exact(length)
        if getattr(self, '_step_application_intake', None) is None:
            message = json.loads(raw_header)
        else:
            from step_application_transport import parse_header
            message = parse_header(raw_header)
        if not isinstance(message, dict):
            raise ValueError('Expected a JSON packet object')
        size = message.get('payloadBytes', 0)
        if type(size) is not int or not 0 <= size <= 32 * 1024 * 1024:
            raise ValueError('Invalid image packet length')
        return message, self._exact(size) if size else b''

    def request(self, command, **kwargs):
        payload = dict(version=1, command=command, sessionId=self.hello['sessionId'],
                       ownerEpoch=self.hello['ownerEpoch'], goalVersion=self.hello['goalVersion'], **kwargs)
        encoded = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode('utf-8')
        if len(encoded) > 65536:
            raise ValueError('Request exceeds the server JSON limit')
        with self.lock:
            intake = getattr(self, '_step_application_intake', None)
            if intake is None:
                packet = memoryview(struct.pack('<I', len(encoded)) + encoded)
                while packet:
                    written = self.handle.write(packet)
                    if not written:
                        raise EOFError('BetterGI disconnected while sending a request')
                    packet = packet[written:]
                return self._read()
            # No production factory installs this stage until native-owner integration is qualified.
            write_attempted = False
            try:
                payload = intake.prepare(payload)
                encoded = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode('utf-8')
                if len(encoded) > 65536:
                    raise ValueError('Request exceeds the server JSON limit')
                packet = memoryview(struct.pack('<I', len(encoded)) + encoded)
                while packet:
                    write_attempted = True
                    written = self.handle.write(packet)
                    if not written:
                        raise EOFError('BetterGI disconnected while sending a request')
                    packet = packet[written:]
                response, pixels = self._read()
                observed_client_ns = time.perf_counter_ns()
                intake.receive(payload, response, observed_client_ns=observed_client_ns)
                return response, pixels
            except BaseException:
                try:
                    intake.failed(payload, write_attempted=write_attempted)
                except BaseException:
                    intake.ledger.uncertain('transport_failure_classification_failed')
                raise
