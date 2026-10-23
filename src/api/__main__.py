"""Entry point for `python -m src.api` and for the packaged dimaagi-backend.exe (see dimaagi-backend.spec)."""
from src.api.app import main

if __name__ == "__main__":
    main()
