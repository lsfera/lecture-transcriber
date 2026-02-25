try:
    from .app import main
except ImportError:
    from lecture_transcriber.app import main


if __name__ == "__main__":
    main()
