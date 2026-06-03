from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from jose import jwt


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate S2S JWT token")
    parser.add_argument("--secret", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--algorithm", default="HS256")
    parser.add_argument("--ttl-minutes", type=int, default=60)
    args = parser.parse_args()

    payload = {
        "service": args.service,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=args.ttl_minutes),
    }
    token = jwt.encode(payload, args.secret, algorithm=args.algorithm)
    print(token)


if __name__ == "__main__":
    main()
