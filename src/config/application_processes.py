"""Run the web server and durable scheduler under the container lifecycle."""
import signal
import subprocess
import sys
import threading


def main():
    stopped = threading.Event()
    children = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *args: stopped.set())
    try:
        children.append(subprocess.Popen([sys.executable, 'manage.py', 'run_application_scheduler']))
        children.append(subprocess.Popen(sys.argv[1:]))
        while not stopped.wait(1):
            for child in children:
                code = child.poll()
                if code is not None:
                    return code or 1
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    sys.exit(main())
