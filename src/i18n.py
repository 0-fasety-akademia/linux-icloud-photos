"""Język interfejsu: polski, angielski, niemiecki i ukraiński.

Teksty w kodzie są po polsku i owinięte w tr(...). Dla polskiego tr() zwraca je bez zmian. Dla pozostałych
języków polski napis najpierw zamieniany jest na angielski (tabela EN w tym pliku), a niemiecki i ukraiński
tłumaczą dalej angielski tekst (tabele DE i UK w i18n_de.py oraz i18n_uk.py, kluczem jest angielski napis).
Brak wpisu = pokazuje się angielski (a w angielskim polski) oryginał; sprawdza to tools/check_i18n.py.

Kolejność wyboru języka:
  1. zmienna ICLOUD_PHOTOS_LANG=pl|en|de|uk (np. do testów),
  2. ustawienie „language” w config.json (auto|pl|en|de|uk; zmieniane w Ustawieniach),
  3. język systemu (LANGUAGE, LC_ALL, LC_MESSAGES, LANG, na końcu locale): polski dla polskiego systemu,
     w pozostałych przypadkach angielski. Niemiecki i ukraiński są opcjonalne - tylko z 1. lub 2.

Szablony z podstawieniami używają numerowanych miejsc ({0}, {1}...), żeby tłumaczenie mogło
zmienić ich kolejność. Gdy ten sam polski napis znaczy co innego, dopisujemy kontekst po
pionowej kresce, np. "Wideo|typ" (po polsku kontekst jest obcinany).
"""
from __future__ import annotations

import json
import locale
import os
from pathlib import Path

LANGUAGES = ("pl", "en", "de", "uk")


def _config_language() -> str:
    try:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        path = base / "linux-icloud-photos" / "config.json"
        if not path.exists():  # ustawienia sprzed zmiany nazwy (przeniesie je backend)
            path = base / "icloud-photos-linux" / "config.json"
        data = json.loads(path.read_text())
        return str(data.get("language", "auto")).lower()
    except Exception:  # noqa: BLE001
        return "auto"


def detect() -> str:
    forced = os.environ.get("ICLOUD_PHOTOS_LANG", "").strip().lower()
    if forced[:2] in LANGUAGES:
        return forced[:2]
    cfg = _config_language()
    if cfg in LANGUAGES:
        return cfg
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "").strip()
        if not value:
            continue
        first = value.split(":")[0].strip().lower()
        if first in ("", "c", "posix"):
            continue
        return "pl" if first.startswith("pl") else "en"
    try:
        code = (locale.getlocale()[0] or "").lower()
    except Exception:  # noqa: BLE001
        code = ""
    return "pl" if code.startswith("pl") else "en"


LANG = detect()


def _load_table():
    """Tabela dla niemieckiego/ukraińskiego (ładowana tylko, gdy potrzebna)."""
    if LANG == "de":
        from i18n_de import DE
        return DE
    if LANG == "uk":
        from i18n_uk import UK
        return UK
    return None


def tr(text: str) -> str:
    """Tłumaczy polski napis na język interfejsu."""
    plain = text.split("|", 1)[0] if "|" in text else text
    if LANG == "pl":
        return plain
    en = EN.get(text, plain)
    return _TABLE.get(en, en) if _TABLE else en


def plural(n: int, pl: tuple, en: tuple, de: tuple | None = None, uk: tuple | None = None) -> str:
    """Odmiana liczebnika: pl = (1, 2-4, 5+), uk = (1, 2-4, 5+), en/de = (pojedyncza, mnoga)."""
    if LANG == "pl" or (LANG == "uk" and uk):
        forms = pl if LANG == "pl" else uk
        if n % 10 == 1 and n % 100 != 11 and (LANG == "uk" or n == 1):
            return forms[0]
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return forms[1]
        return forms[2]
    forms = de if (LANG == "de" and de) else en
    return forms[0] if n == 1 else forms[1]


_MONTHS = {
    "pl": ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec",
           "sierpień", "wrzesień", "październik", "listopad", "grudzień"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
           "September", "Oktober", "November", "Dezember"],
    "uk": ["січень", "лютий", "березень", "квітень", "травень", "червень", "липень",
           "серпень", "вересень", "жовтень", "листопад", "грудень"],
}
_ABBR = {
    "pl": ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "de": ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
    "uk": ["січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"],
}


def month_names() -> list:
    return list(_MONTHS[LANG])


