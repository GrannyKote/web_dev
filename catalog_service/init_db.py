from .database import init_db


def main() -> None:
    init_db()
    print("Catalog DB schema and missing tables are initialized.")


if __name__ == "__main__":
    main()
