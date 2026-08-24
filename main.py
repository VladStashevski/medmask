from __future__ import annotations

import sys


def run() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--batch":
        from medmask.batch import MedMaskError, process_folder

        try:
            result = process_folder(sys.argv[2])
        except MedMaskError as error:
            print(error, file=sys.stderr)
            return 1
        print(result.output_dir)
        return 0

    from medmask.app import main

    main()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
