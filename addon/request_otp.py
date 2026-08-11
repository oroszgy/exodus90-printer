"""Send the Exodus 90 OTP email without a stdin prompt.

The CLI's `login` command sends the code itself and then prompts for it;
this helper only triggers the email so the add-on can direct the user to
paste the code into the `login_code` config option.
"""

from __future__ import annotations

import sys

from exodus90_printer.auth import request_otp
from exodus90_printer.client import ExodusClient
from exodus90_printer.config import load_settings


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: request_otp.py <email>", file=sys.stderr)
        return 2
    settings = load_settings()
    with ExodusClient(settings) as client:
        request_otp(client, sys.argv[1])
    print("OTP emailed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
