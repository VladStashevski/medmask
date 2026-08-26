from __future__ import annotations

import sys


def _report(message: object, stream=None) -> None:
    """Печатает, если есть куда.

    В оконной сборке PyInstaller stdout и stderr отсутствуют, и обычный print
    роняет программу. В windowed-режиме упавший процесс показывает модальное
    окно с трейсбеком, которое некому закрыть, — так пакетный режим зависал.
    """
    target = stream or sys.stdout
    if target is None:
        return
    try:
        print(message, file=target)
        target.flush()
    except (ValueError, OSError):
        pass


def run() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--batch":
        from medmask.batch import MedMaskError, process_folder

        try:
            result = process_folder(sys.argv[2])
        except MedMaskError as error:
            _report(error, sys.stderr)
            return 1
        except Exception:  # noqa: BLE001 — наружу не должны попасть пути и имена
            _report("Не удалось завершить обработку.", sys.stderr)
            return 1
        _report(result.output_dir)
        return 0

    from medmask.launcher import main

    main()
    return 0


if __name__ == "__main__":
    # Обязательно для spawn-worker'ов в оконной сборке PyInstaller: без этого
    # дочерний процесс повторно запускает GUI вместо выполнения задания.
    import multiprocessing

    multiprocessing.freeze_support()
    raise SystemExit(run())
