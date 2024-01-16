# Copyright © 2024. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.

import enum
import typing


class CertificateStoreLocation(enum.Enum):
    CURRENT_USER = 1
    LOCAL_MACHINE = 2

def codesign_file(filename: typing.Any, certificate: str, password: typing.Any, timestamp: typing.Optional[str] = None,
                  use_rfc3161: bool = False, use_sha256: bool = False) -> None: ...
def codesign_file_from_store(filename: typing.Any, store_location: CertificateStoreLocation, store_name: typing.Any,
                             store_cn: typing.Any, timestamp: typing.Optional[str] = None,
                             use_rfc3161: bool = False, use_sha256: bool = False) -> None: ...