def month_abbr() -> list:
    return list(_ABBR[LANG])


EN = {
    # --- presety widoku ---
    "Małe": "Small", "Standardowe": "Standard", "Duże": "Large", "Bardzo duże": "Extra large",
    # --- podgląd zdjęcia ---
    "Podgląd": "Preview",
    "Odtwórz (Spacja / Enter)": "Play (Space / Enter)",
    "Pomniejsz (Ctrl −)": "Zoom out (Ctrl −)",
    "Powiększ (Ctrl +)": "Zoom in (Ctrl +)",
    "Dopasuj": "Fit",
    "Dopasuj do okna (Ctrl 0)": "Fit to window (Ctrl 0)",
    "Informacje o zdjęciu (I)": "Photo information (I)",
    "Dodaj do albumu (A)": "Add to album (A)",
    "(Spacja = pauza, M = mpv)": "(Space = pause, M = mpv)",
    "(Spacja/Enter/▶ = odtwórz)": "(Space/Enter/▶ = play)",
    "(L/Spacja = Live)": "(L/Space = Live)",
    "[błąd: {0}]": "[error: {0}]",
    "(oryginał niedostępny: brak dekodera HEIC?)": "(original unavailable: no HEIC decoder?)",
    "(oryginał)": "(original)",
    "(wysłano na TV)": "(sent to TV)",
    "[wbudowany odtwarzacz nie wystartował]": "[built-in player did not start]",
    "[GStreamer nie odtworzył - brak kodeka?]": "[GStreamer could not play it - missing codec?]",
    "[brak części wideo tego Live Photo]": "[this Live Photo has no video part]",
    "(pobieram Live Photo…)": "(downloading the Live Photo…)",
    "[brak wersji wideo]": "[no video version]",
    "(pobieranie filmu…)": "(downloading video…)",
    "Wysyłanie na: {0}": "Sending to: {0}",
    "{0}: brak połączenia z Chromecastem ({1}:{2}): {3}": "{0}: no connection to the Chromecast ({1}:{2}): {3}",
    "Pokaz slajdów": "Slideshow",
    # --- wysyłanie do iCloud ---
    "Prześlij do iCloud": "Upload to iCloud",
    "Pliki do wysłania: {0}": "Files to upload: {0}",
    "Dodaj do albumu:": "Add to album:",
    "Tylko biblioteka (bez albumu)": "Library only (no album)",
    "Anuluj": "Cancel",
    "Prześlij": "Upload",
    "Wysyłanie 0/{0}…": "Uploading 0/{0}…",
    "Wysyłanie {0}/{1}…": "Uploading {0}/{1}…",
    "Wysłano {0} z {1}.": "Uploaded {0} of {1}.",
    "\nBłędy:\n": "\nErrors:\n",
    "Zamknij": "Close",
    # --- informacje o zdjęciu ---
    "Informacje o zdjęciu": "Photo information",
    "Wideo|typ": "Video",
    "Zdjęcie": "Photo",
    "Nazwa pliku": "File name",
    "Typ": "Type",
    "Data wykonania": "Date taken",
    "Dodano do iCloud": "Added to iCloud",
    "Wymiary": "Dimensions",
    "Rozmiar oryginału": "Original size",
    "Dane aparatu: wczytuję…": "Camera data: loading…",
    "Lokalizacja": "Location",
    "Pokaż na mapie (OpenStreetMap)": "Show on map (OpenStreetMap)",
    "Pokaż nazwę miejsca": "Show place name",
    "Wysyła współrzędne do OpenStreetMap (Nominatim)": "Sends the coordinates to OpenStreetMap (Nominatim)",
    "Szukam…": "Searching…",
    "Nie udało się: {0}": "Failed: {0}",
    "Nie udało się wczytać danych aparatu: {0}": "Could not load the camera data: {0}",
    "Podgląd z iCloud nie zawiera danych aparatu.": "The iCloud preview contains no camera data.",
    "Oryginał nie zawiera danych EXIF.": "The original contains no EXIF data.",
    "Wczytaj z oryginału (większy plik)": "Load from the original (larger file)",
    "Pobieram oryginał…": "Downloading the original…",
    "Telefon / aparat": "Phone / camera",
    "Obiektyw": "Lens",
    "Ekspozycja": "Exposure",
    "Data (EXIF)": "Date (EXIF)",
    # --- albumy w menu ---
    "Wszystkie zdjęcia": "All Photos", "Ulubione": "Favorites", "Wideo": "Videos",
    "Zrzuty ekranu": "Screenshots", "Selfie": "Selfies", "Portrety": "Portraits",
    "Panoramy": "Panoramas", "Serie": "Bursts", "Slow-motion": "Slo-mo",
    "Poklatkowe": "Time-lapse", "Długa ekspozycja": "Long Exposure", "Animacje": "Animated",
    "Ukryte": "Hidden", "Ostatnio usunięte": "Recently Deleted",
    # --- ustawienia ---
    "Ustawienia": "Settings",
    "Limit pamięci podręcznej (GB)": "Cache size limit (GB)",
    "Zajęte teraz": "Used now",
    "Wyczyść pamięć podręczną": "Clear cache",
    "Odtwarzacz filmów": "Video player",
    "Automatycznie (mpv, jeśli jest)": "Automatic (mpv if available)",
    "Wbudowany odtwarzacz": "Built-in player",
    "Zawsze mpv": "Always mpv",
    "znaleziono": "found",
    "NIE znaleziono (sudo apt install mpv)": "NOT found (sudo apt install mpv)",
    "Pamięć podręczna wyczyszczona": "Cache cleared",
    "Nie udało się wyczyścić: {0}": "Could not clear the cache: {0}",
    "Język (wymaga ponownego uruchomienia)": "Language (restart required)",
    "Automatycznie (język systemu)": "Automatic (system language)",
    "Zmiana języka zadziała po ponownym uruchomieniu aplikacji": "The language change takes effect after restarting the app",
    # --- dodawanie do albumu ---
    "Zdjęcie „{0}” jest już w albumie „{1}”.": "The photo “{0}” is already in the album “{1}”.",
    "Wszystkie zaznaczone zdjęcia ({0}) są już w albumie „{1}”.": "All selected photos ({0}) are already in the album “{1}”.",
    "Dodano {0} z {1} do albumu „{2}”.": "Added {0} of {1} to the album “{2}”.",
    "\nJuż w albumie „{0}”: {1} ({2}{3}).": "\nAlready in the album “{0}”: {1} ({2}{3}).",
    " i {0} innych": " and {0} more",
    " ({0} już tam było)": " ({0} were already there)",
    "ostatnio": "recent",
    "Dodaj do albumu": "Add to album",
    "Zdjęcia do dodania: {0}": "Photos to add: {0}",
    "Szukaj albumu…": "Search albums…",
    "Dodaj": "Add",
    "Sprawdzam, czy zdjęcia już są w albumie…": "Checking whether the photos are already in the album…",
    "Dodawanie {0}/{1}…": "Adding {0}/{1}…",
    # --- parowanie AirPlay ---
    "Parowanie: {0}": "Pairing: {0}",
    "Na ekranie telewizora pojawi się kod PIN.\nWpisz go poniżej.": "A PIN code will appear on the TV screen.\nEnter it below.",
    "Łączę z urządzeniem…": "Connecting to the device…",
    "Sparuj": "Pair",
    "Nie udało się rozpocząć parowania: {0}": "Could not start pairing: {0}",
    "Wpisz PIN z ekranu TV.": "Enter the PIN shown on the TV.",
    "Urządzenie nie pokazuje PIN-u - wpisz kod, którego oczekuje.": "The device does not show a PIN - enter the code it expects.",
    "Parowanie…": "Pairing…",
    "Zły PIN albo błąd parowania: {0}": "Wrong PIN or pairing error: {0}",
    # --- okno główne: nagłówek ---
    "Mniejsze miniatury (Ctrl −)": "Smaller thumbnails (Ctrl −)",
    "Większe miniatury (Ctrl +)": "Larger thumbnails (Ctrl +)",
    "Widok siatki": "Grid view",
    "Układ": "Layout",
    "Kafelki (kwadraty)": "Tiles (squares)",
    "Rzędy (jak w Google Photos)": "Rows (like Google Photos)",
    "Oryginalne proporcje (bez przycinania)": "Original proportions (no cropping)",
    "Dodaj zdjęcia do iCloud (możesz też przeciągnąć pliki do okna)": "Add photos to iCloud (you can also drag files into the window)",
    "Informacje o zdjęciu (ostatnio otwartym lub klikniętym prawym przyciskiem)": "Photo information (last opened or right-clicked)",
    "Zaznaczanie wielu zdjęć (Ctrl+klik)": "Select multiple photos (Ctrl+click)",
    # --- logowanie ---
    "Zaloguj się do iCloud": "Sign in to iCloud",
    "Apple ID (e-mail)": "Apple ID (email)",
    "Hasło": "Password",
    "Kod 2FA (6 cyfr)": "2FA code (6 digits)",
    "Zaloguj": "Sign in",
    "Kopiuj błąd": "Copy error",
    "Sesja wygasła - loguję ponownie…": "Session expired - signing in again…",
    "Logowanie z zapisanej sesji…": "Signing in from the saved session…",
    "Skopiowano ✓": "Copied ✓",
    "\n\nApple chwilowo odrzuca logowanie (503 Service Temporarily Unavailable). Odczekaj kilkanaście minut i spróbuj raz - wielokrotne próby mogą wydłużyć blokadę.": "\n\nApple is temporarily rejecting sign-ins (503 Service Temporarily Unavailable). Wait a few minutes and try once - repeated attempts may extend the block.",
    "Weryfikacja kodu…": "Verifying the code…",
    "Podaj Apple ID i hasło.": "Enter your Apple ID and password.",
    "Logowanie…": "Signing in…",
    "Błąd logowania: ": "Sign-in error: ",
    "Sesja wygasła. ": "Session expired. ",
    "Wpisz kod z zaufanego urządzenia Apple.": "Enter the code from your trusted Apple device.",
    "Błąd: zły kod albo problem z weryfikacją: ": "Error: wrong code or verification problem: ",
    "Sesja wygasła. Zaloguj się ponownie.": "Session expired. Please sign in again.",
    # --- menu albumów i lista ---
    "Szukaj albumu": "Search album",
    "Przejdź do daty": "Go to date",
    "Typy mediów": "Media types",
    "Moje albumy": "My albums",
    "Przejdź do: {0}": "Go to: {0}",
    "Błąd albumów: {0}": "Albums error: {0}",
    "Moje albumy ({0})": "My albums ({0})",
    "Szukam daty…": "Looking for the date…",
    "Błąd listy: {0}": "List error: {0}",
    "Kolejność: najnowsze najpierw (kliknij, aby odwrócić)": "Order: newest first (click to reverse)",
    "Kolejność: najstarsze najpierw (kliknij, aby odwrócić)": "Order: oldest first (click to reverse)",
    "Przejdź": "Go",
    "Datę można też wpisać w polu „Szukaj albumu” (np. 08.2024).": "You can also type a date in the “Search album” box (e.g. 08.2024).",
    "Biblioteka jeszcze się ładuje": "The library is still loading",
    "Przechodzę do: {0}…": "Going to: {0}…",
    # --- wysyłanie na TV ---
    "Wyślij na TV (DLNA/UPnP)": "Send to TV",
    "Szukaj ponownie": "Search again",
    "Zatrzymaj wysyłanie": "Stop sending",
    "AirPlay: wideo po sparowaniu PIN-em; zdjęcia eksperymentalnie.": "AirPlay: video after PIN pairing; photos are experimental.",
    "Szukam telewizorów w sieci…": "Looking for TVs on the network…",
    "Nie znaleziono urządzeń DLNA w tej sieci. Upewnij się, że TV jest włączony, w tej samej sieci, a DLNA/udostępnianie włączone.": "No DLNA devices found on this network. Make sure the TV is on, on the same network, and that DLNA/media sharing is enabled.",
    "Znaleziono: {0}. Wybierz urządzenie:": "Found: {0}. Choose a device:",
    "Wysyłanie na: {0}. Otwórz zdjęcie lub włącz pokaz.": "Sending to: {0}. Open a photo or start a slideshow.",
    "Zatrzymano wysyłanie na TV": "Stopped sending to the TV",
    # --- wysyłanie plików ---
    "Brak obsługiwanych plików (JPG, PNG, HEIC, GIF, TIFF, DNG, MOV, MP4)": "No supported files (JPG, PNG, HEIC, GIF, TIFF, DNG, MOV, MP4)",
    "Pominięto {0} plik(ów) nieobsługiwanego typu": "Skipped {0} file(s) of an unsupported type",
    "Wybierz zdjęcia i wideo do wysłania": "Choose photos and videos to upload",
    "Zdjęcia i wideo": "Photos and videos",
    "Zdjęcia wysłane do iCloud": "Photos uploaded to iCloud",
    # --- menu prawego przycisku ---
    "Kliknij zdjęcie prawym przyciskiem i wybierz „Informacje”": "Right-click a photo and choose “Information”",
    "Informacje": "Information",
    "Odtwórz w mpv": "Play in mpv",
    "Wyślij na TV": "Send to TV",
    "Zapisz oryginał jako…": "Save original as…",
    "Kopiuj nazwę pliku": "Copy file name",
    "Skopiowano nazwę pliku": "File name copied",
    "Błąd zapisu: {0}": "Save error: {0}",
    "Zapisano: {0}": "Saved: {0}",
    # --- zaznaczanie ---
    "Zaznaczono: 0": "Selected: 0",
    "Zaznaczono: {0}": "Selected: {0}",
    # --- tryb wyboru (--pick) ---
    "Tryb wyboru: biblioteka jest tylko do odczytu": "Pick mode: the library is read-only",
    "Zaznacz zdjęcia i filmy, potem kliknij „Wybierz”": "Select photos and videos, then click \"Choose\"",
    "Wybierz": "Choose",
    "Wybierz ({0})": "Choose ({0})",
    "Zaznaczono: {0} z {1}": "Selected: {0} of {1}",
    "Przygotowuję…": "Preparing…",
    "Przygotowuję {0}/{1}…": "Preparing {0}/{1}…",
    "Nie udało się przygotować plików: {0}": "Could not prepare the files: {0}",
    "Można wybrać najwyżej {0} plików naraz": "You can choose at most {0} files at once",
    "Zaznacz wszystko": "Select all",
    "Wyczyść": "Clear",
    "Zakończ zaznaczanie (Esc)": "Finish selecting (Esc)",
    "Zapisz oryginały…": "Save originals…",
    "Usuń z ulubionych": "Remove from favourites",
    "Dodaj do ulubionych": "Add to favourites",
    "Do albumu…": "To album…",
    "Najpierw zaznacz zdjęcia": "Select photos first",
    "Nie masz jeszcze własnych albumów": "You have no albums of your own yet",
    "Dodano do ulubionych: {0} z {1}": "Added to favourites: {0} of {1}",
    "Usunięto z ulubionych: {0} z {1}": "Removed from favourites: {0} of {1}",
    ", błędy: {0} (log)": ", errors: {0} (log)",
    "Zmiana": "Updating",
    "Zapis": "Saving",
    "Wybierz folder na oryginały": "Choose a folder for the originals",
    "Zapisano oryginały: {0} z {1} w {2}": "Saved originals: {0} of {1} in {2}",
    " (błędy: {0}, log)": " (errors: {0}, log)",
    # --- album: menu dodawania ---
    "Dodaj do albumu „{0}”{1}": "Add to album “{0}”{1}",
    "Dodaj do albumu…": "Add to album…",
    "Dodaj do innego albumu…": "Add to another album…",
    "Album „{0}” nie jest już dostępny": "The album “{0}” is no longer available",
    "Dodaję do albumu „{0}”…": "Adding to the album “{0}”…",
    # --- wideo ---
    "Streaming filmu nie powiódł się, pobieram go do pamięci podręcznej…": "Streaming the video failed, downloading it to the cache…",
    "Nie udało się odtworzyć filmu: {0}  [log: {1}]": "Could not play the video: {0}  [log: {1}]",
    "Brak wersji wideo do odtworzenia": "No playable video version",
    "Zainstaluj mpv: sudo apt install mpv": "Install mpv: sudo apt install mpv",
    "mpv zakończył się błędem ({0}): {1}  [log: {2}]": "mpv exited with an error ({0}): {1}  [log: {2}]",
    "{0} (kod {1})": "{0} (code {1})",
    # --- backend ---
    "Konto wymaga starszej weryfikacji 2SA (zaufane urządzenie) - ta wersja aplikacji obsługuje tylko 2FA z kodem.": "This account uses legacy two-step verification (trusted devices) - this version of the app only supports 2FA with a code.",
    "pusta odpowiedź": "empty response",
    "nieobsługiwany typ pliku: ": "unsupported file type: ",
    "iCloud nie przyjął pliku (ten album nie przyjmuje zdjęć?)": "iCloud did not accept the file (this album does not accept photos?)",
    "Nie udało się sprawdzić, czy zdjęcia już są w albumie - dodano bez sprawdzania.": "Could not check whether the photos are already in the album - added without checking.",
    "{0}: album nie przyjęło zdjęcia": "{0}: the album did not accept the photo",
    "film jest za duży do pobrania do cache ({0} MB); użyj „Zapisz oryginał jako…”": "the video is too large to download to the cache ({0} MB); use “Save original as…”",
    "pusta odpowiedź przy pobieraniu filmu": "empty response while downloading the video",
    "pusta odpowiedź przy pobieraniu Live Photo": "empty response while downloading the Live Photo",
    "brak oryginału": "no original available",
    "brak wersji do pobrania": "no version available to download",
    "pusty album": "empty album",
    "(brak nazwy)": "(no name)",
    "{0}: nie zmieniono": "{0}: not changed",
    # --- wersje ---
    "Ta aplikacja wymaga GTK {0}.{1} i libadwaita {2}.{3} lub nowszych (masz GTK {4}.{5} i libadwaita {6}.{7}). Zaktualizuj system.": "This application needs GTK {0}.{1} and libadwaita {2}.{3} or newer (you have GTK {4}.{5} and libadwaita {6}.{7}). Please update your system.",
    "Zainstalowana wersja pyicloud ({0}) różni się od przetestowanej ({1}). Jeśli coś nie działa, zainstaluj przetestowaną.": "The installed pyicloud version ({0}) differs from the tested one ({1}). If something does not work, install the tested version.",
    # --- odświeżanie biblioteki ---
    "Odśwież bibliotekę (F5)": "Refresh the library (F5)",
    "Odświeżam bibliotekę…": "Refreshing the library…",
    "Biblioteka odświeżona": "Library refreshed",
    "Nie udało się odświeżyć: {0}": "Could not refresh: {0}",
    "Nie znaleziono albumu „{0}”": "Album “{0}” not found",
    "Nieczytelna data: {0}": "Unreadable date: {0}",
    # --- pokaz slajdów w podglądzie, przezroczystość ---
    "Pokaz slajdów od tego zdjęcia": "Slideshow from this photo",
    "Przezroczystość okna": "Window transparency",
    "Motyw": "Theme",
    "Systemowy": "System",
    "Wyłączona": "Off",
    "Rozmyte tło ze zdjęć. Rozmycie pulpitu za oknem robi tylko system (np. rozszerzenie Blur my Shell).": "Blurred background made from your photos. Blurring the desktop behind the window is done by the system only (for example the Blur my Shell extension).",
    # --- usuwanie zdjęć ---
    "W albumie „Ostatnio usunięte” nie można usuwać zdjęć tutaj": "Photos in “Recently Deleted” cannot be deleted here",
    "Usunąć to zdjęcie?": "Delete this photo?",
    "Usunąć zaznaczone zdjęcia ({0})?": "Delete the selected photos ({0})?",
    "Zdjęcia zostaną przeniesione do albumu „Ostatnio usunięte” w iCloud (Apple zwykle przechowuje je tam 30 dni) i znikną z biblioteki na wszystkich Twoich urządzeniach. Ta aplikacja nie ma przycisku przywracania - zrobisz to w aplikacji Zdjęcia lub na iCloud.com.": "The photos will be moved to the “Recently Deleted” album in iCloud (Apple usually keeps them there for 30 days) and disappear from the library on all your devices. This app has no restore button - use the Photos app or iCloud.com to restore them.",
    "Usuń": "Delete",
    "Usuwam zdjęcia…": "Deleting photos…",
    "Usuwanie {0}/{1}…": "Deleting {0}/{1}…",
    "Przeniesiono do „Ostatnio usunięte”: {0} z {1}": "Moved to “Recently Deleted”: {0} of {1}",
    "Nie usunięto żadnego zdjęcia": "No photo was deleted",
    ", błąd: {0}": ", error: {0}",
    "Usuń zaznaczone zdjęcia (Delete)": "Delete the selected photos (Delete)",
    "Usuń zdjęcie (Delete)": "Delete photo (Delete)",
    "Usuń…": "Delete…",
    "{0}: Apple nie potwierdziło usunięcia": "{0}: Apple did not confirm the deletion",
    # --- cast / AirPlay ---
    "{0}: {1} nie powiodło się: {2} {3}": "{0}: {1} failed: {2} {3}",
    "{0}: urządzenie nie jest sparowane": "{0}: the device is not paired",
    "{0}: nie udało się przygotować zdjęcia: {1}": "{0}: could not prepare the photo: {1}",
    "{0}: to urządzenie nie przyjmuje zdjęć przez AirPlay ({1}). Wideo i pokaz slajdów jako wideo działają tylko po sparowaniu.": "{0}: this device does not accept photos over AirPlay ({1}). Video works only after pairing.",
}

_TABLE = _load_table()
