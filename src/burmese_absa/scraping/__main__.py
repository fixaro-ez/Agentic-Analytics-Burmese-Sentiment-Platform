"""
Entry point so `python -m burmese_absa.scraping` runs the scraping CLI
(preserves the legacy invocation that pre-dated the package split).
"""
from .cli import main

if __name__ == "__main__":
    main()
