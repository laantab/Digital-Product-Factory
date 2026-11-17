"""Copy intermediate files before a work unit can be marked complete."""
from dataclasses import dataclass, replace
from pathlib import Path
import os
import uuid

from .publishing import verified_file
from .worker import Repairable


def r2_storage():
    from services.storage.r2 import R2Driver
    return R2Driver()


def receipts(value):
    if isinstance(value, dict):
        if {'key','sha256','size'} <= set(value):
            yield value
        else:
            for child in value.values():
                yield from receipts(child)
    elif isinstance(value, list):
        for child in value:
            yield from receipts(child)


def object_key(receipt):
    checksum = receipt['sha256']
    if not isinstance(checksum,str) or len(checksum)!=64 or any(c not in '0123456789abcdef' for c in checksum):
        raise ValueError('Invalid file receipt')
    return 'ebook-v2-work/'+checksum


def restore(root, value, storage):
    import hashlib
    root = Path(root).resolve()
    for item in receipts(value):
        path = (root/item['key']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Invalid work file location')
        try:
            verified_file(root,item)
            continue
        except (OSError,ValueError):
            pass
        data = storage.get(object_key(item))
        if len(data)!=item['size'] or hashlib.sha256(data).hexdigest()!=item['sha256']:
            raise ValueError('Shared work file failed verification')
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.part')
        try:
            temporary.write_bytes(data)
            os.replace(temporary,path)
        finally:
            temporary.unlink(missing_ok=True)


def preserve(root, value, storage):
    for item in receipts(value):
        data = verified_file(root,item)
        key = object_key(item)
        if not storage.verify(key,expected_checksum=item['sha256'],expected_size=item['size']):
            storage.put(key,data)
        if not storage.verify(key,expected_checksum=item['sha256'],expected_size=item['size']):
            raise ValueError('Shared work file failed readback')


@dataclass
class DurableHandler:
    handler: object
    validator: object
    storage_factory: object

    def __call__(self,payload,repair):
        storage = self.storage_factory()
        try:
            restore(payload['root'],payload,storage)
        except Exception as exc:
            raise Repairable('SHARED_STORAGE_UNAVAILABLE') from exc
        output = self.handler(payload,repair)
        if not self.validator(output):
            raise Repairable('VALIDATION_FAILED',output)
        try:
            preserve(payload['root'],output,storage)
        except Exception as exc:
            raise Repairable('SHARED_STORAGE_UNAVAILABLE') from exc
        return output


def install(books,storage_factory=r2_storage):
    for stage in ('visuals','export'):
        policy = books.policies[stage]
        books.policies[stage] = replace(policy,version=policy.version+'-shared-1',
            handler=DurableHandler(policy.handler,policy.validator,storage_factory),
            repairs={**policy.repairs,'SHARED_STORAGE_UNAVAILABLE':('rebuild',)})
