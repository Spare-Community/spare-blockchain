import os
from pathlib import Path

DEFAULT_ROOT_PATH = Path(os.path.expanduser(os.getenv("SPARE_ROOT", "~/.spare/mainnet"))).resolve()
STANDALONE_ROOT_PATH = Path(
    os.path.expanduser(os.getenv("SPARE_STANDALONE_WALLET_ROOT", "~/.spare/standalone_wallet"))
).resolve()

DEFAULT_KEYS_ROOT_PATH = Path(os.path.expanduser(os.getenv("SPARE_KEYS_ROOT", "~/.spare_keys"))).resolve()
