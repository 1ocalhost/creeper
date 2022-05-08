import sys


def main():
    from creeper.env import MAIN_DIR
    sys.path.append(str(MAIN_DIR / 'third_party'))

    if not (MAIN_DIR / 'scripts').exists():
        sys.path.append(str(MAIN_DIR.parent))

    from creeper.app import App
    App().run()


main()
