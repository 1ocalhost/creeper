import sys


def main():
    from creeper.env import MAIN_DIR
    sys.path.append(str(MAIN_DIR / 'third_party'))

    from creeper.app import App
    App().run()


main()
