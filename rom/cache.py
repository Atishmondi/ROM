"""Resume stateless pose inference after interruption without losing completed frames."""
import json
from pathlib import Path
from types import SimpleNamespace


class CachedEstimator:
    def __init__(self, factory, path, metadata):
        self.factory, self.path = factory, Path(path)
        self.model = None
        self.cursor = 0
        self.records = []
        self.last_status = 'no_pose'
        self.last_disagreement = {}
        self.max_disagreement = metadata.get('max_disagreement')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            lines = self.path.read_text().splitlines()
            if not lines or json.loads(lines[0]) != {'metadata': metadata}:
                raise ValueError(f'Inference cache belongs to different input/model/settings: {self.path}')
            for index, line in enumerate(lines[1:]):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    if index != len(lines)-2: raise
                    break  # A partial final write after interruption is safe to discard.
                self.records.append(record)
        with self.path.open('w') as stream:
            stream.write(json.dumps({'metadata': metadata})+'\n')
            for record in self.records: stream.write(json.dumps(record, allow_nan=False)+'\n')
        self.stream = self.path.open('a', buffering=1)

    def detect(self, rgb, timestamp_ms):
        if self.cursor < len(self.records):
            record = self.records[self.cursor]
            if record['timestamp_ms'] != timestamp_ms:
                raise ValueError('Inference cache frame timestamps differ from video')
        else:
            if self.model is None: self.model = self.factory()
            landmarks = self.model.detect(rgb, timestamp_ms)
            record = {'timestamp_ms': timestamp_ms,
                      'status': self.model.last_status,
                      'disagreement': self.model.last_disagreement,
                      'landmarks': [vars(point) for point in landmarks] if landmarks else None}
            self.stream.write(json.dumps(record, allow_nan=False)+'\n')
            self.stream.flush()
        self.cursor += 1
        self.last_status = record['status']
        self.last_disagreement = record['disagreement']
        return [SimpleNamespace(**point) for point in record['landmarks']] if record['landmarks'] else None

    def close(self):
        self.stream.close()
        if self.model is not None: self.model.close()
