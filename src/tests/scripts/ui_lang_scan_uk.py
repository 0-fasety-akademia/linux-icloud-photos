# GTK_SCRIPT: uruchamia skrypt z oknami (runner potrzebuje wyświetlacza)
import os, runpy
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_lang_scan.py"), run_name="__main__")
