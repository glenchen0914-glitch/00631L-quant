from src.morning import run_morning
from src.morning_notify import main as notify


def main() -> None:
    run_morning()
    notify()


if __name__ == "__main__":
    main()
